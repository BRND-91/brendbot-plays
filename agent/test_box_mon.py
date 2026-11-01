"""box_mon decodes a storage slot off the party offsets, and level_from_exp reads the growth table
the way the game levels a mon: Pikachu is medium-fast (L10 at 1000), Bulbasaur medium-slow (L20 at 5460)."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rowe_rom
import rowe_symbols as S
from rowe_state import box_mon


def encode(name: str) -> bytes:
    return bytes(0xBB + ord(c) - ord("A") for c in name).ljust(10, b"\xff")


THUNDER_SHOCK, QUICK_ATTACK, GROWL, THUNDER_WAVE = 84, 98, 45, 86


def raw(personality: int, ot_id: int) -> bytes:
    buf = bytearray(S.SIZEOF_BOX_POKEMON)
    struct.pack_into("<I", buf, S.MON_PERSONALITY, personality)
    struct.pack_into("<I", buf, S.MON_OT_ID, ot_id)
    buf[S.MON_NICKNAME:S.MON_NICKNAME + 10] = encode("PIKA")
    struct.pack_into("<I", buf, S.MON_MOVE1_EXP, (1000 << 10) | THUNDER_SHOCK)
    struct.pack_into("<I", buf, S.MON_MOVES_2_3, QUICK_ATTACK | (GROWL << 10) | (70 << 22))
    struct.pack_into("<I", buf, S.MON_SPECIES_MOVE4, 25 | (THUNDER_WAVE << 17))
    buf[S.MON_EVS:S.MON_EVS + 6] = bytes([4, 8, 12, 16, 20, 24])
    buf[S.MON_ABILITY_NUM] = 2 << S.ABILITY_NUM_SHIFT
    return bytes(buf)


def main() -> None:
    m = box_mon(raw(0x12345678, 0x9ABCDEF0), 31)
    assert (m.species, m.nickname, m.experience) == (25, "PIKA", 1000), m
    assert (m.box, m.position) == (1, 1), (m.box, m.position)
    assert m.moves == (THUNDER_SHOCK, QUICK_ATTACK, GROWL, THUNDER_WAVE), m.moves
    assert m.evs == (4, 8, 12, 16, 20, 24), m.evs
    assert m.ability_num == 2, m.ability_num
    assert m.nature == 21, "0x12345678 % 25"
    assert m.shiny, "0x9ABC^0xDEF0 equals 0x1234^0x5678, xor 0 is under 8"
    assert not box_mon(raw(0, 0x9ABCDEF0), 0).shiny, "xor 0x444C is over 8"

    assert rowe_rom.level_from_exp(25, 1000) == 10
    assert rowe_rom.level_from_exp(25, 999) == 9
    assert rowe_rom.level_from_exp(1, 5460) == 20
    assert rowe_rom.level_from_exp(1, 5459) == 19
    assert rowe_rom.level_from_exp(1, 0) == 1
    assert rowe_rom.level_from_exp(1, 10 ** 7) == 100
    print("ok")


if __name__ == "__main__":
    main()
