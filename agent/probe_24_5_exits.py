"""What exits does underwater Sootopolis (24,5) actually offer, and where do they land? The party
is frozen here. Prints its connections and warps, the reachable region from the frozen tile, and
which borders or warp tiles are reachable, to tell whether the route to (0,51)/(0,41) leaves by a
border swim or only by the warp that drops into the dead pocket. Reads the fixture, no writes.
"""
import os

import emu_boot as eb
import map_graph
import play
import rowe_rom
from nav import Grid

BASE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(BASE, "states", "fixtures", "sootopolis_underwater_stuck.ss")


def _player():
    e = eb.Emu()
    e.load_state(open(FIX, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-245.json")
    p.graph = map_graph.MapGraph(
        os.path.join(BASE, "states", "map_graph.json"),
        world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
    return p


if __name__ == "__main__":
    p = _player()
    x, y, g, n = p.g.position()
    print("pos", (x, y, g, n))
    print("connections(24,5):", rowe_rom.map_connections(24, 5))
    print("map_warps(24,5):", rowe_rom.map_warps(24, 5))
    print("world_edges[(24,5)]:", sorted(rowe_rom.world_edges().get((24, 5), set())))
    grid = Grid(p.e)
    w, h, _ = rowe_rom.map_cells(24, 5)
    reach = grid.reachable((x, y), surf=True)
    xs = [t[0] for t in reach]
    ys = [t[1] for t in reach]
    print(f"map {w}x{h} reachable {len(reach)} x[{min(xs)},{max(xs)}] y[{min(ys)},{max(ys)}]")
    print("reachable warp tiles:", sorted(t for t in reach if t in grid.warp_tiles))
    print("all warp_tiles:", sorted(grid.warp_tiles))
    for edge, sel in [("east x==w-1", [t for t in reach if t[0] == w - 1]),
                      ("west x==0", [t for t in reach if t[0] == 0]),
                      ("north y==0", [t for t in reach if t[1] == 0]),
                      ("south y==h-1", [t for t in reach if t[1] == h - 1])]:
        print(f"reachable {edge}:", sorted(sel)[:5], "count", len(sel))
