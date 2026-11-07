"""Overworld pathfinding over the live map grid.

Reads gBackupMapLayout (current map plus the 7-tile margin that holds the
edges of connected maps), blocks cells that carry the collision bit or an NPC,
BFSes to a target tile, and walks it one tile at a time, confirming each tile
against SaveBlock1 so an interrupted walk (wild battle, NPC in the way) is
detected at the step it happened.
"""
import struct
import time
from collections import deque
from typing import Callable

import emu_boot as eb
import rowe_map
import rowe_rom
import rowe_symbols as S
from rowe_state import GameState

DIRS = {(0, -1): eb.KEY_UP, (0, 1): eb.KEY_DOWN, (-1, 0): eb.KEY_LEFT, (1, 0): eb.KEY_RIGHT}
# The game gates every step on height (IsZCoordMismatchAt, event_object_movement.c): a walker
# carries the height of the last tile it stood on, a tile at a different height refuses it, a
# transition tile (0) sets the carried height to 0 and lets the next step go anywhere, and a
# multi-level tile (7, a bridge deck or the water under it) takes any walker and leaves the
# carried height alone (ObjectEventUpdateZCoord). Measured on Lilycove's (53, 12) -> (54, 12):
# the 4 -> 3 press is refused and the 4 -> 4 presses beside it move.
ELEV_TRANSITION = 0
ELEV_MULTI = 7
ELEV_LAND = 3  # the common ground height; the only height a surfer may dismount onto or mount from
# surfable-water behaviors (pond through ocean). Water is foot-impassable and surf-only.
WATERFALL = 0x13  # pokeemerald MB_WATERFALL, numbered inside the water range
# MB_THIN_ICE: the first step onto it cracks it, stepping back on breaks it and the game warps to the
# map's hole warp at the same x,y (Icefall Cave (1,27) tile (8,14) dropped the walk onto (1,28))
THIN_ICE = 0x26
# MB_ICE: a press slides the player on at 8 frames a tile until the tile ahead is blocked or the
# tile landed on is not ice (ForcedMovement_Slide), so one press is a multi-tile move the path
# search has to land where the game does (the Seven Island gym (2,13), an ice floor w/ stop squares)
ICE = 0x20
SLIDE_SETTLE_FRAMES = 20  # a slide still moving changes tile inside this; no change means it stopped
WATER_BEHAVIORS = frozenset(range(0x10, 0x16)) - {WATERFALL}
# MetatileBehavior_IsDiveable: the water a surfer presses A on to submerge. Surfacing from an
# underwater map is the inverse test (MetatileBehavior_IsUnableToEmerge over a fixed dive-warp
# coordinate), not a diveable tile, so dive_tiles resolves submerge spots only.
DIVE_BEHAVIORS = frozenset({0x11, 0x12, 0x14})  # SEMI_DEEP_WATER, DEEP_WATER, SOOTOPOLIS_DEEP_WATER
# MetatileBehavior_IsUnableToEmerge: seabed a B-press cannot surface from. ROWE keeps vanilla's
# MB_NO_SURFACING (0x19) and MB_SEAWEED_NO_SURFACING (0x2A); every other reachable underwater
# tile opens the "Would you like to surface?" yes/no prompt.
NO_SURFACE_BEHAVIORS = frozenset({0x19, 0x2A})
# MB_*BRIDGE* behaviors (metatile_behaviors.h): a deck over water. The game refuses a step
# off the deck onto the water beside it and a surfer's step up onto it, so a route crosses
# a bridge end to end or stays in the water under it (Route 120 jammed pressing off the deck)
# the set is MetatileBehavior_IsBridge plus the south bridge pair and Fortree's; 0x71 and 0x7E
# are "unused" in the header and bridge tiles in the game (Route 120's long bridge is 0x71)
BRIDGE_BEHAVIORS = frozenset({0x70, 0x71, 0x72, 0x73, 0x78, 0x7A, 0x7B, 0x7C, 0x7D, 0x7E, 0x7F})
ITEM_WATERFALL_TOOL = 835  # ROWE's key item standing in for HM07; the climb prompt opens only w/ it
# a waterfall is crossed upward in one ride that starts from the water tile under it; the game
# refuses a plain step onto it in any direction, so the tile itself is never stood on
CLIMB_TICKS = 20  # 30-frame samples the ride may take; Route 119's four-tile fall ends in 4
GATE_SETTLE_FRAMES = 40  # a rotating gate's quarter turn finishes inside this after the press
# A cuttable tree and a breakable rock are object events, not metatiles, so each sits on a tile the
# grid reads as blocked by that object; the graphics id (OBJ_EVENT_GFX_* in RoweSource
# constants/event_objects.h) names the field tool that clears it. Facing the object and confirming
# its yes/no prompt removes it (EventScript_CutTree, EventScript_RockSmash), freeing the tile.
CLEARABLE_OBSTACLES = {82: "CUT", 86: "ROCKSMASH"}
CLEAR_TICKS = 10  # 30-frame samples the cut or smash interaction may take to remove the object
# A Strength boulder is an object event the walker shoves one tile ahead by walking into it, once
# the Power Glove prompt on any boulder of the map has been accepted (ROWE's stand-in for HM04; the
# Yes sets the flag below and the game drops it with the map). The push lands the player on the
# boulder's tile and the boulder on the tile past it, so a route may cross a boulder whose far side
# is open floor at the boulder's height, and the path search carries the boulders it has moved.
PUSHABLE_BOULDER = 87  # OBJ_EVENT_GFX_PUSHABLE_BOULDER
FLAG_POWER_GLOVE = 0xCF9  # the one flag the boulder prompt's Yes flips, read on Victory Road B1F
PUSH_FRAMES = 60  # held frames before the player's tile changes on a push; 34 measured
PUSH_SETTLE_FRAMES = 40  # the slow walk that finishes the push after the tile change

