"""A recorded route state w/ all-zero gate bytes matches on tile alone; a recorded state w/
gate bytes matches only on tile and gates together.

The Fortree recording carries real gate orientations up to its press 55 and zeros from press
56 to the end, while the live game reads non-zero orientations on those same tiles, so an exact
compare lost the route at (1, 7) on every visit."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from routines import route_state_matches

GATES = (1, 3, 2, 1, 0, 3, 1, 2)
ZERO = (0,) * 8


def test_zero_gate_record_matches_on_tile():
    assert route_state_matches(((1, 6), GATES), ((1, 6), ZERO))
    assert not route_state_matches(((1, 7), GATES), ((1, 6), ZERO))


def test_recorded_gates_must_match():
    assert route_state_matches(((1, 7), GATES), ((1, 7), GATES))
    assert not route_state_matches(((1, 7), (1, 3, 2, 1, 0, 3, 1, 3)), ((1, 7), GATES))
