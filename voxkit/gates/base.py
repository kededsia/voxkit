"""Gate infrastructure: findings as data, one process, cached on real inputs.

A gate answers one question about one artifact and returns findings. It does not
print, does not exit, and does not know what the others are doing. That shape is
what makes a gate testable — and a gate that cannot be shown to reject the bad
case is decoration.

Three properties the previous arrangement lacked:

**One process.** Thirteen gates were thirteen Python processes, six of which
decoded the same card PNGs. Import alone cost 2 s per process because the keyer
module imported a segmentation model at module scope for a code path that never
ran. Here the runner is one process, image work is memoised per path, and the
heavy optional dependency is imported inside the function that needs it.

**Cache keyed on what the gate reads.** Not on the module, not on mtime of the
plan: a digest of the exact files the gate declared, plus the gate's own source.
Change a card and the gates that read cards re-run; change nothing and the whole
set is a file read.

**Findings carry a level.** `fail` blocks, `warn` is a number a person should
see, `note` is context. A gate that can only say "PASS" cannot tell you that a
piece is 63 % buried but still under its own threshold — which is exactly how a
buried card shipped.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from ..config import Project
from ..contract import Finding, Plan, fail
from ..words import Narration

CACHE_DIR = ".vox-cache/gates"


@dataclass
class Context:
    """Everything a gate may read, loaded once per run and shared.

    Assets are opened lazily and memoised, because six gates ask about the same
    card PNG and decoding it six times is the same as decoding it once.
    """

    project: Project
    plan: Plan
    narration: Narration | None = None
    lexicon: dict = field(default_factory=dict)
    facts: dict = field(default_factory=dict)
    _memo: dict = field(default_factory=dict, repr=False)

    @property
    def module(self) -> str:
        return self.plan.module

    @property
    def fps(self) -> int:
        return self.project.fps

    def memo(self, key: str, build: Callable[[], object]):
        """Decode-once helper. `build` runs at most once per key per run."""
        if key not in self._memo:
            self._memo[key] = build()
        return self._memo[key]

    def alpha(self, path: Path):
        """A card's alpha channel as a boolean mask, decoded once."""
        import numpy as np
        from PIL import Image

        def build():
            with Image.open(path) as im:
                return np.array(im.convert("RGBA").getchannel("A")) > 40

        return self.memo(f"alpha:{path}", build)

    def grey(self, path: Path):
        """A frame as a small float greyscale array, for structural comparisons."""
        import numpy as np
        from PIL import Image

        def build():
            with Image.open(path) as im:
                return np.asarray(im.convert("L").resize((688, 384), Image.LANCZOS),
                                  dtype=np.float32)

        return self.memo(f"grey:{path}", build)


class Skipped(Exception):
    """Raised when a gate cannot answer yet because its artifact does not exist.

    Not a pass. A gate that quietly passes because it has nothing to look at is
    the failure mode this whole project keeps rediscovering: twelve gates passed
    on a module whose four declared puppets had never been drawn. A skip is
    recorded, shown, and — for a render — refused.
    """


@dataclass(frozen=True, slots=True)
class Gate:
    """One question, one artifact, findings as data."""

    name: str
    run: Callable[[Context], list[Finding]]
    inputs: Callable[[Context], list[Path]]
    #: True when the gate reads a generated file — a still, a card, a layout, a
    #: plate. Those cannot run until the stage that writes them has run. A gate
    #: that needs only the plan and the transcript is free, and `vox plan` runs
    #: it: the faults that cost the most are the ones caught before an image is
    #: paid for.
    needs_assets: bool = False
    #: Shown by `vox gate --list`.
    asks: str = ""


@dataclass
class GateResult:
    name: str
    findings: list[Finding]
    seconds: float = 0.0
    cached: bool = False
    error: str = ""
    skipped: str = ""

    @property
    def failed(self) -> bool:
        return bool(self.error) or any(f.level == "fail" for f in self.findings)

    @property
    def verdict(self) -> str:
        if self.error:
            return "ERROR"
        if self.skipped:
            return "N/A"
        if any(f.level == "fail" for f in self.findings):
            return "FAIL"
        if any(f.level == "warn" for f in self.findings):
            return "WARN"
        return "PASS"


