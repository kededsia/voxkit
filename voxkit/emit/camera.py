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


def plate_cam(keys: Sequence[CamKey], margin: float = MARGIN,
              keep: Sequence[Rect] = ()) -> list[CamKey]:
    """Every key raised to the zoom floor, and every readable figure kept in frame.

    `keep` is the pieces whose ink a viewer reads as a number or a name. A camera
    that pans one of them past the edge leaves a partial figure on screen, and a
    wrong figure is worse than no camera move at all.
    """
    out: list[CamKey] = []
    for k in keys:
        x, y, zoom = k.x, k.y, k.zoom
        zoom = max(zoom, zoom_floor(x, y, margin))
        for box in keep:
            hx = box.w / 2 + margin
            hy = box.h / 2 + margin
            need = max(abs(box.cx - x) + hx, abs(box.cy - y) + hy)
            if 0.5 / zoom < need:
                zoom = max(1.0, 0.5 / need)
            half = 0.5 / zoom
            if abs(box.cx - x) + hx > half:
                x = box.cx + (1 if x >= box.cx else -1) * max(0.0, half - hx)
            if abs(box.cy - y) + hy > half:
                y = box.cy + (1 if y >= box.cy else -1) * max(0.0, half - hy)
        out.append(replace(k, x=x, y=y, zoom=min(zoom, ZOOM_CAP)))
    return out


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
    pull = (before[0] + away[0] * 0.06, before[1] + away[1] * 0.06,
            before[2] * (1 - o["antic_pct"]))
    over = (target[0] - away[0] * 0.02, target[1] - away[1] * 0.02,
            target[2] * (1 + o["over_pct"]))
    head = [k for k in keys if k.at < at - antic]
    tail = [k for k in keys if k.at > at + rise + settle]
    return [
        *head,
        CamKey(at - antic, *before, "slow"),
        CamKey(at - 1, *pull, "linear"),
        CamKey(at + rise, *over, "step"),
        CamKey(at + rise + settle, *target, "slow"),
        *tail,
    ]


def keys_at_least(keys: Sequence[CamKey], gap: int = LEAD) -> list[CamKey]:
    """Two camera keys closer than `gap` frames read as one jump-cut. Keeps the
    later key and drops the earlier, so the move still arrives."""
    out: list[CamKey] = []
    for k in keys:
        if out and k.at - out[-1].at < gap and k.at > out[-1].at:
            continue
        out.append(k)
    return out
