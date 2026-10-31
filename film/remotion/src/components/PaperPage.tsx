import React from "react";
import {Img, OffthreadVideo, spring, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import {arcOffset, breathe, progress, squashStretch, wobble} from "./motion";
import {PAPER} from "./effects";
import {Pin} from "./Pin";

/**
 * A whole frame presented as one printed sheet handled on a desk.
 *
 * This is the sibling of `PaperCutout`: that one moves a single element across a
 * page, this one moves the page itself. Use it when a shot already exists as a
 * finished still (a collage, a map, a photo spread) and you need it to behave
 * like an object instead of a slide.
 *
 * The entrance bows in, stretches, squashes on landing and gets pinned. While it
 * holds it pushes in very slowly so the frame never freezes. It leaves by being
 * swiped off the bottom of the desk, so two consecutive pages hand over instead
 * of cutting.
 */

export type PageFrom = "left" | "right" | "top" | "bottom" | "fade";

const TRAVEL: Record<PageFrom, {dx: number; dy: number; spin: number}> = {
  left: {dx: -460, dy: 40, spin: -2.6},
  right: {dx: 460, dy: 40, spin: 2.6},
  top: {dx: 0, dy: -300, spin: -1.8},
  bottom: {dx: 0, dy: 300, spin: 1.8},
  fade: {dx: 0, dy: 36, spin: 0},
};

/** Stills are generated at 1376x768, so every page keeps that aspect. */
export const PAGE_ASPECT = 768 / 1376;

export const PaperPage: React.FC<{
  /** Printed still for the sheet. Omit for a blank sheet (a scene drawn inside). */
  src?: string;
  /**
   * A generated clip instead of a still — this is the hybrid panel.
   *
   * Use it for the one part of a shot whose meaning is *photographic motion*:
   * a vehicle pulling away, a crowd, weather, a face turning. Paper cannot fake
   * that, and a video model cannot be trusted with the lettering — so the clip
   * gets framed as one panel on the page and everything that must stay exact
   * (names, numbers, arrows, marks) is drawn around it in Remotion.
   */
  video?: string;
  /** Rendered width in px. Height follows the 16:9-ish still aspect. */
  width?: number;
  /** Length of the shot, in local frames — drives the push-in and the exit. */
  totalFrames: number;
  /** Local frame the sheet lands on. Negative = already on screen at cut. */
  enterFrame?: number;
  from?: PageFrom;
  /** Resting tilt, degrees. */
  rotate?: number;
  /** Perpendicular bow of the entrance, px. */
  arc?: number;
  /** Total push-in over the shot, as a scale delta (0.04 = 4%). */
  drift?: number;
  /** Local frames of quick scale punches — one per stressed word. */
  punch?: number | number[];
  punchAmount?: number;
  /** Push pin through the top-left corner. */
  pin?: boolean;
  /**
   * Swipe the sheet off the bottom at the end of the shot. Off by default: a
   * sheet that leaves before the next one lands exposes the bare desk for the
   * length of the narration's breath, which reads as missing footage. Left on
   * the page, the next sheet simply lands on top of it.
   */
  exit?: boolean;
  /** Drawn over the sheet, in normalised 0..1 coordinates of the image box. */
  children?: React.ReactNode;
}> = ({
  src,
  video,
  width = 1580,
  totalFrames,
  enterFrame = 0,
  from = "left",
  rotate = -1.4,
  arc = 0,
  drift = 0.045,
  punch,
  punchAmount = 0.035,
  pin = true,
  exit = false,
  children,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const f = frame - enterFrame;

  const raw = progress(f, 0, 11);
  const travel = from === "fade" ? 0 : 1 - raw;
  const t = TRAVEL[from];

  const land = spring({
    frame: f - 8,
    fps,
    config: {damping: 16, stiffness: 190, mass: 0.6},
  });

  const {sx, sy} = squashStretch(travel * raw * 4, 0, 0.045);
  const base = from === "fade" ? 0.94 + 0.06 * raw : 0.965 + 0.035 * land;

  // slow push-in for the whole hold — the frame must never be fully static
  const push = progress(frame, 0, totalFrames, (x) => x);
  const pushScale = 1 + drift * push;
  const idle = breathe(frame, 0.0028, 74, rotate);

  // one short spike per stressed word
  const punches = punch === undefined ? [] : Array.isArray(punch) ? punch : [punch];
  const hit = punches.reduce((acc, at) => {
    const since = frame - at;
    if (since < 0) return acc;
    return acc + Math.exp(-since / 5) * Math.cos(since * 0.55) * punchAmount;
  }, 0);

  // optional swipe off the desk over the last 9 frames
  const out = exit ? progress(frame, totalFrames - 9, totalFrames, (x) => x * x) : 0;

  const opacity = from === "fade" ? raw : Math.min(1, raw * 2.4);

  return (
    <div
      style={{
        position: "absolute",
        left: "50%",
        top: "50%",
        width,
        height: width * PAGE_ASPECT,
        transform: [
          "translate(-50%, -50%)",
          `translate(${travel * t.dx}px, ${travel * t.dy - arcOffset(raw, arc) + out * 260}px)`,
          `rotate(${rotate + travel * t.spin + out * 4.5 + wobble(frame, 0.28, 88, rotate)}deg)`,
          `scale(${(base * sx * pushScale + hit) * (1 - out * 0.06)}, ${(base * sy * pushScale + hit) * (1 - out * 0.06)})`,
        ].join(" "),
        opacity: opacity * (1 - out),
        boxShadow: "0 30px 70px rgba(58,40,12,0.38), 0 3px 0 rgba(255,255,255,0.45)",
      }}
    >
      {video ? (
        <OffthreadVideo
          src={staticFile(video)}
          muted
          style={{width: "100%", height: "100%", display: "block", objectFit: "cover"}}
        />
      ) : src ? (
        <Img
          src={staticFile(src)}
          style={{width: "100%", height: "100%", display: "block", objectFit: "cover"}}
        />
      ) : (
        <div style={{width: "100%", height: "100%", background: PAPER}} />
      )}

      {children ? <div style={{position: "absolute", inset: 0}}>{children}</div> : null}

      {pin ? (
        <Pin
          x={34}
          y={30}
          startFrame={enterFrame + 15}
          size={54}
          rotate={-12}
          dropFrom={150}
        />
      ) : null}
    </div>
  );
};

/**
 * Convert a narration time to a shot-local frame. Every accent in a timeline is
 * anchored to a spoken word, so this is the only arithmetic worth naming.
 *
 *   const F = clock(33.14);   // shot 06 starts at 33.14 s
 *   <MarkerRing startFrame={F(40.5)} … />
 */
export const clock =
  (shotStart: number, fps = 30) =>
  (seconds: number): number =>
    Math.round((seconds - shotStart) * fps);
