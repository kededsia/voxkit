# voxkit

A documentary-collage engine: narration in, a finished film out, with a contract
between the two that is checked before anything is paid for.

It knows nothing about a particular film. There is no module called `m12`, no
`docs/17min`, no account name, no 17-minute length. A *project* is a directory
with a `vox.toml`, a `plans/` folder and the audio; everything else is derived
from what is in it.

```
narration ──▶ transcript ──▶ plan ──▶ stills ──▶ pieces ──▶ plates ──▶ program ──▶ mp4
                               │                                        │
                               └──────────── gates ─────────────────────┘
                                     free            asset
```

The ordering is the whole economy. A card is a generation, a still is a
generation, a puppet frame is a generation, a re-render is minutes. A fault
found in the plan costs nothing; the same fault found in a render costs
everything downstream, because the executor is faithful — it prints the strings
it is given, draws the numbers it is given, and puts the piece where it is told.

## Quick start

```bash
pip install -e .            # numpy + Pillow; nothing else is needed
cd my-film && vox init      # writes a starter vox.toml
vox plan m01                # every free gate. Costs nothing. Run it first.
vox words m01               # score the transcript: where the voice lands
vox run   m01               # the chain, stopping at the first stage that fails
vox render m01              # gate, render muted, mux, read the file back
```

Exit codes are the contract: `0` means the thing asked for happened. A stage that
wrote some of its files and not others returns `1`, because a caller chaining
stages must not proceed on a hole.

## The plan is the contract

A plan is JSON. It says what the film *is* — shots, cards, where each piece sits,
which word it lands on, what the hand draws. Nothing else in the pipeline decides
anything; every later stage reads the plan and does what it says.

```json
{
  "plan_version": 2,
  "module": "m01",
  "context": {"skills_read": ["..."], "benang_read": ["..."], "laws": ["L-cards"]},
  "shots": [{
    "id": "s01",
    "range": [0, 132],
    "jenis": "PLACE",
    "marks": [["circle", 14, -4.2, "peta", {"at": 40}]],
    "cards": [{
      "name": "peta",
      "z": 4,
      "bahan": "peta",
      "wujud": "plang_fisik",
      "semantik": "CIANJUR",
      "at": "upper left of the frame, centred at 0.26 across, about 0.26 of the frame wide",
      "lands": 30,
      "word": "cianjur"
    }]
  }]
}
```

Three things are deliberately strict, because each was a silent default that
produced a film:

- **`wujud`** names a physical form from a closed table, and its height is
  derived from it. A `wujud` the table does not know is a failure, not a default
  of `0.7` — every overlap that card took part in would otherwise be measured
  against a guessed height.
- **`at`** is prose, and it must parse. An unreadable placement is a failure, not
  "no constraint".
- **`lands`** is relative to its own shot's start. A plan written in film frames
  fails every arrival check by the length of everything before it.

`bahan` decides two rules. A **readable** material (`cetak`, `koran`, `peta`)
must sit above everything that can lie on it, because the camera moves the layers
by different amounts and a figure that only touches a slip in the still will lie
across the words by frame 300. A plan that means to tuck a slip under a
photograph says `tertutup_boleh` and says `tertutup_alasan` — an exemption with
no reason is an exemption nobody can review.

## The gates

One process, findings as data, cached on the exact files each gate declared.

| gate | kind | the question |
|---|---|---|
| `schema` | free | every field has a type, a vocabulary and a placement that parses |
| `context` | free | the plan says what it was written against |
| `ranges` | free | shots tile the narration exactly |
| `arrival` | free | each card settles on the word that names it |
| `marks` | free | gestures exist, arrive after their card, and are not a lattice |
| `readable` | free | printed cards sit above anything that can cover them |
| `compose` | free | pieces are on the page and not buried |
| `data` | free | figures printed on cards are figures the voice says |
| `spell` | free | printed terms are spelled as the facts say |
| `program` | asset | the generated shot arrives on its words, moves variously, and keeps figures in frame |
| `still` | asset | each still is a print, and the shape of the stage |
| `slot` | asset | every piece has a measured slot, on the page, the right shape |
| `pose` | asset | every declared puppet exists, is wired, and is the size of its card |
| `plate` | asset | every shot has a page behind it, and the page is not a blur |
| `public` | asset | the renderer's copy of every asset is current |

