# HANDOFF — voxkit v3 / "Tanah Air"

Written to survive a power cut. If you are a new session: read this file, run the
three commands in **Verify**, and you know exactly where the work stands.

Last updated: 2026-11-01 (asset generation complete, repairs converging).

---

## 1. What this is

A documentary film pipeline. Twenty-two modules, each a plan (JSON) that is drawn
into stills, cut into pieces, assembled on a paper page, and animated with a
camera, a presenter and hand-drawn ink.

```
plan → still → isolate → poses → fills → plate → emit (TSX) → gates → render
```

- Engine: `D:\VOX-PLUGIN-3\voxkit` (Python 3.11).
- Film: `D:\VOX-PLUGIN-3\film` (plans, audio, build artifacts, Remotion app).
- Renderer: `film/remotion` (Remotion/React, TSX emitted by the engine).

**v3's charter:** strong at plan audit, strong at visual output, strong at
enforcing its own rules — with cleaner code and tidier structure than v2.

---

## 2. Verify (three commands)

```bash
cd /d/VOX-PLUGIN-3 && py -m pytest tests -q          # 155 tests, all green
cd /d/VOX-PLUGIN-3/film
PYTHONPATH=/d/VOX-PLUGIN-3 py -m voxkit.cli gate m03 --no-cache
PYTHONPATH=/d/VOX-PLUGIN-3 py -m voxkit.cli camera --all
```

`vox camera` is a *report*, not a gate: it prints what the camera actually does,
frame by frame, because the question that mattered ("does the camera move?")
could not be answered yes/no.

### Environment

```bash
cd /d/VOX-PLUGIN-3/film
PYTHONPATH=/d/VOX-PLUGIN-3 py -m voxkit.cli <cmd> <module>
```

Commands: `init list plan gate gestures words still isolate poses fills plate emit
sync run render camera`. It is `gate`, not `gates`.

**The generator CLI is at `C:/Users/PC/.local/bin/gflow.exe`** — it is *not* on
PATH, and `film/vox.toml` therefore points at the absolute path. Do not "fix" that
back to `gflow`. The account (`videoquincy`) is authenticated, and model `nano2`
does not spend credits, so the only real cost of generation is **about one minute
per image**.

---

## 3. State, module by module

**All 22 modules have programs and assets.** Fourteen passed every gate before the
asset pass; the rest were built last and are being repaired.

| module | state |
|---|---|
| m01–m13, m20 | **all gates pass** (m03 rendered: `out/m03-final.mp4`, 54.53 s) |
| m14 | built; `pose` was missing, `repair.sh` draws it |
| m15–m19, m21, m22 | built last; isolation misses being re-cut (see §4) |

The gate table, at any moment:

```bash
cd /d/VOX-PLUGIN-3/film
for m in $(seq -w 1 22); do
  m="m$m"; printf "%-4s " $m
  PYTHONPATH=/d/VOX-PLUGIN-3 py -m voxkit.cli gate $m --no-cache --quiet 2>&1 \
    | grep FAIL | awk '{print $1}' | sort -u | tr '\n' ' '; echo
done
```

---

## 4. The repair loop — how the remaining work finishes itself

The isolate model sometimes returns **the whole page** instead of one cutout. The
piece then measures ~1.0 × 1.0, and every gate downstream reports a *symptom*: a
burial in `compose`, a camera that cannot hold a figure, a mark that runs off the
page. Three symptoms, one cause.

```bash
py tools/find_bad_pieces.py     # name the cause, per piece, with a repair line
py tools/repair.py              # measure → re-cut only the wrong pieces → rebuild → measure
```

**Why a loop and not a list.** Re-isolating is not idempotent. `--force` on a shot
re-cuts pieces that were already right, and the model is free to miss a different
one next time: repairing m15 s04 fixed two pieces and broke `foto_wadah_batu`,
which had been correct. A hand-written repair list cannot converge, because every
fix can create the next fault. `repair.py` re-measures after each round and stops
when the detector is silent, or when a piece has had its two tries (§4.1).

**The two rules the detector uses** (both are geometry, not taste):

1. a piece measuring ≥0.95 in **both** axes is the page plus its torn edge;
2. a piece whose box contains ≥2 **smaller** pieces (≥80 % of each, each ≤60 % of
   its area) is the page with its ground removed.

