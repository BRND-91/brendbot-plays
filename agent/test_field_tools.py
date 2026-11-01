"""Checks field tools come on at the badge count ROWE grants them, and that a map_graph gate
blocked under a smaller tool set reopens once the set grows, so the executor re-crosses an edge the
newly earned tool can pass."""
import os
import tempfile

import play
from map_graph import MapGraph


def main() -> None:
    assert play.field_tools(0) == frozenset({"SURF", "DIVE"}), play.field_tools(0)
    assert play.field_tools(1) == frozenset({"SURF", "DIVE", "CUT"}), play.field_tools(1)
    assert play.field_tools(2) == frozenset({"SURF", "DIVE", "CUT", "WATERFALL"}), play.field_tools(2)
    assert "ROCKSMASH" in play.field_tools(4) and "ROCKSMASH" not in play.field_tools(3)
    assert "ROCKCLIMB" in play.field_tools(7) and "ROCKCLIMB" not in play.field_tools(6)
    assert "DIVE" in play.field_tools(0), "Dive Gear is a 0-badge start item, DIVE is on from the start"
    # the set only grows with badges, it never drops a tool already earned
    for b in range(8):
        assert play.field_tools(b) <= play.field_tools(b + 1), b

    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)
    try:
        g = MapGraph(path)
        g.observe((0, 0), [(0, 19)])  # (0,19) is a known but unwalked border of (0,0)
        g.block((0, 0), (0, 19), play.field_tools(0))  # gated while the party held only SURF
        surf_only, with_cut = play.field_tools(0), play.field_tools(1)
        assert (0, 19) not in g._open((0, 0), field_moves=surf_only), "edge still gated under the set it was blocked with"
        assert (0, 19) in g._open((0, 0), field_moves=with_cut), "edge did not reopen once the Axe landed"
    finally:
        if os.path.exists(path):
            os.remove(path)
    print("test_field_tools OK")


if __name__ == "__main__":
    main()
