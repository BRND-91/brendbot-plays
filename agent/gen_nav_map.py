"""Render the ROWE map-connection graph the autoplayer routes over as a standalone HTML page.
Nodes are maps keyed (group,num), edges are the overworld connections and warps from
rowe_rom.world_edges(). The party's reachable set (BFS from the start map) is drawn green and the
Sootopolis island (gym 8, unreachable in the map data) red, so the disconnection the planner cannot
route over is visible. One self-contained file, graph data inline, vis-network from a CDN."""
import collections
import json
import sys

import rowe_rom as R

START = (0, 25)
VIS = "https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"


# group 33 is the ROM's placeholder maps, whose warp words point at unrelated data and read as
# bogus edges bridging every component; excluded so a component walk reflects real map links
GARBAGE_GROUP = 33


def component(adj: dict, seeds: set, skip_group=None) -> set:
    seen = set(seeds)
    q = collections.deque(seeds)
    while q:
        u = q.popleft()
        for v in adj.get(u, ()):
            if v[0] == skip_group or v in seen:
                continue
            seen.add(v)
            q.append(v)
    return seen


def build() -> dict:
    directed = {k: set(v) for k, v in R.world_edges().items()}
    party = component(directed, {START}, skip_group=GARBAGE_GROUP)
    # the gym-8 island, directed reach from Sootopolis City with the placeholder group dropped, which
    # stays inside the city, its interiors, and the underwater cluster since no real edge leaves it
    soot = component(directed, {(0, 7)}, skip_group=GARBAGE_GROUP) - party
    gyms = set(R.gym_maps())
    shown = party | soot
    return {"directed": directed, "party": party, "soot": soot, "gyms": gyms, "shown": shown}


def page(g: dict) -> str:
    party, soot, gyms, shown = g["party"], g["soot"], g["gyms"], g["shown"]
    nodes, edges = [], []
    for (grp, num) in sorted(shown):
        if (grp, num) in soot:
            color = "#e0565b"
        elif (grp, num) in party:
            color = "#4caf72"
        else:
            color = "#6b7280"
        node = {"id": f"{grp},{num}", "label": f"{grp},{num}", "color": color}
        if (grp, num) in gyms:
            node["shape"] = "star"
            node["color"] = {"background": color, "border": "#f2c14e"}
            node["borderWidth"] = 3
            node["label"] = f"GYM {grp},{num}"
        nodes.append(node)
    seen_edge = set()
    for u, vs in g["directed"].items():
        if u not in shown:
            continue
        for v in vs:
            if v not in shown or (u, v) in seen_edge:
                continue
            seen_edge.add((u, v))
            edges.append({"from": f"{u[0]},{u[1]}", "to": f"{v[0]},{v[1]}"})
    data = {"nodes": nodes, "edges": edges}
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brendbot Plays — ROWE Nav Map</title>
<style>
  html, body {{ margin: 0; height: 100%; background: #11141a; color: #d6dae0;
    font: 14px/1.5 system-ui, sans-serif; }}
  #bar {{ padding: 10px 16px; border-bottom: 1px solid #232833; }}
  #bar h1 {{ margin: 0 0 4px; font-size: 16px; }}
  #bar span {{ color: #9aa3af; }}
  .key {{ display: inline-block; width: 11px; height: 11px; border-radius: 2px;
    vertical-align: middle; margin: 0 4px 0 12px; }}
  #net {{ height: calc(100% - 64px); }}
</style>
</head>
<body>
<div id="bar">
  <h1>Brendbot Plays — ROWE nav map</h1>
  <span>Every map the autoplayer routes over, as connection and warp edges.
  <span class="key" style="background:#4caf72"></span>reachable from the party ({len(party)} maps)
  <span class="key" style="background:#e0565b"></span>Sootopolis + gym 8 island ({len(soot)} maps), no edge into it
  <span class="key" style="background:#f2c14e"></span>gym</span>
</div>
<div id="net"></div>
<script src="{VIS}"></script>
<script>
const data = {json.dumps(data)};
const nodes = new vis.DataSet(data.nodes);
const edges = new vis.DataSet(data.edges.map(e => Object.assign(e, {{arrows: "to"}})));
new vis.Network(document.getElementById("net"), {{nodes, edges}}, {{
  nodes: {{size: 12, font: {{color: "#d6dae0", size: 11}}}},
  edges: {{color: {{color: "#3a4150", highlight: "#7c8699"}}, width: 0.5,
    arrows: {{to: {{scaleFactor: 0.4}}}}, smooth: false}},
  physics: {{barnesHut: {{gravitationalConstant: -8000, springLength: 90}},
    stabilization: {{iterations: 400}}}},
  interaction: {{hover: true, tooltipDelay: 120}}
}});
</script>
</body>
</html>
"""


def main() -> None:
    out = sys.argv[1]
    g = build()
    html = page(g)
    with open(out, "w") as f:
        f.write(html)
    print(f"wrote {out}: {len(g['shown'])} nodes "
          f"(party {len(g['party'])}, sootopolis {len(g['soot'])}), {len(html)} bytes")


if __name__ == "__main__":
    main()
