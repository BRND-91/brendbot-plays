"""best_switch against the real ROM tables: the Roxanne fight where two Flying leads fell to Nosepass."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from battle_engine import best_switch  # noqa: E402
from rowe_state import BattleMon, PartyMon  # noqa: E402

GUST, TACKLE, BITE, PECK, ROCK_THROW = 16, 33, 44, 64, 88
PIDGEY, NOSEPASS, HERDIER, FLETCHINDER = 16, 299, 507, 662
MYSTERY = 9


def nosepass(hp: int) -> BattleMon:
    return BattleMon(battler=1, species=NOSEPASS, level=12, hp=hp, max_hp=29, moves=(ROCK_THROW, TACKLE, 0, 0),
                     pp=(15, 35, 0, 0), types=(5, 5, MYSTERY), ability=0, status1=0, stat_stages=(6,) * 8,
                     nickname="Nosepass", atk=20, dfn=38, spd=12, sp_atk=17, sp_def=25)


def party_mon(slot, species, level, hp, max_hp, move, name, atk, dfn, sp_atk, sp_def) -> PartyMon:
    return PartyMon(slot=slot, species=species, level=level, hp=hp, max_hp=max_hp, moves=(move, 0, 0, 0),
                    pp=(20, 0, 0, 0), status=0, experience=0, friendship=0, nickname=name, personality=0,
                    atk=atk, dfn=dfn, spd=30, sp_atk=sp_atk, sp_def=sp_def)


def pidgey_battler(hp: int) -> BattleMon:
    return BattleMon(battler=0, species=PIDGEY, level=19, hp=hp, max_hp=52, moves=(GUST, 0, 0, 0), pp=(20, 0, 0, 0),
                     types=(0, 2, MYSTERY), ability=0, status1=0, stat_stages=(6,) * 8, nickname="Pidgey",
                     atk=30, dfn=25, spd=35, sp_atk=22, sp_def=22)


PARTY = [
    party_mon(0, PIDGEY, 19, 52, 52, GUST, "Pidgey", 30, 25, 22, 22),
    party_mon(1, FLETCHINDER, 20, 61, 61, PECK, "Flechinder", 40, 30, 32, 30),
    party_mon(2, HERDIER, 20, 60, 60, BITE, "Herdier", 45, 35, 25, 30),
]


def test_fainted_lead_sends_the_neutral_mon_not_the_next_slot():
    assert best_switch(PARTY, pidgey_battler(0), [nosepass(29)]) == 2


def test_standing_flying_lead_steps_out_for_herdier():
    assert best_switch(PARTY, pidgey_battler(52), [nosepass(29)], margin=0.25) == 2


def test_lead_that_can_finish_the_foe_stays_in():
    herdier = BattleMon(battler=0, species=HERDIER, level=20, hp=60, max_hp=60, moves=(BITE, 0, 0, 0),
                        pp=(20, 0, 0, 0), types=(0, 0, MYSTERY), ability=0, status1=0, stat_stages=(6,) * 8,
                        nickname="Herdier", atk=45, dfn=35, spd=30, sp_atk=25, sp_def=30)
    assert best_switch(PARTY, herdier, [nosepass(3)], margin=0.25) is None


def test_no_bench_with_a_damaging_move_keeps_the_fighter():
    pp_out = [party_mon(1, HERDIER, 20, 60, 60, BITE, "Herdier", 45, 35, 25, 30)]
    pp_out[0].pp = (0, 0, 0, 0)
    assert best_switch(pp_out, pidgey_battler(52), [nosepass(29)], margin=0.25) is None


POOCHYENA, ZIGZAGOON, SKWOVET, BODY_SLAM, DARK = 261, 263, 819, 34, 17


def test_low_wild_lead_steps_out_for_the_bench():
    # the grind lead at 3/18 vs a wild Zigzagoon it cannot finish, w/ a full L22 on the bench:
    # the wild-battle low-HP branch asks best_switch w/ no margin and sends the bench mon
    pooch = BattleMon(battler=0, species=POOCHYENA, level=5, hp=3, max_hp=18, moves=(TACKLE, 0, 0, 0), pp=(30, 0, 0, 0),
                      types=(DARK, DARK, MYSTERY), ability=0, status1=0, stat_stages=(6,) * 8, nickname="Poochyena",
                      atk=10, dfn=9, spd=10, sp_atk=8, sp_def=8)
    zig = BattleMon(battler=1, species=ZIGZAGOON, level=4, hp=11, max_hp=17, moves=(TACKLE, 0, 0, 0), pp=(35, 0, 0, 0),
                    types=(0, 0, MYSTERY), ability=0, status1=0, stat_stages=(6,) * 8, nickname="Zigzagoon",
                    atk=8, dfn=9, spd=10, sp_atk=7, sp_def=8)
    party = [party_mon(0, POOCHYENA, 5, 3, 18, TACKLE, "Poochyena", 10, 9, 8, 8),
             party_mon(1, SKWOVET, 22, 66, 66, BODY_SLAM, "Skwovet", 40, 35, 25, 30)]
    assert best_switch(party, pooch, [zig]) == 1
