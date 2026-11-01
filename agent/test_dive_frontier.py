"""Player._dive_frontier submerges through a diveable tile to cross onto a cluster the ROM
connection table never links (the Dive onto the Sootopolis island), so explore grows adjacency
across the boundary instead of demoting straight to a grind the moment the walkable frontier is
mapped out. The bug it fixes is explore never diving off the recorded graph; pinning the helper to
always-False (its pre-fix behavior) reds the crossing cases below."""
import rowe_map
from play import Player

REGION = (15, 0, (0, 0))


def _player(result: str):
    calls = []

    class Errands:
        @staticmethod
        def take_dive(direction, surf=False, tools=frozenset()):
            calls.append(direction)
            return result

    p = Player.__new__(Player)
    p.errands = Errands()
    p._dived = set()
    return p, calls


def main() -> None:
    surf_dive = frozenset({"SURF", "DIVE"})

    # a reachable dive that changes the map crossed the boundary
    p, calls = _player("map_changed")
    assert p._dive_frontier(REGION, surf_dive) is True
    assert calls == [rowe_map.DIR_DIVE], calls

    # a wild battle mid-dive still counts as progress, the stream keeps feeding
    p, _ = _player("battle")
    assert p._dive_frontier(REGION, surf_dive) is True

    # no diveable tile reachable: take_dive reports unreachable, so fall back to the grind
    p, _ = _player("unreachable")
    assert p._dive_frontier(REGION, surf_dive) is False

    # DIVE not held: never attempt
    p, calls = _player("map_changed")
    assert p._dive_frontier(REGION, frozenset({"SURF"})) is False
    assert calls == [], "dived without the move"

    # the same area is tried once: a bounced dive does not re-fire every explore tick
    p, calls = _player("stuck")
    assert p._dive_frontier(REGION, surf_dive) is False
    assert p._dive_frontier(REGION, surf_dive) is False
    assert calls == [rowe_map.DIR_DIVE], "re-dived the same area"

    print("test_dive_frontier OK")


if __name__ == "__main__":
    main()
