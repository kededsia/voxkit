"""The presenter's hand: which pen, which colour, and whether to write or stamp.

v2 stated the rule and v3 lost it (`DECISIONS.md` §Marker):

    Warna membawa arti. Kuning = penekanan utama, satu per shot. Coral = nama.
    Sky = pendukung. Ink = koreksi. Chalk = tanda di atas foto gelap.
    Pena membawa volume. Highlighter di bawah huruf, felt-tip di atasnya,
    ballpoint untuk koreksi, crayon paling keras.
    Ring kuning di atas stiker kuning tidak terlihat. Ring hanya di atas foto.
    Satu tanda per beat.

v3 emitted 465 marks with **one pen** (`marker`) and two colours chosen by
`"coral" if i % 2 == 0 else "crimson"` — colour by array index, which carries no
meaning at all and is exactly the failure v2 named. The renderer had the answer the
whole time: `PRESET` in `Marker.tsx`.

So this module is the single place that answers "how loud is this mark, and in what
colour", and everything else asks it. Two consequences follow from the v2 text and
are implemented here rather than in a comment:

* **Contrast.** A mark must be visible on what it lands on. Chalk on cream paper and
  ink on a dark halftone are both invisible, and "ring kuning di atas stiker kuning"
  is the same fault with a different colour. The material says which is which, so
  the material decides — no pixels needed, and no per-frame cost.
* **Volume.** A highlighter is a broad wash under lettering; a felt-tip is a line
  above it; a ballpoint is a correction. Choosing one pen for the whole film makes
  every emphasis the same volume, which is the same as having no emphasis.

The second half of this module is the part the client asked for by name: a graphic
presenter does not only choose a colour, it chooses a *vehicle*. A short stiff word
is sometimes written by hand and sometimes stamped; a card is sometimes carried in
and sometimes slapped down. `register()` decides the vehicle, and it is deliberately
deterministic — the same word gets the same treatment in every render, because a
film whose handwriting changes on re-render is not a film.
"""
from __future__ import annotations

from dataclasses import dataclass

from .contract import TRAVEL_MAX

#: The five registers a mark can be in. Mirrors `PRESET` in `Marker.tsx`, and the
#: names are the presenter's, not the renderer's.
INTENTS = ("emphasis", "name", "support", "correction", "quiet")

#: intent -> (colour, pen). One table, read by the emitter and by the gate that
#: asks whether a shot has more than one loud thing in it.
PRESET: dict[str, tuple[str, str]] = {
    "emphasis": ("yellow", "marker"),
    "name": ("coral", "marker"),
    "support": ("sky", "felt"),
    "correction": ("ink", "ballpoint"),
    "quiet": ("chalk", "chalk"),
}

#: Materials that are cream paper. A chalk mark on these is invisible — the
#: literal "ring kuning di atas stiker kuning" fault.
CREAM = frozenset({"cetak", "koran", "peta", "seal"})
#: Materials that are a dark halftone. Ink on these is invisible.
DARK = frozenset({"foto"})

#: What to use instead when the chosen colour would vanish.
FALLBACK = {
    ("quiet", "cream"): ("support", "sky", "felt"),
    ("quiet", "dark"): ("quiet", "chalk", "chalk"),
    ("correction", "dark"): ("quiet", "chalk", "chalk"),
    ("emphasis", "dark"): ("emphasis", "amber", "marker"),
}


def surface(bahan: str) -> str:
    if bahan in DARK:
        return "dark"
    if bahan in CREAM:
        return "cream"
    return "mid"


def _fix(intent: str, bahan: str) -> tuple[str, str, str]:
    """The intent's preset, moved to something visible on this surface."""
    key = (intent, surface(bahan))
    if key in FALLBACK:
        return FALLBACK[key]
    colour, pen = PRESET[intent]
    return intent, colour, pen


