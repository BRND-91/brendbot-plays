"""Rank every save state on the box by game progress, to recover the live save after it was
overwritten. Read-only: loads each .ss into a fresh emulator, prints map, tile, badges, party.

    cd /opt/brendbot/rowe-agent && .venv/bin/python find_best_state.py [extra dirs...]
"""
import glob
import os
import sys
import time

import play
from emu_boot import Emu

DIRS = ["states", "states/probe", "states/fixtures", "/tmp", *sys.argv[1:]]


def main():
    paths = sorted({p for d in DIRS for p in glob.glob(os.path.join(d, "**", "*.ss*"), recursive=True)})
    rows = []
    for path in paths:
        try:
            e = Emu()
            e.load_state(open(path, "rb").read())
            g = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-recover-caught.json").g
            x, y, group, num = g.position()
            party = [m for m in g.party() if m.level]
            levels = [m.level for m in party]
            rows.append((g.badges(), sum(levels), path, (group, num), (x, y), levels, os.path.getmtime(path)))
        except Exception as ex:  # a truncated .tmp or a non-ROWE state
            print(f"skip {path}: {type(ex).__name__} {ex}")
    rows.sort(reverse=True)
    print(f"\n{'badges':>6} {'lvsum':>5}  {'mtime (UTC)':19}  map      tile      party levels  path")
    for badges, lvsum, path, m, t, levels, mtime in rows:
        when = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(mtime))
        print(f"{badges:>6} {lvsum:>5}  {when}  {str(m):8} {str(t):9} {levels}  {path}")


if __name__ == "__main__":
    main()
