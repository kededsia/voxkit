"""The batch runner: the verdict is the filesystem, not the exit code.

This is the module's founding failure, written out so it cannot come back:

    `still_run.py` compiled a batch, ran it, promoted whatever came back, printed
    "5 stills ready" and **exited 0** with two of the five missing. A script
    chaining `still_run && build_module` then built on assets that were not there,
    and the error surfaced three stages later as "split_still failed".

A runner is injectable here for the same reason: a test about how a missing file
is counted must not need a browser, an account or a network.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from voxkit.batch import Job, run_batch
from voxkit.config import Generation, Project


def _project(tmp_path: Path, **gen) -> Project:
    root = tmp_path / "film"
    (root / "build").mkdir(parents=True, exist_ok=True)
    return Project(root=root, generation=Generation(**gen))


def _jobs(n: int) -> list[Job]:
    return [Job(text=f"draw {i}", output=f"s{i:02d}") for i in range(1, n + 1)]


def test_a_batch_that_exits_zero_with_files_missing_is_a_failure(tmp_path):
    """The whole reason this module exists. Five asked, three on disk, exit 0."""
    project = _project(tmp_path)
    out = project.root / "build" / "m01"
    out.mkdir(parents=True)

    def runner(cmd, cwd):
        for name in ("s01", "s02", "s03"):
            (out / f"{name}_0.jpg").write_bytes(b"x")
        return 0, "done, 5 prompts"          # says it did all five; it did three

    outcome = run_batch(project, "m01", _jobs(5), out,
                        lambda j: out / f"{j.output}_0.jpg", runner=runner,
                        say=lambda *_: None)
    assert outcome.asked == 5
    assert sorted(outcome.produced) == ["s01", "s02", "s03"]
    assert sorted(outcome.missing) == ["s04", "s05"]
    assert not outcome.ok, "a hole must not be reported as success"


def test_every_batch_is_written_where_the_backend_can_read_it(tmp_path):
    project = _project(tmp_path)
    out = project.root / "build" / "m01"
    seen: list[dict] = []

    def runner(cmd, cwd):
        seen.append(json.loads(Path(cmd[cmd.index("--config") + 1]).read_text("utf-8")))
        return 0, ""

    run_batch(project, "m01", _jobs(2), out, lambda j: out / f"{j.output}_0.jpg",
              runner=runner, say=lambda *_: None)
    assert seen[0]["profile"] == "default"
    assert [p["output_filename"] for p in seen[0]["prompts"]] == ["s01", "s02"]
    assert seen[0]["prompts"][0]["aspect_ratio"] == "16:9"


def test_resume_is_not_passed_without_a_project_to_resume_in(tmp_path):
    """`--resume` skips the rows a previous run already made *in a project*.
    With no project named the backend refuses the whole batch before drawing
    anything, so the flag is a way to lose every prompt at once."""
    project = _project(tmp_path, resume=True)
    cmds = []

    def runner(cmd, cwd):
        cmds.append(list(cmd))
        return 0, ""

    run_batch(project, "m01", _jobs(1), project.root / "build" / "m01",
              lambda j: project.root / "build" / "m01" / f"{j.output}_0.jpg",
              runner=runner, say=lambda *_: None)
    assert "--resume" not in cmds[0]
    assert "--project" not in cmds[0]


def test_resume_is_passed_when_a_project_is_named(tmp_path):
    project = _project(tmp_path, resume=True, project="proj-123")
    cmds = []

    def runner(cmd, cwd):
        cmds.append(list(cmd))
        return 0, ""

    run_batch(project, "m01", _jobs(1), project.root / "build" / "m01",
              lambda j: project.root / "build" / "m01" / f"{j.output}_0.jpg",
              runner=runner, say=lambda *_: None)
    assert "--resume" in cmds[0]
    assert cmds[0][cmds[0].index("--project") + 1] == "proj-123"


def test_batches_are_small_because_more_reads_as_one_person(tmp_path):
    """Three accounts run in parallel came back PUBLIC_ERROR_UNUSUAL_ACTIVITY on
    every prompt: the backend reads three sessions from one address as one person
    misbehaving."""
    project = _project(tmp_path, batch_size=2)
    sizes = []

    def runner(cmd, cwd):
        cfg = json.loads(Path(cmd[cmd.index("--config") + 1]).read_text("utf-8"))
        sizes.append(len(cfg["prompts"]))
        return 0, ""

    run_batch(project, "m01", _jobs(5), project.root / "build" / "m01",
              lambda j: project.root / "build" / "m01" / f"{j.output}_0.jpg",
              runner=runner, say=lambda *_: None)
    assert sizes == [2, 2, 1]


def test_an_empty_batch_asks_for_nothing_and_is_not_a_failure(tmp_path):
    """A stage with nothing left to do must return 0, not "missing: []"."""
    project = _project(tmp_path)
    outcome = run_batch(project, "m01", [], project.root / "build" / "m01",
                        lambda j: None, runner=lambda *a: pytest.fail("ran nothing"),
                        say=lambda *_: None)
    assert outcome.asked == 0 and outcome.ok
