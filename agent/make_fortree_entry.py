"""Save a Fortree gym door-mat state from the live run's snapshot, for probe_fortree_bfs.py --entry.

The shipped entry state predates the gym's trainer fights; the live run has them beaten, so a
route solved from it meets no fight and the gate bytes it records are the ones the live walk
reads. Drives the executor's own travel from the snapshot's map into the gym, one hop per
call, playing out any wild fight on the way, and stops on the first frame inside the gym.

    make_fortree_entry.py [SNAPSHOT] [OUT]
"""
import os
import shutil
import sys

import emu_boot as eb
import play
from nav import GATE_SETTLE_FRAMES

GYM = (12, 1)
SNAPSHOT = sys.argv[1] if len(sys.argv) > 1 else "states/route101.ss"
OUT = sys.argv[2] if len(sys.argv) > 2 else "states/probe/fortree_entry_beaten.ss"
SRC = "states/probe/entry_src.ss"  # loop() reads goal.json and map_graph.json from this file's dir
MAX_STEPS = 400


def main() -> None:
    shutil.copy(SNAPSHOT, SRC)
    with open(os.path.join(os.path.dirname(SRC), "goal.json"), "w") as f:
        f.write('{"mode": "gym", "map": [12, 1], "badges": 4}')
    e = eb.Emu()
    with open(SRC, "rb") as f:
        e.load_state(f.read())
    player = play.Player(e, play.NullStreamer(), ledger_path=SRC + ".caught.json")
    player.state_path = SRC
    player.loop(0)  # binds goal, map graph and stuck hits off the probe dir, runs no step
    g = player.g
    for step in range(MAX_STEPS):
        if g.position()[2:] == GYM:
            break
        if g.in_battle():
            player.battle_step()
            continue
        player.travel_toward(GYM)
        print(f"step {step}: at {g.position()}", flush=True)
    else:
        print(f"NO ENTRY after {MAX_STEPS} steps, at {g.position()}", flush=True)
        return
    e.run(GATE_SETTLE_FRAMES, 0)
    with open(OUT, "wb") as f:
        f.write(e.save_state())
    print(f"ENTRY WRITTEN {OUT} at {g.position()}", flush=True)


if __name__ == "__main__":
    main()
