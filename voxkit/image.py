"""Image operations: keying, measuring, print matching.

Every piece in this film is generated on a **chroma ground** and keyed off it.
That is not a stylistic choice, it is what makes the cut deterministic: a pale
map on white paper has no edge for a segmentation model to find, so the whole
face comes back at partial alpha, and the "cut-out" is a ghost. A background the
subject never contains has a large colour distance everywhere it matters.

The old keyer imported a segmentation model at module scope for a fallback path
that the current pipeline never takes — every spec element carries a chroma
ground — and paid 1.4 s of import on every invocation of every tool that touched
it. Here the optional dependency is imported inside the one function that needs
it, and the supported path needs nothing but numpy and Pillow.

Heavy morphology (connected components, disc dilation, distance transform) needs
`opencv-python-headless`, declared as the `assets` extra and imported lazily. A
plan gate must not pay for it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image, ImageFilter

# A pixel this opaque is ink; below it is rim.
ALPHA_KEEP = 200
# A card that is on the print already is left alone; this is the band within
# which "the print already matches" is true.
SPREAD_TOL = 1.4
# A print has no saturated pixel anywhere. The test is on the tail, not the mean:
# 3 470 saturated pins on a card is 0.4 % of its area, which moves a mean by less
# than one unit and passes any threshold set on it.
HOT = 55


# --------------------------------------------------------------------- io
def open_rgb(path: Path) -> Image.Image:
    with Image.open(path) as im:
        return im.convert("RGB")


def open_rgba(path: Path) -> Image.Image:
    with Image.open(path) as im:
        return im.convert("RGBA")


def parse_color(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    if len(v) != 6:
        raise ValueError(f"colour {value!r} is not #RRGGBB")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def alpha_bbox(im: Image.Image) -> tuple[int, int, int, int] | None:
    """Bounding box of meaningfully opaque pixels, or None when there are none."""
    a = np.array(im.getchannel("A"))
    mask = a > ALPHA_KEEP
    if not mask.any():
        return None
    ys, xs = np.where(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


# ------------------------------------------------------------------ keying
def chroma_key(im: Image.Image, bg: Sequence[int], tol: float = 62.0,
               feather: float = 20.0) -> Image.Image:
    """Key a background colour, then un-blend and despill the rim.

    The ramp gives a soft edge instead of the stair-stepping a binary threshold
    leaves on a torn paper border. The rim is then partly un-blended — a keyed
    edge pixel is a mixture, and `fg = (p - (1-a)·bg) / a` solves for the subject
    — but the ramp marks a 20 %-background pixel fully opaque, so its colour stays
    tinted and the card keeps a 1–2 px outline of the ground. That line is
    invisible on the ground and glaring on cream paper the moment the card moves.

    So despill too: the ground is chosen so that clamping the ground's dominant
    channels toward the third removes the tint and touches nothing else. White
    paper (R = G = B) and black metal are unaffected.
    """
    arr = np.asarray(im.convert("RGB")).astype(np.float32)
    bgv = np.array(bg, np.float32)
    dist = np.sqrt(((arr - bgv) ** 2).sum(axis=2))
    a = np.clip((dist - tol) / max(feather, 1.0), 0.0, 1.0)
    alpha = (a * 255.0).astype(np.uint8)

    solid = a >= 0.02
    af = np.where(solid, a, 1.0)[..., None]
    fg = (arr - (1.0 - a[..., None]) * bgv) / af
    arr = np.where(solid[..., None], np.clip(fg, 0, 255), arr)

    # Despill only where there is something to despill: on a transparent pixel the
    # ground is still pure, and clamping it would turn it black — which does not
    # matter to the PNG but wrecks the print matcher, which reads RGB.
    excess = np.clip(np.minimum(arr[..., 0], arr[..., 2]) - arr[..., 1], 0, None)
    excess = np.where(solid, excess, 0.0)
    arr[..., 0] -= excess
    arr[..., 2] -= excess

    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
    out.putalpha(Image.fromarray(alpha))
    return out


def erase_rects(im: Image.Image, rects: Sequence[Sequence[float]]) -> Image.Image:
    """Zero the alpha inside declared rectangles, in fractions of the canvas.

    A rectangle here is a statement about the *reply*, not about the piece: "the
    thing in this region is page, a neighbour or a shadow — it is not the card".
    It runs before `keep_largest`, because both objects are still on the canvas.
    """
    if not rects:
        return im
    a = np.array(im.getchannel("A"))
    H, W = a.shape
    for rect in rects:
        x0, y0, x1, y1 = (float(v) for v in rect)
        box = (max(0, int(x0 * W)), max(0, int(y0 * H)),
               min(W, int(x1 * W)), min(H, int(y1 * H)))
        if box[2] > box[0] and box[3] > box[1]:
            a[box[1]:box[3], box[0]:box[2]] = 0
    out = im.copy()
    out.putalpha(Image.fromarray(a))
    return out


def erode_alpha(im: Image.Image, px: int) -> Image.Image:
    """Shrink the alpha by `px`, which removes the last of the ground's fringe."""
    if px <= 0:
        return im
    out = im.copy()
    out.putalpha(out.getchannel("A").filter(ImageFilter.MinFilter(2 * px + 1)))
    return out


