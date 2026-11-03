"""Emerge-candidate ground truth for the third Sootopolis crossing (0,51)->(0,41).

Loads the frozen (24,5) fixture, crosses to the seabed (0,51), then prints the data the
emerge candidate walk needs to pick a tile that actually surfaces instead of stepping onto the
back-warp and bouncing to (24,5): the emerge connection target and its offset, the map's warp
tiles, and for each reachable tile its underwater behaviour, warp flag, and the surface map's
behaviour at the matching coordinate. Reads the fixture, writes nothing but the /tmp ledger.
"""
import os
import struct

import emu_boot as eb
import map_graph
import play
import rowe_map
import rowe_rom
from nav import Grid, DIVE_BEHAVIORS

BASE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(BASE, "states", "fixtures", "sootopolis_underwater_stuck.ss")
GRID_ID_MASK = 0x0FFF


def _player():
    e = eb.Emu()
    e.load_state(open(FIX, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-emerge-probe.json")
    p.graph = map_graph.MapGraph(
        os.path.join(BASE, "states", "map_graph.json"),
        world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
    return p


def connections_with_offset(group, num):
    """(direction, offset, (dest_group, dest_num)) per connection, keeping the s32 offset that
    rowe_rom.map_connections drops, so the emerge target coordinate can be checked."""
    h = rowe_rom.map_header(group, num)
    conn = struct.unpack_from("<I", rowe_rom._rom(), h + rowe_rom.MAPHDR_CONNECTIONS)[0]
    n, ptr = struct.unpack_from("<II", rowe_rom._rom(), rowe_rom._fo(conn))
    out = []
    for i in range(n):
        d, off, g, nm = struct.unpack_from("<IiBB", rowe_rom._rom(), rowe_rom._fo(ptr) + i * 12)
        out.append((d, off, (g, nm)))
    return out


if __name__ == "__main__":
    p = _player()
    print("start", tuple(p.g.position()))
    status, result = p._cross_to((24, 5), (0, 51))
    here = tuple(p.g.position())
    print("CROSS (24,5)->(0,51):", status, result, "landed", here)
    if here[2:] != (0, 51):
        print("not on (0,51), cannot probe emerge; stopping")
        raise SystemExit

    conns = connections_with_offset(0, 51)
    print("connections(0,51) [dir, offset, dest]:", conns)
    emerge = [(off, dest) for d, off, dest in conns if d == rowe_map.DIR_EMERGE]
    print("emerge conn (dir 6):", emerge)
    print("map_warps(0,51):", rowe_rom.map_warps(0, 51))

    grid = Grid(p.e)
    print("warp_tiles:", sorted(grid.warp_tiles))
    x, y, *_ = p.g.position()
    reach = grid.reachable((x, y), surf=True)
    print(f"pos ({x},{y}) reachable {len(reach)} tiles")

    surf_map = emerge[0][1] if emerge else None
    off = emerge[0][0] if emerge else 0
    cells41 = rowe_rom.map_cells(*surf_map) if surf_map else None
    beh41 = rowe_rom.metatile_behavior(*surf_map) if surf_map else None
    print("surface map", surf_map, "offset", off,
          "dims", (cells41[0], cells41[1]) if cells41 else None)

    def surf_beh(sx, sy):
        if not cells41 or not (0 <= sx < cells41[0] and 0 <= sy < cells41[1]):
            return None
        return beh41(cells41[2][sy * cells41[0] + sx] & GRID_ID_MASK)

    nearest = sorted(reach, key=lambda t: abs(t[0] - x) + abs(t[1] - y))
    print("tile | uw_beh | warp | surf_beh | surf_beh+off | dive0 | diveoff")
    for t in nearest[:30]:
        uw = grid._behavior(grid.cell(*t) & GRID_ID_MASK)
        sb0 = surf_beh(t[0], t[1])
        sboff = surf_beh(t[0] + off, t[1])
        print(f"{t} {uw:#x} warp={t in grid.warp_tiles} "
              f"s0={sb0 if sb0 is None else hex(sb0)} soff={sboff if sboff is None else hex(sboff)} "
              f"dive0={sb0 in DIVE_BEHAVIORS} diveoff={sboff in DIVE_BEHAVIORS}")

    emergeable0 = [t for t in reach if surf_beh(t[0], t[1]) in DIVE_BEHAVIORS and t not in grid.warp_tiles]
    emergeableoff = [t for t in reach if surf_beh(t[0] + off, t[1]) in DIVE_BEHAVIORS and t not in grid.warp_tiles]
    print("non-warp emergeable (offset 0):", len(emergeable0))
    print("non-warp emergeable (offset applied):", len(emergeableoff))

    print("--- current-code emerge (0,51)->(0,41) from", tuple(p.g.position()), "---")
    st2, r2 = p._cross_to((0, 51), (0, 41))
    print("CROSS (0,51)->(0,41):", st2, r2, "landed", tuple(p.g.position()))
