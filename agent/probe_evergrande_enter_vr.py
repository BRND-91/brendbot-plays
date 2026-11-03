"""Step-1 trace: from the /tmp copy parked at (0,8) tile (0,67), walk straight to the Victory Road
entrance door's approach tile (27,49) with surf+climb, then press UP and poll map_id across the
press, expecting map (16,12). Separates the walk (does it reach the approach up the fall) from the
door press (does UP fire the warp), so the stuck-before-climb story is retested now the climb runs."""
import shutil

import emu_boot as eb
import nav
import play
import rowe_symbols as S

SCRATCH = "/tmp/rowe_vr_entry.ss"
ENTRY = (16, 12)
APPROACH = (27, 49)
DOOR = (27, 48)


def cellinfo(grid, x, y):
    c = grid.cell(x, y)
    beh = grid._behavior(c & S.GRID_ID_MASK) if grid._behavior else None
    elev = (c >> S.GRID_ELEVATION_SHIFT) & 0xF
    return beh, elev, bool(c & S.GRID_BLOCKED)


def main():
    shutil.copy("states/live.ss", SCRATCH)
    emu = eb.Emu()
    with open(SCRATCH, "rb") as f:
        emu.load_state(f.read())
    player = play.Player(emu, play.NullStreamer(), ledger_path=SCRATCH + ".caught.json")
    moves = frozenset(player.field_moves())
    print(f"start: {player.g.position()}")

    r = player.nav.walk_to(APPROACH, surf=True, tools=moves)
    pos = player.g.position()
    print(f"walk_to {APPROACH}: {r}  now {pos[:2]} map ({pos[2]},{pos[3]})")
    emu.save_png("/tmp/vr_01_approach.png")
    grid = nav.Grid(emu)
    for t in (APPROACH, DOOR):
        b, e, blk = cellinfo(grid, *t)
        print(f"  {t}: beh {hex(b)} elev {e} blocked {blk}")
    print(f"  player_elev off object event at approach: {grid.player_elev}")

    if pos[:2] != APPROACH:
        print("did not reach the approach; door press skipped")
        return

    before = (pos[2], pos[3])
    player.run(24, eb.KEY_UP)
    trace = []
    for i in range(6):
        player.run(30, 0)
        p = player.g.position()
        trace.append((i, (p[2], p[3]), (p[0], p[1])))
        if (p[2], p[3]) != before:
            break
    emu.save_png("/tmp/vr_02_afterUP.png")
    print(f"UP press poll (tick, map, tile): {trace}")
    p = player.g.position()
    print(f"RESULT reached_entry={(p[2], p[3]) == ENTRY} final map ({p[2]},{p[3]}) tile ({p[0]},{p[1]})")


if __name__ == "__main__":
    main()