def keep_largest(im: Image.Image, near: tuple[float, float] | None = None,
                 reach: tuple[float, float] | None = None) -> Image.Image:
    """Drop alpha specks and edge slivers that are not part of the object.

    JPEG ringing along the frame edge leaves pixels a few units outside the
    tolerance, and those become opaque specks pinned to the border. They stretch
    the alpha bbox to the full canvas, so a card measured the full frame and every
    downstream scale came out wrong.

    **Area alone picks the wrong blob.** A strip of the page along the top edge,
    a few pixels tall and as wide as the frame, has more pixels than a small card,
    so "keep the largest" kept the strip and threw the card away. A card is the
    object that sits *on* the page, so a blob touching the border is kept only
    when it is comparable in size *and thickness* to the largest blob that does
    not.

    `near` and `reach` are the answer to the failure this stage kept having. Asked
    for one clipping, the isolate model often returns **all** of them, correctly
    separated from the page — five cards, every one keyed cleanly. Keeping every
    blob within 50 % of the largest then keeps all five, and the piece measures as
    the whole collage. The model was right about *what is ink*; it was wrong about
    *which ink*. Given the point the plan says the piece is at, and roughly how big
    it should be, the choice is arithmetic, not a second opinion.

    The window matters more than the choice. A near-magenta wash between two
    clippings joins them into one blob — m18's `kartu_cara` came back as a single
    1316x750 component holding five pieces, and no amount of "pick the right blob"
    can split what the mask has joined. So the search is *bounded* first: only ink
    inside the window is considered, and then the largest thing in it wins.
    """
    cv2 = _cv2()
    a = np.array(im.getchannel("A"))
    mask = (a > ALPHA_KEEP).astype(np.uint8)
    if mask.sum() == 0:
        return im

    # Break hair-thin bridges first: a faint wash left in a corner joins the card
    # into one blob, and then the bbox is the whole frame. A card is hundreds of
    # pixels thick and survives an opening of 5; a wash does not.
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    if mask.sum() == 0:
        return im

    if near is not None and reach is not None:
        px, py = near
        rw, rh = reach
        h0, w0 = mask.shape
        # A *tight* bound. An earlier version allowed 85 % of the piece's size as
        # slack on each side, which on a large card covers the whole frame and
        # bounds nothing. The plan's box is a good enough statement of where the
        # piece is: 15 % of its own size is room for a torn edge and a slip of
        # misplacement, and no more.
        x0 = int(max(0, px - rw * 0.65))
        x1 = int(min(w0, px + rw * 0.65))
        y0 = int(max(0, py - rh * 0.65))
        y1 = int(min(h0, py + rh * 0.65))
        window = np.zeros_like(mask)
        if x1 > x0 and y1 > y0:
            window[y0:y1, x0:x1] = 1
        bounded = mask & window
        # If the plan pointed at empty page, the bound is wrong, not the ink — fall
        # through to the unbounded rules rather than returning nothing.
        if bounded.sum() > 0.02 * max(1, mask.sum()):
            mask = bounded

    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 2:
        return im

    h, w = mask.shape
    inner, edge = [], []
    for i in range(1, n):
        x, y = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
        bw, bh = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        touches = x <= 1 or y <= 1 or x + bw >= w - 1 or y + bh >= h - 1
        (edge if touches else inner).append((int(stats[i, cv2.CC_STAT_AREA]), i))

    if inner:
        ref_area, ref_id = max(inner)
        rivals = [i for area, i in inner if area >= ref_area * 0.50]
        # Only a reply with more than one *substantial* blob needs a decision. A
        # single piece that came back slightly split is not a collage, and letting
        # the point choose there would throw away the smaller half of a figure.
        if near is not None and len(rivals) > 1:
            # Pick the blob whose box surrounds the point the plan asked for.
            # Distance to the centre alone picks a neighbour when the target is
            # large and off-centre, so a blob that *contains* the point wins.
            px, py = near
            best, best_cost = None, None
            for i in rivals:
                x, y = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
                bw, bh = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
                inside = x <= px <= x + bw and y <= py <= y + bh
                dx = (x + bw / 2 - px) / max(1.0, w)
                dy = (y + bh / 2 - py) / max(1.0, h)
                cost = (0.0 if inside else 1.0) + (dx * dx + dy * dy) ** 0.5
                if best_cost is None or cost < best_cost:
                    best, best_cost = i, cost
            if best is not None:
                # A shadow or a torn sliver of the same piece sits next to it and
                # is part of it; anything not touching the chosen blob is another
                # piece and is dropped.
                keep = {best}
                grown = cv2.dilate((lab == best).astype(np.uint8),
                                   cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
                for _area, i in inner + edge:
                    if i != best and (grown[lab == i].any()):
                        keep.add(i)
                out = im.copy()
                out.putalpha(Image.fromarray(
                    np.where(np.isin(lab, list(keep)), a, 0).astype(np.uint8)))
                return out

        keep = set(rivals)
        ref_thick = min(stats[ref_id, cv2.CC_STAT_WIDTH], stats[ref_id, cv2.CC_STAT_HEIGHT])
        thick = max(0.15 * min(h, w), 0.5 * ref_thick)
        keep |= {
            i for area, i in edge
            if area >= ref_area * 0.50
            and min(stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]) >= thick
        }
    else:
        keep = {max(edge)[1]}

    out = im.copy()
    out.putalpha(Image.fromarray(np.where(np.isin(lab, list(keep)), a, 0).astype(np.uint8)))
    return out


