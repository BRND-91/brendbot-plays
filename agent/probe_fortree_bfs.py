"""Search the Fortree gym's rotating-gate puzzle in the emulator and write the press route.

The gates are sprites outside the object-event table and the metatile collision, so the grid
cannot see their arms; the game keeps each gate's orientation as one byte of the temp-var
block in SaveBlock1 (pokeemerald rotating_gate.c, VAR_TEMP_0 as a byte array), reset to the
puzzle config on every map load. A breadth-first search over (tile, orientations) nodes, each
edge one direction press on a loaded save state, finds the press sequence from the door mat to
the leader's stand without modelling arm shapes or rotation rules.

    probe_fortree_bfs.py  -> states/fixtures/fortree_route.json {"start": [x, y], "presses": [[dx, dy], ...]}
"""
import heapq
import json
import sys
import zlib

import emu_boot as eb
import play
import rowe_symbols as S
from nav import DIRS, GATE_SETTLE_FRAMES

# --entry PATH swaps the start state, e.g. one saved on the door mat w/ the trainers beaten
ENTRY = sys.argv[sys.argv.index("--entry") + 1] if "--entry" in sys.argv else "states/fixtures/fortree_entry.ss"
OUT = "states/fixtures/fortree_route.json"
STAND = (15, 3)
GYM = (12, 1)
GATE_VARS = 0x1BCA  # SaveBlock1 offset of the 8 orientation bytes, found by their config values
GATE_COUNT = 8
SETTLE_FRAMES = GATE_SETTLE_FRAMES
MAX_NODES = 6000


def pressor(player):
    """One direction press the way Errands.follow_route replays it. A trainer whose sight the
    step entered freezes the player behind an intro that no later press gets past; two A taps
    catch a fight already at its text box and the executor's own battle loop plays it out, then
    the press the intro swallowed runs again. At a free tile the same taps face-talk an empty
    tile and B closes whatever they opened. A fresh freeze needs more taps than two (nine from
    the first frozen frame at (9,10)), so a node no press moves goes through `press.wake`.
    False when the fight was lost or the press left the gym (the door mat warps out, and the
    search must not wander the city)."""
    e, g = player.e, player.g

    def move(d: tuple) -> None:
        x, y, *_ = g.position()
        for _ in range(24):
            e.run(2, DIRS[d])
            if g.position()[:2] != (x, y):
                break
        e.run(SETTLE_FRAMES, 0)

    def fight() -> bool:
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
        for _ in range(3):  # the loser's closing line
            e.run(8, eb.KEY_B)
            e.run(30, 0)
        won = g.battle_outcome() == 1
        # a beaten trainer never freezes the player again, so the fight count is part of the
        # search node; the caller sets it from the node before the press and reads it after
        press.wins += won
        return won

    def press(d: tuple) -> bool:
        before = g.position()[:2]
        move(d)
        if g.position()[:2] == STAND:
            return True  # an A here would open the leader's fight
        if g.position()[:2] != before:
            # the step landed, so nothing holds the player; an A here talks to whatever the
            # player now faces, and the gym guide at (15, 21) held the replay at (15, 22)
            return g.position()[2:] == GYM
        for _ in range(2):
            e.run(8, eb.KEY_A)
            e.run(40, 0)
        if g.in_battle():
            if not fight():
                return False
            move(d)
        else:
            for _ in range(2):
                e.run(8, eb.KEY_B)
                e.run(20, 0)
        return g.position()[2:] == GYM

    def wake() -> bool:
        """Tap A through a trainer's intro until the fight opens, then play it out. False when
        no fight opened within 16 taps or it was lost."""
        for _ in range(16):
            if g.in_battle():
                return fight()
            e.run(8, eb.KEY_A)
            e.run(40, 0)
        return False
    press.wins = 0
    press.wake = wake
    return press


def boot():
    """(player, emulator, game state, gates reader, press) on the entry state."""
    e = eb.Emu()
    e.load_state(open(ENTRY, "rb").read())
    player = play.Player(e, play.NullStreamer(), ledger_path=ENTRY + ".caught.json")
    player.goal = {"mode": "gym", "map": list(GYM), "badges": 4}
    g = player.g
    sb1 = e.u32(S.addr("gSaveBlock1Ptr"))

    def gates() -> tuple:
        return tuple(e.read(sb1 + GATE_VARS, GATE_COUNT))

    return player, e, g, gates, pressor(player)


