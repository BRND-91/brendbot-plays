"""The map graph the travel loop routes over.

Edges come from two places: the ROM's full connection and warp tables (`world`,
rowe_rom.world_edges), which make every map routable before it is walked, and
the live connection reads the executor records as it moves (`adj`, persisted).
`visited` is what has been stood on. The graph answers two questions: the first
hop toward a map, and the next map to step into to uncover an unseen one.

A pass-through map (`passthrough`, rowe_rom.passthroughs) can lead back to the
map it was entered from, onto a part of it the player could not walk to (Route
104's halves either side of Petalburg Woods), so a route may re-enter its own
source through such a map and only such a map. A `blocked` set applies only to
the first hop, the one taken from where the player stands now.
"""
import hashlib
import json
import os

Node = tuple  # (map_group, map_num)
MAP_DYNAMIC = (127, 127)  # a dynamic-warp header: no edge, the real dest resolves at runtime


def _source_version(paths) -> str:
    """A token over the navigation sources' bytes. Editing any of them changes the token, so every
    gate recorded under the old bytes reads as a different version and _gate_shut grants it one retry."""
    h = hashlib.sha256()
    for p in sorted(paths):
        with open(p, "rb") as f:
            h.update(f.read())
    return "src:" + h.hexdigest()[:12]


_HERE = os.path.dirname(os.path.abspath(__file__))
# The crossing and routing modules. A gate carries the token of the sources that recorded it; editing
# any of these to fix a wedge changes the token, so _gate_shut reads the stale gate open and the walker
# retries the crossing once instead of the gate needing a manual cache clear. A fresh failure re-records
# it under the new token. Pre-token gates on disk load as version 0, which never matches, so they retry.
EXECUTOR_CAP_VERSION = _source_version(
    os.path.join(_HERE, n) for n in
    ("play.py", "map_graph.py", "script_decode.py", "planner.py", "routines.py", "nav.py"))


def _key(node: Node) -> str:
    return f"{node[0]},{node[1]}"


def _node(key: str) -> Node:
    g, n = key.split(",")
    return int(g), int(n)


