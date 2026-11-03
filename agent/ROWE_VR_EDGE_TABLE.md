# Group 16 (Victory Road) edge table — decode result

Answering the audit's bar: a complete, script-aware edge table for group 16 that routes
`(0,8)->(25,60)` on paper. The table is below. The audit's central call, that `world_edges` is
incomplete and the fix is a decode gap, does not hold for group 16. Every group-16 edge resolves
statically from header warps. The break is in-map traversal, not graph topology.

## The edge table (all 15 group-16 maps + the city and the two League rooms)

Source: `rowe_rom.map_warps` / `map_connections` / `world_edges`. All group-16 maps are indoor and
carry zero overworld connections; the entire VR graph is header warps. No warp in group 16 is a
MAP_DYNAMIC `(127,127)` target, so nothing here needs script decode.

```
map        dim      warps (tile -> dest)                                       world_edges
(16,0)   13x14   (6,13)->(16,9)  (6,2)->(16,5)                               {(16,5),(16,9)}
(16,1)   13x14   (6,13)->(16,5)  (6,2)->(16,6)                               {(16,5),(16,6)}
(16,2)   13x14   (6,13)->(16,6)  (6,2)->(16,7)                               {(16,6),(16,7)}
(16,3)   13x14   (6,13)->(16,7)  (6,2)->(16,8)                               {(16,7),(16,8)}
(16,4)   13x13   (6,12)->(16,8)  (6,2)->(16,11)                              {(16,8),(16,11)}
(16,5)   11x13   (5,12)->(16,0)  (5,2)->(16,1)  (4,12)/(6,12)->(16,0)        {(16,0),(16,1)}
(16,6)   11x13   (5,12)->(16,1)  (5,2)->(16,2)  (4,12)/(6,12)->(16,1)        {(16,1),(16,2)}
(16,7)   11x13   (5,12)->(16,2)  (5,2)->(16,3)  (4,12)/(6,12)->(16,2)        {(16,2),(16,3)}
(16,8)   11x34   (5,33)->(16,3)  (5,2)->(16,4)                               {(16,3),(16,4)}
(16,9)   11x13   (5,12)->(16,10) (5,2)->(16,0)  (4,12)/(6,12)->(16,10)       {(16,0),(16,10)}
(16,10)  19x12   (9,11)/(10,11)->(0,8)  (9,1)/(10,1)->(16,9)  (1,7)->(16,14) {(0,8),(16,9),(16,14)}
(16,11)  15x17   (7,11)->(16,4)                                             {(16,4)}
(16,12)  14x9    (7,8)/(6,8)->(0,8)  (1,6)->(16,13)                          {(0,8),(16,13)}
(16,13)  14x10   (1,6)->(16,12)  (5,1)->(25,60)  (9,1)->(25,25)              {(16,12),(25,25),(25,60)}
(16,14)  14x10   (1,6)->(16,10)  (5,1)->(25,60)  (9,1)->(25,25)              {(16,10),(25,25),(25,60)}
(0,8)    40x80   (18,5)->(16,10) (27,48)->(16,12) (18,41)/(18,27)->(24,43)   {(0,43),(16,10),(16,12),(24,43)}  + conn W (0,43)
(25,60)  15x12   (7,11)/(8,11)->(127,127) DYNAMIC                            {(127,127)}
(25,25)  12x9    (5,8)/(6,8)->(127,127) DYNAMIC                              {(127,127)}
```

## The three paper routes the graph expresses

1. **Via (16,10), the real forward path.** `(0,8) --(18,5)--> (16,10) --(1,7)--> (16,14) --(5,1)--> (25,60)`.
   Three warps. The League exit `(16,14)` is a direct warp off `(16,10)`, not through the dive chain.
2. **Via (16,12), a dead-end spur.** `(0,8) --(27,48)--> (16,12) --(1,6)--> (16,13) --(5,1)--> (25,60)`.
   The graph lists it, but `(16,13)` entered from `(16,12)` is a closed basin (below), so this leg
   cannot go forward.
3. **The dive chain is a side loop, not the League path.** `(16,9)->(16,0)->(16,5)->(16,1)->(16,6)->
   (16,2)->(16,7)->(16,3)->(16,8)->(16,4)->(16,11)` hangs off `(16,10)` and ends in the side room
   `(16,11)`. It never touches `(16,13)`/`(16,14)` or the League. It is an item/excursion loop.

## The real break — in-map traversal, not topology

The audit guessed a missing edge or a one-way tile nav can't cross. The warp tiles are plain floor
on isolated elevation shelves, and the edge table that names them is correct.

- In `(16,13)` the forward warps `(5,1)` and `(9,1)` are behavior NORMAL (`0x00`), not ledges or
  dive tiles. `reachable((5,1))` is 3 tiles, `{(4,2),(5,1),(5,2)}`; `(9,1)` is a separate region
  again; the entry `reachable((2,6))` is 77 tiles and holds neither. `path((2,6),(5,1))` is `None`
  both directions. The warp shelf reads at elevation 6-7 against the entry pool, so the surfer
  can't dismount up onto it.
- The two dive spots in `(16,13)` (behavior `0x14`, at `(8,4)`/`(12,4)`) are also outside the
  entry basin, and `(16,13)` carries no dive connection and no `setdivewarp` script edge, so the
  dive leads nowhere decodable and isn't the way up either.
- So `(16,13)` from the `(16,12)` side is forward-impassable. It is the return leg
  (League -> `(16,13)` -> `(16,12)` -> the city fall), which is why the executor correctly blocked
  it as a dead end.

## The one open problem — reach (16,10)

`(16,10)`'s city door is `(0,8)` tile `(18,5)`, behavior NORMAL. It sits in a northern region of
`(0,8)` disconnected from the shore-reachable area even with the Waterfall climb. The city's
reachable set with climb is 414 tiles topping out at the fall edge `y~60`; the `(18,5)` door is at
`y=5`, and the ENDGAME_PLAN decode has the fall-top surf topping out near `y=43`, short of it. The
24 waterfall tiles at `y=60`/`y=67` are the Ever Grande fall. Reaching `(18,5)` is a terrain-routing
problem up the north of the city, not a graph edge.

## Corrections to the audit and the next step

- `world_edges` keeps all connection directions (DIVE/EMERGE included); group 16 simply has none,
  so nothing was dropped. The script-aware decode the audit ordered (setdynamicwarp / setescapewarp)
  changes nothing in group 16 because there are zero dynamic warps here. It is a group-25 (E4)
  concern, which is Phase 2.
- The paper route that threads is `(0,8) -> (16,10) -> (16,14) -> (25,60)`, on one assumption not
  yet measured: that `(16,14)` entered from `(16,10)` lands on the warp-shelf side rather than in a
  closed basin like `(16,13)`. Confirming it needs a `(16,10)` fixture, which needs the city ->
  `(16,10)` crossing solved first.
- Nav primitives the audit named still earn their place for the post-League return and any
  whiteout retry (waterfall descent, dive-as-map-change), but they are not what unblocks the
  forward route; the forward route is blocked on the `(0,8)` -> `(18,5)` terrain crossing alone.

Restart stays held. Evidence: `rowe_rom` static dumps and `nav.Grid` region/path on
`states/fixtures/vr_16_13.ss`, `evergrande_0_8.ss`, `vr_entry_16_12.ss`.
