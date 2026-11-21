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

from .. import ink, intent
from ..contract import TRAVEL_MAX, Finding, fail, note, warn
from ..emit import camera as cam
from ..emit.choreography import MARK_LEAD, MIN_SWAP_GAP, build_module
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

# What counts as a camera that moved. A shot must change the frame's size by
# `DEAD_ZOOM` or travel `DEAD_PAN` of the stage, unless it is too short or too
# empty for a move to mean anything.
DEAD_ZOOM = 0.05
DEAD_PAN = 0.08
DEAD_SHOT_FRAMES = 60
#: How long the page may go without anything touching it, in frames. Forty-five
#: frames is a second and a half — the point at which a viewer stops watching a
#: film and starts waiting for one. `presenter.GAP_FILL` is the same number from
#: the other side: the presenter fills what this rule refuses.
DEAD_AIR = 45
#: How much the frame must change across a second to count as moving.
DEAD_STILL = 0.010
#: How far the frame may drift while the pen is down, as a fraction of the page.
#: Not zero: a rounding step of 1e-4 per frame is 0.003 over a thirty-frame stroke
#: and is not a move. Above this, the card is sliding out from under the stroke.
PEN_STILL = 0.012


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


def _busy(shot, a: int, b: int) -> bool:
    """Is anything on the page moving between these two frames?

    A card in flight, a stroke being drawn, a word being written: any of these
    gives the eye something to follow, so a camera that holds still is a choice
    rather than a freeze. Nothing moving at all is dead air, and that is the
    fault the client named.
    """
    if any(c.enter <= b and c.settle >= a for c in shot.cards):
        return True
    if any(m.at <= b and m.at + m.duration >= a for m in shot.marks):
        return True
    return any(k.at <= b and k.at + k.duration >= a for k in shot.khats)


