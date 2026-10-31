/**
 * Motion helpers for a hand-made, cartoon feel.
 *
 * The single biggest reason AI-generated motion looks monotonous is that
 * everything travels in a straight line at a constant speed. Real cut-out
 * animation does the opposite: it arcs, it overshoots, it holds, it squashes on
 * impact. These helpers are the small vocabulary needed to get there.
 */

import {Easing, interpolate, spring} from "remotion";

/**
 * Stop-motion hold. Quantise the frame so motion advances in steps of N frames
 * — the 2s/3s animation cadence of paper cutout work.
 *
 * `stepped(21, 3)` -> 21. Apply to any 0..1 progress before using it.
 */
export const stepped = (frame: number, hold = 2): number =>
  Math.floor(frame / hold) * hold;

/** Clamped 0..1 progress with easing, the shape almost everything needs. */
export const progress = (
  frame: number,
  from: number,
  to: number,
  easing: (t: number) => number = Easing.out(Easing.cubic),
): number =>
  interpolate(frame, [from, to], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing,
  });

/**
 * Perpendicular bow for an entrance. A straight slide reads mechanical; adding
 * a sine bulge makes the element swing in on an arc, like it was carried.
 *
 * `t` is 0..1 progress, `curve` the peak offset in px.
 */
export const arcOffset = (t: number, curve: number): number =>
  Math.sin(t * Math.PI) * curve;

/**
 * Squash and stretch. Stretches along the travel axis while moving, squashes on
 * landing. Returns multipliers to apply to scaleX/scaleY.
 *
 * `speed` is 0..1 (how fast it is currently moving), `land` is 0..1 (impact).
 */
export const squashStretch = (
  speed: number,
  land = 0,
  amount = 0.06,
): {sx: number; sy: number} => {
  const stretch = amount * speed;
  const squash = amount * 1.6 * land;
  return {sx: 1 - stretch + squash, sy: 1 + stretch - squash};
};

/** A settling spring with a little visible overshoot. */
export const settleSpring = (
  frame: number,
  fps: number,
  damping = 14,
  stiffness = 190,
): number =>
  spring({frame, fps, config: {damping, stiffness, mass: 0.5}});

/** Idle drift so a held frame never looks frozen. */
export const breathe = (
  frame: number,
  amount = 0.004,
  period = 46,
  phase = 0,
): number => 1 + amount * Math.sin((frame / period) * Math.PI * 2 + phase);

/**
 * Wobble in degrees, for a pin or sticker that never quite sits still.
 * Different `phase` per element keeps a group from pulsing in unison.
 */
export const wobble = (
  frame: number,
  amplitude = 0.6,
  period = 60,
  phase = 0,
): number => amplitude * Math.sin((frame / period) * Math.PI * 2 + phase);
