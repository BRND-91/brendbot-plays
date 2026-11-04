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


def test_version_2_ferry_gate_reopens_at_current_cap(tmp_path):
    """A Seagallop dock->Three Island arm gated by an older executor (version 2) under the live
    8-badge field-move set must read open once EXECUTOR_CAP_VERSION advances past it, so routing
    to the Sevii islands retries the crossing instead of staying shut forever."""
    import map_graph
    dock, island = (9, 9), (0, 79)
    moves = frozenset({"CUT", "DIVE", "ROCKCLIMB", "ROCKSMASH", "SURF", "WATERFALL"})
    g = map_graph.MapGraph(str(tmp_path / "g.json"), world={dock: {island}})
    g.cur_badges = 8
    edge = (dock, island)
    g.gated[edge] = moves
    g.gate_badges[edge] = 8
    g.gate_version[edge] = 2
    assert g.route(dock, island, field_moves=moves) == island


def test_version_4_ferry_gate_reopens_at_current_cap(tmp_path):
    """A Seagallop dock->Three Island arm last shut by the version-4 executor must read open
    under the live 8-badge field-move set once EXECUTOR_CAP_VERSION advances past 4, so the
    re-armed no_row menu dump gets one more crossing attempt to fire on."""
    import map_graph
    dock, island = (13, 10), (0, 79)
    moves = frozenset({"CUT", "DIVE", "ROCKCLIMB", "ROCKSMASH", "SURF", "WATERFALL"})
    g = map_graph.MapGraph(str(tmp_path / "g.json"), world={dock: {island}})
    g.cur_badges = 8
    edge = (dock, island)
    g.gated[edge] = moves
    g.gate_badges[edge] = 8
    g.gate_version[edge] = 4
    assert g.route(dock, island, field_moves=moves) == island


def test_version_5_approach_gate_reopens_at_current_cap(tmp_path):
    """The dock-approach arm (0,1)->(9,9), last shut by the version-5 executor as a 'bounce',
    must read open under the live 8-badge field-move set once EXECUTOR_CAP_VERSION advances past
    5, so the run routes onto the Seagallop dock and the decode-fixed menu gets its crossing."""
    import map_graph
    here, dock = (0, 1), (9, 9)
    moves = frozenset({"CUT", "DIVE", "ROCKCLIMB", "ROCKSMASH", "SURF", "WATERFALL"})
    g = map_graph.MapGraph(str(tmp_path / "g.json"), world={here: {dock}})
    g.cur_badges = 8
    edge = (here, dock)
    g.gated[edge] = moves
    g.gate_badges[edge] = 8
    g.gate_version[edge] = 5
    assert g.route(here, dock, field_moves=moves) == dock


if __name__ == "__main__":
    main()