# A directional ledge: one press in the ledge's own direction hops the player two tiles that way,
# over the ledge tile, and the reverse is refused. Values are the pokeemerald MB_JUMP_* behaviors.
LEDGE_HOPS = {0x38: (1, 0), 0x39: (-1, 0), 0x3A: (0, -1), 0x3B: (0, 1)}
# A water current carries a surfer who enters it the way it flows, tile after tile, until still
# water, and never holds position on it. Values are the pokeemerald MB_*WARD_CURRENT behaviors.
CURRENTS = {0x50: (1, 0), 0x51: (-1, 0), 0x52: (0, -1), 0x53: (0, 1)}
# A directionally impassable tile, pokeemerald's MB_IMPASSABLE_* behaviors on open floor w/ no
# collision bit: the game refuses a step that leaves it in a listed direction and a step that
# enters it heading the opposite way (a pond bank the surfer may not land on from the water).
# ROWE numbers the two double-sided ones 0xC0 and 0xC1, per its metatile_behaviors.h.
_BLOCKED_NORTH = frozenset({0x32, 0x34, 0x35, 0xC0})
_BLOCKED_SOUTH = frozenset({0x33, 0x36, 0x37, 0xC0})
_BLOCKED_WEST = frozenset({0x31, 0x35, 0x37, 0xC1})
_BLOCKED_EAST = frozenset({0x30, 0x34, 0x36, 0xC1})
LEAVE_BLOCKED = {(0, -1): _BLOCKED_NORTH, (0, 1): _BLOCKED_SOUTH, (-1, 0): _BLOCKED_WEST, (1, 0): _BLOCKED_EAST}
ENTER_BLOCKED = {(0, -1): _BLOCKED_SOUTH, (0, 1): _BLOCKED_NORTH, (-1, 0): _BLOCKED_EAST, (1, 0): _BLOCKED_WEST}
NPC_WAIT_FRAMES = 30  # one NPC random-walk step, so a replan sees a different tile freed
MAP_LOAD_FRAMES = 120  # a warp rebuilds the layout buffer within 5 frames of the map id change


def map_loaded(emu: eb.Emu) -> bool:
    """gBackupMapLayout holds the map gMapHeader names. A warp changes the map id frames
    before the buffer is rebuilt, so a grid read in between is the previous map's."""
    bw, bh = struct.unpack("<ii", emu.read(S.addr("gBackupMapLayout"), 8))
    w, h = struct.unpack("<ii", rowe_map._rd(emu.u32(S.addr("gMapHeader") + S.MAPHDR_LAYOUT), 8))
    return (bw, bh) == (w + S.BACKUP_MARGIN_W, h + S.BACKUP_MARGIN_H)


