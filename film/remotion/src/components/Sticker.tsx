import React from "react";
import {Img, spring, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import {contactShadow, cutoutLook, YELLOW} from "./effects";
import {breathe, progress, squashStretch, wobble} from "./motion";

/**
 * A cutout presented as a die-cut sticker: a margin of white vinyl around the
 * artwork, then the yellow keyline, then a soft shadow.
 *
 * **The white margin must already be baked into the asset** — run
 * `scripts/sticker_border.py` on the cutout first. Building it from stacked
 * drop-shadow filters at render time costs ~17 raster passes per frame and was
 * measured at **213 seconds per frame**; baked into the PNG it costs nothing.
 * That is the general rule here: if an effect never changes over time, it
 * belongs in the asset, not in the render.
 *
 * Entrance is deliberately physical: it drops in, over-stretches, squashes on
 * landing, then settles into a slow wobble.
 */
export const Sticker: React.FC<{
  /** A cutout that already carries its white margin. */
  src: string;
  width: number;
  enterFrame: number;
  /** Degrees of resting tilt. */
  rotate?: number;
  /** Yellow keyline thickness; 0 disables it. */
  keyline?: number;
  /** Where it falls in from, in px. */
  dropFrom?: number;
  /** Phase offset so a group does not wobble in unison. */
  phase?: number;
  style?: React.CSSProperties;
}> = ({src, width, enterFrame, rotate = -2, keyline = 5, dropFrom = 160, phase = 0, style}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const f = frame - enterFrame;

  const fall = spring({
    frame: f,
    fps,
    config: {damping: 12, stiffness: 160, mass: 0.7},
  });

  // peak speed around the middle of the fall, used for stretch
  const speed = f < 0 ? 0 : Math.max(0, 1 - Math.abs(fall - 0.55) * 2.2);
  const landed = f > 0 ? Math.max(0, 1 - f / 8) : 0;
  const {sx, sy} = squashStretch(speed, landed, 0.055);

  const idle = breathe(frame, 0.005, 52, phase);
  const tilt = rotate + wobble(frame, 0.7, 64, phase);

  const opacity = progress(frame, enterFrame, enterFrame + 4);

  return (
    <div
      style={{
        position: "relative",
        width,
        opacity,
        transform: `translateY(${(1 - fall) * -dropFrom}px) rotate(${tilt}deg) scale(${sx * idle}, ${sy * idle})`,
        filter: keyline > 0 ? cutoutLook(keyline) : contactShadow(14, 22, 0.32),
        ...style,
      }}
    >
      <Img src={staticFile(src)} style={{width: "100%", display: "block"}} />
    </div>
  );
};

/**
 * A sticker built from text instead of an image — for a label that must be
 * editable without regenerating artwork.
 */
export const StickerLabel: React.FC<{
  children: React.ReactNode;
  enterFrame: number;
  rotate?: number;
  background?: string;
  color?: string;
  fontSize?: number;
  phase?: number;
}> = ({children, enterFrame, rotate = -1.5, background = YELLOW, color = "#1A1A1A", fontSize = 30, phase = 0}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const f = frame - enterFrame;

  const pop = spring({
    frame: f,
    fps,
    config: {damping: 13, stiffness: 240, mass: 0.4},
  });

  if (f < 0) return null;

  return (
    <div
      style={{
        display: "inline-block",
        background,
        color,
        fontFamily: "'Segoe Print', 'Comic Sans MS', cursive",
        fontWeight: 700,
        fontSize,
        letterSpacing: 0.5,
        padding: "9px 20px 11px",
        whiteSpace: "nowrap",
        transform: `rotate(${rotate + wobble(frame, 0.5, 70, phase)}deg) scale(${0.7 + 0.3 * pop})`,
        filter: "drop-shadow(3px 4px 0 rgba(0,0,0,0.18))",
      }}
    >
      {children}
    </div>
  );
};
