"""Migrate the old `v2.0-conscious-vox-director` tree into a voxkit project.

The old tree kept its build artifacts in a shape that only the old tools knew:
`rebuild/mNN/sNN.jpg` for a still, `rebuild/plates/mNNsNN.jpg` for a plate,
`rebuild/mNN/fills/mNNsNN_0.jpg` for a fill, and a `layout.json` whose pose
entries point at `rebuild/...` by hand-written path. voxkit derives every one of
those names from `Project`, so the same assets have to be renamed once.

Nothing is regenerated here. A file that exists is copied; a file that does not
is reported and left missing, because a migration that invents an asset is worse
than one that admits the gap.

    py tools/migrate_legacy.py --check     # report only, writes nothing
    py tools/migrate_legacy.py             # copy + rewrite layouts

Two things are rewritten rather than copied:

- `layout.json` gains the `src` of each piece (voxkit's layout records it) and
  drops `inset`/`still`/`size`, which nothing reads any more.
- every pose `src` is remapped from `rebuild/...` to `build/...`. Left alone,
  the pose gate would fail on a path that exists in the other tree.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

SHAPES = ("*.jpg", "*.jpeg", "*.png", "*.webp")


def _plan_shots(plans: Path) -> dict[str, list[tuple[str, list[str]]]]:
    """module -> [(shot id, [card names])], straight from the plan."""
    out = {}
    for p in sorted(plans.glob("*.json")):
        if p.name.startswith("_"):
            continue
        raw = json.loads(p.read_text(encoding="utf-8"))
        out[p.stem] = [(s["id"], [c["name"] for c in s.get("cards", [])])
                       for s in raw.get("shots", [])]
    return out


def _pose_src(old: str, module: str, shot: str) -> str:
    """`rebuild/m01/cards/s01/x_pose2.png` -> `m01/cards/s01/x_pose2.png`.

    The renderer reads `public/<module>/…` and resolves a relative path against
    it, so a pose path is module-relative — the same shape as a card's `src`.
    Left as `rebuild/…` or rewritten to `build/…`, it resolves to
    `/public/rebuild/…` in the browser and 404s during a render, after every gate
    has confirmed the file exists.

    A pose that pointed somewhere else (another module's folder, an absolute
    path) keeps its own file name and is placed beside its card: the only place
    the frame can live and still be found is next to the card it replaces.
    """
    name = Path(old.replace("\\", "/")).name
    return f"{module}/cards/{shot}/{name}"


def rewrite_layout(raw: dict, module: str, shot: str) -> dict:
    elements = {}
    for name, e in (raw.get("elements") or {}).items():
        out = {
            "x": round(float(e["x"]), 5),
            "y": round(float(e["y"]), 5),
            "w": round(float(e["w"]), 5),
            "h": round(float(e.get("h") or 0.0), 5),
            "aspect": round(float(e.get("aspect") or 0.7), 5),
            "src": f"build/{module}/cards/{shot}/{name}.png",
            "z": int(e.get("z") or 0),
        }
        poses = [{"atFrame": int(p["atFrame"]), "src": _pose_src(p["src"], module, shot)}
                 for p in (e.get("poses") or []) if "atFrame" in p and "src" in p]
        if poses:
            out["poses"] = sorted(poses, key=lambda p: p["atFrame"])
        elements[name] = out
    return {"elements": elements}


def copy_file(src: Path, dst: Path, copied: list[str], force: bool = False) -> None:
    """Copy once. A file that already exists has been migrated and possibly
    repaired since — a pose realigned onto its card, a layout re-ordered — and
    overwriting it silently undoes that work. `--force` is the way to say
    "the destination is wrong, take the source again"."""
    if dst.is_file() and not force:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    copied.append(str(dst))


def migrate(src: Path, dst: Path, plans: Path, check: bool, force: bool = False) -> int:
    modules = _plan_shots(plans)
    copied: list[str] = []
    gaps: list[str] = []

    # ---------------------------------------------------------------- project
    for rel in ("assets", "plans", "audio", "build"):
        if not check:
            (dst / rel).mkdir(parents=True, exist_ok=True)
    for p in plans.glob("*.json"):
        if not check:
            copy_file(p, dst / "plans" / p.name, copied, force)
    style_key = src / "rebuild" / "stills" / "style-key.jpg"
    if style_key.is_file() and not check:
        copy_file(style_key, dst / "assets" / "style-key.jpg", copied, force)
    for name in ("lexicon.json", "facts.json"):
        doc = src / "docs" / "17min" / name
        if doc.is_file() and not check:
            copy_file(doc, dst / name, copied, force)

    for module, shots in modules.items():
        wav = src / "audio" / f"{module}.wav"
        tr = src / "audio" / f"{module}.json"
        if wav.is_file() and not check:
            copy_file(wav, dst / "audio" / wav.name, copied, force)
        if tr.is_file() and not check:
            copy_file(tr, dst / "audio" / tr.name, copied, force)
        if not wav.is_file():
            gaps.append(f"{module}: no narration wav")

        build = src / "rebuild" / module
        for sid, cards in shots:
            # still
            still = build / f"{sid}.jpg"
            if still.is_file():
                if not check:
                    copy_file(still, dst / "build" / module / f"{sid}.jpg", copied, force)
            else:
                gaps.append(f"{module} {sid}: no still")

            # fill (old name carries the module and the shot twice)
            fill = build / "fills" / f"{module}{sid}_0.jpg"
            if fill.is_file():
                if not check:
                    copy_file(fill, dst / "build" / module / "fills" / f"{sid}_0.jpg", copied, force)
            else:
                gaps.append(f"{module} {sid}: no fill")

            # plate
            plate = src / "rebuild" / "plates" / f"{module}{sid}.jpg"
            if plate.is_file():
                if not check:
                    copy_file(plate, dst / "build" / module / "plates" / f"{sid}.jpg", copied, force)
            else:
                gaps.append(f"{module} {sid}: no plate")

            # pieces + layout
            card_dir = build / "cards" / sid
            layout = card_dir / "layout.json"
            if not layout.is_file():
                gaps.append(f"{module} {sid}: no layout.json — nothing was measured")
                continue
            raw = json.loads(layout.read_text(encoding="utf-8"))
            elements = raw.get("elements") or {}
            for card in cards:
                png = card_dir / f"{card}.png"
                if png.is_file():
                    if not check:
                        copy_file(png, dst / "build" / module / "cards" / sid / png.name, copied, force)
                else:
                    gaps.append(f"{module} {sid}/{card}: no piece png")
                if card not in elements:
                    gaps.append(f"{module} {sid}/{card}: not in layout.json")
                for pose in sorted(card_dir.glob(f"{card}_pose*.png")):
                    if not check:
                        copy_file(pose, dst / "build" / module / "cards" / sid / pose.name, copied, force)
            out = dst / "build" / module / "cards" / sid / "layout.json"
            if not check and (force or not out.is_file()):
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(rewrite_layout(raw, module, sid), indent=1,
                                          ensure_ascii=False) + "\n", encoding="utf-8")
                copied.append(str(out))
            for name in elements:
                if name not in cards:
                    gaps.append(f"{module} {sid}/{name}: measured but not in the plan")

        # isolation replies and specs are inputs to a re-run, not to a render
        for sub, target in (("iso", "iso"), ("specs", "specs")):
            for f in sorted((build / sub).glob("*")):
                if f.is_file() and f.suffix.lower() in {".png", ".jpg", ".json"}:
                    if not check:
                        copy_file(f, dst / "build" / module / target / f.name, copied, force)

    verb = "would copy" if check else "copied"
    print(f"{verb} {len(copied)} file(s) into {dst}")
    if gaps:
        print(f"\n{len(gaps)} gap(s):")
        for g in gaps:
            print("  ·", g)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default="D:/VOX-PLUGIN-2", type=Path)
    ap.add_argument("--dst", default="film", type=Path)
    ap.add_argument("--plans", default="_sweep/plans", type=Path)
    ap.add_argument("--check", action="store_true", help="report only; write nothing")
    ap.add_argument("--force", action="store_true",
                    help="overwrite files that already exist (undoes later repairs)")
    a = ap.parse_args(argv)
    return migrate(a.src, a.dst, a.plans, a.check, a.force)


if __name__ == "__main__":
    raise SystemExit(main())
