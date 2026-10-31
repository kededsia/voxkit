"""The narration's own timings: where the voice lands, in frames.

Two tools used to answer "where does the voice lean" and they disagreed, so the
answer depended on which tool asked:

  * `accent.py` read `json["words"]` and scored each word by the pause before it,
    how long it was held *per syllable*, and the silence after it.
  * the choreographer read `json["segments"][i]["words"]` — a shape the
    transcriber stopped producing. It found zero words, so its scorer returned
    its default 0.45 for every card. Travel collapsed to one value, every camera
    ease collapsed to "slow", and no accent ever reached a render. The gate that
    checks accents used the other reader, so it passed. Twenty-two modules were
    built on a dead branch and every check was honest about the file it read.

The lesson is not "fix the key". It is that a single question gets a single
implementation. So this module is the only place a transcript is read, the only
place a word's accent is scored, and it refuses a transcript it cannot parse
instead of quietly returning an empty list.

Scoring, unchanged in substance from the version that measured well:

    pause before    the speaker takes a breath to lean on a word    0.45
    held            seconds per syllable against the module median  0.35
    tail after      the silence that makes a last word land         0.20

Each term is capped so one long silence cannot outrank a line that is actually
being leaned on. The result is a score in [0, 1]; `FLOOR` is the point above
which the voice is landing hard enough that a motion is *allowed* to answer it.
It never says a motion is required — that is the plan's decision.
"""
from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

FLOOR = 0.55            # at or above: the voice lands here; a motion may answer
SOFT = 0.40             # between SOFT and FLOOR: name it, explain it, do not skip
VOWELS = "aeiouy"


@dataclass(frozen=True, slots=True)
class Word:
    """One spoken word, measured. Frames are absolute in the module's audio."""

    text: str
    start: float
    end: float
    fps: int = 30

    @property
    def key(self) -> str:
        """The form a plan's `word` field is compared against: lowercase, no
        punctuation. `Cianjur,` and `cianjur` are the same word."""
        return normalise(self.text)

    @property
    def start_frame(self) -> int:
        return round(self.start * self.fps)

    @property
    def end_frame(self) -> int:
        return round(self.end * self.fps)

    @property
    def duration(self) -> float:
        return max(0.01, self.end - self.start)


@dataclass(frozen=True, slots=True)
class Accent:
    """A word plus the three numbers that make its stress measurable."""

    word: Word
    gap: float          # silence before it
    tail: float         # silence after it
    syllables: int
    rate: float         # seconds per syllable
    held: float         # this word's rate against the module's median
    score: float

    @property
    def lands(self) -> bool:
        return self.score >= FLOOR

    @property
    def soft(self) -> bool:
        return SOFT <= self.score < FLOOR


def normalise(text: str) -> str:
    return re.sub(r"[^\w]", "", (text or "")).lower()


def syllables(text: str) -> int:
    """Vowel groups. Indonesian glides are close enough for a rate, and a rate is
    all this is used for — 'mempertanggungjawabkan' is not stressed merely
    because it is long."""
    w = "".join(c for c in text.lower() if c.isalpha())
    if not w:
        return 1
    n, prev = 0, False
    for c in w:
        vowel = c in VOWELS
        if vowel and not prev:
            n += 1
        prev = vowel
    return max(1, n)


# ------------------------------------------------------------------- reading
def load(path: Path, fps: int = 30) -> tuple[list[Word], float]:
    """Read a transcript. Accepts the flat shape and the segmented one.

    Raises rather than returning an empty list: an empty word list is not a
    transcript with no words, it is a reader that did not understand the file,
    and every consumer downstream would then quietly fall back to a default.
    """
    if not path.is_file():
        raise FileNotFoundError(f"no transcript at {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: transcript is not an object")

    rows = raw.get("words")
    if not rows:
        # The segmented shape, if a transcriber ever produces it again.
        rows = [w for seg in (raw.get("segments") or []) for w in (seg.get("words") or [])]
    if not rows:
        keys = ", ".join(sorted(raw)) or "nothing"
        raise ValueError(
            f"{path.name}: no words found (keys: {keys}). "
            "A transcript must carry `words` or `segments[].words`."
        )

    words = []
    for i, w in enumerate(rows):
        try:
            words.append(Word(str(w["word"]).strip(), float(w["start"]), float(w["end"]), fps))
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"{path.name}: word {i} is malformed ({e}): {w!r}") from None

    total = float(raw.get("duration") or (words[-1].end if words else 0.0))
    return words, total


# ------------------------------------------------------------------ scoring
def analyse(words: Sequence[Word], total: float | None = None) -> list[Accent]:
    """Score every word. One implementation; the gates and the choreographer
    both call this, so they cannot disagree about which words are accented."""
    if not words:
        return []
    total = total if total is not None else words[-1].end
    rates = [w.duration / syllables(w.text) for w in words]
    median = statistics.median(rates) if rates else 0.2

    out: list[Accent] = []
    for i, w in enumerate(words):
        gap = w.start - words[i - 1].end if i else w.start
        tail = (words[i + 1].start - w.end) if i + 1 < len(words) else max(0.0, total - w.end)
        syl = syllables(w.text)
        rate = w.duration / syl
        held = rate / median if median else 1.0
        score = (min(max(gap, 0.0), 0.9) / 0.9 * 0.45
                 + min(max(held - 1.0, 0.0), 1.0) * 0.35
                 + min(max(tail, 0.0), 0.8) / 0.8 * 0.20)
        out.append(Accent(w, max(0.0, gap), max(0.0, tail), syl, rate, held,
                          round(min(1.0, max(0.0, score)), 4)))
    return out


class Narration:
    """The scored narration, with the lookups the pipeline actually makes."""

    def __init__(self, accents: Sequence[Accent], total: float, fps: int = 30) -> None:
        self.accents = list(accents)
        self.total = total
        self.fps = fps

    @classmethod
    def from_file(cls, path: Path, fps: int = 30) -> "Narration":
        words, total = load(path, fps)
        return cls(analyse(words, total), total, fps)

    # ------------------------------------------------------------- accessors
    @property
    def words(self) -> list[Word]:
        return [a.word for a in self.accents]

    @property
    def total_frames(self) -> int:
        return round(self.total * self.fps)

    def score(self, frame: int, word: str = "") -> float:
        """The accent score at a frame, preferring a word match.

        `frame` is absolute. With no word given, the nearest word wins; with a
        word, the nearest *occurrence of that word* wins. The old version
        returned a hardcoded 0.45 when nothing matched, which is how a broken
        reader became an invisible default instead of an error — so the neutral
        value here is the median of the real scores, not a constant.
        """
        if not self.accents:
            return 0.5
        target = normalise(word)
        pool = [a for a in self.accents if a.word.key == target] if target else []
        if not pool:
            pool = self.accents
        best = min(pool, key=lambda a: abs(a.word.start_frame - frame))
        return best.score

    def between(self, lo: int, hi: int) -> list[Accent]:
        return [a for a in self.accents if lo <= a.word.start_frame <= hi]

    def at(self, frame: int, tol: int = 2) -> list[Accent]:
        return [a for a in self.accents if abs(a.word.start_frame - frame) <= tol]

    def has_word(self, word: str) -> bool:
        target = normalise(word)
        return any(a.word.key == target for a in self.accents)

    def candidates(self, floor: float = FLOOR) -> list[Accent]:
        return [a for a in self.accents if a.score >= floor]


def frames_of(accents: Iterable[Accent]) -> list[int]:
    return [a.word.start_frame for a in accents]
