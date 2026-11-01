"""map_loaded against the ROM's Petalburg Woods layout (48x44): the buffer the player
arrives with is still Route 104's 55x94, the rebuilt one is 63x58. Grid.path over
literal maps: land before water under surf, water only when land has no route."""
import struct

import rowe_rom
import rowe_symbols as S
from nav import Grid, map_loaded

WOODS_LAYOUT = 0x0876D364  # mapLayout pointer gMapHeader holds inside Petalburg Woods


class _Emu:
    def __init__(self, buffer_dims: tuple):
        self.buffer_dims = buffer_dims

    def read(self, address: int, length: int = 1) -> bytes:
        assert address == S.addr("gBackupMapLayout") and length == 8, (hex(address), length)
        return struct.pack("<ii", *self.buffer_dims)

    def u32(self, address: int) -> int:
        assert address == S.addr("gMapHeader") + S.MAPHDR_LAYOUT, hex(address)
        return WOODS_LAYOUT


WATER = S.SURF_ELEVATION << S.GRID_ELEVATION_SHIFT
# current tiles carry a metatile id the behavior table maps to the MB_*WARD_CURRENT value
CURRENT_IDS = {">": (1, 0x50), "<": (2, 0x51), "^": (3, 0x52), "v": (4, 0x53)}


def _grid(rows: list) -> Grid:
    """A Grid over a literal map: '.' land at elevation 3, '~' water, '#' blocked, 'O' a warp
    tile (open floor that fires a map change on contact), '<' '>' '^' 'v' a water current
    flowing that way."""
    g = Grid.__new__(Grid)
    h, w = len(rows), len(rows[0])
    g.width, g.height = w + 2 * S.MAP_OFFSET, h + 2 * S.MAP_OFFSET
    cells = [S.GRID_UNDEFINED | S.GRID_BLOCKED] * (g.width * g.height)
    warps = set()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in CURRENT_IDS:
                cell = WATER | CURRENT_IDS[ch][0]
            else:
                cell = {".": 3 << S.GRID_ELEVATION_SHIFT, "~": WATER,
                        "#": S.GRID_BLOCKED, "O": 3 << S.GRID_ELEVATION_SHIFT}[ch]
            cells[(y + S.MAP_OFFSET) * g.width + x + S.MAP_OFFSET] = cell
            if ch == "O":
                warps.add((x, y))
    g.cells = tuple(cells)
    g.blocked_by_npc = set()
    g.warp_tiles = warps
    g._behavior = None
    if any(ch in CURRENT_IDS for row in rows for ch in row):
        beh = {i: b for i, b in CURRENT_IDS.values()}
        g._behavior = lambda mid: beh.get(mid, 0x15 if mid == 0 else 0)
    return g


