"""Drive the Icefall Cave chain through the live crossing primitive on a /tmp copy: lobby of
(1,27) -> thin-ice drop to (1,28) -> ladder up into the sailor's pocket of (1,27) -> ferry to Five
Island (1,32). Each leg goes through Player._cross_to with the onward hop the route would pass, so
the landing ranks are the ones the run uses. Reads only.

    probe_icefall_chain.py --state /tmp/rowe_127_probe.ss
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb  # noqa: E402
import play  # noqa: E402

LEGS = [((1, 27), (1, 28), (1, 27)), ((1, 28), (1, 27), (1, 32)), ((1, 27), (1, 32), (2, 11))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    a = ap.parse_args()
    e = eb.Emu()
    e.load_state(open(a.state, "rb").read())
    p = play.Player(e, play.NullStreamer(), ledger_path="/tmp/rowe_icefall_probe.json")
    moves = p.field_moves()
    for hop in ((1, 26), (1, 27)):
        print(f"via {hop}: {p.errands.take_warp(hop, surf=True, tools=moves)} at {p.g.position()}", flush=True)
    for here, hop, nxt in LEGS:
        if tuple(p.g.position()[2:]) != here:
            print(f"not on {here}, at {p.g.position()}; stopping", flush=True)
            return
        status, result = p._cross_to(here, hop, nxt)
        print(f"leg {here} -> {hop} (then {nxt}): {status} ({result}) at {p.g.position()}", flush=True)


if __name__ == "__main__":
    main()
