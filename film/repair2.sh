#!/usr/bin/env bash
# Second repair round.
#
# Round one fixed the misses that measured as the whole page in BOTH axes. Then
# `tools/find_bad_pieces.py` learned a second rule — a piece that swallows other
# pieces is the page with its ground removed, whatever its width says — and found
# thirty-three more, mostly in the modules that were generated last (m19–m22).
#
# m21 s06 also needs a new page. Its plan asked for a "full-bleed indigo page" and
# the still gate refused it as a modern digital colour photograph: correct, because
# twenty-one other pages are cream and the pieces are warm sepia, so the page was
# fighting its own clippings. The indigo idea is right for a shot about indigo dye;
# a full-bleed indigo page is not. The plan now keeps the indigo as a block, so the
# page still reads as paper.
set -u

export PYTHONPATH=/d/VOX-PLUGIN-3
cd /d/VOX-PLUGIN-3/film || exit 1

LOG=build/_repair2.log
: > "$LOG"
say() { echo "$(date +%H:%M:%S)  $*" >> "$LOG"; }

say "===== m21 s06 new page ====="
py -u -m voxkit.cli still m21 --shots s06 --force >> "$LOG" 2>&1
say "m21 still exit $?"

say "===== remaining swallowed pieces ====="
py -u -m voxkit.cli isolate m19 --shots s02,s05,s08,s12 --force >> "$LOG" 2>&1
say "m19 exit $?"
py -u -m voxkit.cli isolate m20 --shots s05 --force >> "$LOG" 2>&1
say "m20 exit $?"
py -u -m voxkit.cli isolate m21 --shots s01,s02,s03,s04,s06 --force >> "$LOG" 2>&1
say "m21 exit $?"
py -u -m voxkit.cli isolate m22 --shots s01,s02,s03,s05,s07 --force >> "$LOG" 2>&1
say "m22 exit $?"

say "===== poses ====="
for m in m19 m20 m21 m22; do
  py -u -m voxkit.cli poses "$m" >> "$LOG" 2>&1
  say "$m poses exit $?"
done

for m in m19 m20 m21 m22; do
  say "===== $m emit ====="
  py -u -m voxkit.cli emit "$m" >> "$LOG" 2>&1
  say "$m emit exit $?"
  py -u -m voxkit.cli sync "$m" >> "$LOG" 2>&1
  say "----- $m gate -----"
  py -u -m voxkit.cli gate "$m" --no-cache --quiet >> "$LOG" 2>&1
  say "===== $m gate exit $? ====="
done

say "ALL DONE"
