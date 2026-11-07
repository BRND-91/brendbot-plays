# How the bot is built

The agent plays Pokémon ROWE v2.1b, a closed build of pokeemerald-expansion, with no human at
the controls. It boots the ROM in a headless mGBA build, reads the game's state out of RAM and the
ROM's static tables, decides what to do next, and drives real button presses one frame at a time.
It plays through the actual UI the way a person would. The only RAM writes are fixture staging in
tests and dev tools, never gameplay shortcuts.

This file is the map: which module and which symbol holds a thing, so a lookup is a targeted
read or one `grep -n "def <name>"`, never a cold sweep of the 4000-line `play.py` and 30-odd
modules. When this file and the code disagree, the code wins and this file is stale.

## What it has played

The run went 8 Hoenn gyms, then the ferry to the Sevii Islands for the 8 Johto leaders ROWE
places there (16 badges, the count the League guard reads), then Victory Road, the Elite Four,
and the Champion. The Hall of Fame saves the game to a flash file and the title screen's Continue
restores it. Two post-game bosses remain in the ladder, Steven in Meteor Falls and Red in Shoal
Cave, each a team of six at L100. Steven has three wins over the current six, tallied in
`states/boss_losses.json`, and the planner answers a loss by pricing the retry and grinding for
a catch that out-scores the weakest member (the ladder below). After both bosses the planner
emits `done` and the supervisor stops.

## Control flow

A single run is a supervisor around one executor process, both reading and rewriting a handful
of files under `agent/states/`.

1. `run-grind.sh [hours] [speed]` loops for a wall-clock budget. Each iteration runs the planner,
   launches the executor, waits for it to exit, and relaunches from the saved state. All runs
   append to `states/grind.log` (rotated at 50M, one kept). It traps TERM/INT to stop. A live
   watchdog samples the map graph and badge count once a minute and TERMs a non-grind run that
   shows no new map and no new badge for 15 samples, so a phantom route cannot bounce for hours.
   It stops on a `done*` exit reason, on 3 identical exits at the same map and tile, on 3
   spin-breaks in a row, or on 5 crashes inside 600s. On the live box it runs as a transient
   systemd unit behind `flock states/grind.lock`, so two supervisors can never write the same
   save.
2. `planner.py --apply` reads `states/status.json`, decides the next goal, and writes
   `states/goal.json` when it differs. The goal is re-decided before every launch, so a goal the
   executor reached never outlives the run that wrote it.
3. `play.py --state states/live.ss [--minutes N] [--speed N] [--no-stream]` runs the loop: read
   state, pick an action toward the goal, press it, repeat. It rewrites `status.json` on every
   party change and at least every 15s, and snapshots `live.ss` only at responsive moments after
   a battle, so a crash mid-menu resumes from the last clean frame. A goal reached raises
   `GoalExit`; `drive()` catches it and `Player.replan` re-decides the goal in-process, so the
   emulator and the stream run on through a goal change. Only an `unsupported*`, `done*`, or
   `no_grass_idle` exit, or a burst of replans, hands the exit to the supervisor.
4. `stream_sink.py` pushes the emulator's frames and audio into the HLS stream Caddy serves at
   live.brenergy.net. `--speed` sets the frame decimation; the site's admin speed button writes
   `states/speed.ctl`, which `Player._apply_speed_ctl` picks up by mtime and passes to
   `FrameStreamer.set_speed` with no encoder restart.

The state files under `states/`:
- `live.ss` is the save the supervisor relaunches from and the executor rewrites in place.
  `rowe_live.guard_write` raises on any write to it from a process whose `--state` is not this
  path, so a probe or test cannot overwrite it.
- `live.ss.sav` is the 1M flash save beside the state. The Hall of Fame writes the game save
  there and Continue loads it; `play.main` creates it blank at 0xFF when missing.
- `live.ss.caught.json` is the catch ledger (`catch.Ledger`).
- `live/` is the snapshot ring, the last 20 `YYYYmmddTHHMM.ss` copies (`rowe_live.archive`).
  `find_best_state.py` ranks every `.ss` on the box by badges when a restore goes wrong.
