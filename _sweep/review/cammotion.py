"""Camera motion from a finished film, decomposed into pan and zoom.

Phase correlation alone cannot answer "did the camera move": a push-in around the
frame centre produces almost no *translation*, so a shot that zooms from 1.0 to
1.35 reads as perfectly still. That is exactly the mistake that let a frozen film
pass its own gates.

So features are tracked instead, and a similarity transform (scale + rotation +
translation) is fitted per frame pair. "Motion" is then the change in that
transform, measured as the distance the *corner of the frame* travels:

    travel = |t| + scale_delta * half_diagonal

which counts a pan and a push-in on the same axis, in px of the output frame.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

W = 640


def read(path: Path):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise SystemExit(f"cannot open {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames = []
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        h = int(g.shape[0] * W / g.shape[1])
        frames.append(cv2.resize(g, (W, h)))
    cap.release()
    return frames, fps


def motion(frames):
    orb = cv2.ORB_create(900)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    kp = [orb.detectAndCompute(f, None) for f in frames]
    half_diag = (W * W + frames[0].shape[0] ** 2) ** 0.5 / 2
    out = []
    for (k1, d1), (k2, d2) in zip(kp, kp[1:]):
        if d1 is None or d2 is None or len(k1) < 12 or len(k2) < 12:
            out.append((0.0, 0.0, 0.0))
            continue
        m = bf.match(d1, d2)
        if len(m) < 12:
            out.append((0.0, 0.0, 0.0))
            continue
        p1 = np.float32([k1[x.queryIdx].pt for x in m])
        p2 = np.float32([k2[x.trainIdx].pt for x in m])
        M, _ = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC,
                                           ransacReprojThreshold=2.0)
        if M is None:
            out.append((0.0, 0.0, 0.0))
            continue
        scale = (M[0, 0] ** 2 + M[1, 0] ** 2) ** 0.5
        shift = (M[0, 2] ** 2 + M[1, 2] ** 2) ** 0.5
        out.append((shift, abs(scale - 1.0), shift + abs(scale - 1.0) * half_diag))
    return out


def report(name: str, path: Path):
    frames, fps = read(path)
    if len(frames) < 10:
        print(f"{name}: too short")
        return
    m = np.array(motion(frames))
    travel = m[:, 2]
    still = travel < 0.6
    best = run = 0
    for v in still:
        run = run + 1 if v else 0
        best = max(best, run)
    moves, run = 0, 0
    for v in ~still:
        run = run + 1 if v else 0
        if run == 4:
            moves += 1
    secs = len(frames) / fps
    print(f"\n=== {name}  ({path.name}, {len(frames)}f, {secs:.1f}s)")
    print(f"  travel/frame   median {np.median(travel):5.2f}px  p90 {np.percentile(travel,90):6.2f}px")
    print(f"  pan px/frame   median {np.median(m[:,0]):5.2f}   zoom %/frame median "
          f"{np.median(m[:,1])*100:5.3f}")
    print(f"  still frames   {still.mean()*100:5.1f}%   longest still run {best}f ({best/fps:.2f}s)")
    print(f"  distinct moves {moves:3d}  ({moves/secs:.2f}/s)   frames moving >2px: "
          f"{(travel>2).mean()*100:.1f}%")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        p = Path(arg)
        report(p.parent.name + "/" + p.stem, p)
