"""Does the ROM refuse a step between two open tiles of different elevation, the way
IsZCoordMismatchAt does in the vendored source, or does the executor's grid rule (any open tile
walks at any height) match the game? Each press across a height change is logged beside a press
of the same kind between equal heights, so a refusal has its control on the same path.

Drives the Fortree gym door-mat state out of the gym, east into Route 120 to the long bridge's
west end (elevation 4 land onto the elevation 7 deck), then surfs the upper pool back to that
end and presses from the water onto it and onto a plain elevation-3 bank.

    probe_elevation.py [SNAPSHOT]     -> states/fixtures/elevation_probe.jsonl
"""
import json
import os
import shutil
import sys

import emu_boot as eb
import play
import rowe_map
import rowe_symbols as S
from nav import Grid
from routines import Errands

SNAPSHOT = sys.argv[1] if len(sys.argv) > 1 else "states/fixtures/fortree_entry_beaten.ss"
SRC = "states/fixtures/elev_src.ss"
OUT = "states/fixtures/elevation_probe.jsonl"
GYM, FORTREE, ROUTE120 = (12, 1), (0, 4), (0, 35)
UP, DOWN, LEFT, RIGHT = (0, -1), (0, 1), (-1, 0), (1, 0)


def main() -> None:
    shutil.copy(SNAPSHOT, SRC)
    with open(os.path.join(os.path.dirname(SRC), "goal.json"), "w") as f:
        f.write('{"mode": "travel", "to": [0, 35]}')
    e = eb.Emu()
    with open(SRC, "rb") as f:
        e.load_state(f.read())
    player = play.Player(e, play.NullStreamer(), ledger_path=SRC + ".caught.json")
    player.state_path = SRC
    player.loop(0)
    g, nav = player.g, player.nav
    out = open(OUT, "w")

    def rec(**ev) -> None:
        out.write(json.dumps(ev) + "\n")
        out.flush()
        print(ev, flush=True)

    def fight() -> None:
        while g.in_battle():
            player.battle_step()

    def go(goal: tuple, surf: bool = False) -> bool:
        for _ in range(40):
            status = nav.walk_to(goal, surf)
            if status == "arrived":
                return True
            if status == "battle":
                fight()
                continue
            rec(kind="walk", goal=list(goal), surf=surf, status=status, at=list(g.position()))
            return False
        return False

    def press(label: str, d: tuple) -> bool:
        grid = Grid(e)
        cur = g.position()[:2]
        nxt = (cur[0] + d[0], cur[1] + d[1])
        elev = [grid.cell(*cur) >> S.GRID_ELEVATION_SHIFT, grid.cell(*nxt) >> S.GRID_ELEVATION_SHIFT]
        beh = [grid._behavior(grid.cell(*t) & S.GRID_ID_MASK) for t in (cur, nxt)]
        nav.step(d)
        fight()
        moved = g.position()[:2] == nxt
        rec(kind="press", label=label, frm=list(cur), to=list(nxt), elev=elev, beh=beh,
            map=list(g.position()[2:]), moved=moved)
        return moved

    assert g.position()[2:] == GYM, g.position()
    for _ in range(4):  # the exit mat is a few tiles under the start tile; the warp fires on it
        nav.step(DOWN)
        nav.settle_map()
        if g.position()[2:] == FORTREE:
            break
    if g.position()[2:] != FORTREE:
        rec(kind="walk", goal="fortree", status="no exit", at=list(g.position()))
        return
    Errands(e, e.run).cross_edge(rowe_map.DIR_EAST)
    fight()
    if g.position()[2:] != ROUTE120:
        rec(kind="walk", goal="route120", status="no crossing", at=list(g.position()))
        return
    if go((8, 15)):
        press("r120 land 4->4 control", RIGHT)
        if press("r120 land 4->7 bridge end", RIGHT):
            press("r120 bridge end 7->7 deck", RIGHT)
            press("r120 deck 7->1 water, no surf prompt accepted", UP)
            nav.run(8, eb.KEY_B)
            nav.run(30, 0)

    # the bank at (20, 13) is the pool's only elevation-3 shore; the walk mounts there
    if go((20, 13)) and go((10, 14), surf=True):
        press("r120 water 1->7 bridge west end", DOWN)
        if go((17, 14), surf=True):
            press("r120 water 1->3 bank control", UP)
    rec(kind="done", at=list(g.position()))


if __name__ == "__main__":
    main()
