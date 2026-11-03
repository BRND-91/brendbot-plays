"""Route reachability from (0,7) with the two stale Sootopolis gates cleared in memory.

Loads the live graph read-only, pops gates (0,7)->(24,5) and (24,5)->(0,51) from an
in-memory MapGraph (never saves), then routes from (0,7) to every land grass map and to
(0,8) under the live field-move set. Answers whether fixing the third crossing lands the
party somewhere routable or on a Route 126 dead end that is a graph problem instead."""
import json
import os

import map_graph
import rowe_rom

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = (0, 7)
EVER_GRANDE = (0, 8)
GATES = [(SRC, (24, 5)), ((24, 5), (0, 51)), ((24, 5), SRC), ((0, 51), (24, 5))]


def _graph() -> map_graph.MapGraph:
    g = map_graph.MapGraph(
        os.path.join(BASE, "states", "map_graph.json"),
        world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs())
    return g


if __name__ == "__main__":
    status = json.load(open(os.path.join(BASE, "states", "status.json")))
    moves = frozenset(status.get("field_moves", []))
    g = _graph()

    land = sorted(m for m in g.visited if m[0] == 0 and m[1] >= 16 and not rowe_rom.is_underwater(*m))
    under = sorted(m for m in g.visited if rowe_rom.is_underwater(*m))
    print("field_moves", sorted(moves))
    print("land grass maps", len(land), "underwater", under)

    def count(tag):
        hit = [m for m in land if g.route(SRC, m, field_moves=moves) is not None]
        eg = g.route(SRC, EVER_GRANDE, field_moves=moves)
        print(f"{tag}: land routable {len(hit)}/{len(land)}  route(0,7->0,8) {eg}")
        return hit

    count("gates in place")
    present = [k for k in GATES if k in g.gated]
    for k in present:
        g.gated.pop(k)
    print("cleared gates", present)
    count("gates cleared")

    for seq in [[(24, 5)], [(24, 5), (0, 51)], [(24, 5), (0, 51), (0, 41)]]:
        src = SRC
        ok = True
        for nxt in seq:
            if g.route(src, nxt, field_moves=moves) is None:
                ok = False
                break
            src = nxt
        print("escape leg", [SRC] + seq, "routable" if ok else f"breaks before {nxt}")
