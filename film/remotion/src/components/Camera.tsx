import React from "react";
import {Easing, interpolate, useCurrentFrame} from "remotion";

/**
 * Camera moves that answer to the sentence.
 *
 * A shot with one constant push-in has a camera that is not listening. Real
 * explainer editing changes the *rate* with the narration: it creeps while a
 * sentence builds, snaps when a name lands, and then holds still so the viewer
 * can read. The rule this module exists to make easy:
 *
 *   **the camera moves when the words move, and stops when the words stop.**
 *
 * Two things follow from that:
 *   - `fast` is for arrival (a name, a number, a reveal) and should last 8–14
 *     frames. Any longer and it reads as a drift.
 *   - `slow` is for a hold (a sentence being spoken) and should last most of the
 *     shot. Any shorter and it reads as a nudge.
 *
 * A camera that keeps moving through a held line forces the eye to keep tracking,
 * which is the opposite of what a hold is for.
 */

export type CamEase = "slow" | "fast" | "snap" | "linear" | "step";

export type CamKey = {
  /** Local frame this key is reached. */
  at: number;
  /** Focus point, 0..1 of the box. Default 0.5, 0.5 (centre). */
  x?: number;
  y?: number;
  /** 1 = untouched. 1.3 = noticeably closer. */
  zoom?: number;
  /** How the camera *arrives* at this key. */
  ease?: CamEase;
};

/*
  Every curve except `step` is blended toward linear by `EASE_FLOOR`, so that no
  move ever reaches zero velocity.

  `inOut(cubic)` is stationary at both ends — that is what easing out means — and
  every segment of every shot used it, so the camera *stopped at every key*:
  accelerate, stop, accelerate, stop. With keys twenty frames apart that reads as
  a stutter, and it was reported, correctly, as the camera not moving at all.

  `voxkit/emit/camera.py` carries the same floor in `ease()`. The two must agree:
  the gates measure the Python curve, the film is drawn with this one, and a
  mismatch means a gate passing a film nobody is watching.
*/
const EASE_FLOOR = 0.4;

const floored = (f: (t: number) => number) => (t: number) =>
  EASE_FLOOR * t + (1 - EASE_FLOOR) * f(t);

const EASE: Record<CamEase, (t: number) => number> = {
  slow: floored(Easing.inOut(Easing.cubic)),
  fast: floored(Easing.out(Easing.exp)),
  snap: Easing.out(Easing.back(1.5)),
  linear: (t) => t,
  /*
    Four positions, no in-between. The camera does not slide to the new framing,
    it *is* in the new framing: 0, ⅓, ⅔, 1, each held for a couple of frames.

    This is the move a printed page wants. A smooth 12 % push reads as a lens; a
    stepped one reads as someone leaning closer, or as the next slide in a
    projector — which is the material the film is made of. It is also the only
    way to get a move that *feels* bigger than it is, which matters because the
    stills are 1376 px wide and a real 40 % push would turn the halftone to mush.
  */
  step: (t) => Math.min(1, Math.floor(t * 3 + 0.0001) / 3),
};

export type CameraValue = {x: number; y: number; zoom: number};

/**
 * Resolve a keyframe list to a camera value for the current frame.
 *
 * Keys are absolute and must be sorted. Missing fields carry forward from the
 * previous key, so a move only has to state what changes.
 */
export const useCamera = (
  keys: CamKey[],
  fallback: CameraValue = {x: 0.5, y: 0.5, zoom: 1},
): CameraValue => {
  const frame = useCurrentFrame();

  const resolved: CameraValue[] = [];
  let prev = fallback;
  for (const k of keys) {
    prev = {
      x: k.x ?? prev.x,
      y: k.y ?? prev.y,
      zoom: k.zoom ?? prev.zoom,
    };
    resolved.push(prev);
  }

  if (frame <= keys[0].at) return resolved[0];

  for (let i = 1; i < keys.length; i++) {
    if (frame <= keys[i].at) {
      const a = resolved[i - 1];
      const b = resolved[i];
      const ease = EASE[keys[i].ease ?? "slow"];
      const p = interpolate(frame, [keys[i - 1].at, keys[i].at], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });
      const e = ease(p);
      return {
        x: a.x + (b.x - a.x) * e,
        y: a.y + (b.y - a.y) * e,
        zoom: a.zoom + (b.zoom - a.zoom) * e,
      };
    }
  }

  return resolved[resolved.length - 1];
};

/**
 * Applies a camera value to its children. Coordinates are the box's own, so put
 * this inside a sheet and the focus points are the same numbers you used to place
 * the elements.
 */
export const Camera: React.FC<{
  value: CameraValue;
  /** The box the camera is moving over, in px. */
  width: number;
  height: number;
  children: React.ReactNode;
}> = ({value, width, height, children}) => {
  const {x, y, zoom} = value;

  return (
    <div style={{position: "absolute", inset: 0, overflow: "hidden"}}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          transformOrigin: "50% 50%",
          transform: `translate(${(0.5 - x) * width * zoom}px, ${(0.5 - y) * height * zoom}px) scale(${zoom})`,
        }}
      >
        {children}
      </div>
    </div>
  );
};

/**
 * Blend a camera toward a moving subject — for following a vehicle, a hand, a
 * cursor. `weight` 0 ignores the subject, 1 locks to it.
 *
 * The subject is usually produced by `sampleRoute`, so the camera and the moving
 * element are driven by the same number and cannot drift apart.
 */
export const withSubject = (
  base: CameraValue,
  subject: {x: number; y: number},
  weight: number,
): CameraValue => ({
  zoom: base.zoom,
  x: base.x + (subject.x - base.x) * weight,
  y: base.y + (subject.y - base.y) * weight,
});

