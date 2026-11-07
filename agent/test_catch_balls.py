"""Ball-tier plumbing: catch_chance reads the strongest held ball's multiplier, the catch count sums
every tier, and the shopping line upgrades to Ultra by balance. The Haxorus numbers are the case that
drove it, a L100 at 1 HP that a Poké Ball leaves under the 25% throw floor and an Ultra Ball lifts
over it, so the plumbing is the difference between a throw and a max-damage fight."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from catch import POKE_BALL, ball_count, catch_chance, strongest_ball  # noqa: E402
from play import THROW_FLOOR, ball_to_buy  # noqa: E402

POKE, GREAT, ULTRA = 4, 3, 2
HAXORUS = 612


class Foe:
    def __init__(self, species, max_hp, hp, status1=0):
        self.species, self.max_hp, self.hp, self.status1 = species, max_hp, hp, status1


def test_strongest_ball_takes_the_top_tier_held():
    assert strongest_ball({}) == (POKE_BALL, 1.0)
    assert strongest_ball({POKE: 5}) == (POKE, 1.0)
    assert strongest_ball({POKE: 5, GREAT: 2}) == (GREAT, 1.5)
    assert strongest_ball({ULTRA: 1, POKE: 5}) == (ULTRA, 2.0)


def test_ball_count_sums_the_tiers_and_skips_other_balls():
    assert ball_count({POKE: 5, GREAT: 2, ULTRA: 1}) == 8
    assert ball_count({POKE: 3, 999: 7}) == 3  # 999 is not a thrown tier


def test_haxorus_at_one_hp_crosses_the_floor_only_on_an_ultra():
    foe = Foe(HAXORUS, max_hp=200, hp=1)
    assert catch_chance(foe, 1.0) == pytest.approx(0.176, abs=0.005)
    assert catch_chance(foe, 2.0) == pytest.approx(0.352, abs=0.005)
    assert catch_chance(foe, 1.0) < THROW_FLOOR
    assert catch_chance(foe, 2.0) >= THROW_FLOOR


def test_ball_to_buy_picks_the_strongest_batch_the_budget_covers():
    # prices Poké 100, Great 300, Ultra 600; batch 20 costs 2000 / 6000 / 12000
    assert ball_to_buy(12000, 20) == ULTRA
    assert ball_to_buy(11999, 20) == GREAT
    assert ball_to_buy(5999, 20) == POKE
    assert ball_to_buy(0, 20) == POKE_BALL


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
