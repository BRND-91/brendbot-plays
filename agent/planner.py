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
import script_decode  # noqa: E402

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
# Johto gym entrance interior -> League flag index (8-15), set on the Johto leader win. These maps
# carry non-gym music so gym_maps() does not list them; this table is the source. Falkner (2,7)
# through Clair (2,15), flags 0x2A4-0x2AB; (2,14) between them is the region hub, not a gym.
JOHTO_GYM = {(2, 7): 8, (2, 8): 9, (2, 9): 10, (2, 10): 11, (2, 11): 12, (2, 12): 13, (2, 13): 14, (2, 15): 15}
ALL_GYMS = {**GYM_BADGE, **JOHTO_GYM}
GYM_CLOSED = os.path.join(STATES, "gym_closed.json")
PARTY_SIZE = 6

# vanilla pokeemerald IndoorEverGrande group 16, index for index: the Elite Four chambers, the
# connecting halls, the League entry floor, the Hall of Fame, and the two link-club rooms.
ENDGAME_ROOMS = {
    (16, 0): "Sidney", (16, 1): "Phoebe", (16, 2): "Glacia", (16, 3): "Drake", (16, 4): "Wallace",
    (16, 5): "Hall1", (16, 6): "Hall2", (16, 7): "Hall3", (16, 8): "Hall4", (16, 9): "Hall5",
    (16, 10): "League1F", (16, 11): "HallOfFame", (16, 12): "Center1F", (16, 13): "Center2F",
    (16, 14): "League2F",
}
# Victory Road is group 24: 1F, B1F, B2F. The city (0,8) doors (18,41) south and (18,27) north both
# warp to VR 1F (24,43); VR exits back into the League half of (0,8), which reaches League1F (16,10).
VICTORY_ROAD = [(24, 43), (24, 44), (24, 45)]
# The League 1F door guard despawns on flag 0xDFA, which the Ever Grande map-load chain (ROM
# 0x82f861c) sets only once all 16 gym flags are up: the 8 Hoenn badges 0xCD7-0xCDE and the 8 Johto
# badges 0x2A4-0x2AB (leaders Falkner through Clair, gyms on group 2). So League-forward travel
# waits on 16 gyms, not 8 Hoenn badges. Order once every gym is down: Victory Road, then the
# League-half halls and the Elite Four ladder, League1F -> Hall5 -> Sidney -> Hall1 -> Phoebe -> ...
# -> Hall4 -> Wallace -> Hall of Fame, each dropping out as reached. group 16 is IndoorEverGrande.
ENDGAME_CHAIN = VICTORY_ROAD + [(16, 10), (16, 9), (16, 0), (16, 5), (16, 1), (16, 6),
                                (16, 2), (16, 7), (16, 3), (16, 8), (16, 4), (16, 11)]
# Three Island dock, the Seagallop ferry row that stays open once the 8 Hoenn badges are in; the
# Johto-bound rows report locked and gate out, so this is where the 8-badge leg heads.
SEVII_ENTRY = (0, 79)


def build_graph(path: str, flags=frozenset()) -> map_graph.MapGraph:
    """The map graph both the CLI planner and the in-process executor route over, assembled one way
    so the two never disagree on the neighbor set. Carries the ROM world edges, the pass-through
    maps, the script-warp layer (the Seagallop ferry), and the gate flags set right now, so a dock's
    ferry arm is a neighbor whenever its flag is up. The executor passes flags read live off the
    emulator; the CLI planner passes the set the executor recorded into status.json."""
    return map_graph.MapGraph(path, world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs(),
                              script=script_decode.script_edges(), flags=flags)


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
    """BFS hop distance to every map the party can traverse from `start`, over the same three-layer
    neighbor set `MapGraph.route` walks (the world table, the walked `adj` borders, and the script
    warps whose gate flags are currently set) and skipping any border `_gate_shut` reports closed,
    the same badge-count and executor-version test `route` applies. hops_from and route disagreeing
    on reachability is what made the planner emit explore for a gym route could already reach, so
    both apply one test now; a gym nobody has walked to still gets a distance from the world table
    when no graph is passed."""
    edges = rowe_rom.world_edges()
    dist = {start: 0}
    frontier = [start]
    while frontier:
        nxt = []
        for m in frontier:
            dests = graph.neighbors(m) if graph is not None else edges.get(m, set())
            for d in dests:
                if d in dist:
                    continue
                if graph is not None and graph._gate_shut(m, d, moves):
                    continue
                dist[d] = dist[m] + 1
                nxt.append(d)
        frontier = nxt
    return dist


def league_flags(status: dict) -> list:
    """The 16 League-entry gym flags as booleans: the 8 Hoenn badges then the 8 Johto badges
    (flags 0x2A4-0x2AB, Falkner through Clair). The Ever Grande guard flag 0xDFA sets only when all
    16 are up, so 8 Hoenn badges alone leaves the guard standing and the League sealed."""
    hoenn = status.get("badge_flags") or [False] * len(GYM_BADGE)
    johto = status.get("johto_flags") or [False] * len(JOHTO_GYM)
    return list(hoenn) + list(johto)


