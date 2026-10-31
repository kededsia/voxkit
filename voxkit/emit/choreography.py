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

from dataclasses import dataclass, field
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
        poses=tuple(Pose(int(p["atFrame"]), str(p["src"]))
                    for p in (slot.poses if slot else ()) if "atFrame" in p and "src" in p),
    )


def build_camera(shot: Shot, motions: Sequence[CardMotion], narration: Narration) -> list[cam.CamKey]:
    """Hold on information, move on transitions.

    The first card gets a punch (anticipate, overshoot, settle) because it is the
    shot's statement. Each later card gets a key that *starts* moving `LEAD`
    frames before the card lands, so the frame arrives with the word rather than
    after it.
    """
    if not motions:
        return [cam.CamKey(0, 0.5, 0.5, 1.04), cam.CamKey(max(1, shot.span - 6), 0.5, 0.5, 1.03)]

    first = motions[0]
    at = max(8, min(shot.span - 30, first.settle))

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

    # Dedupe the transition keys *before* the punch goes in. A punch is a
    # deliberately dense group — anticipate two frames back, pull one frame
    # before, overshoot three after, settle eight after that — and a gap filter
    # run over the finished list keeps only the last of those four. Every shot
    # in the film then had exactly one ease, "slow", and the hit that the whole
    # camera language is built on was silently dropped. The filter exists to
    # stop two *transitions* from reading as a jump-cut; a hit is not a jump-cut.
    keys = cam.keys_at_least(sorted(keys, key=lambda k: k.at), gap=8)
    keys = cam.punch(keys, at, cam.on(first.rect, 1.16), **cam.EMPHASIS)
    return sorted(keys, key=lambda k: k.at)


def build_shot(shot: Shot, plan: Plan, layout: Layout, narration: Narration,
               shot_index: int, plate: str, prefix: str = "") -> ShotProgram:
    motions: list[CardMotion] = []
    for i, card in enumerate(shot.ordered()):
        motions.append(build_card(card, layout.get(card.name), shot, i, shot_index,
                                  narration, prefix))

    keys = build_camera(shot, motions, narration)
    keep = tuple(m.rect for m, c in zip(motions, shot.ordered())
                 if any(ch.isdigit() for ch in c.semantik))
    keys = cam.plate_cam(keys, cam.MARGIN, keep)

    marks = []
    for i, m in enumerate(shot.marks):
        target = next((c for c in motions if c.name == m.card), motions[-1] if motions else None)
        box = (Rect.from_edges(*m.box) if m.box
               else (target.rect.expanded(0.014) if target else Rect(0, 0, 1, 1)))
        at = m.at if m.at is not None else min(shot.span - m.duration - 3,
                                              (target.settle + 6) if target else 8)
        marks.append(MarkMotion(
            shape=m.shape, box=box, at=at, duration=m.duration, rotate=m.rotate,
            pen=m.pen, motion=m.motion,
            color=m.color or ("coral" if i % 2 == 0 else "crimson"),
            sw=m.sw, seed=1000 + (shot_index + 1) * 73 + i * 17,
        ))

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
