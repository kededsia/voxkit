"""Choreography: the shot's motion, computed as data.

The previous generator built its output by appending formatted strings to a list,
so the only way to know what a shot did was to read the TSX it produced — and a
defect in the maths was indistinguishable from a defect in the template. That is
how twenty-two modules ended up with every card travelling the same 17 frames and
every camera ease set to "slow": the accent lookup returned a constant, the
constant was formatted faithfully, and nothing between the plan and the render
could ask "does this shot move at all differently from the last one".

Here the program is a value. It can be printed, diffed, asserted on, and gated —
`vox gate program` reads it. The TSX emitter is a thin template over it and knows
no arithmetic.

Rules the numbers serve, each of which was a client correction:

  * a card settles on the word that names it (`lands`), and travels 14–21 frames
    depending on how hard the voice lands on that word;
  * the camera leads by at least `LEAD` frames and holds on information;
  * a puppet swap is a read, not a flicker: at least `MIN_SWAP_GAP` frames apart;
  * a shot never ends on a camera that is still travelling.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Sequence

from ..contract import TRAVEL_MAX, TRAVEL_MIN, Card, Plan, Shot
from ..geometry import Rect
from ..layout import Layout
from ..presenter import AGAIN_HOLD, connector, note_frames, present
from ..words import Narration
from . import camera as cam

# A puppet swap is a READ. Below this the puppet vibrates instead of moving.
MIN_SWAP_GAP = 6
# The calm beat between swaps; the widest step that still fits every action.
SWAP_BEAT = 22

# Material -> the renderer's idle behaviour. Read from `bahan`, which is the
# field the whole build obeys; deriving it from prose was a second opinion that
# disagreed (a man described as "a climber" was counted as a landscape).
KIND = {
    "figur": "figure", "foto": "photo", "cetak": "type", "koran": "type",
    "peta": "type", "benda": "other", "seal": "other",
}

# Travel in frames by how accented the landing word is. A calm word gets the long
# float; a struck word gets the short one, because the card has to be there when
# the voice hits it.
TRAVEL_BY_ACCENT = ((0.52, 14), (0.40, 17), (0.0, 21))
# Above this the camera answers the word with a `snap`; below it, a `slow` push.
SNAP_AT = 0.62

# A bound mark is timed by the card it points at: the pen touches the paper this
# many frames after the card has come to rest. Two frames is the beat it takes the
# eye to register that the piece has landed; a longer beat and the hand looks like
# it is answering something else.
MARK_LAG = 2
# Frames the pen needs to lift before the camera may leave the card. A mark that
# finishes on the same frame the camera starts moving reads as a flicker.
MARK_GAP = 3
# How early the frame must be holding the marked card before the pen touches it.
MARK_LEAD = 8
# How much of the frame the card under the pen should fill.
#
# The pen is the shot's subject while it is down, so the camera comes to it. This
# is the half of the mark framing that was missing: correcting *only* downwards
# made every marked card a reason to widen to zoom 1.0, which is the widest legal
# framing and therefore a still camera. 0.56 of the frame is close enough to read
# the card and far enough that its edges are still on the page.
MARK_PUSH = 0.56
# A push worth a camera key. Below this the move is a nudge, and a nudge on every
# mark turns a shot into a pump.
PUSH_GAIN = 1.05
# How much of the frame a card should fill when it lands.
#
# The camera's first job is to make each piece the right size on screen, and that
# number depends on the piece: a small slip has to be closer than a photograph
# that already spans half the page. Choosing it per card is what puts a zoom range
# inside a shot — a big card lands wide, a small one lands close, and the move
# between them is the camera working rather than drifting.
#
# Clamped below at 1.06 so a card that fills the page still leaves the camera
# somewhere to pull *back* to. That clamp is the fix for a camera that rested at
# zoom 1.000 for half of every module: 1.0 is the widest legal framing, so a
# camera sitting there has no "out" left to perform.
CAM_FILL = 0.50
CAM_ZOOM_MIN = 1.06


def card_zoom(rect) -> float:
    """The zoom at which `rect` fills `CAM_FILL` of the frame, within limits."""
    want = CAM_FILL / max(0.001, max(rect.w, rect.h))
    return max(CAM_ZOOM_MIN, min(cam.ZOOM_CAP, want))


@dataclass(frozen=True, slots=True)
class Pose:
    at: int
    src: str


@dataclass(frozen=True, slots=True)
class CardMotion:
    name: str
    src: str
    enter: int              # frame the card starts travelling (relative to the shot)
    settle: int             # frame it is on the page (relative to the shot)
    travel: int
    from_side: str
    stepped: int
    phase: float
    kind: str
    rect: Rect              # where the piece really is: the measured slot, not the prose
    z: int = 0              # stacking order, so a gate can ask what lies on top
    poses: tuple[Pose, ...] = ()


@dataclass(frozen=True, slots=True)
class MarkMotion:
    shape: str
    box: Rect
    at: int
    duration: int
    rotate: float
    pen: str
    motion: str
    color: str
    sw: int | None
    seed: int
    #: The card the gesture is drawn on. A mark is evidence of a hand looking at
    #: one thing; naming that thing lets the camera and the gates ask whether it
    #: was actually in the frame when the pen touched it.
    on: str = ""


@dataclass(frozen=True, slots=True)
class Khat:
    text: str
    at: int
    duration: int
    x: float
    y: float
    w: float
    h: float
    sw: int
    color: str
    rotate: float
    seed: int
    #: Ink goes on top of the collage, because that is what a hand does: it draws
    #: on the page, not under the pieces that are already glued to it. Below
    #: everything would read as a note slipped behind a photograph, which is a
    #: different (and much quieter) gesture than the one being made.
    z: int = 99


@dataclass(frozen=True, slots=True)
class ShotProgram:
    id: str
    start: int
    span: int
    plate: str
    cards: tuple[CardMotion, ...]
    camera: tuple[cam.CamKey, ...]
    marks: tuple[MarkMotion, ...] = ()
    #: The handwritten notes on this page. A page may carry more than one — the
    #: presenter writes "Cianjur" while the voice names it and "kecamatan" three
    #: seconds later, and refusing the second one because the first exists is a
    #: limit of the data model, not of the film.
    khats: tuple[Khat, ...] = ()
    keep: tuple[Rect, ...] = ()

    @property
    def khat(self) -> Khat | None:
        return self.khats[0] if self.khats else None

    @property
    def end(self) -> int:
        return self.start + self.span

    def card(self, name: str) -> CardMotion | None:
        return next((c for c in self.cards if c.name == name), None)


@dataclass(frozen=True, slots=True)
class ModuleProgram:
    module: str
    fps: int
    shots: tuple[ShotProgram, ...]
    audio: str = ""

    @property
    def duration(self) -> int:
        return max((s.end for s in self.shots), default=0)

    def travels(self) -> set[int]:
        return {c.travel for s in self.shots for c in s.cards}

    def eases(self) -> set[str]:
        return {k.ease for s in self.shots for k in s.camera}


# ------------------------------------------------------------------ building
def travel_for(accent: float) -> int:
    for floor, frames in TRAVEL_BY_ACCENT:
        if accent >= floor:
            return frames
    return TRAVEL_MAX


def mark_frame(m, target: CardMotion | None, shot: Shot) -> int:
    """When the pen touches the paper.

    A **bound** mark is timed by the card it points at, never by a frame of its
    own. This is the correction of the worst timing defect in the film: `at` used
    to be an absolute frame typed into the plan, nothing compared it with the
    card's own arrival, and it drifted — 74 % of the marks in the film fired while
    the camera was on a *different* card, and the worst fired 240 frames (eight
    seconds) after its card had landed. The arrow was correct, the box was
    correct, and the audience had already been moved somewhere else.

    The landing frame is the frame the voice names the card (`lands` == the word),
    so "two frames after the card lands" is also "two frames after the word",
    which is the only timing the plan was ever trying to express.

    A **page** mark (`box` given) has no card to be relative to and keeps its own
    absolute frame.
    """
    if target is None:
        return m.at if m.at is not None else max(2, shot.span // 2)
    if m.box is not None:
        return m.at if m.at is not None else min(shot.span - m.duration - 3,
                                                 target.settle + 6)
    delay = m.delay if m.delay is not None else MARK_LAG
    # The card may have been pushed later than `lands` (see `build_card`), so the
    # delay is applied to the frame the card really settles on.
    at = int(target.settle) + int(delay)
    # ...and the pen has to finish inside the shot.
    return max(0, min(at, shot.span - m.duration - 1))


def build_card(card: Card, slot, shot: Shot, index: int, shot_index: int,
               narration: Narration, prefix: str = "") -> CardMotion:
    """One card's motion. `lands` is relative to the shot, so `settle` is too."""
    settle = card.lands
    accent = narration.score(shot.start + settle, card.word)
    travel = min(travel_for(accent), max(2, settle))
    enter = max(0, settle - travel)
    if enter + travel != settle:
        # A card whose word is the shot's first frame has no room to travel in:
        # the earliest it can arrive is `travel` frames after the cut. Saying it
        # lands at f0 would be a claim the renderer cannot perform, and the
        # program gate is right to refuse that. The program says what will
        # actually happen — the card arrives on the first frame that has room.
        settle = enter + travel
    sides = ("left", "top", "right", "bottom")
    return CardMotion(
        name=card.name,
        src=f"{prefix}cards/{shot.id}/{card.name}.png",
        enter=enter,
        settle=settle,
        travel=travel,
        from_side=sides[(shot_index + index) % 4],
        stepped=3 if card.bahan == "seal" else 2,
        phase=round(0.5 + index * 0.75, 2),
        kind=KIND.get(card.bahan, "other"),
        rect=card.placed(slot.rect if slot else card.rect),
        z=card.z,
        poses=tuple(Pose(int(p["atFrame"]), str(p["src"]))
                    for p in (slot.poses if slot else ()) if "atFrame" in p and "src" in p),
    )


