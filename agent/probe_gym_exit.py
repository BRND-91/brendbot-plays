"""Drive the live party out of the gym it stands in, on a scratch copy of the state, and record
every descend_gym verdict and position, so the mat-by-mat descent is seen reaching the exit
before the production supervisor runs it.

    probe_gym_exit.py [max_steps]
"""
import os
import shutil
import sys

import emu_boot as eb
import play

LIVE = "states"
SCRATCH = "states/probe"


def main() -> None:
    steps = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    os.makedirs(SCRATCH, exist_ok=True)
    state = os.path.join(SCRATCH, "route101.ss")
    shutil.copy(os.path.join(LIVE, "route101.ss"), state)
    emu = eb.Emu()
    with open(state, "rb") as f:
        emu.load_state(f.read())
    player = play.Player(emu, play.NullStreamer(), ledger_path=state + ".caught.json")
    here = player.g.position()[2:]
    print(f"PROBE start at {player.g.position()} gym {here in player._gyms}", flush=True)
    for i in range(steps):
        r = player.errands.descend_gym((0, 0))
        pos = player.g.position()
        print(f"PROBE step {i} -> {r} at {pos}", flush=True)
        if pos[2:] != here:
            print("PROBE DONE map changed", flush=True)
            return
    print("PROBE DONE budget spent", flush=True)


if __name__ == "__main__":
    main()
