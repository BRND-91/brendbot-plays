#!/usr/bin/env python3
"""Watch the grind until the Lavaridge gym (badge index 3) is captured, re-closed, or the window
ends. One N/M progress line per sample feeds the task dashboard. Exit 0 captured, 3 the gym closed
itself again (the sweep or the walk failed and needs a code fix), 2 the window ended with neither."""
import json
import sys
import time

STATES = "/opt/brendbot/rowe-agent/states"
LAVARIDGE = [4, 1]
LAVA_BADGE = 3            # badge_flags index Flannery's badge sets
SAMPLES = 40             # ~90s apart, a one-hour watch
PERIOD_S = 90


def _load(name: str):
    try:
        with open(f"{STATES}/{name}") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


for i in range(1, SAMPLES + 1):
    status = _load("status.json") or {}
    flags = status.get("badge_flags") or []
    goal = status.get("goal") or {}
    closed = {tuple(e["gym"]) for e in (_load("gym_closed.json") or []) if isinstance(e, dict)}
    captured = len(flags) > LAVA_BADGE and flags[LAVA_BADGE]
    print(f"{i}/{SAMPLES} map {status.get('map')} goal {goal.get('mode')}->"
          f"{goal.get('map') or goal.get('to')} badges {status.get('badges')} "
          f"lavaridge {'CAPTURED' if captured else 'pending'}", flush=True)
    if captured:
        print("Lavaridge captured, badge flag set", flush=True)
        sys.exit(0)
    if tuple(LAVARIDGE) in closed:
        print("Lavaridge re-closed itself, the gym attempt failed", flush=True)
        sys.exit(3)
    time.sleep(PERIOD_S)

print("watch window ended, Lavaridge neither captured nor re-closed", flush=True)
sys.exit(2)
