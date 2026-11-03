"""Core and flex scoring over leader builds. Six Greedent w/ Tackle at 0 badges: a boxed Marill w/ Water
Gun, projected to Azumarill at the floor, lifts the score against the League and the eight leaders past
the core margin and the score against Roxanne alone past the flex margin; a boxed Greedent is an equal
trade and never fires; a Glalie w/ Ice Beam credits Ice since its Atk and SpA tie; do_pc_swap spends at
most one swap per badge count."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rowe_rom
import rowe_symbols as S
from play import (CORE_MARGIN_FLOOR, FLEX_MARGIN, LEVEL_CUTOFF, Player, SwapLedger, best_swap, core_margin, flex_slot, foe_types,
                  mon_profile, score_flex, team_score, wanted_types)

NORMAL, FLYING, WATER, ICE, GRASS, POISON = 0, 2, 11, 15, 12, 3
GREEDENT, MARILL, AZUMARILL, LAPRAS, MAGIKARP, PIDGEY, ODDISH = 820, 183, 184, 131, 129, 16, 43  # Lapras: Atk 85, SpA 85 in this ROM
TACKLE, WATER_GUN, ICE_BEAM, SPARK, GUST, GIGA_DRAIN = 33, 55, 58, 209, 16, 202
NO_IVS = (0, 0, 0, 0, 0, 0)


class Mon:
    made = 0

    def __init__(self, slot: int, species: int, level: int, moves: list):
        self.slot, self.species, self.level, self.moves = slot, species, level, tuple(moves)
        self.nature, self.evs = 0, NO_IVS
        self.nickname = rowe_rom.TYPE_NAMES[rowe_rom.species(species).types[0]]
        Mon.made += 1
        self.personality = Mon.made
        self.experience = rowe_rom.exp_bounds(species, level)[0]


Boxed = Mon


class G:
    def __init__(self, party: list, box: list, badges: int):
        self._party, self._box, self._badges = party, box, badges

    def party(self) -> list:
        return self._party

    def boxes(self) -> list:
        return self._box

    def badges(self) -> int:
        return self._badges

    def flag(self, flag_id: int) -> bool:
        return flag_id - S.FLAG_BADGE01 < self._badges

    def iv_boosts(self) -> tuple:
        return NO_IVS

    def swap(self, out: int, slot: int) -> None:
        """What the PC does: the party mon goes to the box slot, the box mon takes the party slot."""
        i = next(k for k, bm in enumerate(self._box) if bm.slot == slot)
        self._party[out], self._box[i] = self._box[i], self._party[out]
        self._party[out].slot, self._box[i].slot = out, slot


class Errands:
    def __init__(self, g: G):
        self.g, self.calls = g, []

    def swap_at_pc(self, out: int, slot: int) -> bool:
        self.calls.append((out, slot))
        self.g.swap(out, slot)
        return True


def player(g: G, state_path: str) -> Player:
    p = Player.__new__(Player)
    p.g, p.errands, p.state_path = g, Errands(g), state_path
    p.goal = {"mode": "grind", "map": [0, 16]}
    return p


def main() -> None:
    assert rowe_rom.species(GREEDENT).types == (NORMAL, NORMAL)
    assert rowe_rom.species_at_level(MARILL, 41) == AZUMARILL
    assert rowe_rom.move(TACKLE).split == rowe_rom.SPLIT_PHYSICAL and rowe_rom.move(ICE_BEAM).split == rowe_rom.SPLIT_SPECIAL

    party = [Mon(i, GREEDENT, 41, [TACKLE]) for i in range(6)]
    team = [mon_profile(m, 41, NO_IVS) for m in party]
    core = [foe_types(rowe_rom.leader_build(n, min(i, 8))) for i, n in enumerate(rowe_rom.LEADERS)]
    core += [foe_types(rowe_rom.leader_build(n, rowe_rom.LEAGUE_BADGES)) for n in rowe_rom.LEAGUE]
    roxanne = foe_types(rowe_rom.leader_build("Roxanne", 0))
    assert team_score(team, core) == 32, "characterization pin, six Normals w/ Tackle vs 13 builds"
    assert core_margin(team, core) == CORE_MARGIN_FLOOR
    flex = flex_slot(team, core)
    core_slots = [i for i in range(6) if i != flex]

    marill = mon_profile(Boxed(0, MARILL, 3, [WATER_GUN]), 41, NO_IVS)
    assert (marill.species, marill.attack_types) == (AZUMARILL, frozenset({WATER})), marill
    plan = best_swap(team, [(0, marill)], core, core_slots, core_margin(team, core))
    assert plan is not None and plan[1] == 0 and plan[0] in core_slots, f"a Water attacker lifts the core, got {plan}"
    plan = best_swap(team, [(0, marill)], [roxanne], [flex], FLEX_MARGIN)
    assert plan is not None and plan[0] == flex, f"Water on Rock fills the flex slot, got {plan}"

    same = mon_profile(Boxed(0, GREEDENT, 41, [TACKLE]), 41, NO_IVS)
    assert best_swap(team, [(0, same)], core, core_slots, core_margin(team, core)) is None, "an even trade never fires"
    assert best_swap(team, [(0, same)], [roxanne], [flex], FLEX_MARGIN) is None

    glalie = mon_profile(Boxed(0, LAPRAS, 41, [ICE_BEAM]), 41, NO_IVS)
    assert glalie.attack_types == frozenset({ICE}), f"a tied Atk/SpA credits both splits, got {glalie}"
    assert rowe_rom.species(LAPRAS).base_stats[1] == rowe_rom.species(LAPRAS).base_stats[4]

    mixed = team[:5] + [marill]
    assert flex_slot(mixed, core) != 5, "the one mon w/ coverage is core, a Greedent is the flex slot"
    ROCK, FIRE, GROUND, GHOST = 5, 10, 4, 7
    gaps = wanted_types(team, core)
    assert {ROCK, FIRE, GROUND, GHOST} <= gaps, f"Normal attacks alone leave every foe type wanted, got {gaps}"
    gaps = wanted_types(mixed, core)
    assert not {ROCK, FIRE, GROUND} & gaps and GHOST in gaps, f"a Water attack closes Rock, Fire and Ground, got {gaps}"

    with tempfile.TemporaryDirectory() as d:
        state = os.path.join(d, "route101.ss")
        ledger = os.path.join(d, "swaps.json")
        marill_box, lapras_box = Boxed(0, MARILL, 41, [WATER_GUN]), Boxed(1, LAPRAS, 41, [ICE_BEAM])
        g = G([Mon(i, GREEDENT, 41, [TACKLE]) for i in range(6)], [marill_box, lapras_box], 3)
        greedents = {m.personality for m in g.party()}
        p = player(g, state)
        p.do_pc_swap()
        assert p.errands.calls and p.errands.calls[0][1] == 0, f"visit 1 takes Marill into the core, got {p.errands.calls}"
        led = json.load(open(ledger))
        assert led["last_core_visit"] == 1 and led["locked"] == {str(marill_box.personality): 5}, led
        out_first = next(iter(led["barred"]))
        assert int(out_first) in greedents and led["barred"][out_first] == 9, led
        for visit in range(2, 5):
            p = player(g, state)
            p.do_pc_swap()
            led = json.load(open(ledger))
            assert led["visits"] == visit and led["last_core_visit"] == 1, f"core budget closed through visit 4, got {led}"
        assert marill_box in g.party(), "a mon swapped into the core stays four visits"
        assert all(bm.personality != int(out_first) for bm in g.party()), "the swapped-out mon never comes straight back"
        p = player(g, state)
        p.do_pc_swap()
        led = json.load(open(ledger))
        assert led["visits"] == 5 and len(p.errands.calls) <= 1 and led["last_core_visit"] in (1, 5), led
        # the level cutoff: a candidate ten under the grind map's top wild level is cut before scoring
        # Spark (physical Electric) covers Water and Flying, so a low Magikarp, Gyarados at the floor, is not a wanted type
        top_map, (_, top) = max(rowe_rom.wild_land_levels().items(), key=lambda kv: kv[1][1])
        g2 = G([Mon(i, GREEDENT, 41, [TACKLE, SPARK]) for i in range(6)], [Boxed(0, MAGIKARP, max(1, top - LEVEL_CUTOFF - 1), [TACKLE])], 3)
        p = player(g2, os.path.join(d, "two.ss"))
        p.goal = {"mode": "grind", "map": list(top_map)}
        p.do_pc_swap()
        assert not p.wanted & {WATER, FLYING}, p.wanted
        assert p.errands.calls == [], f"a L{top - LEVEL_CUTOFF - 1} catch under a L{top} grind map is cut, got {p.errands.calls}"
        p.goal = {"mode": "gym", "map": [11, 3]}
        p.do_pc_swap()
        assert len(p.errands.calls) == 1, "off a grind the cutoff does not apply"
        # a wanted-type catch is exempt from the cutoff: six Normals want Water's targets, so a low Marill scores
        g3 = G([Mon(i, GREEDENT, 41, [TACKLE]) for i in range(6)], [Boxed(0, MARILL, max(1, top - LEVEL_CUTOFF - 1), [WATER_GUN])], 3)
        p = player(g3, os.path.join(d, "three.ss"))
        p.goal = {"mode": "grind", "map": list(top_map)}
        p.wanted = frozenset({WATER})
        p.do_pc_swap()
        assert len(p.errands.calls) == 1, "a Water catch on a Water-wanting party is exempt from the cutoff"

    # flex scoring at the cap: the flex slot asks which mon the grind makes the better counter to the
    # next leader, so a low Grass/Poison counter still beats a Rock-weak flyer into Roxanne while a
    # higher one of the same type wins on the smaller grind cost.
    assert rowe_rom.species(PIDGEY).types == (NORMAL, FLYING) and rowe_rom.species(ODDISH).types == (GRASS, POISON)
    roxanne_now = foe_types(rowe_rom.leader_build("Roxanne", 0))
    pidgey = mon_profile(Mon(0, PIDGEY, 15, [GUST]), 15, NO_IVS)
    oddish = mon_profile(Boxed(0, ODDISH, 4, [GIGA_DRAIN]), 15, NO_IVS)
    assert oddish.attack_types == frozenset({GRASS}), f"a special Grass move credits Grass, got {oddish}"
    assert score_flex(pidgey, 15, 15, roxanne_now) == 0, "a Rock-weak flyer counters Roxanne for nothing"
    assert score_flex(oddish, 4, 15, roxanne_now) == 2, "a L4 Grass counter clears the flex margin once grown to the cap"
    assert score_flex(oddish, 15, 15, roxanne_now) == 4, "the same counter at the cap pays no grind cost"

    with tempfile.TemporaryDirectory() as d:
        state = os.path.join(d, "route101.ss")
        ledger = os.path.join(d, "swaps.json")
        strong = [Mon(0, MARILL, 15, [WATER_GUN]), Mon(1, LAPRAS, 15, [ICE_BEAM]), Mon(2, GREEDENT, 15, [SPARK]),
                  Mon(3, GREEDENT, 15, [TACKLE]), Mon(4, GREEDENT, 15, [TACKLE])]
        # core closed on the ledger (a swap four visits back), so the flex path is what runs
        json.dump({"visits": 5, "last_core_visit": 5}, open(ledger, "w"))
        pidgey_mon = Mon(5, PIDGEY, 15, [GUST])
        low, high = Boxed(0, ODDISH, 4, [GIGA_DRAIN]), Boxed(1, ODDISH, 15, [GIGA_DRAIN])
        g = G(list(strong) + [pidgey_mon], [low, high], 0)
        p = player(g, state)
        p.goal = {"mode": "grind", "map": [0, 16], "cap": 15}
        team = [mon_profile(m, 15, NO_IVS) for m in g.party()]
        assert flex_slot(team, p.scoring_builds()[0]) == 5, "the Rock-weak flyer is the flex slot"
        p.do_pc_swap()
        assert p.errands.calls == [(5, 1)], f"Pidgey out of the flex slot, the L15 Grass/Poison in over the L4, got {p.errands.calls}"
        assert pidgey_mon not in g.party() and high in g.party(), "the flyer is gone and the cap-level counter is in"
        led = json.load(open(ledger))
        assert led["flex_locked"] == {str(high.personality): 0}, led
        lg = SwapLedger(ledger)
        assert lg.flex_hold(high.personality, 0) and not lg.flex_hold(high.personality, 1), "the hold lifts once Roxanne is beaten"

        # the churn guard gates do_pc_swap: with the flyer flex-locked for Roxanne the swap is held,
        # without the lock the same board swaps, so the lock is what blocks it
        def board():
            fresh = [Mon(i, m.species, 15, list(m.moves)) for i, m in enumerate(strong)] + [Mon(5, PIDGEY, 15, [GUST])]
            return G(fresh, [Boxed(0, ODDISH, 15, [GIGA_DRAIN])], 0), fresh[5]
        g2, locked_flyer = board()
        json.dump({"visits": 5, "last_core_visit": 5, "flex_locked": {str(locked_flyer.personality): 0}}, open(ledger, "w"))
        p = player(g2, state)
        p.goal = {"mode": "grind", "map": [0, 16], "cap": 15}
        p.do_pc_swap()
        assert p.errands.calls == [], f"a flex-locked flyer is held before Roxanne is beaten, got {p.errands.calls}"
        g3, _ = board()
        json.dump({"visits": 5, "last_core_visit": 5}, open(ledger, "w"))
        p = player(g3, state)
        p.goal = {"mode": "grind", "map": [0, 16], "cap": 15}
        p.do_pc_swap()
        assert p.errands.calls == [(5, 0)], f"the same board with no lock swaps the flyer out, got {p.errands.calls}"
    print("ok")


if __name__ == "__main__":
    main()
