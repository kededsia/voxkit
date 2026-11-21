"""Read the stacking order out of the still, and write it into the plan.

The still is a photograph of a finished collage: it already knows which piece is on
top. The plan's `z` is a separate, hand-made opinion, and nothing ever compared the
two. m02 s05 had the map at `z=4` — the highest — over the slip that says "SELURUH
KABUPATEN" and over the red pin, so the film showed a map lying on top of the words
it was there to point at. Four of the client's six findings were this.

How the still answers it. Where two pieces overlap, the visible ink belongs to the
one on top. So for each overlapping pair, compare the still against each piece's own
cutout in the overlap: the piece whose cutout matches the page is the piece you can
see, and the other was occluded when it was cut. Count the wins, sort, write `z`.

    py tools/stack.py m02 --dry
    py tools/stack.py m02 --shot s05
    py tools/stack.py --all

Writes the plan's `z` only. The emitter stacks by it, so a re-emit is enough.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voxkit import config  # noqa: E402
from voxkit.figure import PERSON  # noqa: E402
from voxkit.geometry import head_band  # noqa: E402

#: Working frame. The question is "which of these two is on top", not "by how much".
W, H = 640, 360
#: Overlap below this is a corner touch, not a stack.
MIN_OVERLAP = 0.02
#: A pair this close is a tie and decides nothing.
MIN_MARGIN = 1.5

#: What each material is worth in the stack, lowest first.
#:
#: A page is read in this order: the map or the photograph is the ground it is pasted
#: on; the printed slip lies on the ground, because it carries the words; the cut-out
#: object — and above all the person — is pasted last. The client's findings were a
#: map over the slip that says "SELURUH KABUPATEN" and a map over a figure, and both
#: are this order violated by a plan whose `z` was hand-written and never checked.
#:
#: **People last, and that is deliberate.** The rule "kepala sampai leher jangan
#: tertutup" is absolute, and any order that puts lettering above a figure can break
#: it — the first run of this table did exactly that on m02 s06, where a slip landed
#: on `pejalan`'s head. A slip across a torso is collage and is lost by this order;
#: a slip across a face is not, and is worth more than the collage.
#:
#: Measuring the order from the still was tried first and is not reliable: a small
#: object's cutout carries its sticker margin, so the pixel comparison inside a
#: 700-pixel overlap says the map is on top of the pin. Material answers it without a
#: threshold, and the still is then only used to order pieces *within* a class.
MATERIAL = {"peta": 1, "foto": 2, "benda": 3, "figur": 4, "cetak": 5, "koran": 5, "seal": 5}


def rank_of(bahan: str) -> int:
    return MATERIAL.get(bahan, 3)


def load(project, module, shot, elements):
    """Every piece, as (alpha, grey) in page coordinates."""
    out = {}
    for name, e in elements.items():
        p = project.card_dir(module, shot) / f"{name}.png"
        if not p.is_file():
            continue
        im = Image.open(p).convert("RGBA")
        a = np.asarray(im)[:, :, 3] > 128
        if a.sum() < 400:
            continue
        x0 = int(round((e["x"] - e["w"] / 2) * W))
        y0 = int(round((e["y"] - e["h"] / 2) * H))
        w = max(1, int(round(e["w"] * W)))
        h = max(1, int(round(e["h"] * H)))
        xs, ys = max(0, x0), max(0, y0)
        xe, ye = min(W, x0 + w), min(H, y0 + h)
        if xe <= xs or ye <= ys:
            continue
        am = np.asarray(Image.fromarray((a * 255).astype(np.uint8))
                        .resize((w, h), Image.BILINEAR)) > 127
        g = np.asarray(im.convert("L").resize((w, h), Image.BILINEAR), float)
        alpha = np.zeros((H, W), bool)
        grey = np.full((H, W), np.nan)
        alpha[ys:ye, xs:xe] = am[ys - y0:ye - y0, xs - x0:xe - x0]
        grey[ys:ye, xs:xe] = g[ys - y0:ye - y0, xs - x0:xe - x0]
        out[name] = (alpha, grey)
    return out


def order(pieces, still, bahan):
    """Rank the pieces, back to front: material first, then who the page shows.

    Material decides the *class*; the still only breaks ties inside a class, because
    two photographs lying over each other have no material rule between them and the
    page does know which one is on top.
    """
    names = sorted(pieces)
    wins = {n: 0 for n in names}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if rank_of(bahan.get(a, "")) != rank_of(bahan.get(b, "")):
                continue
            aa, ga = pieces[a]
            ab, gb = pieces[b]
            both = aa & ab
            if both.sum() < MIN_OVERLAP * min(aa.sum(), ab.sum()):
                continue
            s = still[both]
            ea = np.nanmean(np.abs(s - ga[both]))
            eb = np.nanmean(np.abs(s - gb[both]))
            if abs(ea - eb) < MIN_MARGIN:
                continue
            # The smaller error is the piece whose ink is visible on the page, so it
            # is the piece on top. m02 s05: the map's cutout was redrawn without the
            # photograph that lay over it (err 80 against the page's 8.6), so the
            # photograph is above the map — which is what the still shows and the
            # plan had exactly backwards.
            wins[a if ea < eb else b] += 1
    return sorted(names, key=lambda n: (rank_of(bahan.get(n, "")), wins[n], n))


# --------------------------------------------------------------- people lift
#: A material order alone cannot settle this shot set, and pretending otherwise cost
#: a round trip. Two rules point opposite ways:
#:
#:   R6  the printed card is read, so nothing may lie across its words;
#:   the head rule  a person is never covered from head to neck.
#:
#: Words-on-top satisfies R6 and buries `pejalan`'s head under `kartu_kabupaten` in
#: m02 s06 (48 % of the band). People-on-top satisfies the head rule and leaves a
#: hand lying across the nameplate's words in s01. Neither total order is right,
#: because the answer differs per pair — so the order is decided by material and
#: then repaired only where the measurement says a head is actually crossed.
def _is_person(card: dict) -> bool:
    """The plan's own statement of a face first, then the noun — `figure.is_person`
    refuses `poses_planned` as evidence, because a magnifying glass moves too."""
    if card.get("head"):
        return True
    return any(w in str(card.get("name", "")) for w in PERSON)


def _head_on_page(alpha: np.ndarray, head) -> np.ndarray | None:
    """The head-and-neck band of one piece, in page coordinates."""
    ys, xs = np.where(alpha)
    if not len(ys):
        return None
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
    band = head_band(alpha[y0:y1 + 1, x0:x1 + 1], head)
    if not band.any():
        return None
    out = np.zeros_like(alpha)
    out[y0:y1 + 1, x0:x1 + 1] = band
    return out


def lift_people(ranked: list[str], pieces, cards: dict[str, dict]) -> list[str]:
    """Raise a person above any piece that crosses their head, and only there.

    Bounded and monotone: each pass moves one person up past one blocker, so it
    either settles or runs out of passes, and it never loops.
    """
    seq = list(ranked)
    for _ in range(64):
        moved = False
        for name in list(seq):
            card = cards.get(name)
            if card is None or not _is_person(card):
                continue
            band = _head_on_page(pieces[name][0], card.get("head"))
            if band is None:
                continue
            for other in seq[seq.index(name) + 1:]:
                if not (band & pieces[other][0]).any():
                    continue
                seq.remove(name)
                seq.insert(seq.index(other) + 1, name)
                moved = True
                break
            if moved:
                break
        if not moved:
            break
    return seq


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("module", nargs="?", default="")
    ap.add_argument("--shot", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    project = config.discover(Path.cwd())
    mods = [a.module] if a.module else [f"m{n:02d}" for n in range(1, 23)]
    if not a.module and not a.all:
        ap.error("give a module, or --all")

    for module in mods:
        path = Path(project.require_module(module))
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = 0
        print(module)
        for shot in data["shots"]:
            if a.shot and shot["id"] != a.shot:
                continue
            lay = project.card_dir(module, shot["id"]) / "layout.json"
            if not lay.is_file():
                continue
            elements = json.loads(lay.read_text(encoding="utf-8"))["elements"]
            still_path = project.still(module, shot["id"])
            if not still_path.is_file():
                continue
            still = np.asarray(Image.open(still_path).convert("L")
                               .resize((W, H), Image.BILINEAR), float)
            pieces = load(project, module, shot["id"], elements)
            if len(pieces) < 2:
                continue
            bahan = {c.get("name"): c.get("bahan", "") for c in shot["cards"]}
            ranked = order(pieces, still, bahan)
            ranked = lift_people(ranked, pieces, {c.get("name"): c for c in shot["cards"]})
            want = {name: i + 1 for i, name in enumerate(ranked)}
            moved = []
            for c in shot["cards"]:
                n = c.get("name")
                if n in want and c.get("z") != want[n]:
                    moved.append(f"{n} {c.get('z')}→{want[n]}")
                    c["z"] = want[n]
            if moved:
                changed += 1
                print(f"  {shot['id']}: " + ", ".join(moved))
        if changed and not a.dry:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {'would fix' if a.dry else 'fixed'} {changed} shot(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
