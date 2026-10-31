"""Emission: the program is a value, and the TSX is a template over it.

The generator this replaces appended formatted strings to a list, so a defect in
the maths was indistinguishable from a defect in the template, and the only way
to know what a shot did was to read the code it produced. Twenty-two modules
shipped with every card travelling 17 frames and every ease set to "slow"
because nothing between the plan and the render could ask the question.

Here the questions are asked of a value.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from PIL import Image

from voxkit.emit import camera as cam
from voxkit.emit.choreography import (
    CardMotion, ModuleProgram, ShotProgram, build_module, travel_for,
)
from voxkit.emit.gen_pose import align_to_base
from voxkit.emit.tsx import num, render_film, render_module, render_root, write, write_indexes
from voxkit.geometry import Rect
from voxkit.gates import program as prog_gate
from voxkit.gates.base import Context

from conftest import make_narration, make_plan

PLAN = make_plan()


def _plate(sid: str) -> str:
    return f"plates/{sid}.jpg"


def _program(prefix: str = "") -> ModuleProgram:
    return build_module(PLAN, {}, make_narration(), _plate, fps=30,
                        audio="audio/t01.wav", prefix=prefix)


# -------------------------------------------------------------------- travel
@pytest.mark.parametrize("accent,want", [
    (1.00, 14), (0.62, 14), (0.52, 14),
    (0.51, 17), (0.40, 17),
    (0.39, 21), (0.00, 21),
])
def test_travel_answers_the_accent(accent, want):
    """A struck word gets the short float; a calm word gets the long one."""
    assert travel_for(accent) == want


def test_the_module_does_not_move_uniformly():
    """The check that would have caught the dead accent branch: travels must
    differ across a module whose narration has stressed words."""
    prog = _program()
    assert len(prog.travels()) > 1, f"every card travels {prog.travels()}"


def test_a_card_lands_on_the_frame_the_plan_declared():
    prog = _program()
    for shot, src in zip(prog.shots, PLAN.shots):
        for motion, card in zip(shot.cards, src.ordered()):
            assert motion.settle == card.lands
            assert motion.enter + motion.travel == motion.settle
            assert 2 <= motion.travel <= 21


def test_the_program_names_the_files_the_renderer_will_read():
    prog = _program(prefix="t01/")
    shot = PLAN.shot("s01")
    assert prog.shots[0].plate == "plates/s01.jpg"
    for motion, card in zip(prog.shots[0].cards, shot.ordered()):
        assert motion.src == f"t01/cards/s01/{card.name}.png"
    assert "t01/cards/s01/peta.png" in render_module(prog)


# -------------------------------------------------------------------- camera
def test_the_camera_never_zooms_out_past_the_plate():
    """`zoom_floor` used to be able to ask for more image than the page had,
    which is why the pipeline carried a second, overscanned plate per shot."""
    for x, y in ((0.5, 0.5), (0.0, 0.0), (1.0, 1.0), (0.02, 0.98)):
        assert cam.zoom_floor(x, y) >= 1.0


def test_the_frame_arrives_with_the_word_not_after_it():
    """A camera that starts moving on the word it is moving to is already late.
    The key that frames a card sits on the card's own settle frame."""
    from conftest import card, shot
    plan = make_plan(shots=[shot("s01", 0, 90, [
        card("a", z=1, lands=20, word="peta"),
        card("b", z=2, lands=45, word="orang"),
        card("c", z=3, lands=70, word="slang"),
    ])])
    prog = build_module(plan, {}, make_narration(), _plate, fps=30)
    shot_prog = prog.shots[0]
    for motion in shot_prog.cards[1:]:
        assert any(abs(k.at - motion.settle) <= 2 for k in shot_prog.camera), \
            f"nothing frames {motion.name} at its arrival f{motion.settle}"


def test_no_two_camera_keys_are_closer_than_a_jump_cut():
    for shot in _program().shots:
        gaps = [b.at - a.at for a, b in zip(shot.camera, shot.camera[1:])]
        assert all(g >= 8 for g in gaps), gaps


def test_every_camera_key_belongs_to_its_own_shot():
    for shot in _program().shots:
        assert shot.camera, "a shot with no camera keys never moves"
        for k in shot.camera:
            assert 0 <= k.at <= shot.span
            assert 1.0 <= k.zoom <= cam.ZOOM_CAP


