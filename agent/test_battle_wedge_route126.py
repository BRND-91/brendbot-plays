"""The Route 126 move-list wedge. A wild single (flags 0xc) leaves battler 0's controller on the
move-select func 0x83C12BC, which is in PLAYER_CHOOSE_ACTION_FUNCS, so Grid.choosing(0) reads True
with the move list already drawn. battle_step's Fight-open gate presses A until choosing(0) flips,
which never happens, so the A lands on the drawn cursor (slot 0, Last Resort, 0 PP) the ROM refuses
and the turn never advances until the 12-step WEDGE dump. The fix steers and confirms from the live
move list instead of looping the open.

Fixture states/fixtures/stall_route126_1793564465.ss is the dumped wedge: Stoutland vs Gyarados,
cursor on the 0-PP Last Resort slot.
"""
import os

import emu_boot as eb
import play

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "stall_route126_1793564465.ss")


def _player() -> play.Player:
    e = eb.Emu()
    e.load_state(open(FIXTURE, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-wedge-test.json")
    for a in ("_wedge", "_act_stuck", "_prompt_taps", "end_taps"):
        setattr(p, a, 0)
    p._wedge_sig = p._act_sig = p._switch_active = None
    p._wild_switched = False
    return p


def test_route126_move_list_wedge_advances():
    p = _player()
    b, _, _ = p.sides()
    assert p.g.move_cursor(b) == 0, "fixture should park the cursor on the 0-PP Last Resort slot"
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
