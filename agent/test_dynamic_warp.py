"""A dynamic warp (header dest (127,127)) is no edge until a script edge names its real target, so
world_edges drops it and map_graph.neighbors never hands it back. Group-25 League rooms like (25,25)
warp only through dynamic doors the room script sets; before the fix their only border was the phantom
(127,127), so the explorer re-entered them forever (the (13,22) loop in states/grind.log)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import map_graph  # noqa: E402
import rowe_rom  # noqa: E402


def main() -> None:
    w = rowe_rom.world_edges()
    # the dynamic sentinel is never a node and never a border
    assert (127, 127) not in w, "dynamic warp still a world_edges node"
    assert not any((127, 127) in dests for dests in w.values()), "dynamic warp still a world_edges border"
    # a League room whose only warp is dynamic has no open border at all
    assert w[(25, 25)] == set(), f"(25,25) border not empty: {sorted(w[(25, 25)])}"
    assert w[(25, 60)] == set(), f"(25,60) border not empty: {sorted(w[(25, 60)])}"

    # neighbors asserts the sentinel can never leak back, whatever a stale graph on disk holds
    fd, gp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(gp)
    try:
        g = map_graph.MapGraph(gp)
        g.world = {(25, 25): {(127, 127)}}
        raised = False
        try:
            g.neighbors((25, 25))
        except AssertionError as e:
            raised = True
            assert "dynamic" in str(e), e
        assert raised, "neighbors did not reject the dynamic warp"
    finally:
        if os.path.exists(gp):
            os.remove(gp)

    print("DYNAMIC WARP PASS", flush=True)


if __name__ == "__main__":
    main()
