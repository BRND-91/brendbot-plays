"""Instrument the Seagallop sailor's native multichoice per A-press so the empty-menu read at the
Three Island dock can be diffed against the known-good Slateport fixture. Boots any .ss (a /tmp copy
of live or a fixture), approaches the sailor, then logs map / FIELD_LOCKED / MENU_CURSOR / the raw
MENU_LIST_TEMPLATE items-pointer + totalItems / _menu_rows() after every A. Writes nothing; reads
only. /tmp prefix rowe_ti so no live dump is shadowed.

    probe_ti_ferry.py --state /tmp/rowe_ti_probe.ss --dest 9,9 [--obj X,Y --approach X,Y] [--taps 12]
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb  # noqa: E402
import play  # noqa: E402
import rowe_symbols as S  # noqa: E402
import script_decode  # noqa: E402


def pair(s):
    return tuple(int(x) for x in s.split(","))


def template(e):
    items = struct.unpack_from("<I", e.read(S.MENU_LIST_TEMPLATE, 4), 0)[0]
    total = struct.unpack_from("<H", e.read(S.MENU_LIST_TEMPLATE + 0x0C, 2), 0)[0]
    return items, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--dest", type=pair, default=(9, 9))
    ap.add_argument("--obj", type=pair, default=None)
    ap.add_argument("--approach", type=pair, default=None)
    ap.add_argument("--taps", type=int, default=12)
    a = ap.parse_args()

    e = eb.Emu()
    e.load_state(open(a.state, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe_ti_probe.json")
    g, er = p.g, p.errands
    here = tuple(g.position()[2:])
    print(f"start pos {g.position()} map {here} badges {g.badges()}", flush=True)

    obj, approach = a.obj, a.approach
    if obj is None:
        t = script_decode.talk_object(here, a.dest)
        print(f"talk_object({here},{a.dest}) -> {t}", flush=True)
        if t is None:
            print("no talk_object; pass --obj/--approach", flush=True)
            return
        obj = t["obj"]
        approach = approach or t.get("approach")
    if approach is None:
        approach = er._approach_tile(obj)
    print(f"obj {obj} approach {approach}", flush=True)

    r = p.nav.walk_to(approach)
    print(f"walk_to {approach} -> {r} at {g.position()}", flush=True)
    if r != "arrived":
        print("did not reach approach; stopping", flush=True)
        return
    dx, dy = obj[0] - approach[0], obj[1] - approach[1]
    if abs(dx) >= abs(dy):
        face = eb.KEY_RIGHT if dx > 0 else eb.KEY_LEFT
    else:
        face = eb.KEY_DOWN if dy > 0 else eb.KEY_UP
    p.run(8, face)
    p.run(8, 0)
    print(f"faced {face} at {g.position()}", flush=True)

    for i in range(a.taps):
        p.tap(eb.KEY_A)
        p.run(45, 0)
        pos = g.position()
        m = tuple(pos[2:])
        locked = e.read(S.FIELD_LOCKED, 1)[0]
        cursor = e.read(S.MENU_CURSOR, 1)[0]
        items, total = template(e)
        rows = er._menu_rows()
        print(f"A{i}: map {m} tile {tuple(pos[:2])} locked {locked} cursor {cursor} "
              f"tmpl_items {items:#010x} total {total} rows {sorted(rows.items())}", flush=True)
        if m != here:
            print(f"MAP CHANGED to {m} after {i} A-taps", flush=True)
            return
    print("no map change after taps", flush=True)


if __name__ == "__main__":
    main()
