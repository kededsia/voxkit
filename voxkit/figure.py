"""Where a person's head is, and whether anything is on top of it.

The client's rule, and the only version of it that survives the pipeline:

    "yg paling penting untuk gambar orang itu bagian kepala sampai leher jgn
     tertutup" — a slip across a torso is collage, a slip across a face is not.

So the measure is not "how much of the body is behind a card". It is: how much of
the head-and-neck band is owned by a piece that sits above this one.

Three things this module refuses to do, each because a previous version did it and
shipped a fault:

* **It does not measure the top of the silhouette.** `head_band` finds the head by
  shape — the first band that is narrow compared with the widest row and stays
  narrow — because a driver's piece begins at the car roof and a man holding a
  framed photo has sky above his head.
* **It does not treat `siluet_organik` as "a person".** That form is every organic
  cut-out: a river, a tree, a palace, a map. The first run of this measurement
  without the noun test reported 113 covered heads, and 97 of them were rivers.
* **It does not fix by moving the card.** A nudge of 45–114 px leaves a printed
  slip with no card over it; the plate fills the hole and the eye reads two of
  everything. The fix is a layer swap, and it lives in `tools/uncover.py`.

The geometry (`head_band`, `head_top`) is in `geometry.py` and is not duplicated
here. This module only answers "whose head, and what is on it".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from .contract import Card, Plan, Shot
from .geometry import head_band
from .image import open_rgba
from .layout import Layout

#: Working resolution. The question is "is the head clear", not "by how many px".
STAGE_W, STAGE_H = 640, 360
#: The pass mark. Same number as v2's `piece_audit` and `uncover`, so the two
#: engines disagree about nothing.
COVER = 0.10

#: `siluet_organik` is every organic cut-out. The rule is about *people*, so the
#: set has to be named. A puppet is a person by definition; the rest are found by
#: the noun the plan gave them.
PERSON = (
    "orang", "figur", "petani", "penjaga", "nelayan", "petugas", "peneliti",
    "juru", "pembaca", "pencatat", "penulis", "arkeolog", "pangeran", "brahmana",
    "purwocaraka", "geolog", "penggembala", "penggali", "tukang", "penghitung",
    "pencari", "pengemudi", "warga", "pendatang", "pengambil", "penonton",
    "penyimpan", "perenung", "penyaksi", "penutur", "pengukur", "pejalan",
    "penemu", "pengirim", "pendengar", "pendaki", "penyusur", "filolog",
    "pedagang", "penjual", "pengrajin", "siswa", "guru", "sopir", "ibu", "bapak",
    "anak", "pria", "wanita", "lelaki", "perempuan", "pembuat", "pekerja",
    "buruh", "penari", "penabuh", "pemain",
)


def is_person(card: Card) -> bool:
    """A plan may say where the face is. Otherwise the noun decides.

    `poses_planned` is **not** evidence of a person, and treating it as such was the
    first version's mistake: m01 animates a magnifying glass and a rubber stamp, so
    both arrived here as "people", and the fixer raised a magnifying glass above a
    printed slip to clear a head it does not have. A puppet is a thing that moves.
    """
    if card.head:
        return True
    return any(w in card.name for w in PERSON)


@dataclass
class Placed:
    """One card, resampled once into the working frame, with its ink separated."""

    index: int
    name: str
    mask: np.ndarray          # alpha, at working resolution
    ink: np.ndarray           # dark pixels inside the alpha: the card's own words
    box: tuple[int, int, int, int]   # x0, y0, w, h on the stage
    card: Card | None = None


@dataclass
class Cover:
    """One person whose head is under something."""

    card: str
    share: float
    by: dict[str, float] = field(default_factory=dict)
    z: int = 0


def _place(mask: np.ndarray, box, size) -> np.ndarray:
    """A card's mask, on the stage, clipped to it."""
    x0, y0, w, h = box
    out = np.zeros((size[1], size[0]), bool)
    sx0, sy0 = max(0, x0), max(0, y0)
    sx1, sy1 = min(size[0], x0 + w), min(size[1], y0 + h)
    if sx1 > sx0 and sy1 > sy0:
        out[sy0:sy1, sx0:sx1] = mask[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]
    return out


