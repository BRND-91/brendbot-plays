"""Errands.menu_step takes the short way round a wrapping list: one row up is one UP tap, never a
lap of DOWN, which is what the start menu and the Trainer Skills list used to cost."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb
from routines import START_MENU_ROWS, Errands


def test_short_way_round():
    assert START_MENU_ROWS == 12
    assert Errands.menu_step(1, 3, 12) == (eb.KEY_DOWN, 2)
    assert Errands.menu_step(4, 1, 12) == (eb.KEY_UP, 3), "Trainer Skills row down to Pokémon is three UP taps"
    assert Errands.menu_step(11, 0, 12) == (eb.KEY_DOWN, 1), "the last row wraps to the first on one DOWN"
    assert Errands.menu_step(0, 11, 12) == (eb.KEY_UP, 1)
    assert Errands.menu_step(21, 16, 25) == (eb.KEY_UP, 5), "Speed Boost back to HP Boost on the skills list"
    assert Errands.menu_step(7, 7, 12)[1] == 0
