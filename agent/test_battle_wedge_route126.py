"""The Route 126 move-list wedge. The action func 0x83C12BC drives both the "What will X do?" grid
and the Fight move list, branching on gBattleCommunication[0] (0 or 2 on the grid, 3 in the list),
so Grid.choosing(0) reads True on both screens and cannot gate the Fight-open press. The old gate
pressed A until choosing(0) flipped, which never happens on a live list, so the A confirmed whatever
slot the cursor was parked on before steer ran: a 0-PP Last Resort slot the ROM refuses, which
wedged, or a PP'd slot that fired a move pick_move did not choose. The fix reads in_move_list, which
keys on the comm[0]==3 sub-state, skips the open when the list is already drawn, then steers to the
picked slot and confirms.

Fixture states/fixtures/stall_route126_1793564465.ss is the dumped wedge: Stoutland vs Gyarados,
cursor parked on the 0-PP Last Resort slot 0.
"""
import os

import emu_boot as eb
import play
import rowe_symbols as S

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "stall_route126_1793564465.ss")
# the wedge dump parks the cursor on the 0-PP Last Resort slot, which the ROM refuses, so it tests
# the stall clearance. PARKED is that same Stoutland fight with the cursor steered onto a PP'd slot
# the pick does not choose, which is where the old gate's A confirmed the wrong move before steering.
PARKED = os.path.join(BASE, "states", "fixtures", "movelist_parked_pp.ss")


def _player(fixture: str = FIXTURE) -> play.Player:
    e = eb.Emu()
    e.load_state(open(fixture, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-wedge-test.json")
    for a in ("_wedge", "_act_stuck", "_prompt_taps", "end_taps"):
        setattr(p, a, 0)
    p._wedge_sig = p._act_sig = p._switch_active = None
    p._wild_switched = False
    return p


def test_fixture_is_the_move_list_not_the_grid():
    p = _player()
    b, _, _ = p.sides()
    assert p.g.choosing(b), "controller should sit on the shared choose func"
    assert p.g.in_move_list(b), "comm[0]==3 should mark the move list open on this dump"
    assert p.g.move_cursor(b) == 0, "fixture should park the cursor on the 0-PP Last Resort slot"


def test_route126_move_list_wedge_advances():
    p = _player()
    start = p.g.script_instr()
    for _ in range(15):
        if not p.g.in_battle():
            break
        try:
            p.battle_step()
        except Exception as ex:
            assert False, f"battle_step wedged ({type(ex).__name__}) before advancing the turn"
        if p.g.script_instr() != start:
            break
    assert p.g.script_instr() != start, (
        "battle_step never advanced the turn off the move-list wedge; the Fight-open gate looped "
        "pressing A on the refused Last Resort slot instead of steering to a usable move")


def test_route126_fires_the_picked_move_not_the_parked_slot():
    p = _player(PARKED)
    b, me, foes = p.sides()
    moves = list(me.moves)
    parked = p.g.move_cursor(b)
    pick = p.pick_move(me, foes)
    assert pick != parked, "fixture must park a different slot than the pick to test the misfire"
    assert me.pp[parked] > 0, "the parked slot must have PP, else the ROM refusal masks the misfire"
    assert p.g.in_move_list(b), "fixture should have the move list open on a PP'd parked slot"
    fired = None
    for _ in range(15):
        if not p.g.in_battle():
            break
        try:
            p.battle_step()
        except Exception as ex:
            assert False, f"battle_step wedged ({type(ex).__name__}) before firing a move"
        raw = p.e.read(S.addr("gCurrentMove"), 2)
        mv = raw[0] | (raw[1] << 8)
        if mv in moves and mv != 0:
            fired = mv
            break
    assert fired == moves[pick], (
        f"fired move {fired} is not the picked slot {pick} ({moves[pick]}); the old gate confirmed "
        f"the parked slot {parked} ({moves[parked]}) before steering to the pick")
