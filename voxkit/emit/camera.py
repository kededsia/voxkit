"""Camera arithmetic, in Python, so a camera move can be tested without rendering.

This is a faithful port of the renderer's `Camera.tsx`: the same key structure,
the same five ease curves, the same `punch` shape, the same emphasis preset. It
exists in Python because a camera move that cannot be measured cannot be gated —
and every camera fault in this project was found by watching a render, which is
the most expensive way to find anything.

The rule the numbers serve: *hold on information, move on transitions*. The
camera leads the word it is moving toward by at least `LEAD` frames, and it never
pans a printed figure out of frame — a pan that trims `8.848` to `0.848` puts a
wrong number on screen at the exact moment the voice says the right one.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Sequence

from ..geometry import Rect

# A camera that starts moving on the word it is moving to is already late; the
# eye needs the frame to arrive with the word.
LEAD = 14
# The frame must never be panned so tight that a margin is lost.
MARGIN = 0.015
# `fitZoom` is a ceiling, not a composition. A real 40 % push turns a 1376 px
# halftone to mush, so the camera is capped well below what the geometry allows.
ZOOM_CAP = 1.35

EMPHASIS = {"antic": 2, "rise": 3, "settle": 8, "antic_pct": 0.05, "over_pct": 0.12}
DEFAULT_PUNCH = {"rise": 5, "settle": 9, "antic": 2, "antic_pct": 0.015, "over_pct": 0.025}


@dataclass(frozen=True, slots=True)
class CamKey:
    at: int
    x: float = 0.5
    y: float = 0.5
    zoom: float = 1.0
    ease: str = "slow"
    #: Part of a hit — the four keys of an anticipate/overshoot/settle. A hit is
    #: dense on purpose (2, 1, 3, 8 frames apart) and the "no two keys closer than
    #: a jump-cut" rule is about *transitions*, not about a hit. Without this flag
    #: the rule cannot tell the two apart, and the only way to satisfy it is to
    #: delete the hit — which is what happened: every shot in the film carried one
    #: ease, `slow`, and no camera hit at all.
    hit: bool = False
    #: Part of a *hold* — a framing the pen needs. The pen is the reason the frame
    #: is where it is, so a hold key is never moved to make room for a transition;
    #: the transition is what gives way.
    hold: bool = False

    def as_value(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.zoom)


# --------------------------------------------------------------------- easing
def ease(name: str, t: float) -> float:
    """The five curves the renderer knows. `step` is four held positions and no
    interpolation: on a print collage a smooth push reads as a lens, a stepped one
    reads as a body leaning in."""
    t = max(0.0, min(1.0, t))
    if name == "linear":
        return t
    if name == "slow":                       # inOut(cubic)
        return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2
    if name == "fast":                       # out(exp)
        return 1.0 if t >= 1.0 else 1 - 2 ** (-10 * t)
    if name == "snap":                       # out(back(1.5))
        s = 1.5
        return 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2
    if name == "step":
        return min(1.0, math.floor(t * 3 + 0.0001) / 3)
    raise ValueError(f"unknown ease {name!r}")


def resolve(keys: Sequence[CamKey], frame: int) -> tuple[float, float, float]:
    """The camera at a frame: keys are cumulative, each carrying forward what it
    does not state, and the segment is interpolated with the destination's ease."""
    if not keys:
        return (0.5, 0.5, 1.0)
    values: list[tuple[float, float, float]] = []
    x = y = 0.5
    zoom = 1.0
    for k in keys:
        x, y, zoom = k.x, k.y, k.zoom
        values.append((x, y, zoom))
    if frame <= keys[0].at:
        return values[0]
    for i in range(1, len(keys)):
        if frame <= keys[i].at:
            a, b = values[i - 1], values[i]
            span = max(1, keys[i].at - keys[i - 1].at)
            t = max(0.0, min(1.0, (frame - keys[i - 1].at) / span))
            e = ease(keys[i].ease, t)
            return tuple(a[j] + (b[j] - a[j]) * e for j in range(3))  # type: ignore[return-value]
    return values[-1]


# ------------------------------------------------------------------ framing
def zoom_floor(x: float, y: float, margin: float = MARGIN) -> float:
    """The smallest zoom that still keeps a `margin` around the frame edges.

    Never below 1.0. A zoom under 1 asks the renderer for more image than the plate
    has, which is why the pipeline used to carry a second, overscanned plate per
    shot and a gate to check it was not older than the still. A camera that only
    ever zooms in needs neither: the plate is exactly the page.
    """
    raw = 0.5 / max(0.001, 0.5 + margin - max(abs(x - 0.5), abs(y - 0.5)))
    return max(1.0, raw)


