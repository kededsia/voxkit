"""Project configuration: everything project-specific lives in `vox.toml`.

The engine must not know a module id, a film length, an account name or a
folder layout. All of that is data. The previous toolchain had `docs/17min`,
`m01`, `videoquincy` and `rebuild/` written into twenty files, so the same code
could not run on a second film without editing it.

    [project]
    name = "tanah-air"
    fps = 30

    [paths]
    plans = "plans"
    audio = "audio"
    assets = "assets"
    build = "build"

    [style]
    style_key = "assets/style-key.jpg"

Every path is relative to the directory holding `vox.toml`. A missing key takes
the default below, so a project only writes what differs.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_NAME = "vox.toml"


@dataclass(frozen=True, slots=True)
class Style:
    """The look. Constants of the collage language, not of one film."""

    style_key: str = "assets/style-key.jpg"
    paper: str = "#EFE7D6"
    ink: str = "sepia"
    # The chroma ground every isolated piece is generated on. Keying a known
    # colour is deterministic; segmentation is not, and it is the reason a pale
    # map came back as a half-transparent ghost.
    chroma: str = "#FF00FF"
    chroma_tolerance: float = 62.0
    chroma_feather: float = 20.0
    paper_border: float = 0.022


@dataclass(frozen=True, slots=True)
class Paths:
    plans: str = "plans"
    audio: str = "audio"
    assets: str = "assets"
    build: str = "build"
    remotion: str = "remotion"


@dataclass(frozen=True, slots=True)
class Generation:
    """How images are asked for. `gflow` is the only backend the batch writer
    knows how to spell; the batch format itself is a list of prompts, so another
    backend is a different emitter, not a different pipeline."""

    binary: str = "gflow"
    profiles: tuple[str, ...] = ("default",)
    batch_size: int = 6          # prompts per call; more reads as one person
    model: str = "nano2"
    aspect: str = "16:9"
    resume: bool = True


@dataclass(frozen=True, slots=True)
class Project:
    root: Path
    name: str = "untitled"
    fps: int = 30
    width: int = 1920
    height: int = 1080
    language: str = "id"
    paths: Paths = field(default_factory=Paths)
    style: Style = field(default_factory=Style)
    generation: Generation = field(default_factory=Generation)

    # ------------------------------------------------------------------ paths
    def p(self, key: str) -> Path:
        return self.root / getattr(self.paths, key)

    @property
    def plans(self) -> Path:
        return self.p("plans")

    @property
    def audio(self) -> Path:
        return self.p("audio")

    @property
    def assets(self) -> Path:
        return self.p("assets")

    @property
    def build(self) -> Path:
        return self.p("build")

    def plan(self, module: str) -> Path:
        return self.plans / f"{module}.json"

    def transcript(self, module: str) -> Path:
        return self.audio / f"{module}.json"

    def narration(self, module: str) -> Path:
        return self.audio / f"{module}.wav"

    def mod_build(self, module: str) -> Path:
        return self.build / module

    def still(self, module: str, shot: str) -> Path:
        return self.mod_build(module) / f"{shot}.jpg"

    def card_dir(self, module: str, shot: str) -> Path:
        return self.mod_build(module) / "cards" / shot

    def plate(self, module: str, shot: str) -> Path:
        return self.mod_build(module) / "plates" / f"{shot}.jpg"

    def fill(self, module: str, shot: str) -> Path:
        return self.mod_build(module) / "fills" / f"{shot}_0.jpg"

    def iso_dir(self, module: str) -> Path:
        return self.mod_build(module) / "iso"

    def spec_dir(self, module: str) -> Path:
        return self.mod_build(module) / "specs"

    def style_key(self) -> Path:
        return self.root / self.style.style_key

    # --------------------------------------------------------------- modules
    def modules(self) -> list[str]:
        """Every module that has a plan, in id order. The engine never assumes
        a count, a prefix or a film length."""
        return sorted(p.stem for p in self.plans.glob("*.json") if not p.name.startswith("_"))

    def require_module(self, module: str) -> Path:
        path = self.plan(module)
        if not path.is_file():
            raise FileNotFoundError(f"no plan for {module!r} at {path}")
        return path


def discover(start: Path | None = None) -> Project:
    """Walk up from `start` until a `vox.toml` is found."""
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / CONFIG_NAME).is_file():
            return load(d / CONFIG_NAME)
    raise FileNotFoundError(
        f"no {CONFIG_NAME} in {here} or any parent — run `vox init` or point at a project"
    )


def load(path: Path) -> Project:
    raw: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    root = path.resolve().parent

    proj = raw.get("project", {}) or {}
    paths = raw.get("paths", {}) or {}
    style = raw.get("style", {}) or {}
    gen = raw.get("generation", {}) or {}

    known_paths = set(Paths.__dataclass_fields__)
    known_style = set(Style.__dataclass_fields__)
    known_gen = set(Generation.__dataclass_fields__)

    _reject_unknown(paths, known_paths, "paths")
    _reject_unknown(style, known_style, "style")
    _reject_unknown(gen, known_gen, "generation")

    if "profiles" in gen:
        gen["profiles"] = tuple(gen["profiles"])

    return Project(
        root=root,
        name=str(proj.get("name", root.name)),
        fps=int(proj.get("fps", 30)),
        width=int(proj.get("width", 1920)),
        height=int(proj.get("height", 1080)),
        language=str(proj.get("language", "id")),
        paths=Paths(**paths),
        style=Style(**style),
        generation=Generation(**gen),
    )


def _reject_unknown(values: dict, known: set[str], section: str) -> None:
    """A typo in a config key is a setting that silently does nothing. Refuse it."""
    unknown = sorted(set(values) - known)
    if unknown:
        raise ValueError(f"[{section}] has unknown key(s) {unknown}; known: {sorted(known)}")
