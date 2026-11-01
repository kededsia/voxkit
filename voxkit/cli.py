"""Command line.

    vox init                     write a starter vox.toml here
    vox list                     every gate, and the question it asks
    vox plan  <module>           the plan gates only — free, run before any image
    vox gate  <module>           every gate
    vox words <module>           score the narration, show where the voice lands
    vox still|isolate|poses|fills|plate|emit|sync <module>
    vox run   <module>           the whole chain, in order, stopping at the first stage
                                 that could not finish
    vox render <module>          gate, render muted, mux, read the file back

Exit codes are the contract: 0 means the thing asked for happened. A stage that
produced some of its files and not others returns 1, because a caller chaining
stages must not proceed on a hole.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config, stages
from .contract import Plan
from .gates import Context, gate_set, run as run_gates
from .words import Narration

CONFIG_STUB = """\
[project]
name = "{name}"
fps = 30
width = 1920
height = 1080
language = "id"

[paths]
plans = "plans"
audio = "audio"
assets = "assets"
build = "build"
remotion = "remotion"

[style]
style_key = "assets/style-key.jpg"
paper = "#EFE7D6"
chroma = "#FF00FF"
"""

#: The order the chain runs in. `run` walks it; a stage that returns non-zero
#: stops the walk, because everything after it reads what it would have written.
CHAIN = ("words", "still", "isolate", "fills", "plate", "poses", "emit")


def _project() -> config.Project | None:
    """The project, or None after saying why. `main` returns the exit code; it
    does not raise one, so a caller can test the tool the way a person runs it."""
    try:
        return config.discover()
    except (FileNotFoundError, ValueError) as e:
        # A typo'd key in vox.toml is a file to fix, not a crash to read.
        print(f"{e}", file=sys.stderr)
        return None


def _context(project: config.Project, module: str) -> Context | None:
    path = project.require_module(module)
    try:
        plan = Plan.load(path, project.width / project.height)
    except ValueError as e:
        # A plan that is not valid JSON is a file to fix, not a crash to read.
        print(f"{e}", file=sys.stderr)
        return None
    narration = None
    if project.transcript(module).is_file():
        narration = Narration.from_file(project.transcript(module), project.fps)
    lexicon, facts = {}, {}
    for name, target in (("lexicon.json", lexicon), ("facts.json", facts)):
        path = project.root / name
        if path.is_file():
            import json
            try:
                target.update(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError as e:
                print(f"{name} is not valid JSON ({e}) — fix it, do not run without it",
                      file=sys.stderr)
                return None
    return Context(project=project, plan=plan, narration=narration,
                   lexicon=lexicon, facts=facts)


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(prog="vox", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="write a starter vox.toml in this directory")
    sub.add_parser("list", help="every gate and the question it asks")

    for name, text in (("plan", "the plan gates only (free)"),
                       ("gate", "every gate")):
        p = sub.add_parser(name, help=text)
        p.add_argument("module")
        p.add_argument("--only", default="", help="comma-separated gate names")
        p.add_argument("--no-cache", action="store_true")
        p.add_argument("--quiet", action="store_true", help="only failures and the summary")

    gs = sub.add_parser("gestures", help="what the presenter would draw, and why")
    gs.add_argument("module", nargs="?", default="")
    gs.add_argument("--brief", action="store_true", help="print the presenter's charter")

    # Not a gate: a gate answers yes or no, and the question that was actually
    # asked ("does the camera move?") needed a distribution. See `voxkit.audit`.
    ca = sub.add_parser("camera", help="measure the camera: zoom spread, pan, dead frames")
    ca.add_argument("module", nargs="?", default="")
    ca.add_argument("--all", action="store_true", help="every module that can be built")

    for name in ("words", "still", "isolate", "poses", "fills", "plate", "emit", "sync"):
        p = sub.add_parser(name)
        p.add_argument("module")
        p.add_argument("--profile", default="")
        p.add_argument("--dry", action="store_true")
        p.add_argument("--force", action="store_true")
        p.add_argument("--shots", default="", help="comma-separated shot ids")
        p.add_argument("--pieces", default="",
                       help="comma-separated card names, for a surgical re-isolation")
        if name == "isolate":
            p.add_argument("--crop", action="store_true",
                           help="send a close crop around the piece, for pieces the "
                                "model keeps returning as the whole page")

    r = sub.add_parser("run", help="the whole chain, in order")
    r.add_argument("module")
    r.add_argument("--profile", default="")
    r.add_argument("--from", dest="start", default="", help=f"start at a stage: {', '.join(CHAIN)}")
    r.add_argument("--dry", action="store_true")
    r.add_argument("--render", action="store_true", help="continue into the render")

    rd = sub.add_parser("render")
    rd.add_argument("module")
    rd.add_argument("--force", action="store_true")
    rd.add_argument("--concurrency", type=int, default=4)

    a = ap.parse_args(argv)

    if a.cmd == "init":
        target = Path.cwd() / config.CONFIG_NAME
        if target.exists():
            print(f"{target} already exists")
            return 1
        target.write_text(CONFIG_STUB.format(name=Path.cwd().name), encoding="utf-8")
        print(f"wrote {target.name} — edit the paths, then `vox plan <module>`")
        return 0

    if a.cmd == "list":
        for gate in gate_set():
            kind = "asset" if gate.needs_assets else "free"
            print(f"{gate.name:<9} {kind:<6} {gate.asks}")
        return 0

    project = _project()
    if project is None:
        return 2
    module = getattr(a, "module", "")

    # `camera` reports; it does not gate. It has to run before `require_module`
    # because `--all` names no module, and it must not be filtered by `plan`.
    if a.cmd == "camera":
        from . import audit
        from .gates.base import Skipped

        names = project.modules() if a.all else ([module] if module else [])
        if not names:
            print("vox camera <module>   or   vox camera --all", file=sys.stderr)
            return 2
        worst = 0
        for name in names:
            ctx = _context(project, name)
            if ctx is None:
                continue
            try:
                code, text = audit.camera(ctx)
            except Skipped as e:
                print(f"\n{name}: cannot build the program — {e}")
                continue
            print(f"\n{name}")
            print(text)
            worst = max(worst, code)
        return worst

    # The charter is about the film, not about one module, so it must not require
    # a module to exist — asking for it with no plan is the most likely way a
    # person will read it.
    if a.cmd == "gestures" and getattr(a, "brief", False):
        from .presenter import BRIEF
        print(BRIEF)
        return 0

    try:
        project.require_module(module)
    except FileNotFoundError as e:
        print(f"{e}\nKnown modules: {', '.join(project.modules()) or 'none'}", file=sys.stderr)
        return 2

    if a.cmd in ("plan", "gate"):
        ctx = _context(project, module)
        if ctx is None:
            return 2
        only = [g for g in a.only.split(",") if g]
        # `plan` is every gate that reads no generated file. That includes the
        # ones that need the transcript, because a misprinted word or a gesture
        # drawn before its card arrives is caught just as cheaply as a bad range
        # — and both cost a generation to fix later.
        gates = [g for g in gate_set(only) if a.cmd == "gate" or not g.needs_assets]
        result = run_gates(ctx, gates, use_cache=not a.no_cache)
        if not a.quiet:
            print(result.summary())
            for f in result.findings("warn"):
                print(f"  {f}")
            for f in result.findings("note"):
                print(f"  {f}")
        else:
            print(result.summary())
        return 1 if result.failed else 0

    if a.cmd == "words":
        return stages.words(project, module)

    if a.cmd == "gestures":
        if a.brief:
            from .presenter import BRIEF
            print(BRIEF)
            return 0
        return stages.gestures(project, module)

    only = tuple(s for s in getattr(a, "shots", "").split(",") if s)
    if a.cmd == "still":
        return stages.stills(project, module, profile=a.profile, dry=a.dry,
                             force=a.force, only=only)
    if a.cmd == "isolate":
        pieces = tuple(s for s in getattr(a, "pieces", "").split(",") if s)
        return stages.isolate(project, module, profile=a.profile, dry=a.dry,
                              force=a.force, only=only, pieces=pieces,
                              crop=bool(getattr(a, "crop", False)))
    if a.cmd == "poses":
        return stages.poses(project, module, profile=a.profile, dry=a.dry, force=a.force)
    if a.cmd == "fills":
        return stages.fills(project, module, profile=a.profile, dry=a.dry,
                            force=a.force, only=only)
    if a.cmd == "plate":
        return stages.plates(project, module, only=only, force=a.force)
    if a.cmd == "emit":
        return stages.emit(project, module)
    if a.cmd == "sync":
        return stages.sync(project, module)

    if a.cmd == "run":
        chain = list(CHAIN)
        if a.start:
            if a.start not in chain:
                print(f"unknown stage {a.start!r}; known: {', '.join(chain)}", file=sys.stderr)
                return 2
            chain = chain[chain.index(a.start):]
        for stage in chain:
            print(f"\n=== {module}: {stage} ===")
            code = _one(project, module, stage, a)
            if code != 0:
                print(f"\n{module}: stopped at `{stage}` (exit {code}). "
                      "The stages after it read what it would have written.")
                return code
        if a.render:
            return stages.render(project, module)
        print(f"\n{module}: chain complete — run `vox gate {module}` then `vox render {module}`")
        return 0

    if a.cmd == "render":
        return stages.render(project, module, force=a.force, concurrency=a.concurrency)

    return 2


def _one(project: config.Project, module: str, stage: str, a) -> int:
    if stage == "words":
        return stages.words(project, module)
    if stage == "still":
        return stages.stills(project, module, profile=a.profile, dry=a.dry)
    if stage == "isolate":
        return stages.isolate(project, module, profile=a.profile, dry=a.dry)
    if stage == "fills":
        return stages.fills(project, module, profile=a.profile, dry=a.dry)
    if stage == "plate":
        return stages.plates(project, module)
    if stage == "poses":
        return stages.poses(project, module, profile=a.profile, dry=a.dry)
    if stage == "emit":
        return stages.emit(project, module)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
