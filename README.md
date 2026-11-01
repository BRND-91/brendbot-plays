# Brendbot Plays

The code and the map for an autoplayer that plays Pokémon ROWE with no human at the controls.
It boots the ROM in a headless mGBA build, reads game state out of RAM and the ROM's static
tables, decides a goal, and drives real button presses, streaming the result.

- `agent/` is everything the bot runs to play: the emulator boot layer, the RAM and ROM
  readers, the pathfinder, the battle and catch logic, the planner, the executor loop, and
  the test suite.
- `ARCHITECTURE.md` explains how it is built and what each script does.
- `index.html` is the interactive nav map (also hosted on Pages).

## The nav map

`index.html` renders the map-connection graph the autoplayer routes over. Nodes are maps
keyed `group,num`. Edges are the overworld connections and warps read straight from the ROM.
The layout is force-directed, so a connected mesh means the maps link and a separate cluster
means they do not.

- **Green** is the 337 maps reachable from the party's start, the set the planner can path
  over.
- **Red** is Sootopolis City, its interiors, gym 8, and the underwater maps beneath it: 19
  maps with no connection, warp, or dive edge leading into them from the reachable set.
- **Gold star** is a gym entrance. Seven sit inside the green mesh; the eighth sits in the
  red island.

The red cluster floating free of the green mesh is why the autoplayer never reaches the last
gym. The entrance is a story-flag script warp the connection, warp, and coord tables never
expose, so no graph route into it exists to follow.

## Running it

See `ARCHITECTURE.md`. The emulator, the ROM, and the runtime state are not in this repo;
build mGBA, supply your own ROWE ROM, and point the agent at a save state. No ROM, BIOS, or
save data ships here.
