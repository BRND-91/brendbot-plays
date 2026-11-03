"""Reproduce the Sootopolis lower-floor double-trainer wedge from before the fight.

Boot a Player from a /tmp copy of states/fixtures/sootopolis_src.ss (never the fixture itself, never
the live save), walk the lower floor (15, 1) toward the trainers' line of sight at (9, 8), save the
in-battle start to /tmp/wedge_start.ss, then drive the fight with battle_step. Every press logs key,
chooser, controller_func(0..3) and gChosenActionByBattler[0:4], and the press that first drives
controller_func(1) to 0x0 or chosen[1] to 13 is marked. tap hold/gap come from argv so the same
battle start replays at 2/3 and 8/12.

    .venv/bin/python probe_wedge_repro.py <hold> <gap> [steps]
"""
import os
import shutil
import sys
from collections import deque

import emu_boot as eb
import play
import rowe_symbols as S
from nav import DIRS, Grid

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "states", "fixtures", "sootopolis_src.ss")
WORK = "/tmp/wedge_src.ss"
START = "/tmp/wedge_start.ss"
TARGET = (9, 8)
KEYS = {1: "A", 2: "B", 64: "U", 128: "D", 32: "L", 16: "R", 8: "ST", 0: "-"}


def mkplayer(path):
    e = eb.Emu()
    e.load_state(open(path, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-wedge.json")
    return p, e, p.g


def _step(e, g, d):
    """One overworld press toward d, held until the tile changes or a battle starts."""
    before = tuple(g.position())
    for _ in range(24):
        e.run(2, DIRS[d])
        if g.position()[:2] != before[:2] or g.in_battle():
            break
    e.run(6, 0)
    return before


BLK = 0x1000


def _walkable(grid, x, y):
    return 0 <= x < grid.width and 0 <= y < grid.height and not (grid.cell(x, y) & BLK)


def _plan(grid, start, goal):
    """Shortest walk over the floor collision grid from start to goal, as a list of DIRS keys."""
    q = deque([start])
    prev = {start: None}
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        for d in DIRS:
            nxt = (cur[0] + d[0], cur[1] + d[1])
            if _walkable(grid, *nxt) and nxt not in prev:
                prev[nxt] = (cur, d)
                q.append(nxt)
    if goal not in prev:
        return None
    path = []
    node = goal
    while prev[node] is not None:
        node, d = prev[node]
        path.append(d)
    path.reverse()
    return path


def reach_battle():
    """Walk the planned floor path toward (9,8) until a trainer's sight starts the fight, save the
    battle start, return whether it started. The lower floor is plain floor with no ice slide."""
    shutil.copy(SRC, WORK)
    p, e, g = mkplayer(WORK)
    grid = Grid(e)
    start = tuple(g.position()[:2])
    path = _plan(grid, start, TARGET)
    if path is None:
        print(f"no floor path from {start} to {TARGET}", flush=True)
        return False
    print(f"planned {len(path)} steps from {start} to {TARGET}", flush=True)
    trail = [tuple(g.position())]
    for d in path:
        if g.in_battle():
            break
        _step(e, g, d)
        if tuple(g.position()) != trail[-1]:
            trail.append(tuple(g.position()))
    print(f"walk trail: {trail}", flush=True)
    print(f"reached in_battle {g.in_battle()} at {g.position()} "
          f"flags {g.battle_type_flags():#x}", flush=True)
    if g.in_battle():
        with open(START, "wb") as f:
            f.write(e.save_state())
        print(f"saved battle start -> {START}", flush=True)
    return g.in_battle()


def drive(hold, gap, steps):
    p, e, g = mkplayer(START)
    print(f"=== drive hold {hold} gap {gap}: start in_battle {g.in_battle()} "
          f"flags {g.battle_type_flags():#x} pos {g.position()} ===", flush=True)
    real_tap = p.tap
    state = {"prev_f1": None, "prev_c1": None, "n": 0}

    def tap(keys, *a, **k):
        funcs = [g.controller_func(i) for i in range(4)]
        chosen = list(e.read(S.addr("gChosenActionByBattler"), 4))
        mark = ""
        if state["prev_f1"] not in (None, 0) and funcs[1] == 0:
            mark = "  <== controller_func(1) -> 0x0"
        if state["prev_c1"] != 13 and chosen[1] == 13:
            mark += "  <== chosen[1] -> 13"
        fstr = " ".join(f"{v:#x}" for v in funcs)
        print(f"press {state['n']:3d} {KEYS.get(keys, keys):2} chooser {g.chooser()} "
              f"funcs [{fstr}] chosen {chosen}{mark}", flush=True)
        state["prev_f1"], state["prev_c1"] = funcs[1], chosen[1]
        state["n"] += 1
        k.setdefault("hold", hold)
        k.setdefault("gap", gap)
        real_tap(keys, *a, **k)

    p.tap = tap
    for i in range(steps):
        if not g.in_battle():
            print(f"battle ended after {i} battle_steps, pos {g.position()}", flush=True)
            break
        funcs = [g.controller_func(j) for j in range(4)]
        chosen = list(e.read(S.addr("gChosenActionByBattler"), 4))
        print(f"step {i}: pos {g.position()} chooser {g.chooser()} "
              f"funcs {[hex(x) for x in funcs]} chosen {chosen}", flush=True)
        try:
            p.battle_step()
        except play.StopRequested:
            print(f"battle_step raised StopRequested (WEDGE/STALL) at step {i}", flush=True)
            break
    print(f"=== end hold {hold} gap {gap}: in_battle {g.in_battle()} pos {g.position()} "
          f"after {state['n']} presses ===", flush=True)


def main():
    hold = int(sys.argv[1])
    gap = int(sys.argv[2])
    steps = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    if not os.path.exists(START):
        if not reach_battle():
            print("WALK FAILED: no battle reached from src", flush=True)
            sys.exit(2)
    drive(hold, gap, steps)


if __name__ == "__main__":
    main()