def unbeaten_gyms(status: dict) -> list:
    """Gym entrances whose own flag is unset, Hoenn and Johto together. ROWE lets badges fall in any
    order, so each gym reads its flag from league_flags rather than the badge count."""
    flags = league_flags(status)
    return [g for g, bi in ALL_GYMS.items() if bi >= len(flags) or not flags[bi]]


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


def sevii_goal(graph: map_graph.MapGraph, moves: frozenset) -> tuple:
    """(goal, reason) for the 8-badge Sevii leg. Every Johto gym sits behind the Seagallop ferry and
    Hoenn grass tops out under the cap, so travel to Three Island while it is unwalked, then explore
    the nearest unvisited map reachable from it. Never grind."""
    if SEVII_ENTRY not in graph.visited:
        return {"mode": "travel", "to": list(SEVII_ENTRY)}, f"travel to Three Island {list(SEVII_ENTRY)}"
    reach = hops_from(SEVII_ENTRY, graph, moves)
    target = min((m for m in reach if m not in graph.visited),
                 key=lambda m: (reach[m], m), default=SEVII_ENTRY)
    return {"mode": "explore", "to": list(target), "cap": None}, f"on Three Island, exploring Sevii toward {list(target)}"


def recommend(status: dict, graph: map_graph.MapGraph) -> tuple:
    """(goal dict, reason)"""
    badges = status.get("badges", 0)
    graph.cur_badges = badges
    cap = CAPS[badges] if badges < len(CAPS) else CAPS[-1]
    party = status["party"]
    attackers = [m for m in party if any(mv["power"] >= 10 and mv["pp"] for mv in m["moves"])]
    low = min((m["level"] for m in attackers), default=0)
    here = tuple(status["map"])
    blocked = blocked_grinds(status)
    hops = hops_from(here, graph, frozenset(status.get("field_moves", [])))
    unbeaten = unbeaten_gyms(status)
    gym = nearest_gym(unbeaten, hops, still_closed(status, graph))
    anchor = planning_anchor(status, here, gym)
    if badges >= len(GYM_BADGE) and unbeaten and gym is None:
        # 8 Hoenn badges, no gym the walk can route to: the Johto gyms are ferry-locked and Hoenn
        # grass raises nothing at cap, so take the Three Island ferry and explore Sevii, never grind
        goal, note = sevii_goal(graph, frozenset(status.get("field_moves", [])))
        return goal, f"at cap {cap}, {badges} badges, no gym reachable, {note}"
    if len(party) < PARTY_SIZE or low < cap:
        grass = grind_map(graph, blocked, anchor, cap)
        return {"mode": "grind", "map": grass, "cap": cap}, f"party {len(party)}/6, lowest attacker L{low} vs cap {cap}, grind {grass} toward {list(anchor)}"
    if not unbeaten:
        if status.get("champion"):
            return {"mode": "done"}, "champion, every badge in and the League cleared, no goal left"
        moves = frozenset(status.get("field_moves", []))
        # every gym down, all 16 League flags in: advance the endgame chain to the first map not
        # yet reached that there is a walkable route to from here, so arrival at (0,8) travels on into
        # Victory Road and the League halls and each room drops out once cleared. here != m keeps a
        # travel-to-self off it
        dest = next((m for m in ENDGAME_CHAIN
                     if m not in graph.visited and here != m
                     and graph.route(here, m, field_moves=moves) is not None), None)
        if dest is not None:
            return {"mode": "travel", "to": list(dest)}, f"at cap {cap}, {badges} badges, League travel to {list(dest)} ({ENDGAME_ROOMS.get(tuple(dest), 'VictoryRoad')})"
        # no walkable route onward: explore toward the first unreached chain map, never grind. a grind
        # here anchors the grass rank on an unreachable cell and walks the party back across Hoenn, and
        # at cap the party earns nothing. the reason names here, the moves it routed under, and the
        # reachable-map count so a bad here (an interior map or a mid-warp write) reads in one line
        target = next((m for m in ENDGAME_CHAIN if m not in graph.visited), ENDGAME_CHAIN[-1])
        hop = graph.route(here, target, field_moves=frozenset())
        return {"mode": "explore", "to": list(target), "cap": None}, f"at cap {cap}, {badges} badges, here {list(here)}, no League travel route under moves {sorted(moves)}, {len(hops)} maps reachable, hop {list(hop) if hop else None}, exploring toward {list(target)}"
    if gym is None:
        target = min(unbeaten, key=lambda g: ALL_GYMS[g])
        return {"mode": "explore", "to": list(target), "cap": None}, f"at cap {cap}, no gym reachable over world edges, exploring toward {list(target)}"
    goal = {"mode": "gym", "map": list(gym), "badges": badges, "flags": sum(league_flags(status))}
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
    graph = build_graph(GRAPH, flags=frozenset(status.get("gate_flags", [])))
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