def build_camera(shot: Shot, motions: Sequence[CardMotion],
                 narration: Narration) -> list[cam.CamKey]:
    """Hold on information, move on transitions.

    The first card gets a punch (anticipate, overshoot, settle) because it is the
    shot's statement. Each later card gets a key that *starts* moving `LEAD`
    frames before the card lands, so the frame arrives with the word rather than
    after it.

    Then the camera answers the pen. Every mark is drawn on a card, so before the
    pen touches the paper the card has to be whole in the frame — 115 of the
    film's 205 marks were drawn on a card the camera had left partly outside it,
    which reads as an arrow that misses. A mark whose card is already framed adds
    no key at all, so this costs nothing on a shot that was already right.
    """
    if not motions:
        return [cam.CamKey(0, 0.5, 0.5, 1.04), cam.CamKey(max(1, shot.span - 6), 0.5, 0.5, 1.03)]

    # Time order, not stacking order. `shot.ordered()` sorts by `z`, because that
    # is what the renderer needs — but this loop walks the shot with a moving
    # `prev_settle`, so fed a z-order it sees a card that lands at f151, then one
    # that lands at f28, refuses the second for arriving "too early", and skips
    # every key between them. m03/s01 came out with five keys for ten seconds,
    # all of them flattened to zoom 1.000 by the settle pass.
    motions = sorted(motions, key=lambda m: (m.settle, m.enter))
    first = motions[0]
    keys = [cam.CamKey(0, 0.48, 0.48, 1.04)]
    prev_settle, prev_zoom = first.settle, 1.16
    for m in motions[1:]:
        if not (prev_settle + cam.LEAD <= m.settle <= shot.span - 14):
            continue
        accent = narration.score(shot.start + m.settle, "")
        zoom = card_zoom(m.rect)
        if accent >= 0.52:
            zoom = min(cam.ZOOM_CAP, zoom + 0.06)
        lead = max(prev_settle + 8, m.settle - cam.LEAD)
        if lead > prev_settle + 8:
            keys.append(cam.CamKey(lead, *cam.on(m.rect, prev_zoom), "slow"))
        keys.append(cam.CamKey(m.settle, *cam.on(m.rect, zoom),
                               "snap" if accent >= SNAP_AT else "slow"))
        prev_settle, prev_zoom = m.settle, zoom

    keys.append(cam.CamKey(max(1, shot.span - 6), 0.5, 0.5, 1.03, "slow"))

    # Two keys closer than a jump-cut apart are one move, not two. This runs
    # before the punch for a reason: a hit is *deliberately* dense — anticipate
    # two frames back, pull one before, overshoot three after, settle eight after
    # that — and a gap filter over the finished list keeps only the last of those
    # four. That is how every shot in this film ended up with exactly one ease,
    # "slow", and no camera hit at all.
    #
    # The punch itself is applied later, in `build_shot`, once the marks are
    # known: a hit drags the frame onto one card, and if a hand is drawing on a
    # *different* card at that moment the two fight. The anchor has to be chosen
    # knowing where the pen is.
    return cam.keys_at_least(sorted(keys, key=lambda k: k.at), gap=8)


