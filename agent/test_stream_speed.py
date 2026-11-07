import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emu_boot  # noqa: E402,F401  loads the vendored mgba onto sys.path
from mgba import ffi  # noqa: E402
from stream_sink import BLIP_MAX, FrameStreamer  # noqa: E402


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

    def close(self):
        pass


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
    fs._sec_main = 0
    fs._sec_keep = 0
    fs._main_gap = 0.0
    fs._injected = False
    fs._main_push_at = None
    fs._frame_i = 0
    fs._next_deadline = time.monotonic()
    fs.audio = _CountingSink()
    fs.video = _CountingSink()
    return fs


def test_blocked_encoder_write_is_killed_and_respawned():
    # the live freeze: ffmpeg stopped draining its input pipe (every thread in futex wait, the HLS
    # edge frozen), the main thread sat in a blocking pipe write and the stream died with the game
    # still running. A write pending past the stall bound kills the encoder, the write fails with
    # a broken pipe, and the sink respawns ffmpeg instead of waiting forever
    frame_bytes = 16
    fs = _push_harness(1, frame_bytes, 0)
    released = threading.Event()

    class _BlockingSink:
        def write(self, b):
            if not released.wait(10):
                raise TimeoutError("encoder never killed")
            raise BrokenPipeError

        def close(self):
            pass

    class _Proc:
        def __init__(self, pid):
            self.pid = pid

        def kill(self):
            released.set()

        def wait(self, timeout=None):
            pass

    opened = []

    def reopen():
        opened.append(1)
        fs.video = _CountingSink()
        fs.audio = _CountingSink()
        fs.proc = _Proc(2)

    fs.video = _BlockingSink()
    fs.proc = _Proc(1)
    fs._open_encoder = reopen
    fs._closing = False
    fs._write_at = None
    fs.stall_seconds = 0.2
    threading.Thread(target=fs._watchdog, daemon=True).start()
    screen = type("Screen", (), {"buffer": ffi.new("char[]", frame_bytes)})()
    pusher = threading.Thread(target=fs.push, args=(screen,), daemon=True)
    pusher.start()
    pusher.join(3)
    assert not pusher.is_alive(), "push stayed blocked on the dead encoder"
    assert opened == [1], f"encoder respawned {len(opened)} times"
    assert fs.proc.pid == 2
    fs._closing = True


def test_push_drops_video_and_audio_together_at_2x():
    frame_bytes, n = 16, 800
    fs = _push_harness(2, frame_bytes, n)
    screen = type("Screen", (), {"buffer": ffi.new("char[]", frame_bytes)})()
    for _ in range(120):
        fs.push(screen)
    assert fs.video.nwrites == 60      # every 2nd of 120 frames
    assert fs.audio.nwrites == 60      # audio rides the same kept frame, not every frame
    assert fs.video.nbytes == 960      # 60 frames * 16 bytes
    assert fs.audio.nbytes == 192000   # 60 kept frames * 800 samples * 4 bytes, real-time


def test_push_keeps_every_frame_at_1x():
    frame_bytes, n = 16, 800
    fs = _push_harness(1, frame_bytes, n)
    screen = type("Screen", (), {"buffer": ffi.new("char[]", frame_bytes)})()
    for _ in range(120):
        fs.push(screen)
    assert fs.video.nwrites == 120 and fs.audio.nwrites == 120
    assert fs.video.nbytes == 1920 and fs.audio.nbytes == 384000


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


def test_set_speed_moves_without_touching_the_encoder():
    fs = _set_speed_harness()
    fs._open_encoder = lambda: (_ for _ in ()).throw(AssertionError("speed change must not re-spawn ffmpeg"))
    fs.set_speed(2)
    assert fs.speed == 2
    assert not fs.video.closed and not fs.audio.closed and not fs.proc.terminated  # encoder left running
    assert fs._frame_i == 0                                                        # kept-frame phase reset


def test_set_speed_same_value_is_noop():
    fs = _set_speed_harness()
    fs.speed = 2
    fs._frame_i = 5
    fs.set_speed(2)
    assert fs.speed == 2 and fs._frame_i == 5  # unchanged speed leaves the phase alone
    assert not fs.video.closed and not fs.proc.terminated
