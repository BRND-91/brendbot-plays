"""Reproduce the surf cross the travel loop gives up on and record the metatile behavior
of every dismount bank it tries, split by whether the step landed.

The grid models only water behaviors (nav.WATER_BEHAVIORS); a directional ledge reads as open
floor, so a surf dismount onto one is driven by the walk but refused by the game. ROWE numbers
behaviors in 9 bits with no name table in the repo, so the culprit id is found here empirically:
a value on refused banks and absent from accepted ones is the dismount-blocker. Accepted banks
are the control, the same dismount on the same path that does land.

Runs in a scratch dir off a copy of the live save so the production supervisor keeps its own
state, and drops the gates whose only requirement is SURF so the executor re-drives the water
crosses it had given up on instead of reading them as permanently closed.
"""
import json
import os
import shutil

import emu_boot as eb
import rowe_symbols as S
import rowe_rom
import nav
import play

LIVE = "states/fixtures"
SCRATCH = "/tmp/rowe_probe"
GYM = {"mode": "gym", "map": [11, 3], "badges": 0}
BUDGET_S = 1500


def stage() -> str:
    os.makedirs(SCRATCH, exist_ok=True)
    shutil.copy(os.path.join(LIVE, "route101.ss"), os.path.join(SCRATCH, "route101.ss"))
    with open(os.path.join(LIVE, "map_graph.json")) as f:
        graph = json.load(f)
    graph["gated"] = [g for g in graph.get("gated", []) if sorted(g[2]) != ["SURF"]]
    with open(os.path.join(SCRATCH, "map_graph.json"), "w") as f:
        json.dump(graph, f)
    with open(os.path.join(SCRATCH, "goal.json"), "w") as f:
        json.dump(GYM, f)
    with open(os.path.join(SCRATCH, "gym_closed.json"), "w") as f:
        json.dump([], f)
    return os.path.join(SCRATCH, "route101.ss")


def main() -> None:
    rowe_rom.self_check()
    state = stage()
    out = open(os.path.join(SCRATCH, "surf_dismount_probe.jsonl"), "w")

    def rec(ev: dict) -> None:
        out.write(json.dumps(ev) + "\n")
        out.flush()

    orig_advance = nav.Navigator._advance

    def advance(self, grid, cur, d, surf):
        nxt = (cur[0] + d[0], cur[1] + d[1])
        is_dismount = surf and grid._is_water(*cur) and not grid._is_water(*nxt)
        bank_beh = grid._behavior(grid.cell(*nxt) & S.GRID_ID_MASK) if grid._behavior else None
        before = self.g.position()[:2]
        moved = orig_advance(self, grid, cur, d, surf)
        if is_dismount:
            rec({"kind": "dismount", "bank": list(nxt), "bank_beh": bank_beh,
                 "moved": self.g.position()[:2] != before,
                 "map": list(self.g.position()[2:])})
        return moved

    nav.Navigator._advance = advance

    orig_cross = play.Errands.cross_edge

    def cross_edge(self, direction, surf=False, rank=None):
        status = orig_cross(self, direction, surf=surf, rank=rank)
        rec({"kind": "cross_edge", "dir": direction, "surf": surf, "status": status})
        return status

    play.Errands.cross_edge = cross_edge

    emu = eb.Emu()
    with open(state, "rb") as f:
        emu.load_state(f.read())
    player = play.Player(emu, play.NullStreamer(), ledger_path=state + ".caught.json")
    player.state_path = state
    rec({"kind": "start", "pos": list(player.g.position())})
    try:
        player.loop(BUDGET_S)
    except play.GoalExit as g:
        rec({"kind": "goal_exit", "reason": str(g)})

    seen = {}
    for line in open(os.path.join(SCRATCH, "surf_dismount_probe.jsonl")):
        ev = json.loads(line)
        if ev.get("kind") != "dismount":
            continue
        beh = ev["bank_beh"]
        acc, ref = seen.get(beh, (0, 0))
        seen[beh] = (acc + (1 if ev["moved"] else 0), ref + (0 if ev["moved"] else 1))
    summary = {hex(b) if isinstance(b, int) else str(b): {"accepted": a, "refused": r}
               for b, (a, r) in seen.items()}
    rec({"kind": "summary", "by_behavior": summary})
    out.close()
    print("PROBE DONE", json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
