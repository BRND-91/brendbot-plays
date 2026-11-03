# Cell-diff instrument (build after the live-save acceptance drive lands)

On every map load, diff the live grid cells against static `map_cells`.
Each mismatch is a script-managed tile (a `setmetatile` in that map's ON_LOAD
script, keyed on a flag). Log each mismatch with that flag check.

- Source correction: (7,55) static behavior 0x60 (door) vs live rock => (24,68)
  is a sealed entrance, not a dead stub.
- Output: the game's gate list, without border-walker probing. Would have named
  the League ridge and this One Island entrance up front.
- Depends on: acceptance drive (task 20261103T160720-76f7ff) landing first.
