import React from "react";
import {Img, spring, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import {cutoutLook} from "./effects";
import {arcOffset, breathe, progress, squashStretch} from "./motion";
import {StickerLabel} from "./Sticker";

/**
 * One paper element arriving on the page: slides in, lands with a stamp, its
 * caption pops on a few frames later.
 *
 * The motion is deliberately not a straight line. It bows along `arc` (like it
 * was carried in), stretches while it travels, squashes on contact, then holds
 * with a slow breath so the frame is never fully static.
 */
export type EnterFrom = "left" | "right" | "top" | "bottom" | "fade";

const TRAVEL: Record<EnterFrom, {dx: number; dy: number; spin: number}> = {
  left: {dx: -110, dy: 0, spin: -3},
  right: {dx: 110, dy: 0, spin: 3},
  top: {dx: 0, dy: -90, spin: -1.5},
  bottom: {dx: 0, dy: 90, spin: 1.5},
  fade: {dx: 0, dy: 0, spin: 0},
};

export const PaperCutout: React.FC<{
  src: string;
  width: number;
  enterFrame: number;
  from: EnterFrom;
  /** Resting tilt in degrees. */
  rotate?: number;
  /** Yellow label under the piece. Omit for a panel that carries no caption. */
  caption?: string;
  /** Extra content drawn over the image, in normalised coordinates. */
  overlay?: React.ReactNode;
  /** Frames after landing before the caption pops. */
  captionDelay?: number;
  /** Perpendicular bow of the entrance path, in px. Negative bows the other way. */
  arc?: number;
  /** Outline thickness; 0 for a plain contact shadow only. */
  outline?: number;
  /** Phase offset for the idle breath. */
  phase?: number;
  /** Quantise the slide to this many frames for a stop-motion feel. */
  stepped?: number;
  captionFontSize?: number;
}> = ({
  src,
  width,
  enterFrame,
  from,
  rotate = 0,
  caption,
  overlay,
  captionDelay = 9,
  arc = 0,
  outline = 5,
  phase = 0,
  stepped,
  captionFontSize = 34,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const f = frame - enterFrame;

  const raw = progress(f, 0, 9);
  const drag = stepped ? Math.floor(raw * 9) / 9 : raw;

  const stamp = spring({
    frame: f - 5,
    fps,
    config: {damping: 17, stiffness: 210, mass: 0.45},
  });

  const t = TRAVEL[from];
  const travelling = from === "fade" ? 0 : 1 - drag;

  const translateX = travelling * t.dx;
  const translateY = travelling * t.dy - arcOffset(drag, arc);

  const {sx, sy} = squashStretch(from === "fade" ? 0 : drag * (1 - drag) * 4, 0, 0.05);
  const base = from === "fade" ? 0.92 + 0.08 * drag : 0.93 + 0.07 * stamp;
  const idle = f > 14 ? breathe(frame, 0.0042, 46, phase) : 1;

  const rotation = rotate + travelling * t.spin;
  const opacity = from === "fade" ? drag : Math.min(1, drag * 2.2);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: caption ? 18 : 0,
        transform: "translate(-50%, -50%)",
        opacity,
      }}
    >
      <div
        style={{
          position: "relative",
          width,
          transform: `translate(${translateX}px, ${translateY}px) rotate(${rotation}deg) scale(${base * sx * idle}, ${base * sy * idle})`,
        }}
      >
        <Img
          src={staticFile(src)}
          style={{
            width: "100%",
            display: "block",
            filter: outline > 0 ? cutoutLook(outline) : "drop-shadow(0 10px 18px rgba(0,0,0,0.28))",
          }}
        />
        {overlay ? <div style={{position: "absolute", inset: 0}}>{overlay}</div> : null}
      </div>
      {caption ? (
        <StickerLabel
          enterFrame={enterFrame + captionDelay}
          rotate={rotate * -0.4}
          fontSize={captionFontSize}
          phase={phase + 1.1}
        >
          {caption}
        </StickerLabel>
      ) : null}
    </div>
  );
};
