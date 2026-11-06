"""Load the locally built libmgba + cffi binding and expose a raw-core helper.

Import this before `import mgba` anywhere in rowe-agent. The build is in
mgba-build/ (libmgba.so.0.10.5 + python/lib.*/mgba); mgba-stubs.so supplies
the e-Reader symbols the header exports but the ffmpeg-less build omits.
"""
import ctypes
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "mgba-build")
ROM = "/opt/brendbot/games/rowe/rowe-v2.1b.gba"

_lib = sorted(glob.glob(BUILD + "/**/libmgba.so.0.10*", recursive=True))[0]
ctypes.CDLL(_lib, mode=ctypes.RTLD_GLOBAL)
ctypes.CDLL(os.path.join(HERE, "mgba-stubs.so"), mode=ctypes.RTLD_GLOBAL)
_pydir = os.path.dirname(os.path.dirname(sorted(glob.glob(BUILD + "/python/lib.*/mgba/_pylib*.so"))[0]))
if _pydir not in sys.path:
    sys.path.insert(0, _pydir)

# the vendored 0.10 binding imports the external `cached_property` package, which is absent under
# py3.14; functools.cached_property (stdlib since 3.8) is the same descriptor, aliased under that name
import functools as _functools
import types as _types

if "cached_property" not in sys.modules:
    _cp = _types.ModuleType("cached_property")
    _cp.cached_property = _functools.cached_property
    sys.modules["cached_property"] = _cp

import mgba.core  # noqa: E402
import mgba.image  # noqa: E402
import mgba.log  # noqa: E402
import mgba.vfs  # noqa: E402
from mgba import ffi  # noqa: E402

KEY_A, KEY_B, KEY_SELECT, KEY_START = 1, 2, 4, 8
KEY_RIGHT, KEY_LEFT, KEY_UP, KEY_DOWN = 16, 32, 64, 128


class Emu:
    def __init__(self, rom: str = ROM, save: str | None = None):
        mgba.log.silence()
        self.core = mgba.core.load_path(rom)
        if not self.core:
            raise RuntimeError(f"load_path failed: {rom}")
        if save:
            self._save = mgba.vfs.open_path(save, "r+")
            self.core.load_save(self._save)
        self.screen = mgba.image.Image(*self.core.desired_video_dimensions())
        self.core.set_video_buffer(self.screen)
        self.core.reset()

    def run(self, frames: int, keys: int = 0) -> None:
        self.core._core.setKeys(self.core._core, keys)
        for _ in range(frames):
            self.core.run_frame()
        self.core._core.setKeys(self.core._core, 0)

    def tap(self, keys: int, hold: int = 8, gap: int = 12) -> None:
        self.run(hold, keys)
        self.run(gap)

    def ewram(self) -> bytes:
        return bytes(ffi.buffer(ffi.cast("char*", self.core._native.memory.wram), 0x40000))

    def iwram(self) -> bytes:
        return bytes(ffi.buffer(ffi.cast("char*", self.core._native.memory.iwram), 0x8000))

    def read(self, address: int, length: int = 1) -> bytes:
        bank = address >> 24
        if bank == 2:
            off = address & 0x3FFFF
            return self.ewram()[off:off + length]
        if bank == 3:
            off = address & 0x7FFF
            return self.iwram()[off:off + length]
        return bytes(self.core._core.busRead8(self.core._core, address + i) & 0xFF for i in range(length))

    def u32(self, address: int) -> int:
        return int.from_bytes(self.read(address, 4), "little")

    def write(self, address: int, data: bytes) -> None:
        """Patch EWRAM or IWRAM in place; used to stage fixtures (exp just under a level-up)."""
        bank = address >> 24
        if bank == 2:
            buf, off = ffi.buffer(ffi.cast("char*", self.core._native.memory.wram), 0x40000), address & 0x3FFFF
        elif bank == 3:
            buf, off = ffi.buffer(ffi.cast("char*", self.core._native.memory.iwram), 0x8000), address & 0x7FFF
        else:
            raise ValueError(f"write outside work RAM: {address:#x}")
        buf[off:off + len(data)] = data

    def save_png(self, path: str) -> None:
        self.screen.to_pil().convert("RGB").save(path)

    def save_state(self) -> bytes:
        return bytes(ffi.buffer(self.core.save_raw_state()))

    def load_state(self, state: bytes) -> None:
        self.core.load_raw_state(state)
