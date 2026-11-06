"""Replay a battle wedge dump through battle_step and log every press, so a fix to the no-PP
dispatch is red on the dump before the edit and green after. --classify presses B, then DOWN, and
reads the move cursor back, which tells a controller func that takes list input from one that holds
a text box. Reads only; writes nothing under states/.

    probe_morty_wedge.py --state /tmp/rowe_stall_1793924806.ss [--steps 8] [--classify]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb  # noqa: E402
import play  # noqa: E402
import rowe_symbols as S  # noqa: E402


def state_line(p, tag):
    g = p.g
    b = g.chooser()
    mons = g.battlers()
    me = mons[b] if b < len(mons) else None
    foes = [f"{m.nickname} {m.hp}/{m.max_hp}" for m in mons[1::2]]
    print(f"{tag}: cb2 {g.callback2():#x} func {g.controller_func(b):#x} comm {g.comm(b)} "
          f"action {g.action_cursor(b)} move {g.move_cursor(b)} "
          f"me {me.nickname if me else None} pp {list(me.pp) if me else None} foes {foes} "
          f"instr {p.e.u32(S.addr('gBattlescriptCurrInstr')):#x}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--steps", type=int, default=8)
    ap.add_argument("--classify", action="store_true")
    a = ap.parse_args()

    e = eb.Emu()
    e.load_state(open(a.state, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe_morty_probe.json")
    state_line(p, "start")
    if a.classify:
        for key, name in ((eb.KEY_B, "B"), (eb.KEY_DOWN, "DOWN"), (eb.KEY_UP, "UP"), (eb.KEY_B, "B")):
            p.tap(key)
            p.run(20)
            state_line(p, f"after {name}")
        return
    for i in range(a.steps):
        p.battle_step()
        state_line(p, f"step {i + 1}")
        if not p.g.in_battle():
            print("battle over", flush=True)
            break


if __name__ == "__main__":
    main()
