"""Ever Grande (0,8) is two halves: the shore holds the Victory Road entrance (18,41) and the Center
door, the plateau holds the League door (18,5) and the Victory Road exit (18,27). Victory Road 1F
(24,43) is a south half and a north half joined only through B1F (24,44) and B2F (24,45), and B1F's
two halves join only through B2F. The live run left B2F by the ladder into B1F's south half, came up
into 1F's south half, took the one door it could reach back to the shore, found the League door
unreachable, gated (0,8)->(16,10) and spent the night exploring Hoenn (states/grind.log, "travel
(0, 8) -> [16, 10] warp: stuck (blocked)"). The region route threads the dungeon on the ROM layouts
and names the ladder that reaches the far half, so each crossing lands where the next one starts."""
import region_route
from routines import landing_rank

SHORE = (0, 67)
CITY, VR1F, VRB1F, VRB2F, LEAGUE = (0, 8), (24, 43), (24, 44), (24, 45), (16, 10)
NEIGHBORS = {CITY: {(0, 43), (16, 12), VR1F, LEAGUE}, VR1F: {CITY, VRB1F}, VRB1F: {VR1F, VRB2F},
             VRB2F: {VRB1F}, (16, 12): {CITY, (16, 13)}, (16, 13): {(16, 12)}}


def _allowed(m):
    return NEIGHBORS.get(m, set())


def test_shore_to_league_threads_victory_road_down_and_back_up():
    steps = region_route.route(CITY, SHORE, LEAGUE, _allowed, surf=True, climb=True)
    assert steps is not None, "no region route from the shore to League1F"
    maps = [s.dest for s in steps]
    assert maps == [VR1F, VRB1F, VRB2F, VRB1F, VR1F, CITY, LEAGUE], maps
    assert (18, 41) in steps[0].tiles, steps[0].tiles
    # the B2F ladders that come up into B1F's north half, never (30,25) or (43,2) into the south
    assert steps[3].tiles & {(5, 26), (19, 12)} and not steps[3].tiles & {(30, 25), (43, 2)}, steps[3].tiles
    assert (39, 5) in steps[5].tiles, steps[5].tiles
    # the League door pad reads blocked, so the reach holds the tile below it and the portal names the door
    assert steps[-1].tiles == {(18, 6)} and (18, 5) in steps[-1].portal.landings, steps[-1]


def test_without_the_waterfall_climb_b2f_does_not_connect():
    assert region_route.route(CITY, SHORE, LEAGUE, _allowed, surf=True, climb=False) is None


MOVES = frozenset(("CUT", "DIVE", "ROCKCLIMB", "ROCKSMASH", "SURF", "WATERFALL"))


def _graph(tmp_path, gates: list):
    """A MapGraph over NEIGHBORS w/ the given (src, dst, reason) gates recorded at the live token,
    badge count and move set, the shape the shore stuck and the 1F bounce left on disk."""
    import map_graph
    g = map_graph.MapGraph(str(tmp_path / "map_graph.json"), world=NEIGHBORS)
    g.cur_badges = 16
    for src, dst, reason in gates:
        g.block(src, dst, MOVES, reason=reason)
    return g


def test_open_hops_reads_a_half_gate_open_only_on_a_layout_pair(tmp_path):
    # (0,8)->(0,43) is a ROM border, (0,8)->(16,12) a ROM warp, (0,8)->(0,1) a pair no portal of (0,8) names
    g = _graph(tmp_path, [(CITY, (0, 43), "stuck"), (CITY, (16, 12), "no_sailor"), (CITY, (0, 1), "stuck")])
    g.world[CITY].add((0, 1))
    allowed = region_route.open_hops(g, CITY, frozenset(), MOVES)
    assert (0, 43) in allowed(CITY), "a stuck gate on a border pair sealed the layout search"
    assert (16, 12) not in allowed(CITY), "a no_sailor gate on a warp pair opened"
    assert (0, 1) not in allowed(CITY), "a stuck gate on a pair w/ no ROM portal opened"
    assert VR1F not in region_route.open_hops(g, CITY, frozenset({VR1F}), MOVES)(CITY), "a run-local block opened"


def test_half_gates_from_the_shore_and_1f_south_do_not_seal_the_league(tmp_path):
    # the live run's gates: the League door stuck from the shore, the city bounced from 1F's south half
    g = _graph(tmp_path, [(CITY, LEAGUE, "stuck"), (VR1F, CITY, "bounce")])
    sealed = region_route.route(CITY, SHORE, LEAGUE, lambda m: g.passable(m, frozenset(), MOVES), surf=True, climb=True)
    assert sealed is None, "the map-level gates alone should seal the route; the control is broken"
    steps = region_route.route(CITY, SHORE, LEAGUE, region_route.open_hops(g, CITY, frozenset(), MOVES), surf=True, climb=True)
    assert steps is not None and [s.dest for s in steps] == [VR1F, VRB1F, VRB2F, VRB1F, VR1F, CITY, LEAGUE], steps


def test_landing_rank_chain_demotes_the_ladder_into_the_dead_half():
    # from B1F into 1F, (8,3) lands at (9,14) in the south half and (20,21) at (21,32) in the north.
    # One hop ahead both halves hold a door to the city; two hops ahead only the north reaches the League.
    one, _, _ = landing_rank(VR1F, CITY, surf=False)
    assert one((9, 14))[0] == 0 and one((21, 32))[0] == 0, (one((9, 14)), one((21, 32)))
    two, _, _ = landing_rank(VR1F, CITY, surf=False, chain=(LEAGUE,))
    assert two((9, 14))[0] == 1, two((9, 14))
    assert two((21, 32))[0] == 0, two((21, 32))


def test_shared_border_portals_split_by_connection_offset():
    """(1,62)'s west edge meets (1,85) at offset 0, (1,58) at 40 and (1,65) at 80. Each edge portal
    holds only the border tiles whose shifted y lands inside its neighbour, so a route to (1,58)
    never aims at a tile that steps into (1,85)."""
    edges = {p.dest: p for p in region_route.portals((1, 62)) if p.kind == "edge"}
    assert set(edges) == {(1, 85), (1, 58), (1, 65)}, sorted(edges)
    for dest, lo, hi in (((1, 85), 0, 20), ((1, 58), 40, 70), ((1, 65), 80, 100)):
        ys = {y for _x, y in edges[dest].landings}
        assert ys and ys <= set(range(lo, hi)), (dest, sorted(ys))
    assert (0, 5) not in edges[(1, 58)].landings and (0, 5) in edges[(1, 85)].landings
    assert (0, 48) in edges[(1, 58)].landings
    assert all(0 <= ly < 30 for _lx, ly in edges[(1, 58)].landings.values())
