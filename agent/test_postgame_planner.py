"""After the Champion the planner sends the party at the post-game bosses in POSTGAME order, each
dropping out on its defeat flag, and returns done only once both are down. Pre-change the champion
bit alone returned done from the Hall of Fame."""
import os
import tempfile

import map_graph
import planner
import rowe_rom

HALL_OF_FAME = (16, 11)


def _status(boss_flags):
    return {
        "badges": 16,
        "badge_flags": [True] * 8,
        "johto_flags": [True] * 8,
        "party": [{"level": 100, "moves": [{"name": "Surf", "power": 90, "pp": 10}]} for _ in range(6)],
        "map": list(HALL_OF_FAME),
        "field_moves": ["CUT", "DIVE", "ROCKCLIMB", "ROCKSMASH", "SURF", "WATERFALL"],
        "champion": True,
        "boss_flags": boss_flags,
        "exit_reason": "",
    }


def _graph():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)
    return map_graph.MapGraph(path, world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())


def test_first_boss_is_steven():
    goal, why = planner.recommend(_status([False, False]), _graph())
    assert goal["mode"] in ("travel", "explore") and goal["to"] == [24, 107], (goal, why)


def test_steven_down_sends_the_party_at_red():
    goal, why = planner.recommend(_status([True, False]), _graph())
    assert goal["mode"] in ("travel", "explore") and goal["to"] == [24, 51], (goal, why)


def test_both_bosses_down_is_done():
    goal, why = planner.recommend(_status([True, True]), _graph())
    assert goal == {"mode": "done"}, (goal, why)
