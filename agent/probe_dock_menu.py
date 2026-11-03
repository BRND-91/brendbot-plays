"""Smoke the Seagallop dock menu on the fixture: walk to the sailor's approach tile, face up, press A,
and log the map id and the multichoice cursor byte each step so the talk_warp executor can ground
"menu is open" in observed RAM rather than a frame count. Reads states/fixtures/seagallop_dock.ss,
writes only /tmp. Phase 1 is observation; no picks fed yet.

    probe_dock_menu.py [--taps 40] [--dest 25,24]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb  # noqa: E402
import play  # noqa: E402
import rowe_symbols as S  # noqa: E402
import script_decode  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "seagallop_dock.ss")
OUT = "/tmp/rowe-dock"


def cur(e):
    return e.read(S.MENU_CURSOR, 1)[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--taps", type=int, default=40)
    ap.add_argument("--dest", default="25,24")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    dest = tuple(int(x) for x in a.dest.split(","))

    t = script_decode.talk_object((2, 3), dest)
    print("talk_object", t, flush=True)
    seq = script_decode.menu_sequence((2, 3), dest)
    print("menu_sequence", seq, flush=True)

    e = eb.Emu()
    e.load_state(open(FIXTURE, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path=os.path.join(OUT, "probe.json"))
    g = p.g
    print("start", g.position(), "cursor", cur(e), "cb2", hex(g.callback2()), flush=True)

    # (10,3) directly below the sailor is a blocked counter (behavior 0x80); the player talks
    # across it from (10,4). talk_object's tile-below approach is wrong for a counter and gets fixed
    # in piece 1 once this confirms the counter reach.
    approach = (t["obj"][0], t["obj"][1] + 2)
    r = p.nav.walk_to(approach)
    print(f"walk_to {approach} -> {r} at {g.position()}", flush=True)
    p.run(8, eb.KEY_UP)
    p.run(8, 0)
    print("faced up at", g.position(), flush=True)
    e.save_png(os.path.join(OUT, "dock_faced.png"))

    last = None
    for i in range(a.taps):
        p.tap(eb.KEY_A)
        p.run(16, 0)
        pos = g.position()
        line = (tuple(pos[2:]), tuple(pos[:2]), cur(e), hex(g.callback2()))
        if line != last:
            print(f"tap {i}: map {line[0]} tile {line[1]} cursor {line[2]} cb2 {line[3]}", flush=True)
            last = line
        if tuple(pos[2:]) != (2, 3):
            print(f"MAP CHANGED to {tuple(pos[2:])} after {i} A-taps", flush=True)
            e.save_png(os.path.join(OUT, "dock_warped.png"))
            return
    e.save_png(os.path.join(OUT, "dock_endtaps.png"))
    print("no map change after taps; final", g.position(), "cursor", cur(e), flush=True)


if __name__ == "__main__":
    main()
