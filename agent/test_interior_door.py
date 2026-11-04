"""An interior map's door is never a dead border. The executor bounce- and stuck-gated the sole exit
of a Lavaridge interior (4,5)->(0,12), walling the save in a pocket, and every run exited travel stuck
until the supervisor stopped. _never_dead keeps an indoor map's one non-indoor warp open, and the
no-route exit keeps the last snapshot instead of baking the wedged tile into live.ss."""
import pytest

import map_graph
import play


MOVES = frozenset({"CUT", "DIVE", "ROCKCLIMB", "ROCKSMASH", "SURF", "WATERFALL"})


def _player(graph):
    p = play.Player.__new__(play.Player)
    p.graph = graph
    p._stuck_hits = {}
    p._save_stuck_hits = lambda: None
    p.field_moves = lambda: MOVES
    return p


def _graph(tmp_path):
    g = map_graph.MapGraph(str(tmp_path / "g.json"))
    g.cur_badges = 8
    return g


def test_interior_sole_exit_is_never_gated(tmp_path):
    # (4,5) is indoor and its only warp to a non-indoor map goes to (0,12); STUCK_GATE stuck
    # crossings must leave that door open
    g = _graph(tmp_path)
    p = _player(g)
    for _ in range(play.STUCK_GATE + 1):
        p._persist_blocked((4, 5), (0, 12), "stuck")
    assert not g._gate_shut((4, 5), (0, 12), MOVES), "an interior's sole door was gated shut"


def test_overworld_border_still_gates(tmp_path):
    # control: (0,19) is an outdoor route, so the guard does not apply and STUCK_GATE still gates it,
    # proving the exemption is scoped to interiors and not a blanket off switch
    g = _graph(tmp_path)
    p = _player(g)
    for _ in range(play.STUCK_GATE + 1):
        p._persist_blocked((0, 19), (0, 3), "stuck")
    assert g._gate_shut((0, 19), (0, 3), MOVES), "an outdoor border must still gate after STUCK_GATE"


def test_no_route_exit_keeps_the_last_snapshot():
    class _Graph:
        cur_badges = 0

        def route(self, *a, **k):
            return None

        def explore_hop(self, *a, **k):
            return None

    class _G:
        def position(self):
            return (2, 2, 4, 5)

        def badges(self):
            return 0

    p = play.Player.__new__(play.Player)
    p.graph = _Graph()
    p.g = _G()
    p._gyms = set()
    p.goal = {"mode": "grind", "map": [0, 27]}
    p.keep_state = False
    p.field_moves = lambda: frozenset()
    p.region = lambda: (4, 5, 2, 2)
    p._blocked_from = lambda region: set()
    with pytest.raises(play.GoalExit):
        p.travel_toward((0, 27))
    assert p.keep_state is True, "a no-route exit must keep the last good snapshot"
