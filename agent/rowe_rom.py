"""Static tables read straight out of rowe-v2.1b.gba.

Offsets were located by fingerprinting known vanilla entries (Pound through
Fire Punch for the move table, the Normal attacking row for the type chart,
"Pound"/"Karate Chop" spacing for the names) and hold for this ROM only.
"""
import bisect
import struct
from dataclasses import dataclass
from functools import lru_cache

from emu_boot import ROM

MOVES_OFFSET = 0x427340       # gBattleMoves, 20 bytes per entry
MOVE_STRIDE = 20
TYPE_CHART_OFFSET = 0x41F0F0  # u16 UQ_4_12 [19][19], attacker row x defender column
NUM_TYPES = 19
MOVE_NAMES_OFFSET = 0x4118D3  # 17 bytes per name, 0xFF terminated
MOVE_NAME_LEN = 17
MOVE_COUNT = 827  # ROWE's table runs past vanilla: 819 Trailblaze on a Route 104 trainer's Tyrunt, 826 Raging Fury is the last named row
ABILITY_NAMES_OFFSET = 0x416100  # gAbilityNames, 21 bytes per name; 1 Stench, 11 Water Absorb, 308 Evaporate (Slugma's second slot)
ABILITY_NAME_LEN = 21
ABILITY_SCAN_CAP = 512  # the table runs past 359 Tera Shell w/ no terminator; a row past the end decodes to junk no lookup names
SPECIES_NAMES_OFFSET = 0x40B558  # gSpeciesNames, 13 bytes per name; id 1 Bulbasaur, 4 Charmander, 7 Squirtle
SPECIES_NAME_LEN = 13
REGION_MAP_ENTRIES = 0x08FBD474  # gRegionMapEntries, indexed by mapsec; entry 0 Littleroot Town
REGION_MAP_ENTRY_SIZE = 8  # {u8 x, y, width, height; const u8* name}
SPECIES_OFFSET = 0x4F710C      # gSpeciesInfo, 64 bytes per entry, ids are national dex numbers
SPECIES_STRIDE = 0x40
SPECIES_COUNT = 1959           # rows 1-1025 the dex, 1026-1500 zero, 1501-1958 ROWE's forms (League pools reach 1644)
SPECIES_GROWTH = 27            # u8 growthRate, index into gExperienceTables
SPECIES_ABILITIES = 0x1E       # u16[2] ability slots, then u16 at 0x22 always 0 and the hidden ability at 0x24
SPECIES_HIDDEN_ABILITY = 0x24
# gEvolutionTable[NUM_SPECIES][10], an 8-byte row {u16 method, u16 param, u16 target, u16 pad}; located by
# Bulbasaur's {EVO_LEVEL, 16, Ivysaur} row w/ Charmander's and Squirtle's 240 bytes apart
EVOLUTIONS_OFFSET = 0x5A607C
EVOS_PER_MON = 10
EVO_ROW = 8
EVO_LEVEL = 4
EVO_LEVEL_ALT = 39             # ROWE's level row beside a trade or stone row (Magneton 42, Machoke 42, Kadabra 36)
LEVEL_METHODS = (EVO_LEVEL, EVO_LEVEL_ALT)  # the methods the planner projects; item, trade and friendship rows stay put
NUM_NATURES = 25
NATURE_NAMES = ("Hardy", "Lonely", "Brave", "Adamant", "Naughty", "Bold", "Docile", "Relaxed", "Impish", "Lax",
                "Timid", "Hasty", "Serious", "Jolly", "Naive", "Modest", "Mild", "Quiet", "Bashful", "Rash",
                "Calm", "Gentle", "Sassy", "Careful", "Quirky")  # gNatureNames order, indexed by personality % 25
HP, ATK, DEF, SPE, SPA, SPD = range(6)
EXP_TABLES_OFFSET = 0x4EDC8C   # gExperienceTables[6][MAX_LEVEL + 1] u32, medium-fast first
EXP_TABLE_LEN = 101
GROWTH_RATE_COUNT = 6
ITEMS_OFFSET = 0xF63E74        # gItems, 56 bytes per entry, 16-byte name then u16 id
ITEM_PRICE = 20                # u16 after the id; Poké Ball reads 100, Potion 300
ITEM_STRIDE = 0x38
ITEM_COUNT = 1000
ITEM_TM01 = 482                # TM01 Focus Punch; TM120 is 601, HM01..HM08 682..689, the ids between unused
TM_MOVES_OFFSET = 0x1041518    # sTMHMMoves, u16 move per item from TM01 through HM08, index item - ITEM_TM01
TM_MOVES_COUNT = 208
TM_LEARNSETS_OFFSET = 0x4EBEA4  # gTMHMLearnsets, a ROM pointer per species to u8 TM indexes (item - ITEM_TM01)
                                # ended by 0xFF; form rows past 1013 carry a null pointer
LEVEL_UP_LEARNSETS_OFFSET = 0x5D3688  # gLevelUpLearnsets, a ROM pointer per species to {u16 move, u16 level} rows
                                      # ended by move 0xFFFF; level 0 is the on-evolution move
EGG_MOVES_OFFSET = 0x5DAD5C    # gEggMoves, u16 stream: species + EGG_MOVES_SPECIES_OFFSET opens a block of move ids,
EGG_MOVES_SPECIES_OFFSET = 20000  # 0xFFFF ends the table; keyed by the line's first stage (Pawmi holds Pawmo's)

ROM_BASE = 0x08000000
# gMapGroups, a table of MAP_GROUP_COUNT group arrays, each an array of MapHeader
# pointers. Found by matching the live gMapHeader of map (0,0) (mapLayout + connections
# words) against the ROM and walking the two pointer tables back to their base.
MAP_GROUPS = 0x088273CC
MAP_GROUP_COUNT = 34
MAP_GROUP_SCAN_CAP = 256  # the last group has no successor pointer to size it against; measured 47
MAX_CONNECTIONS = 16  # a real map has at most a few per side; a count past this is a misread word
PASSTHROUGH_SPREAD = 4  # tiles between warps to one destination; a double door spans 1, the Woods' mouths 33
# every town's Pokémon Center 1F reuses one shared map layout, every Mart another, so the
# layout id classifies a map without visiting it. Grounded on Oldale PC (2,2) and Mart (2,4).
CENTER_LAYOUT_ID = 61
MART_LAYOUT_ID = 63
# struct MapHeader: mapLayout* +0, events* +4, mapScripts* +8, connections* +0xC,
# music +0x10, mapLayoutId +0x12 (head matches vanilla, as rowe_symbols already relies on)
MAPHDR_LAYOUT = 0x0
MAPHDR_EVENTS = 0x4
MAPHDR_SCRIPTS = 0x8
MAPHDR_CONNECTIONS = 0xC
MAPHDR_MUSIC = 0x10
MAPHDR_LAYOUT_ID = 0x12
MAPHDR_REGION_SECTION = 0x14  # regionMapSectionId, the mapsec a map belongs to
MAPHDR_MAP_TYPE = 0x17
MAP_TYPE_UNDERGROUND = 4
MAP_TYPE_UNDERWATER = 5
MAP_TYPE_INDOOR = 8
MAP_SCRIPT_SCAN_CAP = 64  # map-script table entries, terminated by a 0 type byte; cap guards a garbage header pointer
GYM_MUSIC = 0x14F  # every gym interior shares this track; the eight entrance maps plus a few inner floors
OBJ_STRIDE = 24
OBJ_X = 0x4         # s16 x, s16 y follow
OBJ_MOVEMENT = 0x9
OBJ_SCRIPT = 0x10   # u32 event script run on an A-press interaction
OBJ_FLAG = 0x14     # u16 visibility flag
STATIC_MOVEMENT = frozenset({0, 7, 8, 9, 10})  # movement types that hold the tile: none, face down/up/left/right
MAX_MAP_CELLS = 0x2800  # MAX_MAP_DATA_SIZE, the backup buffer every layout must fit
# struct MapEvents: u8 objCount, warpCount, coordCount, bgCount; then obj*, warp*, coord*, bg*
MAPEVENTS_WARP_COUNT = 0x1
MAPEVENTS_BG_COUNT = 0x3
MAPEVENTS_WARP_PTR = 0x8
MAPEVENTS_BG_PTR = 0x10
# struct BgEvent (12 bytes): s16 x, s16 y, u8 elevation, u8 kind, 2 pad, then a 4-byte union; for a
# hidden item (kind 7) the union is u16 item, then u16 {flagId:12, quantity:4}
BG_STRIDE = 12
BG_HIDDEN_ITEM_KIND = 7
# an item-ball object hands its item through setorcopyvar VAR_0x8000, <item> near the script top
SETORCOPYVAR_OP = 0x1A
VAR_RECEIVED_ITEM = 0x8000
# struct WarpEvent (8 bytes): s16 x, s16 y, u8 elevation, u8 warpId, u8 mapNum, u8 mapGroup
WARP_STRIDE = 8
WARP_MAP_NUM = 0x6
WARP_MAP_GROUP = 0x7

