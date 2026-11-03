# rowe-agent handoff

The live grind rewrites `states/live.ss` while it runs, so the live-save sha and position below are a point-in-time read, not a constant.

## Live save

- `states/live.ss`: parked at Ever Grande `(0,8)` tile `(0,67)`, 8 badges, party L59-62, 152044 money; frozen as `states/fixtures/evergrande_0_8.ss` for the Victory Road fixture. Source: `find_best_state.py` this run.
- `states/fixtures/route101.ss`: 0-badge rollback, position `(6, 15, 0, 49)`, sha256 prefix `b190482f519e3fb8`, 397312 bytes. Do not promote over the live save. There is no `states/route101.ss`; the only route101 files under `states/` are `.pre-rename`, `.pre-rename2`, `.black`, and `route101.softlock.ss`.
- Snapshot ring `states/live/`: timestamped `.ss` copies (newest `20261101T1701.ss`) plus `_playable_0_25_7badge.ss.keep`. Source: `ls states/live/`.

## rowe-grind service

- relaunched this run (MainPID 1374217, child `play.py --state states/live.ss --minutes 1440`) off commit `2e1fa67`; the Victory Road entry leg `(0,8) -> (16,12)` is confirmed end to end and the live planner pass emits `recommend travel (16,12)` at `(0,8)`. Source: `systemctl show rowe-grind` this run. The run resumed from `states/live.ss` parked at `(0,8)` tile `(0,67)`.
- Launched as a systemd transient unit (`systemd-run --unit=rowe-grind`), FragmentPath `/run/systemd/transient/rowe-grind.service`, WorkingDirectory `/opt/brendbot/rowe-agent`, ExecStart `/opt/brendbot/rowe-agent/run-grind.sh 24`.
- Restart after a verified fix is brendbot's; a partial fix does not get a restart. Relaunch: `systemctl reset-failed rowe-grind && systemd-run --unit=rowe-grind -p WorkingDirectory=/opt/brendbot/rowe-agent /opt/brendbot/rowe-agent/run-grind.sh 24`.

## Sootopolis escape, third crossing (emerge)

- Emerge (0,51)->(0,41) is a yes/no dialogue, "Light is filtering down from above. Would you like to surface?". `take_dive(EMERGE)` sends B, waits for the two-line prompt, then A for YES; the old single-B press left the prompt open and read as stuck, so emerge never fired in this agent (zero `emerge: moved` across 30427 grind.log lines, the (0,7) sightings were `snapshot -> states/live.ss` relaunches).
- `nav.Grid.emerge_tiles` picks reachable seabed minus the back-warp tile and the no-surfacing behaviours `NO_SURFACE_BEHAVIORS = {0x19, 0x2A}`. Landing (45,66) is behaviour 0x00 and surfaces to (0,41) at the same coords.
- Gates `(0,7)->(24,5)` and `(24,5)->(0,51)` cleared from `states/map_graph.json` (backup `states/map_graph.json.pre-gateclear`), so `graph.route((0,7),(0,8))` threads the crossing. `(0,51)->(0,52)` left gated.
- Planner at all-gyms-beaten returns `{"mode":"travel","to":[0,8]}` when a route exists, else explores toward `(0,8)` (see the endgame-planner section below). `planner.py` builds its `MapGraph` with `world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs()` (matching `play.py`); the earlier worldless `MapGraph(GRAPH)` made `graph.route()` traverse only walked borders, so `route((0,7),(0,8))` read None and the travel branch fell through to grind-hold even with the gates cleared. `hops_from` was unaffected since it reads `world_edges()` directly.
- Crossing confirmed live: executor reached `map [0,41] tile [42,65]` this run, so the dive/warp/emerge legs all fired in play. With the worldless bug, the stale `travel [0,8]` goal drove the crossing; with the fix the planner re-emits travel [0,8] on the next relaunch (explore toward `[0,8]` otherwise).

## Endgame planner, no-route fallback (fixed)

