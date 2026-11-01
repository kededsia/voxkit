"""Plan gates: everything that can be known before an image is paid for.

These run on the plan alone. That ordering is the whole economy of the pipeline:
a card costs a generation, a still costs a generation, a puppet frame costs a
generation, and a re-render costs minutes. A plan fault caught here costs
nothing, and a plan fault that reaches the executor costs everything downstream
while the executor faithfully reproduces it.

Every gate below corresponds to a fault that actually shipped:

    schema    a `wujud` the aspect table did not know, so every overlap it took
              part in was measured against a guessed height
    context   a plan with no record of what it was written against
    ranges    a shot that lost or duplicated time
    arrival   a card that settles on a different word than the one it names
    marks     a mark drawn on blank paper, before its card had begun to arrive
    readable  a printed card under a figure — `CAHAYA HIT` read as a typo
    compose   a slip 100 % buried, and a card whose bottom edge left the page
    data      a figure on a card the narration never says
    spell     `CAHI` printed for `cai`, drawn faithfully by the model
"""
from __future__ import annotations

import re

from ..contract import (
    ARRIVE_EARLY, ARRIVE_LATE, JENIS, MIN_ARRIVAL_GAP, WUJUD,
    Finding, Plan, fail, is_placeholder, note, tile, warn, words_in,
)
from ..language import get as language
from ..style import COLORS, MIRROR, MOTIONS, PENS, shapes
from ..words import FLOOR
from .base import Context, Gate, Skipped

# How late a bound mark may start after the card it points at has landed.
#
# The pen is annotating the word the voice just said, so it belongs on the beat,
# not after it. 8 frames is a quarter of a second — a beat, not a pause. Past
# that the audience has already been carried to the next thing and the gesture
# reads as a stray line that happens to be near the card. Measured over the film
# the authored frames ran up to 240, and every one of the 74 late marks was late
# because the number had drifted from the card, not because anyone wanted a pause.
MARK_DELAY_MAX = 8


# ------------------------------------------------------------------ helpers
def _needs_narration(ctx: Context):
    if ctx.narration is None or not ctx.narration.accents:
        raise Skipped("no scored narration — run `vox words <module>` after transcribing")
    return ctx.narration


def _plan_inputs(ctx: Context):
    paths = [ctx.plan.path] if ctx.plan.path else []
    if ctx.project.transcript(ctx.module).is_file():
        paths.append(ctx.project.transcript(ctx.module))
    return [p for p in paths if p]


def _printed(card) -> list[str]:
    """Text a viewer will read on this card: its headline and anything quoted in
    the prompt. An apostrophe inside a word is not a quote delimiter — reading
    `Bandung's` as an opening quote accused a plan of printing eight words it
    never printed.

    De-duplicated, because a headline that also appears quoted in the prompt is
    one thing printed once, and reporting it twice makes a single fault look like
    two.
    """
    out = [card.semantik] if card.semantik else []
    if card.what:
        clean = re.sub(r"(?<=[A-Za-z])'(?=[A-Za-z])", "", card.what)
        out.extend(re.findall(r"'([^']{2,80})'", clean))
    return list(dict.fromkeys(out))


def _phrases(narration) -> list[str]:
    """The narration split where the speaker paused.

    A figure is spoken as a phrase, not as a word: `enam puluh` is 60, and neither
    `enam` nor `puluh` is. Scoring word by word reported every honest number in
    the film as invented — and a checker that fails the right answer is worse
    than none. Splitting at the pauses keeps `seribu` from one sentence gluing to
    `ratus` from the next.
    """
    out, current = [], []
    for acc in narration.accents:
        if acc.gap > 0.30 and current:
            out.append(" ".join(current))
            current = []
        current.append(acc.word.text)
    if current:
        out.append(" ".join(current))
    return out


