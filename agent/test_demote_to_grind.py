import types

import play
import planner

MOVES = frozenset({"CUT", "DIVE", "ROCKCLIMB", "ROCKSMASH", "SURF", "WATERFALL"})


def test_demote_to_grind_passes_status_to_sevii_goal(monkeypatch):
    """The 8-badge branch of demote_to_grind feeds sevii_goal the live status dict. sevii_goal's
    signature is (graph, moves, status); a two-arg call crashes the run with a TypeError that the
    supervisor reads as three identical 'crash' exits and stops the grind. Red before the status
    arg is passed (the spy's required third param is unfilled), green after."""
    seen = {}

    def spy(graph, moves, status):
        seen["status"] = status
        seen["moves"] = moves
        return {"mode": "explore", "to": [0, 79], "cap": None}, "spy goal"

    monkeypatch.setattr(planner, "sevii_goal", spy)

    p = play.Player.__new__(play.Player)
    p.graph = object()
    p.g = type("_G", (), {"badges": lambda self: 8})()
    p.field_moves = lambda: MOVES
    p.write_status = lambda: {"map": [2, 9], "badges": 8}
    p._held = "something"
    p.state_path = ""
    p.say = lambda msg: None

    play.Player.demote_to_grind(p, (2, 9))

    assert seen["status"] == {"map": [2, 9], "badges": 8}
    assert seen["moves"] == MOVES
    assert p.goal == {"mode": "explore", "to": [0, 79], "cap": None}
    assert p._held is None


def test_demote_to_grind_at_sixteen_badges_holds_a_grind(monkeypatch):
    """With every Hoenn and Johto flag set there is no Sevii gym left. sevii_goal's min() over the
    empty unbeaten set crashed the live run at badge 16, and handing back recommend's explore goal
    re-demoted 7163 times at [14, 3] with no frame between. The branch holds the wild grind on the
    map underfoot, the same hold the sub-8-badge frontier takes."""
    def boom(*a, **k):
        raise AssertionError("planner called with no unbeaten Sevii gym")

    monkeypatch.setattr(planner, "sevii_goal", boom)
    monkeypatch.setattr(planner, "recommend", boom)

    class _Grid:
        def reachable(self, start, surf):
            return {(3, 4), (3, 5)}

        def tiles_with_id(self, tile_id):
            return [(3, 5)]

    p = play.Player.__new__(play.Player)
    p.graph = types.SimpleNamespace(visited={(14, 3)}, adj={(14, 3): set()})
    p.g = types.SimpleNamespace(badges=lambda: 16, position=lambda: (3, 4, 14, 3))
    p.field_moves = lambda: MOVES
    p._grid = lambda: _Grid()
    p.write_status = lambda: {"map": [14, 3], "badges": 16, "badge_flags": [True] * 8, "johto_flags": [True] * 8}
    p.battles = 7
    p._held = None
    p.state_path = ""
    p.say = lambda msg: None

    play.Player.demote_to_grind(p, (14, 3))

    assert p.goal == {"mode": "grind", "map": [14, 3], "cap": None}
    assert p._held is not None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
