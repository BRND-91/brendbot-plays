"""Push emulator frames and audio into the HLS stream Caddy serves at live.brenergy.net.

The core renders RGBX 32-bit at 240x160 into `Emu.screen.buffer` and mixes
stereo audio into two blip buffers; each frame both are written raw to an
encoder that scales 3x nearest-neighbour, encodes AAC, and emits rolling 2s
segments into /var/www/brenergy/live, the layout the player page reads.
"""
import fcntl
import os
import subprocess
import sys
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
# a pipe write to ffmpeg pending this long means the encoder stopped draining (every ffmpeg thread
# in futex wait, the HLS edge frozen); the 1 MiB pipe holds 6 frames, so a live encoder clears a
# write within a frame period
ENCODER_STALL_SECONDS = 5.0
# frames the keepalive writes on one wake at most; a planner stall holds the GIL and wakes it late,
# so it pays the frames its deadline owes in small runs instead of one dump when it finally runs
KEEPALIVE_BURST_CAP = 4
# a main-thread absence this long prints the main thread's stack once, so grind.log names the step
# that froze the picture
STALL_TRACE_SECONDS = 0.4


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


class FrameStreamer:
    stall_seconds = ENCODER_STALL_SECONDS

    def __init__(self, core, width: int = 240, height: int = 160, out_dir: str = OUT_DIR,
                 speed: int = 1, rtsp_url: str = RTSP_URL):
        # speed>1 runs the emulator faster than real time: only every speed-th
        # frame's video and audio reach the encoder, so the stream stays
        # real-time and pitch-correct while the game inside it advances
        # speed-fold. The dropped frames' audio is discarded with their video,
        # which keeps the encoder config independent of speed so a speed change
        # never restarts ffmpeg (set_speed)
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
        # per-second frame accounting beside the gap: kept main pushes, keepalive repeats, and the
        # longest the main thread stayed away, so a stall and its size read off one GAPLOG line
        self._sec_main = 0
        self._sec_keep = 0
        self._main_gap = 0.0
        # set by the keepalive once it has repeated a frame; the next main push paces from its own
        # moment instead of catching up on the pre-stall deadline
        self._injected = False
        # keepalive: while the main thread is stalled in planning, a daemon
        # thread re-sends the last frame and a frame of silence at FPS so
        # ffmpeg's two inputs never gap and the HLS edge keeps advancing.
        # _audio_accum holds the fractional samples-per-frame so injected audio
        # stays locked to the frame count
        self._main_push_at = None
        self._main_ident = None
        self._traced = False
        self._last_frame = bytearray(self.frame_bytes)
        self._audio_accum = 0.0
        self._frame_i = 0
        self._closing = False
        self._keeper = threading.Thread(target=self._keepalive, name="frame-keepalive", daemon=True)
        self._keeper.start()
        # the watchdog runs outside _lock, since a stalled write holds the lock
        self._write_at = None
        self._dog = threading.Thread(target=self._watchdog, name="encoder-watchdog", daemon=True)
        self._dog.start()

    def _write(self, pipe, data) -> None:
        """One pipe write under the stall watch; a broken pipe (the encoder died or the watchdog
        killed it) respawns ffmpeg and drops this frame. Caller holds _lock."""
        self._write_at = time.monotonic()
        try:
            pipe.write(data)
        except BrokenPipeError:
            self._respawn()
        finally:
            self._write_at = None

    def _respawn(self) -> None:
        """Replace a dead or wedged encoder with a fresh one on new pipes. Caller holds _lock."""
        pid = self.proc.pid
        self.video.close()
        self.audio.close()
        self.proc.kill()
        self.proc.wait(timeout=10)
        self._open_encoder()
        print(f"encoder respawn: ffmpeg {pid} stopped draining, pipes reopened on {self.proc.pid}", flush=True)

    def _watchdog(self) -> None:
        while True:
            time.sleep(min(1.0, self.stall_seconds / 2))
            if self._closing:
                return
            at = self._write_at
            if at is not None and time.monotonic() - at > self.stall_seconds:
                print(f"encoder stall: write pending {time.monotonic() - at:.1f}s, killing ffmpeg {self.proc.pid}", flush=True)
                self.proc.kill()

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
        # one real output frame of silence; the keepalive injects one of these
        # per real frame period regardless of speed
        self._silence = bytes((int(AUDIO_RATE / FPS) + 2) * 4)

    def set_speed(self, speed: int) -> None:
        """Change stream speed on the running encoder. Speed only sets the push
        decimation ratio, read per push, so the new rate takes on the next frame
        with no encoder restart and no stream gap. _frame_i resets so the kept
        frame lands a whole speed-count after the switch."""
        speed = max(1, int(speed))
        with self._lock:
            if speed == self.speed:
                return
            self.speed = speed
            self._frame_i = 0
            self._next_deadline = time.monotonic()
        print(f"stream speed -> {speed}x", flush=True)

    def push(self, screen) -> None:
        """Drain this frame's audio, stream the frame and its audio only on every
        speed-th frame, and hold the loop to real time."""
        now = time.monotonic()
        # the channel is drained every frame so the blip buffer never backs up,
        # but only a kept frame's audio is written: speed-fold frames arrive per
        # real second, so keeping one in speed holds the stream at real time
        left, right = self.channels
        n = left.available
        left.read_into(self.audio_buf, n, 2, 0)
        right.read_into(self.audio_buf, n, 2, 1)
        with self._lock:
            self._mark_gap(now)
            self._main_push_at = now
            self._main_ident = threading.get_ident()
            self._traced = False
            self._frame_i += 1
            if self._frame_i % self.speed == 0:
                # audio goes first: ffmpeg probes its inputs one after another
                # before any demux thread runs, so a video write that blocks on a
                # full pipe while ffmpeg still waits for its first audio packet
                # deadlocks both
                self._write(self.audio, ffi.buffer(self.audio_buf, n * 4))
                self._write(self.video, ffi.buffer(screen.buffer, self.frame_bytes))
                self._sec_main += 1
            self._last_frame[:] = ffi.buffer(screen.buffer, self.frame_bytes)
            if self._injected:
                # the keepalive carried the timeline through the stall with repeats, so the frames
                # the loop renders now pace from here; pushing the backlog against the old deadline
                # put a stall's worth of extra frames into the encoder in one burst after every
                # battle exit and warp, the on-stream churn
                self._next_deadline = now
                self._injected = False
        self._next_deadline += 1 / (FPS * self.speed)
        delay = self._next_deadline - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    def _mark_gap(self, now: float) -> None:
        """Track the largest interval between consecutive pushes of either thread
        per wall second. Caller holds _lock."""
        if self._gap_prev is not None:
            sec = int(now)
            if self._gap_sec is None:
                self._gap_sec = sec
            elif sec != self._gap_sec:
                print(f"GAPLOG sec={self._gap_sec} max_gap_ms={self._gap_max * 1000:.1f} main={self._sec_main} "
                      f"keep={self._sec_keep} main_gap_ms={self._main_gap * 1000:.0f}", flush=True)
                self._gap_sec = sec
                self._gap_max = 0.0
                self._sec_main = self._sec_keep = 0
                self._main_gap = 0.0
            if now - self._gap_prev > self._gap_max:
                self._gap_max = now - self._gap_prev
        self._gap_prev = now

    def _keepalive(self) -> None:
        period = 1 / FPS
        due = None
        while True:
            time.sleep(period / 2)
            with self._lock:
                if self._closing:
                    return
                if self._main_push_at is None:
                    continue
                now = time.monotonic()
                # fire only after the main thread has been gone over two frame periods, then pay
                # one frame per period from the last push until it returns. The wake is late and
                # irregular under a GIL-holding stall (41 to 46 of 60 landed per second at one
                # frame per wake), so each wake writes every frame its deadline owes, capped
                if now - self._main_push_at <= 2 * period:
                    due = None
                    continue
                if due is None:
                    due = self._gap_prev + period
                owed = 0
                while due <= now and owed < KEEPALIVE_BURST_CAP:
                    self._inject(now)
                    due += period
                    owed += 1
                if owed:
                    self._trace_stall(now)

    def _inject(self, now: float) -> None:
        """One repeat of the last frame with one real frame of silence, the same amount a kept push
        writes, so an injected frame holds the audio clock at real time. Caller holds _lock."""
        self._audio_accum += AUDIO_RATE / FPS
        nsamp = int(self._audio_accum)
        self._audio_accum -= nsamp
        self._write(self.audio, self._silence[:nsamp * 4])
        self._write(self.video, self._last_frame)
        self._mark_gap(now)
        self._sec_keep += 1
        self._main_gap = max(self._main_gap, now - self._main_push_at)
        self._injected = True

    def _trace_stall(self, now: float) -> None:
        """Print the main thread's stack once per stall past STALL_TRACE_SECONDS, innermost first,
        so the GAPLOG line that follows has the function that held the loop beside it."""
        if self._traced or self._main_ident is None or now - self._main_push_at < STALL_TRACE_SECONDS:
            return
        self._traced = True
        frame = sys._current_frames().get(self._main_ident)
        chain = []
        while frame is not None and len(chain) < 7:
            chain.append(f"{os.path.basename(frame.f_code.co_filename)}:{frame.f_lineno} {frame.f_code.co_name}")
            frame = frame.f_back
        print(f"STALL {now - self._main_push_at:.1f}s main thread at " + " < ".join(chain), flush=True)

    def close(self) -> None:
        with self._lock:
            self._closing = True
        self._keeper.join(timeout=2)
        self._dog.join(timeout=2)
        self.video.close()
        self.audio.close()
        self.proc.wait(timeout=30)
