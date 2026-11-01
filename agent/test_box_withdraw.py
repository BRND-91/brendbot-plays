"""_withdraw drives the storage withdraw grid off button presses with no read-back on the in-box
cursor. It reaches the grid through the box title and turns pages until the stored current box
matches the target, stepping toward it so a target behind the open box wraps or steps back instead
of stopping short on an empty box and pressing A on a blank slot."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb
import rowe_symbols as S
from routines import Errands


class FakeStorage:
    """The box UI as the hand moves through it: a main menu, then a grid whose cursor climbs to the
    box title. On the title RIGHT turns to the next box and wraps to the first; LEFT turns to the
    previous box when `left_works`, otherwise it does nothing, the build the fallback RIGHT covers.
    `n_boxes` is the real box count, which ROWE sets above S.PC_BOX_COUNT. `drops` RIGHT presses on
    the title register nothing, the input drop the read-back absorbs."""

    def __init__(self, start_box: int, drops: int = 0, n_boxes: int = S.PC_BOX_COUNT, left_works: bool = True):
        self.menu = 0
        self.box = start_box
        self.n_boxes = n_boxes
        self.left_works = left_works
        self.phase = "menu"
        self.on_title = False
        self.row = 0
        self.col = 0
        self.drops = drops
        self.landed = None

    def read(self, addr: int, n: int = 1) -> bytes:
        if addr == S.BOX_MENU_CURSOR:
            return bytes([self.menu])
        return bytes(n)

    def current_box(self) -> int:
        return self.box

    def press(self, key: int) -> None:
        if self.phase == "menu":
            if key == eb.KEY_DOWN:
                self.menu = min(self.menu + 1, 4)
            elif key == eb.KEY_UP:
                self.menu = max(self.menu - 1, 0)
            elif key == eb.KEY_A:
                self.phase, self.row, self.col, self.on_title = "grid", 0, 0, False
            return
        if self.on_title:
            if key == eb.KEY_RIGHT:
                if self.drops > 0:
                    self.drops -= 1
                else:
                    self.box = (self.box + 1) % self.n_boxes
            elif key == eb.KEY_LEFT and self.left_works:
                self.box = (self.box - 1) % self.n_boxes
            elif key == eb.KEY_DOWN:
                self.on_title, self.row, self.col = False, 0, S.BOX_TITLE_DROP_COL
            return
        if key == eb.KEY_UP:
            if self.row == 0:
                self.on_title = True
            else:
                self.row -= 1
        elif key == eb.KEY_DOWN:
            self.row = min(self.row + 1, 4)
        elif key == eb.KEY_LEFT:
            self.col = max(self.col - 1, 0)
        elif key == eb.KEY_RIGHT:
            self.col = min(self.col + 1, S.BOX_GRID_COLS - 1)
        elif key == eb.KEY_A and self.landed is None:
            self.landed = (self.box, self.row * S.BOX_GRID_COLS + self.col)


def withdraw(start_box: int, box_slot: int, drops: int = 0, n_boxes: int = S.PC_BOX_COUNT,
             left_works: bool = True) -> FakeStorage:
    m = FakeStorage(start_box, drops, n_boxes, left_works)
    e = Errands.__new__(Errands)
    e.e, e.g, e.log = m, m, lambda s: None
    e.run = lambda frames, keys=0: None
    e.tap = lambda key: m.press(key)
    e._withdraw(box_slot)
    return m


def test_withdraw_lands_on_the_target_box_and_slot():
    # box_slot 49 is box 1 position 19: column 1, row 3
    assert withdraw(start_box=0, box_slot=49).landed == (1, 19)


def test_a_dropped_page_turn_is_pressed_again_not_counted_short():
    m = withdraw(start_box=0, box_slot=49, drops=1)
    assert m.landed == (1, 19), f"a dropped RIGHT must not leave the hand a box short, got {m.landed}"


def test_already_on_the_target_box_still_enters_at_the_known_column():
    assert withdraw(start_box=1, box_slot=49).landed == (1, 19)


def test_a_target_behind_the_open_box_steps_back_instead_of_overshooting():
    # the open box is 1, the mon is box 0 position 25; LEFT turns one page back to it
    m = withdraw(start_box=1, box_slot=25, n_boxes=16)
    assert m.landed == (0, 25), f"must reach box 0, not an empty page, got {m.landed}"


def test_a_right_only_build_wraps_forward_to_a_box_behind_it():
    # ROWE holds 16 boxes and LEFT is dead, so box 1 -> box 0 wraps past box 16 rather than stopping
    m = withdraw(start_box=1, box_slot=25, n_boxes=16, left_works=False)
    assert m.landed == (0, 25), f"RIGHT-only must wrap all the way to box 0, got {m.landed}"
