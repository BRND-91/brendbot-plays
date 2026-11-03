"""Parked-copy acceptance drive: travel from the live party's current map to a Sevii island,
proving the Seagallop crossing end to end with a map-id trace. Never touches the live save.

Copies states/live.ss and states/map_graph.json under /tmp, sets a travel goal to One Island
(0,75) (the Seagallop landing off the (13,10) hub), and drives play.Player.loop in short legs so
a heartbeat lands every leg. Writes each map change to trace.log, stops on arrival or timeout, and
records the trace SHA-256 last.

    drive_to_island.py [total-seconds] [--to G,N]

Channel rule "ROWE live save": the copy and every write resolve under /tmp; the live run is the
only writer of states/live.ss and rowe_live.guard_write enforces it.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb  # noqa: E402
import play  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
DRIVE = "/tmp/rowe-island-drive"
LEG = 25.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("total", nargs="?", type=float, default=1800.0)
    ap.add_argument("--to", default="0,75")
    a = ap.parse_args()
    target = tuple(int(v) for v in a.to.split(","))

    os.makedirs(DRIVE, exist_ok=True)
    drive_ss = os.path.join(DRIVE, "drive.ss")
    shutil.copy(os.path.join(BASE, "states", "live.ss"), drive_ss)
    shutil.copy(os.path.join(BASE, "states", "map_graph.json"), os.path.join(DRIVE, "map_graph.json"))
    for scratch in ("stuck_hits.json", "status.json"):
        p = os.path.join(DRIVE, scratch)
        if os.path.exists(p):
            os.remove(p)
    with open(os.path.join(DRIVE, "goal.json"), "w") as f:
        json.dump({"mode": "travel", "to": list(target)}, f)

    trace = os.path.join(DRIVE, "trace.log")

    def hb(msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
        with open(trace, "a") as f:
            f.write(line + "\n")
        print(line, flush=True)

    e = eb.Emu()
    with open(drive_ss, "rb") as f:
        e.load_state(f.read())
    player = play.Player(e, play.NullStreamer(), ledger_path=os.path.join(DRIVE, "caught.json"))
    player.state_path = drive_ss

    start = player.g.position()[2:]
    hb(f"START from {start} tile {player.g.position()[:2]} badges {player.g.badges()}, target island {target}")

    end = time.monotonic() + a.total
    last = None
    arrived = False
    while time.monotonic() < end and not arrived:
        try:
            player.loop(LEG)
        except play.GoalExit as g:
            hb(f"GoalExit {g}: at {player.g.position()[2:]}")
            with open(os.path.join(DRIVE, "goal.json"), "w") as f:
                json.dump({"mode": "travel", "to": list(target)}, f)
        pos = player.g.position()[2:]
        if pos != last:
            hb(f"MAP {pos} tile {player.g.position()[:2]}")
            last = pos
        arrived = pos == target

    hb(f"ARRIVED island {target}" if arrived else f"STOP timeout {a.total}s at {player.g.position()[2:]}")
    hb(f"TRACE_SHA256 {hashlib.sha256(open(trace, 'rb').read()).hexdigest()}")


if __name__ == "__main__":
    main()
