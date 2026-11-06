# Brendbot Plays

The code and the map for an autoplayer that plays Pokémon ROWE with no human at the controls.
It boots the ROM in a headless mGBA build, reads game state out of RAM and the ROM's static
tables, decides a goal, and drives real button presses through the game's own menus, streaming
the result live at live.brenergy.net.

- `agent/` is everything the bot runs to play: the emulator boot layer, the RAM and ROM
  readers, the pathfinders, the battle and catch logic, the planner, the executor loop, the
  errands, and the test suite.
- `ARCHITECTURE.md` is the full reference: control flow, every module and its key symbols, a
  feature locator, the routing model, and the current build state.
- `agent/HANDOFF.md` is the engineering log, one entry per fix with symptom, cause, change and
  verification. `agent/PROGRESSION.md` is the run log.
- `games/rowe/rowe_rom.db` is the ROM's mechanics and map tables as SQLite, built by
  `agent/build_rom_db.py`.
- `index.html` is the interactive nav map, also hosted on Pages.

## How a run works

A supervisor (`agent/run-grind.sh`) relaunches one executor (`agent/play.py`) from a save state
for a wall-clock budget. Before each launch `agent/planner.py` reads the executor's published
status and writes the next goal: grind a grass map to the badge level cap, travel to a map,
explore toward an unvisited one, fight a gym, run the League, or fight a post-game boss. The
executor walks the overworld tile by tile, crosses maps by border, warp, dive, or a talked
ferry, fights with moves ranked off the ROM's own damage tables, catches to fill the party,
heals and restocks in service towns, builds the team from the PC box against the next leader,
and solves the puzzle gyms from recorded routes. A goal reached is re-planned in-process so the
stream never drops.

## The nav map

`index.html` renders the map-connection graph the autoplayer routes over. Nodes are maps keyed
`group,num`. Edges are the overworld connections, warps, and dive edges read straight from the
ROM. The layout is force-directed, so a connected mesh means the maps link and a separate
cluster means they do not.

- **Green** is the 375 maps reachable from the party's start, the set the planner can path over.
- **Red** is any map with no connection, warp, or dive edge into it from that set. The graph
  currently has none.
- **Gold star** is a Hoenn gym entrance. All eight sit inside the green mesh.

Sootopolis and gym 8 used to float free of the mesh as a 19-map red island, because the entrance
is not a connection or a plain warp. It is a `setdivewarp` buried in the map's ON_DIVE_WARP
script that fires when the player surfaces in the underwater Sootopolis map. `world_edges()`
parses that script table and emits the dive edge, so the planner has a route in.

The Sevii Islands, where ROWE places the eight Johto leaders, are reached over a second layer
the map does not draw: the Seagallop ferry, a scripted crossing decoded from the dock sailors'
event scripts and driven through their dialogue menus.

## Status

16 badges, Champion. The run cleared the 8 Hoenn gyms, the 8 Johto leaders on the Sevii
Islands, Victory Road, the Elite Four, and Wallace, and the Hall of Fame save restored through
the title screen's Continue. The planner's remaining goals are the two post-game bosses, Steven
in Meteor Falls and Red in Shoal Cave; after both it emits `done` and the supervisor stops.
Per-fix findings are in `agent/HANDOFF.md`, the run log in `agent/PROGRESSION.md`.

## Running it

See `ARCHITECTURE.md`. The emulator, the ROM, and the runtime state are not in this repo; build
mGBA, supply your own ROWE v2.1b ROM, and point the agent at a save state. No ROM, BIOS, or save
data ships here.
