"""A return hop that served a different dest is a detour, never a bounce. Off Four Island the
walk hopped (0,123)->(1,26) toward Chuck's gym, then hopped straight back because needs_heal
re-aimed the next hop at the service town; _after_cross read the return as the walk's own bounce,
_blocked_from retired (1,26), and w/ the only exit blocked the route came back as the map itself."""
import play

ISLAND, EXIT_MAP, GYM = (0, 123), (1, 26), (2, 11)
ISLAND_REGION, EXIT_REGION = ISLAND + (5, 6), EXIT_MAP + (8, 6)


def _player(landed: tuple, exits: set) -> play.Player:
    p = play.Player.__new__(play.Player)
    p.g = type("G", (), {"position": staticmethod(lambda: (0, 0) + landed)})()
    p.graph = None
    p.goal = {"mode": "gym"}
    p._blocked, p._bounced, p._stuck = {}, {}, {}
    p._last_hop, p._last_hop_dest, p._returned = None, None, False
    p._landing_exits = lambda: exits
    return p


def test_return_toward_another_dest_is_a_detour():
    p = _player(ISLAND, {EXIT_MAP, GYM})
    p._after_cross(ISLAND_REGION, EXIT_MAP, ("map_changed", "moved"), dest=GYM)
    p._after_cross(EXIT_REGION, ISLAND, ("map_changed", "moved"), dest=ISLAND)
    assert p._returned is False, "a heal-run return is a detour, so the outbound hop is not retired"
    assert p._last_hop == (EXIT_REGION, ISLAND), "the return hop is the new last hop"


def test_return_toward_the_same_dest_is_a_bounce():
    p = _player(ISLAND, {EXIT_MAP, GYM})
    p._after_cross(ISLAND_REGION, EXIT_MAP, ("map_changed", "moved"), dest=GYM)
    p._after_cross(EXIT_REGION, ISLAND, ("map_changed", "moved"), dest=GYM)
    assert p._returned is True, "coming straight back on the same dest is the bounce _blocked_from retires"
    assert p._last_hop == (ISLAND_REGION, EXIT_MAP), "the outbound record is kept for the landing to retire"
