"""Warps and connections of the current map, read through gMapHeader into the ROM."""
import struct
from dataclasses import dataclass
from functools import lru_cache

import rowe_symbols as S
from emu_boot import ROM, Emu

ROM_BASE = 0x08000000
DIR_SOUTH, DIR_NORTH, DIR_WEST, DIR_EAST = 1, 2, 3, 4
DIR_DIVE, DIR_EMERGE = 5, 6  # CONNECTION_DIVE/EMERGE: a vertical link taken from the field-move menu over water, not a map border


@dataclass(frozen=True)
class Warp:
    x: int
    y: int
    dest_group: int
    dest_num: int
    dest_warp: int


@dataclass(frozen=True)
class Connection:
    direction: int
    offset: int
    group: int
    num: int


@lru_cache(maxsize=1)
def _rom() -> bytes:
    with open(ROM, "rb") as f:
        return f.read()


def _rd(addr: int, n: int) -> bytes:
    if not ROM_BASE <= addr < ROM_BASE + len(_rom()):
        raise ValueError(f"not a ROM address: {addr:#x}")
    return _rom()[addr - ROM_BASE:addr - ROM_BASE + n]


def warps(emu: Emu) -> list:
    events = emu.u32(S.addr("gMapHeader") + S.MAPHDR_EVENTS)
    _, nwarp, _, _, _, pwarp, _, _ = struct.unpack("<4B4I", _rd(events, 20))
    out = []
    for i in range(nwarp):
        x, y, _elev, wid, num, group = struct.unpack("<hhBBBB", _rd(pwarp + i * 8, 8))
        out.append(Warp(x, y, group, num, wid))
    return out


def connections(emu: Emu) -> list:
    conn = emu.u32(S.addr("gMapHeader") + S.MAPHDR_CONNECTIONS)
    if not conn:
        return []
    n, p = struct.unpack("<II", _rd(conn, 8))
    out = []
    for i in range(n):
        d, off, group, num = struct.unpack("<IiBB", _rd(p + i * 12, 10))
        out.append(Connection(d, off, group, num))
    return out


COORD_EVENT_SIZE = 16  # struct CoordEvent: s16 x, y; u8 elevation; u16 trigger; u16 index; script*


def coord_events(emu: Emu) -> list:
    """(x, y) of every coord event on the current map, the floor switches and step triggers
    whose script runs when the player stands on the tile (Mauville's four barrier switches)."""
    events = emu.u32(S.addr("gMapHeader") + S.MAPHDR_EVENTS)
    _, _, ncoord, _, _, _, pcoord, _ = struct.unpack("<4B4I", _rd(events, 20))
    return [tuple(struct.unpack_from("<hh", _rd(pcoord + i * COORD_EVENT_SIZE, 4))) for i in range(ncoord)]


OBJ_TEMPLATE_SIZE = 24
# movement types that never leave the tile: none, face down, up, left, right
STATIC_MOVEMENT = {0, 7, 8, 9, 10}


def static_objects(emu: Emu) -> list:
    """(x, y, flag) of every object on the current map that holds its tile for good, read
    from the ROM templates, since the game spawns an object only once the camera is near
    and a grid read from across the map would show its tile open (Route 104's flower-shop
    gap, an ambient Bulbasaur in the only tile into the grass). The object is hidden while
    its flag is set; flag 0 means never."""
    events = emu.u32(S.addr("gMapHeader") + S.MAPHDR_EVENTS)
    nobj, _, _, _, pobj = struct.unpack("<4BI", _rd(events, 8))
    out = []
    for i in range(nobj):
        raw = _rd(pobj + i * OBJ_TEMPLATE_SIZE, OBJ_TEMPLATE_SIZE)
        x, y = struct.unpack_from("<hh", raw, 4)
        if raw[9] in STATIC_MOVEMENT:
            out.append((x, y, struct.unpack_from("<H", raw, 20)[0]))
    return out


ITEM_BALL_GFX = 0x3B  # OBJ_EVENT_GFX_ITEM_BALL in this build; graphicsId is the u16 at template +2


def item_balls(emu: Emu) -> list:
    """(x, y, flag) of every item-ball object on the current map, picked out by the item-ball
    sprite id. The flag is the collected flag, set once the ball is picked up, so a caller skips
    a ball whose flag reads set; flag 0 tracks no collected state."""
    events = emu.u32(S.addr("gMapHeader") + S.MAPHDR_EVENTS)
    nobj, _, _, _, pobj = struct.unpack("<4BI", _rd(events, 8))
    out = []
    for i in range(nobj):
        raw = _rd(pobj + i * OBJ_TEMPLATE_SIZE, OBJ_TEMPLATE_SIZE)
        if struct.unpack_from("<H", raw, 2)[0] == ITEM_BALL_GFX:
            x, y = struct.unpack_from("<hh", raw, 4)
            out.append((x, y, struct.unpack_from("<H", raw, 20)[0]))
    return out


def warp_to(emu: Emu, group: int, num: int) -> Warp | None:
    for w in warps(emu):
        if (w.dest_group, w.dest_num) == (group, num):
            return w
    return None
