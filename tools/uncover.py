"""Raise a figure above whatever is covering its head — and only when that is safe.

The client's rule is absolute: head and neck clear, always. v2 fixed it by swapping
the layer, never by nudging the card, because a card 45-114 px off its slot leaves a
printed slip with no card over it — the plate fills the hole and the eye reads two of
everything. This is the same fix, against v3's data.

Two refusals, both measured:

* **A swap that buries the other card's lettering is refused.** A silhouette over a
  blank margin of a slip is collage; a silhouette over "4.000 M" is a lost fact. The
  card's ink is its dark pixels inside its own alpha, and a raise may put the person
  over at most `CARD_INK` of them.
* **A swap that leaves the person still covered is refused.** Raising above one
  coverer can put the person under another; the check is re-run, not assumed.

    py tools/uncover.py m20 --dry
    py tools/uncover.py m20 --shot s02
    py tools/uncover.py --all

Writes the plan's `z` (the emitter stacks by it, so a re-emit is enough — unlike v2,
where the JSX paint order had to be edited as well) and re-emits the module. It does
not render: a chapter whose `.tsx` is newer than its `.mp4` is stale, and
`film/render_all.sh` picks it up.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voxkit import config                                    # noqa: E402
from voxkit.contract import Plan                             # noqa: E402
from voxkit.figure import _place, covered, stack              # noqa: E402
from voxkit.layout import Layout                             # noqa: E402

#: A raise may put the person over at most this share of another card's lettering.
CARD_INK = 0.10


def plan_path(film: Path, module: str) -> Path:
    return film / "plans" / f"{module}.json"


def fix_shot(project, film: Path, module: str, plan: Plan, shot, dry: bool) -> list[str]:
    """Try to clear every covered head in one shot. Returns what happened, in words."""
    lay_p = project.card_dir(module, shot.id) / "layout.json"
    if not lay_p.is_file():
        return [f"{shot.id}: no layout.json"]
    layout = Layout.load(lay_p)

    log: list[str] = []
    # Each raise changes the stack, so re-measure after every one.
    for _ in range(6):
        hits = covered(project, module, plan, shot, layout)
        if not hits:
            break
        target = hits[0]
        card = next(c for c in shot.cards if c.name == target.card)
        # Where the person has to go: above every card currently on top of its head.
        owner, placed = stack(project, module, shot, layout)
        by_index = {p.name: p for p in placed}
        coverers = [by_index[n] for n in target.by if n in by_index]
        if not coverers:
            log.append(f"{shot.id}/{card.name}: covered but no coverer found — skipped")
            break
        new_z = max(c.card.z for c in coverers if c.card is not None) + 1
        # A map is place names edge to edge, and R6 keeps it above everything. A
        # figure standing anywhere on a map buries words, so this is not a pair the
        # free `readable` gate may excuse — the shot has to be recomposed.
        maps = [c.card.name for c in coverers if c.card is not None and c.card.bahan == "peta"]
        if maps:
            log.append(f"{shot.id}/{card.name}: refused — {', '.join(maps)} is a map, "
                       "and a map stays above a figure (R6). Recompose the still")
            break
        if new_z <= card.z:
            log.append(f"{shot.id}/{card.name}: already above its coverers — skipped")
            break

        # Would the raise bury another card's lettering? Measured on the stage, not
        # on the card: two pieces resampled to their own boxes are different sizes,
        # and `mask & ink` on those two arrays is a shape error, not an answer.
        person = by_index.get(card.name)
        if person is None:
            log.append(f"{shot.id}/{card.name}: no piece on disk — skipped")
            break
        size = (owner.shape[1], owner.shape[0])
        pmask = _place(person.mask, person.box, size)
        worst, worst_name = 0.0, ""
        for q in placed:
            if q.index <= person.index:
                continue
            qink = _place(q.ink, q.box, size)
            inter = pmask & qink
            if not inter.any():
                continue
            share = float(inter.sum()) / float(qink.sum()) if qink.any() else 0.0
            if share > worst:
                worst, worst_name = share, q.name
        if worst > CARD_INK:
            log.append(f"{shot.id}/{card.name}: raise refused — it would bury "
                       f"{worst:.0%} of {worst_name}'s lettering")
            break

        log.append(f"{shot.id}/{card.name}: z {card.z} -> {new_z} "
                   f"(clears {', '.join(sorted(target.by, key=lambda n: -target.by[n]))}; "
                   f"worst lettering cost {worst:.0%} {worst_name or '-'})")
        if dry:
            break
        # Apply: mutate the plan file's z, then re-measure from the file.
        p = plan_path(film, module)
        raw = json.loads(p.read_text(encoding="utf-8"))
        for s in raw["shots"]:
            if s["id"] != shot.id:
                continue
            for c in s["cards"]:
                if c["name"] == card.name:
                    c["z"] = new_z
        p.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        plan = Plan.load(p, project.width / project.height)
        shot = next(s for s in plan.shots if s.id == shot.id)
    return log


def run(module: str, dry: bool, only: str) -> int:
    film = ROOT / "film"
    project = config.discover(film)
    plan = Plan.load(project.require_module(module), project.width / project.height)
    changed = False
    for shot in plan.shots:
        if only and shot.id != only:
            continue
        for line in fix_shot(project, film, module, plan, shot, dry):
            print(f"  {line}")
            changed |= "->" in line
    if changed and not dry:
        r = subprocess.run([sys.executable, "-m", "voxkit.cli", "emit", module],
                           cwd=film, env={**__import__("os").environ,
                                          "PYTHONPATH": str(ROOT)},
                           capture_output=True, text=True)
        if r.returncode:
            print(f"  emit failed: {r.stderr.strip()[:400]}")
            return 1
        print("  re-emitted")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("module", nargs="?", help="m01..m22, or omit with --all")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--shot", default="", help="only this shot, e.g. s02")
    ap.add_argument("--dry", action="store_true", help="measure, change nothing")
    a = ap.parse_args()
    mods = [f"m{i:02d}" for i in range(1, 23)] if a.all else [a.module]
    if not mods or mods == [None]:
        ap.error("give a module or --all")
    bad = 0
    for m in mods:
        print(m)
        bad |= run(m, a.dry, a.shot)
    return bad


if __name__ == "__main__":
    raise SystemExit(main())
