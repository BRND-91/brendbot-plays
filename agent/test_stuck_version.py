"""The executor-cap version is part of the stuck-hit key, so a crossing-primitive bump starts the
tally fresh, and _load_stuck_hits drops pre-version rows (the 32-miss Seagallop dock counts that
would otherwise re-gate the ferry on the first retry the bump grants)."""
import json

import map_graph
from play import Player


def test_stuck_key_carries_the_executor_version():
    k = Player._stuck_key((13, 10), (0, 75), frozenset({"SURF"}))
    assert k == f"13,10>0,75|SURF|v{map_graph.EXECUTOR_CAP_VERSION}", k


def test_load_drops_pre_version_rows(tmp_path):
    path = tmp_path / "stuck_hits.json"
    cur = f"13,10>0,75|SURF|v{map_graph.EXECUTOR_CAP_VERSION}"
    stale = "9,9>0,75|CUT,DIVE,SURF"  # a pre-version dock row sitting at the gate
    path.write_text(json.dumps({cur: 1, stale: 3}))
    loaded = Player.__new__(Player)._load_stuck_hits(str(path))
    assert loaded.get(cur) == 1
    assert stale not in loaded, "a pre-version dock row must be dropped on load"
