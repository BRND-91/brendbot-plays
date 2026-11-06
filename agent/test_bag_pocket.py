"""The bag tabs wrap across ten pockets, so the walk to a pocket takes the shorter direction. The
RIGHT-only walk crossed six tabs from Poké Balls (2) to TMs (8) where LEFT reaches it in four, and
the live TM teach opened and closed the bag on every Center visit doing it."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import emu_boot as eb  # noqa: E402
from routines import bag_pocket_key  # noqa: E402


def test_short_way_round_each_direction():
    assert bag_pocket_key(2, 3) == eb.KEY_RIGHT
    assert bag_pocket_key(2, 8) == eb.KEY_LEFT, "2 to 8 is four LEFT taps against six RIGHT"
    assert bag_pocket_key(8, 1) == eb.KEY_RIGHT, "8 to 1 wraps forward in three"
    assert bag_pocket_key(9, 0) == eb.KEY_RIGHT
    assert bag_pocket_key(0, 9) == eb.KEY_LEFT


if __name__ == "__main__":
    test_short_way_round_each_direction()
    print("test_bag_pocket OK")
