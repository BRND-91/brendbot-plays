"""The live-save ring keeps the last LIVE_RING snapshots and the write guard refuses every non-live
writer, so a stray probe or a careless restore can never bury the grind the way a 0-badge restore
once buried a 7-badge save."""
import os

import rowe_live


def test_guard_blocks_a_non_live_writer_to_the_live_save():
    for p in (rowe_live.LIVE_SAVE, os.path.join(rowe_live.RING_DIR, "20260101T0000.ss")):
        try:
            rowe_live.guard_write(p, is_live_run=False)
        except RuntimeError:
            continue
        raise AssertionError(f"a non-live write to {p} must raise")


def test_guard_allows_scratch_fixtures_and_the_live_run():
    rowe_live.guard_write("/tmp/probe_scratch.ss", is_live_run=False)
    rowe_live.guard_write("states/fixtures/route101.ss", is_live_run=False)
    rowe_live.guard_write(rowe_live.LIVE_SAVE, is_live_run=True)


def test_ring_prunes_to_the_last_LIVE_RING(tmp_path, monkeypatch):
    monkeypatch.setattr(rowe_live, "RING_DIR", str(tmp_path))
    cap = rowe_live.LIVE_RING
    for n in [f"202601{d:02d}T{h:02d}00.ss" for d in (1, 2) for h in range(cap)][: cap + 5]:
        (tmp_path / n).write_bytes(b"old")
    monkeypatch.setattr(rowe_live.time, "strftime", lambda *a, **k: "20260299T2359")
    rowe_live.archive(b"new")
    kept = sorted(p.name for p in tmp_path.iterdir())
    assert len(kept) == cap, f"ring kept {len(kept)}, want {cap}"
    assert "20260299T2359.ss" in kept, "the newest snapshot survives the prune"


if __name__ == "__main__":
    test_guard_blocks_a_non_live_writer_to_the_live_save()
    test_guard_allows_scratch_fixtures_and_the_live_run()
    print("test_rowe_live OK (run the ring test under pytest for tmp_path)")
