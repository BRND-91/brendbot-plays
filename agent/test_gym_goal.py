"""A gym goal completes when the League-flag count rises past its write-time value. A Johto leader
sets a League flag (0x2A4-0x2AB) but not the Hoenn badge var self.g.badges() reads, so keying the
exit on badges() left a Johto win ending in a spurious "talked" close with the goal still open."""
import json

import rowe_symbols as S
from play import GoalExit, Player


class _G:
    def __init__(self, flags):
        self._flags = set(flags)

    def position(self):
        return (5, 3, 2, 7)  # Falkner's gym interior (2,7)

    def badges(self):
        return sum(1 for i in range(S.BADGE_COUNT) if (S.FLAG_BADGE01 + i) in self._flags)

    def flag(self, f):
        return f in self._flags


def _player(tmp_path, goal, flags):
    sp = tmp_path / "live.ss"
    sp.write_bytes(b"")
    (tmp_path / "goal.json").write_text(json.dumps(goal))
    p = Player.__new__(Player)
    p.state_path = str(sp)
    p.g = _G(flags)
    return p


def test_gym_goal_completes_on_a_johto_win(tmp_path):
    hoenn = {S.FLAG_BADGE01 + i for i in range(S.BADGE_COUNT)}  # 8 Hoenn badges already up
    goal = {"mode": "gym", "map": [2, 7], "badges": 8, "flags": 8}
    p = _player(tmp_path, goal, hoenn | {S.JOHTO_BADGE01})  # Falkner's flag now set, badges() stays 8
    try:
        p.check_goal()
    except GoalExit as g:
        assert "league flags" in str(g), g
    else:
        raise AssertionError("a Johto win must complete the gym goal though badges() did not rise")


def test_gym_goal_holds_until_a_flag_rises(tmp_path):
    hoenn = {S.FLAG_BADGE01 + i for i in range(S.BADGE_COUNT)}
    goal = {"mode": "gym", "map": [2, 7], "badges": 8, "flags": 8}
    p = _player(tmp_path, goal, hoenn)  # count still 8, no Johto flag yet
    p.check_goal()  # must not raise
