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

#: How far the plate extends beyond the page, in frame widths.
#:
#: `Stage.tsx` draws every plate at `OVERSCAN = 1.55`, so real collage sits a
#: quarter of a frame outside each edge. The camera's clamp did not know that, and
#: the result was a camera that could only address the middle 29 % of the page —
#: 12 % of the film's 852 pieces were reachable at any legal zoom. This is the
#: overscan turned into a number the camera is allowed to use: (1.55 - 1) / 2.
BLEED = 0.275
# The frame must never be panned so tight that a margin is lost.
MARGIN = 0.015
# `fitZoom` is a ceiling, not a composition. A real 40 % push turns a 1376 px
# halftone to mush, so the camera is capped well below what the geometry allows.
ZOOM_CAP = 1.35

# A camera hit: anticipate back, overshoot, settle. The shape is what makes a move
# read as a body rather than a zoom — but the *proportions* decide whether it reads
# as a body or as a flinch.
#
# These were 3 / 8 frames with a 5 % anticipation and a 12 % overshoot. On a key
# that has to travel from 1.00 to 1.30 that is a 30 % change in four frames, then a
# retreat: a twitch, not a move, and the reason the camera felt stiff however much
# it moved. Longer and shallower — 8 / 16 frames, 2.5 % anticipation, 3 %
# overshoot — covers the same distance as something a person would do with their
# hands.
#
# `antic_pct` is how far the frame pulls *away* from where it is going before it
# goes: at 1.5 % the anticipation was invisible, and an invisible anticipation is a
# zoom with a stutter rather than a body leaning in. It can only be seen at all
# because the camera now rests above 1.0 — from a resting zoom of 1.03 a 3 % pull
# lands under the plate's own edge.
#
# There used to be a second shape, `EMPHASIS` (6/14), used by `punch_for` — an
# unconditional hit on every shot's first card. Two shapes and two callers meant
# the film could hit twice on one frame, and on m17 the decided hit lost that
# collision. Both are gone: a hit is whatever `intent` decided, in this shape.
DEFAULT_PUNCH = {"rise": 8, "settle": 16, "antic": 3, "antic_pct": 0.025, "over_pct": 0.03}


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
    #: **Why this key moves.** One of `REASONS`. A key with no reason is a wild
    #: move: it exists because a pass wanted the frame somewhere, not because the
    #: film wanted the viewer to look at something. The `program` gate refuses one,
    #: and the whole point of the vocabulary is that "the camera should move more"
    #: is not a reason.
    #:
    #:   open      the shot's first framing, and its statement
    #:   arrive    the move to the piece a word names, landing before the word
    #:   reveal    a push on a name, a number, a figure — a stressed word
    #:   rest      the frame holds still while the pen is down or a line is read
    #:   widen     pulled back until one framing holds two pieces at once
    #:   follow    tracking a subject that itself moves
    #:   breathe   the breath `creep` puts into a hold, so a hold is not frozen
    #:   leave     the move off the page at the end of a shot
    reason: str = ""
    #: **What the beat asked this key to do**, from `voxkit.intent` — `punch`,
    #: `drift`, `arrive`, `pull`, `hold`, `none`. Set before the key exists, by the
    #: decision, and executed by the passes below.
    #:
    #: This is separate from `reason` on purpose. `reason` answers "why is the
    #: frame here", which is a property of the shot; `move` answers "what did the
    #: beat want", which is a property of the word. Conflating them is how the
    #: camera ended up with a vocabulary it never consulted: every key carried a
    #: plausible `reason` that had been attached *after* the move was computed.
    #:
    #: The `program` gate checks that every decided `punch` produced a hit, so a
    #: decision that nothing executes is a finding rather than a silent loss.
    move: str = ""

    def as_value(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.zoom)


#: Every legitimate reason for the frame to move. Anything else is decoration.
REASONS = ("open", "arrive", "reveal", "rest", "widen", "follow", "breathe", "leave")


