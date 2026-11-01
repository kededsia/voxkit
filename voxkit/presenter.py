"""The presenter: what a person with a marker would do on this page, and why.

A mark is not a shape with a target. It is an *answer*. The voice says something,
the page shows something, and a hand moves to put the two together. Everything in
this module exists to keep that order — reason first, stroke second — because the
fault the client kept reporting ("the arrow misses the word") is what a stroke
looks like when nobody decided what it was for.

Two people do this job in a real edit, and the distinction is the whole design:

    the **director** decides *what is being said* — which piece carries the claim,
    which two pieces the sentence joins, which piece it contradicts.

    the **presenter** decides *what the hand does about it* — a circle around the
    thing named, an arrow between two things that are being related, a bracket
    holding a set together, a strike through what has been cancelled.

This module is the director and the presenter in one pass, because on a 40-second
shot they are the same thought. It reads the narration and the page and returns
`Gesture`s, each carrying the sentence it answers. Nothing here draws: geometry
and timing belong to `emit/choreography.py`, which cannot invent a gesture and
can only place the ones decided here.

The vocabulary is a presenter's, not a renderer's:

    POINT   identify the thing being named     circle · underline · box
    RELATE  show how two things connect        connector (the mindmap edge)
    GROUP   hold several things as one set     brackets · box
    STRIKE  cancel what is written             strike
    TRACE   follow a path the voice describes  squiggle · arrow-curve

RELATE is the one that makes the page a mindmap rather than a set of highlights.
A viewer watching four pieces appear one after another sees four things; a viewer
watching an arrow drawn from the first to the second, and then from the second to
the third, sees an argument. That edge is the difference between a collage and an
explanation, and it is the piece the film was missing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .contract import READABLE, Card, Shot
from .geometry import Rect
from .words import Narration, normalise

# --------------------------------------------------------------- the words
#: The presenter's charter. Printed by `vox gestures --brief`, and the thing every
#: gesture in this module is answerable to. It is written out because a presenter
#: that has not been told what the film is for will decorate: it will add a circle
#: because a card arrived, and the circle will mean nothing. The brief is the
#: difference between a hand that explains and a hand that scribbles.
BRIEF = """\
WHAT YOU ARE
  You are presenting a 40-second Vox-style explainer, one page at a time, to a
  viewer who has not read the script. You have a marker, a page of cut paper, and
  the voice. Your job is not to decorate the page. It is to make the viewer's eye
  arrive at the same place as the sentence, at the same moment.

WHAT THE OUTPUT MUST LOOK LIKE
  Hand-made. Everything you add is drawn by a hand on paper: marker strokes,
  underlined words, arrows, brackets, circled objects, handwritten labels and
  numbers, torn tape, pencil rules. No UI chrome, no smooth vector graphics, no
  drop shadows that a camera could not photograph, no typefaces that a pen could
  not write. If you add text, it is handwriting — never a font.
  The page is a collage: halftone photographs, torn slips, printed columns, tape.
  Your marks live ON that paper, so they wobble, overshoot, and occasionally
  catch an edge. A perfectly straight line would look pasted on.

WHAT YOU MAY DO
  point     mark the thing being named            circle · underline · box
  relate    draw the edge between two pieces      connector — this is the mindmap
  group     hold several pieces as one set        brackets
  strike    cancel what has been contradicted     strike
  trace     follow a path the voice describes     squiggle · arrow-curve
  write     add a handwritten word or figure      the number, the name, the count
  again     go back to something already there    a second stroke on a piece the
                                                  sentence has returned to
  shift     move a card, a cut-out or a puppet    to make room for the explanation
  motion    add hand-drawn movement               a drawn arrow that travels, a
                                                  stroke that re-draws, a slip that
                                                  slides, a puppet that turns

  You may move a piece if moving it helps the sentence land — clearing a corner so
  an arrow can reach, sliding a slip aside so a figure is readable, bringing a
  puppet forward so it can be pointed at. A piece that is in the way of the
  explanation is part of the problem, not a fixed fact.

WHAT YOU MAY NOT DO
  Draw anything that does not answer a sentence. Mark the same piece twice for
  the same reason. Cover a figure the viewer has to read. Add a mark the camera
  cannot keep on screen. Use a shape because it is available rather than because
  it says something.

THE TEST
  For every stroke: say out loud what the voice is saying at that frame, then say
  what the stroke does about it. If the second sentence is "it makes it look
  busier", the stroke is wrong.