- `status.json` is the executor's published state: map, tile, party, boxes, field_moves, balls,
  money, badges, `badge_flags` (Hoenn), `johto_flags`, `champion`, `elite_flags`, `boss_flags`,
  `ferry_flags`, `gate_flags`, `tickets`, `hidden_givers`, dex owned and seen, goal, exit_reason,
  pid. The planner and any status claim read this, never the logs alone.
- `goal.json` is the planner's decision for the next launch.
- `map_graph.json` is the learned world graph (walked borders, visited maps, gated edges).
- `grind_blocked.json` is the set of grass maps the executor gave up reaching.
- `gym_closed.json` is gyms recorded unclearable, with the condition that reopens each;
  `gym_losses.json` counts leader losses.
- `boss_losses.json` is the boss attempt ledger: whiteouts per boss under the party signature
  that lost them, each attempt's whiteout and rematch time. `planner.boss_losses` prices a
  retry off the median span, and a changed party restarts the count at zero.
- `pace.json` keeps the exp and hop-time samples across relaunches, so a fresh run prices a
  grind against a boss retry with measured numbers.
- `stuck_hits.json` counts repeated crossing failures per edge toward a gate, keyed with
  `EXECUTOR_CAP_VERSION` so a capability change reopens old gates.
- `egg_declined.json`, `party_full.json`, `swap_order.json` are team-management ledgers.
- `speed.ctl` is the stream speed the site's control endpoint last wrote.
- `fixtures/` are frozen savestates the tests and probes replay (137 files at this writing).

## Repo layout

- `agent/` is everything the bot runs to play: the emulator boot layer, the RAM and ROM readers,
  the pathfinders, the battle and catch logic, the planner, the executor loop, the errands, the
  tests, and the probes. `agent/HANDOFF.md` is the per-fix engineering log (symptom, cause,
  change, verification) and `agent/PROGRESSION.md` the run log.
- `ARCHITECTURE.md` (this file) explains how it is built and where each feature lives.
- `README.md` is the front page and the nav-map explanation.
- `index.html` is the interactive nav map, generated by `agent/gen_nav_map.py`, also hosted on
  Pages.
- `games/rowe/rowe_rom.db` is the ROM snapshot of record, built by `agent/build_rom_db.py`.

## The code, by layer

### Emulator boot and I/O
- `emu_boot.py` loads the locally built libmgba and its cffi binding and exposes `class Emu`
  (`run`, `tap`, `read`, `u32`, `write`, `ewram`, `iwram`, `save_state`, `load_state`,
  `save_png`), taking a `save=` path for the flash file. Import it before `mgba` anywhere else.
  The ROM path is pinned here.
- `drive.py` steps the ROM from a save state, applies an input script
  (`A,w120,START,UP*3,hold:A:60`), and snapshots the result. The manual tool behind most probes.
  `drive_endgame.py`, `drive_to_island.py`, `drive_ti_probe.py`, `drive_dock_fixture.py` are
  scripted drives over `/tmp` copies that freeze fixtures along a leg.
- `stream_sink.py` (`class FrameStreamer`) scales each 240x160 frame 3x, encodes AAC audio, and
  emits rolling 2s HLS segments with a 60s playlist window. It respawns the encoder on a stall,
  injects silence to hold the clock, and logs frame gaps (`GAPLOG`). `set_speed` moves the
  decimation ratio per push. `play.py`'s `NullStreamer` is the `--no-stream` stand-in.

### Reading the game
- `rowe_symbols.py` is the RAM address map. ROWE ships no `.sym`, so each address carries how it
  was established: observed live, found as a Thumb literal in the ROM, or projected from the
  vendored decomp layout. Flags of record: the badge flags, `FLAG_SYS_GAME_CLEAR`,
  `FLAG_DEFEATED_ELITE_4`, `FLAG_DEFEATED_METEOR_FALLS_STEVEN`, `FLAG_DEFEATED_RED`.
