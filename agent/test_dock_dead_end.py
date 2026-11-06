"""A landing whose only walkable exit is the map it came from is a dead end unless the graph carries a
ferry arm off it. The Slateport harbor (9,9) lands w/ exits {(0,1)} and eight Seagallop arms; blocking
it from Slateport as a dead end cut the only route back to Six Island, and the gym run bounced
(0,1)<->(0,25)<->(0,24) for the rest of the budget."""
import collections

import play

SLATEPORT, HARBOR, SIX_ISLAND, GYM = (0, 1), (9, 9), (1, 58), (2, 12)
SLATEPORT_REGION = SLATEPORT + (2, 22)
POND, PETALBURG = (0, 17), (0, 0)
POND_REGION = POND + (3, 3)


class _Graph:
    def __init__(self, arms: set):
        self.visited = set()
        self.arms = arms

    def neighbors(self, node: tuple) -> set:
        return set(self.arms)

    def observe(self, here: tuple, neighbors: list) -> list:
        return []


def _player(landed: tuple, exits: set, graph) -> play.Player:
    p = play.Player.__new__(play.Player)
    p.g = type("G", (), {"position": staticmethod(lambda: (0, 0) + landed)})()
    p.graph = graph
    p.goal = {"mode": "gym"}
    p._blocked, p._bounced, p._stuck = {}, {}, {}
    p._last_hop, p._last_hop_dest, p._returned = None, None, False
    p._visit_log = collections.deque(maxlen=play.CYCLE_WINDOW)
    p._landing_exits = lambda: exits
    return p


def test_harbor_with_ferry_arms_is_not_a_dead_end():
    p = _player(HARBOR, {SLATEPORT}, _Graph({SLATEPORT, SIX_ISLAND}))
    p._after_cross(SLATEPORT_REGION, HARBOR, ("map_changed", "moved"), dest=GYM)
    assert HARBOR not in p._blocked.get(SLATEPORT_REGION, set()), "a dock w/ a ferry arm stays routable"


def test_pond_corner_is_still_a_dead_end():
    p = _player(PETALBURG, {POND}, _Graph({POND}))
    p._after_cross(POND_REGION, PETALBURG, ("map_changed", "moved"), dest=GYM)
    assert PETALBURG in p._blocked[POND_REGION], "a landing w/ no way on but back is blocked from its origin"
