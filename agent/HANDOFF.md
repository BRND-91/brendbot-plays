# rowe-agent handoff

The live grind rewrites `states/live.ss` while it runs, so the live-save sha and position below are a point-in-time read, not a constant.

## Live save

- `states/live.ss`: 7 badges, out of battle, position `(x, y, group, num) = (5, 6, 24, 5)`. sha256 `138d25f8eda6ae3a7912b02bf4c172daf49e982e84660ec8d572b0c5f9521272`, 397312 bytes. Source: loaded a `/tmp` copy this run.
- `states/fixtures/route101.ss`: 0-badge rollback, position `(6, 15, 0, 49)`, sha256 prefix `b190482f519e3fb8`, 397312 bytes. Do not promote over the live save. There is no `states/route101.ss`; the only route101 files under `states/` are `.pre-rename`, `.pre-rename2`, `.black`, and `route101.softlock.ss`.
- Snapshot ring `states/live/`: timestamped `.ss` copies (newest `20261101T1701.ss`) plus `_playable_0_25_7badge.ss.keep`. Source: `ls states/live/`.

## rowe-grind service

- active (running) since 2026-11-01 16:44:32 UTC, MainPID 501777 (`run-grind.sh`), cgroup `/system.slice/rowe-grind.service`. Source: `systemctl show`/`status` this run.
- Launched as a systemd transient unit (`systemd-run --unit=rowe-grind`), FragmentPath `/run/systemd/transient/rowe-grind.service`, WorkingDirectory `/opt/brendbot/rowe-agent`, ExecStart `/opt/brendbot/rowe-agent/run-grind.sh 24`.
- Restart after a verified fix is brendbot's; a partial fix does not get a restart. Relaunch: `systemctl reset-failed rowe-grind && systemd-run --unit=rowe-grind -p WorkingDirectory=/opt/brendbot/rowe-agent /opt/brendbot/rowe-agent/run-grind.sh 24`.

## Sootopolis escape, third crossing (emerge)

- Emerge (0,51)->(0,41) is a yes/no dialogue, "Light is filtering down from above. Would you like to surface?". `take_dive(EMERGE)` sends B, waits for the two-line prompt, then A for YES; the old single-B press left the prompt open and read as stuck, so emerge never fired in this agent (zero `emerge: moved` across 30427 grind.log lines, the (0,7) sightings were `snapshot -> states/live.ss` relaunches).
- `nav.Grid.emerge_tiles` picks reachable seabed minus the back-warp tile and the no-surfacing behaviours `NO_SURFACE_BEHAVIORS = {0x19, 0x2A}`. Landing (45,66) is behaviour 0x00 and surfaces to (0,41) at the same coords.
- Gates `(0,7)->(24,5)` and `(24,5)->(0,51)` cleared from `states/map_graph.json` (backup `states/map_graph.json.pre-gateclear`), so `graph.route((0,7),(0,8))` threads the crossing. `(0,51)->(0,52)` left gated.
- Planner at all-gyms-beaten returns `{"mode":"travel","to":[0,8]}` when a route exists, grind-hold otherwise. `planner.py` builds its `MapGraph` with `world=rowe_rom.world_edges(), passthrough=rowe_rom.passthroughs()` (matching `play.py`); the earlier worldless `MapGraph(GRAPH)` made `graph.route()` traverse only walked borders, so `route((0,7),(0,8))` read None and the travel branch fell through to grind-hold even with the gates cleared. `hops_from` was unaffected since it reads `world_edges()` directly.
- Crossing confirmed live: executor reached `map [0,41] tile [42,65]` this run, so the dive/warp/emerge legs all fired in play. With the worldless bug, the stale `travel [0,8]` goal drove the crossing; with the fix the planner re-emits travel [0,8] on the next relaunch (grind-hold `[0,39]` otherwise).

## Sootopolis gym `(15,0)`

- `gym_routes.json["15,0"]`: start `[8, 25, 15, 0]`, 76 presses, 77 states, ends `[8, 3, 15, 0]`, Juan's stand. Source: `json.load`, `len(presses)`.
- Fall hook in `play.py` (`ICE_FALL_FLOOR = {(15,0): (15,1)}`, `ICE_DOOR_TILE = {(15,0): (8,25)}`, `gym_step` at the `ICE_FALL_FLOOR.get(gym)` branch): a second step on cracked ice drops the party to `(15,1)`; the hook climbs the ladder at `(11,22)` via `take_warp((15,0))` and redoes the route from the door `(8,25)`.
- Juan is a single battle, `battle_type_flags 0xc`, double bit clear.

