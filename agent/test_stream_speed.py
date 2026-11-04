import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot  # noqa: E402,F401  loads the vendored mgba onto sys.path
from mgba import ffi  # noqa: E402
from stream_sink import BLIP_MAX, FrameStreamer, _atempo_chain  # noqa: E402


class _FakeChannel:
    def __init__(self, n):
        self.available = n

    def read_into(self, buf, n, step, off):
        pass


class _CountingSink:
    """Stands in for the ffmpeg pipe; records what push would stream out."""

    def __init__(self):
        self.nwrites = 0
        self.nbytes = 0

    def write(self, b):
        self.nwrites += 1
        self.nbytes += len(bytes(b))


def _push_harness(speed, frame_bytes, n):
    # push() needs the attrs __init__ sets minus the ffmpeg process and threads,
    # so build the object directly and point video/audio at counting sinks
    fs = FrameStreamer.__new__(FrameStreamer)
    fs.speed = speed
    fs.frame_bytes = frame_bytes
    fs.channels = (_FakeChannel(n), _FakeChannel(n))
    fs.audio_buf = ffi.new("short[]", 2 * BLIP_MAX)
    fs._last_frame = bytearray(frame_bytes)
    fs._lock = threading.Lock()
    fs._gap_prev = None
    fs._gap_sec = None
    fs._gap_max = 0.0
    fs._main_push_at = None
    fs._frame_i = 0
    fs._next_deadline = time.monotonic()
    fs.audio = _CountingSink()
    fs.video = _CountingSink()
    return fs


def test_push_drops_video_keeps_audio_at_2x():
    frame_bytes, n = 16, 800
    fs = _push_harness(2, frame_bytes, n)
    screen = type("Screen", (), {"buffer": ffi.new("char[]", frame_bytes)})()
    for _ in range(120):
        fs.push(screen)
    assert fs.video.nwrites == 60      # every 2nd of 120 frames
    assert fs.audio.nwrites == 120     # every frame's audio is kept
    assert fs.video.nbytes == 960      # 60 frames * 16 bytes
    assert fs.audio.nbytes == 384000   # 120 frames * 800 samples * 4 bytes


def test_atempo_chain_factors_stay_within_two():
    assert _atempo_chain(2) == "atempo=2"
    assert _atempo_chain(4) == "atempo=2,atempo=2"
    assert _atempo_chain(3) == "atempo=2,atempo=1.5"


class _FakeProc:
    def __init__(self):
        self.terminated = False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


class _FakePipe:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _set_speed_harness():
    fs = FrameStreamer.__new__(FrameStreamer)
    fs._lock = threading.Lock()
    fs.speed = 1
    fs._frame_i = 5
    fs._audio_accum = 0.7
    fs._next_deadline = 0.0
    fs.video = _FakePipe()
    fs.audio = _FakePipe()
    fs.proc = _FakeProc()
    return fs


def test_set_speed_bounces_encoder_and_resets_counters():
    fs = _set_speed_harness()
    old_video, old_audio, old_proc = fs.video, fs.audio, fs.proc
    opened = []

    def fake_open():
        fs.video = _FakePipe()
        fs.audio = _FakePipe()
        fs.proc = _FakeProc()
        opened.append(fs.speed)

    fs._open_encoder = fake_open
    fs.set_speed(2)
    assert fs.speed == 2
    assert old_video.closed and old_audio.closed and old_proc.terminated  # old encoder torn down
    assert opened == [2]                                                  # re-spawned once at the new speed
    assert fs._frame_i == 0 and fs._audio_accum == 0.0                    # counters reset to the new timeline


def test_set_speed_same_value_is_noop():
    fs = _set_speed_harness()
    fs.speed = 2
    fs._open_encoder = lambda: (_ for _ in ()).throw(AssertionError("must not re-spawn on an unchanged speed"))
    fs.set_speed(2)
    assert fs.speed == 2
    assert not fs.video.closed and not fs.proc.terminated
