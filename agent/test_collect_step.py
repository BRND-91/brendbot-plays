"""collect_step skips a ball only on a verdict about the ball: a walk cut short by a wild
battle leaves it on the list, an open-side failure or a press that took nothing retires it."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from play import Player

BALL = (43, 8, 99)
HERE = (0, 36)


class G:
    def __init__(self, got: bool):
        self.got = got

    def position(self) -> tuple:
        return (43, 10) + HERE

    def flag(self, flag_id: int) -> bool:
        return self.got


class Errands:
    def __init__(self, result: str):
        self.result = result
        self.calls = 0

    def collect_item(self, ball: tuple, surf: bool) -> str:
        self.calls += 1
        return self.result


def player(result: str, got: bool = False) -> Player:
    p = Player.__new__(Player)
    p.g = G(got)
    p.errands = Errands(result)
    p._item_skip = set()
    p.collectable_balls = lambda: [BALL]
    p.field_moves = lambda: set()
    return p


def main() -> None:
    p = player("battle")
    assert p.collect_step() is True and p._item_skip == set(), "a battle on the way keeps the ball in play"
    p = player("unreachable")
    assert p.collect_step() is True and p._item_skip == {(HERE, 43, 8)}, "no open side retires it"
    p = player("got")
    assert p.collect_step() is True and p._item_skip == {(HERE, 43, 8)}, "a press that took nothing retires it"
    p = player("got", got=True)
    assert p.collect_step() is True and p._item_skip == set(), "a pickup needs no skip"
    print("test_collect_step: 4 passed")


if __name__ == "__main__":
    main()
