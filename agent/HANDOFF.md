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

- A wild single (`battle_type_flags 0xc`) left battler 0 on the move-select func `0x83C12BC`, which is in `PLAYER_CHOOSE_ACTION_FUNCS`, so `Grid.choosing(0)` read True with the move list already drawn. `battle_step`'s Fight-open gate pressed A until `choosing(0)` flipped, which never happens on a live move list, so the A landed on the drawn cursor (slot 0, Last Resort, 0 PP) the ROM refuses and the turn never advanced until the 12-step `WEDGE ... ctrl 0x83c12bc` dump. Hit Route 126 `(0,41)` after the crossing opened that water to the grind.
- Fix: `battle_step` now steers the live move cursor to the picked slot and calls `confirm_move` whether or not the Fight-open A flipped `choosing`, since `confirm_move` already backs out of a spent slot with B. Verified: `test_battle_wedge_route126.py` red on the old gate and green on the fix, a full wild battle on `/tmp/live_route126.ss` won in 5 steps with no wedge, pytest 108 passed.
- The `(15,1)` double (`battle_type_flags 0x800d`) freeze is a different controller state (ctrl `0x83aa958` idle or `0x93898e4`, not `0x83C12BC`) and stays open. Dumps at `states/fixtures/stall_<ts>.ss`, `/tmp/live_route126.ss` is the pre-battle `(0,41)` save.
- Still open: the catch readback is one battle stale on entry. A Gyarados fight logs `catch: ... soften Luvdisc` (the prior foe) and switches a softener in; the battle still wins, so it is a spurious switch, not a freeze.

## Repos

- Live tree `/opt/brendbot/rowe-agent`. Mirror `BRND-91/brendbot-plays` `agent/` at `5f5cc70` (emerge crossing + planner endgame travel, pytest 107 passed).
- Drift of `agent/` against live (excluding gitignored `gym_routes.json`), from a per-file `diff -q` this run:
  - 25 files differ: `PROGRESSION.md`, `battle_engine.py`, `catch.py`, `make_fortree_entry.py`, `rowe_rom.py`, `rowe_state.py`, `run-grind.sh`, `swaps.json`, `test_battle_engine.py`, `test_catch.py`, `test_exp_lead_switch.py`, `test_gym_maps.py`, `test_party_menu_double.py`, and the probes `probe_dive_sootopolis.py`, `probe_elevation.py`, `probe_fortree_bfs.py`, `probe_fortree_gym.py`, `probe_fortree_offline.py`, `probe_gym_exit.py`, `probe_gym_sweep.py`, `probe_lavaridge_bfs.py`, `probe_lilycove_ball.py`, `probe_sootopolis_entry.py`, `probe_surf_dismount.py`, `probe_switch_stall.py`.
  - 12 files only in live: `ENDGAME_PLAN.md`, `build_rom_db.py`, `find_best_state.py`, `mgba-stubs.so`, `probe_chosen_action.py`, `probe_double_stall.py`, `probe_ice_timing.py`, `probe_sootopolis_bfs.py`, `probe_unstick_control.py`, `rowe_live.py`, `test_grind_hold.py`, `test_rowe_live.py`.

## Tests

- `pytest` from rowe-agent: 108 passed, with the new `test_battle_wedge_route126.py` and the 3 `test_emerge.py` crossing tests among them. Source: `.venv/bin/python -m pytest -q` this run.
