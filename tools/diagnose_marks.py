"""Measure every hand-drawn mark against the card it is supposed to point at.

The complaint was: *"hand-drawn arrows and strokes often miss the word that is
coming into focus."* Three different faults can produce that, and they look
identical in a render, so the first job is to tell them apart with numbers.

  registration  the mark's box is not on the card's box (a stale layout, a
                prose rect read as a measured one, a pad in the wrong unit);
  timing        the mark fires before the card lands, or long after, so the pen
                traces empty paper or a card the voice has finished with;
  focus         the mark fires while the camera and the narration are on a
                different card — the mark is drawn correctly, on the right card,
                at the wrong moment, and the eye is elsewhere.

Run:  py tools/diagnose_marks.py [--module m04] [--verbose]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voxkit import config as cfg  # noqa: E402
from voxkit.contract import Plan  # noqa: E402
from voxkit.emit import camera as cam  # noqa: E402
from voxkit.emit.choreography import build_module  # noqa: E402
from voxkit.geometry import Rect  # noqa: E402
from voxkit.layout import Layout  # noqa: E402
from voxkit.words import Narration  # noqa: E402

# A mark drawn more than this many frames after its card lands is answering a
# word the voice has moved past.
LATE = 10
# ...and more than this many frames before it lands is drawing on blank paper.
EARLY = -6


def _window(x: float, y: float, zoom: float) -> Rect:
    """What the frame can see, in page fractions."""
    hw, hh = 0.5 / zoom, 0.5 / zoom
    return Rect(x - hw, y - hh, x + hw, y + hh)


def _visible_share(rect: Rect, win: Rect) -> float:
    return 0.0 if rect.area <= 0 else rect.intersect(win) / rect.area


def _focus(shot, frame: int) -> tuple[str, float] | None:
    """The card the camera is centred on at `frame`, and how centred it is."""
    x, y, zoom = cam.resolve(shot.camera, frame)
    best: tuple[str, float] | None = None
    for c in shot.cards:
        d = max(abs(c.rect.cx - x), abs(c.rect.cy - y))
        if best is None or d < best[1]:
            best = (c.name, d)
    return best


def measure(project, module: str, verbose: bool) -> list[dict]:
    plan_path = project.plan(module)
    if not plan_path.is_file():
        return []
    transcript = project.transcript(module)
    if not transcript.is_file():
        return []
    plan = Plan.load(plan_path, project.height / project.width)
    narration = Narration.from_file(transcript, project.fps)

    layouts: dict[str, Layout] = {}
    for shot in plan.shots:
        p = project.card_dir(module, shot.id) / "layout.json"
        if p.is_file():
            layouts[shot.id] = Layout.load(p)
    if len(layouts) != len(plan.shots):
        return []

    def plate_for(sid: str) -> str:
        return f"{module}/plates/{sid}.jpg"

    prog = build_module(plan, layouts, narration, plate_for, fps=project.fps,
                        prefix=f"{module}/")

    rows: list[dict] = []
    for shot in prog.shots:
        plan_shot = plan.shot(shot.id)
        for i, m in enumerate(shot.marks):
            target = shot.card(plan_shot.marks[i].card) if plan_shot else None
            mid = m.at + m.duration // 2
            x, y, zoom = cam.resolve(shot.camera, mid)
            win = _window(x, y, zoom)
            row = {
                "module": module, "shot": shot.id, "i": i, "shape": m.shape,
                "card": target.name if target else "?", "at": m.at,
                "dur": m.duration, "settle": target.settle if target else -1,
                "zoom": zoom, "focus": (_focus(shot, mid) or ("?", 0))[0],
            }
            row["lag"] = row["at"] - row["settle"]
            if target:
                # registration: how much of the mark's box is the card, and how
                # much of the card the box covers
                row["mark_on_card"] = (m.box.intersect(target.rect) / m.box.area
                                       if m.box.area else 0.0)
                row["card_in_mark"] = (m.box.intersect(target.rect) / target.rect.area
                                       if target.rect.area else 0.0)
                # Visibility is measured on the part of the card that exists.
                # A slot that runs off the page has no ink beyond the edge, so
                # asking whether the whole slot is on screen asks for paper that
                # was never printed — and it reported 115 of 205 marks as clipped
                # when most of them were only hanging off the page.
                visible = target.rect.clamped()
                row["seen_at_start"] = _visible_share(visible, win)
                x2, y2, z2 = cam.resolve(shot.camera, m.at + m.duration)
                row["seen_at_end"] = _visible_share(visible, _window(x2, y2, z2))
                # ...and is anything lying on top of it while the pen draws?
                # Only pieces ABOVE it: a card underneath does not hide the one
                # being marked, and counting it reported 56 marks as buried when
                # most were simply pasted over something.
                # Only pieces above it AND already on the page: a card that has
                # not arrived yet is not lying on anything.
                zs = {c.name: c.z for c in plan_shot.cards} if plan_shot else {}
                row["buried"] = max(
                    (target.rect.covered_by(o.rect) for o in shot.cards
                     if o.name != target.name and zs.get(o.name, 0) > zs.get(target.name, 0)
                     and o.settle <= mid),
                    default=0.0)
            else:
                row["mark_on_card"] = row["card_in_mark"] = 0.0
                row["seen_at_start"] = row["seen_at_end"] = 0.0
                row["buried"] = 0.0
            row["is_focus"] = row["focus"] == row["card"]
            rows.append(row)
            if verbose:
                print(f"  {module}/{shot.id} [{i}] {m.shape:12s} -> {row['card']:18s} "
                      f"at {m.at:3d} settle {row['settle']:3d} lag {row['lag']:+4d} "
                      f"zoom {zoom:.2f} focus={row['focus']:<18s} "
                      f"on-card {row['mark_on_card']:.0%} card-in {row['card_in_mark']:.0%} "
                      f"seen {row['seen_at_start']:.0%}/{row['seen_at_end']:.0%} "
                      f"buried {row['buried']:.0%}")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", action="append")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--root", default=str(ROOT / "film"))
    a = ap.parse_args()

    project = cfg.discover(Path(a.root))
    modules = a.module or [f"m{i:02d}" for i in range(1, 23)]
    rows: list[dict] = []
    for mod in modules:
        got = measure(project, mod, a.verbose)
        if got:
            print(f"{mod}: {len(got)} mark(s)")
        rows.extend(got)

    if not rows:
        print("no marks measured")
        return 1

    n = len(rows)
    off_focus = [r for r in rows if not r["is_focus"]]
    late = [r for r in rows if r["lag"] > LATE]
    early = [r for r in rows if r["lag"] < EARLY]
    clipped = [r for r in rows if r["seen_at_start"] < 0.995 or r["seen_at_end"] < 0.995]
    loose = [r for r in rows if r["card_in_mark"] < 0.9]
    stray = [r for r in rows if r["mark_on_card"] < 0.75]

    print(f"\n{n} marks measured\n")
    print(f"  fires > {LATE} frames after landing    {len(late):3d}  "
          f"({len(late)/n:.0%})   worst lag {max((r['lag'] for r in rows), default=0):+d}")
    print(f"  fires before the card lands        {len(early):3d}")
    print(f"  card partly outside the frame      {len(clipped):3d}")
    buried = [r for r in rows if r["buried"] > 0.35]
    print(f"  card buried while the pen draws    {len(buried):3d}")
    print(f"  box does not cover the card        {len(loose):3d}")
    print(f"  box mostly empty paper             {len(stray):3d}")

    if clipped:
        print("\n  marks whose card is not whole in the frame:")
        for r in sorted(clipped, key=lambda r: r["seen_at_start"])[:25]:
            print(f"    {r['module']}/{r['shot']} {r['shape']:12s} -> {r['card']:18s} "
                  f"at {r['at']:3d} · seen {r['seen_at_start']:.0%}/{r['seen_at_end']:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
