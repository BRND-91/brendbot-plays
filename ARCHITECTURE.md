# How the bot is built

The agent plays Pokémon ROWE, a closed build of pokeemerald-expansion, with no human at
the controls. It boots the ROM in a headless mGBA build, reads the game's state out of RAM
and the ROM's static tables, decides what to do next, and drives real button presses one
frame at a time. It plays through the actual UI the way a person would. The only RAM writes
are fixture staging in tests, never gameplay shortcuts.

## Control flow

A single run is a supervisor around one executor process:

1. `run-grind.sh` loops for a wall-clock budget. Every iteration it re-plans, launches the
   executor, waits for it to exit (stall, crash, or timer), and relaunches from the saved
   state. play.py only rewrites that state at responsive moments, so a crash mid-menu
   resumes from the last clean frame.
2. `planner.py --apply` reads `states/status.json`, decides the next goal, and writes
   `states/goal.json`. The goal is re-decided before every launch, so one the executor
   reached (or a grind it demoted itself to) never outlives the run that wrote it.
3. `play.py --state states/route101.ss` runs the loop: read state, pick an action toward the
   goal, press it, repeat. Travel and explore route over the ROM's connection and warp
   tables plus the live reads the loop records.
4. `stream_sink.py` pushes the emulator's frames and audio into the HLS stream.

## The code, by layer

### Emulator boot and I/O
- `emu_boot.py` loads the locally built libmgba and its cffi binding and exposes the raw
  core: run frames, tap buttons, read and write EWRAM/IWRAM, save and load states, grab a
  PNG. Import it before `mgba` anywhere else. The ROM path is pinned here.
- `drive.py` steps the ROM from a save state, applies an input script
  (`A,w120,START,UP*3,hold:A:60`), and snapshots the result. The manual tool behind most
  probes.
- `stream_sink.py` scales each 240x160 frame 3x, encodes AAC audio, and emits rolling 2s
  HLS segments the public stream serves.

### Reading the game
- `rowe_symbols.py` is the memory map. ROWE ships no `.sym`, so each address carries how it
  was established: observed live, found as a Thumb literal in the ROM, or matched against
  the vendored decomp source.
- `rowe_state.py` gives typed reads over RAM (party, position, battle, bag, boxes) off those
  symbols.
- `rowe_rom.py` reads the static ROM tables: move table, type chart, species data, trainer
  rosters, map headers, connections, warps, metatile behaviors. Offsets were located by
  fingerprinting known vanilla entries and hold for this ROM build only.
- `rowe_map.py` reads the warps and connections of the current map through the live map
  header.

### Rendering art
- `icons.py` renders party-menu mon icons and type badges as the game draws them.
- `sprites.py` renders species front sprites, normal and shiny, as transparent PNGs.

### Navigation
- `nav.py` is the overworld pathfinder. It reads the current map plus its connection margin,
  blocks collision and NPC tiles, models water and ledges and elevation, BFSes to a target,
  and walks it one tile at a time, confirming each step against the save block so an
  interrupted walk is caught.
- `map_graph.py` is the world graph the travel loop routes over. Edges come from the ROM's
  full connection and warp tables (every map routable before it is walked) plus the live
  connection reads the executor records as it moves.

### Battle and catching
- `battle_engine.py` chooses moves and switches from live battler data and the ROM's move
  table, scoring type effectiveness, damage, and matchup.
- `catch.py` computes catch odds from the ROM species table following the game's own throw
  formula and holds the policy for what gets a ball.

### Decision loop
- `planner.py` is the objective ladder: lowest attacker under the level cap means grind, at
  cap means route to the unbeaten gym with the fewest hops, no gym reachable means explore
  toward the nearest one.
- `play.py` is the executor and the largest file: the per-frame loop, goal handling (grind,
  travel, explore), gym fights, menu handling, battle stepping, and the stall detector that
  ends a wedged run so the supervisor can relaunch.
- `routines.py` is the multi-map errands built on nav: heal runs to a Pokémon Center,
  Mart shopping, party refills from the PC box.

### Orchestration and config
- `run-grind.sh` is the supervisor loop described above.
- `gym_routes.json` holds solved press routes for the puzzle gyms.
- `swaps.json` holds admin-set party trade orders.

### Deploy gate and tooling
- `smoke.py` is the offline promotion gate: it boots frozen savestate fixtures and asserts
  the nav and battle behaviors a swap into the live streamer must not regress. A red check
  blocks the swap.
- `gen_nav_map.py` renders the map graph in this repo's `index.html`.
- `lavaridge_watch.py` and `make_fortree_entry.py` are single-purpose run helpers.

### Probes
One-off investigations, each reproducing a specific failure offline on a scratch copy of the
state so a fix can be grounded before it ships. They cover the Fortree rotating-gate puzzle
(`probe_fortree_*`), the Lavaridge hole maze (`probe_lavaridge_bfs`), the Sootopolis entry
hunt (`probe_sootopolis_entry`, `probe_dive_sootopolis`), surf dismounts, elevation, the
wild-battle switch stall, and map-specific pickups. They are kept rather than deleted so the
reasoning behind each fix stays readable.

### Tests
`test_*.py` are behavior pins, most run against the real ROM tables rather than mocks. Each
docstring names the live misplay it locks down: the action-grid wedge, the 0-PP move
confirm, surf-dismount refusals, the exp-lead switch, catch policy, the objective ladder.
`smoke.py` is the gate that must be green before a swap; the unit tests are the finer pins
under it.

## Building and running

The emulator, the ROM, and the runtime state are not in this repo. To run the agent:

1. Build mGBA 0.10.x as a shared library with the Python binding into `agent/mgba-build/`,
   and compile `agent/mgba-stubs.c` to `mgba-stubs.so` for the symbols an ffmpeg-less build
   omits.
2. Supply your own ROWE v2.1b ROM at the path pinned in `emu_boot.py`.
3. Create a venv and install the Python deps (cffi, Pillow, numpy).
4. Provide a starting save state under `agent/states/`.
5. `agent/run-grind.sh [hours]` supervises, or `python agent/play.py --state <state.ss>
   --no-stream` runs one executor without the HLS push.

The code reads one specific ROM build. The fingerprinted offsets in `rowe_rom.py` and the
addresses in `rowe_symbols.py` will not match a different build or a different hack.

## Legal

No ROM, BIOS, or save data ships here. ROWE is a fan project built on
pokeemerald-expansion; this is tooling that reads a copy you supply. mGBA is GPL and is
built from its own upstream source, not vendored here.
