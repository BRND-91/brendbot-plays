"""Drive the live overworld logic from a city save copy into the Sootopolis gym to Juan's fight.

    .venv/bin/python test1_live_gym.py <state.ss> [seconds]

Loads the save onto a /tmp copy, runs Player.overworld_step (the same dispatcher the live loop calls,
not a probe replay) toward gym (15,0). Single wild/trainer fights met on the way are played out by the
real battle_step so the walk continues; the run stops and reports flags at the first battle on the gym
floor (Juan) or any double battle (the double is the known battle_step hang, so it is read, not entered),
or when the time budget elapses. Logs every position change as map/tile and every battle.
"""
import os
import shutil
import sys
import time

import emu_boot as eb
import play
import rowe_rom

BASE = os.path.dirname(os.path.abspath(__file__))
GYM = (15, 0)
STAND = (8, 3)
BATTLE_TYPE_DOUBLE = 0x1
BATTLE_STEP_CAP = 300  # battle_steps per intervening single fight before it is called hung


def mk_player(path):
    work = "/tmp/test1_live_gym.ss"
    shutil.copy(path, work)
    e = eb.Emu()
    e.load_state(open(work, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-test1.json")
    p.goal = {"mode": "gym", "map": list(GYM), "badges": 7, "stand": list(STAND)}
    p.graph = play.map_graph.MapGraph(
        os.path.join(BASE, "states", "map_graph.json"),
        world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
    return p


def main():
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 300.0
    p = mk_player(sys.argv[1])
    g = p.g
    print(f"start pos {g.position()} map {tuple(g.position()[2:])} tile {tuple(g.position()[:2])} "
          f"badges {g.badges()}", flush=True)
    t0 = time.monotonic()
    last = None
    i = 0
    while time.monotonic() - t0 < budget:
        if g.in_battle():
            pos = g.position()
            flags = g.battle_type_flags()
            double = bool(flags & BATTLE_TYPE_DOUBLE)
            onfloor = tuple(pos[2:]) == GYM
            print(f"BATTLE pos {pos} map {tuple(pos[2:])} tile {tuple(pos[:2])} "
                  f"flags {flags:#x} double {double}", flush=True)
            if onfloor:
                print(f"JUAN flags {flags:#x} double {double} at {pos}", flush=True)
                break
            if double:
                print(f"DOUBLE off the gym floor at {pos}, stopping before battle_step (hang risk)", flush=True)
                break
            steps = 0
            while g.in_battle() and steps < BATTLE_STEP_CAP:
                p.battle_step()
                steps += 1
            print(f"cleared intervening battle in {steps} steps, now {g.position()} "
                  f"in_battle {g.in_battle()}", flush=True)
            if g.in_battle():
                print("intervening battle did not end within cap, stopping", flush=True)
                break
            continue
        try:
            p.overworld_step(i)
        except play.GoalExit as ex:
            print(f"GoalExit {ex} at {g.position()}", flush=True)
            break
        except play.StopRequested as ex:
            print(f"StopRequested {ex} at {g.position()}", flush=True)
            break
        i += 1
        pos = tuple(g.position())
        if pos != last:
            print(f"pos {pos} map {pos[2:]} tile {pos[:2]}", flush=True)
            last = pos
    pos = g.position()
    print(f"END pos {pos} map {tuple(pos[2:])} tile {tuple(pos[:2])} in_battle {g.in_battle()} "
          f"elapsed {time.monotonic() - t0:.0f}s steps {i}", flush=True)


if __name__ == "__main__":
    main()
