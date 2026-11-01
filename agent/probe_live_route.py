"""End-to-end live route: the (15,1) fall-point (7,19) up the ladder and through the gym to Juan.

    .venv/bin/python probe_live_route.py <state-at-7,19,15,1.ss>

Prefix RDDDRRR + D climbs the ladder at (11,22) back onto (15,0)'s door room; LLLUUU walks to the
room-1 entry (8,19); the rest is solve_sootopolis_ice's per-room cover with its door approach dropped.
Logs the final map, tile and any battle.
"""
import shutil
import sys

import emu_boot as eb
import play
import solve_sootopolis_ice as S
from nav import DIRS, Grid

U, D, L, R = (0, -1), (0, 1), (-1, 0), (1, 0)
NM = {U: "U", D: "D", L: "L", R: "R"}
PREFIX = [R, D, D, D, R, R, R, D, L, L, L, U, U, U]


def step(e, g, d):
    b = tuple(g.position()[:2])
    bm = tuple(g.position()[2:])
    for _ in range(24):
        e.run(2, DIRS[d])
        if g.position()[:2] != b or tuple(g.position()[2:]) != bm or g.in_battle():
            break
    e.run(6, 0)


def main():
    e0 = eb.Emu()
    e0.load_state(open(S.ENTRY, "rb").read())
    gym = S.to_presses(S.plan(Grid(e0)))
    seq = PREFIX + gym[6:]  # drop the door->(8,19) approach, enter from the ladder instead
    work = "/tmp/live_route.ss"
    shutil.copy(sys.argv[1], work)
    e = eb.Emu()
    e.load_state(open(work, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-live-route.json")
    g = p.g
    print(f"start {g.position()} presses {len(seq)} "
          f"({''.join(NM[d] for d in seq)})", flush=True)
    battles = []
    for i, d in enumerate(seq):
        step(e, g, d)
        if g.in_battle():
            battles.append((i, tuple(g.position()), g.battle_type_flags()))
            print(f"BATTLE at press {i} {g.position()} flags {g.battle_type_flags():#x}", flush=True)
            break
    pos = g.position()
    print(f"end pos {pos} map {tuple(pos[2:])} tile {tuple(pos[:2])} battles {battles}", flush=True)
    print("REACHED STAND" if tuple(pos[:2]) == S.STAND and tuple(pos[2:]) == S.GYM
          else "did not reach stand", flush=True)


if __name__ == "__main__":
    main()
