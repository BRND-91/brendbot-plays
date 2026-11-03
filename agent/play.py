"""ROWE play loop on the stream.

    play.py --state states/live.ss [--minutes 120]

Goals come from states/goal.json: grind a map to a level cap, travel to a map,
or explore outward to uncover new ones. Travel and explore route over the ROM's
connection and warp tables plus the live reads the loop records (map_graph), and
a hop is taken by walking the border or stepping into the warp. Battle:
open Fight, pick the ranked move, confirm, repeat until the battle ends.
Progress lines go to stdout for the track-task tail.
"""
import argparse
import collections
import json
import os
import random
import signal
import sys
import time
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb  # noqa: E402
import rowe_rom  # noqa: E402
from battle_engine import as_battler, best_switch, edge, first_usable_slot, outmatched, rank_moves, replacement_slot, strongest_bench, weakening_move  # noqa: E402
import catch  # noqa: E402
import map_graph  # noqa: E402
import planner  # noqa: E402
import rowe_live  # noqa: E402
import rowe_map  # noqa: E402
import rowe_symbols as S  # noqa: E402
import script_decode  # noqa: E402
from nav import DIVE_BEHAVIORS, Grid, ITEM_WATERFALL_TOOL, Navigator, WATER_BEHAVIORS  # noqa: E402
from routines import Errands  # noqa: E402
from rowe_state import GameState  # noqa: E402
from stream_sink import FrameStreamer  # noqa: E402


_ROM_SHA = None

# Seagallop ferry gates on the overworld heartbeat: CD1 the ferry-service unlock, CE8 and CE7 the
# archipelago unlocks, so a Sevii crossing is visible with the gate flags it rode in one line.
FERRY_FLAGS = (0xCD1, 0xCE8, 0xCE7)


def rom_sha() -> str:
    """sha256 of the ROM on disk, computed once; the live page compares it against the
    rom_sha stamped in species.json and refuses to render on a mismatch."""
    global _ROM_SHA
    if _ROM_SHA is None:
        import hashlib
        with open(eb.ROM, "rb") as f:
            _ROM_SHA = hashlib.sha256(f.read()).hexdigest()
    return _ROM_SHA


class StopRequested(Exception):
    """Raised from run() once a stop signal arrived, so any nested walk or battle unwinds."""


class NullStreamer:
    """Stand-in when running w/o the HLS feed; frames are dropped, no pacing."""

    def push(self, screen) -> None:
        pass

    def close(self) -> None:
        pass

ROUTE_101 = (0, 16)
OLDALE = (0, 10)
LITTLEROOT = (0, 9)


def service_towns() -> dict:
    """town -> (Center, Mart) for every overworld map whose doors lead to one of each, off the
    ROM's map headers, so a town serves the party the first time the walk reaches it."""
    out = {}
    for n in range(rowe_rom.map_count(0)):
        dests = {d for *_, d in rowe_rom.map_warps(0, n)}
        pc = next((d for d in sorted(dests) if rowe_rom.is_center(*d)), None)
        mart = next((d for d in sorted(dests) if rowe_rom.is_mart(*d)), None)
        if pc and mart:
            out[(0, n)] = (pc, mart)
    return out


# the errands run on the town and its two buildings; the loop travels to the nearest town otherwise
SERVICE = service_towns()
SERVICE_MAPS = {town: frozenset({town, *rooms}) for town, rooms in SERVICE.items()}
TALL_GRASS_ID = 13  # every wild battle on Route 101 started on a 0x600D cell
GRASS_WAIT_TICKS = 20  # 60-frame waits w/ no reachable grass before the grind map is given up
GRASS_IDLE_CAP = 600  # seconds idling w/ no grass reachable anywhere before exiting no_grass_idle
# recorded press routes through gym puzzles the grid cannot see (Fortree's rotating gates),
# keyed "group,num", written by probe_fortree_bfs.py and replayed by Errands.follow_route
GYM_ROUTES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gym_routes.json")


def gym_routes() -> dict:
    if not os.path.exists(GYM_ROUTES_PATH):
        return {}
    with open(GYM_ROUTES_PATH) as f:
        return {tuple(int(n) for n in k.split(",")): v for k, v in json.load(f).items()}


GYM_ROUTES = gym_routes()

_GYM_MAP_SETS: dict = {}


def gym_map_set(gym: tuple, cap: int = 6) -> frozenset:
    """The gym's interior maps: the entry map plus every indoor map reached from it through warps,
    so a leader on a lower floor (Lavaridge's B1F behind the 1F fall holes) counts as inside the
    gym. The entry's exit warp leads to the town, which stays out. Testing the INDOOR map type and
    not a connection count keeps a dive-only city like Sootopolis (0, 7), which carries no
    connections of its own, out too; cap bounds a warp chain that would otherwise pull a dungeon
    in."""
    hit = _GYM_MAP_SETS.get(gym)
    if hit is not None:
        return hit
    seen = {gym}
    frontier = [gym]
    interior = {gym}
    while frontier and len(interior) < cap:
        g, n = frontier.pop()
        for _x, _y, dest in rowe_rom.map_warps(g, n):
            if dest in seen:
                continue
            seen.add(dest)
            if rowe_rom.is_indoor(*dest):
                interior.add(dest)
                frontier.append(dest)
    result = frozenset(interior)
    _GYM_MAP_SETS[gym] = result
    return result


ROUTE_RESETS = 3  # door re-entries per gym visit before an off-route run falls back to the sweep
ICE_FALL_FLOOR = {(15, 0): (15, 1)}  # Sootopolis: a second step on a cracked ice tile drops the party here
ICE_DOOR_TILE = {(15, 0): (8, 25)}   # the gym door, where the cover route starts on fresh ice
HEAL_HP_PERCENT = 30
POTION_HP_PERCENT = 30  # lead HP under this fraction uses a bag heal before the wild flee
GYM_READY_HP_PERCENT = 70  # a gym approach tops off at a Center below this lead HP or under two PP attackers
# Medicine-pocket HP restoratives on this ROM, id -> HP restored (0xffff heals fully), named
# off the item table. A status cure, a revive, a PP item or a flute is not here, so the bag
# heal is only ever a straight HP restore.
HP_ITEMS = {28: 20, 37: 60, 36: 120, 35: 0xffff, 34: 0xffff,
            41: 30, 42: 50, 43: 70, 44: 100, 59: 20, 60: 20}
THROW_AT = 0.5  # per-ball catch chance worth a throw without softening the foe first
THROW_FLOOR = 0.25  # under this, w/ no way to soften the foe, the ball stays in the bag and the fight is fought
PARTY_SIZE = 6  # a six-mon party has caught its team; balls stop being a spend priority
MONEY_RESERVE = 1000  # kept after any Mart trip so a lost fight never strands the next heal
# Spend table, (floor, batch) per item class: under the floor the item joins the shopping list and
# the batch is what one trip buys, trimmed to what the money past the reserve covers. Wild
# battles pay nothing in gen 3, so trainer prize money is the only income.
BALL_SPEND = (3, 20)  # party short of six: balls are the catch budget
BALL_SPEND_FULL = (5, 10)  # full party: a few for PC box swaps
HP_SPEND = (3, 5)
CURE_SPEND = (1, 2)
HP_TIER_PERCENT = 70  # one use of the bought restore covers this much of the party's largest max HP
HP_TIERS = (28, 37, 36)  # Potion, Super Potion, Hyper Potion
CURE_BUYS = (29, 33)  # Antidote, Parlyz Heal


def hp_tier(max_hp: int) -> int:
    """Item id of the smallest HP restore whose one use covers HP_TIER_PERCENT of max_hp, the
    Hyper Potion past that, so the battle chooser's smallest-that-covers pick is one item per heal."""
    need = max_hp * HP_TIER_PERCENT // 100
    return next((iid for iid in HP_TIERS if HP_ITEMS[iid] >= need), HP_TIERS[-1])


