"""Restart-bar check: on the parked (0,8) fixture (8 Hoenn badges, party at cap) the planner explores
the open Hoenn frontier, because the (0,5)->(24,23) Sevii-entry warp sits on a collision-blocked tile
and a prior run gated that edge at 8 badges. It travels onto the block once the crossing opens; see
test_planner for the routable travel branch."""
import os
import shutil

import emu_boot as eb
import map_graph
import planner
import play
import rowe_rom
import script_decode

BASE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(BASE, "states", "fixtures", "evergrande_0_8.ss")
SCRATCH = "/tmp/rowe-endgame-rec"


def main() -> None:
    os.makedirs(SCRATCH, exist_ok=True)
    live = os.path.join(SCRATCH, "live.ss")
    shutil.copy(FIXTURE, live)
    shutil.copy(os.path.join(BASE, "states", "map_graph.json"), os.path.join(SCRATCH, "map_graph.json"))

    e = eb.Emu()
    with open(live, "rb") as f:
        e.load_state(f.read())
    player = play.Player(e, play.NullStreamer(), ledger_path=os.path.join(SCRATCH, "caught.json"))
    player.state_path = live
    # build the graph the way play.py does now: the ROM connection/warp tables, plus the NPC-interaction
    # script layer gated by the ferry flags read live off this fixture (CD1/CE8/CE7 all set here).
    player.graph = map_graph.MapGraph(os.path.join(SCRATCH, "map_graph.json"),
                                      world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs(),
                                      script=script_decode.script_edges(), flags=player._graph_flags())
    status = player.write_status()
    goal, why = planner.recommend(status, player.graph)
    here = tuple(status["map"])
    moves = frozenset(status.get("field_moves", []))
    hop = player.graph.explore_hop(here, frozenset(), moves)
    print(f"status map {status['map']} badges {status['badges']} moves {sorted(moves)}", flush=True)
    print(f"recommend -> {goal} because {why}", flush=True)
    print(f"gate flags set {sorted(hex(f) for f in player.graph.flags)}; explore hop {hop}", flush=True)
    # the script layer is wired but the planner still targets the (0,5)->(24,23) anchor, which no edge
    # reaches, so an 8-badge save keeps exploring the Hoenn frontier until the executor can board the
    # ferry. The chosen hop is a normal border, never a script-only ferry edge the executor cannot yet
    # cross, so wiring the layer does not strand the explorer.
    assert goal["mode"] == "explore", f"badge-8 save explores while nothing targets a ferry dest, got {goal}"
    assert status["badges"] == 8, f"VAR_NUM_BADGES should read 8 on the 8-Hoenn-badge fixture, got {status['badges']}"
    script_only = bool(hop) and hop in player.graph._script_dests(here) \
        and hop not in player.graph.world.get(here, set()) and hop not in player.graph.adj.get(here, set())
    assert not script_only, f"explore hop {hop} is a script-only ferry edge with no executor to cross it"
    print("SEVII GATED-EXPLORE PASS", flush=True)


if __name__ == "__main__":
    main()
