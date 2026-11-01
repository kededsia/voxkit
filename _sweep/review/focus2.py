"""Why does the eye have nowhere to land? Four more numbers.

  D. EVENT CADENCE     how often *anything* happens on the page, and whether
                       consecutive events are near each other or across the page.
  E. CROWDING          how many cards sit inside the visible frame at once — a
                       frame with six equal subjects has no subject.
  F. MARK -> WORD      a stroke must answer the sentence being spoken, so its
                       frame should be on a word, not merely on a card.
  G. REST              how much of the film has a camera that is genuinely still.
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

cadence, jumps, crowd, markword, stills = [], [], [], [], []
per_module = []

for m in modules:
    ctx = _context(proj, m)
    prog = program_of(ctx)
    accents = sorted(a.word.start_frame for a in ctx.narration.accents)
    mod_events = 0
    for sp in prog.shots:
        base = sp.start
        # D. events: a card lands, a stroke starts, a puppet turns, a note starts
        ev = [(c.settle, (c.rect.cx, c.rect.cy), "card") for c in sp.cards]
        ev += [(mk.at, (mk.box.cx, mk.box.cy), "mark") for mk in sp.marks]
        ev += [(p.at, (c.rect.cx, c.rect.cy), "pose")
               for c in sp.cards for p in c.poses]
        ev += [(k.at, (k.x + k.w / 2, k.y + k.h / 2), "note") for k in sp.khats]
        ev.sort()
        mod_events += len(ev)
        for (f0, p0, k0), (f1, p1, k1) in zip(ev, ev[1:]):
            cadence.append(f1 - f0)
            jumps.append(((p0[0] - p1[0]) ** 2 + (p0[1] - p1[1]) ** 2) ** 0.5)
        # E. crowding at each event
        for f, _, _ in ev:
            x, y, z = cam.resolve(sp.camera, f)
            hw = 0.5 / z
            inside = 0
            for c in sp.cards:
                if c.settle > f:
                    continue
                if abs(c.rect.cx - x) <= hw + c.rect.w / 2 and \
                   abs(c.rect.cy - y) <= hw + c.rect.h / 2:
                    inside += 1
            crowd.append(inside)
        # F. stroke vs word
        for mk in sp.marks:
            g = base + mk.at
            if accents:
                markword.append(min(abs(g - w) for w in accents))
        # G. still frames
        prev = None
        run = 0
        longest = 0
        for f in range(sp.span):
            p = cam.resolve(sp.camera, f)
            if prev is not None:
                d = abs(p[0] - prev[0]) + abs(p[1] - prev[1]) + abs(p[2] - prev[2])
                if d < 0.0004:
                    run += 1
                    longest = max(longest, run)
                else:
                    run = 0
            prev = p
        stills.append((longest, sp.span))
    per_module.append((m, mod_events))


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))]


print("D. EVENT CADENCE  n=%d  median %df (%.2fs)  p90 %df  p99 %df"
      % (len(cadence), q(cadence, .5), q(cadence, .5) / 30, q(cadence, .9), q(cadence, .99)))
print("   spatial jump between consecutive events: median %.3f  p90 %.3f of the page"
      % (q(jumps, .5), q(jumps, .9)))
print("E. CROWDING  cards inside the frame at an event: median %d  p90 %d  max %d"
      % (q(crowd, .5), q(crowd, .9), max(crowd)))
print("F. STROKE -> WORD  median %df  p75 %df  p90 %df  >24f: %d/%d"
      % (q(markword, .5), q(markword, .75), q(markword, .9),
         sum(1 for x in markword if x > 24), len(markword)))
long = [l for l, s in stills]
print("G. LONGEST GENUINELY STILL RUN per shot: median %df  p90 %df  max %df"
      % (q(long, .5), q(long, .9), max(long)))
print("   shots with a still run >= 20 frames: %d/%d" % (sum(1 for l in long if l >= 20), len(long)))