def test_a_shot_ends_settled():
    """A shot that ends mid-travel reads as a frame that was cut off."""
    for shot in _program().shots:
        assert shot.camera[-1].at <= shot.span - 2


@pytest.mark.parametrize("name", ["linear", "slow", "fast", "snap", "step"])
def test_every_ease_starts_at_zero_and_ends_at_one(name):
    assert cam.ease(name, 0.0) == pytest.approx(0.0, abs=1e-6)
    assert cam.ease(name, 1.0) == pytest.approx(1.0, abs=1e-6)


def test_an_unknown_ease_is_refused():
    """The renderer would have silently interpolated linearly."""
    with pytest.raises(ValueError, match="unknown ease"):
        cam.ease("bounce", 0.5)


def test_keys_are_cumulative():
    keys = [cam.CamKey(0, 0.4, 0.4, 1.1), cam.CamKey(20, 0.6, 0.6, 1.2, "linear")]
    assert cam.resolve(keys, 0) == (0.4, 0.4, 1.1)
    assert cam.resolve(keys, 20) == (0.6, 0.6, 1.2)
    assert cam.resolve(keys, 10) == pytest.approx((0.5, 0.5, 1.15))
    assert cam.resolve(keys, 999) == (0.6, 0.6, 1.2)


@pytest.mark.parametrize("cx,cy,w,h", [
    (0.50, 0.50, 0.60, 0.60),
    (0.80, 0.50, 0.30, 0.30),
    (0.20, 0.50, 0.30, 0.30),
    (0.50, 0.85, 0.40, 0.20),
])
def test_a_camera_framing_a_piece_keeps_it_in_frame(cx, cy, w, h):
    """A camera that lands exactly on a piece at the edge of the page has nowhere
    to breathe, and the piece is cut by the frame it is supposed to be shown in.
    The tether is 0.68 of the way from the centre for exactly this reason."""
    rect = Rect.from_centre(cx, cy, w, h)
    x, y, zoom = cam.on(rect, 1.20)
    half = 0.5 / zoom
    assert abs(rect.cx - x) + rect.w / 2 <= half + 1e-6
    assert abs(rect.cy - y) + rect.h / 2 <= half + 1e-6


def test_two_keys_too_close_together_are_one_jump_cut():
    kept = cam.keys_at_least([cam.CamKey(0), cam.CamKey(3), cam.CamKey(30)], gap=8)
    assert [k.at for k in kept] == [0, 30]


# --------------------------------------------------------------------- poses
def _figure(size: tuple[int, int], box: tuple[int, int, int, int]) -> Image.Image:
    """An opaque rectangle on a transparent canvas, standing on the bottom edge."""
    a = np.zeros((size[1], size[0]), np.uint8)
    x0, y0, x1, y1 = box
    a[y0:y1, x0:x1] = 255
    rgb = np.full((size[1], size[0], 3), 120, np.uint8)
    return Image.fromarray(np.dstack([rgb, a]), "RGBA")


def test_a_pose_is_always_put_back_on_the_cards_own_canvas():
    """The renderer maps canvas WIDTH onto the card's width, so a frame drawn on
    a wider canvas does not overflow — it draws the subject at two thirds size
    and the figure jumps away from the camera on every swap."""
    base = _figure((200, 400), (40, 50, 160, 400))       # figure 350 tall
    pose = _figure((180, 380), (20, 0, 160, 380))        # same figure, new action
    frame, note = align_to_base(base, pose, "orang")
    assert frame.size == (200, 400)
    assert "WARNING" not in note


def test_a_gesture_too_wide_for_the_card_is_reported_not_squashed():
    """Height gives way to width — the head is the one thing that may never be
    cut — and a frame that lost more than a tenth of its height says so."""
    base = _figure((200, 400), (40, 50, 160, 400))
    pose = _figure((300, 380), (5, 0, 295, 380))         # arms out past the card
    frame, note = align_to_base(base, pose, "orang")
    assert frame.size == (200, 400)
    assert "WARNING" in note and "smaller gesture" in note


# ---------------------------------------------------------------- the emitter
def test_regeneration_is_byte_identical():
    """A regenerated file that differs when nothing changed makes every diff
    unreadable and hides the change that mattered."""
    assert render_module(_program()) == render_module(_program())


def test_num_trims_trailing_zeros():
    assert num(0.5) == "0.5"
    assert num(1.0) == "1"
    assert num(-4.2) == "-4.2"
    assert num(0.123456) == "0.1235"
    assert num(-0.00001) == "0"


