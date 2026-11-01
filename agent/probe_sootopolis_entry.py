"""Hunt the scripted warp into Sootopolis. Static analysis shows the gym map (15,0) and
Sootopolis City (0,7) in a component with zero connection or warp edges from the party's
component, and surfacing from the underwater maps lands on (0,34)/(0,126), never the city. So
the entry is a coord-event or metatile-triggered warp the ROM tables do not encode. This drives a
copy of the live save one hop east onto Route 127 (0,127), the Sootopolis-adjacent water, and
steps every non-ordinary metatile there, logging each map change, to find the tile that fires the
warp. Runs off states/fixtures so the live supervisor keeps its own files."""
import json
import os
import shutil
import time

import emu_boot as eb
import map_graph
import nav
import play
import rowe_map
import rowe_rom
import rowe_symbols as S

SCRATCH = "states/fixtures"
LOG = os.path.join(SCRATCH, "sootopolis_entry.jsonl")
ORDINARY = {0x0} | set(range(0x10, 0x16))  # plain ground and surfable water, not a trigger
BUDGET_S = 1200
MAX_WALKS = 400


def main() -> None:
    os.makedirs(SCRATCH, exist_ok=True)
    state = os.path.join(SCRATCH, "entry_probe.ss")
    shutil.copy("states/fixtures/route101.ss", state)
    shutil.copy("states/fixtures/map_graph.json", os.path.join(SCRATCH, "map_graph.json"))

    emu = eb.Emu()
    with open(state, "rb") as f:
        emu.load_state(f.read())
    player = play.Player(emu, play.NullStreamer(), ledger_path=state + ".caught.json")
    player.state_path = state
    player.graph = map_graph.MapGraph(os.path.join(SCRATCH, "map_graph.json"),
                                      world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
    fh = open(LOG, "w")

    def rec(ev: dict) -> None:
        fh.write(json.dumps(ev) + "\n")
        fh.flush()

    def here() -> tuple:
        return player.g.position()[2:]

    def fight_out() -> int:
        # a wild encounter mid-walk leaves the party on its start map, so a crossing or a
        # tile-step reads as a non-move; drain the fight through the real battle loop and the
        # walk resumes instead of the probe calling a stalled position a dead end
        steps = 0
        while player.g.in_battle() and steps < 4000:
            player.battle_step()
            steps += 1
        return steps

    moves = player.field_moves()
    surf = "SURF" in moves
    end = time.monotonic() + BUDGET_S
    rec({"kind": "start", "pos": list(player.g.position()), "moves": sorted(moves)})

    hops = 0
    while here() != (0, 127) and hops < 8:
        st = player.errands.cross_edge(rowe_map.DIR_EAST, surf=surf, tools=moves)
        fought = fight_out() if st == "battle" else 0
        rec({"kind": "hop_east", "status": st, "fought": fought, "pos": list(player.g.position())})
        hops += 1
    if here() != (0, 127):
        rec({"kind": "abort", "why": "never reached (0,127)", "pos": list(player.g.position())})
        fh.close()
        print("PROBE DONE abort, no (0,127)", flush=True)
        return

    grid = nav.Grid(emu)
    x, y, _, _ = player.g.position()
    reach = grid.reachable((x, y), surf)
    behav = {t: grid._behavior(grid.cell(*t) & S.GRID_ID_MASK) for t in reach}
    specials = sorted(t for t in reach if behav[t] not in ORDINARY)
    rec({"kind": "survey", "reachable": len(reach),
         "special_tiles": [[list(t), hex(behav[t])] for t in specials]})

    # stepping onto a trigger tile is what fires a coord-event warp, so walk onto each unusual tile
    # and watch the map; a perimeter sample of plain water catches a trigger that sits on open sea
    perim = sorted(t for t in reach if min(t[0], t[1]) <= 1)[:80]
    targets = specials + [t for t in perim if t not in specials]
    walks = 0
    for t in targets:
        if time.monotonic() > end or walks >= MAX_WALKS:
            rec({"kind": "budget", "walks": walks})
            break
        before = here()
        r = player.errands.nav.walk_to(t, surf=surf, tools=moves)
        tries = 0
        while r == "battle" and tries < 6:
            fight_out()
            r = player.errands.nav.walk_to(t, surf=surf, tools=moves)
            tries += 1
        walks += 1
        after = here()
        if after != before:
            rec({"kind": "transition", "target": list(t), "beh": hex(behav[t]),
                 "from": list(before), "to": list(player.g.position()), "status": r})
            if after[0] == 15 or after == (0, 7):
                rec({"kind": "FOUND", "entry_tile": list(t), "beh": hex(behav[t]),
                     "landed": list(player.g.position())})
                break
            if here() == (0, 25):
                if player.errands.cross_edge(rowe_map.DIR_EAST, surf=surf, tools=moves) == "battle":
                    fight_out()
        elif behav[t] not in ORDINARY:
            # could not step on it: stand adjacent and press A, the dive-prompt path
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nb = (t[0] + dx, t[1] + dy)
                if nb in reach and player.errands.nav.walk_to(nb, surf=surf, tools=moves) == "arrived":
                    b2 = here()
                    player.run(24, eb.KEY_A)
                    player.run(90, 0)
                    if here() != b2:
                        rec({"kind": "interact", "tile": list(t), "beh": hex(behav[t]),
                             "from": list(b2), "to": list(player.g.position())})
                    break
    rec({"kind": "done", "final": list(player.g.position()), "walks": walks})
    fh.close()
    print("PROBE DONE", json.dumps({"final": list(player.g.position()), "walks": walks,
                                    "specials": len(specials)}), flush=True)


if __name__ == "__main__":
    main()
