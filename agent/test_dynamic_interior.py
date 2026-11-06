"""A party saved inside a map whose only warps are dynamic return doors (map [13,22], a building the
phantom (127,127) edge once re-entered forever) has no world edge out, so travel and explore find no
hop. Instead of travel-sticking every run, the executor steps through the dynamic return door to drop
back onto the entrance map. _leave_dynamic_interior fires only when such a door is present and the
step changed the map, and travel_toward takes it rather than raising the stuck exit."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import play  # noqa: E402
import rowe_map  # noqa: E402
import rowe_symbols as S  # noqa: E402


class _Warp:
    def __init__(self, x, y, dg, dn):
        self.x, self.y, self.dest_group, self.dest_num = x, y, dg, dn


class _G:
    @staticmethod
    def position():
        return (1, 5, 13, 22)

    @staticmethod
    def badges():
        return 8


class _Errands:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def take_warp(self, dest, surf=False, rank=None, tools=frozenset()):
        self.calls.append(dest)
        return self.result


class _Graph:
    def __init__(self):
        self.cur_badges = 0
        self.world = {}

    def route(self, *a, **k):
        return None

    def explore_hop(self, *a, **k):
        return None


def _player(result):
    p = play.Player.__new__(play.Player)
    p.e = object()
    p.g = _G()
    p.errands = _Errands(result)
    p.field_moves = lambda: frozenset()
    return p


DYNAMIC = [_Warp(1, 5, 127, 127), _Warp(2, 5, 127, 127)]
CONCRETE = [_Warp(1, 5, 0, 20)]


def main() -> None:
    orig = rowe_map.warps
    try:
        # a dynamic return door is present and the step changed the map: left the building
        rowe_map.warps = lambda e: DYNAMIC
        p = _player("map_changed")
        assert p._leave_dynamic_interior((13, 22), frozenset()) is True
        assert p.errands.calls == [S.MAP_DYNAMIC], p.errands.calls

        # the step could not reach the door: did not leave
        p2 = _player("stuck")
        assert p2._leave_dynamic_interior((13, 22), frozenset()) is False

        # a concrete exit warp is a real graph edge, so the escape never fires and routing handles it
        rowe_map.warps = lambda e: CONCRETE
        p3 = _player("map_changed")
        assert p3._leave_dynamic_interior((13, 22), frozenset()) is False
        assert p3.errands.calls == [], p3.errands.calls

        # travel_toward with no route out of a dynamic-only map takes the door instead of raising
        rowe_map.warps = lambda e: DYNAMIC
        pt = _player("map_changed")
        pt._gyms = set()
        pt._last_hop = None
        pt.graph = _Graph()
        pt.goal = {"mode": "travel", "to": [0, 79]}
        pt.region = lambda: (1, 5, (13, 22))
        pt._blocked_from = lambda r: set()
        pt.travel_toward((0, 79))  # raises GoalExit if the escape is not wired
        assert pt.errands.calls == [S.MAP_DYNAMIC], pt.errands.calls
    finally:
        rowe_map.warps = orig
    print("DYNAMIC INTERIOR PASS", flush=True)


if __name__ == "__main__":
    main()
