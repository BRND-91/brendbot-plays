"""The Sevii run as the planner sequences it: badge order, each gym's island, the ticket that island's
row needs on a mainland dock, and the dispatcher handing that ticket. ISLAND_TICKETS is pinned to the
ROM's dispatcher script, where menu row k checkitems ticket k+1 and warps by the same row, so a wrong
row or a mis-ordered island goes red here before it strands the walk. Falkner, Bugsy and the Three
Island arm are the live controls (two badges in, tickets 1..3 in the bag, the gym route next was
Whitney over the Slateport dock whose Three Island row the old table dropped)."""
import os
import struct

import planner
import rowe_rom as R
import script_decode as sd

ROW_DISPATCH, WARP_TABLE = 0x082F1CC9, 0x082F22EC
SLATEPORT_DOCK, THREE_ISLAND, THREE_TICKET = (9, 9), (0, 79), 0x337


def _rom_rows() -> list:
    """(ticket item, warp dest map) per dispatcher row, read off the shared dispatcher script."""
    rom = R._rom()
    lo, hi = R._fo(ROW_DISPATCH), R._fo(ROW_DISPATCH) + 0x240
    out = []
    for k in range(8):
        i = rom.find(bytes([0x21, 0x00, 0x80, k, 0x00]), lo, hi)   # compare VAR_0x8000, k
        tgt = R._fo(struct.unpack_from("<I", rom, i + 7)[0])        # goto_if eq -> row block
        j = rom.find(b"\x47", tgt, tgt + 40)                          # checkitem
        item = struct.unpack_from("<H", rom, j + 1)[0]
        w = R._fo(WARP_TABLE) + k * 13                                # warp row k: 39 group num ...
        out.append((item, (rom[w + 1], rom[w + 2])))
    return out


def test_island_tickets_match_the_dispatcher_rows():
    rows = _rom_rows()
    assert {dest: item for item, dest in rows} == sd.ISLAND_TICKETS, rows


def test_legs_run_in_badge_order_over_the_landing_maps():
    assert [b for b, _g, _i in planner.SEVII_LEGS] == list(range(8, 16))
    assert [g for _b, g, _i in planner.SEVII_LEGS] == sorted(planner.JOHTO_GYM, key=planner.JOHTO_GYM.get)
    assert [i for _b, _g, i in planner.SEVII_LEGS] == [dest for _item, dest in _rom_rows()]


def test_three_island_arm_opens_on_its_ticket():
    assert sd.passable_island_arm(SLATEPORT_DOCK, THREE_ISLAND, frozenset({0x335, 0x336}))is False
    assert sd.passable_island_arm(SLATEPORT_DOCK, THREE_ISLAND, frozenset({THREE_TICKET}))


def test_dock_has_no_self_arm():
    assert SLATEPORT_DOCK not in planner.script_layer(frozenset({THREE_TICKET}))[SLATEPORT_DOCK]


def test_island_center_serves_a_heal_and_a_buy_sails():
    # Two Island holds a Center and no Mart: a heal stays there, a buy routes to a Mart town
    import play
    p = play.Player.__new__(play.Player)
    p.graph = type("_G", (), {"nearest_all": lambda self, here, towns, blocked: [min(towns)]})()
    p.region = lambda: (0, 76, 10, 7)
    p._blocked_from = lambda region: set()
    assert play.SERVICE[(0, 76)] == ((1, 7), None)
    assert p.service_town((0, 76)) == (0, 76)
    assert p.service_town((1, 7)) == (0, 76), "inside the island Center still serves the heal"


def test_whitney_leg_routes_over_the_slateport_dock(tmp_path):
    graph = planner.build_graph(os.path.join(str(tmp_path), "map_graph.json"),
                                tickets=frozenset({0x335, 0x336, THREE_TICKET}))
    status = {"map": [0, 1], "badges": 10, "badge_flags": [True] * 8, "tickets": [0x335, 0x336, THREE_TICKET],
              "johto_flags": [True, True] + [False] * 6, "party": [], "field_moves": ["SURF"]}
    goal, why = planner.sevii_goal(graph, frozenset({"SURF"}), status)
    assert goal["map"] == [2, 9] and "ticket 0x337 held" in why, (goal, why)
    assert graph.route((9, 9), (2, 9), field_moves=frozenset({"SURF"})) == THREE_ISLAND
