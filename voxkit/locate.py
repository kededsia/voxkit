"""Where a piece really is, measured against the still it was cut from.

The isolation is told "same position, same scale", and it keeps that promise most
of the time. The times it does not are the expensive ones: a piece that comes back
30 % too large gets a slot that is faithful to the asset and wrong about the page,
the slip runs off the frame edge, and the still it was cut from had every letter.

So the reply's own bbox is only a *starting point*. The slot is then refined by
correlating the piece's ink against the still, which is the thing that cannot
lie: the still is where the piece was printed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from .geometry import Rect


@dataclass(frozen=True, slots=True)
class Fit:
    rect: Rect
    score: float            # normalised correlation, -1..1
    moved: float            # how far the centre moved, in frame fractions
    scaled: float           # height scale against the starting rect


def _patch(still: np.ndarray, rect: Rect) -> np.ndarray | None:
    h, w = still.shape
    x0, y0 = int(round(rect.x0 * w)), int(round(rect.y0 * h))
    x1, y1 = int(round(rect.x1 * w)), int(round(rect.y1 * h))
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    return still[y0:y1, x0:x1]


def _score(card: np.ndarray, mask: np.ndarray, patch: np.ndarray) -> float:
    """Correlation of the card's ink against the page under it, on the piece only.

    The mask matters: a card is mostly paper, and paper correlates with everything.
    Scoring only where the piece has ink asks the question that is actually being
    asked — is *this object* printed here.
    """
    if patch is None:
        return -1.0
    p = np.asarray(Image.fromarray(patch).resize((card.shape[1], card.shape[0]),
                                                 Image.BILINEAR), dtype=np.float32)
    if mask.sum() < 64:
        return -1.0
    a = card[mask].astype(np.float32)
    b = p[mask].astype(np.float32)
    a -= a.mean()
    b -= b.mean()
    denom = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / denom) if denom > 1e-6 else -1.0


def refine(card: np.ndarray, alpha: np.ndarray, still: np.ndarray, start: Rect,
           search: float = 0.03, step: float = 0.0075) -> Fit:
    """Search a small window around `start` for the placement the page agrees with.

    A bounded search on purpose. An unbounded one finds a better match somewhere
    else on the page — that is a *different piece*, not a better slot — and
    moving a card 200 px to make the numbers look good is how a collage stops
    being a collage.
    """
    mask = alpha > 40
    best = Fit(start, _score(card, mask, _patch(still, start)), 0.0, 1.0)
    if best.score < -0.9:
        return best

    n = max(1, int(round(search / step)))
    for iy in range(-n, n + 1):
        for ix in range(-n, n + 1):
            if ix == 0 and iy == 0:
                continue
            cand = Rect(start.x0 + ix * step, start.y0 + iy * step,
                        start.x1 + ix * step, start.y1 + iy * step)
            s = _score(card, mask, _patch(still, cand))
            if s > best.score:
                moved = max(abs(cand.cx - start.cx), abs(cand.cy - start.cy))
                best = Fit(cand, s, moved, 1.0)
    return best


def from_alpha(alpha: np.ndarray, canvas: tuple[int, int], pad: int = 0) -> Rect:
    """A slot from a piece's own alpha, in frame fractions of the reply canvas.

    `pad` is the paper border the cut-out was mounted on: the sheet is not the
    piece, and a slot measured from the sheet is a slot the size of the sheet.
    """
    ys, xs = np.where(alpha > 40)
    if not len(ys):
        raise ValueError("the piece has no opaque pixel")
    w, h = canvas
    x0 = (xs.min() + pad) / w
    x1 = (xs.max() + 1 - pad) / w
    y0 = (ys.min() + pad) / h
    y1 = (ys.max() + 1 - pad) / h
    return Rect.from_edges(x0, y0, x1, y1)
