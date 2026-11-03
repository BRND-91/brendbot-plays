"""Is emerge a YES/NO dialogue that a single B opens and never answers? take_dive(EMERGE) presses
B once and reads map_id 120 frames later, so an open "use DIVE?" prompt reads as stuck. This
presses B, dumps the screen, then answers it (A YES, A dismiss) the way the dive-down path does,
on (0,51) tile (48,66) and (24,5) tile (5,6). PNGs to /tmp for the screen read. Reads fixtures,
writes only /tmp.
"""
import os

import emu_boot as eb
import map_graph
import play
import rowe_rom
from nav import Grid

BASE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(BASE, "states", "fixtures", "sootopolis_underwater_stuck.ss")
MASK = 0x0FFF


def _player(ledger):
    e = eb.Emu()
    e.load_state(open(FIX, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path=ledger)
    p.graph = map_graph.MapGraph(
        os.path.join(BASE, "states", "map_graph.json"),
        world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
    return p


def beh(p):
    g = Grid(p.e)
    x, y, *_ = p.g.position()
    return g._behavior(g.cell(x, y) & MASK)


def sequence(p, tag):
    stable_a = tuple(p.g.position())
    p.run(16, 0)
    stopped = tuple(p.g.position()) == stable_a
    b0 = tuple(p.g.position())
    print(f"[{tag}] tile {b0[:2]} beh={beh(p):#x} stopped={stopped}")
    p.run(8, eb.KEY_B)
    p.run(90, 0)
    afterB = tuple(p.g.position())
    p.e.save_png(f"/tmp/emerge_{tag}_afterB.png")
    print(f"[{tag}] after B: {b0[2:]}@{b0[:2]} -> {afterB[2:]}@{afterB[:2]}  png=/tmp/emerge_{tag}_afterB.png")
    p.run(8, eb.KEY_A)
    p.run(90, 0)
    p.run(8, eb.KEY_A)
    p.run(180, 0)
    fin = tuple(p.g.position())
    p.e.save_png(f"/tmp/emerge_{tag}_final.png")
    print(f"[{tag}] after B,A,A: -> {fin[2:]}@{fin[:2]}  "
          f"{'EMERGED' if fin[2:] != b0[2:] else 'no map change'}  png=/tmp/emerge_{tag}_final.png")


if __name__ == "__main__":
    p = _player("/tmp/rowe-dlg51.json")
    p._cross_to((24, 5), (0, 51))
    r = p.nav.walk_to((48, 66), surf=True, tools=p.field_moves())
    if tuple(p.g.position())[2:] == (0, 51):
        sequence(p, "51")
    else:
        print("could not reach (48,66) on (0,51), at", tuple(p.g.position()), "walk", r)

    p = _player("/tmp/rowe-dlg245.json")
    sequence(p, "245")
