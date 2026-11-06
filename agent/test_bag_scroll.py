"""gBagPosition keeps a cursor row and a scroll offset per pocket, and the list shows five rows, so
the cursor stops at 4 and every DOWN past it scrolls instead. A read of the cursor alone reported
row 4 for every TM from the fifth on, so the TM-teach walk to pocket slot 8 tapped DOWN sixteen
times, confirmed whatever sat under the cursor, and the live log holds eleven
`tm: pocket slot 8 on party slot 2 -> learned False` lines, one per Center visit. bag_position
reports the item index, cursor plus scroll. vr_16_13.ss holds 20 TMs on the field."""
import os

import emu_boot as eb
import play
import rowe_symbols as S

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "vr_16_13.ss")


def _open_bag(p: play.Player) -> bool:
    e, g = p.e, p.g
    p.run(60)
    for _ in range(6):
        for _ in range(2):
            p.tap(eb.KEY_B)
            p.run(20)
        p.tap(eb.KEY_START)
        p.run(60)
        for _ in range(8):
            if e.read(S.addr("sStartMenuCursorPos"))[0] == S.START_MENU_BAG:
                break
            p.tap(eb.KEY_DOWN)
            p.run(15)
        p.tap(eb.KEY_A)
        p.run(120)
        if g.callback2() == S.CB2_BAG_MAIN:
            return True
        p.run(60)
    return False


def test_bag_position_counts_the_scrolled_rows():
    e = eb.Emu()
    e.load_state(open(FIXTURE, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-bag-scroll-test.json")
    assert _open_bag(p), "the field bag never opened on the fixture"
    assert p.errands.bag_to_pocket(S.BAG_POCKET_TMS), "the TM pocket was not reached"
    for _ in range(8):
        p.tap(eb.KEY_DOWN)
        p.run(10)
    assert p.g.bag_position() == (S.BAG_POCKET_TMS, 8), p.g.bag_position()
