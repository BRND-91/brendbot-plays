"""Grid on the real Route 120 layout: a surf route never steps between a bridge tile and the
water beside it, in either direction, while a bank tile still mounts the same water."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rowe_rom as R  # noqa: E402
import rowe_symbols as S  # noqa: E402
from nav import BRIDGE_BEHAVIORS, Grid  # noqa: E402

ROUTE_120 = (0, 35)
BRIDGE, WATER_BELOW_BRIDGE = (24, 67), (24, 66)


def route_120() -> Grid:
    w, h, cells = R.map_cells(*ROUTE_120)
    g = Grid.from_cells(w, h, cells)
    g._behavior = R.metatile_behavior(*ROUTE_120)
    return g


def bank_next_to_water(g: Grid) -> tuple:
    """First open land tile on the map that is not a bridge and touches water, w/ that water tile."""
    for y in range(g.height - 2 * S.MAP_OFFSET):
        for x in range(g.width - 2 * S.MAP_OFFSET):
            c = g.cell(x, y)
            if c & S.GRID_BLOCKED or g._is_water(x, y) or g._behavior(c & S.GRID_ID_MASK) in BRIDGE_BEHAVIORS:
                continue
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                if g.inside(x + dx, y + dy) and g._is_water(x + dx, y + dy):
                    return (x, y), (x + dx, y + dy)
    raise AssertionError("no bank tile beside water on Route 120")


def one_press_targets(g: Grid, tile: tuple) -> set:
    elev = g.cell(*tile) >> S.GRID_ELEVATION_SHIFT
    return {t for t, _ in g._steps(tile, elev, tile, True)}


def test_bridge_never_steps_onto_the_water_beside_it():
    # the water is still reachable the long way round, off the bridge's end, so the rule is
    # on the single press, never on path()
    g = route_120()
    assert g._behavior(g.cell(*BRIDGE) & S.GRID_ID_MASK) == 0x72 and g._is_water(*WATER_BELOW_BRIDGE)
    assert WATER_BELOW_BRIDGE not in one_press_targets(g, BRIDGE)
    assert BRIDGE not in one_press_targets(g, WATER_BELOW_BRIDGE)


def test_long_bridge_0x71_never_steps_into_the_river():
    # the long bridge west of the Scorched Slab inlet is behavior 0x71, MB_UNUSED_71 in the
    # header and a bridge in MetatileBehavior_IsBridge; the run stood on it pressing south
    g = route_120()
    deck, river = (17, 16), (17, 17)
    assert g._behavior(g.cell(*deck) & S.GRID_ID_MASK) == 0x71 and g._is_water(*river)
    assert river not in one_press_targets(g, deck)


def test_surf_mounts_only_from_elevation_3():
    # the bridge's west end is open land at elevation 7 w/ the river below it; the game starts
    # Surf only w/ the player at elevation 3, so that step is refused like the deck's
    g = route_120()
    end, river = (10, 16), (10, 17)
    assert g._behavior(g.cell(*end) & S.GRID_ID_MASK) == 0x00 and g.cell(*end) >> S.GRID_ELEVATION_SHIFT == 7
    assert g._is_water(*river)
    assert river not in one_press_targets(g, end)


def test_bank_still_mounts_the_water():
    g = route_120()
    bank, water = bank_next_to_water(g)
    assert water in one_press_targets(g, bank)
