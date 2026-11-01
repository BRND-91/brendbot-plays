import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import play  # noqa: E402
import rowe_rom  # noqa: E402


def test_lavaridge_gym_spans_both_floors():
    # Lavaridge gym 1F is map (4, 1); Flannery sits top-left behind a floor of holes that drop to
    # B1F, map (4, 2), and both are one gym. The exit warp leads to Lavaridge Town (0, 12), which
    # carries overworld connections and stays out. Red if the connection filter is dropped, since
    # (0, 12) then enters, or if the BFS stops at the entry and returns just {(4, 1)}.
    assert play.gym_map_set((4, 1)) == frozenset({(4, 1), (4, 2)})


def test_interior_floors_carry_no_overworld_connection():
    for m in play.gym_map_set((4, 1)) - {(4, 1)}:
        assert rowe_rom.map_connections(*m) == []
