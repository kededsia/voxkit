"""Fixtures: a tiny, valid project, and a plan builder that can break one field.

The plan builder is the point. Every test below changes exactly one thing about a
plan that is otherwise valid, so a failing gate is evidence about that one thing
and not about the fixture.

The base plan is deliberately small but *honest*: four cards, two shots that tile
180 frames, one readable card above its covering piece in each shot, no burial,
and every card settling within three frames of the word it names. It passes the
plan-only gates as written — which is the only way a test can show that a gate
rejects something.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from voxkit.config import Project, Style
from voxkit.contract import Plan
from voxkit.gates.base import Context
from voxkit.words import Narration, Word, analyse

FPS = 30
TOTAL = 6.0          # seconds; 180 frames, matching the base plan's last shot


def card(name: str, **kw) -> dict:
    base = {
        "name": name,
        "z": kw.pop("z", 2),
        "bahan": kw.pop("bahan", "foto"),
        "wujud": kw.pop("wujud", "siluet_organik"),
        "semantik": kw.pop("semantik", f"THE {name.upper()}"),
        "semiotik": kw.pop("semiotik", f"a photograph of {name}"),
        "what": kw.pop("what", f"a sepia halftone photograph of {name}"),
        "at": kw.pop("at", "lower left of the frame, centred at 0.25 across, "
                            "about 0.30 of the frame wide"),
        "lands": kw.pop("lands", 30),
        "word": kw.pop("word", "kata"),
    }
    base.update(kw)
    return base


def shot(sid: str, start: int, end: int, cards: list[dict], **kw) -> dict:
    base = {
        "id": sid,
        "range": [start, end],
        "babak": "Babak satu",
        "peran_retoris": "Pembuka babak",
        "latar_plate": "A torn relief map of the province on aged paper, mustard block",
        "tata_letak_kolase": "Asymmetric diagonal: pieces climb from lower right to upper left",
        "jenis": "DIAGRAM",
        "mark": "Red circle around the pass on 'peta'.",
        "marks": [["circle", 14, -4.2, cards[0]["name"], {"delay": 4}]],
        "kamera": "Slow lens pan following the route, locking on the sign at the word.",
        "cards": cards,
        "still_gate": "PASS 40.0",
    }
    base.update(kw)
    return base


def base_shots() -> list[dict]:
    """Two shots, no burial, readable above covering, each card on its own word."""
    return [
        shot("s01", 0, 90, [
            card("peta", z=4, bahan="cetak", wujud="plang_fisik", lands=30, word="peta",
                 at="upper left of the frame, centred at 0.26 across, "
                    "about 0.26 of the frame wide"),
            card("orang", z=3, bahan="figur", wujud="siluet_organik", lands=45, word="orang",
                 at="lower right of the frame, centred at 0.74 across, "
                    "about 0.24 of the frame wide"),
        ]),
        shot("s02", 90, 180, [
            card("foto", z=1, bahan="foto", wujud="plang_fisik", lands=20, word="foto",
                 at="lower left of the frame, centred at 0.30 across, "
                    "about 0.28 of the frame wide"),
            card("slip", z=4, bahan="cetak", wujud="sobekan_pita", lands=60, word="slip",
                 at="upper right of the frame, centred at 0.72 across, "
                    "about 0.22 of the frame wide"),
        ]),
    ]


def plan_dict(*, shots=None, module="t01", context=True) -> dict:
    out = {
        "plan_version": 2,
        "module": module,
        "klaim": "Ada pola.",
        "payoff": "Polanya bisa diukur.",
        "serah": "papan nama",
        "terima": "tidak ada",
        "konteks_modul": {"konteks_budaya": "Sunda"},
        "shots": shots if shots is not None else base_shots(),
    }
    if context:
        out["context"] = {"skills_read": ["a", "b", "c"], "benang_read": ["x"],
                          "laws": ["L-cards"]}
    return out


def make_plan(**kw) -> Plan:
    return Plan.from_dict(plan_dict(**kw), stage_aspect=1920 / 1080)


# ---------------------------------------------------------------- narration
#: The words the base plan's cards land on, at the frames those cards settle.
#: Written out rather than derived: a fixture that computes its own expectations
#: agrees with the code by construction and proves nothing.
NARRATION = [
    ("di", 0.00, 0.18),
    ("sana", 0.18, 0.50),
    ("peta", 0.90, 1.10),        # f27 — `peta` lands at f30
    ("lalu", 1.20, 1.40),
    ("orang", 1.40, 1.70),       # f42 — `orang` lands at f45
    ("datang", 2.00, 2.40),
    ("ke", 2.55, 2.65),
    ("pasar", 2.65, 3.05),
    ("foto", 3.60, 3.90),        # f108 — `foto` lands at f110
    ("lama", 4.00, 4.30),
    ("itu", 4.40, 4.55),
    ("slip", 4.90, 5.20),        # f147 — `slip` lands at f150
    ("akhir", 5.30, 5.70),
]


def make_narration() -> Narration:
    words = [Word(t, a, b, FPS) for t, a, b in NARRATION]
    return Narration(analyse(words, TOTAL), TOTAL, FPS)


# ------------------------------------------------------------------ fixtures
@pytest.fixture
def project(tmp_path: Path) -> Project:
    (tmp_path / "plans").mkdir()
    (tmp_path / "audio").mkdir()
    (tmp_path / "build").mkdir()
    (tmp_path / "remotion").mkdir()
    return Project(root=tmp_path, name="test", style=Style(paper_border=0.0))


@pytest.fixture
def narration() -> Narration:
    """Thirteen words over six seconds, with three pauses long enough to accent.

    Built by hand rather than from a file: a test that needs a 50-second
    transcript to prove an arrival window is a test nobody runs.
    """
    return make_narration()


@pytest.fixture
def write_plan(tmp_path: Path):
    def _write(data: dict, name: str = "t01") -> Path:
        path = tmp_path / "plans" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path
    return _write


@pytest.fixture
def context(project: Project, narration: Narration) -> Context:
    """A context over the base plan, ready for any gate."""
    return Context(project=project, plan=make_plan(), narration=narration)
