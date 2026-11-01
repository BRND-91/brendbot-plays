"""A party under six while the PC holds a mon is short, and the next Center visit refills it: party_short
reads the gap, best_fill picks the box mon whose addition scores highest, fill_party brings back a member
of the last full party before anything else and otherwise withdraws by score until the party is full, a
swap order from the admin trades by species, and keep_snapshot leaves the state file alone on a signal or
w/ a short party, since a TERM between a swap's deposit and its withdraw is what wrote a five-mon state."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rowe_rom
from play import PARTY_SIZE, Player, best_fill, foe_types, keep_snapshot, mon_profile, party_short
from test_team import GREEDENT, ICE_BEAM, LAPRAS, MARILL, NO_IVS, TACKLE, WATER_GUN, Boxed, G, Mon
from test_team import Errands as SwapErrands


class Errands:
    def __init__(self, g: G):
        self.g, self.calls = g, []

    def withdraw_at_pc(self, slot: int) -> bool:
        """What the PC does: the box mon takes the first free party slot."""
        self.calls.append(slot)
        i = next(k for k, bm in enumerate(self.g._box) if bm.slot == slot)
        bm = self.g._box.pop(i)
        bm.slot = len(self.g._party)
        self.g._party.append(bm)
        return True


def player(g: G, state_path: str, errands=Errands) -> Player:
    p = Player.__new__(Player)
    p.g, p.errands, p.state_path = g, errands(g), state_path
    p.goal = {"mode": "grind", "map": [0, 16]}
    return p


def test_party_short():
    assert party_short(5, 47) is True
    assert party_short(5, 0) is False, "five caught in total is a full party"
    assert party_short(6, 47) is False


def test_best_fill_takes_the_coverage():
    team = [mon_profile(Mon(i, GREEDENT, 41, [TACKLE]), 41, NO_IVS) for i in range(5)]
    roxanne = [foe_types(rowe_rom.leader_build("Roxanne", 0))]
    pool = [(3, mon_profile(Boxed(3, GREEDENT, 41, [TACKLE]), 41, NO_IVS)),
            (7, mon_profile(Boxed(7, MARILL, 41, [WATER_GUN]), 41, NO_IVS))]
    assert best_fill(team, pool, roxanne) == 7, "Water on Rock beats a sixth Normal"
    assert best_fill(team, [], roxanne) is None


def test_fill_party_withdraws_to_six(tmp_path):
    box = [Boxed(30, MARILL, 41, [WATER_GUN]), Boxed(31, LAPRAS, 41, [ICE_BEAM]), Boxed(32, GREEDENT, 41, [TACKLE])]
    g = G([Mon(i, GREEDENT, 41, [TACKLE]) for i in range(4)], box, 3)
    p = player(g, str(tmp_path / "route101.ss"))
    p.fill_party()
    assert len(g.party()) == PARTY_SIZE, [m.species for m in g.party()]
    assert sorted(p.errands.calls) == [30, 31], f"the two coverage mons come in, the third Greedent stays, got {p.errands.calls}"
    p.fill_party()
    assert len(p.errands.calls) == 2, "a full party withdraws nothing"


def test_fill_party_brings_back_the_last_full_partys_member_first(tmp_path):
    lost = Boxed(32, GREEDENT, 41, [TACKLE])
    box = [Boxed(30, MARILL, 41, [WATER_GUN]), Boxed(31, LAPRAS, 41, [ICE_BEAM]), lost]
    g = G([Mon(i, GREEDENT, 41, [TACKLE]) for i in range(5)], box, 3)
    json.dump([m.personality for m in g.party()] + [lost.personality], open(tmp_path / "party_full.json", "w"))
    p = player(g, str(tmp_path / "route101.ss"))
    p.fill_party()
    assert p.errands.calls == [32], f"the deposited member returns ahead of the coverage mons, got {p.errands.calls}"


def test_swap_order_trades_by_species_and_consumes_the_file(tmp_path):
    camerupt, togedemaru = 323, 777
    g = G([Mon(i, GREEDENT, 41, [TACKLE]) for i in range(5)] + [Mon(5, togedemaru, 26, [TACKLE])],
          [Boxed(30, camerupt, 30, [TACKLE]), Boxed(31, camerupt, 34, [TACKLE])], 5)
    order = tmp_path / "swap_order.json"
    json.dump({"out": togedemaru, "in": camerupt}, open(order, "w"))
    p = player(g, str(tmp_path / "route101.ss"), SwapErrands)
    p.do_swap_order()
    assert p.errands.calls == [(5, 31)], f"the Togedemaru slot out, the higher Camerupt in, got {p.errands.calls}"
    assert not order.exists(), "a run order is deleted"
    led = json.load(open(tmp_path / "swaps.json"))
    assert str(g.party()[5].personality) in led["locked"], "the ordered mon is locked like a core swap"
    json.dump({"out": togedemaru, "in": camerupt}, open(order, "w"))
    p = player(g, str(tmp_path / "route101.ss"), SwapErrands)
    p.do_swap_order()
    assert p.errands.calls == [] and not order.exists(), "an order w/ no matching party mon is dropped"


def test_best_swap_never_trades_down_more_than_the_cutoff():
    from play import LEVEL_CUTOFF, best_swap
    team = [mon_profile(Mon(i, GREEDENT, 47, [TACKLE]), 47, NO_IVS) for i in range(6)]
    roxanne = [foe_types(rowe_rom.leader_build("Roxanne", 0))]
    marill = mon_profile(Boxed(28, MARILL, 28, [WATER_GUN]), 47, NO_IVS)
    raw = best_swap(team, [(28, marill)], roxanne, range(6), 1)
    assert raw is not None and raw[2] > 3, f"fixture: the Marill lifts the score, got {raw}"
    levels = ([47] * 6, {28: 47 - LEVEL_CUTOFF - 1})
    assert best_swap(team, [(28, marill)], roxanne, range(6), 1, levels) is None, "a L28 never replaces a L47"
    levels = ([47] * 6, {28: 47 - 3})
    assert best_swap(team, [(28, marill)], roxanne, range(6), 1, levels)[2] == raw[2] - 3, "three levels under costs three points"
    levels = ([47] * 6, {28: 47 - raw[2]})
    assert best_swap(team, [(28, marill)], roxanne, range(6), 1, levels) is None, "a deficit the size of the gain kills the trade"
    levels = ([47] * 6, {28: 47})
    assert best_swap(team, [(28, marill)], roxanne, range(6), 1, levels)[2] == raw[2], "at the floor the gain is the raw gain"


def test_party_row_resolves_every_id_to_its_name():
    from play import party_row
    from rowe_state import PartyMon
    camerupt = 323
    m = PartyMon(slot=2, species=camerupt, level=38, hp=55, max_hp=115, moves=(WATER_GUN, 0, 0, 0), pp=(17, 0, 0, 0),
                 status=0x40, experience=56444, friendship=120, nickname="Camerupt", personality=3,
                 atk=90, dfn=70, spd=40, sp_atk=95, sp_def=72, ot_id=0, ability_num=0, evs=(0,) * 6)
    row = party_row(m)
    assert row["types"] == ["Fire", "Ground"] and row["nature"] == "Adamant" and row["status"] == "PAR"
    assert row["stats"] == {"atk": 90, "def": 70, "spa": 95, "spd": 72, "spe": 40}
    assert row["ability"] == rowe_rom.ability_name(rowe_rom.species(camerupt).abilities[0]) and row["ability"].strip()
    assert row["nature_effect"] == {"up": "Atk", "down": "Sp. Atk"}
    assert row["ability_desc"].endswith(".") and "?" not in row["ability_desc"] and len(row["ability_desc"]) > 20, row["ability_desc"]
    assert rowe_rom.ability_description(11).startswith("If hit by a Water-type move, the Pokémon has its HP restored")
    m.personality = 0
    assert party_row(m)["nature"] == "Hardy" and party_row(m)["nature_effect"] is None
    assert row["moves"] == [{"name": "Water Gun", "type": "Water", "power": 40, "accuracy": 100, "pp": 17, "pp_max": 25}]
    assert (row["exp_lo"], row["exp_hi"]) == rowe_rom.exp_bounds(camerupt, 38) and row["personality"] == 3
    m.status = 0
    assert party_row(m)["status"] == ""


def test_ledger_locks_a_flex_swap_in_too(tmp_path):
    from play import CORE_SWAP_VISITS, SwapLedger
    led = SwapLedger(str(tmp_path / "swaps.json"))
    led.visit()
    led.record("flex", 11, 22)
    assert led.locked(11) and led.barred(22) and led.d["last_core_visit"] is None
    for _ in range(CORE_SWAP_VISITS - 1):
        led.visit()
        assert led.locked(11), led.d
    led.visit()
    assert not led.locked(11)


def test_keep_snapshot():
    assert keep_snapshot("signal", 6, 47) is True, "a TERM lands wherever the loop was, the last responsive snapshot stands"
    assert keep_snapshot("timer", 5, 47) is True, "a short party is never written"
    assert keep_snapshot("timer", 6, 47) is False
    assert keep_snapshot("timer", 5, 0) is False, "five caught in total is a full party"
