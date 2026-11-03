"""Typed reads over ROWE v2.1b RAM. Every offset comes from rowe_symbols."""
import struct
from dataclasses import dataclass

import rowe_symbols as S
from emu_boot import Emu
from rowe_rom import NUM_NATURES


def decode_text(raw: bytes) -> str:
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
        elif c == 0x00:
            out.append(" ")
        else:
            out.append("?")
    return "".join(out)


@dataclass
class PartyMon:
    slot: int
    species: int
    level: int
    hp: int
    max_hp: int
    moves: tuple
    pp: tuple
    status: int
    experience: int
    friendship: int
    nickname: str
    personality: int
    atk: int = 0
    dfn: int = 0
    spd: int = 0
    sp_atk: int = 0
    sp_def: int = 0
    ot_id: int = 0
    ability_num: int = 0
    evs: tuple = (0, 0, 0, 0, 0, 0)

    @property
    def fainted(self) -> bool:
        return self.hp == 0

    @property
    def nature(self) -> int:
        return self.personality % NUM_NATURES

    @property
    def shiny(self) -> bool:
        """The game's test: the xor of the trainer id halves and the personality halves under 8."""
        return ((self.ot_id >> 16) ^ (self.ot_id & 0xFFFF) ^ (self.personality >> 16) ^ (self.personality & 0xFFFF)) < 8


@dataclass
class BattleMon:
    battler: int
    species: int
    level: int
    hp: int
    max_hp: int
    moves: tuple
    pp: tuple
    types: tuple
    ability: int
    status1: int
    stat_stages: tuple
    nickname: str
    personality: int = 0
    atk: int = 0
    dfn: int = 0
    spd: int = 0
    sp_atk: int = 0
    sp_def: int = 0
    item: int = 0


@dataclass
class BoxMon:
    slot: int
    species: int
    nickname: str
    experience: int
    personality: int
    ot_id: int
    moves: tuple
    ability_num: int
    evs: tuple

    @property
    def shiny(self) -> bool:
        return ((self.ot_id >> 16) ^ (self.ot_id & 0xFFFF) ^ (self.personality >> 16) ^ (self.personality & 0xFFFF)) < 8

    @property
    def nature(self) -> int:
        return self.personality % NUM_NATURES

    @property
    def box(self) -> int:
        return self.slot // S.PC_IN_BOX

    @property
    def position(self) -> int:
        return self.slot % S.PC_IN_BOX


def box_mon(raw: bytes, slot: int) -> BoxMon:
    """A storage slot is the party layout's first SIZEOF_BOX_POKEMON bytes, so the MON_* offsets
    apply; level, hp and pp are party-only and absent here."""
    w14, w18, w1c = struct.unpack_from("<III", raw, S.MON_MOVE1_EXP)
    return BoxMon(
        slot=slot,
        species=w1c & 0xFFFF,
        nickname=decode_text(raw[S.MON_NICKNAME:S.MON_NICKNAME + 10]),
        experience=w14 >> 10,
        personality=struct.unpack_from("<I", raw, S.MON_PERSONALITY)[0],
        ot_id=struct.unpack_from("<I", raw, S.MON_OT_ID)[0],
        moves=(w14 & S.MOVE_MASK, w18 & S.MOVE_MASK, (w18 >> 10) & S.MOVE_MASK, (w1c >> 17) & S.MOVE_MASK),
        ability_num=(raw[S.MON_ABILITY_NUM] >> S.ABILITY_NUM_SHIFT) & S.ABILITY_NUM_MASK,
        evs=tuple(raw[S.MON_EVS:S.MON_EVS + 6]),
    )


