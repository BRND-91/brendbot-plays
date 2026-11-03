"""Characterize the (0,51) landing pocket: its reachable bounds, whether any map-border or warp
exit is reachable, the underwater-behaviour histogram, and whether a B press emerges anywhere in
it. Settles whether the third crossing is a warp-exclusion fix or a route-reachability problem.
Reads the fixture, writes only the /tmp ledger.
"""
import collections
import os

import emu_boot as eb
import map_graph
import play
import rowe_rom
from nav import Grid

BASE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(BASE, "states", "fixtures", "sootopolis_underwater_stuck.ss")
GRID_ID_MASK = 0x0FFF


def _on_51():
    e = eb.Emu()
    e.load_state(open(FIX, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-pocket.json")
    p.graph = map_graph.MapGraph(
        os.path.join(BASE, "states", "map_graph.json"),
        world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
    p._cross_to((24, 5), (0, 51))
    return p


if __name__ == "__main__":
    p = _on_51()
    x, y, *_ = p.g.position()
    grid = Grid(p.e)
    reach = grid.reachable((x, y), surf=True)
    w, h, _ = rowe_rom.map_cells(0, 51)
    xs = [t[0] for t in reach]
    ys = [t[1] for t in reach]
    print(f"pos ({x},{y}) map {w}x{h} reachable {len(reach)} x[{min(xs)},{max(xs)}] y[{min(ys)},{max(ys)}]")
    print("reachable warp tiles:", sorted(t for t in reach if t in grid.warp_tiles))
    print("reachable on east edge (x==w-1):", sorted(t for t in reach if t[0] == w - 1)[:5])
    print("reachable on west edge (x==0):", sorted(t for t in reach if t[0] == 0)[:5])
    print("reachable on south edge (y==h-1):", sorted(t for t in reach if t[1] == h - 1)[:5])

    hist = collections.Counter(grid._behavior(grid.cell(*t) & GRID_ID_MASK) for t in reach)
    print("uw behaviour histogram:", {hex(k): v for k, v in hist.most_common()})

    corners = [(min(xs), min(ys)), (max(xs), min(ys)), (min(xs), max(ys)), (max(xs), max(ys)), (x, y)]
    for c in corners:
        cand = min((t for t in reach if t not in grid.warp_tiles),
                   key=lambda t: abs(t[0] - c[0]) + abs(t[1] - c[1]))
        r = p.nav.walk_to(cand, surf=True, tools=p.field_moves())
        if tuple(p.g.position())[2:] != (0, 51):
            print(f"walk toward {c} -> hit {cand}: {r}, map changed to {tuple(p.g.position())}")
            break
        before = tuple(p.g.position())
        p.run(24, eb.KEY_B)
        p.run(120, 0)
        after = tuple(p.g.position())
        print(f"B at {before[:2]} (near {c}): -> {after}")
