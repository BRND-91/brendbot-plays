"""Step every room-1 ice tile once from the door and read the (8,16) slide tile before and after.

    .venv/bin/python probe_ice_cover.py <state.ss>

Room 1 is the bottom field nearest the door (8,25): ice at (8,17),(9,17),(7,18),(8,18),(9,18),
(7,19),(8,19), capped by the 0x47 slide tiles (8,15)/(8,16). The press list climbs column 8 to
(8,19) then covers all seven ice tiles exactly once, ending at (8,17) directly below (8,16). If a
room's slide becomes stairs once its ice is fully cracked, (8,16)'s behavior changes here.
"""
import shutil
import sys

import emu_boot as eb
import play
from nav import DIRS, Grid

GRID_ID_MASK = 0x0FFF
U, D, L, R = (0, -1), (0, 1), (-1, 0), (1, 0)
NAME = {U: "U", D: "D", L: "L", R: "R"}
SEQ = [U, U, U, U, U, U, L, U, R, R, U, L]


def tile(grid, x, y):
    c = grid.cell(x, y)
    mid = c & GRID_ID_MASK
    return f"({x},{y}) metatile {mid:#x} beh {grid._behavior(mid):#x} blocked {bool(c & 0x1000)}"


def step(e, g, d):
    before = tuple(g.position()[:2])
    for _ in range(24):
        e.run(2, DIRS[d])
        if g.position()[:2] != before or g.in_battle():
            break
    e.run(6, 0)


def main():
    src = sys.argv[1]
    work = "/tmp/ice_cover.ss"
    shutil.copy(src, work)
    e = eb.Emu()
    e.load_state(open(work, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-ice.json")
    g = p.g
    grid = Grid(e)
    print(f"start {g.position()}", flush=True)
    print("BEFORE " + tile(grid, 8, 16), flush=True)
    print("BEFORE " + tile(grid, 8, 15), flush=True)
    for d in SEQ:
        step(e, g, d)
        grid = Grid(e)
        print(f"{NAME[d]} -> {g.position()}  (8,16) beh "
              f"{grid._behavior(grid.cell(8, 16) & GRID_ID_MASK):#x}", flush=True)
        if g.position()[2:] != (15, 0):
            print(f"FELL off (15,0) to {g.position()[2:]}, stopping", flush=True)
            break
    grid = Grid(e)
    print("AFTER  " + tile(grid, 8, 16), flush=True)
    print("AFTER  " + tile(grid, 8, 15), flush=True)
    print("AFTER  " + tile(grid, 8, 17), flush=True)
    room1 = [(8, 17), (9, 17), (7, 18), (8, 18), (9, 18), (7, 19), (8, 19)]
    print("room-1 ice behaviors: " + " ".join(
        f"{t}={grid._behavior(grid.cell(*t) & GRID_ID_MASK):#x}" for t in room1), flush=True)
    print(f"end {g.position()} in_battle {g.in_battle()}", flush=True)
    print("--- slide test: press U toward (8,16) four times ---", flush=True)
    for _ in range(4):
        step(e, g, U)
        print(f"U -> {g.position()}", flush=True)
        if g.position()[2:] != (15, 0):
            print(f"FELL to {g.position()[2:]}", flush=True)
            break


if __name__ == "__main__":
    main()
