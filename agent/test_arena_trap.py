"""A wild lead whose every move reads 0 damage into the foe (an Electric move into Dugtrio's Ground
immunity) switched to Run, and Arena Trap refused the escape, so the Run looped to the WEDGE stall
(states/grind.log run 2, 'flee: no usable damaging move' spam). _bench_that_can_hit sends out a
party mon that can hurt the foe instead, and a refused Run latches _cant_escape so the Run sites
stop pressing it and fight the trapping foe."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import play  # noqa: E402
from rowe_state import BattleMon, PartyMon  # noqa: E402

DUGTRIO, GOLDEEN = 51, 118
GROUND, WATER, MYSTERY = 4, 11, 9
ARENA_TRAP = 71
SURF, TACKLE, THUNDERBOLT, SPARK = 57, 33, 85, 209


def _party_mon(slot, moves, personality) -> PartyMon:
    return PartyMon(slot=slot, species=GOLDEEN, level=40, hp=120, max_hp=120, moves=moves,
                    pp=(20, 20, 20, 20), status=0, experience=0, friendship=0, nickname="Mon",
                    personality=personality, atk=90, dfn=70, spd=80, sp_atk=90, sp_def=70)


def _dugtrio() -> BattleMon:
    return BattleMon(battler=1, species=DUGTRIO, level=31, hp=72, max_hp=72, moves=(TACKLE, 0, 0, 0),
                     pp=(35, 0, 0, 0), types=(GROUND, GROUND, MYSTERY), ability=ARENA_TRAP, status1=0,
                     stat_stages=(6,) * 8, nickname="Dugtrio", personality=99, atk=80, dfn=50, spd=120,
                     sp_atk=50, sp_def=70)


def _lead() -> BattleMon:
    # the lead carries only Electric moves, all of which Dugtrio's Ground type takes for 0 damage
    return BattleMon(battler=0, species=GOLDEEN, level=73, hp=220, max_hp=220,
                     moves=(THUNDERBOLT, SPARK, 0, 0), pp=(15, 20, 0, 0), types=(WATER, WATER, MYSTERY),
                     ability=0, status1=0, stat_stages=(6,) * 8, nickname="Lead", personality=1,
                     atk=100, dfn=80, spd=90, sp_atk=110, sp_def=80)


class _G:
    def __init__(self, party):
        self._party = party

    def party(self):
        return self._party


def _player(party):
    p = play.Player.__new__(play.Player)
    p.g = _G(party)
    p._ran = False
    p._cant_escape = False
    p.tap = lambda *a, **k: None
    p.run = lambda *a, **k: None
    return p


def main() -> None:
    lead = _lead()
    foes = [_dugtrio()]

    # a Water bench mon (slot 1) can hit Dugtrio; an Electric bench mon (slot 2) cannot, so the pick
    # is the one that does damage, never the lead's own personality
    party = [
        _party_mon(0, (THUNDERBOLT, SPARK, 0, 0), 1),       # the lead, excluded by personality
        _party_mon(1, (SURF, TACKLE, 0, 0), 2),             # Water, hits Ground
        _party_mon(2, (THUNDERBOLT, SPARK, 0, 0), 3),       # Electric, 0 damage into Ground
    ]
    p = _player(party)
    assert p._bench_that_can_hit(lead, foes) == 1, p._bench_that_can_hit(lead, foes)

    # no party mon can damage the foe: no switch target, the caller falls through to its flee
    none_party = [
        _party_mon(0, (THUNDERBOLT, SPARK, 0, 0), 1),
        _party_mon(2, (THUNDERBOLT, SPARK, 0, 0), 3),
    ]
    p2 = _player(none_party)
    assert p2._bench_that_can_hit(lead, foes) is None, p2._bench_that_can_hit(lead, foes)

    # a Run press marks the attempt; arriving back at the action pick means it was refused, so
    # _cant_escape latches and never clears mid-battle
    p3 = _player(party)
    p3._run_away()
    assert p3._ran is True
    p3._note_escape_result()
    assert p3._cant_escape is True and p3._ran is False
    # a second pick with no fresh Run keeps the latch set and does not re-arm _ran
    p3._note_escape_result()
    assert p3._cant_escape is True and p3._ran is False

    # a Run that worked ended the battle, so _note_escape_result never saw a pending attempt
    p4 = _player(party)
    p4._note_escape_result()
    assert p4._cant_escape is False

    print("ARENA TRAP PASS", flush=True)


if __name__ == "__main__":
    main()
