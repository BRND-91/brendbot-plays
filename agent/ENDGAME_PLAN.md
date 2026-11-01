<!-- fires: 7 / 8 -->
# ROWE endgame path plan

The decode-and-route ledger for everything past badge 8: Sootopolis Gym (Juan) through Ever
Grande City, Victory Road, the Elite Four (Sidney, Phoebe, Glacia, Drake) and Champion Wallace.
An hourly cron advances this one segment per fire. Sootopolis Gym stays the autoplayer's primary
goal until its badge flag flips; only after badge 8 does a fire extend the live goal past it.

Decode each segment against the ROM, not a walkthrough: maps and warps from
`rowe_rom.world_edges()` / `rowe_rom.map_warps(g, n)` / `rowe_rom.map_cells(g, n)`, trainer teams
from `rowe_rom.leader_team(name, badges=8)`, puzzle tiles from `rowe_rom.metatile_behavior(g, n)`.
Interpreter `/opt/brendbot/rowe-agent/.venv/bin/python`. Code map is the `rowe` skill.

Status values: undecoded, decoded (route + trainers written here), enabled (live planner targets it).

## Segment 1 — Sootopolis Gym 8, Juan  [status: decoded]
- Maps: puzzle floor (15, 0), lower fall floor (15, 1). Entry warps (8, 25)/(9, 25) <-> Sootopolis City (0, 7); (11, 22) links (15, 0)<->(15, 1).
- Mechanic: thin-ice crack puzzle, behavior 0x26, 64 tiles in three fields (rows 6-9, 12-14, 17-19) joined by column-8 corridors at (8, 4/5), (8, 10/11), (8, 15/16). Step each ice tile once; a second step falls to (15, 1). No field move inside.
- Leader: Juan object at (8, 2), stand (8, 3). Team via `leader_team("Juan", badges=7)`. Level cap 42.
- Route: `probe_sootopolis_bfs.py` BFS writes `gym_routes.json` key "15,0" (task 20261101T060100-da98bc). `gym_step` replays it through `Errands.follow_route`.

## Segment 2 — Sootopolis City to Ever Grande City  [status: enabled]
- Route (router next-hop chain (0,7)->(0,8)): Sootopolis City (0,7) --dive--> underwater Sootopolis (24,5) --warp(9,8)--> underwater Route 126 (0,51) --emerge--> Route 126 (0,41) --E--> (0,42) --E--> (0,43) --E--> Ever Grande City (0,8). The earlier east-swim decode through (0,52)/(0,53)/(0,43) was wrong: (0,51) leaves by its EMERGE connection (dir 6, offset 0) up to (0,41), not by an east border.
- Emerge is a yes/no dialogue: B opens "Light is filtering down from above. Would you like to surface?", A answers YES on the default cursor. take_dive(EMERGE) now sends B, waits for the two-line prompt, then A; the pre-fix single B left the prompt open and read back as stuck. Candidates are the reachable seabed minus the back-warp tile (45,65) and the two MetatileBehavior_IsUnableToEmerge behaviours 0x19 (MB_NO_SURFACING) and 0x2A (MB_SEAWEED_NO_SURFACING). The warp landing (45,66) is behaviour 0x00 and surfaces to (0,41) at the same local coords.
- Maps: (24,5) and (0,51) MAP_TYPE_UNDERWATER (swim leg); (0,41)/(0,42)/(0,43) Route 126-128 surface water; (0,8) Ever Grande City. The two gates (0,7)->(24,5) and (24,5)->(0,51) were cleared from states/map_graph.json (backup states/map_graph.json.pre-gateclear) so the router threads the crossing.
- Field moves: Dive, Surf, Waterfall, all in the bag at 8 badges. Dive submerges at the crater, the warp carries to (0,51), the emerge surfaces at (0,41); Surf runs the Route 126-128 water east to (0,8). No land encounter table on any node, so wild hits are water slots only. Level cap at 8 badges is 45.

