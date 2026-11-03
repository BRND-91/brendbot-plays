"""Search the Sootopolis gym's ice-crack puzzle in the emulator and write the press route.

Juan stands at the top of (15, 0) at (8, 2), his approach tile (8, 3). Between the door at the
bottom and him are three fields of thin ice (behavior 0x26, 64 tiles over rows 6-9, 12-14 and
17-19) joined by the column-8 corridors at (8, 4/5), (8, 10/11) and (8, 15/16). A thin-ice tile
cracks on the first step and breaks on the second, warping the party down to (15, 1), so a clean
climb steps every tile it uses at most once. That makes the crack configuration part of the search
state: two paths reaching one tile with different sets of already-cracked tiles are different
nodes, and position-only dedup (Lavaridge's, where the holes are static) would wrongly merge them.
A breadth-first search over (position, wins, crack signature) nodes, each edge one direction press
on a loaded save state bounded to (15, 0) so a fall is a pruned edge, finds the no-fall press
sequence from the door to Juan's tile.

    probe_sootopolis_bfs.py          search from the entry state, write the route
    probe_sootopolis_bfs.py --replay re-run an existing route's presses and rewrite its states

Writes states/fixtures/sootopolis_route.json and merges the route into gym_routes.json under "15,0".
"""
import heapq
import json
import os
import shutil
import sys
import zlib

import emu_boot as eb
import play
import rowe_rom
import rowe_symbols as S
from nav import DIRS, GATE_SETTLE_FRAMES, Grid

BASE = os.path.dirname(os.path.abspath(__file__))
LIVE = os.path.join(BASE, "states", "fixtures", "route101.ss")  # a fixture copy, never the live save
SRC = os.path.join(BASE, "states", "fixtures", "sootopolis_src.ss")  # frozen copy made at launch
ENTRY = os.path.join(BASE, "states", "fixtures", "sootopolis_entry.ss")
OUT = os.path.join(BASE, "states", "fixtures", "sootopolis_route.json")
GYM = (15, 0)            # the puzzle floor, Juan's floor
LOWER = (15, 1)          # the floor a crack-through drops to
CITY = (0, 7)            # Sootopolis City, out the gym door
STAND = (8, 3)           # the tile in front of Juan
THIN_ICE = 0x26
MASK = getattr(S, "GRID_ID_MASK", 0x3FF)
SETTLE_FRAMES = GATE_SETTLE_FRAMES
MAX_NODES = 20000

_mc = rowe_rom.map_cells(*GYM)
_beh = rowe_rom.metatile_behavior(*GYM)
ICE = tuple(sorted((x, y) for y in range(_mc[1]) for x in range(_mc[0])
                   if _beh(_mc[2][y * _mc[0] + x] & MASK) == THIN_ICE))


def crack_sig(e) -> tuple:
    """Which of the 64 ice tiles are no longer intact thin ice, read off the live map grid the
    step-crack rewrites. The search node's identity so a revisit with a different set of cracked
    tiles is not pruned as already seen."""
    grid = Grid(e)
    return tuple(1 if grid._behavior(grid.cell(x, y) & MASK) != THIN_ICE else 0 for x, y in ICE)


def battle_out(player) -> bool:
    """Play a wild or trainer fight to its end through the executor's own battle loop. False when
    the fight was lost or a stop was raised mid-fight."""
    e, g = player.e, player.g
    streak = 0
    try:
        for _ in range(4000):
            if not g.in_battle():
                break
            player.battle_step()
            streak = player.stall_check(player.battle_signature(), streak)
    except (play.StopRequested, play.GoalExit):
        return False
    e.run(120, 0)
    for _ in range(3):
        e.run(8, eb.KEY_B)
        e.run(30, 0)
    return g.battle_outcome() == 1


