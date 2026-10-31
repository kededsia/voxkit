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


@dataclass(frozen=True, slots=True)
class ShotProgram:
    id: str
    start: int
    span: int
    plate: str
    cards: tuple[CardMotion, ...]
    camera: tuple[cam.CamKey, ...]
    marks: tuple[MarkMotion, ...] = ()
    khat: Khat | None = None
    keep: tuple[Rect, ...] = ()

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
        rect=slot.rect if slot else card.rect,
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

    first = motions[0]
    keys = [cam.CamKey(0, 0.48, 0.48, 1.04)]
    prev_settle, prev_zoom = first.settle, 1.16
    for m in motions[1:]:
        if not (prev_settle + cam.LEAD <= m.settle <= shot.span - 14):
            continue
        accent = narration.score(shot.start + m.settle, "")
        zoom = 1.17 if accent >= 0.52 else (1.13 if (m.settle // 14) % 2 else 1.15)
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
        # The lead-in matters as much as the stroke: the camera has to be on the
        # card `MARK_LEAD` frames before the pen, so the hit must clear that too.
        lo, hi = mk.at - MARK_LEAD - 2, mk.at + mk.duration + 4
        if at - 3 <= hi and at + 12 >= lo:
            at = hi + 3
    if at > span - 14:
        return list(keys)
    return cam.punch(keys, at, cam.on(first.rect, 1.16), **cam.EMPHASIS)


def fit_marks(keys: Sequence[cam.CamKey], motions: Sequence[CardMotion],
              marks: Sequence[MarkMotion], span: int = 0) -> list[cam.CamKey]:
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

    # Pass 1 — the frame has to be on the card before the pen touches it.
    for mk in sorted(marks, key=lambda k: k.at):
        target = next((c for c in motions if c.name == mk.on), None)
        if target is None:
            continue
        win = cam.resolve(out, mk.at)
        if cam.holds(win, target.rect):
            continue
        at = max(1, mk.at - MARK_LEAD)
        framed = cam.frame_card(target.rect, win[2])
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


def enforce_holds(keys: Sequence[cam.CamKey], motions: Sequence[CardMotion],
                  marks: Sequence[MarkMotion]) -> list[cam.CamKey]:
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
        for f in (mk.at, mk.at + mk.duration):
            if cam.holds(cam.resolve(out, f), target.rect):
                continue
            framed = cam.frame_card(target.rect, cam.resolve(out, f)[2])
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

    keys = build_camera(shot, motions, narration)
    keep = tuple(m.rect for m, c in zip(motions, shot.ordered())
                 if any(ch.isdigit() for ch in c.semantik))
    # A marked card is information too: the camera may not trim the thing a hand
    # is pointing at.
    keep = keep + tuple(c.rect for c in motions
                        if any(mk.on == c.name for mk in marks) and c.rect not in keep)
    # Punch, then keep the figures whole, then the pen. In that order the hit
    # cannot delete the key that brings the camera onto a marked card (`punch`
    # drops every key inside its own eleven-frame window, and one of those is
    # usually exactly the arrival the pen needs), and the hit itself is held to
    # the same rule as every other key: it may not cut a printed figure. The pen
    # goes last, because last writer wins and the last writer must be the pen.
    if motions:
        keys = punch_for(keys, motions[0], marks, shot.span)
    keys = cam.plate_cam(keys, cam.MARGIN, keep)
    keys = fit_marks(keys, motions, marks, shot.span)
    keys = enforce_holds(keys, motions, marks)
    keys = cam.squeeze(keys)

    khat = None
    if shot.script:
        s = shot.script
        khat = Khat(
            text=str(s.get("text", "")), at=int(s.get("at", 8)),
            duration=int(s.get("duration", 34)),
            x=float(s.get("x", 0.16)), y=float(s.get("y", 0.18)),
            w=float(s.get("w", 0.28)), h=float(s.get("h", 0.28)),
            sw=int(s.get("sw", 15)), color=str(s.get("color", "crimson")),
            rotate=float(s.get("rotate", -3)), seed=2000 + (shot_index + 1) * 37,
        )

    return ShotProgram(id=shot.id, start=shot.start, span=shot.span, plate=plate,
                       cards=tuple(motions), camera=tuple(keys), marks=tuple(marks),
                       khat=khat, keep=keep)


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
