"""ROWE v2.1b memory map.

The ROM is a closed build of pokeemerald-expansion, so no .sym ships with it.
Each address below carries how it was established:

  runtime  observed live in the emulator (pointer values, key injection, frame counter)
  literal  the address appears as a Thumb literal-pool constant in the ROM at a
           count matching the symbol's reference density, at the spacing the
           RoweSource (1.9.4) declaration order predicts
  projected RoweSource layout offset plus the measured drift of the nearest
           literal-confirmed anchor; unverified until a runtime read agrees

Save blocks are ASLR'd by SetSaveBlocksPointers (offset 0x44 on this boot
path, re-read the pointer every time). sizeof(SaveBlock2) = 0xD08,
sizeof(SaveBlock1) = 0x3670, both measured from the pointer spacing.
"""

IWRAM = {
    "gMain": (0x03002C10, "runtime"),
    "gBackupMapLayout": (0x03004BB0, "runtime"),
    "gSaveBlock1Ptr": (0x03004B7C, "runtime"),
    "gSaveBlock2Ptr": (0x03004B80, "runtime"),
    "gPokemonStoragePtr": (0x03004B84, "runtime"),
}

EWRAM = {
    "gBattle_BG0_X": (0x02024980, "literal"),
    "gBattleTypeFlags": (0x02024B60, "literal"),
    "gActiveBattler": (0x02024BE4, "literal"),
    "gBattleControllerExecFlags": (0x02024BE8, "literal"),
    "gBattlersCount": (0x02024BEC, "literal"),
    "gBattlerPartyIndexes": (0x02024BEE, "literal"),
    "gBattlerPositions": (0x02024BF6, "literal"),
    "gBattleMons": (0x02024C04, "literal"),
    "gBattlerSpriteIds": (0x02024D84, "literal"),
    "gCurrentMove": (0x02024D8A, "literal"),
    "gBattleMoveDamage": (0x02024D90, "literal"),
    "gBattlerAttacker": (0x02024DAC, "literal"),
    "gBattlerTarget": (0x02024DAD, "literal"),
    "gBattlescriptCurrInstr": (0x02024DB4, "literal"),
    # string placeholder buffers, read off staged level-ups: Buff1 holds the mon as
    # {FD, 07 nick, battler, partyId, FF} and Buff2 the move as {FD, 02, u16 id, FF}, tracked
    # 499/256/499/36 through "trying to learn" / "forgot" / "learned" strings
    # gPartyMenu.slotId: tracked 0,2,4,5,3 under DOWN,DOWN,RIGHT,UP on the in-battle party
    # menu, whose six slots sit in two columns (even left, odd right)
    "gPartyMenuSlot": (0x0203E139, "runtime"),
    "gBattleTextBuff1": (0x02024B28, "runtime"),
    "gBattleTextBuff2": (0x02024B3A, "runtime"),
    "gChosenActionByBattler": (0x02024DB8, "projected"),
    "gDisableStructs": (0x02024E78, "runtime"),
    "gBattleCommunication": (0x02024F1E, "literal"),
    "gBattleOutcome": (0x02024F26, "runtime"),
    "gBattleWeather": (0x02024FC8, "literal"),
    "gBattleStruct": (0x02025098, "projected"),
    "gBattleResources": (0x020250A4, "projected"),
    "gActionSelectionCursor": (0x020250A8, "runtime"),
    "gMoveSelectionCursor": (0x020250AC, "runtime"),
    "gPlayerPartyCount": (0x02025101, "runtime"),
    "gEnemyPartyCount": (0x02025102, "literal"),
    "gPlayerParty": (0x02025104, "runtime"),
    "gEnemyParty": (0x020252CC, "literal"),
    "gMultiuseSpriteTemplate": (0x02025494, "literal"),
    "gObjectEvents": (0x02037A68, "runtime"),
    "gMapHeader": (0x02037A30, "runtime"),
    "gBagPosition": (0x0203E0A8, "runtime"),
    "sStartMenuCursorPos": (0x02000015, "runtime"),
    "gPartyMenu.slotId": (0x0203E139, "runtime"),
    "sPartyMenuActionCursor": (0x0203DFE2, "runtime"),
}

