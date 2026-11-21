"""Gates: every one is shown rejecting the fault it exists for.

A gate that cannot be shown to fail on the bad case is decoration. Each test
below takes the valid base plan, changes one thing, and asserts the specific gate
notices — because the faults listed here are the ones that actually shipped:

    a misprint drawn faithfully by the model
    a gesture drawn on blank paper before its card arrived
    a card whose bottom edge left the page
    a slip under a photograph
    a printed card under a figure
    a module where nothing moves differently from anything else
"""
from __future__ import annotations

import json

import pytest

from voxkit.contract import Plan
from voxkit.gates import base as gbase
from voxkit.gates.base import Context, Gate, run
from voxkit.gates.plan import GATES as PLAN_GATES
from voxkit.gates.program import GATES as PROGRAM_GATES
from voxkit.gates.base import gate_set

from conftest import base_shots, card, make_plan, shot

FREE = [g.name for g in gate_set() if not g.needs_assets]


def _run(ctx: Context, only=None, **kw):
    return run(ctx, gate_set(only), **kw)


def _fails(result, gate: str) -> list[str]:
    """`where: message` for each failure, because which piece is half the finding."""
    return [f"{f.where}: {f.message}" for f in result.findings("fail") if f.gate == gate]


def _ctx(ctx: Context, plan: Plan) -> Context:
    return Context(project=ctx.project, plan=plan, narration=ctx.narration,
                   lexicon=ctx.lexicon, facts=ctx.facts)


# ------------------------------------------------------------------- the base
def test_the_base_plan_passes_every_free_gate(context):
    """If this fails, every other test in this file is measuring the fixture."""
    result = _run(context, FREE)
    assert not result.failed, result.summary()
    assert result.complete, "every free gate should have looked at something"


def test_every_free_gate_reads_no_generated_file(context):
    """`vox plan` runs the free ones. A gate that needs a still must not be among
    them, and one that only needs the transcript must not be excluded — the
    arrival window and the misprint are caught just as cheaply as a bad range."""
    assert "arrival" in FREE and "marks" in FREE and "data" in FREE and "spell" in FREE
    assert "still" not in FREE and "plate" not in FREE and "program" not in FREE


def test_the_base_plan_passes_the_whole_registry_except_the_asset_gates(context):
    """The asset gates need stills and layouts, so they skip — but nothing in the
    plan, the marks or the arrival window may fail."""
    result = _run(context, [g.name for g in PLAN_GATES])
    assert not result.failed, result.summary()


# --------------------------------------------------------------------- spell
def test_a_misprint_is_caught_before_it_is_drawn(context):
    """`CAHI` reached a render twice and read as a typo because it was one."""
    shots = base_shots()
    shots[0]["cards"][0]["semantik"] = "CAHI DARI CIANJUR"
    ctx = _ctx(context, make_plan(shots=shots))
    ctx.lexicon = {"terms": [{"correct": "cai", "never": ["cahi"]}]}
    messages = _fails(_run(ctx, ["spell"]), "spell")
    assert any("cahi" in m and "cai" in m for m in messages)


def test_a_clean_plan_says_nothing_about_spelling(context):
    ctx = _ctx(context, make_plan())
    ctx.lexicon = {"terms": [{"correct": "cai", "never": ["cahi"]}]}
    assert not _fails(_run(ctx, ["spell"]), "spell")


def test_no_lexicon_is_a_note_not_a_pass(context):
    """Silence would be indistinguishable from "checked and clean"."""
    result = _run(context, ["spell"])
    assert [f.level for f in result.findings()] == ["note"]


def test_a_misprint_in_prose_is_caught_not_only_on_a_card(context):
    """`CHI` survived in `klaim`, `tesis_modul`, `fokus` and `semiotik` — four
    fields the old gate never opened, while the two fields it did open were the
    two that got fixed. A gate that only reads the fields the last bug used is a
    gate that catches the last bug."""
    plan = make_plan()
    object.__setattr__(plan, "klaim", "294 dari 1.000 nama berawalan suku kata CHI")
    ctx = _ctx(context, plan)
    ctx.lexicon = {"words": [{"correct": "ci", "never": ["chi"]}]}
    messages = _fails(_run(ctx, ["spell"]), "spell")
    assert any("klaim" in m and "chi" in m for m in messages), messages


