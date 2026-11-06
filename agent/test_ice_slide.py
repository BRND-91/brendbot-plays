"""On MB_ICE a press slides the player until the next tile is blocked or the tile landed on is not
ice, so one press moves several tiles. The Seven Island gym (2,13) is an ice floor w/ stop squares;
w/o the slide the walker planned single steps, slid into corners and reported the leader's stand
stuck 13 times. Landings measured in the emulator on a snapshot at (4,7): RIGHT (9,7), LEFT (2,7),
DOWN (4,15), UP blocked by the trainer at (4,6)."""
import rowe_rom as R
from nav import Grid

GYM = (2, 13)
TRAINERS = {(5, 3), (2, 4), (4, 6), (5, 9)}
START, STAND = (4, 7), (5, 4)


def _grid() -> Grid:
    w, h, cells = R.map_cells(*GYM)
    g = Grid.from_cells(w, h, cells)
    g._behavior = R.metatile_behavior(*GYM)
    g.blocked_by_npc = set(TRAINERS)
    return g


def _landings(g: Grid, start: tuple) -> dict:
    carried = g._start_elev(start)
    return {d: land for land, d in g._steps(start, carried, start, False)}


def test_press_slides_to_the_measured_tile():
    land = _landings(_grid(), START)
    assert land[(1, 0)] == (9, 7)
    assert land[(-1, 0)] == (2, 7)
    assert land[(0, 1)] == (4, 15)
    assert (0, -1) not in land, "the trainer on (4,6) blocks the press up"


def test_stand_is_reachable_by_sliding():
    assert _grid().path(START, STAND) is not None
