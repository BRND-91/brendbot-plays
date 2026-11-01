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
from nav import DIRS, GATE_SETTLE_FRAMES, Grid, Navigator

ROUTE_101 = (0, 16)
OLDALE = (0, 10)
NURSE_LOCAL_ID = 1
MART_COUNTER_TILE = (3, 3)   # right of the counter end at (2,3), facing the clerk at (1,3) through
                             # it; the tile below the counter is an NPC's post in Mossdeep's Mart
BOX_PC_STAND = (10, 3)       # tile below the storage PC on the shared Center layout, face up to boot it
JACK_STAND = (4, 4)          # two below the blue nurse at (4, 2) on that layout, face up across the counter
MOVE_UP, MOVE_DOWN = (0, -1), (0, 1)
# stand tile offset from the ball -> the key that faces the ball from that side
STAND_FACING = {(0, 1): eb.KEY_UP, (0, -1): eb.KEY_DOWN, (1, 0): eb.KEY_LEFT, (-1, 0): eb.KEY_RIGHT}
# pokeemerald MB_*_ARROW_WARP behaviors -> the press that fires the warp from the tile itself.
# 0x6d is MB_WATER_SOUTH_ARROW_WARP, the dive-tunnel current linking underwater maps (Sootopolis
# (24,5) tile (9,8) -> (0,51)); it fires on a south press, same as the land south arrow 0x65.
ARROW_WARP_KEYS = {0x62: eb.KEY_RIGHT, 0x63: eb.KEY_LEFT, 0x64: eb.KEY_UP, 0x65: eb.KEY_DOWN,
                   0x6d: eb.KEY_DOWN}


