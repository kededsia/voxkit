"""Two pieces that claim the same pixels of the page.

The isolation model returns the piece you asked for *plus whatever overlaps it*.
When a blank slip lay under a signboard, the sign's cutout came back carrying the
slip's tape and the slip's cutout came back carrying the tape too — so the same
physical object exists twice in the layer stack, and when both pieces are placed
at their own measured slots the duplicate shows.

The layout is allowed to overlap: that is collage. What is not allowed is two
cutouts containing the *same ink from the still*. This measures that, in still
coordinates, per shot.

Superseded for gating by `voxkit/double.py` + `vox gates/assets.double`,
which measures the bare-paper carry this probe cannot see. Kept because
the silhouette-overlap number is still the quickest way to see *where*.

Usage: python _sweep/review/double.py [m02 ...]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, ".")
from voxkit import config  # noqa: E402

W, H = 480, 270          # working frame; the question is "is it the same object"
MIN_SHARE = 0.04         # of the smaller piece
MIN_AREA = 0.004         # of the page


def masks(project, module, shot):
    lay = project.card_dir(module, shot.id) / "layout.json"
    if not lay.is_file():
        return {}
    import json
    els = json.loads(lay.read_text(encoding="utf-8"))["elements"]
    out = {}
    for name, e in els.items():
        p = project.card_dir(module, shot.id) / f"{name}.png"
        if not p.is_file():
            continue
        im = Image.open(p).convert("RGBA")
        a = np.asarray(im)[:, :, 3] > 40
        # still coordinates: (x, y) is the piece's centre, w/h are page fractions
        x0 = int(round((e["x"] - e["w"] / 2) * W))
        y0 = int(round((e["y"] - e["h"] / 2) * H))
        w = max(1, int(round(e["w"] * W)))
        h = max(1, int(round(e["h"] * H)))
        m = np.zeros((H, W), bool)
        small = np.asarray(Image.fromarray((a * 255).astype(np.uint8))
                           .resize((w, h), Image.BILINEAR)) > 127
        xs, ys = max(0, x0), max(0, y0)
        xe, ye = min(W, x0 + w), min(H, y0 + h)
        if xe <= xs or ye <= ys:
            continue
        m[ys:ye, xs:xe] = small[ys - y0:ye - y0, xs - x0:xe - x0]
        out[name] = m
    return out


def main(argv):
    project = config.discover(Path("film"))
    mods = argv or [f"m{n:02d}" for n in range(1, 23)]
    worst = []
    for module in mods:
        plan = project.require_module(module)
        import json
        data = json.loads(Path(plan).read_text(encoding="utf-8"))
        for s in data["shots"]:
            class S:
                id = s["id"]
            ms = masks(project, module, S)
            names = sorted(ms)
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    both = ms[a] & ms[b]
                    area = both.sum()
                    if area < MIN_AREA * W * H:
                        continue
                    share = area / max(1, min(ms[a].sum(), ms[b].sum()))
                    if share >= MIN_SHARE:
                        worst.append((share, module, s["id"], a, b, area))
    worst.sort(reverse=True)
    print(f"{len(worst)} pairs share ink\n")
    for share, m, sid, a, b, area in worst:
        print(f"  {share:5.1%}  {m}/{sid}  {a}  <->  {b}   ({area} px)")


if __name__ == "__main__":
    main(sys.argv[1:])
