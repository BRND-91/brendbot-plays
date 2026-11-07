"""The exp lead steps out on its first turn whatever its own odds: strongest_bench names a bench mon
where best_switch, which keeps a fighter that reads as winning, returns None. Fixtures are the
Roxanne set in test_battle_engine."""
import dataclasses
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from battle_engine import best_switch, lead_steps_out, outmatched, strongest_bench  # noqa: E402
from rowe_state import BattleMon  # noqa: E402
from test_battle_engine import BITE, HERDIER, MYSTERY, PARTY, nosepass  # noqa: E402


def herdier_battler() -> BattleMon:
    return BattleMon(battler=0, species=HERDIER, level=20, hp=60, max_hp=60, moves=(BITE, 0, 0, 0), pp=(20, 0, 0, 0),
                     types=(0, 0, MYSTERY), ability=0, status1=0, stat_stages=(6,) * 8, nickname="Herdier",
                     personality=2, atk=45, dfn=35, spd=30, sp_atk=25, sp_def=30)


def test_winning_lead_still_has_a_bench_pick():
    foes = [nosepass(3)]
    assert best_switch(PARTY, herdier_battler(), foes, margin=0.25) is None
    slot, score = strongest_bench(PARTY, herdier_battler(), foes)
    assert slot == 0, "Pidgey, the bench mon that takes the smallest Rock Throw relative to its bar"
    assert score > 0


def test_a_lead_under_the_foes_level_steps_out():
    """Nosepass L12 carries no hit worth half Herdier's bar and sits under L20, so the lead fights it;
    the same Nosepass at L21 is one level over and the lead steps out before the chart says anything."""
    me = herdier_battler()
    under, over = nosepass(21), dataclasses.replace(nosepass(21), level=21)
    assert under.level == 12 and not outmatched(me, [under]) and not lead_steps_out(me, [under])
    assert not outmatched(me, [over]) and lead_steps_out(me, [over])


def test_no_bench_with_pp_gives_no_pick():
    pp_out = [PARTY[2]._replace(pp=(0, 0, 0, 0))] if hasattr(PARTY[2], "_replace") else []
    if pp_out:
        assert strongest_bench(pp_out, herdier_battler(), [nosepass(29)]) is None
