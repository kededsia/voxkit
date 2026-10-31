"""The measured layout: where each piece actually sits on the still.

A slot is never typed. It is measured from the piece's own alpha against the
still, because a coordinate typed by a person is that person's reading of the
picture, and a box drawn by hand is a crop instruction. The layout is written by
the isolate stage, copied to the renderer, and read back by the gates — one file,
one answer.

`x`/`y` are the CENTRE. `Rect.from_slot` is the only place that becomes a box.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .geometry import Rect


@dataclass(frozen=True, slots=True)
class Slot:
    name: str
    x: float
    y: float
    w: float
    h: float
    aspect: float = 0.7
    src: str = ""
    poses: tuple[dict, ...] = ()
    z: int = 0

    @property
    def rect(self) -> Rect:
        return Rect.from_slot(self)

    def as_dict(self) -> dict:
        out = {"x": round(self.x, 5), "y": round(self.y, 5),
               "w": round(self.w, 5), "h": round(self.h, 5),
               "aspect": round(self.aspect, 5)}
        if self.poses:
            out["poses"] = list(self.poses)
        return out


@dataclass
class Layout:
    elements: dict[str, Slot] = field(default_factory=dict)
    path: Path | None = None

    @classmethod
    def load(cls, path: Path) -> "Layout":
        if not path.is_file():
            raise FileNotFoundError(f"no layout at {path} — run the isolate stage first")
        raw = json.loads(path.read_text(encoding="utf-8"))
        slots: dict[str, Slot] = {}
        for name, e in (raw.get("elements") or {}).items():
            slots[name] = Slot(
                name=name,
                x=float(e["x"]), y=float(e["y"]),
                w=float(e["w"]), h=float(e.get("h") or 0.0),
                aspect=float(e.get("aspect") or (e["h"] / e["w"] if e.get("w") else 0.7)),
                src=str(e.get("src") or ""),
                poses=tuple(e.get("poses") or ()),
                z=int(e.get("z") or 0),
            )
        return cls(slots, path)

    def __contains__(self, name: str) -> bool:
        return name in self.elements

    def __getitem__(self, name: str) -> Slot:
        return self.elements[name]

    def get(self, name: str) -> Slot | None:
        return self.elements.get(name)

    def require(self, name: str) -> Slot:
        if name not in self.elements:
            raise KeyError(f"layout has no element {name!r}; it has "
                           f"{', '.join(sorted(self.elements)) or 'nothing'}")
        return self.elements[name]

    def save(self, path: Path | None = None) -> Path:
        target = path or self.path
        if target is None:
            raise ValueError("no path to save the layout to")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"elements": {n: s.as_dict() for n, s in self.elements.items()}},
                       indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return target
