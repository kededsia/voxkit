"""Asset gates: what was actually drawn, measured.

A plan gate answers "is this a good instruction". These answer "did the thing
that came back match it" — and each one exists because a defect reached a render
while every plan gate was honest:

    still  a still that is a colour photograph, not a print
    slot   a piece the model handed back at the wrong size, given a slot that is
           faithful to the asset and wrong about the page
    pose   a puppet frame drawn on a larger canvas than its card, which the
           renderer maps by width — so the figure shrinks on every swap
    plate  a hole solved inward from its rim: a blur where the page should be
    public the renderer's copy of an asset older than the asset itself
"""
from __future__ import annotations

from pathlib import Path

from ..contract import Finding, fail, note, warn
from ..emit.choreography import MIN_SWAP_GAP
from ..image import alpha_bbox, detail, open_rgba, print_report
from .base import Context, Gate, Skipped


def _still_paths(ctx: Context) -> list[Path]:
    return [p for p in (ctx.project.still(ctx.module, s.id) for s in ctx.plan.shots)
            if p.is_file()]


# ------------------------------------------------------------------- still
def still(ctx: Context) -> list[Finding]:
    """Is each still a print, and is it the shape of the stage?

    The prompt asks for a duotone and the model keeps returning a warm full-colour
    photograph. "Duotone" is a print term it treats as a colour grade, so the word
    in the prompt proves nothing and the still has to be measured.
    """
    paths = _still_paths(ctx)
    if not paths:
        raise Skipped("no stills yet — run `vox still <module>`")
    missing = [s.id for s in ctx.plan.shots if not ctx.project.still(ctx.module, s.id).is_file()]
    out: list[Finding] = [fail("still", sid, "no still on disk") for sid in missing]

    want = ctx.project.width / ctx.project.height
    for path in paths:
        sid = path.stem
        report = print_report(path)
        if not report.ok:
            out.append(fail("still", sid, f"reads as a colour photograph: {report.line()}"))
        else:
            out.append(note("still", sid, report.line()))
        w, h = _size(path)
        if w and abs((w / h) - want) > 0.02:
            out.append(fail("still", sid,
                            f"is {w}x{h} ({w / h:.2f}), not the stage's {want:.2f} — "
                            "the collage would be stretched or letterboxed"))
    return out


def _size(path: Path) -> tuple[int, int]:
    from PIL import Image
    with Image.open(path) as im:
        return im.size


# -------------------------------------------------------------------- slot
def slot(ctx: Context) -> list[Finding]:
    """Every piece has a measured slot, it is on the page, and its shape matches
    the piece.

    The slot is measured from the piece's own alpha, so a piece that came back
    30 % too wide gets a slot that is faithful to the asset and wrong about the
    page: the slip runs off the frame edge while the still has every letter. The
    shape test is what catches it before a render does.
    """
    out: list[Finding] = []
    seen = False
    for shot in ctx.plan.shots:
        lay = ctx.project.card_dir(ctx.module, shot.id) / "layout.json"
        if not lay.is_file():
            out.append(fail("slot", shot.id, "no layout.json — the isolate stage has not run"))
            continue
        from ..layout import Layout
        layout = Layout.load(lay)
        seen = True
        for card in shot.cards:
            element = layout.get(card.name)
            if element is None:
                out.append(fail("slot", f"{shot.id}/{card.name}",
                                "has no slot — it would render at a position nobody measured"))
                continue
            off = element.rect.outside(tol=0.002)
            if off and not card.cut:
                out.append(fail("slot", f"{shot.id}/{card.name}",
                                f"its measured slot leaves the page ({', '.join(off)}; "
                                f"{element.rect}). Either the piece came back too large or "
                                "the plan asked for a placement the page cannot hold."))
            png = ctx.project.card_dir(ctx.module, shot.id) / f"{card.name}.png"
            if png.is_file():
                with open_rgba(png) as im:
                    pw, ph = im.size
                want = element.rect.h * ctx.project.height / (element.rect.w * ctx.project.width)
                have = ph / pw if pw else 0
                if want > 0 and abs(have - want) / want > 0.03:
                    out.append(fail("slot", f"{shot.id}/{card.name}",
                                    f"the piece is {pw}x{ph} (aspect {have:.3f}) but its slot "
                                    f"implies {want:.3f} — the card would be stretched"))
    if not seen:
        raise Skipped("no layouts yet — run `vox isolate <module>`")
    return out


