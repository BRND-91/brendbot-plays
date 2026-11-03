"""party_menu_step reaches a bench slot on the double-battle party menu, where the cursor runs
down one list (both fielded mons, then the bench) and LEFT/RIGHT change nothing."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb
from play import BATTLE_TYPE_DOUBLE, Player


class Mon:
    def __init__(self, slot: int, nickname: str, hp: int, personality: int = 0):
        self.slot, self.nickname, self.hp, self.personality = slot, nickname, hp, personality


class G:
    def __init__(self, party: list, battlers: list, slot: int):
        self._party, self._battlers, self.slot = party, battlers, slot

    def party(self) -> list:
        return self._party

    def battlers(self) -> list:
        return self._battlers

    def party_menu_slot(self) -> int:
        return self.slot

    def battle_type_flags(self) -> int:
        return BATTLE_TYPE_DOUBLE

    def in_battle(self) -> bool:
        return False  # the pick is the test; the post-pick wait ends on a battle that is over

    def press(self, key: int) -> None:
        if key == eb.KEY_DOWN:
            self.slot = 0 if self.slot > 5 else self.slot + 1
        elif key == eb.KEY_UP and self.slot > 0:
            self.slot -= 1


def test_double_menu_cursor_reaches_the_bench_slot():
    party = [Mon(0, "Goldeen", 0, 10), Mon(1, "Greedent", 106, 11), Mon(2, "Flechinder", 103, 12),
             Mon(3, "Mightyena", 106, 13), Mon(4, "Stoutland", 118, 14), Mon(5, "Gloom", 97, 15)]
    battlers = [party[0], Mon(0, "Mothim", 27, 90), party[1], Mon(1, "Swoobat", 59, 91)]
    g = G(party, battlers, slot=1)
    p = Player.__new__(Player)
    p.g = g
    p.switch_to = 14  # Stoutland's personality
    picked = []

    def tap(key: int, hold: int = 8, gap: int = 12) -> None:
        if key == eb.KEY_A:
            picked.append(g.slot)
        g.press(key)

    p.tap = tap
    p.run = lambda frames, keys=0: None
    p.party_menu_step()
    assert picked[:1] == [4]
