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
import battle_engine  # noqa: E402
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
BOSS_LOSSES = os.path.join(STATES, "boss_losses.json")
PARTY_SIZE = 6
# The boss retry in minutes, the measured median off the attempt ledger w/ this cold-start stand-in
# before a span exists; the reason line names the default when it is priced.
RETRY_MINUTES_DEFAULT = 20  # whiteout to the next fight start: the Center warp and the walk back to the boss room
CATCH_MARGIN = 0.5          # summed boss edge a catchable species must beat the weakest member by, same bar as the Center swap

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
# Post-game bosses in fight order once the Champion is in, each a L100 team of six: Steven in his
# Meteor Falls cave (24,107), whose door in 1F_1R (24,0) opens on the game-clear bit, then Red in Shoal
# Cave's high-tide inner room (24,51). status["boss_flags"] carries each defeat flag in this order.
POSTGAME = [(24, 107), (24, 51)]
# Three Island dock, the Seagallop ferry row that stays open once the 8 Hoenn badges are in; the
# Johto-bound rows report locked and gate out, so this is where the 8-badge leg heads.
SEVII_ENTRY = (0, 79)
# The Sevii run in badge order: (badge index, gym entrance map, the island landing map whose
# dispatcher row and mainland-dock row sail there). Each gym checkflags its own badge and the leaders
# fall in this order; the ticket for an island is handed by any field dispatcher on picking that
# island's row (script_decode.ISLAND_TICKETS), so a leg is: route to the gym over the ferry layer,
# which crosses on a dispatcher when the mainland dock row is still ticketless, fight, re-plan.
# Whitney's gym opens off the Three Island town (0,77), one land hop past the (0,79) landing;
# Pryce's off (1,72), one land hop past Seven Island (1,66).
SEVII_LEGS = [
    (8, (2, 7), (0, 75)), (9, (2, 8), (0, 76)), (10, (2, 9), (0, 79)), (11, (2, 10), (0, 123)),
    (12, (2, 11), (1, 32)), (13, (2, 12), (1, 58)), (14, (2, 13), (1, 66)), (15, (2, 15), (2, 14)),
]


def script_layer(tickets=frozenset(), hidden=frozenset()) -> dict:
    """The script-warp layer (the Seagallop ferry) under the held key-item set `tickets`: a
    Hoenn-mainland dock's island arm whose Sevii ticket is not among them is dropped so routing
    crosses on One Island and the free field dispatchers rather than looping on a dock row that
    refuses without the ticket. A giver map in `hidden` has had its sailor removed by a set
    visibility flag at this story phase, so all its arms drop and routing aims at a present
    dispatcher instead of a gap. The executor rebuilds this layer when the bag's key items or the
    hidden set change."""
    tickets = frozenset(tickets)
    # a dock's own row (the Slateport harbor decodes a (9,9)->(9,9) arm) is no hop: routed as one it
    # re-talks the sailor in place and the walk cycles on the dock
    script = {src: {d: g for d, g in dests.items()
                    if d != src and script_decode.passable_island_arm(src, d, tickets)}
              for src, dests in script_decode.script_edges().items()
              if src not in hidden}
    return {s: d for s, d in script.items() if d}


def build_graph(path: str, flags=frozenset(), tickets=frozenset(), hidden=frozenset()) -> map_graph.MapGraph:
    """The map graph both the CLI planner and the in-process executor route over, assembled one way
    so the two never disagree on the neighbor set. Carries the ROM world edges, the pass-through
    maps, the script-warp layer (the Seagallop ferry), and the gate flags set right now, so a dock's
    ferry arm is a neighbor whenever its flag is up. The executor passes flags read live off the
    emulator and the giver maps whose sailor is gone; the CLI planner passes the sets the executor
    recorded into status.json."""
    return map_graph.MapGraph(path, world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs(),
                              script=script_layer(tickets, hidden), flags=flags,
                              ferry_hubs=script_decode.SEAGALLOP_DOCKS)


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


