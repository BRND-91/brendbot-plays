"""Dump the Sootopolis gym floor grid and the (8,16) slide tile for the room-1 ice check.

    .venv/bin/python probe_ice_room1.py <state.ss>

Prints position, the metatile id and behavior at (8,16) and (8,17), the per-tile behavior map
for rows 2..25 (i = thin ice 0x26, X = 0x47 slide, # = collision-blocked, . = walkable floor),
and the thin-ice tile list grouped by the column-8 rows that split the floor into rooms.
"""
import sys

import emu_boot as eb
from nav import Grid

GRID_ID_MASK = 0x0FFF
GRID_BLOCKED = 0x1000
THIN_ICE = 0x26
SLIDE = 0x47


def glyph(grid, x, y):
    c = grid.cell(x, y)
    if c & GRID_BLOCKED:
        return "#"
    b = grid._behavior(c & GRID_ID_MASK)
    if b == THIN_ICE:
        return "i"
    if b == SLIDE:
        return "X"
    return "."


def main():
    path = sys.argv[1]
    e = eb.Emu()
    e.load_state(open(path, "rb").read())
    grid = Grid(e)
    print(f"state {path}", flush=True)
    # position needs a Player.g; read it off a lightweight grid probe instead
    import play
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-ice.json")
    print(f"pos {p.g.position()} in_battle {p.g.in_battle()}", flush=True)
    for (x, y) in [(8, 16), (8, 17), (8, 15), (8, 3)]:
        c = grid.cell(x, y)
        mid = c & GRID_ID_MASK
        print(f"({x},{y}) cell {c:#x} metatile {mid:#x} beh {grid._behavior(mid):#x} "
              f"blocked {bool(c & GRID_BLOCKED)}", flush=True)
    print("   " + "".join(str(x % 10) for x in range(grid.width)), flush=True)
    for y in range(2, min(26, grid.height)):
        print(f"{y:2d} " + "".join(glyph(grid, x, y) for x in range(grid.width)), flush=True)
    ice = [(x, y) for y in range(grid.height) for x in range(grid.width)
           if not (grid.cell(x, y) & GRID_BLOCKED)
           and grid._behavior(grid.cell(x, y) & GRID_ID_MASK) == THIN_ICE]
    print(f"thin-ice tiles total {len(ice)}: {ice}", flush=True)


if __name__ == "__main__":
    main()
