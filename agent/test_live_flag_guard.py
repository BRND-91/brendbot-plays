"""The dev League-guard flag (0x0dfa) is a fixture shortcut and must never reach the live save.
Two guards: set_flag refuses a live-save target, and the live save on disk is checked clean, so a
flag that ever lands there turns this red. Channel rule "ROWE live save"."""
import os
import shutil

import rowe_live
import set_league_flag as slf

BASE = os.path.dirname(os.path.abspath(__file__))
LIVE = rowe_live.LIVE_SAVE
FIXTURE = os.path.join(BASE, "states", "fixtures", "evergrande_0_8.ss")


def test_set_flag_refuses_live_save():
    try:
        slf.set_flag(LIVE)
    except RuntimeError:
        pass
    else:
        raise AssertionError("set_flag wrote the live save; the guard must refuse it")
    ring = os.path.join(rowe_live.RING_DIR, "20000101T0000.ss")
    try:
        slf.set_flag(ring)
    except RuntimeError:
        pass
    else:
        raise AssertionError("set_flag wrote the live ring; the guard must refuse it")


def test_live_save_guard_flag_clear():
    if not os.path.exists(LIVE):
        return  # no live save in this checkout, nothing to protect
    assert not slf.read_flag(LIVE), (
        f"League guard flag {slf.GUARD_FLAG:#06x} is set on the live save; the live run earns the "
        "League for real and a dev flag here fakes progression"
    )


def test_set_flag_sets_on_a_copy():
    scratch = "/tmp/rowe-flagtest.ss"
    shutil.copy(FIXTURE, scratch)
    assert not slf.read_flag(scratch), "fixture already carries the guard flag; pick a clean base"
    slf.set_flag(scratch)
    assert slf.read_flag(scratch), "set_flag did not set the guard flag on the copy"
    os.remove(scratch)


if __name__ == "__main__":
    test_set_flag_refuses_live_save()
    test_live_save_guard_flag_clear()
    test_set_flag_sets_on_a_copy()
    print("test_live_flag_guard OK")
