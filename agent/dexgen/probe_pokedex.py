"""Read-only fingerprint of the SaveBlock1 dexSeen/dexCaught arrays off a live
savestate. Finds the two adjacent DEX_FLAGS_NO bit arrays (seen then caught,
GetSetPokedexFlag: bit = nationalDexNo-1) by matching the known owned party
national numbers. Prints the SaveBlock1-relative offsets and the stride.

Touches nothing the executor runs; loads a snapshot into a throwaway core.
"""
import os
import sys
import struct

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import emu_boot  # noqa: E402  (sets up libmgba)
import rowe_symbols as S  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "states", "live.ss")

MON_SPECIES = S.MON_SPECIES          # offset of species in a party mon
SIZEOF_POKEMON = S.SIZEOF_POKEMON


def popcount(b: bytes) -> int:
    return sum(bin(x).count("1") for x in b)


def bit_set(buf: bytes, nat: int) -> bool:
    idx = (nat - 1) // 8
    return idx < len(buf) and bool(buf[idx] & (1 << ((nat - 1) % 8)))


def main():
    e = emu_boot.Emu()
    with open(STATE, "rb") as f:
        e.load_state(f.read())

    sb1 = e.u32(S.addr("gSaveBlock1Ptr"))
    sb2 = e.u32(S.addr("gSaveBlock2Ptr"))
    print(f"gSaveBlock1Ptr -> {sb1:#010x}  gSaveBlock2Ptr -> {sb2:#010x}")

    # party national numbers (base species: id == national dex number)
    pcount = e.read(S.addr("gPlayerPartyCount"))[0]
    base = S.addr("gPlayerParty")
    party = []
    for i in range(pcount):
        raw = e.read(base + i * SIZEOF_POKEMON, SIZEOF_POKEMON)
        sp = struct.unpack_from("<H", raw, MON_SPECIES)[0]
        party.append(sp)
    print(f"party species ids: {party}")

    # read a generous SaveBlock1 span. sizeof(SaveBlock1) ~ 0x3850 in emerald;
    # dex arrays sit near 0x31F8+ in the 1.9.4 source, push the window past that.
    span = 0x4000
    buf = e.read(sb1, span)

    # candidate caught-array starts: every byte offset whose bit array has all
    # party nat bits set. same for seen. the pair is (seen, caught) with
    # caught a bitwise subset of seen and a consistent positive gap = DEX_FLAGS_NO.
    owned = sorted(n for n in party if n and n <= 1025)
    NAT_MAX = 1025  # national dex caps at Pecharunt; no flag bit is set above it

    def clean_array(off: int, stride: int) -> bool:
        """array at off has every bit above national 1025 clear."""
        arr = buf[off:off + stride]
        for n in range(NAT_MAX + 1, stride * 8 + 1):
            if bit_set(arr, n):
                return False
        return True

    # candidate caught starts: all party bits set, modest owned count, clean tail
    cands = []
    for off in range(0, span - 0x200):
        window = buf[off:off + 0x200]
        if not all(bit_set(window, n) for n in owned):
            continue
        cands.append(off)
    print(f"{len(cands)} offsets carry all party owned bits")

    pairs = []
    cset = set(cands)
    for caught_off in cands:
        for stride in range(0x60, 0x100):  # DEX_FLAGS_NO: 768..2048 species rows
            if stride * 8 < NAT_MAX:
                continue
            seen_off = caught_off - stride
            if seen_off not in cset:
                continue
            seen = buf[seen_off:seen_off + stride]
            caught = buf[caught_off:caught_off + stride]
            if not all((c & ~s) == 0 for c, s in zip(caught, seen)):
                continue  # caught must be a subset of seen
            nseen, ncaught = popcount(seen), popcount(caught)
            if not (ncaught < nseen):
                continue  # seen strictly larger than owned
            if not (clean_array(caught_off, stride) and clean_array(seen_off, stride)):
                continue  # no bits above national 1025
            pairs.append((seen_off, caught_off, stride, nseen, ncaught))

    print(f"{len(pairs)} (seen,caught,stride) candidate pairs after tail+subset filter")
    for seen_off, caught_off, stride, nseen, ncaught in sorted(pairs, key=lambda p: (p[4], p[2])):
        print(f"  seen@+{seen_off:#06x} caught@+{caught_off:#06x} "
              f"stride={stride:#x}({stride}) seen_pop={nseen} caught_pop={ncaught}")

    if pairs:
        best = min(pairs, key=lambda p: p[4])  # smallest owned count
        seen_off, caught_off, stride, nseen, ncaught = best
        caught = buf[caught_off:caught_off + stride]
        seen = buf[seen_off:seen_off + stride]
        owned_ids = [n for n in range(1, NAT_MAX + 1) if bit_set(caught, n)]
        seen_ids = [n for n in range(1, NAT_MAX + 1) if bit_set(seen, n)]
        print(f"\nBEST: SB1 + {seen_off:#x} (dexSeen), SB1 + {caught_off:#x} (dexCaught), "
              f"DEX_FLAGS_NO={stride}")
        print(f"  caught count={len(owned_ids)} seen count={len(seen_ids)}")
        print(f"  caught national ids: {owned_ids}")
        print(f"  party owned bits present: {all(n in owned_ids for n in owned)}")


if __name__ == "__main__":
    main()
