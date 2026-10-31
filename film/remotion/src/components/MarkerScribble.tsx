import React from "react";
import {useCurrentFrame} from "remotion";
import {progress} from "./motion";
import {INK} from "./effects";

/**
 * A freehand marker stroke that draws itself on.
 *
 * Give it any SVG path in a 0..100 box; it animates `strokeDashoffset` so the
 * line appears to be drawn. Two passes with a tiny offset give the doubled,
 * slightly ragged edge of a real felt-tip mark — a single clean stroke reads as
 * vector art, not as someone marking up a page.
 *
 * For the common cases use the presets rather than hand-writing paths.
 */

export type ScribbleShape =
  | "underline"
  | "circle"
  | "arrow-right"
  | "arrow-down"
  | "check"
  | "bracket"
  | "cross";

const PATHS: Record<ScribbleShape, string> = {
  underline: "M 6 78 C 30 70, 62 82, 94 72",
  circle: "M 50 12 C 82 12, 94 34, 90 56 C 86 82, 58 92, 38 86 C 14 79, 6 54, 14 34 C 22 15, 44 9, 62 14",
  "arrow-right": "M 8 52 C 30 44, 58 58, 86 48 M 70 32 L 90 48 L 68 64",
  "arrow-down": "M 48 8 C 56 30, 44 56, 52 84 M 34 68 L 52 90 L 70 68",
  check: "M 14 52 C 24 60, 32 72, 40 84 C 54 56, 72 30, 90 14",
  bracket: "M 22 8 C 10 8, 8 14, 8 50 C 8 86, 10 92, 22 92",
  cross: "M 20 20 C 40 40, 60 60, 82 84 M 82 20 C 60 42, 40 62, 20 84",
};

/**
 * The stroke is drawn with `vectorEffect="non-scaling-stroke"` so its width stays
 * even when the 0..100 box is stretched to the element. That also means the dash
 * pattern is measured in **screen pixels**, not user units — so `pathLength`
 * normalisation does not help here and the dash length has to be derived from
 * the box the caller actually gave us. Pass `width`/`height` for that.
 *
 * Over-estimating is safe (the stroke finishes a little early); under-estimating
 * leaves visible gaps, so the estimate is deliberately generous.
 */

export const MarkerScribble: React.FC<{
  startFrame: number;
  shape?: ScribbleShape;
  /** Custom path in a 0..100 viewBox; overrides `shape`. */
  d?: string;
  duration?: number;
  color?: string;
  strokeWidth?: number;
  /** Second pass with a small offset — the "drawn twice" felt-tip edge. */
  doubleStroke?: boolean;
  /** Rendered width of the box, in px. Drives the dash length. */
  width?: number;
  /** Rendered height of the box, in px. */
  height?: number;
}> = ({
  startFrame,
  shape = "underline",
  d,
  duration = 14,
  color = INK,
  strokeWidth = 6,
  doubleStroke = true,
  width = 200,
  height = 140,
}) => {
  const frame = useCurrentFrame();
  const p = progress(frame, startFrame, startFrame + duration);

  if (p <= 0) return null;

  const path = d ?? PATHS[shape];
  // Upper bound on the real path length, in screen px. `hypot(w, h) * 1.25`
  // undershot a circle (perimeter ≈ 3.14 × the side, hypot only 1.41 ×) and the
  // mark drew itself three-quarters of the way and stopped.
  const len = (width + height) * 1.8;

  const draw = (offset: number, opacity: number, widthScale: number) => (
    <path
      d={path}
      fill="none"
      stroke={color}
      strokeWidth={strokeWidth * widthScale}
      strokeLinecap="round"
      strokeLinejoin="round"
      vectorEffect="non-scaling-stroke"
      opacity={opacity}
      strokeDasharray={len}
      strokeDashoffset={len * (1 - p)}
      transform={`translate(${offset} ${offset * 0.6})`}
    />
  );

  return (
    <svg
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        overflow: "visible",
        pointerEvents: "none",
      }}
    >
      {draw(0, 1, 1)}
      {doubleStroke ? draw(0.5, 0.45, 0.6) : null}
    </svg>
  );
};