Rule 2 **over-fires**, and this matters: a big photograph with cards taped over it
*is* a box containing smaller boxes, and that is the whole Vox aesthetic. So the
detector is a *finder*, never an authority — `repair.py` asks the gates first and
only repairs modules where `compose`, `slot` or `pose` actually fail. Repairing on
the heuristic alone would have re-cut pieces in five modules that pass every gate.

### 4.1 A repair touches one piece, never a shot

`vox isolate <module> --shots s04 --pieces foto_wadah_batu --force`. The `--pieces`
filter was added for exactly this: a shot-level `--force` is a blunt tool that
breaks correct pieces while fixing wrong ones.

**Try the free repair first.** `vox isolate <m>` with no `--force` re-measures
every piece from the replies already on disk. Since §5.9, that alone fixes most
full-page pieces at no cost. Only what survives it needs generation.

### 4.2 Scripts, in the order they were used

| script | what it does |
|---|---|
| `film/finish.sh` | first pass: stills + isolate + fills + plate + poses + emit for m15–m22 |
| `film/finish2.sh` | second pass: m17/m18/m19 after the prompt-length fix, then sync+gate all |
| `film/repair.sh` | first repair round: the 19 both-axes misses, plus `poses m14` |
| `film/finish_all.sh` | **the chain**: waits for `repair.sh`, runs `tools/repair.py`, gates all 22, then `render_all.sh` |
| `film/render_all.sh` | renders every chapter, verifies the join, writes `out/tanah-air-full.mp4` |

All of them are resumable. `isolate` skips pieces that exist; `repair.py` measures
before it acts; `render` re-renders. **Killing one and running it again is safe.**

---

## 5. Invariants — do not regress these

Each was broken, fixed, and is now guarded by a test or a measurement.
Re-introducing one re-introduces a fault the client has already reported.

### 5.1 A camera never stops — `camera.EASE_FLOOR = 0.40`

`slow` is `inOut(cubic)`, whose derivative is **zero at both ends**. Every segment
of every shot used it, so the camera *stopped dead at every key*: accelerate,
stop, accelerate, stop. With keys twenty frames apart the viewer sees a stutter.

Measured on m03 before: 40 of 86 keys pinned at zoom 1.000, 12 % of one-second
windows under 1 % change, 43 % of frames dead. After: **0 dead frames in 1636**,
and `ffmpeg freezedetect` on the rendered file reports **zero freeze events** at
0.2 % sensitivity.

`ease()` blends both `slow` and `fast` toward linear by `EASE_FLOOR`. **The same
blend must exist in `film/remotion/src/components/Camera.tsx`** — the gates measure
the Python curve, the film is drawn with the TSX one. A test asserts they have not
drifted (`test_the_renderer_agrees_with_the_ease_floor`).

### 5.2 A park is a rate, not a distance — `choreography.PARK`

`creep()` finds holds and breathes them. Equality between keys missed every park
the earlier passes had nudged by 0.3 %; closeness missed m03 s04, which panned
3.7 % over two seconds — a distance that passes any threshold and a speed the eye
reads as a photograph. `slow(p, q)` now measures **change per `STILL_RUN` frames**,
and a long park gets a breath at *both* ends.

### 5.3 The camera pipeline is one ordered sequence

In `build_shot`, once:

```
build_camera → punch_for → plate_cam(read windows) → fit_marks → squeeze
→ steady_holds → plate_cam(figures + pen subjects) → enforce_holds → creep
```

Every step is there because a later step could undo an earlier one, so **the order
is the design**. Do not add a pass without deciding where it belongs.

### 5.4 Dead air is graded, not absolute — `program.DEAD_AIR`

A still camera is a fault only when the viewer has nothing to watch. Rule 9 asks
whether *anything* touches the page; rule 10 asks whether the frame changes, and
allows twice the run when the page is busy (`_busy()`: a card in flight, a stroke
being drawn, a note being written). m13 s07 holds one framing for 48 frames while a
card flies in and two strokes are drawn — a deliberate hold, not a freeze.

### 5.5 The presenter only counts what is drawn — `presenter.DRAWN`

