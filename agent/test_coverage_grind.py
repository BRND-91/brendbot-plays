"""Past the clear a catchable species that out-scores the party's weakest member against the boss's
six sends the party to its grass before the fight, the catch policy takes that one species, and the
grind ends when the catch lands."""
import dataclasses
import json
import os

import catch
import map_graph
import planner
import play
import rowe_rom
from rowe_state import BattleMon

ROUTE_101, ROUTE_103 = (0, 16), (0, 18)
STEVEN = (24, 107)
POOCHYENA, SHELLOS, WOOPER = 261, 422, 194  # Route 101 land Dark; Route 103 land, Gastrodon 0.76 and Quagsire 0.71 vs Steven
GASTRODON, TEDDIURSA, URSALUNA = 423, 216, 901


def _held_status(edge: float, caught: list) -> dict:
    party = [{"species": 55, "level": 100, "moves": [{"name": "Surf", "power": 90, "pp": 10}], "boss_edge": edge}] * 6
    status = {"map": list(ROUTE_101), "badges": 16, "badge_flags": [True] * 8, "johto_flags": [True] * 8,
              "elite_flags": [True] * 4, "champion": True, "boss_flags": [False, True], "party": party,
              "field_moves": ["SURF"], "wanted_types": [], "caught_species": caught, "iv_boosts": [0] * 6}
    return status


def _graph(tmp_path) -> map_graph.MapGraph:
    g = map_graph.MapGraph(os.path.join(str(tmp_path), "map_graph.json"), world=rowe_rom.world_edges())
    for m in (ROUTE_101, (0, 10), (0, 17), ROUTE_103, (0, 19), STEVEN):
        g.observe(m, [])
    return g


def _hold(tmp_path, monkeypatch, status: dict) -> None:
    """Five losses at a 30-minute retry under the current build, on the ledger for the reason line."""
    path = os.path.join(str(tmp_path), "boss_losses.json")
    monkeypatch.setattr(planner, "BOSS_LOSSES", path)
    monkeypatch.setattr(planner, "BLOCKED", os.path.join(str(tmp_path), "grind_blocked.json"))
    attempts = [{"start": 0.0, "whiteout": 100.0, "money_before": 1, "money_after": 1, "rematch": 1900.0}] * 5
    with open(path, "w") as f:
        json.dump([{"boss": list(STEVEN), "count": 5, "signature": planner.party_signature(status), "attempts": attempts}], f)


def test_a_catch_that_beats_the_weakest_member_comes_before_the_boss(tmp_path, monkeypatch):
    """Six Surf Golducks at -3.0 each: Shellos on Route 103, an Earth Power Gastrodon at L100, scores
    0.76 and wins the grass over the Dark Poochyena underfoot on Route 101, whatever the five losses
    cost. The goal names the species so the catch policy spends the reserve on it."""
    status = _held_status(-3.0, [])
    _hold(tmp_path, monkeypatch, status)
    goal, why = planner.recommend(status, _graph(tmp_path))
    assert goal == {"mode": "grind", "map": list(ROUTE_103), "cap": None, "coverage": True, "caught_n": 0, "species": SHELLOS}, (goal, why)
    assert "catch Shellos on [0, 18], edge 0.76 vs weakest -3.0" in why and "5 losses" in why, why


def test_a_caught_species_hands_the_grass_to_the_next_and_a_sound_party_goes_in(tmp_path, monkeypatch):
    """Shellos caught: Wooper on the same grass is next at 0.71. At a weakest edge of 1.0 nothing on
    the walked maps beats it by CATCH_MARGIN and the party travels to the boss."""
    status = _held_status(-3.0, [SHELLOS])
    _hold(tmp_path, monkeypatch, status)
    goal, why = planner.recommend(status, _graph(tmp_path))
    assert goal["species"] == WOOPER and goal["map"] == list(ROUTE_103) and goal["caught_n"] == 1, (goal, why)
    # the ledger holds the form the ball closed on: a caught Gastrodon retires the Shellos row too
    goal, why = planner.recommend(_held_status(-3.0, [GASTRODON]), _graph(tmp_path))
    assert goal["species"] == WOOPER, (goal, why)
    sound = _held_status(1.0, [])
    goal, why = planner.recommend(sound, _graph(tmp_path))
    assert goal["mode"] == "travel" and goal["to"] == list(STEVEN) and "5 losses" in why, (goal, why)


