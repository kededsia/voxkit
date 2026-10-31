import React from "react";
import {Img, spring, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import {breathe, progress, wobble} from "./motion";
import {PAGE_ASPECT} from "./PaperPage";

/**
 * A frame that arrives in two halves and closes at the seam.
 *
 * Use it when a shot was authored as a **layout** — two photos with a gap, arrows
 * between them — instead of as a single picture. Moving that as one sheet reads
 * as a slide no matter how much you bow the entrance, because nothing inside the
 * frame ever moves relative to anything else. Splitting it at the gap and letting
 * the halves travel in from opposite sides gives the frame an inside.
 *
 * The two assets come from `torn_split.py`: both are **full canvas with
 * complementary alpha**, so they sit at exactly the same position and reassemble
 * into the original image with no seam. The tear is what makes the join read as
 * paper rather than as a wipe.
 *
 * The tear closes, then the sheet holds with a slow push-in. `children` are drawn
 * over the assembled sheet in normalised coordinates — that is where a ring or a
 * label goes, so it does not travel with either half.
 */
export const SplitSheet: React.FC<{
  /** Full-canvas RGBA, left of the tear. */
  left: string;
  /** Full-canvas RGBA, right of the tear. */
  right: string;
  width?: number;
  totalFrames: number;
  enterFrame?: number;
  /** How far out each half starts, as a multiple of `width`. */
  spread?: number;
  /** Frames between the two halves starting their run. */
  stagger?: number;
  /** Resting tilt, degrees. */
  rotate?: number;
  /** Total push-in after the seam closes. */
  drift?: number;
  children?: React.ReactNode;
}> = ({
  left,
  right,
  width = 1580,
  totalFrames,
  enterFrame = 0,
  spread = 0.62,
  stagger = 4,
  rotate = -1.1,
  drift = 0.05,
  children,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const height = width * PAGE_ASPECT;

  const cfg = {damping: 19, stiffness: 130, mass: 0.85};
  const pl = spring({frame: frame - enterFrame, fps, config: cfg});
  const pr = spring({frame: frame - enterFrame - stagger, fps, config: cfg});

  // once both halves are home, the sheet behaves like any other page
  const closed = progress(frame, enterFrame + 16, enterFrame + 34);
  const push = 1 + drift * progress(frame, 0, totalFrames, (x) => x);
  const idle = breathe(frame, 0.0026, 78, rotate);

  const opacity = progress(frame, enterFrame, enterFrame + 4);

  const half = (src: string, p: number, dir: -1 | 1, tilt: number) => (
    <div
      style={{
        position: "absolute",
        inset: 0,
        transform: [
          `translateX(${(1 - p) * dir * spread * width}px)`,
          `translateY(${(1 - p) * 26}px)`,
          `rotate(${(1 - p) * tilt}deg)`,
        ].join(" "),
        filter: "drop-shadow(0 14px 26px rgba(58,40,12,0.30))",
      }}
    >
      <Img src={staticFile(src)} style={{width: "100%", height: "100%", display: "block"}} />
    </div>
  );

  return (
    <div
      style={{
        position: "absolute",
        left: "50%",
        top: "50%",
        width,
        height,
        opacity,
        transform: `translate(-50%, -50%) rotate(${rotate + wobble(frame, 0.24, 96, rotate)}deg) scale(${push * idle})`,
      }}
    >
      {half(left, pl, -1, -5.5)}
      {half(right, pr, 1, 5.5)}

      <div style={{position: "absolute", inset: 0, opacity: closed}}>{children}</div>
    </div>
  );
};
