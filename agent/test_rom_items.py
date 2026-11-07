"""ROM-static extraction for the errands: sellable-loot and fossil item ids, Repel/ball tiers,
the Flying Taxi dispatcher and the Rustboro fossil scientist, and the taxi's destination menu."""
import rowe_rom as R

_SELL_AND_FOSSIL_PRICES = {
    "Star Piece": 9800, "Nugget": 10000, "Big Pearl": 7500, "Big Mushroom": 5000,
    "Stardust": 2000, "Pearl": 1400, "Ultra Ball": 600, "Great Ball": 300,
}


def test_item_id_round_trips_every_set_member():
    sets = R.item_sets()
    for item_id in sets["SELLABLE_ITEMS"] | sets["FOSSIL_ITEMS"] | set(sets["REPEL_ITEMS"]) | set(sets["BALL_TIERS"]):
        assert R.item_id(R.item_name(item_id)) == item_id


def test_sellable_drops_the_names_the_rom_lacks():
    sets = R.item_sets()
    assert sets["DROPPED"] == ("Big Nugget", "Balm Mushroom", "Comet Shard", "Pretty Wing")
    assert len(sets["SELLABLE_ITEMS"]) == 14 - len(sets["DROPPED"])


def test_fossil_items_all_present():
    assert len(R.item_sets()["FOSSIL_ITEMS"]) == 11


def test_item_prices_match_the_rom():
    for name, price in _SELL_AND_FOSSIL_PRICES.items():
        assert R.item_price(R.item_id(name)) == price, name


def test_repel_items_in_weakest_first_order():
    sets = R.item_sets()
    assert len(sets["REPEL_ITEMS"]) == 3
    assert sets["REPEL_STEPS"] == dict(zip(sets["REPEL_ITEMS"], (100, 200, 250)))


def test_poke_ball_resolves_to_the_catch_module_id():
    sets = R.item_sets()
    assert sets["BALL_TIERS"][0] == 4
    assert sets["BALL_MULT"][sets["BALL_TIERS"][0]] == 1.0


def test_ferry_and_fossil_reviver_rows_speak_their_lines():
    ferry = " ".join(R.script_texts(R.SLATEPORT_FERRY_NPC[-1]))
    assert "Where would you like to go" in ferry, ferry[:200]
    reviver = " ".join(R.script_texts(R.FOSSIL_REVIVER[-1]))
    assert "bring a Fossil back to life" in reviver, reviver[:200]
    assert "too many Pokémon" in reviver, reviver[:400]


def test_multichoice_rows_on_the_slateport_ferry_menu():
    rows = R.multichoice_rows("Slateport City")
    assert rows[0] == "Slateport City"
    assert "Southern Island" in rows and "Birth Island" in rows
    assert rows[-1] == "Exit"
    assert all(s and all(32 <= ord(c) < 127 for c in s) for s in rows)