`point` and `group` are how the presenter *reads* the page; the emitter draws only
`write`, `again` and `relate`. `_fill()` used to count all of them, so it believed
the page had changed when it had not. `edges_now()` filters on `DRAWN` and is
**recomputed each pass**, because a note the presenter writes is itself an event.

### 5.6 Two declared exemptions, both requiring a reason

The plan may overrule a gate, but never silently — `schema` refuses the flag
without a reason, and the overruled gate emits a note so the decision stays
visible in every future sweep.

- `tertutup_boleh` + `tertutup_alasan` — this piece is *meant* to be covered.
- `angka_bahan` + `angka_alasan` — this printed figure is **material**, read off a
  photographed sign, not a claim the film is making. m01 uses it for `CIANJUR 60
  KM`, `PUNCAK 1.500 M`, `KM 12`.

### 5.7 A nudge moves a piece; it does not resize it — `Card.placed()`

`nudge: [dx, dy]` in frame fractions, applied to the **measured** box. The measured
box carries the cutout's real proportions (a fact about the image); where it lies
is a composition decision. **One definition, `Card.placed()`, used by both the
`compose` gate and the emitter** — a nudge applied in only one of them is a gate
measuring a film nobody is watching.

### 5.8 The isolation prompt must say *where* the piece is

The first version named the piece and never located it, so the model had to find
one clipping among five on a page of halftone newsprint with only a description to
go on. Nineteen pieces across six modules came back as the whole page. `iso_prompt`
now carries a locator ("upper left, about 24 % across and 33 % down") and names the
page, so "remove the page" is an instruction it can obey. Do not trim that locator
to save characters — it costs thirty and it is the difference between a cutout and
a photograph of a page.

### 5.9 Which ink, not which is biggest — `image.keep_largest(near, reach)`

The locator was not enough, and neither was a close crop (see §5.10). What the
model actually does is return **every** clipping, correctly separated from the page
ground. It is right about *what is ink* and wrong about *which ink*. So the choice
is made here, arithmetically, from the box the plan already states:

