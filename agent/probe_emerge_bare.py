"""Isolate what an emerge (a bare B press) from the seabed (0,51) actually does, apart from the
candidate walk. The party reaches (0,51) only by warping down from Sootopolis (24,5), which sets
the dynamic dive-return warp, so a B press may surface back to (24,5) regardless of the static
EMERGE connection to (0,41). Three fresh loads: B at the landing tile, B at a far tile, and the
east-border swim to (0,52). Reads the fixture, writes only the /tmp ledger.
"""
import os

import emu_boot as eb
import map_graph
import play
import rowe_rom

BASE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(BASE, "states", "fixtures", "sootopolis_underwater_stuck.ss")


def _on_51():
    e = eb.Emu()
    e.load_state(open(FIX, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-emerge-bare.json")
    p.graph = map_graph.MapGraph(
        os.path.join(BASE, "states", "map_graph.json"),
        world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
    p._cross_to((24, 5), (0, 51))
    return p


def bare_b(p):
    before = tuple(p.g.position())
    p.run(24, eb.KEY_B)
    p.run(120, 0)
    return before, tuple(p.g.position())


if __name__ == "__main__":
    p = _on_51()
    print("trial 1 bare B at landing:", bare_b(p))

    p = _on_51()
    tgt = (45, 74)
    r = p.nav.walk_to(tgt, surf=True, tools=p.field_moves())
    print(f"trial 2 walk to {tgt}: {r} at {tuple(p.g.position())}")
    if tuple(p.g.position())[2:] == (0, 51):
        print("trial 2 bare B at far tile:", bare_b(p))

    p = _on_51()
    st, res = p._cross_to((0, 51), (0, 52))
    print("trial 3 cross (0,51)->(0,52):", st, res, "landed", tuple(p.g.position()))
