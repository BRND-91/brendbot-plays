"""outmatched: a foe's super-effective hit worth half the lead's remaining bar sends a far-outlevelled
exp lead out anyway; a neutral hit or a small one lets it fight. Fixtures from test_battle_engine."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from battle_engine import outmatched  # noqa: E402
from test_battle_engine import nosepass, pidgey_battler  # noqa: E402
from test_exp_lead_switch import herdier_battler  # noqa: E402


def test_rock_throw_on_a_full_pidgey_is_under_half():
    # Rock Throw lands 20 of 52 on the Flying lead, super effective but under the half-bar line
    assert outmatched(pidgey_battler(52), [nosepass(29)]) is False


def test_rock_throw_on_a_chipped_pidgey_is_over_half():
    assert outmatched(pidgey_battler(20), [nosepass(29)]) is True


def test_neutral_hit_never_counts():
    assert outmatched(herdier_battler(), [nosepass(29)]) is False
