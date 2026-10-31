"""Program gates: what the shot will actually do, checked before it is rendered.

Every other gate reads an input — the plan, a still, a piece. This one reads the
*output of the generator*, and that is the only place a whole class of defect is
visible:

    twenty-two modules were built where every card travelled the same 17 frames
    and every camera ease was "slow". The plan was fine. The stills were fine. The
    accents were measured. The generator's word lookup read a transcript shape the
    transcriber had stopped producing, found no words, and returned its default
    for every card. No gate could see it, because every gate asked about the plan
    and the answer was in the emitted code.

So: the program is computed, and then questioned. Does a card arrive on the frame
its word is spoken? Does the module move differently from shot to shot? Is every
camera key inside its own shot? Does the camera ever push past its cap, or pan a
figure out of frame? Do the puppets keep their distance?
"""
from __future__ import annotations

from ..contract import TRAVEL_MAX, Finding, fail, note, warn
from ..emit import camera as cam
from ..emit.choreography import MIN_SWAP_GAP, build_module
from ..layout import Layout
from ..words import FLOOR
from .base import Context, Gate, Skipped

# How much of a stroke may land on a piece other than the one it is marking.
#
# Measured on the *stroke*, not on the card. How much of a card is hidden is a
# question about the composition, and `compose` already answers it at 55 %; what
# makes an arrow "miss the word" is the ink crossing a different piece, so that
# the gesture points at two things at once.
#
# A marker dragged across a collage will catch a torn edge, and that is the
# material rather than a fault. A third of the box on another piece is worth
# looking at.
MARK_STRAY_WARN = 0.34


def program_of(ctx: Context):
    """Build the module's program, or explain why it cannot be built yet."""
    narration = ctx.narration
    if narration is None or not narration.accents:
        raise Skipped("no scored narration — the choreography has nothing to answer")

    layouts: dict[str, Layout] = {}
    missing = []
    for shot in ctx.plan.shots:
        path = ctx.project.card_dir(ctx.module, shot.id) / "layout.json"
        if path.is_file():
            layouts[shot.id] = Layout.load(path)
        else:
            missing.append(shot.id)
    if missing:
        raise Skipped(f"no measured layout for {', '.join(missing)} — run the isolate stage")

    def plate_for(sid: str) -> str:
        # The camera only ever zooms in (see `camera.zoom_floor`), so the plate is
        # exactly the page and there is no overscanned twin to keep in step.
        #
        # The path is module-relative because that is where `sync` puts it and
        # how the renderer resolves it. Written as `plates/s01.jpg` it resolved to
        # `/public/plates/s01.jpg`, 404'd, and `PaperStage` silently fell back to
        # the shared cream sheet — a whole module rendered without its page, with
        # every gate green, because the gate asked whether the file existed in
        # `build/` and it did.
        return f"{ctx.module}/plates/{sid}.jpg"

    return build_module(ctx.plan, layouts, narration, plate_for, fps=ctx.fps,
                        audio=f"audio/{ctx.module}.wav", prefix=f"{ctx.module}/")


