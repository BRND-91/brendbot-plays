"""The binding's mCorePythonCallbackCreate mallocs the core's callback struct and sets five of
its eight function pointers, so shutdown, savedataUpdated and alarm hold heap garbage, and
Core.__init__ copies that struct into the core's callback list. The core calls savedataUpdated
on the frame a flash save finishes syncing, which the Hall of Fame save was the first to do in
the live run: a jump into the garbage pointer segfaulted the executor at the ceremony's end in
every relaunch. Emu zeroes the three and re-registers, so the list entry the core reads holds
NULL where no callback exists."""
import emu_boot as eb
from mgba._pylib import ffi

UNSET = ("shutdown", "savedataUpdated", "alarm")
SET = ("videoFrameStarted", "videoFrameEnded", "coreCrashed", "sleep", "keysRead")


def test_core_callback_list_holds_null_for_the_unset_callbacks():
    e = eb.Emu()
    lst = e.core._native.coreCallbacks
    assert lst.size == 1
    entry = lst.vector[0]
    assert {k: int(ffi.cast("uintptr_t", getattr(entry, k))) for k in UNSET} == {k: 0 for k in UNSET}
    assert all(getattr(entry, k) != ffi.NULL for k in SET)
