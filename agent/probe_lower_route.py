"""Drive the (15,1) lower-floor escape from (7,19) to the (11,22) ladder and up into the gym floor.

    .venv/bin/python probe_lower_route.py <state.ss>

RDDDRRR walks the fall-floor from (7,19) down through the south-slide column to the ladder at
(11,22); the ladder warps back onto (15,0). Logs position and map after every press and any battle.
"""
import shutil
import sys

import emu_boot as eb
import play
from nav import DIRS

U, D, L, R = (0, -1), (0, 1), (-1, 0), (1, 0)
NM = {U: "U", D: "D", L: "L", R: "R"}
SEQ = [R, D, D, D, R, R, R, D, U, U, D]


def step(e, g, d):
    b = tuple(g.position()[:2])
    bm = tuple(g.position()[2:])
    for _ in range(24):
        e.run(2, DIRS[d])
        if g.position()[:2] != b or tuple(g.position()[2:]) != bm or g.in_battle():
            break
    e.run(6, 0)


def main():
    src = sys.argv[1]
    work = "/tmp/lower_route.ss"
    shutil.copy(src, work)
    e = eb.Emu()
    e.load_state(open(work, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-lr.json")
    g = p.g
    print(f"start {g.position()}", flush=True)
    for d in SEQ:
        step(e, g, d)
        print(f"{NM[d]} -> {g.position()} battle {g.in_battle()}", flush=True)
        if g.in_battle():
            print(f"BATTLE flags {g.battle_type_flags():#x}", flush=True)
            break
    print(f"end {g.position()}", flush=True)


if __name__ == "__main__":
    main()
