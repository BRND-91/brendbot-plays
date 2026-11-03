"""Reproduce the Sootopolis underwater dive-out crossing on the frozen fixture.
Control run: attempt (24,5)->(0,51) and print where the party lands. The live log shows this
warp 'missed' to (0,7), the emerge surface, instead of warping to (0,51)."""
import os
import emu_boot as eb
import map_graph
import play
import rowe_rom

BASE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(BASE, "states", "fixtures", "sootopolis_underwater_stuck.ss")


def _player():
    e = eb.Emu()
    e.load_state(open(FIX, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-cross-probe.json")
    p.graph = map_graph.MapGraph(
        os.path.join(BASE, "states", "map_graph.json"),
        world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
    return p


if __name__ == "__main__":
    p = _player()
    print("start pos (x,y,group,num)", tuple(p.g.position()))
    print("is_underwater here", rowe_rom.is_underwater(*p.g.position()[2:]))
    print("map_warps(24,5)", rowe_rom.map_warps(24, 5))
    status, result = p._cross_to((24, 5), (0, 51))
    print("CROSS (24,5)->(0,51):", status, result, "landed", tuple(p.g.position()))