## Battle move-list wedge (fixed)

- The action func `0x83C12BC` drives both the "What will X do?" grid and the Fight move list, branching on `gBattleCommunication[0]` (0 or 2 on the grid, 3 in the list), so `choosing(b)` reads True on both screens and cannot gate the Fight-open press. The old gate pressed A until `choosing(b)` flipped, which never happens on a live list, so the A confirmed whatever slot the cursor was parked on before `steer_move_cursor` ran: a 0-PP Last Resort slot the ROM refuses (the `WEDGE ... ctrl 0x83c12bc` dump on Route 126 `[0,41]`), or a PP'd slot that fired a move `pick_move` never chose.
- Fix: `GameState.in_move_list(b)` reads the `comm[0] == MOVE_LIST_COMM_STATE` sub-state behind the shared func, and `battle_step` presses A to open Fight only `if not in_move_list(b)`; once the list is drawn it steers to the picked slot and confirms. `PLAYER_CHOOSE_ACTION_FUNCS` keeps `0x83C12BC` because the same func is the action handler, so removing it would break `choosing`/`chooser`. Control: diffed the action grid against the move list at the same func across `roxanne`, `battle_disabled`, `stall_route126`; the move cursor moved and `comm[0]` read 3 only on the list.
- Verified: `test_battle_wedge_route126.py` (3 tests) green, the parked-PP misfire reproduced on `states/fixtures/movelist_parked_pp.ss` (the old gate fires the parked slot move 514, the fix fires the pick move 36), pytest 110 passed.
- Still open: a wild single can freeze on the idle controller `0x83aa958` (`choosing` and `in_move_list` both False) out of the catch/softener-switch path, dump at `states/fixtures/stall_idle_route126_1793566797.ss`. The `(15,1)` double (`battle_type_flags 0x800d`) freeze (`0x83aa958`/`0x93898e4`) and the one-battle-stale catch readback (`soften Luvdisc` on the wrong foe, a spurious switch that still wins) remain. `/tmp/live_route126.ss` is the pre-battle `(0,41)` save.

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

- Live tree `/opt/brendbot/rowe-agent`. Mirror `BRND-91/brendbot-plays` `agent/` at `5f5cc70` (emerge crossing + planner endgame travel, pytest 107 passed).
- Drift of `agent/` against live (excluding gitignored `gym_routes.json`), from a per-file `diff -q` this run:
  - 25 files differ: `PROGRESSION.md`, `battle_engine.py`, `catch.py`, `make_fortree_entry.py`, `rowe_rom.py`, `rowe_state.py`, `run-grind.sh`, `swaps.json`, `test_battle_engine.py`, `test_catch.py`, `test_exp_lead_switch.py`, `test_gym_maps.py`, `test_party_menu_double.py`, and the probes `probe_dive_sootopolis.py`, `probe_elevation.py`, `probe_fortree_bfs.py`, `probe_fortree_gym.py`, `probe_fortree_offline.py`, `probe_gym_exit.py`, `probe_gym_sweep.py`, `probe_lavaridge_bfs.py`, `probe_lilycove_ball.py`, `probe_sootopolis_entry.py`, `probe_surf_dismount.py`, `probe_switch_stall.py`.
  - 12 files only in live: `ENDGAME_PLAN.md`, `build_rom_db.py`, `find_best_state.py`, `mgba-stubs.so`, `probe_chosen_action.py`, `probe_double_stall.py`, `probe_ice_timing.py`, `probe_sootopolis_bfs.py`, `probe_unstick_control.py`, `rowe_live.py`, `test_grind_hold.py`, `test_rowe_live.py`.

## Tests

- `pytest` from rowe-agent: 115 passed, with the 3 `test_battle_wedge_route126.py` move-list tests, the 2 `test_party_menu_faint.py` forced-replacement tests, the 2 `test_press_log.py` battle-log tests, the 3 `test_throw_ball.py` bag-guard tests, and the 3 `test_emerge.py` crossing tests among them. Source: `.venv/bin/python -m pytest -q` this run.