- Symptom: at 8 badges the party (L58-62, 15 over cap 45) ground Route 121 `(0,36)` and the west routes instead of finishing to Ever Grande. `recommend` returned a grind every replan.
- Evidence: the new-format replan in `states/grind.log`, `no route from [0,8] to [0,8], hop [0,8] blocked, holding on [0,36]`. `here == dest == (0,8)`: the party had reached Ever Grande, so the `here != dest` travel guard sent arrival into the no-route fallback, which `grind_map` anchored on `(0,8)` and ranked grass back toward `(0,36)`. Not an interior map, not a mid-map-change status write.
- Change (`38b8cd8`): the `not unbeaten` branch in `recommend` travels to `(0,8)` when `graph.route(here,(0,8))` under the live moves exists, else returns `{"mode":"explore","to":[0,8]}`, never `grind_map`. The `here != dest` guard keeps the arrival case out of a travel-to-self loop. The `low < cap` top grind branch is dead at badge 8 (cap 45 under every party level) and stays for the earlier game.
- Verification: live `recommend` on `states/status.json` from `(0,36)` returns `travel (0,8)`. `test_planner` covers the gated-route hold (explore, never grind) and the arrival case `here==(0,8)`. pytest 122 passed.

## Endgame executor halt (fixed)

- Symptom: after `recommend` returned explore/travel to `(0,8)`, the party still reached Ever Grande then wandered back west, dove the underwater `24,x` maps, and ground Route `(0,53)`. `states/status.json` goal read `grind (0,53)`.
- Evidence: `states/grind.log`, `explore frontier gated at [0,53], grinding toward [0,53]`, and the three blocked exits off `(0,8)`: `travel (0,8) -> [16,10] warp: stuck (blocked)` (same for `[16,12]` into Victory Road and `[24,43]` underwater). The travel goal `(0,8)` completes on arrival (`goal reached: arrived at map [0,8]`); with no goal past the city and the Victory Road warp tiles unreachable, `explore_step` fell to `demote_to_grind` and routed to the nearest grass, west.
- Change (`56732f3`): `explore_step` at `badges >= 8` with a gated frontier and a failed dive raises `GoalExit("unsupported: endgame blocked at [0,8], no reachable frontier past the last badge")`, which `replan` propagates (`exit_reason.startswith("unsupported")`) and the supervisor halts on (`case unsupported*) exit 0`). `run-grind.sh` now posts to Discord on that halt. `demote_to_grind` keeps its below-8 grind contract unchanged, so `test_underwater_bounce` still holds.
- Verification: `test_endgame_halt` covers the badge-8 halt (unsupported reason, names `[0,8]`) and the below-8 demote. Red-capability: without the guard `explore_step` demotes to a grind and never raises an unsupported reason. pytest 124 passed.
- Measured (step 3): the `0x13` climb was already committed (`c7646ac`, `nav._climb` + `Grid.path` one-way-up edge) and rides the real Ever Grande fall on a `/tmp` copy parked at `(0,8)`, foot `(15,68)` -> plateau `(15,59)`, prompt "It's a large waterfall, do you want to use the Waterfall Tool to climb it?". The `0x13` is a 12-wide by 8-tall sheet, 96 tiles `x=15..26 y=60..67`, bottom row `y=67`, surf foot `y=68` behaviour `0x15`. The break was the door, fixed in the Victory Road entry section below.

## Victory Road entry, door above the climb (fixed)