def pressor(player):
    """One direction press the way Errands.follow_route replays it, bounded to (15, 0) so a step
    that cracks through to (15, 1) is a dead edge the search drops. A press onto Juan's tile stops
    short of his fight. A press a trainer's intro froze fights it out, then repeats the swallowed
    press. False when the fight was lost or the step left the gym floor."""
    e, g = player.e, player.g

    def move(d: tuple) -> None:
        x, y, *_ = g.position()
        for _ in range(24):
            e.run(2, DIRS[d])
            if g.position()[:2] != (x, y):
                break
        e.run(SETTLE_FRAMES, 0)

    def press(d: tuple) -> bool:
        before = g.position()
        move(d)
        if g.position()[:2] == STAND and g.position()[2:] == GYM:
            return True
        if g.position() != before:
            return g.position()[2:] == GYM
        for _ in range(2):
            e.run(8, eb.KEY_A)
            e.run(40, 0)
        if g.in_battle():
            if not battle_out(player):
                return False
            press.wins += 1
            move(d)
        else:
            for _ in range(2):
                e.run(8, eb.KEY_B)
                e.run(20, 0)
        return g.position()[2:] == GYM

    def wake() -> bool:
        for _ in range(16):
            if g.in_battle():
                won = battle_out(player)
                press.wins += won
                return won
            e.run(8, eb.KEY_A)
            e.run(40, 0)
        return False

    press.wins = 0
    press.wake = wake
    return press


def make_player(e):
    player = play.Player(e, play.NullStreamer(), ledger_path=ENTRY + ".caught.json")
    player.goal = {"mode": "gym", "map": list(GYM), "badges": 7, "stand": list(STAND)}
    player.graph = play.map_graph.MapGraph(
        os.path.join(BASE, "states", "map_graph.json"),
        world=play.rowe_rom.world_edges(), passthrough=play.rowe_rom.passthroughs())
    return player


def fresh(e) -> bool:
    return e and sum(crack_sig(e)) == 0


def move_down(player) -> None:
    e, g = player.e, player.g
    x, y, *_ = g.position()
    for _ in range(24):
        e.run(2, DIRS[(0, 1)])
        if g.position()[:2] != (x, y):
            break
    e.run(SETTLE_FRAMES, 0)


def capture_entry() -> None:
    """Drive a copy of the live save into the gym and freeze it at the door with every ice tile
    intact, the search's start. Inside the gym on a cracked floor or down on (15, 1) it exits to
    the city and re-enters, since entering reloads the map and resets the ice. The executor's own
    travel walks the overworld and fights the wilds on the way."""
    os.makedirs(os.path.dirname(ENTRY), exist_ok=True)
    shutil.copy(LIVE, SRC)
    e = eb.Emu()
    e.load_state(open(SRC, "rb").read())
    player = make_player(e)
    g = player.g
    for _ in range(600):                      # phase 1: out to the city, so entry comes through the door
        if g.in_battle():
            battle_out(player)
            continue
        here = g.position()[2:]
        if here == CITY:
            break
        if here == LOWER:
            player.errands.take_warp(GYM)     # (11, 22) climbs back onto (15, 0)'s bottom floor
            continue
        if here == GYM:
            r = player.errands.descend_gym(CITY)
            if r == "battle":
                battle_out(player)
            elif g.position()[2:] == GYM:
                for _ in range(6):            # stuck mid-ice: crack through to (15, 1), climb, retry
                    move_down(player)
                    if g.position()[2:] != GYM:
                        break
            continue
        try:
            player.travel_toward(GYM)
        except (play.StopRequested, play.GoalExit):
            pass
    for _ in range(400):                      # phase 2: re-enter from the city onto the door, ice reset
        if g.in_battle():
            battle_out(player)
            continue
        if g.position()[2:] == GYM:
            break
        try:
            player.travel_toward(GYM)
        except (play.StopRequested, play.GoalExit):
            pass
    if not (g.position()[2:] == GYM and fresh(e)):
        print("capture failed, not fresh in the gym at", g.position(),
              "cracked", sum(crack_sig(e)), flush=True)
        sys.exit(1)
    with open(ENTRY, "wb") as f:
        f.write(e.save_state())
    print("entry captured at", g.position(), "ice intact", len(ICE), flush=True)


def boot():
    e = eb.Emu()
    e.load_state(open(ENTRY, "rb").read())
    player = make_player(e)
    return player, e, player.g, pressor(player)


def _h(pos: tuple) -> int:
    return abs(pos[0] - STAND[0]) + abs(pos[1] - STAND[1])