def test_a_misprint_the_voice_says_is_caught(context):
    """The voice is what the viewer hears. A card is checked *against* the
    transcript by `arrival` and `data`, so a word misspelled in both agreed with
    itself and passed every gate in the registry."""
    from voxkit.words import Narration, Word, analyse

    words = [Word(w.text, w.start, w.end, w.fps) for w in context.narration.words]
    first = words[0]
    words[0] = Word("Chi", first.start, first.end, first.fps)
    spoken = Narration(analyse(words, context.narration.total),
                       context.narration.total, context.narration.fps)

    ctx = Context(project=context.project, plan=make_plan(), narration=spoken,
                  lexicon={"words": [{"correct": "ci", "never": ["chi"]}]})
    messages = _fails(_run(ctx, ["spell"]), "spell")
    assert any("narration" in m for m in messages), messages


def test_the_gate_reads_the_key_the_file_is_authored_with(context):
    """The bug in one line: the file said `words`, the reader asked for `terms`,
    and the gate passed over zero terms."""
    plan = make_plan()
    object.__setattr__(plan, "klaim", "berawalan suku kata CHI")
    ctx = _ctx(context, plan)
    ctx.lexicon = {"words": [{"correct": "ci", "never": ["chi"]}]}
    assert _fails(_run(ctx, ["spell"]), "spell"), "read `words` and checked nothing"


# --------------------------------------------------------------------- marks
def test_a_bound_mark_with_an_absolute_frame_is_caught(context):
    """The number that drifted: an absolute frame is not tied to the card.

    This is the defect the client saw — arrows and strokes arriving on a card the
    camera had already left. `at` was a frame typed into the plan and nothing
    compared it with the card's own landing, so it drifted by up to 240 frames.
    A bound mark must say `delay`, which is re-read against the landing every
    time the plan is emitted.
    """
    shots = base_shots()
    shots[0]["marks"] = [["circle", 14, -4.2, "orang", {"at": 30}]]
    ctx = _ctx(context, make_plan(shots=shots))
    messages = _fails(_run(ctx, ["marks"]), "marks")
    assert any("absolute `at`" in m for m in messages)


def test_a_mark_that_starts_long_after_its_card_lands_is_caught(context):
    """A gesture that answers a word the voice finished with is a stray line."""
    shots = base_shots()
    shots[0]["marks"] = [["circle", 14, -4.2, "orang", {"delay": 40}]]
    ctx = _ctx(context, make_plan(shots=shots))
    messages = _fails(_run(ctx, ["marks"]), "marks")
    assert any("delay 40 is outside" in m for m in messages)


def test_a_mark_on_a_card_the_shot_does_not_have_is_caught(context):
    shots = base_shots()
    shots[0]["marks"] = [["circle", 14, -4.2, "hantu", {"delay": 2}]]
    ctx = _ctx(context, make_plan(shots=shots))
    assert any("does not have" in m for m in _fails(_run(ctx, ["marks"]), "marks"))


def test_a_shape_outside_the_renderer_is_caught(context):
    """The executor is faithful: it draws a perfectly rendered *other* gesture."""
    shots = base_shots()
    shots[0]["marks"] = [["zigzag-double", 14, -4.2, "peta", {"delay": 2}]]
    ctx = _ctx(context, make_plan(shots=shots))
    assert any("vocabulary" in m for m in _fails(_run(ctx, ["marks"]), "marks"))


def test_one_gesture_printed_twice_is_caught(context):
    """Two page marks, one shape, one length: one gesture printed twice.

    Page marks only — a mark bound to a card is one job on one card, and six of
    them on six cards are six jobs. The rule used to test `bound`, which is the
    opposite set.
    """
    shots = base_shots()
    box = [0.1, 0.1, 0.4, 0.3]
    shots[0]["marks"] = [["circle", 14, -4.2, "peta", {"box": box, "at": 34}],
                         ["circle", 14, 1.9, "orang", {"box": [0.5, 0.5, 0.9, 0.9],
                                                       "at": 50}]]
    ctx = _ctx(context, make_plan(shots=shots))
    assert any("printed twice" in m for m in _fails(_run(ctx, ["marks"]), "marks"))


def test_a_lattice_of_equal_angles_is_caught(context):
    """Six underlines at ±0.7 is a pattern even when each is bound to its card."""
    shots = base_shots()
    shots[0]["marks"] = [
        ["underline", 10, 0.7, "peta", {"delay": 2}],
        ["underline", 12, -0.7, "peta", {"delay": 6}],
        ["underline", 14, 0.72, "orang", {"delay": 2}],
    ]
    ctx = _ctx(context, make_plan(shots=shots))
    assert any("lattice" in m for m in _fails(_run(ctx, ["marks"]), "marks"))