def on(rect: Rect, zoom: float = 1.15, dx: float = 0.0, dy: float = 0.0,
       margin: float = MARGIN) -> tuple[float, float, float]:
    """A camera framing that holds a piece, tethered so it never runs off the page.

    The tether is 0.68 of the way from the centre: a camera that lands exactly on
    a piece at the edge of the page has nowhere to breathe, and the piece is cut
    by the frame it is supposed to be shown in.
    """
    zoom = min(zoom, ZOOM_CAP)
    max_off = max(0.02, 0.5 + margin - 0.5 / zoom)

    def tether(v: float) -> float:
        return 0.5 + max(-max_off, min(max_off, (v - 0.5) * 0.68))

    return (tether(rect.cx + dx), tether(rect.cy + dy), zoom)


def keep_interval(keep: Sequence[Rect], margin: float = MARGIN):
    """The frame positions that keep every one of these boxes whole at zoom 1.

    Returns `(lo_x, hi_x, lo_y, hi_y)` or `None` when no single position can hold
    them all — three pieces spread across the page, or one piece larger than the
    frame, cannot be framed together no matter where the camera sits. Both the
    camera and the gate ask this question, and they must get the same answer, so
    it is asked in one place.
    """
    fit = [b for b in keep if b.w / 2 + margin <= 0.5 and b.h / 2 + margin <= 0.5]
    if not fit:
        return None
    lo_x = max(b.cx - (0.5 - (b.w / 2 + margin)) for b in fit)
    hi_x = min(b.cx + (0.5 - (b.w / 2 + margin)) for b in fit)
    lo_y = max(b.cy - (0.5 - (b.h / 2 + margin)) for b in fit)
    hi_y = min(b.cy + (0.5 - (b.h / 2 + margin)) for b in fit)
    if lo_x > hi_x or lo_y > hi_y:
        return None
    return lo_x, hi_x, lo_y, hi_y


def plate_cam(keys: Sequence[CamKey], margin: float = MARGIN,
              keep: Sequence[Rect] = ()) -> list[CamKey]:
    """Every key raised to the zoom floor, and every readable figure kept in frame.

    `keep` is the pieces whose ink a viewer reads as a number or a name. A camera
    that pans one of them past the edge leaves a partial figure on screen, and a
    wrong figure is worse than no camera move at all.

    The frame is placed on the *group*, not on the last box in the list. The
    previous loop adjusted the frame for one box at a time, so each box undid the
    one before it and only the final box was ever kept: a shot with three pieces
    carrying figures satisfied none of them. Here the interval that keeps every
    box whole at zoom 1 is computed once and the frame is clamped into it, which
    is the most any single camera position can do. A group that cannot be framed
    together has no interval; the camera then keeps the one it is closest to.
    """
    span = keep_interval(keep, margin)
    fit = [b for b in keep if b.w / 2 + margin <= 0.5 and b.h / 2 + margin <= 0.5]

    out: list[CamKey] = []
    for k in keys:
        x, y, zoom = k.x, k.y, k.zoom
        zoom = max(zoom, zoom_floor(x, y, margin))
        if span is not None:
            lo_x, hi_x, lo_y, hi_y = span
            x = min(max(x, lo_x), hi_x)
            y = min(max(y, lo_y), hi_y)
            need = max(max(abs(b.cx - x) + b.w / 2 + margin,
                           abs(b.cy - y) + b.h / 2 + margin) for b in fit)
            if need > 0.5 / zoom:
                zoom = max(1.0, min(zoom, 0.5 / need))
        out.append(replace(k, x=x, y=y, zoom=min(zoom, ZOOM_CAP)))
    return out


