"""Which pieces are buried, and by what.

A piece is drawn at its measured slot with the plan's `z`. Nothing checks that the
z-order agrees with the *still*: the still is a photograph of a finished collage, so
it already knows which piece is on top, and the plan's `z` is a separate, hand-made
opinion. Where the two disagree, a card that the page shows on top is drawn behind
something else, and the viewer sees a signboard inside a map.

This measures, per shot, how much of each piece's own opaque area is hidden by
pieces stacked above it — in page coordinates, which is what the viewer sees before
any camera move.

Usage: python _sweep/review/buried.py [m02 ...]
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, ".")
from voxkit import config  # noqa: E402

W, H = 640, 360


def piece(project, module, shot, name, e):
    p = project.card_dir(module, shot) / f"{name}.png"
    if not p.is_file():
        return None
    im = Image.open(p).convert("RGBA")
    a = np.asarray(im)[:, :, 3] > 128
    if a.sum() < 400:
        return None
    x0 = int(round((e["x"] - e["w"] / 2) * W))
    y0 = int(round((e["y"] - e["h"] / 2) * H))
    w = max(1, int(round(e["w"] * W)))
    h = max(1, int(round(e["h"] * H)))
    small = np.asarray(Image.fromarray((a * 255).astype(np.uint8))
                       .resize((w, h), Image.BILINEAR)) > 127
    m = np.zeros((H, W), bool)
    xs, ys = max(0, x0), max(0, y0)
    xe, ye = min(W, x0 + w), min(H, y0 + h)
    if xe <= xs or ye <= ys:
        return None
    m[ys:ye, xs:xe] = small[ys - y0:ye - y0, xs - x0:xe - x0]
    return m


def main(argv):
    project = config.discover(Path("film"))
    mods = argv or [f"m{n:02d}" for n in range(1, 23)]
    rows = []
    for module in mods:
        data = json.loads(Path(project.require_module(module)).read_text(encoding="utf-8"))
        for s in data["shots"]:
            lay = project.card_dir(module, s["id"]) / "layout.json"
            if not lay.is_file():
                continue
            els = json.loads(lay.read_text(encoding="utf-8"))["elements"]
            z = {c["name"]: c.get("z", 1) for c in s["cards"] if "name" in c}
            ms = {}
            for name, e in els.items():
                m = piece(project, module, s["id"], name, e)
                if m is not None:
                    ms[name] = m
            for name, m in ms.items():
                above = [o for o in ms if o != name and z.get(o, 1) > z.get(name, 1)]
                if not above:
                    continue
                cover = np.zeros_like(m)
                for o in above:
                    cover |= ms[o]
                hidden = (m & cover).sum() / max(1, m.sum())
                if hidden >= 0.15:
                    who = sorted(above, key=lambda o: -(m & ms[o]).sum())[:2]
                    rows.append((hidden, module, s["id"], name, who))
    rows.sort(reverse=True)
    print(f"{len(rows)} pieces at least 15% buried\n")
    for hidden, m, sid, name, who in rows[:40]:
        print(f"  {hidden:5.0%}  {m}/{sid}  {name:<26} under {', '.join(who)}")


if __name__ == "__main__":
    main(sys.argv[1:])
