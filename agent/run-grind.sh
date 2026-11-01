#!/bin/bash
# Supervise play.py for a wall-clock budget: every exit (stall, crash, timer) relaunches
# from the state file, which play.py only rewrites at responsive moments.
#   run-grind.sh [hours, default 10]
cd /opt/brendbot/rowe-agent || exit 1
end=$((SECONDS + ${1:-10} * 3600))
child=0
trap 'echo "supervisor: TERM, stopping run"; [ "$child" -gt 0 ] && kill -TERM "$child"; wait "$child"; exit 0' TERM INT
n=0
crashes=()
last_sig=""
same=0
while [ $((end - SECONDS)) -gt 120 ]; do
    n=$((n + 1))
    # the planner re-decides the goal from the last status before every launch, so a goal the
    # executor reached, or a grind it demoted itself to, never outlives the run that wrote it
    [ -f states/status.json ] && .venv/bin/python planner.py --apply
    echo "run $n start $(date +%T), $(( (end - SECONDS) / 60 )) min left"
    # append every run into one log so a bounce several relaunches back survives for diagnosis,
    # rotating at 50M with one kept since /etc/logrotate.d is read-only on this host
    [ -f states/grind.log ] && [ "$(stat -c%s states/grind.log)" -gt 52428800 ] && mv -f states/grind.log states/grind.log.1
    echo "=== run $n start $(date -u +%FT%TZ), $(( (end - SECONDS) / 60 )) min left ===" >>states/grind.log
    .venv/bin/python play.py --state states/live.ss --minutes $(( (end - SECONDS) / 60 )) >>states/grind.log 2>&1 &
    child=$!
    wait "$child"; code=$?
    echo "run $n exit $code at $(date +%T)"
    child=0
    reason=$(.venv/bin/python -c "import json; print(json.load(open('states/status.json'))['exit_reason'])" 2>/dev/null)
    case "$reason" in
        unsupported*) echo "supervisor: executor needs a decision ($reason)"; exit 0 ;;
    esac
    # stop a map that re-exits identically: 3 runs ending with the same reason at the same map+tile
    # means the planner keeps re-entering a dead spot, so post the reason and position and stop
    sig=$(.venv/bin/python -c "import json; s=json.load(open('states/status.json')); print('{}|{}|{}'.format(s.get('exit_reason'), s.get('map'), s.get('tile')))" 2>/dev/null)
    if [ -n "$reason" ] && [ "$sig" = "$last_sig" ]; then
        same=$((same + 1))
    else
        same=1; last_sig="$sig"
    fi
    if [ "$same" -ge 3 ]; then
        pos=$(.venv/bin/python -c "import json; s=json.load(open('states/status.json')); print('map {} tile {}'.format(s.get('map'), s.get('tile')))" 2>/dev/null)
        echo "supervisor: 3 identical exits '$reason' at $pos, stopping"
        /opt/brendbot/scripts/send-discord "1497841038323220651" "rowe grind stopped: 3 identical exits '$reason' at $pos"
        exit 1
    fi
    # stop a deterministic crash from relaunching into itself for hours: bound consecutive crashes
    # in a 10-minute window and back off between them
    if [ "$code" -ne 0 ] || [ "$reason" = crash ]; then
        now=$SECONDS
        kept=()
        for t in "${crashes[@]}"; do [ $((now - t)) -lt 600 ] && kept+=("$t"); done
        kept+=("$now")
        crashes=("${kept[@]}")
        echo "supervisor: crash ${#crashes[@]}/5 in 600s (exit $code reason ${reason:-none})"
        if [ "${#crashes[@]}" -ge 5 ]; then
            echo "supervisor: 5 crashes in 600s, stopping; traceback in states/grind.log"
            exit 1
        fi
        sleep $(( ${#crashes[@]} * 10 ))
    else
        crashes=()
        sleep 5
    fi
done
echo "supervisor: budget spent after $n runs"
