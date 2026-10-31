"""Geometry: the centre convention, both axes, and the aspect conversion.

These tests exist because the same three facts were got wrong, separately, in
five tools: a slot's `x` is a centre, a card leaves the page on either axis, and a
card's height in frame fractions is not `width * aspect`.
"""
from __future__ import annotations

import numpy as np
import pytest

from voxkit.contract import parse_placement
from voxkit.geometry import Placed, Rect, buried, covered_share, head_band

STAGE = 1920 / 1080


def test_slot_is_a_centre_not_a_corner():
    r = Rect.from_slot({"x": 0.5, "y": 0.5, "w": 0.4, "h": 0.2})
    assert r.as_tuple() == pytest.approx((0.3, 0.4, 0.7, 0.6))
    assert r.cx == pytest.approx(0.5)


def test_covered_share_is_of_the_lower_piece():
    card = Rect.from_centre(0.5, 0.5, 0.5, 0.5)
    stamp = Rect.from_centre(0.5, 0.5, 0.05, 0.05)
    # The stamp hides a hundredth of the card, and none of itself.
    assert card.covered_by(stamp) == pytest.approx(0.01)
    assert stamp.covered_by(card) == pytest.approx(1.0)


def test_a_card_leaves_the_page_on_either_axis():
    """The guard used to look only at `across`, so a strip pinned at 0.94 lost its
    bottom edge in silence — and that was the commonest placement in the set."""
    r = Rect.from_centre(0.5, 0.94, 0.34, 0.16)
    assert "bottom" in r.outside()
    assert "left" not in r.outside()


def test_height_needs_the_stage_ratio():
    """A card 0.32 wide and 0.86 as tall is 0.49 of the frame high, not 0.275.

    The board omitted the ratio, drew every card 44 % too short, and reported a
    63 % burial as 34 % — under its own threshold.
    """
    p = parse_placement(
        "lower left of the frame, centred at 0.25 across, about 0.32 of the frame wide",
        aspect=0.86, stage_aspect=STAGE)
    assert p.w == pytest.approx(0.32)
    assert p.h == pytest.approx(0.32 * 0.86 * STAGE, rel=1e-6)
    assert p.h > 0.47


def test_placement_reads_every_region_the_plans_use():
    cases = {
        "upper centre of the frame, centred at 0.50 across, about 0.30 of the frame wide": 0.33,
        "lower centre left of the frame, centred at 0.30 across, about 0.30 of the frame wide": 0.68,
        "right of the frame, centred at 0.80 across, about 0.20 of the frame wide": 0.50,
        "the middle, centred at 0.50 across, about 0.20 of the frame wide": 0.50,
        "bottom of the frame, centred at 0.50 across, about 0.20 of the frame wide": 0.86,
    }
    for text, want in cases.items():
        assert parse_placement(text, 0.7, STAGE).cy == pytest.approx(want), text


def test_placement_refuses_prose_it_cannot_read():
    with pytest.raises(ValueError, match="centred at"):
        parse_placement("somewhere on the left, quite big", 0.7, STAGE)
    with pytest.raises(ValueError, match="wide"):
        parse_placement("lower left, centred at 0.2 across", 0.7, STAGE)


def test_buried_has_no_size_exemption():
    """A small slip that is 100 % under a card is a piece paid for and unseen."""
    slip = Placed("slip", Rect.from_centre(0.5, 0.5, 0.05, 0.05), 1, {})
    card = Placed("card", Rect.from_centre(0.5, 0.5, 0.6, 0.6), 2, {})
    hits = buried([slip, card])
    assert len(hits) == 1
    assert hits[0][2] == pytest.approx(1.0)


def test_a_declared_head_is_a_fraction_of_the_piece_box():
    """The contract, stated once so nothing has to guess it: `head` fractions are
    measured against the piece's own ink box, not against the array.

    That distinction only matters for a mask with transparent padding. Cards are
    trimmed to their ink before a border of 2.2 % is added, so for every real
    piece the ink box and the image box are the same box to within a hair — but
    the function must still say which one it means.
    """
    band = head_band(np.ones((100, 100), bool), head=[0.2, 0.2, 0.6, 0.6])
    # Ink box is the whole array, so the box is rows 19..59 by cols 19..59.
    assert band.sum() == pytest.approx(40 * 40, abs=2)
    assert not band[:19].any() and not band[60:].any()
    assert not band[:, :19].any() and not band[:, 60:].any()


def test_head_band_ignores_the_sky_above_a_declared_head():
    """A photograph of a man holding a framed picture has sky at the top of the
    piece; a card over the sky is not a card over his head.

    The figure: a wide roof strip at the top, his head below it, a torso below
    that. The shape test alone would call the roof the top of the head and hand
    back the sky as the face.
    """
    mask = np.zeros((100, 100), bool)
    mask[20:30, :] = True          # a roof: wide, and not him
    mask[40:60, 40:60] = True      # his head
    mask[60:90, 35:65] = True      # his torso

    # Ink box is y 20..90 (h 70), x 0..99 (w 99); these are that box's fractions.
    band = head_band(mask, head=[40 / 99, (40 - 20) / 70, 60 / 99, (60 - 20) / 70])

    assert not band[:40].any(), "the roof and the sky above him are not his head"
    assert not band[60:].any(), "his torso is collage, not a face"
    assert band[40:60, 40:60].sum() > 350, "his head is in the band"


def test_head_band_falls_back_to_shape_when_nothing_is_declared():
    """No declaration: a narrow band that stays narrow is the head."""
    mask = np.zeros((100, 100), bool)
    mask[10:20, 10:90] = True      # a wide hat
    mask[25:45, 40:60] = True      # the head, narrow and sustained
    band = head_band(mask)
    assert not band[:25].any(), "a hat is wide; the head starts below it"
    assert band[25:].sum() > 0


def test_head_band_can_be_told_there_is_no_face():
    mask = np.ones((20, 20), bool)
    assert head_band(mask, head=False).sum() == 0


def test_covered_share_is_a_fraction_of_the_band():
    band = np.zeros((10, 10), bool)
    band[0:5, :] = True
    other = np.zeros((10, 10), bool)
    other[0:5, 0:5] = True
    assert covered_share(band, other) == pytest.approx(0.5)
    assert covered_share(np.zeros((10, 10), bool), other) == 0.0
