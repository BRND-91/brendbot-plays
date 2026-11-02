"""The Victory Road entry door (27,48)->(16,12) is entered by an UP press from approach (27,49)
above the Ever Grande climb. From a fixture frozen on (27,49) the press fires MB_ANIMATED_DOOR and
the map id flips from (0,8) to (16,12). test_warp_approach only proves the approach is no longer
pruned; this asserts the warp itself fires and the map changes."""
import os
import shutil

import emu_boot as eb
import play

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "vr_door_27_49.ss")
ENTRY = (16, 12)
APPROACH = (27, 49)


def test_vr_door_press_changes_map():
    work = "/tmp/rowe-vr-door-press.ss"
    shutil.copy(FIXTURE, work)
    e = eb.Emu()
    e.load_state(open(work, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-vr-door-press.json")
    before = p.g.position()
    assert before[2:] == (0, 8), f"fixture not on Ever Grande: map {before[2:]}"
    assert before[:2] == APPROACH, f"fixture not on the door approach: tile {before[:2]}"
    status = p.errands.take_warp(ENTRY, surf=True, tools=frozenset(p.field_moves()))
    after = p.g.position()
    assert status == "map_changed", f"door press did not fire: take_warp -> {status}"
    assert after[2:] == ENTRY, f"map did not flip to {ENTRY}: at {after[2:]} tile {after[:2]}"


if __name__ == "__main__":
    test_vr_door_press_changes_map()
    print("test_vr_door_press OK")
