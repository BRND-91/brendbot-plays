"""Coverage counts members: a foe type stays wanted until COVER_DEPTH members each hit it super
effectively, and the catch want list carries the types that hit a gap plus the types that resist a
foe attack the party stacks a weakness to."""
from play import COVER_DEPTH, Profile, wanted_catch_types, wanted_types

NORMAL, FIGHTING, GROUND, ROCK, BUG, GHOST, STEEL = 0, 1, 4, 5, 6, 7, 8
FIRE, WATER, GRASS, ELECTRIC, PSYCHIC, ICE, DRAGON, DARK, FAIRY = 10, 11, 12, 13, 14, 15, 16, 17, 18

# Steven's six as type pairs: Magnezone, Excadrill, Dracovish, Aegislash, Diancie, Metagross
STEVEN = [[(ELECTRIC, STEEL), (GROUND, STEEL), (WATER, DRAGON), (STEEL, GHOST), (ROCK, FAIRY), (STEEL, PSYCHIC)]]


def _mon(types: tuple, attacks: frozenset) -> Profile:
    return Profile(0, types, attacks, 300)


LIVE_PARTY = [
    _mon((ROCK, ICE), frozenset({NORMAL, WATER, ICE, PSYCHIC})),      # Aurorus
    _mon((WATER, WATER), frozenset({GROUND, WATER})),                 # Golduck, the one Mud Bomb
    _mon((NORMAL, NORMAL), frozenset({NORMAL, DARK, ROCK})),          # Greedent
    _mon((NORMAL, NORMAL), frozenset({ROCK, NORMAL, ICE})),           # Stoutland
    _mon((WATER, WATER), frozenset({WATER, BUG})),                    # Seaking
    _mon((BUG, ELECTRIC), frozenset({BUG, ELECTRIC})),                # Vikavolt
]


def test_one_steel_answer_leaves_steel_wanted():
    assert COVER_DEPTH == 2
    assert STEEL in wanted_types(LIVE_PARTY, STEVEN), "Golduck alone hits Steel"
    two_ground = LIVE_PARTY[:5] + [_mon((GROUND, GROUND), frozenset({GROUND}))]
    assert STEEL not in wanted_types(two_ground, STEVEN), "a second Ground attacker closes Steel"


def test_catch_wants_the_counters_and_the_resists():
    want = wanted_catch_types(LIVE_PARTY, STEVEN)
    assert {FIRE, FIGHTING, GROUND} <= want, f"Steel's counters are the catch targets, got {sorted(want)}"
    # three Waters are weak to Magnezone's Electric and only Vikavolt resists it
    assert {GRASS, ELECTRIC, DRAGON} <= want, f"Electric resists are wanted, got {sorted(want)}"
    assert FAIRY not in want, f"Diancie's own type is never wanted for its own sake, got {sorted(want)}"


def test_two_resists_settle_the_weakness():
    magnezone = [[(ELECTRIC, STEEL)]]
    assert GRASS in wanted_catch_types(LIVE_PARTY, magnezone), "three Waters under one Electric resist want a Grass"
    team = LIVE_PARTY[:2] + LIVE_PARTY[3:] + [_mon((GROUND, DRAGON), frozenset({GROUND, DRAGON}))]  # Greedent out
    assert GRASS not in wanted_catch_types(team, magnezone), "Vikavolt plus a Ground resist settle Electric, Grass is no longer wanted for it"
