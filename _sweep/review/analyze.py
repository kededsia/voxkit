"""Read the emitted program of all 22 modules and describe what the film does.

Not a gate. A census: what actually reaches the screen, how often, and how it
sits in time. Run from film/ with PYTHONPATH=/d/VOX-PLUGIN-3.
"""
from __future__ import annotations

import json
import sys
from collections import Counter

from pathlib import Path
from voxkit import config
from voxkit.cli import _context
from voxkit.gates.program import program_of

proj = config.discover(Path("."))
modules = [f"m{i:02d}" for i in range(1, 23)]

all_rows = []
grand = Counter()
for m in modules:
    ctx = _context(proj, m)
    if ctx is None:
        print(m, "NO CONTEXT")
        continue
    prog = program_of(ctx)
    shapes = Counter()
    marks = 0
    khats = 0
    poses = 0
    pose_cards = 0
    cards = 0
    gaps = []
    for sp in prog.shots:
        cards += len(sp.cards)
        marks += len(sp.marks)
        khats += len(sp.khats)
        for mk in sp.marks:
            shapes[mk.shape] += 1
        for c in sp.cards:
            if c.poses:
                pose_cards += 1
                poses += len(c.poses)
        # event density: every card settle, mark start, pose swap
        ev = sorted([c.settle for c in sp.cards]
                    + [mk.at for mk in sp.marks]
                    + [p.at for c in sp.cards for p in c.poses]
                    + [k.at for k in sp.khats])
        for a, b in zip(ev, ev[1:]):
            gaps.append(b - a)
        if ev:
            gaps.append(ev[0])
            gaps.append(sp.span - ev[-1])
    row = dict(module=m, shots=len(prog.shots), cards=cards, marks=marks,
               khats=khats, pose_cards=pose_cards, poses=poses,
               frames=sum(s.span for s in prog.shots),
               shapes=dict(shapes), gaps=gaps)
    all_rows.append(row)
    grand.update(shapes)
    print(f"{m}  shots {row['shots']:2d}  cards {cards:3d}  marks {marks:3d} "
          f"khat {khats:2d}  puppets {pose_cards:2d}/{poses:2d}  "
          f"maxgap {max(gaps) if gaps else 0:3d}f  "
          f"shapes {dict(shapes)}")

print()
print("SHAPE VOCABULARY OVER THE FILM:", dict(grand.most_common()))
print("TOTAL", {k: sum(r[k] for r in all_rows)
                for k in ("shots", "cards", "marks", "khats", "pose_cards", "poses", "frames")})

gaps = [g for r in all_rows for g in r["gaps"]]
gaps_sorted = sorted(gaps)
n = len(gaps_sorted)
print(f"EVENT GAPS  n={n}  median={gaps_sorted[n//2]}  p90={gaps_sorted[int(n*.9)]}  "
      f"p99={gaps_sorted[int(n*.99)]}  max={gaps_sorted[-1]}")
print("gaps > 45 frames:", sum(1 for g in gaps if g > 45))
print("gaps > 60 frames:", sum(1 for g in gaps if g > 60))

json.dump(all_rows, open("_rows.json", "w"), indent=1)
