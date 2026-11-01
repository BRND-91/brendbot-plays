"""Why the executor logged the Lilycove ball at (57, 12) as unreachable and walked past it.

Crosses the live snapshot east off Route 121 into Lilycove, saves that state for a fix test,
and prints what the pickup path sees: the live grid around the ball, the ball list, the sides
collectable_balls() accepts, the stand tiles collect_item() would walk to, and per side the
passable and path verdicts.

    probe_lilycove_ball.py [SNAPSHOT]   -> states/fixtures/lilycove.ss
"""
import os
import shutil
import sys

import emu_boot as eb
import play
import rowe_map
import rowe_symbols as S
from nav import Grid
from routines import Errands

SNAPSHOT = sys.argv[1] if len(sys.argv) > 1 else "states/fixtures/route101.ss"
SRC = "states/fixtures/lily_src.ss"
OUT = "states/fixtures/lilycove.ss"
LILYCOVE = (0, 5)
BALL = (57, 12)


def main() -> None:
    shutil.copy(SNAPSHOT, SRC)
    with open(os.path.join(os.path.dirname(SRC), "goal.json"), "w") as f:
        f.write('{"mode": "travel", "to": [0, 5]}')
    e = eb.Emu()
    with open(SRC, "rb") as f:
        e.load_state(f.read())
    player = play.Player(e, play.NullStreamer(), ledger_path=SRC + ".caught.json")
    player.state_path = SRC
    player.loop(0)
    g = player.g
    errands = Errands(e, e.run)
    for _ in range(30):
        if g.position()[2:] == LILYCOVE:
            break
        while g.in_battle():
            player.battle_step()
        # the live snapshot is rewritten every few minutes; Route 121 is west of Lilycove and
        # Route 124 east, so the crossing direction follows the map the snapshot is on
        direction = rowe_map.DIR_EAST if g.position()[2:] == (0, 36) else rowe_map.DIR_WEST
        status = errands.cross_edge(direction, surf="SURF" in player.field_moves())
        print(f"cross {direction}: {status} at {g.position()}", flush=True)
    if g.position()[2:] != LILYCOVE:
        print(f"NO ARRIVAL at {g.position()}", flush=True)
        return
    with open(OUT, "wb") as f:
        f.write(e.save_state())
    x, y, *_ = g.position()
    grid = Grid(e)
    beh = grid._behavior

    def cs(cx: int, cy: int) -> str:
        c = grid.cell(cx, cy)
        if c & S.GRID_ID_MASK == S.GRID_UNDEFINED:
            return " ?? "
        mark = "@" if (cx, cy) == (x, y) else "N" if (cx, cy) in grid.blocked_by_npc else "#" if c & S.GRID_BLOCKED else "."
        return f"{mark}{c >> S.GRID_ELEVATION_SHIFT:x}{beh(c & S.GRID_ID_MASK):02x}"

    print(f"player {(x, y)} elev {grid.cell(x, y) >> S.GRID_ELEVATION_SHIFT}", flush=True)
    for cy in range(BALL[1] - 5, BALL[1] + 7):
        print(f"{cy:3} " + " ".join(cs(cx, cy) for cx in range(BALL[0] - 7, BALL[0] + 8)), flush=True)
    print("item balls:", rowe_map.item_balls(e), flush=True)
    surf = "SURF" in player.field_moves()
    print("collectable:", player.collectable_balls(), "surf", surf, flush=True)
    print("stand tiles:", Errands.stand_tiles(grid, BALL, (x, y), surf), flush=True)
    elev = grid.cell(x, y) >> S.GRID_ELEVATION_SHIFT
    reach = grid.reachable((x, y), surf)
    for d in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        side = (BALL[0] + d[0], BALL[1] + d[1])
        print(f"side {side}: cell {cs(*side)} passable {grid.passable(*side, elev, (x, y), surf)} "
              f"in reach {side in reach} path {grid.path((x, y), side, surf) is not None}", flush=True)


if __name__ == "__main__":
    main()
