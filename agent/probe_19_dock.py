"""Why the (1,9) dispatcher sailor reads unreachable from the live tile. Boots a /tmp copy of the
save, builds the live Grid, reports whether the approach tile is reachable on foot and under surf,
prints the map's passability (P player, S sailor, A approach, n npc, ~ water, # blocked, . foot
reach, , surf-only reach, digit elevation of an unreached tile), then runs walk_to. Reads only.

    probe_19_dock.py --state /tmp/rowe_19_probe.ss [--dest 0,123]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb  # noqa: E402
import play  # noqa: E402
import rowe_rom  # noqa: E402
import rowe_symbols as S  # noqa: E402
import script_decode  # noqa: E402
from nav import Grid  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--dest", default="0,123")
    ap.add_argument("--via", nargs="*", default=[], help="maps to take_warp through before the dump, e.g. 1,26 1,27")
    a = ap.parse_args()
    dest = tuple(int(v) for v in a.dest.split(","))

    e = eb.Emu()
    e.load_state(open(a.state, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe_19_probe.json")
    g = p.g
    moves = p.field_moves()
    for hop in a.via:
        hop = tuple(int(v) for v in hop.split(","))
        r = p.errands.take_warp(hop, surf=True, tools=moves)
        print(f"via {hop}: {r} at {g.position()}", flush=True)
    x, y, grp, num = g.position()
    here = (grp, num)
    print(f"pos {(x, y)} map {here} badges {g.badges()} moves {sorted(moves)}", flush=True)
    t = script_decode.talk_object(here, dest)
    print(f"talk_object -> {t}", flush=True)
    if t is None:
        print(f"objects {rowe_rom.map_object_scripts(*here)}", flush=True)
        return
    obj = tuple(t["obj"])
    approach = tuple(t["approach"]) if t["approach"] else p.errands._approach_tile(obj, True, moves)
    print(f"approach {approach} (_approach_tile when the object has no fixed facing)", flush=True)
    if approach is None:
        approach = (obj[0], obj[1] + 1)

    grid = Grid(e)
    grid.tools = moves
    w, h = grid.width - 2 * S.MAP_OFFSET, grid.height - 2 * S.MAP_OFFSET
    print(f"map {w}x{h} player_tile {grid.player_tile} elev {grid.player_elev}", flush=True)
    around = [(obj[0] - 1, obj[1]), (obj[0] + 1, obj[1]), (obj[0], obj[1] - 1), (obj[0], obj[1] + 1)]
    reach = {}
    for surf in (False, True):
        reach[surf] = grid.reachable((x, y), surf)
        path = grid.path((x, y), approach, surf)
        print(f"surf={surf}: reach {len(reach[surf])} tiles, approach in reach {approach in reach[surf]}, "
              f"sailor neighbours in reach {[n for n in around if n in reach[surf]]}, "
              f"path {None if path is None else len(path)} steps", flush=True)
    for yy in range(h):
        row = []
        for xx in range(w):
            c = grid.cell(xx, yy)
            if (xx, yy) == (x, y):
                ch = "P"
            elif (xx, yy) == obj:
                ch = "S"
            elif (xx, yy) == approach:
                ch = "A"
            elif (xx, yy) in grid.blocked_by_npc:
                ch = "n"
            elif grid._is_water(xx, yy):
                ch = "~"
            elif c & S.GRID_BLOCKED:
                ch = "#"
            elif (xx, yy) in reach[False]:
                ch = "."
            elif (xx, yy) in reach[True]:
                ch = ","
            else:
                ch = str(c >> S.GRID_ELEVATION_SHIFT)
            row.append(ch)
        print(f"{yy:2d} {''.join(row)}", flush=True)
    r = p.nav.walk_to(approach, surf=True, tools=moves)
    print(f"walk_to {approach} surf=True -> {r} at {g.position()}", flush=True)


if __name__ == "__main__":
    main()
