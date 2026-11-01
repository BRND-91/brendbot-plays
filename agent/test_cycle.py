"""_after_cross ends a goal-directed run that loops across three or more maps without finding a
new one, the cycle the 2-map _last_hop bounce never names (Slateport <-> the water east <-> back).
A crossing that turns up a new map keeps the run going, and grind heals bounce a center against a
route on purpose, so the guard counts only non-grind modes."""
import collections

from play import CYCLE_WINDOW, GoalExit, Player

LOOP = [(29, 0), (0, 25), (1, 31)]  # Slateport, the water east, the dead-end past it


class _Graph:
    def __init__(self):
        self.visited = set()

    def neighbors(self, node):
        return set()


class _Emu:
    def __init__(self):
        self.map = (29, 0)

    def position(self):
        return (5, 5) + self.map


def _player(mode="explore") -> Player:
    p = Player.__new__(Player)
    p.graph = _Graph()
    p.g = _Emu()
    p.goal = {"mode": mode}
    p.keep_state = False
    p._blocked, p._stuck, p._bounces = {}, {}, {}
    p._last_hop, p._returned = None, False
    p._visit_log = collections.deque(maxlen=CYCLE_WINDOW)
    p._landing_exits = lambda: {(1, 1), (2, 2)}  # not a dead end, so only the cycle guard can fire
    return p


def _land(p, mapid, grow_at=None) -> None:
    if grow_at is not None:
        p.graph.visited.add(("new", grow_at))  # a freshly discovered map grows maps-seen
    p.g.map = mapid
    p._after_cross((0, 0, (0, 0)), mapid, ("moved", "moved"))


def main() -> None:
    # a 3-map loop that discovers nothing new ends the run once one map recurs CYCLE_HITS times
    p = _player()
    p.graph.visited.update(LOOP)  # all three already seen, maps-seen never grows
    for i in range(CYCLE_WINDOW + 1):
        try:
            _land(p, LOOP[i % 3])
        except GoalExit as g:
            assert "cycle" in str(g) and p.keep_state, g
            assert i == CYCLE_WINDOW, f"fired at crossing {i}, not once the window filled"
            break
    else:
        raise AssertionError("a no-progress 3-map loop never ended the run")

    # the same loop while a new map turns up each crossing keeps going
    q = _player()
    for i in range(CYCLE_WINDOW * 3):
        _land(q, LOOP[i % 3], grow_at=i)
    assert not q.keep_state, "a loop that kept finding new maps was cut short"

    # grind heals bounce a center against a route on purpose, so the guard stays off
    r = _player(mode="grind")
    r.graph.visited.update(LOOP[:2])
    for i in range(CYCLE_WINDOW * 3):
        _land(r, LOOP[i % 2])
    assert not r.keep_state, "the cycle guard fired in grind mode"
    print("test_cycle OK")


if __name__ == "__main__":
    main()
