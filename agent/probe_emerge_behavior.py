"""Does emerge fire from the (0,51) pocket on a surfaceable tile? The prior pocket probe pressed
B without recording each tile's behaviour, so it never controlled for MB_NO_SURFACING (0x19) /
MB_SEAWEED_NO_SURFACING (0x2A), the only behaviours that block emerge. This runs the controlled
test: connection dump, behaviour buckets, B on the nearest 0x22 and 0x00 tiles, and a dive->B
control on a known dive fixture. Reads fixtures, writes only the /tmp ledger.
"""
import collections
import os

import emu_boot as eb
import map_graph
import play
import rowe_map
import rowe_rom
from nav import Grid

BASE = os.path.dirname(os.path.abspath(__file__))
FIXDIR = os.path.join(BASE, "states", "fixtures")
STUCK = os.path.join(FIXDIR, "sootopolis_underwater_stuck.ss")
DIVE = os.path.join(FIXDIR, "dive_probe.ss")
MASK = 0x0FFF
NO_SURFACE = {0x19, 0x2A}


def _player(fix, ledger):
    e = eb.Emu()
    e.load_state(open(fix, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path=ledger)
    p.graph = map_graph.MapGraph(
        os.path.join(BASE, "states", "map_graph.json"),
        world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
    return p


def beh(grid, t):
    return grid._behavior(grid.cell(*t) & MASK)


def stopped(p, frames=16):
    a = tuple(p.g.position())
    p.run(frames, 0)
    return tuple(p.g.position()) == a


def press_b(p):
    before = tuple(p.g.position())
    p.run(8, eb.KEY_B)
    p.run(180, 0)
    return before, tuple(p.g.position())


if __name__ == "__main__":
    p = _player(STUCK, "/tmp/rowe-emerge-beh.json")
    p._cross_to((24, 5), (0, 51))
    x, y, *_ = p.g.position()
    grid = Grid(p.e)
    land_beh = beh(grid, (x, y))
    print(f"=== step 1: connections(0,51), landing ({x},{y}) beh={land_beh:#x} ===")
    print("map_connections(0,51) [dir,dest]:", rowe_rom.map_connections(0, 51))
    print("map_warps(0,51):", rowe_rom.map_warps(0, 51))

    print("=== step 2: behaviour buckets from landing ===")
    reach = grid.reachable((x, y), surf=True)
    hist = collections.Counter(beh(grid, t) for t in reach)
    print("histogram:", {hex(k): v for k, v in hist.most_common()})
    for want in (0x22, 0x00):
        cand = sorted((t for t in reach if beh(grid, t) == want and t not in grid.warp_tiles),
                      key=lambda t: abs(t[0] - x) + abs(t[1] - y))[:3]
        print(f"nearest {want:#x} tiles:", cand)

    print("=== step 3: B on nearest 0x22 then nearest 0x00 ===")
    for want in (0x22, 0x00):
        p = _player(STUCK, "/tmp/rowe-emerge-beh.json")
        p._cross_to((24, 5), (0, 51))
        g2 = Grid(p.e)
        hx, hy, *_ = p.g.position()
        cands = sorted((t for t in g2.reachable((hx, hy), surf=True)
                        if beh(g2, t) == want and t not in g2.warp_tiles),
                       key=lambda t: abs(t[0] - hx) + abs(t[1] - hy))
        if not cands:
            print(f"{want:#x}: no non-warp tile of this behaviour, not run")
            continue
        tgt = cands[0]
        r = p.nav.walk_to(tgt, surf=True, tools=p.field_moves())
        pos = tuple(p.g.position())
        if pos[2:] != (0, 51):
            print(f"{want:#x} walk to {tgt}: {r}, bounced off (0,51) to {pos}, not a clean test")
            continue
        tb = beh(Grid(p.e), pos[:2])
        still = stopped(p)
        before, after = press_b(p)
        print(f"{want:#x} tile {pos[:2]} beh={tb:#x} walk={r} stopped={still} "
              f"B: {before[2:]}@{before[:2]} -> {after[2:]}@{after[:2]} "
              f"{'EMERGED' if after[2:] != before[2:] else 'no change'}")

    print("=== step 4: dive->B control on dive_probe.ss ===")
    if not os.path.exists(DIVE):
        print("dive_probe.ss missing, not run")
    else:
        p = _player(DIVE, "/tmp/rowe-dive-ctl.json")
        start = tuple(p.g.position())
        print("dive fixture start:", start)
        st = p.errands.take_dive(rowe_map.DIR_DIVE, surf=True, tools=p.field_moves())
        downpos = tuple(p.g.position())
        print(f"take_dive(DIVE): {st} -> {downpos}")
        if downpos[2:] != start[2:] and rowe_rom.is_underwater(*downpos[2:]):
            g3 = Grid(p.e)
            sb = beh(g3, downpos[:2])
            still = stopped(p)
            before, after = press_b(p)
            print(f"seabed {downpos[:2]} beh={sb:#x} stopped={still} "
                  f"B: {before[2:]}@{before[:2]} -> {after[2:]}@{after[:2]} "
                  f"{'EMERGED' if after[2:] != before[2:] else 'no change'}")
        else:
            print("did not reach an underwater seabed, control inconclusive")
