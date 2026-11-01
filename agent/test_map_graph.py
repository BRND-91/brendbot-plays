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

        reloaded = MapGraph(path)
        assert reloaded.visited == g.visited, reloaded.visited
        assert reloaded.adj == g.adj, reloaded.adj
    finally:
        if os.path.exists(path):
            os.remove(path)
    print("ok")


if __name__ == "__main__":
    main()
