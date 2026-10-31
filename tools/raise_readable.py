"""Put every readable card above the pieces that can lie on it (R6), and renumber.

The rule is blunt on purpose: the camera moves layers by different amounts, so a
figure that only touches a slip in the still lies across the words by frame 300.
The old toolchain fixed this in the renderer (`uncover.py` swapped two layers at
a time); here the order is data, so it is fixed once in the plan and the layout
together — the two places `z` is read from.

Renumbering keeps the shot's existing order wherever the rule does not force a
change, so a module that was composed by hand is not reshuffled by a tool.

    py tools/raise_readable.py --dry
    py tools/raise_readable.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voxkit import config  # noqa: E402
from voxkit.contract import Plan  # noqa: E402
from voxkit.layout import Layout  # noqa: E402


def fix(project: config.Project, module: str, dry: bool) -> list[str]:
    plan_path = project.plan(module)
    raw = json.loads(plan_path.read_text(encoding="utf-8"))
    plan = Plan.load(plan_path, project.width / project.height)
    notes: list[str] = []

    for shot in raw["shots"]:
        pshot = plan.shot(shot["id"])
        cards = {c["name"]: c for c in shot["cards"]}
        covering = [c for c in pshot.cards if c.covering]
        if not covering:
            continue
        ceiling = max(c.z for c in covering)
        moved = []
        for c in pshot.cards:
            if not c.readable or c.tertutup_boleh:
                continue
            if any(o.z >= c.z for o in covering):
                cards[c.name]["z"] = ceiling + 1
                moved.append(c.name)
        if not moved:
            continue
        # Renumber 1..n, keeping the order the plan already had.
        order = sorted(shot["cards"], key=lambda c: (c["z"], c["name"]))
        for i, c in enumerate(order, 1):
            c["z"] = i
        notes.append(f"{shot['id']}: {', '.join(moved)} raised above z{ceiling}")

        lay_path = project.card_dir(module, shot["id"]) / "layout.json"
        if lay_path.is_file():
            lay = Layout.load(lay_path)
            for name, z in ((c["name"], c["z"]) for c in shot["cards"]):
                if name in lay.elements:
                    slot = lay.elements[name]
                    lay.elements[name] = type(slot)(
                        name=slot.name, x=slot.x, y=slot.y, w=slot.w, h=slot.h,
                        aspect=slot.aspect, src=slot.src, z=z, poses=slot.poses)
            if not dry:
                lay.save(lay_path)

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
        notes = fix(project, module, a.dry)
        if notes:
            total += len(notes)
            print(f"{module}:")
            for n in notes:
                print("  ·", n)
    print(f"\n{total} shot(s) reordered" + (" (dry run)" if a.dry else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
