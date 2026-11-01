"""Grid.path across a cuttable tree or breakable rock: the obstacle is an object event sitting on
an otherwise walkable tile, so the route may cross it only when the clearing tool is in grid.tools,
CUT for a tree and ROCKSMASH for a rock. Without the matching tool the tile blocks like any object."""
import rowe_symbols as S
from nav import Grid

GROUND = 0x00 | (3 << S.GRID_ELEVATION_SHIFT)  # plain land at the common ground height
RIGHT = (1, 0)


def _corridor(obstacle_tool: str) -> Grid:
    """A 3-tile west-east land corridor whose middle tile (1, 0) carries a clearable obstacle
    object that `obstacle_tool` removes."""
    g = Grid.__new__(Grid)
    w, h = 3, 1
    g.width, g.height = w + 2 * S.MAP_OFFSET, h + 2 * S.MAP_OFFSET
    cells = [S.GRID_UNDEFINED | S.GRID_BLOCKED] * (g.width * g.height)
    for x in range(w):
        cells[S.MAP_OFFSET * g.width + x + S.MAP_OFFSET] = GROUND
    g.cells = tuple(cells)
    g.blocked_by_npc = {(1, 0)}
    g.clearable = {(1, 0): obstacle_tool}
    g.warp_tiles = set()
    g.tools = frozenset()
    g._behavior = lambda mid: 0  # plain floor everywhere; no water, current, ledge or waterfall
    return g


def main() -> None:
    tree = _corridor("CUT")
    assert tree.path((0, 0), (2, 0)) is None, "a tree blocks the corridor with no tool held"
    tree.tools = frozenset({"CUT"})
    assert tree.path((0, 0), (2, 0)) == [RIGHT, RIGHT], tree.path((0, 0), (2, 0))
    tree.tools = frozenset({"ROCKSMASH"})
    assert tree.path((0, 0), (2, 0)) is None, "Rock Smash does not clear a tree"

    rock = _corridor("ROCKSMASH")
    rock.tools = frozenset({"ROCKSMASH"})
    assert rock.path((0, 0), (2, 0)) == [RIGHT, RIGHT], rock.path((0, 0), (2, 0))
    rock.tools = frozenset({"CUT"})
    assert rock.path((0, 0), (2, 0)) is None, "Cut does not smash a rock"
    print("test_cut_rocksmash OK")


if __name__ == "__main__":
    main()
