#!/usr/bin/env bash
# Second pass: the two modules whose stills were rejected for prompt length, then
# a sync + gate over everything that has a program.
#
# The first pass could not finish m17 and m18: gflow rejects a batch when any one
# prompt is over 2000 characters, and both had a 2146-character page. The trim in
# `prompt.py` now guarantees the cap, so they are re-run here.
#
# `sync` is not in the `run` chain, and without it the `public` gate fails on
# every fresh module — the cards are on disk but not where the renderer looks.
set -u

export PYTHONPATH=/d/VOX-PLUGIN-3
cd /d/VOX-PLUGIN-3/film || exit 1

LOG=build/_finish2.log
: > "$LOG"
say() { echo "$(date +%H:%M:%S)  $*" >> "$LOG"; }

for m in m17 m18 m19; do
  say "===== $m START ====="
  py -u -m voxkit.cli run "$m" >> "$LOG" 2>&1
  say "===== $m chain exit $? ====="
done

# Every module that has a program: sync, then gate. A module without a shot file
# is simply not built yet and is named as such rather than silently skipped.
for m in m01 m02 m03 m04 m05 m06 m07 m08 m09 m10 m11 m12 m13 m14 m15 m16 m17 m18 m19 m20 m21 m22; do
  if [ ! -f "remotion/src/shots/$(echo "$m" | tr 'a-z' 'A-Z').tsx" ]; then
    say "$m: no program"
    continue
  fi
  py -u -m voxkit.cli sync "$m" >> "$LOG" 2>&1
  say "----- $m gate -----"
  py -u -m voxkit.cli gate "$m" --no-cache --quiet >> "$LOG" 2>&1
  say "===== $m gate exit $? ====="
done

say "ALL DONE"
