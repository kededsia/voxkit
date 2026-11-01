"""Move pieces apart until no piece is buried, and write the moves into the plan.

The `compose` gate fails a shot when a piece is more than 55 % covered by something
in front of it — paid for and mostly unseen. That is usually not a bad cutout and
not a bad still: it is two clippings that landed on top of each other. The remedy is
a `nudge`, which moves a piece without touching its measured size (§5.7 of
HANDOFF), so the fix costs no generation and no redraw.

The solver is deliberately dumb and honest:

  * it moves **either** piece in a bad pair, and prefers the smaller move;
  * it never reduces a piece's visible area — pushing a piece further off the page
    to win the pair is trading one fault for another;
  * it solves **all** pairs in a shot together, not one at a time. Fixing one pair
    by hand repeatedly created a new one: m02 s06 went from 63 % to 100 % that way.

    py tools/nudge.py m16 m17        # solve and write
    py tools/nudge.py --dry m16      # print the moves, change nothing
"""
from __future__ import annotations

import itertools
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILM = ROOT / "film"

#: The gate fails above 0.55. Solving to 0.50 leaves room for the fact that the
#: solver works in plan space and the gate measures the nudged measured box.
TARGET = 0.50
#: How much visible area a move may cost. Zero would forbid moving a piece that
#: already bleeds off the page, which is most of them.
SLACK = 0.02


def _rect(box: dict) -> tuple[float, float, float, float]:
    """(x0, y0, x1, y1) from a layout element."""
    return (float(box["x"]) - float(box["w"]) / 2,
            float(box["y"]) - float(box["h"]) / 2,
            float(box["x"]) + float(box["w"]) / 2,
            float(box["y"]) + float(box["h"]) / 2)


def _area(r) -> float:
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def _inter(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


def _visible(r) -> float:
    return _inter(r, (0.0, 0.0, 1.0, 1.0))


def _shift(r, dx: float, dy: float):
    return (r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy)


def solve(shot: dict, elements: dict) -> dict[str, tuple[float, float]]:
    """The smallest set of *additional* moves that un-buries this shot.

    Starts from where the pieces actually are — measured box plus any nudge the
    plan already carries — so the tool can be run repeatedly. Solving from the raw
    measured box would re-propose the same moves every time and never converge.
    """
    z = {c["name"]: int(c.get("z") or 0) for c in shot["cards"]}
    already = {c["name"]: tuple(c.get("nudge") or (0.0, 0.0)) for c in shot["cards"]}
    base = {c["name"]: _shift(_rect(elements[c["name"]]), *already.get(c["name"], (0.0, 0.0)))
            for c in shot["cards"] if c["name"] in elements}
    if len(base) < 2:
        return {}

    def worst(rects: dict) -> tuple[float, tuple[str, str] | None]:
        top, pair = 0.0, None
        for a, b in itertools.permutations(rects, 2):
            if z.get(a, 0) >= z.get(b, 0):
                continue                      # a is not below b
            frac = _inter(rects[a], rects[b]) / max(1e-9, _area(rects[a]))
            if frac > top:
                top, pair = frac, (a, b)
        return top, pair

    rects = dict(base)
    moves: dict[str, tuple[float, float]] = {}
    for _ in range(24):
        frac, pair = worst(rects)
        if frac <= TARGET or pair is None:
            break
        best = None
        for which in pair:
            current = rects[which]
            vis = _visible(current)
            for step in (0.02, 0.04, 0.06, 0.09, 0.12, 0.16, 0.20):
                for ang in range(0, 360, 15):
                    dx = round(step * math.cos(math.radians(ang)), 3)
                    dy = round(step * math.sin(math.radians(ang)), 3)
                    trial = dict(rects)
                    trial[which] = _shift(current, dx, dy)
                    if _visible(trial[which]) < vis - SLACK:
                        continue              # would push it further off the page
                    after, _ = worst(trial)
                    if after >= frac - 1e-6:
                        continue
                    if best is None or after < best[0]:
                        best = (after, which, dx, dy)
                if best is not None and best[0] <= TARGET:
                    break
            if best is not None and best[0] <= TARGET:
                break
        if best is None:
            break
        _after, which, dx, dy = best
        rects[which] = _shift(rects[which], dx, dy)
        ox, oy = moves.get(which, (0.0, 0.0))
        moves[which] = (round(ox + dx, 3), round(oy + dy, 3))
    return moves


def gate_failures(modules: list[str]) -> dict[str, set[str]]:
    """Shots with a `compose` failure, read from the gate's own report.

    The gate prints a verdict line (`compose   FAIL`) and then indented detail
    lines that begin with `sNN/<piece>: …`. The shot id is only on the detail, so
    a parser that reads the verdict line finds nothing and silently solves nothing.
    """
    out = {}
    for m in modules:
        r = subprocess.run([sys.executable, "-m", "voxkit.cli", "gate", m,
                            "--no-cache", "--quiet"],
                           cwd=FILM, text=True, capture_output=True,
                           env={**_env(), "PYTHONPATH": str(ROOT)})
        shots: set[str] = set()
        in_compose = False
        for line in (r.stdout or "").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if line[:1] not in (" ", "\t"):
                in_compose = stripped.startswith("compose") and "FAIL" in stripped
                continue
            if in_compose and "/" in stripped:
                shots.add(stripped.split("/")[0].strip())
        if shots:
            out[m] = shots
    return out


def _env():
    import os
    return dict(os.environ)


def main(argv: list[str]) -> int:
    dry = "--dry" in argv
    modules = [a for a in argv[1:] if not a.startswith("-")]
    if not modules:
        modules = [f"m{i:02d}" for i in range(1, 23)]

    failures = gate_failures(modules)
    if not failures:
        print("no compose failures")
        return 0

    changed = 0
    for module, shots in sorted(failures.items()):
        path = FILM / "plans" / f"{module}.json"
        plan = json.loads(path.read_text(encoding="utf-8"))
        for shot in plan["shots"]:
            if shot["id"] not in shots:
                continue
            layout_path = FILM / "build" / module / "cards" / shot["id"] / "layout.json"
            if not layout_path.is_file():
                continue
            elements = json.loads(layout_path.read_text(encoding="utf-8"))["elements"]
            moves = solve(shot, elements)
            if not moves:
                print(f"  {module} {shot['id']}: no move helps — needs a new still")
                continue
            for card in shot["cards"]:
                if card["name"] in moves:
                    dx, dy = moves[card["name"]]
                    ox, oy = card.get("nudge") or (0.0, 0.0)
                    card["nudge"] = [round(ox + dx, 3), round(oy + dy, 3)]
                    print(f"  {module} {shot['id']}/{card['name']}: "
                          f"nudge {dx:+.3f}, {dy:+.3f}  (total {card['nudge'][0]:+.3f}, "
                          f"{card['nudge'][1]:+.3f})")
                    changed += 1
        if not dry:
            path.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")
    print(f"{changed} piece(s) nudged" + (" (dry run)" if dry else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
