"""Two pieces, one sheet of paper.

The isolate stage does not cut a matte out of the still. It *re-draws* the piece:
it sends the page and a description and gets back one object on a chroma ground.
So a piece that something lies across is ambiguous, and the model resolves it the
safe way — it keeps the other thing's paper and leaves it **blank**. The letters
are gone (it read them as a separate object) but the sheet is there, torn edge and
all.

Then the layout puts the other piece at its own slot, a little off where it sat in
the still, and the blank copy shows beside it. The client saw exactly that:

    "dua kartu identik ditumpuk — yang di belakang terpisah tapi karena
     bentuknya identik dan bukan puppets jadi nya aneh"

A duplicated *object* is a fault with a mechanism, so it is measurable: where the
other piece sat, the carrier is bare paper, and all around that footprint it is
printed. Two-sided evidence, because one side alone is not evidence at all — a
photograph of a white wall is bare paper, and a card's own margin is bare paper.

This module answers only that question. It does not choose the repair: a re-cut
with a corrected prompt is one price, a recomposed still another.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .figure import Placed, _place

#: Working resolution. The question is "is it the same sheet", not "by how many px".
STAGE_W, STAGE_H = 640, 360

#: How much of the other piece's footprint has to lie inside the carrier before
#: the pair is worth asking about. A slip half over a photo is collage; a slip
#: wholly inside a photo is the case the model has to invent for.
INSIDE = 0.80

#: Bare paper. A print's darkest half is below this; paper stock is above it.
PAPER = 110

#: The two-sided test. This much of the other's footprint is bare paper, and the
#: carrier is printed this much in the ring around it.
BARE = 0.85
PRINTED = 0.25

#: And it has to be big enough to read as a second card rather than as noise.
MIN_AREA = 0.004          # of the page


@dataclass(frozen=True, slots=True)
class Carried:
    """One piece that keeps a copy of another piece's sheet."""

    card: str             # the piece that carries
    other: str            # whose sheet it carries
    bare: float           # share of `other`'s footprint that is bare paper in `card`
    printed: float        # how printed `card` is in the ring around that footprint
    area: int             # px of the footprint, on the working stage


def _ring(mask: np.ndarray, width: int = 2) -> np.ndarray:
    """The outline of a mask, `width` px thick on both sides."""
    out = np.zeros_like(mask)
    h, w = mask.shape
    for dy in range(-width, width + 1):
        for dx in range(-width, width + 1):
            if abs(dy) + abs(dx) > width:
                continue
            ys = slice(max(0, dy), h + min(0, dy))
            xs = slice(max(0, dx), w + min(0, dx))
            ty = slice(max(0, -dy), h + min(0, -dy))
            tx = slice(max(0, -dx), w + min(0, -dx))
            out[ys, xs] |= mask[ty, tx]
    return out & ~mask


def carried(placed: list[Placed], size: tuple[int, int] = (STAGE_W, STAGE_H),
            inside: float = INSIDE, bare: float = BARE, printed: float = PRINTED,
            min_area: float = MIN_AREA) -> list[Carried]:
    """Every (carrier, carried) pair in one shot.

    Pure: masks in, findings out. `figure.stack` already paints the cards and has
    one implementation of "where does this slot put this mask", so this module
    borrows it rather than repeating it — a second placement is how a measurement
    starts disagreeing with the renderer.
    """
    W, H = size
    stage = [(p.name,
              _place(p.mask, p.box, size),
              _place(p.ink, p.box, size))
             for p in placed]
    stage = [(n, m, i) for n, m, i in stage if m.any()]

    floor = max(1, int(min_area * W * H))
    out: list[Carried] = []
    for an, am, ai in stage:
        blank = am & ~ai
        for bn, bm, _ in stage:
            if bn == an:
                continue
            area = int(bm.sum())
            if area < floor:
                continue
            if (am & bm).sum() / area < inside:
                continue
            share = float((blank & bm).sum()) / area
            if share < bare:
                continue
            band = _ring(bm) & am & ~bm
            if band.sum() < 40:
                continue
            ink = float(ai[band].mean())
            if ink < printed:
                continue
            out.append(Carried(an, bn, share, ink, area))
    out.sort(key=lambda c: -c.area)
    return out