def punch_for(keys: Sequence[cam.CamKey], first: CardMotion,
              marks: Sequence[MarkMotion], span: int) -> list[cam.CamKey]:
    """The shot's opening hit, placed where it does not collide with the pen.

    A hit on the marked card is fine — the camera and the hand agree. A hit on
    another card while a stroke is being drawn is not, so the anchor moves past
    the stroke. If the shot has no room left for a hit, the marks win: an arrow on
    the wrong card is a fault, a missing flourish is a loss.
    """
    at = max(8, min(span - 30, first.settle))
    for mk in sorted(marks, key=lambda k: k.at):
        if mk.on == first.name:
            continue
        # A page mark belongs to no card — it is the edge *between* two pieces —
        # so it does not compete with the hit for the same frame. Treating it as a
        # stroke on "some other card" pushed the opening hit out of every shot the
        # presenter drew a connector in, which is how adding an edge removed a
        # camera move.
        if not mk.on:
            continue
        # The lead-in matters as much as the stroke: the camera has to be on the
        # card `MARK_LEAD` frames before the pen, so the hit must clear that too.
        lo, hi = mk.at - MARK_LEAD - 2, mk.at + mk.duration + 4
        if at - 3 <= hi and at + 12 >= lo:
            at = hi + 3
    if at > span - 14:
        return list(keys)
    return cam.punch(keys, at, cam.on(first.rect, 1.16), **cam.EMPHASIS)


def fit_marks(keys: Sequence[cam.CamKey], motions: Sequence[CardMotion],
              marks: Sequence[MarkMotion], span: int = 0,
              keep: Sequence = (),
              windows: Sequence = ()) -> list[cam.CamKey]:
    """Put the frame on every card a hand is about to draw on — and keep it there.

    A mark is a gesture *on* a card. If the card is half out of the frame when the
    pen touches it, the stroke runs off the page and the eye reads an arrow that
    missed — which is exactly what the client reported. So for each mark: if the
    card is already whole in the frame, change nothing; if it is not, move the
    camera to it a few frames before the pen arrives.

    The second pass is the one that matters as much as the first: a camera that
    *arrives* on the marked card and then leaves four frames later drags the card
    out from under the stroke. Every key that would move the frame off the card
    while the pen is down is pushed past the end of the gesture. A punch is moved
    as a group, because half a hit is not a hit.
    """
    out = list(keys)

    # Pass 0 — no two transition keys inside a jump-cut of each other. This runs
    # FIRST because it *moves* keys, and a key moved after a hold has been placed
    # silently undoes the hold: the card slides out from under the stroke again,
    # and the gate that catches it points at the mark rather than at the ordering.
    kept: list[cam.CamKey] = []
    for k in out:
        if kept and k.at - kept[-1].at < 8 and not (kept[-1].hit and k.hit):
            # Move it, unless there is no room left in the shot — then the shot is
            # one key too long and the later key is the one that goes.
            if span and kept[-1].at + 8 > span - 2:
                continue
            k = replace(k, at=kept[-1].at + 8)
        kept.append(k)
    out = kept

    # Pass 1 — the frame has to be on the card before the pen touches it, and on
    # a card the pen is drawing on the frame should be *closer* than it was.
    for mk in sorted(marks, key=lambda k: k.at):
        target = next((c for c in motions if c.name == mk.on), None)
        if target is None:
            continue
        win = cam.resolve(out, mk.at)
        framed = cam.frame_card(target.rect, win[2], push=MARK_PUSH)
        # The push must not leave a printed figure half on screen. `settle`
        # answers with a pan when it can — the neighbour slides off the page,
        # which is harmless — and only falls back to widening when the pan would
        # cost the card the pen is on.
        # Only the figures that are being read *while this stroke is drawn*. The
        # full list is a demand that the camera hold every number in the shot at
        # once, and honouring it collapsed the frame to zoom 1.000 — the widest
        # framing, where a pan has five per cent of room and reads as nothing.
        local = tuple(r for (lo, hi, r) in windows
                      if lo <= mk.at <= hi or lo <= mk.at + mk.duration <= hi)
        framed = cam.settle(framed, local if windows else keep, subject=target.rect)
        if cam.holds(win, target.rect) and framed[2] <= win[2] * PUSH_GAIN:
            # Already whole in the frame and no worthwhile push to make: leave
            # the camera alone. A correction is not a second opinion about how
            # tight the shot should be — but a card the pen is on *is* the shot.
            continue
        at = max(1, mk.at - MARK_LEAD)
        near = next((i for i, k in enumerate(out) if abs(k.at - at) < 8 and not k.hit), None)
        if near is not None:
            out[near] = cam.CamKey(at, *framed, out[near].ease, hit=out[near].hit, hold=True)
        else:
            out.append(cam.CamKey(at, *framed, "slow", hold=True))

    for mk in sorted(marks, key=lambda k: k.at):
        target = next((c for c in motions if c.name == mk.on), None)
        if target is None:
            continue
        lo = mk.at
        hi = min(span - 4 if span else 10 ** 6, mk.at + mk.duration + MARK_GAP)

        # The framing the camera must be holding when the pen touches down.
        # Taken from the last key at or before `lo` that actually holds the card,
        # because that is the framing the frame will have *arrived* at.
        anchor = next((k for k in reversed(sorted(out, key=lambda k: k.at))
                       if k.at <= lo and cam.holds((k.x, k.y, k.zoom), target.rect)), None)
        if anchor is None:
            anchor = cam.CamKey(lo, *cam.frame_card(target.rect, cam.resolve(out, lo)[2]),
                                "slow", hold=True)
            out.append(anchor)

        # Freeze the frame until the stroke is finished. Without this the camera
        # is already in transit when the pen lands — it starts moving at the
        # previous key, which is typically eight frames earlier — and the card
        # slides out from under the stroke while it is being drawn. That is the
        # second half of "the mark misses the word", and it is invisible in the
        # plan: both the mark and the camera are individually correct.
        if not any(k.at == hi and cam.holds((k.x, k.y, k.zoom), target.rect) for k in out):
            out.append(cam.CamKey(hi, anchor.x, anchor.y, anchor.zoom, "slow", hold=True))

        # ...and nothing may start moving away on the frame the pen lifts either:
        # a key one frame after the hold is a jump-cut.
        for i, k in enumerate(out):
            if lo < k.at < hi and not cam.holds((k.x, k.y, k.zoom), target.rect):
                # A key *inside* the stroke is worse than one after it: the frame
                # dips away and comes back, so the card slides out from under the
                # pen and returns. Delaying it past the gesture keeps the move and
                # loses nothing but its original timing.
                out[i] = replace(k, at=min(span - 2, hi + 8) if span else hi + 8)
            elif hi < k.at < hi + 8 and not cam.holds((k.x, k.y, k.zoom), target.rect):
                out[i] = replace(k, at=min(span - 2, hi + 8) if span else hi + 8)

    # Two keys on one frame is not a move; keep the later one, which is the one
    # the pen and the landing both agree on.
    by_frame: dict[int, cam.CamKey] = {}
    for k in sorted(out, key=lambda k: k.at):
        by_frame[k.at] = k
    out = sorted(by_frame.values(), key=lambda k: k.at)

    # Pass 3 — a hold key inserted in pass 2 can land two frames after a key that
    # was already there. Push the *later* one forward: moving it can never move a
    # key into a stroke, and the hold is the one thing in the list that must not
    # budge.
    kept = []
    for k in out:
        if kept and k.at - kept[-1].at < 8 and not (kept[-1].hit and k.hit):
            if k.hold and not kept[-1].hold:
                # The pen is the reason the frame is here, so the key in front of
                # it gives way — by being *dropped*, not moved. Moving it back
                # would put it on top of the key before that, and the pair would
                # still be two frames apart with one more collision to fix.
                kept.pop()
                if kept and k.at - kept[-1].at < 8:
                    continue
            elif span and kept[-1].at + 8 > span - 2:
                continue
            else:
                k = replace(k, at=kept[-1].at + 8)
        kept.append(k)
    return kept