# struct DisableStruct[battler], vanilla layout confirmed off a dump where Poison
# Sting read 40 at +0x4 and the disableTimer byte read 0x43 at +0xF
DISABLE_STRUCT_SIZE = 0x1C
DISABLE_DISABLED_MOVE = 0x4  # u16

START_MENU_POKEMON = 1  # Start menu rows: Pokédex, Pokémon, trainer card, Inventory, ...
START_MENU_BAG = 3      # Inventory is the fourth row of that list
START_MENU_SKILLS = 4   # Trainer Skills, ROWE's perk screen
# Trainer Skills list: 25 rows wrapping at the end, cursor opens on row 0, RIGHT parks the +/-
# selector on + and A buys a level. The six stat boosts are one block; each level is +3 IVs on
# every owned mon (ROWE ships every mon at 0 IVs), 3 points a level, cap 10.
SKILL_ROW_STAT_BOOSTS = range(16, 22)   # HP, Attack, Defense, Sp.Atk, Sp.Def, Speed
SKILL_ROWS = 25
SKILL_STAT_COST = 3
SKILL_IV_PER_LEVEL = 3
CB2_BAG_MAIN = 0x82054F1  # gMain.callback2 on the bag item list, the field and battle bag share it
PARTY_ACTION_SWITCH = 1  # mon submenu rows: Summary, Switch, Item, Cancel

# struct BagPosition: exitCallback*, u8 location, u8 pocket, u16 cursorPosition[]
# at +8 (pocket byte and cursor found by diffing EWRAM across tab switches)
BAGPOS_POCKET = 0x5
BAGPOS_CURSOR = 0x8
BAG_POCKET_MEDICINE = 1    # tab order in the battle bag: Items, Medicine, Poké Balls, ...
BAG_POCKET_POKE_BALLS = 2

# struct MapHeader copy in EWRAM: mapLayout*, events*, mapScripts*, connections*
MAPHDR_LAYOUT = 0x0
MAPHDR_EVENTS = 0x4
MAPHDR_CONNECTIONS = 0xC

# struct BackupMapLayout {s32 width; s32 height; u16 *map;}; the grid carries a
# 7-tile margin on every side, so map tile (x, y) is cell (x + 7, y + 7).
MAP_OFFSET = 7
# the backup buffer is the layout plus its margin: width + 15, height + 14
# (Route 104 40x80 -> 55x94, Petalburg Woods 48x44 -> 63x58)
BACKUP_MARGIN_W = 15
BACKUP_MARGIN_H = 14
# ROWE 2.1b repacked the cell word: bits 0-11 metatile id, bit 12 blocks
# movement, bits 13-15 elevation. Measured by walking into 0x1xxx (blocked)
# and 0x6xxx (open) cells; the 1.9.4 masks (0x0C00 collision) do not apply.
GRID_ID_MASK = 0x0FFF
GRID_BLOCKED = 0x1000
GRID_ELEVATION_SHIFT = 13
GRID_UNDEFINED = 0x0FFF
# a surfable water body sits at elevation 1 while the player walks land at 3, so the
# heights never match on foot and Surf is the only crossing (measured on Route 104)
SURF_ELEVATION = 1

# struct ObjectEvent, 16 entries of 0x24 (RoweSource include/global.fieldmap.h)
OBJECT_EVENTS_COUNT = 16
OBJ_EVENT_SIZE = 0x24
OBJ_FLAGS = 0x00           # u32, bit 0 active, bit 16 isPlayer
OBJ_ACTIVE_BIT = 0x1
OBJ_IS_PLAYER_BIT = 0x10000
OBJ_GRAPHICS_ID = 0x04     # u16; a cuttable tree or breakable rock is an object event, told apart
                           # from an NPC by this id (OBJ_EVENT_GFX_* in constants/event_objects.h)
