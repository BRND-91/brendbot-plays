# rowe-agent handoff

The live grind rewrites `states/live.ss` while it runs, so the live-save sha and position below are a point-in-time read, not a constant.

## Live save

- `states/live.ss`: 7 badges, out of battle, position `(x, y, group, num) = (5, 6, 24, 5)`. sha256 `138d25f8eda6ae3a7912b02bf4c172daf49e982e84660ec8d572b0c5f9521272`, 397312 bytes. Source: loaded a `/tmp` copy this run.
- `states/fixtures/route101.ss`: 0-badge rollback, position `(6, 15, 0, 49)`, sha256 prefix `b190482f519e3fb8`, 397312 bytes. Do not promote over the live save. There is no `states/route101.ss`; the only route101 files under `states/` are `.pre-rename`, `.pre-rename2`, `.black`, and `route101.softlock.ss`.
- Snapshot ring `states/live/`: timestamped `.ss` copies (newest `20261101T1701.ss`) plus `_playable_0_25_7badge.ss.keep`. Source: `ls states/live/`.

## rowe-grind service

- active (running) since 2026-11-01 16:44:32 UTC, MainPID 501777 (`run-grind.sh`), cgroup `/system.slice/rowe-grind.service`. Source: `systemctl show`/`status` this run.
- Launched as a systemd transient unit (`systemd-run --unit=rowe-grind`), FragmentPath `/run/systemd/transient/rowe-grind.service`, ExecStart `/opt/brendbot/rowe-agent/run-grind.sh 24`.
- Started and stopped only by Brendan.

## Sootopolis gym `(15,0)`

- `gym_routes.json["15,0"]`: start `[8, 25, 15, 0]`, 76 presses, 77 states, ends `[8, 3, 15, 0]`, Juan's stand. Source: `json.load`, `len(presses)`.
- Fall hook in `play.py` (`ICE_FALL_FLOOR = {(15,0): (15,1)}`, `ICE_DOOR_TILE = {(15,0): (8,25)}`, `gym_step` at the `ICE_FALL_FLOOR.get(gym)` branch): a second step on cracked ice drops the party to `(15,1)`; the hook climbs the ladder at `(11,22)` via `take_warp((15,0))` and redoes the route from the door `(8,25)`.
- Juan is a single battle, `battle_type_flags 0xc`, double bit clear.

## Open bug

- The lower-floor double battle (`battle_type_flags 0x800d`), met at `(9,8)`/`(8,13)` on map `(15,1)`, freezes on a foe move message ("Foe Bibarel used Quick Attack!"). `chosen` stays `[0, 0, 0, 0]` and no action menu is drawn. Off the gym route, so Juan is reachable without it.
- Suspects: the ROWE battle script, or `mgba-stubs.c`.

## Repos

- Live tree `/opt/brendbot/rowe-agent`. Mirror `BRND-91/brendbot-plays` `agent/` at `3c768fa`.
- Drift of `agent/` against live (excluding gitignored `gym_routes.json`), from a per-file `diff -q` this run:
  - 25 files differ: `PROGRESSION.md`, `battle_engine.py`, `catch.py`, `make_fortree_entry.py`, `rowe_rom.py`, `rowe_state.py`, `run-grind.sh`, `swaps.json`, `test_battle_engine.py`, `test_catch.py`, `test_exp_lead_switch.py`, `test_gym_maps.py`, `test_party_menu_double.py`, and the probes `probe_dive_sootopolis.py`, `probe_elevation.py`, `probe_fortree_bfs.py`, `probe_fortree_gym.py`, `probe_fortree_offline.py`, `probe_gym_exit.py`, `probe_gym_sweep.py`, `probe_lavaridge_bfs.py`, `probe_lilycove_ball.py`, `probe_sootopolis_entry.py`, `probe_surf_dismount.py`, `probe_switch_stall.py`.
  - 12 files only in live: `ENDGAME_PLAN.md`, `build_rom_db.py`, `find_best_state.py`, `mgba-stubs.so`, `probe_chosen_action.py`, `probe_double_stall.py`, `probe_ice_timing.py`, `probe_sootopolis_bfs.py`, `probe_unstick_control.py`, `rowe_live.py`, `test_grind_hold.py`, `test_rowe_live.py`.

## Tests

- `pytest` from rowe-agent: 100 passed, including 27 script-style tests run by `test_script_suite.py`. Source: bare `pytest` this run.
