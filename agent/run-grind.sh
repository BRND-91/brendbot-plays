#!/bin/bash
# Supervise play.py for a wall-clock budget: every exit (stall, crash, timer) relaunches
# from the state file, which play.py only rewrites at responsive moments.
#   run-grind.sh [hours, default 10]
cd /opt/brendbot/rowe-agent || exit 1
end=$((SECONDS + ${1:-10} * 3600))
child=0
trap 'echo "supervisor: TERM, stopping run"; [ "$child" -gt 0 ] && kill -TERM "$child"; wait "$child"; exit 0' TERM INT
n=0
while [ $((end - SECONDS)) -gt 120 ]; do
    n=$((n + 1))
    # the planner re-decides the goal from the last status before every launch, so a goal the
    # executor reached, or a grind it demoted itself to, never outlives the run that wrote it
    [ -f states/status.json ] && .venv/bin/python planner.py --apply
    echo "run $n start $(date +%T), $(( (end - SECONDS) / 60 )) min left"
    # capture the executor's per-turn decision prints so a reported misplay reads back from one
    # file instead of a console socket nothing records; truncated each run to the live fight
    .venv/bin/python play.py --state states/route101.ss --minutes $(( (end - SECONDS) / 60 )) >states/grind.out 2>&1 &
    child=$!
    wait "$child"
    echo "run $n exit $? at $(date +%T)"
    child=0
    reason=$(.venv/bin/python -c "import json; print(json.load(open('states/status.json'))['exit_reason'])" 2>/dev/null)
    case "$reason" in
        unsupported*) echo "supervisor: executor needs a decision ($reason)"; exit 0 ;;
    esac
    sleep 5
done
echo "supervisor: budget spent after $n runs"
