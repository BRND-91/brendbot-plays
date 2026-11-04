"""Push emulator frames and audio into the HLS stream Caddy serves at live.brenergy.net.

The core renders RGBX 32-bit at 240x160 into `Emu.screen.buffer` and mixes
stereo audio into two blip buffers; each frame both are written raw to an
encoder that scales 3x nearest-neighbour, encodes AAC, and emits rolling 2s
segments into /var/www/brenergy/live, the layout the player page reads.
"""
import fcntl
import os
import subprocess
import threading
import time

from mgba import ffi

OUT_DIR = os.environ.get("ROWE_STREAM_DIR", "/var/www/brenergy/live")
F_SETPIPE_SZ = 1031  # linux fcntl op, absent from the fcntl module
PIPE_BYTES = 1 << 20
# GBA frame clock; both streams are timestamped off it, so a 60 fps video
# timeline against sample-counted audio would drift 0.45% and lose sync
CORE_HZ = 16777216
FRAME_CYCLES = 280896
FPS = CORE_HZ / FRAME_CYCLES
AUDIO_RATE = 48000
BLIP_MAX = 16384  # mGBA's blip buffer length, so one read always drains it
SEGMENT_SECONDS = 2
PLAYLIST_LENGTH = 30  # 60s window, slack for a throttled background tab to resync
SCALE = 3
# MediaMTX takes the RTSP publish on localhost and fans it out as WebRTC
RTSP_URL = os.environ.get("ROWE_RTSP_URL", "rtsp://127.0.0.1:8554/rowe")
# tee slave options: ':' separates them, so select names output streams by
# index (0 video, 1 aac, 2 opus, the -map order) instead of a 'a:1' specifier
RTSP_SELECT = "[f=rtsp:rtsp_transport=tcp:select=0,2]"


def hls_branch(out_dir: str) -> str:
    opts = ":".join([
        "f=hls",
        f"hls_time={SEGMENT_SECONDS}",
        f"hls_list_size={PLAYLIST_LENGTH}",
        "hls_flags=delete_segments+append_list+omit_endlist",
        # media sequence numbers keep rising across restarts, so a viewer
        # mid-stream resyncs instead of failing on a reset
        "hls_start_number_source=epoch",
        "hls_segment_filename=" + os.path.join(out_dir, "stream%d.ts"),
        "select=0,1",
    ])
    return f"[{opts}]{os.path.join(out_dir, 'stream.m3u8')}"


def _atempo_chain(speed: float) -> str:
    # atempo blends cleanly only up to 2.0 and skips samples past it, so a
    # speed above 2 becomes a chain of factors each <= 2 whose product is speed
    factors = []
    rem = float(speed)
    while rem > 2.0:
        factors.append(2.0)
        rem /= 2.0
    factors.append(rem)
    return ",".join(f"atempo={f:g}" for f in factors)


