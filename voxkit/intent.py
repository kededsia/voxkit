"""One decision per beat. The presenter's judgement, in one place.

This module exists because of a specific, repeated failure, and it is worth
naming before describing what replaces it.

Twice the engine was given the same instruction and twice it built a *vocabulary*
instead of a *decision*:

* The camera got `reason="arrive"` on every key — a label applied **after** the
  move had been computed by `punch_for` and `creep`. The camera never chose
  anything; it was moved by whoever ran last, and then named. And because the
  label was never read by the renderer, the film had no camera movement at all
  while sixteen gates reported green.
* The markers got `INTENTS` (five), `PRESET` (five), and `for_gesture` (seven
  words). Measured: `for_gesture` was called twice, both times with a hardcoded
  string, and every handwritten note was registered with the literal
  `"emphasis"`. The intent table was fed by nothing.

So the client asked, reasonably: *"saya tanya paham? anda jawab paham. tapi paham
kok gak dikerjain dengan bener."*

The answer this module gives is structural. A **beat** is one scored accent — one
thing the voice leans on. For that beat, exactly one decision is made, and that
decision carries *every* consequence:

    register   what this beat is doing      emphasis / name / support / correction / quiet
    colour     and in what ink              yellow / coral / sky / ink / chalk / amber
    pen        and at what volume           marker / felt / ballpoint / chalk
    vehicle    how a note arrives           write / stamp
    arrival    how a card is placed         carried / placed / unrolled / snapped / dropped
    move       what the camera does         punch / drift / arrive / pull / hold / none

Four systems used to answer those six questions separately and disagree. Now one
function answers them, and the gates check that the answer was used.

The last field is the one the client asked for by name: *"itu juga masukin ke
bagian intent, jadi ga ada gerak liar, yg ada gerak kamera terukur yg sengaja
dengan tujuan presentasi dan fokus penonton."* A camera move is not chosen by the
camera. It is chosen here, from what the beat is doing, and the camera only
executes it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from . import ink

#: What the camera is allowed to do. Each name is a shape, not a direction, and
#: each one exists because a different kind of beat needs it.
MOVES = (
    #: A stressed word. Three frames in, eight back. The camera *goes* somewhere.
    "punch",
    #: A sentence being spoken. 1–2 % over most of the shot. The still is alive.
    "drift",
    #: Something being named. A steady push that ends on the thing.
    "arrive",
    #: A list, or a page already full. The frame opens to take the next item.
    "pull",
    #: A line that has to be read, or ink being laid down. The frame stops.
    "hold",
    #: Nothing to add. A shot can have a beat with no camera at all, and that is
    #: a decision rather than an omission.
    "none",
)

#: How a card arrives. Not a material property — a *beat* property, though the
#: material narrows it (a map cannot be snapped).
ARRIVALS = ("carried", "placed", "unrolled", "snapped", "dropped")

#: The earliest frame a hit may start on. `cam.punch` needs `rise + settle` (24)
#: frames of runway before its final key, so a card landing on f2 has nowhere to
#: put one — and asking for one produced eight modules where the decision said
#: `punch` and the executor had no frame to place it on. The decision has to know
#: how much room it has, or it is a wish.
PUNCH_AT_MIN = 4

#: The accent score above which a word counts as *stressed*, used only when a
#: module has no accents at all to measure. `stress_line` is what is actually
#: called, because a single absolute number is the wrong shape for the question:
#: m09, m12, m15 and m20 have no card above 0.52 — their narration is quieter —
#: and those modules came out with every camera key easing `slow`, which the gate
#: correctly read as "no move answers the voice". A presenter does not carry a
#: decibel meter; they lean on the strongest word *in the paragraph they are
#: speaking*.
STRESS = 0.52

#: The share of a module's cards that may earn a hit. Five per cent of a
#: forty-card module is two: enough to make a point, few enough to mean one.
STRESS_SHARE = 0.05


def stress_line(accents: Sequence[float], share: float = STRESS_SHARE) -> float:
    """The emphasis line for *this* module, from its own accents.

    Relative, not absolute, and there is deliberately no floor under it. A floor
    looks prudent and is wrong in both directions: set high, it silences a quiet
    module completely (four of them, measured); set low, it is decoration. Relative
    means the loudest word in the paragraph always crosses the line — which is the
    claim being made: the presenter leans on the strongest word they have, and in a
    quiet paragraph that word is still the one worth a camera hit.
    """
    if not accents:
        return STRESS
    ordered = sorted(accents)
    at = max(0, min(len(ordered) - 1, int(round(len(ordered) * (1.0 - share)))))
    return ordered[at]


@dataclass(frozen=True, slots=True)
class Beat:
    """One scored accent, and everything the decision is allowed to see.

    Deliberately flat and cheap: the presenter must be able to answer without
    touching a pixel, so the same decision can be asserted on in a test.
    """

    #: `mark` (a stroke), `note` (a handwritten word), `card` (a piece arriving).
    kind: str = "mark"
    #: The gesture's shape, for a mark.
    shape: str = ""
    #: The word, for a note.
    text: str = ""
    #: What it lands on: `foto`, `cetak`, `koran`, `peta`, `figur`, `benda`, `seal`.
    bahan: str = "cetak"
    #: The card under the mark can be read, so a loud wash would hide it.
    readable: bool = False
    #: Things already on this page — pieces *and* strokes. A fifth piece needs the
    #: frame to open, not to close, so this is what `_move` reads.
    crowd: int = 0
    #: Hand-made marks already on this page. This is a *different* number and it
    #: was the bug: the vehicle question is "can the eye take another gesture?",
    #: which is about ink, not about how many photographs are underneath it.
    #: Counted as `crowd`, a page with four pieces and one arrow scored five, so
    #: `ink.register` stamped 83 notes out of 95 — the same over-correction as the
    #: old `len(word) > 8`, with the sign flipped.
    strokes: int = 0
    #: Something in this shot is already the emphasis. v2: one per shot.
    loud: bool = False
    #: Frames the beat has.
    duration: int = 0
    #: The previous beat in this shot already punched. Two punches in a row is
    #: not twice the emphasis, it is a camera having a fit.
    punched: bool = False
    #: The word under this beat is stressed (a high accent score). Only a stressed
    #: word earns a camera hit.
    stressed: bool = False
    #: The frame the hit would *start* on, if this beat gets one: the settle frame
    #: minus the hit's own runway (`rise + settle`). A hit needs
    #: `PUNCH_AT_MIN` frames of room before it; with less, the camera arrives
    #: instead of striking, and that is a decision rather than a failed execution.
    room: int = PUNCH_AT_MIN


@dataclass(frozen=True, slots=True)
class Decision:
    register: str
    color: str
    pen: str
    vehicle: str
    arrival: str
    move: str

    def as_dict(self) -> dict:
        return {
            "register": self.register, "color": self.color, "pen": self.pen,
            "vehicle": self.vehicle, "arrival": self.arrival, "move": self.move,
        }


def _register(beat: Beat) -> str:
    """What this beat is doing. Shape first, then the page's own hierarchy."""
    if beat.kind == "note":
        # A note is written because the voice leaned on a word that is not on the
        # page; it is an emphasis by definition, demoted only if something else
        # already is.
        return "support" if beat.loud else "emphasis"
    if beat.kind == "card":
        # A piece landing on a stressed word is the shot's emphasis. Without this
        # branch every card fell through to "support", so `_move` could never
        # answer `punch` and the punch decision was dead code: the film's only
        # camera hits came from `punch_for`, which fires on the first card and
        # knows nothing about the voice.
        if beat.stressed and not beat.loud:
            return "emphasis"
        return "name" if not beat.loud else "support"
    if beat.shape in ("strike", "cross"):
        return "correction"
    if beat.shape in ("circle", "box", "underline", "underline-double"):
        return "emphasis" if not beat.loud else "name"
    if beat.shape in ("brackets", "bracket-left", "bracket-right", "ellipse"):
        return "support"
    return "support"


