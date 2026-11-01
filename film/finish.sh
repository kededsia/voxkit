#!/usr/bin/env bash
# Finish every module that has no assets yet, in order, then gate it.
#
# Resumable by construction: every stage skips a job whose output is already on
# disk, so re-running this script after an interruption costs nothing and loses
# nothing. That is also why it is safe to kill: the filesystem is the progress
# bar, not a counter in here.
#
# m15 first: its five stills already exist, so it is 23 pieces of work and no
# generation of pages — the cheapest module in the queue and the one that proves
# the isolate → plate → emit path before the expensive ones start.
set -u

export PYTHONPATH=/d/VOX-PLUGIN-3
cd /d/VOX-PLUGIN-3/film || exit 1

LOG=build/_finish.log
: > "$LOG"

say() { echo "$(date +%H:%M:%S)  $*" >> "$LOG"; }

for m in m15 m16 m17 m18 m19 m21 m22; do
  say "===== $m START ====="
  py -m voxkit.cli run "$m" >> "$LOG" 2>&1
  code=$?
  say "===== $m chain exit $code ====="
  if [ "$code" -eq 0 ]; then
    py -m voxkit.cli gate "$m" --no-cache --quiet >> "$LOG" 2>&1
    say "===== $m gate exit $? ====="
  else
    say "===== $m chain stopped early; skipping gate ====="
  fi
done

say "ALL DONE"
