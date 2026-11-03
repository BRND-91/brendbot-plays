"""Drive the Victory Road interior leg on the parked (16,12) fixture through the real executor
loop, to measure where nav stops between the entry hall (16,12) and the League exit toward
(25,60). The static world graph expresses (16,12)->(16,13)->(25,60) and (16,10)->(16,14)->(25,60);
the live grind bounced (16,12)<->(0,8) without taking (16,13), so this isolates each forward
crossing. Target map comes from argv (default (16,13)); each take_warp logs map id and tile
before/after so a stall shows as the map not changing. On arrival at the target it freezes a
fixture for the next leg's deterministic test."""
import os
import shutil
import sys

import emu_boot as eb
import play
import routines

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "vr_entry_16_12.ss")
SCRATCH = "/tmp/rowe-vrint"


def main(target: tuple, budget: float) -> None:
    os.makedirs(SCRATCH, exist_ok=True)
    live = os.path.join(SCRATCH, "live.ss")
    shutil.copy(FIXTURE, live)
    shutil.copy(os.path.join(BASE, "states", "map_graph.json"), os.path.join(SCRATCH, "map_graph.json"))
    with open(os.path.join(SCRATCH, "goal.json"), "w") as f:
        f.write('{"mode": "travel", "to": [%d, %d]}' % target)

    e = eb.Emu()
    with open(live, "rb") as f:
        e.load_state(f.read())
    player = play.Player(e, play.NullStreamer(), ledger_path=os.path.join(SCRATCH, "caught.json"))
    player.state_path = live

    orig_warp = routines.Errands.take_warp

    def traced_warp(self, dest, surf=False, rank=None, tools=frozenset()):
        p0 = self.g.position()
        r = orig_warp(self, dest, surf=surf, rank=rank, tools=tools)
        p1 = self.g.position()
        changed = p0[2:] != p1[2:]
        print(f"take_warp {dest}: map {p0[2:]} tile {p0[:2]} -> map {p1[2:]} tile {p1[:2]} "
              f"changed={changed} r={r}", flush=True)
        return r

    routines.Errands.take_warp = traced_warp

    start = player.g.position()
    print(f"start map {start[2:]} tile {start[:2]}, target {target}, budget {budget}s", flush=True)
    try:
        player.loop(budget)
        pos = player.g.position()
        print(f"TIMER: budget ran out at map {pos[2:]} tile {pos[:2]}, battles {player.battles}", flush=True)
    except play.GoalExit as g:
        end = player.g.position()
        print(f"GOALEXIT: {g}", flush=True)
        print(f"end map {end[2:]} tile {end[:2]}, battles {player.battles}", flush=True)
        if end[2:] == target:
            out = os.path.join(BASE, "states", "fixtures", "vr_%d_%d.ss" % target)
            with open(out, "wb") as fh:
                fh.write(player.e.save_state())
            print(f"LEG SUCCESS: map changed to {target}, froze {out}", flush=True)
        else:
            print(f"LEG INCOMPLETE: stopped at map {end[2:]}", flush=True)


if __name__ == "__main__":
    tgt = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (16, 13)
    bud = float(sys.argv[3]) if len(sys.argv) > 3 else 90.0
    main(tgt, bud)
