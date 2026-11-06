"""After a main-thread stall the keepalive has already carried the stream timeline with repeats of
the last frame, so the frames the loop renders next pace from the moment it returns. The old pacer
kept its pre-stall deadline and pushed the backlog as fast as the core rendered, so every battle
exit and warp (the two longest stalls) put a stall's worth of extra frames into the encoder in a
burst, the on-stream churn. Red while the burst stands (30 frames in well under a frame period
each), green once they take 30 frame periods."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import emu_boot  # noqa: E402, F401  (puts the mgba build on sys.path)
from mgba import ffi  # noqa: E402

import stream_sink  # noqa: E402


class _Channel:
    available = 0

    def set_rate(self, rate):
        pass

    def clear(self):
        pass

    def read_into(self, buf, n, stride, offset):
        pass


class _Core:
    def get_audio_channel(self, i):
        return _Channel()


class _Screen:
    def __init__(self, nbytes):
        self.buffer = ffi.new("unsigned char[]", nbytes)


class _NoPipe(stream_sink.FrameStreamer):
    """The encoder is out of process, so its pipe write is the one double: counted, never blocking,
    so the timing under test is the pacer's alone."""
    writes = 0

    def _write(self, pipe, data):
        self.writes += 1


def test_frames_after_a_stall_pace_at_real_time(tmp_path):
    s = _NoPipe(_Core(), out_dir=str(tmp_path), rtsp_url="")
    try:
        screen = _Screen(s.frame_bytes)
        for _ in range(6):
            s.push(screen)
        before = s.writes
        time.sleep(0.5)  # a planning stall; the keepalive repeats the last frame through it
        kept_alive = (s.writes - before) // 2
        t0 = time.monotonic()
        for _ in range(30):
            s.push(screen)
        took = time.monotonic() - t0
    finally:
        s.close()
    assert kept_alive >= 20, f"the keepalive wrote {kept_alive} frames through a 0.5s stall"
    floor = 29 / stream_sink.FPS
    assert took >= floor, f"30 post-stall frames took {took:.3f}s, a catch-up burst under the {floor:.3f}s real-time floor"


def test_keepalive_holds_full_frame_rate_through_a_stall(tmp_path):
    """A stalled second used to land 41 to 46 repeats (live GAPLOG `main=0 keep=42`), so the stream
    fell a third of a second behind per stalled second. The live stall is a planner computing in
    pure Python, which holds the GIL and wakes the keepalive late, so the stall here is a busy loop
    and never a sleep. The keepalive writes every frame its deadline owes when it does wake."""
    s = _NoPipe(_Core(), out_dir=str(tmp_path), rtsp_url="")
    try:
        screen = _Screen(s.frame_bytes)
        for _ in range(3):
            s.push(screen)
        before = s.writes
        end = time.monotonic() + 1.0
        n = 0
        while time.monotonic() < end:
            n = (n * 31 + 7) % 1000003
        kept_alive = (s.writes - before) // 2
    finally:
        s.close()
    assert kept_alive >= 56, f"{kept_alive} keepalive frames in a stalled second, under the 60 the timeline needs"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
