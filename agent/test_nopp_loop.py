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

IDLE = next(iter(play.INTRO_IDLE_FUNCS))  # a controller func the no-PP box and parked list run under


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
    """Selection-script box up (comm 6) under the idle controller. _comm_action taps B each pass;
    once the box has cleared the controller returns to the action pick (choosing True), so the intro
    loop returns without ever tapping A into the box."""
    def __init__(self):
        self._reads = 0

    def controller_func(self, battler):
        return IDLE

    def comm(self, battler=0):
        self._reads += 1
        return 6

    def choosing(self, battler):
        return self._reads >= 2

    def in_battle(self):
        return True


class _ParkedMoveG:
    """Move list bounced to the idle controller (comm 3), cursor parked on the 0-PP slot 0."""
    def __init__(self):
        self.cursor = 0

    def controller_func(self, battler):
        return IDLE

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
        return IDLE


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


class _OpenBoxG:
    """A 0-PP lead pops the selection-script box (comm 6) while the Fight list is opening, under the
    idle controller; the box clears to the open move list (comm 3) once B dismisses it. This is the
    move-list open gate's path, the sibling loop _advance_intro's fix first missed."""
    def __init__(self):
        self.n = 0

    def controller_func(self, battler):
        return IDLE

    def comm(self, battler=0):
        return 6 if self.n == 0 else 3

    def in_battle(self):
        return True

    def tick(self):
        self.n += 1


def test_comm_wait_leaves_opening_box_with_b_never_mashes_the_open_key():
    g = _OpenBoxG()
    p = play.Player.__new__(play.Player)
    p.g = g
    p.presses = []

    def tap(keys, hold=8, gap=12):
        p.presses.append((keys, g.comm()))
        if keys == eb.KEY_B:
            g.tick()  # B dismisses the box; the open move list (comm 3) sits behind it
        if len(p.presses) > 200:
            raise RuntimeError("comm_wait hung")

    p.tap = tap
    p.run = lambda frames, keys=0: None
    verdict = p.comm_wait(0, lambda: g.comm() == 3, key=eb.KEY_A)
    assert verdict in ("ready", "move_list"), "the open Fight list is reached, not a timeout"
    assert (eb.KEY_A, 6) not in p.presses, "the open key at comm 6 re-opens the no-PP box"
    assert (eb.KEY_B, 6) in p.presses, "the box is left with B, not the open key"
