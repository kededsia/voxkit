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

**All 22 modules have programs and assets.** `program` has no failures anywhere,
`spell` and `data` pass on all 22, `double` passes on 21, and `readable` on 15.
What is left is `figure` (9 modules), `readable` (7) and `motion` (21 stale
`.mp4`s: the gate measures pixels, and only m02 has been re-rendered against the
current emitter).

| gate | two sessions ago | before this session | now |
|---|---|---|---|
| `spell` | 22 PASS over **zero** terms | **22 PASS** over 9 terms | 22 PASS |
| `data` | — | 22 PASS | 22 PASS |
| `double` | gate did not exist | gate did not exist | **21 / 22** |
| `readable` | 3 / 22 | 16 / 22 | 15 / 22 |
| `figure` | 9 / 22 | 14 / 22 | 13 / 22 |

| module | state |
|---|---|
| m02 | **every gate PASS**, re-cut at 2K on s01, re-synced, re-rendered (37.30 s) |
| m01, m06, m07, m12–m15, m17, m21 | `readable` + `figure` + `spell` + `double` PASS; `.mp4` stale |
| m03, m08, m09, m11 | **`readable` fails** — a person stands on a map, burying place names |
| m04, m16, m20 | **`figure` fails** — a person stands on a card's lettering |
| m05, m10, m18, m22 | both |
| m19 | `double` fails on s04 (named, needs a new still) + `figure` on s03 |

The 15 `readable`/`figure` failures are **one fault**: a person overlaps a printed
surface and no `z` order satisfies both rules — below, the head is covered; above,
the lettering is buried. The still must be recomposed. `uncover.py` refuses all of
them for the same reason, now on record (§5.24).

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

### 5.18 One decision per beat, and the camera is one of the consequences

`voxkit/intent.py` is the file that answers "paham kok gak dikerjain dengan bener".
The history it replaces is worth keeping in view, because it looks like progress
and was not:

- **The camera** carried `reason="arrive"` on every key — a label attached *after*
  `punch_for` and `creep` had already moved the frame. The renderer never read the
  label, so the film had no camera movement at all while sixteen gates were green.
- **The markers** had `INTENTS` (five), `PRESET` (five) and `for_gesture` (seven
  words); measured, `for_gesture` was called twice, both with a hardcoded string,
  and every note was registered with the literal `"emphasis"`.

So one `Beat` goes in, one `Decision` comes out, and the decision carries the
register, the colour, the pen, the note's vehicle, the card's arrival and the
camera's move. The camera is not allowed to choose. `MOVES` is
`punch / drift / arrive / pull / hold / none` and each name is a shape with a
reason, not a direction — see `PRINCIPLES.md` P4.

Three restraints keep it from becoming a lookup table, and all three were learned
by breaking them:

1. **A stroke never punches.** The pen emphasises by drawing, the camera by
   arriving. `pin_pen_windows` deletes any hit inside a stroke anyway, so a punch
   there is a wish. (This cost two rule-13 failures on m02 before it was believed.)
2. **A punch that follows a punch is a twitch.** Two hits inside `PUNCH_GAP` are
   one; `intent.settle_moves` demotes the second to `arrive`.
3. **The emphasis line is relative to the module** (`intent.stress_line`). An
   absolute 0.52 silenced m04, m12, m15 and m19 completely — their narration is
   quieter — and those modules came out with every key easing `slow`. There is
   deliberately no floor: a relative line always admits the module's own loudest
   word, which is the claim being made.

**A decided move is performed or demoted, never dropped.** `program` rule 13 fails
a `punch` with no hit behind it, and every demotion happens inside the decision,
before a key exists. When this was first wired up, eight modules failed rule 13 at
once — the decision asked for hits the executor had nowhere to place — and the
gate was right.

### 5.19 Widen the pen windows *before* merging them, not after

