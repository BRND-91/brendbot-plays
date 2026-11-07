"""Catch odds from the ROM species table and the policy for what gets a ball.

Odds follow Cmd_handleballthrow: odds = catchRate * ballMult * (3*maxHP - 2*hp) / (3*maxHP),
x2 asleep or frozen, x1.5 under any other status; 255+ is a sure catch, otherwise
four shake checks each passing with probability 1048560 / sqrt(sqrt(16711680 / odds)) / 65536.
"""
import json
import os

import rowe_rom as R
from battle_engine import as_battler, weakening_move
from rowe_state import BattleMon

STATUS_SLEEP = 0x07
STATUS_FREEZE = 0x20
STATUS_MOVES = {"Poison Gas", "Poison Powder", "Sleep Powder", "Stun Spore", "Thunder Wave",
                "Hypnosis", "Toxic", "Spore", "Will-O-Wisp", "Glare", "Sing", "Yawn"}
# type ids: POISON 3, GROUND 4, STEEL 8, FIRE 10, GRASS 12, ELECTRIC 13 (gBaseStats order)
_POISON, _GROUND, _STEEL, _FIRE, _GRASS, _ELECTRIC = 3, 4, 8, 10, 12, 13
# foe types a status move does nothing to (pokeemerald-expansion rules): Poison and Steel
# take no poison, Grass no powder or spore, Electric no paralysis, Ground no Thunder Wave,
# Fire no burn; a Weedle took seven Poison Gases before this table existed
STATUS_IMMUNE = {"Poison Gas": {_POISON, _STEEL}, "Toxic": {_POISON, _STEEL},
                 "Poison Powder": {_POISON, _STEEL, _GRASS}, "Sleep Powder": {_GRASS}, "Spore": {_GRASS},
                 "Stun Spore": {_GRASS, _ELECTRIC}, "Thunder Wave": {_GROUND, _ELECTRIC}, "Glare": {_ELECTRIC},
                 "Will-O-Wisp": {_FIRE}}
POKE_BALL = 4
BALL_RESERVE = 3  # the last balls go only to a foe whose type the core cannot hit super effectively


def catch_chance(foe: BattleMon, ball_mult: float = 1.0) -> float:
    if not 0 <= foe.species < R.SPECIES_COUNT:
        # a species id past the ROM table has no catch_rate row, so odds are undefined and the foe
        # is uncatchable. R.species() raises on it, which would crash the battle step and the run.
        return 0.0
    rate = R.species(foe.species).catch_rate * ball_mult
    odds = rate * (3 * foe.max_hp - 2 * foe.hp) / (3 * foe.max_hp)
    if foe.status1 & (STATUS_SLEEP | STATUS_FREEZE):
        odds *= 2
    elif foe.status1:
        odds *= 1.5
    if odds <= 0:
        return 0.0
    if odds >= 255:
        return 1.0
    shake = 1048560 / (16711680 / odds) ** 0.25
    return (shake / 65536) ** 4


def strongest_ball(balls: dict) -> tuple:
    """(item id, catch multiplier) of the strongest ball tier in the pocket, (POKE_BALL, 1.0) when
    none of the tiers are held. `balls` is {item id: qty} off the Poké Balls pocket; BALL_TIERS runs
    weakest-first, so the reversed walk takes Ultra over Great over Poké."""
    sets = R.item_sets()
    for iid in reversed(sets["BALL_TIERS"]):
        if balls.get(iid, 0) > 0:
            return iid, sets["BALL_MULT"][iid]
    return POKE_BALL, 1.0


def ball_count(balls: dict) -> int:
    """Throwable balls summed across the tiers, so the catch count sees Great and Ultra Balls a
    Poké-Ball-only read missed."""
    tiers = R.item_sets()["BALL_TIERS"]
    return sum(qty for iid, qty in balls.items() if iid in tiers)


def status_move_slot(user: BattleMon, foe: BattleMon) -> int | None:
    """Slot of a usable status-inflicting move the foe's types do not shrug off, when the foe
    carries no status yet."""
    if foe.status1:
        return None
    for slot, (move_id, pp) in enumerate(zip(user.moves, user.pp)):
        if not (move_id and pp):
            continue
        name = R.move(move_id).name
        if name in STATUS_MOVES and not STATUS_IMMUNE.get(name, set()) & set(foe.types):
            return slot
    return None


def helper_slot(party, active: BattleMon, foe: BattleMon) -> int | None:
    """Bench slot worth switching in to set up a catch: a mon w/ a usable status move first,
    else one whose lightest hit leaves the foe standing. None when the bench has neither."""
    bench = [m for m in party if m.hp > 0 and m.personality != active.personality]
    for m in bench:
        if status_move_slot(as_battler(m), foe) is not None:
            return m.slot
    for m in bench:
        if weakening_move(as_battler(m), foe) is not None:
            return m.slot
    return None


class Ledger:
    """Species already caught this save, kept beside the save state so a restart doesn't re-catch them."""

    def __init__(self, path: str, party_species) -> None:
        self.path = path
        self.caught = set(party_species)
        if os.path.exists(path):
            with open(path) as f:
                self.caught |= set(json.load(f))

    def wants(self, foe: BattleMon, wanted: frozenset = frozenset(), balls: int = BALL_RESERVE + 1,
              species: int | None = None) -> bool:
        """A species not caught yet; once the bag is down to BALL_RESERVE balls, only one carrying a type
        in `wanted`, the types no core attack hits super effectively, or the one `species` the grind
        goal went out for, which the reserve is for. The goal names the encounter table's row and the
        post-clear scaling fields that row at its evolved stage, Teddiursa's slot as a L52 Ursaluna, so
        the form the row takes at the foe's level counts as the goal species."""
        if foe.species in self.caught:
            return False
        goal_form = species is not None and foe.species in (species, R.species_at_level(species, foe.level))
        return goal_form or balls > BALL_RESERVE or bool(set(foe.types) & wanted)

    def record(self, species: int) -> None:
        self.caught.add(species)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(sorted(self.caught), f)
        os.replace(tmp, self.path)
