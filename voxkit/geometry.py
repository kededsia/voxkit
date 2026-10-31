"""Geometry: one definition of "where a piece is", used by every tool.

This module exists because the same question was answered eight times in the
previous codebase and answered differently. A card's slot is stored as a CENTRE
plus a size, because that is what the renderer uses:

    <Img style={{left: `${x*100}%`, top: `${y*100}%`,
                transform: "translate(-50%,-50%)"}} />

Three tools read those numbers as a top-left corner. Every "the card covers 45 %
of the person" they printed was measured half a card away from the person, and
two of them shipped that number into a decision. Nothing about the numbers was
wrong; the reading of them was, in three places at once.

So: a slot becomes a `Rect` in exactly one function (`Rect.from_slot`), and every
question about overlap, coverage, containment and frame edges is a method on
`Rect`. There is no second implementation to drift from this one.

Coordinates are frame fractions in [0, 1]: x rightwards, y downwards, origin at
the top-left corner of the frame — the same space the plan is written in.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol, Sequence

import numpy as np


class SlotLike(Protocol):
    """Anything with a centre and a size: a layout element, a dataclass, a dict."""

    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True, slots=True)
class Rect:
    """An axis-aligned box in frame fractions. Immutable, so it cannot be edited
    into an inconsistent state by a caller that only meant to ask a question."""

    x0: float
    y0: float
    x1: float
    y1: float

    # ---------------------------------------------------------------- builders
    @classmethod
    def from_slot(cls, slot: SlotLike | dict) -> "Rect":
        """A centre-and-size slot -> a box.

        THE conversion. `x`/`y` are the centre, not the corner; getting this
        wrong is silent, plausible and off by half a card.
        """
        x, y, w, h = _slot_fields(slot)
        hw, hh = w / 2.0, h / 2.0
        return cls(x - hw, y - hh, x + hw, y + hh)

    @classmethod
    def from_edges(cls, x0: float, y0: float, x1: float, y1: float) -> "Rect":
        """A box given by corners. Normalises a reversed pair instead of
        producing a negative area that silently passes every overlap test."""
        return cls(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    @classmethod
    def from_centre(cls, cx: float, cy: float, w: float, h: float) -> "Rect":
        return cls.from_slot({"x": cx, "y": cy, "w": w, "h": h})

    # ------------------------------------------------------------------ shape
    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0

    @property
    def area(self) -> float:
        return max(0.0, self.w) * max(0.0, self.h)

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)

    def scaled(self, sx: float, sy: float | None = None) -> "Rect":
        """Multiply into pixel space (or any other space)."""
        sy = sx if sy is None else sy
        return Rect(self.x0 * sx, self.y0 * sy, self.x1 * sx, self.y1 * sy)

    def expanded(self, pad: float) -> "Rect":
        return Rect(self.x0 - pad, self.y0 - pad, self.x1 + pad, self.y1 + pad)

    def clamped(self) -> "Rect":
        """Cut to the frame. A piece that runs off the page has no honest
        overlap number until it is cut to what a viewer can actually see."""
        return Rect(max(0.0, self.x0), max(0.0, self.y0),
                    min(1.0, self.x1), min(1.0, self.y1))

    # --------------------------------------------------------------- relations
    def intersect(self, other: "Rect") -> float:
        ox = min(self.x1, other.x1) - max(self.x0, other.x0)
        oy = min(self.y1, other.y1) - max(self.y0, other.y0)
        return ox * oy if ox > 0 and oy > 0 else 0.0

    def covered_by(self, other: "Rect") -> float:
        """What share of THIS piece the other one hides.

        Share of the piece that is hidden, not share of the smaller box. A stamp
        pasted on the corner of a big card covers a third of the card and none of
        itself; calling that "91 % overlap" tells a designer nothing true.
        """
        a = self.area
        return 0.0 if a <= 0 else self.intersect(other) / a

    def contains(self, other: "Rect", tol: float = 0.0) -> bool:
        return (other.x0 >= self.x0 - tol and other.y0 >= self.y0 - tol
                and other.x1 <= self.x1 + tol and other.y1 <= self.y1 + tol)

    def overlap_ratio(self, other: "Rect") -> float:
        """Intersection over the smaller area — symmetric, for "do these two
        pieces sit in the same place" rather than "who hides whom"."""
        a = min(self.area, other.area)
        return 0.0 if a <= 0 else self.intersect(other) / a

    # ----------------------------------------------------------------- bounds
    def outside(self, lo: float = 0.0, hi: float = 1.0, tol: float = 0.005) -> list[str]:
        """Which edges leave the frame. Empty means it sits on the page.

        Both axes, always. The previous check looked only at `across`, so a strip
        pinned at `down at 0.94` on a 0.34-tall slip ended at 1.015 and lost its
        bottom edge with no complaint — and that was the commonest placement in
        the whole module set. Sixteen cards had already passed that way.
        """
        out = []
        if self.x0 < lo - tol:
            out.append("left")
        if self.x1 > hi + tol:
            out.append("right")
        if self.y0 < lo - tol:
            out.append("top")
        if self.y1 > hi + tol:
            out.append("bottom")
        return out

    def __str__(self) -> str:  # a stable, readable form for findings
        return (f"x {self.x0:.3f}..{self.x1:.3f} · y {self.y0:.3f}..{self.y1:.3f}")


