"""Does the finished film actually move? Measured from the pixels, not the plan.

This gate exists because of the worst failure this project has produced, and it is
worth stating precisely so it is not repeated:

  The emitter wrote `camera={[{at, x, y, zoom}, …]}` — a key list. `PaperStage`
  read `camera.x`, `camera.y`, `camera.zoom` — all `undefined`. The transform came
  out as `translate(NaNpx, NaNpx) scale(NaN)`, and **a browser discards an invalid
  transform without any error at all**. The camera never moved, in any module, for
  the entire film.

  Every gate was green, because every gate read the *program*, and the program was
  correct. The program was never the thing on screen. The client watched the film
  and said, correctly, "kameranya gak gerak ini".

So this is the one gate that does not read the plan. It decodes the rendered mp4
and measures the camera's own motion between consecutive frames: features are
tracked and a similarity transform is fitted, which gives pan and zoom together.
Phase correlation alone is not enough — it sees translation only, so a push-in
around the frame centre reads as perfectly still, which is exactly the shape of
the bug being guarded against.

A film is not "moving" because a card slid in. A camera that never moves is a
slideshow with better paper. The thresholds are not taste: the reference render
(v2, the one the client approved) sits at 22.5 % still frames with a longest hold
of 22 frames, and the broken build sat at 95.3 % and 211.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..contract import Finding, fail, note
from .base import Context, Gate, Skipped

#: Frames where the camera is essentially still, as a fraction of the film.
#: Not zero — a hold is a legitimate move, and the pen needs the frame to stop.
MAX_STILL = 0.70
#: The longest single frozen run. Two seconds of a locked-off frame is a
#: photograph; past that the viewer has left the page.
MAX_HOLD = 60
#: Below this much movement (px at 640 wide, pan + scale change combined) the
#: frame is counted as still.
STILL_PX = 0.6


def render_path(ctx: Context) -> Path | None:
    """The module's finished render, wherever the pipeline left it."""
    root = ctx.project.root
    for name in (f"{ctx.module}-final.mp4", f"_{ctx.module}-mute.mp4"):
        for base in (root / "remotion" / "out", root / "out"):
            p = base / name
            if p.is_file():
                return p
    return None


def measure(path: Path, limit: int = 1800) -> dict:
    """Pan and zoom per frame, from the decoded film."""
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise Skipped(f"cannot decode {path.name}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = 640
    frames = []
    while len(frames) < limit:
        ok, fr = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        frames.append(cv2.resize(g, (w, int(g.shape[0] * w / g.shape[1]))))
    cap.release()
    if len(frames) < 12:
        raise Skipped("render is too short to judge")

    orb = cv2.ORB_create(900)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    kp = [orb.detectAndCompute(f, None) for f in frames]
    half_diag = (w * w + frames[0].shape[0] ** 2) ** 0.5 / 2

    travel = []
    for (k1, d1), (k2, d2) in zip(kp, kp[1:]):
        if d1 is None or d2 is None or len(k1) < 12 or len(k2) < 12:
            travel.append(0.0)
            continue
        m = bf.match(d1, d2)
        if len(m) < 12:
            travel.append(0.0)
            continue
        p1 = np.float32([k1[x.queryIdx].pt for x in m])
        p2 = np.float32([k2[x.trainIdx].pt for x in m])
        M, _ = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC,
                                           ransacReprojThreshold=2.0)
        if M is None:
            travel.append(0.0)
            continue
        scale = (M[0, 0] ** 2 + M[1, 0] ** 2) ** 0.5
        shift = (M[0, 2] ** 2 + M[1, 2] ** 2) ** 0.5
        travel.append(shift + abs(scale - 1.0) * half_diag)

    arr = np.array(travel)
    still = arr < STILL_PX
    longest = run = 0
    for v in still:
        run = run + 1 if v else 0
        longest = max(longest, run)
    moves = run = 0
    for v in ~still:
        run = run + 1 if v else 0
        if run == 4:
            moves += 1
    return {
        "frames": len(frames),
        "fps": fps,
        "still": float(still.mean()),
        "longest": int(longest),
        "moves": moves,
        "median": float(np.median(arr)),
        "p90": float(np.percentile(arr, 90)),
    }


def motion(ctx: Context) -> list[Finding]:
    path = render_path(ctx)
    if path is None:
        raise Skipped("not rendered yet — this gate reads the film, not the plan")

    m = measure(path)
    out: list[Finding] = []
    secs = m["frames"] / m["fps"]
    if m["still"] > MAX_STILL:
        out.append(fail("motion", ctx.module,
                        f"{m['still'] * 100:.0f}% of the finished film is a still frame "
                        f"(limit {MAX_STILL * 100:.0f}%) — the camera is not moving. The "
                        "plan may be full of moves; this is measured from the pixels, so "
                        "if it says still, the render is still."))
    if m["longest"] > MAX_HOLD:
        out.append(fail("motion", ctx.module,
                        f"the frame is frozen for {m['longest']} frames "
                        f"({m['longest'] / m['fps']:.1f}s) with nothing moving — past "
                        f"{MAX_HOLD / m['fps']:.1f}s the viewer has left the page."))
    out.append(note("motion", ctx.module,
                    f"{secs:.1f}s measured from {path.name}: "
                    f"{m['still'] * 100:.0f}% still, longest hold {m['longest']}f, "
                    f"{m['moves']} moves ({m['moves'] / secs:.2f}/s), "
                    f"median {m['median']:.2f}px/frame, p90 {m['p90']:.1f}px"))
    return out


def _inputs(ctx: Context):
    p = render_path(ctx)
    return [p] if p else []


GATES = [
    Gate("motion", motion, _inputs, needs_assets=True,
         asks="the finished film actually moves — measured from the rendered pixels"),
]