OBJ_LOCAL_ID = 0x08
OBJ_MAP_NUM = 0x09
OBJ_MAP_GROUP = 0x0A
OBJ_ELEVATION = 0x0B       # u8: low nibble currentElevation, high nibble previousElevation
OBJ_CURRENT_COORDS = 0x10  # s16 x, s16 y, both carrying the +7 margin

SIZEOF_POKEMON = 0x4C          # gEnemyParty - gPlayerParty == 6 * 0x4C
SIZEOF_BOX_POKEMON = 0x34      # measured stride between filled box slots; the party mon's first
                               # 0x34 bytes without the party-only status/level/hp/stats tail
SIZEOF_BATTLE_POKEMON = 0x60   # gBattlerSpriteIds - gBattleMons == 4 * 0x60
PARTY_SIZE = 6
# struct PokemonStorage at *gPokemonStoragePtr: u32 currentBox, then boxes[14][30] of BoxPokemon.
# The mon grid begins past the currentBox word; a box slot is contiguous from 0 across all boxes.
PC_CURRENT_BOX = 0x0  # steps 0 -> 1 -> 2 as RIGHT turns pages from the withdraw grid's title row
PC_BOXES = 0x4
PC_BOX_COUNT = 14
PC_IN_BOX = 30

# box storage PC UI, probed on the Center's storage terminal (not the ROWE service PC).
CB2_PC_BOX = 0x81108FD     # gMain.callback2 on the box deposit/withdraw grid; the main menu is field
BOX_MENU_CURSOR = 0x0203DFE2  # Move 0, Withdraw 1, Deposit 2, Move items 3, See ya 4
BOX_DEPOSIT_COL = 0x0203AD11  # party-column cursor in the deposit grid, slot 0 at top
BOX_MENU_WITHDRAW = 1
BOX_MENU_DEPOSIT = 2
BOX_GRID_COLS = 6             # withdraw grid is 6 wide, so box position i sits at col i%6, row i//6
BOX_TITLE_DROP_COL = 2        # DOWN from the box title lands on this column of the top row (Pawmi at 2 read as Oddish at 4 after two RIGHTs)

# struct Pokemon, ROWE 2.1b packing, read off a fresh L10 Trubbish starter
# (personality/otId/nickname/otName/species/pp/level/hp all matched). Nothing is encrypted:
# the EV bytes and the ability slot were fitted on the fixture parties, six stats per mon
# reproduced within a point from base stats, EVs and personality % 25 at 0 skill levels, and
# the ability slot matched gBattleMons' ability on five paired mons. No IV field exists on the
# mon; IVs are the Trainer Skill stat boosts (SKILL_IV_PER_LEVEL below). 0x26-0x2A hold met data.
MON_PERSONALITY = 0x00     # u32
MON_OT_ID = 0x04           # u32
MON_NICKNAME = 0x08        # u8[10]
MON_LANGUAGE = 0x12        # low 3 bits
MON_MOVE1_EXP = 0x14       # u32: move1 bits 0-9, experience bits 10-31
MON_MOVES_2_3 = 0x18       # u32: move2 bits 0-9, move3 10-19, friendship bits 22-29
MON_SPECIES_MOVE4 = 0x1C   # u32: species bits 0-15, move4 bits 17-26
MON_SPECIES = 0x1C         # u16 view of the same word
MON_EVS = 0x20             # u8[6]: HP, Atk, Def, Spe, SpA, SpD
MON_OT_NAME = 0x2B         # u8[7]
MON_ABILITY_NUM = 0x32     # bits 4-5: 0 and 1 the species' two ability slots, 2 the hidden ability
ABILITY_NUM_SHIFT = 4
ABILITY_NUM_MASK = 0x3
MON_PP = 0x34              # u8[4]
MON_STATUS = 0x38          # u32
MON_LEVEL = 0x3C           # u8
MON_HP = 0x3E              # u16
MON_MAX_HP = 0x40          # u16
MON_ATK = 0x42             # u16, then def/spd/spA/spD at 2-byte steps
MOVE_MASK = 0x3FF

