"""The 2026-11-01 Sootopolis bounce: stuck underwater at (24,5), the supervisor relaunched the run
every ~138s. demote_to_grind picked grind target (0,51) from _reachable_grass_map, but
travel_toward's graph.route((24,5),(0,51)) is None, so every run raised "travel stuck: no route"
and churned the supervisor. _reachable_grass_map walked graph.neighbors() from the live grid's
landing exits and returned (0,51) because its node[1]>=16 test classes it grass, though (0,51) is a
MAP_TYPE_UNDERWATER seabed pocket that holds no grass and that graph.route cannot reach from (24,5).

A MAP_TYPE_UNDERWATER map is never a grass target, so _reachable_grass_map now skips underwater nodes
whole and demote_to_grind falls back to here, which the grind holds in place instead of bouncing.
The demote assertion fails on the pre-patch code (target (0,51), unroutable) and passes after.

Fixture states/fixtures/sootopolis_underwater_stuck.ss is the frozen live save at (24,5).
"""
import os

import emu_boot as eb
import map_graph
import play
import rowe_rom

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "sootopolis_underwater_stuck.ss")
HERE = (24, 5)


def _player() -> play.Player:
    e = eb.Emu()
    e.load_state(open(FIXTURE, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-underwater-test.json")
    p.graph = map_graph.MapGraph(
        os.path.join(BASE, "states", "map_graph.json"),
        world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
    return p


def test_fixture_is_the_stuck_underwater_tile():
    p = _player()
    assert tuple(p.g.position()[2:]) == HERE
    assert rowe_rom.is_underwater(*HERE)


def test_reachable_grass_map_pick_is_not_underwater():
    p = _player()
    pick = p._reachable_grass_map(HERE)
    assert pick is None or not rowe_rom.is_underwater(*pick), (
        f"_reachable_grass_map picked {pick}, a MAP_TYPE_UNDERWATER map that holds no grass")


def test_demote_sets_a_reachable_grind_target():
    p = _player()
    moves = p.field_moves()
    p.demote_to_grind(HERE)
    target = tuple(p.goal["map"])
    assert target == HERE or p.graph.route(HERE, target, field_moves=moves) is not None, (
        f"demote_to_grind set grind target {target} that travel_toward cannot reach from {HERE}")