`pin_pen_windows` absorbs a neighbouring key within eight frames of a window edge,
because a freeze that opens three frames after a key reads as a jump cut. It did
that *inside* the per-run loop, and widening is exactly the distance that separated
one stroke's window from the next — so the later run's freeze deleted the closing
key the earlier run had just written, and the earlier stroke was drawn on a frame
that drifted 6.6 % of the page. m09 s04, m11 s03 and m14 s07 all reported it.

Widen every window first, merge what now touches, then freeze once per run. A run
has one value by construction — which the docstring had claimed since the first
version.

### 5.20 The shot opens on the page and reaches its first piece by `OPEN_BY`

The opening key used to be `(0.48, 0.48, 1.04)` — which is where a card of ordinary
size sits, so it was doing double duty as the first card's framing. A shot whose
pieces were all the same size therefore opened and ended at the same zoom: m01 s05
travelled 0.06 of the stage across 235 frames with six strokes in it.

Now the shot opens at `(0.5, 0.5, 1.0)` — the whole page — and the first card gets
its own key like every other, reached by `OPEN_BY = 24` frames rather than on its
settle. Without that cap m04 s03 held a wide page for 46 frames while the voice
spoke, and `program` failed it for dead air. Going to the place the piece will
appear is not a guess; it is the one thing the shot is about.

### 5.21 `punch_for` is gone, and so is the second hit shape

`punch_for` fired an unconditional hit on every shot's first card, in its own
`EMPHASIS` (6/14) shape. Two systems deciding the same thing meant the film could
hit twice on one frame: on m17 the opening hit sat on the same frame as the decided
one, `PUNCH_GAP` dropped the decided hit, and the gate called it. Both the function
and the second shape are deleted. A hit that fires on every first card regardless
of what the voice is doing is the "gerak liar" the client objected to.

### 5.22 Stillness is only a fault *outside* the pen

The whole-film number lies in both directions: a camera drifting under every stroke
is moving and wrong, and a film that stops for the pen is still and right. m02
measures 49 % still frames, which sounds like the original complaint — and every
single still run of 20 frames or more sits inside a pen window. Split by ink:

```
still INSIDE the pen   96.2%   (the stroke is read on a still frame)
still OUTSIDE the pen  30.9%   median 1.85px/frame  p90 20.1px  >2px: 48.9%
still runs >= 20f: 13, of which 0 have no pen
```

Use `python _sweep/review/alive.py m02` for this split. Any future "the camera is
too still" claim has to survive it.

### 5.23 A check that iterates nothing reports PASS, not silence

The spelling gate passed on all twenty-two modules while checking zero words.

`film/lexicon.json` is authored with the key `words`. The gate read
`ctx.lexicon.get("terms", [])`. `.get` with a default returned an empty list, the
loop body never ran, no finding was produced, and the gate reported **PASS** —
not `Skipped`, not "no lexicon". The tests set `ctx.lexicon = {"terms": [...]}`,
which is the *reader's* key, so the tests agreed with the bug.

The result was `CHI` drawn into m02 s03 by the model, faithfully, on the same page
that already printed `BERAWALAN CI` correctly. `ci` was in the lexicon with
`never: []`, so even a working reader had nothing to match.

Two rules came out of it, and they are now `voxkit/lexicon.py`:

1. **One reader.** `Lexicon.from_dict` accepts both authored keys and raises when a
   file has entries and none parse. A caller cannot pick a key and get an empty
   answer that looks like a clean bill of health.
2. **A lexicon that yields nothing is broken, not clean.** `len(lex) == 0` with a
   non-empty file is a `ValueError`, not a pass.

The gate also stopped reading only cards. `CHI` survived in `klaim`,
`tesis_modul`, `fokus` and `semiotik` — four prose fields no earlier version
opened, while the two fields it *did* open were the two that got fixed. It now
walks every string in the plan (`_strings`, via `dataclasses.asdict`) plus the
**transcript**, because a card is checked *against* the transcript by `arrival`
and `data`, so a word misspelled in both agreed with itself and passed every gate.

Running it for the first time found the same fault in five more modules:

```
m03 m04 m05 m16   "chai"   for spoken cai   (water)
m20               "cahi"   for cai — the error lexicon.json was written to record
m10               "sansekerta" for sanskerta
```

