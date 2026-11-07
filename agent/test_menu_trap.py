"""A script-opened menu B never leaves ends the run after MENU_TAP_CAP presses and gates the talked
door; a crossing that moves the party over a gated edge drops the gate and its stuck tally."""
import collections
import os

import pytest

import map_graph
import play
import rowe_symbols as S

VERDANTURF, TENT = (6, 0), (6, 1)
MOVES = frozenset({"SURF", "CUT"})


def _graph(tmp_path) -> map_graph.MapGraph:
    return map_graph.MapGraph(os.path.join(tmp_path, "map_graph.json"))


def _menu_player(graph) -> play.Player:
    p = play.Player.__new__(play.Player)
    party_cb2 = next(iter(S.CB2_PARTY_MENU))
    p.g = type("G", (), {"callback2": staticmethod(lambda: party_cb2), "in_battle": staticmethod(lambda: False),
                         "party": staticmethod(lambda: [object()]), "position": staticmethod(lambda: (6, 6) + VERDANTURF)})()
    p.graph = graph
    p.tap = lambda *_a, **_k: None
    p.run = lambda *_a, **_k: None
    p.field_moves = lambda: MOVES
    p.keep_state = False
    p._cutscene_cb2 = None
    p._menu_cb2 = None
    p._menu_taps = 0
    p._script_cross = (VERDANTURF, TENT)
    return p


def test_menu_cap_ends_the_run_and_gates_the_script_door(tmp_path):
    graph = _graph(tmp_path)
    p = _menu_player(graph)
    for _ in range(play.MENU_TAP_CAP - 1):
        assert p.cutscene_step() is True
    with pytest.raises(play.GoalExit, match="menu stuck"):
        p.cutscene_step()
    assert p.keep_state, "the pre-menu snapshot is the resume point"
    reloaded = _graph(tmp_path)
    assert reloaded._gate_shut(VERDANTURF, TENT, MOVES), "the talked door is gated on disk under the live move set"
    assert reloaded.gate_reason[(VERDANTURF, TENT)] == "script_menu"


def test_field_return_resets_the_tap_count(tmp_path):
    p = _menu_player(_graph(tmp_path))
    for _ in range(play.MENU_TAP_CAP - 1):
        p.cutscene_step()
    p.g.callback2 = staticmethod(lambda: S.CB2_OVERWORLD)
    assert p.cutscene_step() is False
    assert p._menu_taps == 0


def _cross_player(graph, landed: tuple, exits: set) -> play.Player:
    p = play.Player.__new__(play.Player)
    p.g = type("G", (), {"position": staticmethod(lambda: (0, 0) + landed)})()
    p.graph = graph
    p.goal = {"mode": "travel"}
    p._blocked, p._bounced, p._stuck = {}, {}, {}
    p._last_hop, p._last_hop_dest, p._returned = None, None, False
    p._visit_log = collections.deque(maxlen=play.CYCLE_WINDOW)
    p._landing_exits = lambda: exits
    p.field_moves = lambda: MOVES
    p._stuck_hits = {}
    p._script_cross = (VERDANTURF, TENT)
    return p


def test_a_crossing_that_moved_drops_the_gate_and_its_tally(tmp_path):
    falls, boss = (24, 0), (24, 107)
    graph = _graph(tmp_path)
    graph.observe(falls, [boss])
    graph.block(falls, boss, MOVES, reason="stuck")
    assert graph.route(falls, boss, field_moves=MOVES) is None
    p = _cross_player(graph, boss, {falls})
    p._stuck_hits[p._stuck_key(falls, boss, MOVES)] = 3
    p._after_cross(falls + (1, 3), boss, ("map_changed", "moved"), dest=boss)
    assert graph.route(falls, boss, field_moves=MOVES) == boss
    assert _graph(tmp_path).gated == {}, "the dropped gate is gone from disk"
    assert p._stuck_hits == {}
    assert p._script_cross is None