def main() -> None:
    player, e, g, gates, press = boot()
    start = (g.position()[:2], gates(), 0)
    print("start", start, flush=True)
    states = {start: zlib.compress(e.save_state(), 1)}
    prev = {start: None}
    depth = {start: 0}
    # nearest-to-stand first: the puzzle's corridors funnel toward the leader, so the nodes
    # closest by Manhattan distance expand first and the search stays small
    q = [(abs(start[0][0] - STAND[0]) + abs(start[0][1] - STAND[1]), 0, start)]
    goal = None
    expanded = 0
    fights = set()  # (tile, press) edges a trainer's sight turned into a fight, dropped
    while q and len(prev) < MAX_NODES:
        _, _, node = heapq.heappop(q)
        if node[0] == STAND:
            goal = node
            break
        expanded += 1
        moved = False
        for d in DIRS:
            e.load_state(zlib.decompress(states[node]))
            press.wins = node[2]
            if not press(d):
                if g.in_battle():
                    fights.add((node[0], d))
                continue
            nxt = (g.position()[:2], gates(), press.wins)
            moved = moved or nxt != node
            if nxt == node or nxt in prev:
                continue
            prev[nxt] = (node, d)
            depth[nxt] = depth[node] + 1
            states[nxt] = zlib.compress(e.save_state(), 1)
            heapq.heappush(q, (abs(nxt[0][0] - STAND[0]) + abs(nxt[0][1] - STAND[1]), depth[nxt], nxt))
        if not moved:
            # no press changed (tile, gates): a trainer's sight holds the player mid-intro and
            # his fight is the only edge out; the route carries it as no press, since the
            # live walk fights it where the next press freezes
            e.load_state(zlib.decompress(states[node]))
            press.wins = node[2]
            if not press.wake():
                fights.add((node[0], None))
                continue
            nxt = (g.position()[:2], gates(), press.wins)
            if nxt in prev:
                continue
            prev[nxt] = (node, None)
            depth[nxt] = depth[node] + 1
            states[nxt] = zlib.compress(e.save_state(), 1)
            heapq.heappush(q, (abs(nxt[0][0] - STAND[0]) + abs(nxt[0][1] - STAND[1]), depth[nxt], nxt))
        if expanded % 100 == 0:
            print(f"{expanded}/{MAX_NODES} expanded, {len(prev)} nodes, frontier {len(q)}, at {node[0]}", flush=True)
    if goal is None:
        tiles = sorted({n[0] for n in prev})
        combos = len({n[1] for n in prev})
        print(f"NO ROUTE after {len(prev)} nodes: {len(tiles)} tiles, {combos} gate states, "
              f"min y {min(t[1] for t in tiles)}", flush=True)
        print("tiles reached:", tiles, flush=True)
        print("fight edges:", sorted(fights, key=lambda f: (f[0], f[1] or ())), flush=True)
        return
    presses = []
    node = goal
    while prev[node]:
        node, d = prev[node]
        if d is not None:
            presses.append(list(d))
    presses.reverse()
    print(f"route {len(presses)} presses, nodes {len(prev)}", flush=True)
    replay(e, g, gates, press, presses)


def replay(e, g, gates, press, presses: list) -> None:
    """Run the presses from the entry state in one go and write the route w/ the (tile, gates)
    state before each press and after the last, the keys Errands.follow_route resumes on."""
    e.load_state(open(ENTRY, "rb").read())
    states = [[list(g.position()[:2]), list(gates())]]
    for d in presses:
        press(tuple(d))
        if [list(g.position()[:2]), list(gates())] == states[-1] and press.wake():
            press(tuple(d))  # the press a trainer's intro swallowed
        states.append([list(g.position()[:2]), list(gates())])
    end = tuple(states[-1][0])
    print(f"replay ends at {end}", flush=True)
    if end == STAND:
        with open(OUT, "w") as f:
            json.dump({"start": list(states[0][0]), "gate_vars": GATE_VARS, "gate_count": GATE_COUNT,
                       "presses": presses, "states": states}, f)
        print("ROUTE WRITTEN", OUT, flush=True)


def replay_existing() -> None:
    """--replay: re-run the presses in an existing route file and fill in its states."""
    player, e, g, gates, press = boot()
    with open(OUT) as f:
        presses = json.load(f)["presses"]
    replay(e, g, gates, press, presses)


if __name__ == "__main__":
    replay_existing() if "--replay" in sys.argv else main()
