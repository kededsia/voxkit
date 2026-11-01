#!/usr/bin/env bash
# Emit then render the modules that pass every gate on the current logic.
set -u
cd /d/VOX-PLUGIN-3/film || exit 1
export PYTHONPATH=/d/VOX-PLUGIN-3
mkdir -p ../_sweep/logs
: > ../_sweep/logs/_final.txt
for m in "$@"; do
  echo "=== $m emit $(date +%H:%M:%S)" | tee -a ../_sweep/logs/_final.txt
  py -m voxkit.cli emit "$m" >"../_sweep/logs/$m.emit.log" 2>&1 || { echo "    emit failed" | tee -a ../_sweep/logs/_final.txt; continue; }
  py -m voxkit.cli render "$m" >"../_sweep/logs/$m.final.log" 2>&1
  rc=$?
  tail -2 "../_sweep/logs/$m.final.log" | sed 's/^/    /' | tee -a ../_sweep/logs/_final.txt
  echo "    exit=$rc" | tee -a ../_sweep/logs/_final.txt
done
echo "=== done $(date +%H:%M:%S)" | tee -a ../_sweep/logs/_final.txt
