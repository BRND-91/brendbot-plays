import os
import tempfile

import map_graph
import play

MOVES = frozenset({"CUT", "DIVE", "ROCKCLIMB", "ROCKSMASH", "SURF", "WATERFALL"})


def _graph():
    path = os.path.join(tempfile.mkdtemp(), "map_graph.json")
    g = map_graph.MapGraph(path)
    # (0,79) was reached and its only ROM map-edge connection is the back-edge to (0,77);
    # the onward Sevii map (0,80) is warp-linked, so it is absent from adj until observed.
    g.observe((0, 77), [(0, 79)])
    g.observe((0, 79), [(0, 77)])
    return g


def _player(graph, exits):
    p = play.Player.__new__(play.Player)
    p.graph = graph
    p.g = type("_G", (), {"position": lambda self: (12, 0, 0, 79)})()
    p.goal = {"mode": "grind", "to": [0, 79]}
    p._last_hop = None
    p._blocked = {}
    p._landing_exits = lambda: set(exits)
    return p


def test_after_cross_observes_warp_linked_onward_map():
    """Landing on (0,79) whose live exits include the warp-only onward map (0,80): before the
    _after_cross observe call the planner cannot see (0,80) and explore_hop off (0,79) with the
    back-edge blocked finds nothing; after it, (0,80) is a real border and gets returned."""
    g = _graph()
    assert (0, 80) not in g.adj.get((0, 79), set())
    assert g.explore_hop((0, 79), blocked={(0, 77)}, field_moves=MOVES) is None

    p = _player(g, {(0, 77), (0, 80)})
    p._after_cross((2, 9, 1, 6), (0, 79), ("warped", "moved"))

    assert (0, 80) in g.adj[(0, 79)]
    assert g.explore_hop((0, 79), blocked={(0, 77)}, field_moves=MOVES) == (0, 80)
    print("OBSERVE LANDING EXITS PASS")


def test_observe_here_folds_warp_linked_exit_of_stood_on_map():
    """The party stands on the Three Island arrival map (2,9), which has no ROM edge-connection
    and whose only link is the sailor-door warp back to (0,77). Observing connections alone (the
    old overworld_step) leaves adj[(2,9)] empty, so sevii_goal's empty-adj frontier test picks
    (2,9) as an unmapped onward map and the goal degenerates to explore-to-self. _observe_here
    folds the live landing exits (warps included) so the back-edge enters adj and (2,9) stops
    reading as a frontier."""
    path = os.path.join(tempfile.mkdtemp(), "map_graph.json")
    g = map_graph.MapGraph(path)
    g.observe((0, 77), [(2, 9)])            # the link was only ever seen from the (0,77) side
    assert g.adj.get((2, 9), set()) == set()  # the live wedge: (2,9) empty

    p = play.Player.__new__(play.Player)
    p.graph = g
    p.g = type("_G", (), {"position": lambda self: (1, 6, 2, 9)})()
    p._last_obs = None
    p._landing_exits = lambda: {(0, 77)}   # the only reachable warp dest off (2,9)

    p._observe_here((2, 9))

    assert (0, 77) in g.adj[(2, 9)]        # no longer empty -> no longer a false frontier
    print("OBSERVE HERE PASS")


if __name__ == "__main__":
    test_after_cross_observes_warp_linked_onward_map()
    test_observe_here_folds_warp_linked_exit_of_stood_on_map()
