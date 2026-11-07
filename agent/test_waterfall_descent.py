"""Waterfall descent: surfing Down a WATERFALL run lands on the first water tile below it, no tool.
Without it the Ever Grande (0,8) approach above the fall (27,49) sees only the Center door (16,12),
so the Sevii leg west to (0,43) is unreachable and the grind round-trips (0,8)<->(16,12). Fixtures:
evergrande_0_8.ss holds the (0,8) grid, vr_door_27_49.ss is parked on the approach tile (27,49)."""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb  # noqa: E402
import map_graph  # noqa: E402
import play  # noqa: E402
import rowe_rom  # noqa: E402
from nav import Grid  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "states", "fixtures")


def _emu(name: str):
    e = eb.Emu()
    with open(os.path.join(FIX, name), "rb") as f:
        e.load_state(f.read())
    return e


def main() -> None:
    # 1. down the fall is a surf route from the approach above it to the water below. Removing the
    # descent edge makes this None (the only forced waterfall move would be the up climb).
    grid = Grid(_emu("evergrande_0_8.ss"))
    steps = grid.path((27, 49), (0, 67), surf=True)
    assert steps is not None, "no surf route down the Ever Grande fall"
    assert steps[0] == (0, 1), f"route does not start by descending the fall: {steps[0]}"
    # descent needs no Waterfall tool; the climb up does
    no_tool = Grid(_emu("evergrande_0_8.ss"))
    no_tool.climb = False
    assert no_tool.path((27, 49), (0, 67), surf=True) is not None, "descent wrongly gated on the climb tool"

    # 2. standing on the approach, the landing area now reaches the west border map (0,43), where
    # before it saw only the Center door (16,12) and bounced on it
    p = play.Player(_emu("vr_door_27_49.ss"), play.NullStreamer())
    exits = p._landing_exits()
    assert (0, 43) in exits, f"west border (0,43) unreachable from the approach: {sorted(exits)}"
    assert exits != {(16, 12)}, "landing exits still only the Center door"

    # 4. driving the approach toward (0,43) crosses the west border in one hop instead of
    # round-tripping. The graph is copied so block()/save() never touches the live map_graph.json.
    tmp = tempfile.mkdtemp()
    try:
        gpath = os.path.join(tmp, "map_graph.json")
        shutil.copy(os.path.join(HERE, "states", "map_graph.json"), gpath)
        d = play.Player(_emu("vr_door_27_49.ss"), play.NullStreamer())
        d.state_path = os.path.join(tmp, "probe.ss")  # Center errands resolve their json beside the save
        d.graph = map_graph.MapGraph(gpath, world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
        d.goal = {"mode": "travel", "to": [0, 43]}
        start, dest = d.g.position()[2:], (0, 43)
        changed = None
        for _ in range(25):
            try:
                d.travel_toward(dest)
            except play.GoalExit:
                break
            cur = d.g.position()[2:]
            if cur != start:
                changed = cur
                break
        assert changed == dest, f"drive did not cross to (0,43), reached {changed}"

        # the planner's Sevii leg goal is unrouted, so the executor maps westward for it: driving
        # mode=sevii crosses the same west border instead of halting on an unsupported goal
        gpath2 = os.path.join(tmp, "map_graph_sevii.json")
        shutil.copy(os.path.join(HERE, "states", "map_graph.json"), gpath2)
        s = play.Player(_emu("vr_door_27_49.ss"), play.NullStreamer())
        s.state_path = os.path.join(tmp, "probe.ss")
        s.graph = map_graph.MapGraph(gpath2, world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
        s.goal = {"mode": "sevii", "need": 16}
        sstart, schanged = s.g.position()[2:], None
        # drive the executor loop, not overworld_step alone: a surf crossing draws wild encounters,
        # so the step that fights them is battle_step on the in_battle branch
        in_battle = False
        for i in range(300):
            try:
                if s.g.in_battle():
                    if not in_battle:
                        in_battle = True
                        s._wedge = s._freezes = 0
                        s._wedge_sig = s._switch_active = None
                        s._wild_switched = False
                        s._start_items, s._avoid_slots = {}, set()
                    s.battle_step()
                else:
                    in_battle = False
                    s.overworld_step(i)
            except play.GoalExit:
                break
            if s.g.position()[2:] != sstart:
                schanged = s.g.position()[2:]
                break
        assert schanged == dest, f"sevii drive did not cross to (0,43), reached {schanged}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("ok")


if __name__ == "__main__":
    main()
