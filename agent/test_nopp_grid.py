"""The no-PP selection-script loop, replayed from one step before the box. The live recurrence the
first fix missed enters on the action grid (gBattleCommunication[0]==2, under the choose func
0x83c12bc), not at the box: a battler steps onto the grid after a forced switch with slot 0 at 0 PP.
The old _advance_intro read comm once at entry, took the A-mash branch, and never re-read comm as the
box toggled 6<->3, so it pressed A straight into the box (comm 6) and onto the parked 0-PP slot (comm
3). The fix routes every battle choose-phase wait loop through _comm_action: B at comm 6, steer to a
PP'd slot at comm 3.

seaking_nopp_grid.ss is that comm-2 entry: Vileplume on the grid vs Starmie, the catch plan sends
Seaking out, and Seaking's slot 0 (Megahorn) is spent. Replayed with the dispatch live, the step
steers off slot 0 and confirms a PP'd move with no A at comm 6; with the dispatch disabled the same
fixture presses A at comm 6 fourteen times in six steps, the live loop. seaking_seel_nopp.ss is the
second case: the box already up at comm 6, left with B.
"""
import os

import emu_boot as eb
import play

BASE = os.path.dirname(os.path.abspath(__file__))
GRID = os.path.join(BASE, "states", "fixtures", "seaking_nopp_grid.ss")
BOX = os.path.join(BASE, "states", "fixtures", "seaking_seel_nopp.ss")


def _player(fixture: str) -> play.Player:
    e = eb.Emu()
    e.load_state(open(fixture, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-nopp-grid-test.json")
    for a in ("_wedge", "_act_stuck", "_prompt_taps", "end_taps"):
        setattr(p, a, 0)
    p._wedge_sig = p._act_sig = p._switch_active = None
    p._wild_switched = False
    return p


def _run_logged(fixture: str, steps: int) -> list:
    """Replay `steps` battle_steps, recording (key, comm, pp-under-cursor) per press. pp is the active
    battler's PP for the slot the move cursor sits on, or None off the move list."""
    p = _player(fixture)
    g = p.g
    log = []
    orig = p.tap

    def tap(keys, hold=8, gap=12):
        pp = None
        if g.in_move_list(0):
            mons = g.battlers()
            if mons:
                pp = mons[0].pp[g.move_cursor(0) & 3]
        log.append((keys, g.comm(0), pp))
        return orig(keys, hold, gap)

    p.tap = tap
    for _ in range(steps):
        if not g.in_battle():
            break
        p.battle_step()
    return log


def test_grid_entry_never_presses_a_into_the_box_or_parked_slot():
    log = _run_logged(GRID, 6)
    assert (eb.KEY_A, 6) not in [(k, c) for k, c, _ in log], \
        "an A at comm 6 re-opens the no-PP box, the live A-at-comm6 loop"
    assert not [1 for k, c, pp in log if k == eb.KEY_A and c == 3 and pp == 0], \
        "an A at comm 3 on a 0-PP slot re-confirms the move the ROM just refused"


def test_grid_entry_confirms_a_ppd_move():
    log = _run_logged(GRID, 6)
    confirms = [pp for k, c, pp in log if k == eb.KEY_A and c == 3 and pp is not None]
    assert confirms, "the step never confirmed a move off the open list"
    assert all(pp > 0 for pp in confirms), \
        "every move confirmed at comm 3 came off a slot with PP, never the parked 0-PP one"


def test_box_already_up_leaves_on_b_never_a():
    log = _run_logged(BOX, 6)
    assert (eb.KEY_A, 6) not in [(k, c) for k, c, _ in log], \
        "the box up at entry is left with B, never dismissed with an A that re-opens it"
    assert (eb.KEY_B, 6) in [(k, c) for k, c, _ in log], \
        "B is the only key that leaves the selection-script box"