def steady_holds(keys: Sequence[cam.CamKey], marks: Sequence[MarkMotion],
                 motions: Sequence[CardMotion]) -> list[cam.CamKey]:
    """A stroke may be drawn under a drifting camera, never under a resizing one.

    This is the last arithmetic fault in the mark framing, and it is invisible in
    every key: two keys can each hold the card perfectly, and the *line between
    them* still not hold it. A card flush with the bottom of the page can only be
    framed at `y = 1 - 0.5/zoom`, which is a curve; the renderer interpolates a
    straight chord, and the chord sits inside the curve. Measured on `m03/s05` the
    error is two hundred-thousandths of the frame — enough for the gate to be
    right and the stroke to run a hair off the card's edge.

    The repair is not a tolerance. With zoom constant the constraint becomes a
    plain interval in x and y, and an interval is convex: if both ends are inside
    it, everything between them is. So the zoom of the framing in force when the
    pen touches down is held for the whole stroke, and the camera is free to move
    across the card — which is what a hand-held shot looks like anyway.
    """
    out = list(keys)
    for mk in sorted(marks, key=lambda k: k.at):
        target = next((c for c in motions if c.name == mk.on), None)
        if target is None:
            continue

        # The framing the stroke is drawn under: the first key at or before the
        # pen, repaired if it does not actually hold the card.
        before = [i for i, k in enumerate(out) if k.at <= mk.at]
        if before:
            i = max(before, key=lambda j: out[j].at)
            anchor = (out[i].x, out[i].y, out[i].zoom)
        else:
            anchor = cam.frame_card(target.rect, MARK_PUSH)
        if not cam.holds(anchor, target.rect):
            anchor = cam.frame_card(target.rect, anchor[2])

        # A stroke that overlaps this one on *another* card cannot be given its
        # own framing: the camera would have to be in two places at once, and the
        # stroke whose anchor was written last would be drawn on a card the frame
        # had already left. m15 s03 is the case — an underline on the bottom card
        # at f44 and a circle on the top one at f47, and the circle took the
        # camera with it, so the underline ran off the page.
        #
        # The answer is not to make the pen wait. Delaying the later stroke is a
        # time shift the viewer did not ask for, and it cascades: in m01 s04 four
        # strokes were pushed a hundred frames late and the camera lost the move
        # that was covering the silence. The answer is the one a camera operator
        # would give — pull back until one framing holds both cards, and draw
        # both strokes in it. `settle` reduces the zoom only as far as it must.
        both = [target.rect]
        for other in marks:
            if other is mk or not other.on or other.on == mk.on:
                continue
            if not (other.at <= mk.at + mk.duration + MARK_LEAD
                    and mk.at <= other.at + other.duration + MARK_LEAD):
                continue
            t2 = next((c for c in motions if c.name == other.on), None)
            if t2 is not None and cam.frameable(t2.rect):
                both.append(t2.rect)
        if len(both) > 1:
            anchor = cam.settle(anchor, tuple(both), subject=target.rect)

        # Every key from just before the pen to just after it carries the *same*
        # framing — including the key the camera leaves on. Not the same zoom with
        # a re-solved position, and not two legal framings joined by a chord: the
        # same three numbers. A constant is the only interpolation that cannot
        # leave a convex region, and the region a card occupies at a fixed zoom is
        # convex. The trailing key is in the window because the chord *toward* it
        # starts moving eight frames before it arrives, which is inside the
        # stroke: a camera that leaves early drags the card out from under the pen
        # on the last frames of the gesture.
        lo, hi = mk.at - 1, mk.at + mk.duration
        for i, k in enumerate(out):
            if lo <= k.at <= hi + MARK_LEAD:
                out[i] = replace(k, x=anchor[0], y=anchor[1], zoom=anchor[2], hold=True)
        # ...and the stroke needs a key at its own end, or the next transition
        # starts pulling the card out from under the pen on its final frames. Only
        # when nothing is already there to close the stroke: a key inside the
        # trailing window has just been set to the anchor, which closes it, and
        # adding another one eight frames or less away would be the jump-cut the
        # camera rules forbid.
        if not any(hi < k.at <= hi + MARK_LEAD for k in out):
            out.append(cam.CamKey(hi, *anchor, "slow", hold=True))
    by_frame: dict[int, cam.CamKey] = {}
    for k in sorted(out, key=lambda k: k.at):
        by_frame[k.at] = k
    return sorted(by_frame.values(), key=lambda k: k.at)