def add_paper_border(im: Image.Image, frac: float = 0.022, seed: int = 7):
    """Put a cut-out on a torn white sheet, with its own shadow, and pad for it.

    Returns `(image, pad)`. A torn edge is not a blurred silhouette: it is the
    same shape with a band of fibre around it, and the width of that band wanders,
    so the outline moves in and out by a few pixels the way a tear does. A
    constant offset reads as a vinyl sticker.
    """
    cv2 = _cv2()
    a = np.array(im.getchannel("A"))
    mask = (a > ALPHA_KEEP).astype(np.uint8)
    h, w = mask.shape
    grow = max(6, int(round(frac * min(w, h))))
    sh = max(4, int(round(grow * 1.1)))
    pad = grow + sh + 2

    W, H = w + 2 * pad, h + 2 * pad
    M = np.zeros((H, W), np.uint8)
    M[pad:pad + h, pad:pad + w] = mask
    outer = _torn(M, grow, seed, grow * 0.85)

    sheet = np.zeros((H, W, 4), np.uint8)
    sheet[..., :3] = (247, 243, 233)
    sheet[..., 3] = outer

    sh_a = cv2.GaussianBlur(outer, (0, 0), max(2.0, grow * 0.6)).astype(np.float32) / 255.0
    shadow = np.zeros((H, W, 4), np.uint8)
    shadow[..., :3] = 28
    shadow[..., 3] = np.clip(sh_a * 255.0 * 0.42, 0, 255).astype(np.uint8)

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.alpha_composite(Image.fromarray(shadow), (sh // 2, sh))
    canvas.alpha_composite(Image.fromarray(sheet), (0, 0))
    canvas.alpha_composite(im, (pad, pad))
    return canvas, pad


def _torn(mask: np.ndarray, grow: int, seed: int, amp: float) -> np.ndarray:
    cv2 = _cv2()
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1))
    grown = cv2.dilate(mask, k)
    dist = cv2.distanceTransform(grown, cv2.DIST_L2, 5)

    rng = np.random.default_rng(seed)
    n = cv2.GaussianBlur(rng.random(mask.shape).astype(np.float32), (0, 0), max(2.0, grow * 1.4))
    span = float(n.max() - n.min())
    n = (n - n.min()) / (span if span > 1e-6 else 1.0)
    return (((dist > n * amp) & (grown > 0)).astype(np.uint8)) * 255


