# Progression plan

Why the loop keeps landing on Route 101. `planner.recommend` knows one objective, Roxanne,
and one default, grind the grass nearest the executor's last position. Past badge 1 the
objective list is empty, so the default runs forever, and every Oldale errand leaves the
executor standing in Oldale, where the nearest grass is Route 101. The guide FAQ #13 says
stats lock at the level cap until the next gym falls, so a capped party gains nothing from
any grind; the only progress at cap is a badge.

## Mechanisms, in build order

1. Objective ladder. `recommend` picks, in priority: lowest attacker under cap -> grind;
   at cap -> the unbeaten gym w/ the fewest hops over `rowe_rom.world_edges` from the goal
   map under the current field tools; no gym reachable -> explore toward the nearest one.
   The eight interiors come off the ROM by music id 0x14f, Rustboro (11,3) the control:
   Petalburg (8,1), Dewford (3,3), Mauville (10,0), Lavaridge (4,1), Fortree (12,1),
   Mossdeep (14,0), Sootopolis (15,0). Beaten gyms read from the per-gym badge flags, never
   the count. The leader stand tile comes from the gym's object events, confirmed on entry
   the way Roxanne's was. Whether Norman opens at one badge is checked by walking in; gym
   mode already reports `talked` when no fight starts, and that result drops the gym to
   the back of the ladder.
   Check: status at cap 21, badge 1, Route 102 -> gym (8,1), never a grind.

