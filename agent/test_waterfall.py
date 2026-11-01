"""Grid.path over a waterfall: the fall is a one-way ride up from the water under it, taken
only w/ the Waterfall Tool, and never a tile to stand on or to surf down."""
import rowe_symbols as S
from nav import Grid, WATERFALL

WATER = S.SURF_ELEVATION << S.GRID_ELEVATION_SHIFT
IDS = {".": (0, 0x00), "~": (1, 0x15), "W": (2, WATERFALL)}
UP = (0, -1)


def _grid(rows: list, climb: bool) -> Grid:
    """'.' land, '~' water, 'W' waterfall; the behavior table maps each metatile id."""
    g = Grid.__new__(Grid)
    h, w = len(rows), len(rows[0])
    g.width, g.height = w + 2 * S.MAP_OFFSET, h + 2 * S.MAP_OFFSET
    cells = [S.GRID_UNDEFINED | S.GRID_BLOCKED] * (g.width * g.height)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            mid = IDS[ch][0]
            cells[(y + S.MAP_OFFSET) * g.width + x + S.MAP_OFFSET] = mid | (WATER if ch != "." else 3 << S.GRID_ELEVATION_SHIFT)
    g.cells = tuple(cells)
    g.blocked_by_npc = set()
    g.warp_tiles = set()
    g.climb = climb
    beh = {mid: b for mid, b in IDS.values()}
    g._behavior = lambda mid: beh.get(mid, 0)  # the undefined margin reads as plain floor
    return g


def main() -> None:
    rows = [".",   # 0 bank above the fall
            "W",   # 1
            "W",   # 2
            "~",   # 3 water under the fall
            "."]   # 4 bank below
    g = _grid(rows, climb=True)
    assert g.path((0, 4), (0, 0), surf=True) == [UP, UP], g.path((0, 4), (0, 0), surf=True)
    assert g.path((0, 4), (0, 0), surf=False) is None, "the ride needs Surf under it"
    assert g.path((0, 0), (0, 4), surf=True) is None, "no ride down the fall"
    assert g.path((0, 4), (0, 2), surf=True) is None, "a waterfall tile is never stood on"
    assert _grid(rows, climb=False).path((0, 4), (0, 0), surf=True) is None, "no ride without the tool"
    print("test_waterfall OK")


if __name__ == "__main__":
    main()