class MapGraph:
    def __init__(self, path: str, world: dict | None = None, passthrough: dict | None = None,
                 script: dict | None = None, flags: set | None = None, ferry_hubs: set | None = None):
        self.path = path
        self.adj: dict[Node, set[Node]] = {}
        self.visited: set[Node] = set()
        self.gated: dict[tuple[Node, Node], frozenset] = {}
        self.gate_badges: dict[tuple[Node, Node], int] = {}
        self.gate_version: dict[tuple[Node, Node], int] = {}
        self.gate_reason: dict[tuple[Node, Node], str] = {}
        self.cur_badges: int = 0
        self.world: dict = {k: set(v) for k, v in (world or {}).items()}
        self.passthrough: dict = {k: set(v) for k, v in (passthrough or {}).items()}
        # NPC-interaction warps (script_decode.script_edges): a dest is a neighbor only while its
        # gate flags are all set, so the Seagallop ferry opens the Sevii block once its flag is earned.
        self.set_script(script or {})
        self.flags: set = set(flags or ())
        # Seagallop dock maps: a walk onto one is always a valid board, its onward reach is the
        # ferry menu drive, so a walk-bounce there is a driver miss _gate_shut must never seal.
        self.ferry_hubs: set = set(ferry_hubs or ())
        self.load()

    def set_script(self, script: dict) -> None:
        """Replace the script-warp layer, whole: it is a function of the held key items, so a Sevii
        ticket handed over mid-run re-derives it rather than patching one arm."""
        self.script: dict = {k: {d: frozenset(f) for d, f in v.items()} for k, v in script.items()}

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        with open(self.path) as f:
            data = json.load(f)
        self.visited = {_node(k) for k in data.get("visited", [])}
        self.adj = {_node(k): {_node(v) for v in vs} for k, vs in data.get("adj", {}).items()}
        self.gated = {}
        self.gate_badges = {}
        self.gate_version = {}
        self.gate_reason = {}
        for row in data.get("gated", []):
            edge = (_node(row[0]), _node(row[1]))
            self.gated[edge] = frozenset(row[2])
            if len(row) > 3 and row[3] is not None:
                self.gate_badges[edge] = row[3]
            self.gate_version[edge] = row[4] if len(row) > 4 else 0
            if len(row) > 5 and row[5] is not None:
                self.gate_reason[edge] = row[5]

    def save(self) -> None:
        gated_rows = []
        for (a, b), t in self.gated.items():
            row = [_key(a), _key(b), sorted(t), self.gate_badges.get((a, b)),
                   self.gate_version.get((a, b), 0), self.gate_reason.get((a, b))]
            gated_rows.append(row)
        data = {
            "visited": sorted(_key(n) for n in self.visited),
            "adj": {_key(k): sorted(_key(v) for v in vs) for k, vs in self.adj.items()},
            "gated": sorted(gated_rows, key=lambda e: (e[0], e[1])),
        }
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, self.path)

    def _script_dests(self, node: Node) -> set:
        """Script-warp destinations of node whose gate flags are all currently set."""
        return {d for d, gate in self.script.get(node, {}).items() if gate <= self.flags}

    def neighbors(self, node: Node) -> set:
        out = self.adj.get(node, set()) | self.world.get(node, set()) | self._script_dests(node)
        assert MAP_DYNAMIC not in out, f"{node} neighbors leaked dynamic warp {MAP_DYNAMIC}"
        return out

    def observe(self, here: Node, neighbors: list) -> list:
        """Record that `here` is visited and borders `neighbors`; return nodes seen for the first time."""
        before = set(self.adj)
        self.visited.add(here)
        self.adj.setdefault(here, set()).update(neighbors)
        # a neighbor is a known node even before it is walked, so routing can aim at it
        for nb in neighbors:
            self.adj.setdefault(nb, set())
        new = [n for n in self.adj if n not in before]
        self.save()
        return new

    def _gate_shut(self, here: Node, nb: Node, field_moves) -> bool:
        """An edge stays shut only while the field-move set and the badge count that recorded it
        both hold, so gaining an HM or a badge reopens it. A gate whose version differs from the
        current source token was recorded under different navigation code, so it reads open and the
        walker retries the crossing once; a fresh failure re-records it at the current token. A gate
        set directly in a test carries no version and is treated as current."""
        if nb in self.ferry_hubs:
            return False
        edge = (here, nb)
        if self.gated.get(edge) != field_moves:
            return False
        if self.gate_version.get(edge, EXECUTOR_CAP_VERSION) != EXECUTOR_CAP_VERSION:
            return False
        return self.gate_badges.get(edge, self.cur_badges) == self.cur_badges

    def _bfs(self, src: Node, is_goal, blocked=frozenset(), field_moves=frozenset()) -> Node | None:
        """First hop out of src along the shortest path to a node is_goal accepts, or None.
        A shut edge (see `_gate_shut`) is impassable at every hop, not just the first, so a
        route never threads through a border the walk already gave up on."""
        if is_goal(src):
            return src
        seen = set()
        frontier = [(src, None)]
        while frontier:
            cur, first = frontier.pop(0)
            if first is not None and is_goal(cur):
                return first
            for nb in sorted(self.neighbors(cur)):
                # a map's world layer can list itself (Four Island's in-map warps), and a hop onto
                # the map the walk stands on is no hop: with the real exit blocked it came back as
                # the route and the walk re-crossed nothing 12 times to an explore-cycle exit
                if first is None and (nb in blocked or nb == src):
                    continue
                if self._gate_shut(cur, nb, field_moves):
                    continue
                # a one-map return (a house door) leads back to where the walk left; a chain of two
                # or more maps that lands back on src joins two regions of it the same way a
                # pass-through does (Mt. Ember's summit path (1,20) -> (33,10) -> (33,11) -> (33,8))
                if nb == src and cur == first and src not in self.passthrough.get(cur, ()):
                    continue
                # seen per first hop, since the same map reached as a first hop is a dead end for
                # the return above but reached deeper down a chain is the way back in
                key = (nb, nb if first is None else first)
                if key not in seen:
                    seen.add(key)
                    frontier.append(key)
        return None

    def route(self, src: Node, dst: Node, blocked=frozenset(), field_moves=frozenset()) -> Node | None:
        return self._bfs(src, lambda n: n == dst, blocked, field_moves)

    def passable(self, node: Node, blocked=frozenset(), field_moves=frozenset()) -> set:
        """Neighbours a walk may hop to from node now: not node itself, not blocked this run, not
        shut under the field-move set."""
        return {nb for nb in self.neighbors(node)
                if nb != node and nb not in blocked and not self._gate_shut(node, nb, field_moves)}

    def nearest(self, src: Node, dests, blocked=frozenset()) -> Node | None:
        """The member of dests the fewest hops from src, src itself when it is one, else None."""
        tier = self.nearest_all(src, dests, blocked)
        return min(tier) if tier else None

    def nearest_all(self, src: Node, dests, blocked=frozenset()) -> list:
        """Every member of dests at the fewest hops from src, [src] when it is one, else []."""
        if src in dests:
            return [src]
        seen = {src}
        frontier = [src]
        while frontier:
            nxt = []
            for cur in frontier:
                for nb in sorted(self.neighbors(cur)):
                    if (cur == src and nb in blocked) or nb in seen:
                        continue
                    seen.add(nb)
                    nxt.append(nb)
            hits = [n for n in nxt if n in dests]
            if hits:
                return hits
            frontier = nxt
        return []

    def block(self, here: Node, neighbor: Node, field_moves=frozenset(), reason: str | None = None) -> None:
        """Record that here->neighbor had no passable edge tile under `field_moves` at the current
        badge count. The block holds only while both hold, so gaining an HM or a badge reopens it.
        A badge-guard edge such as the League doors shut below 16 badges therefore retries once the
        badge count climbs, instead of staying shut because the field-move set never moved. The gate
        carries the current EXECUTOR_CAP_VERSION, so a later crossing primitive reopens it for one
        retry, and `reason` tags why the crossing failed for a later queryable purge."""
        edge = (here, neighbor)
        self.gated[edge] = frozenset(field_moves)
        self.gate_badges[edge] = self.cur_badges
        self.gate_version[edge] = EXECUTOR_CAP_VERSION
        if reason is not None:
            self.gate_reason[edge] = reason
        self.save()

    def unblock(self, here: Node, neighbor: Node) -> bool:
        """Drop the gate on here->neighbor once a crossing moved the party over it. A stuck tally
        gates the map-level edge, so three misses from one region of Meteor Falls shut the boss
        room while the walk later entered it from another, and the gate outlived that entry: route
        read None, the planner fell to an explore of a map already visited. True when a gate went."""
        edge = (here, neighbor)
        if edge not in self.gated:
            return False
        del self.gated[edge]
        self.gate_badges.pop(edge, None)
        self.gate_version.pop(edge, None)
        self.gate_reason.pop(edge, None)
        self.save()
        return True

    def _open(self, node: Node, blocked=frozenset(), field_moves=frozenset()) -> list:
        """Unvisited borders of node worth a crossing attempt now: not visited, not blocked
        this run, and not gated under the current field-move set."""
        return [nb for nb in sorted(self.neighbors(node))
                if nb not in self.visited and nb not in blocked
                and not self._gate_shut(node, nb, field_moves)]

    def explore_hop(self, cur: Node, blocked=frozenset(), field_moves=frozenset()) -> Node | None:
        """Next map to step into to reach an unvisited one: a direct open border first,
        else the first hop toward the nearest map that still has one, else None.
        `blocked` holds borders of cur already found unreachable from where the player stands."""
        direct = self._open(cur, blocked, field_moves)
        if direct:
            return direct[0]
        return self._bfs(cur, lambda n: bool(self._open(n, blocked if n == cur else frozenset(), field_moves)), blocked, field_moves)

    def frontier_exhausted(self, field_moves=frozenset()) -> bool:
        """No open border anywhere: every unvisited map is either mapped or sits past an
        edge the party's current field moves cannot cross."""
        return bool(self.visited) and not any(self._open(v, field_moves=field_moves) for v in self.visited)

    def gated_frontier(self, field_moves=frozenset()) -> bool:
        """An unvisited map is reachable only past an edge this field-move set cannot cross."""
        return any(nb not in self.visited and self._gate_shut(prev, nb, field_moves)
                   for (prev, nb) in self.gated)
