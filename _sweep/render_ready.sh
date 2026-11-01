#!/usr/bin/env bash
# Render every module that is already gate-clean and has its assets.
# One at a time: each render is CPU-bound and they would only starve each other.
set -u
cd /d/VOX-PLUGIN-3/film || exit 1
export PYTHONPATH=/d/VOX-PLUGIN-3
mkdir -p ../_sweep/logs
for m in "$@"; do
  log="../_sweep/logs/$m.render.log"
  echo "=== $m $(date +%H:%M:%S) ===" | tee -a ../_sweep/logs/_sweep.txt
  py -m voxkit.cli render "$m" >"$log" 2>&1
  rc=$?
  tail -3 "$log" | sed 's/^/    /' | tee -a ../_sweep/logs/_sweep.txt
  echo "    exit=$rc" | tee -a ../_sweep/logs/_sweep.txt
done
echo "=== sweep done $(date +%H:%M:%S) ===" | tee -a ../_sweep/logs/_sweep.txt
