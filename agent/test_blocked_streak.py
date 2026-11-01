"""Player._cross_to ends the run after BLOCKED_STREAK blocked crossings of one border from one
tile. travel_toward retakes the only graph route out of a map even when this run marked it
blocked, so a crossing that stays unreachable with the player never moving (Pacifidlog's
plank islands, Route 131 at (33, 7)) otherwise loops on run(60) with no exit."""
import rowe_map
from play import Player, GoalExit, BLOCKED_STREAK

HERE, HOP = (0, 46), (0, 45)


def _player() -> Player:
    p = Player.__new__(Player)
    p.e = None
    p.graph = None
    p._blocked_streak = {}
    p.field_moves = lambda: frozenset({"SURF"})
    p._landing_rank = lambda hop, nxt, surf: None
    p.run = lambda frames, keys=0: None

    class G:
        @staticmethod
        def position():
            return (33, 7) + HERE

    class Errands:
        @staticmethod
        def cross_edge(direction, surf=False, rank=None, tools=frozenset()):
            return "unreachable"

    p.g, p.errands = G(), Errands()
    return p


def main() -> None:
    rowe_map.connections = lambda emu: [rowe_map.Connection(rowe_map.DIR_EAST, 0, *HOP)]
    p = _player()
    for n in range(BLOCKED_STREAK - 1):
        assert p._cross_to(HERE, HOP) == ("unreachable", "blocked"), f"crossing {n + 1} did not report blocked"
    try:
        p._cross_to(HERE, HOP)
    except GoalExit as g:
        assert "travel stuck" in str(g) and "(33, 7)" in str(g), f"reason names no tile: {g}"
    else:
        raise AssertionError(f"{BLOCKED_STREAK} blocked crossings from one tile never ended the run")

    # a crossing from a different tile is a new attempt, so the tally starts over
    p2 = _player()
    for _ in range(BLOCKED_STREAK - 1):
        p2._cross_to(HERE, HOP)
    p2.g.position = staticmethod(lambda: (34, 7) + HERE)
    assert p2._cross_to(HERE, HOP) == ("unreachable", "blocked"), "a new tile inherited the old tile's tally"
    print("ok")


if __name__ == "__main__":
    main()
