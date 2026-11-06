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
    er.nav = type("N", (), {"walk_to": lambda self, tile, **k: "arrived"})()
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
    assert er.talk_warp((5, 5), ISLAND, "One Island", approach=(5, 6)) == "locked"


def test_talk_warp_menu_still_open_is_stuck():
    # field held but the menu is still up: the party never cleared the row, which is stuck, not locked
    er = _errands(menu_second={0: "One Island"})
    assert er.talk_warp((5, 5), ISLAND, "One Island", approach=(5, 6)) == "stuck"


def test_talk_warp_row_confirm_crosses():
    # the island row is selected, the yes/no is answered, and the map flips to dest: map_changed.
    # guards the row+confirm path (part 3's A-on-Yes loop); the live yes/no is proven by grind.log
    er = Errands.__new__(Errands)
    er.e = type("E", (), {"read": lambda self, addr, n: [1]})()
    er.nav = type("N", (), {"walk_to": lambda self, tile, **k: "arrived"})()
    er.run = lambda *a, **k: None
    er.tap = lambda *a, **k: None
    er._menu_rows = lambda: {0: "One Island"}
    calls = {"n": 0}

    def map_id() -> tuple:
        calls["n"] += 1
        return SRC if calls["n"] <= 3 else ISLAND

    er.map_id = map_id
    assert er.talk_warp((5, 5), ISLAND, "One Island", approach=(5, 6)) == "map_changed"


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


def _door_errands(flip_after: int, land_map: tuple) -> Errands:
    """talk_warp harness for a label=None scripted door: map_id returns the source for the first
    `flip_after` reads then `land_map`, so the return turns on where the party lands after the A's."""
    er = Errands.__new__(Errands)
    er.e = type("E", (), {"read": lambda self, addr, n: [1]})()
    er.nav = type("N", (), {"walk_to": lambda self, tile, **k: "arrived"})()
    er.run = lambda *a, **k: None
    er.tap = lambda *a, **k: None
    calls = {"n": 0}

    def map_id() -> tuple:
        calls["n"] += 1
        return SRC if calls["n"] <= flip_after else land_map

    er.map_id = map_id
    return er


def test_door_warps_to_dest_is_map_changed():
    er = _door_errands(flip_after=2, land_map=ISLAND)
    assert er.talk_warp((5, 5), ISLAND, None, approach=(5, 6)) == "map_changed"


def test_door_warps_elsewhere_is_wrong_map():
    er = _door_errands(flip_after=2, land_map=(1, 1))
    assert er.talk_warp((5, 5), ISLAND, None, approach=(5, 6)) == "wrong_map"


def test_door_never_fires_is_locked():
    # map never leaves src and the field stays held (read -> [1]): an unmet event flag, not stuck
    er = _door_errands(flip_after=999, land_map=ISLAND)
    assert er.talk_warp((5, 5), ISLAND, None, approach=(5, 6)) == "locked"


def test_three_island_sailor_is_a_labeled_ferry():
    # part 2: (0,79) joined the dock set, so the Three Island sailor's Slateport arm resolves a menu
    # label and _cross_to routes it as a ferry row pick, not a label=None door. Its (13,10) arm has
    # no label and stays an unlabeled door, and the Hoenn dock sailor still labels its island arms.
    import script_decode as sd
    assert (0, 79) in sd.SEAGALLOP_DOCKS
    assert sd.seagallop_label((0, 79), (9, 9)) == "Slateport City"
    assert sd.seagallop_label((0, 79), (13, 10)) is None
    assert (9, 9) in sd.script_edges().get((0, 79), {})
    assert sd.seagallop_label((9, 9), (0, 75)) == "One Island", "the dock sailor still takes a label"


def test_three_island_sailor_approach_is_above():
    # part 1: the sailor at (12,13) is FACE_UP (movement 7), so talk_object resolves the approach to
    # the tile above (12,12), reachable from the party's landing at (12,0). The old below-tile (12,14)
    # is not reachable, which is why every crossing died "unreachable".
    import script_decode as sd
    import rowe_rom
    import nav
    obj = sd.talk_object((0, 79), (9, 9))
    assert obj is not None and obj["obj"] == (12, 13), obj
    assert obj["approach"] == (12, 12), obj
    w, h, cells = rowe_rom.map_cells(0, 79)
    grid = nav.Grid.from_cells(w, h, cells)
    grid._behavior = rowe_rom.metatile_behavior(0, 79)
    reach = grid.reachable((12, 0), False)
    assert (12, 12) in reach, "the approach above the sailor is reachable from the landing"
    assert (12, 14) not in reach, "the old below-tile approach is not reachable, the original block"


def main() -> None:
    test_talk_warp_locked_row_returns_locked()
    test_talk_warp_menu_still_open_is_stuck()
    test_talk_warp_row_confirm_crosses()
    test_locked_gates_on_first_failure()
    test_stuck_row_still_needs_the_tally()
    test_door_warps_to_dest_is_map_changed()
    test_door_warps_elsewhere_is_wrong_map()
    test_door_never_fires_is_locked()
    test_three_island_sailor_is_a_labeled_ferry()
    test_three_island_sailor_approach_is_above()
    print("test_dock_lock: ok")


if __name__ == "__main__":
    main()
