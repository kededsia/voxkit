# Example project — one module, one style key

`examples/project` is a complete project as the engine sees one: a `vox.toml`, a plan,
a transcript, and the style key. It is small enough to read and real enough to run.

```
examples/project/
  vox.toml              name = "example", 30 fps
  plans/m12.json        one module, already written
  audio/m12.json        its transcript, already scored
  assets/style-key.jpg  the look
```

```bash
cd examples/project
vox plan m12            # every free gate; costs nothing, calls no backend
vox still m12 --dry     # the prompts and the jobs it would queue, drawn nowhere
```

`vox plan m12` is the whole point of the example: it proves the engine reads a project
it has never seen, without an account, a key, or a network.

## The style key

`assets/style-key.jpg` is a single reference image. It is passed as `ref` on **every
still job** and on nothing else — `stages.py`:

```python
jobs = [Job(text=prompt.still_prompt(plan, s), output=s.id,
            ref=str(project.style_key()) if project.style_key().is_file() else None, ...)]
```

Pieces, poses and fills do not get it: a piece is cut from a still that already has the
look, so handing it the key again would be a second opinion about the same thing.

The prompt says what to take from it (`prompt.STYLE`):

> copy the TREATMENT of the attached style key — hand-cut editorial zine PAPER COLLAGE:
> bold flat colour blocks, torn newsprint edges, masking tape, coarse sepia/charcoal
> halftone (zero green/blue), real paper drop shadows. Pieces are scissor-cut organic
> silhouettes with a rough white border. Vary them: most in warm sepia, some in
> aged-newsprint one-ink monochrome — never all cold, never modern digital colour.
> **Do not copy the reference words or subjects.**

That last sentence is load-bearing. A style key is a *treatment*, not a subject: the
model will happily reproduce its people, its signage and its place names into a film
about somewhere else.

## The constants the key has to agree with

`voxkit/config.py::Style` — these are the engine's, not the film's:

| | | why |
|---|---|---|
| `paper` | `#EFE7D6` | the plate is drawn in this colour; a still on a different cream reads as a foreign sheet |
| `ink` | `sepia` | one ink, so a card and a photograph share a palette |
| `chroma` | `#FF00FF` | pieces are keyed, not segmented; a pale map on a guessed background came back a ghost |
| `chroma_tolerance` | `62.0` | measured, not chosen |
| `chroma_feather` | `20.0` | a hard key leaves a magenta fringe on torn edges |
| `paper_border` | `0.022` | the rough white border, as a fraction of the piece |

## Making your own

Three rules, and they are the three the gate `still` will hold you to:

1. **Cream, not white.** White paper next to `#EFE7D6` plates reads as a different film.
2. **One ink.** Sepia and charcoal halftone, zero green and zero blue. A cool block is
   the single most common reason a page is rejected as "modern digital colour".
3. **Physical, not rendered.** Torn edges, masking tape, a real drop shadow. A clean
   vector rectangle is not collage.

Keep it around 1400 px wide. It is a treatment reference, not a plate: it is never
composited, only looked at.