def main() -> None:
    assert map_loaded(_Emu((55, 94))) is False, "Route 104's buffer is stale inside the Woods"
    assert map_loaded(_Emu((63, 58))) is True, "48x44 plus the margin is the Woods buffer"

    # a pond between start and goal: 2 steps across the water, 6 around it by land
    pond = _grid([".....",
                  ".~~~.",
                  ".....",
                  ])
    assert len(pond.path((0, 1), (4, 1), surf=False)) == 6
    assert len(pond.path((0, 1), (4, 1), surf=True)) == 6, "land route wins while one exists"
    channel = _grid([".~~~."])
    assert channel.path((0, 0), (4, 0), surf=False) is None
    assert len(channel.path((0, 0), (4, 0), surf=True)) == 4, "water is the fallback"

    # a water current carries the surfer the way it flows until still water: pressing into a
    # westward current from its west bank lands the surfer back where it started, so no route
    # runs east through it (Route 134's rapids), while an eastward current is one press across
    rapids = _grid(["~<<~"])
    assert rapids.path((0, 0), (3, 0), surf=True) is None, "routed east through a westward current"
    assert len(rapids.path((3, 0), (0, 0), surf=True)) == 1, "riding the current west is one press"
    assert (3, 0) not in rapids.reachable((0, 0), surf=True), "the far bank reads reachable against the flow"
    flow = _grid(["~>>~"])
    assert len(flow.path((0, 0), (3, 0), surf=True)) == 1, "riding the current east is one press"
    assert flow.passable(1, 0, 0, (0, 0), surf=True) is False, "a current tile is never a tile to stand on"
    # a current that runs off the map carries the surfer into the next map (Route 132's belts
    # into Route 133), so the ride ends on the margin tile past the edge and the crossing is one press
    belt_out = _grid(["<<~"])
    assert belt_out.path((2, 0), (-1, 0), surf=True) == [(-1, 0)], "a belt off the west edge is one press into the margin"
    assert belt_out.path((2, 0), (0, 0), surf=True) is None, "the belt's own tiles are still no place to stand"

    # a Granite Cave hole on the straight path: the walk detours around it (6 steps, not the
    # 4 straight through) so it never falls to the level below while crossing to somewhere else
    cave = _grid([".....",
                  "..O..",
                  ".....",
                  ])
    assert len(cave.path((0, 1), (4, 1))) == 6, "route goes around the hole, never onto it"
    tile, steps = (0, 1), cave.path((0, 1), (4, 1))
    for dx, dy in steps:
        tile = (tile[0] + dx, tile[1] + dy)
        assert tile != (2, 1), "the hole is never stepped on mid-route"
    # the hole as the goal is reachable: taking the warp on purpose still works
    onto = cave.path((0, 1), (2, 1))
    assert onto is not None and len(onto) == 2, "the hole is reachable when it is the goal"

    # Petalburg off the ROM: the west gate at row 12 opens on a pond-locked northwest corner,
    # the one at row 29 on the town proper, where the east exit to Route 102 is rows 27-29
    w, h, cells = rowe_rom.map_cells(0, 0)
    assert (w, h) == (36, 40), (w, h)
    town = Grid.from_cells(w, h, cells)
    east = {(35, 27), (35, 28), (35, 29)}
    assert east.isdisjoint(town.reachable((0, 12), surf=False)), "row 12 lands in the enclave"
    # a directional ledge (MB_JUMP_SOUTH = 0x3B): one DOWN press hops the player over the ledge to
    # the tile two south, the reverse is refused, and the ledge tile is never stood on. The map
    # flags the ledge collision, so a grid reading every collision tile as a wall finds no way south.
    def _beh(mid):
        return 0x3B if mid == 5 else 0x00
    ledge = Grid.__new__(Grid)
    ledge.width, ledge.height = 1 + 2 * S.MAP_OFFSET, 3 + 2 * S.MAP_OFFSET
    buf = [S.GRID_UNDEFINED | S.GRID_BLOCKED] * (ledge.width * ledge.height)
    for y, v in enumerate((3, 5 | S.GRID_BLOCKED, 3)):  # land, south-jump ledge (collision), land
        buf[(y + S.MAP_OFFSET) * ledge.width + S.MAP_OFFSET] = v
    ledge.cells, ledge.blocked_by_npc, ledge.warp_tiles, ledge._behavior = tuple(buf), set(), set(), _beh
    assert ledge.path((0, 0), (0, 2)) == [(0, 1)], "one DOWN press hops the south ledge, two tiles in one move"
    assert ledge.path((0, 2), (0, 0)) is None, "the ledge is one-way: no route back north over it"
    wbuf = list(buf)
    wbuf[(1 + S.MAP_OFFSET) * ledge.width + S.MAP_OFFSET] = 4 | S.GRID_BLOCKED  # beh 0x00: a plain wall
    wall = Grid.__new__(Grid)
    wall.width, wall.height = ledge.width, ledge.height
    wall.cells, wall.blocked_by_npc, wall.warp_tiles, wall._behavior = tuple(wbuf), set(), set(), _beh
    assert wall.path((0, 0), (0, 2)) is None, "a collision tile with a non-ledge behavior still blocks"
    # a directionally impassable tile (MB_IMPASSABLE_NORTH = 0x32, open floor, no collision bit):
    # the game refuses a step onto it heading south and a step north off it, the two moves the
    # Petalburg pond bank at (23, 19) refused the surfer, and allows the approach from the south
    def _nbeh(mid):
        return 0x32 if mid == 6 else 0x00
    north = Grid.__new__(Grid)
    north.width, north.height = ledge.width, ledge.height
    nbuf = list(buf)
    nbuf[(1 + S.MAP_OFFSET) * north.width + S.MAP_OFFSET] = 6 | (3 << S.GRID_ELEVATION_SHIFT)
    north.cells, north.blocked_by_npc, north.warp_tiles, north._behavior = tuple(nbuf), set(), set(), _nbeh
    assert north.path((0, 0), (0, 2)) is None, "no step south onto an impassable-north tile"
    assert north.path((0, 2), (0, 1)) == [(0, -1)], "the same tile is entered from the south"
    assert north.path((0, 1), (0, 0)) is None, "no step north off an impassable-north tile"
    print("test_nav: 20 passed")


if __name__ == "__main__":
    main()
