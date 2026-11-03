"""Drive the live party at one gym in a scratch dir and record every gym_step verdict, so
the sweep (trainers in reach, then the gym's own doors) is seen clearing a gate or room
gym before the production supervisor runs it.

    probe_gym_sweep.py GROUP NUM [budget_seconds]
"""
import json
import os
import shutil
import sys

import emu_boot as eb
import play

LIVE = "states/fixtures"
SCRATCH = "/tmp/rowe_probe"


def stage(gym: list) -> str:
    os.makedirs(SCRATCH, exist_ok=True)
    shutil.copy(os.path.join(LIVE, "route101.ss"), os.path.join(SCRATCH, "route101.ss"))
    shutil.copy(os.path.join(LIVE, "map_graph.json"), os.path.join(SCRATCH, "map_graph.json"))
    with open(os.path.join(SCRATCH, "gym_closed.json"), "w") as f:
        json.dump([], f)
    return os.path.join(SCRATCH, "route101.ss")


def main() -> None:
    gym = [int(sys.argv[1]), int(sys.argv[2])]
    budget = int(sys.argv[3]) if len(sys.argv) > 3 else 1500
    state = stage(gym)
    emu = eb.Emu()
    with open(state, "rb") as f:
        emu.load_state(f.read())
    player = play.Player(emu, play.NullStreamer(), ledger_path=state + ".caught.json")
    player.state_path = state
    # check_goal reads a badge above this count as the gym won, so it is the save's own count
    with open(os.path.join(SCRATCH, "goal.json"), "w") as f:
        json.dump({"mode": "gym", "map": gym, "badges": player.g.badges()}, f)
    print(f"PROBE start gym {gym} at {player.g.position()} badges {player.g.badges()}", flush=True)
    try:
        player.loop(budget)
        print("PROBE DONE budget spent", flush=True)
    except play.GoalExit as g:
        print(f"PROBE DONE goal_exit {g}", flush=True)
    emu.save_png(os.path.join(SCRATCH, "gym_sweep_end.png"))
    print(f"PROBE end at {player.g.position()} badges {player.g.badges()} wins {player.wins}/{player.battles}", flush=True)


if __name__ == "__main__":
    main()
