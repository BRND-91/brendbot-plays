"""The per-press battle log names the key and the state read before the press, so a wrong press is
findable in grind.log. It reads the main callback and, for the player chooser, the controller func,
gBattleCommunication, and the cursor slot on the open screen with the hp or pp under it."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb
import play

BASE = os.path.dirname(os.path.abspath(__file__))


def _p(fixture: str) -> play.Player:
    e = eb.Emu()
    e.load_state(open(os.path.join(BASE, "states", "fixtures", fixture), "rb").read())
    return play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-presslog-test.json")


def test_press_log_party_menu_names_the_slot_and_hp():
    p = _p("party_menu_faint.ss")
    line = p._battle_press_log(eb.KEY_DOWN)
    assert line.startswith("  press DOWN cb2 "), line
    assert "party slot 0 Flechinder hp 0/61" in line, line  # cursor on the fainted lead


def test_press_log_move_list_names_the_slot_and_pp():
    p = _p("movelist_parked_pp.ss")
    line = p._battle_press_log(eb.KEY_A)
    assert line.startswith("  press A cb2 "), line
    assert "move slot 1 pp 5" in line, line  # parked PP'd slot on this fixture
