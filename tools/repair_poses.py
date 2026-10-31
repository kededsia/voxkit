"""Put every puppet frame back on its card's canvas, without redrawing it.

The renderer maps a card's canvas *width* onto the card's stage width, so a frame
drawn on a larger canvas renders its subject smaller: a man who jumps away from
the camera on every swap. Sixty-five such frames shipped from the old tree, and a
few survived the migration — the pose gate measures the canvas, not the picture.

`align_to_base` already knows the answer (scale to the base figure's height, stand
it on the base figure's feet, on a canvas the base's size). This tool applies it
to frames that were drawn before the rule existed. No model is called: the
picture is already on disk, only its canvas is wrong.

    py tools/repair_poses.py m20            # fix one module
    py tools/repair_poses.py --all --dry    # report only

The source tree is untouched, so a repair that looks wrong can be undone by
re-running the migration.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voxkit import config  # noqa: E402
from voxkit.emit.gen_pose import align_to_base  # noqa: E402
from voxkit.layout import Layout  # noqa: E402


def repair(project: config.Project, module: str, dry: bool) -> tuple[int, int, list[str]]:
    fixed, ok, notes = 0, 0, []
    build = project.mod_build(module)
    for layout_path in sorted((build / "cards").glob("*/layout.json")):
        shot = layout_path.parent.name
        layout = Layout.load(layout_path)
        for name, slot in layout.elements.items():
            if not slot.poses:
                continue
            base_path = layout_path.parent / f"{name}.png"
            if not base_path.is_file():
                notes.append(f"{shot}/{name}: no base card")
                continue
            with Image.open(base_path) as im:
                base = im.convert("RGBA")
            for pose in slot.poses:
                src = project.root / str(pose["src"]).replace("\\", "/")
                if not src.is_file():
                    alt = layout_path.parent / Path(str(pose["src"])).name
                    src = alt if alt.is_file() else src
                if not src.is_file():
                    notes.append(f"{shot}/{name}: pose at f{pose['atFrame']} is missing")
                    continue
                with Image.open(src) as im:
                    frame = im.convert("RGBA")
                if frame.size == base.size:
                    ok += 1
                    continue
                aligned, note = align_to_base(base, frame, name)
                if not dry:
                    aligned.save(src)
                fixed += 1
                notes.append(f"{shot}/{name} f{pose['atFrame']}: {frame.width}x{frame.height} "
                             f"→ {aligned.width}x{aligned.height} ({note})")
    return fixed, ok, notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("modules", nargs="*", help="module ids; default: every module with a plan")
    ap.add_argument("--root", default="film", type=Path)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)

    project = config.load(a.root / "vox.toml")
    modules = a.modules or project.modules()
    total_fixed = total_ok = 0
    for module in modules:
        fixed, ok, notes = repair(project, module, a.dry)
        total_fixed += fixed
        total_ok += ok
        print(f"{module}: {fixed} frame(s) realigned, {ok} already on their card")
        for n in notes[:12]:
            print("  ·", n)
        if len(notes) > 12:
            print(f"  · … {len(notes) - 12} more")
    print(f"\n{total_fixed} realigned, {total_ok} untouched" + (" (dry run)" if a.dry else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