def shopping_list(money: int, balls: int, medicine: list, party: list) -> list:
    """[(item id, qty)] for the next counter: balls, then HP restores, then cures, each only
    when its count sits under the floor, each batch cut to the money left past the reserve."""
    held = dict(medicine)
    floor, batch = BALL_SPEND if len(party) < PARTY_SIZE else BALL_SPEND_FULL
    wants = []
    if balls < floor:
        wants.append((catch.POKE_BALL, batch))
    if sum(q for iid, q in medicine if iid in HP_ITEMS) < HP_SPEND[0]:
        wants.append((hp_tier(max(m.max_hp for m in party)), HP_SPEND[1]))
    wants.extend((iid, CURE_SPEND[1]) for iid in CURE_BUYS if held.get(iid, 0) < CURE_SPEND[0])
    budget = money - MONEY_RESERVE
    out = []
    for iid, qty in wants:
        price = rowe_rom.item_price(iid)
        qty = min(qty, budget // price)
        if qty > 0:
            out.append((iid, qty))
            budget -= qty * price
    return out
OUTCOME_CAUGHT = 7
OUTCOME_LOST = 2  # gBattleOutcome when the party faints out, which whites the player to the last Center
OUTCOME_DREW = 3  # both sides down the same turn, a gym non-clear the same as a loss
GYM_LOSS_CAP = 2  # whiteouts against one gym before it is closed so the ladder routes past it
LEAD_GAP = 3  # levels the lead may sit above the party's lowest before the lowest takes point
SWITCH_MARGIN = 0.25  # edge a bench mon must hold over a losing fighter to be worth the free hit
ACTION_POKEMON = 2  # action-menu cursor for Pokémon; grid is Fight 0, Bag 1, Pokémon 2, Run 3
SWITCH_FAIL_CAP = 3  # voluntary-switch tries before the chooser gives up and fights, so an action
# grid the presses never land the party menu from cannot spin the battle step forever
STUCK_GATE = 3  # stuck crossings of one border before it is gated in the graph, so a warp the walk
# never clears stops being re-picked every tick once the per-battle _stuck clear wipes its run record
BLOCKED_STREAK = 5  # blocked crossings of one border from one tile before the run ends for a relaunch
# off the snapshot, since travel_toward retakes the only graph route however often it was blocked
BOUNCE_STREAK = 3  # round trips through one hop from one area before the run ends, for the same reason
IDLE_STREAK = 5  # explore ticks finding no hop before the run re-plans, so a pocket whose every exit
# bounced or dead-ended relaunches off the snapshot instead of freezing the frame on run(60) forever
CYCLE_WINDOW = 12  # recent map landings watched for a loop longer than the 2-map bounce _last_hop catches
CYCLE_HITS = 4  # times one map recurs in that window with no new map found before the run re-plans
CB2_EVOLUTION = 0x8197385  # gMain.callback2 while "What? X is evolving!" plays, read off a stall dump
CB2_NAMING = 0x813088D  # gMain.callback2 on the nickname keyboard, read off a stall dump; START is its OK
BATTLE_TYPE_TRAINER = 0x08  # gBattleTypeFlags bit; a trainer battle refuses Run
BATTLE_TYPE_DOUBLE = 0x01  # gBattleTypeFlags bit; two foe slots, so a wild encounter never collapses to single
# gBattlescriptCurrInstr offsets into BattleScript_AskToLearnMove, the layout the move-learn
# flow shares across builds (vendor/pokebot-gen3 battle_move_replacing): the "Delete a move to
# make room for X?" box at +0x11 (also the move-select summary screen, gMain.callback2
# S.CB2_MOVE_SELECT) and the "Stop learning X?" box at +0x20. A level-up reached mid-battle
# settles a step early on the lead-in text, so the whole region routes to learn_step, not the
# two box addresses alone, which a staged dump froze on but the live loop steps past.
ASK_TO_LEARN = 0x83963FE
LEARN_PROMPT = ASK_TO_LEARN + 0x11
STOP_LEARN_PROMPT = ASK_TO_LEARN + 0x20
CB2_MOVE_SELECT = S.CB2_MOVE_SELECT
MOVE_SELECT_CANCEL_ROW = 4  # the summary lists the four held moves, then the new one as the cancel row
CB2_PARTY_MENU = S.CB2_PARTY_MENU
SNAPSHOT_SECONDS = 120  # savestate snapshot cadence, taken right after a battle resolves
REPLAN_BURST = 5        # goal exits inside REPLAN_WINDOW_S before the process hands back to the supervisor
REPLAN_WINDOW_S = 120
STATUS_SECONDS = 15  # status.json write cadence, so the overlay and planner refresh between battles
STALL_STEPS = 60  # ~30s of battle frames; an evolution scene holds the signature for ~20s
WEDGE_STEPS = 12  # steps the controller func, battlescript instr, cb2 and HP/PP all hold identical
# before the battle engine is wedged and the run bails for a snapshot relaunch. A live battle moves
# one of these within a few steps; a script-main freeze holds all of them. Clear of the live-battle
# max so an animation never trips it, well under STALL_STEPS so the bail runs in seconds
PACE =[eb.KEY_LEFT, eb.KEY_LEFT, eb.KEY_UP, eb.KEY_RIGHT, eb.KEY_RIGHT, eb.KEY_DOWN]
# move menu is a 2x2 grid: 0 1 / 2 3
MOVE_GRID = {0: (0, 0), 1: (1, 0), 2: (0, 1), 3: (1, 1)}
# action-grid nav retries. A held text box or open submenu (Bag/Pokemon) parks the cursor off
# Fight and eats the UP+LEFT, so each retry taps B to dismiss it first; B on the bare grid is a
# no-op. Widened past the old 3 so a stubborn submenu gets more dismiss attempts before the
# prompt fallback, the 0x83aa958 attack-turn wedge the 3x cap could not clear
ACT_NAV_RETRIES = 6
MOVE_OPEN_RETRIES = 4   # A presses to open the Fight list; the first is eaten while the "What will X do?" text draws
MOVE_STEER_RETRIES = 6  # hops to land the move cursor, re-read each step so a dropped tap retries
PARTY_MENU_WALK_RETRIES = 3  # walks to settle the party cursor on the live target before A; a stale slot read re-walks
# a battler's controller holds one of these idle funcs after its intro text ("X appeared!", "Go! X!")
# and before its action menu opens, one value per battler slot. battler 0 at 0x83AA958 is the player
# lead's post-intro idle. pressing A again here instead of waiting for the engine to open the menu
# desyncs a wild double into a freeze no input recovers (the Golbat+Lunatone double on map [24, 0]).
INTRO_IDLE_FUNCS = frozenset({0x083AA958, 0x083AA964, 0x083AA968})
INTRO_STEP_FRAMES = 180     # frames to let one intro text box clear after an A before the next press
INTRO_PROMOTE_FRAMES = 300  # frames to wait at the post-intro idle for the action menu to open, no press
INTRO_PRESSES = 8           # A presses one battle_step spends advancing an intro before it yields
# one frame of hold is a press edge to the ROM's newKeys read; the release frames give the next
# press a fresh edge. The old 8+12 spent 20 frames (333 ms at the stream's real-time clock) per key
TAP_HOLD = 2
TAP_GAP = 3
MENU_POLL_FRAMES = 2        # poll step for menu waits that gate on a RAM readback instead of a fixed run()
INTRO_POLL_FRAMES = 5       # frames per poll while waiting on the engine; the press fires the poll after the
                            # controller moves, so a tighter poll shortens the gap without pressing early
KEY_NAMES = {eb.KEY_A: "A", eb.KEY_B: "B", eb.KEY_UP: "UP", eb.KEY_DOWN: "DOWN", eb.KEY_LEFT: "LEFT",
             eb.KEY_RIGHT: "RIGHT", eb.KEY_START: "START", eb.KEY_SELECT: "SELECT", 0: "-"}


def nearer_border(maps: list, pos: tuple, size: tuple, connections: list) -> tuple:
    """The map in `maps` whose border is the shorter straight walk from pos on a width x height
    map, given its (direction, map) connections; a map w/ no border here ranks last, ties by id."""
    x, y = pos
    w, h = size
    edge = {rowe_map.DIR_WEST: x, rowe_map.DIR_EAST: w - 1 - x, rowe_map.DIR_NORTH: y, rowe_map.DIR_SOUTH: h - 1 - y}
    walk = {dest: edge[d] for d, dest in connections if d in edge}
    return min(maps, key=lambda m: (walk.get(m, w + h), m))


STATUS1_SLEEP = 0x7
STATUS1_POISON = 0x8 | 0x80
STATUS1_BURN = 0x10
STATUS1_FREEZE = 0x20
STATUS1_PARALYSIS = 0x40
# Medicine-pocket status cures, id -> the status1 bits one clears, narrowest first so a Full Heal
# is only spent when nothing specific is on hand
CURE_ITEMS = ((29, STATUS1_POISON), (33, STATUS1_PARALYSIS), (32, STATUS1_SLEEP), (30, STATUS1_BURN),
              (31, STATUS1_FREEZE), (38, 0xFF))


def best_status_item(pocket: list, status1: int):
    """(pocket slot, item id) of the cure to use on a battler carrying status1, None when it is
    clean or the bag holds nothing that clears it. The slot is the battle-bag cursor row."""
    if not status1 & 0xFF:
        return None
    rows = {iid: slot for slot, (iid, _) in enumerate(pocket)}
    for iid, bits in CURE_ITEMS:
        if status1 & bits and iid in rows:
            return rows[iid], iid
    return None


def can_attack(mon) -> bool:
    return any(pp and rowe_rom.move(mid).power >= 10 for mid, pp in zip(mon.moves, mon.pp))


def best_hp_item(pocket: list, deficit: int):
    """(pocket slot, item id, heal) of the HP item to use on a mon missing `deficit` HP: the
    smallest heal that covers the deficit so the strong restoratives are saved, else the largest
    on hand when none covers it. None when the Medicine pocket holds no HP item. The slot is the
    item's row in the packed pocket, which is its battle-bag cursor position."""
    usable = [(i, iid, HP_ITEMS[iid]) for i, (iid, qty) in enumerate(pocket) if iid in HP_ITEMS and qty > 0]
    if not usable:
        return None
    covering = [u for u in usable if u[2] >= deficit]
    return min(covering, key=lambda u: u[2]) if covering else max(usable, key=lambda u: u[2])


# ROWE grants overworld traversal as badge-reward key items, not party HM moves. The Surfboard and
# Dive Gear are both start items, so SURF and DIVE are on at zero badges with no mon knowing the move;
# each listed badge count adds a tool (the Axe cuts trees, the Waterfall Tool climbs falls, the
# Pickaxe smashes rock, the Rock Climb Tool scales walls). The set grows as badges accrue, so a
# map_graph gate blocked under a smaller set reopens for a re-cross once the unlocking tool lands.
FIELD_TOOL_BADGE = ((1, "CUT"), (2, "WATERFALL"), (4, "ROCKSMASH"), (7, "ROCKCLIMB"))


def field_tools(badges: int) -> frozenset:
    return frozenset({"SURF", "DIVE"} | {move for need, move in FIELD_TOOL_BADGE if badges >= need})


# the type each Hoenn gym leader attacks and defends with, indexed by badge-flag order: Roxanne
# Rock, Brawly Fighting, Wattson Electric, Flannery Fire, Norman Normal, Winona Flying, Tate & Liza
# Psychic, Wallace Water. Team scoring reads the next unbeaten gym's entry.
GYM_LEADER_TYPES = [5, 1, 13, 10, 0, 2, 14, 11]

TYPE_MYSTERY = 9  # the ??? slot in the chart, nothing attacks or defends with it
CORE_MARGIN_FLOOR = 5   # a core swap needs the larger of this and a CORE_MARGIN_SHARE-th of the core score
CORE_MARGIN_SHARE = 10
FLEX_MARGIN = 2         # points a boxed mon must out-score the current flex mon by before the flex slot moves
FLEX_GRIND_DIV = 4      # levels under the cap a flex candidate trades for one point of counter score
VALUE_DIV = 20          # stat points per score point; a L40 mon's offence + Spe + mean bulk runs ~260, so 13
CORE_SWAP_VISITS = 4    # heal visits between core swaps, and the visits a mon swapped into the core stays put
BARRED_VISITS = 8       # heal visits a swapped-out mon stays out of the candidate pool
LEVEL_CUTOFF = 10       # a candidate this far under the grind map's top wild level is cut before scoring


class SwapLedger:
    """states/swaps.json: heal visits counted, the visit of the last core swap, and per-mon lock and bar
    windows keyed by personality, so the hysteresis survives a relaunch. A window value is the first
    visit the mon is free again."""

    def __init__(self, path: str):
        self.path = path
        self.d = json.load(open(path)) if os.path.exists(path) else {}
        for key, empty in (("visits", 0), ("last_core_visit", None), ("locked", {}), ("barred", {}), ("flex_locked", {})):
            self.d.setdefault(key, empty)

    def visit(self) -> None:
        self.d["visits"] += 1
        self.save()

    def core_open(self) -> bool:
        last = self.d["last_core_visit"]
        return last is None or self.d["visits"] - last >= CORE_SWAP_VISITS

    def locked(self, personality: int) -> bool:
        return self.d["locked"].get(str(personality), 0) > self.d["visits"]

    def barred(self, personality: int) -> bool:
        return self.d["barred"].get(str(personality), 0) > self.d["visits"]

    def flex_hold(self, personality: int, badges: int) -> bool:
        """A flex swap made at `badges` badges holds until that leader is beaten, so the incoming mon
        cannot be swapped back out while the badge count still sits at the value the swap was made for."""
        return self.d["flex_locked"].get(str(personality), -1) >= badges

    def record(self, kind: str, in_personality: int, out_personality: int, badges: int | None = None) -> None:
        v = self.d["visits"]
        if kind == "core":
            self.d["last_core_visit"] = v
        self.d["locked"][str(in_personality)] = v + CORE_SWAP_VISITS
        self.d["barred"][str(out_personality)] = v + BARRED_VISITS
        if kind == "flex" and badges is not None:
            self.d["flex_locked"][str(in_personality)] = badges
        self.save()

    def save(self) -> None:
        with open(self.path, "w") as f:
            json.dump(self.d, f)


class Profile(NamedTuple):
    species: int
    types: tuple
    attack_types: frozenset
    value: int


def mon_profile(m, level: int, ivs: tuple) -> Profile:
    """A party or box mon scored at `level`, the party floor: species walked through the EVO_LEVEL
    steps at or under it, stats from the game's formula w/ its nature, EVs and the skill IVs, attack
    types from its damaging moves whose split runs off its larger offence stat. Value is that
    offence plus Spe plus the mean of HP, Def and SpD."""
    sp_id = rowe_rom.species_at_level(m.species, level)
    st = rowe_rom.stats_at(sp_id, level, m.nature, ivs, m.evs)
    credited = {rowe_rom.SPLIT_PHYSICAL} if st[rowe_rom.ATK] > st[rowe_rom.SPA] else {rowe_rom.SPLIT_SPECIAL} \
        if st[rowe_rom.SPA] > st[rowe_rom.ATK] else {rowe_rom.SPLIT_PHYSICAL, rowe_rom.SPLIT_SPECIAL}
    moves = [rowe_rom.move(mid) for mid in m.moves if mid]
    attacks = frozenset(mv.type for mv in moves if mv.power > 0 and mv.split in credited)
    value = max(st[rowe_rom.ATK], st[rowe_rom.SPA]) + st[rowe_rom.SPE] + (st[rowe_rom.HP] + st[rowe_rom.DEF] + st[rowe_rom.SPD]) // 3
    return Profile(sp_id, rowe_rom.species(sp_id).types, attacks, value)


def foe_types(build: list) -> list:
    """The type pair of each (species, level) in a leader_build."""
    return [rowe_rom.species(sp).types for sp, _ in build]


def matchup(team: list, foes: list) -> int:
    """Over one build's foes: two points per member that hits the foe super effectively w/ a credited
    attack type, two per member that resists every type the foe carries, minus two per member past
    the first that one of the foe's types hits super effectively."""
    score = 0
    for ft in foes:
        kinds = {t for t in ft if t != TYPE_MYSTERY}
        hits = sum(any(rowe_rom.effectiveness(a, ft) > 1 for a in p.attack_types) for p in team)
        resists = sum(all(rowe_rom.effectiveness(t, p.types) < 1 for t in kinds) for p in team)
        weak = sum(any(rowe_rom.effectiveness(t, p.types) > 1 for t in kinds) for p in team)
        score += 2 * (hits + resists - max(0, weak - 1))
    return score


def team_score(team: list, builds: list) -> int:
    """matchup summed over every build, plus the team's value in VALUE_DIV steps so a stronger mon
    at the same coverage wins the slot."""
    return sum(matchup(team, foes) for foes in builds) + sum(p.value for p in team) // VALUE_DIV


def wanted_types(team: list, builds: list) -> frozenset:
    """Types among the builds' foes that no attack type on the team hits super effectively, the gaps
    the catch policy fills first."""
    kinds = {t for foes in builds for ft in foes for t in ft if t != TYPE_MYSTERY}
    attacks = frozenset().union(*(p.attack_types for p in team))
    return frozenset(t for t in kinds if not any(rowe_rom.effectiveness(a, (t,)) > 1 for a in attacks))


def tm_assignments(party: list, ivs: tuple, tms: list, builds: list) -> list:
    """[(TM pocket slot, party slot, forget slot, move)] closing the team's wanted types from the bag:
    per gap type, the strongest damaging TM move of that type goes to the core member that can learn
    it, does not hold it, runs its split off its larger offence stat, and whose least valuable move
    it outranks; the highest such stat wins between members. One TM per member per visit, since the
    forget slot is read off the moves it holds now; a taught move drops every gap it hits."""
    floor = min(m.level for m in party)
    team = [mon_profile(m, floor, ivs) for m in party]
    flex = flex_slot(team, builds)
    gaps = set(wanted_types(team, builds))
    offence = {}
    for i, m in enumerate(party):
        st = rowe_rom.stats_at(m.species, m.level, m.nature, ivs, m.evs)
        offence[i] = {rowe_rom.SPLIT_PHYSICAL: st[rowe_rom.ATK], rowe_rom.SPLIT_SPECIAL: st[rowe_rom.SPA]}
    pocket = [(slot, item, rowe_rom.move(rowe_rom.tm_move(item))) for slot, (item, _) in enumerate(tms)]
    out, taken = [], set()
    while gaps:
        t = min(gaps)
        gaps.discard(t)
        ranked = sorted((p for p in pocket if p[2].power > 0 and p[2].split != rowe_rom.SPLIT_STATUS
                         and rowe_rom.effectiveness(p[2].type, (t,)) > 1),
                        key=lambda p: (-p[2].power * (p[2].accuracy or 100), p[0]))
        for slot, item, mv in ranked:
            best = None
            for i, m in enumerate(party):
                if i == flex or i in taken or mv.id in m.moves or item not in rowe_rom.tm_learnset(m.species):
                    continue
                st = offence[i]
                if st[mv.split] < st[1 - mv.split]:
                    continue
                forget = replacement_slot(m, mv.id)
                if forget is not None and (best is None or st[mv.split] > best[0]):
                    best = (st[mv.split], i, forget)
            if best is not None:
                _, i, forget = best
                out.append((slot, i, forget, mv.id))
                taken.add(i)
                gaps = {g for g in gaps if rowe_rom.effectiveness(mv.type, (g,)) <= 1}
                break
    return out


def egg_assignments(party: list, ivs: tuple, bp: int, builds: list, declined: frozenset = frozenset()) -> list:
    """[(party slot, forget slot, move)] closing the team's wanted types at the blue nurse, TEACH_EGG_BP
    of `bp` each: per gap type, the core member whose egg list holds a damaging move that hits it, runs
    its split off the larger offence stat, and outranks its least valuable move; the higher offence stat
    wins, then the stronger move. `declined` is (species, move) pairs the nurse's list has not offered,
    skipped since the ROM egg table is wider than her list. One move per member per visit."""
    floor = min(m.level for m in party)
    team = [mon_profile(m, floor, ivs) for m in party]
    flex = flex_slot(team, builds)
    gaps = set(wanted_types(team, builds))
    out, taken = [], set()
    while gaps and bp >= S.TEACH_EGG_BP:
        t = min(gaps)
        gaps.discard(t)
        best = None
        for i, m in enumerate(party):
            if i == flex or i in taken:
                continue
            st = rowe_rom.stats_at(m.species, m.level, m.nature, ivs, m.evs)
            offence = {rowe_rom.SPLIT_PHYSICAL: st[rowe_rom.ATK], rowe_rom.SPLIT_SPECIAL: st[rowe_rom.SPA]}
            listed = [mid for mid in rowe_rom.egg_moves(m.species) if mid not in m.moves and (m.species, mid) not in declined]
            for mid in listed:
                mv = rowe_rom.move(mid)
                if mv.power <= 0 or mv.split == rowe_rom.SPLIT_STATUS or rowe_rom.effectiveness(mv.type, (t,)) <= 1:
                    continue
                if offence[mv.split] < offence[1 - mv.split]:
                    continue
                forget = replacement_slot(m, mid)
                key = (offence[mv.split], mv.power * (mv.accuracy or 100))
                if forget is not None and (best is None or key > best[0]):
                    best = (key, i, forget, mid)
        if best is not None:
            _, i, forget, mid = best
            out.append((i, forget, mid))
            taken.add(i)
            bp -= S.TEACH_EGG_BP
            gaps = {g for g in gaps if rowe_rom.effectiveness(rowe_rom.move(mid).type, (g,)) <= 1}
    return out


def flex_slot(team: list, builds: list) -> int:
    """The party slot whose removal costs the score against `builds` least; the other five are the core."""
    base = team_score(team, builds)
    return min(range(len(team)), key=lambda i: (base - team_score(team[:i] + team[i + 1:], builds), i))


def core_margin(team: list, builds: list) -> int:
    return max(CORE_MARGIN_FLOOR, team_score(team, builds) // CORE_MARGIN_SHARE)


def best_swap(team: list, box: list, builds: list, slots, margin: int, levels: tuple | None = None):
    """(party slot out, box slot in, gain) for the one trade over `slots` that raises team_score
    against `builds` the most, or None when the best gain is under `margin`. box is
    [(box slot, Profile)]. An equal trade never fires, the hysteresis against cycling two sound mons.
    `levels` is (party levels by slot, {box slot: level}); w/ it a box mon more than LEVEL_CUTOFF
    under the party mon it would replace is skipped, and one under it by less pays a point of gain per
    level, since profiles score at the party floor and a L28 Marill otherwise outscored a L47 Vileplume
    on coverage alone, then a L27 Trapinch took a L37 Camerupt's slot for +9 and reset the grind."""
    base = team_score(team, builds)
    best = None
    for out in slots:
        for slot, prof in box:
            if levels is not None and levels[1][slot] < levels[0][out] - LEVEL_CUTOFF:
                continue
            trial = list(team)
            trial[out] = prof
            gain = team_score(trial, builds) - base
            if levels is not None:
                gain -= max(0, levels[0][out] - levels[1][slot])
            if best is None or gain > best[2]:
                best = (out, slot, gain)
    return best if best and best[2] >= margin else None


def score_flex(prof: Profile, level: int, cap: int, nxt: list) -> int:
    """A flex candidate's value against the next leader's build `nxt`: its coverage scored at the grind
    cap (prof is built there, so a mon that evolves before the gym is judged as the form that fights),
    minus one point per FLEX_GRIND_DIV levels it sits under the cap now. A mistyped lead loses on
    coverage at any level; between two same-type counters the one closer to the cap wins on grind cost."""
    return matchup([prof], nxt) - max(0, cap - level) // FLEX_GRIND_DIV


def best_flex(flex_mon, level: int, box: list, nxt: list, flex: int, cap: int, ivs: tuple):
    """(flex slot out, box slot in, score gain) for the box mon that most out-scores the current flex
    mon as a counter to `nxt` once both are at the cap, or None when the best gain is under FLEX_MARGIN.
    box is [(box slot, mon, level)]. Both sides score through score_flex at the cap, so the comparison
    is which mon the grind would make the better counter, not which is stronger at today's level."""
    held = score_flex(mon_profile(flex_mon, cap, ivs), level, cap, nxt)
    best = None
    for slot, bm, bl in box:
        gain = score_flex(mon_profile(bm, cap, ivs), bl, cap, nxt) - held
        if best is None or gain > best[2]:
            best = (flex, slot, gain)
    return best if best and best[2] >= FLEX_MARGIN else None


STATUS_WORDS = ((0x7, "SLP"), (0x88, "PSN"), (0x10, "BRN"), (0x20, "FRZ"), (0x40, "PAR"))  # status1 bits: sleep turns, poison or toxic, burn, freeze, paralysis


def status_word(bits: int) -> str:
    """The summary screen's condition tag off the party struct's status word, empty when healthy."""
    return next((word for mask, word in STATUS_WORDS if bits & mask), "")


NATURE_STATS = ("Atk", "Def", "Speed", "Sp. Atk", "Sp. Def")  # the order nature_modifier indexes, stat id minus one


def nature_effect(nature: int) -> dict | None:
    """{"up": stat, "down": stat} for the 10% the nature moves, None for the five neutral natures."""
    up, down = nature // 5, nature % 5
    return None if up == down else {"up": NATURE_STATS[up], "down": NATURE_STATS[down]}


def party_row(m) -> dict:
    """One status.json party row, what the live page's row and its summary sheet read, every ROM id
    resolved to its name here so the page carries no tables."""
    lo, hi = rowe_rom.exp_bounds(m.species, m.level)
    sp = rowe_rom.species(m.species)
    ability = sp.abilities[m.ability_num]
    return {
        "slot": m.slot, "personality": m.personality, "species": m.species, "name": m.nickname, "level": m.level,
        "shiny": m.shiny, "hp": m.hp, "max_hp": m.max_hp, "exp": m.experience, "exp_lo": lo, "exp_hi": hi,
        "types": [rowe_rom.TYPE_NAMES[t] for t in dict.fromkeys(sp.types)],
        "nature": rowe_rom.NATURE_NAMES[m.nature], "nature_effect": nature_effect(m.nature),
        "ability": rowe_rom.ability_name(ability), "ability_desc": rowe_rom.ability_description(ability),
        "stats": {"atk": m.atk, "def": m.dfn, "spa": m.sp_atk, "spd": m.sp_def, "spe": m.spd},
        "status": status_word(m.status), "friendship": m.friendship,
        "moves": [{"name": mv.name, "type": rowe_rom.TYPE_NAMES[mv.type], "power": mv.power, "accuracy": mv.accuracy,
                   "pp": pp, "pp_max": mv.pp}
                  for mid, pp in zip(m.moves, m.pp) if mid for mv in [rowe_rom.move(mid)]],
    }


def party_short(party_len: int, box_len: int) -> bool:
    """A party under PARTY_SIZE while the PC holds a mon: six caught means six carried, so the next
    Center visit withdraws until the party is full."""
    return party_len < PARTY_SIZE and box_len > 0


def best_fill(team: list, box: list, builds: list):
    """Box slot whose mon added to `team` scores highest against `builds`, None on an empty pool. A
    fill has no margin, since an empty slot loses to any mon."""
    best = None
    for slot, prof in box:
        score = team_score(team + [prof], builds)
        if best is None or score > best[1]:
            best = (slot, score)
    return best[0] if best else None


def write_json(path: str, obj) -> None:
    """Atomic json write: a crash mid-write leaves the previous file instead of a truncated one
    that json.load trips on, which would then fail every relaunch."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def keep_snapshot(exit_reason: str, party_len: int, box_len: int) -> bool:
    """Whether the exit leaves the state file alone. A signal lands wherever the loop was, the storage
    PC between a deposit and its withdraw included, so only the loop's own responsive snapshots stand;
    a short party is never written, since the next run would carry it out of the Center."""
    return exit_reason == "signal" or party_short(party_len, box_len)


class GoalExit(Exception):
    """Raised with the reason the executor stops and hands the next decision to the planner."""


DEFAULT_GOAL = {"mode": "grind", "map": [0, 16], "cap": 16}

HOLD_REPLAN_BATTLES = 25  # wild battles a capless hold-grind runs before it re-attempts the
# gated frontier, the in-process echo of run-grind.sh's per-launch re-plan


def hold_stale(held: tuple, graph: "map_graph.MapGraph", moves, battles: int) -> bool:
    """A capless hold-grind entered at `held` = (visited count, adj count, field-move set, battle
    count) should raise its goal exit so drive() re-plans once any of three grew (a map walked, a
    border learned, or a field move gained can each open the route the hold parked against) or
    HOLD_REPLAN_BATTLES wild battles passed, which re-attempts a frontier a transient block has
    since cleared. An unchanged frontier inside the battle window keeps the hold, so a re-plan
    that would decide nothing never drops the stream."""
    v, a, m, b0 = held
    return (len(graph.visited) > v or len(graph.adj) > a or frozenset(moves) != m
            or battles - b0 >= HOLD_REPLAN_BATTLES)


def read_goal(path: str) -> dict:
    if not os.path.exists(path):
        return dict(DEFAULT_GOAL)
    with open(path) as f:
        return json.load(f)


class Player:
    def __init__(self, emu: eb.Emu, streamer: FrameStreamer, ledger_path: str = "/tmp/rowe-caught.json"):
        self.e = emu
        self.s = streamer
        self.g = GameState(emu)
        self.nav = Navigator(emu, self.run)
        self.errands = Errands(emu, self.run, log=lambda s: print(s, flush=True))
        self._gym_done = {}  # gym map id -> object tiles talked to and doors taken this run
        self._route_resets = {}  # gym map id -> door re-entries spent re-syncing its recorded route
        self._replans = []   # monotonic times of in-process goal changes, for the burst guard
        self._skills_spent = False
        self._gyms = rowe_rom.gym_maps()
        self.ledger = catch.Ledger(ledger_path, (m.species for m in self.g.party()))
        self.wanted = frozenset()
        self.refresh_wanted()
        self.need_heal = False
        self.shopping = []  # (item id, qty) for the next counter, from shopping_list after each battle
        self.mart_trek = False  # the list alone justifies walking to town, else it waits for a heal run
        self.rng = random.Random()
        self.battles = 0
        self.wins = 0
        self.caught = 0
        self.stop = False
        self.last_sig = None
        self.target = None
        self.swap_failures = 0
        self._act_sig = None
        self._act_stuck = 0
        self._wedge_sig = None
        self._wedge = 0
        self.stalled = False
        self._blocked_streak: dict = {}
        self.keep_state = False  # exit w/o rewriting the state file, so the next run resumes the last snapshot
        self.end_taps = 0
        self.state_path = ""
        self._live_writer = False  # only the live run (main) may write the live save and its ring
        self.goal = dict(DEFAULT_GOAL)
        self.events = collections.deque(maxlen=20)
        self.event_seq = 0  # lines ever said; the live page prepends the delta since its last row
        self._party_full = None  # personalities last written to party_full.json
        self.exit_reason = ""
        self.grass_waits = 0  # consecutive grind ticks w/ no reachable grass
        self.grass_idle_since = None  # monotonic time the no-grass-anywhere idle began, for the cap
        self.last_snapshot = time.monotonic()
        self.last_status = time.monotonic()
        self._status_sig: tuple | None = None  # party fields status.json last carried
        self.graph: map_graph.MapGraph | None = None
        self._last_obs: tuple | None = None
        self._blocked: dict = {}
        self._stuck: dict = {}
        self._stuck_hits: dict = {}  # "here>hop|moves" -> failed crossings, persisted across runs
        self._stuck_hits_path: str | None = None
        self._item_skip: set = set()  # (map, x, y) of item balls a pickup could not complete this run
        self._last_hop: tuple | None = None
        self._returned = False  # the last crossing was the walk's own return over _last_hop
        self._bounces: dict = {}  # (region, hop) -> round trips the walk made through it
        self._idle = 0  # consecutive explore ticks with no hop; a passing NPC clears, a trapped pocket does not
        self._held: tuple | None = None  # (visited, adj, moves, battles) a capless hold-grind started at
        self._dived: set = set()  # regions whose off-cluster dive was already tried, so it fires once
        self._visit_log: collections.deque = collections.deque(maxlen=CYCLE_WINDOW)  # (map, maps-seen) per landing
        self._prompt_taps = 0
        self.switch_to: int | None = None  # personality the next party menu sends out
        self._switch_active: int | None = None  # personality the voluntary-switch fail count tracks
        self._switch_fails = 0
        self._wild_switched = False  # a wild fight gets one voluntary switch: the low lead out, the finisher in
        self._start_items: dict = {}  # personality -> held item at that mon's first action, for the Belch precondition; keyed by mon not slot so a switch-in doesn't inherit the slot's prior baseline
        self._avoid_slots: set = set()  # move slots a freeze bailed on this battle, skipped by pick_move
        self._freezes = 0  # unstick firings this battle: the first swaps the slot, the second runs from a wild foe
        self._last_pick = 0  # slot pick_move last returned, the one a freeze blames

    def run(self, frames: int, keys: int = 0) -> None:
        if self.stop:
            raise StopRequested
        core = self.e.core
        core._core.setKeys(core._core, keys)
        for _ in range(frames):
            core.run_frame()
            self.s.push(self.e.screen)
        core._core.setKeys(core._core, 0)

    def tap(self, keys: int, hold: int = TAP_HOLD, gap: int = TAP_GAP) -> None:
        if self.g.in_battle():
            print(self._battle_press_log(keys), flush=True)
        self.run(hold, keys)
        self.run(gap)

    def _battle_press_log(self, keys: int) -> str:
        """One line naming a battle press and the state read before it, so a wrong press is
        findable in grind.log. Prints the key, the main callback, and for the player chooser b its
        controller func, gBattleCommunication[b], and the cursor slot on the open screen with the
        hp or pp under it."""
        g = self.g
        cb2 = g.callback2()
        b = g.chooser()
        func = g.controller_func(b)
        comm = self.e.read(S.addr("gBattleCommunication") + b, 1)[0]
        head = f"  press {KEY_NAMES.get(keys, hex(keys))} cb2 {cb2:#x} func {func:#x} comm[{b}] {comm}"
        if cb2 in S.CB2_PARTY_MENU:
            slot = g.party_menu_slot()
            party = g.party()
            if slot < len(party):
                m = party[slot]
                return f"{head} party slot {slot} {m.nickname} hp {m.hp}/{m.max_hp}"
            return f"{head} party slot {slot}"
        if g.in_move_list(b):
            slot = g.move_cursor(b)
            mons = g.battlers()
            if b < len(mons) and slot < len(mons[b].pp):
                return f"{head} move slot {slot} pp {mons[b].pp[slot]}"
            return f"{head} move slot {slot}"
        return f"{head} action cursor {g.action_cursor(b)}"

    def wait_until(self, pred, max_frames: int, poll: int = MENU_POLL_FRAMES) -> bool:
        """Run frames until pred() holds or max_frames pass; returns pred(). Replaces a fixed
        run(N) after a press, so the next input fires the frame the menu is ready, not N later."""
        for _ in range(0, max_frames, poll):
            if pred():
                return True
            self.run(poll)
        return pred()

    def press_until(self, key: int, pred, timeout: int = 30, tries: int = 3) -> bool:
        """Tap key until pred() holds, re-pressing only when the readback shows the press was eaten."""
        for _ in range(tries):
            if pred():
                return True
            self.tap(key)
            if self.wait_until(pred, timeout):
                return True
        return False

    def _comm_action(self, b: int) -> str:
        """The no-PP selection-box dispatch, single-sourced so no battle wait loop presses its own key
        into the box. While b's controller is in the action or move choose phase, read
        gBattleCommunication[b]: at the selection-script box (comm 6) tap B, the only key that leaves
        it, and return "box"; at a move list bounced under the idle controller (comm 3) return
        "move_list" so the caller steers to a PP'd slot instead of confirming the parked 0-PP one. comm
        is read only under a choose or intro-idle controller func, where it is the live sub-state; the
        bag and party-menu callbacks leave it holding a stale value a blind read would act on."""
        cf = self.g.controller_func(b)
        if cf not in S.PLAYER_CHOOSE_ACTION_FUNCS and cf not in INTRO_IDLE_FUNCS:
            return ""
        c = self.g.comm(b)
        if c == S.SELECTION_SCRIPT_COMM_STATE:
            self.tap(eb.KEY_B)
            return "box"
        if c == S.MOVE_LIST_COMM_STATE:
            return "move_list"
        return ""

    def comm_wait(self, b: int, pred, timeout: int = 30, tries: int = 4,
                  poll: int = MENU_POLL_FRAMES, key: int = 0) -> str:
        """press_until with the no-PP box dispatch folded in: the one waiter every battle choose-phase
        loop runs, so a selection-script box that toggles up mid-wait is left with B rather than mashed
        back open by the loop's own key. Per try, return "gone" if the battle ended, "ready" once pred
        holds, "move_list" if the list bounced under the idle controller (comm 3) for the caller to
        steer and confirm. At the box (comm 6) _comm_action taps B, so that try skips `key`; otherwise
        tap `key` once when given, then wait up to `timeout` frames, re-reading the box each poll.
        Returns "ready"/"move_list"/"gone", or "" after `tries` presses without pred."""
        for _ in range(tries):
            if not self.g.in_battle():
                return "gone"
            if pred():
                return "ready"
            act = self._comm_action(b)
            if act == "move_list":
                return "move_list"
            if act == "" and key:
                self.tap(key)
            for _ in range(0, timeout, poll):
                self.run(poll)
                if not self.g.in_battle():
                    return "gone"
                if pred():
                    return "ready"
                inner = self._comm_action(b)
                if inner == "move_list":
                    return "move_list"
                if inner == "box":
                    break
        if not self.g.in_battle():
            return "gone"
        return "ready" if pred() else ""

    def _reach_fight(self, b: int) -> bool:
        """Steer the action cursor to Fight (slot 0). Returns True once it lands on Fight or the
        battle ends, False if a held prompt kept it off Fight after every retry. Each retry taps
        B before the UP+LEFT to dismiss a held text box or open submenu (Bag/Pokemon) that parks
        the cursor off Fight and eats the nav; B on the bare grid is a no-op. This is the recovery
        the 0x83aa958 attack-turn wedge needed past the old 3x UP+LEFT that never pressed B."""
        for _ in range(ACT_NAV_RETRIES):
            if self.g.action_cursor(b) == 0 or not self.g.in_battle():
                return True
            self.tap(eb.KEY_B)
            self.tap(eb.KEY_UP)
            self.tap(eb.KEY_LEFT)
        return False

    def sides(self) -> tuple:
        """(chooser battler, its mon, live foes) for the player's mon currently picking an action."""
        mons = self.g.battlers()
        b = self.g.chooser()
        if len(mons) <= b:
            return b, None, []
        foes = [m for m in mons[1::2] if m.hp > 0]
        return b, mons[b], foes

    def pick_move(self, me, foes) -> int:
        self._start_items.setdefault(me.personality, me.item)
        disabled = self.g.disabled_move(me.battler)
        ranked = [s for foe in foes for s in rank_moves(me, foe)
                  if me.moves[s.slot] != disabled and s.slot not in self._avoid_slots
                  and self._selectable(me, s.move)]
        if ranked:
            top = max(ranked, key=lambda s: s.score)
            print(f"  {me.nickname}: {top.move.name} x{top.effectiveness:g} est {top.damage:.0f} vs {[f'{f.nickname} {f.hp}/{f.max_hp}' for f in foes]}", flush=True)
            self._last_pick = top.slot
            return top.slot
        # scoring left nothing selectable: take the most-PP move still allowed (Belch barred until
        # its berry is gone, a freeze-barred slot skipped), else whatever has PP so the engine moves
        usable = [i for i, (m, pp) in enumerate(zip(me.moves, me.pp))
                  if m and pp and i not in self._avoid_slots and self._selectable(me, rowe_rom.move(m))]
        self._last_pick = max(usable, key=lambda i: me.pp[i]) if usable else first_usable_slot(me.moves, me.pp)
        return self._last_pick

    def _selectable(self, me, move) -> bool:
        """Belch cannot be chosen until the user's held item is gone this battle, the engine's
        eaten-berry precondition approximated as a nonzero item at the first action now at zero. A
        consumed gem or herb trips the same approximation, and the unstick slot-swap is the net for
        that false positive. Every other move is selectable here."""
        if move.name.lower() != "belch":
            return True
        return self._start_items.get(me.personality, me.item) != 0 and me.item == 0

    def catch_plan(self, me, foes) -> tuple:
        """("throw", None) | ("move", slot) | None when no ball goes out this turn.

        A ball only flies at a lone foe, so a double battle KOs one side first; a trainer
        blocks the ball and the game still consumes it."""
        flags = self.g.battle_type_flags()
        if flags & BATTLE_TYPE_TRAINER or flags & BATTLE_TYPE_DOUBLE:
            # A wild double keeps two foe slots the whole battle, so the softener-switch and throw
            # flow, which drives the single-foe menu, loops the party screen for a non-lead battler.
            # Fight both mons down instead; the catch waits for a single encounter.
            return None
        balls = dict(self.g.poke_balls()).get(catch.POKE_BALL, 0)
        if len(foes) != 1 or not self.ledger.wants(foes[0], self.wanted, balls) or not self.g.poke_balls():
            return None
        foe = foes[0]
        chance = catch.catch_chance(foe)
        if chance >= THROW_AT:
            print(f"  throw: {foe.nickname} {foe.hp}/{foe.max_hp} status {foe.status1:#x} chance {chance:.0%}", flush=True)
            return "throw", None
        slot = catch.status_move_slot(me, foe)
        if slot is not None:
            print(f"  soften: {rowe_rom.move(me.moves[slot]).name} on {foe.nickname} (chance {chance:.0%})", flush=True)
            return "move", slot
        weak = weakening_move(me, foe)
        if weak is not None:
            print(f"  chip: {weak.move.name} est {weak.damage:.0f} vs {foe.hp} (chance {chance:.0%})", flush=True)
            return "move", weak.slot
        # the fight's one switch already went to the finisher, so no helper comes in behind it;
        # a second switch only splits the exp and hands the foe another free hit
        helper = None if self._wild_switched else catch.helper_slot(self.g.party(), me, foe)
        if helper is not None:
            print(f"  catch: {me.nickname} out, slot {helper} in to soften {foe.nickname} (chance {chance:.0%})", flush=True)
            return "switch", helper
        if chance >= THROW_FLOOR:
            print(f"  throw anyway: no safe chip, chance {chance:.0%}", flush=True)
            return "throw", None
        print(f"  no catch: chance {chance:.0%} under {THROW_FLOOR:.0%} w/ no softener on the bench", flush=True)
        return None

    def throw_ball(self) -> None:
        """From the action menu on Fight: Bag, Poké Balls tab, first slot, confirm, then sit through the result."""
        self.tap(eb.KEY_RIGHT)
        self.tap(eb.KEY_A)
        self.run(150)
        if self.g.callback2() != S.CB2_BAG_MAIN:
            # the presses landed on some other grid (the move list keeps the chooser flag set
            # after a dropped A), so a second A here would fire whatever the cursor sits on.
            # gBagPosition holds its last value with the bag closed, so no cursor read is safe.
            # cb2 CB2_BATTLE_MAIN (0x803c761) means the RIGHT+A never left the battle screen. Dump
            # the state and screen like the switch-stall path, so the next occurrence is a fixture
            # the polled rewrite fails-first on.
            cb2 = self.g.callback2()
            path = f"/tmp/rowe_throw_nobag_{int(time.time())}"
            with open(path + ".ss", "wb") as f:
                f.write(self.e.save_state())
            self.e.save_png(path + ".png")
            print(f"  throw: bag never opened (cb2 {cb2:#x}), backing out, state {path}.ss", flush=True)
            self.tap(eb.KEY_B)
            return
        for _ in range(6):
            if self.g.bag_position()[0] == S.BAG_POCKET_POKE_BALLS:
                break
            self.tap(eb.KEY_RIGHT)
            self.run(30)
        for _ in range(8):
            if self.g.bag_position()[1] == 0:
                break
            self.tap(eb.KEY_UP)
        self.tap(eb.KEY_A)
        self.run(40)
        self.tap(eb.KEY_A)
        # throw animation, shakes and the caught/nickname/dex prompts; B declines each prompt
        # and is a no-op once the action menu is back
        for _ in range(10):
            self.run(60)
            if not self.g.in_battle():
                return
            self.tap(eb.KEY_B)

    def use_hp_item_in_battle(self, pocket_slot: int, target_slot: int) -> None:
        """From the action menu on Fight: open the Bag, the Medicine tab, the item at pocket_slot,
        use it on the party mon at target_slot, then sit through the recovery text back to the
        action menu. A medicine in the battle bag goes straight to the party menu to pick a mon,
        no Use/Toss submenu in the way."""
        self.tap(eb.KEY_RIGHT)
        self.tap(eb.KEY_A)
        self.run(150)
        if self.g.callback2() != S.CB2_BAG_MAIN:
            # same no-bag-open hazard as throw_ball: an eaten RIGHT leaves the chooser flag set and
            # bag_position holds its last value with the bag closed, so the pocket walk below would
            # tap into the Fight list. Dump state + png like the switch-stall path so the next
            # occurrence is a fixture, then B out.
            cb2 = self.g.callback2()
            path = f"/tmp/rowe_item_nobag_{int(time.time())}"
            with open(path + ".ss", "wb") as f:
                f.write(self.e.save_state())
            self.e.save_png(path + ".png")
            print(f"  item: bag never opened (cb2 {cb2:#x}), backing out, state {path}.ss", flush=True)
            self.tap(eb.KEY_B)
            return
        for _ in range(6):
            pk = self.g.bag_position()[0]
            if pk == S.BAG_POCKET_MEDICINE:
                break
            self.tap(eb.KEY_RIGHT if pk < S.BAG_POCKET_MEDICINE else eb.KEY_LEFT)
            self.run(30)
        for _ in range(pocket_slot + 8):
            cur = self.g.bag_position()[1]
            if cur == pocket_slot:
                break
            self.tap(eb.KEY_DOWN if cur < pocket_slot else eb.KEY_UP)
        # selecting a medicine raises a Use/Cancel box on Use; the second A takes Use and opens
        # the party menu to pick the mon
        self.tap(eb.KEY_A)
        self.run(40)
        self.tap(eb.KEY_A)
        self.run(60)
        for _ in range(8):
            if self.g.party_menu_slot() == target_slot:
                break
            self.tap(eb.KEY_DOWN if self.g.party_menu_slot() < target_slot else eb.KEY_UP)
            self.run(10)
        # the first A on "Use on which Pokémon?" is eaten while the party menu is still settling,
        # so press until the pocket count drops: the item is spent the frame the selection lands
        before = sum(q for _, q in self.g.medicine())
        for _ in range(5):
            self.tap(eb.KEY_A)
            self.run(60)
            if not self.g.in_battle() or sum(q for _, q in self.g.medicine()) < before:
                break
        # recovery animation, the "HP restored" line, then the foe's turn; B advances text and
        # is a no-op back at the action menu
        for _ in range(12):
            self.run(60)
            if not self.g.in_battle():
                return
            self.tap(eb.KEY_B)

    def steer_move_cursor(self, battler: int, target: int) -> None:
        """Land the move cursor on `target` in the Fight list. The caller only gets here once
        in_move_list(b) holds, so the list is open and a steer tap cannot move Fight->Pokemon on a
        still-live grid; each hop reads the cursor back so a tap the list eats while it draws is
        retried instead of waited out."""
        for _ in range(MOVE_STEER_RETRIES):
            cur = self.g.move_cursor(battler)
            if cur == target:
                return
            cx, cy = MOVE_GRID[cur & 3]
            tx, ty = MOVE_GRID[target]
            if tx != cx:
                key = eb.KEY_RIGHT if tx > cx else eb.KEY_LEFT
            else:
                key = eb.KEY_DOWN if ty > cy else eb.KEY_UP
            # a tap eaten while the list draws leaves the cursor put; the readback retries it
            self.tap(key)
            self.wait_until(lambda: self.g.move_cursor(battler) != cur, 12)

    def _battle_pulse(self) -> tuple:
        """State that moves whenever the engine advances a text box or hands off control: the four
        controller funcs and the battle-script instruction pointer. The intro-advance loop fires the
        next A as soon as this moves, so damage and effect text clears at reading speed instead of
        waiting out the full per-press timeout. The controller-func half still breaks on a handoff,
        keeping the one-press-per-step pacing the intro needs to not over-mash a wild double."""
        return (tuple(self.g.controller_func(i) for i in range(4)),
                self.e.u32(S.addr("gBattlescriptCurrInstr")))

    def battle_step(self) -> None:
        # An A can land in the Bag or Pokémon submenu instead of opening Fight;
        # that submenu holds our turn open with the foe hidden, so the party-shift
        # prompt reads as zero foes and the action branches loop on it. When the
        # battle state has not moved for several steps, B backs out of the submenu
        # a press at a time, and is a no-op at the top menu of a wild battle.
        cb2 = self.g.callback2()
        if cb2 == CB2_EVOLUTION:
            # the scene holds the battle signature frozen for its whole run and cancels on
            # B, so it is handled before the unstick counter can fire a B into it
            self._act_stuck = self._wedge = 0
            self.tap(eb.KEY_A)
            self.run(30)
            return
        if cb2 == CB2_NAMING:
            # a Yes that reached "Give a nickname?" opened the keyboard, where B only deletes
            # a letter; START parks the cursor on OK, A presses it, the empty name keeps the
            # species name
            self._act_stuck = self._wedge = 0
            self.tap(eb.KEY_START)
            self.run(20)
            self.tap(eb.KEY_A)
            self.run(60)
            return
        instr = self.g.script_instr()
        if ASK_TO_LEARN <= instr <= STOP_LEARN_PROMPT:
            self._act_stuck = self._wedge = 0
            self.learn_step(instr, cb2)
            return
        if cb2 in CB2_PARTY_MENU:
            self._act_stuck = self._wedge = 0
            self.party_menu_step()
            return
        sig = self.battle_signature()
        self._act_stuck = self._act_stuck + 1 if sig == self._act_sig else 0
        self._act_sig = sig
        # a battle whose controller func, script instr, cb2 and HP/PP all hold across steps is
        # wedged under the input, not slow: no button moves it (600 frames of A/B on the Spinda
        # switch-in dump left all four fixed), so bail for a relaunch instead of the full STALL wait
        wedge_sig = (sig[0], sig[1], self.e.u32(S.BATTLER0_CONTROLLER_FUNC),
                     self.e.u32(S.addr("gBattlescriptCurrInstr")), cb2)
        self._wedge = self._wedge + 1 if wedge_sig == self._wedge_sig else 0
        self._wedge_sig = wedge_sig
        if self._wedge >= WEDGE_STEPS:
            self._stall_dump(f"WEDGE: battle frozen {self._wedge} steps, ctrl {wedge_sig[2]:#x} exec {sig[0]:#x}")
        if self._act_stuck >= 4:
            self._freezes += 1
            _, me_f, _ = self.sides()
            wild = not self.g.battle_type_flags() & BATTLE_TYPE_TRAINER
            if self._freezes >= 2 and wild and me_f is not None and me_f.battler == 0:
                # the slot swap did not clear it and the foe is wild: leave rather than freeze the
                # turn again on a move the engine keeps refusing. Run sits down-right of Fight
                print(f"  unstick: second freeze after {self._act_stuck} steps vs wild, running", flush=True)
                self.tap(eb.KEY_DOWN)
                self.tap(eb.KEY_RIGHT)
                self.tap(eb.KEY_A)
                self.run(150)
            else:
                # bar the slot the freeze is stuck on so pick_move takes the next usable move, then
                # clear whatever box is up; B on the bare grid is a no-op
                self._avoid_slots.add(self._last_pick)
                print(f"  unstick: frozen {self._act_stuck} steps, barring slot {self._last_pick}, next usable move", flush=True)
                self.tap(eb.KEY_B)
                self.run(30)
            self._act_stuck = 0
        b, me, foes = self.sides()
        if b % 2 or me is None:
            # the foe's controller holds the flag through its own turn and through end-of-battle
            # text ("Got away safely!"); B advances the text and declines any yes/no
            self.tap(eb.KEY_B)
            self.run(30)
            return
        if not foes:
            # every foe down: faint and exp text take either button. The learn-move flow
            # needs B ("Delete a move?" No) then A ("Stop learning?" Yes) in that order, and
            # a mistimed A there deletes slot 1, so the two alternate.
            self.end_taps += 1
            self.tap(eb.KEY_A if self.end_taps % 2 == 0 else eb.KEY_B)
            self.run(30)
            return
        # action menu: cursor 0 is Fight; any text box in the way eats the A
        if not self._reach_fight(b):
            # a yes/no prompt holds a nonzero cursor. "Give a nickname?" dies on one B. A
            # mid-battle level-up (double battle, first foe down) raises the learn-move pair
            # "Delete a move?" / "Stop learning?", where B alone cycles the two forever, so
            # every fourth press is an A, which lands on "Stop learning?" as Yes
            self._prompt_taps += 1
            key = eb.KEY_A if self._prompt_taps % 4 == 0 else eb.KEY_B
            print(f"  prompt? battler {b} action {self.g.action_cursor(b)} move {self.g.move_cursor(b)}, {'A' if key == eb.KEY_A else 'B'}", flush=True)
            self.e.save_png("/tmp/rowe_prompt.png")
            self.tap(key)
            self.run(30)
            return
        self._prompt_taps = 0
        if not self.g.choosing(b):
            self._advance_intro(b, me, foes)
            return
        disabled = self.g.disabled_move(b)
        # Run escapes the whole encounter and only works from the lead battler; a non-lead mon in a
        # double battle has no working Run on its action grid, so steering there freezes the turn.
        # That mon fights with what it has instead (a status move still advances the turn) or switches.
        can_run = me.battler == 0
        if can_run and not any(me.moves[s.slot] != disabled and s.damage > 0 for foe in foes for s in rank_moves(me, foe)) \
                and not self.g.battle_type_flags() & BATTLE_TYPE_TRAINER:
            # Disable or empty PP left no damaging move, so flee the wild battle instead of
            # flailing with a status move; Disable resets when the next battle starts
            print(f"  flee: no usable damaging move (disabled {disabled}), running", flush=True)
            self.tap(eb.KEY_DOWN)
            self.tap(eb.KEY_RIGHT)
            self.tap(eb.KEY_A)
            self.run(150)
            return
        # a KO in hand from the faster mon ends the fight now, whatever the HP: Pawmo at 12/57
        # ran from a Lombre at 1/43 it outsped, and the exp stayed on the field
        finish = all(me.spd > f.spd and any(me.moves[s.slot] != disabled and s.damage >= f.hp for s in rank_moves(me, f)) for f in foes)
        # a status on the active mon is cured from the bag before anything else, unless the KO in
        # hand ends the fight this turn anyway
        cure = None if finish else best_status_item(self.g.medicine(), me.status1)
        if cure is not None:
            slot, iid = cure
            print(f"  cure: {rowe_rom.item_name(iid)} on {me.nickname} status {me.status1:#x}", flush=True)
            self.use_hp_item_in_battle(slot, self.g.battler_slot(b))
            return
        if self.needs_heal() and not finish:
            if not self.g.battle_type_flags() & BATTLE_TYPE_TRAINER:
                # a low lead in a wild fight hands the turn to a healthy bench mon, the one w/ the
                # best edge, so the grind goes on w/ a new lead; a bench w/ nobody healthy means the
                # party as a whole is spent, and the flee below walks to a Center instead of
                # fleeing fight after fight on the same low lead
                party = self.g.party()
                healthy = [m for m in party if m.personality != me.personality and can_attack(m)
                           and m.hp * 100 >= m.max_hp * HEAL_HP_PERCENT]
                # needs_heal reads party slot 0, so a fainted lead kept it true after the forced
                # switch and sent a full-HP Greedent back out "on low HP"; the switch is for the
                # mon on the field being low, read off its own bar
                low = me.hp * 100 < me.max_hp * HEAL_HP_PERCENT
                # _open_wild_switch drives the single-battle action grid, so a wild double is left
                # to fight; party_menu_step covers a forced replacement there
                double = bool(self.g.battle_type_flags() & BATTLE_TYPE_DOUBLE)
                if healthy and low and not double:
                    slot = max(healthy, key=lambda m: (lambda d, t: d - t)(*edge(as_battler(m), foes))).slot
                    if not self._wild_switched and self._switch_budget(me.personality):
                        print(f"  switch: {me.nickname} {me.hp}/{me.max_hp} out on low HP, slot {slot} in", flush=True)
                        self._open_wild_switch(slot)
                        return
                elif not healthy:
                    self.need_heal = True
            if me.hp * 100 < me.max_hp * POTION_HP_PERCENT and any(me.pp):
                # a potion on a lead with no PP left heals a mon that still cannot attack, so the
                # 0-PP low lead takes the switch above (or the flee below) over a wasted item
                item = best_hp_item(self.g.medicine(), me.max_hp - me.hp)
                if item is not None:
                    slot, iid, _ = item
                    print(f"  potion: {rowe_rom.item_name(iid)} on {me.nickname} {me.hp}/{me.max_hp}", flush=True)
                    self.use_hp_item_in_battle(slot, self.g.battler_slot(b))
                    return
            if self._retreat_warranted(self.g.party()):
                self.need_heal = True
            if can_run and not self.g.battle_type_flags() & BATTLE_TYPE_TRAINER:
                # Run sits at action-grid slot 3, one step down and one right of Fight.
                # A trainer refuses Run, so the press loops the menu until STALL; fight
                # through instead and the overworld rotates or heals after the flee.
                self.tap(eb.KEY_DOWN)
                self.tap(eb.KEY_RIGHT)
                self.tap(eb.KEY_A)
                self.run(150)
                return
        flags = self.g.battle_type_flags()
        # the voluntary switch drives the single-battle action grid; in a double the party menu
        # never opened (Fortree's Flint + Edwardo pair, five STALLs before the fight resumed)
        if flags & BATTLE_TYPE_TRAINER and not flags & BATTLE_TYPE_DOUBLE:
            party = self.g.party()
            slot = best_switch(party, me, foes, SWITCH_MARGIN)
            if slot is not None and self._switch_budget(me.personality):
                print(f"  switch: {me.nickname} out on matchup, slot {slot} in", flush=True)
                self.switch_to = party[slot].personality
                # after a foe faints the game asks "will you switch?" w/ Yes on cursor 0, the
                # same cursor as Fight, and Yes opens the party menu as a free switch. A first;
                # a voluntary switch opens the move list instead, so back out and take Pokémon
                self.tap(eb.KEY_A)
                self.run(40)
                if self.g.callback2() not in CB2_PARTY_MENU:
                    self.tap(eb.KEY_B)
                    self.run(20)
                    for _ in range(4):
                        if self.g.action_cursor(b) == ACTION_POKEMON:
                            break
                        self.tap(eb.KEY_DOWN)
                        self.run(10)
                    self.tap(eb.KEY_A)
                    self.run(20)
                for _ in range(5):
                    self.run(30)
                    if self.g.callback2() in CB2_PARTY_MENU:
                        return  # party_menu_step sends the bench mon out next step
                # the menu never opened, so the presses did not land Pokémon on this action grid.
                # the mon is still out, so next turn's _switch_budget spends the try and falls
                # through to Fight once the budget is gone, instead of re-deciding forever
                self.switch_to = None
                print(f"  switch stalled: party menu never opened (cb2 {self.g.callback2():#x})", flush=True)
                return
        if not flags & BATTLE_TYPE_TRAINER and not flags & BATTLE_TYPE_DOUBLE and self._exp_lead(me) and outmatched(me, foes):
            # the lowest mon leads so each wild fight pays it an exp share, and it fights the round
            # itself to earn that exp, stepping out only when a foe carries a hit worth half its bar.
            # a healthy lead swapped on a close level gap handed the foe a free turn every fight for
            # an exp split it already gets by standing on the field, the switch-for-no-reason a
            # viewer sees; the low-HP switch above still covers a fight that turns.
            pick = strongest_bench(self.g.party(), me, foes)
            if pick is not None and not self._wild_switched and self._switch_budget(me.personality):
                print(f"  switch: {me.nickname} L{me.level} led for exp, slot {pick[0]} in", flush=True)
                self._open_wild_switch(pick[0])
                return
        plan = self.catch_plan(me, foes)
        if plan is not None and plan[0] == "throw":
            self.target = foes[0]
            self.throw_ball()
            return
        if plan is not None and plan[0] == "switch":
            # the helper switch spends the same budget as the matchup and low-HP switches: a Shift
            # that never puts the helper out otherwise re-decides itself every turn (21 rounds of
            # "Stoutland out, slot 1 in" on a Torkoal before the stall exit)
            if self._switch_budget(me.personality):
                self._open_wild_switch(plan[1])
                return
            print(f"  switch budget spent on {me.nickname}, fighting instead", flush=True)
            plan = None
        # A on Fight opens the move list. The action func 0x83c12bc drives both the action grid and
        # the move list, so choosing(b) reads True on each and cannot gate the Fight-open: pressing A
        # once the list is already up confirms whatever slot the cursor is parked on before steer
        # runs, firing a wrong-but-PP'd move. in_move_list reads the gBattleCommunication[0] sub-state
        # that separates them, so press A only from the grid; when the ROM has bounced control back
        # with the list still drawn (a refused 0-PP or Last Resort slot), skip the open and steer.
        if not self.g.in_move_list(b):
            # A opens the Fight list, but a 0-PP lead pops the selection-script box here the same as
            # mid-intro; comm_wait leaves that box with B instead of mashing A back into it
            if self.comm_wait(b, lambda: self.g.in_move_list(b),
                              tries=MOVE_OPEN_RETRIES, key=eb.KEY_A) == "gone":
                return
        if not self.g.in_battle():
            return
        self.steer_move_cursor(b, plan[1] if plan is not None else self.pick_move(me, foes))
        self.confirm_move(b, me)

    def _advance_intro(self, b: int, me, foes) -> None:
        """Advance the turn while b's controller is off the action pick (an intro, a switch or foe
        animation, a text box, or the no-PP selection box). The grid is drawn but a decision read
        now re-issues the leaving mon, so no action key goes out until the engine opens the menu.
        Keying on b reads a double on its real chooser, battler 2 while battler 0 idles at 0x83aa958.
        The box dispatch runs through _comm_action each pass, since the no-PP box can toggle up
        mid-intro, not only on entry, and that dispatch is shared with every other wait loop."""
        for _ in range(INTRO_PRESSES):
            if self.g.choosing(0) or self.g.choosing(2) or not self.g.in_battle():
                return
            act = self._comm_action(b)
            if act == "box":
                # _comm_action tapped B to leave the no-PP box; an A would re-open it, the Seaking
                # loop, so re-read next pass instead of advancing
                self.run(INTRO_POLL_FRAMES)
                continue
            if act == "move_list":
                # a move list bounced to the idle controller: steer to a PP'd slot and confirm. An A
                # on the parked 0-PP slot re-confirms the move the ROM just refused
                self.steer_move_cursor(b, self.pick_move(me, foes))
                if self.confirm_move(b, me):
                    return
                continue
            before = self._battle_pulse()
            self.tap(eb.KEY_A)
            for _ in range(INTRO_STEP_FRAMES // INTRO_POLL_FRAMES):
                self.run(INTRO_POLL_FRAMES)
                if self.g.choosing(0) or self.g.choosing(2):
                    return
                if self._battle_pulse() != before:
                    break
            if self.g.controller_func(0) in INTRO_IDLE_FUNCS or self.g.controller_func(2) in INTRO_IDLE_FUNCS:
                for _ in range(INTRO_PROMOTE_FRAMES // INTRO_POLL_FRAMES):
                    self.run(INTRO_POLL_FRAMES)
                    if self.g.choosing(0) or self.g.choosing(2):
                        return

    def confirm_move(self, b: int, me) -> bool:
        """Confirm the move under b's cursor, or back out if it is spent. Returns True on a confirm.
        The only A pressed inside the Fight list: a dropped steer tap that leaves the cursor on a
        0-PP slot must never reach it, since the ROM rejects the move w/ "no PP left" and deadlocks
        the menu (the 0x83aa958 / 0x84f4c78 wedge). B backs out to the grid and the next step re-steers."""
        landed = self.g.move_cursor(b)
        if not me.pp[landed & 3]:
            self.tap(eb.KEY_B)
            self.run(20)
            return False
        self.tap(eb.KEY_A)
        self.run(30)
        if self.g.battle_type_flags() & BATTLE_TYPE_DOUBLE and self.g.chooser() == b:
            # a double battle always asks which foe to hit, even after one foe faints, so key
            # off the battle type and not the live-foe count; A locks the default target
            self.tap(eb.KEY_A)
            self.run(30)
        # no 120-frame tail: the turn plays out under the next battle_step's pulse-gated wait
        return True

    def _open_wild_switch(self, slot: int) -> None:
        """Open the party menu on bench `slot` from a wild battle's action grid: Pokémon sits
        under Fight and no faint prompt is in the way, so party_menu_step sends the mon out next
        step. A menu that never opens drops the plan, since a slot left here would be spent by
        the next party menu that opens for any other reason, after the party order has moved on."""
        self.switch_to = self.g.party()[slot].personality
        # the action grid ignores input during its opening slide-in (cb2 holds a pre-input wait
        # state), so a blind single DOWN leaves the cursor on Fight and A opens the move list,
        # not the party menu. Retry the whole open with settle frames between, which both
        # advances past the lock and re-presses DOWN until the cursor reads Pokémon; three
        # single-press misses in a row spent the switch budget and dropped Goldeen to a Run it
        # could not survive at 3 HP vs a faster Yanma.
        trail = []
        for _ in range(6):
            for _ in range(4):
                cur = self.g.action_cursor(0)
                if cur == ACTION_POKEMON:
                    break
                # grid is Fight 0 Bag 1 / Pokémon 2 Run 3: DOWN from the top row, LEFT off Run
                key = eb.KEY_DOWN if cur in (0, 1) else eb.KEY_LEFT
                self.tap(key)
                trail.append(f"{'DOWN' if key == eb.KEY_DOWN else 'LEFT'} cur {self.g.action_cursor(0)} cb2 {self.g.callback2():#x}")
            if self.g.action_cursor(0) != ACTION_POKEMON:
                # the presses never moved the cursor, so the grid is still locked; an A now lands on
                # whatever the cursor holds, Fight or Run, which is how a lead at 5 HP got left in
                # or a 95% catch fled. Settle and retry the walk, no A
                self.run(20, 0)
                continue
            self.tap(eb.KEY_A)
            trail.append(f"A cur {self.g.action_cursor(0)} cb2 {self.g.callback2():#x} func {self.e.u32(S.BATTLER0_CONTROLLER_FUNC):#x}")
            for _ in range(6):
                self.run(20)
                cb2 = self.g.callback2()
                if cb2 in CB2_PARTY_MENU:
                    self._wild_switched = True
                    return
                if cb2 != S.CB2_BATTLE_MAIN:
                    break  # another screen is loading under this A; pressing more only drives it
            trail.append(f"wait cb2 {self.g.callback2():#x} func {self.e.u32(S.BATTLER0_CONTROLLER_FUNC):#x} in_battle {self.g.in_battle()}")
            if self.g.callback2() == S.CB2_BATTLE_MAIN and self.e.u32(S.BATTLER0_CONTROLLER_FUNC) not in S.PLAYER_CHOOSE_ACTION_FUNCS:
                # the A went past the grid into the move list; B is back to the grid, and a turn
                # already running ignores it
                self.tap(eb.KEY_B)
                self.run(20, 0)
        self.switch_to = None
        # the live run is the only place this fires, so it leaves the state and screen behind
        # for a replay instead of a bare address nobody can map
        path = f"/tmp/rowe_switch_stall_{int(time.time())}"
        with open(path + ".ss", "wb") as f:
            f.write(self.e.save_state())
        self.e.save_png(path + ".png")
        print(f"  switch stalled: party menu never opened (cb2 {self.g.callback2():#x}), state {path}.ss", flush=True)
        for row in trail:
            print(f"    {row}", flush=True)

    def learn_step(self, instr: int, cb2: int) -> None:
        """Answer a level-up move prompt: take the new move over the least valuable slot, else decline."""
        new = self.g.offered_move()
        mon = self.g.party()[self.g.learning_mon()]
        slot = replacement_slot(mon, new)
        if cb2 == CB2_MOVE_SELECT:
            # the summary opens on row 0; walking to the cancel row answers "Stop learning?" next
            for _ in range(MOVE_SELECT_CANCEL_ROW if slot is None else slot):
                self.tap(eb.KEY_DOWN)
                self.run(10)
            self.tap(eb.KEY_A)
            self.run(60)
            return
        if instr == STOP_LEARN_PROMPT:
            # "Should X stop learning Y?" Yes drops the move we declined; No bounces back to the
            # "make room?" box when a slot was picked and the box loop landed here first
            self.tap(eb.KEY_A if slot is None else eb.KEY_B)
            self.run(60)
            return
        if slot is None:
            print(f"  learn: {mon.nickname} declines move {new}", flush=True)
            self.tap(eb.KEY_B)
        else:
            print(f"  learn: {mon.nickname} swaps slot {slot} ({rowe_rom.move(mon.moves[slot]).name}) for {rowe_rom.move(new).name}", flush=True)
            self.tap(eb.KEY_A)
        self.run(60)

    def party_menu_step(self) -> None:
        """On the party menu after a faint or a matchup switch: cursor to the bench mon with the
        best edge against the foes, pick it, confirm Send Out. A "no energy left" box from a
        wrong pick swallows one press; the next step lands the rest."""
        party = self.g.party()
        mons = self.g.battlers()
        active = mons[0]
        name, self.switch_to = self.switch_to, None
        # resolved by name at menu time: every switch swaps two party slots, so a slot planned
        # before one resolved would send the mon just recalled straight back out
        # in a double the partner is on the field too; picking it gets "is already in battle!" and
        # the menu ate every press (Fortree's Flint + Edwardo fight, ten STALLs on Greedent)
        fielded = {m.personality for m in mons[0::2]}
        bench = [m for m in party if m.personality not in fielded]
        target = next((m.slot for m in bench if name in (m.personality, m.nickname) and m.hp > 0), None)
        if target is None and any(m.hp == 0 for m in mons[0::2]):
            # a fielded mon fainted (the lead, or the partner in a double), so the menu is a forced
            # replacement that ignores B; pick the best live bench mon instead of parking on Cancel
            foes = [m for m in mons[1::2] if m.hp > 0]
            target = best_switch(bench, active, foes)
            if target is None:
                target = next((m.slot for m in bench if m.hp > 0), None)
        if target is None:
            # a "will you switch?" Yes opened this menu with the fighter standing; the first B
            # parks the cursor on Cancel, the second leaves (a forced switch refuses both)
            self.tap(eb.KEY_B)
            self.run(30)
            self.tap(eb.KEY_B)
            self.run(60)
            return
        # grid is 0 1 / 2 3 / 4 5 w/ Cancel below, traced on party_menu.ss and catch_switch.ss
        # (DOWN 0 -> 2 -> 4, RIGHT 0 -> 1, UP 1 <-> 3); the menu eats the first press after its
        # opening fade and the slot read trails the press by one, so every press is checked
        # against the cursor it left
        # a double battle lays the menu out as one list, both fielded mons then the bench, so
        # UP and DOWN step the slot by one and LEFT and RIGHT change nothing
        double = bool(self.g.battle_type_flags() & BATTLE_TYPE_DOUBLE)
        # gPartyMenuSlot updates a few frames behind the dpad press under the cursor's slide, so a
        # fixed run() after a tap can read the slot the cursor is leaving instead of the one it
        # reaches, and an A fired on that read confirms whatever slot the cursor actually settled
        # on, a fainted one costing a "no energy left" box, a B and a step. Poll the slot off its
        # pre-tap value after every tap, and confirm only a live slot that is the target, re-walking
        # from wherever the cursor really sits otherwise.
        for _ in range(PARTY_MENU_WALK_RETRIES):
            for _ in range(10):
                cur = self.g.party_menu_slot()
                if cur == target:
                    break
                if cur > 5:
                    key = eb.KEY_DOWN  # Cancel wraps to slot 0
                elif not double and cur % 2 != target % 2:
                    key = eb.KEY_RIGHT if target % 2 else eb.KEY_LEFT
                else:
                    key = eb.KEY_DOWN if target > cur else eb.KEY_UP
                self.tap(key)
                self.wait_until(lambda c=cur: self.g.party_menu_slot() != c, 30)
            landed = self.g.party_menu_slot()
            if landed == target and party[landed].hp > 0:
                break
        else:
            # the cursor never settled on the live target: a message box ("no energy left to
            # battle!") ate the presses, or the slot read never caught the walk. B closes a box; a
            # forced switch ignores a B with no box up
            self.tap(eb.KEY_B)
            self.run(30)
            return
        print(f"  switch: send out {party[target].nickname} (slot {target})", flush=True)
        self.tap(eb.KEY_A)
        self.run(30)
        self.tap(eb.KEY_A)
        self.run(90)
        # the grid redraws under the leaving mon for a beat before the turn runs, and a step that
        # reads it there re-decides the same switch; hold until the pick is on the field or the
        # controller has left the action menu
        for _ in range(10):
            if self.g.battlers()[0].personality == party[target].personality or not self.g.in_battle() \
                    or self.e.u32(S.BATTLER0_CONTROLLER_FUNC) not in S.PLAYER_CHOOSE_ACTION_FUNCS:
                break
            self.run(30)

    def _switch_budget(self, active_pid: int) -> bool:
        """True while a matchup switch is still worth trying for the mon now choosing. A switch
        decided for the mon that already chose last turn never put a new one out (a double-battle
        send the party menu could not land), so each repeat spends one of SWITCH_FAIL_CAP tries and
        a different active resets the count. Caps the retries so a non-landing switch falls through
        to Fight instead of re-deciding the same switch every turn with no floor."""
        if active_pid != self._switch_active:
            self._switch_active, self._switch_fails = active_pid, 0
        else:
            self._switch_fails += 1
        return self._switch_fails < SWITCH_FAIL_CAP

    @staticmethod
    def gym_ready(party) -> bool:
        """Lead above the readiness line with two mons still holding attacking PP, so a leader
        fight opens with a switch in reserve instead of a PP-starved lead a wild-grind trek left
        behind. A Center visit restores both."""
        if party[0].hp * 100 < party[0].max_hp * GYM_READY_HP_PERCENT:
            return False
        return sum(1 for m in party if can_attack(m)) >= 2

    def _retreat_warranted(self, party) -> bool:
        """Whether a hurt party treks to a Center now, grounded in the active goal. A team with no
        mon able to attack always goes, rotation cannot save it. Approaching a gym the whole team
        fights at once, so top off when not gym_ready. A grind or explore tolerates a chipped lead
        and the overworld rotation leads the next able mon, so one low mon is no trek."""
        if not any(can_attack(m) for m in party if m.hp > 0):
            return True
        if self.goal.get("mode") == "gym" and self.g.position()[2:] != tuple(self.goal.get("map", ())):
            return not self.gym_ready(party)
        return False

    def needs_heal(self) -> bool:
        party = self.g.party()
        if party[0].hp * 100 < party[0].max_hp * HEAL_HP_PERCENT:
            return True
        # a lead w/ no attacking PP runs; the Center restores PP and the overworld
        # rotation then hands the slot to whoever can still attack
        return not can_attack(party[0])

    @staticmethod
    def top_off_due(party) -> bool:
        """Whether a free Center stop is worth taking from inside a service town: any mon below
        full HP, or a lead w/ no attacking PP. The retreat thresholds gate a trek across the map
        to a Center; this gates only a stop the walk already stands on, so the bar is full-vs-not."""
        if any(m.hp < m.max_hp for m in party):
            return True
        return not can_attack(party[0])

    def battle_signature(self) -> tuple:
        return (self.g.exec_flags(), tuple((m.hp, m.pp) for m in self.g.battlers()), self.g.poke_balls())

    def _stall_dump(self, msg: str) -> None:
        """Save the frozen state to /tmp, flag the stall so the snapshot is left untouched, and stop
        the run so the supervisor relaunches from the last good snapshot."""
        path = f"/tmp/rowe_stall_{int(time.time())}"
        with open(path + ".ss", "wb") as f:
            f.write(self.e.save_state())
        self.e.save_png(path + ".png")
        print(f"{msg}, dumped {path}.ss", flush=True)
        self.stalled = True
        raise StopRequested

    def stall_check(self, sig: tuple, streak: int) -> int:
        """Count unchanged battle signatures across steps; dump and stop at the limit."""
        if sig != self.last_sig:
            self.last_sig = sig
            return 0
        if streak + 1 >= STALL_STEPS:
            self._stall_dump(f"STALL: {STALL_STEPS} steps w/o change, chooser {self.g.chooser()} exec {sig[0]:#x}")
        return streak + 1

    def say(self, line: str) -> None:
        self.events.append(line)
        self.event_seq += 1
        print(line, flush=True)

    def write_status(self) -> dict:
        """states/status.json, the planner's only view of the game; returns the row written."""
        x, y, group, num = self.g.position()
        party = [party_row(m) for m in self.g.party() if m.level]  # a slot mid-deposit reads level 0
        # the last full roster, what fill_party brings back first after an interrupted swap
        if len(party) == PARTY_SIZE and self.state_path:
            full = sorted(m["personality"] for m in party)
            if full != self._party_full:
                self._party_full = full
                write_json(self.state_file("party_full.json"), full)
        boxes = [{
            "box": m.box, "slot": m.position, "species": m.species, "name": m.nickname,
            "level": rowe_rom.level_from_exp(m.species, m.experience), "shiny": m.shiny,
        } for m in self.g.boxes() if m.species < rowe_rom.SPECIES_COUNT]
        dex_owned, dex_seen = self.g.pokedex()
        status = {
            "ts": time.time(), "pid": os.getpid(), "goal": self.goal,
            "map": [group, num], "tile": [x, y], "party": party, "boxes": boxes, "field_moves": sorted(self.field_moves()),
            "balls": dict(self.g.poke_balls()).get(catch.POKE_BALL, 0), "money": self.g.money(),
            "badges": self.g.badges(), "var_badges": self.g.var(S.VAR_NUM_BADGES),
            "badge_flags": [self.g.flag(S.FLAG_BADGE01 + i) for i in range(S.BADGE_COUNT)],
            "johto_flags": [self.g.flag(S.JOHTO_BADGE01 + i) for i in range(S.JOHTO_BADGE_COUNT)],
            "champion": self.g.flag(S.FLAG_SYS_GAME_CLEAR),
            "ferry_flags": {f"0x{f:X}": self.g.flag(f) for f in FERRY_FLAGS},
            "caught_species": sorted(self.ledger.caught),
            "dex_owned": dex_owned, "dex_seen": dex_seen, "rom_sha": rom_sha(),
            "wanted_types": sorted(rowe_rom.TYPE_NAMES[t] for t in self.wanted),
            "battles": self.battles, "wins": self.wins, "caught": self.caught,
            "events": list(self.events), "event_seq": self.event_seq, "exit_reason": self.exit_reason,
        }
        path = os.path.join(os.path.dirname(self.state_path), "status.json")
        with open(path + ".tmp", "w") as f:
            json.dump(status, f, indent=1)
        os.replace(path + ".tmp", path)
        self.last_status = time.monotonic()
        return status

    def check_goal(self) -> None:
        """Re-read the goal and stop when it is met or its mode is unknown."""
        self.goal = read_goal(os.path.join(os.path.dirname(self.state_path), "goal.json"))
        mode = self.goal.get("mode")
        here = self.g.position()[2:]
        if mode == "grind":
            cap = self.goal.get("cap")
            able = [m for m in self.g.party() if can_attack(m)]
            # cap None is a hold-grind past a gated frontier: never exits, so the supervisor
            # keeps the stream up instead of stopping on a handoff nothing can act on yet
            if cap and able and min(m.level for m in able) >= cap:
                raise GoalExit(f"goal reached: every attacker at cap {cap}")
            if cap is None and self._held and hold_stale(self._held, self.graph, self.field_moves(), self.battles):
                self._held = None
                raise GoalExit("hold-grind re-checking the gated frontier, re-planning")
            return
        if mode == "travel":
            if here == tuple(self.goal.get("to", ())):
                raise GoalExit(f"goal reached: arrived at map {list(here)}")
            return
        if mode == "explore":
            to = self.goal.get("to")
            if to and tuple(to) in self.graph.visited:
                raise GoalExit(f"goal reached: discovered map {to}")
            cap = self.goal.get("max_maps")
            if cap and len(self.graph.visited) >= cap:
                raise GoalExit(f"goal reached: {len(self.graph.visited)} maps mapped")
            return
        if mode == "gym":
            badges = self.g.badges()
            if badges > self.goal.get("badges", 0):
                raise GoalExit(f"goal reached: badge {badges} earned")
            return
        if mode == "sevii":
            # the Sevii leg's routed destination and its badge-flag decode are a later ticket. Until
            # then the leg maps westward toward the island pass, which nothing here completes, so the
            # stream stays up instead of halting on an unsupported goal.
            return
        raise GoalExit(f"unsupported goal {self.goal}")

    def _graph_flags(self) -> set:
        """Gate flags currently set, read live from the emulator for the script-edge layer. Only the
        flags that actually gate a crossing are read, so routing sees a ferry open the frame the game
        sets its flag rather than from a snapshot on disk."""
        return {f for f in script_decode.gate_flags() if self.g.flag(f)}

    def replan(self) -> bool:
        """After a GoalExit, re-decide the goal in this process the way run-grind.sh's planner
        pass does between launches, and return True once the loop can go on w/ the emulator and
        stream still running. False hands the exit to the supervisor: an unsupported goal (its
        halt case), or a burst of REPLAN_BURST exits inside REPLAN_WINDOW_S, which is the tight
        loop a relaunch's reload and five-second pause used to pace."""
        status = self.write_status()
        if self.exit_reason.startswith("unsupported") or self.exit_reason == "no_grass_idle":
            return False
        now = time.monotonic()
        self._replans = [t for t in self._replans if now - t < REPLAN_WINDOW_S] + [now]
        if len(self._replans) >= REPLAN_BURST:
            print(f"replan: {len(self._replans)} goal exits in {REPLAN_WINDOW_S}s, handing to the supervisor", flush=True)
            return False
        if self.keep_state:
            # the stuck exits resume the last good snapshot instead of saving the wedged spot
            with open(self.state_path, "rb") as f:
                self.e.load_state(f.read())
            self.keep_state = False
        else:
            self.snapshot(self.state_path)
        self.graph.flags = self._graph_flags()
        goal, why = planner.recommend(status, self.graph)
        print(f"replan: {goal} because {why}", flush=True)
        goal_path = os.path.join(os.path.dirname(self.state_path), "goal.json")
        with open(goal_path + ".tmp", "w") as f:
            json.dump(goal, f)
        os.replace(goal_path + ".tmp", goal_path)
        self.exit_reason = ""
        self._gym_done.clear()
        self._route_resets.clear()
        self._stuck.clear()
        return True

    def snapshot(self, path: str) -> None:
        """Atomic save-state write; called only at moments the game just proved responsive. The
        live run also keeps a timestamped copy in the backup ring so a bad overwrite is recoverable;
        a non-live writer aimed at the live save raises instead of clobbering it."""
        rowe_live.guard_write(path, self._live_writer)
        blob = self.e.save_state()
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(blob)
        os.replace(tmp, path)
        self.last_snapshot = time.monotonic()
        if self._live_writer and rowe_live.is_live_target(path):
            rowe_live.archive(blob)

    def lowest_lead(self) -> int | None:
        """Slot of the lowest-level conscious mon when the lead outlevels it by LEAD_GAP, else None."""
        party = self.g.party()
        if party[0].hp == 0:
            self.need_heal = True
            return None
        # only a mon above the heal line takes point, so a chipped grinder waits on the bench
        # instead of leading into grass, fleeing on low HP and leading again; nobody healthy
        # means the party as a whole needs the Center
        healthy = [m for m in party if can_attack(m) and m.hp * 100 >= m.max_hp * HEAL_HP_PERCENT]
        if not healthy:
            self.need_heal = True
            return None
        low = min(healthy, key=lambda m: m.level)
        lowest = min((m for m in party if can_attack(m) and m.hp > 0), key=lambda m: m.level)
        cap = self.goal.get("cap") if self.goal.get("mode") == "grind" else None
        if lowest not in healthy and (low.level - lowest.level >= LEAD_GAP or (cap is not None and low.level >= cap)):
            # the grinder sits hurt on the bench and every healthy mon is past the grind gap or at
            # the cap, so fights lead by them move no level toward it; one Center trip puts it back in front
            self.need_heal = True
        if party[0] not in healthy:
            return low.slot or None
        # a lead at the grind cap gains nothing from the fight, so any attacker still under
        # the cap takes point even inside the gap
        lead_done = cap is not None and party[0].level >= cap > low.level
        return low.slot if low.slot and (party[0].level - low.level >= LEAD_GAP or lead_done) else None

    def _exp_lead(self, me) -> bool:
        """Whether the active mon is out for the exp share: a conscious party member outlevels
        it by the same LEAD_GAP that lowest_lead puts it in front for."""
        return any(m.hp > 0 and m.level - me.level >= LEAD_GAP for m in self.g.party())

    def heal_bench_from_bag(self) -> None:
        """Spend Medicine-pocket HP items on party mons under the heal line, worst off first, until
        none is low or the bag holds no item that helps. A fainted mon needs a Revive, so it is left
        for the Center. Call from the overworld with the post-battle text already cleared."""
        if self.goal.get("mode") == "grind":
            # the Center a few maps over heals the bench for free; bought restores are for travel
            # and the gym approach, where the walk back is the cost
            return
        for _ in range(len(self.g.party())):
            low = [m for m in self.g.party() if 0 < m.hp and m.hp * 100 < m.max_hp * HEAL_HP_PERCENT]
            if not low:
                return
            target = min(low, key=lambda m: m.hp * 100 // m.max_hp)
            item = best_hp_item(self.g.medicine(), target.max_hp - target.hp)
            if item is None:
                return
            slot, iid, _ = item
            before = sum(q for _, q in self.g.medicine())
            print(f"  field heal: {rowe_rom.item_name(iid)} on {target.nickname} {target.hp}/{target.max_hp}", flush=True)
            self.errands.use_hp_item_in_field(slot, target.slot)
            if sum(q for _, q in self.g.medicine()) >= before:
                return

    def next_leader_type(self) -> int | None:
        """Attack/defence type of the next unbeaten gym's leader by the fixed Hoenn order, or None
        once all eight badges are in, so a Center swap scores the team against the gym it heads for."""
        for i in range(S.BADGE_COUNT):
            if not self.g.flag(S.FLAG_BADGE01 + i):
                return GYM_LEADER_TYPES[i]
        return None

    def unbeaten_leaders(self) -> list:
        """Badge indexes of the gyms still standing, Hoenn order."""
        return [i for i in range(S.BADGE_COUNT) if not self.g.flag(S.FLAG_BADGE01 + i)]

    def scoring_builds(self) -> tuple:
        """(core builds, next leader's build or None): every remaining leader at the badge count it will
        be fought at in ladder order, then the League at LEAGUE_BADGES, each as foe type pairs."""
        badges = self.g.badges()
        left = self.unbeaten_leaders()
        core = [foe_types(rowe_rom.leader_build(rowe_rom.LEADERS[k], min(badges + i, rowe_rom.LEAGUE_BADGES)))
                for i, k in enumerate(left)]
        core += [foe_types(rowe_rom.leader_build(n, rowe_rom.LEAGUE_BADGES)) for n in rowe_rom.LEAGUE]
        nxt = foe_types(rowe_rom.leader_build(rowe_rom.LEADERS[left[0]], badges)) if left else None
        return core, nxt

    def refresh_wanted(self) -> None:
        """The types the catch policy prefers: wanted_types over the party at its floor against the core
        builds; at launch and after every heal visit, when the party can have changed."""
        party = self.g.party()
        if not party:
            return
        floor = min(m.level for m in party)
        team = [mon_profile(m, floor, self.g.iv_boosts()) for m in party]
        self.wanted = wanted_types(team, self.scoring_builds()[0])

    def teach_tms(self) -> None:
        """On the field after the PC at a heal visit: each bag TM that closes a wanted type goes on the
        core member tm_assignments names, through the field bag."""
        party, tms = self.g.party(), self.g.tms()
        if not party or not tms:
            return
        for pocket_slot, slot, forget, move in tm_assignments(party, self.g.iv_boosts(), tms, self.scoring_builds()[0]):
            mon = self.g.party()[slot]
            ok = self.errands.teach_tm_in_field(pocket_slot, slot, forget, move)
            print(f"tm: {rowe_rom.item_name(tms[pocket_slot][0])} {rowe_rom.move(move).name} on {mon.nickname} over "
                  f"{rowe_rom.move(mon.moves[forget]).name} -> {ok}", flush=True)
        self.refresh_wanted()

    def teach_egg_moves(self) -> None:
        """At the blue nurse after the PC and the TMs: egg moves that close a wanted type, TEACH_EGG_BP
        each, once the badge count opens the service."""
        if self.g.badges() < S.TEACH_EGG_BADGES:
            return
        party, bp = self.g.party(), self.g.battle_points()
        # (species, move) pairs her list has not offered, kept across runs so a move the ROM egg table
        # names and she never lists stops costing a visit
        declined_path = self.state_file("egg_declined.json")
        declined = {tuple(x) for x in json.load(open(declined_path))} if os.path.exists(declined_path) else set()
        for slot, forget, move in egg_assignments(party, self.g.iv_boosts(), bp, self.scoring_builds()[0], frozenset(declined)):
            mon = self.g.party()[slot]
            r = self.errands.teach_egg_move_at_nurse(slot, forget, move)
            print(f"egg move: {rowe_rom.move(move).name} on {mon.nickname} over {rowe_rom.move(mon.moves[forget]).name} "
                  f"-> {r}, BP {bp} -> {self.g.battle_points()}", flush=True)
            if r == "absent":
                declined.add((mon.species, move))
                write_json(declined_path, sorted(declined))
        self.refresh_wanted()

    def state_file(self, name: str) -> str:
        return os.path.join(os.path.dirname(self.state_path), name)

    def fill_party(self) -> None:
        """Inside a Center after the heal: a party under six while the PC holds a mon is withdrawn back
        to six. A boxed mon that was in the last full party comes back first, highest level first,
        since a short party is an interrupted swap and its own member is what it lost; after that the
        box mon whose addition scores highest against the core builds among those within LEVEL_CUTOFF
        of the grind map's top wild level, barred mons only when nothing else is boxed."""
        ledger = SwapLedger(self.state_file("swaps.json"))
        full_path = self.state_file("party_full.json")
        last_full = set(json.load(open(full_path))) if os.path.exists(full_path) else set()
        core_builds, _ = self.scoring_builds()
        top = self.grind_wild_top()
        for _ in range(PARTY_SIZE):
            party = self.g.party()
            box = [bm for bm in self.g.boxes() if bm.species < rowe_rom.SPECIES_COUNT]
            if not party_short(len(party), len(box)):
                return
            pool = [bm for bm in box if not ledger.barred(bm.personality)] or box
            level = lambda bm: rowe_rom.level_from_exp(bm.species, bm.experience)
            back = [bm for bm in pool if bm.personality in last_full]
            if back:
                incoming = max(back, key=level)
            else:
                near = [bm for bm in pool if top is None or level(bm) >= top - LEVEL_CUTOFF] or pool
                floor = min(m.level for m in party)
                ivs = self.g.iv_boosts()
                team = [mon_profile(m, floor, ivs) for m in party]
                slot = best_fill(team, [(bm.slot, mon_profile(bm, floor, ivs)) for bm in near], core_builds)
                incoming = next(bm for bm in near if bm.slot == slot)
            ok = self.errands.withdraw_at_pc(incoming.slot)
            print(f"fill party: species {incoming.species} L{level(incoming)} box slot {incoming.slot} in"
                  f"{' (last full party)' if back else ''}, party {len(party)} -> {len(self.g.party())} -> {ok}", flush=True)
            if not ok:
                return

    def do_swap_order(self) -> None:
        """Inside a Center after the heal: states/swap_order.json, {"out": species, "in": species} written
        by the admin, trades the party mon of the out species for the highest-level boxed mon of the in
        species, locks the incoming mon like a core swap and bars the outgoing one, then deletes the
        order. An order neither side matches is logged and deleted."""
        path = self.state_file("swap_order.json")
        if not os.path.exists(path):
            return
        order = json.load(open(path))
        party = self.g.party()
        out = next((m for m in party if m.species == order["out"]), None)
        box = [bm for bm in self.g.boxes() if bm.species == order["in"]]
        if out is None or not box:
            print(f"swap order: out {order['out']} in {order['in']} unmatched, party {[m.species for m in party]}, dropped", flush=True)
            os.remove(path)
            return
        incoming = max(box, key=lambda bm: bm.experience)
        ok = self.errands.swap_at_pc(out.slot, incoming.slot)
        print(f"swap order: {out.nickname} slot {out.slot} out, species {incoming.species} box slot {incoming.slot} in -> {ok}", flush=True)
        if ok:
            SwapLedger(self.state_file("swaps.json")).record("order", incoming.personality, out.personality)
            os.remove(path)

    def after_heal(self) -> None:
        """The Center's errands once the nurse is done: the admin's swap order, the party refill, the PC
        swap, the TMs for the team it left, then the blue nurse's egg moves."""
        self.do_swap_order()
        self.fill_party()
        self.do_pc_swap()
        self.teach_tms()
        self.teach_egg_moves()

    def grind_wild_top(self) -> int | None:
        """Top land wild level on the map the grind goal names; None off a grind or on a map w/ no land table."""
        if self.goal.get("mode") != "grind":
            return None
        span = rowe_rom.wild_land_levels().get(tuple(self.goal.get("map", ())))
        return span[1] if span else None

    def do_pc_swap(self) -> None:
        """Inside a Center after the heal, one heal visit on the ledger: a core swap when the budget is
        open (CORE_SWAP_VISITS since the last) and a box mon lifts the score against the League and every
        remaining leader by the core margin, else a flex swap when a box mon out-scores the current flex
        mon as a counter to the next leader by FLEX_MARGIN, through the storage PC. Core scores every mon
        at the party floor; flex scores both sides at the grind cap, since a flex candidate is judged by
        what the grind makes it before the gym. A core mon swapped in is locked for CORE_SWAP_VISITS, a
        flex mon swapped in holds until that leader is beaten, a mon swapped out is barred for
        BARRED_VISITS, and a candidate more than LEVEL_CUTOFF under the grind map's top wild level is cut
        before scoring unless its type fills a gap. Every box is a candidate since swap_at_pc turns
        pages."""
        ledger = SwapLedger(os.path.join(os.path.dirname(self.state_path), "swaps.json"))
        ledger.visit()
        badges = self.g.badges()
        box = [bm for bm in self.g.boxes() if bm.species < rowe_rom.SPECIES_COUNT and not ledger.barred(bm.personality)]
        party = self.g.party()
        floor = min(m.level for m in party)
        ivs = self.g.iv_boosts()
        team = [mon_profile(m, floor, ivs) for m in party]
        core_builds, nxt = self.scoring_builds()
        self.wanted = wanted_types(team, core_builds)
        top = self.grind_wild_top()
        if top is not None:
            box = [bm for bm in box if rowe_rom.level_from_exp(bm.species, bm.experience) >= top - LEVEL_CUTOFF
                   or set(rowe_rom.species(bm.species).types) & self.wanted]
        if not box:
            return
        box_level = {bm.slot: rowe_rom.level_from_exp(bm.species, bm.experience) for bm in box}
        pool = [(bm.slot, mon_profile(bm, floor, ivs)) for bm in box]
        levels = ([m.level for m in party], box_level)
        flex = flex_slot(team, core_builds)
        movable = [i for i in range(len(team)) if not ledger.locked(party[i].personality)]
        plan, kind = None, "core"
        if ledger.core_open():
            plan = best_swap(team, pool, core_builds, [i for i in movable if i != flex], core_margin(team, core_builds), levels)
        if plan is None and nxt is not None and flex in movable and not ledger.flex_hold(party[flex].personality, badges):
            kind = "flex"
            cap = self.goal.get("cap") or top or floor
            plan = best_flex(party[flex], party[flex].level, [(bm.slot, bm, box_level[bm.slot]) for bm in box], nxt, flex, cap, ivs)
        if plan is None:
            print(f"box swap: none at visit {ledger.d['visits']}, floor {floor}, core {'open' if ledger.core_open() else 'closed'}", flush=True)
            return
        out, slot, gain = plan
        incoming = next(bm for bm in box if bm.slot == slot)
        outgoing = party[out]
        ok = self.errands.swap_at_pc(out, slot)
        print(f"box swap ({kind}): {outgoing.nickname} slot {out} out, species {incoming.species} box slot {slot} in, "
              f"+{gain} -> {ok}", flush=True)
        if ok:
            ledger.record(kind, incoming.personality, outgoing.personality, badges)

    def field_moves(self) -> frozenset:
        return field_tools(self.g.badges())

    def _grid(self) -> Grid:
        """Live-frame grid with climb set from the Waterfall Tool in the bag, the same check the
        crossing path uses, so a reachability read and the walk that acts on it agree on whether a
        fall is climbable. A grid built without this check left climb False and hid the upper half
        of any map reached over a waterfall."""
        grid = Grid(self.e)
        grid.climb = any(item == ITEM_WATERFALL_TOOL for item, _ in self.g.key_items())
        return grid

    def _landing_rank(self, hop: tuple, nxt: tuple | None, surf: bool = False):
        """(rank, w, h) for a crossing into `hop`, off its ROM layout, or None when unreadable.
        rank(landing_tile) is (0, -region size) when the tile's region under `surf` reaches
        hop's crossing toward `nxt` (or no such crossing is known), (1, -size) when it does
        not, (2, 0) off the map. A pocket (Route 104's east cove, Petalburg's pond-locked
        northwest) is small and reaches nothing, so it ranks behind the map proper. A surf
        crossing lands on water, so its region is read w/ surf, else every bank is a pocket."""
        cells = rowe_rom.map_cells(*hop)
        if cells is None:
            return None
        w, h, _ = cells
        grid = Grid.from_cells(*cells)
        grid._behavior = rowe_rom.metatile_behavior(*hop)
        edge_rows = {rowe_map.DIR_NORTH: [(x, 0) for x in range(w)], rowe_map.DIR_SOUTH: [(x, h - 1) for x in range(w)],
                     rowe_map.DIR_WEST: [(0, y) for y in range(h)], rowe_map.DIR_EAST: [(w - 1, y) for y in range(h)]}
        targets = set()
        for d, dest in rowe_rom.map_connections(*hop):
            if dest == nxt:
                targets.update(edge_rows.get(d, []))
        for x, y, dest in rowe_rom.map_warps(*hop):
            if dest == nxt:
                targets |= {(x, y), (x, y + 1), (x, y - 1), (x + 1, y), (x - 1, y)}
        memo = {}

        def rank(landing: tuple) -> tuple:
            c = grid.cell(*landing)
            if c & S.GRID_ID_MASK == S.GRID_UNDEFINED or c & S.GRID_BLOCKED:
                return (2, 0)
            region = grid.region(landing, surf)
            if region not in memo:
                reach = grid.reachable(landing, surf)
                memo[region] = (0 if not targets or not targets.isdisjoint(reach) else 1, -len(reach))
            return memo[region]
        return rank, w, h

    def _cross_to(self, here: tuple, hop: tuple, nxt: tuple | None = None) -> tuple:
        """Take the live connection to bordering map `hop`, else its warp. Returns (status,
        result): result "moved" when the map changed, "battle" when a wild battle interrupted
        the walk, "blocked" when the edge could not be reached, which idles frames so the loop
        keeps feeding the stream. `nxt`, the hop after this one, picks the landing region."""
        surf = "SURF" in self.field_moves()
        lr = self._landing_rank(hop, nxt, surf)
        for c in rowe_map.connections(self.e):
            if (c.group, c.num) == hop:
                edge_rank = None
                if lr is not None:
                    rank, w, h = lr

                    def edge_rank(edge: tuple) -> tuple:
                        if c.direction in (rowe_map.DIR_NORTH, rowe_map.DIR_SOUTH):
                            return rank((edge[0] - c.offset, h - 1 if c.direction == rowe_map.DIR_NORTH else 0))
                        return rank((w - 1 if c.direction == rowe_map.DIR_WEST else 0, edge[1] - c.offset))
                if c.direction in (rowe_map.DIR_DIVE, rowe_map.DIR_EMERGE):
                    status = self.errands.take_dive(c.direction, surf=surf, tools=self.field_moves())
                else:
                    status = self.errands.cross_edge(c.direction, surf=surf, rank=edge_rank, tools=self.field_moves())
                how = f"dir {c.direction}"
                break
        else:
            ferry_label = script_decode.seagallop_label(here, hop)
            ferry_obj = script_decode.talk_object(here, hop) if ferry_label is not None else None
            if ferry_obj is not None:
                # the Seagallop crossing is a talk, not a step-on warp: the sailor opens a native
                # scrolling menu whose row text picks the destination, so take_warp finds no tile and
                # talk_warp drives the menu to the matching row instead.
                status = self.errands.talk_warp(ferry_obj["obj"], hop, ferry_label)
                how = "ferry"
            elif hop in rowe_rom.dive_script_edges().get(here, set()):
                # here and hop are linked by a setdivewarp the ROM connection table never carries
                # (Sootopolis (0,7) <-> underwater (24,5)). Surfacing from the seabed emerges on a B
                # press; diving in from the surface submerges on an A press over deep water.
                if rowe_rom.is_underwater(*here):
                    status = self.errands.take_dive(rowe_map.DIR_EMERGE, surf=surf, tools=self.field_moves())
                    how = "emerge"
                else:
                    status = self.errands.take_dive(rowe_map.DIR_DIVE, surf=surf, tools=self.field_moves())
                    how = "dive"
            else:
                warp_rank = None
                if lr is not None:
                    rank, dest_warps = lr[0], rowe_rom.map_warps(*hop)

                    def warp_rank(wp: rowe_map.Warp) -> tuple:
                        return rank(dest_warps[wp.dest_warp][:2]) if wp.dest_warp < len(dest_warps) else (2, 0)
                status = self.errands.take_warp(hop, surf=surf, rank=warp_rank, tools=self.field_moves())
                how = "warp"
        after = self.g.position()[2:]
        if status == "battle":
            result = "battle"
        elif after == hop:
            result = "moved"
        elif after == here:
            result = "blocked"
        else:
            # left `here` for a map other than the hop: a press that was meant to fire the warp
            # walked a connection instead (the city gate on [1,31]'s east edge, the party pressed
            # off the edge back onto Route [0,33]), so the crossing counts as stuck, never as moved
            result = "missed"
            self._persist_blocked(here, hop, status)
        print(f"travel {here} -> {list(hop)} {how}: {status} ({result}) at {list(after)}", flush=True)
        if result == "blocked":
            self._persist_blocked(here, hop, status)
            tile = self.g.position()[:2]
            key = (here, hop, tile)
            self._blocked_streak[key] = self._blocked_streak.get(key, 0) + 1
            if self._blocked_streak[key] >= BLOCKED_STREAK:
                # the tile the walk cannot leave is no place to resume from, so the state file
                # keeps the last snapshot that preceded it
                self.keep_state = True
                raise GoalExit(f"travel stuck: {status} {here} -> {list(hop)} {BLOCKED_STREAK}x from {tile}, re-planning")
            self.run(60)
        return status, result

    def _persist_blocked(self, here: tuple, hop: tuple, status: str) -> None:
        """Gate a border the walk could not cross so exploration stops re-picking it. "unreachable"
        means no passable edge tile exists at all, a structural gate (water without Surf), gated on
        the first failure. A "stuck" border has a tile the walk never clears (a warp that loops back,
        a door on an unmet event flag) and reports the same every run. play.py re-execs per
        grind run, so the tally is persisted to states/stuck_hits.json; without that, one stuck per
        run never reaches STUCK_GATE and the dead warp is re-picked every run. The count keys on the
        field moves too, so the gate it feeds reopens when a new tool changes that set. Gating the
        edge lets the frontier exhaust into a grind instead of the party re-treading the dead warp."""
        if self.graph is None:
            return
        if status == "unreachable":
            # no path from where the player stands: a border the ROM layout reads shut (no_warp,
            # unreachable, or a dormant dive) is gated for good under that reason, any other is a
            # region miss the run-local _stuck already holds and never counts toward the gate
            # (Route 134 gated both exits from one pocket)
            reason = self._border_open(here, hop)
            if reason in ("no_warp", "unreachable", "script_no_go"):
                self.graph.block(here, hop, self.field_moves(), reason=reason)
            return
        moves = self.field_moves()
        key = self._stuck_key(here, hop, moves)
        self._stuck_hits[key] = self._stuck_hits.get(key, 0) + 1
        self._save_stuck_hits()
        if self._stuck_hits[key] >= STUCK_GATE:
            self.graph.block(here, hop, moves, reason="stuck")

    def _border_open(self, here: tuple, hop: tuple) -> str | None:
        """Why the border of `here` toward `hop` is crossable, read off the ROM layout rather than
        from where the player stands, since a map split by water or a ledge (Route 110 either side
        of the cycling road) reaches a border from one region and not the other. "open" when a
        standable connection tile or an enterable warp tile exists, "no_warp" when every warp tile
        to `hop` is solid rock, "unreachable" when a connection border holds no passable tile,
        "script_no_go" when a dive header is dormant (water present, no diveable tile). None when
        `hop` is neither a connection nor a warp of `here`, or the layout is unreadable."""
        layout = rowe_rom.map_cells(*here)
        if layout is None:
            return None
        w, h, cells = layout
        grid = Grid.from_cells(w, h, cells)
        grid._behavior = rowe_rom.metatile_behavior(*here)
        for direction, dest in rowe_rom.map_connections(*here):
            if tuple(dest) == hop:
                break
        else:
            warps = [(x, y) for x, y, dest in rowe_rom.map_warps(*here) if tuple(dest) == hop]
            if not warps:
                return None
            # the static map_cells layout misreads some warp tiles (a dead wall-warp reads as open
            # floor), so is_wall_warp off the from-cells grid lies; the live grid carries the
            # resolved collision, so read the warp tile there whenever the party stands on `here`.
            pos = self.g.position()[2:] if getattr(self, "g", None) is not None else None
            wgrid = self._grid() if here == pos else grid
            return "open" if not all(wgrid.is_wall_warp(x, y) for x, y in warps) else "no_warp"
        if direction in (rowe_map.DIR_DIVE, rowe_map.DIR_EMERGE):
            # a dive/emerge link fires from a water tile the field-move prompt accepts, never a
            # border tile, so "open" is whether the layout holds such a tile. A dive needs a
            # diveable (deep-water) tile; a surf-only ocean route carries a dormant dive header to
            # its underwater twin and has none, so that link is shut. Emerge surfaces from the
            # seabed, which every behavior but the no-surface pair does, so it reads open. A layout
            # whose behaviors carry no water at all is unreadable here, so it gates nothing (None).
            if direction == rowe_map.DIR_EMERGE:
                return "open"
            if grid._behavior is None:
                return None
            behaviors = {grid._behavior(grid.cell(x, y) & S.GRID_ID_MASK)
                         for y in range(S.MAP_OFFSET, grid.height - S.MAP_OFFSET)
                         for x in range(S.MAP_OFFSET, grid.width - S.MAP_OFFSET)}
            if behaviors & DIVE_BEHAVIORS:
                return "open"
            return "script_no_go" if behaviors & WATER_BEHAVIORS else None
        if direction == rowe_map.DIR_NORTH:
            tiles = [(x, 0) for x in range(w)]
        elif direction == rowe_map.DIR_SOUTH:
            tiles = [(x, h - 1) for x in range(w)]
        elif direction == rowe_map.DIR_WEST:
            tiles = [(0, y) for y in range(h)]
        else:
            tiles = [(w - 1, y) for y in range(h)]
        surf = "SURF" in self.field_moves()
        return "open" if any(grid.passable(x, y, 0, (x, y), surf) for x, y in tiles) else "unreachable"

    @staticmethod
    def _stuck_key(here: tuple, hop: tuple, moves: frozenset) -> str:
        return f"{here[0]},{here[1]}>{hop[0]},{hop[1]}|{','.join(sorted(moves))}"

    def _load_stuck_hits(self, path: str) -> dict:
        self._stuck_hits_path = path
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return {}

    def _save_stuck_hits(self) -> None:
        if not getattr(self, "_stuck_hits_path", None):
            return
        tmp = self._stuck_hits_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._stuck_hits, f)
        os.replace(tmp, self._stuck_hits_path)

    def region(self) -> tuple:
        """(group, num, min reachable tile): where the player stands, down to the walkable area."""
        x, y, group, num = self.g.position()
        return (group, num) + self._grid().region((x, y), "SURF" in self.field_moves())

    def _after_cross(self, region: tuple, hop: tuple, crossed: tuple) -> None:
        """Remember what the crossing taught about this area: a hop w/ no path or warp is dead
        for the run, a mid-walk stuck is dropped at the next battle, and a hop that moved is
        kept so landing back in this same area can retire it."""
        status, result = crossed
        if result == "moved":
            # a crossing straight back to the area the last hop left keeps that record, so
            # the landing retires the door instead of the return trip erasing it
            back = self._last_hop is not None and self._last_hop[0][:2] == hop and self._last_hop[1] == region[:2]
            if not back:
                self._last_hop = (region, hop)
            # the walk itself bringing the player back is the record _blocked_from retires the
            # hop on; an errand's return leaves it False so a route map left for a heal stays open
            self._returned = back
            exits = self._landing_exits()
            print(f"land: {list(self.g.position()[2:])} exits {sorted(list(e) for e in exits)} back={back}", flush=True)
            # a landing area w/ no way on except back across this border is a dead end for the
            # area it was entered from, whatever the rest of the map connects to: Route 104's
            # north half enters Petalburg on a pond-locked corner that reaches no door and no
            # other edge, so the walk bounced between the two maps until the budget ran out
            if exits == {region[:2]}:
                self._blocked.setdefault(region, set()).add(hop)
                print(f"dead end: {list(hop)} entered from {list(region[:2])} reaches nothing else, blocked", flush=True)
            # a loop longer than the 2-map bounce above: Slateport -> water -> back, three maps the
            # _last_hop pair never names. watch recent landings, and when one map recurs CYCLE_HITS
            # times across the window with no new map found in it, re-plan off the snapshot. grind
            # heals bounce a center against a route on purpose, so only goal-directed modes count.
            if self.goal.get("mode") != "grind" and self.graph is not None:
                land, seen = self.g.position()[2:], len(self.graph.visited)
                full = len(self._visit_log) == self._visit_log.maxlen
                oldest_seen = self._visit_log[0][1] if full else None
                self._visit_log.append((land, seen))
                if oldest_seen == seen and sum(1 for m, _ in self._visit_log if m == land) >= CYCLE_HITS:
                    self.keep_state = True
                    self._visit_log.clear()
                    raise GoalExit(f"explore cycle: {list(land)} {CYCLE_HITS}x in {CYCLE_WINDOW} crossings, no new map, re-planning")
        elif status in ("unreachable", "no_warp"):
            self._blocked.setdefault(region, set()).add(hop)
        elif result in ("blocked", "missed"):
            self._stuck.setdefault(region, set()).add(hop)

    def _landing_exits(self) -> set:
        """Maps the walkable area the player stands in leads to: every bordering map whose shared
        edge holds a reachable tile, and every warp destination whose tile or a neighbour of it is
        reachable. Read off the live grid so NPCs and the party's field moves count."""
        x, y, *_ = self.g.position()
        grid = self._grid()
        reach = set(grid.reachable((x, y), "SURF" in self.field_moves()))
        w, h = grid.width - 2 * S.MAP_OFFSET, grid.height - 2 * S.MAP_OFFSET
        edge = {rowe_map.DIR_NORTH: lambda t: t[1] == 0, rowe_map.DIR_SOUTH: lambda t: t[1] == h - 1,
                rowe_map.DIR_WEST: lambda t: t[0] == 0, rowe_map.DIR_EAST: lambda t: t[0] == w - 1}
        # a dive connection (direction 5, Route 124's seabed) has no edge tile to stand on
        exits = {(c.group, c.num) for c in rowe_map.connections(self.e)
                 if c.direction in edge and any(edge[c.direction](t) for t in reach)}
        for wp in rowe_map.warps(self.e):
            around = {(wp.x, wp.y), (wp.x, wp.y + 1), (wp.x, wp.y - 1), (wp.x + 1, wp.y), (wp.x - 1, wp.y)}
            if around & reach:
                exits.add((wp.dest_group, wp.dest_num))
        return exits

    def _blocked_from(self, region: tuple) -> set:
        """Hops not worth taking from this area now; a hop that last led straight back here
        (a house entered, left by the same door) joins them."""
        if self._last_hop and self._last_hop[0] == region:
            hop = self._last_hop[1]
            # a dead end earns the block, and so does a hop the walk took and came straight back
            # from (Scorched Slab off Route 120, whose other exit the route never reached, 100
            # round trips); a route map left for a heal detour (Route 110 from Slateport) has
            # other borders, returns by errand, and stays the way toward the goal
            if self.graph is None or self.graph.neighbors(hop) <= {region[:2]} or self._returned:
                self._blocked.setdefault(region, set()).add(hop)
            if self._returned:
                n = self._bounces[(region, hop)] = self._bounces.get((region, hop), 0) + 1
                if n >= BOUNCE_STREAK and self.graph is not None:
                    # the hop keeps leading straight back here: a repeated identical plan is a wrong
                    # plan, not an exit. Mark the border dead for the session so the next pick and any
                    # re-exec take another exit; travel_toward ends the run only when none is left.
                    self.graph.cur_badges = self.g.badges()
                    self.graph.block(region[:2], hop, self.field_moves(), reason="bounce")
                    print(f"bounce block: {n} round trips {list(region[:2])} <-> {list(hop)}, border marked dead, next exit", flush=True)
            self._last_hop = None
        return self._blocked.get(region, set()) | self._stuck.get(region, set())

    def service_town(self, here: tuple) -> tuple:
        """The town whose Center and Mart serve the party from here: the one it stands in or
        inside, else the fewest map hops away, a tie going to the town whose border is the
        shorter walk across this map. Oldale when nothing known reaches a town."""
        for town, maps in SERVICE_MAPS.items():
            if here in maps:
                return town
        tier = self.graph.nearest_all(here, SERVICE, self._blocked_from(self.region()))
        if not tier:
            return OLDALE
        x, y, _, _ = self.g.position()
        grid = self._grid()
        # grid.width/height carry the MAP_OFFSET pad on each side; the border walk is measured
        # against the real map size, or east and south read farther than they are
        w, h = grid.width - 2 * S.MAP_OFFSET, grid.height - 2 * S.MAP_OFFSET
        return nearer_border(tier, (x, y), (w, h), rowe_rom.map_connections(*here))

    def travel_toward(self, dest: tuple) -> None:
        here = self.g.position()[2:]
        if here == dest:
            raise GoalExit(f"goal reached: arrived at map {list(dest)}")
        if here in self._gyms:
            # the graph hop out of a room gym is its exit mat, which an inner room has no walking
            # path to; three jams gated the warp and every later route out came up empty
            exits = self.graph.world.get(here, set()) - {here}
            if exits:
                out = min(exits)
                r = self.errands.descend_gym(out)
                print(f"gym exit {list(here)} -> {r} at {self.g.position()[:2]}", flush=True)
                if r in ("map_changed", "warped", "battle"):
                    return
        region = self.region()
        # the destination is never a run-local block: a gym entered and left again for a heal
        # detour reads as a bounce by its neighbours and as a dead end by its exits, and once it
        # was blocked the route skipped it and the walk bounced through Mauville's side map for
        # the rest of the budget
        blocked = self._blocked_from(region) - {dest}
        moves = self.field_moves()
        self.graph.cur_badges = self.g.badges()
        route_hop = self.graph.route(here, dest, blocked, moves)
        if route_hop is None and self.goal.get("mode") == "travel":
            print(f"warn: no graph route {list(here)} -> {list(dest)} under moves {sorted(moves)} "
                  f"badges {self.graph.cur_badges}, falling to explore", flush=True)
        hop = route_hop or self.graph.explore_hop(here, blocked, moves)
        if hop is None and blocked:
            # a run-local block (the hop that led straight back here, an item detour that re-crossed
            # the border) never outranks the only graph route out of this map; retake it
            hop = self.graph.route(here, dest, field_moves=moves)
        if hop is None:
            # no graph route and nothing to explore: the only hop is blocked, a field-move gate on
            # the path (Dewford past water without Surf) or a run-local snag. End the run so the
            # supervisor re-plans instead of idling the whole budget with no status write, which
            # froze the frame. For a gym this also records it closed, so the ladder drops a gym the
            # party cannot reach now; once every reachable gym is demoted the planner explores, which
            # holds a capless grind at the gated frontier and keeps the stream up.
            if self.goal.get("mode") == "gym" and tuple(self.goal.get("map", ())) == dest:
                self.record_closed_gym(dest, "travel_stuck")
            raise GoalExit(f"travel stuck: no route from {list(here)} to {list(dest)}, re-planning")
        nxt = self.graph.route(hop, dest, field_moves=moves) if hop != dest else None
        print(f"hop: {list(here)} region {list(region[2:])} -> dest {list(dest)}: route {list(hop)} onward {nxt and list(nxt)}, blocked {sorted(list(b) for b in blocked)}", flush=True)
        self._after_cross(region, hop, self._cross_to(here, hop, nxt))

    def explore_step(self) -> None:
        here = self.g.position()[2:]
        moves = self.field_moves()
        self.graph.cur_badges = self.g.badges()
        region = self.region()
        hop = self.graph.explore_hop(here, self._blocked_from(region), moves)
        if hop is None:
            if self.graph.frontier_exhausted(moves) or self.graph.gated_frontier(moves):
                # no open border left to walk: try a dive off the cluster first. below 8 badges a
                # gated frontier falls to a wild-battle grind rather than idling against a gate the
                # walk cannot open. at 8 badges there is no gym left and the party is over cap 45, so
                # a gated frontier means the endgame route out is blocked and a grind earns nothing,
                # so halt on an unsupported reason the supervisor stops on instead of the walk back west
                if not self._dive_frontier(region, moves):
                    if self.g.badges() >= 8:
                        raise GoalExit(f"unsupported: endgame blocked at {list(here)}, no reachable frontier past the last badge")
                    self.demote_to_grind(here)
            else:
                # only this run's borders are blocked: an NPC in a doorway clears in a tick, a pocket
                # whose every exit bounced or dead-ended never does, so idle a few ticks for the
                # transient case then re-plan, relaunching off the snapshot with the run-local blocks
                # cleared instead of standing on run(60) for the rest of the budget
                self._idle += 1
                if self._idle >= IDLE_STREAK:
                    # the pocket the walk cannot leave is no place to resume from, so the state file
                    # keeps the last snapshot that preceded it
                    self.keep_state = True
                    raise GoalExit(f"explore stuck: {self._idle} idle ticks at {list(here)}, re-planning")
                self.run(60)
            return
        self._idle = 0
        self._after_cross(region, hop, self._cross_to(here, hop))

    def _reachable_grass_map(self, here: tuple) -> tuple | None:
        """Nearest map holding wild grass (a group-0 route numbered 16 or above) the walk can
        physically reach from where the party stands. The search seeds on the borders the live grid
        reaches now (`_landing_exits`), never the map's full adjacency, so a pocket entered by water
        that reaches only the border back (the surf pocket east of Slateport, whose adjacency also
        lists 0,26 and 0,32 the grid cannot walk to) grinds toward the reachable grass instead of
        stalling the grind against a neighbour it cannot cross. Underwater maps are skipped whole,
        candidate and traversal both: the seabed holds no grass, and the numbering that marks a grass
        route (num >= 16) also spans the seabed pockets off Sootopolis (0,50..0,52), which 24,5
        borders and the walk can swim to but which demote would then target as an unroutable grind,
        churning the supervisor. None when no reachable map holds grass, so the caller falls back to
        `here`."""
        moves = self.field_moves()
        seen = {here}
        q: collections.deque = collections.deque()
        for nb in self._landing_exits():
            if nb not in seen:
                seen.add(nb)
                q.append(nb)
        while q:
            node = q.popleft()
            if rowe_rom.is_underwater(*node):
                continue  # seabed holds no grass, and a grind never routes across it (the 24,5 bounce)
            if node[0] == 0 and node[1] >= 16:
                return node
            for nb in self.graph.neighbors(node):
                if self.graph.gated.get((node, nb)) == moves or nb in seen:
                    continue
                seen.add(nb)
                q.append(nb)
        return None

    def _dive_frontier(self, region: tuple, moves: frozenset) -> bool:
        """Submerge through a diveable tile to cross onto a cluster the ROM connection table never
        links. Dive Gear is a zero-badge item in ROWE, so a deep-water tile reaches the seabed the
        overworld edges omit (the route onto the Sootopolis island), and the next overworld_step
        observes the landing into adjacency. True when the dive moved the party; False when DIVE is
        off, this area's dive was already tried, or no diveable tile crossed. The region is marked
        before the attempt so a bounced dive fires once, never every explore tick."""
        if "DIVE" not in moves or region in self._dived:
            return False
        self._dived.add(region)
        return self.errands.take_dive(rowe_map.DIR_DIVE, surf="SURF" in moves, tools=moves) in ("map_changed", "battle")

    def demote_to_grind(self, here: tuple) -> None:
        """Reachable frontier is gated behind a field move, so hold the run on a wild-battle grind
        rather than idle in place; capless so it never raises the goal exit that would stop the
        supervisor and drop the stream. A grassless dead-end (the one-connection surf pocket off
        map 24) can never spawn a wild battle, so the grind routes to the nearest reachable grass
        map instead of idling the frame on a map that has none."""
        x, y, _, _ = self.g.position()
        grid = self._grid()
        reach = grid.reachable((x, y), "SURF" in self.field_moves())
        has_grass = any(t in reach for t in grid.tiles_with_id(TALL_GRASS_ID))
        target = here if has_grass else (self._reachable_grass_map(here) or here)
        self.goal = {"mode": "grind", "map": list(target), "cap": None}
        self._held = (len(self.graph.visited), len(self.graph.adj), frozenset(self.field_moves()), self.battles)
        if self.state_path:
            path = os.path.join(os.path.dirname(self.state_path), "goal.json")
            with open(path + ".tmp", "w") as f:
                json.dump(self.goal, f)
            os.replace(path + ".tmp", path)
        self.say(f"explore frontier gated at {list(here)}, grinding toward {list(target)}")

    def _grind_no_grass(self, here: tuple, x: int, y: int) -> None:
        """No grass reachable from the grind tile. A grid read mid-transition (menu closing, map
        reloading after a battle) shows nothing reachable for one step and settles on the next, so
        wait it out. A wait that outlasts every transient is a standing gap to the grass (Route 104
        north's flower-shop gate), and exiting names the map so the planner grinds elsewhere, unless
        every reachable map is grassless too (the Sootopolis gym floor held behind the thin-ice
        gate): there exiting re-plans straight back into the identical stall and churns the
        supervisor every GRASS_WAIT_TICKS, so the run holds the frame and keeps the stream up until a
        field route opens a grass map or GRASS_IDLE_CAP passes, when it exits no_grass_idle so the
        supervisor can stop a map that never opens."""
        self.grass_waits += 1
        if self.grass_waits >= GRASS_WAIT_TICKS:
            if self._reachable_grass_map(here) is None:
                self.grass_waits = 0
                if self.grass_idle_since is None:
                    self.grass_idle_since = time.monotonic()
                elif time.monotonic() - self.grass_idle_since >= GRASS_IDLE_CAP:
                    raise GoalExit("no_grass_idle")
                print(f"grind held: no reachable grass anywhere from {list(here)}, idling", flush=True)
                self.run(60)
                return
            raise GoalExit(f"grind blocked: no reachable grass on {list(here)} from {(x, y)}")
        print(f"grind: no reachable grass on {list(here)} from {(x, y)}, waiting", flush=True)
        self.run(60)

    def collectable_balls(self) -> list:
        """Uncollected item balls on this map the grid can reach a side of, nearest first,
        skipping any whose pickup already failed this run and any with no collected flag."""
        x, y, group, num = self.g.position()
        here = (group, num)
        surf = "SURF" in self.field_moves()
        reach = self._grid().reachable((x, y), surf)
        out = []
        for bx, by, flag in rowe_map.item_balls(self.e):
            if not flag or self.g.flag(flag) or (here, bx, by) in self._item_skip:
                continue
            if any((bx + dx, by + dy) in reach for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0))):
                out.append((bx, by, flag))
        out.sort(key=lambda b: abs(b[0] - x) + abs(b[1] - y))
        return out

    def collect_step(self) -> bool:
        """Detour to the nearest reachable uncollected item ball and pick it up, so the goal
        resumes next step. False when none is reachable, leaving the goal to run this step. A
        ball whose pickup does not flip its flag (a side that would not open, a press that took
        nothing) is skipped for the rest of the run so the detour cannot loop on it; a wild
        battle on the way is no verdict on the ball, so the next step walks at it again (Route
        121's three balls were each skipped after one interrupted walk and left on the ground)."""
        balls = self.collectable_balls()
        if not balls:
            return False
        here = self.g.position()[2:]
        bx, by, flag = balls[0]
        r = self.errands.collect_item((bx, by), "SURF" in self.field_moves())
        got = self.g.flag(flag)
        if not got and r != "battle":
            self._item_skip.add((here, bx, by))
        print(f"item: ball {(bx, by)} on {list(here)} -> {r}, collected {got}", flush=True)
        return True

    def overworld_step(self, i: int) -> None:
        x, y, group, num = self.g.position()
        here = (group, num)
        if self.graph is not None and here != self._last_obs:
            new = self.graph.observe(here, [(c.group, c.num) for c in rowe_map.connections(self.e)])
            self._last_obs = here
            if new:
                print(f"map: {list(here)} borders {[list(n) for n in sorted(self.graph.adj[here])]}, {len(self.graph.visited)} maps seen", flush=True)
        slot = self.lowest_lead()
        if slot is not None and not self.need_heal and self.swap_failures < 3:
            ok = self.errands.lead_with(slot)
            self.swap_failures = 0 if ok else self.swap_failures + 1
            print(f"lead swap -> slot {slot}: {ok}", flush=True)
            return
        if not self.need_heal and self.top_off_due(self.g.party()) and here in SERVICE_MAPS[self.service_town(here)]:
            self.need_heal = True
        # a short party is a Center trip from anywhere; the boxes read only runs on the short party
        if not self.need_heal and len(self.g.party()) < PARTY_SIZE and party_short(len(self.g.party()), len(self.g.boxes())):
            print(f"party {len(self.g.party())}/{PARTY_SIZE} w/ a boxed mon, Center trip to refill", flush=True)
            self.need_heal = True
        if not self.need_heal and self.state_path and os.path.exists(self.state_file("swap_order.json")):
            print("swap order on file, Center trip to run it", flush=True)
            self.need_heal = True
        in_goal_gym = self.goal.get("mode") == "gym" and here == tuple(self.goal.get("map", ()))
        if self.need_heal and in_goal_gym:
            # the gym's inner rooms have no walking path back to its exit, so a heal trip from
            # one jams on the warp; the leader fight runs on what is left, and a whiteout heals
            # at the Center and the sweep re-takes the open doors from the entrance
            self.need_heal = False
        if self.need_heal:
            town = self.service_town(here)
            if here not in SERVICE_MAPS[town]:
                self.travel_toward(town)
                return
            r = self.errands.heal_at(town, SERVICE[town][0], after_heal=self.after_heal, surf="SURF" in self.field_moves())
            print(f"heal run -> {r} at {self.g.position()}", flush=True)
            if r == "healed":
                self.need_heal = False
                return
            if r == "battle":
                return
            # Center warp unreachable from this tile (a surfed-into town pond, door off the
            # water): hold need_heal and fall through to normal nav so the player moves off this
            # spot instead of re-running the same blocked warp every step
        if self.shopping:
            town = self.service_town(here)
            if here in SERVICE_MAPS[town]:
                bought = self.errands.restock_at(town, SERVICE[town][1], self.shopping, surf="SURF" in self.field_moves(), downgrade=HP_TIERS)
                print(f"restock -> {bought} at {self.g.position()}", flush=True)
                if bought == "battle":
                    return
                if bought is not None:
                    self.shopping = []
                    self.mart_trek = False
                    return
                # the Mart warp is unreachable from this tile: stop the trek and fall through to
                # normal nav so the player moves off the spot instead of re-running the blocked warp
                self.mart_trek = False
            if self.mart_trek:
                self.travel_toward(town)
                return
        if self.collect_step():
            return
        if self.goal.get("mode") == "travel":
            self.travel_toward(tuple(self.goal.get("to", ())))
            return
        if self.goal.get("mode") in ("explore", "sevii"):
            self.explore_step()
            return
        if self.goal.get("mode") == "gym":
            self.gym_step()
            return
        goal_map = tuple(self.goal.get("map", ROUTE_101))
        if (group, num) == OLDALE and goal_map == ROUTE_101:
            print(f"back to route 101 -> {self.errands.back_to_route_101()}", flush=True)
            return
        if (group, num) == LITTLEROOT:
            print(f"north out of Littleroot -> {self.errands.cross_edge(rowe_map.DIR_NORTH)}", flush=True)
            return
        for town, rooms in SERVICE.items():
            if (group, num) in rooms:
                self.dismiss_text()
                print(f"leave building {(group, num)} -> {self.errands.leave_by_warp(town)}", flush=True)
                return
        if (group, num) != goal_map:
            # off the grind map after a heal or restock trip: walk the corridor back
            self.travel_toward(goal_map)
            return
        # the hop that brought the walk here worked; a PACE key stepping back over the border
        # must not read as a dead door and retire the route from the town
        self._last_hop = None
        grid = self._grid()
        # only grass this walkable area reaches: Route 104 holds grass on both sides of the
        # Woods, and a pick across the split fails walk_to, then a PACE key at the border
        # steps back into town and retires the route's own hop
        # surf counts, since a walk that crossed water leaves the player on a tile at the
        # water height, where every land tile fails the height match and no grass is reachable
        surf = "SURF" in self.field_moves()
        # one flood fill, then the membership test: the fill inside the comprehension ran once per
        # grass tile, 130 fills on Route 102, and the stream held a frozen frame for the whole pick
        reach = grid.reachable((x, y), surf)
        grass = [t for t in grid.tiles_with_id(TALL_GRASS_ID) if t in reach]
        if not grass:
            self._grind_no_grass(here, x, y)
            return
        self.grass_waits = 0
        self.grass_idle_since = None
        goal = self.rng.choice(grass)
        r = self.nav.walk_to(goal, surf)
        if r not in ("arrived", "battle"):
            print(f"walk_to {goal} -> {r} from {(x, y)}", flush=True)
            self.dismiss_text()
            self.run(20, PACE[i % len(PACE)])
            self.run(4)

    def gym_step(self) -> None:
        """Inside the gym walk at the leader and talk; the trainers on the way interrupt with
        fights the battle loop takes, and check_goal exits once the badge flag flips."""
        gym = tuple(self.goal["map"])
        gym_maps = gym_map_set(gym)
        here = self.g.position()[2:]
        if here not in gym_maps:
            self.travel_toward(gym)
            return
        done = self._gym_done.setdefault(gym, set())
        if here != gym:
            drop = ICE_FALL_FLOOR.get(gym)
            if drop is not None and here == drop:
                # a second step on a cracked ice tile dropped the party to the lower floor; take the
                # ladder back up and walk to the door so follow_route re-runs the cover on fresh ice
                r = self.errands.take_warp(gym)
                print(f"gym: ice fall {here} climb -> {r} at {self.g.position()}", flush=True)
                if r == "battle":
                    return
                if self.g.position()[2:] == gym:
                    self.nav.walk_to(ICE_DOOR_TILE[gym])
                return
            # on an interior floor below the leader's (Lavaridge's B1F, [4, 2]): no leader object
            # on this map. A recorded maze route resumes here by (floor, tile) and climbs the holes
            # back to the leader's floor; failing that the sweep takes the stairs and holes blindly,
            # and a floor with no trainer, switch or untried intra-gym warp left closes the gym.
            route = GYM_ROUTES.get(gym)
            if route:
                r = self.errands.follow_route(route)
                print(f"gym: route -> {r} at {self.g.position()[:2]}", flush=True)
                if r == "battle":
                    return
                if r == "arrived":
                    here = self.g.position()[2:]  # back on the leader's floor, challenge below
                else:
                    self.dismiss_text()
                    return
            if here != gym:
                r = self.errands.gym_sweep(self.gym_stand(), done, gym_maps)
                print(f"gym: sweep -> {r} at {self.g.position()[:2]}, {len(done)} done", flush=True)
                if r == "battle":
                    return
                if r == "exhausted":
                    self.record_closed_gym(gym, "unreachable")
                    raise GoalExit(f"gym not clearable at badge {self.g.badges()}: {list(gym)} (unreachable)")
                self.dismiss_text()
                return
        stand = self.gym_stand()
        route = GYM_ROUTES.get(gym)
        if route:
            r = self.errands.follow_route(route)
            print(f"gym: route -> {r} at {self.g.position()[:2]}", flush=True)
            if r == "battle":
                return
            if r == "off_route" and self._route_resets.get(gym, 0) < ROUTE_RESETS:
                # the recorded states hold gate orientations, and the game resets those only
                # through the door (RotatingGate_InitPuzzle runs from the gym's map script on
                # entry); the sweep turns gates at random and never lands back on a recorded
                # state, so the way back onto the route is out and in again
                self._route_resets[gym] = self._route_resets.get(gym, 0) + 1
                exits = self.graph.world.get(gym, set()) - {gym}
                if exits:
                    out = min(exits)
                    r = self.errands.descend_gym(out)
                    print(f"gym: route reset {self._route_resets[gym]}/{ROUTE_RESETS}, out to {list(out)} -> {r}", flush=True)
                    return
        r = self.errands.challenge_leader(stand)
        print(f"gym: leader -> {r} at {self.g.position()[:2]} stand {stand}", flush=True)
        if r == "unreachable":
            # no walking path to the leader yet, which every gym past the first presents on entry:
            # Mauville's gates open from its floor switches, Petalburg is rooms linked by doors, and
            # a trainer standing in a one-tile gap blocks Rustboro's aisle. Fight the trainers in
            # reach, stand on the switches and take the gym's own doors one per step, re-trying the
            # leader each time.
            r = self.errands.gym_sweep(stand, done, gym_maps)
            print(f"gym: sweep -> {r} at {self.g.position()[:2]}, {len(done)} done", flush=True)
            if r == "battle":
                return
            if r != "exhausted":
                self.dismiss_text()
                return
            r = "unreachable"
        if r not in ("battle", "arrived"):
            self.dismiss_text()
        if r == "talked":
            # the leader's speech after the fight sets the badge flag, later than the
            # post-battle check_goal, so a dialog that ran out re-reads it here
            self.check_goal()
        if r in ("talked", "unreachable"):
            # talked: the dialog ran out with no fight, the gym is shut at this badge. unreachable:
            # every trainer in reach is fought and every door taken and the stand still has no
            # path. Neither clears the gym now, so record it closed and end the run; the re-plan
            # routes to the next gym instead of re-walking the same dead path every loop.
            self.record_closed_gym(gym, r)
            raise GoalExit(f"gym not clearable at badge {self.g.badges()}: {list(gym)} ({r})")

    def gym_stand(self) -> tuple:
        """Tile below the leader. The planner pre-seeds only Roxanne's; every other stand is the
        tile under the northmost object read on entry, where a leader stands facing the door."""
        if self.goal.get("stand"):
            return tuple(self.goal["stand"])
        objs = rowe_map.static_objects(self.e)
        if not objs:
            return self.g.position()[:2]
        leader = min(objs, key=lambda o: o[1])
        return (leader[0], leader[1] + 1)

    def _close_signature(self, gym: tuple, reason: str) -> dict:
        """The run state a closed gym is measured against to decide when to retry it. A lost fight
        reopens once the party out-levels this, an unreachable gym once the map graph outgrows this
        map count; a new field move reopens either."""
        party = self.g.party()
        return {
            "gym": list(gym), "reason": reason,
            "min_level": min((m.level for m in party), default=0),
            "field_moves": sorted(self.field_moves()),
            "maps": len(self.graph.visited) if self.graph is not None else 0,
        }

    def record_closed_gym(self, gym: tuple, reason: str) -> None:
        path = os.path.join(os.path.dirname(self.state_path), "gym_closed.json")
        entries = {}
        if os.path.exists(path):
            with open(path) as f:
                for e in json.load(f):
                    key = tuple(e["gym"]) if isinstance(e, dict) else tuple(e)
                    entries[key] = e if isinstance(e, dict) else {"gym": list(key)}
        entries[tuple(gym)] = self._close_signature(gym, reason)
        with open(path + ".tmp", "w") as f:
            json.dump(list(entries.values()), f)
        os.replace(path + ".tmp", path)

    def record_gym_loss(self, gym: tuple) -> int:
        """Increment and persist this gym's whiteout count, returning the new total."""
        path = os.path.join(os.path.dirname(self.state_path), "gym_losses.json")
        losses = {}
        if os.path.exists(path):
            with open(path) as f:
                losses = {tuple(k): v for k, v in json.load(f)}
        gym = tuple(gym)
        losses[gym] = losses.get(gym, 0) + 1
        with open(path + ".tmp", "w") as f:
            json.dump(sorted([list(k), v] for k, v in losses.items()), f)
        os.replace(path + ".tmp", path)
        return losses[gym]

    def note_gym_loss(self, outcome: int) -> None:
        """A lost or drawn fight faints the party out to the last Center with half the money gone.
        When the objective was a gym, tally the loss, since the whiteout warps the player off the
        gym and the gym goal would otherwise walk back and re-fight the same team until the budget
        ran out. The after_heal swap already runs on the Center trip the whiteout forces; after
        GYM_LOSS_CAP losses the gym is recorded closed so the ladder routes past it."""
        if outcome not in (OUTCOME_LOST, OUTCOME_DREW) or self.goal.get("mode") != "gym":
            return
        gym = tuple(self.goal.get("map", ()))
        if not gym:
            return
        n = self.record_gym_loss(gym)
        self.say(f"whiteout vs gym {list(gym)}, loss {n}")
        if n >= GYM_LOSS_CAP:
            self.record_closed_gym(gym, "loss")
            self.say(f"gym {list(gym)} closed after {n} losses, demoting on the ladder")

    def dismiss_text(self) -> None:
        """Close a leftover text box ("The Pokémon got away!") that blocks walking."""
        for _ in range(2):
            self.tap(eb.KEY_B)
            self.run(20)

    def loop(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        i = 0
        in_battle = False
        streak = 0
        last_ow = None
        ow_stall = 0
        # SIGINT lands inside libmgba's cffi callbacks and gets swallowed there,
        # so a stop request is a flag the loop polls between steps
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "stop", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "stop", True))
        if self.state_path:
            states_dir = os.path.dirname(self.state_path)
            self.goal = read_goal(os.path.join(states_dir, "goal.json"))
            self.graph = map_graph.MapGraph(os.path.join(states_dir, "map_graph.json"),
                                            world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs(),
                                            script=script_decode.script_edges(), flags=self._graph_flags())
            self._stuck_hits = self._load_stuck_hits(os.path.join(states_dir, "stuck_hits.json"))
        # points accrue at trainer-level milestones and the supervisor relaunches often enough
        # that a launch-time spend keeps them from piling up unspent; once per process, since
        # every in-process replan re-enters here and the menu trip w/ nothing to buy is a stall
        if not self._skills_spent and not self.g.in_battle():
            self.errands.spend_skill_points()
            self._skills_spent = True
        while time.monotonic() < end and not self.stop:
            if self.state_path:
                # the site holds each row until the stream frame it belongs to has played, so a
                # row's ts has to be the moment the party changed, not the next 15s tick: a write
                # on every HP, exp, pp or roster change inside a fight keeps the overlay on the
                # frame, the periodic write covers a long walk w/ nothing changing
                sig = tuple((m.species, m.level, m.hp, m.experience, m.pp) for m in self.g.party())
                since = time.monotonic() - self.last_status
                if since > STATUS_SECONDS or (sig != self._status_sig and since > 0.5):
                    self._status_sig = sig
                    self.write_status()
            if self.g.in_battle():
                if not in_battle:
                    in_battle = True
                    self.battles += 1
                    print(f"battle {self.battles}: {[f'{m.nickname} L{m.level}' for m in self.g.battlers()[1::2]]}", flush=True)
                    streak = 0
                    self._wedge = 0
                    self._wedge_sig = None
                    self._switch_active = None  # new battle, let this battle's lead try a switch
                    self._wild_switched = False
                    self._start_items = {}
                    self._avoid_slots = set()
                    self._freezes = 0
                self.battle_step()
                streak = self.stall_check(self.battle_signature(), streak)
            else:
                if in_battle:
                    in_battle = False
                    outcome = self.g.battle_outcome()
                    if outcome == 1:
                        self.wins += 1
                    elif outcome == OUTCOME_CAUGHT:
                        # a full party sends the catch to the PC, so the foe at throw time is the record
                        self.caught += 1
                        self.ledger.record(self.target.species)
                        print(f"CAUGHT {self.target.nickname} L{self.target.level}, party {len(self.g.party())}, balls {self.g.poke_balls()}", flush=True)
                    else:
                        self.note_gym_loss(outcome)
                    balls = dict(self.g.poke_balls()).get(catch.POKE_BALL, 0)
                    party = self.g.party()
                    self.shopping = shopping_list(self.g.money(), balls, self.g.medicine(), party)
                    # a counter trip on its own only for an empty ball pocket w/ a party to fill;
                    # everything else is bought when a heal run or the route already passes a town
                    self.mart_trek = bool(self.shopping) and balls == 0 and len(party) < PARTY_SIZE
                    low = [m for m in party if m.hp * 100 < m.max_hp * HEAL_HP_PERCENT]
                    # two mons under the heal line is a Center trip on its own; one is worth it when
                    # the Mart next door is the destination anyway
                    center_trip = len(low) >= 2 or (low and self.shopping) or self._retreat_warranted(party)
                    mon = party[0]
                    ferry = " ".join(f"{f:03X}:{int(self.g.flag(f))}" for f in FERRY_FLAGS)
                    self.say(f"{self.wins}/{self.battles} won, {self.caught} caught, {mon.nickname} L{mon.level} {mon.hp}/{mon.max_hp} exp {mon.experience}, balls {balls}, badges {self.g.badges()}, map {self.g.position()[2:]}, ferry {ferry}")
                    self.dismiss_text()
                    if center_trip:
                        # the bag's HP items cover the bench first, so the Center trip only fires
                        # when nothing in the Medicine pocket helps (or a mon fainted and needs a Revive)
                        self.heal_bench_from_bag()
                        low = [m for m in self.g.party() if m.hp * 100 < m.max_hp * HEAL_HP_PERCENT]
                        if len(low) >= 2 or (low and self.shopping) or self._retreat_warranted(self.g.party()):
                            self.need_heal = True
                    # NPCs wandered through the battle, so an edge they plugged may be open
                    self._stuck.clear()
                    if self.state_path:
                        if time.monotonic() - self.last_snapshot > SNAPSHOT_SECONDS:
                            self.snapshot(self.state_path)
                            self.say(f"snapshot -> {self.state_path}")
                        self.write_status()
                        self.check_goal()
                pos = self.g.position()
                ow_stall = ow_stall + 1 if pos == last_ow else 0
                last_ow = pos
                if 1 <= ow_stall <= 5:
                    # a forced text box (a trainer's challenge or defeat line, an NPC) stalls
                    # movement with in_battle false; B advances it toward the battle or frees
                    # the tile, firing on each stalled step so a multi-box dialogue clears at
                    # reading speed instead of waiting out the counter
                    self.tap(eb.KEY_B)
                    if self.g.in_battle():
                        continue
                elif ow_stall >= 6:
                    # B did not free it: an NPC plug or a wedged walk. Forget the stuck
                    # edges and pace a tile so the next plan starts from a new spot
                    self._stuck.clear()
                    self.run(20, PACE[i % len(PACE)])
                    ow_stall = 0
                self.overworld_step(i)
                i += 1


def drive(player: Player, seconds: float) -> None:
    """Run the loop for the budget, re-planning in-process on every GoalExit that replan() accepts,
    so the emulator and the stream run on through a goal change; a process exit here cost the
    viewer a gap every time the planner moved the party on. Raises GoalExit for the exits replan()
    hands to the supervisor and sets exit_reason "timer" on a budget that runs out."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            player.loop(deadline - time.monotonic())
            player.exit_reason = "timer"
            return
        except GoalExit as g:
            player.exit_reason = str(g)
            print(f"goal exit: {g}", flush=True)
            if not player.replan():
                raise


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=rowe_live.LIVE_SAVE)
    ap.add_argument("--minutes", type=float, default=120)
    ap.add_argument("--no-stream", action="store_true")
    a = ap.parse_args()
    rowe_rom.self_check()
    emu = eb.Emu()
    with open(a.state, "rb") as f:
        emu.load_state(f.read())
    streamer = NullStreamer() if a.no_stream else FrameStreamer(emu.core)
    player = Player(emu, streamer, ledger_path=a.state + ".caught.json")
    player.state_path = a.state
    player._live_writer = rowe_live.is_live_target(a.state)
    try:
        drive(player, a.minutes * 60)
    except StopRequested:
        player.exit_reason = "stall" if player.stalled else "signal"
    except GoalExit as g:
        player.exit_reason = str(g)
    except Exception:
        # a crash lands wherever the loop was, often a menu or the PC; keep the last responsive
        # snapshot rather than save the wedged frame, or the same exception repeats every relaunch
        player.keep_state = True
        player.exit_reason = "crash"
        raise
    finally:
        # never persist a mid-battle frame as the resume point: a timer exit inside a battle saves
        # that battle, and a battle that then softlocks replays on every relaunch, the loop the
        # stream was stuck in. the loop's own post-battle overworld snapshot is the resume state; a
        # stall, a signal, or a short party likewise keeps the last good one.
        keep = (player.stalled or player.keep_state or player.g.in_battle()
                or keep_snapshot(player.exit_reason, len(player.g.party()), len(player.g.boxes())))
        if not keep:
            player.snapshot(a.state)
        player.write_status()
        streamer.close()
        print(f"stopped: {player.wins}/{player.battles} won, {player.caught} caught, state {'kept' if keep else 'written'}, exit {player.exit_reason}", flush=True)


if __name__ == "__main__":
    main()