SPLIT_PHYSICAL, SPLIT_SPECIAL, SPLIT_STATUS = 0, 1, 2
TYPE_NAMES = ["Normal", "Fighting", "Flying", "Poison", "Ground", "Rock", "Bug", "Ghost", "Steel",
              "Mystery", "Fire", "Water", "Grass", "Electric", "Psychic", "Ice", "Dragon", "Dark", "Fairy"]


@dataclass(frozen=True)
class Move:
    id: int
    name: str
    effect: int
    power: int
    type: int
    accuracy: int
    pp: int
    priority: int
    split: int
    flags: int


@dataclass(frozen=True)
class Species:
    id: int
    base_stats: tuple
    types: tuple
    catch_rate: int
    exp_yield: int
    abilities: tuple  # (slot 0, slot 1, hidden), ability ids, 0 where the species has none; indexed by a mon's ability_num


ABILITY_DESC_TABLE = 0x417EB4  # gAbilityDescriptionPointers, a ROM pointer per ability-name row; Shining Fist's is null
_PUNCT = {0x1B: "é", 0xAB: "!", 0xAC: "?", 0xAD: ".", 0xB4: "'", 0xB8: ",", 0xBA: "/", 0xF0: ":", 0xB1: "“", 0xB2: "”",
          0x5C: "(", 0x5D: ")", 0xB5: "♂", 0xB6: "♀", 0xB0: "…"}


@lru_cache(maxsize=None)
def ability_description(ability_id: int) -> str:
    """The summary screen's one-line description, empty for a row w/ no string."""
    if not 0 <= ability_id < ABILITY_SCAN_CAP:
        raise ValueError(f"ability id out of range: {ability_id}")
    rom = _rom()
    ptr = struct.unpack_from("<I", rom, ABILITY_DESC_TABLE + ability_id * 4)[0]
    if not ptr:
        return ""
    o = ptr - ROM_BASE
    return _decode(rom[o:o + 200])


def _decode(raw: bytes) -> str:
    out = []
    for c in raw:
        if c == 0xFF:
            break
        if 0xBB <= c <= 0xD4:
            out.append(chr(ord("A") + c - 0xBB))
        elif 0xD5 <= c <= 0xEE:
            out.append(chr(ord("a") + c - 0xD5))
        elif 0xA1 <= c <= 0xAA:
            out.append(chr(ord("0") + c - 0xA1))
        elif c == 0x00 or c == 0xFE:  # space, and the line break the description strings wrap on
            out.append(" ")
        elif c in _PUNCT:
            out.append(_PUNCT[c])
        elif c == 0xAE:
            out.append("-")
        else:
            out.append("?")
    return "".join(out)


@lru_cache(maxsize=1)
def _rom() -> bytes:
    with open(ROM, "rb") as f:
        return f.read()


@lru_cache(maxsize=None)
def move(move_id: int) -> Move:
    if not 0 <= move_id < MOVE_COUNT:
        raise ValueError(f"move id out of range: {move_id}")
    rom = _rom()
    o = MOVES_OFFSET + move_id * MOVE_STRIDE
    effect, power, mtype, acc, pp, _chance, _target, prio = struct.unpack_from("<HBBBBBBb", rom, o)
    flags = struct.unpack_from("<I", rom, o + 12)[0]
    split = rom[o + 16]
    n = MOVE_NAMES_OFFSET + move_id * MOVE_NAME_LEN
    return Move(move_id, _decode(rom[n:n + MOVE_NAME_LEN]), effect, power, mtype, acc, pp, prio, split, flags)


@lru_cache(maxsize=1)
def ability_ids() -> dict:
    """{name: id} over the ROM's ability-name table, so a lookup names an ability instead of a constant
    copied from a vendored source tree that predates the ROM (ROWE's Evaporate is absent from it)."""
    rom = _rom()
    out = {}
    for i in range(ABILITY_SCAN_CAP):
        o = ABILITY_NAMES_OFFSET + i * ABILITY_NAME_LEN
        out.setdefault(_decode(rom[o:o + ABILITY_NAME_LEN]), i)
    return out


def ability_id(name: str) -> int:
    ids = ability_ids()
    if name not in ids:
        raise KeyError(f"ability not in the ROM's name table: {name}")
    return ids[name]


@lru_cache(maxsize=None)
def ability_name(ability_id: int) -> str:
    if not 0 <= ability_id < ABILITY_SCAN_CAP:
        raise ValueError(f"ability id out of range: {ability_id}")
    o = ABILITY_NAMES_OFFSET + ability_id * ABILITY_NAME_LEN
    return _decode(_rom()[o:o + ABILITY_NAME_LEN])


@lru_cache(maxsize=None)
def species(species_id: int) -> Species:
    if not 0 <= species_id < SPECIES_COUNT:
        raise ValueError(f"species id out of range: {species_id}")
    rom = _rom()
    o = SPECIES_OFFSET + species_id * SPECIES_STRIDE
    stats = struct.unpack_from("<6H", rom, o)
    a0, a1 = struct.unpack_from("<HH", rom, o + SPECIES_ABILITIES)
    hidden = struct.unpack_from("<H", rom, o + SPECIES_HIDDEN_ABILITY)[0]
    return Species(species_id, stats, (rom[o + 12], rom[o + 13]), rom[o + 14], struct.unpack_from("<H", rom, o + 16)[0],
                   (a0, a1, hidden))


def ability_of(species_id: int, ability_num: int) -> int:
    """The ability a mon w/ this species and ability slot has, the game's GetAbilityBySpecies: an empty
    slot falls back to slot 0."""
    abilities = species(species_id).abilities
    return abilities[ability_num] or abilities[0]


@lru_cache(maxsize=None)
def evolutions(species_id: int) -> tuple:
    """((method, param, target), ...) rows of the species' evolution table, empty rows dropped."""
    if not 0 <= species_id < SPECIES_COUNT:
        raise ValueError(f"species id out of range: {species_id}")
    rom = _rom()
    o = EVOLUTIONS_OFFSET + species_id * EVOS_PER_MON * EVO_ROW
    rows = [struct.unpack_from("<HHH", rom, o + i * EVO_ROW) for i in range(EVOS_PER_MON)]
    return tuple(r for r in rows if r[2])


def species_at_level(species_id: int, level: int) -> int:
    """The species a mon of `species_id` holds once raised to `level` through every EVO_LEVEL or
    EVO_LEVEL_ALT step at or under it, the stage the game evolves a leader's row to. A species w/ two
    level rows (a Wurmple split) takes the first."""
    seen = {species_id}
    while True:
        step = next((t for m, p, t in evolutions(species_id) if m in LEVEL_METHODS and p <= level), None)
        if step is None or step in seen:
            return species_id
        seen.add(step)
        species_id = step


def nature_modifier(nature: int, stat: int) -> tuple:
    """(numerator, denominator) the game multiplies a non-HP stat by: nature // 5 is the raised stat and
    nature % 5 the lowered one over Atk, Def, Spe, SpA, SpD; equal means neutral."""
    up, down = nature // 5, nature % 5
    if up == down:
        return 1, 1
    if stat - 1 == up:
        return 110, 100
    if stat - 1 == down:
        return 90, 100
    return 1, 1


