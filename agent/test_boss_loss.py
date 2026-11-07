"""The post-game boss attempt ledger. Every whiteout against a boss lands an attempt row (fight start,
whiteout, money, the next fight's start as the rematch); planner.recommend names losses under the
current build x the measured retry span in its reason line, and a build change zeroes the count. The
catch-before-boss decision itself is test_coverage_grind."""
import json
import os

import map_graph
import planner
import play
import rowe_rom

STEVEN = (24, 107)
TACKLE, SURF = 33, 57
ROUTE_101, ROUTE_103 = (0, 16), (0, 18)


class Mon:
    def __init__(self, species, moves, level=100):
        self.species, self.moves, self.level = species, moves, level


def _player(tmp_path, party, last_boss=STEVEN, flag=False) -> play.Player:
    p = play.Player.__new__(play.Player)
    p.state_path = os.path.join(tmp_path, "live.ss")
    p._last_boss = last_boss
    p._boss_fight = None
    p.g = type("_G", (), {
        "party": lambda self: party,
        "flag": lambda self, f: flag,
        "money": lambda self: 90048,
    })()
    p.say = lambda s: None
    return p


def test_each_loss_writes_an_attempt_row_and_the_rematch_closes_it(tmp_path):
    p = _player(str(tmp_path), [Mon(612, (TACKLE, SURF))])
    p._boss_fight = (1000.0, 95048)
    p.note_boss_loss(play.OUTCOME_LOST)
    rows = json.load(open(os.path.join(str(tmp_path), "boss_losses.json")))[0]["attempts"]
    assert len(rows) == 1 and rows[0]["start"] == 1000.0 and rows[0]["money_before"] == 95048
    assert rows[0]["money_after"] == 90048 and rows[0]["rematch"] is None and rows[0]["whiteout"] > 1000.0
    # the next fight against the same boss opens: its start is the retry span's far end
    p._boss_fight = (2200.0, 90048)
    p.record_boss_rematch(STEVEN)
    rows = json.load(open(os.path.join(str(tmp_path), "boss_losses.json")))[0]["attempts"]
    assert rows[0]["rematch"] == 2200.0
    # a second loss w/ no fight start on record (relaunch mid-fight) still lands a row
    p._last_boss, p._boss_fight = STEVEN, None
    p.note_boss_loss(play.OUTCOME_LOST)
    rows = json.load(open(os.path.join(str(tmp_path), "boss_losses.json")))[0]["attempts"]
    assert len(rows) == 2 and rows[1]["start"] is None and rows[1]["rematch"] is None
    assert not os.path.exists(os.path.join(str(tmp_path), "boss_closed.json")), "no loss count holds a boss any more"


def test_a_win_or_a_non_boss_loss_records_nothing(tmp_path):
    p = _player(str(tmp_path), [Mon(612, (TACKLE,))], flag=True)  # boss flag up = beaten
    p.note_boss_loss(play.OUTCOME_LOST)
    p._last_boss = None
    p.note_boss_loss(play.OUTCOME_LOST)
    assert not os.path.exists(os.path.join(str(tmp_path), "boss_losses.json"))


def test_a_changed_move_resets_the_count(tmp_path):
    p = _player(str(tmp_path), [Mon(612, (TACKLE, SURF))])
    p.note_boss_loss(play.OUTCOME_LOST)
    # relearn a move: the signature changes, so the next loss is the first under the new build
    p.g = type("_G", (), {"party": lambda self: [Mon(612, (TACKLE, 85))], "flag": lambda self, f: False,
                          "money": lambda self: 90048})()
    p._last_boss = STEVEN
    p.note_boss_loss(play.OUTCOME_LOST)
    losses = {tuple(e["boss"]): e["count"] for e in json.load(open(os.path.join(str(tmp_path), "boss_losses.json")))}
    assert losses[STEVEN] == 1


def _status() -> dict:
    party = [{"species": 55, "level": 100, "moves": [{"name": "Surf", "power": 90, "pp": 10}]}] * 6
    return {"map": list(ROUTE_101), "badges": 16, "badge_flags": [True] * 8, "johto_flags": [True] * 8,
            "elite_flags": [True] * 4, "champion": True, "boss_flags": [False, True], "party": party,
            "field_moves": ["SURF"], "wanted_types": ["Ground"], "caught_species": []}


def _graph(tmp_path) -> map_graph.MapGraph:
    g = map_graph.MapGraph(os.path.join(str(tmp_path), "map_graph.json"), world=rowe_rom.world_edges())
    for m in (ROUTE_101, (0, 10), (0, 17), ROUTE_103, (0, 19), STEVEN):
        g.observe(m, [])
    return g


