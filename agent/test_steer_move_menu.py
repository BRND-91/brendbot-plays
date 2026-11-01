"""steer_move_cursor must never press A while the Fight list is open on a spent slot. The list
defaults the cursor to slot 0, and on Pawmot that slot is a 0-PP Supercell Slam; confirming it in a
double battle wedges the player's controller at 0x83aa958 with no input able to recover (the frozen
Golbat+Lunatone double on map [24, 0]). A dropped open-probe tap used to fall through to a blind A."""
import emu_boot as eb
import play

ZERO_PP = (0, 10, 5, 20)  # slot 0 spent, the Supercell Slam case
DOWN_NEIGHBOR = {0: 2, 1: 3, 2: 2, 3: 3}
UP_NEIGHBOR = {0: 0, 1: 1, 2: 0, 3: 1}


class FakeGame:
    def __init__(self, drops):
        self.mc = 0          # Fight list open, cursor on the spent lead move
        self.drops = drops   # open-probe taps the menu eats mid-draw before it responds

    def move_cursor(self, battler=0):
        return self.mc

    def action_cursor(self, battler=0):
        return 0             # list is open, the action grid never moves


class FakePlayer:
    def __init__(self, drops):
        self.g = FakeGame(drops)
        self.taps = []

    def run(self, frames, keys=0):
        pass

    def tap(self, key, *a, **k):
        self.taps.append(key)
        g = self.g
        if key == eb.KEY_DOWN:
            if g.drops > 0:
                g.drops -= 1   # dropped, cursor holds
            else:
                g.mc = DOWN_NEIGHBOR[g.mc]
        elif key == eb.KEY_UP:
            g.mc = UP_NEIGHBOR[g.mc]


def test_no_blind_confirm_on_dropped_probe():
    p = FakePlayer(drops=2)
    play.Player.steer_move_cursor(p, 0, 2)   # target Close Combat, slot 2, has PP
    assert eb.KEY_A not in p.taps, f"steer confirmed a move itself, taps {p.taps}"
    assert p.g.mc == 2, f"cursor did not reach the PP target, at {p.g.mc}"


def test_reaches_target_without_drops():
    p = FakePlayer(drops=0)
    play.Player.steer_move_cursor(p, 0, 2)
    assert eb.KEY_A not in p.taps, f"steer confirmed a move itself, taps {p.taps}"
    assert p.g.mc == 2


if __name__ == "__main__":
    for name in ("test_no_blind_confirm_on_dropped_probe", "test_reaches_target_without_drops"):
        globals()[name]()
        print(f"{name}: passed")
