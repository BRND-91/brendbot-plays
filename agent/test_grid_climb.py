"""Player._grid is the one place a live-frame grid is built, so climb is set from the Waterfall
Tool on every reachability read. A bare Grid(self.e) anywhere else leaves climb False and hides
the half of a map that sits above a waterfall, which stranded the party at Ever Grande with the
upper-plateau exits unseen. One test guards the single build site, one proves the climb opens the
plateau the bare grid missed."""
import inspect
import os

import emu_boot as eb
import nav
import play

BASE = os.path.dirname(os.path.abspath(__file__))
EVERGRANDE = os.path.join(BASE, "states", "fixtures", "evergrande_0_8.ss")
# a (0,8) upper-plateau tile the surfer reaches only after climbing the fall; unreachable on foot
# from the lower landing, so its presence in the reach set is the climb working
PLATEAU_TILE = (18, 43)


def no_bare_grid_outside_helper() -> None:
    src = open(play.__file__).read()
    in_helper = inspect.getsource(play.Player._grid).count("Grid(self.e)")
    total = src.count("Grid(self.e)")
    assert in_helper == 1, f"_grid should build the grid once, builds {in_helper}"
    assert total == in_helper, f"{total - in_helper} bare Grid(self.e) outside _grid; route them through self._grid()"


def helper_climbs_the_plateau() -> None:
    e = eb.Emu()
    with open(EVERGRANDE, "rb") as f:
        e.load_state(f.read())
    p = play.Player(e, play.NullStreamer())
    x, y, _, _ = p.g.position()
    surf = "SURF" in p.field_moves()
    helper = set(p._grid().reachable((x, y), surf))
    bare = set(nav.Grid(e).reachable((x, y), surf))
    assert len(helper) > len(bare), f"helper reach {len(helper)} not past bare {len(bare)}, climb never set"
    assert PLATEAU_TILE in helper, f"{PLATEAU_TILE} unreached with climb on"
    assert PLATEAU_TILE not in bare, f"{PLATEAU_TILE} reachable without climb, pick a climb-gated tile"


def main() -> None:
    no_bare_grid_outside_helper()
    helper_climbs_the_plateau()
    print("test_grid_climb: ok")


if __name__ == "__main__":
    main()
