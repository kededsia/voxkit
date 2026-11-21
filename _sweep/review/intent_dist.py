"""What the intent system actually decided, across the whole film.

The point of `voxkit.intent` is that the *choice* is visible: not one pen for
every mark, not one vehicle for every note, not one arrival for every card. This
counts the decisions so the claim can be checked instead of believed.
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, ".")
from voxkit import config
from voxkit.cli import _context
from voxkit.gates.program import program_of

proj = config.discover(Path("film"))

reg = Counter()
pen = Counter()
col = Counter()
veh = Counter()
mov = Counter()
arr = Counter()
hits = 0
notes_n = 0

for n in range(1, 23):
    mod = "m%02d" % n
    prog = program_of(_context(proj, mod))
    for s in prog.shots:
        hits += sum(1 for k in s.camera if k.hit)
        for k in s.khats:
            veh[k.mode] += 1
            notes_n += 1
        for c in s.cards:
            arr[c.move or "(none)"] += 1
        for k in s.camera:
            if k.move:
                mov[k.move] += 1
        for m in s.marks:
            pen[m.pen] += 1
            col[m.color] += 1
            mov[m.move or "(none)"] += 1

print("cards arrival move :", dict(arr))
print("camera moves       :", dict(mov))
print("hits in film       :", hits)
print("notes              :", dict(veh), f"({notes_n} total)")
print("pens               :", dict(pen))
print("colours            :", dict(col))
