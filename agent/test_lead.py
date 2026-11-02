"""lowest_lead: a lead at the grind cap hands the slot to any attacker under it, inside LEAD_GAP."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rowe_rom
from play import LEAD_GAP, Player

ATK = next(mid for mid in range(1, 600) if rowe_rom.move(mid).power >= 10)


class Mon:
    def __init__(self, slot: int, level: int, hp: int = 80, max_hp: int = 80):
        self.slot, self.level, self.hp, self.max_hp = slot, level, hp, max_hp
        self.moves = [ATK]
        self.pp = [10]


class G:
    def __init__(self, party: list):
        self._party = party

    def party(self) -> list:
        return self._party


def player(party: list, goal: dict) -> Player:
    p = Player.__new__(Player)
    p.g = G(party)
    p.goal = goal
    p.need_heal = False
    return p


def main() -> None:
    assert LEAD_GAP == 3
    live = [Mon(0, 29), Mon(1, 28), Mon(2, 28), Mon(3, 28), Mon(4, 27), Mon(5, 27)]
    assert player(live, {"mode": "grind", "cap": 29}).lowest_lead() == 4, "lead at cap, L27 takes point"
    assert player(live, {"mode": "grind", "cap": None}).lowest_lead() is None, "hold-grind keeps the gap rule"
    assert player(live, {"mode": "travel", "to": [0, 1]}).lowest_lead() is None, "gap rule outside a grind"
    under = [Mon(0, 28), Mon(1, 27), Mon(2, 27)]
    assert player(under, {"mode": "grind", "cap": 29}).lowest_lead() is None, "lead under the cap waits on the gap"
    done = [Mon(0, 29), Mon(1, 29), Mon(2, 29)]
    assert player(done, {"mode": "grind", "cap": 29}).lowest_lead() is None, "everyone at cap, no swap"
    # every healthy mon at cap and the grinders hurt under the heal line: fights go nowhere, so heal
    stalled = [Mon(0, 29), Mon(1, 29), Mon(2, 27, hp=10), Mon(3, 27, hp=12)]
    p = player(stalled, {"mode": "grind", "cap": 29})
    assert p.lowest_lead() is None and p.need_heal is True, "cap lead over hurt grinders heals"
    p = player(stalled, {"mode": "grind", "cap": None})
    assert p.lowest_lead() is None and p.need_heal is False, "hold-grind keeps the gap rule for heals"
    print("ok")


if __name__ == "__main__":
    main()
