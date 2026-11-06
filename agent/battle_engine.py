"""Move choice from live battler data and the ROM's own move table."""
from dataclasses import dataclass

import rowe_rom as R
from rowe_state import BattleMon

TYPE_MYSTERY = 9

# effect ids of two-turn/charging moves, read from the ROM move table: the first turn deals no
# damage and shows no action menu, so a catch-chip that picks one desyncs the per-turn action
# read onto Bag and wedges the grid. 155 semi-invulnerable (Dig/Fly/Dive/Bounce/Phantom Force/
# Shadow Force), 151 Solar Beam, 75 charge (Razor Wind/Sky Attack/Freeze Shock/Ice Burn), 145
# Skull Bash.
CHARGING_EFFECTS = frozenset({75, 145, 151, 155})
# effect ids (constants/battle_move_effects.h) whose listed power the formula cannot take at face
# value. Two turns per hit, so half: the charging set above plus 80 recharge (Giga Impact). Never
# worth a pick on their power: 148 Future Sight lands two turns on and fails while one is pending,
# 158 Fake Out first turn only, 170 Focus Punch drops when hit, 7 self-KO, 8 Dream Eater and 92 Snore
# need a sleeper, 325 Belch an eaten berry, 305 Synchronoise a shared type, and 26/89/144/257 hit
# back off damage taken. 286 Last Resort fails until every other move has been used this battle.
TWO_TURN_EFFECTS = CHARGING_EFFECTS | {80}
NO_PICK_EFFECTS = frozenset({7, 8, 26, 89, 92, 144, 148, 158, 170, 257, 305, 325})
LAST_RESORT_EFFECT = 286

# abilities that take a move of the type for no damage, from the ABILITYEFFECT_ABSORBING branch of
# battle_util.c plus Levitate; ids resolve by name because the ROM's table outruns the vendored source
_TYPE_IMMUNE = {
    R.TYPE_NAMES.index("Water"): ("Water Absorb", "Dry Skin", "Storm Drain", "Water Compaction", "Evaporate"),
    R.TYPE_NAMES.index("Electric"): ("Volt Absorb", "Motor Drive", "Lightningrod"),
    R.TYPE_NAMES.index("Fire"): ("Flash Fire", "Well-Baked Body"),
    R.TYPE_NAMES.index("Ground"): ("Levitate", "Earth Eater"),
    R.TYPE_NAMES.index("Grass"): ("Sap Sipper",),
    R.TYPE_NAMES.index("Bug"): ("Insect Eater",),
    R.TYPE_NAMES.index("Steel"): ("Steel Eater",),
}
TYPE_IMMUNE = {t: frozenset(R.ability_id(n) for n in names) for t, names in _TYPE_IMMUNE.items()}


def immune(foe: BattleMon, move_type: int) -> bool:
    return foe.ability in TYPE_IMMUNE.get(move_type, ())


@dataclass
class Scored:
    slot: int
    move: R.Move
    damage: float
    effectiveness: float
    score: float


def expected_damage(user: BattleMon, foe: BattleMon, mv: R.Move, used=frozenset()) -> tuple:
    """Gen-3 base damage formula times STAB, type chart and accuracy, per turn the move costs.
    `used` is the slots user has picked this battle, the Last Resort precondition."""
    if mv.split == R.SPLIT_STATUS or mv.power == 0 or mv.effect in NO_PICK_EFFECTS:
        return 0.0, 1.0
    if mv.effect == LAST_RESORT_EFFECT:
        others = {i for i, m in enumerate(user.moves) if m and m != mv.id}
        if not others <= set(used):
            return 0.0, 1.0
    if mv.split == R.SPLIT_SPECIAL:
        atk, dfn = user.sp_atk, foe.sp_def
    else:
        atk, dfn = user.atk, foe.dfn
    eff = 0.0 if immune(foe, mv.type) else R.effectiveness(mv.type, [t for t in foe.types if t != TYPE_MYSTERY])
    stab = 1.5 if mv.type in user.types else 1.0
    base = ((2 * user.level / 5 + 2) * mv.power * atk / max(dfn, 1)) / 50 + 2
    acc = mv.accuracy / 100 if mv.accuracy else 1.0
    turns = 2 if mv.effect in TWO_TURN_EFFECTS else 1
    return base * stab * eff * acc / turns, eff


def rank_moves(user: BattleMon, foe: BattleMon, used=frozenset()) -> list:
    out = []
    for slot, (move_id, pp) in enumerate(zip(user.moves, user.pp)):
        if not move_id or not pp:
            continue
        mv = R.move(move_id)
        dmg, eff = expected_damage(user, foe, mv, used)
        # a status move scores under any hit that does damage, above a 0x hit
        score = dmg if dmg > 0 else (0.5 if mv.split == R.SPLIT_STATUS else 0.0)
        out.append(Scored(slot, mv, dmg, eff, score))
    out.sort(key=lambda s: (s.score, s.move.priority, user.pp[s.slot]), reverse=True)
    return out


def first_usable_slot(moves, pps) -> int:
    """Slot of the most-PP move that can actually be selected. The move chooser falls back
    here when scoring leaves nothing (every scored move disabled or 0x), and confirming a
    spent slot makes the game reject it with "no PP left" and wedge the action menu. When no
    move has PP the game auto-Struggles and the menu is never shown, so 0 is harmless."""
    usable = [i for i, (m, pp) in enumerate(zip(moves, pps)) if m and pp]
    return max(usable, key=lambda i: pps[i]) if usable else 0