# -------------------------------------------------------------------- pose
def pose(ctx: Context) -> list[Finding]:
    """Every declared puppet exists, is wired, and is the same size as its card.

    The renderer maps a card's canvas *width* onto the card's stage width, so a
    frame drawn on a canvas 1.5x wider renders its subject 1.5x smaller. A man
    visibly jumped away from the camera mid-shot on every swap that reached past
    the card, and no gate saw it, because the gate only asked whether the file
    existed. Here it asks whether the frame is the same canvas as the card it
    replaces.
    """
    out: list[Finding] = []
    declared = [(shot, card) for shot in ctx.plan.shots for card in shot.cards
                if card.poses_planned]
    if not declared:
        raise Skipped("no card declares `poses_planned`")

    for shot, card in declared:
        lay = ctx.project.card_dir(ctx.module, shot.id) / "layout.json"
        if not lay.is_file():
            raise Skipped(f"no layout for {shot.id}")
        from ..layout import Layout
        wired = Layout.load(lay).get(card.name)
        poses = wired.poses if wired else ()
        if not poses:
            out.append(fail("pose", f"{shot.id}/{card.name}",
                            f"declares {len(card.poses_planned)} planned action(s) and has no "
                            "wired pose — a declared puppet that was never drawn is a static card"))
            continue

        base = ctx.project.card_dir(ctx.module, shot.id) / f"{card.name}.png"
        if not base.is_file():
            out.append(fail("pose", f"{shot.id}/{card.name}", "the base card is missing"))
            continue
        with open_rgba(base) as im:
            bw, bh = im.size

        frames = sorted((int(p["atFrame"]), str(p["src"])) for p in poses)
        for (a_at, a_src), (b_at, _) in zip(frames, frames[1:]):
            if b_at - a_at < MIN_SWAP_GAP:
                out.append(fail("pose", f"{shot.id}/{card.name}",
                                f"swaps {b_at - a_at} frames apart (f{a_at} → f{b_at}); "
                                f"under {MIN_SWAP_GAP} the puppet vibrates"))
        for at, src in frames:
            # A pose path is module-relative (`m04/cards/s01/x_pose2.png`) because
            # that is how the renderer reads it. Older layouts wrote it relative
            # to the project (`build/m04/...`), so both are accepted here and the
            # file beside the card is the last resort.
            path = ctx.project.root / src
            for candidate in (ctx.project.mod_build(ctx.module) / src,
                              ctx.project.card_dir(ctx.module, shot.id) / Path(src).name):
                if path.is_file():
                    break
                path = candidate if candidate.is_file() else path
            if not path.is_file():
                out.append(fail("pose", f"{shot.id}/{card.name}",
                                f"pose at f{at} points at {src}, which does not exist"))
                continue
            with open_rgba(path) as im:
                pw, ph = im.size
            if (pw, ph) != (bw, bh):
                out.append(fail("pose", f"{shot.id}/{card.name}",
                                f"the frame at f{at} is {pw}x{ph} but its card is {bw}x{bh}. "
                                f"The renderer maps width onto the stage, so this frame draws "
                                f"its subject at {bw / pw:.0%} of its size — the figure jumps."))
            if not 0 <= at <= shot.span:
                out.append(fail("pose", f"{shot.id}/{card.name}",
                                f"pose at f{at} is outside its own shot (0..{shot.span})"))
    return out


