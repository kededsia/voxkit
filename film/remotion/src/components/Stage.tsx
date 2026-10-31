import React from "react";
import {staticFile, useCurrentFrame} from "remotion";
import {Camera, CameraValue} from "./Camera";
import {progress} from "./motion";

/**
 * The stage: one sheet of paper filling the whole frame, and nothing else.
 *
 * This is the correction of a real mistake. `PaperPage` presented a whole shot as
 * a sheet pinned on a desk — which meant every shot had *two* layers of paper
 * (the desk, then the sheet) and a white margin between the viewer and the
 * content. The reference samples in `test-audio/sa-frames` and `sb-frames` have
 * exactly one paper layer, and it is the frame itself. Elements sit directly on
 * it, not on a document floating above it.
 *
 * Consequences that matter:
 *   - the paper is edge-to-edge, so there is no margin, no pin, no drop shadow
 *     around a rectangle — the frame is the page;
 *   - the camera moves over the paper, so a push-in reveals more paper rather
 *     than enlarging a document;
 *   - anything placed inside is an independent object, so it can arrive on its
 *     own, at its own time, and be marked on its own.
 *
 * A shot is therefore: one `PaperStage` + 3–5 `Element`s + marks timed to words.
 */
export const STAGE_W = 1920;
export const STAGE_H = 1080;

type Slotish = {x: number; y: number; w: number; h: number};

/**
 * The largest zoom at which every element is still wholly inside the frame.
 *
 * This exists because of a defect that kept coming back: the stills are composed
 * by an image model that likes to fill the frame edge to edge, so a camera at
 * 1.05 slices the outermost card in half. Six shots had that fault at once, and
 * hand-lowering each zoom was patchwork — the next shot would do it again.
 *
 * The envelope is not a taste question, it is arithmetic. An element whose slot
 * reaches `reach` (normalised distance from the focus point to its far edge) is
 * still visible while `reach * zoom <= 0.5 - margin`. So the camera asks the
 * layout what it is allowed to do, and cannot ask for more.
 *
 * With a pan, pass the focus point you are panning to: panning away from an
 * element makes the far side reach further, and the allowed zoom drops
 * accordingly. A camera that would have to zoom out to pan simply zooms out.
 */
export const fitZoomAt = (
  elements: Record<string, Slotish>,
  x = 0.5,
  y = 0.5,
  margin = 0.03,
) => {
  let reach = 0;
  for (const e of Object.values(elements)) {
    reach = Math.max(
      reach,
      Math.abs(e.x - x) + e.w / 2,
      Math.abs(e.y - y) + e.h / 2,
    );
  }
  return reach === 0 ? 3 : (0.5 - margin) / reach;
};

/** `fitZoomAt` from the centre — the widest useful zoom for a still. */
export const fitZoom = (elements: Record<string, Slotish>, margin = 0.03) =>
  fitZoomAt(elements, 0.5, 0.5, margin);

/**
 * The plate image, in the one form that cannot letterbox.
 *
 * A plain `<img>` with `width`/`height` set to the frame and `object-fit` doing
 * the conforming. Deliberately not Remotion's `<Img>`: that component measures
 * the asset and lets its intrinsic aspect ratio drive layout, which is correct
 * for an element placed in a slot and wrong for a background that must fill a
 * frame. See the full-bleed note at the call site.
 */
const PlateImg: React.FC<{
  src: string;
  fullBleed: boolean;
  style: React.CSSProperties;
}> = ({src, fullBleed, style}) => (
  <img
    src={src}
    alt=""
    style={{
      ...style,
      // `display:block` matters: an inline `<img>` sits on a text baseline inside
      // its absolute box and inherits a few px of line-box slack, which is enough
      // to have it overflow one edge and expose the stage on the other.
      display: "block",
      objectFit: fullBleed ? "cover" : (style.objectFit as React.CSSProperties["objectFit"]),
      // A full-bleed plate must be pinned to the frame on all four sides. An
      // explicit width/height pair *plus* right/bottom guards against a caller
      // passing only left/top, which leaves the right and bottom edges free and
      // is exactly how 87 px of bare stage appeared down the left of s01.
      right: fullBleed ? 0 : style.right,
      bottom: fullBleed ? 0 : style.bottom,
    }}
  />
);

