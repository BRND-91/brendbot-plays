"""The height gate: a step between open tiles of different heights is refused, a transition
tile (0) opens the next step to any height, a multi-level tile (7) keeps the height walked
in, and a surfer dismounts onto height 3 alone. Pinned on literal grids and on Lilycove's
real layout, where the item ball at (57, 12) sits behind the 4 -> 3 edge at (53, 12) the game
refused (probe_lilycove_ball.py, press test: 4->3 moved False, 4->4 moved True)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rowe_rom
import rowe_symbols as S
from nav import Grid


def strip(heights: list, water: set = frozenset()) -> Grid:
    """A one-row grid, each cell at the given height; water cells carry the pond behavior."""
    g = Grid.__new__(Grid)
    g.width, g.height = len(heights) + 2 * S.MAP_OFFSET, 1 + 2 * S.MAP_OFFSET
    buf = [S.GRID_UNDEFINED | S.GRID_BLOCKED] * (g.width * g.height)
    for x, h in enumerate(heights):
        buf[S.MAP_OFFSET * g.width + S.MAP_OFFSET + x] = (h << S.GRID_ELEVATION_SHIFT) | (1 if x in water else 0)
    g.cells, g.blocked_by_npc, g.warp_tiles = tuple(buf), set(), set()
    g._behavior = lambda mid: 0x10 if mid == 1 else 0x00
    return g


def main() -> None:
    assert strip([3, 3, 3]).path((0, 0), (2, 0)) == [(1, 0), (1, 0)]
    assert strip([4, 3, 3]).path((0, 0), (2, 0)) is None, "4 -> 3 is a cliff"
    assert strip([3, 4, 4]).path((0, 0), (2, 0)) is None, "3 -> 4 is a cliff"
    assert strip([4, 0, 3]).path((0, 0), (2, 0)) == [(1, 0), (1, 0)], "a transition tile joins the heights"
    assert strip([3, 0, 4]).path((2, 0), (0, 0)) == [(-1, 0), (-1, 0)], "and in the other direction"
    assert strip([4, 7, 7, 4]).path((0, 0), (3, 0)) is not None, "a deck keeps the height walked in"
    assert strip([4, 7, 7, 3]).path((0, 0), (3, 0)) is None, "so its far end at another height refuses"
    assert strip([3, 7, 3]).path((0, 0), (2, 0)) is not None
    # surf: mounted from height 3, left onto height 3; the water under a deck is still water,
    # and a surfer who rides under the deck carries the water's height onto a height-4 bank
    assert strip([3, 1, 3], {1}).path((0, 0), (2, 0), surf=True) == [(1, 0), (1, 0)]
    assert strip([3, 1, 4], {1}).path((0, 0), (2, 0), surf=True) is None, "no dismount onto height 4"
    assert strip([4, 1, 3], {1}).path((0, 0), (2, 0), surf=True) is None, "no mount from height 4"
    assert strip([3, 1, 7, 4], {1}).path((0, 0), (3, 0), surf=True) is None, "under the deck and out onto 4 is refused"
    assert strip([3, 1, 7, 1, 3], {1, 3}).path((0, 0), (4, 0), surf=True) is not None, "under the deck and on is water"
    assert (2, 0) in strip([3, 1, 7], {1}).reachable((0, 0), surf=True), "the deck tile itself takes the surfer"

    # Lilycove off the ROM: the strip (54..56, 12) beside the ball is height 3, entered only
    # from (53, 12) at height 4, so no side of the ball is reachable from the town floor
    w, h, cells = rowe_rom.map_cells(0, 5)
    town = Grid.from_cells(w, h, cells)
    town._behavior = rowe_rom.metatile_behavior(0, 5)
    assert town.cell(53, 12) >> S.GRID_ELEVATION_SHIFT == 4 and town.cell(54, 12) >> S.GRID_ELEVATION_SHIFT == 3
    assert town.path((53, 13), (56, 12)) is None, "the ball's only open side is behind the cliff edge"
    assert town.path((53, 13), (53, 12)) == [(0, -1)], "the cliff-top tile beside it is still floor"
    print("test_elevation: 17 passed")


if __name__ == "__main__":
    main()
