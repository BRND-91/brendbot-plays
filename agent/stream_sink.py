"""Push emulator frames and audio into the HLS stream Caddy serves at live.brenergy.net.

The core renders RGBX 32-bit at 240x160 into `Emu.screen.buffer` and mixes
stereo audio into two blip buffers; each frame both are written raw to an
encoder that scales 3x nearest-neighbour, encodes AAC, and emits rolling 2s
segments into /var/www/brenergy/live, the layout the player page reads.
"""
import fcntl
import os
import subprocess
import time

from mgba import ffi

OUT_DIR = "/var/www/brenergy/live"
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
RTSP_URL = "rtsp://127.0.0.1:8554/rowe"
# tee slave options: ':' separates them, so select names output streams by
# index (0 video, 1 aac, 2 opus, the -map order) instead of a 'a:1' specifier
RTSP_BRANCH = "[f=rtsp:rtsp_transport=tcp:select=0,2]" + RTSP_URL


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
    def __init__(self, core, width: int = 240, height: int = 160, out_dir: str = OUT_DIR):
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
        video_r, video_w = os.pipe()
        audio_r, audio_w = os.pipe()
        # ffmpeg probes each input in turn before any demux thread reads, so
        # the writer must never block on one pipe while the probe waits on the
        # other: a 1 MiB pipe holds 6 frames of video, and the probe flags cap
        # what the probe asks for; both were required to clear the deadlock
        for fd in (video_w, audio_w):
            fcntl.fcntl(fd, F_SETPIPE_SZ, PIPE_BYTES)
        probe = ["-probesize", "32", "-analyzeduration", "0"]
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
                hls_branch(out_dir) + "|" + RTSP_BRANCH,
            ],
            pass_fds=(video_r, audio_r),
        )
        os.close(video_r)
        os.close(audio_r)
        self.video = os.fdopen(video_w, "wb", buffering=0)
        self.audio = os.fdopen(audio_w, "wb", buffering=0)
        self._next_deadline = time.monotonic()

    def push(self, screen) -> None:
        """Write the audio a frame produced, then the frame, and hold the loop to real time."""
        # audio goes first: ffmpeg probes its inputs one after another before
        # any demux thread runs, so a video write that blocks on a full pipe
        # while ffmpeg still waits for its first audio packet deadlocks both
        left, right = self.channels
        n = left.available
        left.read_into(self.audio_buf, n, 2, 0)
        right.read_into(self.audio_buf, n, 2, 1)
        self.audio.write(ffi.buffer(self.audio_buf, n * 4))
        self.video.write(ffi.buffer(screen.buffer, self.frame_bytes))
        self._next_deadline += 1 / FPS
        delay = self._next_deadline - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        elif delay < -1:
            self._next_deadline = time.monotonic()

    def close(self) -> None:
        self.video.close()
        self.audio.close()
        self.proc.wait(timeout=30)