def _slot_fields(slot) -> tuple[float, float, float, float]:
    if isinstance(slot, dict):
        try:
            return float(slot["x"]), float(slot["y"]), float(slot["w"]), float(slot["h"])
        except KeyError as e:
            raise ValueError(f"slot is missing {e.args[0]!r}: {slot!r}") from None
    try:
        return float(slot.x), float(slot.y), float(slot.w), float(slot.h)
    except AttributeError as e:
        raise ValueError(f"not a slot: {slot!r}") from e


# --------------------------------------------------------------------- stacks
@dataclass(frozen=True, slots=True)
class Placed:
    """A named piece at a depth. `z` is the stacking order: higher is on top."""

    name: str
    rect: Rect
    z: int
    data: dict


def stack(items: Iterable[Placed]) -> list[Placed]:
    """Back to front, ties broken by name so the order is reproducible."""
    return sorted(items, key=lambda p: (p.z, p.name))


def buried(items: Sequence[Placed], floor: float = 0.55) -> list[tuple[Placed, Placed, float]]:
    """Every pair where the upper piece hides more than `floor` of the lower.

    No size exemption. A slip is small on purpose, and a slip that is 100 %
    buried is still a piece that was paid for and cannot be seen. The previous
    version excused small pieces with an area test, and a 0.024-area slip went
    completely under a card while the board reported nothing.
    """
    out = []
    ordered = stack(items)
    for i, below in enumerate(ordered):
        for above in ordered[i + 1:]:
            frac = below.rect.covered_by(above.rect)
            if frac > floor:
                out.append((below, above, frac))
    return sorted(out, key=lambda t: -t[2])


# ---------------------------------------------------------------------- heads
# Client's rule, verbatim: "yg paling penting untuk gambar orang itu bagian
# kepala sampai leher jgn tertutup" — a slip across a torso is collage, a slip
# across the face is not. So coverage is measured on head-and-neck only; body
# coverage is reported as a note and never fails a shot.
HEAD_FRAC = 0.26        # head + neck, measured down from the top of the head
NARROW = 0.45           # a head row is at most this share of the widest row
STAY = 0.06             # ...and it must stay narrow for this share of the height


def head_band(mask: np.ndarray, head: Sequence[float] | bool | None = None) -> np.ndarray:
    """The head-and-neck band of a silhouette, as a boolean mask of equal shape.

    Accepts a boolean mask or a raw 0-255 alpha channel (a first version summed
    alpha values as if they were pixels and reported a band of 1.9 million
    pixels for one piece).

    `head` is the plan's own statement of where the faces are, in fractions of
    the piece's box: `[x0,y0,x1,y1]`, or `[cx,cy]` for a single face, or `False`
    for a piece with no face at all. A silhouette cannot always answer: a photo
    of a man holding a framed picture has sky at the top, a torn page can carry
    two boys, a pair of hands has no head. The shape test is the default, not
    the truth.
    """
    m = np.asarray(mask)
    if m.dtype != bool:
        m = m > 40
    if head is False:
        return np.zeros_like(m)
    ys, xs = np.where(m)
    if not len(ys):
        return np.zeros_like(m)
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())

    if head:
        if len(head) == 4:
            bx0, by0, bx1, by1 = (float(v) for v in head)
        else:
            cx, cy = float(head[0]), float(head[1])
            bx0, by0, bx1, by1 = cx - 0.17, cy - 0.13, cx + 0.17, cy + 0.13
        w, h = max(1, x1 - x0), max(1, y1 - y0)
        box = np.zeros_like(m)
        box[max(0, int(by0 * h + y0)):int(by1 * h + y0),
            max(0, int(bx0 * w + x0)):int(bx1 * w + x0)] = True
        # Cut to the piece's own ink: a card over the sky beside his head is not
        # a card over his head.
        return m & box

    top = head_top(m)
    cut = top + max(2, int((y1 - top) * HEAD_FRAC))
    out = np.zeros_like(m)
    out[top:cut] = m[top:cut]
    return out


def head_top(mask: np.ndarray) -> int:
    """First row of the head: the first narrow band, below the top of the piece,
    that stays narrow. A roof, a held frame and a paper strip are all wide."""
    rows = np.asarray(mask).sum(axis=1)
    ys = np.where(rows > 0)[0]
    if not len(ys):
        return 0
    y0, y1 = int(ys.min()), int(ys.max())
    wmax = int(rows.max())
    span = max(1, int((y1 - y0) * STAY))
    for y in range(y0, y1 + 1):
        if rows[y] <= NARROW * wmax and rows[y:y + span].max() <= 0.60 * wmax:
            return y
    return y0


def covered_share(band: np.ndarray, other: np.ndarray) -> float:
    """Share of a head band that sits under `other`."""
    n = int(np.asarray(band).sum())
    if not n:
        return 0.0
    return int((np.asarray(band) & np.asarray(other)).sum()) / n