"""

#: What the presenter is allowed to do. The vocabulary is a presenter's, not a
#: renderer's: these are *decisions*, and the emitter decides what draws them.
KINDS = ("point", "relate", "group", "strike", "trace", "write", "again", "shift", "motion")

# A sentence that relates two things. These are the words that earn a connector:
# without one of them the two pieces are merely adjacent on the page, and an
# arrow between adjacent things is decoration.
RELATION = {
    "lalu": "then", "kemudian": "then", "sesudah": "after", "sebelum": "before",
    "sehingga": "so that", "sampai": "until", "maka": "therefore", "jadi": "so",
    "karena": "because", "sebab": "because", "dari": "from", "ke": "to",
    "menuju": "toward", "lewat": "via", "dan": "and", "dengan": "with",
    "tetapi": "but", "tapi": "but", "namun": "however", "sedangkan": "while",
    "sementara": "while", "lawan": "against", "dibanding": "compared with",
}
# A sentence that cancels something. A strike is the only gesture that says
# "not this", and it may only be drawn on a piece the voice has just cancelled.
NEGATION = {"bukan", "tidak", "tak", "tanpa", "belum", "bukanlah", "tiada",
            "hilang", "berhenti", "berakhir", "lenyap"}

#: Words that carry no subject. A presenter does not point at "and" or "this";
#: a card whose `word` is one of these has not been named, and treating it as if
#: it had is how the first version of this module produced "the voice says 'Dan'
#: at f13" — a gesture with a reason that explains nothing.
STOP = {
    "dan", "atau", "ini", "itu", "ia", "dia", "yang", "di", "ke", "dari", "pada",
    "dengan", "untuk", "dalam", "ada", "adalah", "juga", "sudah", "telah", "akan",
    "masih", "hanya", "saja", "bisa", "boleh", "kita", "kami", "mereka", "saya",
    "aku", "kamu", "para", "sang", "si", "sebuah", "seorang", "satu", "dua",
    "tapi", "tetapi", "namun", "lalu", "karena", "sebab", "jadi", "maka",
    "sehingga", "sampai", "kalau", "jika", "bila", "saat", "ketika", "sedang",
    "begitu", "sangat", "lebih", "paling", "semua", "setiap", "tiap", "banyak",
    "bukan", "tidak", "tak", "tanpa", "belum", "pun", "lah", "kah", "nya",
    # Prepositions and connectives that a sentence leans on but a page cannot
    # use. The gap-filler was writing "daripada" and "Mari" — words the voice
    # stresses and the eye has no use for, because they name nothing. A note is
    # only worth the ink if it is a *thing*, so the words that are not things are
    # refused here rather than left to the stress score.
    "daripada", "kepada", "terhadap", "bagi", "buat", "atas", "antara",
    "seperti", "sebagai", "supaya", "agar", "mari", "ayo", "bahwa", "yakni",
    "yaitu", "misalnya", "memang", "justru", "bahkan", "hanya", "sambil",
}

#: How many pieces a shot may be pointed at. The pen is scarce: a page with six
#: strokes on it explains less than a page with two, because the eye has to choose.
POINT_MAX = 2

#: A stretch with nothing happening is a fault, not a rest. At 30 fps this is a
#: second and a half of the viewer staring at a page that has stopped talking
#: while the voice has not. Measured on `m03`, the worst was 109 frames — 3.6
#: seconds of nothing — and it was invisible to every gate because "nothing
#: arrives" was only ever a warning.
GAP_FILL = 42
#: How long a written note stays. Long enough to read a word twice, short enough
#: that it is gone before it becomes furniture.
WRITE_HOLD = 34


def note_frames(text: str) -> int:
    """How long the hand takes to write this word.

    A word takes as long as it has letters. A fixed thirty-four frames made a
    nine-letter word a scribble and a four-letter one a crawl, and neither fills
    a silence honestly.

    One definition, because two places need the answer and they must not drift:
    `_fill` needs it to know when the pen lifts (so it can look for the next
    silence), and the emitter needs it to draw the note. They were two copies of
    the same arithmetic in two modules, which is the shape of a bug waiting.
    """
    return min(max(26, 5 * len(text)), 56)

#: How many silences a shot may answer in writing. Filling every gap turns the
#: page into a notebook, so writing is capped and the rest of a silence is
#: answered by pointing back at something already on the page.
WRITE_MAX = 2
#: How many times a shot may return to a piece it has already shown. The gesture
#: exists because a four-second tail with five pieces on screen is not a moment
#: to write something new — it is a moment to say "look at this again".
AGAIN_MAX = 3
#: How long that second stroke takes, in frames.
AGAIN_HOLD = 16
#: How long before the same piece may be returned to. Long enough that the two
#: strokes are separate thoughts, short enough that a long tail can be held.
AGAIN_COOL = 28
#: How long a gap has to be open before going back to a piece counts as answering
#: silence rather than pointing at what just arrived.
AGAIN_DELAY = 24
#: The gestures the emitter turns into ink. The presenter's vocabulary is wider
#: than this — `point` and `group` are how it reads the page and decides what to
#: connect — but a gesture the renderer drops is not an event, and counting one as
#: an event is how a shot passes its own solver and fails the gate.
DRAWN = frozenset({"write", "again", "relate"})
#: A word longer than this is a phrase, and a phrase written by hand takes longer
#: to read than the gap it is filling. The presenter writes the shortest true
#: word instead.
WORD_MAX = 12

#: How many strokes a page can carry before the eye has to choose. Not a taste
#: call: four marks on a 200-frame shot is already one every second and a half.
BUDGET = ((120, 3), (240, 4), (10_000, 5))

#: How much of a piece a written note may cover before it is in the way. A note
#: that clips the corner of a slip is fine; one that lands on a face is not.
NOTE_CLEAR = 0.06

#: How close a relation word has to sit to both pieces to join them, in frames.
JOIN_WINDOW = 90
#: A group needs this many pieces named close together to be a set.
GROUP_MIN = 3
#: A piece named more than this long after the previous one is a new thought, not
#: a member of the same set.
GROUP_WINDOW = 110


@dataclass(frozen=True, slots=True)
class Gesture:
    """One decision: what the hand does, to what, and the sentence that asked."""

    kind: str            # point | relate | group | strike | trace | write | shift
    shape: str           # the renderer's name for the stroke
    on: str              # the card it is drawn on ("" for a page gesture)
    to: str              # the second card, for `relate`
    at: int              # the frame the pen should touch down
    why: str             # the reason, in words, for a person reading the plan
    word: str = ""       # the word in the narration that motivates it
    text: str = ""       # for `write`: what the hand writes
    spot: Rect | None = None   # for `write`: where on the page, decided here
    dx: float = 0.0      # for `shift`: how far the piece moves, in page fractions
    dy: float = 0.0

    def __str__(self) -> str:
        target = f"{self.on}→{self.to}" if self.to else self.on
        return f"f{self.at:<4} {self.kind:<7} {self.shape:<13} {target:<24} {self.why}"


# ------------------------------------------------------------- the page
#: Where the pen may not go. A presenter reads the page before writing on it: a
#: note dropped on a face, a printed column or a number the sentence is about is
#: not an explanation, it is damage. This is the model the first version of this
#: module did not have, and it is why the notes it wrote had no position at all —
#: the emitter was left to invent one, and the emitter cannot see the argument.
def _ink(cards: tuple[Card, ...]) -> tuple[Rect, ...]:
    """Where a note may not go: every piece, and printed ink hardest.

    Every piece, not only the printed ones. A note written across a photograph is
    a note written over the thing the sentence is about — it reads as damage
    rather than as commentary, and on a page this dense the photograph is usually
    the subject. Printed text and figures are the last resort of all, so they
    carry double weight.
    """
    out = []
    for c in cards:
        box = c.rect.clamped().expanded(0.010)
        out.append(box)
        if c.readable or any(ch.isdigit() for ch in c.semantik):
            out.append(box)
    return tuple(out)


def _note_box(word: str, aspect: float) -> tuple[float, float]:
    """How big a box a written word needs, in page fractions.

    Derived from the letterforms rather than guessed: `HandLetters` advances
    about 62 units per letter in a 126-unit-tall box, so a word's pixel aspect is
    `0.49 × letters`. A box of the wrong aspect does not distort the word —
    `preserveAspectRatio="meet"` prevents that — but it does make it smaller than
    the room it was given, which is the difference between a note you can read
    and a smudge.
    """
    n = max(3, min(WORD_MAX, len(word)))
    # A note, not a headline. At 0.075 of the frame the letters are about fifty
    # pixels tall — the size a person writes in a margin, which is the size that
    # reads as "I wrote this down" instead of "this is the title".
    h = 0.075
    w = h * (0.43 * n) / aspect
    return (min(0.34, w), h)


def free_spot(cards: tuple[Card, ...], aspect: float, word: str,
              near: Card | None = None, taken: tuple[Rect, ...] = ()) -> Rect:
    """The best place on this page to write `word`, given what is already there.

    A grid, scored three ways, in this order of importance: do not cover ink, do
    not leave the page, stay near the thing being talked about. The last one
    matters more than it looks — a note in the far corner is a caption, and a
    caption is read after the sentence rather than with it.
    """
    w, h = _note_box(word, aspect)
    ink = _ink(cards)
    taken = tuple(t.expanded(0.02) for t in taken)
    best: tuple[float, Rect] | None = None
    for i in range(13):
        for j in range(9):
            x = 0.03 + i * (0.94 - w) / 12
            y = 0.05 + j * (0.90 - h) / 8
            box = Rect.from_edges(x, y, x + w, y + h)
            if box.x1 > 0.985 or box.y1 > 0.975:
                continue
            hit = sum(min(1.0, box.covered_by(o)) for o in ink)
            hit = max((box.overlap_ratio(o) for o in ink), default=0.0) + 0.5 * hit
            # A note already on the page is not room. Two words written over each
            # other is the one thing worse than one word in the wrong place.
            used = max((box.overlap_ratio(t) for t in taken), default=0.0)
            edge = max(0.0, 0.035 - min(x, y, 1 - (x + w), 1 - (y + h))) * 8.0
            away = 0.0 if near is None else math.hypot(
                (box.cx - near.rect.cx) * aspect, box.cy - near.rect.cy)
            score = hit * 10.0 + used * 12.0 + edge + away * 0.30
            if best is None or score < best[0]:
                best = (score, box)
    return best[1] if best else Rect.from_edges(0.04, 0.06, 0.04 + w, 0.06 + h)


def budget(span: int) -> int:
    """How many strokes this shot can carry."""
    for frames, n in BUDGET:
        if span <= frames:
            return n
    return BUDGET[-1][1]



def _keys(card: Card) -> list[str]:
    """Every word this piece could be called by, most specific first.

    The plan's `word` is the word the card *lands* on, and it is not always the
    word the piece is about — a slip about a suffix can land on "dan". So the
    piece's own label (`semantik`) is read as well, and the two are tried in
    order of length: `pengumbahan` identifies a piece, `ci` barely does.
    """
    raw = [card.word] + [w for w in card.semantik.replace(",", " ").split()]
    seen: list[str] = []
    for w in raw:
        k = w.strip().lower().strip(".,;:!?\"'()")
        if not k or k in STOP or len(k) < 3 or k in seen:
            continue
        seen.append(k)
    return sorted(seen, key=len, reverse=True)


def _named(card: Card, narration: Narration, lo: int, hi: int) -> tuple[int, str] | None:
    """The frame the voice names this piece inside `[lo, hi]`, and the word used."""
    keys = _keys(card)
    if not keys:
        return None
    best: tuple[int, str] | None = None
    for a in narration.between(lo, hi):
        if a.word.key in keys:
            if best is None or a.word.start_frame < best[0]:
                # Quoted back to the reader as the presenter heard it: no trailing
                # comma, because "'benda,'" reads as a typo rather than a word.
                best = (a.word.start_frame, a.word.text.lower().strip(".,;:!?\"'()"))
    return best


def _shape_for(card: Card) -> str:
    """The stroke a presenter would use on *this kind of piece*.

    A printed slip is read line by line, so an underline sits under the line the
    voice is on. A photograph is an object, so a circle goes round it. A small
    stamp or a number is boxed, because a box is what you draw round a value you
    are about to use. This is not decoration: the stroke has to agree with how the
    piece is read, or the eye does not know where to stop.
    """
    if card.bahan in READABLE:
        return "underline" if len(card.semantik) > 18 else "box"
    return "circle"


def present(shot: Shot, narration: Narration, *, cards: tuple[Card, ...] = ()) -> list[Gesture]:
    """Every gesture this shot earns, in frame order.

    Deliberately conservative, and the conservatism is the presenter's judgement
    rather than a limit of the code. A shot with five pieces does not get five
    strokes: a page covered in marks explains nothing, because the eye has to
    choose which one it is being told about. So at most `POINT_MAX` pieces are
    pointed at, and they are the ones the voice leans on — the accented ones. A
    connector is drawn only where the narration actually joins two named pieces,
    and a bracket only where three are named as a set.
    """
    cards = cards or shot.cards
    lo, hi = shot.start, shot.end
    out: list[Gesture] = []

    # 1. Which pieces does the voice actually name?
    said: list[tuple[int, str, Card]] = []
    for c in cards:
        hit = _named(c, narration, lo, hi)
        if hit is None:
            continue
        f, word = hit
        said.append((f, word, c))
    said.sort(key=lambda t: t[0])

    # 2. POINT — the pieces it leans on, not every piece it mentions.
    ranked = sorted(said, key=lambda t: (-narration.score(t[0], t[1]), t[0]))
    chosen = sorted(ranked[:POINT_MAX], key=lambda t: t[0])
    for f, word, c in chosen:
        out.append(Gesture(
            kind="point", shape=_shape_for(c), on=c.name, to="", at=f, word=word,
            why=f"the voice names '{word}' at f{f}, and this piece is what carries it"))

    # 3. RELATE — the sentence joins two named pieces, so the page gets an edge.
    #    The connector belongs to the *pair*: it is the only gesture drawn on the
    #    page rather than on a card, because a relation is not a property of one
    #    thing. This is what turns four highlights into a mindmap.
    for (fa, wa, a), (fb, wb, b) in zip(said, said[1:]):
        if fb - fa > JOIN_WINDOW:
            continue
        word = _joiner(narration, fa, fb)
        if word is None:
            continue
        out.append(Gesture(
            kind="relate", shape="arrow-curve", on=a.name, to=b.name, at=fb, word=word,
            why=f"'{word}' joins '{wa}' to '{wb}', so the page needs an edge between "
                "them — this is the mindmap, not a highlight"))

    # 4. GROUP — three or more pieces named in one breath are one set.
    #
    #    ...but only if nothing joins them. "A, B, lalu C" is a *chain*, and a
    #    chain is what a connector is for: a bracket round it says these three are
    #    one thing, which is the opposite of what the sentence did. So a run
    #    containing a relation word is not a group, and the earlier `relate` has
    #    already drawn the edge that belongs there.
    if len(said) >= GROUP_MIN:
        run = [said[0]]
        for f, w, c in said[1:]:
            run = run + [(f, w, c)] if f - run[-1][0] <= GROUP_WINDOW else [(f, w, c)]
            if len(run) < GROUP_MIN:
                continue
            if _joiner(narration, run[0][0], run[-1][0]) is None:
                out.append(Gesture(
                    kind="group", shape="brackets", on=run[0][2].name,
                    to=run[-1][2].name, at=run[-1][0], word="",
                    why=f"{len(run)} pieces are named inside {GROUP_WINDOW} frames "
                        "with nothing joining them — they are being handed over as "
                        "one set"))
            break

    # 5. STRIKE — the voice cancels a piece it has just named.
    #
    #    One negation cancels one thing. "Bukan benda, tapi perbuatan" strikes
    #    `benda` and does *not* strike `perbuatan` — the second half of that
    #    sentence is what replaces the cancelled thing, and striking it too says
    #    the opposite of what was said. So each negation is spent once, on the
    #    next piece named after it.
    spent: set[int] = set()
    struck: set[str] = set()
    for f, word, c in said:
        neg = _negated(narration, f, spent)
        if neg is None:
            continue
        struck.add(c.name)
        out.append(Gesture(
            kind="strike", shape="strike", on=c.name, to="", at=f, word=neg[1],
            why=f"'{neg[1]}' cancels '{word}' here, and a cancelled piece has to be "
                "seen to be cancelled"))

    # A struck piece is not also pointed at. "Bukan asal-usul" draws one stroke
    # through the slip; a box round it at the same frame is a second hand saying
    # the opposite thing, and the viewer reads the box.
    out = [g for g in out if not (g.kind == "point" and g.on in struck)]

    # 6. GAPS — the page must not stop talking while the voice keeps going.
    #
    #    A presenter who has said everything the page can show does not stand
    #    still: they write the term down. This is the gesture the film was
    #    missing most, because it is the one that answers *silence* rather than a
    #    word — and silence was never a thing the pipeline thought a gesture could
    #    answer. Measured on m03, the worst stretch ran 109 frames with nothing
    #    arriving while the narration kept going.
    #
    #    Two rules keep it from becoming a notebook. Only the two worst silences
    #    are answered (the camera covers the rest), and the word written is one
    #    the page does not already say — writing "upacara" over a slip that is
    #    already printed "upacara" is a hand with nothing to add.
    #
    #    One coordinate space, and it is the narration's: `lands` is relative to
    #    the shot and every word frame is absolute, so the two are only comparable
    #    after `shot.start` is added. Mixing them made this loop read the previous
    #    shot's words — it "filled" a silence in s02 with a word spoken in s01.
    printed = {w.lower() for c in cards
               for w in [c.word, *c.semantik.replace(",", " ").split()] if w}
    marked = {m.card for m in shot.marks if m.card}
    out += _fill(shot, cards, narration, out, printed, marked)

    return sorted(out, key=lambda g: (g.at, g.kind))


def _fill(shot: Shot, cards: tuple[Card, ...], narration: Narration,
          already: list[Gesture], printed: set[str], marked: set[str]) -> list[Gesture]:
    """Answer every silence on this page until it stops being a silence.

    The first version of this filled one gap per shot and moved on, which is why
    m03 still had a hundred and seventeen dead frames in s01 after eight notes had
    been written: a note covers fifty frames, and the gap was a hundred and
    seventeen. A silence is not answered by *a* gesture, it is answered by
    gestures until it ends.

    So the clock is walked forward. At each point the page is quiet, the presenter
    does the most useful thing available: write the word the voice is leaning on,
    if the page does not already say it; otherwise go back to a piece that is
    already there and point at it again, because "look at this" is a real thing to
    say and a shot's tail is where it is said.
    """
    out: list[Gesture] = []
    notes = sum(1 for g in already if g.kind == "write")
    again = 0
    #: Every word this shot's narration actually says. A piece whose word is not
    #: in here is not something the voice is talking about, whatever its accent
    #: score says — and going back to it would be decoration.
    named = {a.word.key for a in narration.between(shot.start, shot.end)}
    #: When each piece was last gone back to. A cooldown rather than a ban: going
    #: back to a photograph two seconds later is a presenter returning to a point;
    #: going back to it four frames later is a twitch.
    revisited: dict[str, int] = {}

    def edges_now() -> list[int]:
        """Every moment the page changes, including the gestures just decided.

        Recomputed each pass, because a note the presenter writes is itself an
        event: it holds the page from `at` until its last letter, and the frames
        after that are a *new* silence. m08 s06 is the proof — the solver answered
        the gap at f889 with a note and then left fifty-nine frames to f984 empty,
        because the note it had just written was not in the edge list it was
        walking. The docstring below always claimed the clock was walked "until it
        stops being a silence"; now it is.

        Only gestures the emitter actually draws count. `point` and `group` are
        the presenter *reading* the page — they decide what to connect and what
        the sentence is about — but no stroke is drawn for them, so a silence with
        a `group` in it is still a silence. Counting them was how m08 s06 passed
        its own solver and then failed the gate: the presenter believed the page
        had changed at f957 and the page had not.
        """
        moments = [shot.start + c.lands for c in cards]
        for g in list(already) + out:
            if g.kind not in DRAWN:
                continue
            moments.append(g.at)
            if g.kind == "write" and g.text:
                moments.append(g.at + note_frames(g.text))
            elif g.kind == "again":
                moments.append(g.at + AGAIN_HOLD)
        return sorted(set(moments))

    # Four passes is enough: each one can only add gestures, and the budget
    # (`WRITE_MAX` + `AGAIN_MAX`) caps the total at five. A pass that adds
    # nothing ends the walk.
    for _pass in range(4):
        before = len(out)
        events = edges_now()
        for a, b in zip([shot.start] + events, events + [shot.end]):
            if b - a <= GAP_FILL:
                continue
            t = a + 3
            while b - t > GAP_FILL:
                said = [x for x in narration.between(t + 2, b - 2)
                        if x.word.key not in STOP and len(x.word.key) >= 4
                        and x.word.key not in printed]
                if said and notes < WRITE_MAX:
                    hot = max(said, key=lambda x: (x.score, -x.word.start_frame))
                    word = hot.word.text.lower().strip(".,;:!?\"'()")[:WORD_MAX]
                    at = max(t, min(hot.word.start_frame, t + 7))
                    near = (min(cards, key=lambda c: abs(shot.start + c.lands - at))
                            if cards else None)
                    out.append(Gesture(
                        kind="write", shape="khat", on="", to="", at=at,
                        word=hot.word.key, text=word,
                        spot=free_spot(cards, 16 / 9, word, near,
                                       tuple(g.spot for g in out if g.spot is not None)),
                        why=f"the page goes quiet for {b - a} frames at f{a}, and the "
                            f"voice leans on '{hot.word.text}' (f{hot.word.start_frame}) "
                            "— so the hand writes it down instead of leaving the viewer "
                            "to stare"))
                    notes += 1
                    # The page now says this word, so the next note may not say it
                    # again. Without this the solver wrote "memulai" twice in one
                    # shot — two identical words on one page is the clearest possible
                    # sign that nobody was looking at the page.
                    printed.add(word)
                    printed.add(hot.word.key)
                    t = at + note_frames(word) + 4
                    continue
                # Nothing worth writing, or the pen has written enough. Go back to
                # something the viewer has already seen and is still being talked
                # about: the last piece to land before now, that no plan stroke
                # already covers, and that this shot has not already revisited.
                #
                # But not the instant the gap opens. The first three frames of a
                # silence are still the arrival — the card has just landed, the
                # eye is on it, and an arrow at that moment is the presenter
                # pointing at something the viewer is already looking at. Worse,
                # it spends the cooldown before the gap it was supposed to fill:
                # m01 s04 got a stroke at f477 that ended at f493, and the
                # fifty-five frames after it could not be answered at all.
                # ...but only when waiting still leaves a gap to fill. A silence
                # of forty-nine frames has a four-frame window in which an
                # answer is possible at all, and a rule that waits twenty-four
                # frames for politeness closes it. m15 s05 has exactly that gap:
                # the card lands at f623, the next one at f672, and the whole
                # answer has to start by f630.
                if t - a < AGAIN_DELAY and b - (a + AGAIN_DELAY) > GAP_FILL:
                    t += 2
                    continue
                here = [c for c in cards
                        if shot.start + c.lands + 4 <= t and _keys(c)
                        and t - revisited.get(c.name, -10_000) >= AGAIN_COOL]
                # A piece that already carries a stroke is the last resort, not a
                # forbidden one: when it is the only thing on the page, going back to
                # it is better than four seconds of nothing — but the second stroke
                # has to be a *different* stroke, or it reads as a redraw.
                free = [c for c in here if c.name not in marked]
                # ...and the voice has to be *on* it. Going back to a piece the
                # sentence has stopped mentioning is decoration, not a gesture:
                # an arrow drawn because the shot exists rather than because
                # there is something to say. Walking the clock forward instead of
                # breaking made this reachable — every gap eventually finds a
                # card old enough to point at, whether or not anyone is talking
                # about it.
                #
                # `score` cannot answer this: it falls back to the nearest accent
                # when the word never occurs, so it is positive for any piece in
                # any shot. The question is not "how stressed is the voice" but
                # "does this shot talk about this piece at all" — and that is a
                # lookup, not a score.
                #
                # The reach is the shot, not the moment. A tighter window was
                # tried and it failed in the other direction: m01 s04 and m09 s05
                # each lost the stroke that was covering a two-second silence,
                # because the voice had named the piece forty frames earlier and
                # stopped. "Look at this again" is a fair thing to say about
                # something the shot has already introduced.
                pool = [c for c in (free or here) if normalise(c.word) in named]
                if not pool or again >= AGAIN_MAX:
                    # The clock still has to move, even when there is nothing to
                    # do at this instant — and it has to move in *small* steps.
                    # Breaking here is how m15 s05 kept forty-nine dead frames:
                    # the gap began one frame after the only card on the page had
                    # landed, so that card became eligible at a+4 and the walk was
                    # at a+3. A step of six jumped over the one frame where the
                    # answer was, and the solver gave up a frame short of it.
                    t += 2
                    continue
                pick = max(pool, key=lambda c: (narration.score(t, c.word), c.lands))
                revisited[pick.name] = t
                again += 1
                shape = _shape_for(pick)
                if pick.name in marked:
                    shape = "circle" if shape != "circle" else "underline"
                out.append(Gesture(
                    kind="again", shape=shape, on=pick.name, to="", at=t,
                    word=pick.word,
                    why=f"f{a}–f{b} is still quiet, and the sentence is still on "
                        f"'{pick.word}' — so the hand goes back to it rather than the "
                        "page sitting still"))
                t += AGAIN_HOLD + 4
        if len(out) == before:
            break
    return out


def review(shot: Shot, gestures: list[Gesture], cards: tuple[Card, ...],
           aspect: float = 16 / 9, plan_marks: int = 0) -> list[str]:
    """The presenter reading back its own page before anyone else sees it.

    A decision that is not checked is a decision that is only a guess. Every
    finding here is something a person standing at the paper would notice in one
    look: a note on a face, a stroke drawn before the piece arrived, two hands
    fighting over one card, a page with more marks than the eye can hold. None of
    them are renderer faults — they are all choices, which is why they are
    checked here and not in a gate that can only see the geometry afterwards.
    """
    out: list[str] = []
    owned = [g for g in gestures if g.kind in ("relate", "write")]
    ink = _ink(cards)
    lands = {c.name: shot.start + c.lands for c in cards}
    names = {c.name for c in cards}

    if len(owned) + plan_marks > budget(shot.span):
        out.append(f"{len(owned) + plan_marks} strokes in {shot.span} frames — this "
                   f"shot carries {budget(shot.span)}; the eye has to choose")

    for g in owned:
        if g.on and g.on not in names:
            out.append(f"f{g.at} {g.kind} names '{g.on}', which is not on this page")
        if g.on and g.on in lands and g.at < lands[g.on] - 2:
            out.append(f"f{g.at} {g.kind} on '{g.on}' starts {lands[g.on] - g.at} "
                       "frame(s) before the piece lands — the pen is ahead of the page")
        if g.kind == "write" and g.spot is not None:
            for o in ink:
                share = g.spot.covered_by(o)
                if share > NOTE_CLEAR:
                    out.append(f"f{g.at} the note '{g.text}' covers {share:.0%} of a "
                               "piece whose ink is being read")
        if g.kind == "write" and not g.text:
            out.append(f"f{g.at} a write gesture with nothing to write")
        if g.kind == "relate":
            a = next((c for c in cards if c.name == g.on), None)
            b = next((c for c in cards if c.name == g.to), None)
            if a and b and a.rect.overlap_ratio(b.rect) > 0.25:
                out.append(f"f{g.at} '{g.on}' and '{g.to}' sit on top of each other — "
                           "an edge between them says nothing")
            if a and b:
                px = math.hypot((b.rect.cx - a.rect.cx) * aspect,
                                b.rect.cy - a.rect.cy)
                if px < 0.10:
                    out.append(f"f{g.at} the edge from '{g.on}' to '{g.to}' is "
                               f"{px:.2f} of the frame long — too short to read as a line")

    # Two hands on the same thing at the same time: two edges leaving one card,
    # or two notes fighting for the page.
    for kind, group in (("stroke", [g for g in owned if g.on]),
                        ("note", [g for g in owned if g.kind == "write"])):
        buckets: dict[str, list[Gesture]] = {}
        for g in group:
            buckets.setdefault(g.on if kind == "stroke" else "page", []).append(g)
        for name, gs in buckets.items():
            gs = sorted(gs, key=lambda g: g.at)
            for a, b in zip(gs, gs[1:]):
                if b.at - a.at < 24:
                    out.append(f"{name} is marked twice {b.at - a.at} frame(s) apart "
                               f"({a.kind} then {b.kind}) — that reads as one confused "
                               f"{kind}")
    return out



def _joiner(narration: Narration, fa: int, fb: int) -> str | None:
    """The relation word spoken between two pieces, if any."""
    for a in narration.between(min(fa, fb), max(fa, fb)):
        if a.word.key in RELATION:
            return a.word.text.lower()
    return None


def _negated(narration: Narration, f: int, spent: set[int] | None = None) -> tuple[int, str] | None:
    """The negation spoken just before `f`, if any, and not already used.

    A strike answers a sentence, not a word, so the window is the second and a bit
    before the piece is named. `spent` carries the negations already spent on an
    earlier piece: one "bukan" cancels one thing, and letting it cancel the next
    two says the opposite of what the voice said.
    """
    for a in narration.between(f - 34, f):
        if a.word.key in NEGATION and (spent is None or a.word.start_frame not in spent):
            if spent is not None:
                spent.add(a.word.start_frame)
            return (a.word.start_frame, a.word.text.lower().strip(".,;:!?\"'()"))
    return None


# ------------------------------------------------------------------ geometry
def connector(a, b, aspect: float = 16 / 9) -> tuple[float, float, float, float, float]:
    """A thin box from the centre of `a` to the centre of `b`, and its angle.

    Returns `(cx, cy, w, h, rotate_degrees)`. The box is laid along the x axis and
    rotated, which is the only way to get a stroke that starts on one piece and
    ends on another: an axis-aligned box around both would draw the *diagonal of
    the bounding box*, which is the right direction only when the two pieces
    happen to be diagonal to each other.

    The angle is computed in pixels, not in page fractions. A page fraction is a
    fraction of the width on x and of the height on y, so an angle taken from the
    fractions is wrong by the aspect ratio — a 45° join on a 16:9 stage is 24°.
    """
    dx = (b.cx - a.cx) * aspect
    dy = b.cy - a.cy
    length = math.hypot(dx, dy)
    angle = math.degrees(math.atan2(dy, dx))
    cx, cy = (a.cx + b.cx) / 2, (a.cy + b.cy) / 2
    return (cx, cy, max(0.02, length / aspect), 0.10, angle)
