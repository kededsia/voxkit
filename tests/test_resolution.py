"""The upscale step: does it read the right row, and does it refuse to guess.

Two faults are worth a test each, and both of them happened:

* **The wrong row.** A re-cut writes the same path twice and the catalog keeps
  both rows. Taking the older id copies an old answer over the fresh reply — which
  reads as "the model returned the same thing again" and cost three re-cuts of
  `m19/s04/kartu_bukan_itu` before it was spotted.
* **Silence.** A file the catalog has never seen cannot be upscaled, and the step
  has to say how many it skipped rather than report success for the whole batch.
"""
from __future__ import annotations

import json

import pytest

from voxkit import resolution
from voxkit.resolution import Upscaled, parse_catalog


def _row(path: str, media: str, when: str) -> str:
    return json.dumps({"media_id": media, "local_path": path, "created_at": when})


def test_the_newest_row_for_a_path_wins():
    """The exact bug: two rows for one file, the older one read last."""
    text = "\n".join([
        _row(r"D:\film\build\m19\iso\s04-kartu-a_0.jpg", "old", "2026-11-01T13:41:09"),
        _row(r"D:\film\build\m19\iso\s04-kartu-a_0.jpg", "new", "2026-11-01T13:43:20"),
    ])
    assert parse_catalog(text)[str(__import__("pathlib").Path(
        r"D:\film\build\m19\iso\s04-kartu-a_0.jpg")).lower()] == "new"


def test_the_newest_row_wins_in_either_order():
    text = "\n".join([
        _row("/film/iso/x.jpg", "new", "2026-11-01T13:43:20"),
        _row("/film/iso/x.jpg", "old", "2026-11-01T13:41:09"),
    ])
    assert list(parse_catalog(text).values()) == ["new"]


def test_junk_lines_are_skipped_not_fatal():
    text = "\n".join([
        "gflow-cli t2i",
        "│ media_name │ seed │",
        "not json at all",
        _row("/film/iso/y.jpg", "m1", "2026-11-01T00:00:00"),
    ])
    assert len(parse_catalog(text)) == 1


def test_an_unknown_scale_is_refused():
    with pytest.raises(ValueError, match="not one of"):
        resolution.upscale(None, [], "3k")


def test_1k_is_the_original_and_does_nothing():
    out = resolution.upscale(None, [__import__("pathlib").Path("a.jpg")], "1k")
    assert out == Upscaled(asked=1, done=0)


def test_the_summary_names_what_it_could_not_do():
    """A count of skips, not a claim of success."""
    line = Upscaled(asked=7, done=6, unknown=1).summary
    assert "6/7" in line and "not in the catalog" in line
