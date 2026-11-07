"""Errands.sell_at_counter driven headless against mart_buy.ss: back out to the overworld, inject a
mixed Items pocket, walk to the counter, and sell. The clerk takes only the sellable stacks at full
quantity and the non-sellables stay, read back off the bag and the money delta. mart_buy.ss freezes
inside the buy menu, so the drive steps back to CB2_OVERWORLD before it starts."""
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import emu_boot as eb  # noqa: E402
import play  # noqa: E402
import rowe_symbols as S  # noqa: E402
from routines import MART_COUNTER_TILE  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "states", "fixtures", "mart_buy.ss")
# Escape Rope and Repel are not sellable loot; Big Pearl and Star Piece are.
INJECT = [(89, 1), (121, 2), (90, 3), (123, 1)]


def _inject_items(e, slots):
    sb1 = e.u32(S.addr("gSaveBlock1Ptr"))
    sb2 = e.u32(S.addr("gSaveBlock2Ptr"))
    key = e.u32(sb2 + S.SB2_ENCRYPTION_KEY) & 0xFFFF
    raw = b"".join(struct.pack("<HH", iid, qty ^ key) for iid, qty in slots)
    e.write(sb1 + S.SB1_BAG_ITEMS, raw + struct.pack("<HH", 0, 0))


def test_sell_takes_only_the_sellables_at_full_stack():
    e = eb.Emu()
    e.load_state(open(FIXTURE, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-test-sell.json")
    for _ in range(6):
        if p.g.callback2() == S.CB2_OVERWORLD and not e.read(S.FIELD_LOCKED, 1)[0]:
            break
        p.errands.tap(eb.KEY_B)
        p.errands.run(45, 0)
    assert p.g.callback2() == S.CB2_OVERWORLD, "fixture never reached the overworld"
    _inject_items(e, INJECT)
    money_before = p.g.money()

    assert p.errands.nav.walk_to(MART_COUNTER_TILE) == "arrived"
    sold = p.errands.sell_at_counter()

    assert sold == {121: 2, 123: 1}
    assert p.g.money() - money_before == 12400
    assert p.g.items() == [(89, 1), (90, 3)]
    assert p.g.callback2() == S.CB2_OVERWORLD


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