# ------------------------------------------------------------------- schema
def schema(ctx: Context) -> list[Finding]:
    plan = ctx.plan
    out = list(plan.load_problems())

    if not plan.module:
        out.append(fail("schema", "-", "the plan has no module id"))
    if plan.plan_version < 2:
        out.append(fail("schema", plan.module,
                        f"plan_version {plan.plan_version} — this engine reads version 2 or later"))
    if not plan.shots:
        out.append(fail("schema", plan.module, "the plan has no shots"))

    for shot in plan.shots:
        sid = shot.id
        for field, minimum in (("babak", 2), ("peran_retoris", 2), ("kamera", 6),
                               ("latar_plate", 8), ("tata_letak_kolase", 8)):
            value = getattr(shot, field)
            if is_placeholder(value):
                out.append(fail("schema", sid, f"{field} is empty or a placeholder"))
            elif words_in(value) < minimum:
                out.append(fail("schema", sid,
                                f"{field} has {words_in(value)} word(s), needs {minimum}: "
                                f"'{value[:60]}'"))
        if shot.jenis not in JENIS:
            out.append(fail("schema", sid,
                            f"jenis '{shot.jenis}' is not one of {', '.join(sorted(JENIS))}"))
        if is_placeholder(shot.mark):
            out.append(fail("schema", sid,
                            "`mark` is empty — the sentence the hand-draws come from is missing"))

        if len(shot.cards) < 2:
            out.append(fail("schema", sid,
                            f"{len(shot.cards)} card(s) — a shot needs at least 2, "
                            "otherwise it is a still with a camera move"))
        names = set()
        for card in shot.cards:
            where = f"{sid}/{card.name}"
            if card.name in names:
                out.append(fail("schema", where, "two cards share this name"))
            names.add(card.name)
            if card.z < 1 or card.z > 20:
                out.append(fail("schema", where, f"z is {card.z}, outside 1..20"))
            for field in ("semantik", "semiotik", "what", "word"):
                if is_placeholder(getattr(card, field)):
                    out.append(fail("schema", where, f"{field} is empty or a placeholder"))
            if card.lands < 0 or card.lands > shot.span:
                out.append(fail("schema", where,
                                f"lands f{card.lands} is outside its own shot (0..{shot.span}). "
                                "`lands` is relative to the shot's start, not to the film"))
            if card.placement.w < 0.02:
                out.append(fail("schema", where,
                                f"width {card.placement.w:.3f} of the frame is too small to read"))
            if card.tertutup_boleh and not card.tertutup_alasan.strip():
                out.append(fail("schema", where,
                                "declares `tertutup_boleh` without `tertutup_alasan` — "
                                "an exemption with no reason is an exemption nobody can review"))
            if card.angka_bahan and not card.angka_alasan.strip():
                out.append(fail("schema", where,
                                "declares `angka_bahan` without `angka_alasan` — "
                                "an exemption with no reason is an exemption nobody can review"))
    return out


def context_gate(ctx: Context) -> list[Finding]:
    """The plan has to say what it was written against.

    Not bureaucracy: without it there is no way to tell a plan written from the
    laws and the facts from one written from memory, and the second kind is the
    kind that prints `CAHI`."""
    ctx_data = ctx.plan.context or {}
    out = []
    for field in ("skills_read", "benang_read", "laws"):
        value = ctx_data.get(field)
        if not value:
            out.append(fail("context", ctx.plan.module,
                            f"context.{field} is empty — the plan must say what it was written against"))
    return out


# ------------------------------------------------------------------- ranges
def ranges(ctx: Context) -> list[Finding]:
    duration = 0
    if ctx.narration is not None and ctx.narration.accents:
        duration = ctx.narration.total_frames
    out = tile(ctx.plan.shots, duration)
    for shot in ctx.plan.shots:
        if shot.span <= 0:
            out.append(fail("ranges", shot.id, f"range {shot.start}..{shot.end} is empty or reversed"))
    return out


