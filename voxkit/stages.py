"""The stages, in the order they must run.

Each stage is idempotent and says what it skipped. Nothing here reports success
for work that did not happen: a generation batch is done when its files exist, a
layout is done when every piece has a slot, and a stage that cannot finish
returns non-zero so the driver stops rather than building on sand.

    plan   -> words -> still -> isolate -> fill -> plate -> poses -> emit -> gates -> render

The order is forced by the artifacts. A still is the page; pieces are cut from it;
the plate is what is behind the pieces; a puppet is a piece with a second pose; the
program needs measured slots; the render needs a program that passed its gates.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from . import image, locate, prompt
from .batch import Job, run_batch
from .config import Project
from .contract import Plan
from .layout import Layout, Slot
from .words import Narration


def _say(msg: str) -> None:
    print(msg)


# ------------------------------------------------------------------- words
def words(project: Project, module: str) -> int:
    """Score the narration and write nothing — the transcript is the source."""
    from .words import FLOOR, load, analyse
    path = project.transcript(module)
    if not path.is_file():
        _say(f"{module}: no transcript at {path}")
        return 1
    w, total = load(path, project.fps)
    accents = analyse(w, total)
    hot = [a for a in accents if a.score >= FLOOR]
    _say(f"{module}: {len(w)} words, {total:.1f}s = {round(total * project.fps)} frames, "
         f"{len(hot)} accented")
    for a in hot[:8]:
        _say(f"  f{a.word.start_frame:>5}  {a.score:.2f}  {a.word.text}")
    return 0


# ------------------------------------------------------------------- still
def stills(project: Project, module: str, *, profile: str = "", dry: bool = False,
           force: bool = False, only: tuple[str, ...] = (), runner=None) -> int:
    plan = Plan.load(project.require_module(module), _aspect(project))
    out = project.mod_build(module)
    out.mkdir(parents=True, exist_ok=True)

    over = prompt.over_length(plan)
    for sid, n in over:
        _say(f"{module} {sid}: prompt is {n} chars, over the {prompt.MAX_PROMPT} cap")

    todo = [s for s in plan.shots
            if (only and s.id in only) or (force and (not only or s.id in only))
            or (not only and not project.still(module, s.id).is_file())]
    if not todo:
        _say(f"{module}: every shot already has a still")
        return 0

    jobs = [Job(text=prompt.still_prompt(plan, s), output=s.id,
                ref=str(project.style_key()) if project.style_key().is_file() else None,
                aspect=f"{project.width}:{project.height}",
                model=project.generation.model) for s in todo]

    outcome = run_batch(project, module, jobs, out, lambda j: out / f"{j.output}_0.jpg",
                        profile=profile, dry=dry, runner=runner, say=_say)
    if dry:
        _say(f"{module}: {len(jobs)} still(s) would be drawn")
        return 0

    promoted = 0
    for job in jobs:
        raw = out / f"{job.output}_0.jpg"
        if raw.is_file():
            project.still(module, job.output).write_bytes(raw.read_bytes())
            promoted += 1
    _say(f"{module}: {outcome.summary()}")
    if outcome.missing:
        _say(f"{module}: {len(outcome.missing)} still(s) did not come back — "
             "the build must not continue on them")
        return 1
    _say(f"{module}: {promoted} still(s) ready — look at them before isolating")
    return 0


# ----------------------------------------------------------------- isolate
def isolate(project: Project, module: str, *, profile: str = "", dry: bool = False,
            force: bool = False, only: tuple[str, ...] = (), runner=None) -> int:
    """Cut every piece out of its still and measure where it sat."""
    plan = Plan.load(project.require_module(module), _aspect(project))
    iso_dir = project.iso_dir(module)
    spec_dir = project.spec_dir(module)
    iso_dir.mkdir(parents=True, exist_ok=True)
    spec_dir.mkdir(parents=True, exist_ok=True)

    jobs: list[tuple[Job, str, str]] = []
    for shot in plan.shots:
        if only and shot.id not in only:
            continue
        still_path = project.still(module, shot.id)
        if not still_path.is_file():
            _say(f"{module} {shot.id}: no still — skipped")
            continue
        for card in shot.ordered():
            stem = f"{shot.id}-{card.name}-a"
            if not force and any((iso_dir / f"{stem}{s}").is_file()
                                 for s in ("_0.jpg", ".png", ".jpg")):
                continue
            jobs.append((
                Job(text=prompt.iso_prompt(card, project.style.chroma), output=stem,
                    ref=str(still_path), model=project.generation.model),
                shot.id, card.name,
            ))

    if not jobs:
        _say(f"{module}: every piece is already isolated")
        return _build_layouts(project, plan, only)
    if dry:
        for job, sid, name in jobs:
            _say(f"  · {sid}/{name}: {len(job.text)} chars")
        _say(f"{module}: {len(jobs)} piece(s) would be cut")
        return 0

    outcome = run_batch(project, module, [j for j, _, _ in jobs], iso_dir,
                        lambda j: _first(iso_dir, j.output),
                        profile=profile, dry=dry, runner=runner, say=_say)
    _say(f"{module}: {outcome.summary()}")
    if outcome.missing:
        _say(f"{module}: {len(outcome.missing)} piece(s) did not come back")
        return 1
    return _build_layouts(project, plan, only)


def _first(iso_dir: Path, stem: str) -> Path | None:
    for suffix in ("_0.jpg", ".png", ".jpg", "_0.png"):
        p = iso_dir / f"{stem}{suffix}"
        if p.is_file():
            return p
    return None


def _build_layouts(project: Project, plan: Plan, only: tuple[str, ...] = ()) -> int:
    """Key each reply, measure its slot, and write the layout.

    The slot starts from the reply's own bbox — the isolation was told "same
    position, same scale" — and is then refined by correlating the piece's ink
    against the still. The reply can be wrong about scale; the still cannot.
    """
    bad = 0
    module = plan.module
    for shot in plan.shots:
        if only and shot.id not in only:
            continue
        still_path = project.still(module, shot.id)
        if not still_path.is_file():
            continue
        still = image.open_rgb(still_path)
        still_grey = np.asarray(still.convert("L"), dtype=np.float32)
        layout = Layout()
        card_dir = project.card_dir(module, shot.id)
        card_dir.mkdir(parents=True, exist_ok=True)

        for card in shot.ordered():
            reply_path = _first(project.iso_dir(module), f"{shot.id}-{card.name}-a")
            if reply_path is None:
                _say(f"  {shot.id}/{card.name}: no isolated reply")
                bad += 1
                continue
            keyed = image.chroma_key(
                image.open_rgb(reply_path), image.parse_color(project.style.chroma),
                project.style.chroma_tolerance, project.style.chroma_feather)
            keyed = image.erase_rects(keyed, card.erase)
            keyed = image.keep_largest(keyed)
            keyed = image.erode_alpha(keyed, 2)

            bb = image.alpha_bbox(keyed)
            if bb is None:
                _say(f"  {shot.id}/{card.name}: the reply keyed to nothing")
                bad += 1
                continue
            piece = keyed.crop(bb)
            pad = 0
            if project.style.paper_border > 0:
                piece, pad = image.add_paper_border(piece, project.style.paper_border)

            # The slot, in frame fractions of the reply canvas. The paper border is
            # symmetric, so the centre is the piece's centre; the size grows by it.
            rw, rh = reply_path_canvas(reply_path)
            cx = (bb[0] + bb[2]) / 2 / rw
            cy = (bb[1] + bb[3]) / 2 / rh
            w = (bb[2] - bb[0] + 2 * pad) / rw
            h = (bb[3] - bb[1] + 2 * pad) / rh

            # Put the card back on the print it was cut from, then measure again
            # against the page — a slot that is faithful to a wrong asset is still
            # a wrong slot.
            box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            piece, note = image.print_match(piece, still, (
                box[0] * still.width, box[1] * still.height,
                box[2] * still.width, box[3] * still.height))
            piece.save(card_dir / f"{card.name}.png")

            from .geometry import Rect
            fit = locate.refine(
                np.asarray(piece.convert("L"), dtype=np.float32),
                np.array(piece.getchannel("A")),
                still_grey, Rect(*box))
            layout.elements[card.name] = Slot(
                name=card.name, x=fit.rect.cx, y=fit.rect.cy,
                w=fit.rect.w, h=fit.rect.h,
                aspect=piece.height / piece.width,
                src=str((card_dir / f"{card.name}.png").relative_to(project.root)),
                z=card.z,
            )
            _say(f"  {shot.id}/{card.name}: {piece.width}x{piece.height}, "
                 f"fit {fit.score:.2f}, moved {fit.moved:.3f} — {note}")

        layout.save(card_dir / "layout.json")
    return 1 if bad else 0


def reply_path_canvas(path: Path) -> tuple[int, int]:
    with Image.open(path) as im:
        return im.size


# -------------------------------------------------------------------- poses
def poses(project: Project, module: str, *, profile: str = "", dry: bool = False,
          force: bool = False, gap: int = 22, runner=None) -> int:
    """Draw the declared puppet frames and wire them into the layout.

    One batch for the module, not one call per frame: a call costs a browser and a
    project, and a module has up to nine frames. Verified per frame afterwards,
    because a frame that did not come back is a card that silently stays static.
    """
    plan = Plan.load(project.require_module(module), _aspect(project))
    iso_dir = project.iso_dir(module)
    iso_dir.mkdir(parents=True, exist_ok=True)

    jobs: list[tuple[Job, str, str, str, int]] = []
    for shot in plan.shots:
        for card in shot.ordered():
            if not card.poses_planned:
                continue
            layout_path = project.card_dir(module, shot.id) / "layout.json"
            if not layout_path.is_file():
                _say(f"  {shot.id}/{card.name}: no layout — isolate first")
                continue
            layout = Layout.load(layout_path)
            slot = layout.get(card.name)
            if slot is None:
                continue
            frames = _spread(card.lands, shot.span, len(card.poses_planned), gap)
            if len(frames) < 2:
                _say(f"  {shot.id}/{card.name}: no room for two swaps — left static")
                continue
            for i, (at, action) in enumerate(zip(frames, card.poses_planned)):
                pose = f"pose{i + 2}"
                stem = f"{shot.id}-{card.name}-{pose}"
                target = project.card_dir(module, shot.id) / f"{card.name}_{pose}.png"
                if target.is_file() and not force:
                    continue
                jobs.append((
                    Job(text=prompt.pose_prompt(card, str(action.get("action", "")),
                                                project.style.chroma),
                        output=stem, ref=str(project.card_dir(module, shot.id) / f"{card.name}.png"),
                        model=project.generation.model),
                    shot.id, card.name, pose, at,
                ))

    if not jobs:
        _say(f"{module}: every declared pose is already drawn")
        return 0
    if dry:
        _say(f"{module}: {len(jobs)} frame(s) would be drawn in "
             f"{-(-len(jobs) // max(1, project.generation.batch_size))} batch(es)")
        return 0

    outcome = run_batch(project, module, [j for j, *_ in jobs], iso_dir,
                        lambda j: _first(iso_dir, j.output),
                        profile=profile, dry=dry, runner=runner, say=_say)
    _say(f"{module}: {outcome.summary()}")
    if outcome.missing:
        return 1
    return _wire_poses(project, plan, jobs)


def _spread(lands: int, span: int, count: int, gap: int) -> list[int]:
    """Frames for the swaps: after the card lands, inside the shot, `gap` apart."""
    start, end = lands + max(6, 10), span - 6
    out: list[int] = []
    t = start
    while len(out) < count and t <= end:
        out.append(t)
        t += gap
    return out


def _wire_poses(project: Project, plan: Plan, jobs) -> int:
    """Align every frame onto its card's canvas and write the list into the layout.

    The canvas is always the base card's size. The renderer maps a card's canvas
    *width* onto the card's stage width, so a frame on a wider canvas draws its
    subject smaller — a man who jumps away from the camera on every swap.
    """
    from .emit.gen_pose import align_to_base

    by_card: dict[tuple[str, str], list[dict]] = {}
    for _job, sid, name, pose, at in jobs:
        src = _first(project.iso_dir(plan.module), f"{sid}-{name}-{pose}")
        if src is None:
            _say(f"  {sid}/{name}/{pose}: no reply")
            return 1
        base_path = project.card_dir(plan.module, sid) / f"{name}.png"
        out_path = project.card_dir(plan.module, sid) / f"{name}_{pose}.png"
        card = plan.shot(sid).card(name)
        keyed = image.chroma_key(image.open_rgb(src),
                                 image.parse_color(project.style.chroma),
                                 project.style.chroma_tolerance, project.style.chroma_feather)
        keyed = image.erase_rects(keyed, card.erase if card else ())
        keyed = image.keep_largest(keyed)
        keyed = image.erode_alpha(keyed, 2)
        aligned, note = align_to_base(image.open_rgba(base_path), keyed, name)
        aligned.save(out_path)
        _say(f"  {sid}/{name}/{pose}: {aligned.width}x{aligned.height} — {note}")
        by_card.setdefault((sid, name), []).append({
            "atFrame": at,
            "src": str(out_path.relative_to(project.root)).replace("\\", "/"),
        })

    for (sid, name), frames in by_card.items():
        path = project.card_dir(plan.module, sid) / "layout.json"
        layout = Layout.load(path)
        slot = layout.elements[name]
        layout.elements[name] = Slot(
            name=slot.name, x=slot.x, y=slot.y, w=slot.w, h=slot.h,
            aspect=slot.aspect, src=slot.src, z=slot.z,
            poses=tuple(sorted(frames, key=lambda f: f["atFrame"])),
        )
        layout.save(path)
    return 0


# -------------------------------------------------------------------- fills
def fills(project: Project, module: str, *, profile: str = "", dry: bool = False,
          force: bool = False, only: tuple[str, ...] = (), runner=None) -> int:
    """Ask for the page behind each shot's pieces, one prompt per shot."""
    plan = Plan.load(project.require_module(module), _aspect(project))
    out = project.mod_build(module) / "fills"
    out.mkdir(parents=True, exist_ok=True)

    jobs = []
    for shot in plan.shots:
        if only and shot.id not in only:
            continue
        if not project.still(module, shot.id).is_file():
            continue
        target = out / f"{shot.id}_0.jpg"
        if target.is_file() and not force:
            continue
        jobs.append(Job(
            text=prompt.fill_prompt(shot, _ground(shot), project.style.chroma),
            output=shot.id, ref=str(project.still(module, shot.id)),
            model=project.generation.model))

    if not jobs:
        _say(f"{module}: every shot already has a fill")
        return 0
    outcome = run_batch(project, module, jobs, out, lambda j: out / f"{j.output}_0.jpg",
                        profile=profile, dry=dry, runner=runner, say=_say)
    if dry:
        return 0
    _say(f"{module}: {outcome.summary()}")
    return 0 if outcome.ok else 1