def test_a_shot_with_no_marks_is_caught(context):
    shots = base_shots()
    shots[0]["marks"] = []
    ctx = _ctx(context, make_plan(shots=shots))
    assert any("no marks" in m for m in _fails(_run(ctx, ["marks"]), "marks"))


# ------------------------------------------------------------------- compose
def test_a_card_that_leaves_the_page_is_caught(context):
    """The guard used to look only at `across`, so a strip pinned at `down at
    0.94` lost its bottom edge in silence."""
    shots = base_shots()
    shots[0]["cards"][1]["at"] = ("bottom of the frame, centred at 0.74 across, "
                                  "about 0.34 of the frame wide")
    ctx = _ctx(context, make_plan(shots=shots))
    messages = _fails(_run(ctx, ["compose"]), "compose")
    assert any("bottom" in m for m in messages)


def test_a_card_marked_cut_may_leave_the_page(context):
    """A piece torn off at the edge is a composition, not a mistake."""
    shots = base_shots()
    shots[0]["cards"][1]["at"] = ("bottom of the frame, centred at 0.74 across, "
                                  "about 0.34 of the frame wide")
    shots[0]["cards"][1]["cut"] = True
    ctx = _ctx(context, make_plan(shots=shots))
    assert not _fails(_run(ctx, ["compose"]), "compose")


def test_a_buried_card_is_caught(context):
    """A slip 100 % under a photograph is a piece paid for and never seen."""
    shots = base_shots()
    shots[0]["cards"] = [
        card("slip", z=1, bahan="cetak", wujud="sobekan_pita", lands=30, word="peta",
             at="centre of the frame, centred at 0.50 across, about 0.20 of the frame wide"),
        card("foto", z=3, bahan="foto", wujud="plang_fisik", lands=45, word="orang",
             at="centre of the frame, centred at 0.50 across, about 0.70 of the frame wide"),
    ]
    ctx = _ctx(context, make_plan(shots=shots))
    messages = _fails(_run(ctx, ["compose"]), "compose")
    assert any("100%" in m or "99%" in m for m in messages)


def test_a_partly_covered_card_is_a_warning_not_a_failure(context):
    """A finding carries a level: 36 % is a number to look at, not a stop."""
    shots = base_shots()
    shots[0]["cards"] = [
        card("bawah", z=1, bahan="foto", wujud="sobekan_pita", lands=30, word="peta",
             at="centre of the frame, centred at 0.50 across, down at 0.30, "
                "about 0.30 of the frame wide"),
        card("atas", z=3, bahan="foto", wujud="sobekan_pita", lands=45, word="orang",
             at="centre of the frame, centred at 0.50 across, down at 0.45, "
                "about 0.30 of the frame wide"),
    ]
    ctx = _ctx(context, make_plan(shots=shots))
    result = _run(ctx, ["compose"])
    assert not result.failed
    warns = [f for f in result.findings("warn") if f.gate == "compose"]
    assert warns, "a 36 % burial should be reported, not swallowed"


# ------------------------------------------------------------------ readable
def test_a_map_under_a_figure_is_caught(context):
    """R6, and the reason `peta` is in the vocabulary: a printed map is place names
    edge to edge, so a figure standing anywhere on it buries words.

    A *slip* under a figure is the one pair R6 excuses — see
    `test_a_slip_under_a_figure_is_judged_by_its_lettering` — but a map is not a
    slip, and this is the test that keeps the difference from being blurred.
    """
    shots = base_shots()
    shots[0]["cards"][0]["bahan"] = "peta"
    shots[0]["cards"][0]["z"] = 1          # the map, under the figure
    ctx = _ctx(context, make_plan(shots=shots))
    messages = _fails(_run(ctx, ["readable"]), "readable")
    assert any("peta" in m for m in messages)


def test_a_slip_under_a_figure_is_judged_by_its_lettering(context):
    """A silhouette over a slip's blank margin is collage; over its lettering it is
    a lost fact. The plan cannot tell those apart, so `readable` defers and the
    asset gate `figure` answers with the card's own ink.

    This replaces an older test that failed the arrangement itself. That rule came
    from v2, where the camera moved layers by different amounts and a card merely
    beside a figure ended up under it. In v3 the plate and every card are inside one
    transform — there is no parallax — so the arrangement is only a risk when the
    ink is actually covered, which is measurable and is measured.
    """
    shots = base_shots()
    shots[0]["cards"][0]["z"] = 1          # the slip, under the figure
    ctx = _ctx(context, make_plan(shots=shots))
    assert not _run(ctx, ["readable"]).failed


