import React from "react";
import {Img, staticFile, useCurrentFrame} from "remotion";
import {progress} from "./motion";

/**
 * Move a cutout along a route drawn on the page.
 *
 * A map with a dotted line on it says "here is a map". The same map with a
 * vehicle crawling along the dotted line says "you drive from here to there" —
 * which is what a shot like that is usually for. Paper cannot fake photographic
 * motion, but it can do this: a small object travelling a drawn path is exactly
 * how hand-made explainers show a journey.
 *
 * Waypoints are normalised 0..1 against the box, so the route survives any
 * display size. The heading is derived from the tangent; a vehicle that would end
 * up upside-down is mirrored instead of rotated past vertical, so the asset only
 * ever needs to be drawn facing one way.
 */

/**
 * Where a route is at progress `t` (0..1), in the same normalised coordinates the
 * waypoints use. Exported so a camera can follow the same point the vehicle is
 * on — both read this one function, so they cannot drift apart.
 */
export const sampleRoute = (
  waypoints: [number, number][],
  t: number,
): {x: number; y: number; heading: number} => {
  const lens: number[] = [];
  let total = 0;
  for (let i = 1; i < waypoints.length; i++) {
    const d = Math.hypot(
      waypoints[i][0] - waypoints[i - 1][0],
      waypoints[i][1] - waypoints[i - 1][1],
    );
    lens.push(d);
    total += d;
  }

  let target = t * total;
  let idx = 0;
  while (idx < lens.length - 1 && target > lens[idx]) {
    target -= lens[idx];
    idx++;
  }

  const a = waypoints[idx];
  const b = waypoints[Math.min(idx + 1, waypoints.length - 1)];
  const k = Math.max(0, Math.min(1, target / (lens[idx] || 1)));

  return {
    x: a[0] + (b[0] - a[0]) * k,
    y: a[1] + (b[1] - a[1]) * k,
    heading: (Math.atan2(b[1] - a[1], b[0] - a[0]) * 180) / Math.PI,
  };
};

export const RouteTravel: React.FC<{
  /** Cutout on plain white, facing RIGHT. */
  src: string;
  /** Normalised route, in travel order. */
  waypoints: [number, number][];
  /** The box the route is measured against, in px. */
  boxWidth: number;
  boxHeight: number;
  /** Local frame the vehicle leaves. */
  startFrame: number;
  /** Local frame it arrives. */
  endFrame: number;
  /** Rendered width of the vehicle, px. */
  size?: number;
  /** Vertical bob, px — a paper cutout does not glide on rails. */
  bob?: number;
  /** Constant tilt added to the heading, degrees. */
  tilt?: number;
  /**
   * Clamp on the pitch, degrees. A side-view cutout pitched to the true tangent
   * looks like it is falling off the page — a sticker on a map stays roughly
   * upright and merely leans into the slope.
   */
  maxTilt?: number;
  /**
   * Where on the sprite the route line crosses it, 0..1 from the top.
   *
   * `0.96` seats the wheels on the ink. The first version centred the sprite on the
   * route (`-50%`), which puts the line through the middle of the van: the wheels
   * hang below the road and the body floats above it, and the whole thing reads as
   * a vehicle flying over a map. Client: "arah angkot kayak lagi terbang".
   */
  contact?: number;
  /** The sprite is drawn from above: rotate with the heading, never mirror. */
  plan?: boolean;
  /**
   * Mirror the asset. The heading-based mirror only flips a vehicle that turns
   * past vertical; an asset drawn facing the other way needs telling — a toy
   * angkot driven backwards up a printed road is the kind of detail that ruins
   * a shot nobody can explain.
   */
  flip?: boolean;
}> = ({
  src,
  waypoints,
  boxWidth,
  boxHeight,
  startFrame,
  endFrame,
  size = 150,
  bob = 0,
  tilt = 0,
  maxTilt = 0,
  contact = 0.96,
  plan = false,
  flip = false,
}) => {
  const frame = useCurrentFrame();
  const t = progress(frame, startFrame, endFrame, (x) => x);
  const {x, y, heading: raw} = sampleRoute(waypoints, t);
  const px = x * boxWidth;
  const py = y * boxHeight;

  let heading = raw;
  let mirror = 1;
  /*
    **A side elevation and a plan view need different heading maths.**

    A van drawn in profile always faces right, so a heading past ±90° is handled
    by flipping it and subtracting 180° — otherwise it drives backwards. A van
    drawn **from above** must not be flipped at all: rotating it past 90° is
    exactly what it should do, and mirroring it turns it round to face the wrong
    way along the road. `plan` turns the side-view fix-up off.

    Module 1 shipped the side-view sprite on a top-down map, which is why the
    angkot read as flying: the map turns north, the sprite cannot, and `maxTilt 0`
    froze it at the tilt baked into its own pixels. A plan-view sprite plus
    `plan` plus no clamp is the fix.
  */
  if (!plan) {
    if (heading > 90) {
      heading -= 180;
      mirror = -1;
    } else if (heading < -90) {
      heading += 180;
      mirror = -1;
    }
  }

  const pitch = plan ? heading : Math.max(-maxTilt, Math.min(maxTilt, heading));
  const hop = Math.sin(t * Math.PI * 7) * bob * (t > 0 && t < 1 ? 1 : 0);
  const wob = Math.sin(t * Math.PI * 11) * 0.9 * (t > 0 && t < 1 ? 1 : 0);

  return (
    <div
      style={{
        position: "absolute",
        left: px,
        top: py + hop,
        width: size,
        transform: `translate(-50%, -${contact * 100}%) rotate(${pitch + tilt + wob}deg) scaleX(${mirror * (flip ? -1 : 1)})`,
        // Tight and close. A 9 px blur is the shadow of something hovering ten
        // centimetres above the page — it was half of why the van read as flying.
        filter: "drop-shadow(0 3px 3px rgba(40,28,8,0.42))",
        opacity: progress(frame, startFrame - 4, startFrame + 2),
      }}
    >
      <Img src={staticFile(src)} style={{width: "100%", display: "block"}} />
    </div>
  );
};
