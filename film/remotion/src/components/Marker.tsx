import React from "react";
import {useCurrentFrame} from "remotion";
import {progress} from "./motion";
import {FILLED, compose, ribbon, widen, type Stroke} from "./HandStroke";

/**
 * The marker library.
 *
 * A marker is not one thing. A highlighter is a wide translucent band that sits
 * *under* the eye, a felt-tip is an opaque line that sits *on* the page, a
 * ballpoint is a thin correction, chalk is broken. Using one yellow 6 px stroke
 * for all of those is why annotation starts to feel like a template — everything
 * is emphasised at the same volume, so nothing is.
 *
 * Three axes, chosen independently:
 *
 *   colour  — what the mark means (see MARKER_COLORS)
 *   pen     — how loud it is (see PENS)
 *   shape   — what it points at (see SHAPES)
 *
 * plus a motion that decides how the mark arrives.
 *
 * **The geometry is generated, not authored.** `HandStroke.ts` builds a
 * centreline with smooth noise and a half-width that varies with pressure, and
 * this component fills it as a ribbon. That is the difference between a mark that
 * reads as a pen and one that reads as vector art: an authored bezier is closed,
 * symmetric and identical every time, and eight of them in a row read as a
 * template. Pass a different `seed` per call site and no two marks are the same.
 *
 * Two implementation details worth knowing before changing anything here:
 *
 * 1. **Geometry is in pixels**, in a `viewBox` of the container's real size. The
 *    old version drew in a `0..100` box with `preserveAspectRatio="none"`, which
 *    stretched the pen as well as the shape: an ellipse in a wide container came
 *    out with one thick end and one thin one.
 * 2. **The draw-on is a mask, not a dash on the visible stroke.** A ribbon is a
 *    fill, so it has no dash pattern to animate. The mask holds a fat stroke along
 *    the same centreline with `pathLength={100}`, so `strokeDashoffset` is exact
 *    for any shape — this also retires the old `(width + height) * 1.8` guess,
 *    which undershot circles and left them three-quarters drawn.
 */

// ---------------------------------------------------------------- colours

/**
 * Twelve marks, not twelve tints. Each is picked to survive on cream paper and
 * on a black-and-white photograph, which is where most of these end up.
 */
export const MARKER_COLORS = {
  /** The house yellow. Reserve it for the one thing that must be seen first. */
  yellow: "#F2C200",
  amber: "#E8890C",
  coral: "#E8503A",
  magenta: "#D6336C",
  plum: "#8E3B6B",
  violet: "#6B4FD8",
  sky: "#2E86DE",
  teal: "#0E9E8F",
  mint: "#35B37E",
  lime: "#A8C400",
  /** Correction, not emphasis. Use when something is wrong. */
  ink: "#1A1A1A",
  /** For marking a dark photo where nothing else reads. */
  chalk: "#F7F3E8",
} as const;

export type MarkerColor = keyof typeof MARKER_COLORS;

// ---------------------------------------------------------------- pens

export type PenName = "marker" | "highlighter" | "felt" | "ballpoint" | "chalk" | "crayon";

export const PENS: Record<
  PenName,
  {
    strokeWidth: number;
    opacity: number;
    blend: "normal" | "multiply";
  }
> = {
  /**
   * Default, and the one the client asked for: *"handraw, bold, dan TEBAL"*.
   *
   * 10 px was the old default and it read as a fine liner on a 1080p still — a
   * correction mark, not an emphasis. This is a **fat sharpie**: 16 px, fully
   * opaque, slightly warm black-shadow territory. On a card 400 px wide, 16 px is
   * 4 % of the card — the proportion a real marker has against a word.
   *
   * Thick marks are allowed to cover what they pass over: the user's note was
   * explicit that covering neighbouring art while the mark draws on is fine, so
   * there is no reason to thin the pen to protect the picture.
   *
   * Opacity is 0.94, not 1: a marker on newsprint never quite hides the fibre
   * under it, and the missing 6 % is what stops the ribbon reading as vinyl. The
   * fringe that sells it is `BLEED` below.
   */
  marker: {strokeWidth: 16, opacity: 0.94, blend: "normal"},
  /** Wide and translucent: a band you can still read through. Goes under text. */
  highlighter: {strokeWidth: 38, opacity: 0.42, blend: "multiply"},
  /** Opaque and precise. The pen you use when the mark is a fact, not a mood. */
  felt: {strokeWidth: 11, opacity: 1, blend: "normal"},
  /** Thin, hard, no softness at all — corrections and small brackets. */
  ballpoint: {strokeWidth: 5, opacity: 1, blend: "normal"},
  /** Broken and dusty. Good on dark photos, where a clean line looks pasted on. */
  chalk: {strokeWidth: 18, opacity: 0.92, blend: "normal"},
  /** Waxy, wide, uneven — the loudest mark in the box. Use once per piece. */
  crayon: {strokeWidth: 22, opacity: 0.88, blend: "multiply"},
};

