"""The presenter: a gesture is an answer, so it can be argued with.

Every test here is about the *reason*, not the shape. The shape is the easy part
and it was never the fault: the arrows landed on the wrong piece because nothing
had decided what the stroke was for, and a plan cannot be corrected by a better
arrow — only by a better question.

So these tests ask the presenter's questions:
    does it point at a piece the voice actually names?
    does it stay silent when the voice names nothing?
    does it draw an edge only where the sentence joins two pieces?
    does it cancel one thing per negation, and not two?
"""
from __future__ import annotations

import pytest

from voxkit.presenter import connector, present
from voxkit.words import Narration, Word, analyse

from conftest import card, make_plan, shot

FPS = 30


def _say(*lines: tuple[str, float, float]) -> Narration:
    return Narration(analyse([Word(t, a, b, FPS) for t, a, b in lines], 8.0), 8.0, FPS)


def _shot(**kw):
    """A contract `Shot`, built through the real parser rather than by hand — a
    test that constructs the object itself agrees with the code by construction."""
    cards = kw.pop("cards", None) or [
        card("peta", z=4, bahan="cetak", lands=30, word="peta",
             semantik="PETA JALAN"),
        card("orang", z=3, bahan="foto", lands=60, word="orang",
             semantik="ORANG BERJALAN"),
    ]
    plan = make_plan(shots=[shot("s01", 0, 240, cards, **kw)])
    return plan.shots[0]


# ------------------------------------------------------------------ pointing
def test_it_points_at_the_piece_the_voice_names():
    """The card's `word` is the word it lands on, and the voice says it — so the
    pen goes there, on that frame, and says why."""
    s = _shot()
    n = _say(("peta", 0.9, 1.2), ("jalan", 1.2, 1.4), ("orang", 1.9, 2.2))
    found = present(s, n)
    points = [g for g in found if g.kind == "point"]
    assert [g.on for g in points] == ["peta", "orang"]
    assert points[0].at == 27, "the pen lands on the frame the word starts"
    assert "peta" in points[0].why


def test_a_stopword_is_not_a_naming():
    """The first version of this module pointed at a piece because the voice said
    'dan' — a gesture with a reason that explains nothing."""
    s = _shot(cards=[card("peta", z=4, bahan="cetak", lands=30, word="dan",
                          semantik="DAN")])
    n = _say(("dan", 0.9, 1.1), ("lalu", 1.3, 1.5))
    assert present(s, n) == []


def test_it_stays_silent_when_the_voice_names_nothing_here():
    """A shot whose pieces are never named gets no gesture. An arrow drawn because
    the shot exists is decoration."""
    s = _shot(cards=[card("peta", z=4, bahan="cetak", lands=30, word="peta",
                          semantik="PETA")])
    n = _say(("kota", 0.9, 1.1), ("ini", 1.3, 1.5))
    assert present(s, n) == []


def test_the_pen_is_scarce():
    """Four named pieces, two strokes. A page with four marks on it explains less
    than a page with two, because the eye has to choose."""
    cards = [card(f"k{i}", z=i + 1, bahan="cetak", lands=20 + i * 10, word=f"kata{i}",
                  semantik=f"KATA{i}") for i in range(4)]
    s = _shot(cards=cards)
    n = _say(*[(f"kata{i}", 1.0 + i * 0.3, 1.2 + i * 0.3) for i in range(4)])
    points = [g for g in present(s, n) if g.kind == "point"]
    assert len(points) == 2


# ----------------------------------------------------------------- relations
def test_it_draws_an_edge_where_the_sentence_joins_two_pieces():
    """This is the mindmap: the voice says 'lalu', and the page gets a line from
    the first piece to the second. Without it the viewer sees two highlights."""
    s = _shot()
    n = _say(("peta", 0.9, 1.2), ("lalu", 1.3, 1.5), ("orang", 1.9, 2.2))
    rel = [g for g in present(s, n) if g.kind == "relate"]
    assert len(rel) == 1
    assert (rel[0].on, rel[0].to) == ("peta", "orang")
    assert "lalu" in rel[0].why


def test_no_edge_without_a_word_that_joins():
    """Two pieces named in the same breath are not automatically related. An arrow
    between adjacent things is decoration."""
    s = _shot()
    n = _say(("peta", 0.9, 1.2), ("orang", 1.9, 2.2))
    assert [g for g in present(s, n) if g.kind == "relate"] == []


def test_the_connector_box_runs_from_one_piece_to_the_other():
    """The stroke has to start on one piece and end on the other. An axis-aligned
    box round both would draw the diagonal of the bounding box, which points the
    right way only when the pieces happen to be diagonal to each other."""
    from voxkit.geometry import Rect

    a = Rect.from_centre(0.2, 0.3, 0.2, 0.2)
    b = Rect.from_centre(0.8, 0.7, 0.2, 0.2)
    cx, cy, w, h, rot = connector(a, b, 16 / 9)
    assert (cx, cy) == pytest.approx((0.5, 0.5))
    # The angle is computed in pixels: a 0.6 × 0.4 step in page fractions is
    # 1152 × 432 px on a 16:9 stage, so the join is 20.6°, not the 33.7° the
    # fractions alone would give. Taking the angle from the fractions tilts every
    # connector on the page by the aspect ratio.
    assert rot == pytest.approx(20.56, abs=0.2)
    # The box is as long as the join in pixels, expressed back in page fractions.
    assert w * 1920 == pytest.approx((1152 ** 2 + 432 ** 2) ** 0.5, rel=1e-3)


# -------------------------------------------------------------------- strike
def test_one_negation_cancels_one_piece():
    """"Bukan benda, tapi perbuatan" strikes `benda` and does not strike
    `perbuatan` — the second half is what replaces the cancelled thing, and
    striking it too says the opposite of what was said."""
    s = _shot(cards=[
        card("benda", z=2, bahan="foto", lands=30, word="benda", semantik="BENDA"),
        card("kerja", z=3, bahan="foto", lands=70, word="perbuatan",
             semantik="PERBUATAN"),
    ])
    n = _say(("bukan", 0.7, 0.9), ("benda", 0.9, 1.2), ("tapi", 1.3, 1.5),
             ("perbuatan", 2.3, 2.7))
    strikes = [g for g in present(s, n) if g.kind == "strike"]
    assert [g.on for g in strikes] == ["benda"]
