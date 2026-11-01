"""Does anything cover a person's head? v2 had a tool for this; v3 has none.

For every shot: paint the cards onto a stage-sized owner map in z order, then for
each organic silhouette take its head-and-neck band (voxkit.geometry.head_band)
and ask how much of that band is owned by a card above it.

Static: the worst case over the whole shot, which is what v2's piece_audit did.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from voxkit import config
from voxkit.contract import Plan
from voxkit.geometry import head_band
from voxkit.layout import Layout

SW, SH = 640, 360
COVER = 0.10          # v2's pass mark, same number

# `siluet_organik` is every organic cut-out — a river, a tree, a palace, a map.
# The rule is about *people*, so the set has to be named. A puppet is a person by
# definition; the rest are found by the noun the plan gave them.
PERSON = ("orang", "figur", "petani", "penjaga", "nelayan", "petugas", "peneliti",
          "juru", "pembaca", "pencatat", "penulis", "arkeolog", "pangeran",
          "brahmana", "purwocaraka", "geolog", "penggembala", "penggali", "tukang",
          "penghitung", "pencari", "pengemudi", "warga", "pendatang", "pengambil",
          "penonton", "penyimpan", "perenung", "penyaksi", "penutur", "pengukur",
          "pejalan", "penemu", "pengirim", "pendengar", "pendaki", "penyusur",
          "filolog", "pedagang", "penjual", "pengrajin", "siswa", "guru", "sopir",
          "ibu", "bapak", "anak", "pria", "wanita", "lelaki", "perempuan",
          "pembuat", "pekerja", "buruh", "penari", "penabuh", "pemain")


def is_person(card) -> bool:
    if card.poses_planned or card.head:
        return True
    return any(w in card.name for w in PERSON)

proj = config.discover(Path("."))
rows = []
for i in range(1, 23):
    m = f"m{i:02d}"
    plan = Plan.load(proj.require_module(m), proj.width / proj.height)
    for shot in plan.shots:
        lp = proj.card_dir(m, shot.id) / "layout.json"
        if not lp.is_file():
            continue
        layout = Layout.load(lp)
        ordered = sorted(shot.ordered(), key=lambda c: c.z)
        owner = np.full((SH, SW), -1, dtype=np.int16)
        placed = []
        for idx, card in enumerate(ordered):
            slot = layout.get(card.name)
            png = proj.card_dir(m, shot.id) / f"{card.name}.png"
            if slot is None or not png.is_file():
                placed.append(None)
                continue
            alpha = np.array(Image.open(png).convert("RGBA"))[..., 3]
            x0 = int(round(slot.rect.x0 * SW))
            y0 = int(round(slot.rect.y0 * SH))
            w = max(1, int(round(slot.rect.w * SW)))
            h = max(1, int(round(slot.rect.h * SH)))
            small = np.array(Image.fromarray(alpha).resize((w, h), Image.BILINEAR)) > 40
            # clip to the stage
            sx0, sy0 = max(0, x0), max(0, y0)
            sx1, sy1 = min(SW, x0 + w), min(SH, y0 + h)
            if sx1 <= sx0 or sy1 <= sy0:
                placed.append(None)
                continue
            sub = owner[sy0:sy1, sx0:sx1]
            cut = small[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]
            sub[cut] = idx
            placed.append((idx, card, alpha, (x0, y0, w, h), small))

        for p in placed:
            if p is None:
                continue
            idx, card, alpha, (x0, y0, w, h), small = p
            if card.wujud != "siluet_organik" or card.tertutup_boleh:
                continue
            if not is_person(card):
                continue
            hb = head_band(alpha, card.head)
            if not hb.any():
                continue
            hbs = np.array(Image.fromarray(hb.astype(np.uint8) * 255)
                           .resize((w, h), Image.NEAREST)) > 40
            hbs &= small
            if not hbs.any():
                continue
            sx0, sy0 = max(0, x0), max(0, y0)
            sx1, sy1 = min(SW, x0 + w), min(SH, y0 + h)
            band = hbs[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]
            own = owner[sy0:sy1, sx0:sx1]
            cov = (own > idx) & band
            share = cov.sum() / max(1, band.sum())
            if share >= COVER:
                by = {}
                for q in placed:
                    if q is None or q[0] <= idx:
                        continue
                    hit = (own == q[0]) & band
                    if hit.any():
                        by[q[1].name] = round(hit.sum() / band.sum(), 2)
                rows.append(dict(module=m, shot=shot.id, card=card.name,
                                 cover=round(float(share), 3), by=by, z=card.z))

rows.sort(key=lambda r: -r["cover"])
print(f"PERSON cut-outs with a head band covered >= {COVER:.0%}: {len(rows)}")
for r in rows[:25]:
    print(f"  {r['module']} {r['shot']} {r['card']:26s} z{r['z']:2d} "
          f"{r['cover']:.0%} by {r['by']}")
json.dump(rows, open("_heads.json", "w"), indent=1)
