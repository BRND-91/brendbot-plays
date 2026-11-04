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


def _bounce_player(graph, returned=True):
    p = play.Player.__new__(play.Player)
    p.graph = graph
    p.g = type("_G", (), {"badges": lambda self: 8})()
    p._blocked = {}
    p._stuck = {}
    p._bounces = {}
    p._returned = returned
    p.field_moves = lambda: MOVES
    return p


class _BounceGraph:
    cur_badges = 8

    def __init__(self, calls):
        self._calls = calls

    def neighbors(self, hop):
        # more than just the way back, so the first-pass block in _blocked_from is not what fires
        return {(0, 12), (0, 27)}

    def block(self, *a, **k):
        self._calls["block"] += 1


def test_sole_door_bounce_demotes_instead_of_gating():
    # (4,5) is an interior whose only outdoor door is (0,12). when the walk bounces straight back
    # through that door BOUNCE_STREAK times, gating it would re-wall the pocket that
    # test_interior_sole_exit_is_never_gated guards, so the run demotes to a wild grind and leaves
    # the door open. the old code suppressed the bounce block here and did nothing, so the executor
    # ping-ponged (4,5)<->(0,12) for the whole budget and the stream froze on the doorway
    calls = {"block": 0, "demote": 0}
    p = _bounce_player(_BounceGraph(calls))
    p.demote_to_grind = lambda here: calls.__setitem__("demote", calls["demote"] + 1)
    region, hop = (4, 5, 0, 2), (0, 12)
    for _ in range(play.BOUNCE_STREAK):
        p._last_hop = (region, hop)
        p._blocked_from(region)
    assert calls["demote"] == 1, "a bounced sole interior door must demote to grind"
    assert calls["block"] == 0, "the sole door must stay ungated, or the pocket re-walls"


def test_outdoor_bounce_still_gates_the_border():
    # control: (0,19)->(0,3) is an outdoor border, so _never_dead does not apply and the bounce
    # block still marks it dead after BOUNCE_STREAK, proving the demote is scoped to interior doors
    calls = {"block": 0, "demote": 0}
    p = _bounce_player(_BounceGraph(calls))
    p.demote_to_grind = lambda here: calls.__setitem__("demote", calls["demote"] + 1)
    region, hop = (0, 19, 0, 2), (0, 3)
    for _ in range(play.BOUNCE_STREAK):
        p._last_hop = (region, hop)
        p._blocked_from(region)
    assert calls["block"] == 1, "an outdoor border must still gate after BOUNCE_STREAK"
    assert calls["demote"] == 0, "an outdoor border is not a pocket door, so it never demotes"