- Symptom: travel `(0,8) -> (16,12)` left the party at the shore; `take_warp((16,12))` returned `stuck` pinned on the start tile `(0,67)` without a step.
- Evidence: on the parked `(0,8)` copy `take_warp` never called `walk_to`. `_step_into_warp`'s approach prune `if key and not grid.passable(*tile, elev, (x,y), surf)` dropped the only approach `(27,49)` to door `(27,48)`: the approach sits above the climb at elevation 5, which a single-step `passable` from the surfer's carried `SURF_ELEVATION` (1) rejects (a dismount needs `ELEV_LAND` 3), while `grid.path(start,(27,49),surf)` with climb reaches it. Both Victory Road doors read behaviour `0x69` (MB_ANIMATED_DOOR), collision bit set, entered by an UP press from the tile below.
- Change (`86f6ead`): the prune gates on a real route, `if key and grid.path((x,y), tile, surf) is None`, and `_step_into_warp` sets `grid.climb` from the Waterfall Tool key item so the path check crosses the fall. Post-fix `take_warp` walks the `(27,49)` approach (a surf encounter interrupts the walk, which the executor loop fights).
- Verification: `test_warp_approach` on the frozen `states/fixtures/evergrande_0_8.ss` asserts `take_warp((16,12))` no longer stalls pinned on the start tile. Red-capability: pre-fix it returned `stuck` with the avatar unmoved. pytest 125.
- Confirmed (`2e1fa67`): the full leg `(0,8) -> (16,12)` drives through the executor loop on goal `travel (16,12)`, `take_warp` presses UP into door `(27,48)` and the map changes `(0,8) -> (16,12)` (`goal reached: arrived at map [16, 12]`), 0 battles on the clean run (`probe_vr_full_leg.py`, `probe_endgame_recommend.py`). `test_vr_door_press` asserts the map change from the frozen `states/fixtures/vr_door_27_49.ss` pre-press fixture; red-capability is the pre-fix `stuck` with the map unchanged at `(0,8)`.
- Planner chain (`2e1fa67`): `recommend` advances `ENDGAME_CHAIN = [(0,8),(16,12),(16,10),(25,60)]` to the first map not in `graph.visited` with a walkable `graph.route`, so arrival at `(0,8)` emits `travel (16,12)` and each hall drops out once visited. `test_planner` pins `(0,8)->travel (16,12)` then `(16,12)->travel (16,10)` on a world-backed graph. pytest 126. Frozen `states/fixtures/vr_entry_16_12.ss` holds the arrival state for the next leg.
- Next: the city->`(16,10)` leg, door `(18,5)` up north past the fall. `(16,12)` is a spur, not a step toward `(16,10)` (measurement below). ENDGAME_PLAN segment 3: `(16,12)` is the entry from the bottom of the city, `(16,10)`/`(18,5)` the League-side exit.

## Victory Road interior, Phase 1 measurement

- The only Victory Road door reachable from Ever Grande City is `(27,48)->(16,12)`. Control on `states/fixtures/evergrande_0_8.ss` from stand `(0,67)`: `Grid.reachable` with Surf and Waterfall-Tool climb reaches 414 tiles and exactly one warp tile, `(27,48)`; climb off reaches 222 and no warp tile. The League-side door `(18,5)->(16,10)` and both underwater doors `(18,41)`/`(18,27)->(24,43)` are unreachable from the surface either way.
- `(16,12)` is a one-way spur. It reaches `(16,13)` and back to `(0,8)`, nothing else. Inside `(16,13)` the forward League warps `(5,1)->(25,60)` and `(9,1)->(25,25)` sit at row 1 behind a wall the entry pool cannot climb to: `reachable` from the warp-in tile `(2,6)` with Surf and climb is 77 tiles both climb states and holds neither warp tile nor a neighbour, so `take_warp((25,25))` returns `stuck` with the map unchanged. Landing back at `(0,8)` from the `(16,12)` door drops at the fall-top `(27,49)`, a pocket whose only reachable exit is the `(16,12)` door, so `_landing_exits` reports `[[16,12]]`, the hop dead-ends, and the walk bounces `(16,12)<->(0,8)` to the `BOUNCE_STREAK` re-plan.
- So `planner.ENDGAME_CHAIN = [(0,8),(16,12),(16,10),(25,60)]` cannot thread: `(16,12)` is not a stepping stone to `(16,10)`, and `(16,10)` is not reachable from the city surface at all. The open build item is the city->`(16,10)` crossing (how `(18,5)` is actually reached past the fall), not a break inside `(16,12)`.
- Evidence: `probe_vr_interior.py` drives the leg on a `/tmp` copy of `states/fixtures/vr_entry_16_12.ss` through the real executor loop, tracing each `take_warp` before/after. Frozen `states/fixtures/vr_16_13.ss` holds the `(16,13)` pocket state.

## Sootopolis gym `(15,0)`

- `gym_routes.json["15,0"]`: start `[8, 25, 15, 0]`, 76 presses, 77 states, ends `[8, 3, 15, 0]`, Juan's stand. Source: `json.load`, `len(presses)`.
- Fall hook in `play.py` (`ICE_FALL_FLOOR = {(15,0): (15,1)}`, `ICE_DOOR_TILE = {(15,0): (8,25)}`, `gym_step` at the `ICE_FALL_FLOOR.get(gym)` branch): a second step on cracked ice drops the party to `(15,1)`; the hook climbs the ladder at `(11,22)` via `take_warp((15,0))` and redoes the route from the door `(8,25)`.
- Juan is a single battle, `battle_type_flags 0xc`, double bit clear.

## Battle move-list wedge (fixed)

