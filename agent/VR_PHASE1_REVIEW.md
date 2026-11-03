# Victory Road endgame plan — review brief

## What this is

A plan to drive the ROWE autoplayer (`/opt/brendbot/rowe-agent`) from the post-badge-8 state at
Ever Grande City through Victory Road, the Elite Four gauntlet, and Champion Wallace. The bot
boots the ROM headless, reads RAM and the ROM's static tables, picks a goal, and drives button
presses. It has all field moves at badge 8 (Surf, Dive, Waterfall). Phase 1 was started and its
premise failed on measurement; this brief is the original plan plus that measurement, for an audit
of whether the phase ordering and the Phase 1 fix direction still hold.

Relevant modules: `rowe_rom.world_edges` (static routing graph from map connections + warps),
`map_graph.MapGraph` (learned world graph merged with `world_edges`), `nav.Grid`
(`reachable`/`path`, the waterfall-climb edge in `_step_refused`), `planner.recommend` (goal
ladder, holds `ENDGAME_CHAIN`), `play.Player` (`travel_toward`, `_landing_exits`, the executor
loop), `routines.Errands.take_warp`.

## The original plan (verbatim, as written before any measurement)

Recon's in. The VR interior leg is mostly a measurement, the real build is the Elite Four
gauntlet. Plan, ordered:

**Phase 1, VR interior (16,12)→(16,10)→(25,60), measure then fix.** Should route on existing nav.
The interior is a water dungeon gated on SURF+DIVE+WATERFALL, all in the bag at badge 8, and
`map_graph` reopens gated edges as field moves are held (`gated`/`_open`, `travel_toward` passes
`field_moves()` into `graph.route`). VR exits `(16,13)`/`(16,14)` carry static warps to
`(25,60)`/`(25,25)` that `rowe_rom.world_edges` resolves, so the graph can express this leg. Build
step is to drive it on a parked copy, log where it stops, fix the first break, repeat to `(25,60)`.
No STRENGTH-boulder code exists anywhere and none is needed here.

**Phase 2, decode the E4 doors.** The graph cannot route the gauntlet. `rowe_rom.world_edges`
builds from `map_connections`+`map_warps`, and the forward chain `(25,24)→25→26→27→(25,40)` is
dynamic `(127,127)` warps set by each room's script, which `map_warps` can't resolve, and Wallace's
room reads zero header warps. Door behavior per room is undecoded. So scan `metatile_behavior` at
each E4 room exit the way the VR entry was pinned, and freeze a fixture at each room entrance.

**Phase 3, gauntlet handler.** A dedicated goal mode, not chain entries, since the warps aren't
routable. Per room: detect the E4 room id, fight the trainer to a win (`battle_step` already drives
trainer fights, `catch_plan` returns None so no ball), then press the decoded exit and advance to
the next room. Loop across 5 rooms plus Wallace. This is the piece no graph edge can carry.

**Phase 4, pre-gauntlet prep, the sharp risk.** There is no mid-gauntlet heal, no in-bag Revive, and
no PP restore (`heal_bench_from_bag` leaves a fainted mon for the Center, the Center is unreachable
once the doors go dynamic). A faint inside the E4 can't recover until a whiteout. So force a full
Center heal and verify bag HP-item stock before entering `(25,60)`, and treat PP drain across five
straight fights as a real failure mode to measure, not assume.

**Phase 5, tests.** Assert each room transition on a frozen fixture, same shape as
`test_vr_door_press`. Add a planner pin that standing at `(25,60)` emits the league goal, because
today `recommend` finds all four chain maps visited and falls to `explore` → idle, which
`test_planner` doesn't yet catch.

Phase 1 is where I start measuring. Phases 2 and 4 are the unknowns that decide the rest.

## Phase 1 update — measured, the premise failed

Phase 1 assumed the interior "should route on existing nav" and that
`(16,12)→(16,10)→(25,60)` threads on `world_edges`. Driving it on parked copies through the real
executor loop (`probe_vr_interior.py`) shows it does not.

**Control 1 — the only reachable VR door from the city.** On `states/fixtures/evergrande_0_8.ss`,
party standing at Ever Grande City `(0,8)` tile `(0,67)`, `Grid.reachable` with Surf and the
Waterfall-Tool climb reaches 414 tiles and exactly one warp tile, `(27,48)->(16,12)`. With climb
off it reaches 222 tiles and no warp tile. The city's four warps are `(18,5)->(16,10)`,
`(27,48)->(16,12)`, `(18,41)->(24,43)`, `(18,27)->(24,43)`; the League-side door `(18,5)->(16,10)`
and both underwater doors are unreachable from the surface either way.