def for_shape(shape: str, first: bool, on_readable: bool) -> str:
    """Which register a shape is asking for, before the surface is considered.

    `first` is "this is the loudest thing in the shot". v2 allows exactly one
    emphasis per shot; a second one is not a second emphasis, it is a name or a
    support, and demoting it is what keeps the hierarchy readable.
    """
    if shape in ("strike", "cross"):
        return "correction"
    if shape in ("brackets", "bracket-left", "bracket-right", "ellipse"):
        return "support"
    if shape in ("arrow-curve", "arrow-right", "arrow-down", "squiggle",
                 "connector", "route"):
        return "support"
    if shape in ("circle", "box"):
        return "emphasis" if first else "name"
    if shape in ("underline", "underline-double"):
        return "name" if not first else "emphasis"
    return "emphasis" if first else "support"


def for_gesture(kind: str) -> str:
    """The presenter's own vocabulary (`presenter.KINDS`) as registers."""
    return {
        "relate": "support",
        "group": "support",
        "strike": "correction",
        "trace": "support",
        "write": "emphasis",
        "again": "support",
        "point": "name",
    }.get(kind, "support")


@dataclass(frozen=True, slots=True)
class Ink:
    intent: str
    color: str
    pen: str


def resolve(intent: str, bahan: str, *, declared_color: str = "",
            declared_pen: str = "") -> Ink:
    """The final pen and colour. A plan that names its own wins, but is still
    checked for contrast — a declared chalk mark on cream paper is a mistake the
    engine should not faithfully draw."""
    i, colour, pen = _fix(intent, bahan)
    if declared_color:
        colour = declared_color
        # A declared colour still has to be visible; only `quiet` can vanish.
        if surface(bahan) == "cream" and colour == "chalk":
            colour = "ink"
    if declared_pen:
        pen = declared_pen
    return Ink(intent=i, color=colour, pen=pen)


# ------------------------------------------------------------------ vehicles
#: How a card arrives, chosen by the *beat* in `voxkit.intent` and narrowed by
#: what the piece is made of. `travel` is frames, `stepped` is the stop-motion
#: cadence.
#:
#: Every card in v3 arrived with `stepped = 2` and 88 % of them travelled 17 or 21
#: frames, so a photograph, a torn slip and a cut-out person all landed at the
#: same cadence. A cut-out that snaps into place two frames at a time reads as
#: paper; a printed slip that does the same reads as a bug.
#:
#: The first version of this table keyed on `bahan` alone, which is why it was
#: still a lookup: a map always unrolled, whoever was speaking. Now the arrival is
#: a consequence of the register — something being *named* is placed, something
#: arriving on a stressed word is snapped — and the material only vetoes what it
#: cannot physically do.
ARRIVAL = {
    # arrival      travel  stepped
    "carried":    (21, 2),   # heavy, and it keeps moving until it is put down
    "placed":     (14, 1),   # set down deliberately, no cadence at all
    "unrolled":   (21, 3),   # in pulls
    "snapped":    (11, 3),   # an impact: short, jerky
    "dropped":    (18, 4),   # falls, skates, grips
}

#: What each material can physically do. A map cannot be snapped; a slip cannot
#: be unrolled. Anything not listed may use any arrival.
CAN_ARRIVE = {
    "peta": ("unrolled", "placed"),
    "figur": ("snapped", "dropped", "placed"),
    "benda": ("snapped", "dropped", "placed"),
    "foto": ("carried", "placed", "dropped"),
    "cetak": ("placed", "snapped", "carried"),
    "koran": ("placed", "snapped", "carried"),
    "seal": ("snapped", "placed"),
}


def vehicle(bahan: str, wujud: str, travel: int, stepped: int,
            arrival: str = "") -> tuple[int, int]:
    """The card's own arrival, from the beat's decision and what it is made of."""
    if arrival not in ARRIVAL:
        arrival = "placed"
    allowed = CAN_ARRIVE.get(bahan)
    if allowed and arrival not in allowed:
        # The material vetoes. Fall back to the first thing it *can* do that is
        # closest to what the beat asked for — never to a default.
        arrival = allowed[0]
    want_travel, want_stepped = ARRIVAL[arrival]
    # The accent score still decides *when*; the arrival only decides *how long*
    # it takes, and only within a band, so a stressed word is never delivered at
    # a crawl.
    t = max(11, min(TRAVEL_MAX, round((travel + want_travel) / 2)))
    if wujud == "siluet_organik":
        t = max(13, min(19, t))
    return t, want_stepped


