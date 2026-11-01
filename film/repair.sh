#!/usr/bin/env bash
# Repair what the gates found after the full generation pass.
#
# Three kinds of fault, all of them real and all of them cheap:
#
#   full-page pieces   the isolate model returned the whole page instead of one
#                      cutout, so the piece measures 1.0x1.0 and every gate
#                      downstream reports a symptom (a burial, a camera that
#                      cannot hold a figure, a mark that runs off the page).
#                      Found with `tools/find_bad_pieces.py`. The cause was the
#                      prompt: it named the piece but never said where it was, so
#                      the model had to find one clipping among five on a page of
#                      halftone newsprint. `iso_prompt` now carries a locator.
#
#   unwired puppets    m14 never had a `poses` run; m15/m16/m19 have puppets whose
#                      actions are declared and undrawn.
#
#   stale public/      `sync` is not in the `run` chain, so a fresh module fails
#                      its `public` gate on files that exist but are not where the
#                      renderer looks.
set -u

export PYTHONPATH=/d/VOX-PLUGIN-3
cd /d/VOX-PLUGIN-3/film || exit 1

LOG=build/_repair.log
: > "$LOG"
say() { echo "$(date +%H:%M:%S)  $*" >> "$LOG"; }

say "===== re-isolate full-page pieces ====="
py -u -m voxkit.cli isolate m15 --shots s04 --force >> "$LOG" 2>&1
say "m15 s04 exit $?"
py -u -m voxkit.cli isolate m16 --shots s01,s02,s05 --force >> "$LOG" 2>&1
say "m16 exit $?"
py -u -m voxkit.cli isolate m17 --shots s04,s05 --force >> "$LOG" 2>&1
say "m17 exit $?"
py -u -m voxkit.cli isolate m18 --shots s04,s05 --force >> "$LOG" 2>&1
say "m18 exit $?"
py -u -m voxkit.cli isolate m19 --shots s03,s04,s06,s11,s14 --force >> "$LOG" 2>&1
say "m19 exit $?"
py -u -m voxkit.cli isolate m22 --shots s06 --force >> "$LOG" 2>&1
say "m22 exit $?"

say "===== poses ====="
for m in m14 m15 m16 m19; do
  py -u -m voxkit.cli poses "$m" >> "$LOG" 2>&1
  say "$m poses exit $?"
done

# Rebuild every module whose layout or poses changed: a changed layout moves the
# camera and the marks, so the program is recomputed, never patched.
for m in m14 m15 m16 m17 m18 m19 m22; do
  say "===== $m emit ====="
  py -u -m voxkit.cli emit "$m" >> "$LOG" 2>&1
  say "$m emit exit $?"
  py -u -m voxkit.cli sync "$m" >> "$LOG" 2>&1
  say "----- $m gate -----"
  py -u -m voxkit.cli gate "$m" --no-cache --quiet >> "$LOG" 2>&1
  say "===== $m gate exit $? ====="
done

say "ALL DONE"
