"""How stressed the cards actually are, so `SNAP_AT` is a measured line.

A camera hit is earned by a stressed word. If the line sits where almost nothing
crosses it, the camera never emphasises; set it too low and every card is
"stressed", which is the same as none of them being. This prints the
distribution so the threshold can be argued from the film, not from taste.
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, ".")
from voxkit import config
from voxkit.cli import _context
from voxkit.emit.choreography import SNAP_AT
from voxkit.gates.program import program_of

proj = config.discover(Path("film"))

buckets = Counter()
scores = []

for n in range(1, 23):
    mod = "m%02d" % n
    ctx = _context(proj, mod)
    if ctx is None or ctx.narration is None:
        continue
    prog = program_of(ctx)
    for shot in prog.shots:
        pshot = ctx.plan.shot(shot.id)
        if pshot is None:
            continue
        words = {c.name: c.word for c in pshot.cards}
        for card in shot.cards:
            w = words.get(card.name, "")
            a = ctx.narration.score(shot.start + card.settle, w)
            scores.append(a)
            buckets[round(a, 1)] += 1

scores.sort()
n = len(scores)
print(f"cards measured {n}   SNAP_AT {SNAP_AT}   "
      f"crossing {sum(1 for a in scores if a >= SNAP_AT)} "
      f"({100 * sum(1 for a in scores if a >= SNAP_AT) / max(1, n):.1f}%)")
for b in sorted(buckets):
    print(f"  {b:.1f}  {buckets[b]:4d}  {'#' * min(60, buckets[b])}")
for p in (0.50, 0.75, 0.90, 0.95, 0.99):
    print(f"  p{int(p * 100):02d} = {scores[min(n - 1, int(n * p))]:.3f}")
