import React from "react";
import {Img, OffthreadVideo, spring, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import {cutoutLook, contactShadow} from "./effects";
import {arcOffset, breathe, progress, settle, squashStretch, wobble} from "./motion";
import {STAGE_H, STAGE_W} from "./Stage";
import {StickerLabel} from "./Sticker";

/**
 * One element on the stage: a card that arrives from outside the frame, lands in
 * its slot, and stays there.
 *
 * This replaces the pattern of wrapping `PaperCutout` in a hand-written
 * `position:absolute; left:800; top:430` div. Two things were wrong with that:
 *
 * 1. **Positions were px inside a sheet**, so a layout could not be described or
 *    compared — you had to render it to find out where anything was. Slots here
 *    are normalised to the stage, so a shot's layout is a short list of numbers
 *    you can read and argue about.
 *
 * 2. **Elements only travelled ~110 px.** That is a nudge, not an arrival. In the
 *    reference (`sa-frames/a-4.3` → `a-8.4`) cards come from completely outside
 *    the frame. The distance here is derived from the slot, so the element is
 *    guaranteed to start off-frame no matter where it lands or how big it is.
 *
 * The arrival itself is physical: it swings in on an arc, stretches along its
 * direction of travel, squashes on contact, then holds with a slow breath so the
 * frame never freezes.
 */
export type ElementFrom = "left" | "right" | "top" | "bottom" | "fade";

/**
 * What the piece is made of. Motion follows material, not convenience.
 *
 * Before this, every card breathed on the same 52-frame sine and wobbled the same
 * 0.34°, so a halftone photograph and a paper slip had identical body language —
 * the frame moved, but nothing in it behaved like the thing it was (koreksi klien
 * 30-10: "gerak object dan gerak grafik"). Now:
 *
 * - `photo`  — a torn halftone photograph drifts: a slow monotonic push-in, like a
 *              still being eased under a camera. No wobble; print does not ripple.
 * - `figure` — a cut-out of a person sways and breathes, and swings in on the arc.
 * - `type`   — printed matter is dead flat and dead still. Its only motion is the
 *              arrival; that stillness is what makes it read as type.
 * - `other`  — a prop (magnifier, rubber stamp, dictionary) keeps the old idle.
 *
 * `settle` is the same idea applied to the *landing*. A cut-out of a person is a
 * light piece of paper: it skates a few pixels when it is let go. A halftone
 * print is heavy and flat and grips at once. Both come to rest exactly on their
 * slot, because `settle` returns to zero.
 */
export type CardKind = "photo" | "figure" | "type" | "other";

const IDLE: Record<CardKind, {breathe: number; wobble: number; spin: number; drift: number; settle: number}> = {
  photo: {breathe: 0.001, wobble: 0, spin: 0.35, drift: 0.035, settle: 0.0018},
  figure: {breathe: 0.0052, wobble: 0.55, spin: 0.6, drift: 0.012, settle: 0.0085},
  type: {breathe: 0, wobble: 0, spin: 1, drift: 0, settle: 0.0012},
  other: {breathe: 0.0038, wobble: 0.34, spin: 0.8, drift: 0, settle: 0.005},
};

export type ElementPose = {
  /** Local shot frame when this cutout pose replaces the active image. */
  atFrame: number;
  /** Public asset path (e.g. `cards/m04s04/surveyor_pose2.png`). */
  src: string;
};

const SPIN: Record<ElementFrom, number> = {
  left: -4.5,
  right: 4.5,
  top: -2.2,
  bottom: 2.2,
  fade: 0,
};

export const Element: React.FC<{
  /** Still card. Omit when using `video`. */
  src?: string;
  /**
   * A generated clip instead of a still — the hybrid panel.
   *
   * Use it only when the shot's meaning is *photographic motion* that a still
   * cannot imply (a vehicle pulling away, a crowd, weather). Anything whose
   * meaning is in lettering, geography or numbers must never be video: a video
   * model rewrites text and cannot be marked or timed.
   */
  video?: string;
  /** Rendered width in stage px. */
  width: number;
  /** Centre of the card, normalised to the stage. */
  at: [number, number];
  enterFrame: number;
  from?: ElementFrom;
  /** Perpendicular bow of the entrance, px. Negative bows the other way. */
  arc?: number;
  /** Resting tilt, degrees. */
  rotate?: number;
  /** Yellow keyline thickness; 0 for a plain contact shadow. */
  outline?: number;
  /** Role label under the card — the word that names this surface. */
  caption?: string;
  /** Frames after landing before the caption pops. */
  captionDelay?: number;
  /** Absolute local frame for the caption, overriding `captionDelay`. */
  captionAt?: number;
  captionFontSize?: number;
  /** Drawn over the card, in normalised coordinates of the card box. */
  overlay?: React.ReactNode;
  /** Phase offset so a group does not breathe or wobble in unison. */
  phase?: number;
  /** Quantise the arrival to this many frames for a stop-motion feel. */
  stepped?: number;
  /** Frames the arrival takes. Shorter = a whip, longer = carried in. */
  travel?: number;
  /** Extra px of run-up past the frame edge. */
  runUp?: number;
  /**
   * Local frames of a quick scale spike — one per stressed word. This is the
   * mark to use when the element *is* the thing being named: a signboard that
   * arrives exactly on its own name does not also need a ring drawn on it.
   */
  punch?: number | number[];
  punchAmount?: number;
  /**
   * Stop-motion cutout replacement poses (`[{atFrame, src}]`), curated post-still.
   * When `frame >= atFrame`, the cutout swaps to `p.src` with a tactile paper snap.
   */
  poses?: ElementPose[];
  /** Material of the piece — decides how it behaves once it has landed. */
  kind?: CardKind;
  /**
   * Height/width of the card, used only to work out how far above or below the
   * frame it must start. The real height comes from the image; this only has to
   * be close enough that no corner is left peeking in on frame 0.
   */
  aspect?: number;
}> = ({
  src,
  video,
  width,
  at,
  enterFrame,
  from = "left",
  arc = 0,
  rotate = 0,
  outline = 6,
  caption,
  captionDelay = 8,
  captionAt,
  captionFontSize = 34,
  overlay,
  phase = 0,
  stepped,
  travel = 13,
  runUp = 80,
  aspect = 0.72,
  punch,
  punchAmount = 0.05,
  poses,
  kind = "other",
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const f = frame - enterFrame;

  const raw = progress(f, 0, travel);
  const drag = stepped ? Math.floor(raw * (travel / stepped)) / (travel / stepped) : raw;

  const stamp = spring({
    frame: f - travel + 4,
    fps,
    config: {damping: 17, stiffness: 220, mass: 0.45},
  });

  // Distance needed for the card to be entirely outside the stage at t=0.
  // Derived from the slot and the card width, so a card that lands near an edge
  // still gets a real run-up instead of a 110 px nudge.
  const cx = at[0] * STAGE_W;
  const cy = at[1] * STAGE_H;
  const halfH = (width * aspect) / 2;

  const dx =
    from === "left"
      ? -(cx + width / 2 + runUp)
      : from === "right"
        ? STAGE_W - cx + width / 2 + runUp
        : 0;
  const dy =
    from === "top"
      ? -(cy + halfH + runUp)
      : from === "bottom"
        ? STAGE_H - cy + halfH + runUp
        : 0;

  // `fade` has no travel; everything else starts outside the frame.
  const travelling = from === "fade" ? 0 : 1 - drag;
  const tx = travelling * (from === "fade" ? 0 : dx);
  const ty = travelling * (from === "fade" ? 0 : dy) - arcOffset(drag, arc);

  // The skate after release. It is applied *against* the direction of travel, so
  // it carries the piece past its slot rather than short of it, and it decays to
  // zero, so the resting position is still the measured slot to the pixel.
  const skate = f > travel ? settle(f - travel, kind === "figure" ? 8 : 4) : 0;
  const over = skate * IDLE[kind].settle;
  const ox = from === "fade" ? 0 : -dx * over;
  const oy = from === "fade" ? 0 : -dy * over;

  // stretch along the axis of travel while moving, squash on contact
  const moving = from === "fade" ? 0 : drag * (1 - drag) * 4;
  const {sx, sy} = squashStretch(moving, 0, 0.05);

  const base = from === "fade" ? 0.9 + 0.1 * drag : 0.94 + 0.06 * stamp;
  const idle = f > travel ? breathe(frame, IDLE[kind].breathe, 52, phase) : 1;
  const spin =
    rotate +
    travelling * SPIN[from] * IDLE[kind].spin +
    over * SPIN[from] * 9 +
    (f > travel ? wobble(frame, IDLE[kind].wobble, 96, phase) : 0);

  // A photograph keeps being pushed in for as long as it is on screen: monotonic,
  // smoothstepped, never oscillating — the difference between a still under a
  // camera and a sticker on a board.
  const driftT = Math.min(1, Math.max(0, (f - travel) / 150));
  const drift = 1 + IDLE[kind].drift * driftT * driftT * (3 - 2 * driftT);
  const creepY = kind === "photo" ? -3 * driftT : 0;

  const opacity = from === "fade" ? drag : Math.min(1, drag * 3);

  // one short spike per stressed word + automatic tactile snap on pose swap
  const basePunches = punch === undefined ? [] : Array.isArray(punch) ? punch : [punch];
  const posePunches = poses ? poses.map((p) => p.atFrame) : [];
  const punches = [...basePunches, ...posePunches];
  const hit = punches.reduce((acc, atFrame) => {
    const since = frame - atFrame;
    if (since < 0) return acc;
    return acc + Math.exp(-since / 5) * Math.cos(since * 0.55) * punchAmount;
  }, 0);

  let activeSrc = src;
  if (poses && poses.length > 0) {
    for (const p of poses) {
      if (frame >= p.atFrame) {
        activeSrc = p.src;
      }
    }
  }

  return (
    <div
      style={{
        position: "absolute",
        left: `${at[0] * 100}%`,
        top: `${at[1] * 100}%`,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: caption ? 16 : 0,
        transform: "translate(-50%, -50%)",
        opacity,
      }}
    >
      <div
        style={{
          position: "relative",
          width,
          transform: `translate(${tx + ox}px, ${ty + oy + creepY}px) rotate(${spin}deg) scale(${(base * sx * idle * drift) + hit}, ${(base * sy * idle * drift) + hit})`,
        }}
      >
        {video ? (
          <OffthreadVideo
            src={staticFile(video)}
            muted
            style={{width: "100%", display: "block", objectFit: "cover"}}
          />
        ) : (
          <Img
            src={staticFile(activeSrc!)}
            style={{
              width: "100%",
              display: "block",
              filter: outline > 0 ? cutoutLook(outline) : contactShadow(10, 18, 0.28),
            }}
          />
        )}
        {overlay ? <div style={{position: "absolute", inset: 0}}>{overlay}</div> : null}
      </div>

      {caption ? (
        <StickerLabel
          enterFrame={captionAt ?? enterFrame + travel + captionDelay}
          rotate={rotate * -0.35}
          fontSize={captionFontSize}
          phase={phase + 1.3}
        >
          {caption}
        </StickerLabel>
      ) : null}
    </div>
  );
};
