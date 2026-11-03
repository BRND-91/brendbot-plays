"""Why (18,5) is unreachable: climb to the plateau, then from the surfing head try to path to the
door and dump the behavior + collision + elevation of the water-to-land seam around it, so the
blocker (a dismount rule, a stair, a one-way bank) is named rather than guessed."""
import shutil

import emu_boot as eb
import nav
import play
import rowe_symbols as S

SCRATCH = "/tmp/rowe_evergrande_app.ss"
DOOR = (18, 5)


def cellinfo(grid, x, y):
    c = grid.cell(x, y)
    mid = c & S.GRID_ID_MASK
    beh = grid._behavior(mid) if grid._behavior else None
    elev = (c >> S.GRID_ELEVATION_SHIFT) & 0xF
    blocked = bool(c & S.GRID_BLOCKED)
    return beh, elev, blocked


def main():
    shutil.copy("states/live.ss", SCRATCH)
    emu = eb.Emu()
    with open(SCRATCH, "rb") as f:
        emu.load_state(f.read())
    player = play.Player(emu, play.NullStreamer(), ledger_path=SCRATCH + ".caught.json")
    moves = frozenset(player.field_moves())

    player.nav.walk_to((15, 68), surf=True, tools=moves)
    player.nav._climb()
    for _ in range(30):
        player.run(30, 0)
    hx, hy, hg, hn = player.g.position()
    grid = nav.Grid(emu)
    grid.climb = True
    grid.tools = moves
    print(f"plateau pos ({hx},{hy}) map ({hg},{hn})")
    print(f"path head->door: {grid.path((hx, hy), DOOR, surf=True)}")
    print(f"path head->door no-surf: {grid.path((hx, hy), DOOR, surf=False)}")

    # reachable set from the plateau head, to see how far the surf gets before the land seam
    seen = {(hx, hy)}
    frontier = [(hx, hy)]
    while frontier:
        cx, cy = frontier.pop()
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nxt = (cx + dx, cy + dy)
            if nxt in seen:
                continue
            if grid.path((hx, hy), nxt, surf=True):
                seen.add(nxt)
                frontier.append(nxt)
    north = sorted(seen, key=lambda t: (t[1], t[0]))[:8]
    print(f"reachable from head: {len(seen)} tiles, northernmost: {north}")
    for door in [(18, 5), (27, 48)]:
        adj = [(door[0] + dx, door[1] + dy) for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0))]
        print(f"door {door}: in reachable={door in seen}, "
              f"adj reachable={[a for a in adj if a in seen]}, "
              f"path head->door={grid.path((hx, hy), door, surf=True) is not None}")

    print("seam behavior,elev,blocked  rows y=2..14, cols x=12..24 (D=door):")
    for y in range(2, 15):
        row = []
        for x in range(12, 25):
            beh, elev, blk = cellinfo(grid, x, y)
            mark = "D" if (x, y) == DOOR else ("#" if blk else " ")
            row.append(f"{mark}{beh:02x}.{elev}")
        print(f"y{y:2}: " + " ".join(row))


if __name__ == "__main__":
    main()
