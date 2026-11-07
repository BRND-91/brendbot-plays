"""The planner sends a bag holding a fossil to Rustboro's Devon Corp ahead of the grind, and drops the
errand once the executor reports FOSSIL_FAIL_CAP short attempts or the bag holds no fossil."""
import os
import tempfile

import map_graph
import planner
import rowe_rom

HELIX_FOSSIL = 447


def _status(fossils, fails=0):
    return {
        "badges": 1, "badge_flags": [True] + [False] * 7, "johto_flags": [False] * 8,
        "party": [{"level": 18, "moves": [{"name": "Tackle", "power": 40, "pp": 10}]} for _ in range(6)],
        "map": list(planner.RUSTBORO), "exit_reason": "", "fossils": fossils, "fossil_fails": fails,
    }


def _graph():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)
    return map_graph.MapGraph(path, world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())


def test_a_fossil_in_the_bag_is_an_errand_ahead_of_the_grind():
    goal, why = planner.recommend(_status([HELIX_FOSSIL]), _graph())
    assert goal == {"mode": "errand", "errand": "revive_fossil", "to": [0, 3]}, (goal, why)


def test_the_errand_drops_at_the_fail_cap_and_with_an_empty_bag():
    assert planner.recommend(_status([HELIX_FOSSIL], fails=planner.FOSSIL_FAIL_CAP), _graph())[0]["mode"] == "grind"
    assert planner.recommend(_status([]), _graph())[0]["mode"] == "grind"
