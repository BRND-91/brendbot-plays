"""confirm_move is the only A pressed inside the Fight list, so the 0-PP wedge pin lives here. The list
defaults the cursor to slot 0, and on Pawmot that slot is a 0-PP Supercell Slam; confirming it in a
double battle wedges the player's controller at 0x83aa958 with no input able to recover (the frozen
Golbat+Lunatone double on map [24, 0]). steer_move_cursor presses no A at all, so a steer that runs
out of retries on the spent slot is caught here or nowhere."""
import emu_boot as eb
import play

ZERO_PP = (0, 10, 5, 20)  # slot 0 spent, the Supercell Slam case
DOWN_NEIGHBOR = {0: 2, 1: 3, 2: 2, 3: 3}
UP_NEIGHBOR = {0: 0, 1: 1, 2: 0, 3: 1}


class FakeMon:
    pp = ZERO_PP


class FakeGame:
    def __init__(self, drops, double=False):
        self.mc = 0          # Fight list open, cursor on the spent lead move
        self.drops = drops   # steer taps the list eats mid-draw before it responds
        self.double = double

    def move_cursor(self, battler=0):
        return self.mc

    def battle_type_flags(self):
        return play.BATTLE_TYPE_DOUBLE if self.double else 0

    def chooser(self):
        return 0


class FakePlayer:
    def __init__(self, drops=0, double=False):
        self.g = FakeGame(drops, double)
        self.taps = []

    def run(self, frames, keys=0):
        pass

    wait_until = play.Player.wait_until

    def tap(self, key, *a, **k):
        self.taps.append(key)
        g = self.g
        if key == eb.KEY_DOWN:
            if g.drops > 0:
                g.drops -= 1
            else:
                g.mc = DOWN_NEIGHBOR[g.mc]
        elif key == eb.KEY_UP:
            g.mc = UP_NEIGHBOR[g.mc]


def steer_then_confirm(p, target):
    play.Player.steer_move_cursor(p, 0, target)
    return play.Player.confirm_move(p, 0, FakeMon())


def test_spent_slot_backs_out():
    p = FakePlayer()
    assert play.Player.confirm_move(p, 0, FakeMon()) is False
    assert eb.KEY_A not in p.taps, f"confirmed a 0-PP move, taps {p.taps}"
    assert p.taps == [eb.KEY_B], f"expected one B back to the grid, taps {p.taps}"


def test_steer_exhausted_on_spent_slot_never_confirms():
    # more eaten taps than MOVE_STEER_RETRIES: the cursor never leaves slot 0
    p = FakePlayer(drops=play.MOVE_STEER_RETRIES + 2)
    assert steer_then_confirm(p, 2) is False
    assert p.g.mc == 0
    assert eb.KEY_A not in p.taps, f"confirmed the parked 0-PP move, taps {p.taps}"


def test_steer_with_drops_confirms_target():
    p = FakePlayer(drops=2)
    assert steer_then_confirm(p, 2) is True
    assert p.g.mc == 2
    assert p.taps.count(eb.KEY_A) == 1, f"single battle wants one A, taps {p.taps}"


def test_double_locks_target():
    p = FakePlayer(double=True)
    p.g.mc = 2
    assert play.Player.confirm_move(p, 0, FakeMon()) is True
    assert p.taps == [eb.KEY_A, eb.KEY_A], f"double wants move A + target A, taps {p.taps}"


if __name__ == "__main__":
    for name in ("test_spent_slot_backs_out", "test_steer_exhausted_on_spent_slot_never_confirms",
                 "test_steer_with_drops_confirms_target", "test_double_locks_target"):
        globals()[name]()
        print(f"{name}: passed")
