"""The unstick slot bar fires only on a move the ROM refused. A battle frozen four steps on a held
text box (gBattleCommunication 5, the state every live unstick in grind.log sat in) is not the
last pick's fault, and barring it there dropped Pawmot's Close Combat for Spark x0 vs Excadrill and
Greedent's Bite then Covet for Rollout x0.5 vs Garchomp, for the rest of each fight. The move list
(comm 3) and the selection-script box (comm 6) are the two states a refused pick leaves behind."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import play  # noqa: E402
import rowe_symbols as S  # noqa: E402
from rowe_state import BattleMon  # noqa: E402

CLOSE_COMBAT, SPARK = 370, 209
MYSTERY = 9
ELECTRIC, FIGHTING, GROUND, STEEL = 13, 1, 4, 8


class _G:
    def __init__(self, comm: int):
        self._comm = comm

    def callback2(self):
        return S.CB2_BATTLE_MAIN

    def comm(self, battler=0):
        return self._comm

    def in_move_list(self, battler=0):
        return self._comm == S.MOVE_LIST_COMM_STATE

    def in_selection_script(self, battler=0):
        return self._comm == S.SELECTION_SCRIPT_COMM_STATE

    def disabled_move(self, battler=0):
        return 0


def _pawmot() -> BattleMon:
    return BattleMon(battler=0, species=923, level=50, hp=150, max_hp=150,
                     moves=(0, 0, CLOSE_COMBAT, SPARK), pp=(0, 0, 2, 20), types=(ELECTRIC, FIGHTING, MYSTERY),
                     ability=0, status1=0, stat_stages=(6,) * 8, nickname="Pawmot", personality=7,
                     atk=139, dfn=89, spd=115, sp_atk=76, sp_def=73)


def _excadrill() -> BattleMon:
    return BattleMon(battler=1, species=530, level=48, hp=173, max_hp=173, moves=(33, 0, 0, 0),
                     pp=(35, 0, 0, 0), types=(GROUND, STEEL, MYSTERY), ability=0, status1=0,
                     stat_stages=(6,) * 8, nickname="Excadrill", personality=3,
                     atk=135, dfn=60, spd=88, sp_atk=50, sp_def=65)


def _player(comm: int) -> play.Player:
    p = play.Player.__new__(play.Player)
    p.g = _G(comm)
    p._avoid_slots, p._start_items, p._used_slots = set(), {}, {}
    p._last_pick, p._act_stuck = 2, 4
    return p


def _pick_after_unstick(comm: int) -> int:
    p = _player(comm)
    me, foe = _pawmot(), _excadrill()
    p._bar_frozen_slot(me)
    return p.pick_move(me, [foe])


def test_freeze_off_the_move_list_keeps_the_pick():
    assert _pick_after_unstick(5) == 2, "Close Combat x2 barred by a freeze on a text box, Spark x0 picked"


def test_freeze_on_the_move_list_bars_the_pick():
    assert _pick_after_unstick(S.MOVE_LIST_COMM_STATE) == 3, "a pick the list bounced back is barred for the battle"


def test_freeze_at_the_selection_box_bars_the_pick():
    assert _pick_after_unstick(S.SELECTION_SCRIPT_COMM_STATE) == 3, "a pick the box refused is barred for the battle"


if __name__ == "__main__":
    test_freeze_off_the_move_list_keeps_the_pick()
    test_freeze_on_the_move_list_bars_the_pick()
    test_freeze_at_the_selection_box_bars_the_pick()
    print("test_unstick_bar OK")
