"""catch_plan draws nothing once every gym is down and no wanted types remain. In Victory Road at 16
badges the plan kept switching the lead out for a softener and picking chip moves against uncaught
species (grind.log, "catch: Vileplume out, slot 1 in to soften Swanna"), a free hit per turn for a
box the League run never opens. A rebuild run keeps a wanted list at 16 badges, so the gate reads it
and still catches those types."""
import pytest

import planner
import play


def _player(badges: int, wanted=frozenset()) -> play.Player:
    p = play.Player.__new__(play.Player)
    p.g = type("_G", (), {"badges": lambda self: badges})()
    p.wanted = wanted
    return p


def test_all_gyms_down_with_no_wanted_draws_no_catch_plan():
    assert _player(len(planner.ALL_GYMS)).catch_plan(None, []) is None


def test_all_gyms_down_with_a_wanted_list_still_runs():
    # the rebuild run's wanted list keeps the gate open; the fake has no battle state, so a plan that
    # gets past the gate dies on the first read
    with pytest.raises(AttributeError):
        _player(len(planner.ALL_GYMS), frozenset({11})).catch_plan(None, [])


def test_under_the_last_badge_the_plan_still_runs():
    with pytest.raises(AttributeError):
        _player(len(planner.ALL_GYMS) - 1).catch_plan(None, [])
