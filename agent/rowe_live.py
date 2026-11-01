"""The live save and its backup ring, named in one place so a probe, a test, or a careless
restore cannot confuse it with a fixture.

The live run is the only writer of states/live.ss. Every snapshot also drops a timestamped copy
into states/live/ and keeps the last LIVE_RING, so a bad overwrite is always recoverable from the
ring. A loss of 7 badges and ~20 hours of grinding to a stale 0-badge restore is what motivates it.
"""
import glob
import os
import time

BASE = os.path.dirname(os.path.abspath(__file__))
STATES = os.path.join(BASE, "states")
LIVE_SAVE = os.path.join(STATES, "live.ss")
RING_DIR = os.path.join(STATES, "live")
LIVE_RING = 20
_RING_GLOB = "[0-9]" * 8 + "T" + "[0-9]" * 4 + ".ss"  # YYYYmmddTHHMM.ss, the archive() name


def is_live_target(path: str) -> bool:
    """Whether path is the live save itself or a file inside its backup ring."""
    rp = os.path.realpath(path)
    return rp == os.path.realpath(LIVE_SAVE) or rp.startswith(os.path.realpath(RING_DIR) + os.sep)


def guard_write(path: str, is_live_run: bool) -> None:
    """Refuse any write to the live save or its ring from code that is not the live run. A probe or
    test that points a state path here raises instead of silently overwriting grinding progress."""
    if is_live_target(path) and not is_live_run:
        raise RuntimeError(
            f"{path} is the live save; only the live run writes it. "
            "Probes and fixtures read states/fixtures/ and write under /tmp."
        )


def archive(blob: bytes) -> str:
    """Drop blob into the ring as states/live/YYYYmmddTHHMM.ss, prune to the last LIVE_RING, and
    return the copy's path. Minute granularity means a burst of snapshots in one minute keeps one."""
    os.makedirs(RING_DIR, exist_ok=True)
    dst = os.path.join(RING_DIR, time.strftime("%Y%m%dT%H%M", time.gmtime()) + ".ss")
    with open(dst, "wb") as f:
        f.write(blob)
    kept = sorted(glob.glob(os.path.join(RING_DIR, _RING_GLOB)))
    for old in kept[:-LIVE_RING]:
        os.remove(old)
    return dst
