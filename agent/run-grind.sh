#!/bin/bash
# Supervise play.py for a wall-clock budget: every exit (stall, crash, timer) relaunches
# from the state file, which play.py only rewrites at responsive moments.
#   run-grind.sh [hours, default 10] [speed, default 1]
cd /opt/brendbot/rowe-agent || exit 1
end=$((SECONDS + ${1:-10} * 3600))
speed=${2:-1}
child=0
trap 'echo "supervisor: TERM, stopping run"; [ "$child" -gt 0 ] && kill -TERM "$child"; wait "$child"; exit 0' TERM INT
n=0
crashes=()
last_sig=""
same=0
spins=0
WATCH_INTERVAL=60   # seconds between live-progress samples
WATCH_FLAT=15       # flat samples (no new map, no new badge) before a non-grind run is called spun
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
    .venv/bin/python play.py --state states/live.ss --minutes $(( (end - SECONDS) / 60 )) --speed "$speed" >>states/grind.log 2>&1 &
    child=$!
    # live no-progress watchdog: a non-grind run that neither discovers a new map nor wins a badge for
    # WATCH_FLAT samples is bouncing a phantom route (the Seagallop chain into a ticket-locked island
    # reads as routable), which no exit-time check can catch because play.py never exits. TERM it at a
    # save point so the relaunch's planner.py --apply re-decides the goal. A grind holds one grass
    # patch, so a flat map count there is normal and never trips this.
    flat=0; pv=-1; pb=-1; spun=0
    while kill -0 "$child" 2>/dev/null; do
        sleep "$WATCH_INTERVAL"
        kill -0 "$child" 2>/dev/null || break
        prog=$(.venv/bin/python -c "import json,os; \
g=json.load(open('states/map_graph.json')) if os.path.exists('states/map_graph.json') else {}; \
s=json.load(open('states/status.json')) if os.path.exists('states/status.json') else {}; \
go=json.load(open('states/goal.json')) if os.path.exists('states/goal.json') else {}; \
print(len(g.get('visited',[])), s.get('badges',0), go.get('mode','?'))" 2>/dev/null)
        [ -z "$prog" ] && continue
        read -r v b m <<<"$prog"
        if [ "$m" = grind ] || [ "$m" = done ] || [ "$m" = "?" ]; then flat=0
        elif [ "$v" = "$pv" ] && [ "$b" = "$pb" ]; then flat=$((flat + 1)); else flat=0; fi
        pv=$v; pb=$b
        if [ "$flat" -ge "$WATCH_FLAT" ]; then
            echo "supervisor: no-progress spin ($v maps, $b badges, mode $m) for $((WATCH_FLAT * WATCH_INTERVAL))s, breaking to re-plan"
            echo "=== supervisor spin-break $(date -u +%FT%TZ): $v maps $b badges mode $m ===" >>states/grind.log
            kill -TERM "$child"; spun=1; break
        fi
    done
    wait "$child"; code=$?
    echo "run $n exit $code at $(date +%T)"
    child=0
    reason=$(.venv/bin/python -c "import json; print(json.load(open('states/status.json'))['exit_reason'])" 2>/dev/null)
    # a spin-break relaunches so the corrected goal takes effect, but a spin that keeps recurring is a
    # goal the planner cannot advance, so bound it the way 3 identical exits are bounded: stop and page.
    if [ "$spun" -eq 1 ]; then
        spins=$((spins + 1))
        echo "supervisor: spin-break $spins/3 (reason ${reason:-signal})"
        if [ "$spins" -ge 3 ]; then
            pos=$(.venv/bin/python -c "import json; s=json.load(open('states/status.json')); print('map {} tile {}'.format(s.get('map'), s.get('tile')))" 2>/dev/null)
            echo "supervisor: 3 spin-breaks in a row, goal not advancing, stopping at $pos"
            /opt/brendbot/scripts/send-discord "1497841038323220651" "rowe grind stopped: 3 no-progress spin-breaks in a row, goal not advancing (last $pos)"
            exit 1
        fi
        sleep 5
        continue
    fi
    spins=0
    case "$reason" in
        done*)
            # the Champion is beaten and the planner has no goal: post once and stop for good
            pos=$(.venv/bin/python -c "import json; s=json.load(open('states/status.json')); print('map {} tile {}'.format(s.get('map'), s.get('tile')))" 2>/dev/null)
            echo "supervisor: $reason at $pos, stopping"
            /opt/brendbot/scripts/send-discord "1497841038323220651" "rowe: Champion. $reason, at $pos. grind stopped."
            exit 0
            ;;
        unsupported*)
            # the executor can exit with nowhere left to explore. never stop the stream here:
            # planner.py --apply on the next loop re-decides a goal from the latest status, so the
            # run keeps moving. heartbeat, back off, loop.
            echo "supervisor: $reason, grind-hold $(date -u +%FT%TZ)"
            echo "=== supervisor grind-hold $(date -u +%FT%TZ): $reason ===" >>states/grind.log
            sleep 30
            continue
            ;;
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