`cahi` is the strongest evidence available: `lexicon.json`'s own note describes
m20's `CAHI` bug, and `CAHI` was still in m20. The file documented a fix that was
never verified.

**`chai` is not a variant of `ci`.** It belongs to `cai` (water). Listing it under
both made `forbidden()` a dict where the last entry silently won, so that now
raises too. `Lexicon.forbidden()` refuses a variant claimed by two words.

### 5.24 Two rules, one total order, no solution

`readable` (R6: a printed card sits above what covers it) and the head rule (a
person is never covered head to neck) point opposite ways, and `z` is one number
per piece. Every total order fails one of them:

```
                    readable    figure
people last          3 / 22     9 / 22     <- the previous choice
words on top        13 / 22    14 / 22     <- and it is not close
```

So the order is decided by material and then **repaired per pair**:
`tools/stack.py::lift_people` raises a person above any piece that actually
crosses their head band, and only there. `readable` is 16/22 and `figure` 14/22
under that; both were worse under either total order.

Two corrections came with it:

* **`cetak` above `figur`.** Words are what R6 protects; a hand has no head. The
  old order put people last and left a hand lying across a nameplate's words.
* **A map at the bottom of the stack is the page.** Requiring it above everything
  is not a legibility rule but an impossibility — and it is what put the map over
  the "SELURUH KABUPATEN" slip in the first place. A `peta` at the lowest `z` now
  yields to slips, photographs and pins, and `compose` still fails a page buried
  past 55 %. It does **not** yield to a person: a silhouette on place names buries
  them, and `test_a_map_under_a_figure_is_caught` holds that line.

The 14 remaining `readable`/`figure` failures are one fault, not two: **a person
overlaps a printed surface, and no `z` order satisfies both rules.** Below → head
covered; above → lettering buried. The still has to be recomposed. `uncover.py`
already refused these, and now the reason is on record.

### 5.25 The camera can only point at 12 % of the page

This is the root of "kameranya gak gerak" and of the reviewer's sixth finding —
"saat voice bilang lembah tidak ada zoom ke lembah". The camera is not lazy. It
is geometrically unable to look at most of the picture.

`cam.on()` clamps the frame centre so the frame never runs off the page:

    max_off = 0.5 + MARGIN - 0.5 / zoom

At `card_zoom` (median 1.06) that is **±0.043** — four per cent of the page. At
`ZOOM_CAP` (1.35) it is **±0.145**. So the camera can only ever address the
central 29 % of the frame, and:

```
pieces the camera can point at, even at the zoom cap:  103 / 852  = 12%
pieces out of reach at any legal zoom:                 749        = 88%
```

`m02/s04/foto_lembah_luas` sits at (0.27, 0.75). It is 38 % off centre. No legal
zoom can centre it, so its `arrive` key at f139 comes out at (0.457, 0.543) —
which is the page centre, which is the same key every other non-stressed card
gets. The camera "arrives" and does not move, because the two framings are the
same framing.

**Why raising the zoom is not the fix.** Making `card_zoom` reach-aware pushed
86 % of all pieces to the cap — a film that sits at 1.35 everywhere is not a film
that moves either. And the pieces are not too big: the median piece is 0.51 of
the frame and only 9 % would overflow at 1.35. The problem is not size, it is
*position*.

**What this means.** The collage spreads presented pieces across the whole page,
but the camera can only address the middle. Either presented pieces are composed
inside `|centre − 0.5| ≤ 0.145`, or the camera is allowed to show past the page
edge — which needs the plate to be full-bleed beyond the frame, and it is not.
That is a composition decision, not a camera one, and it is why two waves of
"make the camera move" did not fix it.

---

### 5.26 A piece carries the sheet that lay on top of it

The client's first finding — "dua kartu identik ditumpuk, yang di belakang
terpisah tapi karena bentuknya identik dan bukan puppets jadi nya aneh" — is not a
`z` fault and not a composition fault. The stacking order was right and both pieces
were where the plan put them. Every gate was green.

