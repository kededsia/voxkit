#!/usr/bin/env bash
# Finish the film: wait for the repair already in flight, then converge the
# isolations, then render every chapter and join them.
#
# Why a chain and not three commands typed in sequence: the repair in flight takes
# over an hour, and the two steps after it cannot start until it stops. Waiting by
# hand means somebody has to be watching at the right moment; a chain means the
# work continues whether or not anyone is.
#
# Every step is resumable — `isolate` skips pieces that exist, `render` skips
# nothing but is safe to repeat, and `repair.py` measures before it acts — so this
# script can be killed and run again at any point.
set -u

export PYTHONPATH=/d/VOX-PLUGIN-3
cd /d/VOX-PLUGIN-3/film || exit 1

LOG=build/_finish_all.log
: > "$LOG"
say() { echo "$(date +%H:%M:%S)  $*" >> "$LOG"; }

say "waiting for the repair in flight"
for _ in $(seq 1 480); do
  grep -q "ALL DONE" build/_repair.log 2>/dev/null && break
  sleep 30
done
say "repair round one is done (or timed out)"

say "===== converge isolations ====="
py -u /d/VOX-PLUGIN-3/tools/repair.py >> "$LOG" 2>&1
say "repair.py exit $?"

# A re-cut rebuilds a slot, and a slot carries the puppet's frames. The wiring is
# preserved across a re-measure, but a module whose poses were never drawn at all
# has nothing to preserve — so draw them now, after the pieces are final. `poses`
# skips frames that exist, so this only costs the genuinely missing ones.
say "===== poses ====="
for m in $(seq -w 1 22); do
  m="m$m"
  out=$(py -u -m voxkit.cli poses "$m" 2>&1 | tail -1)
  say "$m: $out"
done

say "===== gate sweep ====="
for m in $(seq -w 1 22); do
  m="m$m"
  out=$(py -u -m voxkit.cli gate "$m" --no-cache --quiet 2>&1)
  fails=$(echo "$out" | grep FAIL | awk '{print $1}' | sort -u | tr '\n' ' ')
  say "$m: ${fails:-PASS}"
done

say "===== render ====="
bash render_all.sh >> "$LOG" 2>&1
say "render_all exit $?"

say "ALL DONE"
