"""The plan contract: a typed model, one vocabulary, one placement parser.

A plan is an instruction set that costs money to execute — every card in it is a
generation, every still is a generation, every puppet frame is a generation. A
plan that *looks* complete but is not is the most expensive kind of mistake in
this pipeline, because the executor is faithful: it prints the strings it is
given, draws the numbers it is given, and puts the piece where it is told. When
the plan says `CAHI` for `cai`, the model draws `CAHI` perfectly.

So the plan is modelled here as types, and three things that used to be scattered
become single definitions:

1. **One vocabulary.** Which materials exist, which of them a viewer must be able
   to READ, and what each physical form's aspect ratio is. Previously the aspect
   table lived only inside the storyboard renderer, so a `wujud` the table did not
   know silently got 0.7 and every overlap number derived from it was wrong.

2. **One placement parser.** `at` is prose because it also feeds the image prompt
   ("lower left of the frame, centred at 0.20 across, about 0.32 of the frame
   wide"). Two tools parsed it with two regexes and both returned `None` on a
   shape they did not expect — which the callers read as "no constraint" rather
   than "I did not understand you". Here an unparseable `at` is a hard failure.

3. **One aspect conversion.** A card's height in frame fractions is
   `w * aspect * (stage_w / stage_h)`. The board used `w * aspect` and therefore
   under-reported every overlap by the stage ratio: a pair 63 % buried read as
   34 %, and a 63 % burial passed in a shipped module.

Nothing in this file knows a module id or a film length.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .geometry import Rect

# --------------------------------------------------------------- vocabulary
# Materials a piece can be made of. `READABLE` materials carry words or figures a
# viewer has to read; `COVERING` materials are physical things that can lie on
# top of them. The camera moves layers by different amounts, so a readable card
# that is merely beside a photograph in the still can be under it by frame 300 —
# the rule is blunt on purpose: readable above covering, always.
BAHAN = {
    "foto": "halftone photograph, a clipping",
    "cetak": "printed card, slip, label or placard",
    "koran": "newsprint strip, a number to be read",
    "figur": "cut-out person",
    "benda": "physical object: stamp, tool, specimen",
    "peta": "printed map or survey sheet",
    "seal": "wax seal, the closing mark",
}
READABLE = frozenset({"cetak", "koran", "peta"})
COVERING = frozenset({"foto", "figur", "benda", "seal"})

JENIS = frozenset({"PLACE", "OBJECT", "DIAGRAM", "SUBJECT", "QUANTITY",
                   "PROCESS", "TIME", "ACTION"})

# Physical form -> height/width in PIXELS. Two cards the same width are not the
# same height, and a board that assumes they are cannot tell a slip from a plate.
WUJUD = {
    "sobekan_pita": 0.44,
    "siluet_organik": 0.86,
    "plang_fisik": 0.70,
    "segel_lilin": 0.55,
}

# Values that read as "someone will fill this in later". None of them ever were.
PLACEHOLDER = frozenset({"", "-", "--", "?", "tbd", "todo", "n/a", "na", "true",
                         "false", "yes", "no", "ok", "x", "…", "..."})

# How far a card flies in, in frames. The choreographer picks from this range by
# how accented the word it lands on is; a mark may not start before the card has
# begun to arrive.
TRAVEL_MIN, TRAVEL_MAX = 14, 21
ARRIVE_EARLY, ARRIVE_LATE = -6, 9
MIN_ARRIVAL_GAP = 3

#: The prose is compositional — a vertical word and a horizontal word — so the
#: default height is read from the vertical one, not from a table of whole
#: phrases. A table of exact strings would reject "upper centre", "lower centre
#: left" and "the middle" for being phrased differently from the row someone
#: happened to write first, and a parser that fails good prose fails for the
#: wrong reason. Ordered: "lower centre" contains "centre".
VERTICAL = (
    ("bottom", 0.86),
    ("lower", 0.68),
    ("upper", 0.33),
    ("top", 0.14),
    ("centre", 0.50),
    ("center", 0.50),
    ("middle", 0.50),
)
HORIZONTAL_ONLY = ("left", "right")


def default_down(region: str) -> float | None:
    """The centre-down a region implies, or None when the region says nothing.

    A region that names only a side ("right of the frame") is vertically centred:
    that is what the phrase means, and it is what the stills were drawn to.
    """
    low = region.lower()
    for word, value in VERTICAL:
        if word in low:
            return value
    return 0.50 if any(w in low for w in HORIZONTAL_ONLY) else None


# ------------------------------------------------------------------ findings
LEVELS = ("fail", "warn", "note")


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing wrong, in the terms a person can act on.

    Findings are data, not print statements: a gate returns them, the runner
    sorts them, the CLI decides what to show. A gate that printed as it went
    could not be tested, counted or cached.
    """

    gate: str
    where: str
    message: str
    level: str = "fail"

    def __str__(self) -> str:
        tag = {"fail": "FAIL", "warn": "WARN", "note": "NOTE"}[self.level]
        return f"{tag}  {self.where}: {self.message}"


