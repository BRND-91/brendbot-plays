"""Run the script-style test files pytest cannot collect, failing on any non-zero exit.

A test_*.py whose checks sit under a __main__ runner with no def test_ function is invisible to
pytest's collector, so a green summary used to hide both the file and any rot in it (test_bounce
had been failing unseen). This module finds each such file in this directory and runs it as a
subprocess under the same interpreter, asserting exit 0 with the captured output on failure. A new
script-style test is picked up here with no edit, and converting one to real pytest functions drops
it from this list automatically.
"""
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
SELF = pathlib.Path(__file__).name


def _is_script_test(path: pathlib.Path) -> bool:
    text = path.read_text()
    has_pytest_fn = any(ln.lstrip().startswith("def test_") for ln in text.splitlines())
    has_main = '__name__ == "__main__"' in text or "__name__ == '__main__'" in text
    return has_main and not has_pytest_fn


SCRIPT_TESTS = sorted(p.name for p in HERE.glob("test_*.py")
                      if p.name != SELF and _is_script_test(p))


@pytest.mark.parametrize("script", SCRIPT_TESTS)
def test_script_passes(script):
    r = subprocess.run([sys.executable, str(HERE / script)],
                       capture_output=True, text=True, timeout=300, cwd=HERE)
    assert r.returncode == 0, (
        f"{script} exited {r.returncode}\n--- stdout ---\n{r.stdout[-2000:]}\n"
        f"--- stderr ---\n{r.stderr[-2000:]}")