def stats_at(species_id: int, level: int, nature: int, ivs: tuple, evs: tuple) -> tuple:
    """(HP, Atk, Def, Spe, SpA, SpD) the game's CalculateMonStats produces, integer math throughout, so a
    box mon's stats at the party floor come out as they will read once it is raised there."""
    bs = species(species_id).base_stats
    out = [(2 * bs[HP] + ivs[HP] + evs[HP] // 4) * level // 100 + level + 10]
    for i in range(ATK, SPD + 1):
        n = (2 * bs[i] + ivs[i] + evs[i] // 4) * level // 100 + 5
        num, den = nature_modifier(nature, i)
        out.append(n * num // den)
    return tuple(out)


@lru_cache(maxsize=None)
def exp_bounds(species_id: int, level: int) -> tuple[int, int]:
    """Experience at `level` and at the next one for the species' growth rate; equal at the cap."""
    if not 0 <= species_id < SPECIES_COUNT:
        raise ValueError(f"species id out of range: {species_id}")
    if not 1 <= level < EXP_TABLE_LEN:
        raise ValueError(f"level out of range: {level}")
    rom = _rom()
    growth = rom[SPECIES_OFFSET + species_id * SPECIES_STRIDE + SPECIES_GROWTH]
    if growth >= GROWTH_RATE_COUNT:
        raise ValueError(f"growth rate out of range for species {species_id}: {growth}")
    table = EXP_TABLES_OFFSET + growth * EXP_TABLE_LEN * 4
    lo = struct.unpack_from("<I", rom, table + level * 4)[0]
    hi = struct.unpack_from("<I", rom, table + min(level + 1, EXP_TABLE_LEN - 1) * 4)[0]
    return lo, hi


@lru_cache(maxsize=None)
def level_from_exp(species_id: int, exp: int) -> int:
    """The highest level whose table entry is at or under `exp`; a box mon stores no level byte."""
    if not 0 <= species_id < SPECIES_COUNT:
        raise ValueError(f"species id out of range: {species_id}")
    rom = _rom()
    growth = rom[SPECIES_OFFSET + species_id * SPECIES_STRIDE + SPECIES_GROWTH]
    if growth >= GROWTH_RATE_COUNT:
        raise ValueError(f"growth rate out of range for species {species_id}: {growth}")
    entries = struct.unpack_from(f"<{EXP_TABLE_LEN}I", rom, EXP_TABLES_OFFSET + growth * EXP_TABLE_LEN * 4)
    return max(1, bisect.bisect_right(entries, exp) - 1)


@lru_cache(maxsize=None)
def species_name(species_id: int) -> str:
    if not 0 <= species_id < SPECIES_COUNT:
        raise ValueError(f"species id out of range: {species_id}")
    o = SPECIES_NAMES_OFFSET + species_id * SPECIES_NAME_LEN
    return _decode(_rom()[o:o + SPECIES_NAME_LEN])


@lru_cache(maxsize=None)
def item_name(item_id: int) -> str:
    if not 0 <= item_id < ITEM_COUNT:
        raise ValueError(f"item id out of range: {item_id}")
    o = ITEMS_OFFSET + item_id * ITEM_STRIDE
    return _decode(_rom()[o:o + 16])


@lru_cache(maxsize=None)
def item_price(item_id: int) -> int:
    if not 0 <= item_id < ITEM_COUNT:
        raise ValueError(f"item id out of range: {item_id}")
    return struct.unpack_from("<H", _rom(), ITEMS_OFFSET + item_id * ITEM_STRIDE + ITEM_PRICE)[0]


def tm_move(item_id: int) -> int:
    """Move the TM or HM teaches, 0 on an unused id in the span."""
    if not ITEM_TM01 <= item_id < ITEM_TM01 + TM_MOVES_COUNT:
        raise ValueError(f"not a TM or HM item: {item_id}")
    return struct.unpack_from("<H", _rom(), TM_MOVES_OFFSET + 2 * (item_id - ITEM_TM01))[0]


@lru_cache(maxsize=None)
def level_up_learnset(species_id: int) -> tuple:
    """((level, move), ...) in table order for the species; a reminder offers every row at or under the mon's level."""
    if not 0 <= species_id < SPECIES_COUNT:
        raise ValueError(f"species id out of range: {species_id}")
    rom = _rom()
    p = struct.unpack_from("<I", rom, LEVEL_UP_LEARNSETS_OFFSET + 4 * species_id)[0]
    if p < ROM_BASE:
        return ()
    p -= ROM_BASE
    out = []
    while True:
        mv, lv = struct.unpack_from("<HH", rom, p)
        if mv == 0xFFFF:
            return tuple(out)
        out.append((lv, mv))
        p += 4


@lru_cache(maxsize=1)
def _pre_evolutions() -> dict:
    """{child species: parent species} over every evolution row in the table."""
    out = {}
    for sp in range(1, SPECIES_COUNT):
        for _method, _param, child in evolutions(sp):
            out.setdefault(child, sp)
    return out


def first_stage(species_id: int) -> int:
    """The species at the root of the evolution line, which keys the egg move table."""
    pre = _pre_evolutions()
    while species_id in pre:
        species_id = pre[species_id]
    return species_id


@lru_cache(maxsize=1)
def _egg_move_blocks() -> dict:
    rom = _rom()
    out, p, cur = {}, EGG_MOVES_OFFSET, None
    while True:
        v = struct.unpack_from("<H", rom, p)[0]
        if v == 0xFFFF:
            return out
        if v >= EGG_MOVES_SPECIES_OFFSET:
            cur = out.setdefault(v - EGG_MOVES_SPECIES_OFFSET, [])
        else:
            cur.append(v)
        p += 2


def egg_moves(species_id: int) -> tuple:
    """Move ids the blue nurse's egg tutor offers the species, in table order, looked up by its first stage."""
    if not 0 <= species_id < SPECIES_COUNT:
        raise ValueError(f"species id out of range: {species_id}")
    return tuple(_egg_move_blocks().get(first_stage(species_id), ()))


@lru_cache(maxsize=None)
def tm_learnset(species_id: int) -> frozenset:
    """Item ids of the TMs and HMs the species can learn."""
    if not 0 <= species_id < SPECIES_COUNT:
        raise ValueError(f"species id out of range: {species_id}")
    rom = _rom()
    p = struct.unpack_from("<I", rom, TM_LEARNSETS_OFFSET + 4 * species_id)[0]
    if p < ROM_BASE:
        return frozenset()
    p -= ROM_BASE
    out = []
    while rom[p] != 0xFF:
        out.append(ITEM_TM01 + rom[p])
        p += 1
    return frozenset(out)


@lru_cache(maxsize=1)
def type_chart() -> list:
    rom = _rom()
    vals = struct.unpack_from(f"<{NUM_TYPES * NUM_TYPES}H", rom, TYPE_CHART_OFFSET)
    return [[vals[a * NUM_TYPES + d] / 4096 for d in range(NUM_TYPES)] for a in range(NUM_TYPES)]


def effectiveness(attack_type: int, defender_types) -> float:
    chart = type_chart()
    mult = 1.0
    seen = set()
    for t in defender_types:
        if t in seen or t >= NUM_TYPES:
            continue
        seen.add(t)
        mult *= chart[attack_type][t]
    return mult


def _fo(addr: int) -> int:
    return addr - ROM_BASE


def _in_rom(addr: int) -> bool:
    return ROM_BASE <= addr < ROM_BASE + len(_rom())


def map_header(group: int, num: int) -> int | None:
    """File offset of the MapHeader for (group, num), or None when it resolves off-ROM."""
    if not 0 <= group < MAP_GROUP_COUNT:
        return None
    grp = struct.unpack_from("<I", _rom(), _fo(MAP_GROUPS) + group * 4)[0]
    if not _in_rom(grp):
        return None
    hdr = struct.unpack_from("<I", _rom(), _fo(grp) + num * 4)[0]
    return _fo(hdr) if _in_rom(hdr) else None


def map_count(group: int) -> int:
    """Headers in one group array, from the spacing of consecutive group pointers; the last
    group runs to its first word that is not a ROM address."""
    rom = _rom()
    grps = [struct.unpack_from("<I", rom, _fo(MAP_GROUPS) + g * 4)[0] for g in range(MAP_GROUP_COUNT)]
    if group + 1 < MAP_GROUP_COUNT:
        return (grps[group + 1] - grps[group]) // 4
    n = 0
    while n < MAP_GROUP_SCAN_CAP and _in_rom(struct.unpack_from("<I", rom, _fo(grps[group]) + n * 4)[0]):
        n += 1
    return n


# script command lengths (operand bytes after the opcode) for the ON_RESUME / ON_DIVE_WARP
# scripts that set a surface point: getplayerxy, compare_var_to_value, goto_if, goto, setdivewarp,
# end. setdivewarp is 0x40, unshifted from vanilla; the rest of the command table is not needed
# because an unknown opcode just ends that branch of the walk.
_SCRIPT_CMD_LEN = {0x42: 4, 0x21: 4, 0x06: 5, 0x05: 4, 0x40: 7, 0x02: 0}
SETDIVEWARP = 0x40
DIVE_SCRIPT_TYPES = frozenset({5, 6})  # MAP_SCRIPT_ON_RESUME, MAP_SCRIPT_ON_DIVE_WARP


def _warp_in_layout(group: int, num: int, x: int, y: int) -> bool:
    """A setdivewarp destination that names a real map and a tile on its layout, or the (-1, -1)
    that reuses the warp's own coordinate; a misread yields coords off the layout and is dropped."""
    if (x, y) == (-1, -1):
        return map_header(group, num) is not None
    c = map_cells(group, num)
    return c is not None and 0 <= x < c[0] and 0 <= y < c[1]


def _divewarp_targets(script_addr: int) -> set:
    """Surface maps of every setdivewarp reached from script_addr, following goto and goto_if.
    A branch that hits an opcode outside _SCRIPT_CMD_LEN ends there, so a target past an unknown
    command is missed rather than misread, and every target is bounds-checked before it counts."""
    rom = _rom()
    out = set()
    work = [_fo(script_addr)]
    seen = set()
    while work:
        a = work.pop()
        while a not in seen:
            seen.add(a)
            op = rom[a]
            if op not in _SCRIPT_CMD_LEN:
                break
            if op == SETDIVEWARP:
                dg, dn = rom[a + 1], rom[a + 2]
                x, y = struct.unpack_from("<hh", rom, a + 4)
                if _warp_in_layout(dg, dn, x, y):
                    out.add((dg, dn))
            if op == 0x06:  # goto_if: condition byte then a u32 target, with a fallthrough
                tgt = struct.unpack_from("<I", rom, a + 2)[0]
                if _in_rom(tgt):
                    work.append(_fo(tgt))
            elif op == 0x05:  # goto: u32 target, no fallthrough
                tgt = struct.unpack_from("<I", rom, a + 1)[0]
                if _in_rom(tgt):
                    work.append(_fo(tgt))
                break
            elif op == 0x02:  # end
                break
            a += 1 + _SCRIPT_CMD_LEN[op]
    return out


@lru_cache(maxsize=1)
def dive_script_edges() -> dict:
    """{map: {surface maps}} from each map's +0x08 map-script table. An ON_RESUME or ON_DIVE_WARP
    script runs setdivewarp to fix where an emerge from that underwater map surfaces, the
    map-to-map link world_edges would otherwise miss because it reads the events and connections
    tables only. Sootopolis is reached this way, (24, 5) -> (0, 7)."""
    rom = _rom()
    out = {}
    for g in range(MAP_GROUP_COUNT):
        for n in range(map_count(g)):
            h = map_header(g, n)
            if h is None:
                continue
            msc = struct.unpack_from("<I", rom, h + MAPHDR_SCRIPTS)[0]
            if not _in_rom(msc):
                continue
            o = _fo(msc)
            for _ in range(MAP_SCRIPT_SCAN_CAP):
                if o + 5 > len(rom) or rom[o] == 0:
                    break
                t, p = rom[o], struct.unpack_from("<I", rom, o + 1)[0]
                if t in DIVE_SCRIPT_TYPES and _in_rom(p):
                    tgts = _divewarp_targets(p)
                    if tgts:
                        out.setdefault((g, n), set()).update(tgts)
                o += 5
    return out


def is_underwater(group: int, num: int) -> bool:
    """A MAP_TYPE_UNDERWATER map, whose deep-water metatiles are the floor the player swims over
    rather than surf-only water nav must mount onto."""
    h = map_header(group, num)
    return h is not None and _rom()[h + MAPHDR_MAP_TYPE] == MAP_TYPE_UNDERWATER


def is_underground(group: int, num: int) -> bool:
    """A MAP_TYPE_UNDERGROUND map: a cave or dungeon floor (Victory Road), outdoors to the indoor
    test yet a leg the walk finishes rather than leaves for an errand."""
    h = map_header(group, num)
    return h is not None and _rom()[h + MAPHDR_MAP_TYPE] == MAP_TYPE_UNDERGROUND


def is_indoor(group: int, num: int) -> bool:
    """A MAP_TYPE_INDOOR map: a gym floor or building interior, the inside of a place rather than
    the town it exits to."""
    h = map_header(group, num)
    return h is not None and _rom()[h + MAPHDR_MAP_TYPE] == MAP_TYPE_INDOOR


MAP_DYNAMIC = (127, 127)  # a dynamic-warp header: the room script fills the real dest at runtime


@lru_cache(maxsize=1)
def world_edges() -> dict:
    """{(group, num): maps one connection, warp, or dive-warp away} for every map in the ROM, so
    a route can be planned to a map nobody has walked yet."""
    out = {}
    dive = dive_script_edges()
    for g in range(MAP_GROUP_COUNT):
        for n in range(map_count(g)):
            dests = {d for _, d in map_connections(g, n)} | {d for *_, d in map_warps(g, n)}
            dests |= dive.get((g, n), set())
            dests.discard(MAP_DYNAMIC)  # not an edge until a script edge names its target
            out.setdefault((g, n), set()).update(dests)
            for d in dests:
                out.setdefault(d, set())
    return out


@lru_cache(maxsize=1)
def passthroughs() -> dict:
    """{map: routes it can drop the player back onto in a different place}: a map whose warps
    to one destination sit far apart (Petalburg Woods, a tunnel) joins two areas of that
    destination, while a house's door pair leads back to where the player came in."""
    out = {}
    for here in world_edges():
        by_dest = {}
        for x, y, d in map_warps(*here):
            by_dest.setdefault(d, []).append((x, y))
        for d, tiles in by_dest.items():
            xs, ys = [t[0] for t in tiles], [t[1] for t in tiles]
            if max(max(xs) - min(xs), max(ys) - min(ys)) >= PASSTHROUGH_SPREAD:
                out.setdefault(here, set()).add(d)
    return out


def map_layout_id(group: int, num: int) -> int | None:
    h = map_header(group, num)
    return None if h is None else struct.unpack_from("<H", _rom(), h + MAPHDR_LAYOUT_ID)[0]


def is_center(group: int, num: int) -> bool:
    return map_layout_id(group, num) == CENTER_LAYOUT_ID


def is_mart(group: int, num: int) -> bool:
    return map_layout_id(group, num) == MART_LAYOUT_ID


def map_music(group: int, num: int) -> int | None:
    h = map_header(group, num)
    return None if h is None else struct.unpack_from("<H", _rom(), h + MAPHDR_MUSIC)[0]


def map_section(group: int, num: int) -> int | None:
    """regionMapSectionId, the mapsec a map belongs to; maps sharing a town or route share it."""
    h = map_header(group, num)
    return None if h is None else _rom()[h + MAPHDR_REGION_SECTION]


def map_section_name(mapsec: int) -> str | None:
    """Name string for a mapsec, read from gRegionMapEntries[mapsec].name. mapsec 0 is
    Littleroot Town; a mapsec whose name pointer resolves off-ROM returns None."""
    rom = _rom()
    o = _fo(REGION_MAP_ENTRIES) + mapsec * REGION_MAP_ENTRY_SIZE
    if not 0 <= o < len(rom) - REGION_MAP_ENTRY_SIZE:
        return None
    ptr = struct.unpack_from("<I", rom, o + 4)[0]
    if not _in_rom(ptr):
        return None
    name = _decode(rom[_fo(ptr):_fo(ptr) + 40])
    return name or None


def map_sections() -> list:
    """(mapsec, name) for every mapsec a map in the ROM references, so maps.mapsec joins to a name."""
    seen = set()
    for group in range(MAP_GROUP_COUNT):
        for num in range(map_count(group)):
            if map_header(group, num) is None:
                continue
            ms = map_section(group, num)
            if ms is not None:
                seen.add(ms)
    out = []
    for ms in sorted(seen):
        name = map_section_name(ms)
        if name:
            out.append((ms, name))
    return out


def map_objects(group: int, num: int) -> list:
    """(x, y, movement, flag) of each object template on the map, read off the ROM header the
    way rowe_map.static_objects reads the live one, so a leader's tile is known before entry."""
    h = map_header(group, num)
    if h is None:
        return []
    ev = struct.unpack_from("<I", _rom(), h + MAPHDR_EVENTS)[0]
    if not _in_rom(ev):
        return []
    nobj = _rom()[_fo(ev)]
    pobj = struct.unpack_from("<I", _rom(), _fo(ev) + 4)[0]
    if not _in_rom(pobj) or not _in_rom(pobj + nobj * OBJ_STRIDE):
        return []
    out = []
    for i in range(nobj):
        o = _fo(pobj) + i * OBJ_STRIDE
        x, y = struct.unpack_from("<hh", _rom(), o + OBJ_X)
        out.append((x, y, _rom()[o + OBJ_MOVEMENT], struct.unpack_from("<H", _rom(), o + OBJ_FLAG)[0]))
    return out


def map_object_scripts(group: int, num: int) -> list:
    """(index, x, y, movement, script_addr) per object template on (group,num): the 1-based object
    number the game uses, the tile it holds, its movement type, and the event script an A-press
    interaction runs. map_objects drops the script pointer; talk_warp needs it to tie a crossing to
    the NPC that triggers it."""
    h = map_header(group, num)
    if h is None:
        return []
    ev = struct.unpack_from("<I", _rom(), h + MAPHDR_EVENTS)[0]
    if not _in_rom(ev):
        return []
    nobj = _rom()[_fo(ev)]
    pobj = struct.unpack_from("<I", _rom(), _fo(ev) + 4)[0]
    if not _in_rom(pobj) or not _in_rom(pobj + nobj * OBJ_STRIDE):
        return []
    out = []
    for i in range(nobj):
        o = _fo(pobj) + i * OBJ_STRIDE
        x, y = struct.unpack_from("<hh", _rom(), o + OBJ_X)
        out.append((i + 1, x, y, _rom()[o + OBJ_MOVEMENT],
                    struct.unpack_from("<I", _rom(), o + OBJ_SCRIPT)[0]))
    return out


WILD_HEADER_STRIDE = 32   # ROWE widened the vanilla 20-byte WildPokemonHeader to seven info pointers
WILD_LAND_PTR = 0x4       # first info pointer in the header, land encounters
WILD_MONS_PTR = 0x4       # WildPokemonInfo: u8 rate, u8 pad[3], then the WildPokemon* at +4
WILD_SLOTS = 12           # land slots per WildPokemonInfo, each {u8 min, u8 max, u16 species}


def _wild_land_span(land: int) -> tuple | None:
    """(min, max) land level across a WildPokemonInfo's slots, or None when the pointer or its
    slots do not read as an encounter table."""
    if not _in_rom(land):
        return None
    mons = struct.unpack_from("<I", _rom(), _fo(land) + WILD_MONS_PTR)[0]
    if not _in_rom(mons) or not _in_rom(mons + WILD_SLOTS * 4):
        return None
    lo, hi = 100, 0
    for i in range(WILD_SLOTS):
        mn, mx, sp = struct.unpack_from("<BBH", _rom(), _fo(mons) + i * 4)
        if not (1 <= mn <= mx <= 100) or sp == 0 or sp >= SPECIES_COUNT:
            return None
        lo, hi = min(lo, mn), max(hi, mx)
    return lo, hi


def _wild_header_valid(o: int) -> bool:
    if o + WILD_HEADER_STRIDE > len(_rom()):
        return False
    g, nm, pad = _rom()[o], _rom()[o + 1], struct.unpack_from("<H", _rom(), o + 2)[0]
    if g >= MAP_GROUP_COUNT or nm >= 120 or pad != 0:
        return False
    ptrs = struct.unpack_from("<7I", _rom(), o + WILD_LAND_PTR)
    if not any(_in_rom(p) for p in ptrs):
        return False
    return all(p == 0 or _in_rom(p) for p in ptrs)


@lru_cache(maxsize=1)
def wild_land_levels() -> dict:
    """{(group, num): (min, max)} land encounter levels, off gWildMonHeaders. The table is found
    as the longest run of valid headers at the ROWE stride, so the offset is not pinned to one
    ROM build; levels are the unscaled ROM curve, which ROWE multiplies by badge count at
    runtime, so the planner ranks by it but step 10 checks it against the live battle log."""
    rom = _rom()
    best_start, best_run = 0, 0
    o = 0
    while o + WILD_HEADER_STRIDE <= len(rom):
        if _wild_header_valid(o) and (o < WILD_HEADER_STRIDE or not _wild_header_valid(o - WILD_HEADER_STRIDE)):
            run, q = 0, o
            while _wild_header_valid(q):
                run += 1
                q += WILD_HEADER_STRIDE
            if run > best_run:
                best_start, best_run = o, run
        o += 4
    out = {}
    for i in range(best_run):
        h = best_start + i * WILD_HEADER_STRIDE
        land = struct.unpack_from("<I", rom, h + WILD_LAND_PTR)[0]
        span = _wild_land_span(land)
        if span:
            out[(rom[h], rom[h + 1])] = span
    return out


def _wild_header_table() -> tuple:
    """(start_offset, count) of gWildMonHeaders, the longest run of valid headers at the stride."""
    rom = _rom()
    best_start, best_run, o = 0, 0, 0
    while o + WILD_HEADER_STRIDE <= len(rom):
        if _wild_header_valid(o) and (o < WILD_HEADER_STRIDE or not _wild_header_valid(o - WILD_HEADER_STRIDE)):
            run, q = 0, o
            while _wild_header_valid(q):
                run += 1
                q += WILD_HEADER_STRIDE
            if run > best_run:
                best_start, best_run = o, run
        o += 4
    return best_start, best_run


WILD_CATEGORY_COUNT = 7   # the widened header carries 7 WildPokemonInfo pointers after its 4-byte
# head. Category 0 reads 12 slots and matches the proven land table; category 4 reads 10, the
# vanilla fishing count. The other five are populated and read by the same per-slot validator;
# their surface meaning (surf, rock smash, a day/night split) is not pinned to a name here.
WILD_SLOT_CAP = 16


@lru_cache(maxsize=1)
def wild_encounters() -> list:
    """[(group, num, category, slot, min_level, max_level, species)] for every encounter slot on
    every map. category is the 0-6 WildPokemonInfo index. Slots are read while each validates as a
    {1<=min<=max<=100, in-range species} row, so a short real table stops at its end and the read
    never runs past the array into the next one."""
    rom = _rom()
    start, count = _wild_header_table()
    out = []
    for i in range(count):
        h = start + i * WILD_HEADER_STRIDE
        g, nm = rom[h], rom[h + 1]
        ptrs = struct.unpack_from(f"<{WILD_CATEGORY_COUNT}I", rom, h + WILD_LAND_PTR)
        for cat, p in enumerate(ptrs):
            if not (p and _in_rom(p)):
                continue
            mons = struct.unpack_from("<I", rom, _fo(p) + WILD_MONS_PTR)[0]
            if not _in_rom(mons):
                continue
            mo = _fo(mons)
            for slot in range(WILD_SLOT_CAP):
                mn, mx, sp = struct.unpack_from("<BBH", rom, mo + slot * 4)
                if not (1 <= mn <= mx <= 100 and 0 < sp < SPECIES_COUNT):
                    break
                out.append((g, nm, cat, slot, mn, mx, sp))
    return out


@lru_cache(maxsize=1)
def gym_maps() -> frozenset:
    """Every map whose music is the gym track, so the planner's ladder is keyed to the ROM, not
    a hand-list. Includes inner floors beyond the eight entrances; the planner intersects with
    the entrance maps it carries a badge offset for."""
    return frozenset((g, n) for g in range(MAP_GROUP_COUNT) for n in range(map_count(g))
                     if map_music(g, n) == GYM_MUSIC)


def map_connection_links(group: int, num: int) -> list:
    """(direction, offset, (group, num)) for each map bordering (group, num) in the overworld. The
    offset shifts a border tile onto the neighbour: x on a north or south edge lands at x - offset,
    y on a west or east edge at y - offset."""
    h = map_header(group, num)
    if h is None:
        return []
    conn = struct.unpack_from("<I", _rom(), h + MAPHDR_CONNECTIONS)[0]
    if not _in_rom(conn):
        return []
    n, p = struct.unpack_from("<II", _rom(), _fo(conn))
    # placeholder maps carry a header whose connection word points at unrelated data
    if n > MAX_CONNECTIONS or not _in_rom(p) or not _in_rom(p + n * 12):
        return []
    out = []
    for i in range(n):
        d, off, g, nm = struct.unpack_from("<IiBB", _rom(), _fo(p) + i * 12)
        out.append((d, off, (g, nm)))
    return out


def map_connections(group: int, num: int) -> list:
    """(direction, (group, num)) for each map bordering (group, num) in the overworld."""
    return [(d, dest) for d, _off, dest in map_connection_links(group, num)]


def map_warps(group: int, num: int) -> list:
    """(x, y, (dest_group, dest_num)) for each warp tile on (group, num)."""
    h = map_header(group, num)
    if h is None:
        return []
    ev = struct.unpack_from("<I", _rom(), h + MAPHDR_EVENTS)[0]
    if not _in_rom(ev):
        return []
    nwarp = _rom()[_fo(ev) + MAPEVENTS_WARP_COUNT]
    pwarp = struct.unpack_from("<I", _rom(), _fo(ev) + MAPEVENTS_WARP_PTR)[0]
    if not _in_rom(pwarp) or not _in_rom(pwarp + nwarp * WARP_STRIDE):
        return []
    out = []
    for i in range(nwarp):
        o = _fo(pwarp) + i * WARP_STRIDE
        x, y = struct.unpack_from("<hh", _rom(), o)
        out.append((x, y, (_rom()[o + WARP_MAP_GROUP], _rom()[o + WARP_MAP_NUM])))
    return out


def map_warp_links(group: int, num: int) -> list:
    """(x, y, (dest_group, dest_num), dest_warp) per warp tile: `dest_warp` indexes the destination
    map's own warp table, the tile the player lands on."""
    h = map_header(group, num)
    if h is None:
        return []
    ev = struct.unpack_from("<I", _rom(), h + MAPHDR_EVENTS)[0]
    if not _in_rom(ev):
        return []
    nwarp = _rom()[_fo(ev) + MAPEVENTS_WARP_COUNT]
    pwarp = struct.unpack_from("<I", _rom(), _fo(ev) + MAPEVENTS_WARP_PTR)[0]
    if not _in_rom(pwarp) or not _in_rom(pwarp + nwarp * WARP_STRIDE):
        return []
    out = []
    for i in range(nwarp):
        o = _fo(pwarp) + i * WARP_STRIDE
        x, y, _elevation, dest_warp = struct.unpack_from("<hhBB", _rom(), o)
        out.append((x, y, (_rom()[o + WARP_MAP_GROUP], _rom()[o + WARP_MAP_NUM]), dest_warp))
    return out


def map_cells(group: int, num: int) -> tuple | None:
    """(width, height, cells) of a map's layout, cells in the gBackupMapLayout word format
    the game copies them into, so a map's walkable regions are known before it is entered."""
    h = map_header(group, num)
    if h is None:
        return None
    lay = struct.unpack_from("<I", _rom(), h + MAPHDR_LAYOUT)[0]
    if not _in_rom(lay):
        return None
    w, hgt, _border, data = struct.unpack_from("<iiII", _rom(), _fo(lay))
    if not (0 < w * hgt <= MAX_MAP_CELLS and _in_rom(data) and _in_rom(data + w * hgt * 2)):
        return None
    return w, hgt, struct.unpack_from(f"<{w * hgt}H", _rom(), _fo(data))


# metatile attributes are a u16 per metatile; the behavior is the low 9 bits. A u32 read
# merges two adjacent attributes and collapses every behavior to the lower tile's, which read
# water and grass alike as 0 and left elev-1 grass fields indistinguishable from water.
_ATTR_STRIDE = 2
METATILE_BEHAVIOR_MASK = 0x1FF
# ROWE's primary tileset holds 0x800 metatiles under its 12-bit ids and a secondary id counts
# from there. The tileset struct carries no count, and this ROM's metatile and attribute arrays
# are not contiguous, so a count derived from their pointer gap came out at 16.
PRIMARY_METATILES = 0x800


def metatile_behavior(group: int, num: int):
    """A function mapping a map cell's metatile id to its behavior, resolving the map's primary
    and secondary tileset attribute tables, or None when the layout is unreadable. Ids below
    PRIMARY_METATILES index the primary table, the rest index the secondary."""
    h = map_header(group, num)
    if h is None:
        return None
    lay = struct.unpack_from("<I", _rom(), h + MAPHDR_LAYOUT)[0]
    if not _in_rom(lay):
        return None
    prim, sec = struct.unpack_from("<II", _rom(), _fo(lay) + 16)
    if not (_in_rom(prim) and _in_rom(sec)):
        return None
    prim_attrs = struct.unpack_from("<I", _rom(), _fo(prim) + 16)[0]
    sec_attrs = struct.unpack_from("<I", _rom(), _fo(sec) + 16)[0]

    @lru_cache(maxsize=None)
    def behavior(metatile_id: int) -> int:
        base, idx = (prim_attrs, metatile_id) if metatile_id < PRIMARY_METATILES else (sec_attrs, metatile_id - PRIMARY_METATILES)
        a = base + idx * _ATTR_STRIDE
        if not _in_rom(a):
            return -1
        return struct.unpack_from("<H", _rom(), _fo(a))[0] & METATILE_BEHAVIOR_MASK

    return behavior


# gTrainers in this build: 64-byte structs, mixed-case name at +4 (0xFF terminated), party pointer at
# +40, party row count at +60; a party row is 40 bytes w/ the level marker at +0 and species at +10.
# The first struct carrying a leader's name is the gym fight; later ones at 0x40 steps are rematches.
TRAINER_STRUCT_SIZE = 0x40
TRAINER_NAME_OFF, TRAINER_PARTY_OFF, TRAINER_COUNT_OFF = 4, 40, 60
TRAINER_ROW_SIZE, TRAINER_ROW_SPECIES = 40, 10
# leader base level per badge count, fitted on the logged fights: Roxanne 16 at 1, Norman 20 at 2,
# Wattson 23 at 3, Winona 26 at 4, Tate & Liza 29-30 at 5. CAPS - 6 from 2 badges on, CAPS - 5 at 1.
LEADER_CAPS = [16, 21, 26, 29, 32, 36, 39, 42, 45]
LEADER_BASE_LEVEL = [10, 16, 20, 23, 26, 30, 33, 36, 39]
# party size per badge count: 4 logged at 3, 4 and 5 badges; 6+ is assumed until a fight shows it
LEADER_COUNT = [3, 3, 3, 4, 4, 4, 5, 5, 6]
LEADER_ACE_ROW = 5
LEADER_PAIR_ROWS = {"Tate&Liza": (4, 5)}  # the double battle fields rows 4 and 5 last instead of the ace alone
# badge-flag order; the gym structs sit at 0x3fe918 onward in this order, the League's just before them
LEADERS = ["Roxanne", "Brawly", "Wattson", "Flannery", "Norman", "Winona", "Tate&Liza", "Juan"]
LEAGUE = ["Sidney", "Phoebe", "Glacia", "Drake", "Wallace"]
LEAGUE_BADGES = 8


def _encode_text(s: str) -> bytes:
    out = []
    for c in s:
        if c.isupper():
            out.append(0xBB + ord(c) - 65)
        elif c.islower():
            out.append(0xD5 + ord(c) - 97)
        elif c == "&":
            out.append(0x2D)
        else:
            raise ValueError(f"unencodable trainer name char {c!r}")
    return bytes(out) + b"\xff"


@lru_cache(maxsize=None)
def trainer_struct(name: str) -> int:
    """ROM offset of the first gTrainers struct named `name` (the gym fight, not a rematch)."""
    rom = _rom()
    i = rom.find(_encode_text(name))
    if i == -1:
        raise ValueError(f"no trainer named {name!r} in the ROM")
    return i - TRAINER_NAME_OFF


def trainer_pool(name: str) -> list:
    """Species ids of the trainer's party rows in table order, the pool the build draws from."""
    rom = _rom()
    base = trainer_struct(name)
    ptr = struct.unpack_from("<I", rom, base + TRAINER_PARTY_OFF)[0]
    if not _in_rom(ptr):
        raise ValueError(f"trainer {name!r} party pointer {ptr:#x} is outside the ROM")
    po = _fo(ptr)
    out = []
    for j in range(rom[base + TRAINER_COUNT_OFF]):
        sp = struct.unpack_from("<H", rom, po + j * TRAINER_ROW_SIZE + TRAINER_ROW_SPECIES)[0]
        if not 0 < sp < SPECIES_COUNT:
            raise ValueError(f"trainer {name!r} row {j} species {sp} out of range")
        out.append(sp)
    return out


def leader_team(name: str, badges: int) -> list:
    """[(species, level)] a gym leader fields at `badges`: the first LEADER_COUNT-1 pool rows in order
    plus the ace row last, each at LEADER_BASE_LEVEL + slot. Species are the pool's rows as stored;
    the game evolves a row to the stage its level allows, which the caller resolves."""
    pool = trainer_pool(name)
    count = LEADER_COUNT[badges]
    last = [pool[r] for r in LEADER_PAIR_ROWS.get(name, (LEADER_ACE_ROW,))]
    rows = pool[: count - len(last)] + last
    base = LEADER_BASE_LEVEL[badges]
    return [(sp, base + i) for i, sp in enumerate(rows)]


def leader_build(name: str, badges: int) -> list:
    """[(species, level)] as fielded: leader_team's rows evolved to the stage each level allows."""
    return [(species_at_level(sp, lvl), lvl) for sp, lvl in leader_team(name, badges)]


# the post-game bosses in planner.POSTGAME order, one gTrainers struct of six L100 rows each
BOSSES = ["Steven", "Red"]


def boss_build(name: str) -> list:
    """[(species, level)] a post-game boss fields: the rows as stored, final forms already, w/ the
    level byte at +0 of each, so the scorers see the L100 six instead of a leader-ladder level."""
    pool = trainer_pool(name)
    rom = _rom()
    po = _fo(struct.unpack_from("<I", rom, trainer_struct(name) + TRAINER_PARTY_OFF)[0])
    return [(sp, rom[po + j * TRAINER_ROW_SIZE]) for j, sp in enumerate(pool)]


# the 8 Sevii-island leaders giving badges 9-16 (flags rowe_symbols.JOHTO_BADGE01 onward); their
# gTrainers structs run contiguously from Falkner's at TRAINER_STRUCT_SIZE steps, in this order
SEVII_LEADERS = ["Falkner", "Bugsy", "Whitney", "Morty", "Chuck", "Jasmine", "Pryce", "Clair"]


def sevii_leader_pools() -> list:
    """[(name, [species])] for the 8 Sevii-island leaders. Read by offset off Falkner's struct, not
    by name, because 'Jasmine' collides with an earlier trainer of the same name; the name at each
    step is checked so a non-contiguous block fails loud instead of feeding wrong species. ROWE
    scales their levels to the player's badge count at battle time, so no static level is stored."""
    rom = _rom()
    base = trainer_struct(SEVII_LEADERS[0])
    out = []
    for i, name in enumerate(SEVII_LEADERS):
        b = base + i * TRAINER_STRUCT_SIZE
        if not rom.startswith(_encode_text(name), b + TRAINER_NAME_OFF):
            raise ValueError(f"sevii leader slot {i} is not {name!r}; the gTrainers block moved")
        ptr = struct.unpack_from("<I", rom, b + TRAINER_PARTY_OFF)[0]
        if not _in_rom(ptr):
            raise ValueError(f"sevii leader {name} party pointer {ptr:#x} is outside the ROM")
        po = _fo(ptr)
        pool = []
        for j in range(rom[b + TRAINER_COUNT_OFF]):
            sp = struct.unpack_from("<H", rom, po + j * TRAINER_ROW_SIZE + TRAINER_ROW_SPECIES)[0]
            if not 0 < sp < SPECIES_COUNT:
                raise ValueError(f"sevii leader {name} row {j} species {sp} out of range")
            pool.append(sp)
        out.append((name, pool))
    return out


# operand bytes after each 1-byte script opcode, the vanilla pokeemerald command table
# (pret/pokeemerald asm/macros/event.inc + data/script_cmd_table.inc); ROWE keeps vanilla script
# numbering, confirmed by the dive walker above and by gtrainers_base's leader control. An opcode
# absent here ends a walk branch rather than risk a wrong stride. trainerbattle (0x5C) is not in the
# table: its length varies with the type byte, so the walk records its trainer id and stops there.
_CMD_OPERAND_LEN = {
    0: 0, 1: 0, 2: 0, 3: 0, 4: 4, 5: 4, 6: 5, 7: 5, 8: 1, 9: 1, 10: 2, 11: 2, 12: 0, 13: 0, 14: 1,
    15: 5, 16: 2, 17: 5, 18: 5, 19: 5, 20: 2, 21: 8, 23: 4, 24: 4, 26: 4, 27: 2, 28: 2, 29: 5, 30: 5,
    31: 5, 32: 8, 33: 4, 34: 4, 35: 4, 36: 4, 40: 2, 41: 2, 42: 2, 43: 2, 44: 4, 45: 0, 46: 0, 47: 2,
    48: 0, 49: 2, 50: 0, 51: 3, 52: 2, 53: 0, 54: 2, 55: 1, 56: 1, 57: 0, 58: 0, 59: 0, 60: 0, 61: 0,
    62: 0, 63: 0, 64: 0, 65: 0, 66: 4, 67: 0, 68: 4, 69: 4, 70: 4, 71: 4, 72: 2, 73: 4, 74: 4, 75: 2,
    76: 2, 77: 2, 78: 2, 87: 6, 88: 4, 89: 4, 90: 0, 91: 3, 93: 0, 94: 0, 95: 0, 96: 2, 97: 2, 98: 2,
    99: 6, 100: 2, 101: 3, 102: 0, 103: 4, 104: 0, 105: 0, 106: 0, 107: 0, 108: 0, 109: 0, 110: 2,
    111: 4, 112: 5, 113: 5, 114: 0, 115: 4, 116: 4, 117: 4, 118: 0, 119: 1, 120: 4, 121: 14, 122: 2,
    123: 4, 124: 2, 125: 2, 126: 0, 127: 2, 128: 2, 129: 2, 130: 2, 131: 2, 132: 2, 133: 4, 134: 4,
    135: 4, 136: 4, 137: 2, 138: 3, 139: 0, 140: 0, 141: 0, 142: 0, 143: 2, 144: 5, 145: 5, 146: 5,
    147: 3, 148: 2, 149: 3, 150: 2, 151: 1, 152: 2, 153: 2, 154: 1, 155: 4, 156: 2, 157: 3, 158: 2,
    159: 2, 160: 0, 161: 4, 162: 8, 163: 0, 164: 2, 165: 0, 166: 1, 167: 2, 168: 3, 169: 2, 170: 8,
    171: 2, 172: 4, 173: 4, 174: 0, 175: 4, 176: 4, 177: 7, 178: 0, 179: 2, 180: 2, 181: 2, 182: 5,
    183: 0, 184: 4, 185: 4, 186: 4, 187: 5, 188: 5, 189: 4, 190: 4, 191: 4, 192: 2, 193: 2, 194: 2,
    195: 1, 196: 0, 197: 0, 198: 2, 199: 1, 200: 4, 201: 0, 202: 0, 203: 0, 204: 5, 205: 2, 206: 2,
    207: 0, 208: 2, 209: 0, 210: 3, 211: 2, 212: 0, 213: 2, 214: 0, 215: 0, 216: 0, 217: 0, 218: 0,
    219: 4, 220: 1, 221: 2, 222: 2, 223: 4, 224: 0, 225: 2, 226: 4,
}
_SCR_END, _SCR_RETURN, _SCR_CALL, _SCR_GOTO, _SCR_GOTO_IF, _SCR_CALL_IF = 2, 3, 4, 5, 6, 7
TRAINERBATTLE_OP = 0x5C

# leader -> its gym map (group, num), the known-good control that pins gTrainers' base: the base is
# the one offset for which every leader's struct divides to a trainer id that its own gym map's
# object scripts invoke. Tate&Liza are omitted; their stored name does not match by raw text.
_HOENN_GYM_MAP = {"Roxanne": (11, 3), "Brawly": (3, 3), "Wattson": (10, 0), "Flannery": (4, 1),
                  "Norman": (8, 1), "Winona": (12, 1), "Juan": (15, 0)}


def _script_trainer_ids(addr: int) -> set:
    """Trainer ids reached from a script address, following goto/call/goto_if/call_if with the
    vanilla length table. A branch ends at end/return, at an opcode outside the table, or right
    after a trainerbattle (whose id it records first)."""
    rom = _rom()
    found, seen, stack = set(), set(), [addr]
    while stack:
        a = stack.pop()
        while _in_rom(a) and a not in seen:
            seen.add(a)
            fa = _fo(a)
            op = rom[fa]
            if op == TRAINERBATTLE_OP:
                found.add(struct.unpack_from("<H", rom, fa + 2)[0])
                break
            if op in (_SCR_END, _SCR_RETURN):
                break
            if op == _SCR_GOTO:
                a = struct.unpack_from("<I", rom, fa + 1)[0]
                continue
            if op == _SCR_CALL:
                stack.append(struct.unpack_from("<I", rom, fa + 5)[0])
                a = struct.unpack_from("<I", rom, fa + 1)[0]
                continue
            if op in (_SCR_GOTO_IF, _SCR_CALL_IF):
                stack.append(struct.unpack_from("<I", rom, fa + 2)[0])
                a += 1 + _CMD_OPERAND_LEN[op]
                continue
            if op not in _CMD_OPERAND_LEN:
                break
            a += 1 + _CMD_OPERAND_LEN[op]
    return found


def _map_trainer_tiles(group: int, num: int) -> dict:
    """{trainer_id: (x, y)} for every object on (group, num) whose event script runs a battle."""
    out = {}
    for _idx, x, y, _mv, script in map_object_scripts(group, num):
        for tid in _script_trainer_ids(script):
            out.setdefault(tid, (x, y))
    return out


@lru_cache(maxsize=None)
def gtrainers_base() -> int:
    """File offset of gTrainers[0]. Derived, not symboled: for each trainerbattle id on Roxanne's
    gym map a candidate base = her struct - id*0x40 is scored against the other leaders, and the
    base that maps the most leaders' structs to an id their own gym runs wins. Raises unless at
    least four leaders agree, so a moved table fails loud instead of returning a wrong id."""
    structs, gym_ids = {}, {}
    for name, (g, num) in _HOENN_GYM_MAP.items():
        structs[name] = trainer_struct(name)
        gym_ids[name] = _map_trainer_tiles(g, num)
    best = None
    for x in gym_ids["Roxanne"]:
        base = structs["Roxanne"] - x * TRAINER_STRUCT_SIZE
        if base < 0:
            continue
        hits = [n for n in structs
                if (structs[n] - base) % TRAINER_STRUCT_SIZE == 0
                and (structs[n] - base) // TRAINER_STRUCT_SIZE in gym_ids[n]]
        if best is None or len(hits) > len(best[1]):
            best = (base, hits)
    if best is None or len(best[1]) < 4:
        raise ValueError("gTrainers base not confirmed by the Hoenn leader control")
    return best[0]


def sevii_leader_locations() -> list:
    """[(name, group, num, x, y) or (name, None, None, None, None)] for the 8 Sevii leaders. Their
    trainer ids come off Falkner's struct through the derived gTrainers base; every map's object
    scripts are scanned for those ids to recover the tile each leader stands on."""
    base = gtrainers_base()
    falk = trainer_struct(SEVII_LEADERS[0])
    ids = {(falk + i * TRAINER_STRUCT_SIZE - base) // TRAINER_STRUCT_SIZE: nm
           for i, nm in enumerate(SEVII_LEADERS)}
    located = {}
    for g in range(MAP_GROUP_COUNT):
        for num in range(map_count(g)):
            if map_header(g, num) is None:
                continue
            tiles = _map_trainer_tiles(g, num)
            for tid in ids:
                if tid in tiles and tid not in located:
                    located[tid] = (g, num, *tiles[tid])
    out = []
    for tid, nm in sorted(ids.items()):
        if tid in located:
            g, num, x, y = located[tid]
            out.append((nm, g, num, x, y))
        else:
            out.append((nm, None, None, None, None))
    return out


def trainer_name(trainer_id: int) -> str:
    """Name on the gTrainers struct at the derived base for this id, empty past the table."""
    o = gtrainers_base() + trainer_id * TRAINER_STRUCT_SIZE + TRAINER_NAME_OFF
    return _decode(_rom()[o:o + 12])


def all_trainer_tiles() -> list:
    """[(trainer_id, name, group, num, x, y)] for every trainer whose battle a map object script
    runs, the first tile found for each id. Generalizes sevii_leader_locations to the whole roster,
    so the db carries where each opponent stands, not just the eight Sevii leaders."""
    located = {}
    for g in range(MAP_GROUP_COUNT):
        for num in range(map_count(g)):
            if map_header(g, num) is None:
                continue
            for tid, (x, y) in _map_trainer_tiles(g, num).items():
                located.setdefault(tid, (g, num, x, y))
    return [(tid, trainer_name(tid), *located[tid]) for tid in sorted(located)]


def _script_item_given(addr: int) -> int | None:
    """The item an object script hands over, read off the first setorcopyvar into VAR_0x8000,
    following goto/call/goto_if the same way the trainer walk does. None when no such write runs."""
    rom = _rom()
    seen, stack = set(), [addr]
    while stack:
        a = stack.pop()
        while _in_rom(a) and a not in seen:
            seen.add(a)
            fa = _fo(a)
            op = rom[fa]
            if op == SETORCOPYVAR_OP and struct.unpack_from("<H", rom, fa + 1)[0] == VAR_RECEIVED_ITEM:
                return struct.unpack_from("<H", rom, fa + 3)[0]
            if op in (_SCR_END, _SCR_RETURN):
                break
            if op == _SCR_GOTO:
                a = struct.unpack_from("<I", rom, fa + 1)[0]
                continue
            if op == _SCR_CALL:
                stack.append(struct.unpack_from("<I", rom, fa + 5)[0])
                a = struct.unpack_from("<I", rom, fa + 1)[0]
                continue
            if op in (_SCR_GOTO_IF, _SCR_CALL_IF):
                stack.append(struct.unpack_from("<I", rom, fa + 2)[0])
                a += 1 + _CMD_OPERAND_LEN[op]
                continue
            if op not in _CMD_OPERAND_LEN:
                break
            a += 1 + _CMD_OPERAND_LEN[op]
    return None


def field_items() -> list:
    """[(group, num, x, y, kind, item, flag)] for every item placed on a map. kind 'ball' is an
    object the player opens, its item read from the script, flag None. kind 'hidden' is a BgEvent
    the player searches out, its item and hidden-item flag read straight from the event struct."""
    out = []
    for g in range(MAP_GROUP_COUNT):
        for num in range(map_count(g)):
            h = map_header(g, num)
            if h is None:
                continue
            for _i, x, y, _mv, script in map_object_scripts(g, num):
                item = _script_item_given(script)
                if item and item < ITEM_COUNT and item_name(item).strip():
                    out.append((g, num, x, y, "ball", item, None))
            ev = struct.unpack_from("<I", _rom(), h + MAPHDR_EVENTS)[0]
            if not _in_rom(ev):
                continue
            cnt = _rom()[_fo(ev) + MAPEVENTS_BG_COUNT]
            p = struct.unpack_from("<I", _rom(), _fo(ev) + MAPEVENTS_BG_PTR)[0]
            if not _in_rom(p) or not _in_rom(p + cnt * BG_STRIDE):
                continue
            for i in range(cnt):
                o = _fo(p) + i * BG_STRIDE
                if _rom()[o + 5] != BG_HIDDEN_ITEM_KIND:
                    continue
                x, y = struct.unpack_from("<hh", _rom(), o)
                item = struct.unpack_from("<H", _rom(), o + 8)[0]
                flag = struct.unpack_from("<H", _rom(), o + 10)[0] & 0x0FFF
                out.append((g, num, x, y, "hidden", item, flag))
    return out


CHECKFLAG_OP = 0x2B


def _walk_script_ops(addr: int):
    """Yield (opcode, file_offset) for every command reached from a script address, following
    goto/call/goto_if/call_if. A branch stops at end/return or at any opcode absent from the
    length table, trainerbattle (0x5C) among them, so a battle ends its branch as the trainer walk
    expects. A reusable primitive for the flag/item scans that only need to see each command."""
    rom = _rom()
    seen, stack = set(), [addr]
    while stack:
        a = stack.pop()
        while _in_rom(a) and a not in seen:
            seen.add(a)
            fa = _fo(a)
            op = rom[fa]
            yield op, fa
            if op in (_SCR_END, _SCR_RETURN):
                break
            if op == _SCR_GOTO:
                a = struct.unpack_from("<I", rom, fa + 1)[0]
                continue
            if op == _SCR_CALL:
                stack.append(struct.unpack_from("<I", rom, fa + 5)[0])
                a = struct.unpack_from("<I", rom, fa + 1)[0]
                continue
            if op in (_SCR_GOTO_IF, _SCR_CALL_IF):
                stack.append(struct.unpack_from("<I", rom, fa + 2)[0])
                a += 1 + _CMD_OPERAND_LEN[op]
                continue
            if op not in _CMD_OPERAND_LEN:
                break
            a += 1 + _CMD_OPERAND_LEN[op]


def _map_script_ptrs(group: int, num: int) -> list:
    """Script pointers in a map's map-script table: a bare u32 for most entry types, and the
    per-entry pointers inside the var-conditional tables (types 2 and 4)."""
    rom = _rom()
    h = map_header(group, num)
    if h is None:
        return []
    t = struct.unpack_from("<I", rom, h + MAPHDR_SCRIPTS)[0]
    if not _in_rom(t):
        return []
    out, o = [], _fo(t)
    for _ in range(MAP_SCRIPT_SCAN_CAP):
        typ = rom[o]
        if typ == 0:
            break
        if typ in (2, 4):
            tb = struct.unpack_from("<I", rom, o + 1)[0]
            if _in_rom(tb):
                to = _fo(tb)
                for _j in range(32):
                    if struct.unpack_from("<H", rom, to)[0] == 0:
                        break
                    p = struct.unpack_from("<I", rom, to + 4)[0]
                    if _in_rom(p):
                        out.append(p)
                    to += 8
        else:
            p = struct.unpack_from("<I", rom, o + 1)[0]
            if _in_rom(p):
                out.append(p)
        o += 5
    return out


def badge_flags() -> list:
    """[(badge, flag, region, leader)] for the 16 badges. Flags come from rowe_symbols, the values
    play.py reads off the save; badge is 0-based (badge 0 is the first), region 'hoenn' for 0-7 and
    'sevii' for 8-15, leader the trainer who awards it."""
    import rowe_symbols as sym
    out = [(i, sym.FLAG_BADGE01 + i, "hoenn", LEADERS[i]) for i in range(8)]
    out += [(8 + i, sym.JOHTO_BADGE01 + i, "sevii", SEVII_LEADERS[i]) for i in range(8)]
    return out


def badge_gate_maps() -> list:
    """[(group, num, badge)] for every map whose object or map scripts run a checkflag on a badge
    flag, the ROM-verifiable signal that the map gates on that badge. Each gym map checks its own
    badge and each Sevii leader room checks the badge it awards, which is the control."""
    flag_badge = {flag: badge for badge, flag, _r, _l in badge_flags()}
    hits = {}
    for g in range(MAP_GROUP_COUNT):
        for num in range(map_count(g)):
            if map_header(g, num) is None:
                continue
            scripts = [s for _i, _x, _y, _mv, s in map_object_scripts(g, num)]
            scripts += _map_script_ptrs(g, num)
            for s in scripts:
                for op, fa in _walk_script_ops(s):
                    if op == CHECKFLAG_OP:
                        fl = struct.unpack_from("<H", _rom(), fa + 1)[0]
                        if fl in flag_badge:
                            hits.setdefault((g, num), set()).add(flag_badge[fl])
    return sorted((g, num, b) for (g, num), bs in hits.items() for b in bs)


def self_check() -> None:
    pound = move(1)
    if (pound.name, pound.power, pound.type, pound.pp) != ("Pound", 40, 0, 35):
        raise RuntimeError(f"move table fingerprint failed: {pound}")
    if type_chart()[10][12] != 2.0 or type_chart()[3][8] != 0.0:
        raise RuntimeError("type chart fingerprint failed")
    bulba = species(1)
    if (bulba.base_stats, bulba.types, bulba.catch_rate) != ((45, 49, 49, 45, 65, 65), (12, 3), 45):
        raise RuntimeError(f"species table fingerprint failed: {bulba}")
    if bulba.abilities != (ability_id("Overgrow"), ability_id("Solar Power"), ability_id("Chlorophyll")):
        raise RuntimeError(f"species ability slots fingerprint failed: {bulba.abilities}")
    if evolutions(1) != ((EVO_LEVEL, 16, 2),):
        raise RuntimeError(f"evolution table fingerprint failed: {evolutions(1)}")
    if item_name(2) != "Ultra Ball":
        raise RuntimeError(f"item table fingerprint failed: {item_name(2)!r}")
    if wild_land_levels().get((0, 16)) != (2, 5):
        raise RuntimeError(f"wild header fingerprint failed: Route 101 land {wild_land_levels().get((0, 16))}")