def fail(gate: str, where: str, message: str) -> Finding:
    return Finding(gate, where, message, "fail")


def warn(gate: str, where: str, message: str) -> Finding:
    return Finding(gate, where, message, "warn")


def note(gate: str, where: str, message: str) -> Finding:
    return Finding(gate, where, message, "note")


# --------------------------------------------------------------- placement
@dataclass(frozen=True, slots=True)
class Placement:
    """Where a card sits, in frame fractions, read from its `at` prose.

    `cx` is the centre across, `w` the width; `cy` the centre down and `h` the
    height. `h` is derived from `w` and the card's physical form unless the prose
    states it, because a plan is written about a piece, not about pixels.
    """

    cx: float
    cy: float
    w: float
    h: float
    region: str = ""
    stated_down: bool = False

    def rect(self) -> Rect:
        return Rect.from_centre(self.cx, self.cy, self.w, self.h)


def parse_placement(at: str, aspect: float, stage_aspect: float) -> Placement:
    """Read `at` prose into numbers, or raise.

    The prose forms in use:

        "lower left of the frame, centred at 0.20 across, about 0.32 of the frame wide"
        "... about 0.32 of the frame wide, down at 0.41"
        "centre of the frame, centred at 0.50 across, about 0.60 of the frame wide"

    `down at 0.41` states the centre down explicitly. Without it the region
    decides: `upper` 0.33, `lower` 0.68, `bottom` 0.86, `centre` 0.50.

    Height is `w * aspect * stage_aspect` — the conversion the board used to get
    wrong by omitting `stage_aspect`, which made every card it drew 44 % too
    short and every overlap it reported too small to trip its own threshold.
    """
    if not isinstance(at, str) or not at.strip():
        raise ValueError("placement is empty")

    low = at.lower()
    cx = _first(r"centred at\s+([\d.]+)\s+across", low)
    w = _first(r"about\s+([\d.]+)\s+of the frame wide", low) or _first(r"([\d.]+)\s+wide", low)
    if cx is None:
        raise ValueError("no 'centred at <x> across' — the horizontal centre is not stated")
    if w is None:
        raise ValueError("no 'about <w> of the frame wide' — the width is not stated")

    region = re.split(r",\s*centred at", low)[0].strip()
    region = re.sub(r"\s+of the frame$", "", region).strip()

    down = _first(r"down at\s+([\d.]+)", low)
    stated = down is not None
    if down is None:
        down = default_down(region)
        if down is None:
            raise ValueError(
                f"region '{region}' names no height and no 'down at <y>' is given"
            )

    tall = _first(r"about\s+([\d.]+)\s+of the frame tall", low)
    h = tall if tall is not None else w * aspect * stage_aspect
    return Placement(cx=cx, cy=down, w=w, h=h, region=region, stated_down=stated)


