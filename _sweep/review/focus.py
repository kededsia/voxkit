"""Is the camera bound to the word, and to the ink being drawn?

Three measurements per shot, all from the emitted program (what is rendered):

  A. PEN/FRAME AGREEMENT  while a stroke is being drawn, where is the frame
     pointing? Distance from the frame centre to the stroke's own centre, in
     units of the *visible* half-frame. >1.0 means the stroke's centre is
     outside the picture.

  B. CAMERA DURING INK  how far the frame travels while the pen is down,
     compared with how far it travels while the pen is up.

  C. WORD BINDING  for every camera key, the distance in frames to the nearest
     scored word. `camera.LEAD` says a key must precede its word by >=14.
"""
from __future__ import annotations

import json
from pathlib import Path

from voxkit import config
from voxkit.cli import _context
from voxkit.emit import camera as cam
from voxkit.gates.program import program_of

proj = config.discover(Path("."))
modules = [f"m{i:02d}" for i in range(1, 23)]

rows = []
for m in modules:
    ctx = _context(proj, m)
    prog = program_of(ctx)
    accents = [a.word.start_frame for a in ctx.narration.accents]
    for sp in prog.shots:
        if not sp.camera:
            continue
        base = sp.start
        # A. pen/frame agreement at the middle of every stroke
        bad = []
        for mk in sp.marks:
            mid = mk.at + mk.duration // 2
            cx, cy, z = cam.resolve(sp.camera, mid)
            half = 0.5 / z
            dx = (mk.box.cx - cx) / half
            dy = (mk.box.cy - cy) / half
            off = (dx * dx + dy * dy) ** 0.5
            if off > 0.85:
                bad.append((mk.shape, mk.on or "-", round(off, 2)))
        # B. camera travel while ink is down vs up
        def travel(a: int, b: int) -> float:
            if b <= a:
                return 0.0
            p0 = cam.resolve(sp.camera, a)
            p1 = cam.resolve(sp.camera, b)
            return ((p0[0] - p1[0]) ** 2 + (p0[1] - p1[1]) ** 2) ** 0.5
        ink_frames = set()
        for mk in sp.marks:
            ink_frames |= set(range(mk.at, min(sp.span, mk.at + mk.duration)))
        ink_move = [travel(f, f + 6) for f in ink_frames if f + 6 < sp.span]
        rest_move = [travel(f, f + 6) for f in range(sp.span - 6)
                     if f not in ink_frames]
        avg = lambda xs: sum(xs) / len(xs) if xs else 0.0
        # C. keys vs words
        lag = []
        for k in sp.camera:
            g = base + k.at
            if accents:
                lag.append(min(abs(g - w) for w in accents))
        rows.append(dict(module=m, shot=sp.id, span=sp.span,
                         marks=len(sp.marks), off=bad,
                         ink=avg(ink_move), rest=avg(rest_move),
                         lag=sorted(lag)))

# ------------------------------------------------------------------- report
tot_marks = sum(r["marks"] for r in rows)
off = [(r["module"], r["shot"]) + o for r in rows for o in r["off"]]
print(f"shots {len(rows)}  strokes {tot_marks}")
print(f"A. strokes whose centre sits outside the visible frame (off>0.85): {len(off)}")
for x in sorted(off, key=lambda t: -t[-1])[:15]:
    print("   ", x)

ink = sum(r["ink"] for r in rows) / len(rows)
rest = sum(r["rest"] for r in rows) / len(rows)
print(f"B. camera travel per 6 frames: pen down {ink:.4f}  pen up {rest:.4f}  "
      f"ratio {ink / rest if rest else 0:.2f}")

lags = [l for r in rows for l in r["lag"]]
lags.sort()
n = len(lags)
print(f"C. key->nearest word: median {lags[n//2]}f  p75 {lags[int(n*.75)]}f  "
      f"p90 {lags[int(n*.9)]}f  max {lags[-1]}f  "
      f">30f: {sum(1 for l in lags if l > 30)}/{n}")

json.dump(rows, open("_focus.json", "w"), indent=1)