def test_write_puts_the_shot_where_remotion_expects_it(tmp_path):
    path = write(_program(), tmp_path)
    assert path == tmp_path / "src" / "shots" / "T01.tsx"
    assert "export const T01" in path.read_text(encoding="utf-8")


def test_the_film_index_is_generated_from_the_plans():
    """Hand-maintained, a module that passed every gate and was missing from the
    map rendered as a placeholder and nothing objected."""
    src = render_film([("t01", 180), ("t02", 240)])
    assert 'import {T01} from "../shots/T01";' in src
    assert 'import {T02} from "../shots/T02";' in src
    assert '{id: "t01", dur: 180},' in src
    assert "Do not edit" in src


def test_the_root_composition_covers_every_module_and_the_whole_film():
    src = render_root([("t01", 180), ("t02", 240)], fps=30, width=1920, height=1080)
    assert 'id="T01"' in src and 'id="T02"' in src
    assert "durationInFrames={420}" in src, "FILM must be the sum, not the last module"


def test_write_indexes_writes_both(tmp_path):
    paths = write_indexes([("t01", 180)], tmp_path)
    assert [p.name for p in paths] == ["Film.tsx", "Root.tsx"]
    assert all(p.is_file() for p in paths)


# ------------------------------------------------------------- the gate rule
def _uniform(travel: int = 17) -> ModuleProgram:
    """A module where nothing moves differently from anything else — the shape
    twenty-two real modules had."""
    rect = Rect.from_centre(0.5, 0.5, 0.3, 0.3)
    cards = tuple(
        CardMotion(name=f"c{i}", src=f"cards/s01/c{i}.png", enter=settle - travel,
                   settle=settle, travel=travel, from_side="left", stepped=2,
                   phase=0.5, kind="photo", rect=rect, poses=())
        for i, settle in enumerate((20, 35, 50, 65))
    )
    camera = tuple(cam.CamKey(at, 0.5, 0.5, 1.1, "slow") for at in (0, 20, 40, 60, 84))
    return ModuleProgram(module="t01", fps=30, shots=(
        ShotProgram(id="s01", start=0, span=90, plate="plates/s01.jpg",
                    cards=cards, camera=camera),
    ))


def _gate_ctx(context) -> Context:
    return Context(project=context.project, plan=context.plan, narration=make_narration())


def test_the_program_gate_rejects_a_module_that_moves_uniformly(context, monkeypatch):
    monkeypatch.setattr(prog_gate, "program_of", lambda ctx: _uniform())
    messages = [f.message for f in prog_gate.program(_gate_ctx(context)) if f.level == "fail"]
    assert any("travels 17 frames" in m for m in messages)
    assert any("eases 'slow'" in m for m in messages)


def test_the_program_gate_accepts_a_module_that_varies(context, monkeypatch):
    prog = _uniform()
    cards = tuple(replace(c, travel=t, enter=c.settle - t)
                  for c, t in zip(prog.shots[0].cards, (14, 17, 21, 14)))
    camera = tuple(replace(k, ease=e) for k, e in
                   zip(prog.shots[0].camera, ("slow", "snap", "slow", "snap", "slow")))
    varied = ModuleProgram(module="t01", fps=30, shots=(
        ShotProgram(id="s01", start=0, span=90, plate="plates/s01.jpg",
                    cards=cards, camera=camera),
    ))
    monkeypatch.setattr(prog_gate, "program_of", lambda ctx: varied)
    findings = prog_gate.program(_gate_ctx(context))
    assert not [f for f in findings if f.level == "fail"], [f.message for f in findings]


def test_the_program_gate_rejects_a_card_that_does_not_land_on_its_word(context, monkeypatch):
    prog = _uniform(travel=14)
    cards = tuple(replace(c, enter=c.settle - 17) for c in prog.shots[0].cards)
    broken = ModuleProgram(module="t01", fps=30, shots=(
        ShotProgram(id="s01", start=0, span=90, plate="plates/s01.jpg",
                    cards=cards, camera=prog.shots[0].camera),
    ))
    monkeypatch.setattr(prog_gate, "program_of", lambda ctx: broken)
    messages = [f.message for f in prog_gate.program(_gate_ctx(context)) if f.level == "fail"]
    assert any("not at its word" in m for m in messages)
