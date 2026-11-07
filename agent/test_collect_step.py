"""collect_step skips an item only on a verdict about the item: a walk cut short by a wild
battle leaves it on the list, an open-side failure or a press that took nothing retires it.
collectable_items lists the map's hidden-item BgEvents beside its item balls, flagged off
FLAG_HIDDEN_ITEMS_START, w/ a side at the event's elevation, so the same detour searches them out."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rowe_map  # noqa: E402
import rowe_rom  # noqa: E402
import rowe_symbols as S  # noqa: E402
from play import Player  # noqa: E402

BALL = (43, 8, 99, "ball", None)
HERE = (0, 36)
HEART_SCALE, HIDDEN_FLAG_ID = 125, 0x2C


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

    def collect_item(self, ball: tuple, surf: bool, elev=None) -> str:
        self.calls += 1
        return self.result


def player(result: str, got: bool = False) -> Player:
    p = Player.__new__(Player)
    p.g = G(got)
    p.errands = Errands(result)
    p._item_skip = set()
    p.collectable_items = lambda: [BALL]
    p.field_moves = lambda: set()
    return p


class Grid:
    """The tile below the ball and one beside the hidden item are reachable; the hidden item's side
    sits at `side_elev`."""

    def __init__(self, side_elev: int):
        self.side_elev = side_elev

    def reachable(self, origin: tuple, surf: bool) -> set:
        return {(43, 10), (43, 9), (20, 5)}

    def cell(self, x: int, y: int) -> int:
        return (self.side_elev if (x, y) == (20, 5) else 1) << S.GRID_ELEVATION_SHIFT


def test_hidden_items_join_the_detour() -> None:
    """One ball below the party and one hidden Heart Scale at (20,4), elevation 3, w/ a reachable
    side at 3: both list, the ball first by distance, the hidden item flagged off
    FLAG_HIDDEN_ITEMS_START. The same side at elevation 1 drops it, and so does a set hidden flag."""
    p = Player.__new__(Player)
    p._item_skip, p.e = set(), None
    p.field_moves = lambda: set()
    flags = set()
    p.g = type("G", (), {"position": staticmethod(lambda: (43, 10) + HERE), "flag": staticmethod(lambda f: f in flags)})()
    rowe_map.item_balls, rowe_rom.hidden_items = (lambda emu: [(43, 8, 99)]), (lambda g, n: [(20, 4, HEART_SCALE, HIDDEN_FLAG_ID, 3)])
    hidden = (20, 4, S.FLAG_HIDDEN_ITEMS_START + HIDDEN_FLAG_ID, "hidden", 3)
    p._grid = lambda: Grid(3)
    assert p.collectable_items() == [BALL, hidden]
    p._grid = lambda: Grid(1)
    assert p.collectable_items() == [BALL], "a side under the event's elevation gets no answer to the press"
    p._grid = lambda: Grid(3)
    flags.add(S.FLAG_HIDDEN_ITEMS_START + HIDDEN_FLAG_ID)
    assert p.collectable_items() == [BALL], "a searched-out hidden item is off the list"


def main() -> None:
    p = player("battle")
    assert p.collect_step() is True and p._item_skip == set(), "a battle on the way keeps the ball in play"
    p = player("unreachable")
    assert p.collect_step() is True and p._item_skip == {(HERE, 43, 8)}, "no open side retires it"
    p = player("got")
    assert p.collect_step() is True and p._item_skip == {(HERE, 43, 8)}, "a press that took nothing retires it"
    p = player("got", got=True)
    assert p.collect_step() is True and p._item_skip == set(), "a pickup needs no skip"
    test_hidden_items_join_the_detour()
    print("test_collect_step: 5 passed")


if __name__ == "__main__":
    main()
