"""The ferry layer drops a giver whose sailor the ROM removed, so routing plans to a present
dispatcher instead of walking to the gap a used giver left. A Seagallop giver's sailor hides once
its island's ticket is handed over (the (1,9) sailor's flag 0xDF3 sets at 12 badges), and the graph
used to keep its arms, so route() picked the dead dispatcher and the executor no_menu-looped."""
import planner
import script_decode


_EDGES = {
    (1, 9): {(0, 75): frozenset(), (1, 32): frozenset()},   # a used dispatcher, sailor gone
    (1, 27): {(0, 75): frozenset(), (1, 32): frozenset()},  # a present dispatcher
}


def test_script_layer_drops_a_hidden_giver(monkeypatch):
    monkeypatch.setattr(script_decode, "script_edges", lambda: _EDGES)
    monkeypatch.setattr(script_decode, "passable_island_arm", lambda s, d, t: True)
    layer = planner.script_layer(frozenset(), hidden=frozenset({(1, 9)}))
    assert (1, 9) not in layer, "the gone giver's arms are dropped from the ferry layer"
    assert layer[(1, 27)] == {(0, 75): frozenset(), (1, 32): frozenset()}, "the present giver keeps its arms"


def test_script_layer_keeps_every_giver_when_none_hidden(monkeypatch):
    monkeypatch.setattr(script_decode, "script_edges", lambda: _EDGES)
    monkeypatch.setattr(script_decode, "passable_island_arm", lambda s, d, t: True)
    layer = planner.script_layer(frozenset())
    assert set(layer) == {(1, 9), (1, 27)}, "with nothing hidden both givers route"
