"""The plan contract: a fault in the model is a finding, never a default.

Every test here corresponds to a fault that shipped in the old pipeline by
falling back to something plausible instead of refusing. A default is the most
expensive kind of bug in a pipeline whose executor is faithful: it does not
fail, it produces a film.
"""
from __future__ import annotations

import pytest

from voxkit.contract import (
    COVERING, READABLE, WUJUD, Plan, is_placeholder, tile, words_in,
)

from conftest import card, make_plan, plan_dict, shot


# ------------------------------------------------------------------ vocabulary
def test_readable_and_covering_cover_every_material_that_carries_words():
    """`peta` and `benda` used to be in neither set, so thirty-one readable cards
    were exempt from the rule that exists to keep words legible."""
    assert "peta" in READABLE, "a printed map is full of place names"
    assert "cetak" in READABLE and "koran" in READABLE
    assert "foto" in COVERING and "figur" in COVERING
    assert not (READABLE & COVERING), "a material cannot be both"


def test_an_unknown_wujud_is_a_finding_not_a_default():
    """The board defaulted to 0.7 and then measured every overlap with it."""
    plan = make_plan(shots=[shot("s01", 0, 90, [
        card("a", z=1, wujud="sobekan_pita"),
        card("b", z=2, wujud="kertas_licin"),          # not in the table
    ])])
    problems = plan.load_problems()
    assert len(problems) == 1
    assert problems[0].level == "fail"
    assert "kertas_licin" in problems[0].message
    assert "overlap" in problems[0].message, "the message must say why it matters"


def test_height_comes_from_the_wujud_through_the_stage_ratio():
    plan = make_plan(shots=[shot("s01", 0, 90, [
        card("slip", z=1, wujud="sobekan_pita", at="centre of the frame, "
             "centred at 0.50 across, about 0.40 of the frame wide"),
        card("fig", z=2, wujud="siluet_organik", at="right of the frame, "
             "centred at 0.80 across, about 0.40 of the frame wide"),
    ])])
    slip, fig = plan.cards
    assert slip.placement.w == pytest.approx(0.40)
    assert slip.placement.h == pytest.approx(0.40 * WUJUD["sobekan_pita"] * 1920 / 1080)
    assert fig.placement.h > slip.placement.h * 1.9, "a figure is much taller than a slip"


def test_an_unreadable_at_is_a_finding():
    plan = make_plan(shots=[shot("s01", 0, 90, [
        card("a", z=1), card("b", z=2, at="somewhere on the left, quite big"),
    ])])
    problems = plan.load_problems()
    assert any("cannot be read" in p.message for p in problems)


def test_every_structural_fault_is_collected_not_raised():
    """A plan with four problems should report four, not one per round of
    editing."""
    plan = make_plan(shots=[shot("s01", 0, 90, [
        card("a", z=1, wujud="nope", bahan="nope"),
        card("b", z=2, at="unreadable prose entirely"),
        card("", z=3),
    ])])
    assert len(plan.load_problems()) >= 4


# ------------------------------------------------------------------- arrivals
def test_lands_is_relative_to_the_shot():
    """A plan written in film frames fails every arrival check by the length of
    everything before it."""
    plan = make_plan(shots=[
        shot("s01", 0, 90, [card("a", z=1, lands=10), card("b", z=2, lands=40)]),
        shot("s02", 90, 180, [card("c", z=1, lands=10), card("d", z=2, lands=40)]),
    ])
    s2 = plan.shot("s02")
    assert [f for _, f in s2.arrivals()] == [100, 130]


# --------------------------------------------------------------------- tiling
def test_a_gap_between_shots_is_a_finding():
    out = tile(make_plan(shots=[
        shot("s01", 0, 90, [card("a"), card("b")]),
        shot("s02", 95, 180, [card("c"), card("d")]),
    ]).shots, 180)
    assert any("belong to no shot" in f.message for f in out)


def test_an_overlap_between_shots_is_a_finding():
    out = tile(make_plan(shots=[
        shot("s01", 0, 95, [card("a"), card("b")]),
        shot("s02", 90, 180, [card("c"), card("d")]),
    ]).shots, 180)
    assert any("belong to both" in f.message for f in out)


def test_a_film_that_ends_early_is_a_finding():
    out = tile(make_plan(shots=[
        shot("s01", 0, 180, [card("a"), card("b")]),
    ]).shots, 240)
    assert any("would end early" in f.message for f in out)


def test_a_film_that_starts_late_is_a_finding():
    out = tile(make_plan(shots=[shot("s01", 6, 180, [card("a"), card("b")])]).shots, 180)
    assert any("starts at f6" in f.message for f in out)


# ------------------------------------------------------------------- helpers
@pytest.mark.parametrize("value", ["", "  ", "-", "TBD", "n/a", "?", None, 3])
def test_placeholders_are_recognised(value):
    assert is_placeholder(value)


@pytest.mark.parametrize("value", ["cai", "Bandung", "0.5"])
def test_real_values_are_not_placeholders(value):
    assert not is_placeholder(value)


def test_word_count_is_about_words_not_characters():
    assert words_in("A torn relief map") == 4
    assert words_in("  ...  ") == 0


def test_a_mark_bound_to_its_card_is_not_a_page_mark():
    plan = make_plan(shots=[shot("s01", 0, 90, [
        card("a", z=1), card("b", z=2),
    ], marks=[["underline", 12, 0.4, "a", {"box": [0.1, 0.2, 0.5, 0.3]}]] )])
    assert plan.shots[0].marks[0].bound is False