def route_state_matches(live: tuple, recorded: tuple) -> bool:
    """A recorded (tile, gate bytes) entry matches the live read on tile and gates, or on tile
    alone when its gate bytes are all zero. The Fortree recording holds real orientations up to
    press 55 and zeros from press 56 on, while the game reads non-zero bytes on those tiles, so
    an exact compare left the route at (1, 7) every visit."""
    if live[0] != recorded[0]:
        return False
    return not any(recorded[1]) or live[1] == recorded[1]


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

        DIR_EMERGE surfaces from an underwater map: pressedBButton runs the emerge script, which
        warps to the surface point this map's setdivewarp set (Sootopolis, from (24, 5)). Most open
        tiles emerge; a few under land refuse, so the current tile then the nearest reachable ones
        are tried until the map changes."""
        if direction == rowe_map.DIR_EMERGE:
            before = self.map_id()
            grid = Grid(self.e)
            grid.tools = tools
            x, y, *_ = self.g.position()
            nearby = sorted((t for t in grid.reachable((x, y), surf) if t != (x, y)),
                            key=lambda t: abs(t[0] - x) + abs(t[1] - y))
            for tile in [(x, y)] + nearby[:12]:  # 12 fallbacks past the entry tile, for an unable-to-emerge spot
                if tile != (x, y):
                    r = self.nav.walk_to(tile, surf=surf, tools=tools)
                    if r == "battle":
                        return r
                    if r != "arrived":
                        continue
                self.run(24, eb.KEY_B)
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
        """Step down onto an exit mat (bottom-row warp) that leads to dest."""
        w = rowe_map.warp_to(self.e, *dest)
        if w is None:
            return "no_warp"
        r = self.nav.walk_to((w.x, w.y - 1))
        if r != "arrived":
            return r
        before = self.map_id()
        self.run(24, eb.KEY_DOWN)
        self.run(120, 0)
        return "map_changed" if self._landed(before) else "stuck"

    def take_warp(self, dest: tuple, surf: bool = False, rank: Callable | None = None, tools=frozenset()) -> str:
        """Leave the current map through a warp to dest: "map_changed", "battle", "no_warp",
        or "stuck". When several warps lead there (a cave with two mouths onto one route),
        `rank(warp)` -> (class, -landing region size) orders them biggest landing region
        first, class 0 before the rest, and within a tie the farthest from the player goes
        first, since the nearest is the one just arrived by. With surf the approach may cross
        water (Petalburg Woods' pond is its only north link)."""
        ws = [w for w in rowe_map.warps(self.e) if (w.dest_group, w.dest_num) == dest]
        if not ws:
            return "no_warp"
        grid = Grid(self.e)
        ws = [w for w in ws if not grid.is_wall_warp(w.x, w.y)]
        if not ws:
            return "unreachable"
        x, y, *_ = self.g.position()
        ws.sort(key=lambda w: (rank(w) if rank else (0, 0), -(abs(w.x - x) + abs(w.y - y))))
        for w in ws:
            r = self._step_into_warp(w, surf, tools)
            if r in ("map_changed", "battle"):
                return r
        return "stuck"

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
        x, y, *_ = self.g.position()
        elev = grid.cell(x, y) >> S.GRID_ELEVATION_SHIFT
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
            if key and not grid.passable(*tile, elev, (x, y), surf):
                continue
            r = self.nav.walk_to(tile, surf=surf, tools=tools)
            if r == "battle":
                return r
            if r == "map_changed":
                return r
            if r != "arrived":
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

    def talk_to_nurse(self) -> bool:
        nurse = self.npc_tile(NURSE_LOCAL_ID)
        if nurse is None:
            return False
        if self.nav.walk_to((nurse[0], nurse[1] + 2)) != "arrived":
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

    def open_buy_list(self) -> bool:
        """At the counter tile: face the clerk, greeting, Buy. True once the shop's list is readable."""
        self.run(8, eb.KEY_LEFT)
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
                if self.nav.walk_to(MART_COUNTER_TILE) == "arrived" and self.open_buy_list():
                    bought = self.buy_from_list(wants, downgrade)
                else:
                    self.log("restock: counter or Buy list not reached")
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
        # the cursor byte keeps its last value until the menu has drawn, so a read taken too early
        # says Pokémon while the menu opens on Pokédex; the row is re-read after a settle and
        # only a repeat reading lets A fire (the live run opened the Pokédex and left)
        for _ in range(8):
            if self.e.read(S.addr("sStartMenuCursorPos"))[0] == S.START_MENU_POKEMON:
                self.run(20, 0)
                if self.e.read(S.addr("sStartMenuCursorPos"))[0] == S.START_MENU_POKEMON:
                    break
            self.tap(eb.KEY_DOWN)
            self.run(15, 0)
        else:
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
        opened = False
        # the start menu keeps its cursor between opens and DOWN wraps past the last of its
        # twelve rows, so a full lap always passes the Trainer Skills row
        for _ in range(12):
            if self.e.read(S.addr("sStartMenuCursorPos"))[0] == S.START_MENU_SKILLS:
                opened = True
                break
            self.tap(eb.KEY_DOWN)
            self.run(15, 0)
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
                    for _ in range((target - row) % S.SKILL_ROWS):
                        self.tap(eb.KEY_DOWN)
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
        for _ in range(8):
            if self.e.read(S.addr("sStartMenuCursorPos"))[0] == S.START_MENU_BAG:
                break
            self.tap(eb.KEY_DOWN)
            self.run(15, 0)
        self.tap(eb.KEY_A)
        self.run(120, 0)
        if self.g.callback2() == S.CB2_BAG_MAIN:
            for _ in range(10):
                if self.g.bag_position()[0] == S.BAG_POCKET_TMS:
                    break
                self.tap(eb.KEY_RIGHT)
                self.run(25, 0)
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
        for _ in range(8):
            if self.e.read(S.addr("sStartMenuCursorPos"))[0] == S.START_MENU_BAG:
                break
            self.tap(eb.KEY_DOWN)
            self.run(15, 0)
        self.tap(eb.KEY_A)
        self.run(120, 0)
        opened = self.g.callback2() == S.CB2_BAG_MAIN
        if opened:
            for _ in range(6):
                pk = self.g.bag_position()[0]
                if pk == S.BAG_POCKET_MEDICINE:
                    break
                self.tap(eb.KEY_LEFT if pk > S.BAG_POCKET_MEDICINE else eb.KEY_RIGHT)
                self.run(20, 0)
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