# ------------------------------------------------------------------- stamps
#: A word short enough to be a stamp. Beyond this a stamp has to shrink the type
#: until it is unreadable, and an unreadable stamp is a smudge.
STAMP_MAX = 8

#: Frames a hand needs per letter to write legibly. Below this the pen is not
#: writing, it is scribbling: the stroke is still travelling when the letter is
#: already over. Measured on the film's own notes, a note takes about 5 frames a
#: letter; `Cikapundung` was given 26 frames for eleven letters — 2.4 — and the
#: render is a smear that happens to have the right length.
#:
#: A stamp has no such floor. It is an impact, and an impact may be fast, which
#: is the whole reason this is a rule about *writing* and not about notes.
WRITE_FPL = 3.0

#: How many gestures a shot can carry before a note stops being a gesture and
#: becomes an object. Counting marks and cards, not pixels: the question is how
#: many things the eye is already being asked to follow.
CROWDED = 3


def letters(text: str) -> int:
    """Drawable letters, ignoring the spaces the pen only steps over."""
    return sum(1 for ch in text if not ch.isspace())


def can_write(text: str, duration: int) -> bool:
    """Whether a hand could actually write this word in the time it was given.

    The one thing a stamp can do that a pen cannot: arrive instantly. So a note
    that is too fast to write is not a note with a bad duration, it is a note
    that wanted to be pressed on.
    """
    n = letters(text)
    if n == 0:
        return True
    if duration <= 0:
        return True          # no clock declared: nothing to contradict
    return duration / n >= WRITE_FPL


def register(text: str, intent: str = "emphasis", *, duration: int = 0,
             crowd: int = 0) -> str:
    """`write` or `stamp` for a handwritten note — the presenter's choice.

    The client's note, and the reason this exists: *"write text yg kaku dan kecil
    itu kadang harus di rubah misal dengan stamp style"*. A seven-letter word
    written by a pen at 26 px is stiff and small; the same word stamped is an
    object on the page, and the film already has rubber stamps in it — m03's
    `petugas_stempel` presses one.

    The word **kadang** is the instruction. This is not "stamp the short words":
    that is the same failure as stamping none of them, with the sign flipped.
    Every rule below is a *reason*, and none of them is a coin toss:

    1. **What the word is.** A figure is printed, never handwritten — a number
       read off a sign came off a press. A correction is pressed *over* what it
       corrects, so it is a stamp for the same reason a proofreader's mark is.
    2. **Whether the hand has time.** Below `WRITE_FPL` the pen cannot form the
       letters, and the honest vehicle is the one that does not need to.
    3. **Whether the word needs the pen.** Past `STAMP_MAX` a stamp has to shrink
       its type until it is a smudge, so a long word is written.
    4. **How much gesture the shot already carries.** This is the one that keeps
       the film from looking mechanical, and it is the reason the choice cannot
       be made per word in isolation: on a page with three arrows already on it,
       a fourth gesture is noise and the note should arrive as an *object*; on a
       quiet page the act of writing is itself the thing to watch.

    What this replaced is worth naming, because it looked reasonable and was not:
    `len(word) > 8`, and then a **hash of the word** for everything shorter. A
    hash is stable, which is why it survived review — but stability is not a
    reason. Three notes in m06 (`ambil`, `menjadi`, `nama`) all hashed to
    "write", and the module ended up with four handwritten notes and no stamp,
    purely because three numbers happened to be divisible by three.
    """
    word = text.strip()
    if not word:
        return "write"
    if any(ch.isdigit() for ch in word) and len(word) <= STAMP_MAX + 2:
        return "stamp"
    if intent in ("correction", "quiet"):
        return "stamp"
    if not can_write(word, duration):
        return "stamp"
    if len(word) > STAMP_MAX or " " in word:
        return "write"
    # A full page takes the note as an object; an empty one can afford the hand.
    return "stamp" if crowd >= CROWDED else "write"
