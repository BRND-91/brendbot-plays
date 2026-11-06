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
