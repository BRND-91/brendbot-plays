"""Checks the objective ladder: at cap with a full party the planner routes to the nearest
unbeaten gym over the ROM's world edges, demotes a gym that would not fight, and holds a grind
once every Hoenn gym is down. Runs against the real ROM tables through rowe_rom."""
import json
import os
import tempfile

import map_graph
import planner
import rowe_rom


def _status(map_id, badges, beaten, cap_level=21, party=6):
    return {
        "badges": badges,
        "badge_flags": [g in beaten for g in range(8)],
        "party": [{"level": cap_level, "moves": [{"name": "Tackle", "power": 40, "pp": 10}]}
                  for _ in range(party)],
        "map": list(map_id),
        "exit_reason": "",
    }


def main() -> None:
    # the ROM confirms every entrance the ladder carries a badge offset for is a gym
    assert set(planner.GYM_BADGE) <= rowe_rom.gym_maps(), set(planner.GYM_BADGE) - rowe_rom.gym_maps()

    fd, graph_path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(graph_path)
    fd2, graph_path2 = tempfile.mkstemp(suffix=".json")
    os.close(fd2)
    os.remove(graph_path2)
    fd3, graph_path3 = tempfile.mkstemp(suffix=".json")
    os.close(fd3)
    os.remove(graph_path3)
    closed_bak = planner.GYM_CLOSED + ".testbak"
    had_closed = os.path.exists(planner.GYM_CLOSED)
    if had_closed:
        os.replace(planner.GYM_CLOSED, closed_bak)
    try:
        graph = map_graph.MapGraph(graph_path)

        # Check: cap 21, badge 1, Route 102 (0,17) -> gym (8,1) Petalburg, the nearest unbeaten
        # gym by world-edge hops, never a grind
        goal, why = planner.recommend(_status((0, 17), 1, {0}), graph)
        assert goal["mode"] == "gym" and goal["map"] == [8, 1], (goal, why)

        # a party short of cap grinds regardless of gym state
        under = planner.recommend(_status((0, 17), 1, {0}, cap_level=18), graph)[0]
        assert under["mode"] == "grind", under

        # a gym recorded closed is dropped from the ladder, not just ranked behind the open ones:
        # with Petalburg (8,1) shut, a different unbeaten gym is picked
        with open(planner.GYM_CLOSED, "w") as f:
            json.dump([{"gym": [8, 1], "reason": "loss", "min_level": 99, "field_moves": []}], f)
        demoted = planner.recommend(_status((0, 17), 1, {0}), graph)[0]
        assert demoted["mode"] == "gym" and demoted["map"] != [8, 1], demoted
        # every reachable unbeaten gym closed: no gym goal, the planner explores for a new route
        # instead of re-entering a gym the run cannot clear
        with open(planner.GYM_CLOSED, "w") as f:
            json.dump([{"gym": list(g), "reason": "loss", "min_level": 99, "field_moves": []} for g in planner.GYM_BADGE], f)
        allclosed = planner.recommend(_status((0, 17), 1, {0}), graph)[0]
        assert allclosed["mode"] == "explore", allclosed
        os.remove(planner.GYM_CLOSED)

        # every Hoenn gym beaten holds a grind, never a gym goal
        done = planner.recommend(_status((0, 17), 8, set(range(8))), graph)[0]
        assert done["mode"] == "grind", done

        # step 2: grind anchors on the next gym and ranks visited grass by hops then ROM wild
        # level. Route 101 (0,16), Route 102 (0,17) and Route 103 (0,19) walked, anchored on
        # Petalburg (8,1): the pick is (0,19), gym-close with the higher land level, and Route
        # 101 ranks below Route 102
        gg = map_graph.MapGraph(graph_path2)
        gg.visited.update({(0, 16), (0, 17), (0, 19)})
        assert planner.grind_map(gg, frozenset(), (8, 1), 21) == [0, 19], planner.grind_map(gg, frozenset(), (8, 1), 21)
        assert planner.grind_map(gg, frozenset({(0, 19)}), (8, 1), 21) == [0, 17], "Route 101 ranks below Route 102"

        # anchoring on the gym, not the executor's tile, keeps the grind fixed across a restock
        # detour: under cap at badge 1, standing in Oldale (0,10) or on Route 101 (0,16) grinds
        # the same map, never Route 101 while closer grass is walked
        from_oldale = planner.recommend(_status((0, 10), 1, {0}, cap_level=18), gg)[0]
        from_route = planner.recommend(_status((0, 16), 1, {0}, cap_level=18), gg)[0]
        assert from_oldale["mode"] == "grind" and from_oldale["map"] == from_route["map"], (from_oldale, from_route)
        assert from_oldale["map"] != [0, 16], from_oldale

        # step 4: with no gym to anchor on, the grind still anchors on the active goal's map, not
        # the executor's position, so a heal or restock that ends in a service town never moves it
        assert planner.planning_anchor({"goal": {"mode": "grind", "map": [0, 16]}}, (0, 10), None) == (0, 16)
        assert planner.planning_anchor({"goal": {"mode": "explore", "to": [3, 3]}}, (0, 10), None) == (3, 3)
        assert planner.planning_anchor({"goal": {"mode": "grind", "map": [0, 16]}}, (0, 10), (3, 3)) == (3, 3), "a reachable gym still wins"
        assert planner.planning_anchor({}, (0, 10), None) == (0, 10), "first launch before any goal falls back to here"

        # and recommend wires it in: every gym closed so none anchors, a party parked in Oldale
        # (0,10) after an errand grinds its goal's map, matching grind_map anchored on the goal and
        # never grind_map anchored on the errand town
        with open(planner.GYM_CLOSED, "w") as f:
            json.dump([{"gym": list(g), "reason": "loss", "min_level": 99, "field_moves": []} for g in planner.GYM_BADGE], f)
        parked = _status((0, 10), 1, {0}, cap_level=18)
        parked["goal"] = {"mode": "grind", "map": [0, 17], "cap": 21}
        blk = planner.blocked_grinds(parked)
        on_goal = planner.grind_map(gg, blk, (0, 17), 21)
        on_town = planner.grind_map(gg, blk, (0, 10), 21)
        assert on_goal != on_town, "test needs the town and the goal to rank grass differently"
        stuck = planner.recommend(parked, gg)[0]
        assert stuck["mode"] == "grind" and stuck["map"] == on_goal, (stuck, on_goal)
        os.remove(planner.GYM_CLOSED)

        # gym reachability honors the live graph's gated borders: an edge the executor recorded
        # gated under the party's current field moves drops the gym behind it from the ladder, and
        # gaining a move reopens it, so the planner routes over what the walk can actually cross
        pet = (8, 1)
        for p in [m for m, ds in rowe_rom.world_edges().items() if pet in ds]:
            graph.gated[(p, pet)] = frozenset({"SURF"})
        surf_only = _status((0, 17), 1, {0})
        surf_only["field_moves"] = ["SURF"]
        gated_off = planner.recommend(surf_only, graph)[0]
        assert gated_off["mode"] == "gym" and gated_off["map"] != [8, 1], gated_off
        grew = _status((0, 17), 1, {0})
        grew["field_moves"] = ["SURF", "CUT"]
        reopened = planner.recommend(grew, graph)[0]
        assert reopened["mode"] == "gym" and reopened["map"] == [8, 1], reopened
        graph.gated.clear()

        # a post-badge hold with no walkable route to Ever Grande (0,8) explores toward (0,8), never
        # grind_map. a grind fallback here ranks grass by hops to the unreachable target and walks
        # the party back across Hoenn (the live loop that swam it west), and at cap 45 the badge-8
        # party is over the cap so a grind earns nothing. Gate every world edge into (0,8).
        g5 = map_graph.MapGraph(graph_path3)
        g5.visited.update({(0, 16), (0, 40)})
        for p, ds in rowe_rom.world_edges().items():
            if (0, 8) in ds:
                g5.gated[(p, (0, 8))] = frozenset({"SURF"})
        st = _status((0, 16), 8, set(range(8)), cap_level=45)
        st["field_moves"] = ["SURF"]
        st["goal"] = {"mode": "travel", "to": [0, 8]}
        assert g5.route((0, 16), (0, 8), field_moves=frozenset({"SURF"})) is None, "test needs no route to (0,8)"
        g5goal, g5why = planner.recommend(st, g5)
        assert g5goal["mode"] == "explore" and g5goal["to"] == [0, 8], (g5goal, g5why)
        assert g5goal["mode"] != "grind", "no grind fallback at badge 8, it walks the party across Hoenn"
        # the reason carries here, the moves it routed under, and the reachable-map count, so a bad
        # here (an interior map or a mid-warp write) is a one-line diagnosis
        assert "[0, 16]" in g5why and "['SURF']" in g5why and "reachable" in g5why, g5why

        # arrival at Ever Grande, here == (0,8): the endgame chain travels on to the first unreached
        # hall, the Victory Road entry (16,12), never grinds back west. this needs the real ROM warp
        # edges, so build a world-backed graph with (0,8) already reached. the here != m guard skips
        # the self-hop and the (0,8)->(16,12) warp is open
        gw = map_graph.MapGraph(graph_path3, world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
        gw.visited.add((0, 8))
        arr = _status((0, 8), 8, set(range(8)), cap_level=45)
        arr["field_moves"] = ["SURF", "WATERFALL", "DIVE"]
        arrgoal, arrwhy = planner.recommend(arr, gw)
        assert arrgoal["mode"] == "travel" and arrgoal["to"] == [16, 12], (arrgoal, arrwhy)
        assert arrgoal["mode"] != "grind", arrwhy

        # once the entry hall (16,12) is reached it drops out of the chain; standing there the next
        # unreached target is the League-side hall (16,10)
        gw.visited.add((16, 12))
        nxt = _status((16, 12), 8, set(range(8)), cap_level=45)
        nxt["field_moves"] = ["SURF", "WATERFALL", "DIVE"]
        nxtgoal, nxtwhy = planner.recommend(nxt, gw)
        assert nxtgoal["mode"] == "travel" and nxtgoal["to"] == [16, 10], (nxtgoal, nxtwhy)

        print("test_planner OK")
    finally:
        for gp in (graph_path, graph_path2, graph_path3):
            if os.path.exists(gp):
                os.remove(gp)
        if os.path.exists(planner.GYM_CLOSED):
            os.remove(planner.GYM_CLOSED)
        if had_closed:
            os.replace(closed_bak, planner.GYM_CLOSED)


if __name__ == "__main__":
    main()
