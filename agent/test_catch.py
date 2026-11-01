"""helper_slot against the ROM tables: a bench Trubbish w/ Poison Gas sets up a catch the lead would one-shot."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from catch import BALL_RESERVE, Ledger, catch_chance, helper_slot, status_move_slot  # noqa: E402
from rowe_state import BattleMon, PartyMon  # noqa: E402

TACKLE, GUST, BITE, POISON_GAS, STUN_SPORE = 33, 16, 44, 139, 78
PIDGEOTTO, HERDIER, TRUBBISH, CRAMORANT = 17, 507, 568, 845
MYSTERY = 9


def cramorant() -> BattleMon:
    return BattleMon(battler=1, species=CRAMORANT, level=9, hp=34, max_hp=34, moves=(TACKLE, 0, 0, 0), pp=(35, 0, 0, 0),
                     types=(2, 11, MYSTERY), ability=0, status1=0, stat_stages=(6,) * 8, nickname="Cramorant",
                     atk=18, dfn=17, spd=20, sp_atk=16, sp_def=17)


def pidgeotto() -> BattleMon:
    return BattleMon(battler=0, species=PIDGEOTTO, level=22, hp=61, max_hp=65, moves=(TACKLE, GUST, 0, 0),
                     pp=(35, 35, 0, 0), types=(0, 2, MYSTERY), ability=0, status1=0, stat_stages=(6,) * 8,
                     nickname="Pidgeotto", atk=42, dfn=36, spd=45, sp_atk=35, sp_def=36)


def mon(slot, species, name, move, atk=45) -> PartyMon:
    return PartyMon(slot=slot, species=species, level=21, hp=60, max_hp=60, moves=(move, 0, 0, 0), pp=(20, 0, 0, 0),
                    status=0, experience=0, friendship=0, nickname=name, personality=0,
                    atk=atk, dfn=35, spd=30, sp_atk=25, sp_def=30)


def test_bench_status_mover_is_the_helper():
    party = [mon(0, PIDGEOTTO, "Pidgeotto", GUST), mon(2, HERDIER, "Herdier", BITE), mon(4, TRUBBISH, "Trubbish", POISON_GAS)]
    assert helper_slot(party, pidgeotto(), cramorant()) == 4


def test_poison_gas_is_no_softener_against_a_poison_type():
    # Weedle is Bug/Poison (6, 3): Poison Gas does nothing, Stun Spore in the next slot still works
    weedle = cramorant()
    weedle.species, weedle.nickname, weedle.types = 13, "Weedle", (6, 3, MYSTERY)
    trubbish = pidgeotto()
    trubbish.moves, trubbish.pp = (POISON_GAS, 0, 0, 0), (40, 0, 0, 0)
    assert status_move_slot(trubbish, weedle) is None
    assert status_move_slot(trubbish, cramorant()) == 0, "the same move still softens a Flying/Water foe"
    trubbish.moves, trubbish.pp = (POISON_GAS, STUN_SPORE, 0, 0), (40, 30, 0, 0)
    assert status_move_slot(trubbish, weedle) == 1


def test_status_mover_skipped_once_the_foe_carries_a_status():
    party = [mon(0, PIDGEOTTO, "Pidgeotto", GUST), mon(4, TRUBBISH, "Trubbish", POISON_GAS)]
    poisoned = cramorant()
    poisoned.status1 = 0x08
    assert helper_slot(party, pidgeotto(), poisoned) is None


def test_bench_of_one_shotters_gives_no_helper():
    party = [mon(0, PIDGEOTTO, "Pidgeotto", GUST), mon(2, HERDIER, "Herdier", BITE, atk=120)]
    assert helper_slot(party, pidgeotto(), cramorant()) is None


def test_out_of_range_species_is_uncatchable_not_a_crash():
    # a species id past the ROM table (3689, seen on Route 103) has no catch_rate row; catch_chance
    # returns 0 instead of raising, or the battle step crash-loops the run and empties the live
    # HLS segments
    foe = cramorant()
    foe.species = 3689
    assert catch_chance(foe) == 0.0
    foe.species = -1
    assert catch_chance(foe) == 0.0


def test_in_range_species_gives_real_odds():
    foe = cramorant()
    foe.hp = 1  # 1/34 HP, so odds land well inside (0, 1]
    assert 0.0 < catch_chance(foe) <= 1.0


def test_last_balls_go_to_wanted_types_only(tmp_path):
    ledger = Ledger(str(tmp_path / "caught.json"), [PIDGEOTTO])
    foe = cramorant()  # Flying/Water, uncaught
    assert ledger.wants(foe, frozenset(), BALL_RESERVE + 1)
    assert not ledger.wants(foe, frozenset(), BALL_RESERVE), "the reserve holds for a type nobody needs"
    assert ledger.wants(foe, frozenset({11}), BALL_RESERVE), "a Water foe spends the reserve when Water is wanted"
    assert not ledger.wants(pidgeotto(), frozenset({0, 2}), BALL_RESERVE + 5), "a caught species never gets a ball"