# --------------------------------------------------------------------- easing
#: The least speed a move may have, as a fraction of the constant-velocity speed.
#:
#: `inOut(cubic)` is stationary at both ends — that is what "ease in and out"
#: means — and every segment of every shot used it. So the camera *stopped at
#: every key*: accelerate, stop, accelerate, stop. With keys twenty frames apart
#: the viewer sees a stutter, and the client described it, correctly, as the
#: camera not moving. Measured on m03 s04: thirty-two frames straddling a key in
#: which the frame changed by less than one per cent.
#:
#: A real camera has no zero-velocity hold. Blending the curve toward linear
#: keeps the softened ends that make a move feel like a lens and removes the dead
#: frame at the key. The value is a judgement, not a measurement: low enough that
#: the ends still read as eased, high enough that a second never passes unseen.
EASE_FLOOR = 0.40


def ease(name: str, t: float) -> float:
    """The five curves the renderer knows. `step` is four held positions and no
    interpolation: on a print collage a smooth push reads as a lens, a stepped one
    reads as a body leaning in.

    `slow` and `fast` are blended with linear by `EASE_FLOOR`, so that no move
    ever reaches zero velocity. `film/remotion/src/components/Camera.tsx` carries
    the same blend — the two must agree, or the gate measures one film and the
    render shows another.
    """
    t = max(0.0, min(1.0, t))
    if name == "linear":
        return t
    if name == "slow":                       # inOut(cubic), floored
        c = 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2
        return EASE_FLOOR * t + (1 - EASE_FLOOR) * c
    if name == "fast":                       # out(exp), floored
        c = 1.0 if t >= 1.0 else 1 - 2 ** (-10 * t)
        return EASE_FLOOR * t + (1 - EASE_FLOOR) * c
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
       margin: float = MARGIN, tether_ratio: float = 0.82,
       bleed: float = 0.0) -> tuple[float, float, float]:
    """A camera framing that holds a piece, tethered so it never runs off the page.

    The tether keeps the camera from landing exactly on a piece at the edge of the
    page, where the piece would be cut by the frame it is supposed to be shown in.
    It used to be 0.68 — two thirds of the way — and that number quietly deleted
    most of the film's pans: a card at 0.90 across was framed at 0.77, so the pan
    from centre was 27 % of the frame instead of 40 %, and at a resting zoom of
    1.04 the whole move came to under 200 px. A tether is a safety rail, not a
    composition, so it sits at 0.82: far enough to travel, near enough to keep the
    piece whole.

    `bleed` is how far the *plate* extends beyond the page, in frame widths. The
    stage draws every plate at `OVERSCAN` (1.55), so there is real collage a
    quarter of a frame outside each edge — and without this term the clamp ignored
    it. That clamp was the whole reason the camera "did not move":

        max_off = 0.5 + margin - 0.5/zoom          # ±0.043 at zoom 1.06
        pieces the camera could point at:  103 / 852  (12 %)

    With the plate's own bleed counted, the same zoom reaches ±0.303, and the
    client's sixth finding — "saat voice bilang lembah tidak ada zoom ke lembah" —
    stops being a geometric impossibility. The client's decision: the frame may
    leave the page.
    """
    zoom = min(zoom, ZOOM_CAP)
    max_off = max(0.02, 0.5 + margin - 0.5 / zoom + max(0.0, bleed))

    def tether(v: float) -> float:
        return 0.5 + max(-max_off, min(max_off, (v - 0.5) * tether_ratio))

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
              keep: Sequence[Rect] = (),
              windows: Sequence[tuple[float, float, Rect]] = (),
              subjects: Sequence[tuple[float, float, Rect]] = ()) -> list[CamKey]:
    """Every key raised to the zoom floor, and every readable figure kept in frame.

    `keep` is the pieces whose ink a viewer reads as a number or a name. A camera
    that leaves one of them *half* on screen puts a wrong figure on screen, which
    is worse than no camera move at all.

    The frame is placed on the *group*, not on the last box in the list. The
    previous loop adjusted the frame for one box at a time, so each box undid the
    one before it and only the final box was ever kept: a shot with three pieces
    carrying figures satisfied none of them.

    `settle` does the work, and it prefers a pan to a retreat: a figure can be
    pushed off the page, where it is harmless, instead of dragging the camera back
    to the widest framing. That preference is what stopped the camera being flat —
    with only the retreat available, every figure near an edge pinned its shot to
    zoom 1.0.
    """
    span = keep_interval(keep, margin)
    # A group that no single position can hold is not a constraint, it is a fact
    # about the page. Chasing it costs the whole move: `settle` reduces the zoom
    # until it gives up at 1.0, which is why a shot with two figures near opposite
    # edges was pinned to the widest framing for its entire length. When the group
    # cannot be framed, the camera keeps its move and the gate says so in a note.
    workable = keep if span is not None else ()

    out: list[CamKey] = []
    for k in keys:
        x, y, zoom = k.x, k.y, k.zoom
        # A figure has to be whole while it is being *read*, not for the whole
        # shot. Applied globally, "keep this number in frame" is a demand that the
        # camera never leave the widest framing — which is exactly what happened:
        # every key in m03/s01 was pinned to zoom 1.000, and at 1.000 there is no
        # room to pan, because the page already fills the frame. The figure is
        # protected inside its own window instead.
        local = tuple(r for (lo, hi, r) in windows if lo <= k.at <= hi)
        work = local if windows else workable
        # What the pen is on at this frame, if anything. A repair that saves a
        # printed figure by panning away from the card being marked trades one
        # fault for a worse one: the stroke then runs off the page.
        subject = next((r for (lo, hi, r) in subjects if lo <= k.at <= hi), None)
        zoom = max(zoom, zoom_floor(x, y, margin))
        zoom = min(zoom, ZOOM_CAP)
        # The group interval is still the cheapest answer when it exists: a
        # framing that holds every figure at once needs no repair at all.
        if span is not None:
            lo_x, hi_x, lo_y, hi_y = span
            x = min(max(x, lo_x), hi_x)
            y = min(max(y, lo_y), hi_y)
        x, y, zoom = settle((x, y, zoom), work, subject=subject)
        out.append(replace(k, x=x, y=y, zoom=zoom))
    return out


