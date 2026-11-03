"""Pin the script-warp graph layer: an NPC-interaction crossing (the Seagallop ferry) is a neighbor
only while its gate flags are set, so route reaches the Sevii block once the ferry flag is earned and
not before. Red-capable: drop the `self._script_dests(node)` term from neighbors and the gated edge
never appears; ignore the flag check in _script_dests and the no-flag case stops going absent."""
import os

import map_graph
import rowe_rom
import script_decode

BASE = os.path.dirname(os.path.abspath(__file__))
GRAPH = os.path.join(BASE, "states", "map_graph.json")
SE = script_decode.script_edges()


def _graph(flags):
    return map_graph.MapGraph(GRAPH, world=rowe_rom.world_edges(),
                              passthrough=rowe_rom.passthroughs(), script=SE, flags=flags)


def _gated_edge():
    """A flag-gated script crossing into groups 24-26 that no static or learned edge already carries,
    so a flag toggle is the only thing that can move it in or out of neighbors."""
    base = _graph(set())
    for src, dests in SE.items():
        for dest, gate in dests.items():
            if gate and dest[0] in (24, 25, 26) and dest not in base.world.get(src, set()) | base.adj.get(src, set()):
                return src, dest, gate
    raise AssertionError("no flag-gated Sevii script edge found")


def test_ferry_edge_opens_only_with_its_flag():
    src, dest, gate = _gated_edge()
    on = _graph(set(gate))
    on.cur_badges = 8
    off = _graph(set())
    off.cur_badges = 8
    assert dest in on.neighbors(src), (src, dest)
    assert on.route(src, dest) == dest, (src, dest)
    assert dest not in off.neighbors(src), (src, dest)
    assert off.route(src, dest) != dest, (src, dest)


def test_ungated_ferry_edge_is_always_present():
    # (0,71) -> (24,53) is an ungated script warp, a neighbor with no flags set
    assert (24, 53) in SE.get((0, 71), {})
    assert (24, 53) in _graph(set()).neighbors((0, 71))


def test_seagallop_edge_in_layer():
    # the main ferry dock maps reach a (25,*) dock gated by flag 0xCE8
    gated_25 = [(src, dest) for src, dests in SE.items() for dest, gate in dests.items()
                if dest[0] == 25 and 0xCE8 in gate]
    assert gated_25, "no 0xCE8-gated (25,*) crossing in the script layer"


def test_route_crosses_ferry_as_last_hop():
    # port selection is route's job: a Hoenn start reaches (25,24) only with the ferry gate set, and
    # the dock->(25,24) hop is the script edge, since no world or learned edge carries (25,24).
    dock, dest = (2, 3), (25, 24)
    on = _graph(set(SE[dock][dest]))
    on.cur_badges = 8
    off = _graph(set())
    off.cur_badges = 8
    assert dest not in on.world.get(dock, set()) | on.adj.get(dock, set())
    assert on.route(dock, dest) == dest
    assert on.route((0, 4), dest) is not None
    assert off.route((0, 4), dest) is None


def test_branch_gate_keeps_shared_and_branch_flags():
    # (2,3) is the Seagallop dock. Every crossing shares the ferry-service gate 0xCD1 (the upstream
    # checkflag the old nearest-flag heuristic dropped when a later checkflag overwrote it); the
    # (25,26) island additionally carries its own branch flag 0xCE8, while the (25,60) teleport needs
    # only the shared one. Red-capable: a nearest-preceding gate drops 0xCD1 from the 0xCE8 edges and
    # the shared-flag assertion goes red.
    edges = SE[(2, 3)]
    assert all(0xCD1 in g for g in edges.values()), {d: sorted(g) for d, g in edges.items()}
    assert edges[(25, 60)] == frozenset({0xCD1})
    assert edges[(25, 26)] == frozenset({0xCD1, 0xCE8})


def test_talk_object_resolves_dock_sailor():
    # piece 1, the object-event decoder: a crossing ties to the NPC that triggers it. On the Seagallop
    # dock (2,3) the crossing to (25,24) is obj#3 at (10,2), movement 8 (face-up), script 0x0830B1BD,
    # approached from the tile below facing up. The values are read off the ROM object table, not
    # derived here. Red-capable: a wrong OBJ_SCRIPT offset or a wrong object changes index/obj/script.
    objs = rowe_rom.map_object_scripts(2, 3)
    assert [o[0] for o in objs] == [1, 2, 3, 4], objs
    assert (3, 10, 2, 8, 0x0830B1BD) in objs, objs
    t = script_decode.talk_object((2, 3), (25, 24))
    assert t is not None
    assert t["index"] == 3 and t["obj"] == (10, 2), t
    assert t["approach"] == (10, 3) and t["facing"] == (0, -1), t
    assert t["movement"] == 8 and t["script"] == 0x0830B1BD, t
    assert script_decode.talk_object((2, 3), (0, 0)) is None


def test_menu_sequence_distinguishes_dock_destinations():
    # piece 2, the menu-pick planner: each Seagallop crossing is a distinct sequence of multichoice
    # picks. The dock switches on VAR_RESULT copied into a scratch var, then a menu case loads a
    # constant dispatch code with setvar and a shared tail routes on it, so the planner tracks both
    # the menu result and the constants. Values pinned from the ROM; the executor confirms a chain
    # actually lands its warp against the dock fixture in piece 3.
    ms = script_decode.menu_sequence
    assert ms((2, 3), (25, 24)) == (("multi", 1), ("multi", 0))
    assert ms((2, 3), (25, 26)) == (("multi", 2),)
    assert ms((2, 3), (25, 27)) == (("multi", 1), ("multi", 2))
    assert ms((2, 3), (0, 0)) is None
    # (25,24) and (25,27) share the first pick and split on the second; without the constant
    # propagation the shared dispatch tail makes both reachable from either and the chains collapse.
    assert ms((2, 3), (25, 24)) != ms((2, 3), (25, 27))
    # the B-cancel case 0x7F is pruned, so no chain ever carries it
    for dest in ((25, 24), (25, 26), (25, 27)):
        assert all(v != 0x7F for _kind, v in ms((2, 3), dest))


if __name__ == "__main__":
    test_ferry_edge_opens_only_with_its_flag()
    test_ungated_ferry_edge_is_always_present()
    test_seagallop_edge_in_layer()
    test_route_crosses_ferry_as_last_hop()
    test_branch_gate_keeps_shared_and_branch_flags()
    test_talk_object_resolves_dock_sailor()
    test_menu_sequence_distinguishes_dock_destinations()
    print("SCRIPT EDGES PASS", flush=True)
