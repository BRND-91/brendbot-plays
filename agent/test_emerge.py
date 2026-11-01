"""The third Sootopolis escape crossing, emerge from Underwater Route 126 (0,51) up to Route 126
(0,41). Emerge is a yes/no dialogue ("Light is filtering down from above. Would you like to
surface?"), so the pre-fix take_dive(EMERGE) that pressed B once left the prompt open and read back
as stuck at (0,51). The crossing test lands on (0,51) by the dive-tunnel warp, then asserts the
emerge reaches (0,41); the pre-fix single-B walk fails it (stuck on (0,51)) and the B-then-A path
passes. emerge_tiles must drop the back-warp tile (45,65) and the no-surfacing behaviours.

Fixture states/fixtures/sootopolis_underwater_stuck.ss is the frozen live save at (24,5).
"""
import os

import emu_boot as eb
import map_graph
import play
import rowe_rom
from nav import Grid, NO_SURFACE_BEHAVIORS

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "sootopolis_underwater_stuck.ss")
MASK = 0x0FFF
BACK_WARP = (45, 65)  # (0,51) tile that warps back to (24,5)


def _player() -> play.Player:
    e = eb.Emu()
    e.load_state(open(FIXTURE, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-emerge-test.json")
    p.graph = map_graph.MapGraph(
        os.path.join(BASE, "states", "map_graph.json"),
        world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
    return p


def test_emerge_crossing_surfaces_to_route_126():
    p = _player()
    p._cross_to((24, 5), (0, 51))
    assert tuple(p.g.position()[2:]) == (0, 51), "dive-tunnel warp to (0,51) failed"
    status, _ = p._cross_to((0, 51), (0, 41))
    assert tuple(p.g.position()[2:]) == (0, 41), (
        f"emerge (0,51)->(0,41) did not surface, status {status} at {tuple(p.g.position())}; "
        "a single-B press opens the surface prompt and never answers YES")


def test_emerge_opens_a_route_out_of_sootopolis():
    p = _player()
    p._cross_to((24, 5), (0, 51))
    p._cross_to((0, 51), (0, 41))
    assert p.graph.route((0, 41), (0, 8)) is not None, "no route from Route 126 to Ever Grande (0,8)"


def test_emerge_tiles_drop_backwarp_and_no_surfacing():
    p = _player()
    p._cross_to((24, 5), (0, 51))
    g = Grid(p.e)
    x, y, *_ = p.g.position()
    tiles = g.emerge_tiles((x, y), surf=True)
    assert (x, y) in tiles, "the surfaceable landing tile was dropped from the candidate set"
    assert BACK_WARP not in tiles, "the back-warp tile survived as an emerge candidate"
    assert all(g._behavior(g.cell(*t) & MASK) not in NO_SURFACE_BEHAVIORS for t in tiles), (
        "a no-surfacing behaviour survived in the candidate set")
