import play

MOVES = frozenset({"CUT", "DIVE", "ROCKCLIMB", "ROCKSMASH", "SURF", "WATERFALL"})


class _Graph:
    cur_badges = 0

    def __init__(self, onward):
        self._onward = onward
        self.route_calls = []

    def explore_hop(self, cur, blocked=frozenset(), field_moves=frozenset()):
        return None

    def route(self, src, dst, blocked=frozenset(), field_moves=frozenset()):
        self.route_calls.append((src, dst))
        return self._onward

    def frontier_exhausted(self, field_moves=frozenset()):
        return False

    def gated_frontier(self, field_moves=frozenset()):
        return False


def _player(graph, goal, result="moved", blocked=frozenset()):
    p = play.Player.__new__(play.Player)
    p.graph = graph
    p.g = type("_G", (), {
        "position": lambda self: (1, 6, 2, 9),
        "badges": lambda self: 8,
    })()
    p.goal = goal
    p._idle = 0
    p.keep_state = False
    p.field_moves = lambda: MOVES
    p.region = lambda: (2, 9, 1, 6)
    p._blocked_from = lambda region: set(blocked)
    p._leave_dynamic_interior = lambda here, moves: False
    p.run = lambda n: None
    p.crossed = []

    def _cross_to(here, hop):
        p.crossed.append(hop)
        return ("warped", result)

    p._cross_to = _cross_to
    p._after_cross = lambda region, hop, crossed: None
    return p


def test_explore_retakes_graph_route_off_arrival_map():
    """At the Seagallop arrival map (2,9) explore_hop returns None while the frontier still reads
    open, because the open frontier sits back across the dock on the mainland. The graph route to
    the explore target (0,79) gets retaken and crossed instead of idling, whether or not a run-local
    block is present: the live wedge carried an empty blocked set."""
    g = _Graph(onward=(0, 79))
    p = _player(g, {"mode": "explore", "to": [0, 79]}, result="moved")
    p.explore_step()
    assert p.crossed == [(0, 79)]
    assert ((2, 9), (0, 79)) in g.route_calls
    assert p._idle == 0


def test_explore_retakes_with_empty_blocked():
    """The live stop logged `blocked []`: no run-local block, explore_hop None, (0,79) still routable
    off (2,9). The old guard skipped the retake whenever blocked was empty and idled to a stop; the
    retake must fire on the route alone."""
    g = _Graph(onward=(0, 79))
    p = _player(g, {"mode": "explore", "to": [0, 79]}, result="moved", blocked=set())
    p.explore_step()
    assert p.crossed == [(0, 79)]
    assert p._idle == 0


def test_explore_no_route_falls_to_idle():
    """No graph route off the map toward the target: the retake comes back None and explore_step
    idles a tick rather than crossing, so the transient-clear path and the stuck exit still run."""
    g = _Graph(onward=None)
    p = _player(g, {"mode": "explore", "to": [0, 79]})
    p.explore_step()
    assert p.crossed == []
    assert p._idle == 1


def test_explore_retake_that_does_not_move_idles():
    """A retake hop that cannot be crossed this run (an NPC in the dock doorway) returns a non-moved
    result, so explore_step crosses once then falls to the idle counter instead of re-crossing the
    same hop every tick with _idle pinned at zero."""
    g = _Graph(onward=(0, 79))
    p = _player(g, {"mode": "explore", "to": [0, 79]}, result="blocked")
    p.explore_step()
    assert p.crossed == [(0, 79)]
    assert p._idle == 1


def test_explore_target_here_does_not_retake_self():
    """Standing on the explore target with nothing open to walk locally must not route to self and
    cross in place; it idles so the next re-plan picks a new target."""
    g = _Graph(onward=(2, 9))
    p = _player(g, {"mode": "explore", "to": [2, 9]})
    p.explore_step()
    assert p.crossed == []
    assert g.route_calls == []
    assert p._idle == 1
