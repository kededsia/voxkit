# PRINCIPLES — what the film obeys, and what it is not allowed to do

Three principles. Two are taken from VOX-PLUGIN-2 because the client named them;
one comes out of measuring this film. Each one is written as a rule, then as the
evidence that v3 breaks it, then as the test that would prove it fixed. A
principle with no test is a preference.

Nothing here is a port of v2's code. v2 got the *rules* right and this engine gets
the *measurement* right; the rules are what is being taken.

---

## P1 — One presenter, one gaze

> The camera is not a second author. It is where the presenter is looking.

A presenter explaining a page does one thing at a time: the voice names something,
the eye arrives at it, the hand marks it. Three agents, one act. The moment the
camera is allowed its own schedule, the viewer is being shown two things at once
and neither wins.

**v2, verbatim** (`DECISIONS.md` §Kamera):

```
Kalimat sedang diucapkan → slow, zoom kecil, sepanjang kalimat.
Nama / angka / reveal mendarat → fast, 1,15–1,4×, 8–14 frame.
Ada baris yang harus dibaca → berhenti bergerak.
Satu push-in konstan sepanjang shot = kamera tidak mendengarkan.
```

The third line is the one v3 deleted.

**What v3 does instead.** Every camera key gets a breath (`creep`), so no key is
ever allowed to be a rest. Measured on the rendered film:

| | |
|---|---|
| frames with the camera moving | **92.3 %** |
| scored words spoken while the camera is moving | **92.2 %** |
| longest genuinely still run in a shot | **8 frames** (0.27 s), max 29 |
| shots that hold for ≥20 frames | **4 of 165** |
| frames with ≥2 things moving at once | **66.8 %** |

The camera and the pen are each bound to the voice — camera keys sit a median of
3 frames from a word, strokes 1 frame — but they are not bound to *each other*:
**only 50 % of strokes are drawn on the card nearest the centre of the frame.**
Half the time the eye and the hand are on different pieces.

**The rule to enforce.** A shot has three registers, and only three:

1. **arrive** — the frame moves to the thing the word names, and lands before it;
2. **rest** — while a stroke is drawn or a line is read, the frame does not move.
   Not "moves slowly": does not move. `STILL` frames are a feature, not dead air;
3. **leave** — the frame moves on the transition, after the stroke has landed.

**Test.** Per shot: at least one rest of ≥12 frames. During every stroke, frame
centre within 0.30 of the stroke's own centre. No frame with more than two
simultaneous motions. These are three numbers, so they can be gated.

---

## P2 — A mark is a decision, not a decoration

> Colour carries meaning. The pen carries volume. One mark per beat.

**v2, verbatim** (`DECISIONS.md` §Marker):

```
Warna membawa arti. Kuning = penekanan utama, satu per shot. Coral = nama.
Sky = pendukung. Ink = koreksi. Chalk = tanda di atas foto gelap.
Pena membawa volume. Highlighter di bawah huruf, felt-tip di atasnya,
ballpoint untuk koreksi, crayon paling keras.
Ring kuning di atas stiker kuning tidak terlihat. Ring hanya di atas foto.
Satu tanda per beat.
```

Every line there is a rule about *contrast and hierarchy*, and every one is
checkable.

**What v3 does instead.** Measured on the emitted program, 465 marks:

| | v3 | the renderer already supports |
|---|---|---|
| pens used | `marker` × **465** | marker, highlighter, felt, ballpoint, chalk, crayon |
| colours used | coral 263, crimson 201, mustard 1 | yellow, amber, coral, sky, ink, chalk, … |
| how the colour is chosen | `"coral" if i % 2 == 0 else "crimson"` | five intent presets in `Marker.tsx` |

