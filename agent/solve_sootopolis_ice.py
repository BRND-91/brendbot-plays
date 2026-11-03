"""Solve the Sootopolis gym (15,0) thin-ice puzzle as a per-room ice-cover walk.

0x47 is MB_SLIDE_SOUTH, not a wall: approached from the south it pushes the party back one tile,
until every thin-ice tile (behavior 0x26) in the room below it has been cracked by exactly one step,
at which point the column walks like a stair into the next room. A second step on an already-cracked
tile drops the party to (15,1), so each room is crossed by a Hamiltonian path over its ice that steps
every tile once. The route per room, door upward: enter on the room's bottom column-8 ice tile, cover
all of the room's ice ending on the tile directly south of its slide column, then climb the slide into
the next room. The solver finds each cover as a Hamiltonian ice path from entry to exit, concatenates
the presses with the straight column-8 climbs, and replays them on a /tmp copy to validate the climb
to Juan's tile (8,3).
"""
import shutil
import sys
from collections import deque

import emu_boot as eb
import play
from nav import DIRS, Grid
from probe_sootopolis_bfs import ENTRY, GYM, STAND

GRID_ID_MASK = 0x0FFF
GRID_BLOCKED = 0x1000
THIN_ICE = 0x26
SLIDE = 0x47
U, D, L, R = (0, -1), (0, 1), (-1, 0), (1, 0)
NAME = {U: "U", D: "D", L: "L", R: "R"}
DOOR = (8, 25)
# per room, climbing from the door: the ice tile entered on, and the ice tile to end on (directly
# south of the room's slide column so the next U climbs it). Column-8 slides sit between them.
ROOMS = [((8, 19), (8, 17)), ((8, 14), (8, 12)), ((8, 9), (8, 6))]
DFS_CAP = 5_000_000


def is_ice(grid, x, y):
    c = grid.cell(x, y)
    return not (c & GRID_BLOCKED) and grid._behavior(c & GRID_ID_MASK) == THIN_ICE


def neigh(t):
    return [(t[0] + d[0], t[1] + d[1]) for d in (U, D, L, R)]


def room_ice(grid, entry):
    """The room's thin-ice tiles, 4-connected from the entry tile."""
    seen = {entry}
    q = deque([entry])
    while q:
        c = q.popleft()
        for n in neigh(c):
            if n not in seen and is_ice(grid, *n):
                seen.add(n)
                q.append(n)
    return seen


def hamiltonian(ice, entry, exit):
    """A self-avoiding walk from entry to exit stepping every ice tile once. Warnsdorff ordering,
    pruned when the unvisited ice stops being one component still containing the exit."""
    ice = set(ice)
    adj = {t: [n for n in neigh(t) if n in ice] for t in ice}
    n = len(ice)
    path = [entry]
    visited = {entry}
    calls = [0]

    def ok():
        rem = ice - visited
        if not rem:
            return path[-1] == exit
        if exit in visited:
            return False
        seen = {exit}
        dq = deque([exit])
        while dq:
            c = dq.popleft()
            for nb in adj[c]:
                if nb in rem and nb not in seen:
                    seen.add(nb)
                    dq.append(nb)
        return seen == rem and any(nb in rem for nb in adj[path[-1]])

    def dfs():
        calls[0] += 1
        if calls[0] > DFS_CAP:
            return False
        if len(visited) == n:
            return path[-1] == exit
        cur = path[-1]
        nxts = sorted((nb for nb in adj[cur] if nb not in visited),
                      key=lambda t: sum(1 for m in adj[t] if m not in visited))
        for nb in nxts:
            path.append(nb)
            visited.add(nb)
            if ok() and dfs():
                return True
            path.pop()
            visited.remove(nb)
        return False

    return path if dfs() else None


def plan(grid):
    """The full tile path from the door to the stand, cracking each room in turn."""
    positions = [DOOR]
    # door up column 8 to the first room's entry ice
    for y in range(DOOR[1] - 1, ROOMS[0][0][1] - 1, -1):
        positions.append((8, y))
    for i, (entry, exit) in enumerate(ROOMS):
        ice = room_ice(grid, entry)
        cover = hamiltonian(ice, entry, exit)
        if cover is None:
            print(f"room {i} entry {entry} exit {exit}: no cover over {len(ice)} ice tiles", flush=True)
            return None
        print(f"room {i}: {len(ice)} ice, cover {len(cover)} tiles {entry}->{exit}", flush=True)
        positions.extend(cover[1:])
        # climb the slide column to the next room's entry (or to the stand above the top room)
        top = ROOMS[i + 1][0][1] if i + 1 < len(ROOMS) else STAND[1]
        for y in range(exit[1] - 1, top - 1, -1):
            positions.append((8, y))
    return positions


def to_presses(positions):
    presses = []
    for a, b in zip(positions, positions[1:]):
        d = (b[0] - a[0], b[1] - a[1])
        if d not in NAME:
            raise ValueError(f"non-unit step {a}->{b}")
        presses.append(d)
    return presses


def step(e, g, d):
    before = tuple(g.position()[:2])
    for _ in range(24):
        e.run(2, DIRS[d])
        if g.position()[:2] != before or g.in_battle():
            break
    e.run(6, 0)


def replay(presses):
    work = "/tmp/sootopolis_solve.ss"
    shutil.copy(ENTRY, work)
    e = eb.Emu()
    e.load_state(open(work, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-solve.json")
    g = p.g
    print(f"replay start {g.position()}", flush=True)
    battles = []
    for i, d in enumerate(presses):
        step(e, g, d)
        if g.in_battle():
            battles.append((i, tuple(g.position()), g.battle_type_flags()))
            print(f"BATTLE at press {i} pos {g.position()} flags {g.battle_type_flags():#x}", flush=True)
            break
    pos = g.position()
    print(f"replay end pos {pos} map {tuple(pos[2:])} tile {tuple(pos[:2])} "
          f"in_battle {g.in_battle()} battles {battles}", flush=True)
    print("REACHED STAND" if tuple(pos[:2]) == STAND and tuple(pos[2:]) == GYM
          else "did not reach stand", flush=True)
    return tuple(pos[:2]) == STAND and tuple(pos[2:]) == GYM


def main():
    e = eb.Emu()
    e.load_state(open(ENTRY, "rb").read())
    grid = Grid(e)
    if grid._behavior is None:
        print("no behavior table on the gym map", flush=True)
        sys.exit(1)
    positions = plan(grid)
    if positions is None:
        sys.exit(2)
    presses = to_presses(positions)
    print(f"route {len(presses)} presses: {''.join(NAME[d] for d in presses)}", flush=True)
    if "--replay" in sys.argv or True:
        replay(presses)


if __name__ == "__main__":
    main()
