"""The Lilycove Department Store 4F clerks read off the ROM, and tm_shopping buys only what
tm_assignments would teach, within the money past the reserve."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rowe_rom  # noqa: E402
from play import MONEY_RESERVE, tm_shopping  # noqa: E402
from test_team import NO_IVS, Mon  # noqa: E402
from test_tms import DRAGON_BUILD, GREEDENT, LAPRAS, TM13_ICE_BEAM, TM24_THUNDERBOLT, WATER_GUN  # noqa: E402

DEPT_STORE_4F = (13, 19)
TM25_THUNDER, TM75_SWORDS_DANCE, TM90_SUBSTITUTE = 506, 556, 571
FLAG_RECEIVED_BADGE05, FLAG_RECEIVED_BADGE10 = 0xE29, 0xE2E


def test_4f_clerks_read_off_the_rom_with_their_badge_gates():
    rows = {(x, y): (flags, sorted(map(len, lists))) for x, y, flags, lists in rowe_rom.clerk_marts(*DEPT_STORE_4F)}
    assert set(rows) == {(7, 6), (9, 6)}, rows
    assert rows[(7, 6)] == ([FLAG_RECEIVED_BADGE10], [1, 13]) and rows[(9, 6)] == ([FLAG_RECEIVED_BADGE05], [1, 16]), rows
    left = {x: lists for x, _, _, lists in rowe_rom.clerk_marts(*DEPT_STORE_4F)}[7]
    assert TM25_THUNDER in max(left, key=len) and min(left, key=len) == [TM75_SWORDS_DANCE]
    assert [TM90_SUBSTITUTE] in {x: lists for x, _, _, lists in rowe_rom.clerk_marts(*DEPT_STORE_4F)}[9]


def test_tm_shopping_buys_the_assignment_within_budget_and_skips_a_bag_copy():
    mons = [Mon(i, GREEDENT, 41, [WATER_GUN]) for i in range(5)] + [Mon(5, LAPRAS, 41, [WATER_GUN])]
    clerks = [((7, 6), [TM24_THUNDERBOLT, TM13_ICE_BEAM])]
    price = rowe_rom.item_price(TM13_ICE_BEAM)
    assert tm_shopping(mons, NO_IVS, [], price + MONEY_RESERVE, clerks, DRAGON_BUILD) == [((7, 6), [(TM13_ICE_BEAM, 1)])]
    assert tm_shopping(mons, NO_IVS, [], price + MONEY_RESERVE - 1, clerks, DRAGON_BUILD) == [], "the reserve is never spent"
    assert tm_shopping(mons, NO_IVS, [(TM13_ICE_BEAM, 1)], 10 ** 6, clerks, DRAGON_BUILD) == [], "a bag copy is taught, not bought"
