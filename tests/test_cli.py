"""The command line: exit codes are the contract.

`0` means the thing asked for happened. A stage that wrote some of its files and
not others returns non-zero, because a caller chaining stages must not proceed on
a hole — and three tools in the pipeline this replaces returned `exit 0` for work
they had not done.

These tests drive `main(argv)` directly, so they assert on what a person running
the tool actually sees.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from voxkit.cli import CONFIG_STUB, main

from conftest import base_shots, plan_dict


@pytest.fixture
def film(tmp_path: Path, monkeypatch) -> Path:
    """A project on disk with one valid plan, and the cwd inside it."""
    root = tmp_path / "film"
    (root / "plans").mkdir(parents=True)
    (root / "audio").mkdir()
    (root / "vox.toml").write_text(CONFIG_STUB.format(name="film"), encoding="utf-8")
    (root / "plans" / "t01.json").write_text(json.dumps(plan_dict()), encoding="utf-8")
    monkeypatch.chdir(root)
    return root


def test_list_prints_every_gate_and_what_it_asks(film, capsys):
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "schema" in out and "compose" in out and "plate" in out
    assert "free" in out and "asset" in out


def test_a_clean_plan_exits_zero(film, capsys):
    assert main(["plan", "t01"]) == 0
    assert "schema" in capsys.readouterr().out


def test_a_broken_plan_exits_one(film, capsys):
    data = plan_dict()
    data["shots"][0]["cards"][0]["wujud"] = "kertas_licin"
    (film / "plans" / "t01.json").write_text(json.dumps(data), encoding="utf-8")
    assert main(["plan", "t01"]) == 1
    assert "kertas_licin" in capsys.readouterr().out


def test_plan_runs_the_gates_that_need_the_transcript(film, capsys):
    """`vox plan` is every gate that reads no generated file. A misprint and a
    gesture drawn before its card arrived are caught just as cheaply as a bad
    range, and both cost a generation to fix later."""
    assert main(["plan", "t01"]) == 0
    out = capsys.readouterr().out
    assert "arrival" in out and "marks" in out and "data" in out
    assert "still" not in out and "plate" not in out


def test_a_missing_module_is_a_message_not_a_traceback(film, capsys):
    assert main(["plan", "nope"]) == 2
    err = capsys.readouterr().err
    assert "no plan for 'nope'" in err
    assert "Traceback" not in err
    assert "Known modules: t01" in err


def test_a_corrupt_plan_is_a_message_not_a_traceback(film, capsys):
    (film / "plans" / "bad.json").write_text("{oops", encoding="utf-8")
    assert main(["plan", "bad"]) == 2
    err = capsys.readouterr().err
    assert "not valid JSON" in err
    assert "Traceback" not in err


def test_init_writes_a_config_and_refuses_to_overwrite(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert (tmp_path / "vox.toml").is_file()
    assert main(["init"]) == 1
    assert "already exists" in capsys.readouterr().out


def test_a_typo_in_the_config_is_refused(tmp_path, monkeypatch, capsys):
    """A typo'd key is a setting that silently does nothing."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "plans").mkdir()
    (tmp_path / "vox.toml").write_text(
        CONFIG_STUB.format(name="x").replace('plans = "plans"', 'plan = "plans"'),
        encoding="utf-8")
    assert main(["plan", "t01"]) == 2
    err = capsys.readouterr().err
    assert "unknown key" in err
    assert "Traceback" not in err


def test_no_config_anywhere_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["plan", "t01"]) == 2
    assert "vox.toml" in capsys.readouterr().err
