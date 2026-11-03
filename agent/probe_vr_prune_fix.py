"""Confirm the _step_into_warp prune fix: take_warp into (16,12) from the parked (0,8) copy now
attempts the (27,49) approach instead of pruning it. A walk_to wrapper logs each internal leg;
pre-fix none fired and take_warp returned stuck without moving."""
import shutil

import emu_boot as eb
import nav
import play

SCRATCH = "/tmp/rowe_vr_prune.ss"
ENTRY = (16, 12)


def main():
    shutil.copy("states/live.ss", SCRATCH)
    emu = eb.Emu()
    with open(SCRATCH, "rb") as f:
        emu.load_state(f.read())
    player = play.Player(emu, play.NullStreamer(), ledger_path=SCRATCH + ".caught.json")
    moves = frozenset(player.field_moves())
    print(f"start {player.g.position()}")

    orig = nav.Navigator.walk_to
    legs = []

    def traced(self, goal, surf=False, max_replans=20, tools=frozenset()):
        p0 = self.g.position()[:2]
        r = orig(self, goal, surf=surf, max_replans=max_replans, tools=tools)
        legs.append((tuple(goal), r, p0, self.g.position()[:2]))
        return r

    nav.Navigator.walk_to = traced
    status = player.errands.take_warp(ENTRY, surf=True, tools=moves)
    nav.Navigator.walk_to = orig
    for g, r, a, b in legs:
        print(f"  walk_to {g}: {r}  {a} -> {b}")
    p = player.g.position()
    print(f"take_warp({ENTRY}) -> {status}; at ({p[2]},{p[3]}) tile ({p[0]},{p[1]})")
    print(f"approach attempted: {(27, 49) in [g for g, *_ in legs]}")


if __name__ == "__main__":
    main()