- The action func `0x83C12BC` drives both the "What will X do?" grid and the Fight move list, branching on `gBattleCommunication[0]` (0 or 2 on the grid, 3 in the list), so `choosing(b)` reads True on both screens and cannot gate the Fight-open press. The old gate pressed A until `choosing(b)` flipped, which never happens on a live list, so the A confirmed whatever slot the cursor was parked on before `steer_move_cursor` ran: a 0-PP Last Resort slot the ROM refuses (the `WEDGE ... ctrl 0x83c12bc` dump on Route 126 `[0,41]`), or a PP'd slot that fired a move `pick_move` never chose.
- Fix: `GameState.in_move_list(b)` reads the `comm[0] == MOVE_LIST_COMM_STATE` sub-state behind the shared func, and `battle_step` presses A to open Fight only `if not in_move_list(b)`; once the list is drawn it steers to the picked slot and confirms. `PLAYER_CHOOSE_ACTION_FUNCS` keeps `0x83C12BC` because the same func is the action handler, so removing it would break `choosing`/`chooser`. Control: diffed the action grid against the move list at the same func across `roxanne`, `battle_disabled`, `stall_route126`; the move cursor moved and `comm[0]` read 3 only on the list.
- Verified: `test_battle_wedge_route126.py` (3 tests) green, the parked-PP misfire reproduced on `states/fixtures/movelist_parked_pp.ss` (the old gate fires the parked slot move 514, the fix fires the pick move 36), pytest 110 passed.
- Still open: the `(15,1)` double (`battle_type_flags 0x800d`) freeze (`0x83aa958`/`0x93898e4`) and the one-battle-stale catch readback (`soften Luvdisc` on the wrong foe, a spurious switch that still wins) remain. `/tmp/live_route126.ss` is the pre-battle `(0,41)` save. The wild-single idle freeze on `0x83aa958` is the no-PP loop fixed below.

## Battle no-PP selection-script loop (fixed)

- A wild lead whose parked move has no PP froze under the selection-script box: the ROM holds `gBattleCommunication[0] == 6` (the no-PP box) and bounces the move list to the idle controller `0x83aa958` at `comm == 3`, so `choosing(b)` read False and `battle_step` fell into the intro branch and mashed A. Each A at comm 6 dismissed the box and each A at comm 3 re-confirmed the parked 0-PP slot, which re-raised the box, so it looped. `live.ss` replayed it on every relaunch because the snapshot sits one Seel encounter back at the same RNG.
- Fix: the box dispatch is single-sourced in `Player._comm_action(b)` — under a choose or intro-idle controller func it reads `gBattleCommunication[b]`, taps B and returns `"box"` at comm 6, returns `"move_list"` at comm 3, else `""`; it reads comm only under those funcs since the bag and party-menu callbacks leave the value stale. `Player.comm_wait(b, pred, ..., key)` is the `press_until`-style waiter that routes a battle choose-phase loop through `_comm_action`, so a box toggling up mid-wait is left with B rather than mashed back open by the loop's own key. `_advance_intro` calls `_comm_action` each pass (at `"box"` it re-reads next pass, at `"move_list"` it steers to the pick and `confirm_move`, which B's out of a 0-PP slot), and the Fight-open gate in `battle_step` presses A through `comm_wait` instead of a bare `press_until`. A 0-PP low lead still skips the potion (`any(me.pp)` guard) so the switch takes it.
- The first cut (`aa3fa4c`) read `comm` once at entry; the per-pass re-read in `_advance_intro` (`1312772`) fixed that branch but left the Fight-open gate in `battle_step` pressing A blind through `press_until`. A 0-PP lead entering on the grid (comm 2, just after a forced switch) opens the list, pops the box there, and the bare A-mash hit it the same way — the live watcher caught 20 A-at-comm6 presses, and `states/fixtures/seaking_seel_nopp.ss` (comm 6 at load, `instr 0x8396b61`) never covered the comm-2 gate path. `states/fixtures/seaking_nopp_grid.ss` is that comm-2 entry (Vileplume on the grid vs Starmie, the catch plan sends Seaking out onto a spent slot 0): replayed with `_comm_action` disabled it presses A at comm 6 fourteen times in six steps, the live loop; with the dispatch live it steers off slot 0 and confirms a PP'd move with zero A at comm 6. Routing both the gate and `_advance_intro` through `_comm_action` closes it.
- Overworld party-PP-depletion heal unchanged (below). The other battle wait loops are already box-safe: `_open_wild_switch` backs out of a mis-opened list with B on its `func not in PLAYER_CHOOSE_ACTION_FUNCS` check, `party_menu_step`'s hold loop presses no key under the party-menu callback, and the throw/item result loops press B through the catch/recovery text — none presses A while the box can overlay, so the dispatch lives only where a choose-phase loop presses A (the gate and the intro).
- Overworld party-PP-depletion heal: `lowest_lead` already routes to the Center when no mon can attack (its `healthy = [m ... if can_attack(m) ...]` filter goes empty), mirroring `_retreat_warranted`'s battle check; `test_lead.py` pins it with a full-HP, zero-PP party asserting `need_heal`.

