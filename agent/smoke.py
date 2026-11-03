"""Offline deploy gate for the ROWE agent.

Boots frozen savestate fixtures and asserts the nav and battle behaviors a
promotion to the live streamer must not regress. Green is the bar before
swapping rowe-agent into the streaming process; a red check blocks the swap.
Fixtures sit under states/fixtures because the live states/*.ss are rewritten
by the running supervisor on every run and cannot be test inputs.
"""
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import emu_boot as eb  # noqa: E402
import rowe_map  # noqa: E402
from rowe_state import GameState  # noqa: E402

FIX = os.path.join(HERE, "states", "fixtures")
POISON_STING = 40  # the move Disable locked in battle_disabled.ss
PIDGEY, PIDGEOTTO = 16, 17
LEARN_PROMPT = 0x839640F  # gBattlescriptCurrInstr at "Delete a move to make room for X?"
SWALLOW, POISON_GAS, RECYCLE, ACID_SPRAY, CLEAR_SMOG, TAKE_DOWN = 256, 139, 278, 491, 499, 36

CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def _load(name):
    e = eb.Emu()
    with open(os.path.join(FIX, name), "rb") as f:
        e.load_state(f.read())
    return e


def _cross(name, direction):
    from routines import Errands
    e = _load(name)
    before = GameState(e).position()[2:]
    Errands(e, e.run).cross_edge(direction)
    return before, GameState(e).position()[2:]


@check
def nav_petalburg_west_to_route104():
    # the edge that strict-elevation nav sealed; must cross after the wildcard fix
    assert _cross("petalburg.ss", rowe_map.DIR_WEST) == ((0, 0), (0, 19))


@check
def nav_petalburg_east_to_route102():
    # a known-good crossing that must still work after any nav change
    assert _cross("petalburg.ss", rowe_map.DIR_EAST) == ((0, 0), (0, 17))


@check
def nav_surf_crosses_route104_water():
    # Route 104 water (metatile 368) is elevation 1 vs the player's land elevation 3, so
    # it is unreachable on foot; Surf must open a path onto it and leave foot nav blocked
    from nav import Grid
    e = _load("route104.ss")
    x, y, *_ = GameState(e).position()
    g = Grid(e)
    water = sorted(g.tiles_with_id(368), key=lambda t: abs(t[0] - x) + abs(t[1] - y))
    assert water, "route104 fixture has no water at metatile 368"
    near = water[:20]
    assert not any(g.path((x, y), w, surf=False) for w in near), "water reachable on foot"
    assert any(g.path((x, y), w, surf=True) for w in near), "surf opened no path to water"


@check
def nav_region_splits_route104_at_the_water():
    # the south shore and a water tile share one map; on foot they are two regions, w/ Surf one
    from nav import Grid
    e = _load("route104.ss")
    x, y, *_ = GameState(e).position()
    g = Grid(e)
    near = sorted(g.tiles_with_id(368), key=lambda t: abs(t[0] - x) + abs(t[1] - y))[:20]
    water = next(w for w in near if g.path((x, y), w, surf=True))
    assert g.region((x, y)) != g.region(water), "foot region spans the water"
    assert g.region((x, y), surf=True) == g.region(water, surf=True), "surf region does not join shore and water"


@check
def rom_map_reader_classifies_oldale_facilities():
    # the static ROM reader must know a town's Center and Mart without visiting them;
    # Oldale is the control, PC at (2,2) and Mart at (2,4), both warp targets of town (0,10)
    import rowe_rom as rr
    assert rr.is_center(2, 2), "Oldale PC (2,2) not read as a Center"
    assert rr.is_mart(2, 4), "Oldale Mart (2,4) not read as a Mart"
    assert not rr.is_center(0, 10), "Oldale town misread as a Center"
    dests = {d for *_, d in rr.map_warps(0, 10)}
    assert {(2, 2), (2, 4)} <= dests, f"Oldale warps miss its Center/Mart: {sorted(dests)}"


@check
def service_table_comes_off_the_rom_for_every_town():
    # Oldale and Rustboro are the controls, the pairs the loop was first wired w/ by hand;
    # Petalburg is the town a Route 102 or Route 104 grind should be served from
    import play
    assert play.SERVICE[(0, 10)] == ((2, 2), (2, 4)), f"Oldale: {play.SERVICE.get((0, 10))}"
    assert play.SERVICE[(0, 3)] == ((11, 5), (11, 7)), f"Rustboro: {play.SERVICE.get((0, 3))}"
    assert play.SERVICE[(0, 0)] == ((8, 4), (8, 6)), f"Petalburg: {play.SERVICE.get((0, 0))}"
    assert (0, 17) not in play.SERVICE_MAPS[(0, 10)], "Route 102 still pinned to Oldale"


@check
def service_town_tie_goes_to_the_nearer_border():
    # Route 104 is 55x94 w/ Rustboro off the north edge and Petalburg off the east; both are
    # one hop, so the walk across the route decides
    import play
    conns = [(2, (0, 3)), (1, (0, 20)), (4, (0, 0))]
    assert play.nearer_border([(0, 0), (0, 3)], (39, 69), (55, 94), conns) == (0, 0), "south half should go to Petalburg"
    assert play.nearer_border([(0, 0), (0, 3)], (39, 5), (55, 94), conns) == (0, 3), "north half should go to Rustboro"


