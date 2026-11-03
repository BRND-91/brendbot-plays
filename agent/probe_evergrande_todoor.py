"""From the live Ever Grande landing, can one walk_to route surf -> waterfall climb -> surf up to
the Victory Road door warp (18,5) and cross it, with no new code. Proves whether the endgame leg
past (0,8) needs only a planner goal, the climb being already committed."""
import shutil

import emu_boot as eb
import play

SCRATCH = "/tmp/rowe_evergrande_door.ss"
DOOR = (18, 5)


def main():
    shutil.copy("states/live.ss", SCRATCH)
    emu = eb.Emu()
    with open(SCRATCH, "rb") as f:
        emu.load_state(f.read())
    player = play.Player(emu, play.NullStreamer(), ledger_path=SCRATCH + ".caught.json")
    moves = frozenset(player.field_moves())
    start = player.g.position()
    r = player.nav.walk_to(DOOR, surf=True, max_replans=60, tools=moves)
    end = player.g.position()
    print(f"start {start} -> walk_to {DOOR}: {r}, end map ({end[2]},{end[3]}) tile ({end[0]},{end[1]})")
    emu.save_png("/tmp/evergrande_door.png")


if __name__ == "__main__":
    main()
