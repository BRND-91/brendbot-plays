"""The Elite Four gauntlet. states/fixtures/sidney_room.ss is the live save frozen on Sidney's room
(16,0) tile (6,8), the entry door shut behind the party and the executor looping 'travel stuck: no
route from [16, 0] to [16, 5]'. league_step walks at Sidney and opens the fight; red-capability is
the pre-change executor, which has no step for the room and raises the stuck exit. The lobby test
runs the nurse and the clerk on states/fixtures/league_lobby_9_11.ss."""
import os
import shutil

import emu_boot as eb
import play

BASE = os.path.dirname(os.path.abspath(__file__))
SIDNEY = os.path.join(BASE, "states", "fixtures", "sidney_room.ss")
LOBBY = os.path.join(BASE, "states", "fixtures", "league_lobby_9_11.ss")


def _player(fixture: str, work: str, goal: dict) -> play.Player:
    shutil.copy(fixture, work)
    e = eb.Emu()
    e.load_state(open(work, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path=work + ".json")
    p.goal = goal
    return p


def test_league_shopping_list_tops_each_row_up_to_its_count():
    got = play.league_shopping_list(292258, [(34, 4), (38, 6)])
    assert got == [(34, 6), (40, 6), (52, 6)]


def test_league_shopping_list_cuts_to_the_money_past_the_reserve():
    # 4000 past the reserve: one Full Restore (3000), no Max Revive (4000), one Full Heal (600)
    assert play.league_shopping_list(5000, []) == [(34, 1), (38, 1)]


def test_sidney_room_opens_the_fight():
    p = _player(SIDNEY, "/tmp/rowe-sidney-room.ss", {"mode": "travel", "to": [16, 5]})
    before = p.g.position()
    assert before[2:] == (16, 0), f"fixture not on Sidney's room: map {before[2:]}"
    assert not p.g.flag(play.ELITE_FLAGS[(16, 0)])
    assert p.league_step((16, 0)) is True
    assert p.g.in_battle(), f"Sidney's fight did not open from {p.g.position()[:2]}"


def test_lobby_heals_and_buys_the_league_list():
    p = _player(LOBBY, "/tmp/rowe-league-lobby.ss", {"mode": "travel", "to": [16, 9]})
    assert p.g.position()[2:] == (16, 10)
    held = dict(p.g.medicine())
    assert p.league_step((16, 10)) is True
    after = dict(p.g.medicine())
    assert after.get(34, 0) > held.get(34, 0), f"no Full Restore bought: {held} -> {after}"
    assert after.get(40, 0) > held.get(40, 0), f"no Max Revive bought: {held} -> {after}"
    assert p.errands.healed()
    assert p.g.position()[2:] == (16, 10)


if __name__ == "__main__":
    test_league_shopping_list_tops_each_row_up_to_its_count()
    test_league_shopping_list_cuts_to_the_money_past_the_reserve()
    test_sidney_room_opens_the_fight()
    test_lobby_heals_and_buys_the_league_list()
    print("test_league_gauntlet OK")
