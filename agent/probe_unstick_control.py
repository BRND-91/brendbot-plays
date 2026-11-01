"""Run battle_step against saved battle dumps and report whether the turn resolves or loops.

Baseline vs fix control for the double-battle unstick-B loop: a double's two-battler action
selection holds HP/PP flat across steps, so the _act_stuck>=4 unstick fires B, which cancels the
partner's pick and bounces back to battler 0 forever. A single battle resolves because confirming
battler 0's move executes the turn and HP/PP move before the counter reaches 4.

    .venv/bin/python probe_unstick_control.py <state.ss> [state.ss ...] [steps]
"""
import io
import sys
from contextlib import redirect_stdout

import play
from emu_boot import Emu


def run_one(path, steps):
    e = Emu()
    e.load_state(open(path, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-unstick-ctrl.json")
    g = p.g
    if not g.in_battle():
        print(f"{path}: not in battle", flush=True)
        return
    flags = g.battle_type_flags()
    kind = ("DOUBLE" if flags & play.BATTLE_TYPE_DOUBLE else "single")
    kind += "+trainer" if flags & play.BATTLE_TYPE_TRAINER else "+wild"
    funcs = " ".join(f"{g.controller_func(i):#x}" for i in range(4))
    print(f"{path}: {kind} flags {flags:#x} chooser {g.chooser()} "
          f"choosing0 {g.choosing(0)} choosing2 {g.choosing(2)} funcs {funcs}", flush=True)
    buf = io.StringIO()
    stopped = ended = False
    took = 0
    sigs = set()
    with redirect_stdout(buf):
        for i in range(steps):
            if not g.in_battle():
                ended = True
                break
            try:
                p.battle_step()
            except (play.StopRequested, play.GoalExit):
                stopped = True
                break
            took = i + 1
            sigs.add(repr(p.battle_signature()))
    out = buf.getvalue()
    print(f"   -> steps {took} ended {ended} stopped {stopped} distinct_sigs {len(sigs)} "
          f"unstick_B {out.count('clearing submenu')} prompt_taps {out.count('prompt? battler')}",
          flush=True)


def main(argv):
    steps = 60
    paths = []
    for a in argv:
        if a.isdigit():
            steps = int(a)
        else:
            paths.append(a)
    for pth in paths:
        try:
            run_one(pth, steps)
        except (OSError, ValueError, RuntimeError) as ex:
            print(f"{pth}: ERROR {type(ex).__name__} {ex}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
