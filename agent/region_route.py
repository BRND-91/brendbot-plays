"""Region-level routing over the ROM layouts.

The map graph keys on maps, and a map's walkable area splits into regions: Ever Grande (0,8) is a
shore half holding the Victory Road entrance and a plateau half holding the League door, Victory Road
1F is a south half and a north half joined only through B1F and B2F. A map-level route from the shore
to League1F is one hop, the walk finds the door unreachable, and the edge gets gated. Here the search
state is (map, landing tile): the portals out of a state are the warps and border connections whose
trigger tile the landing reaches on the static layout, so the route from the shore threads
1F -> B1F -> B2F -> B1F -> 1F -> plateau -> League door and names the warp to take first.

A layout carries no object events, so trees, rocks, boulders and NPCs read as open floor: the static
reach is a superset of the live one, and the live walk still decides whether a step lands. Grids,
region labels and reach sets are memoised for the process, since the layouts never change.
"""
from collections import deque
from dataclasses import dataclass

import rowe_map
import rowe_rom
import rowe_symbols as S
from nav import DIVE_BEHAVIORS, Grid

MAX_HOPS = 24  # map crossings a route may span; the longest live leg (Sootopolis to the League) is under 12

BORDERS = (rowe_map.DIR_NORTH, rowe_map.DIR_SOUTH, rowe_map.DIR_WEST, rowe_map.DIR_EAST)
# gate reasons a crossing from one half of a split map records against the whole map pair: the
# shore's stuck on the League door and 1F's south-half bounce off the city both sealed the route
# the plateau and the north half carry
HALF_GATES = ("stuck", "bounce")


def open_hops(graph, here: tuple, blocked: frozenset, moves: frozenset):
    """`allowed(m)` for `route`: the map graph's open neighbours, plus a neighbour whose only closure
    is a HALF_GATES gate on a pair the ROM joins by a warp or border, since the layout search judges
    that pair tile by tile from the half it stands on. A gate on a scripted pair (a sailor's arm) is
    the only knowledge of it and holds."""
    def allowed(m):
        run_blocked = blocked if m == here else frozenset()
        open_ = graph.passable(m, run_blocked, moves)
        halves = {nb for (src, nb), reason in graph.gate_reason.items()
                  if src == m and reason in HALF_GATES and nb not in open_ and nb not in run_blocked
                  and any(p.dest == nb for p in portals(m))}
        return open_ | halves
    return allowed


@dataclass(frozen=True)
class Portal:
    kind: str                    # "warp", "edge", "dive", or "script" for a talked crossing w/ no tile
    dest: tuple
    landings: dict | None        # trigger tile on this map -> landing tile on dest; None when unknown
    direction: int | None = None  # the connection direction of an edge portal


@dataclass(frozen=True)
class Step:
    src: tuple
    dest: tuple
    portal: Portal
    tiles: frozenset   # trigger tiles of the portal the state's landing reaches
    landing: tuple | None


_grids: dict = {}
_portals: dict = {}
_labels: dict = {}
_reach: dict = {}
_all: dict = {}


def grid(m: tuple):
    """(Grid, width, height) over m's ROM layout, or None when the ROM holds no layout for it."""
    if m not in _grids:
        cells = rowe_rom.map_cells(*m)
        if cells is None:
            _grids[m] = None
        else:
            g = Grid.from_cells(*cells)
            g._behavior = rowe_rom.metatile_behavior(*m)
            _grids[m] = (g, cells[0], cells[1])
    return _grids[m]


def walkable(g: Grid, tile: tuple) -> bool:
    c = g.cell(*tile)
    return not (c & S.GRID_ID_MASK == S.GRID_UNDEFINED or c & S.GRID_BLOCKED)


def around(tile: tuple) -> tuple:
    x, y = tile
    return (x, y), (x, y + 1), (x, y - 1), (x + 1, y), (x - 1, y)


def stand_tiles(g: Grid, landing: tuple) -> list:
    """The walkable tiles among a landing and its orthogonal neighbours: a door pad or stair
    metatile reads blocked, and the player steps off it onto one of them."""
    return [t for t in around(landing) if walkable(g, t)]


def _label(m: tuple, tile: tuple, surf: bool, climb: bool):
    table = _labels.setdefault((m, surf, climb), {})
    if tile not in table:
        g = grid(m)[0]
        g.climb = climb
        low, tiles = g.region_tiles(tile, surf)
        for t in tiles:
            table[t] = low
    return table[tile]


def _all_walkable(m: tuple) -> frozenset:
    if m not in _all:
        g, w, h = grid(m)
        _all[m] = frozenset((x, y) for x in range(w) for y in range(h) if walkable(g, (x, y)))
    return _all[m]