@dataclass
class RunResult:
    module: str
    results: list[GateResult] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(r.failed for r in self.results)

    @property
    def complete(self) -> bool:
        """True when every gate actually looked at something. A render needs this:
        a skipped gate has not verified the film, it has declined to."""
        return all(not r.skipped and not r.error for r in self.results)

    def findings(self, level: str | None = None) -> list[Finding]:
        out = [f for r in self.results for f in r.findings]
        return [f for f in out if level is None or f.level == level]

    def summary(self) -> str:
        width = max((len(r.name) for r in self.results), default=6)
        lines = []
        for r in self.results:
            tag = " (cache)" if r.cached else (f"  {r.seconds:.1f}s" if r.seconds >= 0.05 else "")
            lines.append(f"{r.name:<{width}}  {r.verdict}{tag}")
            if r.error:
                lines.append(f"          {r.error}")
            if r.skipped:
                lines.append(f"          {r.skipped}")
            for f in r.findings:
                if f.level == "fail":
                    lines.append(f"          {f.where}: {f.message}")
        return "\n".join(lines)


# --------------------------------------------------------------------- cache
def digest(paths: Iterable[Path], root: Path) -> str:
    """Hash what a gate reads. Small files by content, large ones by identity.

    Content for anything under 2 MB, because a layout or a spec is small and an
    edit that keeps the size must still invalidate. Size and mtime above that,
    because hashing a 4 MB still on every run is the cost the cache exists to
    avoid.
    """
    h = hashlib.sha1()
    for p in sorted({Path(p) for p in paths}):
        if not p.is_file():
            continue
        st = p.stat()
        if st.st_size < 2_000_000:
            h.update(p.read_bytes())
        else:
            h.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
        h.update(str(p).encode())
    return h.hexdigest()


class Cache:
    def __init__(self, project: Project, module: str) -> None:
        self.path = project.root / CACHE_DIR / f"{module}.json"
        self.data: dict[str, str] = {}
        if self.path.is_file():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.data = {}

    def hit(self, gate: Gate, key: str) -> bool:
        return self.data.get(gate.name) == key

    def remember(self, gate: Gate, key: str) -> None:
        self.data[gate.name] = key

    def forget(self, gate: Gate) -> None:
        self.data.pop(gate.name, None)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1, sort_keys=True), encoding="utf-8")


def plan_key(plan: Plan) -> str:
    """The plan's own fingerprint.

    Every gate reads the plan, so a changed plan must invalidate every gate — and
    a plan built in memory has no file to hash. Without this the key was constant
    for any plan without a path, and a cached PASS answered for a plan the gate
    had never seen. That is the same class of fault as a gate that passes because
    it has nothing to look at.
    """
    return hashlib.sha1(plan.source.encode("utf-8")).hexdigest()[:16]


# -------------------------------------------------------------------- runner
def run(ctx: Context, gates: Sequence[Gate], *, only: Sequence[str] = (),
        use_cache: bool = True, keep_going: bool = True) -> RunResult:
    """Run gates in order. A crash in one gate is that gate's finding, not the
    end of the run — hidden findings are how a film ships broken."""
    cache = Cache(ctx.project, ctx.module)
    wanted = [g for g in gates if not only or g.name in only]
    result = RunResult(ctx.module)

    for gate in wanted:
        key = (digest([*gate.inputs(ctx), Path(sys.modules[gate.run.__module__].__file__)],
                      ctx.project.root)
               + ":" + plan_key(ctx.plan))
        if use_cache and cache.hit(gate, key):
            result.results.append(GateResult(gate.name, [], 0.0, cached=True))
            continue

        started = time.perf_counter()
        try:
            findings = gate.run(ctx)
        except Skipped as e:
            result.results.append(GateResult(gate.name, [], time.perf_counter() - started,
                                             skipped=str(e)))
            cache.forget(gate)
            continue
        except Exception as e:  # a gate that crashes has found something
            result.results.append(GateResult(
                gate.name, [], time.perf_counter() - started,
                error=f"{type(e).__name__}: {e}",
            ))
            if "--traceback" in sys.argv:
                traceback.print_exc()
            cache.forget(gate)
            if not keep_going:
                break
            continue

        elapsed = time.perf_counter() - started
        res = GateResult(gate.name, list(findings), elapsed)
        result.results.append(res)
        if res.failed:
            cache.forget(gate)
        else:
            cache.remember(gate, key)
        if res.failed and not keep_going:
            break

    if use_cache:
        cache.save()
    return result


def gate_set(names: Sequence[str] | None = None) -> list[Gate]:
    """The registry, in the order a plan is meant to be checked.

    Order matters for reading the output, not for correctness: structure first,
    then the words, then the composition, then the assets. A plan that fails
    `schema` will fail several later gates for the same reason, and seeing the
    root cause first is the whole point.
    """
    from . import assets, plan as plan_gates, program

    registry = [*plan_gates.GATES, *program.GATES, *assets.GATES]
    if names:
        wanted = set(names)
        missing = wanted - {g.name for g in registry}
        if missing:
            raise KeyError(f"unknown gate(s): {', '.join(sorted(missing))}; "
                           f"known: {', '.join(g.name for g in registry)}")
        registry = [g for g in registry if g.name in wanted]
    return registry
