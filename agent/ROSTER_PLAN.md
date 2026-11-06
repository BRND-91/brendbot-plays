# ROWE target roster

The six the run builds toward from the first route, so the party that reaches the League is the party
that beats Steven and Red, instead of six L100s raised on whatever the catch policy met. Every number
here is read off the ROM through `rowe_rom` and the dex encounter table (`dexgen/species.json`), scored
by `play.matchup` over the 23 builds the run fights (8 Hoenn leaders at their badge builds, 8 Sevii
leaders, the five League rooms, Steven, Red). Rerun the scoring w/ `/tmp/rowe-roster/six.py` shape:
`matchup` summed over builds, foes no member hits super effectively, `wanted_types`.

## The six

| Line | Final | Types | Catch | Evolves | L100 Spe / Atk / SpA | Mega stone |
|---|---|---|---|---|---|---|
| Ralts | Gardevoir | Psychic/Fairy | Route 102 L4 land | 20, 30 | 196 / 166 / 286 | Gardevoirite, Tate & Liza, 11 badges |
| Magikarp | Gyarados | Water/Flying | Old Rod, 42 waters incl. Petalburg City and Dewford | 20 | 198 / 286 / 156 | Gyaradosite, Juan, 11 badges |
| Electrike | Manectric | Electric | Route 110 L12 land | 26 | 246 / 186 / 286 | Manectite, Wattson, 11 badges |
| Riolu | Lucario | Fighting/Steel | Route 112 L16 land | 30 (ROWE level row) | 216 / 256 / 266 | Lucarionite, Scorched Slab item |
| Trapinch | Flygon | Ground/Dragon | Route 111 L20 land | 35, 45 | 236 / 236 / 236 | none |
| Houndour | Houndoom | Dark/Fire | Safari Zone L25 or Route 121 L28 land | 24 | 226 / 216 / 256 | Houndoomite, Flannery, 11 badges |

Assembled by badge 3 (caps 16, 21, 26, 29). Four of the six catch under the start cap, Trapinch
after badge 1, Houndour after badge 2. Every evolution is a level row the planner projects
(`rowe_rom.species_at_level`, methods 4 and 39), so no stone, trade or friendship errand is needed.
Every encounter is land or rod; the hidden-grass method (Gible, Bagon, Beldum, Jangmo-o, Deino) needs
the Shaking Tool, which the executor does not drive, so those lines are out until it does.

## Why these six

Scored against the current L100 party (Vileplume, Seaking, Golduck, Greedent, Stoutland, Pawmot):

| | matchup over 23 builds | foes no member hits SE | wanted types |
|---|---|---|---|
| target six | 536 | 1 of 121 | none |
| current six | 344 | 41 of 121 | Fighting, Poison, Bug, Ghost, Electric, Psychic, Dragon |

Steven, who hits each of his six super effectively w/ STAB alone: Magnezone by Lucario, Houndoom,
Flygon; Excadrill by Lucario, Houndoom, Flygon, Gyarados; Dracovish by Gardevoir, Flygon; Aegislash by
Houndoom, Flygon; Diancie by Lucario, Flygon, Gyarados; Metagross by Houndoom, Flygon. The current six
hit Dracovish, Aegislash and Metagross w/ nothing. Speed at L100 runs 196 to 246 across the six against
the current party's 126 to 268, and Flygon and Gyarados take Excadrill's Ground for nothing.

Alternates, each scored lower: Ludicolo for Gyarados (488 total, loses Brawly and Falkner); Garchomp
for Flygon (hidden grass only); Camerupt for Houndoom (Spe 116); Starmie for Gyarados (no mega).

## What the executor has to learn

1. `planner.recommend` carries a roster goal: the next missing line's earliest catch map at or under the
   cap, ahead of the gym when the party has an open slot or a non-roster member above the floor.
2. `catch.Ledger.wants` says yes to a roster species on sight, outside the ball reserve rule and the
   `LEVEL_CUTOFF`; `play.Player.catch_plan` already routes through it.
3. `fill_party` and `do_pc_swap` prefer a boxed roster line over the matchup pick, and a roster member
   is never the flex slot once it is in.
4. `tm_assignments` scores the roster's final forms, so a TM taught at L20 is one the L100 form keeps.
5. Mega: the items pocket reader (`SB1_BAG_ITEMS`, 80 slots), a give-item errand for the stone, and the
   START press in the move menu once the Mega Bracelet is in the key items (11 badges).
6. The current save keeps its six to the end; the roster applies from the next 0-badge start
   (`states/fixtures/route101.ss`).

## Economy heuristic for a fresh run

