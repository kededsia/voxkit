"""The isolate stage: what it must not lose when it re-measures a piece.

A re-isolation is supposed to change one number — where the piece sits — and
nothing else. Twice this session it changed more than that:

  * `--force` at shot level re-cut pieces that were already correct, and one of
    them came back as the whole page;
  * `_build_layouts` wrote a fresh layout, so every puppet in the shot lost its
    pose wiring while the pose files sat on disk, unreferenced.

The second is the dangerous one, because nothing fails: the gate sees no poses
declared-but-missing, the render sees a card with no frames, and the puppet is
simply static. These tests hold the line.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from voxkit.layout import Layout, Slot
from voxkit.stages import _map_crop, _previous_poses


def _write(path: Path, elements: dict) -> None:
    path.write_text(json.dumps({"elements": elements}), encoding="utf-8")


def test_pose_wiring_survives_a_remeasure(tmp_path: Path):
    """The pose list comes back, so a re-cut cannot turn a puppet static."""
    _write(tmp_path / "layout.json", {
        "penjaga": {"x": 0.5, "y": 0.5, "w": 0.3, "h": 0.6, "aspect": 2.0, "z": 3,
                    "poses": [{"atFrame": 40, "src": "m15/cards/s04/penjaga_pose2.png"},
                              {"atFrame": 62, "src": "m15/cards/s04/penjaga_pose3.png"}]},
        "foto": {"x": 0.2, "y": 0.2, "w": 0.3, "h": 0.3},
    })
    before = _previous_poses(tmp_path)
    assert set(before) == {"penjaga"}, "a card with no poses must not appear"
    assert [p["atFrame"] for p in before["penjaga"]] == [40, 62]


def test_a_rebuilt_slot_keeps_its_frames(tmp_path: Path):
    """The frames are carried onto the *new* box, not the old one."""
    _write(tmp_path / "layout.json", {
        "penjaga": {"x": 0.5, "y": 0.5, "w": 0.3, "h": 0.6,
                    "poses": [{"atFrame": 40, "src": "m15/cards/s04/penjaga_pose2.png"}]},
    })
    before = _previous_poses(tmp_path)
    rebuilt = Slot(name="penjaga", x=0.61, y=0.44, w=0.22, h=0.55,
                   poses=before.get("penjaga", ()))
    assert rebuilt.poses and rebuilt.poses[0]["atFrame"] == 40
    assert (rebuilt.x, rebuilt.w) == (0.61, 0.22), "the measurement must still win"


def test_a_missing_or_broken_layout_is_not_fatal(tmp_path: Path):
    """A first isolate has no layout, and a half-written one is not a crash."""
    assert _previous_poses(tmp_path) == {}
    (tmp_path / "layout.json").write_text("{ this is not json", encoding="utf-8")
    assert _previous_poses(tmp_path) == {}


def test_a_layout_round_trips_poses(tmp_path: Path):
    """What `poses` writes is what the next stage reads."""
    layout = Layout()
    layout.elements["a"] = Slot(name="a", x=0.1, y=0.2, w=0.3, h=0.4,
                                poses=({"atFrame": 9, "src": "m/cards/s/a_pose2.png"},))
    layout.save(tmp_path / "layout.json")
    back = Layout.load(tmp_path / "layout.json")
    assert back["a"].poses == ({"atFrame": 9, "src": "m/cards/s/a_pose2.png"},)


# --------------------------------------------------------- crop coordinates
#: A 1000x600 page with a crop over its middle-right quarter: x 500..750, y 150..450.
META = {"box": [500, 150, 750, 450], "canvas": [1000, 600]}


def test_a_centre_in_the_crop_is_a_centre_in_the_page():
    """The reply's centre maps to the crop's centre, not the page's."""
    cx, cy, _w, _h = _map_crop(0.5, 0.5, 0.2, 0.2, META)
    assert cx == pytest.approx(0.625), "x = (500 + 0.5*250)/1000"
    assert cy == pytest.approx(0.5), "y = (150 + 0.5*300)/600"


def test_a_size_shrinks_by_the_crop():
    """A piece filling half the crop fills a quarter of the crop's width of the page."""
    _cx, _cy, w, h = _map_crop(0.5, 0.5, 0.5, 0.5, META)
    assert w == pytest.approx(0.125), "0.5 * 250 / 1000"
    assert h == pytest.approx(0.25), "0.5 * 300 / 600"


def test_the_corners_of_the_crop_map_to_the_corners_of_the_box():
    """A whole-crop reply must land exactly on the box that was cropped."""
    x0, y0, w, h = _map_crop(0.5, 0.5, 1.0, 1.0, META)
    assert (x0 - w / 2, y0 - h / 2) == (pytest.approx(0.5), pytest.approx(0.25))
    assert (x0 + w / 2, y0 + h / 2) == (pytest.approx(0.75), pytest.approx(0.75))


def test_a_crop_covering_the_whole_page_changes_nothing():
    """With no crop the mapping must be the identity, or every piece moves."""
    meta = {"box": [0, 0, 1000, 600], "canvas": [1000, 600]}
    assert _map_crop(0.3, 0.7, 0.2, 0.4, meta) == pytest.approx((0.3, 0.7, 0.2, 0.4))
