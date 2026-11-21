import React from "react";
import {Easing, interpolate, useCurrentFrame} from "remotion";
import {STAGE_H, STAGE_W} from "./Stage";

/**
 * **Stamp** — a word pressed onto the page with a rubber stamp.
 *
 * The client, on the presenter's hand: *"write text yg kaku dan kecil itu kadang
 * harus di rubah misal dengan stamp style"*. A seven-letter word written by a pen
 * at 26 px is stiff and small; the same word stamped is an *object* on the page,
 * with weight, a mis-registered second impression and ink that has bitten into the
 * paper. The film already has rubber stamps in it — m03's `petugas_stempel`
 * presses one — so this is the same grammar, not a new one.
 *
 * Three things make it read as a stamp rather than as a font:
 *
 *   - **the press.** The type arrives 25 % too large and too light, is pushed down
 *     in six frames with a squash, and rebounds. A stamp is an impact, not a fade.
 *   - **the mis-registration.** A second impression a pixel and a half off, at a
 *     quarter of the opacity. Every real stamp double-prints slightly, and the
 *     doubled edge is the tell.
 *   - **the bitten edge.** `feTurbulence` + `feDisplacementMap` roughen the glyph
 *     outline by about a pixel, and the displacement *settles* over the first few
 *     frames as the ink soaks in.
 *
 * The type is set to the box exactly (`textLength` + `spacingAndGlyphs`), so a
 * stamp can never overflow its slot — which is the fault that makes a written note
 * at this size look cramped in the first place.
 */

const INK_FONT =
  '"Impact", "Haettenschweiler", "Arial Narrow", "Franklin Gothic Medium", "Arial Black", sans-serif';

export const Stamp: React.FC<{
  text: string;
  /** Local frame the stamp comes down. */
  at: number;
  /** Frames the press takes. Short — a stamp is an impact. */
  duration?: number;
  color?: string;
  /** Box in normalised stage coords. */
  x: number;
  y: number;
  w: number;
  h: number;
  rotate?: number;
  seed?: number;
  z?: number;
}> = ({text, at, duration = 10, color = "crimson", x, y, w, h, rotate = 0, seed = 7, z = 99}) => {
  const frame = useCurrentFrame();
  const t = frame - at;
  if (t < 0 || !text.trim()) return null;

  const pxW = Math.max(8, w * STAGE_W);
  const pxH = Math.max(8, h * STAGE_H);
  // A viewBox whose height is 100 units and whose width keeps the box's aspect,
  // so the type is never stretched by `preserveAspectRatio`.
  const vbW = (pxW / pxH) * 100;

  const press = interpolate(t, [0, 3, 6, 9], [1.26, 1.02, 0.985, 1], {
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const squash = interpolate(t, [0, 3, 6, 9], [1, 0.955, 1.005, 1], {
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const alpha = interpolate(t, [0, 2, duration], [0, 0.92, 0.88], {
    extrapolateRight: "clamp",
  });
  // The ink bites in: the edge is roughest at contact and settles.
  const bite = interpolate(t, [0, 2, 10], [2.6, 1.5, 0.9], {extrapolateRight: "clamp"});
  const tilt = rotate + ((seed % 7) - 3) * 0.35;

  const uid = `st${seed}`;
  const size = 64;
  const line = Math.min(vbW * 0.9, size * 0.98 * Math.max(1, text.length) * 0.52);

  return (
    <div
      style={{
        position: "absolute",
        left: `${x * 100}%`,
        top: `${y * 100}%`,
        width: `${w * 100}%`,
        height: `${h * 100}%`,
        transform: `rotate(${tilt}deg) scale(${press}, ${press * squash})`,
        transformOrigin: "50% 55%",
        mixBlendMode: "multiply",
        zIndex: z,
      }}
    >
      <svg viewBox={`0 0 ${vbW} 100`} width="100%" height="100%"
           style={{overflow: "visible"}}>
        <defs>
          <filter id={uid} x="-20%" y="-40%" width="140%" height="180%">
            <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2"
                          seed={seed} result="n" />
            <feDisplacementMap in="SourceGraphic" in2="n" scale={bite}
                               xChannelSelector="R" yChannelSelector="G" />
          </filter>
        </defs>
        <g filter={`url(#${uid})`} opacity={alpha}>
          {/* the mis-registered second impression */}
          <text x={vbW / 2 + 0.9} y={70} textAnchor="middle"
                fontFamily={INK_FONT} fontSize={size} letterSpacing={1.2}
                textLength={line} lengthAdjust="spacingAndGlyphs"
                fill={color} opacity={0.22}>
            {text.toUpperCase()}
          </text>
          <text x={vbW / 2} y={70} textAnchor="middle"
                fontFamily={INK_FONT} fontSize={size} letterSpacing={1.2}
                textLength={line} lengthAdjust="spacingAndGlyphs"
                fill={color}>
            {text.toUpperCase()}
          </text>
        </g>
      </svg>
    </div>
  );
};
