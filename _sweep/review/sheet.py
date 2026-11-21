"""A contact sheet of one shot, so a camera move can be *seen* rather than argued.

Twelve frames spread evenly across a shot, tiled with the frame number burned in.
If the camera is moving, the collage shifts and changes scale between tiles; if it
is not, every tile is the same picture with different cards on it.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

OUT = Path("_sweep/rendercheck")


def sheet(video: Path, start: int, span: int, n: int, name: str):
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    want = [int(start + i * (span - 1) / (n - 1)) for i in range(n)]
    tiles = []
    for f in want:
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ok, fr = cap.read()
        if not ok:
            continue
        fr = cv2.resize(fr, (320, 180))
        cv2.putText(fr, f"f{f}", (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(fr, f"f{f}", (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(fr)
    cap.release()
    cols = 4
    rows = (len(tiles) + cols - 1) // cols
    grid = np.zeros((rows * 180, cols * 320, 3), np.uint8)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        grid[r * 180:(r + 1) * 180, c * 320:(c + 1) * 320] = t
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}.png"
    cv2.imwrite(str(p), grid)
    print(p, grid.shape)


if __name__ == "__main__":
    sheet(Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5])