# struct BattlePokemon, RoweSource layout verified in a wild battle; the 2.1b
# build appends 4 bytes after otId (0x5C) to reach 0x60
BM_SPECIES = 0x00          # u16
BM_ATK = 0x02              # u16, then def/spd/spA/spD at 2-byte steps
BM_MOVES = 0x0C            # u16[4]
BM_IVS = 0x14              # u32 packed
BM_STAT_STAGES = 0x18      # u8[8], 6 = neutral
BM_ABILITY = 0x20          # u16
BM_TYPES = 0x22            # u8[3]
BM_PP = 0x25               # u8[4]
BM_HP = 0x2A               # u16
BM_LEVEL = 0x2C            # u8
BM_FRIENDSHIP = 0x2D       # u8
BM_MAX_HP = 0x2E           # u16
BM_ITEM = 0x30             # u16
BM_NICKNAME = 0x32         # u8[11]
BM_OT_NAME = 0x40          # u8[8]
BM_EXPERIENCE = 0x48       # u32
BM_PERSONALITY = 0x4C      # u32
BM_STATUS1 = 0x50          # u32
BM_STATUS2 = 0x54          # u32
BM_OT_ID = 0x58            # u32

# struct Main, unchanged from vanilla (RoweSource include/main.h)
MAIN_CALLBACK2 = 0x4
MAIN_HELD_KEYS = 0x2C
MAIN_NEW_KEYS = 0x2E
MAIN_STATE = 0x438
MAIN_IN_BATTLE_BYTE = 0x439
MAIN_IN_BATTLE_BIT = 0x2

# SaveBlock2 head, vanilla layout (RoweSource offsets; verify at runtime)
SB2_PLAYER_NAME = 0x0
SB2_PLAYER_GENDER = 0x8
SB2_TRAINER_ID = 0xA
SB2_PLAYTIME_HOURS = 0xE
SB2_ENCRYPTION_KEY = 0x40
SB2_SKILL_LEVELS = 0xB4A   # u8[SKILL_ROWS] in list order; HP Boost (row 16) flipped 0 -> 1 at +0xB5A on a buy