# ------------------------------------------------------------------- print
def print_match(card: Image.Image, still: Image.Image, box: Sequence[float],
                spread_tol: float = SPREAD_TOL):
    """Put a cut card back on the print it was cut from.

    The still is a print — two inks and paper. The isolation is told to keep the
    object "same size, same place, same ink", and it keeps the first two; the
    third it re-renders as the material it recognises. A worn wooden ruler comes
    back as *wood*, saturated brown pasted onto a sepia page. No prompt fixes this,
    because the model is being asked to keep a colour the print does not have.

    So take the print from the still itself: sample the still under the card's
    slot, build a luminance → RGB median table, and map the card through it. The
    card is a cut of that exact still, so this is exact by construction and there
    is nothing to tune. A card already on the print is left alone.

    Returns `(image, note)`.
    """
    a = np.array(card.convert("RGBA")).astype(np.float32)
    m = a[..., 3] > ALPHA_KEEP
    if m.sum() < 200:
        return card, "print: too few pixels"
    rgb = a[..., :3][m]
    spread = rgb.max(1) - rgb.min(1)
    card_spread = float(spread.mean())

    sw, sh = still.size
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(sw, x1), min(sh, y1)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return card, "print: slot off the page"
    ref = np.array(still.convert("RGB")).astype(np.float32)[y0:y1, x0:x1]
    ref_spread = float((ref.max(2) - ref.min(2)).mean())
    hot_card = float((spread > HOT).mean())
    hot_ref = float(((ref.max(2) - ref.min(2)) > HOT).mean())
    if card_spread <= ref_spread * spread_tol and hot_card <= hot_ref + 0.002:
        return card, f"print ok ({card_spread:.0f} vs {ref_spread:.0f}, hot {hot_card:.3f})"

    rl = ref.mean(axis=2) / 255.0
    bins = 24
    idx = np.clip((rl * bins).astype(int), 0, bins - 1).ravel()
    flat = ref.reshape(-1, 3)
    lut = np.zeros((bins, 3), np.float32)
    have = np.zeros(bins, bool)
    for b in range(bins):
        sel = flat[idx == b]
        if len(sel) >= 20:
            lut[b] = np.median(sel, axis=0)
            have[b] = True
    if have.sum() < 4:
        return card, "print: still too flat to sample"
    xs = np.nonzero(have)[0]
    for ch in range(3):
        lut[:, ch] = np.interp(np.arange(bins), xs, lut[xs, ch])

    cl = (a[..., :3].mean(axis=2) / 255.0 * bins - 0.5).clip(0, bins - 1)
    lo = np.floor(cl).astype(int)
    hi = np.minimum(lo + 1, bins - 1)
    f = (cl - lo)[..., None]
    a[..., :3] = lut[lo] * (1 - f) + lut[hi] * f
    out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")
    return out, f"print matched ({card_spread:.0f} -> {ref_spread:.0f})"


# ---------------------------------------------------------------- measuring
@dataclass(frozen=True, slots=True)
class PrintReport:
    chroma_mean: float
    strong: float
    green: float
    cool: float
    top: str
    ok: bool
    why: str

    def line(self) -> str:
        return (f"chroma {self.chroma_mean:5.1f}  strong {self.strong * 100:4.1f}%  "
                f"green {self.green * 100:4.1f}%  cool {self.cool * 100:4.1f}%  "
                f"[{self.top}]  {self.why}")


