"""Victory Road B1F (24,44) is sealed from its 1F ladder landing (8,3) by two Strength boulders,
(4,7) and (9,10): every tile past them, the B2F ladders included, read unreachable, the executor
gated (24,44)->(24,45) as stuck, and the planner fell back to exploring Hoenn's sea routes.

The push rule plans the boulders: (4,7) goes west from (5,7) and (9,10) east from (8,10), each
onto open floor, while the shorter push of (4,7) south wedges it in the corridor's corner, so
the plan has to carry the boulder it moved. Executing a push needs the map's Power Glove prompt
accepted once.

Fixtures: states/fixtures/vr_b1f_entry.ss is the live party on the B1F landing (8,3);
states/fixtures/vr_b1f_at_5_7.ss is the same party beside the first boulder, prompt unanswered.
"""
import os

import pytest

import emu_boot as eb
import play
from nav import Grid, Navigator

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(BASE, "states", "fixtures")
B2F_LADDER = (30, 25)


def _player(name: str) -> play.Player:
    e = eb.Emu()
    e.load_state(open(os.path.join(FIXTURES, name), "rb").read())
    return play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-strength-boulder-test.json")


def _walk(start: tuple, steps: list) -> list:
    tiles, cur = [start], start
    for d in steps:
        cur = (cur[0] + d[0], cur[1] + d[1])
        tiles.append(cur)
    return tiles


def test_b1f_landing_routes_to_the_b2f_ladder_by_pushing_both_boulders_sideways():
    p = _player("vr_b1f_entry.ss")
    grid = p._grid()
    grid.tools = p.field_moves()
    assert grid.pushable == {(4, 7), (9, 10)}
    steps = grid.path((8, 3), B2F_LADDER, surf=True)
    assert steps is not None, "no path across the boulders from the landing"
    tiles = _walk((8, 3), steps)
    assert tiles[-1] == B2F_LADDER
    first = tiles.index((4, 7))
    assert (tiles[first - 1], steps[first - 1]) == ((5, 7), (-1, 0)), "the first boulder goes west, off the corridor"
    second = tiles.index((9, 10))
    assert (tiles[second - 1], steps[second - 1]) == ((8, 10), (1, 0)), "the second boulder goes east, off the corridor"


def test_wedging_push_is_not_planned():
    p = _player("vr_b1f_entry.ss")
    grid = p._grid()
    # (4,7) pushed south three times ends at the corner (4,10) with the walker behind it; the
    # search carries the moved boulder, so that line never reaches the corridor east of the corner
    assert grid.path((8, 3), (5, 10), surf=True) is not None
    tiles = _walk((8, 3), grid.path((8, 3), (5, 10), surf=True))
    assert (4, 10) not in tiles


def test_push_executes_through_the_power_glove_prompt():
    p = _player("vr_b1f_at_5_7.ss")
    nav = Navigator(p.e, p.run)
    assert not p.g.flag(0xCF9)
    r = nav.walk_to((4, 8), surf=False, tools=p.field_moves())
    if r == "battle":
        pytest.skip("a wild encounter rolled on the two-tile walk")
    assert r == "arrived", r
    assert p.g.position()[:2] == (4, 8)
    assert Grid(p.e).pushable == {(3, 7), (9, 10)}, "the boulder did not move west"
