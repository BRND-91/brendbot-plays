"""Checks the objective ladder: at cap with a full party the planner routes to the nearest
unbeaten gym over the ROM's world edges, demotes a gym that would not fight, and holds a grind
once every Hoenn gym is down. Runs against the real ROM tables through rowe_rom."""
import json
import os
import tempfile

import map_graph
import planner
import rowe_rom
import script_decode


def _status(map_id, badges, beaten, cap_level=21, party=6, johto=()):
    return {
        "badges": badges,
        "badge_flags": [g in beaten for g in range(8)],
        "johto_flags": [g in johto for g in range(8)],
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
        graph = map_graph.MapGraph(graph_path, world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())

        # Check: cap 21, badge 1, Route 102 (0,17) -> gym (8,1) Petalburg, the nearest unbeaten
        # gym by world-edge hops, never a grind
        goal, why = planner.recommend(_status((0, 17), 1, {0}), graph)
        assert goal["mode"] == "gym" and goal["map"] == [8, 1], (goal, why)
        # the gym goal carries the League-flag count at write time, so the executor completes it on
        # a Johto win too, where the Hoenn badge var never moves (one Hoenn badge up here -> 1)
        assert goal["flags"] == 1, goal

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

        # every Hoenn gym beaten: the Sevii leg takes over off the badge table and never grinds Hoenn
        # again, even short of cap, since the grass raises nothing at the cap. With no ferry route
        # learned in this graph it explores toward a frontier rather than re-entering a gym
        done = planner.recommend(_status((0, 17), 8, set(range(8))), graph)[0]
        assert done["mode"] == "explore", done
        assert done["mode"] != "grind", done

        # part 4: Johto gyms gate off the ROM badge-gate scan, not the loss record. At 8 badges
        # Falkner (2,7) gate badge 8 is open while Bugsy (2,8) and Whitney (2,9) are shut; a 10th
        # badge opens Whitney. A Hoenn gym is never badge-gated this way, it keeps its loss record.
        sc8 = planner.still_closed(_status((0, 79), 8, set(range(8))), graph)
        assert (2, 7) not in sc8 and (2, 8) in sc8 and (2, 9) in sc8, sc8
        sc10 = planner.still_closed(_status((0, 79), 10, set(range(8)), johto={0, 1}), graph)
        assert (2, 9) not in sc10, sc10
        with open(planner.GYM_CLOSED, "w") as f:
            json.dump([{"gym": [8, 1], "reason": "loss", "min_level": 99, "field_moves": []}], f)
        assert (8, 1) in planner.still_closed(_status((0, 17), 1, {0}), graph), "Hoenn loss still shuts"
        os.remove(planner.GYM_CLOSED)

        # step 2: grind anchors on the next gym and ranks visited grass by hops then ROM wild
        # level. Route 101 (0,16), Route 102 (0,17) and Route 103 (0,19) walked, anchored on
        # Petalburg (8,1): the pick is (0,19), gym-close with the higher land level, and Route
        # 101 ranks below Route 102
        gg = map_graph.MapGraph(graph_path2, world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
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

        # all 8 badges in, every Hoenn gym down, but no walkable route onto the endgame chain:
        # explore toward its first unreached map, never grind_map. a grind fallback ranks grass by
        # hops to the unreachable target and walks the party back across Hoenn (the live loop that
        # swam it west), and at cap the party is over it so a grind earns nothing. Gate every world
        # edge into Victory Road 1F.
        g5 = map_graph.MapGraph(graph_path3, world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
        g5.visited.update({(0, 16), (0, 8)})
        chain = set(planner.ENDGAME_CHAIN)
        for p, ds in rowe_rom.world_edges().items():
            for c in ds & chain:
                g5.gated[(p, c)] = frozenset({"SURF"})
        st = _status((0, 16), 8, set(range(8)), cap_level=50, johto=set(range(8)))
        st["field_moves"] = ["SURF"]
        st["goal"] = {"mode": "travel", "to": [24, 43]}
        assert g5.route((0, 16), (24, 43), field_moves=frozenset({"SURF"})) is None, "test needs no route to (24,43)"
        g5goal, g5why = planner.recommend(st, g5)
        assert g5goal["mode"] == "explore" and g5goal["to"] == [24, 43], (g5goal, g5why)
        assert g5goal["mode"] != "grind", "no grind fallback with all badges in, it walks the party across Hoenn"
        # the reason carries here, the moves it routed under, and the reachable-map count, so a bad
        # here (an interior map or a mid-warp write) is a one-line diagnosis
        assert "[0, 16]" in g5why and "['SURF']" in g5why and "reachable" in g5why, g5why

        # all 8 badges in and every Hoenn gym down, arrival at Ever Grande (0,8): the endgame chain
        # travels on into Victory Road (24,43), never grinds back west and never routes to a Sevii
        # phantom. the (0,8)->(24,43) warp is open and here != m skips the self-hop. this needs the
        # real ROM warp edges, hence the world-backed graph.
        gw = map_graph.MapGraph(graph_path3, world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
        gw.visited.add((0, 8))
        # all 16 gym flags in (8 Hoenn + 8 Johto): the guard is lifted and travel enters Victory Road
        leag = _status((0, 8), 8, set(range(8)), cap_level=50, johto=set(range(8)))
        leag["field_moves"] = ["SURF", "WATERFALL", "DIVE"]
        leaggoal, leagwhy = planner.recommend(leag, gw)
        assert leaggoal["mode"] == "travel" and leaggoal["to"] == [24, 43], (leaggoal, leagwhy)
        assert leaggoal["mode"] != "grind", leagwhy

        # 8 Hoenn badges but the 8 Johto gyms still open: the League is sealed, so the ladder routes
        # to the nearest unbeaten Johto gym, Falkner (2,7) one warp from its (0,75) exterior, and
        # never to Victory Road or the endgame chain
        assert planner.league_flags(leag) == [True] * 16, planner.league_flags(leag)
        johto_open = _status((0, 75), 8, set(range(8)), cap_level=50)
        assert planner.league_flags(johto_open) == [True] * 8 + [False] * 8
        jgoal, jwhy = planner.recommend(johto_open, gw)
        assert jgoal["mode"] == "gym" and jgoal["map"] == [2, 7], (jgoal, jwhy)

        # once Victory Road 1F (24,43) is reached it drops out of the chain; standing there the next
        # unreached target is B1F (24,44), warp-adjacent
        gw.visited.add((24, 43))
        nxt = _status((24, 43), 8, set(range(8)), cap_level=50, johto=set(range(8)))
        nxt["field_moves"] = ["SURF", "WATERFALL", "DIVE"]
        nxtgoal, nxtwhy = planner.recommend(nxt, gw)
        assert nxtgoal["mode"] == "travel" and nxtgoal["to"] == [24, 44], (nxtgoal, nxtwhy)

        # champion (FLAG_SYS_GAME_CLEAR set by the Hall of Fame): League cleared, no goal left
        champ = _status((16, 11), 8, set(range(8)), cap_level=50, johto=set(range(8)))
        champ["champion"] = True
        champgoal, champwhy = planner.recommend(champ, gw)
        assert champgoal["mode"] == "done", (champgoal, champwhy)

        # build_graph is the one graph factory both the CLI planner and the executor use, so the two
        # never route over a different neighbor set. The script-warp layer loads (the Seagallop ferry)
        # and the passed gate flags gate its arms; a graph built without that layer is ferry-blind,
        # which is why the CLI planner wrote explore from a Hoenn map while the ferry sat open.
        fdb, gpb = tempfile.mkstemp(suffix=".json")
        os.close(fdb)
        os.remove(gpb)
        try:
            fac = planner.build_graph(gpb, flags=script_decode.gate_flags(), tickets=frozenset({0x335}))
            assert fac.script, "build_graph must load the script-warp layer"
            assert fac.flags == set(script_decode.gate_flags()), fac.flags
            assert (0, 75) in fac._script_dests((13, 10)), "the mainland dock keeps One Island (0,75), ticket held"
            blind = map_graph.MapGraph(gpb, world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
            assert not blind._script_dests((13, 10)), "a graph without the script layer is ferry-blind"
            # the mainland docks only keep an island arm whose ticket is in the bag: with One Island's
            # (0x335) held the Two Island arm (0,76) is dropped so routing cannot loop on the ticketless
            # row, while the free Mt. Ember dispatcher (33,8) keeps it since it needs no ticket
            assert (0, 76) not in fac._script_dests((13, 10)), "the unticketed Two Island dock arm is dropped"
            assert (0, 76) in fac._script_dests((33, 8)), "the free dispatcher keeps the Two Island arm"
            noticket = planner.build_graph(gpb, flags=script_decode.gate_flags())
            assert (0, 75) not in noticket._script_dests((13, 10)), "no ticket held drops even the One Island dock arm"
            # a gated ferry arm needs its flag: flag 3284 opens the (13,10)->(26,9) arm
            assert (26, 9) not in planner.build_graph(gpb, flags=frozenset())._script_dests((13, 10))
            assert (26, 9) in planner.build_graph(gpb, flags=frozenset({3284}))._script_dests((13, 10))
        finally:
            if os.path.exists(gpb):
                os.remove(gpb)

        # bug2: with the ferry-aware graph the ladder reaches Johto. From a Hoenn map (0,4) at 8 Hoenn
        # badges and 0 Johto, Falkner (2,7) is routable over the Seagallop arms: One Island's ticket is
        # held, so the mainland dock reaches One Island and the free field dispatchers carry the party
        # onward with no ticket handout, and the Sevii leg heads straight at the gym, never a phantom
        # ticket clerk (the Hoenn-dock "clerk" runs the ROWE options menu, not a ticket giver).
        fdj, gpj = tempfile.mkstemp(suffix=".json")
        os.close(fdj)
        os.remove(gpj)
        try:
            gj = planner.build_graph(gpj, flags=script_decode.gate_flags(), tickets=frozenset({0x335}))
            johto = _status((0, 4), 8, set(range(8)), cap_level=50)
            johto["field_moves"] = ["SURF", "WATERFALL", "DIVE"]
            johto["tickets"] = [0x335]
            jg, jwhy = planner.recommend(johto, gj)
            assert jg["mode"] == "gym" and jg["map"] == [2, 7], (jg, jwhy)
        finally:
            if os.path.exists(gpj):
                os.remove(gpj)

        # 8 Hoenn badges and no ferry route learned (a ferry-blind graph stands in for every Sevii
        # gym gated off): the run never grinds Hoenn again, the Sevii leg explores toward a frontier
        # instead. The complement is the synthetic gym-routes case below, where the ferry is open.
        fds, gps = tempfile.mkstemp(suffix=".json")
        os.close(fds)
        os.remove(gps)
        try:
            gsev = map_graph.MapGraph(gps, world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
            sevgoal, sevwhy = planner.recommend(_status((0, 36), 8, set(range(8)), cap_level=50), gsev)
            assert sevgoal["mode"] == "explore", (sevgoal, sevwhy)
            assert sevgoal["mode"] != "grind", sevwhy
        finally:
            if os.path.exists(gps):
                os.remove(gps)

        # sevii_goal: once the 8 Hoenn badges are in, target the lowest-indexed unbeaten Sevii gym
        # from the badge table (Falkner, (2,7)) and route to it over the ferry, never nearest-by-hops
        st = {"map": [0, 79], "badges": 8, "field_moves": [],
              "badge_flags": [True] * 8, "johto_flags": [False] * 8,
              "party": [{"level": 80, "moves": [{"power": 40, "pp": 10}]}] * 6}
        fdv, gpv = tempfile.mkstemp(suffix=".json")
        os.close(fdv)
        os.remove(gpv)
        try:
            sv = map_graph.MapGraph(gpv)
            sv.cur_badges = 8
            sv.world = {(0, 79): {(13, 10)}, (13, 10): {(0, 75)}, (0, 75): {(2, 7)}}
            goal = planner.sevii_goal(sv, frozenset(), st)[0]
            # stand [4,3] is the tile below Falkner's object at (4,2), read off the ROM by leader_stand
            assert goal == {"mode": "gym", "map": [2, 7], "badges": 8, "flags": 8, "stand": [4, 3]}, goal
        finally:
            if os.path.exists(gpv):
                os.remove(gpv)
        # no ferry route to the gym: explore toward the nearest unvisited map ((0,80) one hop beats
        # (0,82) two, visited (0,81) skipped), never the gym and never the map underfoot
        fdn, gpn = tempfile.mkstemp(suffix=".json")
        os.close(fdn)
        os.remove(gpn)
        try:
            sv2 = map_graph.MapGraph(gpn)
            sv2.cur_badges = 8
            sv2.world = {(0, 79): {(0, 80), (0, 81)}, (0, 80): {(0, 82)}}
            sv2.visited.add((0, 81))
            g2 = planner.sevii_goal(sv2, frozenset(), st)[0]
            assert g2 == {"mode": "explore", "to": [0, 80], "cap": None}, g2
        finally:
            if os.path.exists(gpn):
                os.remove(gpn)

        # hops_from applies _gate_shut, the same test route uses, so a ferry gate recorded by an
        # older executor (version below the current cap) no longer hides a gym the walk can now cross,
        # while a current gate at the same badge count still does. Before this, hops_from skipped any
        # edge recorded gated under the live moves regardless of badge count or version, so it and
        # route disagreed and the planner explored a gym route could already reach.
        fdg, gpg = tempfile.mkstemp(suffix=".json")
        os.close(fdg)
        os.remove(gpg)
        try:
            mv = frozenset({"SURF"})
            stale = map_graph.MapGraph(gpg)
            stale.world = {(0, 0): {(0, 1)}, (0, 1): {(0, 2)}}
            stale.cur_badges = 8
            stale.gated[((0, 1), (0, 2))] = mv
            stale.gate_version[((0, 1), (0, 2))] = 0
            assert (0, 2) in planner.hops_from((0, 0), stale, mv), "a stale-version gate must not hide a crossable node"
            cur = map_graph.MapGraph(gpg)
            cur.world = {(0, 0): {(0, 1)}, (0, 1): {(0, 2)}}
            cur.cur_badges = 8
            cur.gated[((0, 1), (0, 2))] = mv
            cur.gate_version[((0, 1), (0, 2))] = map_graph.EXECUTOR_CAP_VERSION
            cur.gate_badges[((0, 1), (0, 2))] = 8
            assert (0, 2) not in planner.hops_from((0, 0), cur, mv), "a current gate at the same badge count hides it, same as route"
        finally:
            if os.path.exists(gpg):
                os.remove(gpg)

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
