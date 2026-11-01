"""TM readers against the ROM tables, and tm_assignments over four Greedent and two Lapras facing a Dragon."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rowe_rom  # noqa: E402
from play import tm_assignments  # noqa: E402
from test_team import NO_IVS, Mon  # noqa: E402

GREEDENT, LAPRAS = 820, 131
TACKLE, WATER_GUN, ICE_BEAM, THUNDERBOLT, FOCUS_PUNCH, DIVE = 33, 55, 58, 85, 264, 291
TM01, TM13_ICE_BEAM, TM24_THUNDERBOLT, HM08 = 482, 494, 505, 689
MODEST, ADAMANT = 15, 3  # +SpA -Atk, +Atk -SpA
DRAGON = 16
DRAGON_BUILD = [[(DRAGON, DRAGON)]]


def test_tm_tables_read_off_the_rom():
    assert rowe_rom.tm_move(TM01) == FOCUS_PUNCH and rowe_rom.tm_move(TM13_ICE_BEAM) == ICE_BEAM and rowe_rom.tm_move(HM08) == DIVE
    assert TM13_ICE_BEAM in rowe_rom.tm_learnset(LAPRAS) and TM13_ICE_BEAM not in rowe_rom.tm_learnset(GREEDENT)
    assert rowe_rom.tm_learnset(0) == frozenset()


def test_level_up_learnset_reads_off_the_rom():
    BULBASAUR, BEAUTIFLY, GUST = 1, 267, 16
    rows = rowe_rom.level_up_learnset(BULBASAUR)
    assert rows[0] == (1, TACKLE) and len(rows) == 18, rows
    rows = rowe_rom.level_up_learnset(BEAUTIFLY)
    assert rows[0] == (0, GUST), "the on-evolution move sits at level 0"
    assert rowe_rom.move(rows[-1][1]).name == "Hurricane" and rows[-1][0] == 60, rows[-1]


def test_egg_moves_key_on_the_first_stage():
    PAWMI, PAWMO, WURMPLE, BEAUTIFLY, STOUTLAND = 921, 922, 265, 267, 508
    assert rowe_rom.first_stage(PAWMO) == PAWMI and rowe_rom.first_stage(STOUTLAND) == 506 and rowe_rom.first_stage(PAWMI) == PAWMI
    pawmo = [rowe_rom.move(m).name for m in rowe_rom.egg_moves(PAWMO)]
    assert "Mach Punch" in pawmo and pawmo == [rowe_rom.move(m).name for m in rowe_rom.egg_moves(PAWMI)], pawmo
    assert rowe_rom.egg_moves(BEAUTIFLY) == () and rowe_rom.first_stage(BEAUTIFLY) == WURMPLE


def test_an_egg_move_closes_a_gap_within_the_bp_budget():
    from play import egg_assignments
    STOUTLAND = 508
    ice_fang = next(i for i in range(1, rowe_rom.MOVE_COUNT) if rowe_rom.move(i).name == "Ice Fang")
    mons = [Mon(i, GREEDENT, 41, [TACKLE]) for i in range(5)] + [Mon(5, STOUTLAND, 41, [TACKLE])]
    assert egg_assignments(mons, NO_IVS, 8, DRAGON_BUILD) == [(5, 0, ice_fang)]
    declined = frozenset({(STOUTLAND, ice_fang)})
    assert all(mv != ice_fang for _, _, mv in egg_assignments(mons, NO_IVS, 8, DRAGON_BUILD, declined)), "a move her list never offered is skipped"
    assert egg_assignments(mons, NO_IVS, 3, DRAGON_BUILD) == [], "under one move's BP nothing is bought"


def party() -> list:
    mons = [Mon(i, GREEDENT, 41, [TACKLE]) for i in range(4)] + [Mon(4, LAPRAS, 41, [WATER_GUN]), Mon(5, LAPRAS, 41, [WATER_GUN])]
    mons[4].nature, mons[5].nature = ADAMANT, MODEST
    return mons


def test_an_ice_tm_lands_on_the_core_member_with_the_higher_spa():
    plan = tm_assignments(party(), NO_IVS, [(TM13_ICE_BEAM, 1)], DRAGON_BUILD)
    assert plan == [(0, 5, 0, ICE_BEAM)], plan


def test_a_tm_off_the_gaps_stays_in_the_bag():
    assert tm_assignments(party(), NO_IVS, [(TM24_THUNDERBOLT, 1)], DRAGON_BUILD) == []


def test_a_tm_nobody_can_learn_stays_in_the_bag():
    mons = [Mon(i, GREEDENT, 41, [TACKLE]) for i in range(6)]
    assert tm_assignments(mons, NO_IVS, [(TM13_ICE_BEAM, 1)], DRAGON_BUILD) == []
