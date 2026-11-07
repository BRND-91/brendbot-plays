"""An explore step that finds the frontier gated holds the run on a capless wild-battle grind at
every badge count, including 8, so the stream stays up and the next in-process replan re-decides
the goal from the ferry-aware graph. Raising "unsupported" here relaunched the supervisor into the
same dead goal every 30s (the Lavaridge STOP line); the supervisor's unsupported handler stays a
backstop for an exit explore_step no longer raises. A dive off the cluster is tried first."""
from play import Player


class _Graph:
    def explore_hop(self, here, blocked, moves):
        return None  # no open border to walk

    def frontier_exhausted(self, moves):
        return True

    def gated_frontier(self, moves):
        return True


class _G:
    def __init__(self, badges):
        self._badges = badges

    def position(self):
        return (12, 5, 0, 8)  # Ever Grande City (0,8)

    def badges(self):
        return self._badges


def _player(badges):
    p = Player.__new__(Player)
    p.graph = _Graph()
    p.g = _G(badges)
    p.field_moves = lambda: frozenset({"SURF", "WATERFALL", "DIVE"})
    p.region = lambda: (0, 8, 0)
    p._blocked_from = lambda region: set()
    p._dive_frontier = lambda region, moves: False  # no dive off the cluster
    p._leave_dynamic_interior = lambda here, moves: False  # Ever Grande is an outdoor map, no dynamic warp out
    demoted = []
    p.demote_to_grind = lambda here: demoted.append(here)
    return p, demoted


def test_badge8_gated_frontier_demotes_never_raises():
    p, demoted = _player(8)
    p.explore_step()  # must not raise GoalExit
    assert demoted == [(0, 8)], f"a gated frontier at 8 badges holds a grind, got {demoted}"


def test_below_badge8_still_demotes_to_grind():
    p, demoted = _player(7)
    p.explore_step()
    assert demoted == [(0, 8)], f"below 8 badges a gated frontier still grinds, got {demoted}"


if __name__ == "__main__":
    test_badge8_gated_frontier_demotes_never_raises()
    test_below_badge8_still_demotes_to_grind()
    print("test_endgame_halt OK")
