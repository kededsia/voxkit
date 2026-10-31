"""The shared visual vocabulary: what a mark can be, and what the pen is.

These names are a contract with the renderer. A plan that asks for a gesture the
component does not implement produces a still with a perfectly drawn *other*
gesture — the executor is faithful to the plan, and the plan was not faithful to
the component. So the vocabulary is read from the component when it is present,
and a plan that names something outside it fails before a generation is spent.

The fallback list is the Vox marker set. It exists so the engine can validate a
plan in a project whose renderer has not been checked out yet; when `Marker.tsx`
is found it always wins, because the file is the truth.
"""
from __future__ import annotations

import re
from pathlib import Path

SHAPES_FALLBACK = frozenset({
    "underline", "underline-double", "circle", "ellipse", "box", "cross",
    "check", "strike", "bracket-left", "bracket-right", "brackets",
    "arrow-right", "arrow-down", "arrow-curve", "corner-marks", "burst",
    "lasso", "squiggle", "star", "tape", "band", "question", "exclamation",
})

PENS = frozenset({"marker", "chalk", "pencil", "brush"})
COLORS = frozenset({"coral", "crimson", "charcoal", "mustard", "navy", "cream"})
MOTIONS = frozenset({"draw", "snap", "hold"})

# Shapes that are each other's reflection. Two of them in one shot, one at each
# edge, is the arrangement a viewer reads as symmetrical even when the curve
# varies — the engine varies the curve, not the arrangement.
MIRROR = {"bracket-left": "bracket-right", "bracket-right": "bracket-left"}


def shapes(remotion: Path | None = None) -> frozenset[str]:
    """Read `SHAPES` from the renderer when it exists, else the fallback."""
    for candidate in _marker_candidates(remotion):
        if not candidate.is_file():
            continue
        src = candidate.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"export const SHAPES\s*=\s*\[(.*?)\]", src, re.S)
        if m:
            found = frozenset(re.findall(r'"([a-z][a-z-]*)"', m.group(1)))
            if found:
                return found
    return SHAPES_FALLBACK


def _marker_candidates(remotion: Path | None):
    if remotion is None:
        return []
    return [
        remotion / "src" / "components" / "Marker.tsx",
        remotion / "src" / "components" / "Marker" / "index.tsx",
    ]
