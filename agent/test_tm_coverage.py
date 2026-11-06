"""A bag TM goes on a member whose damaging moves repeat a type, over the weakest of the repeats,
even when the next leader's gaps name no type the TM hits: a fourth Normal move on Stoutland adds
no coverage where Rock Tomb does. The gap pass keeps first claim on a TM and on a member."""
import rowe_rom as R
from rowe_state import PartyMon
import play

STOUTLAND, PAWMOT, SEAKING = 508, 923, 119
LAST_RESORT, RETALIATE, TAKE_DOWN, GIGA_IMPACT = 387, 514, 36, 416
SUPERCELL_SLAM, DISCHARGE, CLOSE_COMBAT, SPARK = 811, 435, 370, 209
WATERFALL, MEGAHORN, FISHIOUS_REND, WATER_PULSE = 127, 224, 701, 352
TM39_ROCK_TOMB, TM40_AERIAL_ACE, TM34_SHOCK_WAVE = 520, 521, 515
IVS = (0, 0, 0, 0, 0, 0)


def _mon(slot, species, moves, atk, spa) -> PartyMon:
    return PartyMon(slot=slot, species=species, level=84, hp=200, max_hp=200, moves=moves, pp=(10, 10, 10, 10),
                    status=0, experience=0, friendship=0, nickname=str(species), personality=slot + 1,
                    atk=atk, dfn=150, spd=150, sp_atk=spa, sp_def=150)


PARTY = [
    _mon(0, STOUTLAND, (LAST_RESORT, RETALIATE, TAKE_DOWN, GIGA_IMPACT), 265, 115),
    _mon(1, SEAKING, (WATERFALL, MEGAHORN, FISHIOUS_REND, WATER_PULSE), 229, 167),
    _mon(2, PAWMOT, (SUPERCELL_SLAM, DISCHARGE, CLOSE_COMBAT, SPARK), 261, 156),
]
BAG = [(TM39_ROCK_TOMB, 1), (TM40_AERIAL_ACE, 1), (TM34_SHOCK_WAVE, 1)]


def test_repeated_type_trades_its_weakest_move_for_an_off_type_tm():
    out = play.tm_assignments(PARTY, IVS, BAG, [])
    by_member = {i: (BAG[slot][0], forget, move) for slot, i, forget, move in out}
    item, forget, move = by_member[0]
    assert R.move(move).type not in {0} and PARTY[0].moves[forget] in (LAST_RESORT, RETALIATE, TAKE_DOWN, GIGA_IMPACT)
    assert item in (TM39_ROCK_TOMB, TM40_AERIAL_ACE), "Shock Wave is special and Stoutland attacks off Attack"


def test_one_tm_goes_to_one_member():
    out = play.tm_assignments(PARTY, IVS, BAG, [])
    slots = [slot for slot, *_ in out]
    assert len(slots) == len(set(slots))


def test_seaking_with_only_water_tms_in_the_bag_gets_nothing():
    out = play.tm_assignments(PARTY, IVS, BAG, [])
    assert 1 not in {i for _, i, _, _ in out}
