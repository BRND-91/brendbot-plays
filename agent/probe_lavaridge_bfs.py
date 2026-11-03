"""Search the Lavaridge gym's two-floor hole maze in the emulator and write the press route.

Flannery is on 1F at (13, 9), her approach tile (13, 10), but the floor between the door and her
is a field of fall-holes down to B1F. Reaching her means dropping through the right holes and
climbing back up the paired ones. The holes are one-way warps `Grid.path` routes around, so the
greedy `gym_sweep` cannot find the order. A breadth-first search over (x, y, group, num) nodes,
each edge one direction press on a loaded save state, finds the press sequence from the entrance to
her tile; the emulator resolves each drop on the step, so a node carries no model of the maze.

    probe_lavaridge_bfs.py          search from the entry state, write the route
    probe_lavaridge_bfs.py --replay re-run an existing route's presses and rewrite its states

Writes states/fixtures/lavaridge_route.json and merges the route into gym_routes.json under "4,1".
"""
import heapq
import json
import os
import sys
import zlib

import emu_boot as eb
import play
from nav import DIRS, GATE_SETTLE_FRAMES

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "states", "fixtures", "lavaridge_src.ss")  # frozen copy of the live save, made at launch
ENTRY = os.path.join(BASE, "states", "fixtures", "lavaridge_entry.ss")
OUT = os.path.join(BASE, "states", "fixtures", "lavaridge_route.json")
GYM = (4, 1)              # Lavaridge gym 1F (group, num), the leader's floor
STAND = (13, 10)         # the tile in front of Flannery on 1F
SETTLE_FRAMES = GATE_SETTLE_FRAMES
MAX_NODES = 5000


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
    for _ in range(3):  # the loser's closing line
        e.run(8, eb.KEY_B)
        e.run(30, 0)
    return g.battle_outcome() == 1


def pressor(player, gym_maps):
    """One direction press the way Errands.follow_route replays it, bounded to the gym's own maps
    so the search never steps out the entrance into the town. A press onto Flannery's tile stops
    short of her fight. A press a trainer's intro froze fights it out, then repeats the swallowed
    press. False when the fight was lost or the step left the gym."""
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
            return True  # on the leader's tile; an A here would open her fight
        if g.position() != before:
            return g.position()[2:] in gym_maps  # a step or a hole-drop that stayed inside the gym
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
        return g.position()[2:] in gym_maps

    def wake() -> bool:
        """Tap A through a trainer's intro until the fight opens, then play it out."""
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
    """A Player wired the way play.run sets one up before the loop: goal set, and the map graph
    loaded from states/map_graph.json so travel_toward can route (play.run builds it at launch,
    not in __init__, so a bare Player leaves self.graph None)."""
    player = play.Player(e, play.NullStreamer(), ledger_path=ENTRY + ".caught.json")
    player.goal = {"mode": "gym", "map": list(GYM), "badges": 6, "stand": list(STAND)}
    player.graph = play.map_graph.MapGraph(
        os.path.join(BASE, "states", "map_graph.json"),
        world=play.rowe_rom.world_edges(), passthrough=play.rowe_rom.passthroughs())
    return player


def capture_entry(gym_maps) -> None:
    """Drive a copy of the live overworld save into the gym and freeze the state at the entrance,
    the search's start. The executor's own travel does the walking and fights the wilds on the way."""
    e = eb.Emu()
    e.load_state(open(SRC, "rb").read())
    player = make_player(e)
    g = player.g
    for _ in range(600):
        if g.in_battle():
            battle_out(player)
            continue
        if g.position()[2:] in gym_maps:
            break
        try:
            player.travel_toward(GYM)
        except (play.StopRequested, play.GoalExit):
            pass
    if g.position()[2:] not in gym_maps:
        print("capture failed, not in the gym at", g.position(), flush=True)
        sys.exit(1)
    os.makedirs(os.path.dirname(ENTRY), exist_ok=True)
    with open(ENTRY, "wb") as f:
        f.write(e.save_state())
    print("entry captured at", g.position(), flush=True)


def boot(gym_maps):
    e = eb.Emu()
    e.load_state(open(ENTRY, "rb").read())
    player = make_player(e)
    return player, e, player.g, pressor(player, gym_maps)


def _h(pos: tuple) -> int:
    # nearest-to-stand first, with a floor penalty so a node already on the leader's floor beats an
    # equidistant one still on B1F
    return abs(pos[0] - STAND[0]) + abs(pos[1] - STAND[1]) + (0 if pos[2:] == GYM else 20)


def main() -> None:
    gym_maps = play.gym_map_set(GYM)
    if not os.path.exists(ENTRY):
        capture_entry(gym_maps)
    player, e, g, press = boot(gym_maps)
    start = (g.position(), 0)  # ((x, y, group, num), wins)
    print("start", start, "gym_maps", sorted(gym_maps), flush=True)
    states = {start: zlib.compress(e.save_state(), 1)}
    prev = {start: None}
    depth = {start: 0}
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
            press.wins = node[1]
            if not press(d):
                continue
            nxt = (g.position(), press.wins)
            moved = moved or nxt != node
            if nxt == node or nxt in prev:
                continue
            prev[nxt] = (node, d)
            depth[nxt] = depth[node] + 1
            states[nxt] = zlib.compress(e.save_state(), 1)
            heapq.heappush(q, (_h(nxt[0]), depth[nxt], nxt))
        if not moved:
            # a trainer's sight holds the player mid-intro; his fight is the only edge out, and the
            # route carries it as no press, fought live where the next press freezes
            e.load_state(zlib.decompress(states[node]))
            press.wins = node[1]
            if press.wake():
                nxt = (g.position(), press.wins)
                if nxt not in prev:
                    prev[nxt] = (node, None)
                    depth[nxt] = depth[node] + 1
                    states[nxt] = zlib.compress(e.save_state(), 1)
                    heapq.heappush(q, (_h(nxt[0]), depth[nxt], nxt))
        if expanded % 50 == 0:
            print(f"{expanded} expanded, {len(prev)} nodes, frontier {len(q)}, at {node[0]}", flush=True)
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
    press = pressor(player, play.gym_map_set(GYM))
    states = [list(g.position())]
    for d in presses:
        before = list(g.position())
        press(tuple(d))
        if list(g.position()) == before and press.wake():
            press(tuple(d))  # the press a trainer's intro swallowed
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
    gr["4,1"] = route
    with open(gr_path, "w") as f:
        json.dump(gr, f)
    print("ROUTE WRITTEN", OUT, "and merged into gym_routes.json", flush=True)


def replay_existing() -> None:
    player, e, g, press = boot(play.gym_map_set(GYM))
    with open(OUT) as f:
        presses = [tuple(p) for p in json.load(f)["presses"]]
    replay(player, presses)


if __name__ == "__main__":
    replay_existing() if "--replay" in sys.argv else main()
