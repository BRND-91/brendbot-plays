"""note_gym_loss tallies a whiteout only when the objective was a gym, and at GYM_LOSS_CAP
losses records the gym closed so planner.closed_gyms demotes it on the ladder. A win, a flee,
or a loss while grinding counts against no gym."""
import json
import os
import tempfile

import planner
from play import Player, OUTCOME_LOST, OUTCOME_DREW, OUTCOME_CAUGHT, GYM_LOSS_CAP

GYM = (8, 1)


class _G:
    def party(self):
        return [type("M", (), {"level": 20})() for _ in range(3)]


class _Graph:
    visited: set = set()


def _player(tmp: str) -> Player:
    p = Player.__new__(Player)
    p.state_path = os.path.join(tmp, "route101.ss")
    p.goal = {"mode": "gym", "map": list(GYM), "badges": 1}
    p.say = lambda *a, **k: None
    p.g = _G()
    p.graph = _Graph()
    p.field_moves = lambda: frozenset()
    return p


def main() -> None:
    tmp = tempfile.mkdtemp()
    losses = os.path.join(tmp, "gym_losses.json")
    orig = planner.GYM_CLOSED
    planner.GYM_CLOSED = os.path.join(tmp, "gym_closed.json")
    try:
        p = _player(tmp)

        # a win, a catch, and a flee are not whiteouts
        p.note_gym_loss(1)
        p.note_gym_loss(OUTCOME_CAUGHT)
        p.note_gym_loss(4)  # B_OUTCOME_RAN
        assert not os.path.exists(losses), "nothing tallied without a loss"

        # a loss while grinding counts against no gym
        p.goal = {"mode": "grind", "map": list(GYM), "cap": None}
        p.note_gym_loss(OUTCOME_LOST)
        assert not os.path.exists(losses), "a grind loss is not a gym loss"

        # gym losses tally and stay open under the cap
        p.goal = {"mode": "gym", "map": list(GYM), "badges": 1}
        for i in range(1, GYM_LOSS_CAP):
            p.note_gym_loss(OUTCOME_LOST)
            assert GYM not in planner.closed_gyms(), f"open after {i} losses"

        # the cap-th loss, a draw counting the same, closes the gym and planner demotes it
        p.note_gym_loss(OUTCOME_DREW)
        assert json.load(open(losses))[0] == [list(GYM), GYM_LOSS_CAP], "every loss tallied"
        assert GYM in planner.closed_gyms(), "closed at the cap, demoted on the ladder"
    finally:
        planner.GYM_CLOSED = orig
    print("test_whiteout: ok")


if __name__ == "__main__":
    main()