# SaveBlock1 head, vanilla layout (RoweSource offsets; verify at runtime)
SB1_POS = 0x0
SB1_LOCATION = 0x4
SB1_PARTY_COUNT = 0x234
SB1_PARTY = 0x238
SB1_MONEY = 0x400          # u32 ^ encryptionKey, matched against the Mart's money box
# bag pockets, {u16 itemId; u16 quantity ^ (encryptionKey & 0xFFFF)} slots, located
# from the starter kit (Repel in Items, the 9 key items, 10 Poké Balls)
SB1_BAG_ITEMS = 0x4D0
SB1_BAG_MEDICINE = 0x888    # cap 40, read off gBagPockets[1].itemSlots in a live save
SB1_BAG_KEY_ITEMS = 0x610
SB1_BAG_POKE_BALLS = 0x6D8
BAG_POKE_BALLS_SLOTS = 32
BAG_KEY_ITEMS_SLOTS = 30
BAG_MEDICINE_SLOTS = 40
# gBagPockets, {u8 *itemSlots; u8 capacity} rows, found by scanning EWRAM for the Items pocket
# pointer; row 8 is the TMs & HMs tab and points into EWRAM, not the save block, which is why a
# save-block scan shows no TM rows
BAG_POCKETS = 0x0203AD70
TM_POCKET = 0x0203ADC4      # gBagPockets[8].itemSlots, quantity ^ (encryptionKey & 0xFFFF) like the rest
TM_POCKET_SLOTS = 208
BAG_POCKET_TMS = 8
# gMain.callback2 on the move-select summary a level-up or TM "Which move should be forgotten?" opens
CB2_MOVE_SELECT = 0x821EDBD
# gMain.callback2 values of the party menu (opening fade and steady), read off a gym trainer fight
# where the forced switch after a faint sat on the fainted mon; the field bag's "Teach which
# Pokémon?" menu shares the steady value
CB2_PARTY_MENU = frozenset({0x820B7BD, 0x820B78D})
# the blue nurse (Jack) on the shared Center layout, local id 6 behind the left counter; the player
# talks from two tiles below. sMenu.cursorPos for his multichoice menus, found by diffing IWRAM
# across DOWN presses; it holds the previous menu's row until the next menu initialises
JACK_LOCAL_ID = 6
MENU_CURSOR = 0x03004CDA
JACK_MENU_TEACH = 3        # Outfit, Mock Battle, Nickname, Teach or Forget a Move, Wonder Trade, Doubles
TEACH_FORGET = 0           # free, through the summary move select
TEACH_EGG = 1              # 4 BP, open at 6 badges on a live screen
TEACH_TUTOR = 2            # 6 BP, "you need 9 badges"
TEACH_TM = 3               # 8 BP, "you need 12 badges"
TEACH_EGG_BP = 4
TEACH_EGG_BADGES = 6
CB2_TUTOR_LIST = 0x81BA2E1     # gMain.callback2 on the nurse's move list (egg, tutor and TM rows share it)
LIST_MENU_CURSOR = 0x0203CFAA  # row the cursor sits on inside the six-row window, found by diffing EWRAM across UP and DOWN presses
LIST_MENU_ABOVE = 0x0203CFA8   # rows scrolled off above the window, steps +1 per DOWN once the cursor holds the bottom row; the
# list's absolute row is ABOVE + CURSOR, and the last row is Cancel
RELEARNER_PTR = 0x0203CFA4     # sMoveRelearnerStruct, the heap struct behind the nurse's list; sits right before the two bytes above
RELEARNER_MENU_ITEMS = 0x1A4   # struct offset of its ListMenuItem rows, {const u8 *name; s32 id} w/ id the move id, Cancel last
LIST_CANCEL = -2
RELEARNER_MAX_ROWS = 64
SB2_BATTLE_POINTS = 0xA3C      # u16, the BP box on the nurse's price prompt; 8 -> 4 across one egg move
# gBattlerControllerFuncs[0], the player's controller step; it holds HandleInputChooseAction only while
# the action grid waits on the player, and other ROM addresses through the turn's animations (found by
# diffing EWRAM across the menu, a switch animation and the menu again)
CB2_BATTLE_MAIN = 0x0803C761   # gMain.callback2 through a battle's action grid, move list and turn playback
BATTLER0_CONTROLLER_FUNC = 0x020207D8
CONTROLLER_FUNC_STRIDE = 4     # gBattlerControllerFuncs holds one 4-byte fn pointer per battler, so battler N sits STRIDE*N past [0]
# 0x83C12BC while "What will X do?" takes input (DOWN moves gActionSelectionCursor, A opens the
# menu under it); 0x83AA958 is the controller's idle value and holds through the whole intro
# ("Wild X appeared!" waiting on a press, "Go! X!"), so a step gating on it acted during the intro
PLAYER_CHOOSE_ACTION = 0x083C12BC
# a second action-choose func the ROM runs for some leads (the Dig-looping Turtonator fight on
# [4, 2] held it the whole battle, steering Fight/the move list/switches the same as 0x83C12BC and
# never touching 0x83C12BC); a step gating on the single value skipped every decision there and
# blind-A-mashed the parked move. found by diffing BATTLER0_CONTROLLER_FUNC in that battle against
# the roxanne and battle_disabled fixtures, which hold 0x83C12BC
PLAYER_CHOOSE_ACTION_ALT = 0x084F5D40
PLAYER_CHOOSE_ACTION_FUNCS = frozenset({PLAYER_CHOOSE_ACTION, PLAYER_CHOOSE_ACTION_ALT})
# gBattleCommunication[0] sub-state while PLAYER_CHOOSE_ACTION drives input. The same func runs the
# action grid and the Fight move list, so this is the only read that tells them apart: 0 or 2 on the
# grid, 3 while the move list takes input (diffed across roxanne, battle_disabled, stall_route126)
MOVE_LIST_COMM_STATE = 3
# gBattleCommunication sub-state while the selection script runs (the no-PP / ineffective-move box).
# The controller bounces to idle 0x83aa958 here, so choosing() reads False and only B leaves it.
SELECTION_SCRIPT_COMM_STATE = 6
FIELD_LOCKED = 0x03004C94      # 1 while an NPC script holds the player (its text box up), 0 on the free field;
                               # gMain.callback2 reads overworld either way, so this tells the two apart
