"""Hunt the wild-battle switch stall ("party menu never opened (cb2 0x80bfd2d)") offline.

Reloads the route101 snapshot, idles a different frame count each run so the encounter RNG
differs, plays the battle through Player.battle_step, and wraps _open_wild_switch to log every
tap's cb2, action cursor and controller func. On a stall it writes /tmp/stall_pre.ss (the state
the switch was decided on), /tmp/stall_after.ss and .png, prints the tap log, and keeps going.

    .venv/bin/python probe_switch_stall.py [minutes]
"""
import shutil
import sys
import time

import emu_boot as eb
import play
import rowe_symbols as S
from emu_boot import Emu

STATE = "states/fixtures/route101.ss"


def main(minutes: float) -> None:
    t0 = time.time()
    n = stalls = battles = 0
    while time.time() - t0 < minutes * 60:
        n += 1
        e = Emu()
        e.load_state(open(STATE, "rb").read())
        e.run(2 + 7 * n)
        p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-probe-caught.json")
        p.wanted = []
        for i in range(400):
            if p.g.in_battle():
                break
            p.run(16, eb.KEY_LEFT if (i // 4) % 2 else eb.KEY_RIGHT)
            p.run(4)
        if not p.g.in_battle():
            continue
        battles += 1
        p._switch_active = None
        p._wild_switched = False
        foes0 = [(m.nickname, m.level) for m in p.g.battlers()[1::2]]
        orig_open, orig_tap, log = p._open_wild_switch, p.tap, []

        def tap(key):
            log.append((key, hex(p.g.callback2()), p.g.action_cursor(0), hex(e.u32(S.BATTLER0_CONTROLLER_FUNC)),
                        p.g.battlers()[0].hp if p.g.in_battle() else None))
            orig_tap(key)
            log.append(("->", hex(p.g.callback2()), p.g.action_cursor(0), p.g.in_battle()))

        def wrapped(slot):
            nonlocal stalls
            open("/tmp/stall_candidate.ss", "wb").write(e.save_state())
            p.tap = tap
            log.clear()
            orig_open(slot)
            p.tap = orig_tap
            if p.switch_to is None:
                stalls += 1
                shutil.copy("/tmp/stall_candidate.ss", "/tmp/stall_pre.ss")
                open("/tmp/stall_after.ss", "wb").write(e.save_state())
                e.save_png("/tmp/stall_after.png")
                print(f"STALL run {n} foes {foes0} lead {p.g.party()[0].nickname} {p.g.party()[0].hp}", flush=True)
                for row in log:
                    print("   ", row, flush=True)
                print("    after:", hex(p.g.callback2()), "in_battle", p.g.in_battle(), "outcome", p.g.battle_outcome(), flush=True)

        p._open_wild_switch = wrapped
        steps = 0
        while p.g.in_battle() and steps < 80:
            p.battle_step()
            steps += 1
        print(f"run {n} foes {foes0} steps {steps} outcome {p.g.battle_outcome()} switched {p._wild_switched}", flush=True)
    print(f"{battles} battles, {stalls} stalls", flush=True)


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 10)