def _first(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


# -------------------------------------------------------------------- marks
@dataclass(frozen=True, slots=True)
class Mark:
    """A hand-drawn gesture. `[shape, duration, rotate, card, opts]` in the file.

    A mark is evidence of a hand, so it is a gesture with a speed and an angle —
    not a boolean. Six labels each getting their own underline is six marks doing
    six jobs; two page marks with the same shape and duration are one gesture
    printed twice, and the eye reads that as a machine.
    """

    shape: str
    duration: int
    rotate: float
    card: str
    at: int | None = None
    box: tuple[float, float, float, float] | None = None
    color: str | None = None
    pen: str = "marker"
    motion: str = "draw"
    sw: int | None = None

    @property
    def bound(self) -> bool:
        """Bound to a card's frame, so the repetition rule does not apply."""
        return self.box is None


# -------------------------------------------------------------------- cards
@dataclass(frozen=True, slots=True)
class Card:
    name: str
    z: int
    bahan: str
    wujud: str
    semantik: str
    semiotik: str
    what: str
    at: str
    lands: int
    word: str
    placement: Placement
    poses_planned: tuple[dict, ...] = ()
    head: Sequence[float] | bool | None = None
    erase: tuple = ()
    hint: tuple | None = None
    fresh: bool = False
    tertutup_boleh: bool = False
    tertutup_alasan: str = ""
    motion_basis: str = ""
    cut: bool = False

    @property
    def readable(self) -> bool:
        return self.bahan in READABLE

    @property
    def covering(self) -> bool:
        return self.bahan in COVERING

    @property
    def rect(self) -> Rect:
        return self.placement.rect()


@dataclass(frozen=True, slots=True)
class Shot:
    id: str
    start: int
    end: int
    babak: str
    peran_retoris: str
    latar_plate: str
    tata_letak_kolase: str
    jenis: str
    mark: str
    marks: tuple[Mark, ...]
    kamera: str
    cards: tuple[Card, ...]
    script: dict | None = None
    still_gate: str = ""
    emphasis: tuple = ()

    @property
    def span(self) -> int:
        return self.end - self.start

    def card(self, name: str) -> Card | None:
        return next((c for c in self.cards if c.name == name), None)

    def ordered(self) -> list[Card]:
        return sorted(self.cards, key=lambda c: (c.z, c.name))

    def arrivals(self) -> list[tuple[Card, int]]:
        """Absolute frames at which each card settles. `lands` is relative to the
        shot's own start, not to the film — a plan written in film frames fails
        every arrival check by the length of the module before it."""
        return [(c, self.start + c.lands) for c in self.ordered()]


@dataclass(frozen=True, slots=True)
class Plan:
    module: str
    shots: tuple[Shot, ...]
    klaim: str = ""
    payoff: str = ""
    serah: str = ""
    terima: str = ""
    konteks_modul: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)
    plan_version: int = 2
    stage_aspect: float = 1920 / 1080
    path: Path | None = None
    #: Structural faults found while building the model. Collected rather than
    #: raised so a plan with four problems reports four, not one per round of
    #: editing.
    problems: tuple[Finding, ...] = ()
    #: The plan's own bytes, canonicalised. The gate cache is keyed on it: every
    #: gate reads the plan, so a plan that changed must invalidate every gate —
    #: and a plan built in memory has no file path to hash.
    source: str = ""

    # ------------------------------------------------------------- accessors
    @property
    def duration(self) -> int:
        return max((s.end for s in self.shots), default=0)

    @property
    def cards(self) -> list[Card]:
        return [c for s in self.shots for c in s.cards]

    def shot(self, sid: str) -> Shot | None:
        return next((s for s in self.shots if s.id == sid), None)

    def shot_at(self, frame: int) -> Shot | None:
        return next((s for s in self.shots if s.start <= frame < s.end), None)

    # ---------------------------------------------------------------- loading
    @classmethod
    def load(cls, path: Path, stage_aspect: float = 1920 / 1080) -> "Plan":
        if not path.is_file():
            raise FileNotFoundError(f"no plan at {path}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path.name}: not valid JSON ({e})") from None
        return cls.from_dict(raw, stage_aspect=stage_aspect, path=path)

    @classmethod
    def from_dict(cls, raw: dict, *, stage_aspect: float = 1920 / 1080,
                  path: Path | None = None) -> "Plan":
        """Build the model, collecting every structural fault instead of dying on
        the first one. A plan with four problems should report four, not one per
        round of editing."""
        problems: list[Finding] = []
        module = str(raw.get("module") or (path.stem if path else ""))
        shots: list[Shot] = []

        for si, s in enumerate(raw.get("shots") or []):
            sid = str(s.get("id") or f"s{si + 1:02d}")
            rng = s.get("range")
            if not (isinstance(rng, list) and len(rng) == 2
                    and all(isinstance(v, int) for v in rng)):
                problems.append(fail("schema", f"{sid}", "range is not [start, end]"))
                rng = [0, 0]

            cards: list[Card] = []
            for c in s.get("cards") or []:
                card = _card(c, sid, stage_aspect, problems)
                if card is not None:
                    cards.append(card)

            shots.append(Shot(
                id=sid, start=rng[0], end=rng[1],
                babak=str(s.get("babak") or ""),
                peran_retoris=str(s.get("peran_retoris") or ""),
                latar_plate=str(s.get("latar_plate") or ""),
                tata_letak_kolase=str(s.get("tata_letak_kolase") or ""),
                jenis=str(s.get("jenis") or ""),
                mark=str(s.get("mark") or ""),
                marks=_marks(s.get("marks") or [], sid, problems),
                kamera=str(s.get("kamera") or ""),
                cards=tuple(cards),
                script=s.get("script") if isinstance(s.get("script"), dict) else None,
                still_gate=str(s.get("still_gate") or ""),
                emphasis=tuple(s.get("emphasis") or ()),
            ))

        plan = cls(
            module=module, shots=tuple(shots),
            klaim=str(raw.get("klaim") or ""),
            payoff=str(raw.get("payoff") or ""),
            serah=str(raw.get("serah") or ""),
            terima=str(raw.get("terima") or ""),
            konteks_modul=raw.get("konteks_modul") or {},
            context=raw.get("context") or {},
            plan_version=int(raw.get("plan_version") or 0),
            stage_aspect=stage_aspect, path=path,
            problems=tuple(problems),
            source=json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str),
        )
        return plan

    def load_problems(self) -> list[Finding]:
        return list(self.problems)