The colour alternates by **array index**. It carries no meaning at all, which is
exactly the failure v2 named ("satu kuning 6 px untuk semua hal membuat semua
penekanan sama volumenya"). And the renderer has had the answer the whole time —
`PRESET` in `Marker.tsx`:

```
emphasis:   {color: "yellow", pen: "marker"}
name:       {color: "coral",  pen: "marker"}
support:    {color: "sky",    pen: "felt"}
correction: {color: "ink",    pen: "ballpoint"}
quiet:      {color: "chalk",  pen: "chalk"}
```

v3's `style.py` also disagrees with its own renderer: it declares
`PENS = {marker, chalk, pencil, brush}` and `COLORS = {coral, crimson, charcoal,
mustard, navy, cream}` — `pencil` and `brush` do not exist in `Marker.tsx`, and
`highlighter`, `felt`, `ballpoint`, `crayon`, `yellow`, `sky`, `ink` are missing
from the validator. A plan asking for the pen the renderer actually has would be
rejected by the schema.

**The rule to enforce.**

1. Every mark names an **intent** (`emphasis`, `name`, `support`, `correction`,
   `quiet`), and the intent picks the pen and the colour. Never an index.
2. At most one `emphasis` per shot. If two things are equally loud, neither is.
3. A mark must contrast with what it lands on: no yellow ring on a yellow block,
   no coral stroke on a crimson card. This is measurable from the card's own
   pixels.
4. One mark per beat — already true (median 1 frame from a word), keep it.

---

## P3 — A face is never covered

> A slip across a torso is collage. A slip across a face is not.

**v2, verbatim** (client, quoted in `tools/heads.py`):

```
yg paling penting untuk gambar orang itu bagian kepala sampai leher jgn tertutup.
kalau ketutup ya di tuker layer cardnya atau di geser. sampai wajah dan lehernya
terlihat.
```

**v2 got three things right, and all three matter:**

- **The measure is head and neck only.** Not "how much of the body is behind a
  card" — a slip across a torso is normal collage. Body coverage is reported, and
  never fails a shot.
- **The head is found by shape, not by position.** The top 26 % of a silhouette is
  wrong often and always in the same direction: a driver's piece starts at the car
  roof, a man holds a framed photo at head height, a torn page carries two boys.
  v2's answer: the first band of rows, below the top of the piece, that is narrow
  compared with the widest row and *stays* narrow.
- **The fix is a layer swap, never a nudge.** Moving a card 45–114 px off its slot
  leaves a printed slip with no card over it — the plate fills the hole and the eye
  reads two of everything. Raising the person costs nothing downstream. And a swap
  is refused when it would bury the *card's* own words: a silhouette over a blank
  margin is collage, a silhouette over "4.000 M" is a lost fact.

**What v3 does instead.** `voxkit/geometry.py` has `head_band()` — the same three
constants, the same shape test, the same docstring quoting the client — and it is
**called by nothing**. It is exported in `__init__.py` and dead. The `compose` gate
measures burial by area only: a face buried 50 % is a `warn`, under the 55 % fail
threshold, and indistinguishable from a blank margin buried 50 %.

Measured on the 137 person cut-outs in the film: **15 have a covered head**
(≥10 % of the head-and-neck band), 3 of them **completely**:

```
m19 s01 figur_pembaca_kuno     100%  by kartu_satu_hal          fixed by swap
m19 s02 figur_orang_lain       100%  by foto_peta_nusantara     needs a still
m22 s07 figur_pembaca_akhir    100%  by kartu_catatan           needs a still
m20 s02 figur_pengamat          80%  by kartu_bersalju          needs a still
m17 s04 orang_memegang_daun     68%  by foto_buah_nangka        needs a still
...
```

`m20 s02` is the one to look at: a man standing, seen from behind, and the card
`BERSALJU, MEMANCARKAN CAHAYA` is pasted across the top of him. He has no head.
The frame is otherwise good — a circled snow field, a bracketed claim, a
handwritten `berarti` on his back. All 22 modules passed every gate.

**The rule, now enforced.** `compose` cannot answer this — it measures area, so a
card over a head is a small percentage of a silhouette and reports as a note. The
new `figure` gate measures the head-and-neck band itself, and `tools/uncover.py`
fixes what can be fixed:

- raise the person above the covering card — **5 of 15 done**, each with the
  lettering cost measured before the raise (0–10 % of the coverer's ink);
- refuse when a **map** is the coverer. A map is place names edge to edge, so a
  figure standing anywhere on it buries words. R6 keeps it on top; the still has
  to be recomposed. **4 refusals**;
- refuse when the raise would bury >10 % of the coverer's own lettering.
  **4 refusals**, and one (`m17 s04`) is a photograph, not a slip.

Ten heads are left, across eight modules, and they are a recomposition job — which
means the film cannot be rebuilt until they are done, because `vox render` refuses
a module that fails its gates. That is the correct behaviour and it is also the
bill.

**One rule of v3's had to yield, and the reason is in v3's own code.** `readable`
used to fail a printed card under a person outright. Its stated reason is a v2
fact — *"the camera moves the layers by different amounts, so a figure that only
touches it in the still will lie across the words by the end of the shot."* In v3
the plate and every card sit inside **one** transform (`Stage.tsx` scales the whole
stage; there is no per-layer parallax), so that failure mode does not exist here.
What exists is static overlap, and that is measurable: `figure` measures the
coverer's own ink. So `readable` now defers that one pair, a `peta` still fails
outright, and two tests were rewritten to say so.

---

## What v3 keeps from v3

These are better here than in v2 and must not be traded away for the above:

- **Measure, do not assert.** `vox camera` exists because "does the camera move?"
  turned out to be a distribution, not a verdict.
- **A skip is not a pass.** `Skipped` is a finding, and a render refuses it.
- **The camera is arithmetic in Python**, so a move can be asserted on without
  rendering. v2 could only look at a render.
- **One question, one implementation.** A placement becomes a box in
  `Rect.from_slot` and nowhere else; v2 had geometry defined six times.
- **The ordered camera pipeline** (`build_camera → … → creep`). The order is the
  design. P1 changes *what one of those steps is allowed to do*, not the order.

---

## The failure mode all three share

Every principle above is a **restraint**: do not move here, do not reuse this
colour, do not cover this. v3's engineering instinct is the opposite — it adds a
pass until a number goes up. `creep` exists because a measurement said "43 % of
frames are still", and the fix was to remove stillness rather than to ask where
stillness belonged.

So the last principle is the one that governs the other three:

> **A gate that can only reward motion will eventually destroy rest.**

Any future rule that says "more X is better" needs a companion that says where X
is wrong. `creep` had no companion. That is why the film moves 92 % of the time.