class FrameStreamer:
    def __init__(self, core, width: int = 240, height: int = 160, out_dir: str = OUT_DIR,
                 speed: int = 1, rtsp_url: str = RTSP_URL):
        # speed>1 runs the emulator faster than real time: every frame's audio
        # is kept but only every speed-th video frame is written, and atempo
        # shrinks the audio back to the kept-frame timeline, so the stream stays
        # real-time while the game inside it advances speed-fold
        self.speed = max(1, int(speed))
        self._width = width
        self._height = height
        self._out_dir = out_dir
        self._rtsp_url = rtsp_url
        os.umask(0o022)
        os.makedirs(out_dir, exist_ok=True)
        for name in os.listdir(out_dir):
            if name.startswith("stream") and name.endswith((".ts", ".m3u8")):
                os.unlink(os.path.join(out_dir, name))
        self.frame_bytes = width * height * 4
        self.channels = (core.get_audio_channel(0), core.get_audio_channel(1))
        for ch in self.channels:
            ch.set_rate(AUDIO_RATE)
            ch.clear()
        self.audio_buf = ffi.new("short[]", 2 * BLIP_MAX)
        # both threads write the pipes under _lock so a frame never interleaves a
        # half-written silence block, and set_speed re-spawns the encoder under it
        self._lock = threading.Lock()
        self._open_encoder()
        self._next_deadline = time.monotonic()
        # largest inter-push interval per wall second, printed to stdout so
        # grind.log keeps each GAPLOG in order with the loop's own prints and
        # the line before it is what the loop was doing when the gap opened
        self._gap_prev = None
        self._gap_sec = None
        self._gap_max = 0.0
        # keepalive: while the main thread is stalled in planning, a daemon
        # thread re-sends the last frame and a frame of silence at FPS so
        # ffmpeg's two inputs never gap and the HLS edge keeps advancing.
        # _audio_accum holds the fractional samples-per-frame so injected audio
        # stays locked to the frame count
        self._main_push_at = None
        self._last_frame = bytearray(self.frame_bytes)
        self._audio_accum = 0.0
        self._frame_i = 0
        self._closing = False
        self._keeper = threading.Thread(target=self._keepalive, name="frame-keepalive", daemon=True)
        self._keeper.start()

    def _open_encoder(self) -> None:
        """Spawn ffmpeg and open the raw video/audio pipes feeding it. The atempo
        chain is fixed at spawn time, so a speed change re-spawns through here."""
        width, height = self._width, self._height
        video_r, video_w = os.pipe()
        audio_r, audio_w = os.pipe()
        # ffmpeg probes each input in turn before any demux thread reads, so
        # the writer must never block on one pipe while the probe waits on the
        # other: a 1 MiB pipe holds 6 frames of video, and the probe flags cap
        # what the probe asks for; both were required to clear the deadlock
        for fd in (video_w, audio_w):
            fcntl.fcntl(fd, F_SETPIPE_SZ, PIPE_BYTES)
        probe = ["-probesize", "32", "-analyzeduration", "0"]
        # one atempo chain per audio output; the tee's two audio encoders are
        # separate output streams, so a single -af would miss the second
        afilter = []
        if self.speed != 1:
            chain = _atempo_chain(self.speed)
            afilter = ["-filter:a:0", chain, "-filter:a:1", chain]
        # drop the RTSP branch when no target is set, so a smoke render writes
        # HLS to a scratch dir without publishing to the live MediaMTX
        tee_out = hls_branch(self._out_dir)
        if self._rtsp_url:
            tee_out += "|" + RTSP_SELECT + self._rtsp_url
        self.proc = subprocess.Popen(
            [
                "ffmpeg", "-loglevel", "error", "-nostdin",
                *probe, "-thread_queue_size", "64",
                "-f", "rawvideo", "-pix_fmt", "rgb0", "-s", f"{width}x{height}",
                "-r", f"{CORE_HZ}/{FRAME_CYCLES}", "-i", f"pipe:{video_r}",
                *probe, "-thread_queue_size", "64",
                "-f", "s16le", "-ar", str(AUDIO_RATE), "-ac", "2", "-i", f"pipe:{audio_r}",
                "-map", "0:v", "-map", "1:a", "-map", "1:a",
                "-vf", f"scale={width * SCALE}:{height * SCALE}:flags=neighbor",
                *afilter,
                "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency", "-pix_fmt", "yuv420p",
                "-g", str(round(FPS * SEGMENT_SECONDS)),
                # the tee muxer cannot pick per-output encoder flags, so the
                # SPS/PPS go in extradata for RTSP and mpegts re-inserts them
                "-flags", "+global_header",
                # one video encode feeds both outputs; HLS wants AAC, WebRTC
                # only takes Opus, so the audio is encoded twice
                "-c:a:0", "aac", "-b:a:0", "96k",
                "-c:a:1", "libopus", "-b:a:1", "96k", "-application:a:1", "lowdelay",
                # each tee branch runs behind its own fifo, so MediaMTX being
                # down or restarting stalls or drops the RTSP branch alone and
                # the HLS branch keeps writing
                "-f", "tee", "-use_fifo", "1",
                "-fifo_options", "attempt_recovery=1:recovery_wait_time=2:drop_pkts_on_overflow=1",
                tee_out,
            ],
            pass_fds=(video_r, audio_r),
        )
        os.close(video_r)
        os.close(audio_r)
        self.video = os.fdopen(video_w, "wb", buffering=0)
        self.audio = os.fdopen(audio_w, "wb", buffering=0)
        # one real frame of silence at the current speed; atempo shrinks the
        # injected block back the same as live audio
        self._silence = bytes((int(AUDIO_RATE / FPS * self.speed) + 2) * 4)

    def set_speed(self, speed: int) -> None:
        """Change stream speed on a running encoder. The frame-drop ratio moves on
        the next push; the audio atempo is fixed at ffmpeg launch, so the encoder
        re-spawns, a brief reconnect the rising HLS media sequence resyncs. Closing
        the pipe ends ffmpeg's stdin, then terminate and a bounded wait reap it."""
        speed = max(1, int(speed))
        with self._lock:
            if speed == self.speed:
                return
            self.video.close()
            self.audio.close()
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
            self.speed = speed
            self._frame_i = 0
            self._audio_accum = 0.0
            self._open_encoder()
            self._next_deadline = time.monotonic()
        print(f"stream speed -> {speed}x", flush=True)

    def push(self, screen) -> None:
        """Write the audio a frame produced, then the frame, and hold the loop to real time."""
        now = time.monotonic()
        # audio goes first: ffmpeg probes its inputs one after another before
        # any demux thread runs, so a video write that blocks on a full pipe
        # while ffmpeg still waits for its first audio packet deadlocks both
        left, right = self.channels
        n = left.available
        left.read_into(self.audio_buf, n, 2, 0)
        right.read_into(self.audio_buf, n, 2, 1)
        with self._lock:
            self._mark_gap(now)
            self._main_push_at = now
            self.audio.write(ffi.buffer(self.audio_buf, n * 4))
            self._frame_i += 1
            if self._frame_i % self.speed == 0:
                self.video.write(ffi.buffer(screen.buffer, self.frame_bytes))
            self._last_frame[:] = ffi.buffer(screen.buffer, self.frame_bytes)
        self._next_deadline += 1 / (FPS * self.speed)
        delay = self._next_deadline - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        elif delay < -1:
            self._next_deadline = time.monotonic()

    def _mark_gap(self, now: float) -> None:
        """Track the largest interval between consecutive pushes of either thread
        per wall second. Caller holds _lock."""
        if self._gap_prev is not None:
            sec = int(now)
            if self._gap_sec is None:
                self._gap_sec = sec
            elif sec != self._gap_sec:
                print(f"GAPLOG sec={self._gap_sec} max_gap_ms={self._gap_max * 1000:.1f}", flush=True)
                self._gap_sec = sec
                self._gap_max = 0.0
            if now - self._gap_prev > self._gap_max:
                self._gap_max = now - self._gap_prev
        self._gap_prev = now

    def _keepalive(self) -> None:
        period = 1 / FPS
        while True:
            time.sleep(period / 2)
            with self._lock:
                if self._closing:
                    return
                if self._main_push_at is None:
                    continue
                now = time.monotonic()
                # fire only after the main thread has been gone over two frame
                # periods, then hold one frame per period until it returns
                if now - self._main_push_at <= 2 * period or now - self._gap_prev < period:
                    continue
                # injected silence is tempo-shrunk by the same atempo as live
                # audio, so it carries speed-fold samples to stay one real frame
                # long; read speed under the lock so a set_speed is picked up
                samples_per_frame = AUDIO_RATE / FPS * self.speed
                self._audio_accum += samples_per_frame
                nsamp = int(self._audio_accum)
                self._audio_accum -= nsamp
                self.audio.write(self._silence[:nsamp * 4])
                self.video.write(self._last_frame)
                self._mark_gap(now)

    def close(self) -> None:
        with self._lock:
            self._closing = True
        self._keeper.join(timeout=2)
        self.video.close()
        self.audio.close()
        self.proc.wait(timeout=30)