def _card(c: dict, sid: str, stage_aspect: float, problems: list[Finding]) -> Card | None:
    name = str(c.get("name") or "")
    where = f"{sid}/{name or '?'}"
    if not name:
        problems.append(fail("schema", sid, "a card has no name"))
        return None

    wujud = str(c.get("wujud") or "")
    if wujud not in WUJUD:
        # Hard failure, not a default. The old board defaulted to 0.7 and then
        # measured every overlap with it.
        problems.append(fail(
            "schema", where,
            f"wujud '{wujud}' is not a known physical form ({', '.join(sorted(WUJUD))}); "
            f"its height cannot be derived and every overlap it takes part in would be a guess"
        ))
        aspect = WUJUD["plang_fisik"]
    else:
        aspect = WUJUD[wujud]

    bahan = str(c.get("bahan") or "")
    if bahan not in BAHAN:
        problems.append(fail("schema", where,
                             f"bahan '{bahan}' is not one of {', '.join(sorted(BAHAN))}"))

    at = str(c.get("at") or "")
    try:
        placement = parse_placement(at, aspect, stage_aspect)
    except ValueError as e:
        problems.append(fail("schema", where, f"`at` cannot be read: {e} — '{at[:80]}'"))
        placement = Placement(0.5, 0.5, 0.2, 0.2 * aspect * stage_aspect, region="?")

    return Card(
        name=name,
        z=int(c.get("z") or 0),
        bahan=bahan, wujud=wujud,
        semantik=str(c.get("semantik") or ""),
        semiotik=str(c.get("semiotik") or ""),
        what=str(c.get("what") or ""),
        at=at,
        lands=int(c.get("lands") or 0),
        word=str(c.get("word") or ""),
        placement=placement,
        poses_planned=tuple(c.get("poses_planned") or ()),
        head=c.get("head"),
        erase=tuple(c.get("erase") or ()),
        hint=tuple(c["hint"]) if isinstance(c.get("hint"), (list, tuple)) else None,
        fresh=bool(c.get("fresh")),
        tertutup_boleh=bool(c.get("tertutup_boleh")),
        tertutup_alasan=str(c.get("tertutup_alasan") or ""),
        motion_basis=str(c.get("motion_basis") or ""),
        cut=bool(c.get("cut")),
    )


