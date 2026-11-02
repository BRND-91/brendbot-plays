"""The Ever Grande (0,8) Victory Road entrance door (16,12) is entered by surfing up the waterfall
to the approach tile (27,49) just below it and pressing UP. That approach sits above the climb at
an elevation the old single-step passable prune in _step_into_warp rejected from the surfer's
carried height, so take_warp dropped the only approach to the door and returned 'stuck' pinned on
the start tile. The fix gates the approach on a real route (grid.path with climb), so the warp
attempt now walks toward the door instead of giving up at the shore."""
import os
import shutil

import emu_boot as eb
import play

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "evergrande_0_8.ss")
ENTRY = (16, 12)


def test_vr_door_approach_not_pruned():
    work = "/tmp/rowe-vr-approach-test.ss"
    shutil.copy(FIXTURE, work)
    e = eb.Emu()
    e.load_state(open(work, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-vr-approach.json")
    start = p.g.position()[:2]
    status = p.errands.take_warp(ENTRY, surf=True, tools=frozenset(p.field_moves()))
    moved = p.g.position()[:2] != start
    # pre-fix the surf-elevation passable prune dropped the only approach (27,49), so take_warp
    # returned 'stuck' with no step; now the walk reaches toward the door. A surf encounter can
    # interrupt the walk, which the executor loop fights, so 'battle' still counts as progress.
    assert status != "stuck", f"approach pruned, take_warp stuck at {start}"
    assert moved, f"avatar never left {start}; the door approach was pruned"


if __name__ == "__main__":
    test_vr_door_approach_not_pruned()
    print("test_warp_approach OK")
