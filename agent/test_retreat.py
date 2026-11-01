"""Player.gym_ready and Player._retreat_warranted ground the Center-trip decision in the active
goal. A party with no mon able to attack always retreats. Approaching a gym the whole team fights
at once, so a low lead or a PP-starved team tops off at a Center first; inside the gym map it does
not, the interior trainers are fought and the bag covers them. A grind or explore tolerates a
chipped lead and rotates to the next able mon instead of trekking back for one low mon.
Player.top_off_due gates the separate case of already standing in a service town, where the
Center is free: any mon below full HP or a PP-starved lead is worth the stop even when the
retreat thresholds would not send the party across the map for it."""
import rowe_rom
from play import Player

ATK = next(mid for mid in range(1, 600) if rowe_rom.move(mid).power >= 10)  # a real damaging move id


class Mon:
    def __init__(self, hp: int, max_hp: int, can_hit: bool):
        self.hp, self.max_hp = hp, max_hp
        self.moves = [ATK]
        self.pp = [10] if can_hit else [0]


class G:
    def __init__(self, pos: tuple):
        self._pos = pos

    def position(self) -> tuple:
        return self._pos


def main() -> None:
    full = [Mon(60, 60, True), Mon(50, 50, True), Mon(40, 40, False)]
    assert Player.gym_ready(full) is True
    assert Player.gym_ready([Mon(6, 60, True), Mon(50, 50, True), Mon(40, 40, False)]) is False, "lead under the HP line"
    assert Player.gym_ready([Mon(60, 60, True), Mon(50, 50, False), Mon(40, 40, False)]) is False, "only one PP attacker"

    p = Player.__new__(Player)
    p.g = G((5, 3, 24, 4))  # standing on map (24,4), not the gym

    # a grind tolerates a chipped lead and rotates, so no trek for one low mon
    p.goal = {"mode": "grind", "map": [11, 3]}
    assert p._retreat_warranted(full) is False
    assert p._retreat_warranted([Mon(6, 60, True), Mon(50, 50, True), Mon(40, 40, False)]) is False, "chipped lead rotates"
    # but a team with nobody able to attack always retreats, rotation cannot save it
    assert p._retreat_warranted([Mon(60, 60, False), Mon(50, 50, False), Mon(40, 40, False)]) is True

    # approaching a gym: a low lead or a PP-starved team tops off at a Center first
    p.goal = {"mode": "gym", "map": [11, 3]}
    assert p._retreat_warranted(full) is False, "ready, no trek"
    assert p._retreat_warranted([Mon(6, 60, True), Mon(50, 50, True), Mon(40, 40, False)]) is True, "low lead tops off"
    assert p._retreat_warranted([Mon(60, 60, True), Mon(50, 50, False), Mon(40, 40, False)]) is True, "PP-starved tops off"

    # inside the gym map the same hurt team does not trek: the interior fights run and the bag covers
    p.g = G((5, 3, 11, 3))
    assert p._retreat_warranted([Mon(6, 60, True), Mon(50, 50, True), Mon(40, 40, False)]) is False, "no trek inside the gym"

    # standing in a service town, the Center is free, so top off below full even when no trek was due
    assert Player.top_off_due(full) is False, "whole party full, lead can attack"
    assert Player.top_off_due([Mon(60, 60, True), Mon(30, 50, True), Mon(40, 40, False)]) is True, "one chipped bench mon the retreat bar ignored"
    assert Player.top_off_due([Mon(55, 60, True), Mon(50, 50, True), Mon(40, 40, False)]) is True, "chipped lead"
    assert Player.top_off_due([Mon(60, 60, False), Mon(50, 50, True), Mon(40, 40, False)]) is True, "full HP but PP-starved lead"
    print("test_retreat: ok")


if __name__ == "__main__":
    main()
