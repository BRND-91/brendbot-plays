"""throw_ball returns when the bag cursor never reaches row 0 or the bag never opens.

bag_position reads gBagPosition whether or not the bag is on screen, so a stale cursor must
not keep the routine pressing UP; a loop that never returns also starves the status writer
and the stall detector in the main loop."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb
import rowe_symbols as S
from play import Player

HANG = 300  # presses; the real routine needs under 30


class G:
    def __init__(self, cb2: int, cursor: int):
        self.cb2, self.cursor = cb2, cursor

    def callback2(self) -> int:
        return self.cb2

    def bag_position(self) -> tuple:
        return S.BAG_POCKET_POKE_BALLS, self.cursor

    def in_battle(self) -> bool:
        return True


class E:
    """Emulator double for the back-out dump; the real routine saves state + png on no bag open."""
    def save_state(self) -> bytes:
        return b""

    def save_png(self, path: str) -> None:
        pass


def player(g: G) -> Player:
    p = Player.__new__(Player)
    p.g = g
    p.e = E()
    p.keys = []

    def tap(keys: int, hold: int = 8, gap: int = 12) -> None:
        p.keys.append(keys)
        if len(p.keys) > HANG:
            raise RuntimeError("throw_ball hung")

    p.tap = tap
    p.run = lambda frames, keys=0: None
    return p


def test_bag_cursor_stuck_off_row_zero_returns():
    p = player(G(S.CB2_BAG_MAIN, cursor=3))
    p.throw_ball()
    assert len(p.keys) < HANG


def test_bag_never_opened_backs_out_with_b():
    p = player(G(0x8000000, cursor=0))
    p.throw_ball()
    # one A is the open attempt; another A outside the bag fires whatever the cursor sits on
    assert p.keys.count(eb.KEY_A) == 1
    assert p.keys[-1] == eb.KEY_B
