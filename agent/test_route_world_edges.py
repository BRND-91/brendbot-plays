"""Pin that route() spans world_edges union the learned graph, so the endgame block is reachable
before any map on it is walked. Red-capable: build the graph with world=None and route returns None
to every unwalked map, which is the regression (the live graph once ran that way) these guard."""
import os

import map_graph
import rowe_rom

BASE = os.path.dirname(os.path.abspath(__file__))
GRAPH = os.path.join(BASE, "states", "map_graph.json")
HM = frozenset({"SURF", "WATERFALL", "DIVE", "STRENGTH", "ROCK_SMASH", "CUT"})


def _graph():
    return map_graph.MapGraph(GRAPH, world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())


def _path(g, a, b, badges, moves=HM, limit=40):
    """The full node path route() walks from a to b, hop by hop, or an AssertionError if it dead-ends."""
    g.cur_badges = badges
    cur, seen, out = a, {a}, [a]
    for _ in range(limit):
        if cur == b:
            return out
        nxt = g.route(cur, b, field_moves=frozenset(moves))
        assert nxt is not None and nxt not in seen, f"route {a}->{b} dead-ended at {cur}: {nxt}"
        out.append(nxt)
        seen.add(nxt)
        cur = nxt
    raise AssertionError(f"route {a}->{b} did not terminate in {limit}: {out}")


def test_sevii_entry_reachable_at_8_badges():
    # the last hop into (24,23) is the (0,5) warp at tile (70,5); the planner travels this at 8 badges
    p = _path(_graph(), (0, 4), (24, 23), 8)
    assert p[-1] == (24, 23) and p[-2] == (0, 5), p


def test_e4_gauntlet_chains_end_to_end():
    p = _path(_graph(), (16, 10), (16, 11), 16)
    assert p[-1] == (16, 11) and len(p) >= 10, p


def test_league_warp_open_at_8_badges():
    # (0,8)->(24,43) is a static ROM warp with no map-connection gate, so route takes it directly at 8
    # badges. the in-game 16-badge guard is a script gate, recorded only as a learned gate once the
    # party is turned away, never a world edge, so route reads it open here. this is why the "None at
    # 8 badges" expectation does not hold against the real warp table.
    g = _graph()
    g.cur_badges = 8
    assert g.route((0, 8), (24, 43), field_moves=HM) == (24, 43)


if __name__ == "__main__":
    test_sevii_entry_reachable_at_8_badges()
    test_e4_gauntlet_chains_end_to_end()
    test_league_warp_open_at_8_badges()
    print("ROUTE WORLD-EDGES PASS", flush=True)