def frame_card(rect: Rect, zoom: float = 1.0) -> tuple[float, float, float]:
    """A framing that holds one piece whole, centred as near as the page allows.

    This is the answer to the pen. A mark is drawn on a card, so the card has to
    be *in* the frame when the pen touches it — not partly, and not at the edge
    where the stroke runs off the page. Measured over the film, 115 of 205 marks
    were drawn on a card the camera had left partly outside the frame, which is
    what "the arrow misses the word" looks like from the seat.

    Three constraints, solved exactly rather than by iterating:
      * the piece must fit — `zoom <= 0.5 / (w/2)`, and the same for h;
      * the window must stay on the page — `x in [0.5/zoom, 1 - 0.5/zoom]`;
      * ...and still contain the piece — `x in [x1 - 0.5/zoom, x0 + 0.5/zoom]`.
    The centre is used when it satisfies both, otherwise the nearest allowed
    position. `zoom` is only ever reduced, never raised: this is a correction to a
    camera, not a second opinion about how tight the shot should be.

    No margin. A piece the size of the page has exactly one legal position, and
    asking for a margin as well turns a solvable constraint into an impossible
    one — which is how a full-height card ended up reported as unframeable.
    """
    rect = rect.clamped()
    zoom = max(1.0, min(zoom, ZOOM_CAP))
    fit = min(0.5 / max(0.001, rect.w / 2), 0.5 / max(0.001, rect.h / 2))
    zoom = max(1.0, min(zoom, fit))
    half = 0.5 / zoom

    def place(c0: float, c1: float, c: float) -> float:
        lo = max(half, c1 - half)
        hi = min(1.0 - half, c0 + half)
        return c if lo > hi else min(max(c, lo), hi)

    return (place(rect.x0, rect.x1, rect.cx), place(rect.y0, rect.y1, rect.cy), zoom)


def holds(win: tuple[float, float, float], rect: Rect) -> bool:
    """Does this camera position show the piece whole?

    Measured on the part of the piece that exists. A slot that runs off the page
    has no ink beyond the edge, so demanding the whole slot be visible would be
    demanding to see paper that was never printed.
    """
    x, y, zoom = win
    half = 0.5 / zoom
    r = rect.clamped()
    return (r.x0 >= x - half - 1e-6 and r.x1 <= x + half + 1e-6
            and r.y0 >= y - half - 1e-6 and r.y1 <= y + half + 1e-6)


def punch(keys: Sequence[CamKey], at: int, target: tuple[float, float, float],
          **opts) -> list[CamKey]:
    """A camera hit: anticipate back, overshoot, settle. Four keys, one move.

    The anticipation is what makes it read as a body rather than a zoom: the
    frame pulls 6 % away from where it is going before it goes, and overshoots
    the destination before it settles.
    """
    o = {**DEFAULT_PUNCH, **opts}
    antic, rise, settle = int(o["antic"]), int(o["rise"]), int(o["settle"])
    before = resolve(keys, at - antic - 1)
    away = (before[0] - target[0], before[1] - target[1])
    # Both ends of a hit stay inside the camera's own limits. A punch pulls 6 %
    # *out* before it goes, and from a resting zoom of 1.03 that lands at 0.97 —
    # below 1.0, where the plate has no overscan and the stage shows through the
    # edge. The cap at the top matters for the same reason in reverse.
    pull = (before[0] + away[0] * 0.06, before[1] + away[1] * 0.06,
            max(1.0, min(ZOOM_CAP, before[2] * (1 - o["antic_pct"]))))
    over = (target[0] - away[0] * 0.02, target[1] - away[1] * 0.02,
            max(1.0, min(ZOOM_CAP, target[2] * (1 + o["over_pct"]))))
    head = [k for k in keys if k.at < at - antic]
    tail = [k for k in keys if k.at > at + rise + settle]
    return [
        *head,
        CamKey(at - antic, *before, "slow", hit=True),
        CamKey(at - 1, *pull, "linear", hit=True),
        CamKey(at + rise, *over, "step", hit=True),
        CamKey(at + rise + settle, *target, "slow", hit=True),
        *tail,
    ]


def squeeze(keys: Sequence[CamKey], gap: int = 8) -> list[CamKey]:
    """Drop keys that sit inside a jump-cut of the one before — never move them.

    The last pass, because every earlier pass either adds keys (a hold for the pen,
    a hit for the voice) or moves them, and each of those can leave a pair two
    frames apart. Dropping is the only repair that cannot create a new collision:
    a missing transition key costs a camera move, a moved one costs a jump-cut.

    Holds and hits are the two kinds of key that carry a promise — the frame the
    pen needs and the four keys that read as one hit — so they are never the ones
    dropped.
    """
    out: list[CamKey] = []
    for k in sorted(keys, key=lambda k: k.at):
        if out and k.at - out[-1].at < gap and not (out[-1].hit and k.hit):
            if out[-1].hold or out[-1].hit:
                continue
            out.pop()
            if out and k.at - out[-1].at < gap:
                continue
        out.append(k)
    return out


def keys_at_least(keys: Sequence[CamKey], gap: int = LEAD) -> list[CamKey]:
    """Two camera keys closer than `gap` frames read as one jump-cut. Keeps the
    later key and drops the earlier, so the move still arrives."""
    out: list[CamKey] = []
    for k in keys:
        if out and k.at - out[-1].at < gap and k.at > out[-1].at:
            continue
        out.append(k)
    return out