def program(ctx: Context) -> list[Finding]:
    prog = program_of(ctx)
    out: list[Finding] = []
    narration = ctx.narration
    assert narration is not None

    for shot in prog.shots:
        sid = shot.id

        # 1. A card arrives on the word, not near it. `enter + travel` must equal
        #    the settle frame the plan declared, or the travel rule silently moved
        #    the landing.
        for card in shot.cards:
            if card.enter + card.travel != card.settle:
                out.append(fail("program", f"{sid}/{card.name}",
                                f"starts at f{card.enter} and travels {card.travel}, which lands "
                                f"at f{card.enter + card.travel}, not at its word (f{card.settle})"))
            if card.travel < 2:
                out.append(fail("program", f"{sid}/{card.name}",
                                f"travels {card.travel} frame(s) — that is a cut, not an arrival"))
            if card.travel > TRAVEL_MAX:
                out.append(fail("program", f"{sid}/{card.name}",
                                f"travels {card.travel} frames, past the calm maximum {TRAVEL_MAX}"))

        # 2. Puppet swaps are reads, not flicker.
        for card in shot.cards:
            for a, b in zip(card.poses, card.poses[1:]):
                if b.at - a.at < MIN_SWAP_GAP:
                    out.append(fail("program", f"{sid}/{card.name}",
                                    f"swaps poses {b.at - a.at} frames apart (f{a.at} → f{b.at}); "
                                    f"under {MIN_SWAP_GAP} the puppet vibrates instead of moving"))
            for p in card.poses:
                if not (0 <= p.at <= shot.span):
                    out.append(fail("program", f"{sid}/{card.name}",
                                    f"pose at f{p.at} is outside its own shot (0..{shot.span})"))

        # 3. Every camera key belongs to this shot, and the shot ends settled.
        if not shot.camera:
            out.append(fail("program", sid, "no camera keys — the frame never moves"))
            continue
        for k in shot.camera:
            if k.at < 0 or k.at > shot.span:
                out.append(fail("program", sid,
                                f"camera key at f{k.at} is outside the shot (0..{shot.span})"))
            if k.zoom > cam.ZOOM_CAP + 1e-6:
                out.append(fail("program", sid,
                                f"camera zooms to {k.zoom:.2f} at f{k.at}, past the cap "
                                f"{cam.ZOOM_CAP} — a real push turns the halftone to mush"))
            if k.zoom < 1.0 - 1e-6:
                out.append(fail("program", sid,
                                f"camera zooms to {k.zoom:.2f} at f{k.at}; below 1 the plate "
                                "has no overscan to give"))
        if shot.camera[-1].at > shot.span - 2:
            out.append(warn("program", sid,
                            f"the last camera key is at f{shot.camera[-1].at} of {shot.span} — "
                            "the shot ends while the frame is still travelling"))

        # 4. A figure the viewer reads as a number is never panned out of frame.
        #
        # Only when the frame could hold them. Three pieces spread across the
        # page, or one piece larger than the frame, cannot be framed together at
        # any zoom the camera is allowed to use — asking anyway produces findings
        # that describe the picture wrongly ("the camera cuts a figure") and
        # point the repair at the camera instead of at the composition. That case
        # is a fact about the shot worth knowing, so it is a note.
        span = cam.keep_interval(shot.keep, cam.MARGIN) if shot.keep else None
        oversized = [b for b in shot.keep
                     if b.w / 2 + cam.MARGIN > 0.5 or b.h / 2 + cam.MARGIN > 0.5]
        for box in oversized:
            out.append(note("program", sid,
                            f"a piece read as a number is {box.w:.2f}×{box.h:.2f} of the stage — "
                            "larger than the frame, so the edge trims it at every zoom. "
                            "No camera position can keep it whole."))
        if shot.keep and span is None and not oversized:
            out.append(note("program", sid,
                            f"{len(shot.keep)} piece(s) read as numbers cannot all be framed "
                            "at zoom ≥ 1 — no camera position holds them together"))
        for box in shot.keep:
            if span is None or box in oversized:
                continue
            for k in shot.camera:
                half = 0.5 / k.zoom
                if (abs(box.cx - k.x) + box.w / 2 > half + 1e-6
                        or abs(box.cy - k.y) + box.h / 2 > half + 1e-6):
                    out.append(fail("program", sid,
                                    f"at f{k.at} the camera ({k.x:.2f}, {k.y:.2f}, zoom "
                                    f"{k.zoom:.2f}) cuts a figure that is read as a number "
                                    f"({box}). A partial figure on screen is a wrong figure."))
                    break

    # 5. A hand-drawn mark is drawn ON its card, at the moment the card is the
    #    subject, and nothing is lying on top of it.
    #
    #    This is the rule that was missing, and it is the client's complaint in
    #    three measurements. An arrow "misses the word" when the card is half out
    #    of the frame while the pen is down, when the camera has already left for
    #    the next card, or when another piece has landed on top of the card being
    #    annotated. All three are invisible in a render and all three are
    #    arithmetic: the frame is `resolve(camera, frame)`, and a box is inside it
    #    or it is not.
    for shot in prog.shots:
        for i, mk in enumerate(shot.marks):
            target = shot.card(mk.on)
            if target is None:
                continue
            where = f"{shot.id} mark '{mk.shape}' on '{target.name}'"
            # Two strokes on two different cards, less than a camera move apart,
            # cannot both be framed: the frame would have to be in two places. The
            # earlier one owns the camera and the later one is exempt — the
            # alternative is a gate that demands the impossible and a plan that
            # can only satisfy it by deleting a gesture.
            crowded = any(prev.on != mk.on and mk.at - (prev.at + prev.duration) < 2 * MARK_LEAD
                          for prev in shot.marks[:i])
            for f in ((mk.at, mk.at + mk.duration) if not crowded else ()):
                if not cam.holds(cam.resolve(shot.camera, f), target.rect):
                    x, y, z = cam.resolve(shot.camera, f)
                    out.append(fail("program", where,
                                    f"the pen is down at f{f} but the frame ({x:.2f}, {y:.2f}, "
                                    f"zoom {z:.2f}) does not hold the card it is drawing on "
                                    f"({target.rect}). The stroke runs off the page and the eye "
                                    "reads a mark that missed."))
                    break
            # What matters is not how much of the card is hidden but how much of
            # the *stroke* lands on something else. An underline along the bottom
            # of a card whose top corner is tucked under a photo is collage; a
            # stroke that runs across the photo points at two things at once.
            mid = mk.at + mk.duration // 2
            above = [c for c in shot.cards
                     if c.name != target.name and c.z > target.z and c.settle <= mid]
            on_other = max(((mk.box.intersect(c.rect) / mk.box.area, c) for c in above),
                           default=(0.0, None), key=lambda t: t[0])
            # A warning, not a failure, and deliberately so. This is measured on
            # the mark's *box*, and a box is not a stroke: an underline lives in
            # the bottom eighth of its box, and an arrow is a thin diagonal
            # through it. A gate that failed a plan on a number it cannot measure
            # precisely would be accusing it of something it never checked — the
            # same fault as the board that drew every card 44 % too short.
            if on_other[0] > MARK_STRAY_WARN:
                frac, other = on_other
                out.append(warn("program", where,
                                f"{frac:.0%} of the mark's box sits on '{other.name}', which "
                                f"is lying over the card at f{mid}. The box is not the stroke, "
                                "so this is a look-at-it rather than a fault — but if the "
                                "gesture crosses that piece, it points at two things at once."))

    # 6. The module must not move uniformly. This is the check that would have
    #    caught the dead accent branch: every card travelling one value, every
    #    ease one value, in a module whose narration is full of stressed words.
    cards = sum(len(s.cards) for s in prog.shots)
    accented = [a for a in narration.accents if a.score >= FLOOR]
    travels = prog.travels()
    if cards >= 4 and accented:
        if len(travels) == 1:
            only = next(iter(travels))
            out.append(fail("program", ctx.module,
                            f"every one of {cards} cards travels {only} frames, though the "
                            f"narration has {len(accented)} accented words. Either the accent "
                            "lookup is not reaching the cards, or the plan's `word` fields do "
                            "not match what is spoken — both make the tempo uniform."))
    eases = prog.eases()
    if cards >= 4 and accented and eases == {"slow"}:
        out.append(fail("program", ctx.module,
                        "every camera key eases 'slow' in a module with accented words — "
                        "no move answers the voice"))

    if len(prog.shots) > 1 and len({c.from_side for s in prog.shots for c in s.cards}) == 1:
        out.append(warn("program", ctx.module,
                        "every card enters from the same side — the arrival reads as a pattern"))

    out.append(note("program", ctx.module,
                    f"{len(prog.shots)} shots, {cards} cards, travels {sorted(travels)}, "
                    f"eases {sorted(eases)}"))
    return out


def _inputs(ctx: Context):
    paths = [ctx.project.card_dir(ctx.module, s.id) / "layout.json" for s in ctx.plan.shots]
    if ctx.plan.path:
        paths.append(ctx.plan.path)
    return [p for p in paths if p.is_file()]


GATES = [
    Gate("program", program, _inputs, needs_assets=True,
         asks="the generated shot arrives on its words, moves variously, and keeps figures in frame"),
]