/**
 * Paper is drawn oversized so the camera can push in without ever reaching its
 * edge, and so a tilt or drift can never expose a corner. 1.55 covers a zoom of
 * about 1.5 with the focus point anywhere in the middle half of the frame.
 */
const OVERSCAN = 1.55;

export const PaperStage: React.FC<{
  /** Camera resolved by `useCamera`. Omit for a locked-off stage. */
  camera?: CameraValue;
  /**
   * The shot's own clean plate — the still with its objects lifted off, extended
   * by `scripts/make_plate.py`.
   *
   * A Vox still is a *designed* background: colour fields, torn edges, halftone,
   * tape. Painting the shared cream sheet instead threw all of that away, so a
   * film rebuilt as collages still rendered as cutouts on paper. When `plate` is
   * given it wins, and it is drawn at exactly overscan size so the original
   * occupies stage coordinates 0…1920 × 0…1080 and stays registered to the
   * slots in `layout.json`.
   */
  plate?: string;
  /** Paper texture. Defaults to the shared crumpled-grid sheet. */
  paper?: string;
  /**
   * Extra scale of the paper across the whole shot (0.03 = 3%). The paper keeps
   * drifting even when the camera holds, so a held frame is never frozen.
   */
  drift?: number;
  /** Length of the shot in local frames — drives `drift`. */
  totalFrames?: number;
  /** Resting tilt of the paper, degrees. Keeps its edges off the frame edges. */
  rotate?: number;
  /** Phase for the paper's own breath, so two shots do not pulse identically. */
  phase?: number;
  /**
   * A shot whose art runs to the frame edge must not be overscanned.
   *
   * `make_plate.py` can extend a plate whose detail stops short of the border:
   * a flat colour field is reproduced exactly, texture continues. But when a
   * collage is full-bleed — s01's map is the whole frame, `box 0,0 → 1,1` —
   * there is nothing to extend *from*. Reflecting it mirrored the torn-paper
   * border into an X across half the screen; repeating it combed that border
   * into stripes. Neither is a fix; both come from asking the wrong question.
   *
   * So: pass this and the plate is drawn at stage size, and the camera must be
   * told to stay at or inside `zoom 1`. `zoom 0.96` is *wider than the frame* —
   * it is precisely what opened s01 on the smear.
   */
  fullBleed?: boolean;
  children?: React.ReactNode;
}> = ({
  camera,
  plate,
  fullBleed = false,
  paper = "bg.jpg",
  drift = 0.03,
  totalFrames = 300,
  rotate = 0,
  phase = 0,
  children,
}) => {
  const frame = useCurrentFrame();
  const OVER = fullBleed ? 1 : OVERSCAN;

  const push = progress(frame, 0, totalFrames, (x) => x);
  const breathe = 0.004 * Math.sin((frame / 118) * Math.PI * 2 + phase);
  // A full-bleed plate has no margin, so it cannot lean: any rotation exposes a
  // corner. The breath is dropped for the same reason — it scales *out* of frame.
  const spin = fullBleed ? 0 : rotate + 0.25 * Math.sin((frame / 210) * Math.PI * 2 + phase);

  /**
   * A plate must not drift. `layout.json` places every card against the plate's
   * own coordinates, so scaling the plate by 3% slides the colour boundary out
   * from under a card that sits half on it. A texture can drift because it has
   * no landmarks; a designed background cannot. The camera supplies the motion
   * instead, and a 0.4% breath is small enough to read as life, not as slip.
   */
  const scale = fullBleed ? 1 : plate ? 1 + breathe : 1 + drift * push + breathe;

  /**
   * The surface is the camera's world, and it is deliberately **not clipped**.
   *
   * This was the bug that put a flat cream band down the side of every shot whose
   * camera panned: `overflow: hidden` sat on the same div the camera transform was
   * applied to, so the overscanned paper was clipped back to exactly 1920 × 1080
   * *before* the camera moved it. Pan 330 px right and the left 330 px of the
   * frame had nothing on it at all. A zoom-only move hid the fault, which is why
   * it survived so long.
   *
   * Clipping belongs one level out, on a box that never moves. Everything inside
   * this div lives in stage coordinates: 0…1920, 0…1080, forever.
   *
   * The resting tilt belongs here too, not on the paper: a tilt is a property of
   * the camera looking at the collage, so the cards must lean with the background
   * they were pasted onto. Rotating only the paper slid every card against its
   * own shadow.
   */
  const surface = (
    <div
      style={{
        position: "absolute",
        inset: 0,
        transform: `rotate(${spin}deg)`,
        transformOrigin: "50% 50%",
      }}
    >
      {/*
        A full-bleed plate must be a plain `<img>`, not Remotion's `<Img>`.

        `<Img>` is a *measured* image: it reads the file's intrinsic size and
        reports it to the parent so the composition can lay out around it. That
        measurement is what broke s01 — the plate rendered with its own aspect
        ratio letterboxed inside the scaled transform, leaving 87 px of bare
        stage down the left and 74 px along the bottom, a cream L that looked
        exactly like a bad plate resample and was neither. A full-bleed plate
        conforms to the frame and has no intrinsic size to report.
      */}
      <PlateImg
        src={staticFile(plate ?? paper)}
        fullBleed={fullBleed}
        style={{
          position: "absolute",
          left: -((OVER - 1) / 2) * STAGE_W,
          top: -((OVER - 1) / 2) * STAGE_H,
          width: OVER * STAGE_W,
          height: OVER * STAGE_H,
          // A plate is already extended to overscan, so it must be drawn 1:1 —
          // `cover` would rescale it and break registration with the slots.
          //
          // A **full-bleed** plate is the exception, and it must be `cover`: its
          // art runs to its own border, so any sliver the aspect ratio leaves
          // uncovered is bare stage, and it showed as a cream L down the left and
          // bottom of s01. `cover` crops instead, which costs a few pixels of
          // collage and no hole.
          objectFit: fullBleed ? "cover" : plate ? "fill" : "cover",
          transform: `scale(${scale})`,
          transformOrigin: "50% 50%",
        }}
      />
      {children}
    </div>
  );

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        overflow: "hidden",
        background: "#EFE7D6",
      }}
    >
      {camera ? (
        <Camera
          value={
            /*
              A full-bleed plate cannot be scaled below 1.0, ever.

              Shot files write zoom as a *multiple of fitZoom* - zoom(els, k) -
              and fitZoom is a containment ceiling that is frequently under 1.0
              (s01's is 0.94, because its one element is the whole frame and the
              function reserves a 3 % margin). At k = 1.0 the camera therefore
              pulled *out* to 0.94, shrinking a frame-filling plate by 6 % and
              letting the stage show through as an L of #EFE7D6 down two edges.
              It looked like a bad plate resample; it was arithmetic.

              On a full-bleed shot the art **is** the frame, so 1.0 is the floor
              and the move happens above it. The shot file already keeps its keys
              at or above 1.0 in *multiple* terms for the same reason; this is the
              guarantee at the one place that cannot be forgotten.
            */
            fullBleed
              ? {
                  ...camera,
                  zoom: Math.max(
                    camera.zoom,
                    0.5 / Math.max(0.001, 0.5 - Math.max(Math.abs(camera.x - 0.5), Math.abs(camera.y - 0.5)))
                  ),
                }
              : camera
          }
          width={STAGE_W}
          height={STAGE_H}
        >
          {surface}
        </Camera>
      ) : (
        surface
      )}
      {/*
        The vignette is a lens, not a surface — it stays put while the camera
        moves underneath it, so a pan never drags the darkening across the frame.
      */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",
          boxShadow: "inset 0 0 300px rgba(60,40,10,0.22)",
        }}
      />
    </div>
  );
};
