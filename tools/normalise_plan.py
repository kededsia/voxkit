"""Bring a migrated plan up to what the gates actually ask for — idempotently.

Four data fixes, all of them cheap, none of them a regeneration:

1. `cut: true` on a card whose *measured* slot bleeds off a page edge. The slot
   includes the paper border the isolate stage adds, so a card placed along the
   bottom edge has a box a few percent taller than the page; the frame edge trims
   it, which is exactly what `cut` means. Shrinking the slot instead would pull
   the card off its print.
2. `tertutup_alasan` on every readable card that declares `tertutup_boleh`. The
   reason is written from the measurement — which card, how much of the box — so
   it can be reviewed. A flag with nothing above it exempts nothing and is
   removed rather than explained.
3. Two page marks of the same shape and the same length read as one gesture
   printed twice; the second gets its own length. Marks are drawn at render time,
   so nothing that was already drawn changes.
4. Every readable card above the pieces that can lie on it (R6), renumbered 1..n,
   written to the plan *and* the layout — `z` is read from both, and two copies of
   one number is how they drift.

    py tools/normalise_plan.py --dry
    py tools/normalise_plan.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voxkit import config  # noqa: E402
from voxkit.contract import Plan  # noqa: E402
from voxkit.geometry import Placed, buried  # noqa: E402
from voxkit.layout import Layout  # noqa: E402


def _layout(project: config.Project, module: str, shot: str) -> Layout:
    path = project.card_dir(module, shot) / "layout.json"
    return Layout.load(path) if path.is_file() else Layout()


def _put(layout: Layout, name: str, z: int) -> bool:
    slot = layout.get(name)
    if slot is None or slot.z == z:
        return False
    layout.elements[name] = type(slot)(
        name=slot.name, x=slot.x, y=slot.y, w=slot.w, h=slot.h,
        aspect=slot.aspect, src=slot.src, poses=slot.poses, z=z)
    return True


def normalise(project: config.Project, module: str, dry: bool) -> list[str]:
    plan_path = project.plan(module)
    raw = json.loads(plan_path.read_text(encoding="utf-8"))
    plan = Plan.load(plan_path, project.width / project.height)
    notes: list[str] = []

    for shot in raw["shots"]:
        pshot = plan.shot(shot["id"])
        layout = _layout(project, module, shot["id"])
        cards = {c["name"]: c for c in shot["cards"]}
        dirty_layout = False

        # 1 — cut flags, from the measured slot
        for card in pshot.cards:
            slot = layout.get(card.name)
            if slot is None or card.cut:
                continue
            off = slot.rect.outside(tol=0.002)
            if off:
                cards[card.name]["cut"] = True
                notes.append(f"{shot['id']}/{card.name}: slot leaves the page ({', '.join(off)}) "
                             "— marked cut")

        # 2 — a reason for every exemption, or no exemption
        items = [Placed(c.name, (layout.get(c.name).rect if layout.get(c.name) else c.rect),
                        c.z, {}) for c in pshot.cards]
        pairs = buried(items, floor=0.0)
        for card in shot["cards"]:
            if not card.get("tertutup_boleh") or card.get("tertutup_alasan"):
                continue
            above = [(a.name, f) for b, a, f in pairs if b.name == card["name"]]
            if not above:
                card.pop("tertutup_boleh", None)
                card.pop("tertutup_alasan", None)
                notes.append(f"{shot['id']}/{card['name']}: exemption dropped (nothing covers it)")
            else:
                name, frac = max(above, key=lambda t: t[1])
                card["tertutup_alasan"] = (f"terukur: {name} menutup {frac:.0%} kotaknya, "
                                           f"{1 - frac:.0%} terbaca")
                notes.append(f"{shot['id']}/{card['name']}: {card['tertutup_alasan']}")

        # 3 — two page marks of one shape and one length are one gesture printed twice
        seen: dict[tuple, int] = {}
        for i, m in enumerate(shot.get("marks") or []):
            if not (len(m) > 4 and isinstance(m[4], dict)):
                continue
            key = (m[0], m[1])
            if key in seen:
                notes.append(f"{shot['id']}: marks[{i}] '{m[0]}' {m[1]} → {m[1] + 2} frames")
                m[1] = m[1] + 2
            else:
                seen[key] = i

        # 4 — R6: the readable card goes above everything that can lie on it.
        #
        # The exemption is read from the *current* card, not from `pshot`: pass 2
        # may have dropped a stale one a few lines ago, and a card that just lost
        # its exemption is exactly a card that now has to be raised.
        covering = [c for c in pshot.cards if c.covering]
        if covering:
            ceiling = max(c.z for c in covering)
            raised = []
            for c in pshot.cards:
                if not c.readable or cards[c.name].get("tertutup_boleh"):
                    continue
                if any(o.z >= cards[c.name].get("z", c.z) for o in covering):
                    cards[c.name]["z"] = ceiling + 1
                    raised.append(c.name)
            if raised:
                for i, c in enumerate(sorted(shot["cards"], key=lambda c: (c["z"], c["name"])), 1):
                    c["z"] = i
                notes.append(f"{shot['id']}: {', '.join(raised)} raised above z{ceiling}")

        for card in shot["cards"]:
            if _put(layout, card["name"], card["z"]):
                dirty_layout = True
        if dirty_layout and not dry:
            layout.save(project.card_dir(module, shot["id"]) / "layout.json")

    if notes and not dry:
        plan_path.write_text(json.dumps(raw, indent=1, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    return notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("modules", nargs="*")
    ap.add_argument("--root", default="film", type=Path)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    project = config.load(a.root / "vox.toml")
    total = 0
    for module in a.modules or project.modules():
        notes = normalise(project, module, a.dry)
        if notes:
            total += len(notes)
            print(f"{module}:")
            for n in notes:
                print("  ·", n)
    print(f"\n{total} change(s)" + (" (dry run)" if a.dry else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