def catch_target(graph: map_graph.MapGraph, blocked: frozenset, here: tuple, boss: str, caught: frozenset,
                 moves: frozenset, ivs: tuple, level: int) -> tuple | None:
    """(edge, species, map) for the uncaught land species on a reachable walked map that would score the
    highest boss_edge against `boss` once raised to `level` (battle_engine.Prospect), the nearest map
    by hops between its spawns; None when every reachable species is caught. The damage formula on the
    prospect's own learnset, so a Teddiursa that becomes an Earthquake Ursaluna outranks a Wurmple
    underfoot and a Dark type that merely hits Steel on the chart."""
    hops = hops_from(here, graph, moves)
    foes = battle_engine.boss_foes(boss)
    best = None
    seen = {}
    for group, num, category, _slot, _lo, _hi, species in rowe_rom.wild_encounters():
        m = (group, num)
        if category != 0 or m not in graph.visited or m in blocked or m not in hops:
            continue
        if species in caught or rowe_rom.species_at_level(species, level) in caught:
            # the ledger records the form the ball closed on, Ursaluna for Teddiursa's slot at L52
            continue
        if species not in seen:
            seen[species] = battle_engine.boss_edge(battle_engine.Prospect(species, level), level, ivs, foes)
        key = (seen[species], -hops[m])
        if best is None or key > best[0]:
            best = (key, species, m)
    return (round(best[0][0], 2), best[1], best[2]) if best else None


def blocked_grinds(status: dict) -> frozenset:
    """Maps the executor gave up grinding on, persisted in states/grind_blocked.json so the next
    launch does not send it straight back: the map it stood on at a `grind blocked` exit, and the
    grind goal's grass at a `travel stuck` exit whose failed destination is that grass, since only
    that walk proved the grass unreachable. A stuck on a heal detour or on the first hop out of a
    wedged map says nothing about the grass; blocking it on every such exit burned 43 maps while the
    party stood on (1,62) with its one onward gate shut."""
    maps = set()
    if os.path.exists(BLOCKED):
        with open(BLOCKED) as f:
            maps = {tuple(m) for m in json.load(f)}
    reason = status.get("exit_reason", "")
    goal = status.get("goal") or {}
    target = None
    if reason.startswith("grind blocked"):
        target = tuple(status["map"])
    elif reason.startswith("travel stuck") and goal.get("mode") == "grind" and goal.get("map"):
        grass = list(goal["map"])
        if f"to {grass}" in reason or f"-> {grass}" in reason:
            target = tuple(grass)
    if target is not None and target not in maps:
        maps.add(target)
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
    """Gyms the ladder routes past. Johto gyms read the ROM badge-gate scan: each one checkflags the
    badge it awards and the Sevii leg is strictly sequential, so a Johto gym whose gate badge exceeds
    the badges earned is shut until the ladder reaches it (Falkner (2,7) badge 8 opens at 8, Whitney
    (2,9) badge 10 stays shut until 10). Hoenn gyms are not badge-order-gated (the party reaches
    Petalburg (8,1), badge 4, at one badge), so their own-badge checkflag is post-win dialogue, not an
    entry gate; they keep the whiteout record, reopening once the party out-levels the close baseline,
    a new field move is in the bag, or the map graph has grown a route since."""
    badges = sum(league_flags(status))
    shut = {(g, num) for g, num, b in rowe_rom.badge_gate_maps()
            if (g, num) in JOHTO_GYM and b > badges}
    party = status.get("party", [])
    now_level = min((m["level"] for m in party), default=0)
    now_moves = set(status.get("field_moves", []))
    now_maps = len(graph.visited)
    for e in _closed_raw():
        if not isinstance(e, dict) or "reason" not in e or tuple(e["gym"]) in JOHTO_GYM:
            continue
        moves_grew = now_moves > set(e.get("field_moves", []))
        if e["reason"] == "loss":
            reopened = now_level > e.get("min_level", 0) or moves_grew
        else:
            reopened = now_maps > e.get("maps", 0) or moves_grew
        if not reopened:
            shut.add(tuple(e["gym"]))
    return shut


