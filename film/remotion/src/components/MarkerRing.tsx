import React from "react";
import {useCurrentFrame} from "remotion";
import {progress} from "./motion";
import {YELLOW} from "./effects";

/**
 * A marker ring drawn around something in a cutout, the way an editor circles a
 * detail with a felt-tip pen.
 *
 * Coordinates are normalised (0..1) against the image box, so the ring survives
 * any display width — change the cutout's `width` and the ring still lands.
 *
 * Use this when the thing being circled is baked into a photograph. Text that
 * you set yourself in the DOM can be highlighted from behind instead, which
 * looks cleaner; a ring is what you have once the pixels are fixed.
 */
export const MarkerRing: React.FC<{
  /** Where the ring starts drawing, in frames. */
  startFrame: number;
  /** Centre of the ring, 0..1 of the image box. */
  cx: number;
  cy: number;
  /** Radii, 0..1 of the image box. */
  rx: number;
  ry: number;
  /** Frames to complete the stroke. */
  duration?: number;
  color?: string;
  strokeWidth?: number;
  /** Slight tilt so it looks drawn, not plotted. */
  rotate?: number;
  /** Rendered width of the box, in px. Drives the dash length — see below. */
  width?: number;
  /** Rendered height of the box, in px. */
  height?: number;
}> = ({
  startFrame,
  cx,
  cy,
  rx,
  ry,
  duration = 12,
  color = YELLOW,
  strokeWidth = 5,
  rotate = -3,
  width,
  height,
}) => {
  const frame = useCurrentFrame();
  const p = progress(frame, startFrame, startFrame + duration);

  if (p <= 0) return null;

  // With `non-scaling-stroke` the dash pattern is measured in screen pixels, so
  // `pathLength` normalisation does not apply. A generous constant is safe for a
  // small ring (the stroke just completes early), but on a big ring it is not:
  // dash 420 against a real perimeter of 860 draws only half the ellipse and the
  // ring looks torn. Pass `width`/`height` and the perimeter is computed properly
  // (Ramanujan's approximation) instead of guessed.
  const PERIM = 420;
  const perim =
    width && height
      ? Math.PI * (3 * (rx * width + ry * height) - Math.sqrt(
          (3 * rx * width + ry * height) * (rx * width + 3 * ry * height),
        ))
      : PERIM;

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
      <ellipse
        cx={cx * 100}
        cy={cy * 100}
        rx={rx * 100}
        ry={ry * 100}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
        transform={`rotate(${rotate} ${cx * 100} ${cy * 100})`}
        strokeDasharray={perim}
        strokeDashoffset={perim * (1 - p)}
      />
    </svg>
  );
};