# shop.c sMartInfo: the open Mart's item list, a ROM pointer to a 0-terminated u16 id array, and
# its u16 count beside it; found by scanning EWRAM with the Petalburg Buy list open (probe_mart.py)
MART_ITEM_LIST = 0x0203B280
MART_ITEM_COUNT = 0x0203B284
# flags bit array, fitted on six flags from Roxanne's script flipping across her defeat:
# 0x9, 0x4F0, 0x1D3, 0xD90, 0xCD7 from its setflag lines and trainer 0x109's 0x500+id
SB1_FLAGS = 0x1754
SB1_SKILL_POINTS = 0x1C88  # u16, the only byte stepping 80 -> 77 -> 74 across two stat-boost buys
# u16 vars[], id - 0x4000 indexes it; the base where VAR_NUM_BADGES reads the badge count and the
# game-stats block after the 0x100 slots is populated. SB1_SKILL_POINTS sits inside it as var 0x405F.
SB1_VARS = 0x1BCA
VAR_NUM_BADGES = 0x4061  # written by the badge-reward ladder (ROM 0x2f388c..) and read by the nurse's tutor gates
FLAG_RECEIVED_BADGE01 = 0xE25  # +n for the nth badge reward handed over, set beside the setvar above
FLAG_BADGE01 = 0xCD7  # system flags start at 0xCD0 here (vanilla 0x860), badge 1 is +7 in both
BADGE_COUNT = 8
FLAG_SYS_GAME_CLEAR = 0xCD4  # SYSTEM_FLAGS+0x4, set natively by the Hall of Fame; the game-cleared bit
JOHTO_BADGE01 = 0x2A4  # badges 9-16 from the 8 Sevii-island leaders, Falkner (0x2A4) through Clair (0x2AB); trainer fights, not gym buildings
JOHTO_BADGE_COUNT = 8
MAP_DYNAMIC = (127, 127)  # a dynamic-warp header (group, num): the real destination resolves at runtime

# Pokedex owned/seen bit arrays in SaveBlock1: adjacent dexSeen then dexCaught, each
# DEX_FLAGS_NO bytes; bit = nationalDexNo - 1, byte index // 8, mask 1 << (index % 8)
# (RoweSource pokedex.c GetSetPokedexFlag). Offsets fingerprinted against live
# savestates by matching the party's owned national numbers (dexgen/probe_pokedex.py);
# stride 188 is ROUND_BITS_TO_BYTES(POKEMON_SLOTS_NUMBER=1500). National dex caps at 1025.
SB1_DEX_SEEN = 0x3320
SB1_DEX_CAUGHT = 0x33DC
DEX_FLAGS_NO = 188
NATIONAL_DEX_MAX = 1025


def addr(name: str) -> int:
    return (IWRAM.get(name) or EWRAM[name])[0]