def reach(m: tuple, landing: tuple | None, surf: bool, climb: bool) -> frozenset:
    """Tiles walkable from a landing on m, one-way ledge drops included. A None landing (a talked
    crossing whose arrival tile the ROM does not name) reads as the whole walkable map."""
    gw = grid(m)
    if gw is None:
        return frozenset()
    if landing is None:
        return _all_walkable(m)
    g = gw[0]
    out = set()
    for t in stand_tiles(g, landing):
        key = (m, surf, climb, _label(m, t, surf, climb))
        if key not in _reach:
            g.climb = climb
            _reach[key] = frozenset(g.reachable(t, surf))
        out |= _reach[key]
    return frozenset(out)


def state_key(m: tuple, landing: tuple | None, surf: bool, climb: bool) -> tuple:
    """(map, region label) so two landings in one walkable area are one search state."""
    gw = grid(m)
    if landing is None or gw is None:
        return (m, landing)
    stands = stand_tiles(gw[0], landing)
    return (m, _label(m, stands[0], surf, climb) if stands else landing)


def portals(m: tuple) -> tuple:
    if m in _portals:
        return _portals[m]
    gw = grid(m)
    if gw is None:
        _portals[m] = ()
        return ()
    g, w, h = gw
    out = []
    for x, y, dest, dw in rowe_rom.map_warp_links(*m):
        if dest == S.MAP_DYNAMIC:
            continue
        links = rowe_rom.map_warp_links(*dest)
        landing = links[dw][:2] if dw < len(links) else None
        # the warp tile itself counts even when its pad reads blocked, since the walk steps onto it
        tiles = {(x, y), *stand_tiles(g, (x, y))}
        out.append(Portal("warp", dest, {t: landing for t in tiles}))
    for d, off, dest in rowe_rom.map_connection_links(*m):
        if d in BORDERS:
            gd = grid(dest)
            if gd is None:
                continue
            _, dw_, dh_ = gd
            if d == rowe_map.DIR_NORTH:
                pairs = {(x, 0): (x - off, dh_ - 1) for x in range(w)}
            elif d == rowe_map.DIR_SOUTH:
                pairs = {(x, h - 1): (x - off, 0) for x in range(w)}
            elif d == rowe_map.DIR_WEST:
                pairs = {(0, y): (dw_ - 1, y - off) for y in range(h)}
            else:
                pairs = {(w - 1, y): (0, y - off) for y in range(h)}
            out.append(Portal("edge", dest, {t: l for t, l in pairs.items() if walkable(g, t)}, d))
        elif d == rowe_map.DIR_DIVE and g._behavior is not None:
            tiles = [t for t in _all_walkable(m) if g._behavior(g.cell(*t) & S.GRID_ID_MASK) in DIVE_BEHAVIORS]
            out.append(Portal("dive", dest, {t: t for t in tiles}, d))
        elif d == rowe_map.DIR_EMERGE:
            out.append(Portal("dive", dest, {t: t for t in _all_walkable(m)}, d))
    _portals[m] = tuple(out)
    return _portals[m]


def threads(m: tuple, landing: tuple | None, chain: tuple, surf: bool, climb: bool) -> bool:
    """True when a landing on m reaches a portal into chain[0] whose own landing threads the rest.
    A map pair w/ no ROM portal between them (a sailor, a scripted door) reads as threading."""
    if not chain:
        return True
    r = reach(m, landing, surf, climb)
    ps = [p for p in portals(m) if p.dest == chain[0]]
    if not ps:
        return True
    return any(t in r and threads(chain[0], l, chain[1:], surf, climb)
               for p in ps for t, l in p.landings.items())


def route(start: tuple, tile: tuple, dest: tuple, allowed, surf: bool, climb: bool,
          dest_tiles: frozenset | None = None) -> list | None:
    """Steps from standing on `tile` of `start` to `dest`, fewest crossings first, or None.
    `allowed(m)` is the set of maps the walk may hop to from m (the map graph minus its gates and
    run-local blocks). With `dest_tiles`, the arrival landing must reach one of them, so a heal
    trip ends on the half of the town that holds the Center door."""
    if grid(start) is None:
        return None
    first = state_key(start, tile, surf, climb)
    parents: dict = {first: None}
    q = deque([(start, tile, first, 0)])
    while q:
        m, landing, key, hops = q.popleft()
        r = reach(m, landing, surf, climb)
        if m == dest and key != first and (dest_tiles is None or r & dest_tiles):
            steps = []
            while parents[key] is not None:
                key, step = parents[key]
                steps.append(step)
            return steps[::-1]
        if hops >= MAX_HOPS:
            continue
        for n in sorted(allowed(m)):
            ps = [p for p in portals(m) if p.dest == n] or [Portal("script", n, None)]
            for p in ps:
                groups: dict = {}
                if p.landings is None:
                    groups[state_key(n, None, surf, climb)] = (None, set())
                else:
                    for t, l in p.landings.items():
                        if t in r:
                            groups.setdefault(state_key(n, l, surf, climb), (l, set()))[1].add(t)
                for nkey, (l, tiles) in groups.items():
                    if nkey in parents:
                        continue
                    parents[nkey] = (key, Step(m, n, p, frozenset(tiles), l))
                    q.append((n, l, nkey, hops + 1))
    return None
