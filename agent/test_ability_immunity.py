"""rank_moves against the real ROM tables: a foe whose ability nullifies the move's type scores it at 0x."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from battle_engine import rank_moves  # noqa: E402
from rowe_state import BattleMon  # noqa: E402

HORN_ATTACK, FURY_ATTACK, QUICK_ATTACK, WATER_PULSE = 30, 31, 98, 352
GOLDEEN, SLUGMA = 118, 218
MAGMA_ARMOR, EVAPORATE = 40, 308
FIRE, WATER, MYSTERY = 10, 11, 9


def goldeen() -> BattleMon:
    return BattleMon(battler=0, species=GOLDEEN, level=31, hp=55, max_hp=79,
                     moves=(FURY_ATTACK, QUICK_ATTACK, HORN_ATTACK, WATER_PULSE), pp=(18, 30, 25, 20),
                     types=(WATER, WATER, MYSTERY), ability=0, status1=0, stat_stages=(6,) * 8, nickname="Goldeen",
                     atk=58, dfn=45, spd=50, sp_atk=42, sp_def=40)


def slugma(ability: int) -> BattleMon:
    return BattleMon(battler=1, species=SLUGMA, level=20, hp=56, max_hp=56, moves=(0, 0, 0, 0), pp=(0, 0, 0, 0),
                     types=(FIRE, FIRE, MYSTERY), ability=ability, status1=0, stat_stages=(6,) * 8, nickname="Slugma",
                     atk=25, dfn=32, spd=27, sp_atk=35, sp_def=28)


def test_water_pulse_scores_zero_into_evaporate():
    ranked = rank_moves(goldeen(), slugma(EVAPORATE))
    pulse = next(s for s in ranked if s.move.id == WATER_PULSE)
    assert pulse.effectiveness == 0 and pulse.damage == 0
    assert ranked[0].move.id == HORN_ATTACK


def test_water_pulse_stays_the_pick_into_magma_armor():
    ranked = rank_moves(goldeen(), slugma(MAGMA_ARMOR))
    assert ranked[0].move.id == WATER_PULSE and ranked[0].effectiveness == 2
