# Brendbot Plays — ROWE nav map

`index.html` renders the map-connection graph the brendbot autoplayer routes over in Pokémon ROWE.

Nodes are maps keyed `group,num`. Edges are the overworld connections and warps read straight from
the ROM. The layout is force-directed, so a connected mesh means the maps link and a separate cluster
means they do not.

- **Green** — the 337 maps reachable from the party's start, the set the planner can path over.
- **Red** — Sootopolis City, its interiors, gym 8, and the underwater maps beneath it. 19 maps with
  no connection, warp, or dive edge leading into them from the reachable set.
- **Gold star** — a gym entrance. Seven sit inside the green mesh; the eighth sits in the red island.

The red cluster floating free of the green mesh is why the autoplayer never reaches the last gym. The
entrance is a story-flag script warp the connection, warp, and coord tables never expose, so no graph
route into it exists to follow.

Open `index.html` locally or view the hosted page.