def test_the_catch_policy_takes_the_goal_species_on_the_reserve(tmp_path):
    """Ledger.wants: the goal species is wanted at the ball reserve w/ no wanted type on it; any other
    uncaught species at the reserve still needs a wanted type."""
    ledger = catch.Ledger(os.path.join(str(tmp_path), "caught.json"), [])
    shellos = BattleMon(battler=1, species=SHELLOS, level=60, hp=100, max_hp=100, moves=(0,) * 4, pp=(0,) * 4,
                        types=rowe_rom.species(SHELLOS).types, ability=0, status1=0, stat_stages=(6,) * 8, nickname="Shellos")
    assert ledger.wants(shellos, frozenset(), catch.BALL_RESERVE, species=SHELLOS)
    assert not ledger.wants(shellos, frozenset(), catch.BALL_RESERVE, species=WOOPER)
    assert not ledger.wants(shellos, frozenset(), catch.BALL_RESERVE)
    # post-clear scaling fields Teddiursa's row as a L52 Ursaluna; the goal names the row, the ball meets the form
    ursaluna = dataclasses.replace(shellos, species=URSALUNA, level=52, types=rowe_rom.species(URSALUNA).types, nickname="Ursaluna")
    assert ledger.wants(ursaluna, frozenset(), catch.BALL_RESERVE, species=TEDDIURSA)
    assert not ledger.wants(ursaluna, frozenset(), catch.BALL_RESERVE, species=SHELLOS)


def test_a_grind_the_walk_cannot_reach_is_blocked_on_the_next_plan(tmp_path, monkeypatch):
    """A travel stuck exit off a grind goal blocks that goal's grass when the failed walk was toward
    the grass itself, so the next plan picks another. A stuck on the way out of a wedged map (the live
    run on (1,62) with its one onward gate shut) names another destination and blocks nothing, since
    the first cut of this rule blocked 43 grass maps in five minutes from that one spot."""
    monkeypatch.setattr(planner, "BLOCKED", os.path.join(str(tmp_path), "grind_blocked.json"))
    status = _held_status(["Dark"], [POOCHYENA])
    status["map"] = [1, 62]
    status["goal"] = {"mode": "grind", "map": [0, 36], "cap": 100}
    status["exit_reason"] = "travel stuck: unreachable (1, 62) -> [1, 58] 5x from (0, 48), re-planning"
    assert planner.blocked_grinds(status) == frozenset()
    status["exit_reason"] = "travel stuck: no route from [1, 62] to [0, 10], re-planning"
    assert planner.blocked_grinds(status) == frozenset()
    assert not os.path.exists(os.path.join(str(tmp_path), "grind_blocked.json"))
    status["map"] = [0, 35]
    status["exit_reason"] = "travel stuck: no route from [0, 35] to [0, 36], re-planning"
    assert planner.blocked_grinds(status) == frozenset({(0, 36)})
    status["exit_reason"] = "travel stuck: unreachable (0, 35) -> [0, 36] 5x from (3, 3), re-planning"
    assert planner.blocked_grinds(status) == frozenset({(0, 36)})
    assert json.load(open(os.path.join(str(tmp_path), "grind_blocked.json"))) == [[0, 36]]
    # the map the party stands on is what a 'grind blocked' exit names, unchanged
    status["exit_reason"] = "grind blocked: no grass reachable"
    status["map"] = [0, 18]
    assert planner.blocked_grinds(status) == frozenset({(0, 36), (0, 18)})
    # a travel stuck exit off a travel goal blocks nothing
    status["goal"] = {"mode": "travel", "to": [24, 107]}
    status["exit_reason"] = "travel stuck: no route from [1, 62] to [24, 107], re-planning"
    assert planner.blocked_grinds(status) == frozenset({(0, 36), (0, 18)})


def test_the_coverage_grind_ends_on_the_catch(tmp_path):
    p = play.Player.__new__(play.Player)
    p.state_path = os.path.join(str(tmp_path), "live.ss")
    with open(os.path.join(str(tmp_path), "goal.json"), "w") as f:
        json.dump({"mode": "grind", "map": list(ROUTE_101), "cap": None, "coverage": True, "caught_n": 3}, f)
    p.ledger = type("L", (), {"caught": {1, 2, 3}})()
    p._held = None
    p.g = type("G", (), {"party": staticmethod(lambda: []), "position": staticmethod(lambda: (5, 5) + ROUTE_101),
                         "badges": staticmethod(lambda: 16)})()
    p.check_goal()
    p.ledger.caught.add(POOCHYENA)
    try:
        p.check_goal()
    except play.GoalExit as ex:
        assert "coverage catch landed" in str(ex)
    else:
        raise AssertionError("the grind kept going after the catch")
