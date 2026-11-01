"""Drive a town fixture into its Mart's Buy list, save that frame as a fixture, and locate the
shop's item list in EWRAM: the u32 ROM pointer to a u16 item-id array that holds the Poké Ball
and ends in 0, with the list's u16 count beside it. Prints the EWRAM address of the pointer so
rowe_symbols can pin it.
    probe_mart.py <fixture.ss> <out_fixture.ss>"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb
import play
import rowe_rom
from routines import MART_COUNTER_TILE, Errands
from rowe_state import GameState

EWRAM = 0x02000000


def main(src: str, dst: str) -> None:
    e = eb.Emu()
    with open(src, "rb") as f:
        e.load_state(f.read())
    g = GameState(e)
    er = Errands(e, e.run)
    town = g.position()[2:]
    mart = play.SERVICE[town][1]
    print("town", town, "mart", mart, "money", g.money(), "balls", g.poke_balls(), flush=True)
    r = er.enter_warp(mart)
    print("enter mart ->", r, g.position(), flush=True)
    e.run(24, eb.KEY_UP)
    e.run(20, 0)
    print("walk ->", er.nav.walk_to(MART_COUNTER_TILE), g.position(), flush=True)
    e.run(8, eb.KEY_UP)
    e.run(8, 0)
    for _ in range(3):
        e.tap(eb.KEY_A)
        e.run(70, 0)
    with open(dst, "wb") as f:
        f.write(e.save_state())
    e.save_png(dst + ".png")
    ram = e.ewram()
    rom = rowe_rom._rom()
    for off in range(0, len(ram) - 8, 4):
        ptr, count = struct.unpack_from("<IH", ram, off)
        if not (0x08000000 <= ptr < 0x08000000 + len(rom)) or not 1 <= count <= 40:
            continue
        ids = list(struct.unpack_from(f"<{count + 1}H", rom, ptr - 0x08000000))
        if ids[-1] != 0 or 0 in ids[:-1] or 4 not in ids:
            continue
        print(f"shop list ptr at {EWRAM + off:#x}: {ptr:#x} count {count} ids {ids[:-1]}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
