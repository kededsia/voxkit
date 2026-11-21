"""The lexicon contract: what a lexicon file is, and that the gate reads it.

These exist because the spelling check reported **PASS** on all twenty-two
modules while checking nothing. The file was authored under the key `words`, the
gate read `terms`, and `.get("terms", [])` returned an empty list. The loop body
never ran, so no finding was produced, so the gate passed.

Every test below is aimed at that shape of failure — not at "does a typo get
caught" (the old tests already asked that, using the reader's own key, so they
agreed with the bug), but at:

    * does the file the film actually ships with yield terms?
    * does a file that yields nothing say so instead of passing?
    * does the gate look where the next typo will be, not where the last one was?
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from voxkit.lexicon import KEYS, Lexicon


# ------------------------------------------------------------------ the file
def test_the_real_lexicon_yields_terms():
    """`film/lexicon.json` uses the key `words`. If the reader ever goes back to
    expecting `terms` alone, this fails instead of the gate going quiet."""
    path = Path(__file__).resolve().parents[1] / "film" / "lexicon.json"
    if not path.is_file():
        pytest.skip("no film/lexicon.json in this checkout")
    lex = Lexicon.from_dict(json.loads(path.read_text(encoding="utf-8")))
    assert len(lex) > 0, "the shipped lexicon parsed to zero terms"
    assert lex.forbidden(), "the shipped lexicon forbids nothing, so it catches nothing"


def test_the_shipped_lexicon_catches_chi():
    """The word the reviewer saw on screen. `chi` must map to `ci`."""
    path = Path(__file__).resolve().parents[1] / "film" / "lexicon.json"
    if not path.is_file():
        pytest.skip("no film/lexicon.json in this checkout")
    lex = Lexicon.from_dict(json.loads(path.read_text(encoding="utf-8")))
    assert lex.forbidden().get("chi") == "ci"


# ------------------------------------------------------------------- reading
@pytest.mark.parametrize("key", KEYS)
def test_both_authored_keys_are_read(key):
    """`lexicon.json` says `words`; `facts.json` says `terms`. One reader, both."""
    lex = Lexicon.from_dict({key: [{"correct": "cai", "never": ["cahi"]}]})
    assert len(lex) == 1
    assert lex.forbidden() == {"cahi": "cai"}


def test_an_unreadable_lexicon_raises_instead_of_passing():
    """A file with entries but no recognised key must not read as empty."""
    with pytest.raises(ValueError, match="cannot be read"):
        Lexicon.from_dict({"entries": [{"correct": "cai"}]})


def test_entries_with_no_correct_field_raise():
    with pytest.raises(ValueError, match="none parse"):
        Lexicon.from_dict({"words": [{"never": ["cahi"]}]})


def test_a_variant_cannot_belong_to_two_words():
    """`chai` was briefly listed under both `cai` and `ci`. A plain dict would
    have silently picked the last one."""
    with pytest.raises(ValueError, match="cannot map to two words"):
        Lexicon.from_dict({
            "words": [
                {"correct": "cai", "never": ["chai"]},
                {"correct": "ci", "never": ["chai"]},
            ]
        }).forbidden()


def test_an_empty_lexicon_is_empty_not_broken():
    assert not Lexicon.from_dict({})
    assert not Lexicon.from_dict({"_comment": "nothing yet"})
    assert not Lexicon.from_dict(None)


def test_unlisted_terms_are_reported():
    """A term with no variants is unprotected; the gate says so rather than
    implying it is safe."""
    lex = Lexicon.from_dict({"words": [{"correct": "purwa", "never": []}]})
    assert [t.correct for t in lex.unlisted()] == ["purwa"]