def test_an_exemption_without_a_reason_is_caught(context):
    shots = base_shots()
    shots[0]["cards"][0]["tertutup_boleh"] = True
    ctx = _ctx(context, make_plan(shots=shots))
    assert any("tertutup_alasan" in m for m in _fails(_run(ctx, ["schema"]), "schema"))


def test_an_exemption_with_a_reason_is_honoured(context):
    shots = base_shots()
    shots[0]["cards"][0].update(tertutup_boleh=True,
                                tertutup_alasan="the map is a ground, not a reading")
    shots[0]["cards"][0]["z"] = 1
    ctx = _ctx(context, make_plan(shots=shots))
    result = _run(ctx, ["readable", "schema"])
    assert not result.failed, result.summary()


# ------------------------------------------------------------------- arrival
def test_a_card_that_settles_on_a_word_never_spoken_is_caught(context):
    shots = base_shots()
    shots[0]["cards"][0]["word"] = "gunung"
    ctx = _ctx(context, make_plan(shots=shots))
    assert any("never says" in m for m in _fails(_run(ctx, ["arrival"]), "arrival"))


def test_a_card_that_settles_outside_its_window_is_caught(context):
    shots = base_shots()
    shots[0]["cards"][0]["lands"] = 80      # `peta` is spoken at f27
    ctx = _ctx(context, make_plan(shots=shots))
    assert any("window" in m for m in _fails(_run(ctx, ["arrival"]), "arrival"))


def test_two_cards_landing_on_top_of_each_other_are_caught(context):
    """Two arrivals three frames apart read as one, which is a slideshow."""
    shots = base_shots()
    shots[0]["cards"][1]["lands"] = 31      # `orang` at f42, `peta` lands f30
    ctx = _ctx(context, make_plan(shots=shots))
    messages = _fails(_run(ctx, ["arrival"]), "arrival")
    assert any("read as one" in m for m in messages)


def test_arrival_needs_a_narration_and_says_so(context):
    ctx = Context(project=context.project, plan=context.plan, narration=None)
    result = _run(ctx, ["arrival"])
    assert result.results[0].skipped
    assert not result.complete, "a skipped gate has not verified anything"


# --------------------------------------------------------------------- ranges
def test_a_shot_range_that_does_not_tile_is_caught(context):
    shots = base_shots()
    shots[1]["range"] = [95, 180]
    ctx = _ctx(context, make_plan(shots=shots))
    assert _fails(_run(ctx, ["ranges"]), "ranges")


def test_a_film_that_ends_before_the_narration_is_caught(context):
    shots = base_shots()
    shots[1]["range"] = [90, 150]
    ctx = _ctx(context, make_plan(shots=shots))
    messages = _fails(_run(ctx, ["ranges"]), "ranges")
    assert any("would end early" in m for m in messages)


# --------------------------------------------------------------------- data
def test_a_figure_the_voice_never_says_is_caught(context):
    shots = base_shots()
    shots[0]["cards"][0]["semantik"] = "1.847 METER"
    ctx = _ctx(context, make_plan(shots=shots))
    messages = _fails(_run(ctx, ["data"]), "data")
    assert any("1.847" in m for m in messages)


def test_a_figure_the_voice_says_as_words_is_accepted(context):
    """`seribu lima ratus` is 1.500 and `enam puluh` is 60. Scoring word by word
    reported every honest number in the film as invented, and a checker that
    fails the right answer is worse than none."""
    from voxkit.words import Narration, Word, analyse
    words = [Word(t, i * 0.5, i * 0.5 + 0.4, 30) for i, t in enumerate(
        ["jalan", "itu", "panjangnya", "seribu", "lima", "ratus", "meter", "lalu",
         "ada", "enam", "puluh", "kilometer", "lagi"])]
    ctx = _ctx(context, make_plan(shots=base_shots()))
    ctx.narration = Narration(analyse(words, 6.5), 6.5, 30)

    shots = base_shots()
    shots[0]["cards"][0]["semantik"] = "1.500 M"
    shots[0]["cards"][1]["semantik"] = "60 KM"
    ctx.plan = make_plan(shots=shots)
    assert not _fails(_run(ctx, ["data"]), "data")


