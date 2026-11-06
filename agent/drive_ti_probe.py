"""Drive a /tmp copy of the live save on the real sevii path until talk_warp reaches a Seagallop
dock sailor, then sweep A-presses in place logging the native multichoice template so the empty read
at the Three Island dock is captured on the production code path. Reads live (copied to /tmp), writes
only under /tmp. Never touches states/live*. Raises ProbeDone to stop the loop at the first dock talk.

    drive_ti_probe.py [--seconds 300] [--sweep 18]
"""
import argparse
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb  # noqa: E402
import play  # noqa: E402
import rowe_symbols as S  # noqa: E402
import script_decode  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
LIVE = os.path.join(BASE, "states", "live.ss")
GRAPH = os.path.join(BASE, "states", "map_graph.json")
GOAL = os.path.join(BASE, "states", "goal.json")
OUT = "/tmp/rowe_ti_drive"


class ProbeDone(Exception):
    pass


def tmpl(e):
    items = struct.unpack_from("<I", e.read(S.MENU_LIST_TEMPLATE, 4), 0)[0]
    total = struct.unpack_from("<H", e.read(S.MENU_LIST_TEMPLATE + 0x0C, 2), 0)[0]
    return items, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=300.0)
    ap.add_argument("--sweep", type=int, default=18)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    work = os.path.join(OUT, "live.ss")
    shutil.copy(LIVE, work)
    shutil.copy(GRAPH, os.path.join(OUT, "map_graph.json"))
    shutil.copy(GOAL, os.path.join(OUT, "goal.json"))

    e = eb.Emu()
    e.load_state(open(work, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path=os.path.join(OUT, "caught.json"))
    p.state_path = work
    er = p.g_errands if hasattr(p, "g_errands") else p.errands
    orig = er._menu_rows

    ISLAND = b"\xc3\xe7\xe0\xd5\xe2\xd8"  # encoded "Island"

    def locate():
        ew = e.read(0x02000000, 0x40000)
        hits = []
        s = 0
        while True:
            k = ew.find(ISLAND, s)
            if k < 0:
                break
            hits.append(0x02000000 + k)
            s = k + 1
        if not hits:
            print("  no island name in EWRAM yet", flush=True)
            return
        lo, hi = min(hits) - 0x40, max(hits) + 0x10
        # a ListMenuItem array is 8-byte stride {u32 label into [lo,hi]; s32 idx}; find the longest run
        best = None
        for start in range(0, len(ew) - 8, 4):
            n = 0
            off = start
            while off + 8 <= len(ew):
                ptr, idx = struct.unpack_from("<Ii", ew, off)
                if lo <= ptr <= hi and -2 <= idx <= 32:
                    n += 1
                    off += 8
                else:
                    break
            if n >= 3 and (best is None or n > best[1]):
                best = (0x02000000 + start, n)
        print(f"  island buffers {[hex(x) for x in hits]}", flush=True)
        if best is None:
            print("  no item array found", flush=True)
            return
        arr, n = best
        print(f"  item-array@ {hex(arr)} entries {n}", flush=True)
        # the real array may start before the island run (Slateport City idx0, Cancel last); widen
        a0 = arr
        while a0 - 8 >= 0x02000000:
            ptr, idx = struct.unpack("<Ii", e.read(a0 - 8, 8))
            if 0x02000000 <= ptr < 0x02040000 and -2 <= idx <= 32:
                a0 -= 8
            else:
                break
        entries = []
        off = a0
        while off < arr + n * 8 + 16:
            ptr, idx = struct.unpack("<Ii", e.read(off, 8))
            if not (0x02000000 <= ptr < 0x0A000000 and -2 <= idx <= 32):
                break
            entries.append((hex(off), hex(ptr), idx))
            off += 8
        print(f"  full array@ {hex(a0)} entries {entries}", flush=True)
        for cand in {arr, a0}:
            needle = struct.pack("<I", cand)
            for lbl, reg, base in (("EWRAM", ew, 0x02000000),
                                   ("WRAM03", e.read(0x03000000, 0x8000), 0x03000000)):
                o = reg.find(needle)
                while o >= 0:
                    if o % 4 == 0:
                        hdr = reg[o:o + 16].hex()
                        print(f"  items={hex(cand)} template@ {lbl} {hex(base + o)} first16 {hdr}", flush=True)
                    o = reg.find(needle, o + 1)

    def patched():
        if er.map_id() in script_decode.SEAGALLOP_DOCKS:
            print(f"\n=== DOCK TALK at map {er.map_id()} pos {p.g.position()} ===", flush=True)
            for i in range(a.sweep):
                items, total = tmpl(e)
                rows = orig()
                locked = e.read(S.FIELD_LOCKED, 1)[0]
                cur = e.read(S.MENU_CURSOR, 1)[0]
                lcur = e.read(0x0203CFAA, 1)[0]
                print(f"step {i}: locked {locked} cur {cur} listcur {lcur} "
                      f"tmpl_items {items:#010x} total {total} rows {sorted(rows.items())}", flush=True)
                if i < 5:
                    p.tap(eb.KEY_A)   # advance greeting only
                    p.run(45, 0)
                else:
                    locate()          # menu should be open; stop pressing A, find the real list
                    p.run(30, 0)
            raise ProbeDone()
        return orig()

    er._menu_rows = patched
    print(f"booted at {p.g.position()} badges {p.g.badges()}", flush=True)
    try:
        p.loop(a.seconds)
    except ProbeDone:
        print("probe done", flush=True)
    print(f"final {p.g.position()}", flush=True)


if __name__ == "__main__":
    main()
