"""Flagged-copy endgame drive: Victory Road traversal and the Elite Four ladder on a /tmp copy of
evergrande_0_8.ss with the League guard flag (0x0dfa) set. Never touches the live save. Walks the
ENDGAME_CHAIN map by map, freezes a state under OUTDIR at each Victory Road floor and each E4 room
entrance, logs party PP around each leg, and writes a heartbeat line every leg so a detached run is
observable. Stops with the reached map and the stall reason on the first leg that does not arrive.

    drive_endgame.py [--leg-seconds 600] [--outdir /tmp/rowe-endgame]

Channel rule "ROWE live save": the copy and all frozen states live under /tmp; set_league_flag
refuses a live target in code.
"""
import argparse
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb  # noqa: E402
import map_graph  # noqa: E402
import planner  # noqa: E402
import play  # noqa: E402
import rowe_rom  # noqa: E402
import set_league_flag as slf  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "evergrande_0_8.ss")
GRAPH = os.path.join(BASE, "states", "map_graph.json")
FREEZE = {(24, 43): "vr1f", (24, 44): "vrb1f", (24, 45): "vrb2f",
          (16, 10): "league1f", (16, 0): "sidney", (16, 1): "phoebe",
          (16, 2): "glacia", (16, 3): "drake", (16, 4): "wallace", (16, 11): "halloffame"}


def hb(outdir: str, msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    with open(os.path.join(outdir, "heartbeat.log"), "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def party_pp(status: dict) -> list:
    return [sum(mv["pp"] for mv in m["moves"]) for m in status["party"]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leg-seconds", type=float, default=600.0)
    ap.add_argument("--outdir", default="/tmp/rowe-endgame")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    live = os.path.join(a.outdir, "drive.ss")
    shutil.copy(FIXTURE, live)
    slf.set_flag(live)  # clears the (18,42) guard; refuses a live target
    shutil.copy(GRAPH, os.path.join(a.outdir, "map_graph.json"))

    e = eb.Emu()
    with open(live, "rb") as f:
        e.load_state(f.read())
    hb(a.outdir, f"booted flagged copy, guard flag {slf.GUARD_FLAG:#06x} set={slf.read_flag(live)} (want True)")

    player = play.Player(e, play.NullStreamer(), ledger_path=os.path.join(a.outdir, "caught.json"))
    player.state_path = live
    player.graph = map_graph.MapGraph(os.path.join(a.outdir, "map_graph.json"),
                                      world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
    # the guard flag set above opens the (0,8) League doors, so a gate the graph learned on an
    # endgame-chain edge while the guard still blocked it is stale on this copy; without dropping it
    # route() returns None under the party's field moves and travel walks off Ever Grande into explore.
    chain = set(planner.ENDGAME_CHAIN)
    player.graph.gated = {edge: mv for edge, mv in player.graph.gated.items() if edge[1] not in chain}
    player.graph.save()
    goal_path = os.path.join(a.outdir, "goal.json")

    for dest in planner.ENDGAME_CHAIN:
        here = player.g.position()[2:]
        if here == dest:
            player.graph.visited.add(dest)
            continue
        with open(goal_path, "w") as f:
            json.dump({"mode": "travel", "to": list(dest)}, f)
        before = party_pp(player.write_status())
        hb(a.outdir, f"leg -> {list(dest)} ({planner.ENDGAME_ROOMS.get(dest, 'VictoryRoad')}) from {list(here)}, pp {before}")
        try:
            player.loop(a.leg_seconds)
        except play.GoalExit as g:
            reached = player.g.position()[2:]
            after = party_pp(player.write_status())
            hb(a.outdir, f"  GoalExit {g}: at {list(reached)}, pp {after}")
            if reached != dest:
                hb(a.outdir, f"STALL: wanted {list(dest)}, stuck at {list(reached)}; drive stops")
                return
        else:
            reached = player.g.position()[2:]
            hb(a.outdir, f"TIMER {a.leg_seconds}s: wanted {list(dest)}, at {list(reached)}; drive stops")
            if reached != dest:
                return
        player.graph.visited.add(dest)
        if dest in FREEZE:
            frozen = os.path.join(a.outdir, f"{FREEZE[dest]}.ss")
            with open(frozen, "wb") as f:
                f.write(e.save_state())
            hb(a.outdir, f"  froze {frozen}")

    hb(a.outdir, "DRIVE COMPLETE: reached Hall of Fame")


if __name__ == "__main__":
    main()