def _idle_gap(shot, a: int, b: int) -> tuple[int, int]:
    """The longest stretch inside `[a, b]` with nothing moving, and where.

    `_busy` answers "was anything happening *at all*", which is the wrong
    question once a hold gets long: one card landing at f190 excuses the 100
    frames after it. Measured across the film, that is what happened — every one
    of the 47 camera-static runs longer than `DEAD_AIR` came back "busy", and
    the rule's only remaining defence was a flat 2× cap, which failed all 47.

    The eye does not experience a hold as an average. It notices the *longest
    stretch where nothing happens*, and a hold is dead air when that stretch
    outlasts the same `DEAD_AIR` a moving camera gets. Measured this way the
    film's worst gap is 26 frames (0.87 s) — inside a 126-frame hold, which is
    not a freeze but a drawing.

    Only the *arrival* of a piece counts as an event. A card that has landed and
    is breathing is not doing anything the viewer can watch, and counting its
    breath as activity would make the rule vacuous.
    """
    busy: set[int] = set()
    for c in shot.cards:
        busy.update(range(max(a, c.enter), min(b, c.settle) + 1))
    for m in shot.marks:
        busy.update(range(max(a, m.at), min(b, m.at + m.duration) + 1))
    for k in shot.khats:
        busy.update(range(max(a, k.at), min(b, k.at + k.duration) + 1))
    best = run = 0
    best_at = a
    for f in range(a, b + 1):
        run = 0 if f in busy else run + 1
        if run > best:
            best, best_at = run, f - run + 1
    return best, best_at


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

        # 4. A figure the viewer reads as a number is never *half* on screen.
        #
        # The distinction matters, and getting it wrong flattened the camera. A
        # piece that is entirely off screen cannot be misread; a piece that is
        # half off screen shows `8.848` as `0.848` at the moment the voice says
        # the right number. Demanding every figure be *whole* at every key — which
        # is what this rule used to do — meant any shot with a figure near the
        # page edge could only ever sit at zoom 1.0, the widest legal framing, and
        # so had no camera move left to make. Half the film's keys were at 1.000
        # for exactly this reason.
        #
        # Only when the frame could hold them at all. Three pieces spread across
        # the page, or one piece larger than the frame, cannot be framed together
        # at any zoom the camera is allowed to use — asking anyway produces
        # findings that describe the picture wrongly and point the repair at the
        # camera instead of at the composition. That case is a note.
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
            if box in oversized or span is None:
                # `span is None` is the note above: no position holds them all, so
                # failing the camera for not achieving it would be accusing it of
                # something the page makes impossible.
                continue
            for k in shot.camera:
                if cam.clipped((k.x, k.y, k.zoom), box):
                    out.append(fail("program", sid,
                                    f"at f{k.at} the camera ({k.x:.2f}, {k.y:.2f}, zoom "
                                    f"{k.zoom:.2f}) shows part of a figure that is read as a "
                                    f"number ({box}). A partial figure on screen is a wrong "
                                    "figure: either hold it whole or take it off the page."))
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
            # A piece that fills the page cannot be held by a tighter frame, and it
            # does not need to be: the stroke is drawn inside it, so wherever the
            # camera is, the stroke is on the card. Demanding the impossible here
            # is what forced the camera back to zoom 1.000 on every shot with a
            # full-height cut-out — a rule that can only be satisfied by deleting
            # the move.
            crowded = crowded or not cam.frameable(target.rect)
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
        # A hit is not the only way the camera can answer a word — **the pen can.**
        # When a module's strongest cards are the ones a hand is drawing on, the
        # camera holds still *because* the film is answering: a push while a pen
        # underlines the same word is two gestures pointing at one thing, and
        # `intent.settle_moves` demotes the hit for exactly that reason. So the
        # question is not "did a key speed up", it is "was the accent answered at
        # all", and a stroke on a stressed card is an answer.
        words = {c.name: c.word for shot in prog.shots
                 for c in (ctx.plan.shot(shot.id).cards if ctx.plan.shot(shot.id) else ())}
        stress = intent.stress_line([
            narration.score(shot.start + c.settle, words.get(c.name, ""))
            for shot in prog.shots for c in shot.cards
        ])
        strong = [c for shot in prog.shots for c in shot.cards
                  if narration.score(shot.start + c.settle,
                                     words.get(c.name, "")) >= stress]
        marked = {mk.on for shot in prog.shots for mk in shot.marks if mk.on}
        if strong and any(c.name in marked for c in strong):
            out.append(note("program", ctx.module,
                            "no camera hit: the cards above the module's emphasis "
                            f"line ({stress:.2f}) are the ones the pen draws on — the "
                            "pen answers the voice here, and the frame holds still for it"))
        else:
            out.append(fail("program", ctx.module,
                            "every camera key eases 'slow' in a module with accented "
                            "words — no move answers the voice"))

    if len(prog.shots) > 1 and len({c.from_side for s in prog.shots for c in s.cards}) == 1:
        out.append(warn("program", ctx.module,
                        "every card enters from the same side — the arrival reads as a pattern"))

    # 7. A shot is not a still. The camera has to go somewhere.
    #
    # This is the rule the client asked for by asking why there was no zoom, pan
    # or pull-out any more. There was no fault to point at: every key was legal,
    # every mark was framed, every figure was whole — and the module sat at zoom
    # 1.000 for half its keys, because 1.0 is the widest legal framing and nothing
    # asked the camera to be anywhere else. A camera that never moves is not a
    # camera, and "it looks flat" is not a review note anyone can act on.
    #
    # So the move is measured, per shot: either the frame changes size by 5 % or it
    # travels 8 % of the stage. A shot shorter than two seconds, or with one piece
    # in it, is allowed to sit still — there is nothing there to move between.
    for shot in prog.shots:
        if shot.span < DEAD_SHOT_FRAMES or len(shot.cards) < 2:
            continue
        xs = [k.x for k in shot.camera]
        ys = [k.y for k in shot.camera]
        zs = [k.zoom for k in shot.camera]
        travel = max(max(xs) - min(xs), max(ys) - min(ys))
        if max(zs) - min(zs) >= DEAD_ZOOM or travel >= DEAD_PAN:
            continue
        message = (f"the camera does not move: zoom stays inside "
                   f"{min(zs):.2f}..{max(zs):.2f} and it travels {travel:.2f} of the "
                   f"stage across {shot.span} frames.")
        if shot.keep:
            # A figure near the page edge pins the framing: the camera cannot go
            # closer without leaving part of a printed number on screen, and it
            # cannot go wider than 1.0 because the plate has no overscan. That is
            # a fact about the composition, not a fault in the move, so it is
            # reported with its cause instead of failing.
            out.append(warn("program", shot.id,
                            message + " The shot carries printed figures, and a framing "
                            "that holds them all is the only one the page allows — so the "
                            "cause is where the figures were placed, not the camera."))
        else:
            out.append(fail("program", shot.id,
                            message + " Nothing in this shot needs to be held whole, so "
                            "there is no reason for it to sit still."))

    # 8. The renderer must not be able to correct the camera.
    #
    # `PaperStage` raises the zoom of a full-bleed plate so the paper never leaves
    # the frame. That net used a stricter formula than this module's, so it fired
    # on every panned key and added an unrequested push of four to eight per cent
    # — cancelling exactly the pull-out a pan was travelling toward. The render
    # then disagreed with every gate, and every gate said the move was right.
    #
    # The net is now the same arithmetic. This rule keeps it that way: a key that
    # does not clear the floor is a key the renderer will silently rewrite, so it
    # is refused here instead.
    for shot in prog.shots:
        for k in shot.camera:
            floor = cam.zoom_floor(k.x, k.y, cam.MARGIN)
            if k.zoom < floor - 1e-6:
                out.append(fail("program", shot.id,
                                f"at f{k.at} the camera (x {k.x:.2f}, y {k.y:.2f}) needs "
                                f"zoom {floor:.3f} to keep the paper in frame, but the key "
                                f"asks for {k.zoom:.3f}. The renderer would raise it, so the "
                                "frame on screen would not be the frame that was checked."))
                break

    # 9. The page must not go quiet while the voice keeps talking.
    #
    # The client's note on m03 at 0:41–0:44 — *"di dalam 3 detik itu tidak ada
    # layer card yang masuk, penonton dibiarkan bengong"* — described a fault that
    # every gate in this file called legal. Nothing was wrong: the cards were
    # placed, the marks were timed, the camera moved. The page had simply stopped
    # talking, and "nothing arrives" was a warning in the plan gate that 22
    # modules passed straight through.
    #
    # So it is a failure now, and it is measured where the answer lives: a shot
    # may not run `DEAD_AIR` frames without *something* touching the page — a card
    # settling, a pen landing, a note being written. A camera move does not count;
    # a camera that drifts across a still page is the very thing that reads as
    # dead air.
    for shot in prog.shots:
        # A stroke is not an instant: while the pen is down the page is talking,
        # even though nothing new arrives. So both ends of every stroke count.
        events = sorted({c.settle for c in shot.cards}
                        | {f for m in shot.marks for f in (m.at, m.at + m.duration)}
                        | {f for k in shot.khats for f in (k.at, k.at + k.duration)})
        edges = [0] + events + [shot.span]
        for a, b in zip(edges, edges[1:]):
            if b - a <= DEAD_AIR:
                continue
            quiet = f"{b - a} frames ({(b - a) / prog.fps:.1f}s)"
            # A hold is not the same thing as a dead page. If the frame is
            # travelling while nothing arrives — a slow push into a photograph, a
            # pan across a strip — the viewer is being shown something. Only a
            # page that is still *and* still framed is the fault the client
            # described, and only that is a failure.
            x0, y0, z0 = cam.resolve(shot.camera, a)
            x1, y1, z1 = cam.resolve(shot.camera, min(b, shot.span))
            travel = max(abs(x1 - x0), abs(y1 - y0))
            if abs(z1 - z0) >= DEAD_ZOOM or travel >= DEAD_PAN:
                out.append(warn("program", shot.id,
                                f"{quiet} pass with nothing arriving between f{a} and "
                                f"f{b}, though the camera does travel — the page is "
                                "held, not empty."))
                continue
            soon = min((k.at for k in shot.khats if k.at > a), default=None)
            if soon is not None:
                # A note is coming, but not soon enough: the gap is still open
                # until the pen touches down.
                out.append(fail("program", shot.id,
                                f"{quiet} pass before the note at f{soon}, on a frame "
                                "that is not moving either — the silence is not "
                                "filled, it is postponed."))
            else:
                out.append(fail("program", shot.id,
                                f"{quiet} with nothing arriving and no camera move "
                                f"between f{a} and f{b}. The presenter may answer "
                                "silence with a handwritten note, a stroke, or a piece "
                                "that moves — but not with nothing."))

    # 10. A hold is a creep, not a freeze.
    #
    # Rule 7 asks whether the shot moves at all, and m03 passed it while sitting
    # perfectly still on 43 % of its frames: it moved *somewhere*. The client
    # watched the film, not the rule, and said "kameranya masih gak bergerak".
    #
    # Measured over a window, not frame by frame. A frame-by-frame test is wrong
    # for the same reason a still photograph of a pan is wrong: an ease-in-out
    # curve is almost flat at both ends, so the first ten frames of a real move
    # look identical and a real 17 % pan was reported as a freeze. What the eye
    # judges is "has this changed in the last second", so that is what is checked.
    window = min(30, max(8, DEAD_AIR))
    for shot in prog.shots:
        if shot.span < DEAD_AIR:
            continue
        frames = [cam.resolve(shot.camera, f) for f in range(shot.span)]
        worst, worst_at = 0, 0
        for f in range(0, len(frames) - window):
            base = frames[f]
            # The *excursion*, not the difference between the ends. A frame that
            # dips two per cent and comes back has moved, and measuring only its
            # endpoints calls that a freeze — which is how a real creep was
            # reported as a still frame and the rule kept failing on a shot that
            # was breathing.
            far = max((abs(c[2] - base[2]), max(abs(c[0] - base[0]), abs(c[1] - base[1])))
                      for c in frames[f:f + window + 1])
            if far[0] >= DEAD_STILL or far[1] >= DEAD_STILL:
                continue
            run = window
            while f + run < len(frames):
                c = frames[f + run]
                if abs(c[2] - base[2]) >= DEAD_STILL or max(abs(c[0] - base[0]),
                                                            abs(c[1] - base[1])) >= DEAD_STILL:
                    break
                run += 1
            if run > worst:
                worst, worst_at = run, f
        if worst < DEAD_AIR:
            continue
        # A still camera is only a fault when the *viewer has nothing to watch*.
        #
        # m13 s07 held one framing for 48 frames while a card flew in and two
        # strokes were drawn across it. The frame did not change and the page was
        # never still — that is a deliberate hold, and failing it teaches the
        # generator to keep the camera busy during a close reading, which is
        # worse. The rule the client actually stated was about dead air: "di situ
        # diem, ga ada layer card yg masuk" — nothing happening.
        #
        # So the hold is judged by its *worst gap*, not by its length. A 126-frame
        # hold with a card landing at one end and a stroke at the other is a
        # drawing; a 47-frame hold with nothing in it is a photograph of a film.
        # Length alone cannot tell those apart, and an average certainly cannot.
        gap, gap_at = _idle_gap(shot, worst_at, worst_at + worst)
        if gap < DEAD_AIR:
            continue
        out.append(fail("program", shot.id,
                        f"nothing happens on the page for {gap} frames "
                        f"({gap / prog.fps:.1f}s) from f{gap_at}, inside a "
                        f"{worst}-frame camera hold — a hold has to creep, or the "
                        "viewer is watching a photograph of a film."))

    # 11. No wild movement: every move has a stated reason, and the frame is
    #     *still* while the pen is down.
    #
    # The client's words: "ga ada gerak liar, yg ada gerak kamera terukur yg
    # sengaja dengan tujuan presentasi dan fokus penonton". Two separate faults
    # hide under "the camera feels busy", and they need two separate rules:
    #
    #   (a) a key with no reason is a move nobody asked for — some pass wanted the
    #       frame somewhere and the film did not want the viewer to look at
    #       anything. `camera.REASONS` is the closed vocabulary; a key outside it
    #       is decoration.
    #   (b) during a stroke, "slow" is not "still". v2 said it plainly — "ada baris
    #       yang harus dibaca → berhenti bergerak" — and v3's `creep` put a breath
    #       into every hold, so 92 % of the scored words were spoken over a moving
    #       frame. The pen tells the viewer where to look; if the frame drifts
    #       under it, the two instructions disagree.
    for shot in prog.shots:
        for k in shot.camera:
            if not k.reason:
                out.append(fail("program", f"{shot.id} f{k.at}",
                                "is a camera key with no reason — a move nobody asked "
                                f"for. Name one of {', '.join(cam.REASONS)}, or drop "
                                "the key."))
            elif k.reason not in cam.REASONS:
                out.append(fail("program", f"{shot.id} f{k.at}",
                                f"moves for '{k.reason}', which is not a reason the "
                                f"film recognises ({', '.join(cam.REASONS)})"))
        for mk in shot.marks:
            lo, hi = mk.at, min(shot.span - 1, mk.at + mk.duration)
            if hi - lo < 3:
                continue
            base = cam.resolve(shot.camera, lo)
            drift = max(
                (max(abs(c[0] - base[0]), abs(c[1] - base[1])) for c in
                 (cam.resolve(shot.camera, f) for f in range(lo, hi + 1))),
                default=0.0,
            )
            if drift > PEN_STILL:
                out.append(fail("program", f"{shot.id} {mk.shape}@f{mk.at}",
                                f"the pen is down for {hi - lo} frames and the frame "
                                f"travels {drift:.3f} of the page under it. A stroke is "
                                "read on a still frame; `creep` must not breathe "
                                "through a pen window."))

    # 12. The presenter chooses a vehicle, and the choice is a choice.
    #
    # The client, in full: *"marker intent sebagai seorang grafik presentasi juga
    # harus kreatif memilih animation, contohnya write text yg kaku dan kecil itu
    # kadang harus di rubah misal dengan stamp style dan variasi lain"*. Three
    # things can go wrong with that instruction, and each has its own failure:
    #
    #   (a) a note is *written* when the hand has no time to write it. That is a
    #       smear with the right length, and it is the fault the note names.
    #   (b) a shot carries more than one emphasis. v2's rule — "kuning = penekanan
    #       utama, satu per shot" — was never enforced here, so a shot with four
    #       equally loud marks has no emphasis at all.
    #   (c) every note in a module arrives by the same vehicle. That is the
    #       monotony the note is asking to avoid, and it cannot be caught by
    #       looking at one note — it is only visible across the module.
    notes = [k for s in prog.shots for k in s.khats]
    for shot in prog.shots:
        for k in shot.khats:
            if k.mode != "write":
                continue
            if not ink.can_write(k.text, k.duration):
                n = max(1, ink.letters(k.text))
                out.append(fail("program", f"{shot.id} note {k.text!r}",
                                f"is written in {k.duration} frames — {k.duration / n:.1f} "
                                f"per letter, and a hand needs {ink.WRITE_FPL:.0f}. The "
                                "pen cannot form the letters in that time; press it on "
                                "instead, or give the note more frames."))
        loud = [m for m in shot.marks if m.color in ("yellow", "amber")]
        if len(loud) > 1:
            out.append(fail("program", f"{shot.id}",
                            f"has {len(loud)} emphatic marks ({', '.join(m.shape for m in loud)}) "
                            "— one per shot, or none of them is the emphasis."))
    if len(notes) >= 4:
        modes = {k.mode for k in notes}
        if modes == {"write"}:
            out.append(fail("program", ctx.module,
                            f"all {len(notes)} notes are written by hand — the presenter "
                            "chose one vehicle for the whole module, which is the same as "
                            "choosing none. `ink.register` answers per note, and one of "
                            "these is a word a stamp would serve better."))
        elif modes == {"stamp"}:
            # Not a fault. A page of stamps is a graphic language, the way a
            # filing clerk's is; the fault this rule exists for is the opposite
            # one — writing things that are too small and too stiff to write.
            out.append(warn("program", ctx.module,
                            f"all {len(notes)} notes are stamped — coherent, but worth a "
                            "look: is one of them a word the voice is dwelling on, where "
                            "the act of writing is the thing to watch?"))
    # 13. A camera move that was decided is a camera move that happens.
    #
    # `voxkit.intent` decides `move` for every beat before any key exists. This
    # rule closes the loop: if the presenter said "punch on this word", there has
    # to be a hit at that frame. Without it a decision can be made, recorded, and
    # then quietly dropped by a later pass — which is exactly the history of this
    # system. The camera used to carry a `reason` on every key that had been
    # attached *after* the move was computed, so it looked directed while nothing
    # had directed it.
    for shot in prog.shots:
        for card in shot.cards:
            if card.move != "punch":
                continue
            if not any(k.hit and abs(k.at - card.settle) <= 26 for k in shot.camera):
                out.append(fail("program", f"{shot.id}/{card.name}@f{card.settle}",
                                "lands on a stressed word and was decided to be a punch, "
                                "and there is no camera hit there. A decided move that "
                                "nothing executes is worse than no decision: the film "
                                "reads flat and the plan says it is emphatic."))

    out.append(note("program", ctx.module,
                    f"{len(notes)} notes: "
                    + ", ".join(f"{m} {n}" for m, n in sorted(
                        {x: sum(1 for k in notes if k.mode == x) for x in
                         {k.mode for k in notes}}.items()))))

    out.append(note("program", ctx.module,
                    f"{len(prog.shots)} shots, {cards} cards, travels {sorted(travels)}, "
                    f"eases {sorted(eases)}, reasons "
                    f"{sorted({k.reason for s in prog.shots for k in s.camera if k.reason})}"))
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
