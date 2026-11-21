"""What a lexicon *is*, in one place.

`lexicon.json` is the list of words this film prints that are not Indonesian —
Sundanese, Javanese, Sanskrit — each with its ONE correct spelling and the
variants that must never reach a still. It is the only defence against a
misprint, because the still prompt is built verbatim from the plan and the model
draws the typo faithfully.

It had stopped working, and it did so silently, which is the worst way:

  * the file was authored with the key `words`; the gate read `terms`. `.get`
    with a default returned an empty list, the loop body never ran, and the gate
    reported **PASS**. Not "skipped", not "no lexicon" — a pass, over zero
    terms, on all twenty-two modules.
  * the test that should have caught it set `ctx.lexicon = {"terms": [...]}`,
    which is the *reader's* key. The test agreed with the bug.
  * `CHI` therefore reached a render, twice, on the same page that already
    printed `BERAWALAN CI` correctly. `ci` was in the lexicon with `never: []`,
    so even a working reader had nothing to match against.

Two rules follow, and they are the reason this module exists rather than a
`.get("terms", [])` at each call site:

  1. **One reader.** The file's shape is decided here. A caller cannot pick a
     key and get an empty answer that looks like a clean bill of health.
  2. **A lexicon that yields nothing is broken, not clean.** If the file has
     entries and none of them parse, that raises. Silence is never a pass — the
     same rule `N/A is not PASS` enforces for gates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

#: Keys the file has been authored under. `words` is what `film/lexicon.json`
#: uses; `terms` is what the reader used to expect and what `facts.json` still
#: uses. Both are accepted so a file is never read as empty by accident.
KEYS = ("words", "terms")


@dataclass(frozen=True, slots=True)
class Term:
    correct: str
    lang: str = ""
    meaning: str = ""
    never: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True, slots=True)
class Lexicon:
    """The terms, plus the lookup the gate actually needs."""

    terms: tuple[Term, ...] = ()
    #: Every `correct` spelling, lowercased — used to notice that a word the film
    #: prints is a term at all, even when no variant of it has been listed yet.
    known: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> "Lexicon":
        """Read a lexicon file, whichever key it was authored under.

        Raises rather than returning an empty lexicon when the file has content
        but no term survives parsing: a lexicon nobody can read is the failure
        this module was written to stop repeating.
        """
        if not raw:
            return cls()

        entries: list[Any] | None = None
        for key in KEYS:
            value = raw.get(key)
            if isinstance(value, list):
                entries = value
                break
        if entries is None:
            # No recognised key, but the file may still be non-empty — a `_comment`
            # only, or a shape nobody has taught this reader yet.
            if any(k not in ("_comment",) for k in raw):
                raise ValueError(
                    f"lexicon has no {' or '.join(KEYS)!r} list — it has "
                    f"{sorted(raw)!r}. A lexicon that cannot be read checks nothing."
                )
            return cls()

        terms: list[Term] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            correct = str(entry.get("correct", "")).strip()
            if not correct:
                continue
            never = tuple(
                str(w).strip().lower()
                for w in entry.get("never", []) or ()
                if str(w).strip()
            )
            terms.append(Term(
                correct=correct,
                lang=str(entry.get("lang", "") or ""),
                meaning=str(entry.get("meaning", "") or ""),
                never=never,
                note=str(entry.get("note", "") or ""),
            ))

        if entries and not terms:
            raise ValueError(
                f"lexicon lists {len(entries)} entr(y/ies) and none parse — "
                f"every one needs a `correct` field."
            )

        return cls(terms=tuple(terms),
                   known=frozenset(t.correct.lower() for t in terms))

    def forbidden(self) -> dict[str, str]:
        """wrong spelling → the one correct spelling.

        A variant claimed by two different terms is an error, not a tie. Building
        this as a plain dict let the last entry win, so `chai` listed under both
        `cai` (water) and `ci` (prefix) would have been "corrected" to whichever
        the file happened to put second — a silent wrong answer, which is the
        same failure as the silent empty list this module exists to prevent.
        """
        out: dict[str, str] = {}
        claimed: dict[str, str] = {}
        for term in self.terms:
            for wrong in term.never:
                if wrong in out and out[wrong] != term.correct:
                    raise ValueError(
                        f"lexicon lists '{wrong}' as a variant of both "
                        f"'{claimed[wrong]}' and '{term.correct}' — a misspelling "
                        f"cannot map to two words. Pick one."
                    )
                out[wrong] = term.correct
                claimed[wrong] = term.correct
        return out

    def unlisted(self) -> list[Term]:
        """Terms with no forbidden variants.

        Not an error — a word may be new. But a term that has been seen in a
        render and still lists nothing is a hole in the net, so the gate reports
        the count instead of implying the term is protected.
        """
        return [t for t in self.terms if not t.never]

    def __bool__(self) -> bool:
        return bool(self.terms)

    def __len__(self) -> int:
        return len(self.terms)

    def __iter__(self) -> Iterable[Term]:
        return iter(self.terms)
