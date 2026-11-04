"""A Seagallop dock-menu row drawn locked (an island not yet open) holds the field with a no-go box
after the A and never moves the party. talk_warp returns "locked" for that, distinct from "stuck"
(the party reached the row but the menu never cleared), and _cross_to gates the ferry script edge on
the first "locked" under script_no_go rather than spending STUCK_GATE runs the way a stuck border does.
Pre-fix talk_warp returned "stuck" for a locked row and _persist_blocked ran it through the three-miss
tally, so each locked island (One, Two) cost three runs before it gated."""
import os
import tempfile

from map_graph import MapGraph
from play import Player
from routines import Errands

SRC, ISLAND = (13, 10), (0, 75)   # the (13,10) Seagallop dock, One Island arm (0,75), drawn locked
FM = frozenset()


def _errands(menu_second: dict) -> Errands:
    """A talk_warp harness that fakes the emulator seam: the field stays held (FIELD_LOCKED set) and
    the map never changes, so the return turns on whether the menu is gone by the terminal read."""
    er = Errands.__new__(Errands)
    er.e = type("E", (), {"read": lambda self, addr, n: [1]})()
    er.nav = type("N", (), {"walk_to": lambda self, tile: "arrived"})()
    er.run = lambda *a, **k: None
    er.tap = lambda *a, **k: None
    er.map_id = lambda: SRC
    calls = {"n": 0}

    def menu() -> dict:
        calls["n"] += 1
        return {0: "One Island"} if calls["n"] == 1 else menu_second

    er._menu_rows = menu
    return er


def test_talk_warp_locked_row_returns_locked():
    er = _errands(menu_second={})
    assert er.talk_warp((5, 5), ISLAND, "One Island") == "locked"


def test_talk_warp_menu_still_open_is_stuck():
    # field held but the menu is still up: the party never cleared the row, which is stuck, not locked
    er = _errands(menu_second={0: "One Island"})
    assert er.talk_warp((5, 5), ISLAND, "One Island") == "stuck"


def _player(graph: MapGraph) -> Player:
    p = Player.__new__(Player)
    p.graph = graph
    p._stuck_hits = {}
    p.field_moves = lambda: FM
    return p


def test_locked_gates_on_first_failure():
    path = tempfile.mkstemp(suffix=".json")[1]
    os.remove(path)
    try:
        g = MapGraph(path)
        g.observe(SRC, [ISLAND])
        assert g.explore_hop(SRC, field_moves=FM) == ISLAND, "the ferry arm is the only open border"
        p = _player(g)
        p._persist_blocked(SRC, ISLAND, "locked")
        assert g.explore_hop(SRC, field_moves=FM) is None, "a locked ferry row gates on the first failure"
        assert g.gate_reason[(SRC, ISLAND)] == "script_no_go", "the locked gate carries script_no_go"
        assert not p._stuck_hits, "a locked row never enters the STUCK_GATE tally"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_stuck_row_still_needs_the_tally():
    # the first-failure gate is the locked branch only: a stuck ferry row still rides STUCK_GATE
    path = tempfile.mkstemp(suffix=".json")[1]
    os.remove(path)
    try:
        g = MapGraph(path)
        g.observe(SRC, [ISLAND])
        p = _player(g)
        p._persist_blocked(SRC, ISLAND, "stuck")
        assert g.explore_hop(SRC, field_moves=FM) == ISLAND, "a single stuck hit must not gate"
    finally:
        if os.path.exists(path):
            os.remove(path)


def main() -> None:
    test_talk_warp_locked_row_returns_locked()
    test_talk_warp_menu_still_open_is_stuck()
    test_locked_gates_on_first_failure()
    test_stuck_row_still_needs_the_tally()
    print("test_dock_lock: ok")


if __name__ == "__main__":
    main()
