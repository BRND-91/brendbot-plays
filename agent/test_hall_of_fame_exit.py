"""states/fixtures/hall_of_fame_entry.ss is the live save frozen on the Hall of Fame walk-in, map
(16,11) tile (7,10), the field callback, before the ceremony's save. With a flash save attached the
ceremony saves the game, cutscene_step presses A through the Hall of Fame screen, the credits and
the title screen, and Continue brings the field back at the player's room (1,1) w/ the party and
the champion flag. Red-capability: w/o the flash file the title screen offers New Game only and
the field comes back on the truck (25,40) w/ an empty party, which is what the live run did."""
import os
import shutil

import emu_boot as eb
import play
import rowe_symbols as S

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "hall_of_fame_entry.ss")
HALL_OF_FAME = (16, 11)
BEDROOM = (1, 1)


def _drive(p: play.Player, ticks: int) -> int:
    """cutscene_step off the field, league_step through the ceremony's text on it, until the field
    is back on another map; the tick count it took."""
    for t in range(ticks):
        try:
            off_field = p.cutscene_step()
        except play.GoalExit as g:
            # the field's return after the credits is the continue exit, which replan takes live
            assert str(g).startswith("continue: field back"), str(g)
            return t
        if not off_field:
            assert p.g.position()[2:] == HALL_OF_FAME, f"left the ceremony w/o the continue exit at {p.g.position()}"
            assert p.league_step(HALL_OF_FAME), "league_step ran nothing on the ceremony"
    return ticks


def test_ceremony_saves_and_continue_restores_the_game():
    work = "/tmp/rowe-hof-entry.ss"
    sav = "/tmp/rowe-hof-entry.sav"
    shutil.copy(FIXTURE, work)
    with open(sav, "wb") as f:
        f.write(b"\xff" * play.FLASH_BYTES)
    e = eb.Emu(save=sav)
    e.load_state(open(work, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path=work + ".json")
    p.goal = {"mode": "travel", "to": list(HALL_OF_FAME)}
    assert p.g.position()[2:] == HALL_OF_FAME and p.g.callback2() == S.CB2_OVERWORLD
    before = (len(p.g.party()), p.g.badges(), p.g.money())
    ticks = _drive(p, 900)
    assert ticks < 900, f"never left the Hall of Fame: cb2 {p.g.callback2():#x} at {p.g.position()}"
    assert p.g.position()[2:] == BEDROOM, f"field came back at {p.g.position()}"
    assert (len(p.g.party()), p.g.badges(), p.g.money()) == before == (6, 16, 330658)
    assert p.g.flag(S.FLAG_SYS_GAME_CLEAR)
    assert any(b != 0xFF for b in open(sav, "rb").read()), "the ceremony wrote nothing to the flash file"
