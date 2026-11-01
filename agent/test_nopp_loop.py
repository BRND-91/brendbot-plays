"""The Seaking/Seel no-PP loop. On a wild turn where every move is out of PP, the ROM holds the
battler under the selection-script box (gBattleCommunication[b] == 6) and bounces the move list to
the idle controller 0x83aa958 (comm 3), so choosing(b) reads False and the intro branch mashed A.
Each A at comm 3 re-confirmed the parked 0-PP slot and each A at comm 6 dismissed the box, which
re-opened, looping forever. The fix: _advance_intro reads comm directly. At comm 6 it only presses
B until the box is gone; at comm 3 it steers to a PP'd slot and confirms rather than re-pressing A.

These pin the key-sequence from the press log alone (no fixture): B at comm 6, steer+confirm at
comm 3. The emulator red/green over a full wild battle runs from states/fixtures/seaking_seel_nopp.ss
once the live play-in captures the in-battle wedge.
"""
import types

import emu_boot as eb
import play


def _player(g) -> play.Player:
    p = play.Player.__new__(play.Player)
    p.g = g
    p.keys = []

    def tap(keys, hold=8, gap=12):
        p.keys.append(keys)
        if len(p.keys) > 200:
            raise RuntimeError("_advance_intro hung")

    p.tap = tap
    p.run = lambda frames, keys=0: None
    return p


class _BoxG:
    """Selection-script box up (comm 6) for the first reads, then B dismisses it and the turn moves
    on (in_battle goes False), so the loop exits without mashing A. choosing() stays False."""
    def __init__(self):
        self._reads = 0

    def comm(self, battler=0):
        self._reads += 1
        return 6 if self._reads <= 2 else 0

    def choosing(self, battler):
        return False

    def in_battle(self):
        return self._reads <= 2


class _ParkedMoveG:
    """Move list bounced to the idle controller (comm 3), cursor parked on the 0-PP slot 0."""
    def __init__(self):
        self.cursor = 0

    def comm(self, battler=0):
        return 3

    def choosing(self, battler):
        return False

    def in_battle(self):
        return True

    def move_cursor(self, battler=0):
        return self.cursor

    def battle_type_flags(self):
        return 0


def test_selection_box_leaves_on_b_never_a():
    g = _BoxG()
    p = _player(g)
    p._advance_intro(0, None, [])
    assert eb.KEY_B in p.keys, "the no-PP box is left with B"
    assert p.keys.count(eb.KEY_A) == 0, "an A re-opens the box, so none goes out at comm 6"


def test_parked_move_list_steers_to_pp_slot_and_confirms():
    g = _ParkedMoveG()
    me = types.SimpleNamespace(pp=[0, 0, 10, 10])
    p = _player(g)
    p.pick_move = lambda me_, foes_: 2
    p.steer_move_cursor = lambda battler, target: setattr(g, "cursor", target)
    p._advance_intro(0, me, [])
    assert g.cursor == 2, "cursor steered off the parked 0-PP slot onto the pick"
    assert me.pp[g.cursor] > 0, "the confirmed slot has PP"
    assert p.keys.count(eb.KEY_A) == 1, "one A confirms the PP'd move, never the parked 0-PP slot"


class _ToggleG:
    """The live recurrence the first pass missed. _advance_intro enters on the action grid (comm 2,
    e.g. just after a forced switch sent the no-PP mon out), and the no-PP box then toggles comm
    6<->3 under the idle controller while the intro A-mash runs. Reading comm once at entry took the
    A-mash branch, which re-polled choosing but never re-read comm, so it tapped A straight into the
    box every other frame (the A-at-comm6 loop the watcher caught). comm here advances one frame per
    press, so a loop that re-reads it each pass sees the 6 and presses B."""
    def __init__(self):
        self.n = 0
        self.cursor = 0

    def cur(self) -> int:
        if self.n == 0:
            return 2
        return 6 if self.n % 2 else 3

    def tick(self) -> None:
        self.n += 1

    def comm(self, battler=0):
        return self.cur()

    def choosing(self, battler):
        return False

    def in_battle(self):
        return True

    def move_cursor(self, battler=0):
        return self.cursor

    def battle_type_flags(self):
        return 0

    def controller_func(self, battler):
        return 0


def test_box_toggling_mid_intro_never_mashes_a_at_comm6():
    g = _ToggleG()
    p = play.Player.__new__(play.Player)
    p.g = g
    p.presses = []

    def tap(keys, hold=8, gap=12):
        p.presses.append((keys, g.cur()))
        g.tick()
        if len(p.presses) > 200:
            raise RuntimeError("_advance_intro hung")

    p.tap = tap
    p.run = lambda frames, keys=0: None
    p._battle_pulse = lambda: 0
    p.pick_move = lambda me_, foes_: 1
    p.steer_move_cursor = lambda battler, target: setattr(g, "cursor", target)
    me = types.SimpleNamespace(pp=[0, 10, 0, 0])
    p._advance_intro(0, me, [])
    assert (eb.KEY_A, 6) not in p.presses, "an A at comm 6 re-dismisses the no-PP box, which reopens"
    assert (eb.KEY_B, 6) in p.presses, "the box is left with B when it toggles up mid-intro"