def _ground(shot) -> str:
    """What stands behind the pieces. Named from the shot's own plate prose, so it
    cannot drift from the composition the still was drawn to."""
    text = shot.latar_plate.strip()
    return text[:240].rstrip(".") if text else "the same newsprint page and colour block"


# -------------------------------------------------------------------- plate
def plates(project: Project, module: str, *, only: tuple[str, ...] = (),
           force: bool = False) -> int:
    """Composite the fill into the holes the pieces left.

    The fill is aligned to the still by phase correlation first. That is the whole
    of the old `--whole` decision: an answer taken from a frame that moved puts
    every card off its own print, so the answer is moved back before it is used.
    Compositing only inside the holes then makes the choice unnecessary — the
    parts of the answer that do not belong are never used.
    """
    cv2 = image._cv2()
    plan = Plan.load(project.require_module(module), _aspect(project))
    made, skipped = 0, []
    for shot in plan.shots:
        if only and shot.id not in only:
            continue
        still_path = project.still(module, shot.id)
        fill_path = project.mod_build(module) / "fills" / f"{shot.id}_0.jpg"
        layout_path = project.card_dir(module, shot.id) / "layout.json"
        target = project.plate(module, shot.id)
        if target.is_file() and not force:
            continue
        if not (still_path.is_file() and fill_path.is_file() and layout_path.is_file()):
            skipped.append(shot.id)
            continue

        still = image.open_rgb(still_path)
        fill = image.open_rgb(fill_path).resize(still.size, Image.LANCZOS)
        still_grey = np.asarray(still.convert("L"), dtype=np.float32)
        fill_grey = np.asarray(fill.convert("L"), dtype=np.float32)
        dx, dy = image.phase_shift(still_grey, fill_grey)
        if abs(dx) > 0.5 or abs(dy) > 0.5:
            fill = fill.transform(fill.size, Image.AFFINE, (1, 0, -dx, 0, 1, -dy),
                                  resample=Image.BICUBIC)

        layout = Layout.load(layout_path)
        hole = np.zeros((still.height, still.width), np.uint8)
        for card in shot.cards:
            slot = layout.get(card.name)
            if slot is None:
                continue
            r = slot.rect
            x0, y0 = int(r.x0 * still.width), int(r.y0 * still.height)
            x1, y1 = int(r.x1 * still.width), int(r.y1 * still.height)
            hole[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = 255
        if not hole.any():
            skipped.append(shot.id)
            continue
        # Grow the mask: the piece's own shadow is part of what it left behind.
        hole = cv2.dilate(hole, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
        plate = np.array(still)
        plate[hole > 0] = np.array(fill)[hole > 0]
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(plate).save(target, quality=95)
        made += 1

    _say(f"{module}: {made} plate(s) built")
    if skipped:
        _say(f"{module}: {len(skipped)} shot(s) cannot be plated yet "
             f"({', '.join(skipped)}) — they need a still, a fill and a layout")
        return 1
    return 0


# -------------------------------------------------------------------- emit
def emit(project: Project, module: str) -> int:
    """Compute the program, write the shot file, and regenerate the two indexes."""
    from .emit import tsx
    from .gates.program import program_of
    from .gates import Context

    plan = Plan.load(project.require_module(module), _aspect(project))
    narration = Narration.from_file(project.transcript(module), project.fps) \
        if project.transcript(module).is_file() else None
    if narration is None:
        _say(f"{module}: no transcript — cannot compute accents")
        return 1

    ctx = Context(project=project, plan=plan, narration=narration)
    prog = program_of(ctx)
    path = tsx.write(prog, project.p("remotion"))
    _say(f"{module}: wrote {path.relative_to(project.root)} "
         f"({len(prog.shots)} shots, {sum(len(s.cards) for s in prog.shots)} cards, "
         f"travels {sorted(prog.travels())}, eases {sorted(prog.eases())})")
    return _indexes(project)


def _indexes(project: Project) -> int:
    from .emit import tsx
    mods = []
    for mod in project.modules():
        try:
            plan = Plan.load(project.plan(mod), _aspect(project))
        except Exception:
            continue
        if plan.shots:
            mods.append((mod, plan.duration))
    if not mods:
        return 0
    files = tsx.write_indexes(mods, project.p("remotion"), fps=project.fps,
                              width=project.width, height=project.height,
                              background=project.style.paper)
    _say(f"indexes: {', '.join(f.name for f in files)} ({len(mods)} module(s))")
    return 0


# -------------------------------------------------------------------- sync
def sync(project: Project, module: str) -> int:
    """Copy the build folder to where the renderer reads it, and only what changed."""
    src_root = project.mod_build(module)
    dst_root = project.root / "remotion" / "public" / module
    if not src_root.is_dir():
        _say(f"{module}: nothing built yet")
        return 1
    copied = 0
    for src in src_root.rglob("*"):
        if not src.is_file() or src.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".json"}:
            continue
        dst = dst_root / src.relative_to(src_root)
        if dst.is_file() and dst.stat().st_mtime >= src.stat().st_mtime \
                and dst.stat().st_size == src.stat().st_size:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        copied += 1
    wav = project.narration(module)
    if wav.is_file():
        audio = project.root / "remotion" / "public" / "audio" / wav.name
        if not audio.is_file() or audio.stat().st_size != wav.stat().st_size:
            audio.parent.mkdir(parents=True, exist_ok=True)
            audio.write_bytes(wav.read_bytes())
            copied += 1
    _say(f"{module}: {copied} file(s) synced to remotion/public/{module}")
    return 0


# ------------------------------------------------------------------ render
def render(project: Project, module: str, *, force: bool = False,
           concurrency: int = 4, runner=None) -> int:
    """Gate, render muted, mux the narration once, then read the file back.

    The readback is the point: the picture must be the narration's length and the
    file must carry audio. A film whose voice runs off the end is not a film.
    """
    from .gates import Context, gate_set, run as run_gates

    plan = Plan.load(project.require_module(module), _aspect(project))
    narration = Narration.from_file(project.transcript(module), project.fps) \
        if project.transcript(module).is_file() else None
    ctx = Context(project=project, plan=plan, narration=narration,
                  lexicon=_json(project.root / "lexicon.json"),
                  facts=_json(project.root / "facts.json"))

    sync(project, module)
    result = run_gates(ctx, gate_set(), use_cache=False)
    print(result.summary())
    if result.failed:
        if not force:
            _say("\nREFUSED — a gate failed. A film that cannot pass its own checks "
                 "is not a deliverable.")
            return 1
        _say("\n--force: rendering with a failed gate. The file will be marked dirty.")
    if not result.complete and not force:
        _say("\nREFUSED — a gate could not run (see N/A above). It has verified nothing.")
        return 1

    kit = project.p("remotion")
    out = kit / "out"
    out.mkdir(parents=True, exist_ok=True)
    mute = out / f"_{module}-mute.mp4"
    run = runner or _subprocess
    _say(f"\n— rendering {module.upper()} —")
    code, log = run([str(kit / "node_modules" / ".bin" / "remotion.cmd"), "render",
                     module.upper(), str(mute), "--muted", f"--concurrency={concurrency}"], kit)
    if code != 0:
        _say(log[-1200:])
        _say(f"FAIL — remotion exited {code}")
        return 1

    wav = project.narration(module)
    if not wav.is_file():
        _say(f"FAIL — no narration at {wav}; the film would be silent")
        return 1
    vdur, _ = _probe(mute)
    adur, _ = _probe(wav)
    if abs(vdur - adur) > 0.05:
        _say(f"FAIL — the picture is {vdur:.2f}s and the narration is {adur:.2f}s. "
             "Do not mux a film whose voice runs off the end.")
        return 1

    final = out / f"{module}-final.mp4"
    code, log = run(["ffmpeg", "-v", "error", "-y", "-i", str(mute), "-i", str(wav),
                     "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(final)], kit)
    if code != 0:
        _say(log[-600:])
        _say("FAIL — could not mux the narration")
        return 1

    dur, has_audio = _probe(final)
    _say(f"{final.relative_to(project.root)}  {dur:.2f}s  "
         f"{final.stat().st_size / 1e6:.0f} MB  audio={'yes' if has_audio else 'NO'}")
    if not has_audio:
        _say("FAIL — the deliverable carries no audio")
        return 1
    if result.failed:
        _say("DIRTY — rendered with a failed gate (--force). Do not present this.")
        return 1
    _say("OK — every gate ran, every gate passed, and the file carries its narration")
    return 0


def _subprocess(cmd, cwd):
    import subprocess
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


def _probe(path: Path) -> tuple[float, bool]:
    import re
    code, out = _subprocess(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                             "-show_entries", "stream=codec_type", "-of", "default=nw=1",
                             str(path)], path.parent)
    m = re.search(r"duration=([\d.]+)", out or "")
    return (float(m.group(1)) if m else 0.0), "codec_type=audio" in (out or "")


def _json(path: Path) -> dict:
    import json
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # A corrupt lexicon is not "no lexicon": the checks it feeds would go quiet.
        raise ValueError(f"{path.name} is not valid JSON — fix it rather than run without it")


def _aspect(project: Project) -> float:
    return project.width / project.height
