"""The one place images are asked for, and the one place their arrival is checked.

Every generation in this pipeline — still, piece, puppet frame, fill — goes
through `run_batch`. That is not tidiness, it is the fix for a specific failure:
`still_run.py` compiled a batch, ran it, promoted whatever came back, printed
"5 stills ready" and **exited 0** with two of the five missing. A script chaining
`still_run && build_module` then built on assets that were not there, and the
error surfaced three stages later as "split_still failed".

So the contract here is: a batch is not done when the process exits, it is done
when every job's output exists on disk. Anything less is a `BatchOutcome` with
`missing` populated, and the caller must treat that as failure.

Batches are small on purpose. Three accounts were once run in parallel and two
came back `PUBLIC_ERROR_UNUSUAL_ACTIVITY` on every prompt: the backend reads three
browser sessions from one address as one person misbehaving. Six prompts per
call, one profile, and the run finishes.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from .config import Project


@dataclass(frozen=True, slots=True)
class Job:
    """One prompt and the file it must produce."""

    text: str
    output: str                  # output_filename, without extension
    ref: str | None = None
    aspect: str = "16:9"
    model: str = "nano2"

    def as_prompt(self) -> dict:
        p = {"text": self.text, "aspect_ratio": self.aspect, "model": self.model,
             "count": 1, "output_filename": self.output}
        if self.ref:
            p["ref"] = self.ref
        return p


@dataclass
class BatchOutcome:
    asked: int = 0
    produced: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    failed_chunks: int = 0

    @property
    def ok(self) -> bool:
        return not self.missing and not self.failed_chunks

    def summary(self) -> str:
        bits = [f"{len(self.produced)}/{self.asked} produced"]
        if self.missing:
            bits.append(f"missing: {', '.join(self.missing[:8])}"
                        + (" …" if len(self.missing) > 8 else ""))
        if self.failed_chunks:
            bits.append(f"{self.failed_chunks} batch(es) failed")
        return " · ".join(bits)


#: `runner(cmd, cwd) -> (returncode, output)`. Injectable so the batch logic can
#: be tested without a browser, an account, or a network.
Runner = Callable[[Sequence[str], Path], tuple[int, str]]


def default_runner(cmd: Sequence[str], cwd: Path) -> tuple[int, str]:
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def run_batch(project: Project, module: str, jobs: Sequence[Job], out_dir: Path,
              exists: Callable[[Job], Path | None], *, profile: str = "",
              dry: bool = False, runner: Runner | None = None,
              say: Callable[[str], None] = print) -> BatchOutcome:
    """Ask for every job, then check every job. Never reports success for a miss.

    `exists(job)` is how the caller says "this is where the answer would land".
    It is a function rather than a naming convention because the four stages put
    their answers in four different shapes (`s01.jpg`, `s01-x-a.png`,
    `s01-x-pose2.png`, `m01s01_0.jpg`).
    """
    outcome = BatchOutcome(asked=len(jobs))
    if not jobs:
        return outcome

    out_dir.mkdir(parents=True, exist_ok=True)
    size = max(1, project.generation.batch_size)
    tmp = project.build / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    profile = profile or project.generation.profiles[0]
    run = runner or default_runner

    for i in range(0, len(jobs), size):
        chunk = list(jobs[i:i + size])
        cfg = tmp / f"{module}-{profile}-{i // size + 1}.json"
        cfg.write_text(json.dumps({
            "profile": profile,
            "output_dir": str(out_dir),
            "prompts": [j.as_prompt() for j in chunk],
        }, ensure_ascii=False, indent=1), encoding="utf-8")

        if dry:
            say(f"  · batch {i // size + 1}: {len(chunk)} prompt(s) → {cfg.name}")
            continue

        say(f"  · batch {i // size + 1}: {len(chunk)} prompt(s) on {profile}")
        cmd = [project.generation.binary, "run", "--config", str(cfg), "--profile", profile]
        # `--resume` is scoped to a named Flow project: it skips the rows a
        # previous run already made *in that project*. This pipeline never reuses
        # a project id — each batch is a new one — so the flag can only fail, and
        # it fails the whole batch before drawing anything ("--resume needs the
        # run's project"). The real resume is the caller's: every stage skips a
        # job whose output is already on disk, which is checked per file rather
        # than per project. So the flag goes on only when a project is named.
        if project.generation.resume and project.generation.project:
            cmd += ["--project", project.generation.project, "--resume"]
        code, output = run(cmd, project.root)
        for line in output.splitlines()[-6:]:
            say("    " + line)

        # The verdict is the filesystem, not the exit code. A batch that exited 0
        # with two answers missing has produced two answers.
        for job in chunk:
            path = exists(job)
            if path is not None and path.is_file():
                outcome.produced.append(job.output)
            else:
                outcome.missing.append(job.output)
        if code != 0 and not outcome.missing:
            outcome.failed_chunks += 1

    return outcome