#: Measured on accepted raw stills, not guessed: chroma mean 39–67, hue almost
#: entirely in the warm 0–60° band. The film's colour blocks are the look; what
#: is forbidden is what a colour photograph brings.
LIMITS = {"green": 0.15, "cool": 0.15}


def print_report(path: Path, limits: dict | None = None) -> PrintReport:
    """Is this still a print, or a colour photograph?

    The prompt asks for a duotone and the model returns a warm full-colour
    photograph, because "duotone" is a print term it treats as a colour grade. So
    the still is measured: how much of it is foliage green, and how much is
    modern digital cool colour. Those two families are the gate; the size of the
    warm chroma is not policed.
    """
    lim = {**LIMITS, **(limits or {})}
    im = open_rgb(path).resize((480, 270), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32)
    chroma = a.max(axis=2) - a.min(axis=2)
    mean = float(chroma.mean())
    strong = float((chroma > 70).mean())

    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(axis=2), a.min(axis=2)
    d = np.maximum(mx - mn, 1e-3)
    hue = np.where(mx == r, ((g - b) / d) % 6,
                   np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60.0
    mask = chroma > 45
    bins = np.zeros(12, np.float32)
    if mask.any():
        idx = (hue[mask] // 30).astype(np.int32) % 12
        np.add.at(bins, idx, 1)
        bins /= max(1, int(mask.sum()))
    green = float(bins[2] + bins[3] + bins[4] + bins[5] * 0.5)
    cool = float(bins[6] + bins[7] + bins[8] + bins[9])

    ok = green <= lim["green"] and cool <= lim["cool"]
    top = ", ".join(f"{int(i * 30)}-{int(i * 30) + 30}deg:{bins[i] * 100:.0f}%"
                    for i in np.argsort(-bins)[:3] if bins[i] > 0.05)
    why = ("FAIL — foliage green: a colour photograph" if green > lim["green"]
           else "FAIL — modern digital cool colour" if cool > lim["cool"]
           else "PASS")
    return PrintReport(mean, strong, green, cool, top, ok, why)


def detail(grey: np.ndarray, box: tuple[int, int, int, int]) -> float:
    """How much structure is inside a region, as a 0..1 number.

    Used on a plate: a hole solved inward from its rim is a blur, and a blur reads
    as a printing defect. Flat paper reads as "space waiting for a card". Both are
    wrong, and both are measurable as a collapse in local variance.
    """
    y0, x0, y1, x1 = box
    y0, x0 = max(0, y0), max(0, x0)
    y1, x1 = min(grey.shape[0], y1), min(grey.shape[1], x1)
    if y1 - y0 < 4 or x1 - x0 < 4:
        return 0.0
    patch = grey[y0:y1, x0:x1].astype(np.float32) / 255.0
    return float(patch.std())


def phase_shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Sub-pixel translation between two frames, by phase correlation.

    Used to decide whether a fill's answer may be taken whole: `--whole` is only
    legal when the frame did not move, because taking a moved answer puts every
    card off its own print.
    """
    A = np.fft.rfft2(a - a.mean())
    B = np.fft.rfft2(b - b.mean())
    cross = A * np.conj(B)
    cross /= np.maximum(np.abs(cross), 1e-9)
    corr = np.fft.irfft2(cross, s=a.shape)
    peak = np.unravel_index(int(np.argmax(corr)), corr.shape)
    dy, dx = peak
    if dy > a.shape[0] // 2:
        dy -= a.shape[0]
    if dx > a.shape[1] // 2:
        dx -= a.shape[1]
    return float(dx), float(dy)


def _cv2():
    """The one place the heavy asset dependency is imported.

    Imported here rather than at module scope on purpose: a plan gate, a camera
    calculation and a TSX emission have no use for connected components, and
    paying 300 ms of import on every one of them is how a two-second build became
    a twenty-second one.
    """
    try:
        import cv2
    except ImportError as e:  # pragma: no cover - depends on the environment
        raise ImportError(
            "the asset stage needs opencv: pip install voxkit[assets]"
        ) from e
    return cv2