The isolate stage does not cut a matte. It **re-draws** the piece: it sends the
page and a description and gets one object back on a chroma ground. The prompt said
"the page behind it, every other clipping, every shadow and all page text become
`#FF00FF`" — which tells the model what to delete and never what to put *there*.
When another clipping lies across the piece, deleting it means inventing what is
underneath, and the model does not invent: it keeps the other clipping's paper and
leaves it blank, letters gone.

Measured on the two pieces the client saw:

```
m02/s01  foto_ruang_arsip <- plang_dinas        95% of the sign's footprint is
                                                bare paper; 28% printed around it
m19/s04  kartu_bukan_itu <- kartu_lampung_wai   96% bare, 33% printed around it
```

and nothing else in 852 pieces passes the same test. So it is measurable, and the
measure is two-sided on purpose: bare paper alone is not evidence — a photograph of
a white wall is bare paper, and so is a card's own margin.

**The source fix** is a sentence in `prompt.OVERLAP`: where another clipping lies
across this piece, take it away completely and *continue this piece's own surface*
where it was. **The instrument** is `gates/assets.double`, which names the pair and
the two numbers and tells you the re-cut command. **The restraint** is that a
re-cut is a re-roll: `m19/s04/kartu_bukan_itu` came back as a page-sized card four
times running (fit 0.14–0.40), and the honest state for that shot is a gate that
still fails until the still is recomposed.

### 5.27 The generator returns 1376x768 at every aspect, and the stage draws 2976 px

Every still, piece and fill in the film is 1376x768 — `nano2`, `nano-pro` and the
1K rung alike. The film is 1920x1080 and `Stage.tsx` draws the page at `OVERSCAN`
1.55 so the camera may leave it. So every asset is drawn at **2.16x**:

```
pieces drawn above 1:1                      851 / 852
median upscale                              2.16x
max (m01/s05 pendatang)                     2.99x
```

At 1:1 the newsprint is mush and the halftone screen has gone grey.

**What does not work.** A larger model (measured: `nano-pro` also returns
1376x768). A local resize (adds no detail — the renderer already resamples). 4K
(Ultra-only).

**What works.** `gflow image upscale --scale 2k`, which is a re-render at 2752x1536,
not a resample. Two properties make it usable and both were measured: it is aligned
to the pixel (best correlation at `dx=dy=0`, so no piece moves), and it is visibly
crisper at the same display size. `voxkit/resolution.py` applies it to every raw
reply before it is keyed, driven by `[generation] upscale = "2k"`.

**Why it is not simply on everywhere.** The upscaler only accepts images Flow
generated, so every piece has to be generated *again* to get a media id: 852
pieces, 165 stills, 165 fills. Each re-cut is a re-roll. `m02/s01` is done and
renders clean; the rest of the film is still 1K and still soft.

---

## 6. What is left, in order

**The intent rewrite invalidated every render.** A chapter whose `.tsx` is newer
than its `.mp4` is stale, and after `voxkit/intent.py` every chapter is stale. The
`motion` gate measures the *pixels*, so it fails 21 of 22 modules for the honest
reason: those films were drawn from a program that no longer exists.

1. **m02 is the reference render** (`out/m02-final.mp4`, 37.30 s). Every gate ran
   and passed, `motion` included. Judge the intent system on it before spending an
   hour re-rendering the rest.