/**
 * How far the ink soaks past the pen, and how light that fringe is.
 *
 * A marker dragged over newsprint has no edge: pigment wicks into the fibre a
 * few pixels beyond the tip and that fringe is much lighter than the body. Drawn
 * as one filled polygon the mark ends on a hard vector boundary — which is the
 * other half of why these marks read as graphics dropped on a photo. The fringe
 * is the same centreline at 1.7× the body, laid underneath at 0.18.
 *
 * Only the wet pens get it. A ballpoint correction is a hard thin line by
 * definition, and a chalk line is broken dust, not a stain.
 */
const BLEED: Partial<Record<PenName, {scale: number; opacity: number}>> = {
  marker: {scale: 1.42, opacity: 0.15},
  crayon: {scale: 1.5, opacity: 0.13},
};

// ---------------------------------------------------------------- shapes
/**
 * Every shape is a *gesture*, and `HandStroke.compose` decides what the gesture
 * looks like in the container it was given. Names are kept stable because they are
 * the vocabulary shots are written in.
 */
export const SHAPES = [
  "underline",
  "underline-double",
  "box",
  "brackets",
  "circle",
  "ellipse",
  "lasso",
  "arrow-right",
  "arrow-down",
  "arrow-curve",
  "bracket-left",
  "bracket-right",
  "corner-marks",
  "cross",
  "check",
  "star",
  "burst",
  "squiggle",
  "strike",
  "band",
  "tape",
  "question",
  "exclamation",
] as const;

export type MarkerShape = (typeof SHAPES)[number];

// ---------------------------------------------------------------- motion

export type MarkerMotion = "draw" | "snap" | "sweep" | "pulse" | "wiggle";

// ---------------------------------------------------------------- component

const polyline = (pts: [number, number][]) =>
  pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join("");

export const Marker: React.FC<{
  shape: MarkerShape;
  /** Colour name from `MARKER_COLORS`, or any CSS colour. */
  color?: MarkerColor | string;
  pen?: PenName;
  /** Local frame the mark starts. */
  at: number;
  duration?: number;
  motion?: MarkerMotion;
  /** Container size in px. Geometry is built in these units. */
  width?: number;
  height?: number;
  /** Override the pen's stroke width, in px. */
  strokeWidth?: number;
  /** Resting tilt, degrees. */
  rotate?: number;
  /** Filled shapes only: how solid the fill is. */
  fillOpacity?: number;
  /** Change this and the same gesture is drawn by a different hand. */
  seed?: number;
}> = ({
  shape,
  color = "yellow",
  pen = "marker",
  at,
  duration = 12,
  motion = "draw",
  width = 240,
  height = 140,
  strokeWidth,
  rotate = -2,
  fillOpacity,
  seed = 1,
}) => {
  const frame = useCurrentFrame();
  const uid = React.useId().replace(/:/g, "");
  const p = progress(frame, at, at + duration);
  if (p <= 0) return null;

  const hex = (MARKER_COLORS as Record<string, string>)[color] ?? color;
  // Fail with the pen's name, not `Cannot read properties of undefined`. A typo in
  // `pen` (e.g. "pencil") reaches here because the bundle strips types without
  // checking them, and the crash it used to produce — reading `strokeWidth` off
  // undefined — arrived hundreds of frames into a render with no mention of which
  // prop was wrong. Silent fallback to `marker` would be worse: a wrong pen is a
  // wrong picture that still renders.
  const style = PENS[pen];
  if (!style) {
    throw new Error(
      `Marker: unknown pen "${pen}". Use one of: ${Object.keys(PENS).join(", ")}.`,
    );
  }
  const sw = strokeWidth ?? style.strokeWidth;

  // a small flick past the end so the stroke does not just stop
  const overshoot =
    motion === "snap" && p > 0.86 ? Math.sin(((p - 0.86) / 0.14) * Math.PI) * 0.04 : 0;

  // after the stroke lands, some marks keep moving
  const settled = progress(frame, at + duration, at + duration + 18);
  const pulse = motion === "pulse" ? 1 + 0.07 * Math.sin(settled * Math.PI) : 1;
  const wob = motion === "wiggle" ? Math.sin(settled * Math.PI * 2.2) * 1.4 : 0;

  const filled = FILLED.has(shape);
  const sweep = motion === "sweep" ? progress(frame, at, at + duration) : 1;

  // A multi-stroke gesture (a box is four passes, an arrow is three) should look
  // like a hand working through it, not like a stamp: stagger the starts and let
  // each pass finish before the whole thing does.
  const strokes: Stroke[] = filled ? [] : compose(shape, width, height, sw, seed);
  const n = strokes.length;
  const stagger = n > 1 ? duration * 0.1 : 0;
  const each = n > 1 ? duration * 0.62 : duration;

  const pad = sw * 6 + 24;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        overflow: "visible",
        pointerEvents: "none",
        mixBlendMode: style.blend,
        transform: `rotate(${rotate + wob}deg) scale(${pulse})`,
        transformOrigin: "50% 50%",
      }}
    >
      {filled ? (
        <Filled
          shape={shape}
          color={hex}
          opacity={fillOpacity ?? 0.55}
          sweep={sweep}
          width={width}
          height={height}
        />
      ) : (
        <>
          <defs>
            <mask
              id={`m${uid}`}
              maskUnits="userSpaceOnUse"
              x={-pad}
              y={-pad}
              width={width + pad * 2}
              height={height + pad * 2}
            >
              {strokes.map((s, i) => {
                const pi = progress(frame, at + i * stagger, at + i * stagger + each);
                return (
                  <path
                    key={i}
                    d={polyline(s.pts)}
                    fill="none"
                    stroke="#fff"
                    strokeWidth={sw * 3}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    pathLength={100}
                    strokeDasharray={100}
                    strokeDashoffset={100 * (1 - Math.min(1, pi + overshoot))}
                  />
                );
              })}
            </mask>
          </defs>
          {BLEED[pen] ? (
            <g opacity={BLEED[pen]!.opacity * style.opacity} mask={`url(#m${uid})`}>
              {strokes.map((s, i) => (
                <path key={`b${i}`} d={ribbon(widen(s, BLEED[pen]!.scale))} fill={hex} />
              ))}
            </g>
          ) : null}
          {strokes.map((s, i) => (
            <path
              key={i}
              d={ribbon(s)}
              fill={hex}
              opacity={style.opacity * (i === 0 ? 1 : 0.86)}
              mask={`url(#m${uid})`}
            />
          ))}
        </>
      )}
    </svg>
  );
};