class Grid:
    climb = False  # the Waterfall Tool is in the bag; walk_to sets it on the grid it reads
    tools = frozenset()  # field tools the party holds; a clearable tile passes only w/ its tool
    clearable = {}       # read-only empty default for a grid built w/o object events (from_cells,
                         # the synthetic test fixtures); a live grid assigns its own in __init__
    pushable = frozenset()  # same default for Strength boulders; only a live grid's own set is pushed
    e = None
    # the player's tile and the height the game holds for it, read off the object event so a
    # BFS from a multi-level tile (a surfer under the bridge) starts at the real carried height
    player_tile = None
    player_elev = ELEV_LAND
    _underwater = False  # set per live map in __init__; a from_cells grid has no map type

    def __init__(self, emu: eb.Emu):
        self.e = emu
        w, h, ptr = struct.unpack("<iiI", emu.read(S.addr("gBackupMapLayout"), 12))
        self.width, self.height = w, h
        self.cells = struct.unpack(f"<{w * h}H", emu.read(ptr, w * h * 2))
        self.blocked_by_npc = set()
        self.clearable = {}   # (x, y) -> the field tool that removes the tree or rock on that tile
        self.pushable = set()  # tiles holding a Strength boulder, walked through by pushing it
        # a warp tile (cave hole, ladder, stairs, door mat) reads as open floor but fires a
        # map change the instant it is stepped on, so a route that is not aiming at it must
        # go around; _path drops it unless it is the goal
        self.warp_tiles = {(wp.x, wp.y) for wp in rowe_map.warps(emu)}
        state = GameState(emu)
        _, _, group, num = state.position()
        self._behavior = rowe_rom.metatile_behavior(group, num)
        self._underwater = rowe_rom.is_underwater(group, num)
        for x, y, flag in rowe_map.static_objects(emu):
            if not (flag and state.flag(flag)):
                self.blocked_by_npc.add((x, y))
        base = S.addr("gObjectEvents")
        for i in range(S.OBJECT_EVENTS_COUNT):
            raw = emu.read(base + i * S.OBJ_EVENT_SIZE, S.OBJ_EVENT_SIZE)
            flags = struct.unpack_from("<I", raw, S.OBJ_FLAGS)[0]
            if not flags & S.OBJ_ACTIVE_BIT:
                continue
            if flags & S.OBJ_IS_PLAYER_BIT:
                px, py = struct.unpack_from("<hh", raw, S.OBJ_CURRENT_COORDS)
                self.player_tile = (px - S.MAP_OFFSET, py - S.MAP_OFFSET)
                self.player_elev = raw[S.OBJ_ELEVATION] & 0xF
                continue
            # the following Pokemon is registered under a map id that is not the
            # current map, and it never blocks the player, so it is skipped here
            if (raw[S.OBJ_MAP_GROUP], raw[S.OBJ_MAP_NUM]) != (group, num):
                continue
            cx, cy = struct.unpack_from("<hh", raw, S.OBJ_CURRENT_COORDS)
            tile = (cx - S.MAP_OFFSET, cy - S.MAP_OFFSET)
            gfx = struct.unpack_from("<H", raw, S.OBJ_GRAPHICS_ID)[0]
            if gfx == PUSHABLE_BOULDER:
                self.pushable.add(tile)
                continue
            self.blocked_by_npc.add(tile)
            if gfx in CLEARABLE_OBSTACLES:
                self.clearable[tile] = CLEARABLE_OBSTACLES[gfx]

    @classmethod
    def from_cells(cls, width: int, height: int, cells) -> "Grid":
        """A grid over a ROM layout (rowe_rom.map_cells) with an undefined margin and no NPCs,
        for reading a map's walkable regions before the player is on it."""
        g = cls.__new__(cls)
        g.e = None
        g.width, g.height = width + 2 * S.MAP_OFFSET, height + 2 * S.MAP_OFFSET
        buf = [S.GRID_UNDEFINED] * (g.width * g.height)
        for y in range(height):
            row = (y + S.MAP_OFFSET) * g.width + S.MAP_OFFSET
            buf[row:row + width] = cells[y * width:(y + 1) * width]
        g.cells = tuple(buf)
        g.blocked_by_npc = set()
        g.clearable = {}
        g.pushable = set()
        g.warp_tiles = set()
        g._behavior = None
        return g

    def tiles_with_id(self, metatile_id: int) -> list:
        """Map-frame (x, y) of every cell inside the map proper w/ this metatile."""
        out = []
        for cy in range(S.MAP_OFFSET, self.height - S.MAP_OFFSET):
            for cx in range(S.MAP_OFFSET, self.width - S.MAP_OFFSET):
                if self.cells[cy * self.width + cx] & S.GRID_ID_MASK == metatile_id:
                    out.append((cx - S.MAP_OFFSET, cy - S.MAP_OFFSET))
        return out

    def cell(self, x: int, y: int) -> int:
        cx, cy = x + S.MAP_OFFSET, y + S.MAP_OFFSET
        if not (0 <= cx < self.width and 0 <= cy < self.height):
            return S.GRID_UNDEFINED
        return self.cells[cy * self.width + cx]

    def _is_water(self, x: int, y: int) -> bool:
        """Surfable water, foot-impassable. The metatile behavior decides it when the tileset is
        known; a grid built from literal cells with no tileset falls back to the surf-elevation
        marker, so the synthetic fixtures and the static ROM reader keep their water split."""
        if self._behavior is not None:
            return self._behavior(self.cell(x, y) & S.GRID_ID_MASK) in WATER_BEHAVIORS
        return (self.cell(x, y) >> S.GRID_ELEVATION_SHIFT) == S.SURF_ELEVATION

    def is_wall_warp(self, x: int, y: int) -> bool:
        """A warp event on a collision-blocked tile w/ the plain-ground behavior is solid rock
        the game never lets the player step into (Route 110's (45, 6) into map 24-106); a real
        door or cave mouth carries a door behavior on its blocked tile or sits on open floor."""
        c = self.cell(x, y)
        return bool(c & S.GRID_BLOCKED) and self._behavior is not None and self._behavior(c & S.GRID_ID_MASK) == 0

    def passable(self, x: int, y: int, carried: int, origin: tuple, surf: bool = False) -> bool:
        tool = self.clearable.get((x, y))
        if tool is not None and tool in self.tools:
            return True  # the tree or rock is cut or smashed on the step onto it, freeing the tile
        c = self.cell(x, y)
        if c & S.GRID_ID_MASK == S.GRID_UNDEFINED or c & S.GRID_BLOCKED:
            return False
        if (x, y) in self.blocked_by_npc and (x, y) != origin:
            return False
        if self._current(x, y) is not None:
            return False  # the flow moves the surfer off it, so it is never a tile to stand on
        if self._is_waterfall(x, y):
            return False
        if self._is_water(x, y):
            return True if self._underwater else surf  # underwater the deep water is the floor, else Surf-only
        elev = c >> S.GRID_ELEVATION_SHIFT
        if carried == ELEV_TRANSITION or elev in (ELEV_TRANSITION, ELEV_MULTI) or elev == carried:
            return True
        # a surfer's mismatch onto a height-3 bank is the dismount (CanStopSurfing); any other
        # height from the water, and any other mismatch on foot, is a cliff
        return surf and carried == S.SURF_ELEVATION and elev == ELEV_LAND

    def _current(self, x: int, y: int):
        """The (dx, dy) a water current at (x, y) flows in, or None when the tile is not one."""
        if self._behavior is None:
            return None
        return CURRENTS.get(self._behavior(self.cell(x, y) & S.GRID_ID_MASK))

    def _is_waterfall(self, x: int, y: int) -> bool:
        return self._behavior is not None and self._behavior(self.cell(x, y) & S.GRID_ID_MASK) == WATERFALL

    def _climb_top(self, tile: tuple) -> tuple:
        """Where the Waterfall Tool ride that enters the fall at `tile` ends: the first tile
        above the run of waterfall tiles."""
        while self._is_waterfall(*tile):
            tile = (tile[0], tile[1] - 1)
        return tile

    def _descend_bottom(self, tile: tuple) -> tuple:
        """Where surfing down the fall that enters at `tile` ends: the first tile below the run
        of waterfall tiles. Descent carries no tool, the current forces the ride down."""
        while self._is_waterfall(*tile):
            tile = (tile[0], tile[1] + 1)
        return tile

    def _ride(self, tile: tuple):
        """Where a surfer who enters the current at `tile` comes to rest: the first tile along the
        flow that is not itself a current, or the first tile past the map edge when the flow
        runs off the map, since the game changes map there (Route 132's belts into Route 133).
        None when the flow loops."""
        seen = set()
        while (flow := self._current(*tile)) is not None:
            if tile in seen:
                return None
            seen.add(tile)
            tile = (tile[0] + flow[0], tile[1] + flow[1])
            if not self.inside(*tile):
                return tile
        return tile

    def inside(self, x: int, y: int) -> bool:
        """Whether (x, y) is on the map proper rather than in the margin filled from its neighbors."""
        return 0 <= x < self.width - 2 * S.MAP_OFFSET and 0 <= y < self.height - 2 * S.MAP_OFFSET

    def _ledge_hop(self, x: int, y: int):
        """The (dx, dy) a directional ledge at (x, y) launches a hop in, or None when the tile is
        not a ledge. The hop goes only this way; walking back over the ledge is refused."""
        if self._behavior is None:
            return None
        return LEDGE_HOPS.get(self._behavior(self.cell(x, y) & S.GRID_ID_MASK))

    def _step_refused(self, cur: tuple, nxt: tuple, d: tuple) -> bool:
        """The game's directional collision: cur's behavior forbids leaving in d, or nxt's forbids
        entering heading d."""
        if self._behavior is None:
            return False
        here, there = self._behavior(self.cell(*cur) & S.GRID_ID_MASK), self._behavior(self.cell(*nxt) & S.GRID_ID_MASK)
        if (here in BRIDGE_BEHAVIORS and there in WATER_BEHAVIORS) or (here in WATER_BEHAVIORS and there in BRIDGE_BEHAVIORS):
            return True
        return here in LEAVE_BLOCKED[d] or there in ENTER_BLOCKED[d]

    def _push_ok(self, tile: tuple, d: tuple, carried: int, origin: tuple, surf: bool, boulders: frozenset) -> bool:
        """A step in d onto the boulder at `tile` pushes it: the tile past it is open floor at the
        boulder's height (the game's GetCollisionAtCoords for the boulder: no wall, object, height
        change or ledge, and no warp mat so the push never seals a door) and the walker can stand
        where the boulder was."""
        beyond = (tile[0] + d[0], tile[1] + d[1])
        if not self.inside(*beyond) or beyond in boulders or beyond in self.blocked_by_npc or beyond in self.warp_tiles:
            return False
        c = self.cell(*beyond)
        if c & S.GRID_ID_MASK == S.GRID_UNDEFINED or c & S.GRID_BLOCKED:
            return False
        if self._is_water(*beyond) or self._is_waterfall(*beyond) or self._current(*beyond) is not None or self._ledge_hop(*beyond) is not None:
            return False
        elev, here = c >> S.GRID_ELEVATION_SHIFT, self.cell(*tile) >> S.GRID_ELEVATION_SHIFT
        if elev not in (ELEV_TRANSITION, ELEV_MULTI) and elev != here:
            return False
        return self.passable(*tile, carried, origin, surf)

    def _after_push(self, cur: tuple, d: tuple, boulders: frozenset) -> frozenset:
        """The boulder set once a step from cur in d lands: a boulder on the next tile moves one
        tile on in d, anything else leaves the set as it is."""
        adj = (cur[0] + d[0], cur[1] + d[1])
        if adj not in boulders:
            return boulders
        return (boulders - {adj}) | {(adj[0] + d[0], adj[1] + d[1])}

    def _steps(self, cur: tuple, carried: int, origin: tuple, surf: bool, boulders: frozenset = frozenset()):
        """Tiles reachable from cur in one key press, each paired with the direction pressed. A
        ledge one tile away in its own hop direction lands the player two tiles over for a single
        press, so the ledge tile never holds the player and the crossing is one-way. `boulders`
        is where the Strength boulders stand along the search's own path; a boulder's tile is
        entered only by a push that _push_ok allows."""
        for d in DIRS:
            adj = (cur[0] + d[0], cur[1] + d[1])
            if adj in boulders:
                if self._push_ok(adj, d, carried, origin, surf, boulders):
                    yield adj, d
            elif self._current(*adj) is not None:
                land = self._ride(adj) if surf else None
                if land is not None and (not self.inside(*land) or self.passable(*land, carried, origin, surf)):
                    yield land, d
            elif self._ledge_hop(*adj) == d:
                land = (adj[0] + d[0], adj[1] + d[1])
                if self.passable(*land, carried, origin, surf):
                    yield land, d
            elif self._is_waterfall(*adj):
                # from water at the edge of a fall: Up climbs the run with the tool in the bag, Down
                # is a free ride the current forces down it. Each lands on the first non-fall tile.
                if surf and self._is_water(*cur):
                    if self.climb and d == (0, -1):
                        land = self._climb_top(adj)
                    elif d == (0, 1):
                        land = self._descend_bottom(adj)
                    else:
                        land = None
                    if land is not None and self.passable(*land, carried, origin, surf):
                        yield land, d
            elif self.passable(*adj, carried, origin, surf) and not self._step_refused(cur, adj, d):
                # a surfer carrying the water's height off a multi-level tile is still surfing
                # and needs no mount; anyone else steps onto water through the Surf prompt
                if (surf and self._is_water(*adj) and not self._is_water(*cur)
                        and carried != S.SURF_ELEVATION and not self._can_mount(carried)):
                    continue
                yield self._slide(adj, d, carried, origin, surf), d

    def _is_ice(self, x: int, y: int) -> bool:
        return self._behavior is not None and self._behavior(self.cell(x, y) & S.GRID_ID_MASK) == ICE

    def _slide(self, tile: tuple, d: tuple, carried: int, origin: tuple, surf: bool) -> tuple:
        """Where a step onto `tile` heading d ends: `tile` itself off ice, else the slide carries
        on in d while the tile ahead is open and stops on the first tile that is not ice."""
        while self._is_ice(*tile):
            ahead = (tile[0] + d[0], tile[1] + d[1])
            if not self.inside(*ahead) or not self.passable(*ahead, carried, origin, surf) or self._step_refused(tile, ahead, d):
                break
            tile = ahead
        return tile

    @staticmethod
    def _can_mount(carried: int) -> bool:
        """Surf starts only w/ the player at height 3 (IsPlayerFacingSurfableFishableWater,
        field_player_avatar.c), so a bank at any other height, a bridge end at 7 or a cliff
        edge at 4, never mounts; a walker off a transition tile carries 0 and is let through."""
        return carried in (ELEV_LAND, ELEV_TRANSITION)

    def _carry(self, nxt: tuple, carried: int, surf: bool) -> int:
        """The height the walker holds after stepping onto nxt: the tile's own, except that a
        multi-level tile keeps the height walked in (a surfer under the bridge stays at the
        water's). The BFS keys on it, so one tile reached at two heights is two nodes."""
        elev = self.cell(*nxt) >> S.GRID_ELEVATION_SHIFT
        return carried if elev == ELEV_MULTI else elev

    def _start_elev(self, start: tuple) -> int:
        """The height a BFS from start carries: the game's own for the player's tile, the tile's
        otherwise, w/ a multi-level start taken at ground height since no walker holds 7."""
        if start == self.player_tile:
            return self.player_elev
        elev = self.cell(*start) >> S.GRID_ELEVATION_SHIFT
        return ELEV_LAND if elev == ELEV_MULTI else elev

    def region(self, start: tuple, surf: bool = False) -> tuple:
        """Smallest tile reachable from start. Every tile of one walkable area yields the same
        value, so a map split by a ledge or water (Route 104 either side of the Woods) reads
        as two regions and a block learned in one does not bind the other. A ledge hop is left
        out, since it is one-way: the summit of Mt. Ember reaches the base by jumping down, so
        following ledges gave both the base's label and the summit inherited the base's blocks."""
        return self.region_tiles(start, surf)[0]

    def region_tiles(self, start: tuple, surf: bool = False) -> tuple:
        """(region label, every tile the region walk visited), so a caller labelling many tiles
        of one area runs the walk once instead of once per tile."""
        start_elev = self._start_elev(start)
        boulders = frozenset(self.pushable)
        seen = {(start, start_elev, boulders)}
        q = deque([(start, start_elev, boulders)])
        low = start
        while q:
            cur, carried, boulders = q.popleft()
            low = min(low, cur)
            for nxt, d in self._steps(cur, carried, start, surf, boulders):
                if self._ledge_hop(cur[0] + d[0], cur[1] + d[1]) == d:
                    continue
                key = (nxt, self._carry(nxt, carried, surf), self._after_push(cur, d, boulders))
                if key not in seen:
                    seen.add(key)
                    q.append(key)
        return low, {tile for tile, _, _ in seen}

    def reachable(self, start: tuple, surf: bool = False) -> set:
        """Every tile walkable from start under the same elevation and NPC rules as region()."""
        start_elev = self._start_elev(start)
        boulders = frozenset(self.pushable)
        seen = {(start, start_elev, boulders)}
        q = deque([(start, start_elev, boulders)])
        while q:
            cur, carried, boulders = q.popleft()
            for nxt, d in self._steps(cur, carried, start, surf, boulders):
                key = (nxt, self._carry(nxt, carried, surf), self._after_push(cur, d, boulders))
                if key not in seen:
                    seen.add(key)
                    q.append(key)
        return {tile for tile, _, _ in seen}

    def dive_tiles(self, start: tuple, surf: bool = True) -> list:
        """Reachable tiles whose behavior carries a dive or emerge warp, nearest to start first.
        Empty when the tileset is unknown or none is reachable."""
        if self._behavior is None:
            return []
        here = [t for t in self.reachable(start, surf)
                if self._behavior(self.cell(*t) & S.GRID_ID_MASK) in DIVE_BEHAVIORS]
        return sorted(here, key=lambda t: abs(t[0] - start[0]) + abs(t[1] - start[1]))

    def emerge_tiles(self, start: tuple, surf: bool = True) -> list:
        """Reachable tiles that surface on a B-press, nearest to start first. Warp tiles drop out
        so the goal is never the back-warp that would walk off the map, and the two
        MetatileBehavior_IsUnableToEmerge behaviors drop out so the surface prompt actually opens.
        Empty when the tileset is unknown."""
        if self._behavior is None:
            return []
        here = [t for t in self.reachable(start, surf)
                if t not in self.warp_tiles
                and self._behavior(self.cell(*t) & S.GRID_ID_MASK) not in NO_SURFACE_BEHAVIORS]
        return sorted(here, key=lambda t: abs(t[0] - start[0]) + abs(t[1] - start[1]))

    def path(self, start: tuple, goal: tuple, surf: bool = False) -> list | None:
        """List of (dx, dy) steps from start to goal, or None when unreachable.

        BFS state carries the walker's height under the rules at the top of this file, so a
        cliff between heights stays blocked and a transition corridor joins the areas it
        touches. With surf, water is mounted from height 3 and left onto a height-3 bank, so
        one water body joins the shores it touches. A land route wins over a water one when
        both exist, since the game refuses the dismount on some banks (Petalburg's pond, south
        side) that the grid reads as open.
        """
        if surf:
            land = self._path(start, goal, False)
            if land is not None:
                return land
        return self._path(start, goal, surf)

    def _path(self, start: tuple, goal: tuple, surf: bool) -> list | None:
        start_elev = self._start_elev(start)
        boulders = frozenset(self.pushable)
        prev = {(start, start_elev, boulders): None}
        q = deque([(start, start_elev, boulders)])
        reached = None
        while q:
            cur, carried, boulders = q.popleft()
            if cur == goal:
                reached = (cur, carried, boulders)
                break
            for nxt, d in self._steps(cur, carried, start, surf, boulders):
                if nxt in self.warp_tiles and nxt != goal:
                    continue
                # a margin cell belongs to the neighbouring map and stepping on it fires the map
                # change, so it is a goal (the edge crossing) and never a waypoint
                if not self.inside(*nxt) and nxt != goal:
                    continue
                key = (nxt, self._carry(nxt, carried, surf), self._after_push(cur, d, boulders))
                if key in prev:
                    continue
                prev[key] = ((cur, carried, boulders), d)
                q.append(key)
        if reached is None:
            return None
        steps = []
        node = reached
        while prev[node]:
            node, d = prev[node]
            steps.append(d)
        return steps[::-1]