def frame_card(rect: Rect, zoom: float = 1.0, push: float = 0.0) -> tuple[float, float, float]:
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
    position.

    `push` is the second half of the answer, and its absence was a fault of its
    own. Correcting only *downwards* made every marked card a reason to pull the
    camera back to 1.0 — the widest legal framing, and therefore a still. With 287
    marks in the film, that pinned half of every module at zoom 1.000. A card the
    pen is drawing on is the thing the shot is about, so the camera moves *toward*
    it: `push` is how much of the frame that card should fill, and the zoom it
    implies is clamped by the three constraints above. Never below the requested
    zoom and never above what the piece allows, so this cannot make a card leave
    the frame — it can only make the frame come to the card.

    No margin. A piece the size of the page has exactly one legal position, and
    asking for a margin as well turns a solvable constraint into an impossible
    one — which is how a full-height card ended up reported as unframeable.
    """
    rect = rect.clamped()
    zoom = max(1.0, min(zoom, ZOOM_CAP))
    if push > 0.0:
        # The zoom at which the piece's longest side covers `push` of the frame.
        want = push / max(0.001, max(rect.w, rect.h))
        zoom = max(zoom, min(ZOOM_CAP, want))
    fit = min(0.5 / max(0.001, rect.w / 2), 0.5 / max(0.001, rect.h / 2))
    zoom = max(1.0, min(zoom, fit))
    half = 0.5 / zoom

    def place(c0: float, c1: float, c: float) -> float:
        lo = max(half, c1 - half)
        hi = min(1.0 - half, c0 + half)
        return c if lo > hi else min(max(c, lo), hi)

    return (place(rect.x0, rect.x1, rect.cx), place(rect.y0, rect.y1, rect.cy), zoom)


#: How close to the page edge a piece may sit and still be "held whole". A piece
#: that is flush with the edge is already cut by the paper: no framing tighter
#: than the whole page can contain it, so demanding one is demanding the camera
#: never leave zoom 1.0 — which is the same as asking for no camera at all.
EDGE = 0.018


def frameable(rect: Rect) -> bool:
    """Can this piece be held whole by a frame tighter than the page?"""
    r = rect.clamped()
    if r.w > 0.72 or r.h > 0.72:
        return False
    return (r.x0 > EDGE and r.y0 > EDGE
            and r.x1 < 1.0 - EDGE and r.y1 < 1.0 - EDGE)


#: The precision a camera key is stored at. `tsx.num` writes four decimals and
#: every pass that settles a framing rounds to the same place, so two framings
#: that differ by less than this are the *same* framing as far as the film is
#: concerned — at 1080 lines it is a tenth of a pixel. Judging containment at 1e-6
#: while storing at 1e-4 made the gate and the emitter disagree about a hairline
#: nobody can see: m15 s02 at f52 was reported as a cut figure because settling to
#: y = 0.4778205 and storing 0.4778 lost two hundred-thousandths.
STAGE_EPS = 1e-4


def holds(win: tuple[float, float, float], rect: Rect) -> bool:
    """Does this camera position show the piece whole?

    Measured on the part of the piece that exists. A slot that runs off the page
    has no ink beyond the edge, so demanding the whole slot be visible would be
    demanding to see paper that was never printed.
    """
    x, y, zoom = win
    half = 0.5 / zoom
    r = rect.clamped()
    return (r.x0 >= x - half - STAGE_EPS and r.x1 <= x + half + STAGE_EPS
            and r.y0 >= y - half - STAGE_EPS and r.y1 <= y + half + STAGE_EPS)


def clipped(win: tuple[float, float, float], rect: Rect) -> bool:
    """Is the piece *partly* on screen — some of it in, some of it out?

    The distinction this draws is the whole reason the camera was flat. A piece
    that is entirely off screen is not on screen: nobody can misread a number they
    cannot see. A piece that is half off screen is a wrong number on screen at the
    moment the voice says the right one. Only the second is a fault, and treating
    the two the same forced every shot with a figure near the page edge back to
    zoom 1.0 — the widest legal framing, and therefore no camera move at all.
    """
    if holds(win, rect):
        return False
    x, y, zoom = win
    half = 0.5 / zoom
    r = rect.clamped()
    on_x = r.x0 < x + half and r.x1 > x - half
    on_y = r.y0 < y + half and r.y1 > y - half
    return on_x and on_y


def settle(win: tuple[float, float, float], keep: Sequence[Rect],
           subject: Rect | None = None, may_reduce: bool = True) -> tuple[float, float, float]:
    """Make a framing legal without giving up the move that produced it.

    Given a framing and the pieces whose ink is read as a number, this returns the
    nearest framing that leaves none of them half on screen. Three answers, in
    order of preference:

      1. **Nothing is clipped.** Return the framing untouched — most of the time.
      2. **Pan the offending piece off the page.** A half-seen figure becomes an
         unseen one, which is not a fault, and the pan is a camera move rather
         than a retreat. Only taken when it leaves `subject` whole, so the piece
         the shot is about never gets pushed aside to hide a neighbour.
      3. **Pull back until it is whole.** The old behaviour, and still the right
         answer when a pan would cost the subject.

    Preference 2 is the one that was missing, and its absence is why half the
    film's keys sat at zoom 1.000: with only the pull-back available, every figure
    near the page edge demanded the widest framing, so the camera had nowhere left
    to travel.
    """
    x, y, zoom = win
    half = 0.5 / zoom

    for _ in range(len(keep) + 1):
        # The frame itself must be on the page. At zoom 1 there is exactly one
        # such position — the centre — and `zoom_floor` does not quite guarantee
        # it: at 1.04 it allows 0.48, which is a hundredth of a percent short of
        # the 0.481 the window needs, so every piece touching the page edge was
        # cut by a hairline. A hairline is enough for the gate to be right and the
        # picture to be wrong.
        x = min(max(x, half), 1.0 - half)
        y = min(max(y, half), 1.0 - half)

        bad = [b for b in keep if clipped((x, y, zoom), b)]
        if not bad:
            return (x, y, zoom)

        # 2. Pan so the offender is *whole*. This was missing, and its absence is
        #    why the camera kept collapsing to the widest framing: given a figure
        #    in the middle of the page, panning it off the edge is often impossible
        #    (it would need a position outside the page) and pulling back to 1.0 is
        #    always available — so the only answer the function had was the one
        #    that kills the move. But a window that can *contain* the figure needs
        #    no zoom change at all, only a position.
        contain: list[tuple[float, float, float]] = []
        for b in bad:
            r = b.clamped()
            if r.w > 2 * half or r.h > 2 * half:
                continue
            lo_x, hi_x = max(half, r.x1 - half), min(1.0 - half, r.x0 + half)
            lo_y, hi_y = max(half, r.y1 - half), min(1.0 - half, r.y0 + half)
            if lo_x <= hi_x and lo_y <= hi_y:
                contain.append((min(max(x, lo_x), hi_x), min(max(y, lo_y), hi_y), zoom))
        for nx, ny, nz in sorted(contain, key=lambda c: abs(c[0] - x) + abs(c[1] - y)):
            cand = (nx, ny, nz)
            if subject is not None and not holds(cand, subject):
                continue
            if any(clipped(cand, b) for b in keep):
                continue
            return cand

        # 3. The cheapest pan that puts every offender off the page.
        options: list[tuple[float, float, float, float]] = []   # (cost, x, y, zoom)
        for b in bad:
            r = b.clamped()
            for nx in (r.x0 - half, r.x1 + half):
                if half <= nx <= 1.0 - half:
                    options.append((abs(nx - x), nx, y, zoom))
            for ny in (r.y0 - half, r.y1 + half):
                if half <= ny <= 1.0 - half:
                    options.append((abs(ny - y), x, ny, zoom))
        for _, nx, ny, nz in sorted(options):
            cand = (nx, ny, nz)
            if subject is not None and not holds(cand, subject):
                continue
            if any(clipped(cand, b) for b in keep):
                continue
            return cand

        # 4. Give up the zoom, not the position — but only if this caller is
        #    willing to pay with the move. The camera's composition is the thing
        #    the shot is for; a figure that cannot be accommodated by a pan is
        #    then reported by the gate rather than silently bought with a still.
        if not may_reduce:
            return (x, y, zoom)
        need = max(max(abs(b.clamped().cx - x) + b.clamped().w / 2,
                       abs(b.clamped().cy - y) + b.clamped().h / 2) for b in bad)
        zoom = max(1.0, min(zoom, 0.5 / max(0.001, need)))
        half = 0.5 / zoom

    return (x, y, zoom)


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
        CamKey(at - antic, *before, "slow", hit=True, reason="reveal"),
        CamKey(at - 1, *pull, "linear", hit=True, reason="reveal"),
        # `fast`, not `step`. A stepped ease holds four positions, which is the
        # right gesture for a long lean-in on a printed page and a flicker on a
        # six-frame overshoot: the eye sees four stills rather than one move.
        CamKey(at + rise, *over, "fast", hit=True, reason="reveal"),
        CamKey(at + rise + settle, *target, "slow", hit=True, reason="reveal"),
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
            if k.hold or k.hit:
                # The arriving key is the promise; the one in front of it is what
                # gives way. This used to drop `k` — so a hold the pen depends on
                # could be deleted by a transition it happened to land near, and
                # the stroke then ran on a card the camera had left. The pen is
                # the reason the frame is anywhere at all, so it is never the
                # thing dropped.
                out.pop()
                if out and k.at - out[-1].at < gap:
                    continue
            elif out[-1].hold or out[-1].hit:
                continue
            else:
                out.pop()
                if out and k.at - out[-1].at < gap:
                    continue
        out.append(k)
    return out


def keys_at_least(keys: Sequence[CamKey], gap: int = LEAD) -> list[CamKey]:
    """Two camera keys closer than `gap` frames read as one jump-cut. Keeps the
    earlier key and drops the later, so the move still arrives."""
    out: list[CamKey] = []
    for k in keys:
        if out and k.at - out[-1].at < gap and k.at > out[-1].at:
            continue
        out.append(k)
    return out
