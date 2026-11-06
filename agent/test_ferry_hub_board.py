"""A bounce gate on a walk into a Seagallop dock must not seal the board. The grind wedged at 8
badges when the executor oscillated the Slateport harbor board (0,1)->(9,9) and the bounce counter
gated it, which dropped route-to-Falkner to None and flipped the goal from ferry-to-ticket into an
explore spin that re-fed the oscillation. A dock is reachable by walking; its onward reach is the
ferry menu drive, so the gate on a board into it is honored nowhere."""
import os
import tempfile

import map_graph


WORLD = {(0, 1): {(9, 9)}, (9, 9): {(0, 1), (2, 7)}, (2, 7): {(9, 9)}}


def _graph(ferry_hubs):
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)  # no file: load() leaves the graph empty, world edges carry routing
    g = map_graph.MapGraph(path, world=WORLD, ferry_hubs=ferry_hubs)
    g.gated[((0, 1), (9, 9))] = frozenset()  # the bounce gate, recorded under empty field moves
    return g


def test_bounce_gate_on_dock_board_does_not_seal_route():
    sealed = _graph(ferry_hubs=set())
    assert sealed.route((0, 1), (2, 7), field_moves=frozenset()) is None, (
        "control: with no ferry-hub exemption the bounce gate must still shut the board"
    )
    open_ = _graph(ferry_hubs={(9, 9)})
    assert open_.route((0, 1), (2, 7), field_moves=frozenset()) == (9, 9), (
        "a board into a Seagallop dock routes through despite the bounce gate"
    )


def test_exemption_is_scoped_to_dock_destinations():
    g = _graph(ferry_hubs={(9, 9)})
    g.gated[((9, 9), (2, 7))] = frozenset()  # a plain overworld border, not a dock destination
    assert g.route((9, 9), (2, 7), field_moves=frozenset()) is None, (
        "a bounce gate on a non-dock edge still shuts; the exemption only covers dock boards"
    )
