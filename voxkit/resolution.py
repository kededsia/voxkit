"""The pixels a piece is drawn at, against the pixels it has.

The generator returns 1376x768 whatever it is asked for — every model on the
platform, at every aspect. The film is 1920x1080 and the stage draws the page at
`OVERSCAN` 1.55 so the camera may leave it, so an asset is drawn at **2976 px
wide**: a 2.16x upscale of a 1K file. At 1:1 the newsprint is mush and the
halftone screen is grey.

There is no size to ask for and no bigger model to switch to, so the only way to
more pixels is the platform's own upscaler, which is a *re-render at 2K*, not a
resample: measured against the 1K original it is aligned to the pixel (best
correlation at dx=dy=0) and visibly crisper. That is what makes it usable — a
drifted upscale would move every piece and the layout would have to be re-measured
against a still that no longer matches.

So: generate, upscale, then key and measure as usual. The upscale has to happen
before `_build_layouts` reads the reply, because that is where the piece's alpha
and its slot are taken from the file.

Two limits are worth knowing:

* Only images Flow generated can be upscaled. An uploaded reference cannot, so
  this step is skipped for anything the catalog does not know — and says so.
* 4K is Ultra-only. `2k` is the top rung on the plans in use.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

#: What the platform's upscaler calls its rungs. `1k` is the original.
SCALES = ("1k", "2k", "4k")


@dataclass
class Upscaled:
    """What the step did, so a caller can say it rather than assume it."""

    asked: int = 0
    done: int = 0
    unknown: int = 0          # no media id: the catalog never saw this file
    failed: int = 0

    @property
    def summary(self) -> str:
        bits = [f"{self.done}/{self.asked} upscaled"]
        if self.unknown:
            bits.append(f"{self.unknown} not in the catalog")
        if self.failed:
            bits.append(f"{self.failed} failed")
        return " · ".join(bits)


def catalog(binary: str, profile: str = "") -> dict[str, str]:
    """Every generated image the backend remembers, as `path -> media id`.

    The catalog is the only place a media id exists after a batch: `run` writes
    files and does not hand back the ids. Matching on the absolute path is exact —
    the id is resolved from it, never guessed from a name.
    """
    cmd: list[str] = [binary, "data", "list", "images"]
    if profile:
        cmd += ["--profile", profile]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=180)
    except (OSError, subprocess.SubprocessError):
        return {}
    return parse_catalog(out.stdout or "")


def parse_catalog(text: str) -> dict[str, str]:
    """The rows of `data list images`, newest id per path.

    A re-cut writes the same path twice and the catalog keeps both rows, so the
    choice is not cosmetic: taking the older one copies an old answer over the
    fresh reply, which reads as "the model returned the same thing again" and is
    really this function picking the wrong row.
    """
    found: dict[str, str] = {}
    newest: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        path, media = row.get("local_path"), row.get("media_id")
        if not (path and media):
            continue
        key = str(Path(path)).lower()
        when = str(row.get("created_at") or "")
        if key not in found or when >= newest[key]:
            found[key] = media
            newest[key] = when
    return found


def upscale(project, paths: Sequence[Path], scale: str = "2k", *,
            profile: str = "", say=print) -> Upscaled:
    """Replace each generated file with its `scale` upscale, in place.

    In place, and in the same format: every later stage reads the reply by the name
    it was written under (`s01-x-a_0.jpg`), and a stage that had to know whether a
    reply had been upscaled would be a second reader of the same fact.
    """
    from PIL import Image

    if scale in ("", "1k"):
        return Upscaled(asked=len(paths))
    if scale not in SCALES:
        raise ValueError(f"upscale {scale!r} is not one of {', '.join(SCALES)}")

    known = catalog(project.generation.binary, profile)
    out = Upscaled(asked=len(paths))
    tmp = project.build / "_tmp" / "upscale"
    tmp.mkdir(parents=True, exist_ok=True)

    for path in paths:
        if not path.is_file():
            continue
        media = known.get(str(path.resolve()).lower())
        if media is None:
            out.unknown += 1
            continue
        cmd = [project.generation.binary, "image", "upscale", media,
               "--scale", scale, "--out", str(tmp)]
        if profile:
            cmd += ["--profile", profile]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=600)
        except (OSError, subprocess.SubprocessError):
            out.failed += 1
            continue
        made = _newest(tmp, media)
        if res.returncode != 0 or made is None:
            out.failed += 1
            continue
        # Keep the reply's own format: the stages name it, and a `.jpg` under a
        # `.png` name is a lie the loader does not check.
        if path.suffix.lower() == ".png":
            Image.open(made).convert("RGB").save(path, optimize=True)
        else:
            shutil.copyfile(made, path)
        made.unlink(missing_ok=True)
        out.done += 1
        say(f"    · {path.name}: {scale}")

    if out.asked:
        say(f"  upscale: {out.summary}")
    return out


def _newest(root: Path, media: str) -> Path | None:
    """The file the upscaler just wrote for `media`.

    It lands in a dated subdirectory (`images/<date>/<id>_2k.jpg`), so the search
    is by media id and the answer is the most recent — a second upscale of the
    same image overwrites nothing and must not be read as the first.
    """
    hits = [p for p in root.rglob(f"{media}_*.jpg") if p.is_file()]
    return max(hits, key=lambda p: p.stat().st_mtime) if hits else None
