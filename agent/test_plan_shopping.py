"""_plan_shopping decides when the shopping list alone is worth a Mart walk. The League leg entered
Victory Road w/ five Hyper Potions, ran dry, and trekked to a Center from B1F; a thin pocket on a
travel leg now buys first, outdoors only, so a dungeon is finished rather than left for the counter."""
import play

EVER_GRANDE, VICTORY_ROAD_1F = (0, 8), (24, 43)
POKE, HYPER = 4, 36


class M:
    max_hp = 320


def _player(goal: dict, here: tuple, medicine: list, balls: int = 12, badges: int = 15) -> play.Player:
    p = play.Player.__new__(play.Player)
    p.goal = goal
    p.g = type("_G", (), {
        "badges": lambda self: badges,
        "money": lambda self: 320000,
        "medicine": lambda self: medicine,
        "position": lambda self: (0, 0) + here,
        "poke_balls": lambda self: [(POKE, balls)],
        "party": lambda self: [M()] * play.PARTY_SIZE,
    })()
    return p


def test_thin_pocket_outdoors_on_a_travel_leg_walks_to_the_counter():
    p = _player({"mode": "travel", "to": [16, 10]}, EVER_GRANDE, [(HYPER, 2)])
    p._plan_shopping(p.g.party(), 12)
    assert any(iid in play.HP_ITEMS for iid, _ in p.shopping), p.shopping
    assert p.mart_trek is True


def test_the_league_leg_never_walks_for_the_counter():
    # the same thin pocket on the shore, every gym down and the goal the League: the trek would be
    # Mossdeep across the ocean routes, so the leg runs on what is left
    p = _player({"mode": "travel", "to": [16, 10]}, EVER_GRANDE, [(HYPER, 2)], badges=16)
    p._plan_shopping(p.g.party(), 12)
    assert p.shopping and p._league_leg() and p.mart_trek is False


def test_the_same_pocket_inside_the_dungeon_waits():
    p = _player({"mode": "travel", "to": [16, 10]}, VICTORY_ROAD_1F, [(HYPER, 2)])
    p._plan_shopping(p.g.party(), 12)
    assert p.shopping and p.mart_trek is False


def test_a_grind_never_walks_for_restores():
    p = _player({"mode": "grind", "map": [0, 16]}, EVER_GRANDE, [(HYPER, 2)])
    p._plan_shopping(p.g.party(), 12)
    assert p.mart_trek is False


def test_a_stocked_pocket_lists_nothing():
    p = _player({"mode": "travel", "to": [16, 10]}, EVER_GRANDE, [(HYPER, play.HP_SPEND[0]), *((iid, 1) for iid in play.CURE_BUYS)])
    p._plan_shopping(p.g.party(), 12)
    assert p.shopping == [] and p.mart_trek is False