# ------------------------------------------------------------------ arrival
def arrival(ctx: Context) -> list[Finding]:
    """A card settles on the word that names it.

    The window is measured, not chosen: across 39 cards the tight ones land at
    +1 and the loose ones at +8, so −6…+9 is what a thrown card can actually do.
    Two cards inside three frames read as one arrival, which is the wall a
    viewer reads as a slideshow.
    """
    narration = _needs_narration(ctx)
    out: list[Finding] = []
    for shot in ctx.plan.shots:
        arrivals = sorted(shot.arrivals(), key=lambda t: t[1])
        for i, (card, abs_frame) in enumerate(arrivals):
            if not card.word:
                continue
            if not narration.has_word(card.word):
                out.append(fail("arrival", f"{shot.id}/{card.name}",
                                f"lands on the word '{card.word}', which the narration never says"))
                continue
            onsets = [a for a in narration.accents if a.word.key == card.word.lower()
                      or a.word.key == re.sub(r"[^\w]", "", card.word).lower()]
            if not onsets:
                continue
            onset = min(onsets, key=lambda a: abs(a.word.start_frame - abs_frame)).word.start_frame
            delta = abs_frame - onset
            if delta < ARRIVE_EARLY or delta > ARRIVE_LATE:
                out.append(fail("arrival", f"{shot.id}/{card.name}",
                                f"settles at f{abs_frame} but '{card.word}' is spoken at f{onset} "
                                f"({delta:+d} frames, window {ARRIVE_EARLY:+d}..{ARRIVE_LATE:+d})"))
            if i and abs_frame - arrivals[i - 1][1] < MIN_ARRIVAL_GAP:
                out.append(fail("arrival", f"{shot.id}/{card.name}",
                                f"settles at f{abs_frame}, {abs_frame - arrivals[i - 1][1]} frame(s) "
                                f"after '{arrivals[i - 1][0].name}' — two cards that close read as one"))
        # The silence check that used to live here is gone on purpose. It warned
        # about gaps between arrivals, and it warned on six of m03's eight shots
        # while the film shipped — because a warning is not a check. The presenter
        # answers silence with a note, and only the program knows whether it did,
        # so the check now lives in `gates/program.py` rule 9 and it fails.
    return out


