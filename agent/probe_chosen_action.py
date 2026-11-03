"""Verify gChosenActionByBattler: in a single wild battle choose Run, read index 0, expect 3.

The symbol is tagged projected in rowe_symbols.py, never confirmed by a live read. route101.ss is
parked on the gym lower floor with no reachable grass, so this drives a saved surf state into a
single wild water encounter instead, walks the action menu cursor to RUN (B_ACTION_RUN == 3) and
confirms it, then reads the four chosen-action bytes. If index 0 is not 3, it diffs a memory window
taken before and after the confirm and reports every address that flipped to 3.

    .venv/bin/python probe_chosen_action.py [state.ss ...]
"""
import os
import sys

import emu_boot as eb
import play
import rowe_symbols as S

BASE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = ["states/fixtures/live_33_7.ss", "states/fixtures/rapids.ss",
              "states/fixtures/lilycove.ss", "states/fixtures/pacifidlog.ss",
              "states/fixtures/route131_33_7.ss"]
B_ACTION_RUN = 3
WIN_BASE = 0x02024C00
WIN_LEN = 0x600
WALK = [eb.KEY_DOWN, eb.KEY_UP, eb.KEY_LEFT, eb.KEY_RIGHT]


def reach_single_wild(g, e) -> bool:
    if g.in_battle():
        return not (g.battle_type_flags() & play.BATTLE_TYPE_DOUBLE)
    for i in range(300):
        e.run(16, WALK[i % 4])
        if g.in_battle():
            return not (g.battle_type_flags() & play.BATTLE_TYPE_DOUBLE)
    return False


def run_action(p, g, e) -> int | None:
    """In the open single-wild battle, pick RUN for battler 0 and return chosen[0], or None if the
    menu never opened."""
    for _ in range(40):
        if g.choosing(0):
            break
        e.run(2, eb.KEY_A)
        e.run(8, 0)
    if not g.choosing(0):
        print(f"  action menu never opened, controller {g.controller_func(0):#x}", flush=True)
        return None
    for _ in range(20):                        # let "What will X do?" finish typing before input
        e.run(4, 0)

    def tap(key):
        e.run(6, key)
        e.run(12, 0)

    for _ in range(5):                         # RUN is the bottom-right cell (cursor 3); retry dropped taps
        c = g.action_cursor(0)
        if c == 3:
            break
        tap(eb.KEY_DOWN if c in (0, 1) else eb.KEY_RIGHT)
    print(f"  cursor before confirm {g.action_cursor(0)} (want 3 = RUN)", flush=True)
    before = e.read(WIN_BASE, WIN_LEN)
    e.run(4, eb.KEY_A)                         # confirm RUN
    e.run(2, 0)
    after = e.read(WIN_BASE, WIN_LEN)
    chosen = list(e.read(S.addr("gChosenActionByBattler"), 4))
    addr = S.addr("gChosenActionByBattler")
    print(f"  gChosenActionByBattler[0:4] at {addr:#x} = {chosen}", flush=True)
    if chosen[0] == B_ACTION_RUN:
        print("PASS: index 0 reads 3, the projected address is correct", flush=True)
    else:
        flipped = [WIN_BASE + i for i in range(WIN_LEN)
                   if after[i] == B_ACTION_RUN and before[i] != B_ACTION_RUN]
        print(f"FAIL: index 0 is {chosen[0]}, not 3", flush=True)
        print(f"  addresses that flipped to 3 on the confirm: {[hex(a) for a in flipped]}", flush=True)
    return chosen[0]


def main() -> None:
    states = sys.argv[1:] or CANDIDATES
    for st in states:
        pth = os.path.join(BASE, st) if not os.path.isabs(st) else st
        if not os.path.exists(pth):
            continue
        e = eb.Emu()
        e.load_state(open(pth, "rb").read())
        p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-chosen.json")
        g = p.g
        if not reach_single_wild(g, e):
            print(f"{os.path.basename(pth)}: no single wild encounter", flush=True)
            continue
        print(f"{os.path.basename(pth)}: single wild, flags {g.battle_type_flags():#x}", flush=True)
        run_action(p, g, e)
        return
    print("no candidate state produced a single wild battle", flush=True)
    sys.exit(1)


if __name__ == "__main__":
    main()
