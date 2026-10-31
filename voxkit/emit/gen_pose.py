"""Putting a swapped frame back on its card.

The renderer maps a card's canvas **width** onto the card's stage width. So a
frame drawn on a canvas 1.5x wider does not overflow — it draws its subject at
two thirds size, and the figure visibly jumps away from the camera on every swap.
That is exactly what happened to sixty-five frames: a man rendered at 37 % of his
own height, mid-shot, with no gate able to see it because the only question asked
was whether the file existed.

So the canvas is always the base card's size, and the figure inside it is scaled
to the base figure's own height and stood on the base figure's own feet. Height is
the invariant: a raised arm or a turned head changes the width of a silhouette,
not how tall the person is.

A gesture that reaches far past the card is a different matter. Fitting it on both
axes would cut the head, and the head is the one thing that may never be cut — so
the width wins, the height gives way, and a frame that had to give up more than a
tenth of its height is reported rather than quietly squashed.
"""
from __future__ import annotations

from PIL import Image

from .. import image

SHRINK_WARN = 0.90
WIDTH_ROOM = 0.98


def align_to_base(base: Image.Image, pose: Image.Image, name: str = "") -> tuple[Image.Image, str]:
    """Return `(frame, note)` with the frame on a canvas the size of the card."""
    bw, bh = base.size
    bi = image.alpha_bbox(base)
    pi = image.alpha_bbox(pose)
    if bi is None or pi is None:
        return pose.resize((bw, bh), Image.LANCZOS), "no alpha to align"

    bi_h = max(1, bi[3] - bi[1])
    pi_h = max(1, pi[3] - pi[1])
    pi_w = max(1, pi[2] - pi[0])

    k = bi_h / pi_h
    room = WIDTH_ROOM * bw / pi_w
    if room < k:
        k = room

    pw, ph = max(1, round(pose.width * k)), max(1, round(pose.height * k))
    pose = pose.resize((pw, ph), Image.LANCZOS)
    pi = (round(pi[0] * k), round(pi[1] * k), round(pi[2] * k), round(pi[3] * k))

    shrunk = (pi[3] - pi[1]) / bi_h
    note = f"scaled {k:.2f}"
    if shrunk < SHRINK_WARN:
        note += (f" — WARNING fitted to {shrunk:.0%} of the card figure's height to stay "
                 "inside the card; draw this frame with a smaller gesture")

    paste_x = int(round((bi[0] + bi[2]) / 2 - (pi[0] + pi[2]) / 2))
    paste_y = int(round(bi[3] - pi[3]))

    canvas = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    canvas.paste(pose, (paste_x, paste_y), pose)
    return canvas, note
