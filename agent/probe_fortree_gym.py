"""Walk the live party back into the Fortree gym on a scratch copy of the state and capture
what the live grid sees the moment challenge_leader reports the stand unreachable.

The ROM layout w/ the trainers' tiles blocked still paths to Winona's stand (15, 3), so the
live block is something the static read does not carry: a runtime object, a gate sprite, or a
layout the game rewrote. The capture is the state file (states/fixtures/fortree_gym.ss), every
active object event w/ its raw header bytes, the grid's NPC-blocked tiles, and the path verdict,
so the blocker is read from the capture instead of guessed.
"""
import json
import os
import shutil
import struct

import emu_boot as eb
import play
import rowe_symbols as S
from nav import Grid

LIVE = "states/fixtures"
SCRATCH = "/tmp/rowe_probe"
GYM = (12, 1)
STAND = (15, 3)
BUDGET_S = 1500


def stage() -> str:
    os.makedirs(SCRATCH, exist_ok=True)
    shutil.copy(os.path.join(LIVE, "route101.ss"), os.path.join(SCRATCH, "route101.ss"))
    shutil.copy(os.path.join(LIVE, "map_graph.json"), os.path.join(SCRATCH, "map_graph.json"))
    with open(os.path.join(SCRATCH, "goal.json"), "w") as f:
        json.dump({"mode": "gym", "map": list(GYM), "badges": 4}, f)
    with open(os.path.join(SCRATCH, "gym_closed.json"), "w") as f:
        json.dump([], f)
    return os.path.join(SCRATCH, "route101.ss")


def capture(player) -> dict:
    e = player.e
    grid = Grid(e)
    base = S.addr("gObjectEvents")
    objs = []
    for i in range(S.OBJECT_EVENTS_COUNT):
        raw = e.read(base + i * S.OBJ_EVENT_SIZE, S.OBJ_EVENT_SIZE)
        flags = struct.unpack_from("<I", raw, S.OBJ_FLAGS)[0]
        if not flags & S.OBJ_ACTIVE_BIT:
            continue
        cx, cy = struct.unpack_from("<hh", raw, S.OBJ_CURRENT_COORDS)
        objs.append({"slot": i, "flags": hex(flags), "head": raw[4:12].hex(),
                     "map": [raw[S.OBJ_MAP_GROUP], raw[S.OBJ_MAP_NUM]],
                     "tile": [cx - S.MAP_OFFSET, cy - S.MAP_OFFSET]})
    pos = player.g.position()
    return {"pos": list(pos), "objects": objs,
            "npc_blocked": sorted(grid.blocked_by_npc), "warps": sorted(grid.warp_tiles),
            "path": grid.path(pos[:2], STAND), "reachable": len(grid.reachable(pos[:2]))}


def main() -> None:
    state = stage()
    out = open(os.path.join(SCRATCH, "fortree_gym_probe.jsonl"), "w")

    def rec(ev: dict) -> None:
        out.write(json.dumps(ev) + "\n")
        out.flush()

    orig = play.Errands.challenge_leader

    def challenge_leader(self, stand):
        r = orig(self, stand)
        rec({"kind": "leader", "result": r, "stand": list(stand)})
        return r

    play.Errands.challenge_leader = challenge_leader
    orig_close = play.Player.record_closed_gym

    def record_closed_gym(self, gym, reason):
        """The sweep has fought every trainer in reach by the time the gym is written off, so
        the capture here carries beaten trainers, and the entry state made from it keeps them
        beaten while a fresh entry resets the gates, the start the route search needs."""
        rec({"kind": "closed", "gym": list(gym), "reason": reason})
        if tuple(gym) != GYM:
            return orig_close(self, gym, reason)
        with open(os.path.join(SCRATCH, "fortree_gym.ss"), "wb") as f:
            f.write(self.e.save_state())
        rec({"kind": "capture", **capture(self)})
        door = min(Grid(self.e).warp_tiles)
        r = self.nav.walk_to(door)
        self.run(24, eb.KEY_DOWN)
        self.run(120, 0)
        self.nav.settle_map()
        self.run(16, eb.KEY_UP)
        self.run(120, 0)
        self.nav.settle_map()
        self.run(60, 0)
        rec({"kind": "entry", "door": list(door), "walk": r, "pos": list(self.g.position())})
        if self.g.position()[2:] == GYM:
            with open(os.path.join(SCRATCH, "fortree_entry.ss"), "wb") as f:
                f.write(self.e.save_state())
        raise play.GoalExit("probe: gym captured after the sweep, entry state written")

    play.Player.record_closed_gym = record_closed_gym

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
    out.close()
    print("PROBE DONE", flush=True)
    if os.path.exists(os.path.join(SCRATCH, "fortree_entry.ss")):
        import probe_fortree_bfs
        probe_fortree_bfs.main()


if __name__ == "__main__":
    main()