- `rowe_state.py` gives typed RAM reads. `class GameState` is the reader the executor holds:
  `position`, `party`, `box`/`boxes`, `in_battle`, `badges` (`VAR_NUM_BADGES`, 0 to 16),
  `flag`, `var`, `money`, `pokedex`, `battle_points`, `skill_points`, `iv_boosts`, `bag_pocket`
  and the pocket helpers (`poke_balls`, `medicine`, `tms`, `key_items`, `items`, `sellables`,
  `fossils`, `repels`, `shop_items`), plus the
  battle-screen reads the menu logic turns on (`callback2`, `controller_func`, `chooser`,
  `choosing`, `comm`, `in_move_list`, `in_selection_script`, `move_cursor`, `action_cursor`,
  `party_menu_slot`, `battlers`, `battle_type_flags`, `battle_outcome`, `disabled_move`,
  `script_instr`, `offered_move`, `learning_mon`). `class PartyMon`/`BattleMon`/`BoxMon` are the
  typed rows.
- `rowe_rom.py` reads the static ROM tables, offsets located by fingerprinting known vanilla
  entries, valid for this build only; `self_check` runs at every executor start. Mechanics:
  `move`, `species`, `stats_at`, `level_from_exp`, `type_chart`, `effectiveness`, `evolutions`,
  `level_up_learnset`, `egg_moves`, `tm_learnset`, `tm_move`, `ability_of`, `nature_modifier`,
  `species_at_level`, `item_name`, `item_price`, `item_sets`. Maps: `map_header`,
  `map_connections`, `map_warps`, `map_warp_links`, `map_cells`, `metatile_behavior`,
  `map_objects`, `map_object_scripts`, `map_music`, `map_section`, `is_underwater`,
  `is_underground`, `is_indoor`, `is_center`, `is_mart`, `wild_land_levels`, `wild_encounters`,
  `field_items` (item balls), `hidden_items` (the hidden-item BgEvents and their flags),
  `clerk_marts` (a shop clerk's gate flags and item lists off its script), `gym_maps`. Trainers:
  `trainer_pool`, `leader_team`, `leader_build`, `boss_build`, `sevii_leader_pools`,
  `sevii_leader_locations`, `all_trainer_tiles`. Progression: `badge_flags` (badge index, flag,
  region, leader) and
  `badge_gate_maps`. The routing graph: `world_edges` (the full static graph), `passthroughs`,
  and `dive_script_edges`, which decodes each map's dive-warp script for the `setdivewarp`
  targets the connection and warp tables never carry.
- `script_decode.py` decodes event-script bytecode off the ROM with an opcode table generated
  from the vendored decomp's `event.inc` macros. It yields the script-warp layer the ferry runs
  on: `script_edges` (talked crossings, the Seagallop sailors and scripted doors), `gate_flags`,
  `talk_object`, `seagallop_docks`, `menu_sequence` (the cursor path to an island row),
  `ISLAND_TICKETS`, `giver_sailor_tile`, `passable_island_arm`. Also a CLI
  (`script_decode.py 0x83078ed`) for reading a script by address.
- `rowe_map.py` reads the current map's live header: warps, connections, coord events, item balls.
- `rowe_live.py` names the live save and its ring in one place: `LIVE_SAVE`, `RING_DIR`,
  `LIVE_RING`, `is_live_target`, `guard_write`, `archive`.

### Rendering art
- `icons.py` renders party-menu mon icons and type badges as the game draws them.
- `sprites.py` renders species front sprites, normal and shiny, as transparent PNGs.
- `dexgen/gen_species.py` emits `species.json` for the site's Pokédex from the ROM's species,
  evolution, wild and name tables.

### Navigation
- `nav.py` is the overworld pathfinder. `class Grid` reads the current map plus its connection
  margin and answers passability: `passable`, `reachable`, `region`, `path` (BFS), plus the water,
  ledge, elevation, waterfall, rock-climb and ride rules in `_step_refused`/`_ride`/`_ledge_hop`/
  `_carry`, the Strength boulder planner, and the dive and surface sets `dive_tiles`/
  `emerge_tiles`. On an underwater map it treats deep water as walkable floor. `class Navigator`
  walks a path one tile at a time (`walk_to`, `step`, `_mount`, `_advance`, `_clear_obstacle`,
  `_climb`), confirming each step against the save block so an interrupted walk is caught.
- `map_graph.py` is the learned world graph the travel loop routes over. `class MapGraph` holds
  `adj` (walked borders, persisted), `visited`, `gated` (edges blocked under a specific field-move
  set), `world` (the static `rowe_rom.world_edges`), `passthrough`, the script layer
  (`set_script`, the ferry arms under the held tickets), and `flags` (gate flags set right now).
  `neighbors` unions the layers. `route`/`_bfs` returns the first hop toward a destination and
  skips any edge whose stored gate is shut under the live moves (`_gate_shut`), so gaining a move
  reopens the edge. `block` records a gate; `observe` records a walked border;
  `explore_hop`/`frontier_exhausted`/`gated_frontier` drive exploration.
- `region_route.py` routes at the level of (map, landing tile) over the ROM layouts, for maps
  whose walkable area splits into regions the map graph cannot tell apart (Ever Grande's shore
  and plateau, Victory Road 1F's two halves). `route` threads the warps and borders whose trigger
  tile the landing reaches and names the first portal to take; `portals`, `reach`, `threads`,
  `open_hops` support it. Grids and reach sets are memoised per process.
- `gym_maze.py` searches a gym split across maps by warp pads (Clair's `(2,15)` over its annex)
  as a graph of walkable pockets: `warp_chain` returns the pads to step on in order.

### Battle and catching
- `battle_engine.py` chooses moves and switches from live battler data and the ROM move table.
  `rank_moves` and `choose_move` score effectiveness and damage (`expected_damage`,
  `effectiveness`, `immune`), skipping two-turn, recharge and situational effects
  (`TWO_TURN_EFFECTS`, `NO_PICK_EFFECTS`, `LAST_RESORT_EFFECT`); `first_usable_slot` is the PP'd
  fallback; `best_switch`/`strongest_bench`/`outmatched`/`edge` handle switching;
  `replacement_slot` picks the move a learn prompt replaces; `weakening_move` picks the catch
  chip, excluding charging effects (`CHARGING_EFFECTS`).
- `catch.py` computes catch odds following the game's throw formula (`catch_chance`) and holds
  the policy for what gets a ball: `helper_slot`, `status_move_slot`, and `class Ledger`
  (`wants`, `record`).

### Decision loop
- `planner.py` is the objective ladder. `recommend` picks, in priority:
  1. 8 Hoenn badges in and a Johto leader unbeaten means the Sevii leg (`sevii_goal`): route to
     the lowest-indexed unbeaten gym from the badge table over the ferry layer, else explore
     toward the nearest unvisited map so the graph grows, never grind.
  2. A fossil in the bag with Rustboro on the known map means the Devon revive errand
     (`FOSSIL_FAIL_CAP` short tries before it is dropped for the run).
  3. A party short of six or a lowest attacker under the badge level cap (`CAPS`) means grind
     on `grind_map` (visited grass ranked by hops to the anchor, then by ROM wild level). Past
     the game clear the cap is the party's own top level.
  4. All 16 gyms down means travel along `ENDGAME_CHAIN` (Victory Road, League 1F, the halls
     and the Elite Four rooms in order, the Hall of Fame) to the first map not yet reached that
     has a route; no route from inside the League holds the travel goal for the door; no route
     from outside explores toward it.
  5. Champion set means the first unbeaten `POSTGAME` boss, Steven then Red, off
     `status["boss_flags"]`. Ahead of the fight, a species the party can reach and catch whose
     summed damage edge against the boss's six beats the weakest member's by `CATCH_MARGIN`
     sets a coverage grind on its grass (`catch_target`), ended by the catch; a lowest attacker
     under the party's top level grinds; otherwise travel to the boss room, or explore toward
     it with no route. Each loss is priced from `boss_losses.json` (`boss_losses`). Both beaten
     means `{"mode": "done"}`.
  6. Otherwise the nearest unbeaten Hoenn gym reachable over the graph, or explore toward the
     nearest when none is.
  Supporting: `unbeaten_gyms`, `nearest_gym`, `still_closed`/`closed_gyms`, `hops_from`,
  `blocked_grinds`, `planning_anchor`, `leader_stand`, `league_flags`, `catch_target`,
  `boss_losses`, `party_signature`, `build_graph` (the one
  factory both the planner and the executor use, with `script_layer` for the ferry arms under
  the held tickets and the sailors the ROM has removed). Tables: `GYM_BADGE`, `JOHTO_GYM`,
  `GYM_STAND`, `ENDGAME_ROOMS`, `VICTORY_ROAD`, `ENDGAME_CHAIN`, `POSTGAME`, `SEVII_ENTRY`,
  `SEVII_LEGS`.
- `play.py` is the executor and the largest file. `class Player` holds the whole run:
  - Frame I/O and waits: `run`, `tap`, `loop`, `wait_until`, `press_until`; `drive()` and
    `main()` wrap it with the flash save, the streamer and the exit handling.
  - Overworld dispatch: `overworld_step` is the per-tick router. In order it runs the lead swap,
    the heal and restock errands, the Department Store TM trip, `scene_step`, `league_step`,
    `boss_step`, `collect_step` (item balls and hidden items on the current map), `fossil_step`
    on an errand goal, then the goal handler: `travel_toward`, `explore_step`, `gym_step`, or
    the grind walk, with `maybe_repel` ahead of a travel or explore step. `demote_to_grind` and
    `grind_wild_top` cover the fallbacks.
  - Endgame: `league_step` heals and buys the League list at the lobby (`league_shopping_list`,
    `LEAGUE_BUYS`), challenges each Elite Four trainer whose flag is down (`ELITE_FLAGS`,
    `ELITE_STAND`), takes the far door once a room is won, and presses A through the Hall of
    Fame ceremony until the game-clear bit sets. `cutscene_step` presses A through the Hall of
    Fame screen, the credits, the title screen and Continue, and raises `GoalExit` when the field
    comes back so the post-game goal is planned from the new position. `scene_step` advances
    Birch's lab scripts after the clear (`BIRCH_LAB`, `VAR_JOHTO_STARTER`). `boss_step` challenges
    a `BOSSES` room whose defeat flag is down. `_league_leg` turns off Center and Mart treks and
    the catch plan while the party fights on the bag.
  - Map crossing: `_cross_to` fires a connection, warp, dive, emerge, or talked script warp for
    the next graph hop (`field_moves`, `_landing_rank`, `_after_cross`, `region`, `service_town`,
    `_region_route`); `_persist_blocked`/`_border_open`/`_stuck_key` record a gate when a crossing
    cannot complete; `_observe_here` and `_landing_exits` enter a stood-on map's exits into the
    graph; `_sync_tickets` and `_gone_givers` rebuild the ferry layer when a ticket lands or a
    sailor despawns; `_dive_frontier`, `_reachable_grass_map`, `_grind_no_grass` handle the
    underwater frontier and the grassless hold; `_leave_dynamic_interior` walks out of a dynamic
    return door.
  - Battle: `battle_step` is the single-step fight handler; `_comm_action` and `comm_wait`
    single-source the selection-script box dispatch (B at `comm 6`, steer at `comm 3`);
    `_advance_intro`, `_reach_fight`, `steer_move_cursor`, `confirm_move`, `pick_move`,
    `catch_plan`, `throw_ball`, `use_hp_item_in_battle`, `_open_wild_switch`, `_switch_budget`,
    `_run_away`, `party_menu_step`, `learn_step` carry the rest. Readiness and heal: `gym_ready`,
    `needs_heal`, `top_off_due`, `_retreat_warranted`, `lowest_lead`, `heal_bench_from_bag`.
  - Stall detection: `battle_signature`/`stall_check` raise `StopRequested` on a wedged battle,
    `_stall_dump` writes the fixture; `_battle_press_log` writes the per-press line.
  - Status and goal: `write_status`, `check_goal`, `replan`, `read_goal`, `snapshot`,
    `keep_snapshot`, `GoalExit`, `hold_stale`, `say`, `_apply_speed_ctl`.
  - Gym bookkeeping: `gym_stand`, `record_closed_gym`, `record_gym_loss`, `note_gym_loss`,
    `_close_signature`.
  - Team management: `fill_party`, `do_pc_swap`, `do_swap_order`, `teach_tms`, `plan_tm_trip`,
    `teach_egg_moves`, `scoring_builds`, `refresh_wanted`, `next_leader_type`,
    `unbeaten_leaders`, `SwapLedger`. Module-level scorers: `team_score`, `matchup`,
    `wanted_types`, `tm_assignments`, `tm_shopping`, `egg_assignments`, `best_swap`, `best_fill`,
    `shopping_list`, `league_shopping_list`, `field_tools`, `service_towns`, `gym_routes`,
    `gym_map_set`.
- `routines.py` is the multi-map errands built on nav. `class Errands`: `cross_edge`/`take_dive`/
  `take_warp`/`enter_warp`/`leave_by_warp`/`fall_through`/`descend_gym`/`take_warp_chain` drive a
  map transition; `talk_warp`/`talk_menu`/`peek_menu`/`_menu_rows` drive a scripted crossing
  through its dialogue and menu (the Seagallop ferry rows, read off the EWRAM list the game
  draws); `heal_at`/`talk_to_nurse` a Center run; `restock_at`/`buy_from_list`/`open_buy_list`/
  `buy_at_counter` a Mart or the League clerk, `sell_at_counter` the Mart's sell branch,
  `buy_tms_at_dept_store` the Lilycove 4F TM climb by the stairs; `revive_fossil_at` the Devon
  reviver; `swap_at_pc`/`withdraw_at_pc`/`deposit_at_pc` the PC box;
  `challenge_leader`/`gym_sweep`/`follow_route` the gym fights and recorded puzzle routes;
  `collect_item` an item ball or a hidden item; `teach_tm_in_field`/`teach_egg_move_at_nurse`/
  `use_hp_item_in_field`/`use_item_in_field` the field uses; `lead_with`/`spend_skill_points`
  the party chores.
  `landing_rank` scores a warp's step-off tile.

### Orchestration and config
- `run-grind.sh` is the supervisor loop described above.
- `gym_routes.json` holds solved press routes for the puzzle gyms (Fortree gates, Lavaridge
  holes, the Sootopolis ice cover).
- `swaps.json` holds admin-set party trade orders (gitignored, runtime).

### ROM mechanics database
- `build_rom_db.py` builds `games/rowe/rowe_rom.db` from `rowe_rom.py`'s readers, so a mechanics
  question is a SQL query instead of an emulator boot: `species`, `moves`, `type_chart`,
  `abilities`, `evolutions`, `learnset_levelup`, `tm_list`/`tm_compat`, `egg_moves`,
  `wild_levels`, `trainers`, `maps`, `map_connections`, `map_warps`, `map_objects`, `items`,
  `trainer_locations`, `wild_encounters`, `field_items`, `badge_flags`, `badge_gates`,
  `map_sections`. The committed db is the ROM snapshot of record, so a game-state claim cites a
  table and row there. Regenerate after a ROM swap.

### Deploy gate and tooling
- `smoke.py` is the offline promotion gate: it boots frozen savestate fixtures and asserts the
  nav and battle behaviors a swap into the live streamer must not regress. A red check blocks the
  swap.
- `gen_nav_map.py` renders the map graph into this repo's `index.html`.
- `solve_sootopolis_ice.py` solves the thin-ice gym-8 floor into a press route and
  `write_sootopolis_route.py` records it into `gym_routes.json`.
- `set_league_flag.py` sets the League-guard flag on a `/tmp` copy of a save so the endgame can be
  driven before the 16th badge; it refuses the live save through `rowe_live.guard_write`.
- `find_best_state.py` ranks every save state on the box by progress, the recovery tool after a
  bad restore.
- `lavaridge_watch.py`, `make_fortree_entry.py` are single-purpose helpers.

### Probes
One-off investigations, each reproducing a specific failure offline on a scratch copy of the
state so a fix is grounded before it ships: the Fortree rotating gates (`probe_fortree_*`), the
Lavaridge hole maze (`probe_lavaridge_bfs`), the Sootopolis entry and dive (`probe_sootopolis_*`,
`probe_dive_sootopolis`), the emerge dialogue, surf dismounts and elevation, the Seagallop dock
menu (`probe_dock_menu`, `probe_19_dock`, `probe_ti_ferry`), the Ever Grande climb, waterfall and
door approach (`probe_evergrande_*`), Victory Road (`probe_vr_*`), the wild-battle switch stall,
the double-battle stall, ice timing. They are kept rather than deleted so the reasoning behind
each fix stays readable.

### Tests
`test_*.py` are behavior pins, 128 files and 329 pytest cases, most run against the real ROM
tables and frozen fixtures rather than mocks. Each docstring names the live misplay it locks
down: the action-grid wedge, the 0-PP selection-script loop, the double-battle action gate,
surf-dismount refusals, the exp-lead switch, catch policy, the objective ladder, the Sevii legs
and ferry rows, the region route to the League, the League gauntlet, the Hall of Fame exit and
Continue, the Birch lab scene, the post-game planner. `smoke.py` is the gate that must be green
before a swap; the unit tests are the finer pins under it. Some pins are also script-style
(`python test_lead.py` prints `ok`).

## Where to find a feature

- Next goal chosen: `planner.recommend`. Goal executed each tick: `play.Player.overworld_step`.
  Goal changed without a process exit: `play.GoalExit` caught in `play.drive`, then
  `play.Player.replan`.
- Why a run ends (stall/wedge): `play.Player.stall_check` raising `StopRequested`; the supervisor
  loop and its watchdog in `run-grind.sh`.
- Pathing a walk: `nav.Grid.path` then `nav.Navigator.walk_to`. Crossing a map edge, warp, or
  dive: `routines.Errands.cross_edge`/`take_warp`/`take_dive`, driven from
  `play.Player._cross_to`. A split map: `region_route.route`.
- The Seagallop ferry: `script_decode.script_edges`/`menu_sequence`, `planner.script_layer`,
  `routines.Errands.talk_warp`, tickets through `play.Player._sync_tickets`.
- Picking a battle move or switch: `battle_engine.choose_move`/`best_switch`, called from
  `play.Player.battle_step`.
- The selection-script no-PP box: `play.Player._comm_action`/`comm_wait`.
- Whether to catch and with what ball: `catch.catch_chance` plus `play.Player.catch_plan`.
- Gym detection and the fight: `rowe_rom.gym_maps` (music id 0x14F) for Hoenn, `planner.JOHTO_GYM`
  for the Sevii gyms, `planner.nearest_gym`/`sevii_goal`, `routines.Errands.gym_sweep`/
  `challenge_leader`/`follow_route`, `gym_maze.warp_chain`, `play.Player.gym_step`.
- A puzzle gym's solved route: `gym_routes.json` replayed by `routines.Errands.follow_route`.
- The world routing graph: `rowe_rom.world_edges` (static, including `dive_script_edges`) plus
  `script_decode.script_edges` merged into `map_graph.MapGraph`; a blocked edge is a gate in
  `map_graph.block`.
- The League: `planner.ENDGAME_CHAIN` for the order, `play.Player.league_step` for the rooms,
  `play.Player.cutscene_step` for the ceremony and credits, `play.FLASH_BYTES` and `play.main`
  for the flash save Continue loads.
- The post-game: `planner.POSTGAME`, `play.BOSSES`, `play.Player.boss_step`, `play.DONE_EXIT`.
- Team building: `play.team_score`/`best_swap`/`tm_assignments`, applied by
  `play.Player.do_pc_swap`/`fill_party`/`teach_tms`.
- Shopping: `play.shopping_list` and `routines.Errands.restock_at`/`sell_at_counter` for the
  Mart; `play.tm_shopping`/`Player.plan_tm_trip` and `routines.Errands.buy_tms_at_dept_store`
  for the Lilycove TMs, stock read by `rowe_rom.clerk_marts`.
- Items on the ground: `rowe_rom.field_items`/`hidden_items`, `play.Player.collect_step`,
  `routines.Errands.collect_item`.
- A boss loss and its retry price: `play.Player.note_boss_loss`, `planner.boss_losses`,
  `planner.catch_target` for the coverage grind.
- The live save and its ring: `rowe_live`, `find_best_state.py`.
- Stream speed: `stream_sink.FrameStreamer.set_speed`, `play.Player._apply_speed_ctl`,
  `states/speed.ctl`.

## The world routing model

The planner and the executor route over the same graph, built by `planner.build_graph`, so the
planner never calls a destination reachable across a border the walk gave up on.
`rowe_rom.world_edges()` is the full static graph, every map routable before it is walked, built
from the ROM's connection and warp tables plus `dive_script_edges()`. `script_decode.script_edges`
adds the talked crossings, the Seagallop sailors and scripted doors; `planner.script_layer` drops
a dock's island arm when its ticket is not held and a giver whose sailor has despawned. The
executor records walked borders into `map_graph.adj` and gates an edge it could not cross into
`map_graph.gated`, keyed on the field moves held at the time, so the gate lifts the turn a new
move lands. `hops_from` ranks gyms and `grind_map` ranks grass over this graph. A grind anchors
on the next gym so a restock detour in a service town cannot drag the grind onto the grass that
town happens to sit next to.

Two maps need finer resolution than a node. Sootopolis reaches the graph through a `setdivewarp`
in the underwater map's ON_DIVE_WARP script, which `dive_script_edges` decodes into a dive edge.
Ever Grande and Victory Road 1F each split into halves with no walk between them, so
`region_route` threads the warps whose trigger tiles a landing reaches and `_cross_to` takes the
portal it names instead of gating the edge.

## Current build state

16 badges, Champion flag set. The live run is past the Hall of Fame ceremony and the credits, with
the Continue restoring the flash save at the player's house. The post-game bosses, Steven at
`(24,107)` and Red at `(24,51)`, are open; Steven has three wins over the current six, and the
planner's goal as of this commit is a coverage grind on Victory Road to catch a Teddiursa whose
edge against his six beats the weakest member's. After both bosses the planner emits `done` and
`run-grind.sh` stops for good. `pytest` collects 329; one pin,
`test_catch_endgame.py::test_all_gyms_down_with_no_wanted_draws_no_catch_plan`, is red and was
red before the current build.

## Building and running

The emulator, the ROM, and the runtime state are not in this repo. To run the agent:

1. Build mGBA 0.10.x as a shared library with the Python binding into `agent/mgba-build/`, and
   compile `agent/mgba-stubs.c` to `mgba-stubs.so` for the symbols an ffmpeg-less build omits.
2. Supply your own ROWE v2.1b ROM at the path pinned in `emu_boot.py`. `rowe_rom.self_check`
   refuses a ROM whose fingerprints do not match.
3. Create a venv and install the Python deps (cffi, Pillow, numpy, pytest). Use
   `agent/.venv/bin/python`, never system `python3`, since the venv holds the mgba binding.
4. Provide a starting save state under `agent/states/`. The flash `.sav` beside it is created
   blank on first launch.
5. `agent/run-grind.sh [hours] [speed]` supervises, or `.venv/bin/python agent/play.py --state
   <state.ss> --no-stream` runs one executor without the HLS push. The stream writes to
   `/var/www/brenergy/live` or `$ROWE_STREAM_DIR`.

The code reads one specific ROM build. The fingerprinted offsets in `rowe_rom.py` and the
addresses in `rowe_symbols.py` will not match a different build or a different hack.

## Legal

No ROM, BIOS, or save data ships here. ROWE is a fan project built on pokeemerald-expansion; this
is tooling that reads a copy you supply. mGBA is GPL and is built from its own upstream source,
not vendored here.