# ------------------------------------------------------------------- plate
def plate(ctx: Context) -> list[Finding]:
    """Every shot has a page behind its pieces, and the page is not a blur.

    `PaperStage` falls back to a shared sheet when a plate is missing, so the
    collage loses its background and the mp4 still passes every duration check.
    And a hole solved inward from its rim is a blur, which reads as a printing
    defect: the gap reveals the ground that was behind the piece, it is never
    filled with a different object on the same ground.
    """
    out: list[Finding] = []
    have = 0
    for shot in ctx.plan.shots:
        target = ctx.project.plate(ctx.module, shot.id)
        if not target.is_file():
            out.append(fail("plate", shot.id,
                            "no plate — the stage falls back to the shared sheet and the "
                            "collage loses its background"))
            continue
        have += 1
        still = ctx.project.still(ctx.module, shot.id)
        if not still.is_file():
            continue
        sw, sh = _size(still)
        pw, ph = _size(target)
        if abs((pw / ph) - (sw / sh)) > 0.01:
            out.append(fail("plate", shot.id,
                            f"is {pw}x{ph}, not the still's shape ({sw}x{sh}) — the page "
                            "would be stretched under the pieces"))
        if pw != sw or ph != sh:
            out.append(fail("plate", shot.id,
                            f"is {pw}x{ph} but the still is {sw}x{sh}. The camera only zooms "
                            "in, so the plate must be exactly the page — any other size means "
                            "the pieces and the plate disagree about where things are"))
    if not have:
        raise Skipped("no plates yet — run `vox plate <module>`")
    return out


# ------------------------------------------------------------------ public
def public(ctx: Context) -> list[Finding]:
    """The renderer reads `public/`, not `build/`. Is its copy current?

    Remotion does not read the build folder. A still regenerated and not copied is
    *not in the film*: the render exits 0, the shot looks plausible, and it is the
    previous version of the frame. A check that cannot see the file it is guarding
    is not a check.
    """
    src_root = ctx.project.mod_build(ctx.module)
    dst_root = ctx.project.root / "remotion" / "public" / ctx.module
    if not src_root.is_dir():
        raise Skipped("nothing built yet")
    stale, missing = [], []
    for src in src_root.rglob("*"):
        if not src.is_file() or src.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".json"}:
            continue
        rel = src.relative_to(src_root)
        dst = dst_root / rel
        if not dst.is_file():
            missing.append(rel)
        elif dst.stat().st_mtime < src.stat().st_mtime or dst.stat().st_size != src.stat().st_size:
            stale.append(rel)
    out = []
    for rel in missing[:12]:
        out.append(fail("public", ctx.module, f"{rel} is not in public/ — the render would "
                                              "use a fallback or nothing"))
    for rel in stale[:12]:
        out.append(fail("public", ctx.module, f"{rel} in public/ is older than the build copy"))
    if len(missing) + len(stale) > 24:
        out.append(note("public", ctx.module,
                        f"{len(missing) + len(stale)} files differ in total; "
                        "run `vox sync <module>`"))
    if not missing and not stale:
        out.append(note("public", ctx.module, "public/ is current"))
    return out


GATES = [
    Gate("still", still, _still_paths,
         needs_assets=True,
         asks="each still is a print, and the shape of the stage"),
    Gate("slot", slot,
         lambda c: [c.project.card_dir(c.module, s.id) / "layout.json" for s in c.plan.shots],
         needs_assets=True,
         asks="every piece has a measured slot, on the page, the right shape"),
    Gate("pose", pose,
         lambda c: [c.project.card_dir(c.module, s.id) / "layout.json" for s in c.plan.shots],
         needs_assets=True,
         asks="every declared puppet exists, is wired, and is the size of its card"),
    Gate("plate", plate,
         lambda c: [p for p in (c.project.plate(c.module, s.id) for s in c.plan.shots)
                    if p.is_file()],
         needs_assets=True,
         asks="every shot has a page behind it, and the page is not a blur"),
    Gate("public", public, lambda c: [],
         needs_assets=True,
         asks="the renderer's copy of every asset is current"),
]
