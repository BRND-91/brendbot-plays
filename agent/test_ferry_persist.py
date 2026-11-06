"""A Seagallop ferry arm's passability is the talk_warp menu drive, so a drive that missed is a
driver miss the next run retries, never a dead edge. _persist_blocked used to funnel that miss into
graph.block (stuck tally or an "unreachable" border read), which gated the arm and made route return
None, so the 18 ferry arms had to be hand-unblocked every run they re-poisoned. The arm stays routable
on any miss; only a row drawn locked (island not open yet) is a real gate. Red-capable against the
exemption: drop it and case A gates (13,10)->(0,79) after STUCK_GATE stuck reports and route goes None.
"""
import os
import tempfile

import map_graph
from play import STUCK_GATE, Player

FERRY = ((13, 10), (0, 79))  # Slateport dock -> Three Island, a Seagallop arm (seagallop_label != None)
LAND = ((0, 25), (0, 33))    # an ordinary overworld border, not a ferry arm


def _graph(tmp: str) -> map_graph.MapGraph:
    g = map_graph.MapGraph(tmp)  # no file at tmp yet, so load() leaves it empty
    g.adj = {
        (13, 10): {(0, 79), (9, 9)},
        (0, 79): {(13, 10)},  # reachable only across the ferry arm, so a gate on it strands (0,79)
        (9, 9): {(13, 10)},
        (0, 25): {(0, 33)},
        (0, 33): {(0, 25)},
    }
    g.cur_badges = 0
    return g


def _player(g: map_graph.MapGraph) -> Player:
    p = Player.__new__(Player)
    p.graph = g
    p._stuck_hits = {}  # no _stuck_hits_path set, so _save_stuck_hits is a no-op, no disk write
    p.field_moves = lambda: frozenset()
    return p


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "g.json")

        # A: every non-locked drive miss leaves the arm routable
        for status in ["stuck", "stuck", "stuck", "unreachable", "wrong_map", "no_menu"]:
            p = _player(_graph(path))
            for _ in range(STUCK_GATE + 1):
                p._persist_blocked(*FERRY, status)
            assert p.graph.route(*FERRY) == (0, 79), \
                f"ferry arm gated on {status!r}, route {p.graph.route(*FERRY)}"

        # B: a row drawn locked is a real gate and still strands the island
        p = _player(_graph(path))
        p._persist_blocked(*FERRY, "locked")
        assert p.graph.route(*FERRY) is None, "locked ferry row did not gate the arm"

        # C: the exemption is scoped to ferry arms; an ordinary border still gates after STUCK_GATE
        p = _player(_graph(path))
        for _ in range(STUCK_GATE):
            p._persist_blocked(*LAND, "stuck")
        assert p.graph.route(*LAND) is None, "ordinary border no longer gates on a stuck tally"

    print("test_ferry_persist OK")


if __name__ == "__main__":
    main()
