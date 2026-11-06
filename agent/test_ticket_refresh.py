"""A Sevii ticket handed over mid-run opens that island's mainland dock arm on the live graph. The
graph was built once at launch, so Ticket 2 (0x336) picked up on Mt. Ember left the Slateport dock
(9,9) without its Two Island arm and the gym route sailed to One Island instead (states/grind.log:
"hop: [9, 9] region [0, 4] -> dest [2, 8]: route [0, 75] onward [1, 19]")."""
import os

import planner
import play

ONE_TICKET, TWO_TICKET = 0x335, 0x336
DOCK, TWO_ISLAND = (9, 9), (0, 76)


def _player(tmp_path, tickets):
    p = play.Player.__new__(play.Player)
    p._tickets = frozenset(tickets)
    p.graph = planner.build_graph(os.path.join(str(tmp_path), "map_graph.json"), tickets=p._tickets)
    return p


def test_new_ticket_opens_the_dock_arm(tmp_path):
    p = _player(tmp_path, {ONE_TICKET})
    assert p.graph.route(DOCK, TWO_ISLAND) != TWO_ISLAND, "arm must start shut for the test to mean anything"
    p._sync_tickets(frozenset({ONE_TICKET, TWO_TICKET}))
    assert p.graph.route(DOCK, TWO_ISLAND) == TWO_ISLAND


def test_unchanged_tickets_keep_the_layer():
    p = play.Player.__new__(play.Player)
    p._tickets = frozenset({ONE_TICKET})
    p.graph = None
    p._sync_tickets(frozenset({ONE_TICKET}))
    assert p.graph is None
