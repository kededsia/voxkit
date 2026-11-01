"""Repair failed isolations until there are none left.

Re-isolating is not idempotent: `--force` on a shot re-cuts pieces that were
already right, and the model is free to miss a different one this time. Round one
of the m15 s04 repair fixed two pieces and broke `foto_wadah_batu`, which had been
correct. A hand-written list of repairs therefore cannot converge — every fix can
create the next fault.

This closes the loop: measure, re-cut only the pieces that are wrong, rebuild the
modules that changed, measure again. It stops when the detector is silent, or when
a round stops making progress (which means the model cannot do that piece and a
human has to look, rather than the tool burning an hour pretending).

    py tools/repair.py               # up to MAX_ROUNDS, every module
    py tools/repair.py m15 m21       # just these
    py tools/repair.py --dry         # print what it would do
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILM = ROOT / "film"
DETECTOR = ROOT / "tools" / "find_bad_pieces.py"
MAX_ROUNDS = 4

#: How many times one piece may be re-cut before the tool stops asking. Some pieces
#: the model simply cannot isolate — a text card among text on a halftone page is
#: the hard case — and a loop that keeps trying is a loop that burns an hour
#: pretending. Two attempts, then it is reported as needing a human.
TRIES = 2

#: The escalation ladder for one piece. It is short on purpose. A close crop around
#: the piece was tried and made things *worse*: the model upscales the crop to its
#: own canvas, so the piece fills most of the reply and the window that selects it
#: has nothing to exclude. What actually fixes these pieces is not a better
#: reference but a better reader — `keep_largest(near=…, reach=…)` bounds the search
#: to the box the plan asked for, so the reply's other clippings are ignored.
#: Re-cutting is therefore only worth doing once more, and only because a fresh
#: sample sometimes separates the ink more cleanly.
LADDER = ((), ())


def run(args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=FILM, text=True,
                          capture_output=capture,
                          env={**_env(), "PYTHONPATH": str(ROOT)})


def _env() -> dict[str, str]:
    import os
    return dict(os.environ)


def repairs(modules: list[str]) -> dict[str, list[list[str]]]:
    """What the detector says to re-cut, grouped by module."""
    if not modules:
        return {}
    out = run([str(DETECTOR), *modules], capture=True)
    found: dict[str, list[list[str]]] = {}
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line.startswith("repair: vox "):
            continue
        argv = line[len("repair: vox "):].split()
        found.setdefault(argv[1], []).append(argv)
    return found


#: The gates a bad cutout can actually cause. A burial in `compose`, a missing
#: slot, a puppet with no art — all of these are the same fault wearing different
#: hats. Anything else (`still`, `program`, `spell`) is not, and re-cutting a piece
#: for it wastes an hour and risks breaking a module that was passing.
CUTOUT_GATES = {"compose", "slot", "pose"}


def gate_failures(modules: list[str]) -> dict[str, set[str]]:
    """Which gates fail, per module. The authority the repair answers to."""
    found: dict[str, set[str]] = {}
    for module in modules:
        r = run(["-m", "voxkit.cli", "gate", module, "--no-cache", "--quiet"],
                capture=True)
        fails = {l.split()[0] for l in (r.stdout or "").splitlines() if "FAIL" in l}
        if fails:
            found[module] = fails
    return found


def main(argv: list[str]) -> int:
    dry = "--dry" in argv
    modules = [a for a in argv[1:] if not a.startswith("-")]
    if not modules:
        modules = [f"m{i:02d}" for i in range(1, 23)]
    attempts: dict[str, int] = {}

    for round_no in range(1, MAX_ROUNDS + 1):
        # Ask the gates first. The detector is a heuristic and it over-fires on a
        # legitimate Vox composition — a big photograph with cards taped over it
        # *is* a box containing smaller boxes. Repairing on the heuristic alone
        # would have re-cut pieces in five modules that pass every gate.
        failing = gate_failures(modules)
        candidates = sorted(m for m, g in failing.items() if g & CUTOUT_GATES)
        if not candidates:
            left = {m: g for m, g in failing.items()}
            if left:
                print("nothing a cutout can fix; these need a plan or a still:")
                for m, g in sorted(left.items()):
                    print(f"  {m}: {' '.join(sorted(g))}")
                return 1
            print(f"round {round_no}: every gate passes")
            return 0
        todo = repairs(candidates)
        # Drop pieces that have already had their tries.
        stubborn: list[str] = []
        for module in list(todo):
            kept = []
            for job in todo[module]:
                key = f"{module}/{' '.join(job)}"
                if attempts.get(key, 0) >= TRIES:
                    stubborn.append(key)
                    continue
                attempts[key] = attempts.get(key, 0) + 1
                kept.append(job)
            if kept:
                todo[module] = kept
            else:
                del todo[module]
        if not todo:
            if stubborn:
                print(f"\n{len(stubborn)} piece(s) the model cannot cut:")
                for key in sorted(set(stubborn)):
                    print(f"  {key}")
                print("these need a new still or a hand-drawn cutout")
                return 1
            print(f"round {round_no}: gates fail but no piece is at fault — "
                  f"see {', '.join(candidates)}")
            return 1
        total = sum(len(v) for v in todo.values())
        print(f"\n=== round {round_no}: {total} piece(s) in "
              f"{len(todo)} module(s) ===")
        for module, jobs in sorted(todo.items()):
            for job in jobs:
                key = f"{module}/{' '.join(job)}"
                step = attempts.get(key, 1) - 1
                extra = list(LADDER[min(step, len(LADDER) - 1)])
                argv = job + extra
                print(f"  {' '.join(argv)}")
                if dry:
                    continue
                r = run(["-m", "voxkit.cli", *argv], capture=True)
                tail = (r.stdout or r.stderr).strip().splitlines()
                print(f"    -> {tail[-1] if tail else '(no output)'}")

        if dry:
            return 0

        # A changed cutout moves the camera and the marks, so the program is
        # recomputed for every module that was touched, then re-gated.
        for module in sorted(todo):
            for stage in ("emit", "sync"):
                run(["-m", "voxkit.cli", stage, module], capture=True)
            gate = run(["-m", "voxkit.cli", "gate", module, "--no-cache", "--quiet"],
                       capture=True)
            fails = [l.split()[0] for l in (gate.stdout or "").splitlines()
                     if "FAIL" in l]
            print(f"  {module} gate: {' '.join(sorted(set(fails))) or 'PASS'}")

    failing = gate_failures(modules)
    if failing:
        print(f"\nstill failing after {MAX_ROUNDS} rounds:")
        for m, g in sorted(failing.items()):
            print(f"  {m}: {' '.join(sorted(g))}")
        print("these need a human or a new still")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