# -------------------------------------------------------------------- marks
def marks(ctx: Context) -> list[Finding]:
    vocab = shapes(ctx.project.p("remotion"))
    out: list[Finding] = []
    for shot in ctx.plan.shots:
        sid = shot.id
        if not shot.marks:
            out.append(fail("marks", sid,
                            "no marks — the gesture has to be declared, not implied"))
            continue
        names = {c.name for c in shot.cards}
        lands = {c.name: c.lands for c in shot.cards}
        fired: dict[tuple[str, int], str] = {}

        for i, m in enumerate(shot.marks):
            where = f"{sid} marks[{i}] '{m.shape}'"
            if m.shape not in vocab:
                out.append(fail("marks", where,
                                f"'{m.shape}' is not in the renderer's vocabulary "
                                f"({', '.join(sorted(vocab)[:6])}…)"))
            if not 4 <= m.duration <= 60:
                out.append(fail("marks", where,
                                f"duration {m.duration} is outside 4..60 frames"))
            if m.card not in names:
                out.append(fail("marks", where,
                                f"points at '{m.card}', which this shot does not have"))
                continue
            if m.pen not in PENS:
                out.append(fail("marks", where, f"pen '{m.pen}' is not one of {sorted(PENS)}"))
            if m.motion not in MOTIONS:
                out.append(fail("marks", where, f"motion '{m.motion}' is not one of {sorted(MOTIONS)}"))
            if m.color and m.color not in COLORS:
                out.append(fail("marks", where, f"color '{m.color}' is not one of {sorted(COLORS)}"))

            if m.box is None:
                # A bound mark is timed by the card it points at, and only by it.
                #
                # This is the rule that was missing, and it is the whole reason
                # hand-drawn arrows and strokes in this film landed on the wrong
                # thing. `at` was an absolute frame typed into the plan, nothing
                # compared it with the card's own arrival, and it drifted: over
                # the film 74 % of marks fired while the camera was on a
                # different card, 36 % fired more than ten frames after their
                # card had landed, and the worst fired 240 frames — eight
                # seconds — late. The gesture, the box and the pen were all
                # correct; only the moment was wrong, and no gate was asking
                # about the moment.
                if m.at is not None:
                    out.append(fail("marks", where,
                                    f"carries an absolute `at` (f{m.at}) but is bound to "
                                    f"'{m.card}'. A bound mark is timed by its card: write "
                                    f"`delay` (frames after the card lands) instead — an "
                                    "absolute frame drifts away from the card it describes"))
                d = m.delay if m.delay is not None else 0
                if not 0 <= d <= MARK_DELAY_MAX:
                    out.append(fail("marks", where,
                                    f"delay {d} is outside 0..{MARK_DELAY_MAX} — the pen "
                                    f"would touch the paper {d} frames after '{m.card}' "
                                    f"lands, and by then the voice has moved on"))
                end = lands[m.card] + d + m.duration
                if end > shot.span:
                    out.append(fail("marks", where,
                                    f"starts {d} frames after '{m.card}' lands and runs "
                                    f"{m.duration} frames, so it ends at f{end} but the shot "
                                    f"ends at f{shot.span}"))
                # Two *different* gestures on one card are two jobs — a circle on
                # the number and an underline under the label is what annotation
                # looks like. Two of the same shape, at the same moment, on the
                # same card is one gesture printed twice.
                key = (m.card, m.shape, d)
                if key in fired:
                    out.append(fail("marks", where,
                                    f"and marks[{fired[key]}] both draw a '{m.shape}' on "
                                    f"'{m.card}' {d} frames after it lands — one gesture "
                                    "drawn twice"))
                else:
                    fired[key] = str(i)
            elif m.at is not None:
                # A page mark is not about one card, so it keeps its own frame —
                # but it still has to be inside the shot it is drawn in.
                if m.at > shot.span:
                    out.append(fail("marks", where,
                                    f"fires at f{m.at}, past the end of its own shot (f{shot.span})"))
                key = ("", m.shape, m.at)
                if key in fired:
                    out.append(fail("marks", where,
                                    f"and marks[{fired[key]}] both fire on the page at "
                                    f"f{m.at} — one gesture drawn twice"))
                else:
                    fired[key] = str(i)
            if m.box is not None and not (m.box[0] < m.box[2] and m.box[1] < m.box[3]):
                out.append(fail("marks", where, f"box {m.box} is degenerate"))

        # Page marks with the same shape and duration are one gesture printed
        # twice; six labels each getting their own underline is six jobs.
        #
        # This read `m.bound`, which is the *opposite* set: a mark bound to a card
        # is one job on one card, and six of them on six cards are six jobs. The
        # rule only has anything to say about marks drawn on the page itself,
        # which have no card to be one job on.
        page = [m for m in shot.marks if not m.bound]
        for i, a in enumerate(page):
            for b in page[i + 1:]:
                if a.shape == b.shape and a.duration == b.duration:
                    out.append(fail("marks", sid,
                                    f"two page marks '{a.shape}' with the same duration "
                                    f"{a.duration} — one gesture printed twice"))
        for left, right in MIRROR.items():
            if left in {m.shape for m in shot.marks} and right in {m.shape for m in shot.marks}:
                out.append(fail("marks", sid,
                                f"'{left}' and '{right}' in one shot — a mirrored pair at two "
                                "edges is the arrangement a viewer reads as symmetrical"))
        # Equal magnitudes with alternating signs is a pattern even when every
        # mark is bound to its own card: six underlines at ±0.7 is a lattice.
        for shape in {m.shape for m in shot.marks}:
            mags = [abs(m.rotate) for m in shot.marks if m.shape == shape]
            if len(mags) >= 3 and max(mags) - min(mags) < 0.05:
                out.append(fail("marks", sid,
                                f"{len(mags)} '{shape}' marks all at the same angle magnitude "
                                f"({mags[0]:.2f}) — an even lattice reads as a machine"))
    return out


