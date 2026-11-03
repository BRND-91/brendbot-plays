"""Measure the Ever Grande (0,8) waterfall the endgame route climbs to reach Victory Road, on a
throwaway copy of the live save so the supervisor keeps its own files. Reports the Victory Road
door warp tile, the 0x13 waterfall column (count + bottom coords), whether the surf tile under it
is reachable from where the avatar stands, and an A,A trace of the real climb with screen captures
so the prompt text is read, not guessed. Answers whether the committed nav climb rides this column,
the part no unit test reaches.

    cd /opt/brendbot/rowe-agent && .venv/bin/python probe_evergrande_waterfall.py
"""
import json
import shutil

import emu_boot as eb
import nav
import play
import rowe_map
import rowe_symbols as S

LIVE = "states/live.ss"
SCRATCH = "/tmp/rowe_evergrande.ss"
WATER_LABELS = {0x10: "WATER", 0x11: "SEMI_DEEP", 0x12: "DEEP", 0x13: "WATERFALL",
                0x14: "DIVE", 0x15: "OCEAN_CURRENT?"}
VICTORY_ROAD_GROUP = 16


def _beh(grid, t):
    return grid._behavior(grid.cell(*t) & S.GRID_ID_MASK) if grid._behavior else None


def _fresh():
    emu = eb.Emu()
    with open(SCRATCH, "rb") as f:
        emu.load_state(f.read())
    return emu


def main():
    shutil.copy(LIVE, SCRATCH)
    emu = _fresh()
    player = play.Player(emu, play.NullStreamer(), ledger_path=SCRATCH + ".caught.json")
    x, y, g, n = player.g.position()
    moves = player.field_moves()
    tool_held = any(item == nav.ITEM_WATERFALL_TOOL for item, _ in player.g.key_items())
    print(f"pos map ({g},{n}) tile ({x},{y}) moves={sorted(moves)} waterfall_tool={tool_held}")

    # (1) warps on this map; the Victory Road door is the one whose dest group is 16
    for w in rowe_map.warps(emu):
        tag = "  <- Victory Road" if w.dest_group == VICTORY_ROAD_GROUP else ""
        print(f"warp tile ({w.x},{w.y}) -> map ({w.dest_group},{w.dest_num}) warp#{w.dest_warp}{tag}")

    # (2) every 0x13 tile on the layout, grouped into columns by x
    grid = nav.Grid(emu)
    lw, lh = grid.width - 2 * S.MAP_OFFSET, grid.height - 2 * S.MAP_OFFSET
    falls = [(lx, ly) for ly in range(lh) for lx in range(lw) if _beh(grid, (lx, ly)) == nav.WATERFALL]
    cols = {}
    for fx, fy in falls:
        cols.setdefault(fx, []).append(fy)
    print(f"0x13 waterfall tiles: {len(falls)} in column(s) x={sorted(cols)}")
    for cx in sorted(cols):
        ys = sorted(cols[cx])
        bottom = (cx, ys[-1])
        top = (cx, ys[0])
        below = (cx, ys[-1] + 1)
        above = (cx, ys[0] - 1)
        print(f"  column x={cx}: {len(ys)} tiles y={ys[0]}..{ys[-1]}, "
              f"bottom {bottom} top {top}")
        print(f"    tile south of bottom {below}: behavior "
              f"{hex(_beh(grid, below)) if _beh(grid, below) is not None else None} "
              f"({WATER_LABELS.get(_beh(grid, below), 'land/other')})")
        print(f"    tile north of top {above}: behavior "
              f"{hex(_beh(grid, above)) if _beh(grid, above) is not None else None} "
              f"({WATER_LABELS.get(_beh(grid, above), 'land/other')})")

    if not cols:
        print("PROBE DONE", json.dumps({"falls": 0}))
        return

    # measure the longest column (the endgame climb), its surf foot and plateau head
    cx = max(cols, key=lambda c: len(cols[c]))
    ys = sorted(cols[cx])
    foot = (cx, ys[-1] + 1)   # surf tile under the fall
    head = (cx, ys[0] - 1)    # first standable tile above the fall

    # (3) is the surf foot reachable from where the avatar stands, and does the grid route the
    # climb up the column as a one-way tool edge
    grid.climb = tool_held
    grid.tools = frozenset(moves)
    surf = "SURF" in moves
    to_foot = grid.path((x, y), foot, surf=surf)
    up_col = grid.path(foot, head, surf=surf)
    print(f"path (avatar {x},{y}) -> surf foot {foot}: "
          f"{'len ' + str(len(to_foot)) if to_foot else 'UNREACHABLE'}")
    print(f"path (surf foot {foot}) -> plateau head {head} up the column: "
          f"{'len ' + str(len(up_col)) + ' ' + str(up_col) if up_col else 'NO ROUTE'}")

    # (4) drive the real climb and read the prompt off the screen
    r = player.nav.walk_to(foot, surf=surf, tools=frozenset(moves))
    px, py, *_ = player.g.position()
    print(f"walk_to surf foot: {r}, now ({px},{py})")
    emu.save_png("/tmp/evergrande_01_atfoot.png")

    if (px, py) == foot:
        run = player.run
        # mirror nav._climb's facing reset, then capture each A press
        for key in (eb.KEY_DOWN, eb.KEY_UP):
            run(4, key)
            run(20, 0)
        emu.save_png("/tmp/evergrande_02_facing.png")
        run(8, eb.KEY_A)
        run(60, 0)
        emu.save_png("/tmp/evergrande_03_prompt.png")
        a_pos = player.g.position()[:2]
        run(8, eb.KEY_A)
        trace = []
        last = a_pos
        for i in range(nav.CLIMB_TICKS):
            run(30, 0)
            now = player.g.position()[:2]
            if now != last:
                trace.append((i, list(now)))
            if now == last and i > 0:
                break
            last = now
        emu.save_png("/tmp/evergrande_04_after.png")
        ex, ey, eg, en = player.g.position()
        print(f"A,A climb: start {foot} after-first-A {a_pos} -> end map ({eg},{en}) tile ({ex},{ey})")
        print(f"rise trace (tick, pos): {trace}")
        print(f"reached plateau head row {head[1]}: {ey <= head[1]}")
    else:
        print(f"did not reach surf foot {foot}; climb drive skipped")

    print("PROBE DONE", json.dumps({"falls": len(falls), "columns": {str(c): sorted(v) for c, v in cols.items()},
                                    "foot": list(foot), "head": list(head),
                                    "foot_reachable": bool(to_foot), "up_route": bool(up_col)}))


if __name__ == "__main__":
    main()