2. **Eight modules cannot be rendered at all** until their `figure` failure is
   cleared — `render` refuses a module that fails a gate, and that refusal is
   correct. The ten heads are listed in §3; `tools/uncover.py` refuses all ten for
   good reasons (4 are maps that stay above a figure under R6, 6 would bury a
   card's lettering), so each needs a **recomposed still**, not a repair.
3. **Then** `film/render_all.sh` — it re-gates, re-renders what is stale, and
   refuses what fails, so the log is the audit.
4. **Watch it.** The gates measure arithmetic; a person measures whether the film
   is any good. `vox camera --all` first, then the renders. Look for a note on a
   face, ink on the wrong card, a figure cut in half, a shot that reads as a
   photograph rather than a page.

What is *not* left: `program` failures. There are none, on any module, for the
first time — and that is a weaker claim than it sounds, because `program` was also
green when the film had no camera movement at all (§5.18). The claim that matters
is the pixel measurement in §5.22, and it currently exists for m02 only.

**Two decisions are waiting, not tasks.**

- **The 2K pass (§5.27).** 852 pieces + 165 stills + 165 fills have to be generated
  again to get a media id the upscaler will accept, then upscaled. m02/s01 is the
  proof; the rest of the film is still 1K. This is a re-roll of every asset, so it
  is also a re-review — and it is the only route to a sharp frame.
- **m19/s04 `kartu_bukan_itu`.** The duplicate is measured and named
  (`double` FAILs it), and four re-cuts produced a page-sized card instead of the
  piece. The repair is a recomposed still for that shot, not another roll.

---

## 7. Where the work was, last session

- `voxkit/intent.py` — **new, and the point of the session.** One `Beat` in, one
  `Decision` out: register, colour, pen, vehicle, arrival, move. §5.18.
- `voxkit/emit/choreography.py` — `by_intent` executes the decided moves;
  `punch_for` deleted (§5.21); pen windows widened before merging (§5.19); the shot
  opens on the page and reaches its first card by `OPEN_BY` (§5.20);
  `build_camera` scores the card's own word instead of the moment.
- `voxkit/ink.py` — `register(text, intent, duration, crowd)`: the note's vehicle is
  a decision, not a hash. `ARRIVAL` / `CAN_ARRIVE` replace the `bahan`-only table.
- `voxkit/gates/motion.py` — **new**. The only gate that reads rendered pixels.
- `voxkit/gates/program.py` — rule 13 (a decided punch must exist), and the ease
  rule now accepts "the pen answered the voice" (§5.22).
- `voxkit/emit/camera.py` — `DEFAULT_PUNCH` is the only hit shape; `EMPHASIS`
  deleted with `punch_for`; `Camera.tsx` throws on a non-finite framing instead of
  silently discarding the transform.
- `film/remotion/src/components/Stage.tsx` — `useResolvedCamera`: the emitter passes
  a *key list* and the stage read `.x/.y/.zoom` off it, so the transform was `NaN`
  and CSS dropped it. That single line is why the camera never moved.
- `voxkit/emit/choreography.py` — `creep` ramps the *interior* of a long park
  (§5.14); `steady_holds` widens for overlapping strokes (§5.15); `finish_figures`.
- `voxkit/presenter.py` — the silence walk advances `t += 2` instead of breaking.
- `voxkit/audit.py` — `vox camera` measures zoom spread, pan range, dead frames.
- `voxkit/gates/plan.py` — `angka_bahan` in `data`; `Card.placed()` in `compose`.
- `tools/find_bad_pieces.py`, `tools/repair.py` — the convergent repair loop.
- `_sweep/review/` — the measuring tools that decide arguments here:
  `intent_dist.py` (what was decided), `cammotion.py` (pixels), `alive.py` (pixels,
  split by the pen), `accent.py` (the emphasis distribution), `keys.py` (one shot's
  keys and strokes), `sheet.py` (contact sheets).

### Numbers worth keeping

| | before | after |
|---|---|---|
| notes stamped / written | 83 / 12 | **47 / 48** |
| cards decided `punch` | 0 | 23 |
| cards decided `arrive` / `pull` | 634 / 203 | 637 / 192 |
| modules with a `program` FAIL | 14 | **0** |
| m02 still frames | 49 % | 49 % — but **every run ≥20f is inside a pen window** |
| m02 still *outside* the pen | — | **30.9 %**, median 1.85 px/frame |
| m02 pen frames that are still | — | **96.2 %** (a stroke is read on a still frame) |
| m02 distinct camera moves | 4 (broken) / 33 (drifting under the pen) | 29, none under ink |
| m03 frames with a still camera | 43 % | 0 % |
| modules with assets | 15 | 22 |
| pieces in the film | — | 852 |

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