/** The camera's value at an arbitrary frame, without being inside a component. */
export const resolveAt = (
  keys: CamKey[],
  frame: number,
  fallback: CameraValue = {x: 0.5, y: 0.5, zoom: 1},
): CameraValue => {
  let prev = fallback;
  const resolved: CameraValue[] = [];
  for (const k of keys) {
    prev = {x: k.x ?? prev.x, y: k.y ?? prev.y, zoom: k.zoom ?? prev.zoom};
    resolved.push(prev);
  }
  if (!keys.length) return fallback;
  if (frame <= keys[0].at) return resolved[0];
  for (let i = 1; i < keys.length; i++) {
    if (frame <= keys[i].at) {
      const a = resolved[i - 1];
      const b = resolved[i];
      const e = EASE[keys[i].ease ?? "slow"](
        Math.max(0, Math.min(1, (frame - keys[i - 1].at) / Math.max(1, keys[i].at - keys[i - 1].at))),
      );
      return {
        x: a.x + (b.x - a.x) * e,
        y: a.y + (b.y - a.y) * e,
        zoom: a.zoom + (b.zoom - a.zoom) * e,
      };
    }
  }
  return resolved[resolved.length - 1];
};

/**
 * **A punch** — the emphasis move, and the one this film was missing.
 *
 * *Client, after watching module 1: "gerakan kamera pada kata kata tertentu atau
 * untuk fokus sesuatu, masih kurang berani dan kurang ekspresif."* He is right,
 * and the cause was structural: every key in the module sat tens of frames from
 * the next one with `ease: "slow"`, so every move was a creep. A creep is not a
 * camera, it is a slideshow with a slow zoom.
 *
 * The research separates two moves that are routinely confused:
 *
 * | move | size | time | reads as |
 * |---|---|---|---|
 * | **drift** (Ken Burns) | 1–4 % per second, ≤ 8 % total | 4–6 s | a still that is alive. *"If the viewer can see the move, it has become an effect rather than a shot"* |
 * | **punch** (emphasis) | 8–20 % | 3–6 frames | a decision. The camera *goes* somewhere on the word |
 *
 * A film needs both, and module 1 only had the first. The punch is built from
 * four parts, and dropping any one of them is why a punch reads as a glitch:
 *
 *  1. **anticipation** — two frames pulling *back*, 1.5 % and 6 % away from the
 *     target. Without it the jump has no cause.
 *  2. **the rise** — 4–6 frames to 2.5 % *past* the target.
 *  3. **the settle** — 6–10 frames back onto it, slow. This is the part that
 *     makes it a camera rather than a cut.
 *  4. **a real destination** — a focus point on the thing the word is about, not
 *     the centre of the frame.
 *
 * The rise is `step` by default: three held positions, no interpolation. On a
 * print collage a smooth 12 % push reads as a lens; a stepped one reads as
 * someone leaning in, and it *feels* twice the size of the number.
 */
export const punch = (
  keys: CamKey[],
  at: number,
  target: CameraValue,
  opts: {
    rise?: number;
    settle?: number;
    antic?: number;
    smooth?: boolean;
    anticPct?: number;
    overPct?: number;
  } = {},
): CamKey[] => {
  const {
    rise = 5,
    settle = 9,
    antic = 2,
    smooth = false,
    anticPct = 0.015,
    overPct = 0.025,
  } = opts;
  const before = resolveAt(keys, at - antic - 1);
  const away = {x: before.x - target.x, y: before.y - target.y};
  const pull: CameraValue = {
    x: before.x + away.x * 0.06,
    y: before.y + away.y * 0.06,
    zoom: before.zoom * (1 - anticPct),
  };
  const over: CameraValue = {
    x: target.x - away.x * 0.02,
    y: target.y - away.y * 0.02,
    zoom: target.zoom * (1 + overPct),
  };
  const head = keys.filter((k) => k.at < at - antic);
  const tail = keys.filter((k) => k.at > at + rise + settle);
  return [
    ...head,
    {at: at - antic, ...before, ease: "slow"},
    {at: at - 1, ...pull, ease: "linear"},
    {at: at + rise, ...over, ease: smooth ? "fast" : "step"},
    {at: at + rise + settle, ...target, ease: "slow"},
    ...tail,
  ];
};

/**
 * **`EMPHASIS` — the punch a `kata penegasan` gets.** R2b1.
 *
 * The default punch above is 1.5 % back and 2.5 % over: enough to make a name or
 * a number arrive, not enough to make a stressed word felt in the body. Round
 * seven was explicit that the emphasis words need the bigger move — *"harusnya
 * gerakannya kayak per zoom out zoom in cepat… biar efek push-nya di pemirsa
 * terasa, ga hanya terdengar dan terlihat"* — so this preset is 5 % back and
 * 12 % over, in three frames, settling over eight.
 *
 * `rise: 3` is not arbitrary. R2b1's mechanical test asks that `zoom(w+3)` be
 * higher than `zoom(w+6)`, i.e. that the peak has already been passed three
 * frames after the word starts. With the default `rise: 5` the camera is still
 * climbing at `w+3` and the test fails on a move that looks fine — the rise has
 * to *complete* inside the window the test samples.
 *
 * Three held positions, no interpolation (`step`): on a print collage a smooth
 * 12 % push reads as a lens, a stepped one reads as a body leaning in.
 */
export const EMPHASIS = {antic: 2, rise: 3, settle: 8, anticPct: 0.05, overPct: 0.12} as const;
