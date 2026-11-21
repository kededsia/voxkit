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
from dataclasses import asdict
from typing import Iterator, Mapping

from ..contract import (
    ARRIVE_EARLY, ARRIVE_LATE, JENIS, MIN_ARRIVAL_GAP, WUJUD,
    Finding, Plan, fail, is_placeholder, note, tile, warn, words_in,
)
from ..language import get as language
from ..lexicon import Lexicon
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


def _phrases_at(narration) -> list[tuple[str, int]]:
    """The narration split where the speaker paused, with the frame each starts.

    One splitter, not two. `_phrases` returns the text for `data`; the onset
    lookup needs the same split *and* the frame, and building it separately is how
    this codebase got a gate that read a different shape from the one the emitter
    read. `numbers()` is likewise the only place a figure is recognised.
    """
    out: list[tuple[str, int]] = []
    current: list[str] = []
    start = 0
    for acc in narration.accents:
        if acc.gap > 0.30 and current:
            out.append((" ".join(current), start))
            current = []
        if not current:
            start = acc.word.start_frame
        current.append(acc.word.text)
    if current:
        out.append((" ".join(current), start))
    return out


def _phrases(narration) -> list[str]:
    """The narration split where the speaker paused.

    A figure is spoken as a phrase, not as a word: `enam puluh` is 60, and neither
    `enam` nor `puluh` is. Scoring word by word reported every honest number in
    the film as invented — and a checker that fails the right answer is worse
    than none. Splitting at the pauses keeps `seribu` from one sentence gluing to
    `ratus` from the next.
    """
    return [text for text, _ in _phrases_at(narration)]


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
        # A map at the bottom of the stack is the *page*, not a piece lying on it:
        # the collage is pasted onto the map. Requiring it above everything is not a
        # legibility rule but an impossibility — and it is what put the map on top of
        # the "SELURUH KABUPATEN" slip, the exact fault this rule exists to prevent.
        # `compose` still fails a page buried past 55 %, so a map that really is
        # hidden is still caught; this only stops the rule demanding the impossible.
        page = None
        if shot.cards:
            lowest = min(shot.cards, key=lambda c: c.z)
            if lowest.bahan == "peta":
                page = lowest.name
        for card in shot.cards:
            if not card.readable or card.tertutup_boleh:
                continue
            for other in shot.cards:
                if other is card or not other.covering:
                    continue
                if card.name == page and not _is_person(other):
                    # A slip, a photograph or a pin lying on the map is the collage
                    # doing its job — the map is the page they are pasted onto. A
                    # *person* on the map is not: a silhouette standing anywhere on
                    # place names buries them, and that stays a failure.
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
#: How far a printed figure may sit from the moment the voice says it.
#:
#: `data` used to ask only *whether* the narration says the figure, and `arrival`
#: asked only whether the card lands on the word it declares — so a card printing
#: `294` that declared `word: "29"` was self-consistent and passed both, while the
#: voice said "294" four seconds earlier in the previous still. The reviewer saw
#: exactly that: the zoom sat on a card that had already been read out.
#:
#: One-sided on purpose. A card that arrives *before* its number is the presenter
#: setting up the beat — show the thing, then say it. A card that arrives after the
#: number has been said is a caption for a moment that is gone. Only the second is
#: a fault, so only the second is measured.
FIGURE_SLACK = 20


def _figure_onsets(narration, lang) -> dict[str, list[int]]:
    """figure -> the frames the voice *finishes* saying it, through `language.numbers`.

    The end, not the start. A number is spoken over a span — "tujuh belas" runs
    about thirty-five frames — and a card is on the beat when it arrives as the
    number finishes, not when it begins. Measuring against the start reported every
    honest card as 24–35 frames late, which is the length of the number itself.

    A two-word window, because the transcriber writes "29 ,4%" as two tokens and a
    single word never reads as 29,4.

    Two-digit minimum: a lone `1` or `2` printed on a page is a numeral in a
    picture, not a claim the film is making, and matching it against "satu" in
    some other sentence produced findings about the right answer.
    """
    words = [a.word for a in narration.accents]
    out: dict[str, list[int]] = {}
    for i, word in enumerate(words):
        windows = [(word.text, word)]
        if i + 1 < len(words):
            windows.append((f"{word.text} {words[i + 1].text}", words[i + 1]))
        for text, last in windows:
            done = round(last.end * last.fps)
            for figure in lang.numbers(text):
                if len(figure) < 2:
                    continue
                frames = out.setdefault(figure, [])
                if done not in frames:
                    frames.append(done)
    return out