## Segment 3 — Victory Road  [status: decoded]
- Maps: group 16, two Ever Grande City (0,8) doors in. Entrance hall (16,10) 19x12 warps (9,11)/(10,11)<->(0,8); exit hall (16,12) 14x9 warps (6,8)/(7,8)<->(0,8). Dive climb chain off (16,10): (16,10)--(9/10,1)-->(16,9)-->(16,0)-->(16,5)-->(16,1)-->(16,6)-->(16,2)-->(16,7)-->(16,3)-->(16,8, the long 11x34)-->(16,4), side room (16,11) 15x17 off (16,4). League exits: (16,14) reached from (16,10) at (1,7), (16,13) reached from (16,12) at (1,6); each warps (5,1)->League (25,60) and (9,1)->League (25,25), the group-25 E4 rooms (segments 4-8).
- Mechanic: water dungeon, not boulders. Deep-water dive corridors (behavior 0x14, diveable) carry the climb: 21 dive tiles each on (16,5)/(16,6)/(16,7)/(16,9), 84 on the long (16,8); scattered Waterfall tiles (0x13) on (16,11)/(16,13)/(16,14); entrance hall (16,10) is 82 tiles of behavior 0x20 floor. Field moves: Surf + Dive + Waterfall, all in the bag at 7 badges. No thin-ice, no strength/rock-smash boulders, no land wild table on any node (water and dive slots only).
- Trainers: object templates at (16,10) [6, movement-8 at (4,2)/(8,2)/(11,2)/(16,2)], (16,12) [5], (16,13)/(16,14) [4 each], (16,4) [3], and one each on (16,0)-(16,3)/(16,11). Teams sit behind each map's `trainerbattle` script, which the ROM readers here do not parse; lift rosters and levels from the live battle log on first traversal or a script-table parse, not fabricated.
- Level cap: 45 (the badge-8 cap from segment 2, carries through the League approach).

## Segment 4 — Elite Four, Sidney  [status: decoded]
- Map: group 25, Sidney's Dark-specialist E4 chamber. Best static match (25,24), 14x9, one leader object at (9,3) movement 9, player stand (9,4). The group-25 single-leader rooms (25,24)/(25,25)/(25,26) are the E4 chambers; the exact leader-to-room binding and ordering are script-set, so confirm on first live traversal.
- Warps: two doors at (6,8)/(7,8), both dynamic (127,127) warps the room script sets, one back to the League approach and one forward to Phoebe that opens after the win. No static forward chain, the whole group-25 League uses dynamic warps (the reader limit segment 3 flagged for the League scripts); the live door targets get lifted on traversal, not fabricated.
- Team: `leader_team("Sidney", badges=8)` returns (658 Greninja L39), (635 Hydreigon L40), (319 Sharpedo L41), (687 Malamar L42), (920 Lokix L43), (248 Tyranitar L44 ace). All Dark; `leader_build` evolves none, final forms already. Base level 39, ace +5.
- Field moves: none, indoor walk-only. Level cap 45 (the badge-8 cap carried from segment 2).

## Segment 5 — Elite Four, Phoebe  [status: decoded]
- Map: group 25, Phoebe's Ghost-specialist E4 chamber. Best static match (25,25), 12x9, one leader object at (9,6) movement 9, player stand (9,7). The same reader reproduced segment 4's Sidney room (25,24) leader (9,3) movement 9 exactly, so the single-leader-chamber decode carries; the leader-to-room binding is script-set, confirm on first live traversal.
- Warps: two doors at (5,8)/(6,8), both dynamic (127,127) warps the room script sets, one back toward the Sidney chamber and one forward to Glacia that opens after the win. No static forward chain, the group-25 League uses dynamic warps (the reader limit segment 3 flagged), live door targets get lifted on traversal, not fabricated.
- Team: `leader_team("Phoebe", badges=8)` returns (681 Aegislash L39), (937 Ceruledge L40), (623 Golurk L41), (442 Spiritomb L42), (1568 L43, types Fire/Ghost, id beyond the national dex so a Rowe-added form, name unresolved), (354 Banette L44 ace). Every member carries Ghost (type id 7, confirmed by pure-Ghost Banette 7/7 and Ghost/Dark Spiritomb 7/17); `leader_build` evolves none, final forms already. Base level 39, ace +5, same shape as Sidney.
- Field moves: none, indoor walk-only. Level cap 45 (the badge-8 cap carried from segment 2).

