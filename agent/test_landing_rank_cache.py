"""Ranking a map's border tiles for a crossing walked the landing region once per tile and per
neighbour, 2.1s over Lilycove's 242 edge tiles on this fixture and up to 3s on Route 121, twice per
crossing, with the frame frozen the whole time (live STALL traces end in nav.region under
routines.rank). One region walk per area labels every tile in it, so the same pass runs in well
under half a second and scores the same seven classes."""
import os
import time

import emu_boot as eb
import play
import rowe_symbols as S
from routines import landing_rank

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "lilycove.ss")


def test_edge_rank_runs_one_region_walk_per_area():
    e = eb.Emu()
    e.load_state(open(FIXTURE, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-rank-test.json")
    p.run(10)
    grid = p._grid()
    w, h = grid.width - 2 * S.MAP_OFFSET, grid.height - 2 * S.MAP_OFFSET
    assert (w, h) == (81, 40), (w, h)
    rank, _, _ = landing_rank(p.g.position()[2:], None, "SURF" in p.field_moves())
    tiles = ([(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
             + [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)])
    t0 = time.monotonic()
    scores = [rank(tl) for tl in tiles]
    took = time.monotonic() - t0
    assert len(set(scores)) == 7, sorted(set(scores))
    assert took < 0.5, f"{len(tiles)} edge tiles ranked in {took:.2f}s, the per-tile region walk is back"
