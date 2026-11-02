# Brendbot Plays

The code and the map for an autoplayer that plays Pokémon ROWE with no human at the controls.
It boots the ROM in a headless mGBA build, reads game state out of RAM and the ROM's static
tables, decides a goal, and drives real button presses, streaming the result live at
live.brenergy.net.

- `agent/` is everything the bot runs to play: the emulator boot layer, the RAM and ROM
  readers, the pathfinder, the battle and catch logic, the planner, the executor loop, the
  errands, and the test suite.
- `ARCHITECTURE.md` is the full reference: control flow, every module and its key symbols, a
  feature locator, the routing model, and the current build state.
- `index.html` is the interactive nav map, also hosted on Pages.

## The nav map

`index.html` renders the map-connection graph the autoplayer routes over. Nodes are maps keyed
`group,num`. Edges are the overworld connections, warps, and dive edges read straight from the
ROM. The layout is force-directed, so a connected mesh means the maps link and a separate
cluster means they do not.

- **Green** is the 375 maps reachable from the party's start, the set the planner can path over.
- **Red** is any map with no connection, warp, or dive edge into it from that set. The graph
  currently has none.
- **Gold star** is a gym entrance. All eight sit inside the green mesh.

Sootopolis and gym 8 used to float free of the mesh as a 19-map red island, because the entrance
is not a connection or a plain warp. It is a `setdivewarp` buried in the map's ON_DIVE_WARP
script that fires when the player surfaces in the underwater Sootopolis map. `world_edges()` now
parses that script table and emits the dive edge, so the planner has a route in. A surface dive
reaches the underwater route, a warp reaches underwater Sootopolis, and surfacing there runs the
`setdivewarp` that lands the party in the city.

## Status

Eight-badge Hoenn run, currently at 7 badges with the Sootopolis dive/warp/emerge crossing
firing in play. At all eight badges the planner routes to Ever Grande. Progress and per-run
findings are logged in `agent/PROGRESSION.md`.

## Running it

See `ARCHITECTURE.md`. The emulator, the ROM, and the runtime state are not in this repo; build
mGBA, supply your own ROWE ROM, and point the agent at a save state. No ROM, BIOS, or save data
ships here.