def party_signature(status: dict) -> list:
    """[species, sorted move names] per party mon, sorted, the build a boss hold is measured against.
    Matches Player._party_signature so a stored hold compares equal to the live party after the JSON
    round trip."""
    return sorted([m["species"], sorted(mv["name"] for mv in m["moves"])]
                  for m in status.get("party", []))


def boss_losses(status: dict, boss: tuple) -> tuple:
    """(losses under the current party signature, measured retry minutes or None) for `boss` off the
    attempt ledger. The retry is the median whiteout-to-rematch span over the attempts that have a
    rematch, so one span left open across a night's relaunch does not price every retry at hours.
    A ledger entry tallied under another build counts zero: the swap or relearn is the change the
    losses were waiting on, and the first fight under a new build is free."""
    if not os.path.exists(BOSS_LOSSES):
        return 0, None
    with open(BOSS_LOSSES) as f:
        entries = {tuple(e["boss"]): e for e in json.load(f)}
    entry = entries.get(tuple(boss))
    if entry is None:
        return 0, None
    spans = sorted((a["rematch"] - a["whiteout"]) / 60 for a in entry.get("attempts", []) if a.get("rematch") is not None)
    retry = spans[len(spans) // 2] if spans else None
    count = entry["count"] if entry.get("signature") == party_signature(status) else 0
    return count, retry



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


def leader_stand(gym: tuple) -> tuple | None:
    """Tile below the gym's leader: the object on the gym map whose script battles the trainer the
    badge table names for that gym, None when no object on the map does (a Hoenn leader in an inner
    room). Player.gym_stand's northmost-static-object entry read picked Al at (0,7) on Bugsy's gym
    (2,8), where Bugsy stands at (6,13) and the one object north of him wanders, so the run fought
    Al, then read his beaten dialog as the gym shut."""
    leader = {b: ld for b, _flag, _region, ld in rowe_rom.badge_flags()}[ALL_GYMS[gym]]
    for _idx, x, y, _move, script in rowe_rom.map_object_scripts(*gym):
        if any(rowe_rom.trainer_name(t) == leader for t in rowe_rom._script_trainer_ids(script)):
            return (x, y + 1)
    return None


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


def sevii_goal(graph: map_graph.MapGraph, moves: frozenset, status: dict) -> tuple:
    """(goal, reason) for the Sevii leg once the 8 Hoenn badges are in. Target the lowest-indexed
    unbeaten Sevii gym from the badge table (Falkner, badge 8, first). Fetch the next unheld island
    ticket whose clerk is reachable before routing to the gym, because the gym's island cannot be
    entered without that ticket. While no route is open, explore toward the nearest unvisited map so
    the graph keeps growing; with no route and nothing unvisited left, explore toward the gym and name
    the shut edges. Never travel to the map the party stands on, never grind."""
    here = tuple(status["map"])
    unbeaten = [g for g in unbeaten_gyms(status) if g in JOHTO_GYM]
    gym = min(unbeaten, key=JOHTO_GYM.get)
    leader = {b: ld for b, _flag, _region, ld in rowe_rom.badge_flags()}[JOHTO_GYM[gym]]
    flags = sum(league_flags(status))
    island = next(isl for _b, g, isl in SEVII_LEGS if g == gym)
    ticket = script_decode.ISLAND_TICKETS[island]
    held = ticket in set(status.get("tickets", []))
    # the ferry layer carries the leg: a mainland dock row needs the island's ticket, a field
    # dispatcher hands that ticket on the row pick and sails, so the gym is routable whenever any
    # dispatcher or a ticketed dock is; route straight to it, else explore to grow the graph.
    if graph.route(here, gym, field_moves=moves) is not None:
        goal = {"mode": "gym", "map": list(gym), "badges": status.get("badges", 0), "flags": flags}
        stand = leader_stand(gym)
        if stand is not None:
            goal["stand"] = list(stand)
        return goal, (f"next leader {leader}, gym {list(gym)} on island {list(island)}, ticket "
                      f"{ticket:#x} {'held' if held else 'from the dispatcher row'}, heading there")
    reach = hops_from(here, graph, moves)
    unvisited = [m for m in reach if m not in graph.visited and m != here]
    if unvisited:
        target = min(unvisited, key=lambda m: (reach[m], m))
        return {"mode": "explore", "to": list(target), "cap": None}, f"no ferry route to {leader} {list(gym)} yet, exploring toward {list(target)}"
    shut = sorted(f"{list(a)}->{list(b)}" for a, b in graph.gated if graph._gate_shut(a, b, moves))
    return {"mode": "explore", "to": list(gym), "cap": None}, f"no route or unvisited frontier toward {leader} {list(gym)}, shut gates {shut}"


RUSTBORO = (0, 3)
DEVON_1F, DEVON_2F = (11, 0), (11, 1)  # Devon Corp; the fossil scientist is on 2F, through 1F's stairs
FOSSIL_FAIL_CAP = 2  # revive attempts that came back short before the errand is dropped for the run


def recommend(status: dict, graph: map_graph.MapGraph) -> tuple:
    """(goal dict, reason)"""
    badges = status.get("badges", 0)
    graph.cur_badges = badges
    party = status["party"]
    cap = CAPS[badges] if badges < len(CAPS) else CAPS[-1]
    if status.get("champion") and party:
        # CAPS tops out at 45, so past the clear no member ever reads under it and a mid-60s catch would
        # march on the L100 bosses as caught; the cap is the party's own top level until every member is there
        cap = max(m["level"] for m in party)
    attackers = [m for m in party if any(mv["power"] >= 10 and mv["pp"] for mv in m["moves"])]
    low = min((m["level"] for m in attackers), default=0)
    here = tuple(status["map"])
    blocked = blocked_grinds(status)
    hops = hops_from(here, graph, frozenset(status.get("field_moves", [])))
    unbeaten = unbeaten_gyms(status)
    gym = nearest_gym(unbeaten, hops, still_closed(status, graph))
    anchor = planning_anchor(status, here, gym)
    sevii_unbeaten = [g for g in unbeaten if g in JOHTO_GYM]
    if badges >= len(GYM_BADGE) and sevii_unbeaten:
        # the 8 Hoenn badges are in and every remaining leader sits behind the Seagallop ferry, so the
        # Sevii leg targets the next leader straight off the badge table, not nearest_gym (which ranks
        # by hops and demotes a gym the ladder recorded closed, sending the party to the wrong island)
        goal, note = sevii_goal(graph, frozenset(status.get("field_moves", [])), status)
        return goal, f"at cap {cap}, {badges} badges, {note}"
    fossils = status.get("fossils", [])
    if fossils and status.get("fossil_fails", 0) < FOSSIL_FAIL_CAP:
        # a fossil in the bag is a roster candidate the catch policy never sees, so the revive goes
        # ahead of the grind as soon as Rustboro is on the known map
        moves = frozenset(status.get("field_moves", []))
        if here in (RUSTBORO, DEVON_1F, DEVON_2F) or graph.route(here, RUSTBORO, field_moves=moves) is not None:
            return {"mode": "errand", "errand": "revive_fossil", "to": list(RUSTBORO)}, f"{len(fossils)} fossil(s) in the bag, Devon Corp revives them"
    if len(party) < PARTY_SIZE or (low < cap and not status.get("champion")):
        grass = grind_map(graph, blocked, anchor, cap)
        return {"mode": "grind", "map": grass, "cap": cap}, f"party {len(party)}/6, lowest attacker L{low} vs cap {cap}, grind {grass} toward {list(anchor)}"
    if not unbeaten:
        if status.get("champion"):
            # a status written before boss_flags existed reads as nobody beaten, never as done
            flags = status.get("boss_flags") or [False] * len(POSTGAME)
            bosses = [m for m, beaten in zip(POSTGAME, flags) if not beaten]
            if not bosses:
                return {"mode": "done"}, "champion, every badge in, the League and the post-game bosses cleared, no goal left"
            moves = frozenset(status.get("field_moves", []))
            boss = bosses[0]
            losses, retry = boss_losses(status, boss)
            retry_min = RETRY_MINUTES_DEFAULT if retry is None else retry
            price = f"boss {list(boss)} {losses} losses x {retry_min:g} min{' default' if retry is None else ''} = {losses * retry_min:g} min"
            # a catch that out-scores the weakest member against the boss's six comes before the fight,
            # whatever the retries cost: the party that lost is the sunk cost, and the swap at the next
            # Center brings the catch in (best_boss_swap). The grind ends on the catch (check_goal).
            caught = frozenset(status.get("caught_species", []))
            edges = [m.get("boss_edge") for m in party]
            if all(e is not None for e in edges):
                target = catch_target(graph, blocked, here, rowe_rom.BOSSES[POSTGAME.index(boss)], caught, moves,
                                      tuple(status.get("iv_boosts", (0,) * 6)), cap)
                if target is not None and target[0] >= min(edges) + CATCH_MARGIN:
                    edge, species, grass = target
                    return ({"mode": "grind", "map": list(grass), "cap": None, "coverage": True, "caught_n": len(caught), "species": species},
                            f"champion, {price}, catch {rowe_rom.species_name(species)} on {list(grass)}, edge {edge} vs weakest {min(edges)}")
            if low < cap:
                grass = grind_map(graph, blocked, anchor, cap)
                return {"mode": "grind", "map": grass, "cap": cap}, f"champion, {price}, lowest attacker L{low} vs cap {cap}, grind {grass} toward {list(anchor)}"
            if here == boss or graph.route(here, boss, field_moves=moves) is not None:
                return {"mode": "travel", "to": list(boss)}, f"champion, {price}, boss travel to {list(boss)}"
            return {"mode": "explore", "to": list(boss), "cap": None}, f"champion, {price}, no route to boss {list(boss)} under moves {sorted(moves)}, exploring toward it"
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
        if here in ENDGAME_ROOMS:
            # inside the League w/ the next hall gated: hold the travel goal so the executor
            # retries the door and the supervisor's spin-break ends the run, instead of exploring
            # Hoenn from the lobby (Route 121 at 16 badges, every mon at L100)
            return {"mode": "travel", "to": list(target)}, f"at cap {cap}, {badges} badges, at {ENDGAME_ROOMS[here]} w/ no route on to {list(target)}, holding for the door"
        hop = graph.route(here, target, field_moves=frozenset())
        return {"mode": "explore", "to": list(target), "cap": None}, f"at cap {cap}, {badges} badges, here {list(here)}, no League travel route under moves {sorted(moves)}, {len(hops)} maps reachable, hop {list(hop) if hop else None}, exploring toward {list(target)}"
    if gym is None:
        target = min(unbeaten, key=lambda g: ALL_GYMS[g])
        return {"mode": "explore", "to": list(target), "cap": None}, f"at cap {cap}, no gym reachable over world edges, exploring toward {list(target)}"
    goal = {"mode": "gym", "map": list(gym), "badges": badges, "flags": sum(league_flags(status))}
    stand = GYM_STAND.get(gym) or leader_stand(gym)
    if stand is not None:
        goal["stand"] = list(stand)
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
    if not status["party"]:
        print(f"status {age}s old holds no party (written off the field), executor {'running' if executor_running() else 'stopped'}, goal unchanged")
        return
    lead = status["party"][0]
    graph = build_graph(GRAPH, flags=frozenset(status.get("gate_flags", [])),
                        tickets=frozenset(status.get("tickets", [])),
                        hidden=frozenset(tuple(m) for m in status.get("hidden_givers", [])))
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
