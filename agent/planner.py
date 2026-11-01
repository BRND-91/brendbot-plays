"""Planner step: read states/status.json, decide the next goal, print one report line.

    planner.py            report + recommendation
    planner.py --apply    also write states/goal.json when the recommendation differs

run-grind.sh runs this with --apply before every executor launch, so a goal the
executor reached or demoted is re-decided from live status each run. Goals the
executor runs: grind a map to a level cap, travel to a map (routed over the ROM's
connection and warp tables), explore outward, or gym: travel to the gym map, fight
through to the leader, and exit once the badge flag count rises so the cap re-reads.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import map_graph  # noqa: E402
import rowe_rom  # noqa: E402

STATES = os.path.join(HERE, "states")
STATUS = os.path.join(STATES, "status.json")
GOAL = os.path.join(STATES, "goal.json")
GRAPH = os.path.join(STATES, "map_graph.json")
BLOCKED = os.path.join(STATES, "grind_blocked.json")
CAPS = [16, 21, 26, 29, 32, 36, 39, 42, 45]  # ROWE badge level caps, guide tab ROWE_Badge_Rewards
# gym entrance interior -> badge flag offset (0-based), the fixed Hoenn gym order. Each key is
# confirmed a gym by rowe_rom.gym_maps(); beaten reads from the per-gym flag, since ROWE lets
# badges fall in any order and the count alone cannot say which gym is still open.
GYM_BADGE = {(11, 3): 0, (3, 3): 1, (10, 0): 2, (4, 1): 3, (8, 1): 4, (12, 1): 5, (14, 0): 6, (15, 0): 7}
# the stand is the tile below the leader, resolved on entry by gym_stand, which takes the northmost
# static object; a gym is pre-seeded here when a non-leader object sits north of the leader and that
# heuristic would pick it (Lavaridge: trainer Danielle at (5, 2), above Flannery at (13, 9))
GYM_STAND = {(11, 3): (5, 3), (4, 1): (13, 10)}
GYM_CLOSED = os.path.join(STATES, "gym_closed.json")
PARTY_SIZE = 6


def executor_running() -> bool:
    out = subprocess.run(["pgrep", "-f", "play.py --state"], capture_output=True, text=True)
    return bool(out.stdout.strip())


def grind_map(graph: map_graph.MapGraph, blocked: frozenset, anchor: tuple, cap: int | None) -> list:
    """Visited grass map to grind, ranked by fewest world-edge hops to `anchor` (the next gym),
    then by the ROM's land wild level, highest under the cap first. Anchoring on the gym rather
    than the executor's tile keeps a restock detour in a starter town from dragging the grind
    back to Route 101, and the wild-level tiebreak fights the strongest grass on the way forward.
    A group-0 map numbered 16 or above holds grass, except a MAP_TYPE_UNDERWATER seabed, which
    holds none and travel_toward cannot route to, so it is filtered out. `blocked` is grass the
    executor could not reach, skipped while another remains."""
    routes = {m for m in graph.visited if m[0] == 0 and m[1] >= 16 and not rowe_rom.is_underwater(*m)}
    routes = (routes - blocked) or routes
    hops = hops_from(tuple(anchor))
    if not routes:
        # no grass walked yet: send the party to the nearest overworld (group 0) map to the
        # anchor over the ROM's world edges, never the anchor itself when it is a gym interior,
        # since a gym holds no wild grass. the walk then explores out and discovers routes to grind
        overworld = [m for m in hops if m[0] == 0]
        return list(min(overworld, key=lambda m: (hops[m], m))) if overworld else list(anchor)

    def rank(m: tuple) -> tuple:
        span = rowe_rom.wild_land_levels().get(m)
        level = span[1] if span else 0
        under = level if (cap is None or level <= cap) else -1
        return hops.get(m, 1 << 30), -under

    return list(min(routes, key=rank))


def blocked_grinds(status: dict) -> frozenset:
    """Maps the executor gave up grinding on, from its `grind blocked` exits, persisted in
    states/grind_blocked.json so the next launch does not send it straight back."""
    maps = set()
    if os.path.exists(BLOCKED):
        with open(BLOCKED) as f:
            maps = {tuple(m) for m in json.load(f)}
    if status.get("exit_reason", "").startswith("grind blocked") and tuple(status["map"]) not in maps:
        maps.add(tuple(status["map"]))
        with open(BLOCKED + ".tmp", "w") as f:
            json.dump(sorted(list(m) for m in maps), f)
        os.replace(BLOCKED + ".tmp", BLOCKED)
    return frozenset(maps)


def _closed_raw() -> list:
    """Raw gym_closed.json entries, each a {"gym", "reason", ...} signature dict or, for a record
    written before signatures existed, a bare [x, y] coordinate."""
    if os.path.exists(GYM_CLOSED):
        with open(GYM_CLOSED) as f:
            return json.load(f)
    return []


def closed_gyms() -> set:
    """Every gym coordinate on record as closed, whether or not it has since reopened."""
    return {tuple(e["gym"]) if isinstance(e, dict) else tuple(e) for e in _closed_raw()}


def still_closed(status: dict, graph: "map_graph.MapGraph") -> set:
    """Closed gyms the run has not changed enough to retry, so the ladder routes past them. A gym
    shut by a lost fight reopens once the party out-levels its close baseline or a new field move
    is in the bag. A gym shut because the walk could not reach its leader reopens once the map
    graph has grown a route since. A record with no signature (written before this format) reopens
    on sight, so a stale permanent close does not strand the run exploring forever."""
    party = status.get("party", [])
    now_level = min((m["level"] for m in party), default=0)
    now_moves = set(status.get("field_moves", []))
    now_maps = len(graph.visited)
    shut = set()
    for e in _closed_raw():
        if not isinstance(e, dict) or "reason" not in e:
            continue
        moves_grew = now_moves > set(e.get("field_moves", []))
        if e["reason"] == "loss":
            reopened = now_level > e.get("min_level", 0) or moves_grew
        else:
            reopened = now_maps > e.get("maps", 0) or moves_grew
        if not reopened:
            shut.add(tuple(e["gym"]))
    return shut


def hops_from(start: tuple, graph: "map_graph.MapGraph | None" = None, moves: frozenset = frozenset()) -> dict:
    """BFS hop distance to every map the party can traverse from `start`, over the ROM's world
    adjacency unioned with the borders the executor has walked (`graph.adj`) and skipping any
    border the graph recorded gated under exactly `moves`. Routing the gym ladder over the same
    graph the executor moves on keeps the planner from calling a gym reachable across a border the
    walk gave up on; a gym nobody has walked to still gets a distance from the world table alone."""
    edges = rowe_rom.world_edges()
    adj = graph.adj if graph is not None else {}
    gated = graph.gated if graph is not None else {}
    dist = {start: 0}
    frontier = [start]
    while frontier:
        nxt = []
        for m in frontier:
            for d in edges.get(m, set()) | adj.get(m, set()):
                if d in dist or gated.get((m, d)) == moves:
                    continue
                dist[d] = dist[m] + 1
                nxt.append(d)
        frontier = nxt
    return dist


def unbeaten_gyms(status: dict, badges: int) -> list:
    """Gym entrances whose per-gym badge flag is unset. The count alone cannot say which, since
    ROWE lets badges fall in any order, so a flag list is used and a count is the fallback."""
    flags = status.get("badge_flags") or [i < badges for i in range(len(GYM_BADGE))]
    return [g for g, bi in GYM_BADGE.items() if bi >= len(flags) or not flags[bi]]


def nearest_gym(unbeaten: list, hops: dict, shut: set) -> tuple | None:
    """Nearest unbeaten, open gym over the world edges, or None when none qualifies. A gym in
    `shut` (closed earlier and not yet reopened, see still_closed) is dropped, not just ranked
    behind the open ones, so the recommend explore branch takes over once every reachable gym is
    demoted instead of re-entering one the run cannot clear."""
    open_reachable = [g for g in unbeaten if g in hops and g not in shut]
    if not open_reachable:
        return None
    return min(open_reachable, key=lambda g: hops[g])


def planning_anchor(status: dict, here: tuple, gym: tuple | None) -> tuple:
    """Map the next goal anchors on. The nearest reachable unbeaten gym when there is one, else
    the active goal's own target map, so a heal or restock that ends in a service town does not
    move the grind off toward the grass that town happens to sit next to. Only `here` on the
    first launch, before any goal is written."""
    if gym is not None:
        return gym
    goal = status.get("goal") or {}
    target = goal.get("map") or goal.get("to")
    return tuple(target) if target else here


def recommend(status: dict, graph: map_graph.MapGraph) -> tuple:
    """(goal dict, reason)"""
    badges = status.get("badges", 0)
    cap = CAPS[badges]
    party = status["party"]
    attackers = [m for m in party if any(mv["power"] >= 10 and mv["pp"] for mv in m["moves"])]
    low = min((m["level"] for m in attackers), default=0)
    here = tuple(status["map"])
    blocked = blocked_grinds(status)
    hops = hops_from(here, graph, frozenset(status.get("field_moves", [])))
    unbeaten = unbeaten_gyms(status, badges)
    gym = nearest_gym(unbeaten, hops, still_closed(status, graph))
    anchor = planning_anchor(status, here, gym)
    if len(party) < PARTY_SIZE or low < cap:
        grass = grind_map(graph, blocked, anchor, cap)
        return {"mode": "grind", "map": grass, "cap": cap}, f"party {len(party)}/6, lowest attacker L{low} vs cap {cap}, grind {grass} toward {list(anchor)}"
    if not unbeaten:
        grass = grind_map(graph, blocked, anchor, None)
        return {"mode": "grind", "map": grass, "cap": None}, f"at cap {cap}, all Hoenn gyms beaten, holding on {grass}"
    if gym is None:
        target = min(unbeaten, key=lambda g: GYM_BADGE[g])
        return {"mode": "explore", "to": list(target), "cap": None}, f"at cap {cap}, no gym reachable over world edges, exploring toward {list(target)}"
    goal = {"mode": "gym", "map": list(gym), "badges": badges}
    if gym in GYM_STAND:
        goal["stand"] = list(GYM_STAND[gym])
    retry = " (retry, closed earlier)" if gym in closed_gyms() else ""
    return goal, f"at cap {cap}, nearest unbeaten gym {list(gym)} at {hops[gym]} hops{retry}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(STATUS):
        print(f"status missing, executor {'running' if executor_running() else 'stopped'}, no battle has ended since launch")
        return
    with open(STATUS) as f:
        status = json.load(f)
    age = int(time.time() - status["ts"])
    lead = status["party"][0]
    graph = map_graph.MapGraph(GRAPH)
    goal, why = recommend(status, graph)
    current = json.load(open(GOAL)) if os.path.exists(GOAL) else None
    running = executor_running()
    print(f"status {age}s old, executor {'running' if running else 'stopped'}, exit_reason {status['exit_reason']!r}, "
          f"{status['wins']}/{status['battles']} won, {status['caught']} caught, lead {lead['name']} L{lead['level']} "
          f"{lead['hp']}/{lead['max_hp']}, balls {status['balls']}, money {status['money']}, map {status['map']} tile {status['tile']}")
    print(f"goal now {current}, recommend {goal} because {why}, {len(graph.visited)} maps mapped")
    if a.apply and goal != current:
        with open(GOAL + ".tmp", "w") as f:
            json.dump(goal, f)
        os.replace(GOAL + ".tmp", GOAL)
        print(f"goal written {goal}")


if __name__ == "__main__":
    main()
