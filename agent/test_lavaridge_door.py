"""The Lavaridge nurse-stand interior (4,5) has three warps to town (0,12): a front mat (dest_warp 3,
two tiles) that lands on a door pad (9,6), and a hot-spring back door (dest_warp 5) that lands in a
dead-end pocket (9,2). The door pad reads blocked, so ranking the pad tile itself scored the front
mat (2,0) and the walk took the pocket door, which reaches nothing toward the route, and bounced
(4,5)<->(0,12) until the budget ran out. The ranker must score the tile the player steps off the pad
onto, so the front mat outranks the pocket and take_warp crosses to the town side that reaches the
(0,27) route toward gym [2,8]."""
import os
import shutil

import emu_boot as eb
import play
import rowe_map
import rowe_rom
from nav import Grid

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "lavaridge_nurse_4_5.ss")
FRONT_PAD = (9, 6)     # dest_warp 3 lands here on (0,12); a door-pad metatile that reads blocked
FRONT_STEP = (9, 7)    # the walkable tile the player steps off the pad onto
BACK_POCKET = (9, 2)   # dest_warp 5 lands here; a dead-end pocket
ONWARD = (0, 27)       # the connection (0,12) must reach toward gym [2,8]


def _player():
    work = "/tmp/rowe-lav-nurse.ss"
    shutil.copy(FIXTURE, work)
    e = eb.Emu()
    e.load_state(open(work, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-lav-nurse.json")
    return e, p


def _town_grid():
    cells = rowe_rom.map_cells(0, 12)
    g = Grid.from_cells(*cells)
    g._behavior = rowe_rom.metatile_behavior(0, 12)
    return g, cells[0], cells[1]


def _onward_targets(w, h):
    rows = {rowe_map.DIR_NORTH: [(x, 0) for x in range(w)], rowe_map.DIR_SOUTH: [(x, h - 1) for x in range(w)],
            rowe_map.DIR_WEST: [(0, y) for y in range(h)], rowe_map.DIR_EAST: [(w - 1, y) for y in range(h)]}
    targets = set()
    for d, dest in rowe_rom.map_connections(0, 12):
        if dest == ONWARD:
            targets.update(rows.get(d, []))
    return targets


def test_front_mat_outranks_hotspring_pocket():
    e, p = _player()
    assert tuple(p.g.position()[2:]) == (4, 5), "fixture is not the (4,5) nurse stand"
    rank, _, _ = p._landing_rank((0, 12), ONWARD, surf=False)
    front = rank(FRONT_PAD)
    back = rank(BACK_POCKET)
    # class 0 means the landing reaches the (0,27) crossing; the front mat does once the ranker
    # steps off the blocked pad, the pocket never does
    assert front[0] == 0, f"front mat must reach the {ONWARD} route, got {front}"
    assert back[0] == 1, f"hot-spring door is a dead-end pocket, got {back}"
    assert front < back, f"front mat {front} must outrank the pocket {back}"


def test_take_warp_crosses_to_the_route_side():
    e, p = _player()
    rank, _, _ = p._landing_rank((0, 12), ONWARD, surf=False)
    dest_warps = rowe_rom.map_warps(0, 12)

    def warp_rank(wp):
        return rank(dest_warps[wp.dest_warp][:2]) if wp.dest_warp < len(dest_warps) else (2, 0)

    status = p.errands.take_warp((0, 12), rank=warp_rank, tools=frozenset(p.field_moves()))
    assert status == "map_changed", f"take_warp did not cross, got {status!r}"
    assert tuple(p.g.position()[2:]) == (0, 12), f"did not land on town (0,12), at {p.g.position()}"
    g, w, h = _town_grid()
    reach = g.reachable(p.g.position()[:2], False)
    assert _onward_targets(w, h) & reach, "crossed into the dead-end pocket, not the route side"


def test_hotspring_pocket_is_walled_from_the_front_door():
    # the pocket is genuinely separate from the front-door region, so a bogus merge is not what made
    # the two doors rank alike; the trap was the blocked-pad rank, not a pocket reaching town
    g, _, _ = _town_grid()
    assert FRONT_STEP not in g.reachable(BACK_POCKET, False), "the hot-spring pocket reaches the front door"
