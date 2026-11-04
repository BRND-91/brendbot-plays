# rowe-agent

Run `pytest` before every commit; the commit message includes the pass count.

## Working rules

- No subagents for reading files in this repo. Read the function directly by name with Grep + Read. Subagents only for a search across more than ten files.
- Never write, restore, or delete `states/live.ss` or `states/live/` without explicit approval. Probes use `/tmp` copies or `states/fixtures/`.
- Probe dumps and live dumps use different filename prefixes.
- Evidence cites its source (live/probe/test). Status claims quote a fresh read (log line, pid, mtime), otherwise "not checked".
- Once a cause is confirmed, make the change, then report symptom, evidence, change, verification. Output verbatim, "not run" for anything skipped.
- Every detached job writes a heartbeat line at least every 30s.
- `rowe-grind` is started and stopped only by Brendan.
