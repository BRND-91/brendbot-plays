"""_blocked_from retires a hop the walk took and came straight back from, however many other maps
that hop connects to. A return by errand (a heal run walking back into town) leaves the hop open,
since the route map still leads on. After BOUNCE_STREAK such round trips the border is marked dead
on the graph for the session, so the next pick and any re-exec take another exit instead of the run
ending on a repeated plan. Route 120 <-> Scorched Slab ran 100 round trips on the old rule, which
blocked only a hop whose every neighbour was the map it was entered from."""
from play import BOUNCE_STREAK, Player

REGION = (0, 35, (0, 5))
HOP = (24, 73)


class _Graph:
    def __init__(self):
        self.blocked = []
        self.cur_badges = 0

    @staticmethod
    def neighbors(node):
        return {(0, 35), (24, 108)}

    def block(self, here, neighbor, field_moves=frozenset(), reason=None):
        self.blocked.append((here, neighbor))


class _G:
    @staticmethod
    def position():
        return (0, 0, 0, 35)  # only _after_cross's land-print reads it here

    @staticmethod
    def badges():
        return 8


def _player() -> Player:
    p = Player.__new__(Player)
    p.g = _G()
    p.graph = _Graph()
    p.goal = {"mode": "grind"}  # the cycle guard counts only goal-directed modes, so it stays off here
    p._blocked, p._stuck, p._bounces = {}, {}, {}
    p._last_hop, p._returned = None, False
    p.field_moves = lambda: frozenset()
    p._landing_exits = lambda: {(0, 35), (24, 108)}  # the slab's door back out plus a deeper warp
    return p


def main() -> None:
    p = _player()
    p._after_cross(REGION, HOP, ("moved", "moved"))
    assert p._last_hop == (REGION, HOP) and not p._returned
    # the return crossing: from the hop's area back over the same border
    p._after_cross((24, 73, (3, 3)), (0, 35), ("moved", "moved"))
    assert p._returned, "the walk's own return trip not recorded"
    assert HOP in p._blocked_from(REGION), "a hop w/ other neighbours survived a round trip"

    # an errand's return: the hop was taken, nothing crossed back through _after_cross
    q = _player()
    q._after_cross(REGION, HOP, ("moved", "moved"))
    assert HOP not in q._blocked_from(REGION), "a route map left by errand got retired"

    # the streak marks the border dead on the graph for the session, no run-ending exit
    r = _player()
    for _ in range(BOUNCE_STREAK):
        r._after_cross(REGION, HOP, ("moved", "moved"))
        r._after_cross((24, 73, (3, 3)), (0, 35), ("moved", "moved"))
        r._blocked_from(REGION)
    assert r.graph.blocked == [((0, 35), HOP)], f"bounce did not mark the border dead once: {r.graph.blocked}"
    print("test_bounce OK")


if __name__ == "__main__":
    main()
