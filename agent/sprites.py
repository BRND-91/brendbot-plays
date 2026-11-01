"""Species front sprites out of the ROWE ROM, as the game draws them: the first 64x64 frame of
gMonFrontPicTable under gMonPaletteTable, or gMonShinyPaletteTable for a shiny, written as a PNG
w/ colour 0 transparent.

    sprites.py OUT_DIR    renders every species as OUT_DIR/<id>.png and OUT_DIR/<id>s.png

The table offsets were found by scanning the ROM for their entry patterns: a pic table is
{lz77 ptr, 0x800, species} per species and a palette table {lz77 ptr, species, 0}; the back
table sits at 0x3C63B4 and was told from the front one by decoding Pikachu.
"""
import io
import os
import struct
import sys

from PIL import Image

import rowe_rom

FRONT_PIC_TABLE = 0x3D9534
PALETTE_TABLE = 0x3CC084
SHINY_PALETTE_TABLE = 0x3D1D54
TABLE_LEN = 1026
SIZE = 64
TILE_BYTES = 32  # 8x8 pixels at 4 bits each
FRAME_TILES = (SIZE // 8) ** 2


def lz77(rom: bytes, off: int) -> bytes:
    """GBA BIOS LZ77 (header type 0x10): a flag byte then eight blocks, each a literal byte or a
    (length-3, displacement-1) back-reference packed into two bytes."""
    if rom[off] != 0x10:
        raise ValueError(f"not an lz77 block at {off:#x}: {rom[off]:#x}")
    size = struct.unpack_from("<I", rom, off)[0] >> 8
    out = bytearray()
    i = off + 4
    while len(out) < size:
        flags = rom[i]
        i += 1
        for b in range(8):
            if len(out) >= size:
                break
            if flags & (0x80 >> b):
                n = (rom[i] >> 4) + 3
                disp = ((rom[i] & 0xF) << 8 | rom[i + 1]) + 1
                i += 2
                for _ in range(n):
                    out.append(out[-disp])
            else:
                out.append(rom[i])
                i += 1
    return bytes(out)


def front_png(species_id: int, shiny: bool = False) -> bytes:
    if not 0 <= species_id < TABLE_LEN:
        raise ValueError(f"species id out of range: {species_id}")
    rom = rowe_rom._rom()
    pic = struct.unpack_from("<I", rom, FRONT_PIC_TABLE + species_id * 8)[0] - rowe_rom.ROM_BASE
    pal = struct.unpack_from("<I", rom, (SHINY_PALETTE_TABLE if shiny else PALETTE_TABLE) + species_id * 8)[0] - rowe_rom.ROM_BASE
    tiles = lz77(rom, pic)
    # 74 Gen 9 palettes are stored short of 16 colours (Pawmi's holds 15); the game reads the
    # missing slots off whatever follows and the sprite never indexes them, so they read black
    colours = struct.unpack_from("<16H", lz77(rom, pal).ljust(32, b"\0"))
    rgb = [((c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3) for c in colours]
    im = Image.new("RGBA", (SIZE, SIZE))
    px = im.load()
    for t in range(FRAME_TILES):
        tx, ty = (t % 8) * 8, (t // 8) * 8
        for y in range(8):
            for x in range(8):
                byte = tiles[t * TILE_BYTES + y * 4 + x // 2]
                idx = byte & 0xF if x % 2 == 0 else byte >> 4
                px[tx + x, ty + y] = (*rgb[idx], 0 if idx == 0 else 255)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def main() -> None:
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for sid in range(1, TABLE_LEN):
        for shiny, suffix in ((False, ""), (True, "s")):
            with open(os.path.join(out, f"{sid}{suffix}.png"), "wb") as f:
                f.write(front_png(sid, shiny))
    print(f"{(TABLE_LEN - 1) * 2} sprites in {out}")


if __name__ == "__main__":
    main()