## Segment 6 — Elite Four, Glacia  [status: decoded]
- Map: group 25, Glacia's Ice-specialist E4 chamber, (25,26) by the chamber order segment 4 fixed ((25,24)/(25,25)/(25,26) the E4 rooms). 20x10, one leader object at (10,5) movement 8, player stand (10,6) directly south. Single-leader chamber, same shape the Sidney (25,24) and Phoebe (25,25) decodes carry; the leader-to-room binding is script-set, confirm on first live traversal.
- Warps: four doors along row 9 at (8,9)/(9,9)/(10,9)/(11,9), all dynamic (127,127) the room script sets, one back toward Phoebe and one forward to Drake that opens after the win. No static forward chain, the group-25 League uses dynamic warps (the reader limit segment 3 flagged), live door targets get lifted on traversal, not fabricated.
- Team: `leader_team("Glacia", badges=8)` returns (584 Vanilluxe L39), (473 Mamoswine L40), (91 Cloyster L41), (975 L42, type Ice, id reassigned from national-dex Houndstone which is Ghost, so a Rowe form, name unresolved), (713 Avalugg L43), (460 Abomasnow L44 ace). Every member carries Ice (type id 15, confirmed by mono-Ice Vanilluxe 15/15 and Water/Ice Cloyster 11/15, Ice/Ground Mamoswine 15/4, Grass/Ice Abomasnow 12/15); `leader_build` evolves none, final forms already. Base level 39, ace +5, same shape as Sidney and Phoebe.
- Field moves: none, indoor walk-only. Level cap 45 (the badge-8 cap carried from segment 2).

## Segment 7 — Elite Four, Drake  [status: decoded]
- Map: group 25, Drake's Dragon-specialist E4 chamber, (25,27) by the chamber order segments 4-6 fixed ((25,24) Sidney, (25,25) Phoebe, (25,26) Glacia, Drake the fourth in sequence). 14x9, four doors along row 8 at (5,8)/(6,8)/(7,8)/(8,8), all dynamic (127,127) the room script sets, one back toward Glacia and one forward to Wallace that opens after the win. Discrepancy flagged: unlike the Sidney/Phoebe/Glacia rooms, each of which carries one static leader object template (9,3)/(9,6)/(10,5), (25,27) reads zero static objects, so Drake's leader is placed by the room script rather than a header template; the leader tile and player stand get lifted on first live traversal, not fabricated here. The leader-to-room binding is script-set, confirm on live traversal, same caveat segments 4-6 carry.
- Team: `leader_team("Drake", badges=8)` returns (691 Dragalge L39), (1019 Hydrapple L40), (882 Dracovish L41), (1018 Archaludon L42), (142 Aerodactyl L43), (6 Charizard L44 ace). Dragon (type id 16) on four of six, confirmed by Water/Dragon Dracovish (11,16), Grass/Dragon Hydrapple (12,16), Steel/Dragon Archaludon (8,16), Poison/Dragon Dragalge (3,16); the two fillers Aerodactyl (5,2) and ace Charizard (10,2) share Flying (id 2), no Dragon. Names map off the national-dex id, the ROM species table carries no name string. `leader_build` evolves none, final forms already. Base level 39, ace +5, same shape as Sidney, Phoebe and Glacia.
- Field moves: none, indoor walk-only. Level cap 45 (the badge-8 cap carried from segment 2).

## Segment 8 — Champion Wallace  [status: decoded]
- Map: group 25, Wallace's champion chamber, best static match (25,40), 10x10, one leader object at (5,6) movement 9, player stand (5,7) directly south. The only single-leader room past the four E4 chambers (25,24)/(25,25)/(25,26)/(25,27) and before the (25,41)+ Hall-of-Fame cluster, same single-leader-chamber shape the Sidney/Phoebe/Glacia decodes carry. The leader-to-room binding is script-set, confirm on first live traversal.
- Warps: none static, the champion chamber reads zero header warps, so entry from Drake (25,27)'s forward dynamic (127,127) door and the post-win warp to the Hall of Fame are both script-set, same dynamic-warp caveat the whole group-25 League carries (the reader limit segment 3 flagged). Live door targets get lifted on traversal, not fabricated.
- Team: `leader_team("Wallace", badges=8)` returns (1644 L39, types Electric/Water, id beyond the national dex so a Rowe-added form, name unresolved), (184 Azumarill L40, Water/Fairy), (230 Kingdra L41, Water/Dragon), (768 Golisopod L42, Bug/Water), (319 Sharpedo L43, Water/Dark), (350 Milotic L44 ace, pure Water). Every member carries Water (type id 11, confirmed by pure-Water Milotic 11/11 and Water/Dragon Kingdra 11/16, Bug/Water Golisopod 6/11, Water/Dark Sharpedo 11/17, Water/Fairy Azumarill 11/18). `leader_build` evolves none, final forms already. Base level 39, ace +5, same shape as Sidney, Phoebe, Glacia and Drake.
- Field moves: none, indoor walk-only. Level cap 45 (the badge-8 cap carried from segment 2).
