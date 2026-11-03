"""Dev shortcut: set the Ever Grande League-guard object flag on a copy of a save state, so the
endgame can be built and driven against a fixture before the 16th badge is earned. The guard is the
(0,8) object at (18,42), object flag 0x0dfa; setting it hides the object, which clears the gate.

Refuses the live save and its backup ring through rowe_live.guard_write: the live run earns the
flag for real by clearing the League, and a dev flag written there would fake progression into the
save that matters. Channel rule "ROWE live save". Writes a copy under /tmp, never a fixture in place.

    set_league_flag.py --state /tmp/evergrande_flagged.ss
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot as eb  # noqa: E402
import rowe_live  # noqa: E402
import rowe_symbols as S  # noqa: E402

GUARD_FLAG = 0x0DFA


def read_flag(path: str, flag_id: int = GUARD_FLAG) -> bool:
    """Whether flag_id is set in the save state at path. Read-only, so the live save is allowed."""
    e = eb.Emu()
    with open(path, "rb") as f:
        e.load_state(f.read())
    sb1 = e.u32(S.addr("gSaveBlock1Ptr"))
    return bool(e.read(sb1 + S.SB1_FLAGS + flag_id // 8)[0] >> (flag_id % 8) & 1)


def set_flag(path: str, flag_id: int = GUARD_FLAG) -> None:
    """Set flag_id in the save state at path and rewrite it. Raises on the live save or its ring."""
    rowe_live.guard_write(path, is_live_run=False)
    e = eb.Emu()
    with open(path, "rb") as f:
        e.load_state(f.read())
    sb1 = e.u32(S.addr("gSaveBlock1Ptr"))
    off = sb1 + S.SB1_FLAGS + flag_id // 8
    e.write(off, bytes([e.read(off)[0] | (1 << (flag_id % 8))]))
    with open(path, "wb") as f:
        f.write(e.save_state())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    a = ap.parse_args()
    set_flag(a.state)
    print(f"flag {GUARD_FLAG:#06x} set on {a.state}, now {read_flag(a.state)}")


if __name__ == "__main__":
    main()