## Party menu forced replacement

- Status: guarded, cause not reproduced, not fixed. The polled walk and the hp/target guard are in, but HEAD's walk already reached the live target on every swept phase, so the stated misfire is unconfirmed on the single grid (double list suspected, no fixture).
- `party_menu_step` walks the party cursor to a live bench slot and confirms with A. `gPartyMenuSlot` is the ROM's own cursor variable and updates a few frames behind the dpad press under the cursor slide, so a fixed `run(10)` after a tap could read the slot the cursor is leaving, and an A on that read confirms whatever slot the cursor settled on. The ROM refuses a fainted selection, so the cost of a stale read is an A on a fainted slot, a "no energy left" box, a B and a wasted step, not a fainted mon actually sent out.
- Fix per the stream directive: after each tap `wait_until(party_menu_slot() != pre_tap, 30)` (poll `MENU_POLL_FRAMES`=2 up to 30), and a pre-A guard confirms only when the fresh slot is the target and `party[slot].hp > 0`, re-walking up to `PARTY_MENU_WALK_RETRIES`=3 otherwise, then B-closing. Replaces the single `run(10)`-per-tap walk.
- Control: HEAD's `run(10)` walk reached the live target and switched on every one of 17 entry-frame phases on `states/fixtures/party_menu_faint.ss` (faints at slots 0,1) and a far-target variant (only slot 5 live). The misfire does not reproduce on the forced-replacement single grid, the 10-iteration loop re-reads and recovers each phase. The stream misfire is the double-battle list (one column, UP/DOWN by one, overshoot onto a fielded slot), for which there is no real `.ss`; the fix hardens both paths and is the polled-wait shape the move-list open already uses.
- Verified: `test_party_menu_faint.py` (2 tests) green on `party_menu_faint.ss`; the switch-to-a-live-mon pin is red-capable, a zero `PARTY_MENU_WALK_RETRIES` leaves the fainted lead on the field. The double fake `test_party_menu_double.py` still passes. pytest 115.
- `states/fixtures/party_menu_faint.ss`: open party grid after a wild lead fainted, cursor slot 0 (fainted), slot 1 fainted, live bench 2-5. Built from `party_menu.ss` (which sits one A earlier, at the "Use next POKéMON?" prompt before the grid).

## Per-press battle log and throw_ball dump

- `Player._battle_press_log` prints one grind.log line per battle press, gated in `tap` on `in_battle()`: the key, `cb2`, the chooser's controller func, `gBattleCommunication[b]`, and the cursor slot on the open screen with the hp (party menu) or pp (move list) under it. The live party-menu walk reads as `press DOWN ... party slot 0 Flechinder hp 0/61` then `press A ... party slot 2 Herdier hp 60/60`. `test_press_log.py` pins the party-menu and move-list lines.
- `0x803c761` is `CB2_BATTLE_MAIN` (rowe_symbols:272), the callback through the action grid, move list and turn playback. `throw: bag never opened (cb2 0x803c761)` means the RIGHT+A never left the battle screen into the bag.
- `throw_ball`'s no-bag back-out now dumps state + png to `/tmp/rowe_throw_nobag_<ts>.ss` like the switch-stall path, so the next live occurrence is a fixture to fail-first the polled rewrite on. The polled rewrite of `throw_ball` (press until `callback2 == CB2_BAG_MAIN`) is not written, it waits on that dump.
- `use_hp_item_in_battle` carried the same gap: RIGHT, A, `run(150)` then straight into the pocket walk off `bag_position` with no callback check, so an eaten RIGHT turned the medicine sequence into Fight-list input. It now runs the same `CB2_BAG_MAIN` guard, dumps to `/tmp/rowe_item_nobag_<ts>.ss`, and B's out. `test_throw_ball.py::test_use_hp_item_bag_never_opened_backs_out_with_b` pins it, red without the guard (the walk reads `party_menu_slot` and raises).

