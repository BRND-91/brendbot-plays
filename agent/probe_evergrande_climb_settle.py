"""Does the committed nav._climb ride the Ever Grande fall all the way to the plateau, or stall
partway. Walk to the surf foot, call the real _climb, then run a long settle and report the final
idle tile and its behavior so a stop on a 0x13 tile (never a standing tile) is distinguished from a
landing above the fall."""
import shutil

import emu_boot as eb
import nav
import play
import rowe_symbols as S

SCRATCH = "/tmp/rowe_evergrande_settle.ss"
FOOT = (15, 68)
HEAD_ROW = 59


def main():
    shutil.copy("states/live.ss", SCRATCH)
    emu = eb.Emu()
    with open(SCRATCH, "rb") as f:
        emu.load_state(f.read())
    player = play.Player(emu, play.NullStreamer(), ledger_path=SCRATCH + ".caught.json")
    moves = frozenset(player.field_moves())

    r = player.nav.walk_to(FOOT, surf=True, tools=moves)
    print(f"walk_to {FOOT}: {r} at {player.g.position()[:2]}")
    climbed = player.nav._climb()
    mid = player.g.position()
    # keep the frames running well past the ride so a slow animation finishes
    for _ in range(40):
        player.run(30, 0)
        if player.g.in_battle():
            print("battle during settle")
            break
    x, y, g, n = player.g.position()
    grid = nav.Grid(emu)
    beh = grid._behavior(grid.cell(x, y) & S.GRID_ID_MASK) if grid._behavior else None
    print(f"_climb returned {climbed}, right after: {mid[:2]}, settled: map ({g},{n}) tile ({x},{y})")
    print(f"final tile behavior {hex(beh) if beh is not None else None}  "
          f"on_waterfall_tile={beh == nav.WATERFALL}  above_fall={y < HEAD_ROW + 1}")
    emu.save_png("/tmp/evergrande_settle.png")


if __name__ == "__main__":
    main()
