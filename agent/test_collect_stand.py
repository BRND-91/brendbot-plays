"""Errands.stand_tiles against the real Route 124 layout: the ball on the one-tile notch at (24, 42)
is picked up from the land tile beside it, never from the water in front of it."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rowe_rom as R  # noqa: E402
from nav import Grid  # noqa: E402
from routines import Errands  # noqa: E402

ROUTE_124 = (0, 34)
BALL = (24, 42)
SURFER = (26, 46)


def route_124() -> Grid:
    w, h, cells = R.map_cells(*ROUTE_124)
    g = Grid.from_cells(w, h, cells)
    g._behavior = R.metatile_behavior(*ROUTE_124)
    g.blocked_by_npc = {(x, y) for x, y, _, _ in R.map_objects(*ROUTE_124)}
    return g


def test_notch_ball_is_taken_from_the_bank_not_the_water():
    g = route_124()
    stands = [s for s, _ in Errands.stand_tiles(g, BALL, SURFER, surf=True)]
    assert stands == [(25, 42)]
    # the water side is reachable, so only the water rule keeps it out
    assert g._is_water(24, 43) and g.path(SURFER, (24, 43), surf=True) is not None
