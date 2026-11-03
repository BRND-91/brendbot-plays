"""Checks the learned map graph: adjacency from observations, routing first-hop,
exploration toward unseen maps, frontier-exhaustion detection, and reload."""
import os
import tempfile

from map_graph import MapGraph

A, B, C, D = (0, 16), (0, 10), (0, 17), (0, 30)


def main() -> None:
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)
    try:
        g = MapGraph(path)

        # a fresh graph has nowhere mapped, so exploration still has a target
        assert g.frontier_exhausted() is False

        new = g.observe(A, [B])
        assert set(new) == {A, B}, new
        assert g.visited == {A}, g.visited
        assert g.route(A, B) == B, "direct border is its own first hop"
        assert g.route(A, C) is None, "C is unknown until a neighbour names it"

        g.observe(B, [A, C])
        assert g.route(A, C) == B, "A->B->C routes through B"
        assert g.explore_hop(A) == B, "B is the hop toward the unseen C behind it"

        g.observe(C, [B, D])
        assert g.frontier_exhausted() is False, "D is named but unwalked"
        assert g.explore_hop(C) == D, "D is a direct unseen border of C"

        g.observe(D, [C])
        assert g.frontier_exhausted() is True, "every named map has been walked"
        assert g.explore_hop(A) is None, "nothing left to uncover"

        # A-B-C-D in a line: from C the nearest of {A, D} is D at one hop, A sits two away
        assert g.nearest(C, {A, D}) == D, "one hop beats two"
        assert g.nearest(C, {A, D}, blocked={D}) == A, "a blocked first hop falls back to the next town"
        assert g.nearest(B, {B, D}) == B, "standing in a town is zero hops"
        assert g.nearest(A, {(9, 9)}) is None, "an unknown town is unreachable"

        # a gate carries the badge count that recorded it: the edge is shut at that count and
        # retried once the count climbs, so a door blocked at 8 badges reopens at 16 with no
        # field-move change, which the field-move-only key left shut forever
        g.cur_badges = 8
        g.block(A, B, frozenset())
        assert g.route(A, B, field_moves=frozenset()) is None, "edge shut at its writing badge count"
        g.cur_badges = 16
        assert g.route(A, B, field_moves=frozenset()) == B, "edge retried once the badge count climbs"
        g.cur_badges = 8
        assert g.route(A, B, field_moves=frozenset()) is None, "and shut again back at the writing count"

        reloaded = MapGraph(path)
        assert reloaded.visited == g.visited, reloaded.visited
        assert reloaded.adj == g.adj, reloaded.adj
        assert reloaded.gate_badges.get((A, B)) == 8, reloaded.gate_badges
    finally:
        if os.path.exists(path):
            os.remove(path)
    print("ok")


if __name__ == "__main__":
    main()
