"""Prompts, derived from the plan.

A prompt is not written, it is compiled: the pieces, their places and their
materials are all in the plan, so a prompt that disagrees with the plan is a bug
with a mechanical cause and a mechanical fix. The one thing a prompt must not do
is carry the plan's own bookkeeping into the picture — a still has no "z", no
"lands", no frame numbers, and telling the model about them spends characters on
things it cannot draw.

Two rules earned the hard way:

  * the piece list names the *physical* thing, never the role ("a seated elder",
    not "the subject"), because a role is not drawable;
  * one composition law rides in every still prompt — no card across a face — 
    because it is the only fault the pipeline cannot repair afterwards: a card
    cannot be moved (it must land on its own print), a figure cannot be put on
    top (the card that gets read sits above every figure), and a rebuilt still
    shows the plate's filled holes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .contract import BAHAN, Card, Plan, Shot, words_in

MAX_PROMPT = 1950          # the backend caps at 2000; the margin is for the wrapper

#: The one case "every other clipping becomes the ground" cannot answer: the other
#: clipping is *on top of* this piece, so removing it means inventing what is
#: underneath. The model's default is to keep that sheet and leave it blank.
OVERLAP = (
    "If another clipping lies across this piece, it is not part of it: take it away "
    "completely, and where it was continue this piece's own surface — its paper, its "
    "print, its photograph. Never leave a blank patch of the other clipping's paper."
)

STYLE = (
    "STYLE: copy the TREATMENT of the attached style key — hand-cut editorial zine PAPER "
    "COLLAGE: bold flat colour blocks, torn newsprint edges, masking tape, coarse "
    "sepia/charcoal halftone (zero green/blue), real paper drop shadows. Pieces are "
    "scissor-cut organic silhouettes with a rough white border. Vary them: most in warm "
    "sepia, some in aged-newsprint one-ink monochrome — never all cold, never modern "
    "digital colour. Do not copy the reference words or subjects."
)

# Material -> how the prompt names it. Deterministic, from `bahan`, because
# deriving the kind from prose was a second opinion that disagreed with the field
# the whole build obeys.
MATERIAL = {
    "foto": "torn halftone photograph",
    "cetak": "printed slip",
    "koran": "newsprint strip",
    "figur": "cut-out figure",
    "benda": "cut-out object",
    "peta": "printed map sheet",
    "seal": "wax seal",
}


@dataclass(frozen=True, slots=True)
class Quotas:
    """The shares a module must hold. Calibrated on the version a client approved,
    not on taste: photographs and figures carry the page, and a module that drifts
    into typography is a board of signs."""

    photo_figure_min: float = 0.40
    figure_min: float = 0.14
    type_max: float = 0.55


def kind(card: Card) -> str:
    return {"foto": "photo", "figur": "figure", "cetak": "type", "koran": "type",
            "peta": "type", "benda": "other", "seal": "other"}.get(card.bahan, "other")


def shares(plan: Plan) -> dict[str, float]:
    cards = plan.cards
    if not cards:
        return {}
    kinds = [kind(c) for c in cards]
    n = len(kinds)
    return {
        "photo_figure": (kinds.count("photo") + kinds.count("figure")) / n,
        "figure": kinds.count("figure") / n,
        "type": kinds.count("type") / n,
        "n": float(n),
    }


def quota_problems(plan: Plan, quotas: Quotas | None = None) -> list[str]:
    q = quotas or Quotas()
    s = shares(plan)
    if not s:
        return ["the plan has no cards"]
    out = []
    if s["photo_figure"] < q.photo_figure_min:
        out.append(f"{s['photo_figure']:.0%} of the pieces are a photograph or a figure, "
                   f"under the {q.photo_figure_min:.0%} floor — the page would be signs")
    if s["figure"] < q.figure_min:
        out.append(f"{s['figure']:.0%} of the pieces are a figure, under the "
                   f"{q.figure_min:.0%} floor — nobody is in the film")
    if s["type"] > q.type_max:
        out.append(f"{s['type']:.0%} of the pieces are printed matter, over the "
                   f"{q.type_max:.0%} ceiling")
    return out


# ------------------------------------------------------------------- prompts
def _place(card: Card) -> str:
    """Where the piece sits, in the terms the model can act on.

    The frame is the only thing a still has, so "of the frame" is spent characters
    saying nothing; six pieces a shot is a third of the budget. `down at` is kept
    when the plan stated it, because that is the one placement the model gets
    wrong by default — everything else drifts to the middle.
    """
    p = card.placement
    where = p.region or "centre"
    out = f"{where}, {p.cx:.2f} across, {p.w:.2f} wide"
    if p.stated_down:
        out += f", {p.cy:.2f} down"
    return out


def still_prompt(plan: Plan, shot: Shot, style: str = STYLE) -> str:
    """Compile a still from the shot's own plan fields.

    The cap is a *guarantee*, not a hope. gflow rejects a batch whose any prompt is
    over 2000 characters — the whole batch, not the one row — so an over-long
    prompt does not lose one still, it loses five and stops the module. m17 and
    m18 died exactly that way: 2146 characters, and the trim only knew how to
    shorten the shot's prose, which was not where the length was.

    So the budget is spent in order of what the model can most afford to lose:
    the shot's mood prose first, then every piece's description in equal measure.
    A piece's `z` and placement are composition facts and are never cut — losing
    one of those loses a subject from the page, which costs a redraw instead of a
    word.
    """
    cards = shot.ordered()
    photos = sum(1 for c in cards if kind(c) == "photo")
    figures = sum(1 for c in cards if kind(c) == "figure")
    demand = []
    if photos:
        demand.append(f"{photos} torn halftone photograph" + ("s" if photos > 1 else ""))
    if figures:
        demand.append(f"{figures} cut-out figure" + ("s" if figures > 1 else ""))
    carry = (" and ".join(demand) + " carry the page. ") if demand else "the pieces carry the page. "

    p1 = f"Irregular Vox zine collage: {shot.latar_plate.strip()} {shot.tata_letak_kolase.strip()}"
    p3 = ("CLIPPING collage, not a board of signs: " + carry +
          "No captions, cutlines or text under photos. Cut-outs are organic silhouettes, "
          "never photo boxes. No slip may cross a face, a head or a neck.")

    def compose(whats: list[str], prose: str) -> str:
        pieces = " ".join(f"(z{c.z}, {_place(c)}) {w.strip().rstrip('.')}."
                          for c, w in zip(cards, whats))
        return f"{prose}\n\nCut-out pieces: {pieces}\n\n{p3}\n\n{style}"

    whats = [c.what for c in cards]
    text = compose(whats, p1)
    if len(text) <= MAX_PROMPT:
        return text

    # 1. the prose the author wrote about the page as a whole
    p1 = _shorten(p1, len(text) - MAX_PROMPT + 40)
    text = compose(whats, p1)
    if len(text) <= MAX_PROMPT:
        return text

    # 2. every piece, by the same share. Cutting one piece to nothing to save
    #    another is how a page quietly loses its subject.
    over = len(text) - MAX_PROMPT + 20
    share = over // max(1, len(whats)) + 1
    whats = [_cut(w, share) for w in whats]
    text = compose(whats, p1)
    # 3. and if a page is still over — six pieces with long names — the last
    #    resort is a hard cut. An over-long prompt is not sent at all, so a
    #    truncated page beats a module that never builds.
    return text[:MAX_PROMPT]


def _cut(text: str, by: int) -> str:
    """Drop `by` characters from the end of a description, at a word boundary."""
    if by <= 0 or len(text) <= by + 20:
        return text
    head = text[:len(text) - by]
    space = head.rfind(" ")
    return (head[:space] if space > 20 else head).rstrip(" ,;:-")


def _shorten(text: str, by: int) -> str:
    if by <= 0:
        return text
    cut = text.rfind(". ", 0, max(40, len(text) - by))
    return text[:cut + 1] if cut > 40 else text


def iso_prompt(card: Card, chroma: str = "#FF00FF", cropped: bool = False) -> str:
    """Isolate one piece. Never "crop": a crop carries its neighbours.

    The first version named the piece but never said where it was, and nineteen
    pieces across six modules came back as the whole page — the model was asked to
    find one clipping among five on a page of halftone newsprint with nothing but
    a description to go on. A locator costs thirty characters and removes the
    guess. The page is named too, so "remove the page" is a thing it can obey.

    `cropped` is for the pieces that still failed: the reference is then a close
    crop around the piece, so the prompt must say the frame is small and the piece
    is the one in the middle — otherwise "the attached collage page" is a lie and
    the model returns the crop's whole collage.

    `OVERLAP` is the third version, and it is the answer to a fault that reached a
    render. "Every other clipping becomes the chroma ground" tells the model what
    to delete, never what to *put there* — and when the other clipping lies across
    this piece, deleting it means inventing what is underneath. The model does not
    invent: it keeps the other clipping's sheet and leaves it blank, letters gone.
    Two identical cards then sit on the page, the one behind offset by however far
    the model drifted. Saying the case out loud is what a prompt can do about it;
    `gates/assets.double` measures whether it worked.
    """
    p = card.placement
    where = f"{p.region}, about {p.cx:.0%} across and {p.cy:.0%} down" if p.region \
        else f"about {p.cx:.0%} across and {p.cy:.0%} down"
    if cropped:
        text = (
            f"The attached image is a close crop of a collage page. It contains one "
            f"piece to isolate: {card.what.strip().rstrip('.')}, near the centre. "
            f"Return only that piece, on pure flat {chroma}: the paper it lies on, "
            f"the paper edge of the crop, every other clipping and every shadow "
            f"become {chroma}. {OVERLAP} "
            f"Keep the piece at the same scale, rotation and ink. "
            f"If it is a printed card, return only that card's own block of paper. "
            f"Do not add, redraw, enlarge, move or re-letter anything."
        )
    else:
        text = (
            f"In the attached collage page, isolate ONE piece: the one that is "
            f"{card.what.strip().rstrip('.')}, located {where}. "
            f"Return only that piece, on pure flat {chroma}: the page behind it, every "
            f"other clipping, every shadow and all page text become {chroma}. "
            f"{OVERLAP} "
            f"Keep the piece at the exact same position, scale, rotation and ink. "
            f"If it is a printed card, return only that card's own block of paper — not the "
            f"page it was printed on and not any neighbouring text. "
            f"It keeps its own torn edge and its own printed detail. Do not add, redraw, "
            f"enlarge, move or re-letter anything."
        )
    if len(text) > MAX_PROMPT:
        text = _shorten(text, len(text) - MAX_PROMPT + 40)
    return text


def pose_prompt(card: Card, action: str, chroma: str = "#FF00FF") -> str:
    """One readable gesture on the same cut-out, on the same ground."""
    return (
        f"Keep this exact same isolated collage cut-out subject, face, clothing, coarse "
        f"halftone print texture, rough white paper border, and solid {chroma} background "
        f"at the exact same position and scale, changing ONLY the pose: {action}. "
        f"The change is one readable gesture — a hand, a turned head, a shoulder, a step — "
        f"everything else in the figure stays where it is. Do not add any object, text or "
        f"background element; keep everything outside the cut-out pure flat {chroma}."
    )


def fill_prompt(shot: Shot, ground: str, chroma: str = "#FF00FF") -> str:
    """Close the page behind the pieces that were lifted.

    The gap reveals the ground that was behind the piece; it is never filled with
    a different object on the same ground. "Kalau ada ruang kosong blur … nano
    banana akan otomatis isi itu dengan object baru" was the client's instruction,
    and it is the opposite of what a solved hole produces: a blur.
    """
    names = "; ".join(c.what.strip().rstrip(".") for c in shot.ordered())
    return (
        f"Remove these {len(shot.cards)} pieces completely: {names} — including anyone "
        f"standing with their back to us.\n\n"
        f"Then close the page behind them, as if those pieces had never been pasted "
        f"there. The print has to run straight through the places they covered — the same "
        f"ruled columns, the same newsprint text, the same halftone dots, the same paper "
        f"grain, unbroken, at the same ink and the same tone. What is behind them is "
        f"{ground}.\n\n"
        f"Do not leave blank paper where a piece was: no empty cream rectangle, no pale "
        f"outline or silhouette of the removed piece, no sheet with a printed border. Do "
        f"not paste anything new — no clippings, no labels, no slips, no tape. No copies "
        f"of what was removed, no grey shadows of them.\n\n"
        f"Everything else stays exactly as it is — same paper, same grain, same crop, "
        f"same shadows."
    )


def over_length(plan: Plan) -> list[tuple[str, int]]:
    """Shots whose compiled prompt is over the cap. Reported before a batch is
    paid for, because a prompt that is cut off is worse than one that names less."""
    out = []
    for shot in plan.shots:
        n = len(still_prompt(plan, shot))
        if n > MAX_PROMPT:
            out.append((shot.id, n))
    return out