def test_one_figure_is_reported_once(context):
    """A headline that also appears quoted in the prompt is one thing printed
    once; reporting it twice makes a single fault look like two."""
    shots = base_shots()
    shots[0]["cards"][0]["semantik"] = "7.000 KAKI"
    shots[0]["cards"][0]["what"] = "a placard that reads '7.000 KAKI' in ink"
    ctx = _ctx(context, make_plan(shots=shots))
    assert len(_fails(_run(ctx, ["data"]), "data")) == 1


# ------------------------------------------------------------------- program
def _layouts(ctx: Context) -> None:
    """Write a measured layout for every shot, so the program gate has something
    to build a program from instead of skipping."""
    for shot_ in ctx.plan.shots:
        elements = {}
        for card_ in shot_.cards:
            slot = card_.rect
            elements[card_.name] = {"x": slot.cx, "y": slot.cy, "w": slot.w,
                                    "h": slot.h, "aspect": slot.h / slot.w,
                                    "src": f"{card_.name}.png", "z": card_.z}
        path = ctx.project.card_dir(ctx.module, shot_.id) / "layout.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"elements": elements}), encoding="utf-8")


def test_the_program_gate_skips_without_layouts_and_is_not_a_pass(context):
    """Twelve gates passed on a module whose four declared puppets had never been
    drawn, because a gate with nothing to look at said PASS."""
    result = _run(context, ["program"])
    assert result.results[0].verdict == "N/A"
    assert "layout" in result.results[0].skipped


def test_two_strokes_on_two_cards_do_not_crash_the_program_gate(context):
    """Two marks a few frames apart on different cards cannot both be framed, and
    the gate has to notice that *and stay standing*.

    It did not: the exemption that recognises the impossible pair referenced a
    constant the module never imported, so the gate raised instead of answering.
    The suite was green because the fixture put one mark in each shot, and the
    expression is only reached when there is an earlier stroke to compare with.
    Every real module has more than one.
    """
    shots = base_shots()
    shots[0]["marks"] = [
        ["circle", 10, -4.2, "peta", {"delay": 2}],
        ["underline", 8, 1.5, "orang", {"delay": 3}],
    ]
    ctx = _ctx(context, make_plan(shots=shots))
    _layouts(ctx)
    result = _run(ctx, ["program"])
    assert result.results[0].verdict != "ERROR", result.results[0].error
    # The second stroke is the crowded one, so only the first may be judged.
    assert not any("does not hold" in f.message and "orang" in f.message
                   for f in result.results[0].findings)


# --------------------------------------------------------------- the runner
def test_a_crashing_gate_is_an_error_not_a_silent_pass(context):
    boom = Gate("boom", lambda ctx: 1 / 0, lambda ctx: [])
    result = run(context, [boom], use_cache=False)
    assert result.results[0].verdict == "ERROR"
    assert "ZeroDivisionError" in result.results[0].error
    assert result.failed


def test_a_second_run_is_a_cache_hit(context):
    """The cache is keyed on the files the gate read, not on the module's mtime."""
    first = _run(context, FREE)
    assert not first.failed
    second = _run(context, FREE)
    assert all(r.cached for r in second.results), second.summary()


def test_a_failed_gate_is_never_cached(context):
    shots = base_shots()
    shots[0]["cards"][0]["wujud"] = "kertas_licin"
    ctx = _ctx(context, make_plan(shots=shots))
    _run(ctx, ["schema"])
    again = _run(ctx, ["schema"])
    assert not again.results[0].cached


def test_the_cache_is_keyed_on_content_not_on_the_path(context):
    """Edit the plan and the gate that read it must re-run."""
    shots = base_shots()
    ctx = _ctx(context, make_plan(shots=shots))
    assert not _run(ctx, ["readable"]).failed

    shots[0]["cards"][0]["bahan"] = "peta"
    shots[0]["cards"][0]["z"] = 1
    ctx = _ctx(context, make_plan(shots=shots))
    assert _run(ctx, ["readable"]).failed


def test_an_unknown_gate_name_is_refused():
    with pytest.raises(KeyError, match="unknown gate"):
        gate_set(["compse"])


def test_every_gate_declares_what_it_asks():
    for gate in gate_set():
        assert gate.asks, f"{gate.name} does not say what it asks"
        assert gate.name.islower()


