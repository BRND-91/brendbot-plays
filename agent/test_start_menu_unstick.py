"""The live run sat 14 minutes in the Start menu (cb2 0x8247bf9) because cutscene_step read every
non-field callback as a ceremony and pressed A, which opened the bag and the party list in turn.
start_menu_open.ss is that live frame; the step now backs out w/ B and hands the field back."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import play  # noqa: E402
import rowe_symbols as S  # noqa: E402
from emu_boot import Emu  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "states", "fixtures", "start_menu_open.ss")


def test_start_menu_backs_out_to_the_field():
    e = Emu()
    e.load_state(open(FIXTURE, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-test-startmenu.json")
    assert p.g.callback2() == S.CB2_START_MENU, hex(p.g.callback2())
    steps = 0
    while p.cutscene_step() and steps < 6:
        steps += 1
    assert p.g.callback2() == S.CB2_OVERWORLD, hex(p.g.callback2())
    assert not p.e.read(S.FIELD_LOCKED, 1)[0]
    assert steps <= 3, steps
