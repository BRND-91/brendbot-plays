"""At 8 badges every Hoenn gym is beaten and the party is over cap 45, so an explore step that
finds the frontier gated has no productive grind left: the endgame route out is blocked (the Ever
Grande waterfall up to the Victory Road warp). explore_step raises an "unsupported" GoalExit the
supervisor halts on instead of falling through to demote_to_grind, which would walk the party back
west across Hoenn. Below 8 badges the same gated frontier still demotes to a grind."""
from play import GoalExit, Player


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
    return p


def test_badge8_gated_frontier_halts_unsupported():
    p = _player(8)
    try:
        p.explore_step()
    except GoalExit as g:
        assert str(g).startswith("unsupported"), f"supervisor halt needs an unsupported reason, got {g}"
        assert "endgame blocked" in str(g) and "[0, 8]" in str(g), f"reason names no endgame map: {g}"
    else:
        raise AssertionError("a gated frontier at 8 badges must halt, never grind the party back west")


def test_below_badge8_still_demotes_to_grind():
    p = _player(7)
    demoted = []
    p.demote_to_grind = lambda here: demoted.append(here)
    p.explore_step()
    assert demoted == [(0, 8)], f"below 8 badges a gated frontier still grinds, got {demoted}"


if __name__ == "__main__":
    test_badge8_gated_frontier_halts_unsupported()
    test_below_badge8_still_demotes_to_grind()
    print("test_endgame_halt OK")