## Repos

- Live tree `/opt/brendbot/rowe-agent`. Mirror `BRND-91/brendbot-plays` `agent/` at `95a23bf` (executor badge-8 halt; `play.py`, `run-grind.sh`, `test_endgame_halt.py` synced this run, pytest 124). `ARCHITECTURE.md`/`README.md`/`dexgen` were refreshed on `main` earlier this run. The drift list below predates these syncs (`run-grind.sh` now matches).
- Drift of `agent/` against live (excluding gitignored `gym_routes.json`), from a per-file `diff -q` this run:
  - 25 files differ: `PROGRESSION.md`, `battle_engine.py`, `catch.py`, `make_fortree_entry.py`, `rowe_rom.py`, `rowe_state.py`, `run-grind.sh`, `swaps.json`, `test_battle_engine.py`, `test_catch.py`, `test_exp_lead_switch.py`, `test_gym_maps.py`, `test_party_menu_double.py`, and the probes `probe_dive_sootopolis.py`, `probe_elevation.py`, `probe_fortree_bfs.py`, `probe_fortree_gym.py`, `probe_fortree_offline.py`, `probe_gym_exit.py`, `probe_gym_sweep.py`, `probe_lavaridge_bfs.py`, `probe_lilycove_ball.py`, `probe_sootopolis_entry.py`, `probe_surf_dismount.py`, `probe_switch_stall.py`.
  - 12 files only in live: `ENDGAME_PLAN.md`, `build_rom_db.py`, `find_best_state.py`, `mgba-stubs.so`, `probe_chosen_action.py`, `probe_double_stall.py`, `probe_ice_timing.py`, `probe_sootopolis_bfs.py`, `probe_unstick_control.py`, `rowe_live.py`, `test_grind_hold.py`, `test_rowe_live.py`.

## Tests

- `pytest` from rowe-agent: 124 passed (the 2 new `test_endgame_halt.py` badge-8 tests added to the prior 122), with the 3 `test_battle_wedge_route126.py` move-list tests, the 4 `test_nopp_loop.py` selection-script tests (B-at-6, steer+confirm-at-3, the mid-intro toggle, and `test_comm_wait_leaves_opening_box_with_b_never_mashes_the_open_key`), the 3 `test_nopp_grid.py` emulator replays off `seaking_nopp_grid.ss` and `seaking_seel_nopp.ss`, the 2 `test_party_menu_faint.py` forced-replacement tests, and the 3 `test_throw_ball.py` bag-guard tests among them. Red-capability: with `_comm_action` stubbed to `return ""` the 4 `test_nopp_loop.py` and 3 `test_nopp_grid.py` tests all fail. Source: `.venv/bin/python -m pytest -q` this run. `test_lead.py` and `test_retreat.py` are script-style (run directly, `python test_lead.py` prints `ok`); the overworld PP-depletion heal pin lives in `test_lead.py`.

## Open: (25,60) identity conflict
The Seagallop dock script on (2,3) warps to (25,60) via warpteleport2 (landing x=7
y=11, gate flag 0xCD1, multichoice case 0). An earlier map read treated (25,60) as
the Pokemon Center 2F link room. Both reads cannot be right; resolve which before
talk_warp targets (25,60). Not chased here.

## Gate capability version (expect a one-run re-probe)
A gate now carries `EXECUTOR_CAP_VERSION` (`map_graph.py`), bumped when a crossing primitive lands
(an NPC-talk warp, a descent link, the live-grid border read). `_gate_shut` reads a gate recorded
below the current version as open, so the walker retries that crossing once and a fresh failure
re-records it at the current version. Every gate persisted before this commit loads as version 0,
so the first grind/drive run after it reopens every recorded gate once and spends time re-walking
borders that are still dead. That one pass is expected, not a regression; by the end of it each
still-dead border is re-gated at the current version and routing settles. `block()` also records a
`reason` (`no_warp`, `unreachable`, `script_no_go` from `_border_open`, `stuck`, `bounce`) so a
later purge is a query over reasons rather than a hand audit.
