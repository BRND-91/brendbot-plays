"""Live smoke of _dive_frontier at the party's stuck grind spot: boot a copy of the running
save, report the diveable tiles the grid reaches and their metatile behavior (0x14 is Sootopolis
deep water), then drive the real dive and read whether the map changed and the graph gained a node.
Answers whether explore's new off-cluster dive actually submerges here, the part the unit test
cannot reach. Runs off states/fixtures so the live supervisor keeps its own files."""
import json
import os
import shutil

import emu_boot as eb
import map_graph
import nav
import play
import rowe_map
import rowe_rom
import rowe_symbols as S

LIVE = "states/fixtures"
SCRATCH = "states/fixtures"
BEH = {0x11: "SEMI_DEEP_WATER", 0x12: "DEEP_WATER", 0x14: "SOOTOPOLIS_DEEP_WATER"}


def main() -> None:
    os.makedirs(SCRATCH, exist_ok=True)
    state = os.path.join(SCRATCH, "dive_probe.ss")
    shutil.copy(os.path.join(LIVE, "route101.ss"), state)
    shutil.copy(os.path.join(LIVE, "map_graph.json"), os.path.join(SCRATCH, "map_graph.json"))

    emu = eb.Emu()
    with open(state, "rb") as f:
        emu.load_state(f.read())
    player = play.Player(emu, play.NullStreamer(), ledger_path=state + ".caught.json")
    player.state_path = state
    player.graph = map_graph.MapGraph(os.path.join(SCRATCH, "map_graph.json"),
                                      world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())

    x, y, g, n = player.g.position()
    moves = player.field_moves()
    surf = "SURF" in moves
    grid = nav.Grid(emu)
    tiles = grid.dive_tiles((x, y), surf=surf)
    labelled = [(list(t), BEH.get(grid._behavior(grid.cell(*t) & S.GRID_ID_MASK), "other"))
                for t in tiles]
    print(f"pos map ({g},{n}) tile ({x},{y}) surf={surf} DIVE={'DIVE' in moves}")
    print(f"reachable diveable tiles: {labelled}")

    # distinguish 'no deep water on this map' from 'deep water the walk cannot reach from here'
    lw, lh = grid.width - 2 * S.MAP_OFFSET, grid.height - 2 * S.MAP_OFFSET
    anywhere = {}
    for ly in range(lh):
        for lx in range(lw):
            b = grid._behavior(grid.cell(lx, ly) & S.GRID_ID_MASK) if grid._behavior else None
            if b in BEH:
                anywhere.setdefault(BEH[b], 0)
                anywhere[BEH[b]] += 1
    print(f"dive behaviors anywhere on this map: {anywhere or 'none'}")
    print(f"connections: {[(c.direction, c.group, c.num) for c in rowe_map.connections(emu)]}")

    before = player.g.position()[2:]
    adj_before = set(player.graph.adj)
    region = player.region()
    if not tiles:
        print("PROBE DONE", json.dumps({"moved": False, "before": list(before),
                                        "reason": "no reachable diveable tile here",
                                        "dive_anywhere": anywhere}))
        return
    moved = player._dive_frontier(region, moves)
    ax, ay, ag, an = player.g.position()
    new = []
    if (ag, an) != before:
        new = player.graph.observe((ag, an), [(c.group, c.num) for c in rowe_map.connections(emu)])
    print(f"dive: moved={moved} map {before} -> ({ag},{an}) tile ({ax},{ay})")
    print(f"graph new nodes from the landing: {[list(m) for m in new]}")
    print(f"adj grew: {len(player.graph.adj) - len(adj_before)} node(s)")
    emu.save_png(os.path.join(SCRATCH, "dive_probe_after.png"))
    print("PROBE DONE", json.dumps({"moved": moved, "before": before, "after": [ag, an],
                                    "dive_tiles": labelled, "new_nodes": [list(m) for m in new]}))


if __name__ == "__main__":
    main()