def _marks(raw: Sequence, sid: str, problems: list[Finding]) -> tuple[Mark, ...]:
    out: list[Mark] = []
    for i, m in enumerate(raw):
        if not (isinstance(m, (list, tuple)) and len(m) >= 4):
            problems.append(fail("schema", sid,
                                 f"marks[{i}] is not [shape, duration, rotate, card, opts]"))
            continue
        opt = m[4] if len(m) > 4 and isinstance(m[4], dict) else {}
        box = opt.get("box")
        if box is not None:
            if not (isinstance(box, (list, tuple)) and len(box) == 4):
                problems.append(fail("schema", sid, f"marks[{i}] box is not [x0,y0,x1,y1]"))
                box = None
            else:
                box = tuple(float(v) for v in box)
        out.append(Mark(
            shape=str(m[0]),
            duration=int(m[1]) if isinstance(m[1], int) else 0,
            rotate=float(m[2]) if isinstance(m[2], (int, float)) else 0.0,
            card=str(m[3]),
            at=int(opt["at"]) if isinstance(opt.get("at"), int) else None,
            box=box,
            color=opt.get("color"),
            pen=str(opt.get("pen", "marker")),
            motion=str(opt.get("motion", "draw")),
            sw=opt.get("sw"),
        ))
    return tuple(out)


# ---------------------------------------------------------------- helpers
def words_in(text: str) -> int:
    return len(re.findall(r"[A-Za-zÀ-ÿ0-9]+", text))


def is_placeholder(value: Any) -> bool:
    return not isinstance(value, str) or value.strip().lower() in PLACEHOLDER


def tile(shots: Iterable[Shot], duration: int) -> list[Finding]:
    """Shots must tile the film exactly: no gap, no overlap, no short ending.

    A gap is a black frame nobody planned; an overlap is two shots fighting for
    the same moment. Both read as a broken cut, and neither is visible in any
    single shot's own numbers.
    """
    out: list[Finding] = []
    ordered = sorted(shots, key=lambda s: s.start)
    if not ordered:
        return [fail("ranges", "-", "no shots")]
    if ordered[0].start != 0:
        out.append(fail("ranges", ordered[0].id,
                        f"the film starts at f{ordered[0].start}, not f0"))
    for a, b in zip(ordered, ordered[1:]):
        if b.start < a.end:
            out.append(fail("ranges", f"{a.id}->{b.id}",
                            f"{a.id} ends at f{a.end} but {b.id} starts at f{b.start} "
                            f"— {a.end - b.start} frames belong to both"))
        elif b.start > a.end:
            out.append(fail("ranges", f"{a.id}->{b.id}",
                            f"{b.start - a.end} frame(s) between f{a.end} and f{b.start} "
                            f"belong to no shot"))
    if duration and ordered[-1].end != duration:
        out.append(fail("ranges", ordered[-1].id,
                        f"the last shot ends at f{ordered[-1].end} but the narration is "
                        f"f{duration} — the film would end early or hang"))
    return out