def finish_figures(keys: Sequence[cam.CamKey], keep: Sequence[Rect],
                   subjects: Sequence[tuple[float, float, Rect]] = ()) -> list[cam.CamKey]:
    """A figure is whole on screen or it is not on screen. Never half.

    Two passes above disagree about this, and both are right in their own terms.
    `plate_cam` protects a figure only *while it is being read*, because holding
    every figure at every key pins the camera to the widest framing — that is the
    fault that flattened m03. The `program` gate asks for more, because a number
    half off the edge still reads as a number, and it reads as the wrong one. It
    is cheaper than `plate_cam` in the only way that matters here: it looks at the
    keys, not at every frame.

    So they are reconciled at the only place they can be. A key that clips a
    figure is moved the smallest distance that makes the figure whole, and
    `settle` prefers a pan of one per cent to a change of zoom — the move the shot
    was built around survives, because a key that clips nothing is not touched at
    all.

    This runs after the figure pass and before the pen, so the pen still has the
    last word on the card it draws on. m15 s02 at f182 is the case: the camera sat
    0.5 % too far right, the left edge of a figure was cut, and every other gate
    was green.
    """
    out = list(keys)
    for i, k in enumerate(out):
        if not any(cam.clipped((k.x, k.y, k.zoom), r) for r in keep):
            continue
        subject = next((r for (lo, hi, r) in subjects if lo <= k.at <= hi), None)
        x, y, z = cam.settle((k.x, k.y, k.zoom), keep, subject=subject)
        if (round(x, 4), round(y, 4), round(z, 4)) != (k.x, k.y, k.zoom):
            out[i] = replace(k, x=round(x, 4), y=round(y, 4), zoom=round(z, 4))
    return out


def enforce_holds(keys: Sequence[cam.CamKey], motions: Sequence[CardMotion],
                  marks: Sequence[MarkMotion],
                  keep: Sequence[Rect] = ()) -> list[cam.CamKey]:
    """The last word: the frame holds every marked card at both ends of its stroke.

    The passes above get this right almost everywhere, but "almost" is not a
    guarantee and the eye only needs one arrow on the wrong card. So the claim is
    checked here and repaired by *moving the key that is in force*, not by adding
    another one — an extra key two frames from an existing one is a jump-cut, and
    the repair would create the fault it is fixing.
    """
    out = list(keys)
    for mk in sorted(marks, key=lambda k: k.at):
        target = next((c for c in motions if c.name == mk.on), None)
        if target is None:
            continue
        # A cut-out that fills the page has no tighter framing that holds it, and
        # no need of one: the stroke is drawn inside the piece.
        if not cam.frameable(target.rect):
            continue
        for f in (mk.at, mk.at + mk.duration):
            if cam.holds(cam.resolve(out, f), target.rect):
                continue
            # Frame the card, then let `settle` reconcile that with the printed
            # figures. Framing the card alone is a repair that creates a fault:
            # the camera arrives on the card the pen is on and cuts a number in
            # half on the way — and then the figure pass moves it back, and the
            # stroke is off the page again. Both constraints have to be solved at
            # once, which is what settle does.
            framed = cam.frame_card(target.rect, cam.resolve(out, f)[2])
            framed = cam.settle(framed, keep, subject=target.rect)
            before = [i for i, k in enumerate(out) if k.at <= f]
            if before:
                i = max(before, key=lambda j: out[j].at)
                out[i] = replace(out[i], x=framed[0], y=framed[1], zoom=framed[2], hold=True)
            else:
                out.append(cam.CamKey(max(1, f), *framed, "slow", hold=True))
            # The key *after* the pen matters as much as the one before it: the
            # frame is already interpolating toward it, so a key that leaves the
            # card drags the card out from under the stroke even though every key
            # individually looks fine. If it does not hold the card, it becomes the
            # hold. The transition it was carrying is lost; the arrow is not.
            after = [i for i, k in enumerate(out) if k.at > f]
            if after:
                j = min(after, key=lambda i: out[i].at)
                if not cam.holds((out[j].x, out[j].y, out[j].zoom), target.rect):
                    out[j] = replace(out[j], x=framed[0], y=framed[1], zoom=framed[2],
                                     hold=True)
    by_frame: dict[int, cam.CamKey] = {}
    for k in sorted(out, key=lambda k: k.at):
        by_frame[k.at] = k
    return sorted(by_frame.values(), key=lambda k: k.at)


#: The longest the frame may sit perfectly still. A "hold" in an edit is a slow
#: creep, never a freeze: the eye reads a dead frame as a mistake within a second,
#: and 43 % of m03's frames were dead because a hold was implemented as a constant.
STILL_RUN = 16
CREEP = 0.022
#: How close two framings have to be before they are the same hold. Not equality:
#: the first version asked for bit-identical keys, and the passes before this one
#: had already nudged every park by a third of a per cent — so the run was not
#: recognised, no breath was added, and two seconds of m03 sat at 0.33 % drift.
#: This is the same 1 % the `program` gate calls "no change"; if the eye cannot
#: see it move, it is a park and it needs a breath.
PARK = 0.010


