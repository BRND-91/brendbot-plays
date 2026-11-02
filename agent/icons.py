"""Party-menu icons and type icons out of the ROWE ROM, as the game draws them: the first 32x32
frame of gMonIconTable under the palette gMonIconPaletteIndices picks from gMonIconPaletteTable,
and each type's 32x14 badge out of the summary screen's move-type sheet under the palette
sMoveTypeToOamPaletteNum assigns it, written as PNGs w/ colour 0 transparent, plus a stylesheet
naming each type's badge colour.

    icons.py OUT_DIR    renders OUT_DIR/icons/<species>.png, OUT_DIR/types/<Type>.png, OUT_DIR/types/types.css

The offsets were found by scanning the ROM for the tables' byte signatures: the icon table is the
one run of pointers 0x400 apart (two 32x32 frames each), the palette table carries tags
0xDAC0-0xDAC5, the type sheet is the {ptr, 0x1800, 0x7532} sprite sheet struct, and the palette
map follows that sheet's sprite template.
"""
import os
import struct
import sys
from collections import Counter

from PIL import Image

import rowe_rom
from sprites import TILE_BYTES, lz77

ICON_TABLE = 0xF5CA0C
ICON_PAL_INDEX = 0xF5F874
ICON_PAL_TABLE = 0xF60410
ICON_COUNT = rowe_rom.SPECIES_COUNT
ICON = 32
TYPE_GFX = 0x1AEF2E0
TYPE_PAL = 0x1AEFD1C
TYPE_PAL_MAP = 0x1050054
TYPE_W, TYPE_H = 32, 16       # 4x2 tiles per type on the sheet
TYPE_ART = (0, 1, 32, 15)     # the badge fills rows 1-14, the first and last row of the cell are clear
TYPE_TILES = 8
OAM_PAL_BASE = 13             # the map names OAM palettes 13-15, the sheet's three in order


def colours(raw: bytes) -> list:
    return [((c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3)
            for c in struct.unpack_from(f"<{len(raw) // 2}H", raw)]


def paint(tiles: bytes, width: int, height: int, rgb: list) -> Image.Image:
    """4bpp tiles in 1D OBJ order onto an RGBA canvas, colour 0 transparent."""
    im = Image.new("RGBA", (width, height))
    px = im.load()
    per_row = width // 8
    for t in range(per_row * (height // 8)):
        tx, ty = (t % per_row) * 8, (t // per_row) * 8
        for y in range(8):
            for x in range(8):
                byte = tiles[t * TILE_BYTES + y * 4 + x // 2]
                idx = byte & 0xF if x % 2 == 0 else byte >> 4
                px[tx + x, ty + y] = (*rgb[idx], 0 if idx == 0 else 255)
    return im


def icon(species_id: int) -> Image.Image | None:
    """The species' first icon frame, None for a slot the table leaves null."""
    if not 0 <= species_id < ICON_COUNT:
        raise ValueError(f"species id out of range: {species_id}")
    rom = rowe_rom._rom()
    ptr = struct.unpack_from("<I", rom, ICON_TABLE + species_id * 4)[0]
    if not ptr:
        return None
    off = ptr - rowe_rom.ROM_BASE
    pal = struct.unpack_from("<I", rom, ICON_PAL_TABLE + rom[ICON_PAL_INDEX + species_id] * 8)[0] - rowe_rom.ROM_BASE
    return paint(rom[off:off + ICON * ICON // 2], ICON, ICON, colours(rom[pal:pal + 32]))


def type_icons() -> dict:
    """{type name: 32x14 badge} for every type in TYPE_NAMES."""
    rom = rowe_rom._rom()
    tiles = lz77(rom, TYPE_GFX)
    pals = colours(lz77(rom, TYPE_PAL))
    out = {}
    for t, name in enumerate(rowe_rom.TYPE_NAMES):
        pal = pals[(rom[TYPE_PAL_MAP + t] - OAM_PAL_BASE) * 16:][:16]
        im = paint(tiles[t * TYPE_TILES * TILE_BYTES:(t + 1) * TYPE_TILES * TILE_BYTES], TYPE_W, TYPE_H, pal)
        out[name] = im.crop(TYPE_ART)
    return out


def badge_colour(im: Image.Image) -> str:
    """The badge's fill, the most common opaque colour, as a CSS hex."""
    counts = Counter(p[:3] for p in im.getdata() if p[3])
    r, g, b = counts.most_common(1)[0][0]
    return f"#{r:02x}{g:02x}{b:02x}"


def main() -> None:
    out = sys.argv[1]
    icons_dir, types_dir = os.path.join(out, "icons"), os.path.join(out, "types")
    os.makedirs(icons_dir, exist_ok=True)
    os.makedirs(types_dir, exist_ok=True)
    n = 0
    for sid in range(1, ICON_COUNT):
        im = icon(sid)
        if im is None:
            continue
        im.save(os.path.join(icons_dir, f"{sid}.png"), "PNG", optimize=True)
        n += 1
    rules = []
    for name, im in type_icons().items():
        im.save(os.path.join(types_dir, f"{name}.png"), "PNG", optimize=True)
        rules.append(f".t-{name} {{ --type: {badge_colour(im)}; }}")
    with open(os.path.join(types_dir, "types.css"), "w") as f:
        f.write("\n".join(rules) + "\n")
    print(f"{n} icons in {icons_dir}, {len(rules)} type badges in {types_dir}")


if __name__ == "__main__":
    main()
