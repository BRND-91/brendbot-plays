"""Multi-map errands built on nav: the Oldale Pokémon Center heal run.

Map ids are ROWE's (vanilla Emerald numbering): Route 101 (0,16), Oldale Town
(0,10), Oldale Pokémon Center 1F (2,2). Inside the Center the nurse is object
localId 1 behind a one-tile counter, so the player talks from two tiles below.
"""
import struct
from typing import Callable

import emu_boot as eb
import rowe_map
import rowe_rom
import rowe_symbols as S
from rowe_state import decode_text
import script_decode
import gym_maze
import region_route
from nav import DIRS, GATE_SETTLE_FRAMES, ITEM_WATERFALL_TOOL, THIN_ICE, Grid, Navigator

ROUTE_101 = (0, 16)
OLDALE = (0, 10)
NURSE_LOCAL_ID = 1
START_MENU_ROWS = 12         # Pokédex through Exit on ROWE's start menu; the cursor wraps at both ends
MENU_ROW_POLLS = 6           # reads of the sailor's row list after the field locks before it is called empty
MENU_ROW_POLL_FRAMES = 15
MART_COUNTER_TILE = (3, 3)   # right of the counter end at (2,3), facing the clerk at (1,3) through
                             # it; the tile below the counter is an NPC's post in Mossdeep's Mart
BOX_PC_STAND = (10, 3)       # tile below the storage PC on the shared Center layout, face up to boot it
PAD_FIRE_TICKS = 6          # 10-frame waits for a teleport pad to fire after the step onto it lands (20 measured)
JACK_STAND = (4, 4)          # two below the blue nurse at (4, 2) on that layout, face up across the counter
MOVE_UP, MOVE_DOWN = (0, -1), (0, 1)
# stand tile offset from the ball -> the key that faces the ball from that side
STAND_FACING = {(0, 1): eb.KEY_UP, (0, -1): eb.KEY_DOWN, (1, 0): eb.KEY_LEFT, (-1, 0): eb.KEY_RIGHT}
# pokeemerald MB_*_ARROW_WARP behaviors -> the press that fires the warp from the tile itself.
# 0x6d is MB_WATER_SOUTH_ARROW_WARP, the dive-tunnel current linking underwater maps (Sootopolis
# (24,5) tile (9,8) -> (0,51)); it fires on a south press, same as the land south arrow 0x65.
GATE_PRESSES = 8  # A presses through a door guard's script, the count that walked the League's guards aside on the lobby fixture
ARROW_WARP_KEYS = {0x62: eb.KEY_RIGHT, 0x63: eb.KEY_LEFT, 0x64: eb.KEY_UP, 0x65: eb.KEY_DOWN,
                   0x6d: eb.KEY_DOWN}


def bag_pocket_key(cur: int, target: int) -> int:
    """Shoulder key that reaches bag tab `target` from `cur` in the fewest taps; the tabs wrap."""
    ahead = (target - cur) % S.BAG_POCKET_COUNT
    return eb.KEY_RIGHT if ahead <= S.BAG_POCKET_COUNT // 2 else eb.KEY_LEFT


def route_state_matches(live: tuple, recorded: tuple) -> bool:
    """A recorded (tile, gate bytes) entry matches the live read on tile and gates, or on tile
    alone when its gate bytes are all zero. The Fortree recording holds real orientations up to
    press 55 and zeros from press 56 on, while the game reads non-zero bytes on those tiles, so
    an exact compare left the route at (1, 7) every visit."""
    if live[0] != recorded[0]:
        return False
    return not any(recorded[1]) or live[1] == recorded[1]


def landing_rank(hop: tuple, nxt: tuple | None, surf: bool = False, climb: bool = False, chain: tuple = ()):
    """(rank, w, h) for a crossing into `hop`, off its ROM layout, or None when unreadable.
    rank(landing_tile) is (0, -region size) when the tile's region under `surf` and `climb`
    reaches hop's crossing toward `nxt` (or no such crossing is known) and that crossing's own
    landing threads the maps in `chain` after it, (1, -size) when it does not, (2, 0) off the
    map. A pocket (Route 104's east cove, Petalburg's pond-locked northwest) is small and reaches
    nothing, so it ranks behind the map proper. A surf crossing lands on water, so its region is
    read w/ surf, else every bank is a pocket. The chain is what tells Victory Road 1F's two halves
    apart: both hold a door to Ever Grande, only the north one's door lands by the League."""
    gw = region_route.grid(hop)
    if gw is None:
        return None
    grid, w, h = gw
    grid.climb = climb
    # target tile -> the landing on nxt it crosses to, None for a tile whose arrival the ROM does
    # not name (a talked crossing), which threads on trust
    targets = {}
    for p in region_route.portals(hop):
        if p.dest == nxt and p.landings is not None:
            targets.update(p.landings)
    # a talked crossing (the Seagallop sailor) is reached from the tiles beside its object, so a
    # landing whose region holds none of them ranks behind: Icefall Cave's three ladders up land in
    # two pockets of (1,27) and only one holds the sailor
    talked = script_decode.talk_object(hop, nxt) if nxt is not None else None
    if talked is not None:
        ox, oy = talked["obj"]
        targets.update({(ox, oy + 1): None, (ox, oy - 1): None, (ox + 1, oy): None, (ox - 1, oy): None})
    memo = {}
    # tile -> region label, filled a whole region at a time: the edge crossing ranks every border
    # tile and its neighbours, and a region walk per tile ran 2 to 3 seconds on an 80x40 city map
    # with the frame frozen for all of it
    label = {}

    def rank(landing: tuple) -> tuple:
        # a door or stair warp lands on a pad metatile that reads blocked; the player steps off it
        # onto an orthogonal neighbour, so rank the best tile actually stood on, the pad or a
        # neighbour, else a front-mat door scores (2, 0) and loses to a dead-end pocket next door
        best = (2, 0)
        for tile in (landing, (landing[0], landing[1] + 1), (landing[0], landing[1] - 1),
                     (landing[0] + 1, landing[1]), (landing[0] - 1, landing[1])):
            c = grid.cell(*tile)
            if c & S.GRID_ID_MASK == S.GRID_UNDEFINED or c & S.GRID_BLOCKED:
                continue
            if tile not in label:
                low, tiles = grid.region_tiles(tile, surf)
                for t in tiles:
                    label[t] = low
            region = label[tile]
            if region not in memo:
                reach = grid.reachable(tile, surf)
                onward = not targets or any(t in reach and region_route.threads(nxt, l, tuple(chain), surf, climb)
                                            for t, l in targets.items())
                memo[region] = (0 if onward else 1, -len(reach))
            if memo[region] < best:
                best = memo[region]
        return best
    return rank, w, h


