"""The planner's done goal, after the Champion. The executor had no branch for it and fell to the
Route 101 default, walking the Hall of Fame toward (0,16) and looping 'travel stuck: no route from
[16, 11] to [0, 16]'. Now the step raises the done exit before any movement, and replan hands it to
the supervisor instead of re-planning the same goal."""
import os
import shutil

import pytest

import emu_boot as eb
import play

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "states", "fixtures", "sidney_room.ss")


def test_done_goal_exits_before_moving():
    work = "/tmp/rowe-done-goal.ss"
    shutil.copy(FIXTURE, work)
    e = eb.Emu()
    e.load_state(open(work, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path=work + ".json")
    p.goal = {"mode": "done"}
    before = p.g.position()
    with pytest.raises(play.GoalExit, match="^done: champion"):
        p.overworld_step(0)
    assert p.g.position() == before