A finding carries a **level**: `fail` blocks, `warn` is a number a person should
see, `note` is context. A gate that can only say PASS cannot tell you that a
piece is 63 % buried but still under its own threshold — which is exactly how a
buried card shipped.

A gate with nothing to look at says **`N/A`**, not PASS, and a render refuses an
incomplete run. Twelve gates passed on a module whose four declared puppets had
never been drawn; the only thing that would have caught it is refusing to call
silence a pass.

## What this replaces

Every rule above exists because its absence shipped. Measured in the old tree:

| the fault | the cost |
|---|---|
| `import rembg` at module scope, for a code path that never ran | 1.39 s of a 2.00 s import, in every one of 13 gate processes |
| 13 gates as 13 subprocesses, six decoding the same card PNGs | ~19 s per module, uncached |
| `--no-cache` in the render path | 1.7 s → 18.6 s per gate run, for nothing |
| one `gflow` call per puppet frame | 177 frames × ~45 s startup ≈ 2.2 h |
| the composition board omitted the stage ratio | every card drawn 44 % too short; a 63 % burial reported as 34 %, under its own threshold |
| geometry defined six times, in six tools | three of them read a slot's `x` as a corner instead of a centre, and shipped the number |
| the choreographer read `segments[].words`; the transcript had only `words` | zero accents found, every card travelled 17 frames, every ease `"slow"`, in all 22 modules |
| the R6 vocabulary had no `peta` and no `benda` | 27 readable cards exempt from the rule that keeps words legible |
| three tools returned `exit 0` for work they had not done | 3 missing stills, reported as success |

Two of these were invisible to every check in the old pipeline because the checks
read a different file than the code did. That is the failure this package is
built around: **one question, one implementation.** A transcript is read in
`words.py` and nowhere else. A placement becomes a box in `Rect.from_slot` and
nowhere else. A camera move is arithmetic in `emit/camera.py`, so it can be
asserted on without rendering.

## Layout

```
voxkit/
  config.py        vox.toml discovery, project paths
  contract.py      Plan, Shot, Card, Mark, Placement — the vocabulary and the parser
  geometry.py      Rect, and the only slot→box conversion
  words.py         the only transcript reader and the only accent scorer
  language.py      what the narration says, in the narration's language
  layout.py        the measured slot (centre + size)
  style.py         the renderer's mark vocabulary, read from the component
  image.py         chroma key, despill, paper border, print match
  locate.py        where a piece actually sits on its still
  batch.py         generation in chunks, judged by the filesystem
  prompt.py        prompt assembly with the laws stated in them
  stages.py        the seven stages, each returning non-zero on a partial result
  cli.py           the command line
  gates/           base.py (runner, cache) · plan.py · program.py · assets.py
  emit/            camera.py · choreography.py · gen_pose.py · tsx.py
tests/             117 tests; every gate is shown rejecting its own fault
```

`Film.tsx` and `Root.tsx` are **generated** from the plans. Hand-maintained, a
module that passed every gate and was missing from the map rendered as a
placeholder in the finished film, and nothing objected.

## The rules the numbers serve

1. A card settles on the word that names it, and travels 14–21 frames depending
   on how hard the voice lands on it.
2. The camera leads the word it moves toward by at least 14 frames. It holds on
   information and moves on transitions.
3. A puppet swap is a read, not a flicker: at least 6 frames apart.
4. A shot never ends on a camera that is still travelling.
5. The camera only ever zooms in, so the plate is exactly the page and there is
   no overscanned twin to keep in step.
6. A head and neck are never covered. Coverage of a torso is collage; coverage of
   a face is not.
7. A readable material sits above everything, always.
8. Nothing is uniform. If every card in a module travels the same distance and
   every camera key eases the same way, the accent lookup is not reaching the
   cards, and the gate says so.

## Tests

```bash
python -m pytest          # 117 tests, under a second
```

The suite is built on one idea: a plan that is *otherwise valid*, with exactly
one thing broken. So a failing gate is evidence about that one thing and not
about the fixture. The gates are shown rejecting a misprint, a gesture drawn on
blank paper, a card whose bottom edge left the page, a slip under a photograph, a
printed card under a figure, a module where nothing moves differently from
anything else.

Run against the 22 real plans this engine was extracted from, the free gates
report 77 failures and 177 warnings across 19 of them; three modules are clean.
The old board reported zero of the 17 worst of those, because it drew every card
too short to reach its own threshold.