def creep(keys: Sequence[cam.CamKey], marks: Sequence[MarkMotion],
          motions: Sequence[CardMotion],
          keep: Sequence[Rect] = (),
          figures: Sequence[tuple[int, int, Rect]] = ()) -> list[cam.CamKey]:
    """Put a breath into every hold.

    The camera used to park: `steady_holds` made the framing constant across a
    stroke (correct — the pen must not be drawn on a moving card) and `fit_marks`
    made it constant across an arrival, and between them the frame was literally
    the same picture for two seconds at a time. The client watched m03 and said
    the camera does not move, and by measurement they were right for 710 of 1636
    frames.

    So a hold becomes a slow push. Two per cent of zoom across a second is
    invisible as a move and unmistakable as life — and it is only applied where
    every piece being marked in that window stays whole, so it can never clip the
    card the pen is on.

    `figures` is the same promise for printed ink: a figure is whole while it is
    being read. This pass runs *last*, after `enforce_holds` has made that true, so
    without the window here the breath could be the thing that cuts a number in
    half — which is exactly what m15 s02 did at f182, and the `program` gate named
    it.
    """
    if len(keys) < 2:
        return list(keys)
    windows: list[tuple[int, int, Rect]] = []
    for m in marks:
        t = next((c for c in motions if c.name == m.on), None)
        if t is None:
            continue
        if not cam.frameable(t.rect):
            continue
        windows.append((m.at, m.at + m.duration, t.rect))

    def safe(at: int, x: float, y: float, z: float) -> bool:
        """Everything that must be whole at `at` is still whole."""
        if z < cam.zoom_floor(x, y, cam.MARGIN) - 1e-9:
            return False
        if any(not cam.holds((x, y, z), r) for r in keep):
            return False
        if any(not cam.holds((x, y, z), r) for (lo, hi, r) in figures if lo <= at <= hi):
            return False
        return all(cam.holds((x, y, z), r)
                   for (lo, hi, r) in windows if lo <= at <= hi)

    def breathe(at: int, x: float, y: float, z: float) -> tuple[float, float, float] | None:
        """A framing near the one asked for that keeps every promise.

        The breath is not allowed to be the thing that cuts a number in half, so
        the candidate is settled against the figures first — which is a *pan* as
        often as a zoom, and a pan is the better answer anyway: the frame drifts
        a little instead of breathing.
        """
        # The piece the pen is on at this frame has to survive the breath, so it
        # is passed as the subject: `settle` will then pan to contain the figures
        # rather than pan away from the card being drawn on.
        subject = next((r for (lo, hi, r) in windows if lo <= at <= hi), None)
        if subject is None:
            # No pen here, but a figure may be being read; the breath has to keep
            # that one whole too, so it becomes the subject the settle protects.
            subject = next((r for (lo, hi, r) in figures if lo <= at <= hi), None)
        sx, sy, sz = cam.settle((x, y, z), keep, subject=subject)
        if not safe(at, sx, sy, sz):
            return None
        return (sx, sy, sz)
    out = list(keys)

    def slow(p: cam.CamKey, q: cam.CamKey) -> bool:
        """Does the camera move too little between these two keys to be seen?

        A *rate*, not a distance. The first version asked whether the two keys
        were bit-identical, and the passes before this one had already nudged
        every park by a third of a per cent, so the run was not recognised and no
        breath was added. The second asked whether they were within a per cent of
        each other, which missed the opposite case: m03 s04 panned 3.7 % over two
        seconds — a key distance that passes any threshold and a speed that the
        eye reads as a photograph. Both faults are the same fault: what matters is
        not how far the frame went, it is how far it went *per second*.
        """
        need = PARK * max(1.0, (q.at - p.at) / STILL_RUN)
        return (abs(p.x - q.x) < need and abs(p.y - q.y) < need
                and abs(p.zoom - q.zoom) < need)

    # Runs, not pairs. A park of two seconds is usually four keys holding one
    # framing, and no single pair between them is long enough to look like a hold
    # — so the first version of this missed every park worth fixing.
    i = 0
    while i < len(out) - 1:
        j = i
        while j + 1 < len(out) and slow(out[j], out[j + 1]):
            j += 1
        if j > i and out[j].at - out[i].at >= STILL_RUN:
            # Creep *backwards*: shrink the first key and let the hold push in.
            # Zooming the last key in would clip the very card the pen is on,
            # because the framing was chosen to hold that card exactly — but
            # anything wider than the hold also holds it, so the room to move is
            # behind the camera, not in front of it. A 2 % pull-out at the start
            # of a hold is the whole gesture: the frame breathes in.
            a, b = out[i], out[j]
            floor = cam.zoom_floor(a.x, a.y, cam.MARGIN)
            # The breath is a *rate*, not an amount. A flat 2.2 % spread over a
            # two-second park is a fifth of a per cent a second — measurably a
            # move, visibly a still. The gain scales with the length of the park,
            # so a long hold breathes as far as a short one.
            gain = min(0.10, CREEP * max(1.0, (b.at - a.at) / 30.0))
            z = max(floor, a.zoom * (1 - gain))
            # A creep that un-holds the card the pen is on is not a breath, it is
            # the arrow-misses-the-word fault reintroduced by the back door.
            moved = False
            if a.zoom - z > 1e-4:
                hit = breathe(a.at, a.x, a.y, z)
                if hit is not None:
                    out[i] = replace(a, x=round(hit[0], 4), y=round(hit[1], 4),
                                     zoom=round(hit[2], 4))
                    moved = True
            # A park long enough to hold two breaths gets both: the frame comes in
            # at the start and keeps coming in to the end, so the whole run is a
            # slow push instead of a step and a freeze. One breath at the head of
            # a two-second park leaves the other second and a half dead, which is
            # exactly what the measurement kept finding.
            if moved and b.at - a.at >= 2 * STILL_RUN:
                # Push in by the *same* gain the head pushed out, so the frame
                # travels 2·gain across the park instead of returning to where it
                # started. Half a gain was tried and measured at 1.17 % on a
                # thirty-two frame park — it clears the gate by a tenth of a per
                # cent and the middle of the park is still dead to the eye.
                z2 = min(cam.ZOOM_CAP, b.zoom * (1 + gain))
                hit = breathe(b.at, b.x, b.y, z2)
                if hit is not None:
                    out[j] = replace(b, x=round(hit[0], 4), y=round(hit[1], 4),
                                     zoom=round(hit[2], 4))
            elif not moved:
                # Nowhere behind the camera to go: the head breath was refused,
                # which means this framing is already at the floor the page
                # allows. The move has to come from in front of it, or from the
                # side — a drift is tried first because it costs no zoom at all,
                # and at zoom 1.0 a drift is the only move left.
                for dx, dy, dz in ((0.0, 0.0, gain), (gain, 0.0, 0.0),
                                   (0.0, gain, 0.0)):
                    z = min(cam.ZOOM_CAP, b.zoom * (1 + dz))
                    hit = breathe(b.at, b.x + dx, b.y + dy, z)
                    if hit is not None and (abs(hit[0] - b.x) + abs(hit[1] - b.y)
                                            + abs(hit[2] - b.zoom)) > 1e-4:
                        out[j] = replace(b, x=round(hit[0], 4), y=round(hit[1], 4),
                                         zoom=round(hit[2], 4))
                        break
            # Two breaths are enough for a park of two seconds and not for a park
            # of four. `resolve` interpolates *between* keys, so a key in the
            # middle of the run that still carries the plateau value holds that
            # value flat until the next key — m15 s05 parked for 126 frames, got
            # a breath at f174 and another at f300, and left f205..f286 at exactly
            # 1.0600. The gate measured 92 dead frames inside a run that was
            # technically breathing at both ends.
            #
            # So the interior keys ride the same ramp as the ends: each one takes
            # the position that a straight line from the head breath to the tail
            # breath would put it at, and `breathe` still has the last word — an
            # interior key that cannot move without clipping a stroke or a figure
            # is left where it was, which is correct, because the ramp exists to
            # remove dead air and not to buy it with a clipped card.
            head, tail = out[i], out[j]
            if (tail.at - head.at > 2 * STILL_RUN
                    and (abs(tail.zoom - head.zoom) > 1e-4
                         or abs(tail.x - head.x) > 1e-4
                         or abs(tail.y - head.y) > 1e-4)):
                for k in range(i + 1, j):
                    t = (out[k].at - head.at) / max(1, tail.at - head.at)
                    hit = breathe(out[k].at,
                                  head.x + (tail.x - head.x) * t,
                                  head.y + (tail.y - head.y) * t,
                                  head.zoom + (tail.zoom - head.zoom) * t)
                    if hit is not None:
                        out[k] = replace(out[k], x=round(hit[0], 4),
                                         y=round(hit[1], 4), zoom=round(hit[2], 4))
        i = j + 1
    return out


