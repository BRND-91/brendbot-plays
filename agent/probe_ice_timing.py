"""One UP tap and its per-frame map+tile, on floor at the door and again onto the thin ice.

Answers one question before the ice solver's step model is touched: does a single press move
exactly one tile, or does it slide across several once the step lands on ice. Walks up the floor
to the tile just below the first ice field (one full-step hold per tile), then holds UP for the tap
window, releases, and runs one frame at a time reading the full position after each.

    .venv/bin/python probe_ice_timing.py [hold_frames]
"""
import os
import sys

import emu_boot as eb
import play
from nav import DIRS, Grid

BASE = os.path.dirname(os.path.abspath(__file__))
ENTRY = os.path.join(BASE, "states", "fixtures", "sootopolis_entry.ss")
UP = DIRS[(0, -1)]
THIN_ICE = 0x26
GRID_ID_MASK = 0x0FFF


def main() -> None:
    hold = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    if not os.path.exists(ENTRY):
        print(f"no entry state at {ENTRY}", flush=True)
        sys.exit(1)
    e = eb.Emu()
    e.load_state(open(ENTRY, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-ice-timing.json")
    g = p.g
    grid = Grid(e)
    if grid._behavior is None:
        print("no behavior table on the gym map, cannot find the ice edge", flush=True)
        sys.exit(1)

    def is_ice(x, y):
        return grid._behavior(grid.cell(x, y) & GRID_ID_MASK) == THIN_ICE

    x, y, grp, num = g.position()
    print(f"entry ({x}, {y}) map ({grp}, {num})", flush=True)
    for _ in range(12):                       # walk up the floor one full-step hold per tile
        x, y, grp, num = g.position()
        if is_ice(x, y - 1):
            print(f"at ({x}, {y}): tile above ({x}, {y - 1}) is thin ice, stopping the approach", flush=True)
            break
        e.run(16, UP)
        e.run(4, 0)
        nx, ny, _, _ = g.position()
        print(f"floor tap UP: ({x}, {y}) -> ({nx}, {ny})", flush=True)
        if (nx, ny) == (x, y):
            print("floor approach stalled", flush=True)
            break

    x, y, grp, num = g.position()
    print(f"--- single UP tap onto the ice from ({x}, {y}), hold {hold} frames then release ---", flush=True)
    last = (x, y, grp, num)
    for f in range(60):
        e.run(1, UP if f < hold else 0)
        x, y, grp, num = g.position()
        cur = (x, y, grp, num)
        mark = "  <- moved" if cur != last else ""
        print(f"frame {f:2d} key {'UP' if f < hold else '..'}  tile ({x}, {y}) map ({grp}, {num}){mark}", flush=True)
        last = cur


if __name__ == "__main__":
    main()
