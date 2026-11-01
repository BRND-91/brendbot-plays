"""hold_stale decides when a capless hold-grind yields for an in-process re-plan: it holds while
the frontier is unchanged inside the battle window and yields once a map, a border, a field move,
or HOLD_REPLAN_BATTLES wild battles arrive. The never-exit bug it replaces is hold_stale pinned to
False, which the True cases below catch."""
import play


class _G:
    def __init__(self, visited, adj):
        self.visited = set(visited)
        self.adj = dict(adj)


def main() -> None:
    moves = frozenset({"SURF", "CUT"})
    g = _G({(0, 25)}, {(0, 25): set()})
    held = (len(g.visited), len(g.adj), moves, 100)

    # unchanged frontier inside the battle window holds the stream, no yield
    assert play.hold_stale(held, g, moves, 100) is False
    assert play.hold_stale(held, g, moves, 100 + play.HOLD_REPLAN_BATTLES - 1) is False

    # a map walked, a border learned, or a field move gained each yields for a re-plan
    assert play.hold_stale(held, _G({(0, 25), (0, 26)}, {(0, 25): set()}), moves, 100) is True
    assert play.hold_stale(held, _G({(0, 25)}, {(0, 25): set(), (0, 26): set()}), moves, 100) is True
    assert play.hold_stale(held, g, moves | {"DIVE"}, 100) is True

    # the battle window elapsing re-attempts the gated frontier
    assert play.hold_stale(held, g, moves, 100 + play.HOLD_REPLAN_BATTLES) is True

    print("test_hold_grind OK")


if __name__ == "__main__":
    main()