class Errands:
    def __init__(self, emu: eb.Emu, run: Callable[[int, int], None], log: Callable[[str], None] = print):
        self.e = emu
        self.run = run
        self.nav = Navigator(emu, run)
        self.g = self.nav.g
        self.log = log

    def map_id(self) -> tuple:
        return self.g.position()[2:]

    def _landed(self, before: tuple) -> bool:
        """True once a warp has left map `before` and the new map's layout is readable."""
        if self.map_id() == before:
            return False
        self.nav.settle_map()
        return True

    def tap(self, key: int) -> None:
        self.run(8, key)
        self.run(12, 0)

    def cross_edge(self, direction: int, surf: bool = False, rank: Callable | None = None, tools=frozenset()) -> str:
        """Walk through the map connection in this direction; returns walk_to's status.
        With surf, a water edge the party can now cross counts as a reachable edge.
        `rank(edge_tile)` -> (class, -landing region size) keeps class-0 tiles only and
        orders them biggest landing region first; a map split into regions (Petalburg's
        pond-locked northwest) otherwise takes the nearest tile and lands the walk where
        its next hop is unreachable."""
        # a current ride can set the surfer down somewhere the chosen edge tile no longer
        # reaches (Route 133's belts end on a shoal), so a walk that moved and then lost its
        # goal picks a fresh edge tile from where it landed
        status, pos = "unreachable", None
        while status == "unreachable" and pos != self.g.position()[:2]:
            pos = self.g.position()[:2]
            status = self._cross_edge_once(direction, surf, rank, tools)
        return status

    def _cross_edge_once(self, direction: int, surf: bool, rank: Callable | None, tools=frozenset()) -> str:
        grid = Grid(self.e)
        grid.tools = tools
        x, y, *_ = self.g.position()
        w, h = grid.width - 2 * S.MAP_OFFSET, grid.height - 2 * S.MAP_OFFSET
        if direction == rowe_map.DIR_NORTH:
            goals = [(cx, -1) for cx in range(w)]
        elif direction == rowe_map.DIR_SOUTH:
            goals = [(cx, h) for cx in range(w)]
        elif direction == rowe_map.DIR_WEST:
            goals = [(-1, cy) for cy in range(h)]
        else:
            goals = [(w, cy) for cy in range(h)]
        # reachable() walks the same steps path() does, and it includes a margin tile a current
        # delivers the surfer to (Route 133's belts into Route 134) that passable() refuses
        reach = grid.reachable((x, y), surf)
        goals = [gl for gl in goals if gl in reach]
        if rank is not None:
            # a landing whose region reaches the next hop first; when none does, any landing
            # still beats standing here, since the far side re-plans from where it lands
            goals = [gl for gl in goals if rank(gl)[0] == 0] or goals
        if not goals:
            return "unreachable"
        goals.sort(key=lambda gl: (rank(gl)[1] if rank else 0, abs(gl[0] - x) + abs(gl[1] - y)))
        return self.nav.walk_to(goals[0], surf=surf, tools=tools)

    def take_dive(self, direction: int, surf: bool = False, tools=frozenset()) -> str:
        """Submerge (DIR_DIVE) through this map's dive connection. ROWE's Dive Gear is a zero-badge
        start item, so the dive needs no HM and no party move, only a Surf mount onto a deep-water
        tile and an A press, the same path vanilla Emerald takes over dark water: field_control_avatar.c
        fires on pressedAButton while the avatar stands on an IsDiveable tile, and TrySetupDiveDownScript
        runs EventScript_UseDive. Walk onto the nearest reachable diveable tile, press A, confirm the
        "Would you like to Dive?" prompt, and read the warp. "map_changed", "battle", "stuck", or
        "unreachable".

        DIR_EMERGE surfaces from an underwater map through a yes/no dialogue: B opens "Would you
        like to surface?", A answers YES on the default cursor, then the warp follows the map's
        EMERGE connection or its setdivewarp point. emerge_tiles drops the back-warp tile and the
        two no-surfacing behaviors, nearest first, until one tile warps."""
        if direction == rowe_map.DIR_EMERGE:
            before = self.map_id()
            grid = Grid(self.e)
            grid.tools = tools
            x, y, *_ = self.g.position()
            for tile in grid.emerge_tiles((x, y), surf)[:13]:
                if tile != (x, y):
                    r = self.nav.walk_to(tile, surf=surf, tools=tools)
                    if r == "battle":
                        return r
                    if r != "arrived":
                        continue
                # walk_to returns on the coordinate change, which lands at the start of the last
                # step, and the game drops an A/B press made mid-step (FieldGetPlayerInput reads
                # them only at tile center or standing still). Underwater moves at walking speed,
                # 16 frames a tile, so let the step finish before the press.
                self.run(16, 0)
                self.run(24, eb.KEY_B)   # "Would you like to surface?" yes/no, cursor on YES
                self.run(60, 0)          # the surface prompt is two lines; A before it finishes
                self.run(24, eb.KEY_A)   # opening advances the text instead of selecting YES
                self.run(120, 0)
                if self._landed(before):
                    return "map_changed"
            return "stuck"
        grid = Grid(self.e)
        grid.tools = tools
        x, y, *_ = self.g.position()
        targets = grid.dive_tiles((x, y), surf=surf)
        if not targets:
            return "unreachable"
        before = self.map_id()
        for tile in targets:
            r = self.nav.walk_to(tile, surf=surf, tools=tools)
            if r in ("battle", "map_changed"):
                return r
            if r != "arrived":
                continue
            self.run(24, eb.KEY_A)  # "The sea is deep here. Would you like to Dive?"
            self.run(16, 0)
            self.run(24, eb.KEY_A)  # the yes/no cursor defaults to YES
            self.run(120, 0)
            if self._landed(before):
                return "map_changed"
        return "stuck"

    def enter_warp(self, dest: tuple, surf: bool = False) -> str:
        """Walk to the tile below a door that leads to dest and step up into it. With surf the
        approach may cross water, which is the only way out of Petalburg's pond-locked northwest
        pocket, where Route 104's north half lets the party in."""
        w = rowe_map.warp_to(self.e, *dest)
        if w is None:
            return "no_warp"
        r = self.nav.walk_to((w.x, w.y + 1), surf=surf)
        if r != "arrived":
            return r
        before = self.map_id()
        self.run(24, eb.KEY_UP)
        self.run(120, 0)
        return "map_changed" if self._landed(before) else "stuck"

    def leave_by_warp(self, dest: tuple) -> str:
        """Leave the current building through the warp back to `dest`, ranked so the biggest
        landing region wins. Several warps can share the town id (Lavaridge's front mat and its
        hot-spring back door both read (0,12)); unranked warp_to took the first in the header,
        the dead-end pocket, and the walk bounced the town border. take_warp scores the step-off
        tile, so the real front door outranks the pocket."""
        lr = landing_rank(dest, None)
        warp_rank = None
        if lr is not None:
            rank, dest_warps = lr[0], rowe_rom.map_warps(*dest)

            def warp_rank(wp: rowe_map.Warp) -> tuple:
                return rank(dest_warps[wp.dest_warp][:2]) if wp.dest_warp < len(dest_warps) else (2, 0)
        return self.take_warp(dest, rank=warp_rank)

    def take_warp(self, dest: tuple, surf: bool = False, rank: Callable | None = None, tools=frozenset()) -> str:
        """Leave the current map through a warp to dest: "map_changed", "battle", "no_warp",
        or "stuck". When several warps lead there (a cave with two mouths onto one route),
        `rank(warp)` -> (class, -landing region size) orders them biggest landing region
        first, class 0 before the rest. Warps sharing a dest_warp land on one tile and are one
        door, so only the first is tried, and within a rank tie the warp nearest the map's
        bottom edge goes first, the exit mat's usual spot. With surf the approach may cross
        water (Petalburg Woods' pond is its only north link)."""
        ws = [w for w in rowe_map.warps(self.e) if (w.dest_group, w.dest_num) == dest]
        if not ws:
            # a dynamic return warp reads its header target as MAP_DYNAMIC and resolves the real
            # destination only when stepped through, so no concrete dest matches it. Fall back to it
            # and take wherever it lands; covers every link room and the League exit, not just here.
            ws = [w for w in rowe_map.warps(self.e) if (w.dest_group, w.dest_num) == S.MAP_DYNAMIC]
        if not ws:
            return "no_warp"
        grid = Grid(self.e)
        ws = [w for w in ws if not grid.is_wall_warp(w.x, w.y)]
        if not ws:
            return "unreachable"
        ws.sort(key=lambda w: (rank(w) if rank else (0, 0), -w.y))
        seen, doors = set(), []
        for w in ws:
            if w.dest_warp in seen:
                continue
            seen.add(w.dest_warp)
            doors.append(w)
        for w in doors:
            r = self._step_into_warp(w, surf, tools)
            if r in ("map_changed", "battle"):
                return r
        return "stuck"

    def fall_through(self, dest: tuple, surf: bool = False, rank: Callable | None = None, tools=frozenset()) -> str:
        """Drop to `dest` through thin ice: the map's hole warp lands at the same x,y on dest, so the
        tile picks the landing. Reachable thin-ice tiles are ordered by `rank(tile)` (class, -landing
        region size, the same order take_warp uses) then nearness, and each is walked onto, off to a
        neighbour, and back on until the map changes. "map_changed", "wrong_map", "battle",
        "unreachable" when no thin ice is reachable, else "stuck"."""
        grid = Grid(self.e)
        grid.tools = tools
        x, y, *_ = self.g.position()
        reach = grid.reachable((x, y), surf)
        ice = [t for t in reach if grid._behavior(grid.cell(*t) & S.GRID_ID_MASK) == THIN_ICE]
        if not ice:
            return "unreachable"
        ice.sort(key=lambda t: (rank(t) if rank else (0, 0), abs(t[0] - x) + abs(t[1] - y)))
        src = self.map_id()
        for tile in ice[:3]:
            sides = ((tile[0], tile[1] + 1), (tile[0], tile[1] - 1), (tile[0] + 1, tile[1]), (tile[0] - 1, tile[1]))
            off = next((n for n in sides if n in reach and n not in ice), None)
            if off is None:
                continue
            print(f"  hole: thin ice {tile} toward {list(dest)}, stepping off to {off}", flush=True)
            for _ in range(4):
                for goal in (tile, off):
                    r = self.nav.walk_to(goal, surf=surf, tools=tools)
                    if r == "battle":
                        return r
                    self.run(60)
                    land = self.map_id()
                    if land != src:
                        return "map_changed" if land == dest else "wrong_map"
        return "stuck"

    def talk_warp(self, obj: tuple, dest: tuple, label: str | None, approach: tuple | None = None, presses: int = 8,
                  surf: bool = False, tools=frozenset()) -> str:
        """Drive an NPC's native scrolling-multichoice crossing (the Seagallop sailor) to dest, or,
        when `label` is None, a plain scripted door whose warp command fixes the destination. Walk to
        `approach` and face the object (talk_object resolves the tile from the object's fixed facing;
        None falls back to the first walkable neighbour off the live grid under `surf` and `tools`,
        the same passability the walk itself gets), A through the greeting
        until the menu locks the field, step the
        selection down to the row whose on-screen text is `label`, then A until the map changes.
        "map_changed" on landing dest, "wrong_map" on landing elsewhere (a per-destination flag still
        shut sends the party back onto the deck), "no_menu" when the menu never opened, "no_row" when
        `label` is absent from the live option list, "locked" when the A on the row left the field
        held with the menu gone (the row's no-go text box, a dock island not yet open), else walk_to's
        status or "stuck". The row is
        matched by text, since ScriptMenu_ScrollingMultichoice runs in native code the bytecode walker
        can't read, so script_edges carries these crossings chain-unknown and the destination comes off
        the live menu rather than menu_sequence. The visible cursor caps at the bottom window row while
        the list scrolls under it, so the absolute row is driven by the DOWN-press count, not a cursor
        read."""
        src = self.map_id()
        if approach is None:
            approach = self._approach_tile(obj, surf, tools)
            if approach is None:
                return "unreachable"
        r = self.nav.walk_to(approach, surf=surf, tools=tools)
        if r == "unreachable":
            # the side a fixed-facing object looks at can be solid (the (1,9) dispatcher faces up
            # into the wall tile at (40,6)), and the talk opens from any side, so stand on the
            # first reachable neighbour instead
            side = self._approach_tile(obj, surf, tools)
            if side is None or side == approach:
                return r
            print(f"talk_warp approach {approach} unreachable, standing at {side}", flush=True)
            approach = side
            r = self.nav.walk_to(approach, surf=surf, tools=tools)
        if r != "arrived":
            return r
        self.run(8, STAND_FACING[(approach[0] - obj[0], approach[1] - obj[1])])
        self.run(8, 0)
        if label is None:
            # the destination is fixed by the script's own warp command, so no row is chosen:
            # press A through the greeting and any yes/no (the prompt opens on Yes) until it fires.
            for _ in range(presses * 2):
                self.tap(eb.KEY_A)
                self.run(60, 0)
                land = self.map_id()
                if land != src:
                    return "map_changed" if land == dest else "wrong_map"
            return "locked" if self.e.read(S.FIELD_LOCKED, 1)[0] else "stuck"
        rows = {}
        for press in range(presses):
            self.tap(eb.KEY_A)
            self.run(45, 0)
            if not (self.e.read(S.FIELD_LOCKED, 1)[0] and self.map_id() == src):
                continue
            rows = self._menu_rows()
            for n in range(1, MENU_ROW_POLLS):
                # the field locks before the list template fills, so an empty read gets a bounded
                # re-read; the row that fired is logged, the miss it bounds is still open
                if rows:
                    break
                self.run(MENU_ROW_POLL_FRAMES, 0)
                rows = self._menu_rows()
                if rows:
                    print(f"ferry rows: empty on read 1, filled on read {n + 1}", flush=True)
            if rows:
                break
            # a lock with no list is a greeting text box ahead of the menu (the (1,9) dispatcher
            # talks for three A's before its island list), so the next A advances it
        if not rows:
            return "no_menu"
        if press:
            print(f"ferry rows: menu opened on A press {press + 1}", flush=True)
        row = next((idx for idx, text in sorted(rows.items()) if text == label), None)
        if row is None:
            # the menu opened but no row's text equals `label`: log what it did list against what
            # was sought so an empty read (the array wasn't found) is told apart from a text
            # mismatch (the row is worded differently) without a live-save probe
            print(f"ferry no_row: want {label!r} among {sorted(rows.items())}", flush=True)
            self._dump_menu_array()
            return "no_row"
        for _ in range(row):
            self.tap(eb.KEY_DOWN)
            self.run(18, 0)
        # A selects the island row, which opens the sailor's "sail to X?" yes/no. It draws on Yes, but
        # a stray frame can leave the cursor on No and close the box unanswered (field_locked 0, no
        # warp), so after the select put the cursor back on Yes before each A until the ferry fires.
        self.tap(eb.KEY_A)
        self.run(60, 0)
        for _ in range(presses):
            self.tap(eb.KEY_UP)
            self.run(8, 0)
            self.tap(eb.KEY_A)
            self.run(90, 0)
            if self.map_id() != src:
                break
        land = self.map_id()
        if land == dest:
            return "map_changed"
        if land != src:
            return "wrong_map"
        if self.e.read(S.FIELD_LOCKED, 1)[0] and not self._menu_rows():
            return "locked"
        print(f"ferry stuck: row {row} label {label!r} src {src} "
              f"field_locked {self.e.read(S.FIELD_LOCKED, 1)[0]} "
              f"rows {sorted(self._menu_rows().items())}", flush=True)
        return "stuck"

    def talk_menu(self, obj: tuple, path: list, approach: tuple | None = None, presses: int = 8) -> str:
        """Drive a native multichoice NPC down a nested `path` of on-screen row labels, one label per
        menu level, to a leaf action such as the island clerk's ticket handout. Walk to `approach`,
        face `obj`, A through the greeting until the field locks, then for each label read the live
        rows, step down to the matching row, and A into the next level. After the last label, A
        through the closing text and B out. "done" when every label matched and the field released,
        "stuck" when it stayed held, "no_menu" when the first menu never opened, "no_row:<label>" when
        a level's rows lack the label, else walk_to's status. The caller checks the bag for the
        granted item; this drives the menu only. The row is matched by text and the absolute row is the
        DOWN-press count, same as talk_warp, since the list runs in native code the walker can't read."""
        if approach is None:
            approach = self._approach_tile(obj)
            if approach is None:
                return "unreachable"
        r = self.nav.walk_to(approach)
        if r != "arrived":
            return r
        # a counter NPC is approached from a tile two away on one axis, so facing comes off the axis
        # sign rather than the adjacent-only STAND_FACING lookup talk_warp uses
        dx, dy = obj[0] - approach[0], obj[1] - approach[1]
        if dx == 0 and dy != 0:
            face = eb.KEY_UP if dy < 0 else eb.KEY_DOWN
        elif dy == 0 and dx != 0:
            face = eb.KEY_LEFT if dx < 0 else eb.KEY_RIGHT
        else:
            raise ValueError(f"approach {approach} is not on one axis from {obj}")
        self.run(8, face)
        self.run(8, 0)
        src = self.map_id()
        opened = False
        for _ in range(presses):
            self.tap(eb.KEY_A)
            self.run(45, 0)
            if self.e.read(S.FIELD_LOCKED, 1)[0] and self.map_id() == src:
                opened = True
                break
        if not opened:
            return "no_menu"
        for label in path:
            rows = self._menu_rows()
            row = next((idx for idx, text in sorted(rows.items()) if text == label), None)
            if row is None:
                print(f"clerk no_row: want {label!r} among {sorted(rows.items())}", flush=True)
                return f"no_row:{label}"
            for _ in range(row):
                self.tap(eb.KEY_DOWN)
                self.run(18, 0)
            self.tap(eb.KEY_A)
            self.run(60, 0)
        for _ in range(presses):
            self.tap(eb.KEY_A)
            self.run(45, 0)
            if not self.e.read(S.FIELD_LOCKED, 1)[0]:
                break
        for _ in range(4):
            self.tap(eb.KEY_B)
            self.run(20, 0)
        return "done" if not self.e.read(S.FIELD_LOCKED, 1)[0] else "stuck"

    def peek_menu(self, obj: tuple, approach: tuple | None = None, presses: int = 8) -> "dict | str":
        """Open a native multichoice NPC's menu, read its rows, and B out without selecting, so a
        clerk whose top menu is native-built can be decoded off the live run without risking a handout
        on an unknown row. Returns the {row: label} dict on success, "no_menu" when it never opened,
        "unreachable" when no approach tile resolves, else walk_to's status."""
        if approach is None:
            approach = self._approach_tile(obj)
            if approach is None:
                return "unreachable"
        r = self.nav.walk_to(approach)
        if r != "arrived":
            return r
        dx, dy = obj[0] - approach[0], obj[1] - approach[1]
        if dx == 0 and dy != 0:
            face = eb.KEY_UP if dy < 0 else eb.KEY_DOWN
        elif dy == 0 and dx != 0:
            face = eb.KEY_LEFT if dx < 0 else eb.KEY_RIGHT
        else:
            raise ValueError(f"approach {approach} is not on one axis from {obj}")
        self.run(8, face)
        self.run(8, 0)
        src = self.map_id()
        opened = False
        for _ in range(presses):
            self.tap(eb.KEY_A)
            self.run(45, 0)
            if self.e.read(S.FIELD_LOCKED, 1)[0] and self.map_id() == src:
                opened = True
                break
        if not opened:
            return "no_menu"
        rows = self._menu_rows()
        for _ in range(6):
            self.tap(eb.KEY_B)
            self.run(20, 0)
            if not self.e.read(S.FIELD_LOCKED, 1)[0]:
                break
        return rows

    def _approach_tile(self, obj: tuple, surf: bool = False, tools=frozenset()) -> tuple | None:
        """First walkable tile adjacent to `obj`, off the live collision grid under the party's surf
        and field tools, for a wandering object whose fixed facing talk_object could not resolve.
        None when every neighbour is solid."""
        grid = Grid(self.e)
        grid.tools = tools
        reach = grid.reachable(self.g.position()[:2], surf)
        for dx, dy in STAND_FACING:
            if (obj[0] + dx, obj[1] + dy) in reach:
                return (obj[0] + dx, obj[1] + dy)
        return None

    def _menu_rows(self) -> dict:
        """{row index: option text} for the open native multichoice, read straight off the live
        ListMenuTemplate: the items pointer at +0x00 and the u16 totalItems at +0x0C, so every row
        decodes instead of a heuristic EWRAM scan locking onto a stale array. ScriptMenu_Multichoice
        fills S.MENU_LIST_TEMPLATE and the Seagallop sailor's ScriptMenu_ScrollingMultichoice fills
        S.SCROLL_MENU_TEMPLATE, so both are read and the one whose header validates is decoded. Each
        ListMenuItem is {const u8 *label; s32 index}, 8 bytes, the label pointing into ROM for a static
        option such as Cancel or into the EWRAM string buffers for a name composed at runtime like the
        Seagallop island rows, so both regions decode. Keys are each item's own index field, values the
        label's trailing letter run."""
        items = total = 0
        for base in (S.SCROLL_MENU_TEMPLATE, S.MENU_LIST_TEMPLATE):
            cand_items = struct.unpack_from("<I", self.e.read(base, 4), 0)[0]
            cand_total = struct.unpack_from("<H", self.e.read(base + 0x0C, 2), 0)[0]
            if 0x02000000 <= cand_items < 0x0A000000 and 0 < cand_total <= 32:
                items, total = cand_items, cand_total
                break
        self._menu_best_off = items
        if not items:
            return {}

        def label(ptr: int) -> str | None:
            if 0x08000000 <= ptr < 0x0A000000 or 0x02000000 <= ptr < 0x02040000:
                raw = self.e.read(ptr, 24)
            else:
                return None
            if len(raw) < 2:
                return None
            text = decode_text(raw)
            # live island rows decode with leading unmapped padding ('??????Four Island'), so keep
            # the trailing run of letters and spaces instead of requiring the whole decode be clean
            tail = ""
            for ch in reversed(text):
                if ch.isalpha() or ch == " ":
                    tail = ch + tail
                else:
                    break
            tail = tail.strip()
            if len(tail) >= 3 and any(c.isalpha() for c in tail):
                return tail
            return None

        rows: dict = {}
        for k in range(total):
            rec = self.e.read(items + k * 8, 8)
            if len(rec) < 8:
                break
            ptr, idx = struct.unpack("<Ii", rec)
            text = label(ptr)
            if text is not None:
                rows.setdefault(idx, text)
        return rows

    def _dump_menu_array(self) -> None:
        """One-shot raw dump of the EWRAM slots spanning the run _menu_rows locked onto, to pin the
        real item-array offset and stride when the decoded run is missing the island rows. Prints the
        {ptr, idx} record and the decoded label at every 4-byte slot across the found run so a broken
        stride or a pointer that fails the letter filter shows directly."""
        if getattr(self, "_menu_dumped", False):
            return
        self._menu_dumped = True
        base = getattr(self, "_menu_best_off", -1)
        if base < 0:
            print("ferry dump: no decodable run located", flush=True)
            return
        ew = self.e.read(0x02000000, 0x40000)

        def raw(ptr: int) -> str | None:
            if 0x08000000 <= ptr < 0x0A000000:
                return decode_text(self.e.read(ptr, 24))
            if 0x02000000 <= ptr < 0x02000000 + len(ew):
                return decode_text(ew[ptr - 0x02000000: ptr - 0x02000000 + 24])
            return None

        lo = max(0, base - 32)
        hi = min(len(ew) - 8, base + 96)
        for off in range(lo, hi, 4):
            ptr, idx = struct.unpack_from("<II", ew, off)
            print(f"ferry dump off {off:#x} ptr {ptr:#010x} idx {idx} text {raw(ptr)!r}", flush=True)

    def descend_gym(self, dest: tuple) -> str:
        """Out of a room gym (Petalburg: rooms stacked on one map, doors up, floor mats back
        down, no walking path from an inner room to the exit mat). take_warp once the exit is
        in the walkable region, else step onto the reachable floor mat whose landing reaches
        it, else the one landing nearest the exit row. "warped" for a mat taken, "no_mat" when
        none is reachable, else take_warp's statuses."""
        grid = Grid(self.e)
        x, y, group, num = self.g.position()
        ws = rowe_map.warps(self.e)
        exits = [(w.x, w.y) for w in ws if (w.dest_group, w.dest_num) == dest]
        if not exits:
            return "no_warp"

        def reaches_exit(start: tuple) -> bool:
            # a mat lands on a door tile, which is collision; measure from the floor below it
            if grid.cell(*start) & S.GRID_BLOCKED:
                start = (start[0], start[1] + 1)
            reach = grid.reachable(start)
            return any(e in reach or (e[0], e[1] - 1) in reach for e in exits)

        if reaches_exit((x, y)):
            return self.take_warp(dest)
        reach = grid.reachable((x, y))
        mats = [w for w in ws if (w.dest_group, w.dest_num) == (group, num) and w.dest_warp < len(ws)
                and not grid.cell(w.x, w.y) & S.GRID_BLOCKED and (w.x, w.y) in reach]
        if not mats:
            return "no_mat"

        def landing(w: rowe_map.Warp) -> tuple:
            land = ws[w.dest_warp]
            return (not reaches_exit((land.x, land.y)), min(abs(land.y - ey) for _, ey in exits))

        w = min(mats, key=landing)
        # a mat fires on the step onto it from a plain tile, and a door drops the party onto the
        # room's mat, so the walk goes to a plain neighbour first and presses back onto it
        warp_tiles = {(v.x, v.y) for v in ws}
        for dx, dy, key in ((0, 1, eb.KEY_UP), (0, -1, eb.KEY_DOWN), (1, 0, eb.KEY_LEFT), (-1, 0, eb.KEY_RIGHT)):
            side = (w.x + dx, w.y + dy)
            if side not in reach or side in warp_tiles:
                continue
            r = self.nav.walk_to(side)
            if r == "battle":
                return r
            if r != "arrived":
                continue
            self.run(24, key)
            self.run(120, 0)
            nx, ny = self.g.position()[:2]
            if abs(nx - w.x) + abs(ny - w.y) > 1:
                return "warped"
        return "stuck"

    def _step_into_warp(self, w: rowe_map.Warp, surf: bool = False, tools=frozenset()) -> str:
        """A door takes an UP press from the tile below; a floor warp (cave mouth, exit mat,
        stairs) fires on arrival or on a step into it from whichever side is open."""
        before = self.map_id()
        underwater = rowe_rom.is_underwater(*before)
        grid = Grid(self.e)
        grid.tools = tools
        grid.climb = any(item == ITEM_WATERFALL_TOOL for item, _ in self.g.key_items())
        x, y, *_ = self.g.position()
        w_max, h_max = grid.width - 2 * S.MAP_OFFSET, grid.height - 2 * S.MAP_OFFSET
        arrow = ARROW_WARP_KEYS.get(grid._behavior(grid.cell(w.x, w.y) & S.GRID_ID_MASK))
        if arrow is not None:
            # an arrow warp fires on the press in its arrow's direction while standing on it, and
            # stays quiet on arrival; a press off the map edge there walks the connection instead
            # (the west-arrow gate at (39, 13) on [1,31]'s east edge led back onto Route [0,33])
            if (x, y) != (w.x, w.y):
                r = self.nav.walk_to((w.x, w.y), surf=surf, tools=tools)
                if r in ("battle", "map_changed"):
                    return r
                if r != "arrived":
                    return "stuck"
            if not underwater:
                # B closes a greeting that ate the press; on the seabed it fires the emerge
                # script and surfaces the party off the warp, so skip it underwater
                self.run(8, eb.KEY_B)
                self.run(16, 0)
            self.run(24, arrow)
            self.run(120, 0)
            return "map_changed" if self._landed(before) else "stuck"
        if (x, y) == (w.x, w.y) and self._press_off_edge(w, w_max, h_max, before):
            return "map_changed"
        approaches = [((w.x, w.y + 1), eb.KEY_UP), ((w.x, w.y - 1), eb.KEY_DOWN),
                      ((w.x + 1, w.y), eb.KEY_LEFT), ((w.x - 1, w.y), eb.KEY_RIGHT)]
        if grid.path((x, y), (w.x, w.y), surf) is not None:
            approaches.insert(1, ((w.x, w.y), 0))
        for tile, key in approaches:
            # the border fill past a map's last row reads walkable and is not, so a warp on
            # the edge is never approached from outside the map
            if not (0 <= tile[0] < w_max and 0 <= tile[1] < h_max):
                continue
            # the approach may sit above a climb or across a dismount, at a height a single-step
            # passable from the avatar's carried elevation rejects, so gate on a real route to it
            if key and grid.path((x, y), tile, surf) is None:
                continue
            r = self.nav.walk_to(tile, surf=surf, tools=tools)
            if r == "battle":
                return r
            if r == "map_changed":
                return r
            if r != "arrived":
                if self._through_gate(tile, key, before):
                    return "map_changed"
                continue
            if key:
                self.run(24, key)
            self.run(120, 0)
            if self._landed(before):
                return "map_changed"
            # a greeting that opened on arrival (Slateport's museum guide) eats the first
            # press; B closes it and the same press then fires the warp
            if key:
                if not underwater:
                    self.run(8, eb.KEY_B)
                    self.run(16, 0)
                    self.run(24, key)
                    self.run(120, 0)
                    if self._landed(before):
                        return "map_changed"
            elif self._press_off_edge(w, w_max, h_max, before):
                return "map_changed"
        return "stuck"

    def _through_gate(self, tile: tuple, key: int, before: tuple) -> bool:
        """A scripted gate one step short of the approach: the League lobby's guards walk in front
        of the player on the tile below the door, speak on A and step aside, so the walk to the
        approach ends a tile early. Only from the tile straight behind `tile` in the press direction:
        the press, A through the lines, then the press on until the map changes."""
        behind = {eb.KEY_UP: (tile[0], tile[1] + 1), eb.KEY_DOWN: (tile[0], tile[1] - 1),
                  eb.KEY_LEFT: (tile[0] + 1, tile[1]), eb.KEY_RIGHT: (tile[0] - 1, tile[1])}.get(key)
        if behind is None or tuple(self.g.position()[:2]) != behind:
            return False
        self.run(24, key)
        self.run(60, 0)
        for _ in range(GATE_PRESSES):
            self.run(8, eb.KEY_A)
            self.run(60, 0)
        for _ in range(3):
            self.run(24, key)
            self.run(90, 0)
            if self._landed(before):
                return True
        return False

    def _press_off_edge(self, w: rowe_map.Warp, w_max: int, h_max: int, before: tuple) -> bool:
        """On an exit mat, which fires on the press off the map edge (a bottom-row door mat
        takes DOWN) and stays quiet when walked onto sideways. B first closes a greeting that
        opened on arrival (Slateport's museum guide), since it eats the press otherwise."""
        underwater = rowe_rom.is_underwater(*before)
        for dx, dy, key in ((0, 1, eb.KEY_DOWN), (0, -1, eb.KEY_UP), (-1, 0, eb.KEY_LEFT), (1, 0, eb.KEY_RIGHT)):
            if 0 <= w.x + dx < w_max and 0 <= w.y + dy < h_max:
                continue
            if not underwater:
                # B underwater emerges instead of closing a greeting, so skip it on the seabed
                self.run(8, eb.KEY_B)
                self.run(16, 0)
            self.run(24, key)
            self.run(120, 0)
            if self._landed(before):
                return True
        return False

    def npc_tile(self, local_id: int) -> tuple | None:
        base = S.addr("gObjectEvents")
        for i in range(S.OBJECT_EVENTS_COUNT):
            raw = self.e.read(base + i * S.OBJ_EVENT_SIZE, S.OBJ_EVENT_SIZE)
            flags = struct.unpack_from("<I", raw, S.OBJ_FLAGS)[0]
            if flags & S.OBJ_ACTIVE_BIT and raw[S.OBJ_LOCAL_ID] == local_id and (raw[S.OBJ_MAP_GROUP], raw[S.OBJ_MAP_NUM]) == self.map_id():
                cx, cy = struct.unpack_from("<hh", raw, S.OBJ_CURRENT_COORDS)
                return cx - S.MAP_OFFSET, cy - S.MAP_OFFSET
        return None

    def talk_to_nurse(self, stand: tuple | None = None) -> bool:
        """Walk to the tile two below the nurse, face up and talk until the party is healed. `stand`
        names the tile when the nurse object is not loaded from where the player stands (the League
        lobby's nurse at (4,2) is out of the spawn window from the entry mat)."""
        if stand is None:
            nurse = self.npc_tile(NURSE_LOCAL_ID)
            if nurse is None:
                return False
            stand = (nurse[0], nurse[1] + 2)
        if self.nav.walk_to(stand) != "arrived":
            return False
        self.run(8, eb.KEY_UP)
        self.run(8, 0)
        for _ in range(10):
            self.tap(eb.KEY_A)
            self.run(70, 0)
            if self.healed():
                break
        for _ in range(6):
            self.tap(eb.KEY_B)
            self.run(30, 0)
        return self.healed()

    def healed(self) -> bool:
        # a Center restores HP and PP together; testing HP alone lets a top-off that fired for 0 PP
        # see full HP and break the nurse loop before the heal lands, leaving the PP empty
        party = self.g.party()
        if not party:
            return False
        return all(m.hp == m.max_hp
                   and all(pp >= rowe_rom.move(mid).pp for mid, pp in zip(m.moves, m.pp) if mid)
                   for m in party)

    def _box_menu_to(self, target: int) -> bool:
        """Move the box main-menu cursor (Move/Withdraw/Deposit/Move items/See ya) onto `target`."""
        for _ in range(8):
            if self.e.read(S.BOX_MENU_CURSOR, 1)[0] == target:
                return True
            self.tap(eb.KEY_DOWN if self.e.read(S.BOX_MENU_CURSOR, 1)[0] < target else eb.KEY_UP)
            self.run(10, 0)
        return self.e.read(S.BOX_MENU_CURSOR, 1)[0] == target

    def _deposit_col_to(self, slot: int) -> None:
        """Move the deposit grid's party-column cursor onto party `slot`."""
        for _ in range(8):
            cur = self.e.read(S.BOX_DEPOSIT_COL, 1)[0]
            if cur == slot:
                return
            self.tap(eb.KEY_DOWN if cur < slot else eb.KEY_UP)
            self.run(10, 0)

    def swap_at_pc(self, out_slot: int, box_slot: int) -> bool:
        """Inside a Center: boot the storage PC, deposit the party mon at out_slot, withdraw the box
        mon at box_slot, then close the PC. Deposit frees the slot the withdraw needs and the deposited
        mon takes a free slot, so box_slot still points at the intended mon. True when the party's
        species list changed; the caller confirms the mon it set out for. box_slot counts across boxes
        the way GameState.boxes slots do: box box_slot//30, then col pos%6, row pos//6 in that box; a
        box past the current one is reached by turning pages from the title row."""
        cb_field = self.g.callback2()
        if not self._open_pc():
            return False
        before = self.g.party()
        outgoing = before[out_slot].personality
        incoming = next((bm.personality for bm in self.g.boxes() if bm.slot == box_slot), None)
        if incoming is None:
            self._close_pc(cb_field)
            self.log(f"pc swap: no box mon at slot {box_slot}")
            return False
        self._deposit(out_slot, len(before))
        self._withdraw(box_slot)
        self._close_pc(cb_field)
        after = self.g.party()
        held = {m.personality for m in after}
        self.log(f"pc swap out {out_slot} box {box_slot}: {[m.species for m in before]} -> {[m.species for m in after]}")
        return incoming in held and outgoing not in held and len(after) == len(before)

    def _open_pc(self) -> bool:
        """Walk to the storage PC and boot it to the box main menu; False when the PC tile is unreachable."""
        if self.nav.walk_to(BOX_PC_STAND) != "arrived":
            return False
        self.run(8, eb.KEY_UP)
        self.run(8, 0)
        # boot, which-PC menu, Someone's PC at the default cursor, "accessed", "system opened"
        for _ in range(5):
            self.tap(eb.KEY_A)
            self.run(60, 0)
        return True

    def _close_pc(self, cb_field: int) -> None:
        """Back out to the field and let the party settle, since the storage screen compacts the party
        on exit and a read taken mid-exit showed two mons of six."""
        for _ in range(8):
            if self.g.callback2() == cb_field:
                break
            self.tap(eb.KEY_B)
            self.run(60, 0)
        self.run(60, 0)

    def _deposit(self, out_slot: int, party_len: int) -> None:
        """From the box main menu: deposit the party mon at out_slot and return to the main menu."""
        if self._box_menu_to(S.BOX_MENU_DEPOSIT):
            self.tap(eb.KEY_A)
            self.run(70, 0)
            self._deposit_col_to(out_slot)
            self.tap(eb.KEY_A)   # select the mon
            self.run(60, 0)
            self.tap(eb.KEY_A)   # Store: the box chooser, open on the current box
            self.run(60, 0)
            # a full box answers the confirm w/ "The Box is full" and nothing moves, and the box the
            # chooser opens on is not the storage's current box (live: current box 1, chooser on
            # box 0 at 30/30, Wailmer never deposited), so the confirm is judged by the party
            # shrinking and the chooser turns RIGHT a box at a time until it does. The count byte
            # only updates on exit, so the shrink is read off the filled slots; judged by the count
            # byte this loop deposited four of six on the live run
            for _ in range(S.PC_BOX_COUNT):
                self.tap(eb.KEY_A)   # confirm the box
                self.run(60, 0)
                if self.g.party_filled() < party_len:
                    break
                self.tap(eb.KEY_A)   # dismiss "The Box is full", back on the chooser
                self.run(30, 0)
                self.tap(eb.KEY_RIGHT)
                self.run(40, 0)
            self.tap(eb.KEY_B)
            self.run(50, 0)
            self.tap(eb.KEY_B)
            self.run(60, 0)

    def _withdraw(self, box_slot: int) -> None:
        """From the box main menu: withdraw the box mon at box_slot into the first free party slot."""
        if self._box_menu_to(S.BOX_MENU_WITHDRAW):
            self.tap(eb.KEY_A)
            self.run(80, 0)
            target_box, pos = divmod(box_slot, S.PC_IN_BOX)
            # Reach the grid through the box title, then turn pages until the stored box matches the
            # target. ROWE holds more boxes than any fixed count, so a target behind the open box is
            # found by stepping toward it, LEFT to a lower box and RIGHT to a higher one; a build that
            # only honors RIGHT is caught when a press leaves the box unmoved and falls through to it.
            self.tap(eb.KEY_UP)
            self.run(30, 0)
            turns = 0
            while self.g.current_box() != target_box:
                cur = self.g.current_box()
                self.tap(eb.KEY_LEFT if target_box < cur else eb.KEY_RIGHT)
                self.run(90, 0)
                if self.g.current_box() == cur:
                    self.tap(eb.KEY_RIGHT)
                    self.run(90, 0)
                turns += 1
                if turns > 4 * S.PC_BOX_COUNT:
                    break
            self.tap(eb.KEY_DOWN)
            self.run(30, 0)
            col = S.BOX_TITLE_DROP_COL
            for _ in range(abs(pos % S.BOX_GRID_COLS - col)):
                self.tap(eb.KEY_RIGHT if pos % S.BOX_GRID_COLS > col else eb.KEY_LEFT)
            for _ in range(pos // S.BOX_GRID_COLS):
                self.tap(eb.KEY_DOWN)
            self.tap(eb.KEY_A)   # the box mon's submenu
            self.run(60, 0)
            self.tap(eb.KEY_A)   # Withdraw, the top row
            self.run(100, 0)

    def withdraw_at_pc(self, box_slot: int) -> bool:
        """Inside a Center w/ a party under six: boot the storage PC, withdraw the box mon at box_slot
        into the free slot, close the PC. True when the party grew."""
        cb_field = self.g.callback2()
        if not self._open_pc():
            return False
        before = len(self.g.party())
        self._withdraw(box_slot)
        landed = self.g.current_box()
        self._close_pc(cb_field)
        after = len(self.g.party())
        self.log(f"pc withdraw box {box_slot} (page {box_slot // S.PC_IN_BOX}): landed box {landed}, party {before} -> {after}")
        return after > before

    def heal_at(self, town: tuple, center: tuple, after_heal: Callable[[], None] | None = None, surf: bool = False) -> str:
        """From the town or its Center: reach the Center, heal, come back out. Returns 'healed',
        'battle' on a wild interruption, or 'unreachable' when the Center warp cannot be walked to
        from where the player stands, so the caller moves on instead of re-running a blocked warp.
        after_heal runs once inside the Center after the nurse, for a box swap on the same visit;
        surf lets the walk to the door cross water."""
        for _ in range(6):
            here = self.map_id()
            if here == town:
                r = self.enter_warp(center, surf=surf)
            elif here == center:
                ok = self.talk_to_nurse()
                self.log(f"nurse: {'healed' if ok else 'not healed'}")
                if ok and after_heal is not None:
                    after_heal()
                r = self.leave_by_warp(town)
                self.log(f"leave center -> {r}")
                return "healed" if ok else "unreachable"
            else:
                self.log(f"heal run: unknown map {here}")
                return "unreachable"
            self.log(f"heal run: {here} -> {r} at {self.g.position()}")
            if r == "battle":
                return "battle"
            if r == "unreachable":
                return "unreachable"
            self.run(60, 0)
        return "unreachable"

    def challenge_leader(self, stand: tuple) -> str:
        """Walk to the tile below the gym leader, face up and talk until the fight starts.
        Returns walk_to's status short of the tile, "battle" once the leader's fight is on, or
        "talked" when the dialog ran out without one (leader already beaten)."""
        r = self.nav.walk_to(stand)
        if r != "arrived":
            return r
        self.tap(eb.KEY_UP)
        self.run(10, 0)
        for _ in range(40):
            self.tap(eb.KEY_A)
            self.run(30, 0)
            if self.g.in_battle():
                return "battle"
        return "talked"

    def _route_key(self, route: dict) -> tuple:
        if "gate_vars" not in route:
            return tuple(self.g.position())  # (x, y, group, num): a hole maze keys on floor and tile
        sb1 = self.e.u32(S.addr("gSaveBlock1Ptr"))
        return (self.g.position()[:2], tuple(self.e.read(sb1 + route["gate_vars"], route["gate_count"])))

    def follow_route(self, route: dict) -> str:
        """Replay a gym's recorded gate presses (probe_fortree_bfs.py) from wherever the player
        is on it. The route stores the (tile, gate orientations) before each press and after
        the last, so the resume point is the entry matching the live state, which survives the
        fights that interrupt the walk and needs no index kept between calls. A press holds the
        key until the tile changes or 48 frames pass, then waits out a gate's quarter turn,
        the recorder's loop. Returns "arrived" past the last press, "battle" when a fight
        opens, "off_route" when the live state matches no entry or a press left a state the
        recording did not, so the caller falls back to the sweep."""
        gated = "gate_vars" in route
        if gated:
            states = [(tuple(t), tuple(gs)) for t, gs in route["states"]]
            matches = route_state_matches
        else:
            states = [tuple(s) for s in route["states"]]  # each a full (x, y, group, num)
            matches = lambda live, rec: live == rec
        presses = [tuple(p) for p in route["presses"]]
        key = self._route_key(route)
        at = next((i for i, s in enumerate(states) if s == key),
                  next((i for i, s in enumerate(states) if matches(key, s)), None))
        if at is None:
            return "off_route"
        for i in range(at, len(presses)):
            x, y, *_ = self.g.position()
            for _ in range(24):
                self.run(2, DIRS[presses[i]])
                if self.g.position()[:2] != (x, y):
                    break
            self.run(GATE_SETTLE_FRAMES, 0)
            if self.g.in_battle():
                return "battle"
            if not matches(self._route_key(route), states[i + 1]):
                # a trainer whose sight the step entered holds the player behind an intro;
                # A runs it into the fight the battle loop takes (nine taps from the first
                # frozen frame at Fortree's (9,10)), and the route resumes after
                for _ in range(16):
                    if self.g.in_battle():
                        return "battle"
                    self.run(8, eb.KEY_A)
                    self.run(40, 0)
                return "off_route"
        return "arrived"

    def take_warp_chain(self, stand: tuple, gym: tuple, gym_maps: frozenset) -> str:
        """Step onto the next warp of the chain that ends w/ a walking path to `stand` on `gym`
        (gym_maze.warp_chain over the ROM warp table, this map off the live grid so its NPCs
        count). A teleport pad fires 20 frames after the step lands, so the map change is waited
        out here. "warped", "battle", "no_chain" when none reaches the stand or it is walkable
        now, else the walk's status."""
        x, y, group, num = self.g.position()
        chain = gym_maze.warp_chain(((group, num), (x, y)), (gym, stand), gym_maps, {(group, num): Grid(self.e)})
        if not chain:
            return "no_chain"
        _, tile = chain[0]
        if tile == (x, y):
            # a pad fires on the step that lands on it, and the player stands on this one already
            # (landed here off its twin), so step off to a neighbour and back on
            grid = Grid(self.e)
            off = next((n for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
                        if grid.path((x, y), n) == [(n[0] - x, n[1] - y)]), None)
            if off is None:
                return "stuck"
            r = self.nav.walk_to(off)
            if r != "arrived":
                return r
        r = self.nav.walk_to(tile)
        if r != "arrived":
            return r
        for _ in range(PAD_FIRE_TICKS):
            self.run(10, 0)
            if self.map_id() != (group, num):
                self.nav.settle_map()
                return "warped"
        return "stuck"

    def gym_sweep(self, stand: tuple, done: set, gym_maps: frozenset = None) -> str:
        """Inside a gym whose leader's stand has no walking path yet: talk to the nearest
        person w/ a reachable neighbouring tile (a gym trainer, whose fight the battle loop
        takes), else stand on an untried floor switch, else step onto an untried warp that stays
        inside the gym. A warp counts as inside when its destination map is in `gym_maps`, which
        covers a same-map door (Petalburg's rooms) and a cross-map floor change (Lavaridge's 1F
        holes down to B1F and the stairs back up). `gym_maps` defaulting to the current map alone
        keeps the same-map-only behaviour for a single-floor gym. `done` holds the tiles spent
        this run, each keyed (group, num, x, y) so a 1F hole and a B1F stair on one column do not
        alias. Returns "battle", "talked", "stepped", "warped", or "exhausted" when nothing is
        left to try."""
        grid = Grid(self.e)
        x, y, group, num = self.g.position()
        if gym_maps is None:
            gym_maps = frozenset({(group, num)})

        def mk(t: tuple) -> tuple:
            return (group, num, t[0], t[1])

        elev = grid.cell(x, y) >> S.GRID_ELEVATION_SHIFT

        def resync() -> None:
            # a walk moved the player, so grid, coords and elevation describe the old tile; a battle
            # or a warp changes the whole map. Re-read before the next passable/path check
            nonlocal grid, x, y, elev
            grid = Grid(self.e)
            x, y = self.g.position()[:2]
            elev = grid.cell(x, y) >> S.GRID_ELEVATION_SHIFT

        leader = (stand[0], stand[1] - 1)
        people = sorted((o for o in grid.blocked_by_npc if o != leader and mk(o) not in done),
                        key=lambda t: abs(t[0] - x) + abs(t[1] - y))
        for obj in people:
            for d, key in STAND_FACING.items():
                side = (obj[0] + d[0], obj[1] + d[1])
                if not grid.passable(*side, elev, (x, y)) or grid.path((x, y), side) is None:
                    continue
                r = self.nav.walk_to(side)
                if r == "battle":
                    done.add(mk(obj))
                    return r
                if r != "arrived":
                    resync()
                    break
                self.tap(key)
                self.run(10, 0)
                for _ in range(6):
                    self.tap(eb.KEY_A)
                    self.run(40, 0)
                    if self.g.in_battle():
                        done.add(mk(obj))
                        return "battle"
                for _ in range(3):
                    self.tap(eb.KEY_B)
                    self.run(20, 0)
                done.add(mk(obj))
                return "talked"
        switches = sorted((t for t in set(rowe_map.coord_events(self.e)) if mk(t) not in done),
                          key=lambda t: abs(t[0] - x) + abs(t[1] - y))
        for tile in switches:
            if grid.path((x, y), tile) is None:
                continue
            done.add(mk(tile))
            r = self.nav.walk_to(tile)
            if r == "battle":
                return r
            self.run(60, 0)
            return "stepped"
        doors = [w for w in rowe_map.warps(self.e) if (w.dest_group, w.dest_num) in gym_maps and mk((w.x, w.y)) not in done]
        # a room door is a collision tile on the room's top wall (Petalburg's MB_PETALBURG_GYM_DOOR,
        # 0x8d) that an UP press never enters: facing it, A reads the room sign and a later A walks
        # the player through, the fourth after a fight in the room. A floor mat fires on arrival.
        # Doors go first, since a room's mats lead back down to the room just left
        doors.sort(key=lambda w: (not grid.cell(w.x, w.y) & S.GRID_BLOCKED, abs(w.x - x) + abs(w.y - y)))
        for w in doors:
            tile = (w.x, w.y)
            door = bool(grid.cell(*tile) & S.GRID_BLOCKED)
            approach = (w.x, w.y + 1) if door else tile
            if grid.path((x, y), approach) is None:
                continue
            # a door that opened stays open to take again, since a whiteout at the leader puts the
            # walk back at the entrance w/ the same `done`; a mat and a door that stayed shut are spent
            if not door:
                done.add(mk(tile))
            r = self.nav.walk_to(approach)
            if r == "battle":
                return r
            if r != "arrived":
                resync()
                continue
            if door:
                self.run(8, eb.KEY_UP)
                self.run(8, 0)
                for _ in range(6):
                    self.run(2, eb.KEY_A)
                    self.run(60, 0)
                    if self.g.position()[:2] != approach:
                        break
            self.run(120, 0)
            nx, ny = self.g.position()[:2]
            if abs(nx - tile[0]) + abs(ny - tile[1]) > 1:
                return "warped"
            done.add(mk(tile))
            resync()
        return "exhausted"

    def collect_item(self, ball: tuple, surf: bool = False) -> str:
        """Walk to a tile beside the item ball, face it and press A to pick it up. Returns
        walk_to's status short of the ball, "battle" on a wild interruption, "unreachable" when
        no side is open, or "got" once the pickup dialog is dismissed. The caller reads the
        collected flag to confirm the pickup."""
        grid = Grid(self.e)
        x, y, *_ = self.g.position()
        for stand, key in self.stand_tiles(grid, ball, (x, y), surf):
            r = self.nav.walk_to(stand, surf=surf)
            if r != "arrived":
                return r
            self.tap(key)
            self.run(10, 0)
            for _ in range(12):
                if self.g.in_battle():
                    # the grab woke a wild encounter. keep mashing A and it walks through the
                    # intro, opens Fight and confirms the lead's default move, Pawmot's 0-PP
                    # Supercell Slam, which wedges a double battle. hand off to battle_step instead.
                    return "battle"
                self.tap(eb.KEY_A)
                self.run(40, 0)
            for _ in range(4):
                if self.g.in_battle():
                    return "battle"
                self.tap(eb.KEY_B)
                self.run(20, 0)
            return "got"
        return "unreachable"

    @staticmethod
    def stand_tiles(grid: Grid, ball: tuple, origin: tuple, surf: bool) -> list:
        """(stand tile, facing key) for each land side of the ball the player can walk to. A water
        side is out: the surfer's elevation is the water's and the ball's is its bank's, and the
        game's object lookup (ObjectEventDoesZCoordMatch) skips an object across that gap, so the
        A press from the water did nothing and the ball kept the one landing tile."""
        elev = grid.cell(*origin) >> S.GRID_ELEVATION_SHIFT
        out = []
        for d, key in STAND_FACING.items():
            stand = (ball[0] + d[0], ball[1] + d[1])
            if grid._is_water(*stand):
                continue
            if grid.passable(*stand, elev, origin, surf) and grid.path(origin, stand, surf) is not None:
                out.append((stand, key))
        return out

    def _held(self, item_id: int) -> int:
        return dict(self.g.poke_balls() + self.g.medicine()).get(item_id, 0)

    def buy_at_counter(self, stand: tuple, wants: list, face: int = eb.KEY_LEFT, downgrade: tuple = ()) -> dict | None:
        """Inside a shop map: walk to `stand`, face the clerk, buy the list. None when the stand or
        the Buy list was not reached. The League lobby's clerk is faced up from (16,4)."""
        if self.nav.walk_to(stand) != "arrived":
            self.log(f"restock: counter tile {stand} not reached from {self.g.position()[:2]}")
            return None
        if not self.open_buy_list(face):
            self.log("restock: Buy list not opened at the counter")
            return None
        return self.buy_from_list(wants, downgrade)

    def open_buy_list(self, face: int = eb.KEY_LEFT) -> bool:
        """At the counter tile: face the clerk, greeting, Buy. True once the shop's list is readable."""
        self.run(8, face)
        self.run(8, 0)
        for _ in range(3):
            self.tap(eb.KEY_A)
            self.run(70, 0)
        return bool(self.g.shop_items())

    def buy_from_list(self, wants: list, downgrade: tuple = ()) -> dict:
        """With the Buy list open on row 0, buy each (item id, qty) the shop stocks, in list order
        so the cursor only moves down. The quantity box opens at 1; RIGHT adds 10, UP adds 1, and the
        game caps it at what the money covers. Each buy is read back off the pocket. Returns
        {item id: bought}, 0 for a row the shop lacks, and backs out to the overworld. `downgrade`
        is a weakest-first ladder of substitutes: a wanted rung the shop lacks buys the strongest
        stocked rung below it instead, since an early-game Mart never carries the top tier."""
        rows = self.g.shop_items()
        want = dict(wants)
        for iid in [w for w in want if w not in rows and w in downgrade]:
            sub = next((t for t in reversed(downgrade[:downgrade.index(iid)]) if t in rows), None)
            if sub is not None:
                want[sub] = want.pop(iid)
                self.log(f"mart: item {iid} not stocked, buying {sub}")
        bought = {iid: 0 for iid in want}
        row = 0
        for i, iid in enumerate(rows):
            if iid not in want:
                continue
            before = self._held(iid)
            for _ in range(i - row):
                self.tap(eb.KEY_DOWN)
                self.run(10, 0)
            row = i
            self.tap(eb.KEY_A)
            self.run(40, 0)
            for _ in range((want[iid] - 1) // 10):
                self.tap(eb.KEY_RIGHT)
            for _ in range((want[iid] - 1) % 10):
                self.tap(eb.KEY_UP)
            self.run(20, 0)
            # quantity, the price yes/no, the thank-you line, then the list again; a fourth A would
            # reopen the quantity box on the same row
            for _ in range(3):
                self.tap(eb.KEY_A)
                self.run(70, 0)
            bought[iid] = self._held(iid) - before
            self.log(f"mart: item {iid} x{want[iid]} -> +{bought[iid]}, money {self.g.money()}")
        for _ in range(5):
            self.tap(eb.KEY_B)
            self.run(60, 0)
        return bought

    def restock_at(self, town: tuple, mart: tuple, wants: list, surf: bool = False, downgrade: tuple = ()):
        """From the town or its Mart: reach the Mart, buy the (item id, qty) list, come back out.
        Every Mart shares the Oldale layout (11x8, same tileset), so the counter tile holds.
        Returns {item id: bought} once the counter was worked, empty when the list never opened,
        "battle" when a wild battle cuts in, None when the Mart counter was never reached."""
        for _ in range(6):
            here = self.map_id()
            if here == town:
                r = self.enter_warp(mart, surf=surf)
            elif here == mart:
                # the door mat sits at a lower elevation than the floor, so step off it before pathing
                self.run(24, eb.KEY_UP)
                self.run(20, 0)
                bought = {}
                if self.nav.walk_to(MART_COUNTER_TILE) != "arrived":
                    self.log(f"restock: counter tile {MART_COUNTER_TILE} not reached from {self.g.position()[:2]}")
                elif not self.open_buy_list():
                    self.log("restock: Buy list not opened at the counter")
                else:
                    bought = self.buy_from_list(wants, downgrade)
                r = self.leave_by_warp(town)
                self.log(f"leave mart -> {r}")
                return bought
            else:
                self.log(f"restock: unknown map {here}")
                return None
            self.log(f"restock: {here} -> {r} at {self.g.position()}")
            if r == "battle":
                return "battle"
            self.run(60, 0)
        return None

    def party_cursor_to(self, slot: int) -> None:
        """Party menu is two columns (even slots left, odd right), three rows."""
        cur = self.e.read(S.addr("gPartyMenu.slotId"))[0]
        if cur % 2 != slot % 2:
            self.tap(eb.KEY_RIGHT if slot % 2 else eb.KEY_LEFT)
        for _ in range(abs(slot // 2 - cur // 2)):
            self.tap(eb.KEY_DOWN if slot // 2 > cur // 2 else eb.KEY_UP)
        self.run(20, 0)

    def lead_with(self, slot: int) -> bool:
        """Start menu > Pokémon > slot > Switch > slot 0, then back out to the overworld."""
        cb_overworld = self.g.callback2()
        before = self.g.party()[0].personality
        for _ in range(2):
            self.tap(eb.KEY_B)
            self.run(20, 0)
        self.tap(eb.KEY_START)
        self.run(90, 0)
        if not self._start_menu_to(S.START_MENU_POKEMON):
            self.log("lead_with: start menu cursor never settled on Pokémon")
            return False
        self.tap(eb.KEY_A)
        self.run(120, 0)
        self.party_cursor_to(slot)
        self.tap(eb.KEY_A)
        self.run(60, 0)
        for _ in range(4):
            if self.e.read(S.addr("sPartyMenuActionCursor"))[0] == S.PARTY_ACTION_SWITCH:
                break
            self.tap(eb.KEY_DOWN)
            self.run(15, 0)
        self.tap(eb.KEY_A)
        self.run(60, 0)
        # the switch-target cursor starts on the picked slot and is not the slotId byte
        if slot % 2:
            self.tap(eb.KEY_LEFT)
        for _ in range(slot // 2):
            self.tap(eb.KEY_UP)
        self.run(20, 0)
        self.tap(eb.KEY_A)
        self.run(150, 0)
        for _ in range(5):
            self.tap(eb.KEY_B)
            self.run(60, 0)
            if self.g.callback2() == cb_overworld:
                break
        lead = self.g.party()[0]
        self.log(f"lead_with {slot}: lead now {lead.nickname} L{lead.level}, overworld {self.g.callback2() == cb_overworld}")
        return lead.personality != before

    def spend_skill_points(self) -> int:
        """Start menu > Trainer Skills, then put every unspent point into the six stat boosts
        round-robin, one level each pass, until less than a level's cost is left. Returns the
        points spent. The points figure only exists while the screen is open (the game derives
        it from trainer level and the per-skill levels on entry), so the screen is opened before
        the count is read. A full pass that buys nothing ends it, which covers every stat at its
        cap."""
        cb_field = self.g.callback2()
        for _ in range(2):
            self.tap(eb.KEY_B)
            self.run(20, 0)
        self.tap(eb.KEY_START)
        self.run(60, 0)
        opened = self._start_menu_to(S.START_MENU_SKILLS)
        pts = start = 0
        if opened:
            self.tap(eb.KEY_A)
            self.run(120, 0)
            self.tap(eb.KEY_RIGHT)
            self.run(20, 0)
            pts = start = self.g.skill_points()
            row = 0
            bought = True
            while bought and pts >= S.SKILL_STAT_COST:
                bought = False
                for target in S.SKILL_ROW_STAT_BOOSTS:
                    if pts < S.SKILL_STAT_COST:
                        break
                    key, taps = self.menu_step(row, target, S.SKILL_ROWS)
                    for _ in range(taps):
                        self.tap(key)
                    row = target
                    self.run(20, 0)
                    self.tap(eb.KEY_A)
                    self.run(40, 0)
                    left = self.g.skill_points()
                    bought |= left < pts
                    pts = left
        else:
            self.log("skills: start menu did not open")
        for _ in range(6):
            self.tap(eb.KEY_B)
            self.run(60, 0)
            if self.g.callback2() == cb_field:
                break
        self.log(f"skills: spent {start - pts} points on stat boosts, {pts} left, overworld {self.g.callback2() == cb_field}")
        return start - pts

    @staticmethod
    def menu_step(cur: int, target: int, rows: int) -> tuple:
        """(key, taps) carrying a cursor from cur to target the short way round a list of rows that
        wraps at both ends, so a row one above never costs a lap of DOWN."""
        down = (target - cur) % rows
        up = (cur - target) % rows
        return (eb.KEY_UP, up) if up < down else (eb.KEY_DOWN, down)

    def _start_menu_to(self, target: int) -> bool:
        """Carry the start menu cursor onto target, re-reading after every tap. The cursor byte keeps
        its last value until the menu has drawn, so a read on target counts only when a second read
        after a settle agrees (the live run once opened the Pokédex off a stale Pokémon reading).
        The menu keeps its cursor between opens and wraps at both ends."""
        for _ in range(START_MENU_ROWS):
            cur = self.e.read(S.addr("sStartMenuCursorPos"))[0]
            if cur == target:
                self.run(20, 0)
                if self.e.read(S.addr("sStartMenuCursorPos"))[0] == target:
                    return True
                continue
            key, _taps = self.menu_step(cur, target, START_MENU_ROWS)
            self.tap(key)
            self.run(15, 0)
        return False

    def _menu_cursor_to(self, row: int) -> bool:
        """Move the nurse's multichoice cursor onto row."""
        for _ in range(8):
            cur = self.e.read(S.MENU_CURSOR, 1)[0]
            if cur == row:
                return True
            self.tap(eb.KEY_DOWN if cur < row else eb.KEY_UP)
            self.run(15, 0)
        return False

    def _press_a_until_menu(self, presses: int) -> bool:
        """A through text boxes until a multichoice is up, at most `presses` times."""
        for _ in range(presses):
            self.tap(eb.KEY_A)
            self.run(80, 0)
            if self.e.read(S.FIELD_LOCKED, 1)[0]:
                return True
        return False

    def _tutor_list(self) -> list:
        """Move ids on the nurse's open list, read off the relearner struct's menu rows up to Cancel."""
        base = self.e.u32(S.RELEARNER_PTR) + S.RELEARNER_MENU_ITEMS
        out = []
        for k in range(S.RELEARNER_MAX_ROWS):
            mid = struct.unpack("<i", self.e.read(base + 8 * k + 4, 4))[0]
            if mid == S.LIST_CANCEL:
                break
            out.append(mid)
        return out

    def teach_egg_move_at_nurse(self, target_slot: int, forget_slot: int, move: int) -> str:
        """Inside a Center: the blue nurse's Teach or Forget a Move > Learn an Egg Move, Yes on the price,
        the party mon at target_slot, `move` on the list the nurse actually shows, forget_slot on the
        summary when it holds four moves, then back out to the field. "learned" when the mon holds
        `move` on the field, "absent" when the list never offered it, "failed" otherwise."""
        cb_field = self.g.callback2()
        result = "failed"
        if self.nav.walk_to(JACK_STAND) != "arrived":
            return False
        self.run(16, eb.KEY_UP)
        self.run(16, 0)
        # the greeting, then the service menu; a visit that starts facing away spends a press on the
        # turn, so A runs until the menu is up (FIELD_LOCKED reads 1 under a multichoice)
        ok = self._press_a_until_menu(4)
        if ok:
            ok = self._menu_cursor_to(S.JACK_MENU_TEACH)
        if ok:
            ok = self._press_a_until_menu(3) and self._menu_cursor_to(S.TEACH_EGG)   # "What kind of move", the kind menu
        if ok:
            for _ in range(3):   # the price prompt, Yes on it, "Which Pokémon" into the party menu
                self.tap(eb.KEY_A)
                self.run(90, 0)
            ok = self.g.callback2() in S.CB2_PARTY_MENU
        if ok:
            self.party_cursor_to(target_slot)
            for _ in range(2):   # the pick, then "Which move" into the list
                self.tap(eb.KEY_A)
                self.run(90, 0)
            ok = self.g.callback2() == S.CB2_TUTOR_LIST
        if ok:
            # the nurse's list is shorter than the ROM egg table (Golduck's never showed Ice Beam), so
            # the row comes from the list in RAM and a move it lacks ends the visit here
            offered = self._tutor_list()
            self.log(f"egg list for party slot {target_slot}: {offered}")
            if move not in offered:
                result = "absent"
                ok = False
        if ok:
            move_index = offered.index(move)
            # the cursor byte is the row inside the six-row window, so past row 5 the list scrolls under
            # a cursor that reads 5 forever. Absolute row is the scrolled-off count plus the window row
            for _ in range(move_index + 8):
                row = self.e.read(S.LIST_MENU_ABOVE, 1)[0] + self.e.read(S.LIST_MENU_CURSOR, 1)[0]
                if row == move_index:
                    break
                self.tap(eb.KEY_DOWN if row < move_index else eb.KEY_UP)
                self.run(15, 0)
            # the pick, "which move should be forgotten", the summary w/ forget_slot, then the learned
            # lines and the nurse's goodbye run on A until the script lets go of the player; the
            # overworld callback is back under the goodbye box, so the lock byte is the exit test
            for _ in range(16):
                cb2 = self.g.callback2()
                if cb2 == cb_field and not self.e.read(S.FIELD_LOCKED, 1)[0]:
                    break
                if cb2 == S.CB2_MOVE_SELECT:
                    for _ in range(forget_slot):
                        self.tap(eb.KEY_DOWN)
                        self.run(10, 0)
                self.tap(eb.KEY_A)
                self.run(90, 0)
        for _ in range(10):
            if self.g.callback2() == cb_field:
                break
            self.tap(eb.KEY_B)
            self.run(40, 0)
        if move in self.g.party()[target_slot].moves and self.g.callback2() == cb_field:
            result = "learned"
        self.log(f"egg move {move} on party slot {target_slot} -> {result}, "
                 f"overworld {self.g.callback2() == cb_field}, BP {self.g.battle_points()}")
        return result

    def bag_to_pocket(self, pocket: int, settle: int = 25, tries: int = 6) -> bool:
        """Shoulder-tab the open bag to `pocket` the short way round; the tabs wrap, so a RIGHT-only
        walk from Berries to Medicine crossed the bag instead of stepping back one."""
        for _ in range(tries):
            cur = self.g.bag_position()[0]
            if cur == pocket:
                return True
            self.tap(bag_pocket_key(cur, pocket))
            self.run(settle, 0)
        return self.g.bag_position()[0] == pocket

    def teach_tm_in_field(self, pocket_slot: int, target_slot: int, forget_slot: int, move: int) -> bool:
        """From the overworld: Start menu > Bag > TMs & HMs pocket > the TM at pocket_slot > Use, A through
        the boot-up, contents and "Teach to a Pokémon?" boxes to the party menu, the mon at target_slot,
        A through "wants to learn" and the four-moves notice (Yes to replacing), forget_slot on the
        move-select summary, then back out to the field. True when the mon holds `move` on the field."""
        cb_field = self.g.callback2()
        for _ in range(2):
            self.tap(eb.KEY_B)
            self.run(20, 0)
        self.tap(eb.KEY_START)
        self.run(60, 0)
        self._start_menu_to(S.START_MENU_BAG)
        self.tap(eb.KEY_A)
        self.run(120, 0)
        if self.g.callback2() == S.CB2_BAG_MAIN:
            self.bag_to_pocket(S.BAG_POCKET_TMS)
            for _ in range(pocket_slot + 8):
                cur = self.g.bag_position()[1]
                if cur == pocket_slot:
                    break
                self.tap(eb.KEY_DOWN if cur < pocket_slot else eb.KEY_UP)
                self.run(10, 0)
            # A raises Use/Give/Cancel and A takes Use; the TM boots, names its move and asks whom to
            # teach, one A each, before the party menu is up
            for _ in range(8):
                if self.g.callback2() in S.CB2_PARTY_MENU:
                    break
                self.tap(eb.KEY_A)
                self.run(60, 0)
        if self.g.callback2() in S.CB2_PARTY_MENU:
            self.party_cursor_to(target_slot)
            # "wants to learn", "already knows four moves", "delete a move?" (A is Yes), "which move?",
            # then the summary; past the pick, "1, 2, and... Poof!" and the learned line run on A until
            # the bag is back. A mon w/ a free slot learns on the first A.
            for _ in range(16):
                cb2 = self.g.callback2()
                if cb2 == S.CB2_BAG_MAIN:
                    break
                if cb2 == S.CB2_MOVE_SELECT:
                    for _ in range(forget_slot):
                        self.tap(eb.KEY_DOWN)
                        self.run(10, 0)
                self.tap(eb.KEY_A)
                self.run(90, 0)
        for _ in range(10):
            if self.g.callback2() == cb_field:
                break
            self.tap(eb.KEY_B)
            self.run(40, 0)
        learned = move in self.g.party()[target_slot].moves
        self.log(f"tm: pocket slot {pocket_slot} on party slot {target_slot} -> learned {learned}, "
                 f"overworld {self.g.callback2() == cb_field}")
        return learned and self.g.callback2() == cb_field

    def use_hp_item_in_field(self, pocket_slot: int, target_slot: int) -> bool:
        """From the overworld: Start menu > Bag > Medicine pocket > the item at pocket_slot > Use >
        the party mon at target_slot, then back out to the field. True only when the bag opened and
        the field is reached again; the caller reads the mon's HP to confirm the item took."""
        cb_field = self.g.callback2()
        for _ in range(2):
            self.tap(eb.KEY_B)
            self.run(20, 0)
        self.tap(eb.KEY_START)
        self.run(60, 0)
        self._start_menu_to(S.START_MENU_BAG)
        self.tap(eb.KEY_A)
        self.run(120, 0)
        opened = self.g.callback2() == S.CB2_BAG_MAIN
        if opened:
            self.bag_to_pocket(S.BAG_POCKET_MEDICINE, settle=20)
            for _ in range(pocket_slot + 8):
                cur = self.g.bag_position()[1]
                if cur == pocket_slot:
                    break
                self.tap(eb.KEY_DOWN if cur < pocket_slot else eb.KEY_UP)
                self.run(10, 0)
            # A raises the item's Use/Give/Toss box, A again takes Use at the top and opens the
            # party menu to pick the mon
            self.tap(eb.KEY_A)
            self.run(40, 0)
            self.tap(eb.KEY_A)
            self.run(60, 0)
            self.party_cursor_to(target_slot)
            self.tap(eb.KEY_A)
            self.run(120, 0)
        for _ in range(8):
            if self.g.callback2() == cb_field:
                break
            self.tap(eb.KEY_B)
            self.run(40, 0)
        done = self.g.callback2() == cb_field
        self.log(f"field heal slot {target_slot}: bag {opened}, field {done}")
        return opened and done

    def back_to_route_101(self) -> str:
        here = self.map_id()
        if here == OLDALE:
            return self.cross_edge(rowe_map.DIR_SOUTH)
        if here == ROUTE_101:
            return "arrived"
        return "unknown_map"
