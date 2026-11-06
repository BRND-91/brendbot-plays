"""Post-game scoring targets. boss_build reads Steven's and Red's six off their gTrainers rows at the
level byte, and scoring_builds swaps the League for the unbeaten bosses once the game-clear flag is up:
Steven then Red w/ both standing, Red alone once Steven's flag flips, the League again w/ nothing left."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rowe_rom
import rowe_symbols as S
from play import foe_types
from test_team import G, GREEDENT, Mon, TACKLE, player

MAGNEZONE, EXCADRILL, DRACOVISH, AEGISLASH, DIANCIE, METAGROSS = 462, 530, 882, 681, 719, 376
MACHAMP, SNORLAX, CHARIZARD, BLASTOISE, VENUSAUR, PIKACHU_LIGHT_BALL = 68, 143, 6, 9, 3, 1600
STEVEN = [(sp, 100) for sp in (MAGNEZONE, EXCADRILL, DRACOVISH, AEGISLASH, DIANCIE, METAGROSS)]
RED = [(sp, 100) for sp in (MACHAMP, SNORLAX, CHARIZARD, BLASTOISE, VENUSAUR, PIKACHU_LIGHT_BALL)]
GROUND, STEEL = 4, 8
BOSS_FLAGS = (S.FLAG_DEFEATED_METEOR_FALLS_STEVEN, S.FLAG_DEFEATED_RED)


class Cleared(G):
    """All 16 badges in and the credits rolled; `beaten` holds the boss defeat flags that are up."""

    def __init__(self, party: list, beaten: set):
        super().__init__(party, [], 16)
        self.beaten = set(beaten)

    def flag(self, flag_id: int) -> bool:
        if flag_id in BOSS_FLAGS:
            return flag_id in self.beaten
        return flag_id == S.FLAG_SYS_GAME_CLEAR or super().flag(flag_id)


def test_boss_build():
    assert rowe_rom.boss_build("Steven") == STEVEN
    assert rowe_rom.boss_build("Red") == RED
    assert foe_types(STEVEN)[1] == (GROUND, STEEL), "Excadrill's pair as the scorers read it"


def test_scoring_builds_past_the_clear(tmp_path):
    party = [Mon(i, GREEDENT, 100, [TACKLE]) for i in range(6)]
    league = [foe_types(rowe_rom.leader_build(n, rowe_rom.LEAGUE_BADGES)) for n in rowe_rom.LEAGUE]
    steven, red = foe_types(STEVEN), foe_types(RED)
    p = player(G(list(party), [], 16), str(tmp_path / "a.ss"))
    assert p.scoring_builds()[0] == league, "before the clear the League is the target"
    p = player(Cleared(list(party), set()), str(tmp_path / "b.ss"))
    assert p.scoring_builds()[0] == [steven, red], "both bosses standing, both are the targets"
    p = player(Cleared(list(party), {S.FLAG_DEFEATED_METEOR_FALLS_STEVEN}), str(tmp_path / "c.ss"))
    assert p.scoring_builds()[0] == [red], "Steven beaten, Red is the target"
    p = player(Cleared(list(party), set(BOSS_FLAGS)), str(tmp_path / "d.ss"))
    assert p.scoring_builds()[0] == league, "nothing left, the League builds stand in"
