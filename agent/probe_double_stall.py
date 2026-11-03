"""Read the Sootopolis double-stall dump from BOTH player battlers, then let battle_step drive it and
log every press, to tell "battler 2's menu is up and the bot keeps cancelling it" from a real wedge.

    .venv/bin/python probe_double_stall.py /tmp/rowe_stall_1793535118.ss [steps]
"""
import sys

import emu_boot as eb
import play
import rowe_symbols as S
from emu_boot import Emu

KEYS = {eb.KEY_A: "A", eb.KEY_B: "B", eb.KEY_UP: "U", eb.KEY_DOWN: "D", eb.KEY_LEFT: "L",
        eb.KEY_RIGHT: "R", eb.KEY_START: "ST"}


def snap(p, tag):
    g = p.g
    funcs = " ".join(f"{g.controller_func(i):#x}" for i in range(4))
    chosen = list(p.e.read(S.addr("gChosenActionByBattler"), 4))
    print(f"[{tag}] type {g.battle_type_flags():#x} exec {g.exec_flags():#x} chooser {g.chooser()}"
          f" choosing0 {g.choosing(0)} choosing2 {g.choosing(2)}\n"
          f"      funcs {funcs}  act_cur 0:{g.action_cursor(0)} 2:{g.action_cursor(2)}"
          f"  move_cur 0:{g.move_cursor(0)} 2:{g.move_cursor(2)}  chosen {chosen}", flush=True)


def main(path, steps):
    e = Emu()
    e.load_state(open(path, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-probe-caught.json")
    snap(p, "dump")
    real_tap = p.tap
    log = []

    def tap(keys, *a, **k):
        log.append(f"{KEYS.get(keys, keys)}@b{p.g.chooser()}")
        real_tap(keys, *a, **k)

    p.tap = tap
    for i in range(steps):
        if not p.g.in_battle():
            print(f"battle ended after {i} steps")
            break
        log.clear()
        try:
            p.battle_step()
        except play.StopRequested:
            print("battle_step raised StopRequested (WEDGE/STALL dump)")
            break
        print(f"step {i}: {' '.join(log)}")
        snap(p, f"after {i}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 20)