def stack(project, module: str, shot: Shot, layout: Layout,
          size: tuple[int, int] = (STAGE_W, STAGE_H)) -> tuple[np.ndarray, list[Placed]]:
    """Paint the shot's cards onto an owner map in z order.

    The map holds the index of the topmost card at each pixel, which is the only
    thing "is this covered" needs. Returns the map and the placed cards in the same
    index order.
    """
    W, H = size
    owner = np.full((H, W), -1, dtype=np.int16)
    placed: list[Placed] = []
    for idx, card in enumerate(sorted(shot.ordered(), key=lambda c: c.z)):
        slot = layout.get(card.name)
        png = project.card_dir(module, shot.id) / f"{card.name}.png"
        if slot is None or not png.is_file():
            continue
        im = open_rgba(png)
        a = np.array(im)[..., 3]
        rgb = np.array(im.convert("L"))
        x0 = int(round(slot.rect.x0 * W))
        y0 = int(round(slot.rect.y0 * H))
        w = max(1, int(round(slot.rect.w * W)))
        h = max(1, int(round(slot.rect.h * H)))
        mask = np.array(Image.fromarray(a).resize((w, h), Image.BILINEAR)) > 40
        lum = np.array(Image.fromarray(rgb).resize((w, h), Image.BILINEAR))
        p = Placed(index=idx, name=card.name, mask=mask,
                   ink=(lum < 110) & mask, box=(x0, y0, w, h), card=card)
        stage = _place(mask, p.box, size)
        owner[stage] = idx
        placed.append(p)
    return owner, placed


def covered(project, module: str, plan: Plan, shot: Shot, layout: Layout,
            floor: float = COVER, size: tuple[int, int] = (STAGE_W, STAGE_H),
            ) -> list[Cover]:
    """Every person in this shot whose head-and-neck band is under a card above it.

    Static — the worst case over the shot, which is what a still can be judged on.
    A shot whose card arrives after the head has been read is still a shot where the
    head is covered for part of its life, and the plan cannot express "cover it at
    frame 90".
    """
    owner, placed = stack(project, module, shot, layout, size)
    out: list[Cover] = []
    for p in placed:
        card = p.card
        if card is None or card.wujud != "siluet_organik" or card.tertutup_boleh:
            continue
        if not is_person(card):
            continue
        png = project.card_dir(module, shot.id) / f"{card.name}.png"
        alpha = np.array(open_rgba(png))[..., 3]
        band = head_band(alpha, card.head)
        if not band.any():
            continue
        x0, y0, w, h = p.box
        hb = np.array(Image.fromarray(band.astype(np.uint8) * 255)
                      .resize((w, h), Image.NEAREST)) > 40
        hb &= p.mask
        if not hb.any():
            continue
        stage_band = _place(hb, p.box, size)
        if not stage_band.any():
            continue
        above = owner > p.index
        hit = above & stage_band
        share = float(hit.sum()) / float(stage_band.sum())
        if share < floor:
            continue
        by: dict[str, float] = {}
        for q in placed:
            if q.index <= p.index:
                continue
            m = (owner == q.index) & stage_band
            if m.any():
                by[q.name] = round(float(m.sum()) / float(stage_band.sum()), 3)
        out.append(Cover(card=card.name, share=round(share, 3), by=by, z=card.z))
    return out


def glyphs_buried(owner_after: np.ndarray, ink: np.ndarray, index: int) -> float:
    """How much of this card's own lettering would end up under something above it."""
    if not ink.any():
        return 0.0
    return float(((owner_after > index) & ink).sum()) / float(ink.sum())


@dataclass
class InkLoss:
    """A person's silhouette standing on a readable card's lettering."""

    person: str
    card: str
    share: float


def ink_under_figure(project, module: str, plan: Plan, shot: Shot, layout: Layout,
                     floor: float = COVER,
                     size: tuple[int, int] = (STAGE_W, STAGE_H)) -> list[InkLoss]:
    """Where a person stands on a card that has to stay readable.

    R6 says a printed card sits above everything that can lie on it, and it makes
    one exception — printed card against a person — because a silhouette over a
    slip's blank margin is collage. That exception is only honest if something
    measures the lettering, and the plan cannot: this is a question about pixels.
    So the free `readable` gate defers here, and here it is answered.

    Ten per cent, the same number as `CARD_INK` in `tools/uncover.py`, so the fixer
    and the gate cannot disagree about whether a raise was legal.
    """
    owner, placed = stack(project, module, shot, layout, size)
    out: list[InkLoss] = []
    for p in placed:
        if p.card is None or p.card.wujud != "siluet_organik" or not is_person(p.card):
            continue
        pmask = _place(p.mask, p.box, size)
        for q in placed:
            if q.card is None or q.index >= p.index:
                continue
            if not q.card.readable or q.card.tertutup_boleh:
                continue
            qink = _place(q.ink, q.box, size)
            if not qink.any():
                continue
            share = float((pmask & qink).sum()) / float(qink.sum())
            if share > floor:
                out.append(InkLoss(person=p.name, card=q.name, share=round(share, 3)))
    return out