class Navigator:
    def __init__(self, emu: eb.Emu, run: Callable[[int, int], None]):
        self.e = emu
        self.g = GameState(emu)
        self.run = run

    def settle_map(self) -> None:
        """Run frames until the layout buffer belongs to the current map, so the first grid
        read after a crossing is the new map's."""
        for _ in range(MAP_LOAD_FRAMES // 5):
            if map_loaded(self.e):
                return
            self.run(5, 0)

    def step(self, d: tuple, slide: bool = False) -> bool:
        """Hold a direction until the tile changes; False when nothing moved. With `slide` the
        step is onto ice, so wait until the tile stops changing before the next press lands."""
        x, y, *_ = self.g.position()
        key = DIRS[d]
        for _ in range(24):
            self.run(2, key)
            nx, ny, *_ = self.g.position()
            if (nx, ny) != (x, y):
                self.run(10, 0)
                while slide:
                    last = self.g.position()[:2]
                    self.run(SLIDE_SETTLE_FRAMES, 0)
                    if self.g.position()[:2] == last:
                        break
                return True
            if self.g.in_battle():
                return False
        self.run(4, 0)
        return False

    def _mount(self, d: tuple) -> bool:
        """Face the water and accept the "Would you like to SURF?" prompt; the Yes
        places the player on the water tile, so a position change confirms the mount.
        ROWE makes Surf usable without the badge, so no HM-teach step precedes this."""
        x, y, *_ = self.g.position()
        self.run(4, DIRS[d])
        self.run(2, 0)
        for _ in range(8):
            self.run(2, eb.KEY_A)
            self.run(20, 0)
            nx, ny, *_ = self.g.position()
            if (nx, ny) != (x, y):
                self.run(10, 0)
                return True
            if self.g.in_battle():
                return False
        return False

    def _advance(self, grid: Grid, cur: tuple, d: tuple, surf: bool) -> bool:
        """Take one step, first clearing a cuttable tree or breakable rock in the way, then
        mounting Surf when the step crosses from land onto water. Dismount is automatic on the
        step back onto land, so it needs no extra press."""
        nxt = (cur[0] + d[0], cur[1] + d[1])
        if nxt in grid.pushable:
            if not self._push(d):
                return False
            # the plan's later steps were searched against the boulder's new tile
            grid.pushable.discard(nxt)
            grid.pushable.add((nxt[0] + d[0], nxt[1] + d[1]))
            return True
        tool = grid.clearable.get(nxt)
        if tool is not None and tool in grid.tools:
            if not self._clear_obstacle(nxt, d):
                return False
            return self.step(d)
        if surf:
            if grid._is_waterfall(*nxt):
                return self._climb()
            # a current is water too: from a shoal (Route 133's shallows) the press into the
            # belt needs the Surf prompt before the ride starts
            if not grid._is_water(*cur) and (grid._is_water(*nxt) or grid._current(*nxt) is not None):
                return self._mount(d)
        return self.step(d, slide=grid._is_ice(*nxt))

    def _clear_obstacle(self, nxt: tuple, d: tuple) -> bool:
        """Face the tree or rock at `nxt` and run its field-move interaction: the facing A opens
        the yes/no prompt (EventScript_CutTree, EventScript_RockSmash), and A on the default YES
        cuts or smashes it, so removeobject drops the object event and the tile reads walkable.
        True once the object is gone. Rock Smash can roll a wild encounter on the break, which
        returns False here and surfaces as a battle on the next walk_to check."""
        self.run(4, DIRS[d])
        self.run(2, 0)
        for _ in range(CLEAR_TICKS):
            self.run(8, eb.KEY_A)
            self.run(30, 0)
            if self.g.in_battle():
                return False
            if nxt not in Grid(self.e).blocked_by_npc:
                return True
        return nxt not in Grid(self.e).blocked_by_npc

    def _push(self, d: tuple) -> bool:
        """Shove the boulder one tile ahead by holding d into it, after accepting the map's Power
        Glove prompt once. The player's tile changes while the slow push walk is still running,
        so the settle idles through it before the next press. False when nothing moved."""
        if not self.g.flag(FLAG_POWER_GLOVE):
            self._accept_power_glove(d)
        x, y, *_ = self.g.position()
        for _ in range(PUSH_FRAMES // 2):
            self.run(2, DIRS[d])
            if self.g.position()[:2] != (x, y):
                self.run(PUSH_SETTLE_FRAMES, 0)
                return True
            if self.g.in_battle():
                return False
        self.run(4, 0)
        return False

    def _accept_power_glove(self, d: tuple) -> None:
        """Face the boulder and answer its prompt: A opens "do you want to use the Power Glove to
        push it?", A takes the default Yes, and a third A closes the line that follows. A push
        pressed inside that last line's window stays dead, hence the idle after it."""
        self.run(4, DIRS[d])
        self.run(2, 0)
        for idle in (40, 40, 60):
            self.run(8, eb.KEY_A)
            self.run(idle, 0)

    def _climb(self) -> bool:
        """Face the fall and accept the Waterfall Tool prompt; the ride ends on the first tile
        above the fall, so a position change confirms it. The A lands only on a fresh facing:
        after a press into the fall the game ignores it, so the player turns away and back
        first. A 4-frame press turns in place, except right after that bump, when it walks;
        a turn that moved the player reports no climb and the replan retries once settled."""
        x, y, *_ = self.g.position()
        for key in (eb.KEY_DOWN, eb.KEY_UP):
            self.run(4, key)
            self.run(20, 0)
        if self.g.position()[:2] != (x, y):
            return False
        self.run(8, eb.KEY_A)
        self.run(60, 0)
        self.run(8, eb.KEY_A)
        last = (x, y)
        for _ in range(CLIMB_TICKS):
            self.run(30, 0)
            if self.g.in_battle():
                return False
            now = self.g.position()[:2]
            if now == last:
                return now != (x, y)
            last = now
        return last != (x, y)

    def walk_to(self, goal: tuple, surf: bool = False, max_replans: int = 20, tools=frozenset()) -> str:
        """'arrived', 'battle', 'map_changed', 'unreachable', or 'stuck'.

        A goal inside the margin of a connected map is reachable; crossing the
        edge rebases the coordinates to the new map, reported as map_changed so
        the caller plans the rest in that map's frame. A step that moved nothing
        is a wandering NPC on the next tile or a trainer's challenge text, so the
        replan presses B and waits; Route 103's east corridor holds three
        wanderers in a two-tile lane, Route 104's woods door has a trainer.
        """
        x, y, group, num = self.g.position()
        here = (group, num)
        refused = set()  # tiles a step would not enter; a second refusal routes around the tile
        dead = set()
        for _ in range(max_replans):
            x, y, group, num = self.g.position()
            if (group, num) != here:
                self.settle_map()
                return "map_changed"
            if (x, y) == goal:
                return "arrived"
            grid = Grid(self.e)
            grid.climb = any(item == ITEM_WATERFALL_TOOL for item, _ in self.g.key_items())
            grid.tools = tools
            grid.blocked_by_npc |= dead
            steps = grid.path((x, y), goal, surf)
            if steps is None:
                return "unreachable"
            for d in steps:
                cur = self.g.position()[:2]
                moved = self._advance(grid, cur, d, surf)
                if self.g.in_battle():
                    return "battle"
                if self.g.position()[2:] != here:
                    self.settle_map()
                    return "map_changed"
                if not moved:
                    # a trainer who spotted the walker opens his line and holds the player
                    # until a button lands; B advances it (into the battle) or does nothing
                    self.run(8, eb.KEY_B)
                    self.run(NPC_WAIT_FRAMES, 0)
                    if self.g.in_battle():
                        return "battle"
                    nxt = (cur[0] + d[0], cur[1] + d[1])
                    if nxt in refused:
                        dead.add(nxt)
                        # the game refused a step the grid allows, twice; the save at that
                        # moment holds whatever stood on the tile, which a later copy cannot
                        path = f"/tmp/rowe_dead_step_{int(time.time())}"
                        with open(path + ".ss", "wb") as f:
                            f.write(self.e.save_state())
                        print(f"dead step {cur} -> {nxt} on {here}: state {path}.ss", flush=True)
                    refused.add(nxt)
                    break
        x, y, *_ = self.g.position()
        return "arrived" if (x, y) == goal else "stuck"