2. Grind anchored on the goal, ranked by wild level. `grind_map` takes the goal map as its
   anchor, never `status["map"]`, so a restock in Oldale cannot move the grind. Candidates
   are visited grass maps ranked by fewest hops to the next gym, then by the ROM's wild
   encounter levels (gWildMonHeaders, located by scanning for Route 101's land table) so
   the party fights the highest wild level under the cap on the way forward.
   Check: exit in Oldale w/ goal Route 116 -> grind stays on 116; Route 101 ranks last at cap 21.

3. Field tools from the bag. `field_moves` reads the key items ROWE hands out per badge
   (Axe at 1, Waterfall Tool at 2, Pickaxe at 4, Rock Climb Tool at 7) beside the start
   Surfboard, so `map_graph` gates (cut trees, boulders, waterfalls) reopen the turn the
   item lands and the gym BFS in step 1 routes through them.
   Check: bag w/ the Axe -> a gated cut-tree edge reports open.

4. Errands stay inside the goal. Heal and restock trips are detours: the executor walks
   back to the goal map after them (already in `overworld_step`), and the planner never
   re-decides off the errand's end position (step 2 covers the anchor).

5. Ground items. `rowe_map.static_objects` already reads every object template off the
   map header w/ its position and its hide flag; an item ball is the template whose
   graphics id is the item-ball sprite, and its flag flips once collected. On every map
   the walk crosses, `overworld_step` detours to each uncollected ball the grid can reach,
   faces it and presses A, then resumes the goal. Hidden items come from the same header's
   bg events and get the same detour once the Itemfinder is read from the bag.
   Check: a map w/ two balls, one flag set -> one detour, the goal resumed after it.

6. Bag use. In battle, a lead under 30% w/ a Potion-class item in the Items pocket uses it
   through the Bag path `throw_ball` already walks (Bag, pocket, slot, confirm, target mon)
   before it flees, which also drops most Center trips. Out of battle the same pocket heals
   the bench after a fight so the two-mons-down trigger fires only when the bag is empty.
   Berries go on as held items, Oran or Sitrus on the lead through the party menu's Give,
   refilled from the Berries pocket after each battle that ate one.
   Check: a fixture w/ the lead at 10% and three Potions -> a Potion used, no flee.

7. Team composition through the box. The box is read from `gPokemonStoragePtr` the way the
   party is read now, species and level per slot. A team scores on two counts: how many
   members share a weakness (three Flying types all taking Rock and Electric super
   effectively) and how many hit the next gym leader's type super effectively or resist
   it, w/ the leader types fixed per gym. A swap happens only on a Center visit the loop
   is already making, replaces one party mon w/ one boxed mon, and fires only when the
   boxed mon raises the team score by at least two points. Equal or one-point trades never
   fire, which is the hysteresis against cycling two sound mons, and a mon swapped out
   stays boxed until the next badge. The new mon trains to the cap on the grind, which is
   short since stats lock there, and the lead rotation already hands it the front slot.
   Check: the current party against the box w/ Pawmi or Fomantis in it -> one flyer out,
   the Electric or Grass mon in; the same party against a box of three more flyers -> no swap.

8. Static core, side deck, real opposition. Scope, six pieces.
   a. How ROWE builds a leader (`CreateNPCTrainerParty`, `src/battle_main.c`, and
      `src/level_scaling.c`). Count = `*_Mode_Boss_Pokemon_Number[badges]`, normal mode
      {3,4,4,5,5,6,6,6,6,6,6}. Species = the first count-1 rows of the leader's party table
      in order plus row 5 as the ace in the last slot, each run through `GetTrainerPokemon`,
      which evolves the row's species to the stage its level allows. Levels =
      `*_Mode_Boss_Pokemon_Min_Level[badges] + slot`, normal {13,19,25,31,37,43,49,60,...},
      raised to the player's max level in New Game Plus. Leaders carry custom moves and held
      items (`partyFlags`), and from 5 badges each mon rolls one of its three abilities at
      random. Tate & Liza take rows 4 and 5 as the last two. The mode comes off save flags
      0x25 easy, 0x27 hard, 0x28 randomized, 0x2B no-evolution, 0x49E NG+. The live save
      is easy mode w/ NG+ set and `VAR_NEW_GAME_PLUS_COUNT` 0 (vars at `SB1_FLAGS` + 300),
      so a leader's count is the easy table {3,4,4,4,5,5,5,6,...} and its base level is the
      larger of the easy table {12,17,22,27,32,37,42,50,...} and the party's max level, which
      means leaders scale w/ the party from here on. That paragraph describes the vendored
      source; the ROM is the authority and it differs on levels. In the ROM a trainer struct
      is 64 bytes, mixed-case name at +4, party pointer at +40, count at +60, and a party
      row is 40 bytes w/ the level marker at +0 and species at +10. The main table's gym
      structs (Flannery 0x3fe9d8, Winona 0x3fea58, Wattson 0x3fe998, Norman 0x3fea18,
      Roxanne 0x3fe918) carry the same pools as the source: Flannery Vulpix, Fletchling,
      Salandit, Scorbunny, Houndour, Torkoal ace; Winona Doduo, Murkrow, Sigilyph, Skarmory,
      Dratini, Swablu ace. The structs at 0x4067xx.. are the rematch variants and hold
      different pools. The live log confirms the build rule: Winona at 4 badges fielded
      Doduo, Sigilyph, Murkrow, Swablu, rows 0-2 plus the ace, count 4. Levels do not follow
      the source's tables: observed leader base levels are 20 at 2 badges (Norman), 23 at 3 (Wattson), 26 at
      4 (Winona), 29-30 at 5 (Tate & Liza, off HP totals), w/ the party max at 37 for Winona, so no party-max
      floor applies. The guide's Badge Rewards level column (29, 32, 36, 39 at 3-6 badges)
      is the level cap the planner already uses, and the leader base sits 6 under it at 3
      and 4 badges, and Tate & Liza's HP totals put their base at 29-30, 6 under as well;
      Roxanne at 1 badge read 16, 5 under. Count was 4 at 3, 4 and 5 badges. Neither the
      cap list nor a base-level list exists as bytes in the ROM, so the levels are computed
      in code, and `rowe_rom.LEADER_BASE_LEVEL` / `LEADER_COUNT` carry the fitted values w/
      the 6+ badge entries marked assumed until a fight shows them. `rowe_rom.trainer_pool`
      and `leader_team` read the ROM layout and apply the rule, `test_leader.py` pins
      Winona's logged fight and Flannery's build at 6 badges. Save-flag
      ids for the mode flags get the same ROM confirmation. The ability is scored as the
      mean over the three slots once badges >= 5.
   b. Core and deck. The party is a five-mon static core plus one flex slot. The core is
      scored against the Elite Four and Champion builds at the badge count they will be
      fought at, weight 1 each, plus every remaining leader at weight 1, so it changes only
      when a mon strictly outclasses a member for the endgame. The flex slot is scored
      against the next leader's build alone and is the only slot a gym can move. Core
      scoring and flex scoring are separate calls w/ separate margins. In code: `mon_profile`
      scores every mon at the party floor (species projected, `stats_at`, attack types from
      moves whose split runs off the larger offence stat, both on a tie); `matchup` gives two
      points per member that hits a foe super effectively or resists all its types, minus two
      per member past the first a foe type hits super effectively, over each build's foes;
      `team_score` adds the team's value in 20-point steps. `Player.scoring_builds` is the
      remaining leaders at the badge count each is reached at plus `LEAGUE` (Sidney, Phoebe,
      Glacia, Drake, Wallace) at 8; `flex_slot` is the member whose removal costs that score
      least; `best_swap` runs once over the core slots at `core_margin` and once over the flex
      slot against the next leader at `FLEX_MARGIN`. Gym leaders by badge order are `LEADERS`,
      Juan at Sootopolis and Wallace the Champion per the ROM's gTrainers rows, and
      Tate&Liza fields pool rows 4 and 5 last.
   c. Mon value, read not projected. Nothing on a 2.1b mon is encrypted: moves sit in the
      three bitfield words at 0x14, EVs are six bytes at 0x20 (HP, Atk, Def, Spe, SpA, SpD),
      the ability slot is bits 4-5 of byte 0x32, nature is personality mod 25, and no IV
      field exists, IVs being the Trainer Skill stat boosts at 3 per level (`iv_boosts`).
      Fitted on the fixture parties: six stats per mon reproduced within a point from base
      stats, EVs and nature at 0 skill levels, exact on the mons whose EVs had not moved
      since their last level-up, and the ability slot matched gBattleMons on five mons.
      `rowe_state.box_mon` and `party_mon` carry `moves`, `evs`, `ability_num`, `nature`;
      `rowe_rom.stats_at` is the game's formula, `species_at_level` the EVO_LEVEL walk, the
      table at ROM 0x5a607c in 8-byte rows, ten per species, and `Species.abilities` the
      two slots plus hidden off the species row (0x1e, 0x20, 0x24). Species is projected to
      the party's level floor through every EVO_LEVEL step at or under it, both for box and
      party mons, item, trade, friendship and mega rows skipped. Offence is the larger of
      Atk and SpA w/ nature applied; an attack type credits coverage only when the move's
      `split` runs off that stat. Value = offence + Spe + mean(HP, Def, SpD). EVs stay
      unscored: the grind refills them.
   d. Moves through the blue nurse, decoded from the ROM script bytes, not the vendored
      source. The badge-reward ladder at ROM 0x2f388c.. gives Good Rod then Pickaxe,
      Catching Charm, Power Glove, each `setflag 0xE26..0xE29` plus `setvar 0x4061 <count>`,
      so `VAR 0x4061` is the badge count and flags 0xE25.. are the receipts; the save reads
      0xE25-0xE29 set and 0x4061 = 6, matching the bag. The teach-moves script at ROM
      0x2f0300-0x2f0640 gates on `compare 0x4061 >= N`. Read live on the Center fixture w/
      the var forced: the nurse is local id 6 behind the left counter, talked to from two
      tiles below, menu row 3 is Teach or Forget a Move, and its submenu is Forget (free,
      through the summary move select), Egg Move (4 Battle Points, open at 6 badges),
      Tutor Move ("you need 9 badges", 6 BP), TM/HM Move ("you need 12 badges", 8 BP).
      The charge unit is Battle Points, the BP box is drawn top-left on the price prompt.
      No level-up reminder sits in this menu; that is Fallarbor's Move Relearner house, so
      the per-visit upkeep at six badges is the egg tutor. `rowe_rom.level_up_learnset`
      (0x5D3688, {u16 move, u16 level}), `egg_moves` (gEggMoves 0x5DAD5C keyed by
      `first_stage`) read the tables. Routine: a swap lands, and the next heal visit offers
      the newcomer and the core the egg moves that close a wanted type, 4 BP each; tutor
      moves wait for badge 9.
      The save block's vars start at `SB1_VARS` 0x1BCA (the base where 0x4061 reads 6 and
      the game-stats block after it is populated), so `VAR_0x405C` reads 0 there.
   e. TMs. TMs are reusable in ROWE (`party_menu.c` `Task_LearnedMove`, the RemoveBagItem
      is commented out), so a TM teaches every core member that learns it. HMs are off the
      plan, field moves are key items here. The TM pocket is `gBagPockets[8]` (the table at
      EWRAM 0x203AD70, found by scanning for the Items pocket pointer): an EWRAM array at
      0x203ADC4 of 208 slots outside the save block, which is why a save-block scan shows no
      TM rows. `sTMHMMoves` is u16[208] at ROM 0x1041518 indexed item - 482 (TM01), and
      `gTMHMLearnsets` at ROM 0x4EBEA4 is a pointer per species to 0xFF-ended u8 TM indexes
      (`rowe_rom.tm_move`, `tm_learnset`, `GameState.tms`). The bag's TMs are a reserved
      pool for the core: on each heal visit, after the PC, a TM whose type closes a coverage
      gap in the target set goes on the core member w/ the matching offence stat that can
      learn it (`play.tm_assignments`, `Player.after_heal`), driven by
      `routines.teach_tm_in_field`: Start > Bag > TMs tab > Use, three text boxes, the party
      menu, Yes to replacing, the forget slot on the move-select summary, A until the bag is
      back. Gap types the bag cannot cover are bought: Lilycove Dept. Store 4F sells attack
      TMs, among them TM14 Blizzard (20000), TM79 Frost Breath, TM82 Dragon Tail and TM116
      Dragon Dance, and the restock list carries the cheapest TM per open gap once money
      clears the restock's own needs; that buy list is still open. TM13 Ice Beam is Game
      Corner only and stays off the list.
   f. Pool. The target-set gaps (types no core attack hits super effectively) become a
      wanted-types list the catch policy prefers on the next wild encounter of that type,
      so the box grows toward the gaps instead of toward whatever walked by. A wanted-type
      catch is exempt from the level cutoff in g. In code: `play.wanted_types` over the party
      at its floor against the core builds, held on `Player.wanted` (launch, then every heal
      visit) and written to status.json as `wanted_types`; `catch.Ledger.wants` keeps the
      one-of-each policy and, from `BALL_RESERVE` balls down, spends only on a wanted type.
   g. Locks and budget. Core margin 10% of the core score w/ a floor of 5; flex margin 2.
      The core budget counts Center visits, not badges: one core swap per four heal visits
      since the last swap, a swapped-in core mon locked for the next four visits, a
      swapped-out one barred for eight, all in `states/swaps.json`, and the Elite Four plus
      Champion count as four more targets so the budget keeps running after badge eight.
      The level cutoff is relative to the grind map's wild level, not the floor: a
      candidate more than 10 levels under the highest wild level on the current grind map
      is cut before scoring, so catches off the route the party grinds on stay eligible.
      `swap_at_pc` turns box pages so all 90 catches are candidates, and after a swap the
      planner sets the grind cap to the floor so the newcomer trains to the party and stops.
      In code: `play.SwapLedger` holds `visits`, `last_core_visit`, `locked` and `barred`
      windows by personality (the window value is the first free visit), `do_pc_swap` counts
      the visit, bars, locks, cuts by `grind_wild_top` and runs core then flex; `swap_at_pc`
      reaches a box past the current one by UP onto the title row then RIGHT per page (90
      frames a turn, R and L turn nothing), `GameState.current_box` reads the page it opened
      on. The grind cap needs no change: `planner.recommend` already grinds while the lowest
      attacker is under the badge cap, which is the floor the rest of the party sits at
      once the ladder has moved to the gym, so a newcomer trains to the party and stops.
   Files: rowe_rom.py (leader_team, evolution and ability readers), rowe_state.py (substruct
   decrypt), play.py (Profile, core and flex scoring, locks, TM use), routines.py (box
   paging, tutor and TM menus), catch.py (wanted types), planner.py (cap), test_team.py.
   Check: `leader_team("Flannery", 6)` returns Vulpix 33, Fletchling 34, Salandit 35,
   Scorbunny 36, Torkoal 37, Houndour left out, each evolved in-game to the stage its
   level allows (`leader_build`: Fletchinder and Cinderace off the ROM's rows, Scorbunny's second step sits at 35; Salandit's step is female-gated, method 16, so the projection keeps Salandit and the Lavaridge fight settles it), independent of party max; a box Marill reports its real ability
   slot and moves against the summary screen; the core never changes on a gym-only gain;
   eight badges w/ two mons alternating as best yields at most one core swap each and never
   the reverse of the last one; an Ice TM in the bag lands on the core member w/ the higher
   SpA when no core attack hits Dragon.

## Cross-cutting

- Whiteout. A lost trainer or gym fight warps the player to the last Center w/ half the
  money gone. No step reads that today, so the walk would treat the jump as a nav failure
  and the gym goal would retry the same fight w/ the same team until the budget ran out.
  The loop detects it (map jump to a Center map plus the money drop), counts a loss per
  gym, and after two losses on one gym runs step 7's swap against that leader's type or
  moves the gym to the back of the ladder.
- Money. Balls, potions and berries all cost, and the cash on hand is under one restock.
  Every purchase holds a floor, balls before potions while the party is short of six, and
  trainer fights along the ladder are the income, so travel never routes around one.
- Wild level scaling. The thread calls the wild curve badge-scaled, so step 2's ROM
  encounter table may be rewritten at runtime; the rank is checked against the levels the
  live battle log shows before the table is trusted.

## Past Hoenn

ROWE runs 16 badges, eight Hoenn gyms and eight on the Sevii Islands, in any order
(pokecommunity thread 442592; RoweSource `flags.h` carries FLAG_RECEIVED_BADGE_09..16).
Step 1's ladder covers the eight interiors the ROM identifies by gym music. The Sevii
gyms, how the islands are reached, and the League after them are not wired; they get
read off the ROM's warp tables once the Hoenn ladder has a badge count that reaches
them, and the ladder's "no gym reachable" branch holds an explore goal until then.

## Not changing

Catch policy, learn policy, trainer fights on the way (a forced challenge is taken in
every mode since the stall->B fix), the gym step itself.

## Working method (named ban: the speculative revert)

A change that passes its offline test ships to the live supervisor and runs. The next
decision about those same lines waits for a real run to show what they did; a line is not
re-edited or torn out on a prediction that it will fail. "It might not work" is a run, not
a revert. The churn this bans is the make-then-cut-next-turn loop on nav.py and play.py:
every undo so far was speculation with no failed run behind it, zero game progress across
126 edits. The offline test gate stays (a broken save corrupts the live state), and a
change that a live run shows is worse gets reverted with that run cited as the cause.

## Named ban: progress claimed from an offline probe

Any statement about where the run is (badges, gyms beaten, gyms skipped, party) reads
`states/status.json` `badge_flags` and the live `logs/tasks/<run>.out` first. An offline
probe or saved-state replay describes its own save, never the run. The miss: a Fortree
BFS wake reported "Fortree stays skipped" while the live log already had badge 5 earned at
FortreeCity_Gym (12,1) and badge 6 at MossdeepCity_Gym (14,0). Offline gym probes do not
launch while the live run has the same gym in reach; the live run is the only source.

## Stream watch log

Hourly stream-watch findings, newest last, append-only. Each entry is a confirmed bug or
stalled-play finding co-verified against BOTH the live stream (https://live.brenergy.net/)
and the rowe-grind ground truth (states/status.json, newest states/*.ss snapshot mtime,
journalctl -u rowe-grind), never the logs alone. A run that finds the game healthy writes
nothing here. Entry fields: ET timestamp; symptom as expected vs actual; receipts (the
status fields, the journal line verbatim, the screenshot observation); the ranked recommended
fix; and a status of open or applied, set to applied with the file or edit named once a later
run lands the fix.

### 2026-10-31 00:20 ET
- symptom: expected the lead to clear the Route 113 wild battle and keep walking to the Lavaridge gym [4,1]; actual the move-select menu freezes on Pawmot vs wild Sandslash L23, the run bails on WEDGE in 12 steps, and the supervisor relaunches the same snapshot straight back into the same encounter, looping every ~90s (runs 19, 20, 21 identical)
- receipts: status.json map [0,28] Route 113 tile [24,12], lead Pawmot L45, Supercell Slam pp 0/10; journal `WEDGE: battle frozen 12 steps, ctrl 0x83aa958 exec 0x1, dumped /tmp/rowe_stall_1793420479.ss` then `run 21 start 04:19:51` resuming states/route101.ss; stream: Pawmot move menu frozen, cursor on Supercell Slam, vs Sandslash L23 74/74, 7s behind
- fix: 1) break the deterministic re-entry, since run-grind.sh resumes the identical states/route101.ss each run so the same wild encounter and wedge re-roll: on 2+ consecutive stall exits at the same map tile, desync the RNG or reroute before relaunch 2) mitigate the move-select wedge at ctrl 0x83aa958, same class as run 16's 0x84f4c78 switch-in freeze
- status: applied for the 0-PP instance only; the live loop persists via a distinct wedge, logged below. The Sandslash stream here showed the cursor on Supercell Slam (pp 0/10) and the 05:13 stream showed Pawmot L45 69/139 vs Donphan L25 with "There's no PP left for this move!" over status.json Supercell Slam pp 0/10, one confirmed cause: pick_move (play.py) fell back to `return 0` when scoring left nothing, confirming slot 0 even when spent. Fix: battle_engine.first_usable_slot returns the most-PP selectable move for that fallback, pick_move calls it instead of 0. test_pick_fallback.py red-capable, offline gate green (48 passed), shipped on run 53. This did NOT clear the live loop: run 53 still wedges on battle 3 Skarmory with a valid move chosen, a separate mechanism.

### 2026-10-31 01:22 ET
- symptom: expected the lead to clear the battle-3 Skarmory L28 wild encounter at map [0,28] and walk on to Lavaridge [4,1]; actual the run wins battles 1 (Spinda) and 2 (Honedge) every launch, then on battle 3 the catch-chip picks a valid move but the action grid freezes with the cursor parked on Bag and never reaching Fight, bailing on WEDGE and relaunching the same snapshot every ~90s. Distinct from the 00:20 0-PP wedge (that one confirmed a spent slot; this one chooses a move with PP). Persists after the first_usable_slot fix shipped on run 53.
- receipts: status.json map [0,28] tile [71,10], lead Pawmot L45, Dig pp 10/10 Close Combat 5/5 Spark 20/20; journal (run 53, post-fix) `battle 3: ['Skarmory L28']` then `chip: Dig est 65 vs 87 (chance 8%)` then `prompt? battler 0 action 1 move 0, B` repeating into `unstick: battle frozen 4 steps, clearing submenu`; stream 05:21 Pawmot L45 139/139 vs Honedge L23 "Go! Pawmot!", the battle-2 step of the same loop
- fix: 1) the chip selects Dig, a two-turn semi-invulnerable move, as the lowest-damage safe chip (est 65 < 0.8x87); a charging move leaves the next turn with no action choice, so the per-turn action read desyncs onto Bag. Exclude multi-turn/charging moves from weakening_move's catch-chip pool (battle_engine.weakening_move / catch.py), fall to the next lowest single-turn hit. 2) harden the action-grid recovery (play.py ~845-849, 3x UP+LEFT): when the cursor will not reach Fight, detect the held text/submenu and press B to dismiss before retrying, widening past 3 tries
- status: applied, fix 1 at root. Added battle_engine.CHARGING_EFFECTS = {75,145,151,155} (semi-invulnerable Dig/Fly/Dive/Bounce/Phantom/Shadow, Solar Beam, Razor Wind/Sky Attack/Freeze Shock/Ice Burn, Skull Bash; effect ids read off the ROM move table) and weakening_move now drops any move whose effect is in that set from the chip pool, falling to the next single-turn hit. test_catch_chip_charging.py red-first (chose Dig effect 155, est 51), green after. Offline gate: test_*.py 49 passed, smoke 44/45 (the one FAIL pc_swap_sheds_a_rock_weak_flyer is unrelated PC-box logic). Shipped on executor restart run 73 (pid 1691640, 06:11 ET). Live clear waits on the next battle-3 Skarmory encounter under run 73.

### 2026-10-31 03:09 ET
- symptom: expected the lead to clear each wild battle and keep exploring toward Lavaridge [4,1]; actual the executor does advance map-to-map ([1,31] -> [0,26] -> [0,28] over a 150s watch) but the ctrl 0x83aa958 action-grid WEDGE recurs on normal attack turns, not catch-chips, bailing ~1 battle per hit and relaunching the snapshot: run 126 wedged on battle 2 with Pawmot choosing Close Combat, run 127 wedged on battle 4 vs Stonjourne L26. Persists after run 73's fix-1 (charging-move catch-chip exclusion), which only covered the catch-chip path and not attack-turn freezes
- receipts: status.json map [0,28] tile [83,10], lead Pawmot L47 81/145; journal `WEDGE: battle frozen 12 steps, ctrl 0x83aa958 exec 0x1, dumped /tmp/rowe_stall_1793430578.ss` then `stopped: 3/4 won, 0 caught, state kept, exit stall`; stream live.brenergy.net title "exploring, now at Route 111", party Pawmot L47 / Seaking FNT intact, LOG "2/2 won, 0 caught, Pawmot L47 81/145" 16s prior, overworld not hard-frozen (executor recovers and keeps exploring between bails)
- fix: 1) land the 01:22 entry's unapplied fix 2: harden action-grid recovery in play.py (~845-849, the 3x UP+LEFT): when the cursor will not reach Fight, detect the held text/submenu and press B to dismiss before retrying, widen past the 3-try cap. The catch-chip cause is already closed by fix-1, so this attack-turn freeze is the remaining live blocker 2) same wedge class as run 16's 0x84f4c78 switch-in freeze; if B-dismiss does not clear it, resync the battler/action cursor from the live battle struct before issuing the move rather than trusting the stale per-turn action read
- status: applied, fix 1. Extracted the action-grid nav loop into play.py Player._reach_fight(b) and hardened it: each retry taps B to dismiss a held text box or open submenu (Bag/Pokemon) that parks the cursor off Fight and eats the UP+LEFT, before the UP+LEFT, and the retry cap widened from 3 to ACT_NAV_RETRIES=6 (B on the bare grid is a no-op). test_action_grid_recovery.py red-first (old no-B loop leaves cursor on Bag=2, never reaches Fight; 3 cases: fixture triggers the wedge, B-dismiss reaches Fight, unclearable prompt falls through to the prompt handler). Offline gate green: test_*.py 52 passed, smoke 44/45 (the one FAIL pc_swap_sheds_a_rock_weak_flyer is the same unrelated PC-box logic the 01:22 entry noted). Shipped on executor restart run 178 (pid 1865529). Live clear waits on the next ctrl 0x83aa958 attack-turn wedge under run 178; if B-dismiss does not clear it, fix 2 (resync the battler/action cursor from the live battle struct) remains the next step.

### 2026-10-31 05:08 ET
- symptom: expected the lead to clear the map [24,0] (Route 111) wild encounter and keep walking to Lavaridge [4,1]; actual the encounter is a DOUBLE battle (Golbat L23 + Lunatone L23), the move menu renders but the ctrl 0x83aa958 action grid wedges, run 178's _reach_fight B-dismiss fires ("unstick: clearing submenu") 3x and does NOT clear, the run bails on WEDGE in 12 steps at 0/1 won and the supervisor relaunches straight back into the same double encounter, looping every ~60s. This is the 03:09 entry's fix-2 trigger landing: B-dismiss confirmed insufficient. New signal vs all prior wedges (single battles): the encounter is a double battle
- receipts: status.json map [24,0] tile [6,21], battles 0 wins 0, lead Pawmot L47 110/145; journal (6 consecutive runs 231-237 in a 6-min window, all identical) `battle 1: ['Golbat L23', 'Lunatone L23']` then `unstick: battle frozen 4 steps, clearing submenu` x3 then `WEDGE: battle frozen 12 steps, ctrl 0x83aa958 exec 0x1, dumped /tmp/rowe_stall_1793437724.ss` then `stopped: 0/1 won, 0 caught, state kept, exit stall`; stream live.brenergy.net: Pawmot L47 in a double battle vs Golbat L23 + Lunatone L23, move menu open and frozen, cursor on Supercell Slam (pp 0/10 per status.json)
- fix: 1) land the 03:09 entry's unapplied fix 2 scoped to the double-battle layout: a double battle inserts a target-select submenu and a second player-battler action between move-select and turn commit, so the single-battler per-turn action read in _reach_fight desyncs and the 3x B-dismiss cannot reach a stable Fight. Resync the active battler index and action cursor from the live battle struct before issuing each move, and teach _reach_fight / the action-grid nav the double-battle target-select step rather than trusting the stale single-battler read 2) if the double-battle action logic is too deep to land safely, break the deterministic re-entry (same as the 00:20 fix-1): the run resumes and walks to [24,0] into the identical Golbat/Lunatone double encounter every launch, so on 2+ consecutive stall exits at the same map and encounter, reroute around [24,0] or desync the RNG before relaunch
- status: applied, fix 1 at root. Cause confirmed from the live run, not a dump: the decision gate at play.py read BATTLER0_CONTROLLER_FUNC hardcoded, so in a double where the second mon chooses as battler 2 while battler 0's controller has gone idle at 0x83aa958 (the exact ctrl the WEDGE dump reports), the gate saw idle, skipped the decision and never picked a move (no pick_move print in journalctl, confirming the bail landed before move-select). Added GameState.controller_func(battler) and GameState.choosing(battler) reading gBattlerControllerFuncs[battler] (base BATTLER0_CONTROLLER_FUNC + CONTROLLER_FUNC_STRIDE*battler), and changed the play.py gate to `if not self.g.choosing(b)` keyed on the chooser b from sides(). test_double_action_gate.py red-first (old battler-0 read returns False on the battler-2 double and skips the turn, new chooser read returns True), green after. Offline gate: test_*.py 54 passed, smoke 44/45 (the one FAIL pc_swap_sheds_a_rock_weak_flyer is the same unrelated PC-box logic). The two switch-flow gates at play.py ~1061 and ~1166 still read battler 0 and belong to the voluntary-switch path, left untouched this pass. Live clear waits on the next [24,0] double under a fresh relaunch, which imports the edited modules; if battler 2's controller there is a third func outside PLAYER_CHOOSE_ACTION_FUNCS, that func gets added the same way the [4,2] ALT was.

### 2026-10-31 07:07 ET
- symptom: expected the lead to clear the map [24,0] (Route 111) Golbat L23 + Lunatone L23 double encounter and walk to Lavaridge [4,1]; actual the 05:08 choosing(b)-gate fix is on disk (play.py:877 `if not self.g.choosing(b)`, mtime 1793443712, predating these runs) and imported by 4 fresh relaunches, yet runs 356-359 wedge identically on the same double: ctrl 0x83aa958 WEDGE in 12 steps at 0/1 won, supervisor relaunches the same encounter every ~60s. Fix-1 (the battler-chooser decision gate) shipped and did NOT clear the live loop
- receipts: status.json map [24,0] tile [6,21], battles 0 wins 0, lead Pawmot L47 110/145 Supercell Slam pp 0/10; journal (runs 356/357/358, 3-min window, identical) `battle 1: ['Golbat L23', 'Lunatone L23']` then `unstick: battle frozen 4 steps, clearing submenu` x3 then `WEDGE: battle frozen 12 steps, ctrl 0x83aa958 exec 0x1, dumped /tmp/rowe_stall_1793444818.ss` then `stopped: 0/1 won, 0 caught, state kept, exit stall`; stream dashboard LOG "stopped, stall", 0/1 WON, party matching status.json (Pawmot 110/145, Seaking 163/168, Vileplume, Greedent, Golduck, Talonflame), video pane offline between relaunch frames
- fix: 1) land the 05:08 fix-2, break the deterministic re-entry, since two battle-action fixes (first_usable_slot, the choosing(b) gate) have each shipped green offline and failed to clear this live double: the run resumes states/route101.ss and walks to [24,0] into the identical encounter every launch, so on 2+ consecutive stall exits at the same map+encounter, reroute around [24,0] or desync the RNG before relaunch (run-grind.sh resume / planner, not the battle action path). 2) ctrl 0x83aa958 is still the controller the WEDGE reports after the choosing(b) gate, so battler 2's chooser at the wedge is a func outside PLAYER_CHOOSE_ACTION_FUNCS; dump the live gBattlerControllerFuncs at the freeze and register that func id, same as the [4,2] ALT
- status: open

### 2026-11-01 02:07 ET
- symptom: expected the party (6/6, all L57-60 over the cap-42 grind floor) to explore toward the Sootopolis gym 8 at [15,0] and start the ice approach; actual the executor cannot path the [15,1]->[15,0] thin-ice puzzle, so the frontier reads gated at [15,1], it demotes to a grind on the ice gym floor which has no grass, raises grind blocked after GRASS_WAIT_TICKS, and the supervisor relaunches the identical state every ~35s. The prior open entry's [24,0] Route 111 double wedge is no longer on stream; the game has advanced to Sootopolis, so that defect could not be co-verified this run and its status is left as-is
- receipts: status.json map [15,1] tile [7,19] battles 0 wins 0 exit_reason 'grind blocked: no reachable grass on [15, 1] from (7, 19)', lead Stoutland L58 197/197, unchanged across a 165s re-sample (ts 1793516938 -> 1793517039); journal runs 108-116 at ~35s cadence `goal now {'mode': 'grind', 'map': [15, 1], 'cap': None}, recommend {'mode': 'explore', 'to': [15, 0], 'cap': None} because at cap 42, no gym reachable over world edges` then `goal written {'mode': 'explore', 'to': [15, 0], 'cap': None}` then next run `grind blocked: no reachable grass on [15, 1]`; stream title "grinding on Sootopolis City", player parked on thin ice at the gym entrance, LOG "stopped, grind blocked: no reachable grass on [15, 1] from (7, 19)" then "explore frontier gated at [15, 1], grinding toward [15, 1]" repeated, 0/0 won 0 caught
- fix: 1) the gym approach crosses the Sootopolis thin-ice puzzle the grid nav treats as impassable, so explore hands off to demote_to_grind (play.py:2107) on a grassless floor and _reachable_grass_map returns nothing, pinning target back to [15,1]; land the recorded press-route across the cracking ice (probe_sootopolis_bfs.py, the Sootopolis ice-route workflow) into PRESS_ROUTES keyed on the Sootopolis gym map so Errands.follow_route replays it the way Fortree's rotating gates are replayed 2) until the route lands, add [15,1] to an explore-gated hold set so the planner stops regenerating a grassless grind on it and idles the frame instead of the ~35s relaunch churn
- status: applied, fix 2. Fix 1 still open: no sootopolis_route.json was ever written (fortree/lavaridge both have one), so the press-route cannot land into PRESS_ROUTES until the bounded BFS probe (probe_sootopolis_bfs.py) runs to completion, a separate route job, not this watch. Fix 2 landed at the root of the churn: extracted the grind grass-blocked tail into play.py Player._grind_no_grass(here, x, y); when the wait crosses GRASS_WAIT_TICKS it now checks _reachable_grass_map(here), and when that is None (every reachable map grassless too, the [15,1] gym floor behind the thin-ice gate) it resets grass_waits and idles with run(60) instead of raising GoalExit, so the supervisor stops relaunching the identical stall every ~35s and the stream holds. The exit stays for the Route-104 case where a reachable grass map exists, so re-planning there still grinds elsewhere. test_grind_hold.py red-first (old unconditional raise exits on the None case; 3 cases: holds when all-grassless, exits when a grass map is reachable, counts a sub-threshold transient tick). Offline gate test_*.py 69 passed, grind smoke executor_holds_grind_when_frontier_gated OK. Ships on the next executor relaunch, which imports the edited play.py.