def choose_move(user: BattleMon, foe: BattleMon) -> int:
    ranked = rank_moves(user, foe)
    return ranked[0].slot if ranked else 0


def move_value(types, move_id: int) -> float:
    """Worth of a move in a party slot, foe unknown: power times accuracy with STAB; status is 0."""
    if not 0 < move_id < R.MOVE_COUNT:
        return 0.0
    mv = R.move(move_id)
    if mv.split == R.SPLIT_STATUS or mv.power < 10 or mv.effect in NO_PICK_EFFECTS or mv.effect == LAST_RESORT_EFFECT:
        return 0.0
    acc = mv.accuracy / 100 if mv.accuracy else 1.0
    turns = 2 if mv.effect in TWO_TURN_EFFECTS else 1
    return mv.power * acc * (1.5 if mv.type in types else 1.0) / turns


def replacement_slot(mon, new_move: int) -> int | None:
    """Slot new_move should overwrite, or None when every current move is worth at least as much."""
    types = R.species(mon.species).types
    worth = [move_value(types, m) for m in mon.moves]
    slot = min(range(len(worth)), key=lambda s: worth[s])
    return slot if move_value(types, new_move) > worth[slot] else None


def as_battler(mon) -> BattleMon:
    """A bench PartyMon in BattleMon shape so the damage formula can score it against a foe."""
    return BattleMon(
        battler=-1, species=mon.species, level=mon.level, hp=mon.hp, max_hp=mon.max_hp,
        moves=mon.moves, pp=mon.pp, types=R.species(mon.species).types, ability=0,
        status1=mon.status, stat_stages=(6,) * 8, nickname=mon.nickname, personality=mon.personality,
        atk=mon.atk, dfn=mon.dfn, spd=mon.spd, sp_atk=mon.sp_atk, sp_def=mon.sp_def,
    )


def edge(user: BattleMon, foes: list) -> tuple:
    """(dealt, taken): the best hit user lands as a fraction of the foe's remaining HP, and the
    best hit the foes land as a fraction of user's, each capped at 1. Worst foe counts."""
    dealt, taken = 1.0, 0.0
    for foe in foes:
        hits = [s.damage for s in rank_moves(user, foe)]
        dealt = min(dealt, min(1.0, max(hits, default=0.0) / max(foe.hp, 1)))
        back = [expected_damage(foe, user, R.move(m))[0] for m, pp in zip(foe.moves, foe.pp)
                if 0 < m < R.MOVE_COUNT and pp]
        taken = max(taken, min(1.0, max(back, default=0.0) / max(user.hp, 1)))
    return dealt, taken


def strongest_bench(party: list, active: BattleMon, foes: list) -> tuple[int, float] | None:
    """(slot, dealt-minus-taken edge) of the bench mon best placed against foes, or None when no
    bench mon stands with a damaging move left."""
    bench = [m for m in party if m.hp > 0 and m.personality != active.personality
             and any(pp and R.move(mid).power >= 10 for mid, pp in zip(m.moves, m.pp))]
    if not bench:
        return None
    scored = {m.slot: (lambda d, t: d - t)(*edge(as_battler(m), foes)) for m in bench}
    best = max(scored, key=scored.get)
    return best, scored[best]


def outmatched(user: BattleMon, foes: list, frac: float = 0.5) -> bool:
    """Whether a foe holds a move super effective against user that takes at least `frac` of
    user's remaining HP in one hit, the fight a lead loses in two turns however far it outlevels."""
    for foe in foes:
        for m, pp in zip(foe.moves, foe.pp):
            if not (0 < m < R.MOVE_COUNT and pp):
                continue
            mv = R.move(m)
            if R.effectiveness(mv.type, user.types) > 1 and expected_damage(foe, user, mv)[0] >= frac * max(user.hp, 1):
                return True
    return False


def best_switch(party: list, active: BattleMon, foes: list, margin: float = 0.0, ko_edge: bool = True) -> int | None:
    """Party slot to send out against foes, or None to keep active on the field.

    A fainted active takes the bench mon with the best dealt-minus-taken edge. A standing
    active steps out when it cannot finish the foe this turn and either it is losing the
    exchange (edge below 0) w/ a bench mon beating its edge by `margin`, or a bench mon lands a
    one-hit KO where the active needs three hits or more (the type edge, Electric into Water);
    the free hit the switch hands the foe is worth that. `ko_edge` False turns that second
    route off, for a mon the type edge itself brought in, so two edges never chain into a
    switch every turn."""
    pick = strongest_bench(party, active, foes)
    if pick is None:
        return None
    best, score = pick
    if active.hp == 0:
        return best
    dealt, taken = edge(active, foes)
    if dealt >= 1.0:
        return None
    if ko_edge and dealt < 0.5 and edge(as_battler(next(m for m in party if m.slot == best)), foes)[0] >= 1.0:
        return best
    if dealt - taken >= 0 or score < dealt - taken + margin:
        return None
    return best


def weakening_move(user: BattleMon, foe: BattleMon) -> Scored | None:
    """Hardest hit expected to leave the foe standing, for chipping before a throw; the lowest safe
    hit stretched a catch over turns of free hits for the foe."""
    # power under 10 is a charge-up or counter move (Bide) whose listed power is a placeholder;
    # a CHARGING_EFFECTS move deals no damage on the turn it is picked and wedges the action read
    safe = [s for s in rank_moves(user, foe)
            if s.move.power >= 10 and s.move.effect not in CHARGING_EFFECTS and 0 < s.damage < foe.hp * 0.8]
    return max(safe, key=lambda s: s.damage) if safe else None
