"""The League lobby's door to Hall5 (16,9) sits between two guards at (8,2) and (11,2). The step
onto (9,2) runs their badge check: both walk in front of the player, speak on A ("Trainer! Believe
in yourself and your Pokémon, and go forth!"), then step aside, and only then does UP fire the warp.
take_warp pressed UP once, B, UP, and reported stuck five times from (9,3) (states/grind.log,
"travel (16, 10) -> [16, 9] warp: stuck (blocked)"), gating the League off the run."""
import os
import shutil

import emu_boot as eb
import play

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "states", "fixtures", "league_lobby_9_11.ss")
LOBBY, HALL5 = (16, 10), (16, 9)


def test_league_guards_let_the_press_through():
    work = "/tmp/rowe-league-door.ss"
    shutil.copy(FIXTURE, work)
    e = eb.Emu()
    e.load_state(open(work, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-league-door.json")
    before = p.g.position()
    assert before[2:] == LOBBY, f"fixture not in the lobby: map {before[2:]}"
    status = p.errands.take_warp(HALL5, tools=frozenset(p.field_moves()))
    after = p.g.position()
    assert status == "map_changed", f"guards held the door: take_warp -> {status} at {after}"
    assert after[2:] == HALL5, f"map did not flip to {HALL5}: at {after[2:]} tile {after[:2]}"


if __name__ == "__main__":
    test_league_guards_let_the_press_through()
