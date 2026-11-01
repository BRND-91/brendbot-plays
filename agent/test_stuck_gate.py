"""Player._persist_blocked gates a border the walk cannot cross. An "unreachable" edge
(no passable tile) gates on the first failure; a "stuck" edge (a warp the walk reaches
but never clears) gates only after STUCK_GATE repeats, since the per-battle _stuck clear
wipes its run record. A gate is keyed by the field-move set, so a new tool reopens it."""
import os
import tempfile

from map_graph import MapGraph
from play import Player, STUCK_GATE

A, WARP = (0, 18), (24, 106)
FM = frozenset({"SURF"})


def _player(graph: MapGraph) -> Player:
    p = Player.__new__(Player)
    p.graph = graph
    p._stuck_hits = {}
    p.field_moves = lambda: FM
    return p


def main() -> None:
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)
    try:
        g = MapGraph(path)
        g.observe(A, [WARP])
        assert g.explore_hop(A, field_moves=FM) == WARP, "the warp is the only open border"
        assert g.frontier_exhausted(FM) is False

        p = _player(g)
        for n in range(STUCK_GATE - 1):
            p._persist_blocked(A, WARP, "stuck")
            assert g.explore_hop(A, field_moves=FM) == WARP, f"still open after {n + 1} stuck hits"
        p._persist_blocked(A, WARP, "stuck")
        assert g.explore_hop(A, field_moves=FM) is None, "gated after STUCK_GATE stuck hits"
        assert g.frontier_exhausted(FM) is True, "no open border left, so the run demotes to a grind"

        # a different field-move set is a new capability, so the gate does not apply
        assert g.explore_hop(A, field_moves=frozenset({"SURF", "CUT"})) == WARP, "a new tool reopens it"

        # an unreachable edge gates on the first failure only when the ROM layout has no tile
        # to stand on along that border; unreachable from where the player happens to stand
        # (a map split by water or a ledge) is a stuck hit, since another region reaches it
        g2 = MapGraph(path + ".2")
        g2.observe(A, [WARP])
        p2 = _player(g2)
        p2._border_open = lambda here, hop: False
        p2._persist_blocked(A, WARP, "unreachable")
        assert g2.explore_hop(A, field_moves=FM) is None, "a closed border gates immediately"
        g2b = MapGraph(path + ".2b")
        g2b.observe(A, [WARP])
        p2b = _player(g2b)
        p2b._border_open = lambda here, hop: True
        p2b._persist_blocked(A, WARP, "unreachable")
        assert g2b.explore_hop(A, field_moves=FM) == WARP, "an open border unreachable from one region is not gated"
        for _ in range(STUCK_GATE):
            p2b._persist_blocked(A, WARP, "unreachable")
        assert not p2b._stuck_hits and g2b.explore_hop(A, field_moves=FM) == WARP, "region misses tallied toward the gate"
        # a warp hop is closed when every warp tile to it is solid rock w/ no door behavior
        # (Route 110's wall warp at (45, 6)), open when a warp sits on a door or cave-mouth tile
        p2c = _player(MapGraph(path + ".2c"))
        assert p2c._border_open(A, WARP) is False, "the wall warp into (24, 106) reads open"
        assert p2c._border_open((0, 19), (24, 11)) is True, "the cave mouths into (24, 11) read closed"

        # a gated border is not a corridor: a frontier reachable only through it stays
        # unreachable, so neither explore nor route may hand back the gate as the hop
        beyond = (24, 200)
        g3 = MapGraph(path + ".3")
        g3.observe(A, [WARP])
        g3.observe(WARP, [A, beyond])  # WARP walked, a further border still unseen behind it
        p3 = _player(g3)
        for _ in range(STUCK_GATE):
            p3._persist_blocked(A, WARP, "stuck")
        assert g3.explore_hop(A, field_moves=FM) is None, "explore threaded a gated border to the map behind it"
        assert g3.route(A, beyond, field_moves=FM) is None, "route threaded a gated border"
        assert g3.route(A, beyond) == WARP, "with no field-move context the gate does not apply"

        # cross-run persistence: play.py re-execs per grind run, so one stuck per run must still
        # reach the gate. Each run is a fresh Player loading the same stuck_hits.json; the warp
        # gates on the STUCK_GATE-th run, not never.
        hits = path + ".hits"
        for n in range(STUCK_GATE):
            g4 = MapGraph(path + ".4")
            g4.observe(A, [WARP])
            p4 = Player.__new__(Player)
            p4.graph = g4
            p4.field_moves = lambda: FM
            p4._stuck_hits = p4._load_stuck_hits(hits)  # the prior runs' tally, off disk
            p4._persist_blocked(A, WARP, "stuck")        # one stuck this run
            gated = g4.explore_hop(A, field_moves=FM) is None
            assert gated == (n == STUCK_GATE - 1), f"run {n + 1}: gated={gated}"
    finally:
        for pth in (path, path + ".2", path + ".2b", path + ".2c", path + ".3", path + ".4", path + ".hits"):
            if os.path.exists(pth):
                os.remove(pth)
    print("test_stuck_gate: ok")


if __name__ == "__main__":
    main()