# ------------------------------------------------------------------- double
def _piece_png(path, size, *, blank=None, ink=True):
    """A piece as a PNG: opaque paper, halftone print, and optionally a bare
    patch where something else lay on top of it."""
    import numpy as np
    from PIL import Image

    w, h = size
    rng = np.random.default_rng(7)
    a = np.full((h, w, 4), 255, np.uint8)
    a[..., :3] = 214                      # paper
    if ink:
        a[..., :3] = np.where(rng.random((h, w, 1)) < 0.45, 40, 214)   # halftone
    if blank is not None:
        x0, y0, x1, y1 = blank
        a[y0:y1, x0:x1, :3] = 214         # the other piece's sheet, left bare
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(a).save(path)


def _two_pieces(ctx, shot_id, *, bare_under_card):
    """One photograph with a card lying wholly inside it, as the still had them.

    The card's footprint is 160x90 at the centre of a 640x360 stage; the photo is
    448x252, so the footprint is (144, 81)-(304, 171) in the photo's own pixels.
    """
    shot_ = next(s for s in ctx.plan.shots if s.id == shot_id)
    d = ctx.project.card_dir(ctx.module, shot_id)
    _piece_png(d / "foto.png", (448, 252),
               blank=(144, 81, 304, 171) if bare_under_card else None)
    _piece_png(d / "kartu.png", (160, 90))
    elements = {}
    for name, (cx, cy, w, h) in (("foto", (0.50, 0.50, 0.70, 0.70)),
                                 ("kartu", (0.50, 0.50, 0.25, 0.25))):
        elements[name] = {"x": cx, "y": cy, "w": w, "h": h, "aspect": h / w,
                          "src": f"{name}.png"}
    (d / "layout.json").write_text(json.dumps({"elements": elements}), encoding="utf-8")
    return shot_


def _double_plan():
    shots = base_shots()
    shots[0]["cards"] = [
        card("foto", z=1, bahan="foto", lands=30, word="peta",
             at="centre of the frame, centred at 0.50 across, about 0.70 of the frame wide"),
        card("kartu", z=5, bahan="cetak", lands=45, word="orang",
             at="centre of the frame, centred at 0.50 across, about 0.25 of the frame wide"),
    ]
    return make_plan(shots=shots)


def test_a_cut_out_that_keeps_the_sheet_on_top_of_it_is_caught(context):
    """The client's finding: two identical cards stacked, the one behind separated.

    The isolate stage re-draws the piece, so the card lying across the photograph
    came back inside the photograph's cut-out — bare paper, letters gone. Every
    other gate was green: the stacking order was right and both pieces were where
    the plan put them.
    """
    ctx = _ctx(context, _double_plan())
    _two_pieces(ctx, "s01", bare_under_card=True)
    messages = _fails(_run(ctx, ["double"]), "double")
    assert messages, "a bare copy of the card inside the photo is a second card"
    assert "foto" in messages[0] and "kartu" in messages[0]


def test_a_piece_whose_texture_continues_behind_the_card_is_not_a_fault(context):
    """The control. A photograph that prints its own halftone where the card lay
    is a correct cut-out, and the gate has to say so — otherwise it is just
    measuring "these two overlap", which is every collage ever made."""
    ctx = _ctx(context, _double_plan())
    _two_pieces(ctx, "s01", bare_under_card=False)
    assert not _fails(_run(ctx, ["double"]), "double")


def test_a_card_s_own_margin_is_not_a_copy_of_anything(context):
    """Bare paper alone proves nothing: a card is paper, and the piece lying on
    its blank margin leaves no print around it. Two-sided evidence or no finding."""
    ctx = _ctx(context, _double_plan())
    _two_pieces(ctx, "s01", bare_under_card=True)
    # The carrier is now a card with one line of type along its top edge and a
    # blank body: bare under the piece, and not printed around it either.
    _piece_png(ctx.project.card_dir(ctx.module, "s01") / "foto.png", (448, 252),
               blank=(0, 40, 448, 252))
    assert not _fails(_run(ctx, ["double"]), "double")


def test_the_double_gate_skips_without_layouts_and_is_not_a_pass(context):
    """A gate with nothing to look at has verified nothing — `N/A` is not PASS."""
    result = _run(_ctx(context, _double_plan()), ["double"])
    assert result.results[0].verdict == "N/A"
    assert "layout" in result.results[0].skipped
