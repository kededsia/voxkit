"""Find pieces that came back as the whole page instead of a cutout.

`isolate` asks the model for one piece on a chroma field, then measures the
result. When the model returns the entire page instead — a chroma-key miss — the
measurement is honest and useless: the piece is measured at (or beyond) the full
frame, and every gate downstream then reports a burial, a camera that cannot hold
it, and a mark that runs off the page. Three different symptoms, one cause.

This finds the cause, per module and per piece, so the repair is one targeted
re-isolation instead of a hunt.

    py tools/find_bad_pieces.py            # every module with a layout
    py tools/find_bad_pieces.py m15        # one module
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

#: A piece measured at this fraction of the frame or more is not a cutout. Real
#: pieces run from about 0.2 to 0.8; a miss is 1.0 and up, because the measured
#: box is the page plus its torn edge.
FULL = 0.95

#: A piece that contains this much of another piece is not a cutout either — it is
#: the page with its ground removed. Size alone cannot see this: m21's
#: `kartu_mulai_hilang` came back 0.85 x 1.00, under the width test, and it held
#: three photographs and a second card inside its own box.
SWALLOW = 0.80

#: …and the swallowed piece has to be genuinely smaller than its swallower. Without
#: this, two pieces measured to the same box each "contain" the other and both get
#: re-isolated for nothing — m19 s16's laptop photograph was already correct.
SMALLER = 0.60

#: A piece covering this much of the page *area* is the page. Rules 1 and 2 both
#: miss the case that matters: m19 s11's `kartu_satu_nama` measured 0.99 x 0.91 —
#: under the height test, and too big for the "smaller" clause — while sitting on
#: top of four other pieces. Aspect is the wrong question; a clipping that covers
#: nine tenths of the sheet is not a clipping.
PAGE_AREA = 0.72


def _area(b: dict) -> float:
    return max(0.0, float(b.get("w", 0))) * max(0.0, float(b.get("h", 0)))


def _overlap(a: dict, b: dict) -> float:
    """What fraction of b's box lies inside a's?"""
    bw = _area(b)
    if bw <= 0:
        return 0.0
    x0 = max(float(a["x"]) - float(a["w"]) / 2, float(b["x"]) - float(b["w"]) / 2)
    x1 = min(float(a["x"]) + float(a["w"]) / 2, float(b["x"]) + float(b["w"]) / 2)
    y0 = max(float(a["y"]) - float(a["h"]) / 2, float(b["y"]) - float(b["h"]) / 2)
    y1 = min(float(a["y"]) + float(a["h"]) / 2, float(b["y"]) + float(b["h"]) / 2)
    return max(0.0, x1 - x0) * max(0.0, y1 - y0) / bw


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parents[1] / "film" / "build"
    if not root.is_dir():
        print(f"no build directory at {root}", file=sys.stderr)
        return 2

    wanted = argv[1:] or sorted(p.name for p in root.glob("m[0-9][0-9]"))
    total = 0
    for module in wanted:
        cards = root / module / "cards"
        if not cards.is_dir():
            continue
        bad: list[str] = []
        #: piece name -> shot, so the repair can name the piece and not the shot.
        where: dict[str, str] = {}
        for layout in sorted(cards.glob("*/layout.json")):
            shot = layout.parent.name
            try:
                elements = json.loads(layout.read_text(encoding="utf-8"))["elements"]
            except (json.JSONDecodeError, KeyError):
                bad.append(f"{shot}: layout is not readable")
                continue
            for name, box in elements.items():
                w = float(box.get("w", 0))
                h = float(box.get("h", 0))
                if w >= FULL and h >= FULL:
                    bad.append(f"{shot}/{name}  {w:.2f}x{h:.2f}")
                    where[name] = shot
                    continue
                if w * h >= PAGE_AREA:
                    bad.append(f"{shot}/{name}  {w:.2f}x{h:.2f}  "
                               f"(covers {w * h:.0%} of the page)")
                    where[name] = shot
                    continue
                eaten = [o for o, ob in elements.items()
                         if o != name and _overlap(box, ob) >= SWALLOW
                         and _area(ob) <= SMALLER * _area(box)]
                if len(eaten) >= 2:
                    bad.append(f"{shot}/{name}  {w:.2f}x{h:.2f}  "
                               f"(contains {len(eaten)} other pieces)")
                    where[name] = shot
        if bad:
            total += len(bad)
            print(f"\n{module}  {len(bad)} piece(s) came back as the whole page")
            for line in bad:
                print(f"  {line}")
            by_shot: dict[str, list[str]] = {}
            for name, shot in where.items():
                by_shot.setdefault(shot, []).append(name)
            for shot, names in sorted(by_shot.items()):
                print(f"  repair: vox isolate {module} --shots {shot} "
                      f"--pieces {','.join(sorted(names))} --force")

    if not total:
        print("no full-page pieces found")
    else:
        print(f"\n{total} piece(s) to re-isolate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