def _ledger(tmp_path, monkeypatch, status: dict, losses: int, retry_minutes: float) -> None:
    path = os.path.join(str(tmp_path), "boss_losses.json")
    monkeypatch.setattr(planner, "BOSS_LOSSES", path)
    monkeypatch.setattr(planner, "BLOCKED", os.path.join(str(tmp_path), "grind_blocked.json"))
    attempts = [{"start": 0.0, "whiteout": 100.0, "money_before": 95048, "money_after": 90048,
                 "rematch": 100.0 + retry_minutes * 60} for _ in range(losses)]
    with open(path, "w") as f:
        json.dump([{"boss": list(STEVEN), "count": losses, "signature": planner.party_signature(status), "attempts": attempts}], f)


def test_losses_are_priced_in_the_reason_and_the_boss_stays_open(tmp_path, monkeypatch):
    """A status w/ no boss_edge rows (a writer from before the field) weighs no catch and goes back in."""
    status = _status()
    _ledger(tmp_path, monkeypatch, status, losses=5, retry_minutes=10)
    goal, why = planner.recommend(status, _graph(tmp_path))
    assert goal["mode"] == "travel" and goal["to"] == list(STEVEN), (goal, why)
    assert "5 losses x 10 min = 50" in why, why


def test_a_signature_change_zeroes_the_losses_and_a_cold_ledger_names_its_defaults(tmp_path, monkeypatch):
    status = _status()
    _ledger(tmp_path, monkeypatch, status, losses=5, retry_minutes=10)
    grown = dict(status, party=[dict(m, moves=m["moves"] + [{"name": "Dig", "power": 80, "pp": 10}]) for m in status["party"]])
    goal, why = planner.recommend(grown, _graph(tmp_path))
    assert goal["mode"] == "travel" and "0 losses" in why, (goal, why)
    # no span measured yet: the retry default is priced and named
    path = os.path.join(str(tmp_path), "boss_losses.json")
    with open(path, "w") as f:
        json.dump([{"boss": list(STEVEN), "count": 5, "signature": planner.party_signature(status),
                    "attempts": [{"start": None, "whiteout": 1.0, "money_before": None, "money_after": 1, "rematch": None}] * 5}], f)
    goal, why = planner.recommend(status, _graph(tmp_path))
    assert f"5 losses x {planner.RETRY_MINUTES_DEFAULT} min" in why and "default" in why, why


def test_measured_retry_is_the_median_span(tmp_path, monkeypatch):
    status = _status()
    path = os.path.join(str(tmp_path), "boss_losses.json")
    monkeypatch.setattr(planner, "BOSS_LOSSES", path)
    spans = [3, 300, 9]  # a relaunch left one span a night long; the median prices the retry
    attempts = [{"start": 0.0, "whiteout": 100.0, "money_before": 1, "money_after": 1, "rematch": 100.0 + s * 60} for s in spans]
    attempts.append({"start": 0.0, "whiteout": 100.0, "money_before": 1, "money_after": 1, "rematch": None})
    with open(path, "w") as f:
        json.dump([{"boss": list(STEVEN), "count": 4, "signature": planner.party_signature(status), "attempts": attempts}], f)
    assert planner.boss_losses(status, STEVEN) == (4, 9.0)


def test_pace_samples_round_trip_through_pace_json(tmp_path):
    """A relaunch used to replan on the exp and hop defaults every time; the samples the last run
    measured come back from pace.json so the first plan of the new run is priced w/ them."""
    import collections
    path = os.path.join(str(tmp_path), "pace.json")
    p = play.Player.__new__(play.Player)
    # lead 7 gains 3000 exp over 60s, twice; a lead change to 9 in between is not a gain sample
    p._lead_exp = collections.deque([(100.0, 7, 1000), (160.0, 7, 4000), (200.0, 9, 500), (220.0, 7, 4000), (280.0, 7, 7000)], maxlen=play.PACE_SAMPLES)
    p._hop_sec = collections.deque([30.0, 300.0, 45.0], maxlen=play.PACE_SAMPLES)
    p._pace_path = path
    p._save_pace()
    q = play.Player.__new__(play.Player)
    q._lead_exp = collections.deque(maxlen=play.PACE_SAMPLES)
    q._hop_sec = collections.deque(maxlen=play.PACE_SAMPLES)
    assert q.exp_per_min() is None and q.hop_sec() is None
    q._load_pace(path)
    assert q.exp_per_min() == 3000.0 and q.hop_sec() == 45.0
    assert list(q._lead_exp)[0] == (100.0, 7, 1000), "samples come back as the tuples the measurement reads"
    # a run w/ no pace file yet starts empty and the planner prices the defaults
    r = play.Player.__new__(play.Player)
    r._lead_exp = collections.deque(maxlen=play.PACE_SAMPLES)
    r._hop_sec = collections.deque(maxlen=play.PACE_SAMPLES)
    r._load_pace(os.path.join(str(tmp_path), "absent.json"))
    assert r.exp_per_min() is None and r.hop_sec() is None


if __name__ == "__main__":
    import pytest
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
