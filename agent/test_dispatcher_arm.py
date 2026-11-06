"""A field dispatcher sailor hands the ticket for the island picked and sails there; a row whose ticket
is already in the bag talks and reopens its list w/o sailing (probe on a (1,35) snapshot: One and Four
rows stuck w/ the list open, the ticketless Six row landed on (1,58)). The mainland docks are the
mirror: they sail only on a held ticket."""
import script_decode as sd

FIVE_ISLAND_SAILOR, SLATEPORT_DOCK = (1, 35), (9, 9)
ONE_ISLAND, SIX_ISLAND = (0, 75), (1, 58)
ONE_TICKET, SIX_TICKET = 0x335, 0x33A


def test_dispatcher_refuses_a_held_ticket_island():
    assert sd.passable_island_arm(FIVE_ISLAND_SAILOR, ONE_ISLAND, frozenset({ONE_TICKET})) is False


def test_dispatcher_sails_to_the_ticketless_island():
    assert sd.passable_island_arm(FIVE_ISLAND_SAILOR, SIX_ISLAND, frozenset({ONE_TICKET})) is True


def test_mainland_dock_sails_on_a_held_ticket_only():
    assert sd.passable_island_arm(SLATEPORT_DOCK, ONE_ISLAND, frozenset({ONE_TICKET})) is True
    assert sd.passable_island_arm(SLATEPORT_DOCK, SIX_ISLAND, frozenset({ONE_TICKET})) is False
