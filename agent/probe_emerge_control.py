"""Known-good control for the emerge input routine. Step 3 showed B does nothing on valid 0x00 /
0x22 tiles in the (0,51) pocket, so the question is whether take_dive(EMERGE)'s B press works at
all. rapids.ss (0,49) is a surface map with a dive script; dive there, then emerge back, same
routine. If rapids round-trips and (0,51) does not, the fault is (0,51)'s connection/script; if
rapids emerge also fails, the fault is the B press. Also tests emerge from the stuck (24,5) start
back to Sootopolis (0,7). Reads fixtures, writes only the /tmp ledger.
"""
import os

import emu_boot as eb
import map_graph
import play
import rowe_map
import rowe_rom
from nav import Grid

BASE = os.path.dirname(os.path.abspath(__file__))
FIXDIR = os.path.join(BASE, "states", "fixtures")
MASK = 0x0FFF


def _player(fix, ledger):
    e = eb.Emu()
    e.load_state(open(os.path.join(FIXDIR, fix), "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path=ledger)
    p.graph = map_graph.MapGraph(
        os.path.join(BASE, "states", "map_graph.json"),
        world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
    return p


def beh_here(p):
    g = Grid(p.e)
    x, y, *_ = p.g.position()
    return g._behavior(g.cell(x, y) & MASK)


if __name__ == "__main__":
    print("=== control A: stuck fixture at start, emerge ===")
    p = _player("sootopolis_underwater_stuck.ss", "/tmp/rowe-ctlA.json")
    start = tuple(p.g.position())
    uw = rowe_rom.is_underwater(start[2], start[3])
    print(f"start {start} underwater={uw} beh={beh_here(p):#x}")
    before = tuple(p.g.position())
    st = p.errands.take_dive(rowe_map.DIR_EMERGE, surf=True, tools=p.field_moves())
    print(f"take_dive(EMERGE): {st} {before} -> {tuple(p.g.position())}")

    print("=== control B: rapids (0,49) dive then emerge round-trip ===")
    p = _player("rapids.ss", "/tmp/rowe-ctlB.json")
    start = tuple(p.g.position())
    print(f"start {start}")
    st = p.errands.take_dive(rowe_map.DIR_DIVE, surf=True, tools=p.field_moves())
    down = tuple(p.g.position())
    print(f"take_dive(DIVE): {st} -> {down} underwater={rowe_rom.is_underwater(down[2], down[3])}")
    if down[2:] != start[2:] and rowe_rom.is_underwater(down[2], down[3]):
        print(f"seabed beh={beh_here(p):#x}")
        b2 = tuple(p.g.position())
        st2 = p.errands.take_dive(rowe_map.DIR_EMERGE, surf=True, tools=p.field_moves())
        up = tuple(p.g.position())
        print(f"take_dive(EMERGE): {st2} {b2} -> {up} "
              f"{'EMERGED' if up[2:] != b2[2:] else 'no change'}")
    else:
        print("dive did not reach seabed, control B inconclusive")
