"""The map just left is blocked as the next first hop only when that hop served the same travel
dest. After a heal detour (Slateport harbor (9,9) -> Slateport (0,1), dest the service town) the gym
route back out through (9,9) was blocked, so the walk left by Route 110 and came back round
(states/grind.log: "hop: [0, 1] region [2, 22] -> dest [2, 8]: route [0, 25] onward [0, 1], blocked
[[9, 9]]"). The Mt. Ember summit chain, one dest throughout, keeps its forward walk."""
import play

MOVES = frozenset({"SURF"})
HARBOR, TOWN, GYM, ROUTE110 = (9, 9), (0, 1), (2, 8), (0, 25)


class _Graph:
    gate_reason = {}
    cur_badges = 9

    def route(self, src, dst, blocked=frozenset(), field_moves=frozenset()):
        return ROUTE110 if HARBOR in blocked else HARBOR

    def explore_hop(self, cur, blocked=frozenset(), field_moves=frozenset()):
        return None

    def passable(self, node, blocked=frozenset(), field_moves=frozenset()):
        return set()


def _player(last_hop_dest):
    p = play.Player.__new__(play.Player)
    p.graph = _Graph()
    p.g = type("_G", (), {"position": lambda self: (19, 20, 0, 1), "badges": lambda self: 9})()
    p.goal = {"mode": "gym", "map": list(GYM)}
    p._gyms = set()
    p.field_moves = lambda: MOVES
    p._climb = lambda: False
    p.region = lambda: (0, 1, 2, 22)
    p._blocked_from = lambda region: set()
    p._bounced = {}
    p._last_hop = ((9, 9, 0, 4), TOWN)   # the crossing that landed here came from the harbor
    p._last_hop_dest = last_hop_dest
    p.crossed = []
    p._cross_to = lambda here, hop, nxt=None: (p.crossed.append(hop), ("warped", "moved"))[1]
    p._after_cross = lambda region, hop, crossed, dest=None: None
    return p


def test_hop_that_ended_a_detour_does_not_block_the_way_back():
    p = _player(last_hop_dest=TOWN)
    p.travel_toward(GYM)
    assert p.crossed == [HARBOR], p.crossed


def test_hop_toward_the_same_dest_still_walks_the_chain_forward():
    p = _player(last_hop_dest=GYM)
    p.travel_toward(GYM)
    assert p.crossed == [ROUTE110], p.crossed