A 0-badge start holds the starting purse, 0 BP, and the skill points its trainer level grants, w/
every mon at 0 IVs until the stat boosts are bought. The rules below key on balances as they accrue,
never on a fixed amount. The live save that motivated them (320658 money, 893 BP, 116 skill points
unspent, 30 IVs, all six at 510 EVs in grind-random spreads, Golduck w/ 202 Atk and 22 Spe on a SpA
attacker) shows what a run without them ends up holding. ROM prices via `rowe_rom.item_price`; counters
via the guide db (`t_frequently_asked_questions`, `t_trainer_skills`, `t_new_abilitiesitems`).

### Skill points, in priority order

1. The six stat boosts to their cap, Speed and the larger attacking stat first, then HP and the
   defences (the spender buys round-robin today, which puts Def and SpD ahead of the second Spe point).
2. EVs Changes to its cap, the EV editor's ceiling, so each member's spread is set at its evolution.
3. XP Boost - Pokémon, levels are the long pole on every leg.
4. Gold Rush, then Bargain (1% off per level), both pay for the held items below.
5. Max PP Boost, Sniper Ball, Loot Boost, in that order, w/ whatever is left.

Only the stat boosts have a stored cost, 3 points a level (`rowe_symbols.SKILL_STAT_COST`). No skill
cost table exists on disk (no ROWE source checkout, the guide tab carries descriptions only), so
`spend_skill_points` learns the other costs from the point delta on each buy and logs them.

### Money and BP, by balance

| Balance | Buy |
|---|---|
| money under 1000 | nothing, the reserve |
| money over 5000 w/ a roster line as the catch target | Ultra Balls (600) over Poké Balls; the thrower picks the strongest ball held |
| money over 20000 w/ a roster pre-evolution 10+ levels from its row | Exiolite (4500) so it fights at its final form's base stats |
| money over 60000, before Ever Grande | one held item per member by role, Life Orb 9000, Choice Scarf / Band / Specs 10000, Focus Sash 5000, Leftovers 2000, Expert Belt 2000, Assault Vest 10000 |
| BP over 10 per caught roster line | a Nature Mint at Oldale's Battle Mart, 10 BP |
| BP left after the mints | Ability Capsule, then Patch, Oldale's Battle Mart |

Natures: Timid Gardevoir, Manectric, Houndoom; Jolly Gyarados, Lucario, Flygon. Abilities: Moxie
Gyarados, Lightning Rod Manectric, Flash Fire Houndoom, Justified Lucario. HP restores and cures keep
their existing floors. Vitamins (900) only matter under 510 EVs, and a spread set through the EV
editor makes them moot.

### Loot and menus

Visible item balls on the current map are already picked up every tick (`collect_step`) outside a
heal, a Mart trip, a scene, the League leg and a boss room. Not driven yet: an item ball on another
map as a planner goal (TM26 Earthquake in Seafloor Cavern), hidden items through the Dowsing Machine,
hidden-grass encounters through the Shaking Tool. Menu cursors take the short way round since
`Errands.menu_step`; the start menu and the skills list no longer lap DOWN to reach a row one above.

### Levers, by item

| Lever | Cost | Where | What it buys the roster |
|---|---|---|---|
| Ultra Ball | 600 (Great 300) | any Mart | 2x catch rate on the roster lines; the thrower spends Poké Balls only today |
| EVs Changes skill | skill points | Trainer Skills row, then the summary screen | manual EV spreads, 252 Spe and the attacking stat per member, in place of the grind's random 510 |
| XP Boost, Gold Rush, Bargain | skill points | Trainer Skills | faster levels, more money, 1% off per level at every counter |
| Nature Mint | 10 BP | Oldale Battle Mart | Timid Gardevoir, Manectric, Houndoom; Jolly Gyarados, Lucario, Flygon |
| Ability Capsule / Patch | BP (ROM money price 5000 / 10000) | Oldale Battle Mart | Moxie Gyarados, Lightning Rod Manectric, Flash Fire Houndoom, Justified Lucario |
| Exiolite | 4500 | Oldale Battle Mart, Devon Corp 1F | a pre-evolution fights at its final form's base stats until its level row |
| Life Orb 9000, Choice Scarf / Band / Specs 10000, Focus Sash 5000, Leftovers 2000, Expert Belt 2000, Assault Vest 10000 | money | counter not checked, Lilycove Dept Store and Eight Island Battle Mart per the guide | one held item per member for the League and the bosses |
| Power items | 5000 | Lilycove Dept Store, Eight Island Battle Mart | 20 EVs per KO while held, the fallback when the EV editor is not driven |
| Vitamins | 900 | Mart | moot at 510 EVs; a reassigned spread goes through the EV editor |

Executor pieces, none started. `catch_plan` and `throw_ball` choose the strongest ball held
(`catch_chance` takes a ball multiplier no caller passes); `shopping_list` adds Ultra Balls and the
held items by balance; `spend_skill_points` buys in the priority order above and logs each skill's
cost; a BP counter errand at Oldale; a give-item errand from the bag; the summary-screen EV editor; a
use-item errand for mints and capsules; an item-ball planner goal for a named TM on another map.
