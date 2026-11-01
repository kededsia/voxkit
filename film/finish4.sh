#!/usr/bin/env bash
# Emit, verify, render, join. The last mile.
#
# `gate` reads the program computed from the plan, so it sees a camera fix the
# moment it lands — but the *renderer* draws the emitted TSX, and that file is only
# rewritten by `emit`. Running this between a camera change and a render is the
# difference between a fixed film and a fixed gate report.
#
# `render` refuses a module whose gates fail, so a refusal here is the film telling
# you it is not ready; the join then reports the chapter as MISSING rather than
# quietly shipping a short film.
set -u

export PYTHONPATH=/d/VOX-PLUGIN-3
cd /d/VOX-PLUGIN-3/film || exit 1

LOG=build/_finish4.log
: > "$LOG"
say() { echo "$(date +%H:%M:%S)  $*" >> "$LOG"; }

say "===== emit every module ====="
for m in $(seq -w 1 22); do
  m="m$m"
  py -u -m voxkit.cli emit "$m" >> "$LOG" 2>&1 || say "$m emit FAILED"
done

say "===== sync + gate ====="
failing=0
for m in $(seq -w 1 22); do
  m="m$m"
  py -u -m voxkit.cli sync "$m" >> "$LOG" 2>&1
  out=$(py -u -m voxkit.cli gate "$m" --no-cache --quiet 2>&1)
  fails=$(echo "$out" | grep FAIL | awk '{print $1}' | sort -u | tr '\n' ' ')
  [ -n "$fails" ] && failing=$((failing + 1))
  say "$m: ${fails:-PASS}"
done
say "$failing module(s) failing"

say "===== render ====="
bash render_all.sh >> "$LOG" 2>&1
say "render_all exit $?"

say "ALL DONE"