def _arrival(beat: Beat, register: str) -> str:
    """How a card is placed, given what the beat is doing and what it is made of.

    A map cannot be snapped and a stamp cannot be unrolled — the material narrows
    the choice, but it does not make it. The beat decides the rest: something
    being named is *placed* deliberately; something arriving on a stressed word
    is *snapped*; a page already full takes the piece *dropped* in.
    """
    if beat.bahan == "peta":
        return "unrolled"
    if beat.bahan in ("figur", "benda"):
        # A cut-out is a light thing: it is dropped and skates, or snapped in.
        return "snapped" if register == "emphasis" else "dropped"
    if beat.bahan in ("cetak", "koran", "seal"):
        return "snapped" if register == "emphasis" else "placed"
    return "carried"


def _move(beat: Beat, register: str) -> str:
    """What the camera does — and the one field that makes the film feel directed.

    This is the answer to *"ga ada gerak liar, yg ada gerak kamera terukur yg
    sengaja dengan tujuan presentasi dan fokus penonton."* Three things keep it
    from becoming a lookup table:

    * **Memory.** A punch that follows a punch is not emphasis, it is a twitch.
      The second one becomes a `pull`, which is the camera doing something else
      useful instead of repeating itself.
    * **The page.** On a shot that already carries four gestures, the frame cannot
      get tighter without losing something, so the move opens (`pull`) rather
      than closes (`punch`).
    * **Reading.** Ink being laid down, or a line that must be read, gets `hold`.
      The camera has nothing to add and saying nothing is a choice.

    **A stroke never punches, and this is the important one.** The first version
    of this function gave every emphasis a punch, including the underlined word.
    The result was a fight the film could not win: `pin_pen_windows` freezes the
    frame from five frames before the pen touches, so every punch aimed at a
    marked word was deleted by the freeze — twice on m02 alone, caught by
    `program` rule 13. And even when it survived, a camera pushing in *while* a
    hand underlines the same word is two gestures pointing at one thing, which
    cancels them both.

    So the division is: **the pen emphasises by drawing, the camera emphasises by
    arriving.** A piece that lands on a stressed word gets the hit; a word that
    gets underlined gets a still frame to be read on.
    """
    if beat.kind in ("mark", "note"):
        return "hold"
    if beat.punched:
        return "pull" if beat.crowd >= 3 else "drift"
    if register == "correction":
        return "hold"
    if register == "emphasis" and beat.stressed:
        # A hit with no runway is not a hit. The camera still goes to the piece —
        # `arrive` is a steady push that ends on it — but it walks instead of
        # striking, which is what a piece landing on frame two deserves.
        return "punch" if beat.room >= PUNCH_AT_MIN else "arrive"
    if beat.crowd >= 4:
        return "pull"
    if register == "name":
        return "arrive"
    return "drift"


