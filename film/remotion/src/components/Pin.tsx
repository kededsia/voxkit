import React from "react";
import {spring, useCurrentFrame, useVideoConfig} from "remotion";
import {progress} from "./motion";

/**
 * A drawing pin that drops onto the page and sticks.
 *
 * Anchored at its tip, so you position the point of contact rather than the
 * graphic: `left/top` is where the pin touches down. Useful for pinning a
 * cutout to a board, or for marking a spot on a map without a full annotation.
 *
 * The fall is a spring; the impact is a quick squash; the settle is a small
 * wobble. Three cheap tricks that stop it reading as a sticker sliding in.
 */
export const Pin: React.FC<{
  /** Where the tip lands, in px from the frame's top-left. */
  x: number;
  y: number;
  startFrame: number;
  color?: string;
  /** Overall size, tip-to-head, in px. */
  size?: number;
  /** How far above the landing point it starts, in px. */
  dropFrom?: number;
  rotate?: number;
}> = ({x, y, startFrame, color = "#D63B2F", size = 56, dropFrom = 120, rotate = -8}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const f = frame - startFrame;

  if (f < 0) return null;

  const fall = spring({
    frame: f,
    fps,
    config: {damping: 11, stiffness: 220, mass: 0.55},
  });

  // squash on contact, easing out over ~6 frames
  const impact = Math.max(0, 1 - f / 6);
  const sx = 1 + 0.22 * impact;
  const sy = 1 - 0.18 * impact;

  // settle wobble, decaying
  const settle = Math.exp(-f / 9) * Math.sin(f * 0.9) * 4;

  const opacity = progress(frame, startFrame, startFrame + 2);

  return (
    <svg
      width={size}
      height={size * 1.4}
      viewBox="0 0 40 56"
      style={{
        position: "absolute",
        left: x - size / 2,
        top: y - size * 1.4,
        overflow: "visible",
        opacity,
        transform: `translateY(${(1 - fall) * -dropFrom}px) rotate(${rotate + settle}deg) scale(${sx}, ${sy})`,
        transformOrigin: "50% 100%",
        filter: "drop-shadow(0 6px 8px rgba(0,0,0,0.35))",
      }}
    >
      <defs>
        <radialGradient id="pinHead" cx="35%" cy="30%" r="75%">
          <stop offset="0%" stopColor="#FF8A7A" />
          <stop offset="55%" stopColor={color} />
          <stop offset="100%" stopColor="#7E1A12" />
        </radialGradient>
      </defs>

      {/* needle */}
      <path d="M 20 34 L 20 55" stroke="#8A8A8A" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M 20 51 L 20 56" stroke="#3A3A3A" strokeWidth="2.4" strokeLinecap="round" />

      {/* collar */}
      <rect x="14" y="26" width="12" height="9" rx="3" fill="#B32E22" />

      {/* head */}
      <circle cx="20" cy="15" r="13" fill="url(#pinHead)" />
      <ellipse cx="15" cy="10" rx="4.5" ry="3.2" fill="#FFFFFF" opacity="0.55" />
    </svg>
  );
};

/**
 * A taut string between two pins, for connecting a label to the thing it names.
 * Draws itself on, so it reads as being pulled rather than faded in.
 */
export const PinString: React.FC<{
  from: {x: number; y: number};
  to: {x: number; y: number};
  startFrame: number;
  duration?: number;
  color?: string;
  sag?: number;
}> = ({from, to, startFrame, duration = 12, color = "#8A6A1E", sag = 26}) => {
  const frame = useCurrentFrame();
  const p = progress(frame, startFrame, startFrame + duration);
  if (p <= 0) return null;

  const mx = (from.x + to.x) / 2;
  const my = (from.y + to.y) / 2 + sag;
  const d = `M ${from.x} ${from.y} Q ${mx} ${my} ${to.x} ${to.y}`;
  // screen-space length, since the path is not scaled by a viewBox here
  const len = Math.hypot(to.x - from.x, to.y - from.y) * 1.3;

  return (
    <svg
      width="100%"
      height="100%"
      style={{position: "absolute", inset: 0, pointerEvents: "none", overflow: "visible"}}
    >
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth={2.2}
        strokeLinecap="round"
        strokeDasharray={len}
        strokeDashoffset={len * (1 - p)}
      />
    </svg>
  );
};
