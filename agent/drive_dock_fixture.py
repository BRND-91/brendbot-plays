"""Build the Seagallop dock fixture from a /tmp copy of the live save: walk to the dock building
entrance (2,2), take its warp onto the dock (2,3), freeze the landing as a fixture piece 3 drives
talk_warp against. Never touches the live save; the copy and the frozen state live under OUTDIR and
the fixture is written once at the end to states/fixtures/.

    drive_dock_fixture.py [--leg-seconds 900] [--outdir /tmp/rowe-dock]

(2,2) is the Hoenn-side entrance the live graph has walked and the only visited world source that
warps to (2,3); (33,13) also warps there but is unvisited. Logs the reached map and the ferry flags
on the landing, stops on the first leg that does not arrive.
"""
import argparse
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb  # noqa: E402
import play  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
LIVE = os.path.join(BASE, "states", "live.ss")
GRAPH = os.path.join(BASE, "states", "map_graph.json")
FIXTURE = os.path.join(BASE, "states", "fixtures", "seagallop_dock.ss")
FERRY = (0xCD1, 0xCE8, 0xCE7)
ENTRANCE, DOCK = (2, 2), (2, 3)


def hb(outdir: str, msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    with open(os.path.join(outdir, "heartbeat.log"), "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def write_goal(outdir: str, dest: tuple) -> None:
    import json
    with open(os.path.join(outdir, "goal.json"), "w") as f:
        json.dump({"mode": "travel", "to": list(dest)}, f)


def run_leg(player: play.Player, outdir: str, dest: tuple, seconds: float) -> tuple:
    write_goal(outdir, dest)
    here = player.g.position()[2:]
    if here == dest:
        return dest
    hb(outdir, f"leg -> {list(dest)} from {list(here)}")
    try:
        player.loop(seconds)
    except play.GoalExit as g:
        hb(outdir, f"  GoalExit {g}")
    return player.g.position()[2:]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leg-seconds", type=float, default=900.0)
    ap.add_argument("--outdir", default="/tmp/rowe-dock")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    work = os.path.join(a.outdir, "live.ss")
    shutil.copy(LIVE, work)
    shutil.copy(GRAPH, os.path.join(a.outdir, "map_graph.json"))

    e = eb.Emu()
    with open(work, "rb") as f:
        e.load_state(f.read())
    player = play.Player(e, play.NullStreamer(), ledger_path=os.path.join(a.outdir, "caught.json"))
    player.state_path = work
    hb(a.outdir, f"booted live copy at {list(player.g.position())}, badges {player.g.badges()}")

    for dest in (ENTRANCE, DOCK):
        reached = run_leg(player, a.outdir, dest, a.leg_seconds)
        if reached != dest:
            hb(a.outdir, f"STALL: wanted {list(dest)}, stuck at {list(reached)}; drive stops")
            return

    pos = player.g.position()
    ferry = " ".join(f"{f:03X}:{int(player.g.flag(f))}" for f in FERRY)
    frozen = os.path.join(a.outdir, "seagallop_dock.ss")
    with open(frozen, "wb") as f:
        f.write(e.save_state())
    shutil.copy(frozen, FIXTURE)
    hb(a.outdir, f"DOCK FIXTURE at {list(pos)} tile {list(pos[:2])} ferry {ferry} -> {FIXTURE}")


if __name__ == "__main__":
    main()