- the search is **bounded** to that box (±65 % of the piece's own size), because a
  near-magenta wash between two clippings joins them into one blob — m18's
  `kartu_cara` came back as a single 1316×750 component holding five pieces, and no
  amount of "pick the right blob" can split what the mask has joined;
- the point only decides when there is more than one **substantial** blob, so a
  single piece that came back slightly split does not lose half of itself.

This fixed pieces with **no generation at all**: rebuilding the layout re-measures
from the replies already on disk. `vox isolate <m>` with no `--force` does exactly
that, and it is the cheapest repair in the project.

### 5.10 A cropped reference makes it worse — do not try it again

Sending a tight crop around the piece was the obvious next idea and it failed for a
reason worth remembering: **the model upscales the crop to its own canvas**, so the
piece fills most of the reply and the window that selects it has nothing left to
exclude. `--crop` still exists on `isolate`, but nothing uses it, and `repair.py`'s
ladder is deliberately flat.

### 5.11 A pose frame is aligned to the card it replaces — and re-cut cards move

`poses` used to return early when nothing was left to draw, which made it unable to
repair anything: after a re-isolation rebuilt the layout, the pose files were still
on disk and nothing pointed at them. Every later run said "every declared pose is
already drawn" and wired nothing — a puppet went static and no gate could see it.

Worse, a frame is aligned onto its card's canvas *when it is drawn*. Re-cut the
card and the frame is the wrong size: the renderer maps a card's canvas width onto
its stage width, so the figure jumps on every swap. m17's `orang_di_lubang` kept a
697×483 frame over a 300×377 card — 43 % of its size.

`_rewire_existing` now re-aligns from the raw reply in `iso/` whenever a frame's
canvas disagrees with its card, then rewires. All local, no generation.

### 5.12 One pose swap is still a puppet that moves

Three puppets land so late that only one swap fits in their shot (m15
`penjaga_kabuyutan`, m16 `penjaga_sungai`, m19 `figur_peneliti`). The stage refused
anything under two and left them static for ever, which the `pose` gate correctly
failed. It now draws what fits and says so. A declared action that does not fit is
reported, not pretended.

### 5.13 A prompt over the backend cap kills the whole batch

gflow rejects an *entire batch* if one prompt exceeds 2000 characters. m17 and m18
produced nothing at all because one page was 2146. `still_prompt` now guarantees
`len(text) <= MAX_PROMPT` by trimming the shot's prose first, then the per-piece
descriptions **evenly**, and never the `z` or placement of a piece — those are
composition facts, and losing one loses a subject. Guarded by `tests/test_prompt.py`.

### 5.14 A long park needs its *interior* keys on the ramp, not just its ends

`creep` breathes at the head and the tail of a hold. That is enough for a park of
two seconds and not for a park of four, because `camera.resolve` interpolates
*between keys*: an interior key still carrying the plateau value holds that value
flat until the next key. m15 s05 parked for 126 frames, got a breath at f174 and
another at f300, and left f205..f286 at exactly 1.0600 — the gate measured 92 dead
frames inside a run that was breathing at both ends.

So every interior key now takes the position a straight line from the head breath
to the tail breath would put it at, and `breathe` still has the last word: an
interior key that cannot move without clipping a stroke or a figure is left where
it was. The ramp exists to remove dead air, not to buy it with a clipped card.

### 5.15 Two strokes at once widen the frame; they do not wait

`steady_holds` gives each stroke the framing its card needs, and when two strokes
overlap on different cards the later one overwrites the earlier one's keys — the
first stroke is then drawn on a card the frame has left. m15 s03: an underline on
the bottom card at f44, a circle on the top card at f47, and the underline ran off
the page.

The fix is **not** to delay the later stroke. A time shift is something the viewer
did not ask for and it cascades: serialising m01 s04 pushed four strokes a hundred
frames late, dropped the last one, and the camera lost the move that was covering
the silence — two modules failed on dead air that no gate had complained about
before. What a camera operator would do is pull back until one framing holds both
cards, and `settle` does exactly that, reducing the zoom only as far as it must.

### 5.16 The gate must judge at the precision the program stores

`tsx.num` writes four decimals and every pass that settles a framing rounds to the
same place. `camera.holds` used to demand 1e-6, so settling to `y = 0.4778205` and
storing `0.4778` lost two hundred-thousandths and m15 s02 f52 was reported as a cut
figure — a tenth of a pixel, invisible, and unfixable by any repair because the
repair produced the same rounded number. `camera.STAGE_EPS = 1e-4` is the one
number both sides agree on: below it, two framings are the same framing.

### 5.17 The presenter's silence walk has three bounds, and all three are load-bearing

The walk is the loop in `presenter._fill` that answers a quiet page. Getting it
right took three attempts, and each bound exists because the other two produced a
fault:

- **It must not break when it cannot act at this instant.** The old code broke, and
  m15 s05 kept forty-nine dead frames because the only card on the page became
  eligible one frame after the walk had given up. It now steps `t += 2` — two, not
  six: a step of six jumps over the one frame where the answer is.
- **It must not point at a piece the shot never names.** `narration.score` cannot
  answer "is the voice on this piece" — it falls back to the nearest accent when
  the word never occurs, so it is positive for everything. The test is a lookup in
  the shot's own word set, and the comparison must be `normalise(c.word)`: card
  words are raw text (`"Cipanas,"`) and the narration keys are not.
- **It must not answer the first frame of a gap.** The card has just landed; an
  arrow then is pointing at what the viewer is already looking at, and it spends
  the `AGAIN_COOL` cooldown before the gap it was meant to fill. `AGAIN_DELAY = 24`
  — but only when waiting still leaves a fillable gap, or the delay closes the
  four-frame window in which m15 s05's gap can be answered at all.

A gate failure in this area is never "the presenter is lazy". It is one of these
three bounds being wrong, and the three interact: fixing one alone moves the fault
to another module. Test all 22 after touching any of them.

---

## 6. What is left, in order

**The film is rendered.** `film/remotion/out/tanah-air-full.mp4` — 1920×1080,
31 737 frames, 1057.94 s, 1.69 GB. Verified:

- `ffprobe -count_frames` → 31 737, which is exactly the sum of the 22 chapters and
  exactly what the `FILM` composition declares. The join is not short.
- `ffmpeg -vf freezedetect=n=-55dB:d=0.8` → **zero** frozen spans across seventeen
  and a half minutes. Not one 0.8-second hold anywhere in the film. That is the
  measurement of the client's original complaint ("kameranya masih gak bergerak")
  coming back empty.
- A frame at 12:52 and a frame a second later show the camera closer and a stroke
  landed — the m15 s05 park that used to be 92 dead frames now creeps.

What remains is judgement, not work:

1. **Watch it.** The gates measure arithmetic; a person measures whether the film
   is any good. `vox camera --all` first, then the renders. Look for a note on a
   face, ink on the wrong card, a figure cut in half, a shot that reads as a
   photograph rather than a page.
2. **Any repair after this point must be re-emitted and re-rendered.** A chapter
   whose `.tsx` is newer than its `.mp4` is stale, and `render_all.sh` will redraw
   it — but the join has to be re-run to pick it up.

As of this session **all 22 modules pass every gate with zero failures** (m15 was
the last, fixed by §5.14–5.17). Remaining gate output is warnings and notes only.

---

## 7. Where the work was, last session

- `voxkit/emit/choreography.py` — `creep` now ramps the *interior* of a long park
  (§5.14); `steady_holds` widens the frame for overlapping strokes instead of
  letting the later one steal it (§5.15); new `finish_figures` pass reconciles
  "figure whole at every key" with "never pin the camera".
- `voxkit/emit/camera.py` — `STAGE_EPS`, the precision `holds` judges at (§5.16).
- `voxkit/presenter.py` — the silence walk advances `t += 2` instead of breaking,
  so a gap whose only answer sits one frame past the walk is still answered.
- `voxkit/audit.py` — **new**. `vox camera` measures zoom spread, pan range and
  dead frames per shot, from the same `program_of()` the renderer reads.
- `voxkit/prompt.py` — `iso_prompt` locator; `still_prompt` length guarantee.
- `voxkit/stages.py` — `isolate --pieces` for surgical re-cuts.
- `voxkit/gates/program.py` — `_busy()`, graded rule 10, rule 9 postpone check.
- `voxkit/gates/plan.py` — `angka_bahan` in `data`; `Card.placed()` in `compose`.
- `voxkit/contract.py` — `angka_bahan`/`angka_alasan`, `nudge`, `Card.placed()`.
- `tools/find_bad_pieces.py` — **new**. Two geometry rules for a failed isolation.
- `tools/repair.py` — **new**. The convergent repair loop, with two tries per piece.
- `film/plans/m21.json` — s06 page pulled back from full-bleed indigo to an indigo
  block: the still gate refused it as a modern colour photograph, and it was right
  — twenty-one other pages are cream and the pieces are warm sepia.

### Numbers worth keeping

| | before | after |
|---|---|---|
| m03 frames with a still camera | 43 % | **0 %** |
| m03 zoom, min / median / max | 1.03 / 1.10 / 1.35 | 1.01 / 1.16 / 1.35 |
| m03 pan range (x, y) | 0.13 | 0.26 |
| m03 keys at exactly zoom 1.000 | 40 of 86 | 0 |
| modules with assets | 15 | **22** |
| pieces in the film | — | 852 |
| cost of one generated image | — | ~1 min, 0 credits |

---

## 8. How to not fool yourself

The failure mode this project keeps rediscovering is **a gate that passes a film
nobody is watching**. Four habits defend against it:

- **Measure, do not assert.** When the client said "the camera does not move", the
  gates disagreed and were wrong. `vox camera` exists because the answer was a
  distribution, not a verdict.
- **A skip is not a pass.** `Skipped` is raised when an artifact is missing and is
  reported as such; a render refuses it. Twelve gates once passed on a module whose
  four declared puppets had never been drawn.
- **Check the deliverable, not the program.** `ffmpeg freezedetect` on the rendered
  MP4 is the only proof that the *film* moves:

  ```bash
  ffmpeg -hide_banner -i film/remotion/out/m03-final.mp4 \
    -vf "freezedetect=n=0.002:d=0.6" -f null - 2>&1 | grep -c freeze_start
  ```

  Zero is the answer you want.
- **Look at the picture.** Three times this session a number said "fine" and the
  image said otherwise, and twice the image was right. A piece measured 0.85 wide
  looked reasonable in the table and was a photograph of a whole page.
