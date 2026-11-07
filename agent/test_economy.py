"""play.shopping_list and hp_tier: the spend table. Each item class joins the list only under its
floor, the HP tier follows the party's largest max HP, and every batch is cut to the money left
past the reserve so a broke party stays on the trainer ladder instead of walking to a counter."""
from play import MONEY_RESERVE, PARTY_SIZE, hp_tier, shopping_list

POKE, POTION, SUPER, HYPER, MAXP, ANTIDOTE, PARLYZ = 4, 28, 37, 36, 35, 29, 33
ULTRA = 2  # a flush balance upgrades the ball line to Ultra Balls


class M:
    def __init__(self, max_hp: int):
        self.max_hp = max_hp


def main() -> None:
    assert hp_tier(28) == POTION, "20 HP covers 70% of 28"
    assert hp_tier(80) == SUPER, "a Potion never covers 56 of 80, the Super does"
    assert hp_tier(120) == HYPER, "84 of 120 needs the Hyper"
    assert hp_tier(400) == MAXP, "past the Hyper's 120 the Max Potion is the pick"
    six = [M(80)] * PARTY_SIZE
    assert shopping_list(50000, 0, [], six) == [(ULTRA, 10), (SUPER, 15), (ANTIDOTE, 2), (PARLYZ, 2)], "full party, empty bag, balance buys Ultra"
    assert shopping_list(50000, 0, [], six[:5])[0] == (ULTRA, 20), "party short of six buys the catch batch, Ultra when flush"
    assert shopping_list(50000, 5, [(SUPER, 6), (ANTIDOTE, 1), (PARLYZ, 1)], six) == [], "at every floor buys nothing"
    assert shopping_list(50000, 5, [(POTION, 4), (HYPER, 2), (ANTIDOTE, 1), (PARLYZ, 1)], six) == [], "any HP restore counts toward the floor"
    assert shopping_list(50000, 5, [(SUPER, 5), (ANTIDOTE, 1), (PARLYZ, 1)], six) == [(SUPER, 15)], "five restores sits under the floor"
    assert shopping_list(2400, 0, [], six) == [(POKE, 10), (ANTIDOTE, 2), (PARLYZ, 1)], "reserve cuts the Supers and trims the last cure"
    assert shopping_list(MONEY_RESERVE + 99, 0, [], six) == [], "under the reserve plus one of anything buys nothing"
    print("test_economy: ok")


if __name__ == "__main__":
    main()