def build_shot(shot: Shot, plan: Plan, layout: Layout, narration: Narration,
               shot_index: int, plate: str, prefix: str = "") -> ShotProgram:
    motions: list[CardMotion] = []
    for i, card in enumerate(shot.ordered()):
        motions.append(build_card(card, layout.get(card.name), shot, i, shot_index,
                                  narration, prefix))

    # Marks first, camera second. The pen decides where the frame has to be, so
    # the marks cannot be an afterthought appended to a finished camera move —
    # that ordering is exactly why 115 of 205 marks were drawn on a card the
    # camera had left half outside the frame.
    marks = []
    for i, m in enumerate(shot.marks):
        target = next((c for c in motions if c.name == m.card), motions[-1] if motions else None)
        box = (Rect.from_edges(*m.box) if m.box
               else (target.rect.expanded(0.014) if target else Rect(0, 0, 1, 1)))
        at = mark_frame(m, target, shot)
        marks.append(MarkMotion(
            shape=m.shape, box=box, at=at, duration=m.duration, rotate=m.rotate,
            pen=m.pen, motion=m.motion,
            color=m.color or ("coral" if i % 2 == 0 else "crimson"),
            sw=m.sw, seed=1000 + (shot_index + 1) * 73 + i * 17,
            on=target.name if target and m.box is None else "",
        ))

    # The presenter's decisions, taken once. Every gesture it returns is either
    # a stroke on a card or a note on the page, and both are placed here — the
    # presenter decides *what* and *why*, this function decides *where the ink
    # goes* and when the pen may touch.
    gestures = present(shot, narration)

    # The presenter's edges. A `relate` gesture is the only mark that belongs to
    # two pieces at once: it is drawn on the page, between them, because a
    # relation is not a property of either thing. Without it the viewer sees four
    # pieces appear one after another and has to work out for themselves that the
    # sentence was joining them; with it they see the argument.
    for g in gestures:
        if g.kind == "again":
            # The presenter going back to something already on the page. It is a
            # stroke on a card, so it is timed by the card like every other mark —
            # and the camera has to hold that card while the pen is down, which
            # `fit_marks` and `enforce_holds` already guarantee for anything with
            # an `on`.
            target = next((c for c in motions if c.name == g.on), None)
            if target is None:
                continue
            marks.append(MarkMotion(
                shape=g.shape, box=target.rect.expanded(0.014),
                at=max(target.settle + 2, min(g.at - shot.start, shot.span - 18)),
                duration=AGAIN_HOLD, rotate=-3.0, pen="marker", motion="draw",
                color="crimson" if len(marks) % 2 else "coral", sw=None,
                seed=1000 + (shot_index + 1) * 73 + len(marks) * 17, on=target.name,
            ))
            continue
        if g.kind != "relate":
            continue
        a = next((c for c in motions if c.name == g.on), None)
        b = next((c for c in motions if c.name == g.to), None)
        if a is None or b is None:
            continue
        cx, cy, w, h, rot = connector(a.rect, b.rect, plan.stage_aspect)
        marks.append(MarkMotion(
            shape=g.shape, box=Rect.from_centre(cx, cy, w, h),
            at=max(0, min(g.at - shot.start, shot.span - 20)), duration=16,
            rotate=rot, pen="marker", motion="draw", color="coral", sw=None,
            seed=1000 + (shot_index + 1) * 73 + len(marks) * 17, on="",
        ))

    # ------------------------------------------------------------------ camera
    # The pipeline below is the whole camera, in order, once. Every step is here
    # because it was needed to repair a fault that a later step could undo, so
    # the order is the design and not an accident of editing. A step that runs
    # twice, or a comment that describes a step that no longer exists, is how a
    # camera ends up parked at zoom 1.000 while every gate reports it as moving.
    figures = [(m, c) for m, c in zip(motions, shot.ordered())
               if any(ch.isdigit() for ch in c.semantik) and cam.frameable(m.rect)]
    keep = tuple(m.rect for m, _ in figures)
    # A group that no single position can hold is a fact about the page, not a
    # constraint on the camera: chased, it drags every framing down to the widest
    # one and the shot loses its move. The `program` gate reports it instead.
    if keep and cam.keep_interval(keep, cam.MARGIN) is None:
        keep = ()
    # When each figure is *read*, and when each piece is *written on*. These are
    # different constraints with different lifetimes, and conflating them is what
    # pinned the camera: "keep every number whole for the whole shot" is a demand
    # only the widest framing satisfies.
    read_windows = [(max(0, m.settle - 4), min(shot.span, m.settle + 48), m.rect)
                    for m, _ in figures]
    pen_windows = [(m.at - 26, m.at + m.duration + 26, c.rect)
                   for m in marks for c in motions
                   if m.on and c.name == m.on and cam.frameable(c.rect)]

    keys = build_camera(shot, motions, narration)
    if motions:
        keys = punch_for(keys, motions[0], marks, shot.span)
    # 1. the move, held only to the figures being read at that moment
    keys = cam.plate_cam(keys, cam.MARGIN, keep, read_windows)
    # 2. the pen: put the frame on the card a stroke is about to land on
    keys = fit_marks(keys, motions, marks, shot.span, keep, read_windows)
    # 3. housekeeping: two keys closer together than a jump cut are one move
    keys = cam.squeeze(keys)
    # 4. the hold: a constant framing for the whole stroke. This has to run after
    #    `squeeze`, because `squeeze` drops keys and a dropped key is replaced by
    #    whatever the neighbours carry — which is how a hold got deleted once.
    keys = steady_holds(keys, marks, motions)
    # 5. every figure whole on every frame. The windowed pass above protects the
    #    move; this one protects the number. It is affordable now because
    #    `settle` can answer with a pan that *contains* the figure instead of a
    #    retreat that widens the shot.
    keys = cam.plate_cam(keys, cam.MARGIN, keep, subjects=pen_windows)
    # 5b. a figure is whole or absent, on every key and not only while it is read
    keys = finish_figures(keys, keep, pen_windows)
    # 6. the pen again, because step 5 may have moved a key out from under a
    #    stroke. The stroke is the one constraint that cannot be traded.
    keys = enforce_holds(keys, motions, marks, keep)
    # 7. and the breath, last: every step above can park the frame, and a parked
    #    frame is what the client saw as "kameranya masih gak bergerak".
    keys = creep(keys, marks, motions, keep, figures=read_windows)

    khats: list[Khat] = []
    if shot.script:
        s = shot.script
        khats.append(Khat(
            text=str(s.get("text", "")), at=int(s.get("at", 8)),
            duration=int(s.get("duration", 34)),
            x=float(s.get("x", 0.16)), y=float(s.get("y", 0.18)),
            w=float(s.get("w", 0.28)), h=float(s.get("h", 0.28)),
            sw=int(s.get("sw", 15)), color=str(s.get("color", "crimson")),
            rotate=float(s.get("rotate", -3)), seed=2000 + (shot_index + 1) * 37,
        ))
    else:
        # A note the presenter wrote to answer silence. It comes with its own
        # place on the page, because the presenter is the only thing in the
        # pipeline that can see what the note would cover — the emitter knows
        # where the pieces are but not what they say. All the emitter does is
        # nudge it into the frame the camera is actually holding, which is the
        # one thing the presenter cannot know.
        for note in [g for g in gestures if g.kind == "write"
                     and g.spot is not None and g.text]:
            # `g.at` is on the narration's clock; the renderer's is per shot.
            local = max(0, min(note.at - shot.start, shot.span - 12))
            box = note.spot
            # The note must sit where the camera is actually looking. That is the
            # one thing the presenter cannot know — it decides what to say, not
            # where the frame has gone — so the note is nudged into the window
            # rather than the window widened for the note.
            win = cam.resolve(keys, local)
            half_w = half_h = 0.5 / win[2]
            lo_x, hi_x = max(0.0, win[0] - half_w), min(1.0, win[0] + half_w)
            lo_y, hi_y = max(0.0, win[1] - half_h), min(1.0, win[1] + half_h)
            if box.w <= hi_x - lo_x and box.h <= hi_y - lo_y:
                nx = min(max(box.x0, lo_x), hi_x - box.w)
                ny = min(max(box.y0, lo_y), hi_y - box.h)
                box = Rect.from_edges(nx, ny, nx + box.w, ny + box.h)
            # A word takes as long to write as it has letters — one definition,
            # in `presenter.note_frames`, shared with the solver that decided the
            # note would fit the silence in the first place.
            length = note_frames(note.text)
            if local + length > shot.span - 3:
                length = max(18, shot.span - local - 3)
            khats.append(Khat(
                text=note.text, at=local, duration=length,
                x=box.x0, y=box.y0, w=box.w, h=box.h, sw=9, color="crimson",
                rotate=-2.5, seed=2000 + (shot_index + 1) * 37 + len(khats) * 11,
            ))

    return ShotProgram(id=shot.id, start=shot.start, span=shot.span, plate=plate,
                       cards=tuple(motions), camera=tuple(keys), marks=tuple(marks),
                       khats=tuple(khats), keep=keep)


def build_module(plan: Plan, layouts: dict[str, Layout], narration: Narration,
                 plate_for, fps: int = 30, audio: str = "", prefix: str = "") -> ModuleProgram:
    """Every shot of a module. `plate_for(shot_id)` returns the plate's name in
    the renderer's own terms, so the emitter never guesses a file name.

    `prefix` is where the renderer finds this module's assets under `public/`.
    The program names files the way the renderer will read them, so a gate can
    check that they are there.
    """
    shots = []
    for i, shot in enumerate(plan.shots):
        layout = layouts.get(shot.id) or Layout()
        shots.append(build_shot(shot, plan, layout, narration, i,
                                plate_for(shot.id), prefix))
    return ModuleProgram(module=plan.module, fps=fps, shots=tuple(shots), audio=audio)