def settle_moves(beats: Sequence[tuple[int, int, str]], gap: int,
                 pen: Sequence[tuple[int, int]] = ()) -> list[str]:
    """Revise a shot's moves once they can be seen next to each other.

    `_move` answers for one accent and cannot see its neighbour, or the pen. Two
    things then delete a decision it made in good faith, and both are *correct*:

    * **Two hits inside `gap` frames are one hit.** The eye cannot register a hit,
      return, and hit again inside a second; the second is a stutter, not twice the
      emphasis.
    * **A hit inside a pen window does not survive.** `pin_pen_windows` freezes the
      frame for the whole stroke — the pen outranks the camera, because the viewer
      is following the ink — and the freeze replaces every key in the window,
      including the hit's.

    So a beat that cannot be performed is demoted to `arrive` here: the camera
    still goes to the piece, it just walks instead of striking. The alternative is
    an executor quietly dropping a decision, which is the fault the `program` gate
    calls "worse than no decision".

    `beats` is `(hit_start, settle, move)` in time order.
    """
    out: list[str] = []
    last: int | None = None
    for start, at, move in beats:
        if move != "punch":
            out.append(move)
            continue
        too_soon = last is not None and at - last < gap
        on_pen = any(start < hi and at > lo for lo, hi in pen)
        if too_soon or on_pen:
            out.append("arrive")
            continue
        last = at
        out.append(move)
    return out


def decide(beat: Beat) -> Decision:
    """The one decision. Everything downstream reads this and nothing re-decides.

    The order matters and is the whole point: the register is settled first,
    because a colour chosen before the register is a colour chosen by habit — which
    is how 465 marks ended up in two colours picked by array index.
    """
    register = _register(beat)
    tone = ink.resolve(register, beat.bahan,
                       declared_color="" if beat.kind != "mark" else "",
                       declared_pen="")
    vehicle = "write"
    if beat.kind == "note":
        vehicle = ink.register(beat.text, register, duration=beat.duration,
                               crowd=beat.strokes)
    return Decision(
        register=register,
        color=tone.color,
        pen=tone.pen,
        vehicle=vehicle,
        arrival=_arrival(beat, register),
        move=_move(beat, register),
    )