@check
def unreachable_heal_run_moves_on_instead_of_freezing():
    # the lead drops under the heal threshold while surfing a town pond whose Center door is off
    # the water, so heal_at returns "unreachable" every step; the loop must fall through to normal
    # nav and move, not re-run the blocked warp forever (the live stream froze on exactly this)
    import play
    e = _load("route104.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    here = ex.g.position()[2:]
    calls = []
    ex.errands.heal_at = lambda *a, **k: (calls.append("heal"), "unreachable")[1]
    ex.errands.restock_at = lambda *a, **k: (calls.append("restock"), {})[1]
    ex.need_heal = True
    ex.shopping = [(4, 10)]
    saved = play.SERVICE, play.SERVICE_MAPS
    play.SERVICE = {here: ((0, 0), (0, 0))}
    play.SERVICE_MAPS = {here: frozenset({here})}
    try:
        ex.overworld_step(0)
    finally:
        play.SERVICE, play.SERVICE_MAPS = saved
    assert "heal" in calls, "heal run was not attempted"
    assert "restock" in calls, "the unreachable heal run returned early and froze the step"


@check
def in_town_tops_off_without_a_retreat_trigger():
    # a chipped bench mon behind a healthy lead: the retreat thresholds do not set need_heal, but
    # the party stands in a service town where the Center is free, so the step must route into it
    import play, rowe_rom
    atk = next(mid for mid in range(1, 600) if rowe_rom.move(mid).power >= 10)

    class M:
        def __init__(self, slot, hp, mx):
            self.slot, self.hp, self.max_hp, self.level = slot, hp, mx, 20
            self.moves, self.pp = [atk], [10]

    party = [M(0, 60, 60), M(1, 30, 50), M(2, 40, 40)]
    e = _load("route104.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    ex.g.party = lambda: party
    here = ex.g.position()[2:]
    calls = []
    ex.errands.heal_at = lambda *a, **k: (calls.append("heal"), "healed")[1]
    ex.need_heal = False
    saved = play.SERVICE, play.SERVICE_MAPS
    play.SERVICE = {here: ((0, 0), (0, 0))}
    play.SERVICE_MAPS = {here: frozenset({here})}
    try:
        ex.overworld_step(0)
    finally:
        play.SERVICE, play.SERVICE_MAPS = saved
    assert "heal" in calls, "a chipped party standing in a service town walked past the free Center"


@check
def battle_never_picks_disabled_move():
    import play
    e = _load("battle_disabled.ss")
    ex = play.Player(e, play.NullStreamer())
    assert ex.g.disabled_move(0) == POISON_STING, "fixture lost its disabled move"
    _, me, foes = ex.sides()
    assert me.moves[ex.pick_move(me, foes)] != POISON_STING, "picked the disabled move"


@check
def battle_lets_evolution_finish():
    # evolution.ss is the first frame of "What? Pidgey is evolving!" after a staged level-up;
    # the unstick B that used to fire four steps in cancelled it and left species 16 at L22
    import play
    e = _load("evolution.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    assert ex.g.callback2() == play.CB2_EVOLUTION, "fixture is not at the evolution scene"
    assert ex.g.party()[0].species == PIDGEY, "fixture lead is not Pidgey"
    for _ in range(300):
        if not ex.g.in_battle():
            break
        ex.battle_step()
    assert not ex.g.in_battle(), "battle never resolved after the evolution scene"
    assert ex.g.party()[0].species == PIDGEOTTO, f"evolution cancelled, species {ex.g.party()[0].species}"


@check
def battle_closes_the_nickname_keyboard():
    # nickname.ss is the keyboard after a Yes reached "Give a nickname?"; B there only deletes
    # a letter, so the old prompt branch sat on it until the stall limit
    import play
    e = _load("nickname.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    assert ex.g.callback2() == play.CB2_NAMING, "fixture is not on the naming screen"
    for _ in range(120):
        if not ex.g.in_battle():
            break
        ex.battle_step()
    assert not ex.g.in_battle(), f"battle never resolved off the keyboard, cb2 {ex.g.callback2():#x}"


@check
def battle_learns_the_better_moves():
    # learnmove.ss is the "Delete a move to make room for Clear Smog?" box for Trubbish (slot 4)
    # at L24, with Take Down offered next at the same level; the old prompt branch declined both.
    # Clear Smog (50, STAB) outranks Swallow (status) and Take Down (90 x 0.85) outranks Poison Gas
    import play
    e = _load("learnmove.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    assert ex.g.script_instr() == LEARN_PROMPT, "fixture is not at the learn prompt"
    assert ex.g.party()[4].moves == (SWALLOW, POISON_GAS, RECYCLE, ACID_SPRAY), "fixture Trubbish moveset changed"
    for _ in range(400):
        if not ex.g.in_battle():
            break
        ex.battle_step()
    assert not ex.g.in_battle(), "battle never resolved past the learn prompts"
    assert ex.g.party()[4].moves == (CLEAR_SMOG, TAKE_DOWN, RECYCLE, ACID_SPRAY), f"moves after learning: {ex.g.party()[4].moves}"


@check
def battle_decides_under_the_alt_action_menu():
    # trainer_altmenu.ss is a live stall dump of a [4, 2] trainer fight whose player action menu
    # runs through controller func 0x84F5D40 for the whole battle, never 0x83C12BC. Gating the
    # decision on the single func skipped every choice there and blind-A-mashed the move cursor
    # parked on Dig (0 PP left), so the fight never resolved and the supervisor relaunched the
    # same wedge forever. Pawmot KOs Turtonator with Supercell Slam once the gate lets it act.
    import play
    import rowe_symbols as S
    e = _load("trainer_altmenu.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    assert ex.g.in_battle(), "fixture is not in battle"
    ctrl = ex.e.u32(S.BATTLER0_CONTROLLER_FUNC)
    assert ctrl == S.PLAYER_CHOOSE_ACTION_ALT, f"fixture action func changed, ctrl {ctrl:#x}"
    assert ctrl != S.PLAYER_CHOOSE_ACTION, "fixture no longer exercises the alt func"
    for _ in range(80):
        if not ex.g.in_battle():
            break
        ex.battle_step()
    assert not ex.g.in_battle(), "battle never resolved under the alt action menu"


@check
def battle_wedge_bails_fast_and_live_battles_do_not():
    # battle_wedge.ss is a live dump of a trainer fight frozen on the Shelmet->Spinda switch-in:
    # the controller func, battlescript instr, cb2 and HP/PP all hold across steps and no button
    # moves it, so the run burned ~88s of "clearing submenu" before the 60-step STALL. The wedge
    # bail stops it in WEDGE_STEPS. The live fixtures run a battle to a finish without tripping it,
    # which is what keeps a long animation from being read as a freeze.
    import play
    from play import StopRequested, WEDGE_STEPS

    def run(name, steps):
        e = _load(name)
        ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
        ex._wedge, ex._wedge_sig = 0, None
        for n in range(1, steps + 1):
            if not ex.g.in_battle():
                return False, n
            try:
                ex.battle_step()
            except StopRequested:
                return ex.stalled, n
        return False, steps

    bailed, n = run("battle_wedge.ss", 120)
    assert bailed, "wedged battle never bailed"
    assert n <= WEDGE_STEPS + 2, f"bail took {n} steps, past WEDGE_STEPS {WEDGE_STEPS}"
    for name, steps in [("trainer_altmenu.ss", 90), ("roxanne.ss", 120), ("battle_disabled.ss", 40)]:
        bailed, _ = run(name, steps)
        assert not bailed, f"{name} false-tripped the wedge bail"


@check
def battle_forced_switch_sends_out_a_mon_with_hp():
    # party_menu.ss is the forced switch after Flechinder fainted in the Rustboro gym, cursor
    # on Flechinder; the old branch pressed A into "no energy left to battle!" until the stall
    import play
    e = _load("party_menu.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    assert ex.g.callback2() in play.CB2_PARTY_MENU, "fixture is not on the party menu"
    assert ex.g.battlers()[0].hp == 0, "fixture battler still has HP"
    for _ in range(12):
        ex.battle_step()
        if ex.g.callback2() not in play.CB2_PARTY_MENU and ex.g.battlers()[0].hp > 0:
            break
    assert ex.g.battlers()[0].hp > 0, f"no fresh mon sent out, cb2 {ex.g.callback2():#x}"


@check
def battle_party_menu_drops_a_switch_for_the_mon_already_out():
    # every switch swaps two party slots, so a slot planned before one resolved named the mon
    # just recalled and two mons cycled through the menu w/ no damage dealt
    import play
    e = _load("battle_disabled.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    active = ex.g.battlers()[0]
    ex.switch_to = active.nickname
    # the fixture sits in the move menu; B backs out to the action menu, where it is a no-op
    ex.tap(eb.KEY_B)
    ex.run(30)
    ex.tap(eb.KEY_DOWN)
    ex.tap(eb.KEY_A)
    for _ in range(6):
        ex.run(30)
        if ex.g.callback2() in play.CB2_PARTY_MENU:
            break
    assert ex.g.callback2() in play.CB2_PARTY_MENU, f"Pokémon did not open the party menu, cb2 {ex.g.callback2():#x}"
    ex.party_menu_step()
    assert ex.g.callback2() not in play.CB2_PARTY_MENU, "party menu still open after a switch naming the active mon"
    assert ex.g.battlers()[0].nickname == active.nickname, f"active changed to {ex.g.battlers()[0].nickname}"


@check
def battle_catch_switch_reaches_the_bench_mon():
    # catch_switch.ss is the party menu just opened for a catch helper, cursor on slot 0,
    # where the menu ate the first DOWN and the open-loop press count stopped at slot 2;
    # the plan then re-fired every step and the fight sat 10 minutes w/ no move chosen
    import play
    e = _load("catch_switch.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    assert ex.g.callback2() in play.CB2_PARTY_MENU, "fixture is not on the party menu"
    lead = ex.g.battlers()[0].nickname
    ex.switch_to = "Trubbish"
    for _ in range(30):
        ex.battle_step()
        if ex.g.battlers()[0].nickname == "Trubbish":
            break
    assert ex.g.battlers()[0].nickname == "Trubbish", f"{lead} still out, cb2 {ex.g.callback2():#x}"


@check
def gym_win_sets_badge_one():
    # roxanne.ss is the first frame of Roxanne's fight (Onix, Nosepass, Tyrunt) with Herdier
    # the only standing mon; the win and her speech must leave badge flag 0xCD7 set
    import play
    e = _load("roxanne.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    assert ex.g.battle_type_flags() & play.BATTLE_TYPE_TRAINER, "fixture is not a trainer battle"
    assert ex.g.badges() == 0, "fixture already holds a badge"
    for _ in range(300):
        if not ex.g.in_battle():
            break
        ex.battle_step()
    assert not ex.g.in_battle(), "leader fight never resolved"
    assert ex.g.party()[2].hp > 0, "Herdier went down, outcome is a loss"
    for _ in range(40):
        ex.tap(eb.KEY_A)
        ex.run(40)
    assert ex.g.badges() == 1, f"badge count {ex.g.badges()} after the win"


@check
def learn_policy_declines_a_move_no_better_than_the_slot_it_would_take():
    from types import SimpleNamespace
    from battle_engine import replacement_slot
    trubbish = SimpleNamespace(species=568, slot=4, moves=(CLEAR_SMOG, TAKE_DOWN, RECYCLE, ACID_SPRAY))
    assert replacement_slot(trubbish, POISON_GAS) is None, "a status move displaced a slot"
    assert replacement_slot(trubbish, SWALLOW) is None, "Swallow displaced a slot"
    before = SimpleNamespace(species=568, slot=4, moves=(SWALLOW, POISON_GAS, RECYCLE, ACID_SPRAY))
    assert replacement_slot(before, CLEAR_SMOG) == 0, "Clear Smog did not take the Swallow slot"


@check
def battle_never_throws_at_a_trainers_pokemon():
    # a trainer blocks the ball and the game still consumes it; the same wild fixture with
    # the trainer bit set in gBattleTypeFlags must yield no throw, and without it a throw
    import play
    import rowe_symbols as S
    import struct
    e = _load("battle_disabled.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    # the fixture's ball pocket is empty, so seed five Poké Balls (quantity xor the save key)
    sb1, sb2 = e.u32(S.addr("gSaveBlock1Ptr")), e.u32(S.addr("gSaveBlock2Ptr"))
    key = e.u32(sb2 + S.SB2_ENCRYPTION_KEY) & 0xFFFF
    e.write(sb1 + S.SB1_BAG_POKE_BALLS, struct.pack("<HH", 4, 5 ^ key))
    assert ex.g.poke_balls() == [(4, 5)], f"ball seed misread as {ex.g.poke_balls()}"
    _, me, foes = ex.sides()
    assert ex.catch_plan(me, foes) is not None, "wild control: fixture foe draws no catch plan"
    flags = S.addr("gBattleTypeFlags")
    e.write(flags, (e.u32(flags) | play.BATTLE_TYPE_TRAINER).to_bytes(4, "little"))
    assert ex.catch_plan(me, foes) is None, "catch plan drawn against a trainer's pokemon"


@check
def potion_policy_saves_the_strong_restoratives():
    import play
    pocket = [(28, 2), (37, 1), (34, 1)]  # Potion 20, Super Potion 60, Full Restore full
    assert play.best_hp_item(pocket, 15)[1] == 28, "a 15 gap did not take the Potion"
    assert play.best_hp_item(pocket, 40)[1] == 37, "a 40 gap skipped Super Potion for a lesser or greater item"
    assert play.best_hp_item([(28, 2), (37, 1)], 300)[1] == 37, "no cover did not fall back to the largest heal"
    assert play.best_hp_item([(49, 3)], 20) is None, "Ether read as an HP item"
    assert play.best_hp_item([(28, 0)], 10) is None, "a zero-quantity Potion was offered"


@check
def battle_low_lead_uses_a_potion_before_fleeing():
    # a lead under HEAL_HP_PERCENT in a wild fight reaches for a Medicine-pocket Potion through
    # the bag instead of running; without the bag heal the same state flees and ends the battle
    import struct
    import play
    import rowe_symbols as S
    e = _load("battle_disabled.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    bm, pp = S.addr("gBattleMons"), S.addr("gPlayerParty")
    # the fixture's lead is out of usable damaging moves (Disable), which flees before needs_heal;
    # restore Gust's PP so the fight has a move, then drop the active and the party lead to 5 HP
    e.write(bm + S.BM_PP, bytes([20]))
    e.write(bm + S.BM_HP, struct.pack("<H", 5))
    e.write(pp + S.MON_HP, struct.pack("<H", 5))
    # the fixture's Venonat sits at 1 HP, a KO in hand that outranks the bag heal; give it a body
    foe = bm + S.SIZEOF_BATTLE_POKEMON
    e.write(foe + S.BM_HP, struct.pack("<H", 200))
    e.write(foe + S.BM_MAX_HP, struct.pack("<H", 200))
    # a healthy bench mon would take the turn instead of the Potion; faint the bench
    for slot in range(1, len(ex.g.party())):
        e.write(pp + slot * S.SIZEOF_POKEMON + S.MON_HP, struct.pack("<H", 0))
    ex.tap(eb.KEY_B)  # fixture sits in the move menu; back out to the action menu
    ex.run(30)
    before = dict(ex.g.medicine()).get(28, 0)
    assert before > 0, "fixture Medicine pocket holds no Potion"
    for _ in range(12):
        ex.battle_step()
        if not ex.g.in_battle() or dict(ex.g.medicine()).get(28, 0) < before:
            break
    assert ex.g.in_battle(), "low lead fled instead of using a bag heal"
    assert dict(ex.g.medicine()).get(28, 0) == before - 1, f"no Potion spent, medicine {ex.g.medicine()}"
    assert ex.g.battlers()[0].hp > 5, f"lead not healed, hp {ex.g.battlers()[0].hp}"


@check
def field_bag_heals_the_bench_before_a_center_trip():
    # route104.ss stands in the overworld w/ six Potions in the Medicine pocket; injure two bench
    # mons under the heal line and the field bag must patch both from the pocket, leaving no low
    # mon to send the loop to a Center. A no-op flow leaves them at 10 and the Potion count at 6.
    import struct
    import play
    import rowe_symbols as S
    e = _load("route104.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    pp = S.addr("gPlayerParty")
    for slot in (2, 3):
        e.write(pp + slot * S.SIZEOF_POKEMON + S.MON_HP, struct.pack("<H", 10))
    before = sum(q for _, q in ex.g.medicine())
    assert before >= 2, f"fixture Medicine pocket too thin, {ex.g.medicine()}"
    # on a grind the free Center covers the bench and the pocket is left alone
    ex.goal = {"mode": "grind", "map": [0, 16], "cap": 16}
    ex.heal_bench_from_bag()
    assert sum(q for _, q in ex.g.medicine()) == before, f"a grind spent bench Potions, {ex.g.medicine()}"
    ex.goal = {"mode": "travel", "to": [0, 0]}
    ex.heal_bench_from_bag()
    party = ex.g.party()
    for slot in (2, 3):
        m = party[slot]
        assert m.hp * 100 >= m.max_hp * play.HEAL_HP_PERCENT, f"slot {slot} still low, {m.hp}/{m.max_hp}"
    assert sum(q for _, q in ex.g.medicine()) == before - 2, f"expected two Potions spent, {ex.g.medicine()}"


@check
def field_bag_leaves_the_center_trip_when_the_pocket_is_empty():
    # with no HP item on hand an injured bench stays injured, so the caller's recount still trips
    # need_heal and the Center run fires
    import struct
    import play
    import rowe_symbols as S
    e = _load("route104.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    pp = S.addr("gPlayerParty")
    e.write(pp + 2 * S.SIZEOF_POKEMON + S.MON_HP, struct.pack("<H", 10))
    sb1 = e.u32(S.addr("gSaveBlock1Ptr"))
    e.write(sb1 + S.SB1_BAG_MEDICINE, struct.pack("<HH", 0, 0))
    assert ex.g.medicine() == [], "pocket not emptied"
    ex.heal_bench_from_bag()
    assert ex.g.party()[2].hp == 10, "a mon healed with an empty Medicine pocket"


class _ScoreMon:
    """Party stand-in for the scorer: species, moves, nature and EVs are all it reads."""

    def __init__(self, species, slot=0, moves=()):
        self.species = species
        self.slot = slot
        self.moves = tuple(moves)
        self.nature, self.evs = 0, (0, 0, 0, 0, 0, 0)
        self.nickname = "mon"


STARLY, HOOTHOOT, PAWMI = 396, 163, 921  # Normal/Flying, Normal/Flying, Electric
TACKLE, SPARK = 33, 209  # physical Normal, physical Electric
_NO_IVS = (0, 0, 0, 0, 0, 0)


@check
def box_reads_the_storage_mons():
    # the box mon stride is 0x34, not the 0x38 the symbol file carried; a wrong stride drifts the
    # species read and this list comes back garbage, so the literal pins the stride
    import rowe_rom
    box = GameState(_load("route104.ss")).box()
    assert box == [(0, 261), (1, 263), (2, 921), (3, 504), (4, 43), (5, 570)], f"box {box}"
    assert rowe_rom.species(PAWMI).types == (13, 13), "Pawmi read as something other than Electric"


@check
def box_swap_trades_a_redundant_flyer_for_coverage():
    # six Normal/Flying mons all fold to Electric; the box holds an Electric mon that resists it, so
    # the swap raises the score well past the margin and fires
    import play
    import rowe_rom
    team = [play.mon_profile(_ScoreMon(STARLY, i, [TACKLE]), 30, _NO_IVS) for i in range(6)]
    wattson = [play.foe_types(rowe_rom.leader_build("Wattson", 3))]
    pawmi = play.mon_profile(_ScoreMon(PAWMI, moves=[SPARK]), 30, _NO_IVS)
    plan = play.best_swap(team, [(0, pawmi)], wattson, range(6), play.FLEX_MARGIN)
    assert plan is not None, "no swap when the box fixes a shared weakness"
    out, slot, gain = plan
    assert slot == 0 and gain >= play.FLEX_MARGIN, f"swap {plan}"


@check
def box_swap_holds_on_an_equal_trade():
    # swapping a Starly for a Starly w/ the same move changes nothing, so the gain is zero and the
    # margin holds the party as it is
    import play
    import rowe_rom
    team = [play.mon_profile(_ScoreMon(STARLY, i, [TACKLE]), 30, _NO_IVS) for i in range(6)]
    wattson = [play.foe_types(rowe_rom.leader_build("Wattson", 3))]
    same = play.mon_profile(_ScoreMon(STARLY, moves=[TACKLE]), 30, _NO_IVS)
    assert play.best_swap(team, [(0, same)], wattson, range(6), play.FLEX_MARGIN) is None, "cycled two equivalent mons"


@check
def next_leader_type_is_the_first_unbeaten_gym():
    # no badges on the fixture, so the next gym is Roxanne and her Rock type (5) scores the team
    import play
    ex = play.Player(_load("route104.ss"), play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    assert ex.next_leader_type() == 5, f"leader type {ex.next_leader_type()}"


@check
def pc_swap_deposits_the_party_mon_and_withdraws_the_box_mon():
    # standing in a Center, the storage PC drive must move the exact mons: party slot 2 out, box
    # slot 1 in, verified by species rather than the menu path
    from routines import Errands
    e = _load("center_entry.ss")
    g = GameState(e)
    out_sp = g.party()[2].species
    in_sp = dict(g.box())[1]
    assert out_sp != in_sp, "fixture can't tell the swap apart"
    ok = Errands(e, e.run, log=lambda s: None).swap_at_pc(2, 1)
    after = [m.species for m in g.party()]
    assert ok and in_sp in after and out_sp not in after, f"swap {out_sp}->{in_sp} left party {after}"
    assert len(after) == 6, f"a one-for-one swap left {len(after)} in the party: {after}"


@check
def pc_swap_sheds_a_rock_weak_flyer_before_roxanne():
    # the center fixture runs three Flying types at Roxanne's Rock; do_pc_swap must score, pick the
    # swap and drive the PC so the party ends with fewer flyers and a non-flyer withdrawn
    import rowe_rom
    import play
    ex = play.Player(_load("center_entry.ss"), play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    flyers = lambda: sum(2 in rowe_rom.species(m.species).types for m in ex.g.party())
    before = flyers()
    assert before >= 3, f"fixture is not flyer-heavy, {before}"
    ex.do_pc_swap()
    assert flyers() == before - 1, f"flyer count {before} -> {flyers()}, expected one fewer"


@check
def nav_surfs_the_woods_pond_to_the_north_exit():
    # woods_south.ss stands on the south entrance tile of Petalburg Woods; the north exit at
    # (14,6) is cut off on foot by the pond, so the walk must mount Surf and arrive
    from nav import Navigator
    e = _load("woods_south.ss")
    g = GameState(e)
    assert g.position()[2:] == (24, 11), "fixture is not in Petalburg Woods"
    assert Navigator(e, e.run).walk_to((14, 6), surf=True) == "arrived", f"stopped at {g.position()}"


@check
def map_graph_gate_reopens_when_field_move_gained():
    import tempfile
    import map_graph
    none, surf = frozenset(), frozenset({"SURF"})
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "g.json")
        g = map_graph.MapGraph(p)
        g.observe((0, 19), [(0, 3), (0, 20)])  # Route 104 and its two water borders
        assert g.explore_hop((0, 19), field_moves=none) in ((0, 3), (0, 20)), "open border not offered"
        g.block((0, 19), (0, 3), none)
        g.block((0, 19), (0, 20), none)
        assert g.explore_hop((0, 19), field_moves=none) is None, "gated borders still offered"
        assert g.frontier_exhausted(none) and g.gated_frontier(none), "all-gated frontier not reported"
        # the whole point: learning Surf changes the capability, so the water un-gates
        assert g.explore_hop((0, 19), field_moves=surf) in ((0, 3), (0, 20)), "gate did not reopen on new field move"
        assert not g.frontier_exhausted(surf), "reopened frontier still read as exhausted"
        assert map_graph.MapGraph(p).gated == g.gated, "gates did not persist across reload"


@check
def planner_sends_a_capped_party_to_the_gym():
    import tempfile
    import map_graph
    import planner
    import rowe_rom
    with tempfile.TemporaryDirectory() as d:
        # recommend reads these off disk through module globals; point them at the tempdir so a
        # live run's gym_closed/grind_blocked cannot poison the planning logic under test
        planner.GYM_CLOSED = os.path.join(d, "gym_closed.json")
        planner.BLOCKED = os.path.join(d, "grind_blocked.json")
        g = map_graph.MapGraph(os.path.join(d, "g.json"), world=rowe_rom.world_edges(),
                               passthrough=rowe_rom.passthroughs())
        party = [{"level": 16, "moves": [{"power": 40, "pp": 10}]} for _ in range(6)]
        # [0, 3] is the town linking into the Rustboro gym, so it is the nearest unbeaten gym here
        goal, _ = planner.recommend({"party": party, "map": [0, 3], "badges": 0}, g)
        gym = {"mode": "gym", "map": [11, 3], "stand": [5, 3], "badges": 0}
        # one badge in: ROWE reads the beaten gym off its own flag, not the count, so Rustboro
        # (flag 0) is marked down the way live status.json carries it
        beaten = [True] + [False] * 7
        assert goal == gym, f"capped party not sent to the Rustboro gym: {goal}"
        low = party[:5] + [{"level": 15, "moves": [{"power": 40, "pp": 10}]}]
        goal, _ = planner.recommend({"party": low, "map": [0, 18], "badges": 0}, g)
        assert goal["mode"] == "grind" and goal["cap"] == 16, f"under-cap party not held on a grind: {goal}"
        goal, _ = planner.recommend({"party": party, "map": [11, 3], "badges": 0}, g)
        assert goal == gym, f"at the gym the goal stays the gym fight, got {goal}"
        goal, _ = planner.recommend({"party": party, "map": [11, 3], "badges": 1, "badge_flags": beaten}, g)
        assert goal["mode"] == "grind" and goal["cap"] == 21, f"one badge must re-grind to cap 21, got {goal}"
        # Rustboro beaten, so the grind anchors on the next gym; with no walked route it falls back
        # to the overworld map nearest that anchor
        assert goal["map"] == [0, 0], f"gym grind w/ no walked route falls back to the nearest overworld map, got {goal['map']}"
        # Rustboro walked w/ Route 104 and Route 116 beside it: the grind goes to a route, never the gym
        g.observe((0, 3), [(0, 19), (0, 31)])
        g.observe((0, 19), [(0, 3)])
        goal, _ = planner.recommend({"party": party, "map": [11, 3], "badges": 1, "badge_flags": beaten}, g)
        assert goal["map"] == [0, 19], f"grind from the gym must land on the nearest walked route, got {goal['map']}"
        goal, _ = planner.recommend({"party": low, "map": [0, 3], "badges": 0}, g)
        assert goal["map"] == [0, 19], f"grind from a town must leave for a route, got {goal['map']}"


@check
def map_graph_routes_through_a_warp_loop_past_a_blocked_edge():
    # Route 104 (0,19) borders Rustboro (0,3) only from its north half, reached by warping
    # through Petalburg Woods (24,11) and back out onto the same route map
    import tempfile
    import map_graph
    # Petalburg (0,0) borders it and Mr. Briney's house (17,0) warps back to it, but neither
    # is a pass-through, so neither may carry the route back onto Route 104
    world = {(0, 19): {(0, 3), (0, 0), (0, 20), (17, 0), (24, 11)}, (24, 11): {(0, 19)}, (17, 0): {(0, 19)},
             (0, 0): {(0, 19), (0, 17)}, (0, 3): {(0, 19), (11, 3)}, (11, 3): {(0, 3)}}
    with tempfile.TemporaryDirectory() as d:
        g = map_graph.MapGraph(os.path.join(d, "g.json"), world=world, passthrough={(24, 11): {(0, 19)}})
        assert g.route((0, 19), (11, 3)) == (0, 3), "direct edge not taken when nothing is blocked"
        assert g.route((0, 19), (11, 3), blocked={(0, 3)}) == (24, 11), "blocked edge not routed around through the woods"
        assert g.route((24, 11), (11, 3)) == (0, 19), "no route back out of the woods"
        g.passthrough = {}
        assert g.route((0, 19), (11, 3), blocked={(0, 3)}) is None, "a connection or a house door re-entered the source map"


@check
def rom_world_links_route104_to_the_woods_and_rustboro_to_its_gym():
    import rowe_rom as rr
    world = rr.world_edges()
    assert (24, 11) in world[(0, 19)], f"Route 104 has no warp edge to Petalburg Woods: {sorted(world[(0, 19)])}"
    assert (0, 3) in world[(0, 19)], "Route 104 lost its Rustboro connection"
    assert (11, 3) in world[(0, 3)], f"Rustboro has no warp edge to its gym: {sorted(world[(0, 3)])}"
    assert len(world) > 500, f"world table too small to be the whole ROM: {len(world)} maps"
    through = rr.passthroughs()
    assert (0, 19) in through.get((24, 11), ()), "Petalburg Woods not read as a pass-through onto Route 104"
    assert (0, 19) not in through.get((17, 0), ()), "Mr. Briney's house read as a pass-through"
    assert (0, 10) not in through.get((2, 2), ()), "Oldale Center read as a pass-through"


@check
def executor_holds_grind_when_frontier_gated():
    import tempfile
    import map_graph
    import play
    e = _load("route104.ss")
    ex = play.Player(e, play.NullStreamer())
    here = GameState(e).position()[2:]
    moves = ex.field_moves()
    with tempfile.TemporaryDirectory() as d:
        ex.state_path = os.path.join(d, "route101.ss")
        ex.graph = map_graph.MapGraph(os.path.join(d, "map_graph.json"))
        ex.graph.observe(here, [(0, 3), (0, 20)])
        ex.graph.block(here, (0, 3), moves)
        ex.graph.block(here, (0, 20), moves)
        ex.goal = {"mode": "explore"}
        ex.explore_step()
        assert ex.goal["mode"] == "grind", f"gated explore did not demote in-loop: {ex.goal}"
        assert ex.goal["cap"] is None, "in-loop hold-grind must be capless"


@check
def item_balls_are_read_off_the_rom():
    # Route 104 carries four item balls among 34 object templates; the item-ball sprite id must
    # pick out exactly those four tiles and leave the NPCs, trainers and berry trees out
    e = _load("route104.ss")
    g = GameState(e)
    balls = rowe_map.item_balls(e)
    tiles = {(x, y) for x, y, _ in balls}
    assert tiles == {(39, 15), (29, 53), (37, 22), (5, 8)}, f"item balls misread: {sorted(tiles)}"
    assert all(f and not g.flag(f) for _, _, f in balls), "a Route 104 ball has no flag or reads collected"


@check
def item_ball_detour_collects_then_skips_the_collected_ball():
    # woods_south stands in Petalburg Woods with four uncollected balls; one detour picks up the
    # nearest, its flag flips, and the collected ball drops out so the detour never repeats on it
    import play
    e = _load("woods_south.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    before = ex.collectable_balls()
    assert len(before) >= 2, f"fixture must offer at least two reachable balls: {before}"
    target = before[0]
    assert ex.collect_step() is True, "no detour taken with a reachable ball uncollected"
    assert ex.g.flag(target[2]), "the ball's collected flag did not flip after the pickup"
    after = ex.collectable_balls()
    assert (target[0], target[1]) not in {(b[0], b[1]) for b in after}, "collected ball still offered for a detour"
    assert len(after) == len(before) - 1, f"detour list changed by more than the collected ball: {before} -> {after}"


@check
def shopping_list_waits_for_a_town_unless_the_trek_is_earned():
    # out on a route w/ a list pending, the loop keeps grinding; only mart_trek (balls at zero w/ a
    # party to fill) walks to town on the list alone, and arriving in town works the counter
    import play
    e = _load("route104.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    here = ex.g.position()[2:]
    town = (0, 0)
    calls = []
    ex.travel_toward = lambda *a, **k: calls.append("travel")
    ex.collect_step = lambda: (calls.append("grind"), True)[1]
    ex.errands.restock_at = lambda *a, **k: (calls.append("restock"), {4: 10})[1]
    ex.shopping = [(4, 10)]
    saved = play.SERVICE, play.SERVICE_MAPS
    play.SERVICE = {town: ((0, 0), (0, 0))}
    play.SERVICE_MAPS = {town: frozenset({town})}
    ex.service_town = lambda h: town
    try:
        ex.overworld_step(0)
        assert calls == ["grind"], f"a pending list w/o a trek left the route: {calls}"
        ex.mart_trek = True
        ex.overworld_step(0)
        assert calls[-1] == "travel", f"mart_trek did not walk to town: {calls}"
        play.SERVICE_MAPS = {town: frozenset({town, here})}
        ex.overworld_step(0)
        assert calls[-1] == "restock" and ex.shopping == [] and ex.mart_trek is False, f"in town did not buy and clear: {calls} {ex.shopping}"
    finally:
        play.SERVICE, play.SERVICE_MAPS = saved


@check
def battle_paralysed_lead_uses_the_cure_from_the_bag():
    # battle_disabled.ss w/ the active mon and its party record set paralysed and a Parlyz Heal
    # written into the Medicine pocket behind the Potions: the next step spends the cure through
    # the battle bag and the status bits clear, with the fight still on
    import struct
    import play
    import rowe_symbols as S
    e = _load("battle_disabled.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    bm, pp = S.addr("gBattleMons"), S.addr("gPlayerParty")
    e.write(bm + S.BM_PP, bytes([20]))
    # the fixture's Venonat sits at 1 HP, a KO in hand that outranks any bag use; give it a body
    foe = bm + S.SIZEOF_BATTLE_POKEMON
    e.write(foe + S.BM_HP, struct.pack("<H", 200))
    e.write(foe + S.BM_MAX_HP, struct.pack("<H", 200))
    e.write(bm + S.BM_STATUS1, struct.pack("<I", play.STATUS1_PARALYSIS))
    e.write(pp + S.MON_STATUS, struct.pack("<I", play.STATUS1_PARALYSIS))
    sb1 = e.u32(S.addr("gSaveBlock1Ptr"))
    key = e.u32(e.u32(S.addr("gSaveBlock2Ptr")) + S.SB2_ENCRYPTION_KEY) & 0xFFFF
    slot = len(ex.g.medicine())
    e.write(sb1 + S.SB1_BAG_MEDICINE + 4 * slot, struct.pack("<HH", 33, 1 ^ key))
    assert dict(ex.g.medicine()).get(33) == 1, f"cure not written into the pocket: {ex.g.medicine()}"
    ex.tap(eb.KEY_B)
    ex.run(30)
    for _ in range(6):
        ex.battle_step()
        if not ex.g.in_battle() or 33 not in dict(ex.g.medicine()):
            break
    assert ex.g.in_battle(), "fight ended before the cure was used"
    assert 33 not in dict(ex.g.medicine()), f"Parlyz Heal not spent: {ex.g.medicine()}"
    assert not ex.g.battlers()[0].status1 & play.STATUS1_PARALYSIS, f"still paralysed: {ex.g.battlers()[0].status1:#x}"


@check
def mart_buys_the_list_and_skips_a_row_the_shop_lacks():
    # mart_buy.ss is the Petalburg Mart Buy list open on row 0 with ¥1860, six starter Potions and
    # an empty ball pocket; the list is read off RAM, each wanted row is bought and read back, and
    # a Super Potion the shop does not stock comes back 0 without touching the money
    from routines import Errands
    e = _load("mart_buy.ss")
    er = Errands(e, e.run, log=lambda *_: None)
    assert er.g.shop_items() == [4, 28, 29, 32, 33], f"shop list read wrong: {er.g.shop_items()}"
    money = er.g.money()
    assert dict(er.g.medicine()) == {28: 6}, f"fixture medicine pocket changed: {er.g.medicine()}"
    bought = er.buy_from_list([(4, 3), (28, 2), (37, 1), (29, 1)])
    assert bought == {4: 3, 28: 2, 37: 0, 29: 1}, f"bought {bought}"
    assert dict(er.g.poke_balls()).get(4) == 3, f"ball pocket {er.g.poke_balls()}"
    assert dict(er.g.medicine()) == {28: 8, 29: 1}, f"medicine pocket {er.g.medicine()}"
    assert er.g.money() == money - 300 - 600 - 100, f"money {money} -> {er.g.money()}"
    assert er.map_id() == (8, 6) and not er.g.in_battle(), "did not back out to the Mart floor"


@check
def nav_arrow_warp_gate_enters_the_city():
    # city_gate.ss stands on (39, 14) of [1,31], a west-arrow warp into the walled city [0,2] on
    # the map's east edge; the press off the edge walked the connection back onto Route [0,33]
    from routines import Errands
    e = _load("city_gate.ss")
    er = Errands(e, e.run, log=lambda *_: None)
    assert er.map_id() == (1, 31), f"fixture is on {er.map_id()}"
    r = er.take_warp((0, 2))
    assert r == "map_changed" and er.map_id() == (0, 2), f"take_warp {r}, landed on {er.map_id()}"


@check
def travel_counts_a_landing_off_the_hop_as_a_miss():
    # a crossing that leaves the map for somewhere other than the hop is a stuck hit toward the
    # gate, never a move; with the arrow press in place the gate itself no longer misses, so the
    # warp call is stood in by the east crossing the old press produced
    import tempfile
    import map_graph
    import play
    e = _load("city_gate.ss")
    ex = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-smoke-caught.json")
    ex.errands.take_warp = lambda dest, surf=False, rank=None, tools=frozenset(): ex.errands.cross_edge(rowe_map.DIR_EAST)
    with tempfile.TemporaryDirectory() as d:
        ex.graph = map_graph.MapGraph(os.path.join(d, "map_graph.json"))
        ex.graph.observe((1, 31), [(0, 2), (0, 33)])
        ex._stuck_hits = {}
        status, result = ex._cross_to((1, 31), (0, 2))
        assert (status, result) == ("map_changed", "missed"), f"got {(status, result)} at {ex.g.position()}"
        assert ex.g.position()[2:] == (0, 33), f"party on {ex.g.position()[2:]}"
        assert list(ex._stuck_hits.values()) == [1], f"stuck tally {ex._stuck_hits}"


@check
def modules_import():
    for m in ("battle_engine", "map_graph", "nav", "planner", "play", "routines"):
        importlib.import_module(m)


def main():
    fails = 0
    for fn in CHECKS:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            fails += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"{len(CHECKS) - fails}/{len(CHECKS)} green")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
