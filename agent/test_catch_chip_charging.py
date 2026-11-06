"""weakening_move must never hand the catch chip a two-turn/charging move. The first turn of
Dig/Fly/Solar Beam/Skull Bash deals no damage and shows no action menu, so the per-turn read
desyncs onto Bag and the action grid wedges (PROGRESSION stream-watch 2026-10-31 01:22 ET).

The chip is the hardest hit that leaves the foe standing. Close Combat KOs here, Dig is the hardest
safe hit, so an unfixed weakening_move hands it to the chip; the fix must skip it and fall to
Constrict, the one single-turn hit left under the KO line."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from battle_engine import CHARGING_EFFECTS, weakening_move  # noqa: E402
from rowe_state import BattleMon  # noqa: E402

# Dig effect 155 (semi-invulnerable), Close Combat effect 285 and Constrict effect 70 (single-turn)
DIG, CLOSE_COMBAT, CONSTRICT = 91, 370, 132
MYSTERY = 9


def _user() -> BattleMon:
    return BattleMon(battler=0, species=923, level=45, hp=139, max_hp=139,
                     moves=(DIG, CLOSE_COMBAT, CONSTRICT, 0), pp=(10, 5, 35, 0), types=(3, 1, MYSTERY),
                     ability=0, status1=0, stat_stages=(6,) * 8, nickname="Pawmot",
                     atk=139, dfn=89, spd=115, sp_atk=76, sp_def=73)


def _foe() -> BattleMon:
    return BattleMon(battler=1, species=820, level=40, hp=250, max_hp=250, moves=(33, 0, 0, 0),
                     pp=(35, 0, 0, 0), types=(0, MYSTERY, MYSTERY), ability=0, status1=0,
                     stat_stages=(6,) * 8, nickname="Greedent", atk=80, dfn=90, spd=40,
                     sp_atk=40, sp_def=40)


def test_chip_never_a_charging_move():
    chip = weakening_move(_user(), _foe())
    assert chip is not None, "a single-turn chip was available and should have been picked"
    assert chip.move.effect not in CHARGING_EFFECTS, f"charging effect {chip.move.effect} chosen"
    assert chip.move.id == CONSTRICT, f"expected Constrict fallback, got move id {chip.move.id}"


def test_chip_is_the_hardest_hit_under_the_ko_line():
    foe = _foe()
    foe.hp = foe.max_hp = 400
    chip = weakening_move(_user(), foe)
    assert chip.move.id == CLOSE_COMBAT, f"Close Combat leaves a 400 HP foe standing and out-hits Constrict, got {chip.move.id}"


if __name__ == "__main__":
    test_chip_never_a_charging_move()
    test_chip_is_the_hardest_hit_under_the_ko_line()
    print("test_catch_chip_charging OK")
