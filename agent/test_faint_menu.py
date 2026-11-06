"""The intro A-mash into the forced-switch menu. A turn played out under _advance_intro fainted
the lead and the ROM opened the party menu w/ the cursor on the fainted slot; the loop re-checked
only choosing() and in_battle(), so its remaining A presses each picked the fainted mon ("no energy
left to battle!", six A's on Golduck hp 0/265 in the Four Island gym log) before party_menu_step
got a step. The loop now yields the moment gMain.callback2 is the party menu."""
import play
import rowe_symbols as S
import emu_boot as eb

PARTY_MENU = next(iter(S.CB2_PARTY_MENU))
IDLE = next(iter(play.INTRO_IDLE_FUNCS))


class _FaintG:
    """Turn playback under the idle controller; the first A plays the turn out and the lead faints,
    so every read after it sees the party menu."""
    def __init__(self):
        self.cb2 = S.CB2_BATTLE_MAIN

    def callback2(self):
        return self.cb2

    def controller_func(self, battler):
        return IDLE

    def comm(self, battler=0):
        return 0

    def choosing(self, battler):
        return False

    def in_battle(self):
        return True


def test_intro_mash_stops_at_the_forced_switch_menu():
    g = _FaintG()
    p = play.Player.__new__(play.Player)
    p.g = g
    p.presses = []

    def tap(keys, hold=8, gap=12):
        p.presses.append((keys, g.cb2))
        if keys == eb.KEY_A:
            g.cb2 = PARTY_MENU
        if len(p.presses) > 200:
            raise RuntimeError("_advance_intro hung")

    p.tap = tap
    p.run = lambda frames, keys=0: None
    p._battle_pulse = lambda: 0
    p._advance_intro(0, None, [])
    assert (eb.KEY_A, PARTY_MENU) not in p.presses, "an A on the party menu picks the fainted slot"
    assert p.presses.count((eb.KEY_A, S.CB2_BATTLE_MAIN)) == 1, "one A played the turn out, then the loop yielded"
