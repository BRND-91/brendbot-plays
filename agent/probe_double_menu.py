"""Snapshot the Sootopolis lower-floor double-battle action menu and classify its controller funcs.

    .venv/bin/python probe_double_menu.py

Loads the saved battle start (probe_wedge_repro's /tmp/wedge_start.ss, regenerated from the fixture if
absent), saves a PNG of the opening frame, then runs frames with no input and snapshots a PNG the first
time each distinct controller_func(0..3) value appears, tagging it with the known func set it belongs to
or UNKNOWN. The battler-0 value seen at the wedge is 0x93898e4; the PNG for it shows whether battler 0's
action menu (FIGHT/BAG/POKEMON/RUN) is drawn, the gate on adding it to PLAYER_CHOOSE_ACTION_FUNCS.
"""
import os
import sys

import emu_boot as eb
import play
import probe_wedge_repro as W
import rowe_symbols as S

KNOWN = {
    "PLAYER_CHOOSE_ACTION_FUNCS": S.PLAYER_CHOOSE_ACTION_FUNCS,
    "INTRO_IDLE_FUNCS": play.INTRO_IDLE_FUNCS,
}


def classify(f: int) -> list:
    hits = [name for name, s in KNOWN.items() if f in s]
    return hits or ["UNKNOWN"]


def main():
    if not os.path.exists(W.START):
        if not W.reach_battle():
            print("no battle reached from fixture", flush=True)
            sys.exit(2)
    e = eb.Emu()
    e.load_state(open(W.START, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe-dm.json")
    g = p.g
    print(f"start in_battle {g.in_battle()} flags {g.battle_type_flags():#x} pos {g.position()} "
          f"chooser {g.chooser()}", flush=True)
    e.save_png("/tmp/double_menu_start.png")
    print("PNG /tmp/double_menu_start.png", flush=True)
    seen = {}
    for i in range(400):
        funcs = [g.controller_func(j) for j in range(4)]
        for j, f in enumerate(funcs):
            if f not in seen:
                seen[f] = (i, j)
                png = f"/tmp/func_{f:#x}_b{j}.png"
                e.save_png(png)
                print(f"NEW func {f:#x} battler {j} poll {i} chooser {g.chooser()} "
                      f"-> {classify(f)} PNG {png}", flush=True)
        if g.choosing(0) or g.choosing(2):
            print(f"choosing() true at poll {i} funcs {[hex(x) for x in funcs]}", flush=True)
            break
        e.run(5, 0)
    print("funcs seen:", {hex(k): v for k, v in seen.items()}, flush=True)
    b0 = g.controller_func(0)
    e.save_png("/tmp/double_menu_settled.png")
    print(f"settled battler0 func {b0:#x} in PLAYER_CHOOSE_ACTION_FUNCS "
          f"{b0 in S.PLAYER_CHOOSE_ACTION_FUNCS} PNG /tmp/double_menu_settled.png", flush=True)


if __name__ == "__main__":
    main()
