"""Dump one shot's camera keys and strokes, so a freeze can be inspected.

Usage: python _sweep/review/keys.py m09 s04
"""
import sys
from pathlib import Path

sys.path.insert(0, ".")
from voxkit import config
from voxkit.cli import _context
from voxkit.emit import camera as cam
from voxkit.gates.program import program_of

mod = sys.argv[1] if len(sys.argv) > 1 else "m09"
want = sys.argv[2] if len(sys.argv) > 2 else ""

proj = config.discover(Path("film"))
prog = program_of(_context(proj, mod))
for shot in prog.shots:
    if want and shot.id != want:
        continue
    print(f"== {mod}/{shot.id}  start {shot.start}  span {shot.span}")
    for m in shot.marks:
        print(f"   stroke {m.shape:<16} at {m.at:4d} dur {m.duration:3d} "
              f"on {m.on or '(page)'} move {m.move or '-'}")
    for k in shot.camera:
        print(f"   key    f{k.at:4d}  x {k.x:.4f} y {k.y:.4f} z {k.zoom:.4f} "
              f"{k.ease:<6} {k.reason:<7} {'HIT' if k.hit else '':<3} {k.move or ''}")
