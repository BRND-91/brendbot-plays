"""Step the ROM from a save state, apply an input script, snapshot the result.

    drive.py --state /tmp/rowe.ss [--fresh 300] --inputs "A,w120,START,UP*3,hold:A:60" --shot /tmp/out.png

Tokens: a button name taps it (4 frames down, 12 up); `wN` runs N idle frames;
`NAME*k` repeats a tap; `hold:NAME:N` holds for N frames. The state file is
rewritten after the script so the next call continues from here.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb  # noqa: E402
import rowe_symbols as S  # noqa: E402

KEYS = {"A": eb.KEY_A, "B": eb.KEY_B, "SELECT": eb.KEY_SELECT, "START": eb.KEY_START,
        "RIGHT": eb.KEY_RIGHT, "LEFT": eb.KEY_LEFT, "UP": eb.KEY_UP, "DOWN": eb.KEY_DOWN}

CHARMAP = {0x00: " ", 0xAD: ".", 0xAE: "-", 0xB8: ",", 0xBA: "/", 0xBB: "A"}


def decode(raw: bytes) -> str:
    out = []
    for c in raw:
        if c == 0xFF:
            break
        if 0xBB <= c <= 0xD4:
            out.append(chr(ord("A") + c - 0xBB))
        elif 0xD5 <= c <= 0xEE:
            out.append(chr(ord("a") + c - 0xD5))
        elif 0xA1 <= c <= 0xAA:
            out.append(chr(ord("0") + c - 0xA1))
        else:
            out.append(CHARMAP.get(c, "?"))
    return "".join(out)


def apply(e: eb.Emu, script: str) -> None:
    for tok in filter(None, (t.strip() for t in script.split(","))):
        if tok[0] == "w" and tok[1:].isdigit():
            e.run(int(tok[1:]))
        elif tok.startswith("hold:"):
            _, name, n = tok.split(":")
            e.run(int(n), KEYS[name])
            e.run(12)
        else:
            name, _, k = tok.partition("*")
            for _ in range(int(k) if k else 1):
                e.tap(KEYS[name])


def status(e: eb.Emu) -> dict:
    main = S.addr("gMain")
    sb1 = e.u32(S.addr("gSaveBlock1Ptr"))
    sb2 = e.u32(S.addr("gSaveBlock2Ptr"))
    flags = e.read(main + S.MAIN_IN_BATTLE_BYTE)[0]
    party_n = e.read(S.addr("gPlayerPartyCount"))[0]
    mon0 = e.read(S.addr("gPlayerParty"), S.SIZEOF_POKEMON)
    pos = struct.unpack("<hh", e.read(sb1 + S.SB1_POS, 4))
    loc = e.read(sb1 + S.SB1_LOCATION, 4)
    return {
        "cb2": hex(e.u32(main + S.MAIN_CALLBACK2)),
        "main_state": e.read(main + S.MAIN_STATE)[0],
        "in_battle": bool(flags & S.MAIN_IN_BATTLE_BIT),
        "sb2": hex(sb2),
        "player": decode(e.read(sb2 + S.SB2_PLAYER_NAME, 8)),
        "gender": e.read(sb2 + S.SB2_PLAYER_GENDER)[0],
        "tid": hex(e.u32(sb2 + S.SB2_TRAINER_ID)),
        "pos": pos,
        "map_group_num": (loc[0], loc[1]),
        "party_count": party_n,
        "sb1_party_count": e.read(sb1 + S.SB1_PARTY_COUNT)[0],
        "mon0": mon0.hex(),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--fresh", type=int, default=None, help="boot from reset and run this many frames first")
    ap.add_argument("--inputs", default="")
    ap.add_argument("--shot", default="/tmp/rowe_shot.png")
    a = ap.parse_args()
    e = eb.Emu()
    if a.fresh is not None:
        e.run(a.fresh)
    else:
        with open(a.state, "rb") as f:
            e.load_state(f.read())
    apply(e, a.inputs)
    e.run(2)
    with open(a.state, "wb") as f:
        f.write(e.save_state())
    e.save_png(a.shot)
    for k, v in status(e).items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
