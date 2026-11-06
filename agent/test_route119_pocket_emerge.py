"""Emerge out of ROWE's Route 119 underwater pocket, (0,124) up to Route 119 (0,34). The party
lands on (0,124) at a no-surfacing tile, so take_dive(EMERGE) must walk to a surfaceable tile
first, and the B press it made straight after the walk fell inside the last step's tile
transition, where the game drops field input. Every candidate read back as stuck, the gate sealed
the pocket's only exit, and the heal trek to Fortree exited "travel stuck" until the supervisor
stopped the grind.

Fixture states/fixtures/route119_underwater_pocket.ss is the frozen live save at (0,125) (13,14).
"""
import os

import emu_boot as eb
import map_graph
import play
import rowe_rom

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "route119_underwater_pocket.ss")


def _player() -> play.Player:
    e = eb.Emu()
    e.load_state(open(FIXTURE, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-route119-pocket-test.json")
    p.graph = map_graph.MapGraph(
        "/tmp/rowe-route119-pocket-graph.json",
        world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
    return p


def test_emerge_after_a_walk_surfaces_to_route_119():
    p = _player()
    p._cross_to((0, 125), (0, 124))
    assert tuple(p.g.position()[2:]) == (0, 124), "warp (0,125)->(0,124) failed"
    status, _ = p._cross_to((0, 124), (0, 34))
    assert tuple(p.g.position()[2:]) == (0, 34), (
        f"emerge (0,124)->(0,34) did not surface, status {status} at {tuple(p.g.position())}; "
        "a B press made before the walk's last step finishes is dropped")
