"""The Items pocket reader and the sellable/fossil/repel filters that drive the Mart sell flow, the
Rustboro revive, and the travel-leg repel count. lilycove.ss holds a bag with sellables and a Repel
but no fossil, so the fossil path is exercised on a crafted bag the filter must still catch."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import play  # noqa: E402
import rowe_symbols as S  # noqa: E402
from emu_boot import Emu  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "states", "fixtures", "lilycove.ss")


@pytest.fixture(scope="module")
def g():
    e = Emu()
    e.load_state(open(FIXTURE, "rb").read())
    return play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-test-bag.json").g


def test_items_decodes_the_full_pocket(g):
    assert g.items() == [
        (90, 7), (89, 1), (67, 3), (721, 1), (68, 1),
        (121, 1), (123, 1), (122, 1), (66, 1), (118, 1),
    ]


def test_filters_pick_their_own_set_out_of_the_live_bag(g):
    assert g.sellables() == [(121, 1), (123, 1), (122, 1), (118, 1)]
    assert g.repels() == [(90, 7)]
    assert g.fossils() == []


def test_a_zeroed_slot_hides_nothing_behind_it():
    # the fossil scientist's script zeroes the taken fossil's slot in place and leaves the pocket
    # uncompacted until the next bag open; a reader that stops at the hole loses every item after it
    e = Emu()
    e.load_state(open(FIXTURE, "rb").read())
    g = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-test-hole.json").g
    sb1 = e.u32(S.addr("gSaveBlock1Ptr"))
    e.write(sb1 + S.SB1_BAG_ITEMS + 4, bytes(4))  # slot 1, the (89, 1) stack
    assert g.items() == [
        (90, 7), (67, 3), (721, 1), (68, 1),
        (121, 1), (123, 1), (122, 1), (66, 1), (118, 1),
    ]


def test_a_fossil_in_a_mixed_bag_classifies(g):
    bag = [(447, 1), (118, 2), (90, 3), (4, 10)]  # Helix Fossil, Tiny Mushroom, Repel, Poke Ball
    assert g.fossils(bag) == [(447, 1)]
    assert g.sellables(bag) == [(118, 2)]
    assert g.repels(bag) == [(90, 3)]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
