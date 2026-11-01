"""demote_to_grind must grind toward a map the walk can physically reach, not one the map graph
lists as a neighbour. The surf pocket east of Slateport enters map 1,31 and reaches only the border
back to 0,25, yet 1,31's adjacency also names 0,26, a grass map the grid cannot walk to; grinding
toward it travel-stalls every step and loops the run. _reachable_grass_map seeds on the live grid's
reachable borders so the pick is always crossable."""
from play import Player


class _Graph:
    def __init__(self):
        self.gated = {}
        self._adj = {(1, 31): {(0, 26)}}  # map adjacency names 0,26, a grass map the grid cannot reach

    def neighbors(self, node):
        return self._adj.get(node, set())


def _player(reachable):
    p = Player.__new__(Player)
    p.graph = _Graph()
    p.field_moves = lambda: frozenset()
    p._landing_exits = lambda: set(reachable)  # the borders the live grid reaches from where it stands
    return p


def main():
    # only 0,25 is physically reachable, so the grind targets it, never the adjacency-only 0,26
    p = _player({(0, 25)})
    got = p._reachable_grass_map((1, 31))
    assert got == (0, 25), f"grind target must be the physically reachable grass, got {got}"

    # no border the grid reaches: the search returns None so the caller holds the grind in place
    # rather than target a map adjacency lists but the walk cannot cross
    none = _player(set())._reachable_grass_map((1, 31))
    assert none is None, none
    print("test_grind_target OK")


if __name__ == "__main__":
    main()