def party_mon(raw: bytes, slot: int) -> PartyMon:
    w14, w18, w1c = struct.unpack_from("<III", raw, S.MON_MOVE1_EXP)
    moves = (w14 & S.MOVE_MASK, w18 & S.MOVE_MASK, (w18 >> 10) & S.MOVE_MASK, (w1c >> 17) & S.MOVE_MASK)
    hp, max_hp = struct.unpack_from("<HH", raw, S.MON_HP)
    atk, dfn, spd, sp_atk, sp_def = struct.unpack_from("<5H", raw, S.MON_ATK)
    return PartyMon(
        atk=atk,
        dfn=dfn,
        spd=spd,
        sp_atk=sp_atk,
        sp_def=sp_def,
        slot=slot,
        species=w1c & 0xFFFF,
        level=raw[S.MON_LEVEL],
        hp=hp,
        max_hp=max_hp,
        moves=moves,
        pp=tuple(raw[S.MON_PP:S.MON_PP + 4]),
        status=struct.unpack_from("<I", raw, S.MON_STATUS)[0],
        experience=w14 >> 10,
        friendship=(w18 >> 22) & 0xFF,
        nickname=decode_text(raw[S.MON_NICKNAME:S.MON_NICKNAME + 10]),
        personality=struct.unpack_from("<I", raw, S.MON_PERSONALITY)[0],
        ot_id=struct.unpack_from("<I", raw, S.MON_OT_ID)[0],
        ability_num=(raw[S.MON_ABILITY_NUM] >> S.ABILITY_NUM_SHIFT) & S.ABILITY_NUM_MASK,
        evs=tuple(raw[S.MON_EVS:S.MON_EVS + 6]),
    )


def battle_mon(raw: bytes, battler: int) -> BattleMon:
    atk, dfn, spd, sp_atk, sp_def = struct.unpack_from("<5H", raw, S.BM_ATK)
    return BattleMon(
        atk=atk,
        dfn=dfn,
        spd=spd,
        sp_atk=sp_atk,
        sp_def=sp_def,
        battler=battler,
        species=struct.unpack_from("<H", raw, S.BM_SPECIES)[0],
        level=raw[S.BM_LEVEL],
        hp=struct.unpack_from("<H", raw, S.BM_HP)[0],
        max_hp=struct.unpack_from("<H", raw, S.BM_MAX_HP)[0],
        moves=struct.unpack_from("<4H", raw, S.BM_MOVES),
        pp=tuple(raw[S.BM_PP:S.BM_PP + 4]),
        types=tuple(raw[S.BM_TYPES:S.BM_TYPES + 3]),
        ability=struct.unpack_from("<H", raw, S.BM_ABILITY)[0],
        status1=struct.unpack_from("<I", raw, S.BM_STATUS1)[0],
        stat_stages=tuple(raw[S.BM_STAT_STAGES:S.BM_STAT_STAGES + 8]),
        nickname=decode_text(raw[S.BM_NICKNAME:S.BM_NICKNAME + 10]),
        personality=struct.unpack_from("<I", raw, S.BM_PERSONALITY)[0],
        item=struct.unpack_from("<H", raw, S.BM_ITEM)[0],
    )


