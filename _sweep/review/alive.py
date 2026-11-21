"""Camera motion, split by whether the pen is down.

The whole-film number is misleading in both directions. A film whose camera drifts
under every stroke is *moving* and wrong; a film that stops for the pen is *still*
and right. So the measurement that matters is the one taken **outside** the pen
windows: there the frame must be alive, and inside them it must not be.

Usage: python _sweep/review/alive.py m02
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
sys.path.insert(0, "_sweep/review")
import cammotion as cm  # noqa: E402
from voxkit import config  # noqa: E402
from voxkit.cli import _context  # noqa: E402
from voxkit.gates.program import program_of  # noqa: E402

STILL_PX = 0.6
PAD = 2

mod = sys.argv[1] if len(sys.argv) > 1 else "m02"
proj = config.discover(Path("film"))
prog = program_of(_context(proj, mod))

frames, fps = cm.read(Path(f"film/remotion/out/{mod}-final.mp4"))
motion = np.array(cm.motion(frames))
travel = np.concatenate([[0.0], motion[:, 2]])

pen = np.zeros(len(travel), dtype=bool)
for shot in prog.shots:
    for k in shot.marks:
        lo = max(0, shot.start + k.at - PAD)
        hi = min(len(pen), shot.start + k.at + k.duration + PAD + 1)
        pen[lo:hi] = True

still = travel < STILL_PX
ink = pen
free = ~pen

def pct(mask, base):
    return 100.0 * mask.sum() / max(1, base.sum())

print(f"=== {mod}   {len(travel)}f  {len(travel)/fps:.1f}s   pen {100*ink.mean():.0f}% of frames")
print(f"  still INSIDE the pen   {pct(still & ink, ink):5.1f}%  (must be ~100: the stroke is read on a still frame)")
print(f"  still OUTSIDE the pen  {pct(still & free, free):5.1f}%  (must be low: this is dead air)")
print(f"  median travel  all {np.median(travel):6.2f}px   free {np.median(travel[free]):6.2f}px")
print(f"  p90    travel  all {np.percentile(travel,90):6.2f}px   free {np.percentile(travel[free],90):6.2f}px")
print(f"  frames moving >2px: all {100*(travel>2).mean():4.1f}%   free {100*(travel[free]>2).mean():4.1f}%")

runs, i = [], 0
while i < len(still):
    if still[i]:
        j = i
        while j + 1 < len(still) and still[j + 1]:
            j += 1
        if j - i + 1 >= 20:
            runs.append((i, j - i + 1, bool(pen[i:j + 1].any())))
        i = j + 1
    else:
        i += 1
print(f"  still runs >=20f: {len(runs)}  ({sum(1 for r in runs if not r[2])} with no pen)")
for a, n, p in runs:
    if not p:
        print(f"    DEAD f{a}..{a+n}  {n}f  {n/fps:.2f}s")