def main() -> None:
    if not os.path.exists(ENTRY):
        capture_entry()
    player, e, g, press = boot()
    start = (g.position(), crack_sig(e))
    print("start", start[0], "ice tiles", len(ICE), flush=True)
    states = {start: zlib.compress(e.save_state(), 1)}
    prev = {start: None}
    depth = {start: 0}
    # win count rides beside the node, never in its key: a tile reached with one crack set is the
    # same puzzle state however many gym trainers were beaten getting there, and keying on wins
    # forks a node per win tally and never converges.
    nwins = {start: 0}
    q = [(_h(start[0]), 0, start)]
    goal = None
    expanded = 0
    while q and len(prev) < MAX_NODES:
        _, _, node = heapq.heappop(q)
        if node[0][:2] == STAND and node[0][2:] == GYM:
            goal = node
            break
        expanded += 1
        moved = False
        for d in DIRS:
            e.load_state(zlib.decompress(states[node]))
            press.wins = nwins[node]
            if not press(d):
                continue
            nxt = (g.position(), crack_sig(e))
            moved = moved or nxt != node
            if nxt == node or nxt in prev:
                continue
            prev[nxt] = (node, d)
            depth[nxt] = depth[node] + 1
            nwins[nxt] = press.wins
            states[nxt] = zlib.compress(e.save_state(), 1)
            heapq.heappush(q, (_h(nxt[0]), depth[nxt], nxt))
        if not moved:
            e.load_state(zlib.decompress(states[node]))
            press.wins = nwins[node]
            if press.wake():
                nxt = (g.position(), crack_sig(e))
                if nxt not in prev:
                    prev[nxt] = (node, None)
                    depth[nxt] = depth[node] + 1
                    nwins[nxt] = press.wins
                    states[nxt] = zlib.compress(e.save_state(), 1)
                    heapq.heappush(q, (_h(nxt[0]), depth[nxt], nxt))
        if expanded % 50 == 0:
            print(f"{expanded} expanded, {len(prev)} nodes, frontier {len(q)}, at {node[0]} "
                  f"cracked {sum(node[1])}", flush=True)
    if goal is None:
        reached = sorted({n[0] for n in prev})
        print(f"NO ROUTE after {len(prev)} nodes, {len(reached)} positions reached", flush=True)
        print("reached:", reached, flush=True)
        sys.exit(2)
    presses = []
    node = goal
    while prev[node]:
        node, d = prev[node]
        if d is not None:
            presses.append(list(d))
    presses.reverse()
    print(f"route {len(presses)} presses, {len(prev)} nodes", flush=True)
    replay(player, presses)


def replay(player, presses: list) -> None:
    """Run the presses from the entry state in one pass and write the route with the full position
    (x, y, group, num) before each press and after the last, the keys follow_route resumes on."""
    e, g = player.e, player.g
    e.load_state(open(ENTRY, "rb").read())
    press = pressor(player)
    states = [list(g.position())]
    for d in presses:
        before = list(g.position())
        press(tuple(d))
        if list(g.position()) == before and press.wake():
            press(tuple(d))
        states.append(list(g.position()))
    end = states[-1]
    print("replay ends at", end, flush=True)
    if tuple(end[:2]) != STAND or tuple(end[2:]) != GYM:
        print("replay did not reach the stand, route not written", flush=True)
        sys.exit(3)
    route = {"start": states[0], "presses": presses, "states": states}
    with open(OUT, "w") as f:
        json.dump(route, f)
    gr_path = os.path.join(BASE, "gym_routes.json")
    gr = {}
    if os.path.exists(gr_path):
        with open(gr_path) as f:
            gr = json.load(f)
    gr["15,0"] = route
    with open(gr_path, "w") as f:
        json.dump(gr, f)
    print("ROUTE WRITTEN", OUT, "and merged into gym_routes.json", flush=True)


def replay_existing() -> None:
    player, e, g, press = boot()
    with open(OUT) as f:
        presses = [tuple(p) for p in json.load(f)["presses"]]
    replay(player, presses)


if __name__ == "__main__":
    replay_existing() if "--replay" in sys.argv else main()