# ----------------------------------------------------------------- readable
def _is_person(card) -> bool:
    """Is this cut-out a person? The same test `voxkit/figure.py` uses.

    Imported lazily because `figure` reads card PNGs and this module is a free gate.
    """
    from ..figure import is_person
    return is_person(card)


def readable(ctx: Context) -> list[Finding]:
    """R6: a printed card sits above everything that can lie on top of it.

    Blunt on purpose. The camera moves layers by different amounts, so two pieces
    side by side in the still travel differently and by frame 300 a figure can be
    lying across a slip it never touched in the picture. A plan that means to
    tuck a slip under a photograph says so with `tertutup_boleh` and says why.

    The vocabulary is the fix for a hole: `peta` (a printed map, full of place
    names) and `benda` were in neither list, so thirty-one readable cards in the
    old module set were exempt from the rule that exists to keep words legible.
    """
    out: list[Finding] = []
    for shot in ctx.plan.shots:
        for card in shot.cards:
            if not card.readable or card.tertutup_boleh:
                continue
            for other in shot.cards:
                if other is card or not other.covering:
                    continue
                if _is_person(other) and card.bahan in ("cetak", "koran"):
                    # R6's own exemption, narrowed to the one pair it is honest
                    # about: a *slip* under a *person*. A slip has a headline and a
                    # wide blank margin, so a silhouette standing on the margin is
                    # collage — and `figure` measures that margin with the card's
                    # own ink instead of this gate guessing from the plan.
                    #
                    # A `peta` is not a slip: it is place names edge to edge, and a
                    # figure standing anywhere on it buries words. That stays a
                    # failure here, which is why `peta` is in the vocabulary at all.
                    continue
                if other.z >= card.z:
                    out.append(fail("readable", f"{shot.id}/{card.name}",
                                    f"is the card that gets read and its z ({card.z}) is not above "
                                    f"'{other.name}' ({other.z}, {other.bahan}). The camera moves "
                                    "the layers by different amounts, so a figure that only touches "
                                    "it in the still will lie across the words by the end of the "
                                    "shot. Raise it, or declare `tertutup_boleh` and why."))
    return out


# ------------------------------------------------------------------ compose
def compose(ctx: Context) -> list[Finding]:
    """Where the pieces actually sit: on the page, and not on top of each other.

    Measured with one geometry module and the correct aspect conversion. The
    board that used to answer this omitted the stage ratio, so every card was
    drawn 44 % too short and a pair 63 % buried was reported as 34 % — under its
    own warning threshold.

    A piece sits where it was *measured*, not where the plan's prose asked for
    it: the still is drawn from that prose and then the piece is cut out of the
    still, so the model's own placement wins and the prose is only an
    instruction. Reading the prose here measured a pair as 91 % buried when the
    measured slots overlapped by 8 % — a finding about the plan's sentence, not
    about the picture. Where no layout exists yet the prose is all there is, so
    that is what is used, and it is used knowingly.
    """
    from ..geometry import Placed, buried
    from ..layout import Layout

    out: list[Finding] = []
    for shot in ctx.plan.shots:
        layout_path = ctx.project.card_dir(ctx.module, shot.id) / "layout.json"
        layout = Layout.load(layout_path) if layout_path.is_file() else Layout()

        boxes = {}
        for card in shot.cards:
            slot = layout.get(card.name)
            boxes[card.name] = card.placed(slot.rect if slot else card.rect)
            off = boxes[card.name].outside()
            if off and not (card.cut or card.bahan == "seal"):
                out.append(fail("compose", f"{shot.id}/{card.name}",
                                f"runs off the page ({', '.join(off)} edge; {boxes[card.name]}) "
                                "and is not marked `cut`"))
        placed = [Placed(c.name, boxes[c.name], c.z, {"card": c}) for c in shot.cards]
        for below, above, frac in buried(placed, floor=0.30):
            card = below.data.get("card")
            if card is not None and card.tertutup_boleh:
                # The plan already answered this one, with a reason the schema
                # gate refused to accept silence for. Two gates reading one fact
                # and giving two answers is how a review stops being trusted.
                out.append(note("compose", f"{shot.id}/{below.name}",
                                f"'{above.name}' covers {frac:.0%} of it — declared: "
                                f"{card.tertutup_alasan}"))
                continue
            level = fail if frac > 0.55 else warn
            out.append(level("compose", f"{shot.id}/{below.name}",
                             f"'{above.name}' (z{above.z}) covers {frac:.0%} of it (z{below.z}) "
                             f"— one is paid for and mostly unseen"))
    return out


