"""talk_menu drives a native multichoice NPC down a nested path of row labels, one label per level,
to a leaf like the island clerk's ticket handout. The emulator seam is faked the way test_dock_lock
fakes talk_warp: FIELD_LOCKED reads gate the menu-open detection and the closing-text clear,
_menu_rows returns the rows live at each level, and the assert is the status the caller reads before
it checks the bag for the granted item."""
from routines import Errands

CLERK, APPROACH = (4, 2), (4, 4)   # clerk behind a one-tile counter: stand two below, face up


def _errands(levels: list, lock_reads: list) -> Errands:
    """Errands with the emulator faked. `levels` is the row dict _menu_rows returns on each successive
    call; `lock_reads` is the FIELD_LOCKED byte returned on each successive read, last value held."""
    er = Errands.__new__(Errands)
    reads = {"n": 0}

    def read(addr: int, n: int) -> list:
        i = reads["n"]
        reads["n"] += 1
        return [lock_reads[i] if i < len(lock_reads) else lock_reads[-1]]

    er.e = type("E", (), {"read": lambda self, addr, n: read(addr, n)})()
    er.nav = type("N", (), {"walk_to": lambda self, tile: "arrived"})()
    er.run = lambda *a, **k: None
    er.tap = lambda *a, **k: None
    er.map_id = lambda: (1, 14)
    calls = {"n": 0}

    def menu() -> dict:
        i = calls["n"]
        calls["n"] += 1
        return levels[i] if i < len(levels) else {}

    er._menu_rows = menu
    return er


def test_nested_path_completes():
    er = _errands(levels=[{0: "Tickets", 1: "Cancel"}, {0: "One Island", 1: "Two Island"}],
                  lock_reads=[1, 0])
    assert er.talk_menu(CLERK, ["Tickets", "One Island"], approach=APPROACH) == "done"


def test_field_held_at_end_is_stuck():
    er = _errands(levels=[{0: "Tickets"}, {0: "One Island"}], lock_reads=[1])
    assert er.talk_menu(CLERK, ["Tickets", "One Island"], approach=APPROACH) == "stuck"


def test_missing_row_reports_label():
    er = _errands(levels=[{0: "Heal", 1: "Cancel"}], lock_reads=[1, 1])
    assert er.talk_menu(CLERK, ["Tickets"], approach=APPROACH) == "no_row:Tickets"


def test_menu_never_opens():
    er = _errands(levels=[{0: "Tickets"}], lock_reads=[0])
    assert er.talk_menu(CLERK, ["Tickets"], approach=APPROACH) == "no_menu"


def test_offaxis_approach_raises():
    er = _errands(levels=[{0: "Tickets"}], lock_reads=[1])
    try:
        er.talk_menu(CLERK, ["Tickets"], approach=(5, 6))
    except ValueError:
        return
    assert False, "a diagonal approach must raise, not pick a wrong facing"


def main() -> None:
    test_nested_path_completes()
    test_field_held_at_end_is_stuck()
    test_missing_row_reports_label()
    test_menu_never_opens()
    test_offaxis_approach_raises()
    print("test_talk_menu: ok")


if __name__ == "__main__":
    main()