def data(ctx: Context) -> list[Finding]:
    """A figure on a card has to be a figure the narration says — *when* it says it.

    Two questions, and the second one was missing:

      * does the narration say this figure at all? (`spoken`, unchanged)
      * does the card land on a beat where one of its figures is being said?

    The second is the one the reviewer saw: `kartu_294persen` was self-consistent
    — it declared `word: "29"` and did land on "29" — so `arrival` passed, and
    `data` passed because the film says "294" somewhere. Nothing asked whether the
    number on the card was being spoken *at the card*.

    A card may carry figures said earlier as context — "29,4 % dari 1.000" has
    both. So the rule is not "every figure must be live at the landing", it is
    "the card must land on at least one of the figures it prints". Otherwise the
    check fails the right answer, which is worse than not checking.
    """
    narration = _needs_narration(ctx)
    lang = language(ctx.project.language)
    spoken: set[str] = set()
    for phrase in _phrases(narration):
        spoken |= lang.numbers(phrase)

    onsets = _figure_onsets(narration, lang)

    out: list[Finding] = []
    #: figure -> every (landing frame, where) that prints it, for the first-show rule
    firsts: dict[str, list[tuple[int, str]]] = {}
    for shot in ctx.plan.shots:
        for card in shot.cards:
            printed: list[str] = []
            for text in _printed(card):
                for digits in re.findall(r"\d[\d.,]*", text):
                    if not digits:
                        continue
                    printed.append(digits)
                    # The same reader the narration went through. Comparing a
                    # printed figure against the transcript with a second,
                    # locally-invented normalisation is how `29,4` became `294`.
                    said = lang.numbers(digits)
                    if said & spoken or {d.lstrip("0") for d in said} & spoken:
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

            if printed and not card.angka_bahan:
                for figure in set().union(*(lang.numbers(d) for d in printed)):
                    firsts.setdefault(figure, []).append((shot.start + card.lands,
                                                          f"{shot.id}/{card.name}"))

    # Only the FIRST time the film shows a figure is a claim about that moment.
    # `m03/s02/turus_107` prints "TURUS 107" and lands five seconds after the voice
    # said 107 — but `kartu_107` had already shown it on the beat, and the tally
    # card is a second statement about a number the viewer already has. Failing it
    # was a finding about the right answer.
    for figure, shows in firsts.items():
        frames = onsets.get(figure) or onsets.get(figure.lstrip("0")) or []
        if not frames:
            continue
        land, where = min(shows)
        first_said = min(frames)
        late = land - first_said
        if late > FIGURE_SLACK:
            out.append(fail(
                "data", where,
                f"is the first card to show {figure!r} and lands at f{land}; the voice first says "
                f"it at f{first_said}, {late} frames earlier (slack {FIGURE_SLACK}). The number "
                f"reaches the screen after it has been read out."))
    return out


# -------------------------------------------------------------------- spell
def _strings(value, path: str = "") -> Iterator[tuple[str, str]]:
    """Every string in the plan, with where it sits.

    Walking the plan rather than a hand-listed set of fields is the whole point:
    the fields a word can hide in are the ones nobody remembered. `CHI` survived
    in `klaim`, `tesis_modul`, `fokus` and `semiotik` — four prose fields no
    earlier version of this gate opened, while the two fields it *did* open were
    the two that got fixed. A gate that only reads the fields the last bug used
    is a gate that catches the last bug.
    """
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, Mapping):
        for key, inner in value.items():
            yield from _strings(inner, f"{path}.{key}" if path else str(key))
    elif isinstance(value, (list, tuple)):
        for i, inner in enumerate(value):
            yield from _strings(inner, f"{path}[{i}]")


def spell(ctx: Context) -> list[Finding]:
    """Every term the film says or prints, spelled the one way the lexicon allows.

    The still prompt is built verbatim from the plan, so the model draws the typo
    faithfully: `CAHI` reached a render twice, and `CHI` reached one on the same
    page that already printed `BERAWALAN CI` correctly.

    Three things this now does that it did not:

      * reads the lexicon through `lexicon.Lexicon`, so the file's key cannot
        disagree with the reader and turn the whole check into a silent pass;
      * reads the **transcript**, not only the plan. The voice is what the viewer
        hears, and a card is checked against the transcript by the `arrival` and
        `data` gates — so a word misspelled in both agreed with itself and passed
        every check in the registry;
      * reads every string in the plan, because the surviving misspellings were in
        prose fields, not on cards.
    """
    lex = Lexicon.from_dict(ctx.lexicon)
    if not lex:
        return [note("spell", ctx.plan.module,
                     "no readable lexicon.json — nothing to check printed terms against")]

    forbidden = lex.forbidden()
    if not forbidden:
        return [note("spell", ctx.plan.module,
                     f"lexicon lists {len(lex)} term(s) and no forbidden variant — "
                     f"nothing can match")]

    pattern = re.compile(
        r"\b(" + "|".join(sorted(map(re.escape, forbidden), key=len, reverse=True)) + r")\b",
        re.IGNORECASE,
    )

    out: list[Finding] = []

    # Where a word is spoken, before it is ever drawn.
    if ctx.narration is not None:
        for word in ctx.narration.words:
            for hit in pattern.finditer(word.text):
                wrong = hit.group(0).lower()
                out.append(fail("spell", f"{ctx.plan.module} narration",
                                f"says '{word.text.strip()}' — the word is "
                                f"'{forbidden[wrong]}', not '{wrong}' "
                                f"(at {word.start:.1f}s)"))

    seen: set[tuple[str, str]] = set()
    for where, text in _strings(asdict(ctx.plan)):
        # `source` is the provenance blob: a JSON snapshot of what the plan was
        # written against, echoed into every plan. It repeats whatever the plan
        # already says, so flagging it doubles every finding without naming a
        # second place to fix.
        if where == "source" or where.startswith("source."):
            continue
        for hit in pattern.finditer(text):
            wrong = hit.group(0).lower()
            key = (where, wrong)
            if key in seen:
                continue
            seen.add(key)
            out.append(fail("spell", where or ctx.plan.module,
                            f"writes '{wrong}' — the word is '{forbidden[wrong]}' "
                            f"('{text[:70]}')"))
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
