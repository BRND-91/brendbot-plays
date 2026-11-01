"""rowe_rom.metatile_behavior resolves a layout cell's behavior through the right tileset table.
ROWE packs 12-bit metatile ids w/ 0x800 primary metatiles, so the Center floor (secondary id
0x842) is plain floor and Route 110's water reads as water; a wrong primary count sends every
id past it into the secondary table at the wrong offset and the Center floor reads as a
waterfall, which left the walk unable to reach the nurse from the door mat."""
import nav
import rowe_rom
import rowe_symbols as S

CENTER = (8, 4)
CENTER_FLOOR = 0x842
ROUTE = (0, 19)
TALL_GRASS = 0x00D


def main() -> None:
    beh = rowe_rom.metatile_behavior(*CENTER)
    assert beh(CENTER_FLOOR) == 0x00, f"Center floor behavior {beh(CENTER_FLOOR):#x}, expected plain floor"
    w, h, cells = rowe_rom.map_cells(*CENTER)
    wet = [c & S.GRID_ID_MASK for c in cells if beh(c & S.GRID_ID_MASK) in nav.WATER_BEHAVIORS]
    assert not wet, f"Center cells reading as water: {[hex(i) for i in wet[:6]]}"

    beh = rowe_rom.metatile_behavior(*ROUTE)
    assert beh(TALL_GRASS) == 0x02, f"tall grass behavior {beh(TALL_GRASS):#x}"
    w, h, cells = rowe_rom.map_cells(*ROUTE)
    surf_cells = [c for c in cells if (c >> S.GRID_ELEVATION_SHIFT) == S.SURF_ELEVATION]
    assert surf_cells, "fixture lost its water"
    water = sum(1 for c in surf_cells if beh(c & S.GRID_ID_MASK) in nav.WATER_BEHAVIORS)
    assert water * 10 >= len(surf_cells) * 9, f"only {water}/{len(surf_cells)} surf-elevation cells read as water"
    print("test_metatile_behavior: ok")


if __name__ == "__main__":
    main()
