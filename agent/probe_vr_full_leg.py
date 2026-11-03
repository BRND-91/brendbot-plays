"""Drive the full (0,8)->(16,12) Victory Road entry leg on the parked Ever Grande fixture through
the real executor loop, so wild surf encounters on the climb-and-approach walk are fought by
battle_step instead of hand-walked. The loop re-plans from the post-battle tile each tick and
take_warp presses UP into the MB_ANIMATED_DOOR at (27,48) from approach (27,49). Each take_warp
attempt logs map id and tile before/after so the door-press map change into (16,12) is observed,
and the first time the approach walk lands on (27,49) a pre-press fixture is frozen for a
deterministic door-press test. GoalExit 'arrived at map [16, 12]' is the success signal."""
import os
import shutil
import sys

import emu_boot as eb
import nav
import play
import routines

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "evergrande_0_8.ss")
PREPRESS = os.path.join(BASE, "states", "fixtures", "vr_door_27_49.ss")
ARRIVED = os.path.join(BASE, "states", "fixtures", "vr_entry_16_12.ss")
SCRATCH = "/tmp/rowe-vrleg"
ENTRY = (16, 12)
APPROACH = (27, 49)


def main(budget: float) -> None:
    os.makedirs(SCRATCH, exist_ok=True)
    live = os.path.join(SCRATCH, "live.ss")
    shutil.copy(FIXTURE, live)
    shutil.copy(os.path.join(BASE, "states", "map_graph.json"), os.path.join(SCRATCH, "map_graph.json"))
    with open(os.path.join(SCRATCH, "goal.json"), "w") as f:
        f.write('{"mode": "travel", "to": [16, 12]}')

    e = eb.Emu()
    with open(live, "rb") as f:
        e.load_state(f.read())
    player = play.Player(e, play.NullStreamer(), ledger_path=os.path.join(SCRATCH, "caught.json"))
    player.state_path = live

    frozen = {"done": False}
    orig_walk = nav.Navigator.walk_to

    def traced_walk(self, goal, surf=False, max_replans=20, tools=frozenset()):
        r = orig_walk(self, goal, surf=surf, max_replans=max_replans, tools=tools)
        p = self.g.position()
        if not frozen["done"] and p[:2] == APPROACH and p[2:] == (0, 8):
            with open(PREPRESS, "wb") as fh:
                fh.write(self.e.save_state())
            frozen["done"] = True
            print(f"froze pre-press fixture at tile {p[:2]} map {p[2:]} -> {PREPRESS}", flush=True)
        return r

    nav.Navigator.walk_to = traced_walk

    orig_warp = routines.Errands.take_warp

    def traced_warp(self, dest, surf=False, rank=None, tools=frozenset()):
        p0 = self.g.position()
        r = orig_warp(self, dest, surf=surf, rank=rank, tools=tools)
        p1 = self.g.position()
        print(f"take_warp {dest}: before map {p0[2:]} tile {p0[:2]} -> after map {p1[2:]} tile {p1[:2]} = {r}", flush=True)
        return r

    routines.Errands.take_warp = traced_warp

    start = player.g.position()
    print(f"start map {start[2:]} tile {start[:2]}, budget {budget}s", flush=True)
    try:
        player.loop(budget)
        pos = player.g.position()
        print(f"TIMER: budget ran out at map {pos[2:]} tile {pos[:2]}, battles {player.battles}", flush=True)
    except play.GoalExit as g:
        end = player.g.position()
        print(f"GOALEXIT: {g}", flush=True)
        print(f"end map {end[2:]} tile {end[:2]}, battles {player.battles}", flush=True)
        if end[2:] == ENTRY:
            with open(ARRIVED, "wb") as fh:
                fh.write(player.e.save_state())
            print(f"FULL LEG SUCCESS: map changed to {ENTRY}, froze {ARRIVED}", flush=True)
        else:
            print(f"FULL LEG INCOMPLETE: stopped at map {end[2:]}", flush=True)


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 900.0)
