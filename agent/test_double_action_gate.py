"""GameState.choosing reads the chooser's controller, not a hardcoded battler 0. In a wild double
the player's second mon picks its action as battler 2 while battler 0's controller has gone idle at
0x83aa958; a gate reading battler 0 alone sees idle, skips the decision and wedges the turn (the
[24,0] Golbat + Lunatone double). choosing(b) keyed on the chooser runs the decision for b."""
import rowe_symbols as S
from rowe_state import GameState

IDLE = 0x083AA958  # battler 0's controller once it has chosen, the ctrl the wedge dump reports


class _Emu:
    def __init__(self, funcs: dict):
        self._funcs = funcs  # {battler index: controller func value}

    def u32(self, addr: int) -> int:
        battler = (addr - S.BATTLER0_CONTROLLER_FUNC) // S.CONTROLLER_FUNC_STRIDE
        return self._funcs[battler]


def test_choosing_keys_on_the_chooser():
    # battler 0 has chosen (idle), battler 2 is the live chooser on the action pick: a gate reading
    # battler 0 returns IDLE and skips the turn, the double wedge. choosing(2) must see battler 2.
    g = GameState(_Emu({0: IDLE, 2: S.PLAYER_CHOOSE_ACTION}))
    assert g.choosing(2) is True, "battler 2 is on the action pick, the decision must run"
    assert g.choosing(0) is False, "battler 0 has gone idle, not choosing"


def test_single_battle_unchanged():
    # a single battle only ever chooses as battler 0, so keying on the chooser is a no-op there
    g = GameState(_Emu({0: S.PLAYER_CHOOSE_ACTION}))
    assert g.choosing(0) is True


if __name__ == "__main__":
    test_choosing_keys_on_the_chooser()
    test_single_battle_unchanged()
    print("test_double_action_gate OK")
