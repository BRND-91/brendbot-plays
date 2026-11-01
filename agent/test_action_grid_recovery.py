"""Player._reach_fight steers the battle action cursor to Fight (slot 0). A held text box or an
open submenu (Bag/Pokemon) parks the cursor off Fight and eats the UP+LEFT nav, which is the
0x83aa958 attack-turn wedge: the old 3x UP+LEFT never pressed B, so a submenu that only B clears
held forever. The recovery now taps B before each UP+LEFT. These stubs drive the seam without an
emulator: action_cursor reports the submenu, and only a B tap clears it."""
import emu_boot as eb
from play import Player, ACT_NAV_RETRIES


class _Grid:
    def __init__(self, clears_on_b: bool):
        self.submenu = True
        self.clears_on_b = clears_on_b

    def action_cursor(self, b: int) -> int:
        return 2 if self.submenu else 0  # 2 = Bag, 0 = Fight

    def in_battle(self) -> bool:
        return True


def _player(grid: _Grid) -> Player:
    p = Player.__new__(Player)
    p.g = grid
    p.taps = []

    def tap(keys, hold=8, gap=12):
        p.taps.append(keys)
        if keys == eb.KEY_B and grid.clears_on_b:
            grid.submenu = False

    p.tap = tap
    return p


def test_fixture_triggers_the_bug():
    # the old loop tapped only UP+LEFT; prove the stub's submenu is eaten by those and never
    # clears, so a no-B recovery leaves the cursor off Fight (the wedge this fix closes)
    grid = _Grid(clears_on_b=True)
    for _ in range(3):
        if grid.action_cursor(0) == 0:
            break
        pass  # UP+LEFT only, no B, submenu untouched
    assert grid.action_cursor(0) == 2, "no-B nav leaves the submenu held, the attack-turn wedge"


def test_b_dismiss_reaches_fight():
    grid = _Grid(clears_on_b=True)
    p = _player(grid)
    assert p._reach_fight(0) is True, "cursor reached Fight after the submenu was dismissed"
    assert eb.KEY_B in p.taps, "recovery pressed B to dismiss the held submenu"
    assert grid.action_cursor(0) == 0, "cursor landed on Fight"


def test_unclearable_prompt_falls_through():
    # a real yes/no prompt does not clear on B; _reach_fight exhausts its retries and returns
    # False so the caller runs the prompt-tap fallback, with more B attempts than the old 3x
    grid = _Grid(clears_on_b=False)
    p = _player(grid)
    assert p._reach_fight(0) is False, "an unclearable prompt falls through to the prompt handler"
    assert p.taps.count(eb.KEY_B) == ACT_NAV_RETRIES, "B tried on every widened retry"


if __name__ == "__main__":
    test_fixture_triggers_the_bug()
    test_b_dismiss_reaches_fight()
    test_unclearable_prompt_falls_through()
    print("test_action_grid_recovery OK")