# --------------------------------------------------------------------- data
def data(ctx: Context) -> list[Finding]:
    """A figure on a card has to be a figure the narration says."""
    narration = _needs_narration(ctx)
    lang = language(ctx.project.language)
    spoken: set[str] = set()
    for phrase in _phrases(narration):
        spoken |= lang.numbers(phrase)

    out: list[Finding] = []
    for shot in ctx.plan.shots:
        for card in shot.cards:
            for text in _printed(card):
                for digits in re.findall(r"\d[\d.,]*", text):
                    bare = re.sub(r"[^\d]", "", digits)
                    if not bare:
                        continue
                    if bare in spoken or bare.lstrip("0") in spoken:
                        continue
                    if card.angka_bahan:
                        # Read off a photographed sign rather than asserted by
                        # the film. `schema` has already refused the flag unless
                        # the plan gave a reason, so this is a reviewed
                        # exemption, not a hole.
                        out.append(note("data", f"{shot.id}/{card.name}",
                                        f"prints {digits!r}, which the narration never says — "
                                        f"declared material: {card.angka_alasan}"))
                        continue
                    out.append(fail("data", f"{shot.id}/{card.name}",
                                    f"prints the figure {digits!r}, which the narration never says "
                                    f"('{text[:50]}')"))
    return out


# -------------------------------------------------------------------- spell
def spell(ctx: Context) -> list[Finding]:
    """Every printed term spelled the way the facts say it is spelled.

    The still prompt is built verbatim from the plan, so the model draws the typo
    faithfully: `CAHI` reached a render, twice, and read as a typo because it was
    one. `lexicon.json` is the list of things that have been wrong before.
    """
    if not ctx.lexicon:
        return [note("spell", ctx.plan.module,
                     "no lexicon.json — nothing to check printed terms against")]
    forbidden: dict[str, str] = {}
    for term in ctx.lexicon.get("terms", []):
        correct = str(term.get("correct", "")).strip()
        for wrong in term.get("never", []):
            if correct and str(wrong).strip():
                forbidden[str(wrong).strip().lower()] = correct

    out: list[Finding] = []
    for shot in ctx.plan.shots:
        for card in shot.cards:
            for text in [*_printed(card), card.what, card.semantik]:
                low = (text or "").lower()
                for wrong, correct in forbidden.items():
                    if re.search(rf"\b{re.escape(wrong)}\b", low):
                        out.append(fail("spell", f"{shot.id}/{card.name}",
                                        f"prints '{wrong}' — the facts say '{correct}' "
                                        f"('{(text or '')[:60]}')"))
    return out


GATES = [
    Gate("schema", schema, _plan_inputs,
         asks="every field has a type, a vocabulary and a placement that parses"),
    Gate("context", context_gate, _plan_inputs,
         asks="the plan says what it was written against"),
    Gate("ranges", ranges, _plan_inputs,
         asks="shots tile the narration exactly"),
    Gate("arrival", arrival, _plan_inputs,
         asks="each card settles on the word that names it"),
    Gate("marks", marks, _plan_inputs,
         asks="gestures exist, arrive after their card, and are not a lattice"),
    Gate("readable", readable, _plan_inputs,
         asks="printed cards sit above anything that can cover them"),
    Gate("compose", compose, _plan_inputs,
         asks="pieces are on the page and not buried"),
    Gate("data", data, _plan_inputs,
         asks="figures printed on cards are figures the voice says"),
    Gate("spell", spell, _plan_inputs,
         asks="printed terms are spelled as the facts say"),
]