const Filled: React.FC<{
  shape: string;
  color: string;
  opacity: number;
  sweep: number;
  width: number;
  height: number;
}> = ({shape, color, opacity, sweep, width, height}) => {
  const W = width;
  const H = height;
  if (shape === "tape") {
    // a strip of translucent tape: torn ends, a lighter core
    return (
      <g opacity={opacity * Math.min(1, sweep * 1.2)}>
        <path
          d={`M${0.02 * W} ${0.18 * H} L${0.16 * W} ${0.12 * H} L${0.12 * W} ${0.26 * H} L${0.2 * W} ${0.34 * H} L${0.08 * W} ${0.44 * H} L${0.18 * W} ${0.56 * H} L${0.1 * W} ${0.66 * H} L${0.2 * W} ${0.8 * H} L${0.06 * W} ${0.86 * H} L${0.94 * W} ${0.86 * H} L${0.88 * W} ${0.74 * H} L${0.96 * W} ${0.62 * H} L${0.86 * W} ${0.52 * H} L${0.96 * W} ${0.4 * H} L${0.84 * W} ${0.3 * H} L${0.94 * W} ${0.2 * H} L${0.88 * W} ${0.14 * H} Z`}
          fill={color}
        />
        <path
          d={`M${0.08 * W} ${0.3 * H} L${0.92 * W} ${0.28 * H} M${0.08 * W} ${0.62 * H} L${0.92 * W} ${0.6 * H}`}
          stroke="#FFFFFF"
          strokeWidth={2}
          opacity={0.35}
        />
      </g>
    );
  }

  // highlighter band, wiped on from the left
  return (
    <rect
      x={0.04 * W}
      y={0.22 * H}
      width={0.92 * W * sweep}
      height={0.56 * H}
      rx={Math.min(6, H * 0.08)}
      fill={color}
      opacity={opacity}
    />
  );
};

/**
 * A suggested pairing of colour and pen by *intent*, so a sequence does not end
 * up with six marks all shouting at the same volume.
 *
 *   emphasis  one thing per shot, maximum
 *   name      a label or a proper noun being circled
 *   support   a secondary observation
 *   correction something wrong, or a "no"
 *   quiet     a mark on a dark photo, where nothing else survives
 */
export const MARK_ROLES = {
  emphasis: {color: "yellow", pen: "marker"},
  name: {color: "coral", pen: "marker"},
  support: {color: "sky", pen: "felt"},
  correction: {color: "ink", pen: "ballpoint"},
  quiet: {color: "chalk", pen: "chalk"},
} as const satisfies Record<string, {color: MarkerColor; pen: PenName}>;
