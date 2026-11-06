"""The native Seagallop multichoice composes its island rows into the EWRAM string buffers with
leading unmapped padding, so the live dump reads them back as '??????Four Island' while Cancel is a
clean ROM string. _menu_rows requiring the whole decode be letters-and-spaces dropped every padded
island row and read the list as [(8, 'Eight Island'), (9, 'Cancel')], so talk_warp could never find
'Three Island' (states/grind.log: "ferry no_row: want 'Three Island' among [(8, 'Eight Island'),
(9, 'Cancel')]"). _menu_rows now keeps the trailing letter run of each label, so every island row
reads back regardless of the padding.

Red-capability: the island names here carry the same leading padding the live rows do, which the
pre-fix whole-string filter rejected, so the equality assert returned {9: 'Cancel'} and failed
before the change."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import routines  # noqa: E402
import rowe_symbols as S  # noqa: E402

EWRAM = 0x02000000
ROM = 0x08000000


def _encode(s: str) -> bytes:
    """Game charmap, the inverse of rowe_state.decode_text: A-Z from 0xBB, a-z from 0xD5, space 0x00,
    0xFF terminator."""
    out = bytearray()
    for ch in s:
        if "A" <= ch <= "Z":
            out.append(0xBB + ord(ch) - ord("A"))
        elif "a" <= ch <= "z":
            out.append(0xD5 + ord(ch) - ord("a"))
        elif ch == " ":
            out.append(0x00)
        else:
            raise ValueError(ch)
    out.append(0xFF)
    return bytes(out)


class _Emu:
    def __init__(self, ewram: bytes, rom: dict):
        self._ew = ewram
        self._rom = rom

    def read(self, addr: int, n: int) -> bytes:
        if EWRAM <= addr < EWRAM + len(self._ew):
            off = addr - EWRAM
            return self._ew[off: off + n]
        for base, data in self._rom.items():
            if base <= addr < base + len(data):
                off = addr - base
                return data[off: off + n]
        return b"\x00" * n


def main() -> None:
    ew = bytearray(0x40000)

    # island names composed at runtime into the EWRAM string buffers; Cancel is a static ROM string.
    # 0xAC is outside every decode_text range, so it renders '?', the leading padding the live rows
    # carry ('??????Four Island'); the label pointer aims at the padding, as the dump shows it does.
    PAD = bytes([0xAC, 0xAC, 0xAC, 0xAC, 0xAC, 0xAC])
    names = ["Three Island", "Four Island", "Five Island"]
    name_ptrs = []
    pos = 0x3000
    for nm in names:
        b = PAD + _encode(nm)
        ew[pos: pos + len(b)] = b
        name_ptrs.append(EWRAM + pos)
        pos += len(b) + 1
    cancel_ptr = ROM + 0x1000
    rom = {cancel_ptr: _encode("Cancel")}

    # ListMenuItem array {const u8 *label; s32 index}: islands 0..2 then Cancel at 9, as the live dump
    arr = 0x800
    items = [(name_ptrs[0], 0), (name_ptrs[1], 1), (name_ptrs[2], 2), (cancel_ptr, 9)]
    for i, (ptr, idx) in enumerate(items):
        struct.pack_into("<Ii", ew, arr + i * 8, ptr, idx)

    # live ListMenuTemplate: items pointer at +0x00, u16 totalItems at +0x0C, the struct _menu_rows
    # reads straight instead of scanning EWRAM for the array
    tmpl = bytearray(16)
    struct.pack_into("<I", tmpl, 0x00, EWRAM + arr)
    struct.pack_into("<H", tmpl, 0x0C, len(items))
    rom[S.MENU_LIST_TEMPLATE] = bytes(tmpl)

    p = routines.Errands.__new__(routines.Errands)
    p.e = _Emu(bytes(ew), rom)
    rows = p._menu_rows()

    assert rows == {0: "Three Island", 1: "Four Island", 2: "Five Island", 9: "Cancel"}, rows

    # _menu_rows records the items pointer it read, so the no_row dump can print the slots around it.
    # Red before the change: _menu_best_off is unset and the attribute read raises.
    assert p._menu_best_off == EWRAM + arr, hex(p._menu_best_off)
    print("MENU ROWS PASS", flush=True)


if __name__ == "__main__":
    main()
