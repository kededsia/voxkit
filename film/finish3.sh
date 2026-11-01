#!/usr/bin/env bash
# The last asset pass, then the repair loop, then the gate table.
#
# What is left is small and specific:
#
#   * three puppets that land so late in their shot that only one pose swap fits.
#     The stage used to refuse anything under two swaps and left them static for
#     ever, which the `pose` gate correctly failed. One change is still a puppet
#     that moves.
#   * two pieces cut from a *cropped* reference (m17 `kartu_kerabat`, m18
#     `kartu_cara`). The crop made the model upscale the piece until it filled most
#     of its canvas, so the measured aspect is wrong and the `slot` gate sees a card
#     that would be stretched. The crop experiment is over; these are re-cut from
#     the page.
#   * m21 s06 needs a new page: its plan asked for a full-bleed indigo ground and
#     the `still` gate refused it as a modern colour photograph, correctly.
set -u

export PYTHONPATH=/d/VOX-PLUGIN-3
cd /d/VOX-PLUGIN-3/film || exit 1

LOG=build/_finish3.log
: > "$LOG"
say() { echo "$(date +%H:%M:%S)  $*" >> "$LOG"; }

say "===== the three late puppets ====="
for m in m15 m16 m19; do
  py -u -m voxkit.cli poses "$m" >> "$LOG" 2>&1
  say "$m poses exit $?"
done

say "===== drop the crop experiment ====="
rm -f build/m17/iso/s04-kartu_kerabat-a.crop.json \
      build/m18/iso/s04-kartu_cara-a.crop.json
rm -rf build/m17/iso/crops build/m18/iso/crops

say "===== re-cut the two crop-damaged pieces ====="
py -u -m voxkit.cli isolate m17 --shots s04 --pieces kartu_kerabat --force >> "$LOG" 2>&1
say "m17 kartu_kerabat exit $?"
py -u -m voxkit.cli isolate m18 --shots s04 --pieces kartu_cara --force >> "$LOG" 2>&1
say "m18 kartu_cara exit $?"

say "===== m21 s06 new page ====="
py -u -m voxkit.cli still m21 --shots s06 --force >> "$LOG" 2>&1
say "m21 still exit $?"
py -u -m voxkit.cli isolate m21 --shots s06 --force >> "$LOG" 2>&1
say "m21 isolate exit $?"

say "===== repair loop ====="
py -u /d/VOX-PLUGIN-3/tools/repair.py >> "$LOG" 2>&1
say "repair.py exit $?"

say "===== sync and gate every module ====="
for m in $(seq -w 1 22); do
  m="m$m"
  py -u -m voxkit.cli sync "$m" >> "$LOG" 2>&1
  out=$(py -u -m voxkit.cli gate "$m" --no-cache --quiet 2>&1)
  fails=$(echo "$out" | grep FAIL | awk '{print $1}' | sort -u | tr '\n' ' ')
  say "$m: ${fails:-PASS}"
done

say "ALL DONE"
