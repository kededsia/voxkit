"""The page as the renderer assembles it: plate, then every piece at its slot.

The still is the *source*; the layout is the arrangement. A duplicate that only
appears after the pieces are re-placed cannot be seen in the still, and a render
is a minute a look. This composes the static page so a stacking fault is visible
in a second.

Usage: python _sweep/review/page.py m02 s01 [--out x.jpg] [--scale 1]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, ".")
from voxkit import config  # noqa: E402


def compose(project, module: str, shot_id: str, scale: float = 1.0) -> Image.Image:
    d = project.card_dir(module, shot_id)
    plate = project.plate(module, shot_id)
    with Image.open(plate) as im:
        page = im.convert("RGBA")
    W, H = page.size
    els = json.loads((d / "layout.json").read_text(encoding="utf-8"))["elements"]
    plan = json.loads(Path(project.require_module(module)).read_text(encoding="utf-8"))
    shot = next(s for s in plan["shots"] if s["id"] == shot_id)
    order = {c["name"]: c.get("z", 0) for c in shot["cards"]}
    for name in sorted(els, key=lambda n: order.get(n, 0)):
        p = d / f"{name}.png"
        if not p.is_file():
            continue
        e = els[name]
        w = max(1, round(e["w"] * W))
        h = max(1, round(e["h"] * H))
        with Image.open(p) as im:
            piece = im.convert("RGBA").resize((w, h), Image.LANCZOS)
        x = round(e["x"] * W - w / 2)
        y = round(e["y"] * H - h / 2)
        page.alpha_composite(piece, (x, y))
    if scale != 1.0:
        page = page.resize((round(W * scale), round(H * scale)), Image.LANCZOS)
    return page.convert("RGB")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    module, shot_id = argv[0], argv[1]
    out = "_sweep/_tmp/page_%s_%s.jpg" % (module, shot_id)
    scale = 1.0
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    if "--scale" in argv:
        scale = float(argv[argv.index("--scale") + 1])
    project = config.discover(Path("film"))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    compose(project, module, shot_id, scale).save(out, quality=92)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
