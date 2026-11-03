"""party_menu_step on a forced replacement must send out a live bench mon, never stall on a
fainted slot. gPartyMenuSlot updates a few frames behind the dpad press under the cursor slide,
so the walk polls the slot off its pre-tap value and the pre-A guard confirms only a live slot
that is the target, re-walking otherwise.

Fixture states/fixtures/party_menu_faint.ss is the open party grid after the wild lead fainted:
cursor on slot 0 (fainted Flechinder), slot 1 also fainted (Pidgey), live bench at 2-5. The pin
goes red if the step leaves the fainted lead on the field; its red-capability is shown by a
deliberate break at the change point (a zero walk budget leaves the fighter in, which fails it).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb
import play

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "party_menu_faint.ss")


def _player(fixture: str = FIXTURE) -> play.Player:
    e = eb.Emu()
    e.load_state(open(fixture, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-party-faint-test.json")
    for a in ("_wedge", "_act_stuck", "_prompt_taps", "end_taps"):
        setattr(p, a, 0)
    p._wedge_sig = p._act_sig = p._switch_active = None
    p._wild_switched = False
    p.switch_to = None
    return p


def test_fixture_is_the_open_grid_on_a_fainted_cursor():
    p = _player()
    party = p.g.party()
    assert p.g.party_menu_slot() == 0, "cursor should park on the fainted lead slot"
    assert party[0].hp == 0, "slot 0 (the cursor) must be fainted"
    assert party[1].hp == 0, "slot 1 must be fainted, between the cursor and the live bench"
    assert any(m.hp > 0 for m in party[2:]), "fixture needs a live bench target past the faints"


def test_party_menu_step_sends_out_a_live_mon():
    p = _player()
    fielded_before = {m.personality for m in p.g.battlers()[0::2]}
    p.party_menu_step()
    active = p.g.battlers()[0]
    assert active.hp > 0, f"sent out a fainted mon ({active.nickname} hp {active.hp})"
    assert active.personality not in fielded_before, \
        "the fainted lead is still on the field; the step never landed a switch"
