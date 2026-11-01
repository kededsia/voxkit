"""The prompt budget.

gflow rejects a batch when *any* prompt in it is over 2000 characters — the whole
batch, not the one row. So an over-long prompt does not cost one still, it costs
five and stops the module: m17 and m18 died exactly that way, at 2146 characters,
because the trim only knew how to shorten the shot's prose and the prose was not
where the length was.
"""
from __future__ import annotations

import pytest

from voxkit.prompt import MAX_PROMPT, still_prompt
from conftest import card, make_plan, shot

#: What gflow itself enforces. Kept here as a literal rather than imported,
#: because this is a fact about the backend and the constant in `prompt.py` is a
#: decision about how much margin to leave under it.
BACKEND_MAX = 2000


def _plan(cards_per_shot: int, what_length: int):
    cards = [
        card(f"keping{i}", z=i + 1, lands=10 + i * 6, word="kata",
             what=("a sepia halftone cut-out of a thing that is described at "
                   "considerable length so that the budget is actually spent ") * 4)
        for i in range(cards_per_shot)
    ]
    cards = [dict(c, what=c["what"][:what_length]) for c in cards]
    return make_plan(shots=[shot("s01", 0, 120, cards)])


@pytest.mark.parametrize("n_cards", [2, 5, 6, 9])
@pytest.mark.parametrize("length", [80, 200, 400])
def test_no_still_prompt_can_exceed_the_backend(n_cards, length):
    plan = _plan(n_cards, length)
    text = still_prompt(plan, plan.shots[0])
    assert len(text) <= MAX_PROMPT, f"{len(text)} chars over a {MAX_PROMPT} cap"
    assert len(text) <= BACKEND_MAX, "the backend would reject this batch"


def test_trimming_never_loses_a_pieces_place_on_the_page():
    """`z` and placement are composition facts.

    A page that loses one is a page that lost a subject, which costs a redraw —
    a far worse trade than a shorter description of a piece that is still there.
    """
    plan = _plan(9, 400)
    text = still_prompt(plan, plan.shots[0])
    for i in range(9):
        assert f"(z{i + 1}," in text, f"piece {i} lost its z-order in the trim"


def test_a_short_prompt_is_left_alone():
    """The trim is a safety net, not a style. A page that fits must not be cut."""
    plan = _plan(2, 60)
    text = still_prompt(plan, plan.shots[0])
    assert text.count("(z1,") == 1 and text.count("(z2,") == 1
    assert text.rstrip().endswith("subjects."), "the style block was trimmed off a page that fit"