class GameState:
    def __init__(self, emu: Emu):
        self.e = emu

    def in_battle(self) -> bool:
        return bool(self.e.read(S.addr("gMain") + S.MAIN_IN_BATTLE_BYTE)[0] & S.MAIN_IN_BATTLE_BIT)

    def callback2(self) -> int:
        return self.e.u32(S.addr("gMain") + S.MAIN_CALLBACK2)

    def script_instr(self) -> int:
        """ROM address of the battle script command running now; a yes/no box holds its command."""
        return self.e.u32(S.addr("gBattlescriptCurrInstr"))

    def offered_move(self) -> int:
        """Move id in the last battle string's move placeholder; the new move while a learn prompt holds."""
        return struct.unpack("<H", self.e.read(S.addr("gBattleTextBuff2") + 2, 2))[0]

    def flag(self, flag_id: int) -> bool:
        sb1 = self.e.u32(S.addr("gSaveBlock1Ptr"))
        return bool(self.e.read(sb1 + S.SB1_FLAGS + flag_id // 8)[0] >> (flag_id % 8) & 1)

    def var(self, var_id: int) -> int:
        sb1 = self.e.u32(S.addr("gSaveBlock1Ptr"))
        return struct.unpack("<H", self.e.read(sb1 + S.SB1_VARS + (var_id - 0x4000) * 2, 2))[0]

    def badges(self) -> int:
        # VAR_NUM_BADGES, the count the (0,8) League guard reads: 8 Hoenn badges climbing to 16 as
        # the Sevii badge ladder writes it. The 0xCD7 badge flags top out at 8 and miss the Sevii half.
        return self.var(S.VAR_NUM_BADGES)

    def party_menu_slot(self) -> int:
        """Cursor slot on the party menu, 0-5 in party order."""
        return self.e.read(S.addr("gPartyMenuSlot"))[0]

    def battler_slot(self, battler: int) -> int:
        """Party index of the mon this battler is controlling."""
        return struct.unpack("<H", self.e.read(S.addr("gBattlerPartyIndexes") + 2 * battler, 2))[0]

    def learning_mon(self) -> int:
        """Party index in the last battle string's nickname placeholder; the learner at a learn prompt."""
        return self.e.read(S.addr("gBattleTextBuff1") + 3)[0]

    def battle_points(self) -> int:
        sb2 = self.e.u32(S.addr("gSaveBlock2Ptr"))
        return struct.unpack("<H", self.e.read(sb2 + S.SB2_BATTLE_POINTS, 2))[0]

    def player_name(self) -> str:
        sb2 = self.e.u32(S.addr("gSaveBlock2Ptr"))
        return decode_text(self.e.read(sb2 + S.SB2_PLAYER_NAME, 8))

    def position(self) -> tuple:
        """(x, y, map_group, map_num)"""
        sb1 = self.e.u32(S.addr("gSaveBlock1Ptr"))
        x, y = struct.unpack("<hh", self.e.read(sb1 + S.SB1_POS, 4))
        group, num = self.e.read(sb1 + S.SB1_LOCATION, 2)
        return x, y, group, num

    def party(self) -> list:
        n = self.e.read(S.addr("gPlayerPartyCount"))[0]
        base = S.addr("gPlayerParty")
        return [party_mon(self.e.read(base + i * S.SIZEOF_POKEMON, S.SIZEOF_POKEMON), i) for i in range(n)]

    def party_filled(self) -> int:
        """Party slots holding a species. The storage screen compacts the party the moment a deposit is
        confirmed but rewrites gPlayerPartyCount only on exit, so this is the live count inside the PC."""
        base = S.addr("gPlayerParty")
        return sum(1 for i in range(6) if party_mon(self.e.read(base + i * S.SIZEOF_POKEMON, S.SIZEOF_POKEMON), i).species)

    def box(self) -> list:
        """[(slot, species)] for every filled storage slot, read off gPokemonStoragePtr the way
        party() reads gPlayerParty. slot counts from 0 across all boxes, so the box number is
        slot // S.PC_IN_BOX and the position within it is slot % S.PC_IN_BOX. An empty slot holds
        species 0 and is dropped; the caller bounds the id against the species table."""
        base = self.e.u32(S.addr("gPokemonStoragePtr")) + S.PC_BOXES
        out = []
        for i in range(S.PC_BOX_COUNT * S.PC_IN_BOX):
            sp = struct.unpack("<H", self.e.read(base + i * S.SIZEOF_BOX_POKEMON + S.MON_SPECIES, 2))[0]
            if sp:
                out.append((i, sp))
        return out

    def current_box(self) -> int:
        """Box the storage screen shows; the withdraw grid opens on it and a page turn moves it."""
        return self.e.u32(self.e.u32(S.addr("gPokemonStoragePtr")) + S.PC_CURRENT_BOX)

    def boxes(self) -> list:
        """Every filled storage slot as a BoxMon, off one EWRAM read spanning all PC_BOX_COUNT boxes."""
        base = self.e.u32(S.addr("gPokemonStoragePtr")) + S.PC_BOXES
        n = S.PC_BOX_COUNT * S.PC_IN_BOX
        raw = self.e.read(base, n * S.SIZEOF_BOX_POKEMON)
        out = []
        for i in range(n):
            chunk = raw[i * S.SIZEOF_BOX_POKEMON:(i + 1) * S.SIZEOF_BOX_POKEMON]
            if struct.unpack_from("<H", chunk, S.MON_SPECIES)[0]:
                out.append(box_mon(chunk, i))
        return out

    def battle_type_flags(self) -> int:
        return self.e.u32(S.addr("gBattleTypeFlags"))

    def battlers(self) -> list:
        n = self.e.read(S.addr("gBattlersCount"))[0]
        base = S.addr("gBattleMons")
        return [battle_mon(self.e.read(base + i * S.SIZEOF_BATTLE_POKEMON, S.SIZEOF_BATTLE_POKEMON), i) for i in range(n)]

    def battle_outcome(self) -> int:
        return self.e.read(S.addr("gBattleOutcome"))[0]

    def bag_pocket(self, offset: int, slots: int) -> list:
        """[(item_id, quantity)] for the filled slots of one save-block pocket."""
        sb1 = self.e.u32(S.addr("gSaveBlock1Ptr"))
        return self.item_slots(sb1 + offset, slots)

    def item_slots(self, addr: int, slots: int) -> list:
        """[(item_id, quantity)] for the filled {u16 item, u16 qty ^ key} slots at addr; the game keeps a
        pocket packed from slot 0."""
        sb2 = self.e.u32(S.addr("gSaveBlock2Ptr"))
        key = self.e.u32(sb2 + S.SB2_ENCRYPTION_KEY) & 0xFFFF
        raw = self.e.read(addr, 4 * slots)
        out = []
        for i in range(slots):
            item, qty = struct.unpack_from("<HH", raw, 4 * i)
            if not item:
                break
            out.append((item, qty ^ key))
        return out

    def poke_balls(self) -> list:
        return self.bag_pocket(S.SB1_BAG_POKE_BALLS, S.BAG_POKE_BALLS_SLOTS)

    def medicine(self) -> list:
        return self.bag_pocket(S.SB1_BAG_MEDICINE, S.BAG_MEDICINE_SLOTS)

    def tms(self) -> list:
        """The TMs & HMs pocket, an EWRAM array off gBagPockets rather than a save-block span."""
        return self.item_slots(S.TM_POCKET, S.TM_POCKET_SLOTS)

    def key_items(self) -> list:
        return self.bag_pocket(S.SB1_BAG_KEY_ITEMS, S.BAG_KEY_ITEMS_SLOTS)

    def shop_items(self) -> list:
        """Item ids of the open Mart's Buy list in row order; empty when no shop is open."""
        ptr = self.e.u32(S.MART_ITEM_LIST)
        count = struct.unpack("<H", self.e.read(S.MART_ITEM_COUNT, 2))[0]
        if not 0x08000000 <= ptr < 0x0A000000 or not 1 <= count <= 40:
            return []
        ids = struct.unpack(f"<{count + 1}H", self.e.read(ptr, 2 * (count + 1)))
        return list(ids[:count]) if ids[count] == 0 and 0 not in ids[:count] else []

    def money(self) -> int:
        sb1 = self.e.u32(S.addr("gSaveBlock1Ptr"))
        sb2 = self.e.u32(S.addr("gSaveBlock2Ptr"))
        return self.e.u32(sb1 + S.SB1_MONEY) ^ self.e.u32(sb2 + S.SB2_ENCRYPTION_KEY)

    def pokedex(self) -> tuple:
        """(owned, seen) national dex numbers read off SaveBlock1's dexCaught and dexSeen
        bit arrays; bit n-1, national dex capped at NATIONAL_DEX_MAX. This is the in-game
        Pokedex, not the executor's catch ledger."""
        sb1 = self.e.u32(S.addr("gSaveBlock1Ptr"))
        caught = self.e.read(sb1 + S.SB1_DEX_CAUGHT, S.DEX_FLAGS_NO)
        seen = self.e.read(sb1 + S.SB1_DEX_SEEN, S.DEX_FLAGS_NO)

        def ids(buf: bytes) -> list:
            return [n for n in range(1, S.NATIONAL_DEX_MAX + 1)
                    if buf[(n - 1) // 8] & (1 << ((n - 1) % 8))]
        return ids(caught), ids(seen)

    def iv_boosts(self) -> tuple:
        """Every mon's IVs in stat order (HP, Atk, Def, Spe, SpA, SpD): the Trainer Skill stat-boost
        levels times SKILL_IV_PER_LEVEL. The skill rows run HP, Atk, Def, SpA, SpD, Spe."""
        sb2 = self.e.u32(S.addr("gSaveBlock2Ptr"))
        rows = self.e.read(sb2 + S.SB2_SKILL_LEVELS + S.SKILL_ROW_STAT_BOOSTS.start, 6)
        return tuple(S.SKILL_IV_PER_LEVEL * rows[i] for i in (0, 1, 2, 5, 3, 4))

    def skill_points(self) -> int:
        """Unspent Trainer Skill points, plain u16; the game writes it on entering the Trainer
        Skills screen and it reads 0 in the field, so only call this with the screen open."""
        sb1 = self.e.u32(S.addr("gSaveBlock1Ptr"))
        return struct.unpack("<H", self.e.read(sb1 + S.SB1_SKILL_POINTS, 2))[0]

    def bag_position(self) -> tuple:
        """(pocket, cursor row within that pocket)"""
        base = S.addr("gBagPosition")
        pocket = self.e.read(base + S.BAGPOS_POCKET)[0]
        cursor = struct.unpack("<H", self.e.read(base + S.BAGPOS_CURSOR + 2 * pocket, 2))[0]
        return pocket, cursor

    def action_cursor(self, battler: int = 0) -> int:
        return self.e.read(S.addr("gActionSelectionCursor") + battler)[0]

    def move_cursor(self, battler: int = 0) -> int:
        return self.e.read(S.addr("gMoveSelectionCursor") + battler)[0]

    def exec_flags(self) -> int:
        return self.e.u32(S.addr("gBattleControllerExecFlags"))

    def chooser(self) -> int:
        """Player-side battler whose action menu is waiting on input, 0 or 2. The exec flag can point
        at a different battler mid-turn (a double has battler 2's bit set while battler 0's menu is
        still up), and keying on it there presses the idle battler's A into the live menu and confirms
        its default move, so prefer a battler whose controller sits on a choose func. Falls back to the
        lowest set exec bit before any menu is up (the intro) and in a single battle."""
        for b in (0, 2):
            if self.controller_func(b) in S.PLAYER_CHOOSE_ACTION_FUNCS:
                return b
        flags = self.exec_flags() & 0xF
        return (flags & -flags).bit_length() - 1 if flags else 0

    def controller_func(self, battler: int) -> int:
        """gBattlerControllerFuncs[battler], the controller step running for that battler."""
        return self.e.u32(S.BATTLER0_CONTROLLER_FUNC + battler * S.CONTROLLER_FUNC_STRIDE)

    def choosing(self, battler: int) -> bool:
        """True while that battler's controller waits on the player's action pick. A double's second
        mon chooses as battler 2 while battler 0 has gone idle at 0x83aa958, so a gate must read the
        battler that is actually choosing rather than battler 0."""
        return self.controller_func(battler) in S.PLAYER_CHOOSE_ACTION_FUNCS

    def comm(self, battler: int = 0) -> int:
        """gBattleCommunication[battler], the sub-state behind the shared choose func: 0 or 2 on the
        action grid, 3 while the Fight move list takes input, 6 while the selection script runs."""
        return self.e.read(S.addr("gBattleCommunication") + battler, 1)[0]

    def in_move_list(self, battler: int) -> bool:
        """True while the Fight move list takes input. Keyed on gBattleCommunication alone: the
        controller bounces to idle 0x83aa958 under the list when the ROM refuses a 0-PP slot, so a
        func-gated read missed that state and the intro branch mashed A into the parked move."""
        return self.comm(battler) == S.MOVE_LIST_COMM_STATE

    def in_selection_script(self, battler: int) -> bool:
        """True while the selection script box is up (no PP, ineffective move). Only B leaves it."""
        return self.comm(battler) == S.SELECTION_SCRIPT_COMM_STATE

    def disabled_move(self, battler: int) -> int:
        """Move id Disable has locked out for this battler, 0 when nothing is disabled."""
        addr = S.addr("gDisableStructs") + battler * S.DISABLE_STRUCT_SIZE + S.DISABLE_DISABLED_MOVE
        return struct.unpack("<H", self.e.read(addr, 2))[0]