**Control 2 — `(16,12)` is a one-way spur.** It reaches `(16,13)` and back to `(0,8)`, nothing
else. The `(16,12)→(16,13)` crossing itself works (`take_warp((16,13))` changes the map,
`(7,8)→(2,6)`, 0 battles). Inside `(16,13)` the live warps are `(1,6)->(16,12)`, `(5,1)->(25,60)`,
`(9,1)->(25,25)`. The two forward League warps sit at row 1 behind a wall: `reachable` from the
warp-in tile `(2,6)` with Surf and climb is 77 tiles for both climb states and holds neither warp
tile nor a neighbour, so `take_warp((25,25))` returns `stuck` with the map unchanged. Landing back
at `(0,8)` from the `(16,12)` door drops at the fall-top `(27,49)`, a pocket whose only reachable
exit is the `(16,12)` door, so `_landing_exits` reports `[[16,12]]`, the hop dead-ends, and the
walk bounces `(16,12)<->(0,8)` to the `BOUNCE_STREAK` re-plan.

**Consequence.** `planner.ENDGAME_CHAIN = [(0,8),(16,12),(16,10),(25,60)]` cannot thread.
`(16,12)` is not a stepping stone to `(16,10)`, and `(16,10)` is not reachable from the city
surface at all.

## Ground facts the audit should not re-derive

- `rowe_rom.world_edges()` (static): `(16,12)->{(16,13),(0,8)}`; `(16,13)->{(25,25),(25,60),(16,12)}`;
  `(16,14)->{(25,25),(16,10),(25,60)}`; `(16,10)->{(16,14),(0,8),(16,9)}`.
- ENDGAME_PLAN segment 3 header decode: `(16,12)` is the entry hall from the city fall, warps
  `(6,8)/(7,8)<->(0,8)`, reached via city door `(27,48)->(16,12)` whose approach `(27,49)` sits
  above the Ever Grande waterfall. `(16,10)` is the League-side hall, warps `(9,11)/(10,11)<->(0,8)`,
  via city door `(18,5)->(16,10)` up north past the fall's reach. A Dive-climb chain hangs off
  `(16,10)` through `(16,9),(16,0),(16,5),(16,1),(16,6),(16,2),(16,7),(16,3),(16,8),(16,4)` with a
  side room `(16,11)`. League exits: `(16,14)` reached from `(16,10)` at `(1,7)`, `(16,13)` reached
  from `(16,12)` at `(1,6)`; each warps `(5,1)->(25,60)` and `(9,1)->(25,25)`.
- The waterfall-climb edge (`nav._step_refused`, line ~276) fires only when the current tile is
  water, the pressed direction is up, Surf and `grid.climb` are both set, and the tile above is a
  `WATERFALL` (0x13) metatile; it lands on the first non-waterfall tile above the run. In `(16,13)`
  setting `grid.climb` changes nothing, so no water-under-waterfall column leads from the entry pool
  up to the row-1 warps.

## Open questions for the audit

1. **Which door is the real League entry?** `world_edges` lists forward edges on both `(16,13)`
   (from `(16,12)`) and `(16,14)` (from `(16,10)`), but the only city-reachable door is
   `(27,48)->(16,12)`, and `(16,13)`'s forward warps are walled off the entry pool. Is `(16,13)` a
   genuine dead-end spur the plan should drop, with the intended path running through `(16,10)` and
   `(16,14)`? Verdict plus the ROM evidence (warp/connection table or metatile scan).

2. **How is `(16,10)` reached?** Its city door `(18,5)` is unreachable from the city surface, and
   nothing reaches the Dive-climb chain that hangs off it, because `(16,12)` connects only to
   `(16,13)` and `(0,8)`. Is `(16,10)` reached by a map-border connection or a dynamic warp that
   `world_edges` (built from `map_connections` + `map_warps`) does not carry? Name the crossing and
   where to decode it.

3. **Is the walled-off `(16,13)` pool a decode gap or the real map?** `reachable` from `(2,6)` is 77
   tiles and excludes the row-1 warps under both climb states. Confirm against the ROM metatile
   layout whether a waterfall/dive path to `(5,1)`/`(9,1)` exists that `nav` currently cannot
   express, or the room is genuinely one-way from this side.

4. **Does the phase ordering survive?** Phase 1 was the assumed-cheap measurement and Phases 2–5
   depend on reaching `(25,60)` first. If the city→interior→League crossing is an unsolved routing
   problem rather than a quick nav fix, rank what to build first and flag any dependency the
   original ordering skips.

5. **The dynamic-warp assumption (Phase 2).** The plan treats the E4 forward chain as dynamic
   `(127,127)` warps set per room script and Wallace's room as zero-header-warp. Confirm that
   reading against the ROM, and flag whether the same dynamic-warp shape also governs the
   VR→League `(25,60)`/`(25,25)` entry, which would change Phase 1's fix.

Artifacts: `probe_vr_interior.py` (driver), `states/fixtures/vr_entry_16_12.ss` (parked `(16,12)`),
`states/fixtures/vr_16_13.ss` (the `(16,13)` pocket), measurement recorded in `HANDOFF.md` and
committed on `ed6b68d`.
