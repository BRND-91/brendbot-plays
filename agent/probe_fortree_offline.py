"""Solve the Fortree gym's rotating gates on the ROM layout alone, no emulator.

The gates are the eight of rotating_gate.c's sRotatingGate_FortreePuzzleConfig, pivoted on the
corner at the top-left of config tile (x, y). An arm is a bar on a tile edge: the north and south
arms run along the vertical line x = gx, the west and east arms along the horizontal line y = gy,
one or two tiles out from the pivot. A step across an arm's edge turns the gate the way the
rotation-info tables say, when every arm's sweep tile is passable (RotatingGate_CanRotate),
and otherwise the step is refused. Object events are walls, since a trainer stands still.

    probe_fortree_offline.py  -> prints the press route door -> stand, and writes it as
    states/probe/fortree_route.json {"start": [x, y], "presses": [[dx, dy], ...]} for
    probe_fortree_bfs.py --replay to run in the emulator and fill in the states.
"""
import json
import sys
from collections import deque

import rowe_rom as R
import rowe_symbols as S

GYM = (12, 1)
START = (15, 24)
STAND = (15, 3)
OUT = "states/probe/fortree_route.json"
# (x, y, shape, orientation) in config order; the SaveBlock1 byte i is gate i's orientation
L1, L2, L3, L4, T1, T2, T3, T4 = range(8)
CONFIG = [(6, 7, T2, 1), (9, 15, T2, 2), (3, 19, T2, 1), (2, 6, T1, 1),
          (9, 12, T1, 0), (6, 23, T1, 0), (12, 22, T1, 0), (6, 3, L4, 2)]
# sRotatingGate_ArmLayout, (short, long) per layout arm north, east, south, west
LAYOUT = [(1, 0, 1, 0, 0, 0, 0, 0), (1, 1, 1, 0, 0, 0, 0, 0), (1, 0, 1, 1, 0, 0, 0, 0), (1, 1, 1, 1, 0, 0, 0, 0),
          (1, 0, 1, 0, 1, 0, 0, 0), (1, 1, 1, 0, 1, 0, 0, 0), (1, 0, 1, 1, 1, 0, 0, 0), (1, 0, 1, 0, 1, 1, 0, 0)]
NORTH, EAST, SOUTH, WEST = range(4)
CW, ACW = 1, -1
# sRotatingGate_ArmPositions*Rotation, the tiles an arm sweeps, indexed 2 * world arm + long
SWEEP = {CW: [(0, -1), (1, -2), (0, 0), (1, 0), (-1, 0), (-1, 1), (-1, -1), (-2, -1)],
         ACW: [(-1, -1), (-1, -2), (0, -1), (1, -1), (0, 0), (0, 1), (-1, 0), (-2, 0)]}
# sRotatingGate_RotationInfo*: (direction, centerX, centerY) of the tile stepped into ->
# (rotation, world arm, long)
INFO = {}
for cx, (arm, k, rot) in enumerate([(WEST, 1, CW), (WEST, 0, CW), (EAST, 0, ACW), (EAST, 1, ACW)]):
    INFO[((0, -1), cx, 1)] = (rot, arm, k)
for cx, (arm, k, rot) in enumerate([(WEST, 1, ACW), (WEST, 0, ACW), (EAST, 0, CW), (EAST, 1, CW)]):
    INFO[((0, 1), cx, 2)] = (rot, arm, k)
for cy, (arm, k, rot) in enumerate([(NORTH, 1, ACW), (NORTH, 0, ACW), (SOUTH, 0, CW), (SOUTH, 1, CW)]):
    INFO[((-1, 0), 1, cy)] = (rot, arm, k)
for cy, (arm, k, rot) in enumerate([(NORTH, 1, CW), (NORTH, 0, CW), (SOUTH, 0, ACW), (SOUTH, 1, ACW)]):
    INFO[((1, 0), 2, cy)] = (rot, arm, k)
DIRS = [(0, -1), (0, 1), (-1, 0), (1, 0)]


# where a trainer stands once he has walked at the player: Edwardo at (9, 8) sees two tiles down
# and steps to (9, 9) when the player reaches (9, 10), the only tile north out of (9, 11), so the
# way on is (8, 10) then (8, 9); the replay sat on (9, 10) pressing up into him
APPROACH_TILES = {(9, 9)}


def impassable_set() -> tuple:
    w, h, cells = R.map_cells(*GYM)
    walls = {(x, y) for y in range(h) for x in range(w) if cells[y * w + x] & S.GRID_BLOCKED}
    walls |= {(x, y) for x, y, _, _ in R.map_objects(*GYM)} | APPROACH_TILES
    return walls, w, h


def has_arm(shape: int, orientation: int, arm: int, k: int) -> bool:
    return bool(LAYOUT[shape][2 * ((arm - orientation) % 4) + k])


def can_rotate(gate: tuple, orientation: int, rot: int, walls: set) -> bool:
    gx, gy, shape, _ = gate
    for i in range(4):
        for j in range(2):
            if LAYOUT[shape][2 * i + j]:
                dx, dy = SWEEP[rot][2 * ((orientation + i) % 4) + j]
                if (gx + dx, gy + dy) in walls:
                    return False
    return True


def step(tile: tuple, orients: tuple, d: tuple, walls: set, w: int, h: int) -> tuple:
    """(tile, orients) after pressing d, the same pair when the game refuses the step."""
    nx, ny = tile[0] + d[0], tile[1] + d[1]
    if not (0 <= nx < w and 0 <= ny < h) or (nx, ny) in walls:
        return tile, orients
    for i, gate in enumerate(CONFIG):
        gx, gy = gate[0], gate[1]
        if gx - 2 <= nx <= gx + 1 and gy - 2 <= ny <= gy + 1:
            info = INFO.get((d, nx - gx + 2, ny - gy + 2))
            if info is None:
                continue
            rot, arm, k = info
            if has_arm(gate[2], orients[i], arm, k):
                if can_rotate(gate, orients[i], rot, walls):
                    turned = list(orients)
                    turned[i] = (orients[i] + rot) % 4
                    return (nx, ny), tuple(turned)
                return tile, orients
    return (nx, ny), orients


def solve() -> list | None:
    walls, w, h = impassable_set()
    start = (START, tuple(g[3] for g in CONFIG))
    prev = {start: None}
    q = deque([start])
    while q:
        node = q.popleft()
        if node[0] == STAND:
            presses = []
            while prev[node]:
                node, d = prev[node]
                presses.append(list(d))
            return presses[::-1]
        for d in DIRS:
            nxt = step(node[0], node[1], d, walls, w, h)
            if nxt != node and nxt not in prev:
                prev[nxt] = (node, d)
                q.append(nxt)
    print(f"NO ROUTE over {len(prev)} states, tiles {len({n[0] for n in prev})}")
    return None


if __name__ == "__main__":
    route = solve()
    if route is None:
        sys.exit(1)
    print(f"route {len(route)} presses: {route}")
    with open(OUT, "w") as f:
        json.dump({"start": list(START), "presses": route}, f)
    print("written", OUT)
