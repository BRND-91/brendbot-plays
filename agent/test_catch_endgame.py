"""catch_plan draws nothing once every gym is down. In Victory Road at 16 badges the plan kept
switching the lead out for a softener and picking chip moves against uncaught species (grind.log,
"catch: Vileplume out, slot 1 in to soften Swanna"), a free hit per turn for a box the League run
never opens."""
import pytest

import planner
import play


def _player(badges: int) -> play.Player:
    p = play.Player.__new__(play.Player)
    p.g = type("_G", (), {"badges": lambda self: badges})()
    return p


def test_all_gyms_down_draws_no_catch_plan():
    assert _player(len(planner.ALL_GYMS)).catch_plan(None, []) is None


def test_under_the_last_badge_the_plan_still_runs():
    # the fake carries no battle state, so a plan that gets past the gate dies on the first read
    with pytest.raises(AttributeError):
        _player(len(planner.ALL_GYMS) - 1).catch_plan(None, [])
