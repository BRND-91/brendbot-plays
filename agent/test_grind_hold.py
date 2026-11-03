"""A grind that blocks on a grassless map exits to re-plan only when another reachable map holds
grass. When every reachable map is grassless too (the Sootopolis gym floor held behind the
thin-ice gate), exiting re-plans straight back into the identical stall and churns the supervisor
every GRASS_WAIT_TICKS, so _grind_no_grass holds the frame, raising GoalExit no_grass_idle only
after GRASS_IDLE_CAP so the supervisor can stop a map that never opens."""
import time

from play import Player, GoalExit, GRASS_IDLE_CAP, GRASS_WAIT_TICKS


def _player(reachable_grass):
    p = Player.__new__(Player)
    p.grass_waits = GRASS_WAIT_TICKS - 1  # next tick crosses the threshold
    p.grass_idle_since = None
    p._reachable_grass_map = lambda here: reachable_grass
    p.run = lambda n: None
    return p


def test_holds_when_every_reachable_map_is_grassless():
    p = _player(None)
    p._grind_no_grass((15, 1), 7, 19)  # no GoalExit: the stall would just relaunch
    assert p.grass_waits == 0, f"a held grind resets the wait counter, got {p.grass_waits}"


def test_exits_to_replan_when_a_grass_map_is_reachable():
    p = _player((0, 16))
    raised = False
    try:
        p._grind_no_grass((1, 31), 20, 38)
    except GoalExit:
        raised = True
    assert raised, "a reachable grass map elsewhere must exit to re-plan toward it"


def test_waits_out_a_transient_before_the_threshold():
    p = _player(None)
    p.grass_waits = 0
    p._grind_no_grass((15, 1), 7, 19)  # one transient tick, well under the threshold
    assert p.grass_waits == 1, f"a sub-threshold tick just counts, got {p.grass_waits}"


def test_exits_no_grass_idle_after_the_cap():
    p = _player(None)
    p.grass_idle_since = time.monotonic() - GRASS_IDLE_CAP - 1  # idling longer than the cap
    try:
        p._grind_no_grass((15, 1), 7, 19)
    except GoalExit as g:
        assert str(g) == "no_grass_idle", f"the cap exit names no_grass_idle, got {g}"
    else:
        raise AssertionError("idling past GRASS_IDLE_CAP must exit no_grass_idle")


if __name__ == "__main__":
    test_holds_when_every_reachable_map_is_grassless()
    test_exits_to_replan_when_a_grass_map_is_reachable()
    test_waits_out_a_transient_before_the_threshold()
    test_exits_no_grass_idle_after_the_cap()
    print("test_grind_hold OK")
