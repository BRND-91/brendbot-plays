"""planner.still_closed decides which recorded-closed gyms the ladder keeps skipping. A gym shut
by a lost fight reopens when the party out-levels its close baseline or gains a field move; a gym
shut because the walk could not reach it reopens when the map graph grows a route (or a new move).
A legacy coordinate-only record has no baseline and reopens on sight, so a stale close never
strands the run. closed_gyms still reports the raw record regardless of reopening."""
import json
import os
import tempfile

import planner


class _Graph:
    def __init__(self, n: int):
        self.visited = set(range(n))


def _status(level: int, moves: list, party: int = 6) -> dict:
    return {"party": [{"level": level} for _ in range(party)], "field_moves": sorted(moves)}


def _write(path: str, entries: list) -> None:
    with open(path, "w") as f:
        json.dump(entries, f)


def main() -> None:
    G = (11, 3)
    orig = planner.GYM_CLOSED
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    planner.GYM_CLOSED = path
    try:
        # a lost fight: shut at the close level, reopens once out-leveled or a new move is in the bag
        _write(path, [{"gym": list(G), "reason": "loss", "min_level": 20, "field_moves": ["SURF"], "maps": 50}])
        assert G in planner.still_closed(_status(20, ["SURF"]), _Graph(50)), "same strength stays shut"
        assert G not in planner.still_closed(_status(21, ["SURF"]), _Graph(50)), "out-leveled reopens"
        assert G not in planner.still_closed(_status(20, ["SURF", "CUT"]), _Graph(50)), "a new field move reopens"
        assert G in planner.still_closed(_status(20, ["SURF"]), _Graph(9999)), "map growth does not reopen a lost fight"

        # a reachability close: level is irrelevant, a grown map graph (new route) reopens it
        _write(path, [{"gym": list(G), "reason": "unreachable", "min_level": 20, "field_moves": ["SURF"], "maps": 50}])
        assert G in planner.still_closed(_status(99, ["SURF"]), _Graph(50)), "levels do not reopen a reachability close"
        assert G not in planner.still_closed(_status(20, ["SURF"]), _Graph(51)), "a grown graph reopens the route"
        assert G not in planner.still_closed(_status(20, ["SURF", "CUT"]), _Graph(50)), "a new field move reopens"

        # a legacy bare-coordinate record has no baseline, so it reopens immediately
        _write(path, [list(G)])
        assert G not in planner.still_closed(_status(20, ["SURF"]), _Graph(50)), "legacy entry reopens on sight"
        assert planner.closed_gyms() == {G}, "still on the raw closed record"
    finally:
        planner.GYM_CLOSED = orig
        if os.path.exists(path):
            os.remove(path)
    print("test_gym_reopen: ok")


if __name__ == "__main__":
    main()
