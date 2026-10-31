"""Language layer: what the narration *says*, in the narration's language.

Two checks depend on this and neither can be language-neutral:

  * a card that prints a figure has to print a figure the voice says — and the
    voice says "seribu lima ratus", never `1.500`;
  * a card's printed words have to be words the narration uses, minus the
    function words a card may join its own keywords with.

Comparing digits against a transcript reported every honest number as invented:
m01's elevation, m02's distance, the `dua huruf` of m01 s03. A checker that
fails the right answer is worse than none, so the numbers are converted here.

Adding a language is one class. Nothing else in the engine knows which one is in
use — the project's `vox.toml` names it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


class Language(Protocol):
    code: str
    stopwords: frozenset[str]

    def numbers(self, text: str) -> set[str]:
        """Every figure the text says, as digit strings."""

    def words(self, text: str) -> set[str]:
        """Every word the text says, normalised."""


@dataclass(frozen=True, slots=True)
class Indonesian:
    """Indonesian numerals as spoken, plus the function words a card may use.

    Ordinals are handled separately because "kelima" is a whole figure on its own
    and must not be folded into a running total: `abad kelima Masehi` is the
    number 5, and reading it as part of a larger sum made an honest card look
    invented.
    """

    code: str = "id"

    DIGITS = {"nol": 0, "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5,
              "enam": 6, "tujuh": 7, "delapan": 8, "sembilan": 9}
    SE = {"sepuluh": "satu puluh", "sebelas": "satu belas", "seratus": "satu ratus",
          "seribu": "satu ribu", "sejuta": "satu juta"}
    ORDINAL = {**{f"ke{w}": n for w, n in DIGITS.items()}, "kesepuluh": 10,
               "kesebelas": 11}

    # A card joins its own keywords with these without the narration ever saying
    # them. Everything else is expected to be sayable.
    stopwords: frozenset[str] = frozenset({
        "dan", "atau", "yang", "di", "ke", "dari", "itu", "ini", "ada", "tidak",
        "bukan", "dengan", "untuk", "pada", "dalam", "juga", "sudah", "akan",
        "bisa", "kata", "sehari", "hari", "kab", "kec", "no", "hal", "jl",
    })

    def numbers(self, text: str) -> set[str]:
        """Digit strings the text says, whether written as digits or as words.

        The transcriber splits figures on the space — `8 .848`, `17 .000` — so a
        run of digits separated only by spaces, dots or commas is glued back
        before it is compared. Without that, every figure in the film reads as
        "not in the narration".
        """
        out: set[str] = set()
        for m in re.finditer(r"\d[\d\s.,]*\d|\d", text):
            digits = re.sub(r"[^\d]", "", m.group(0))
            if digits:
                out.add(digits)
        out |= self._spoken(text)
        return out

    def _spoken(self, text: str) -> set[str]:
        toks: list[str] = []
        out: set[str] = set()
        for t in re.findall(r"[a-z]+", text.lower()):
            if t in self.ORDINAL:
                out.add(str(self.ORDINAL[t]))
                continue
            toks.extend(self.SE.get(t, t).split())

        value = section = 0
        seen = False
        for t in toks:
            if t in self.DIGITS:
                section += self.DIGITS[t]
                seen = True
            elif t == "puluh":
                section = max(section, 1) * 10
                seen = True
            elif t == "ratus":
                section = max(section, 1) * 100
                seen = True
            elif t == "belas":
                section += 10
                seen = True
            elif t in ("ribu", "juta"):
                value += max(section, 1) * (1000 if t == "ribu" else 1_000_000)
                section = 0
                seen = True
            elif seen:
                out.add(str(value + section))
                value = section = 0
                seen = False
        if seen:
            out.add(str(value + section))
        return out

    def words(self, text: str) -> set[str]:
        return {w for w in (normalise(t) for t in re.findall(r"[\w'’-]+", text)) if w}


LANGUAGES: dict[str, Language] = {"id": Indonesian()}
DEFAULT = "id"


def get(code: str | None) -> Language:
    """The language named by the project, or the default. An unknown code is a
    configuration error, not a silent fallback — every check downstream would
    quietly do the wrong thing."""
    key = (code or DEFAULT).lower()
    if key not in LANGUAGES:
        raise KeyError(f"no language layer for {key!r}; known: {', '.join(sorted(LANGUAGES))}")
    return LANGUAGES[key]


def normalise(text: str) -> str:
    """Lowercase, no punctuation. `Cianjur,` and `cianjur` are the same word."""
    return re.sub(r"[^\w]", "", (text or "")).lower()
