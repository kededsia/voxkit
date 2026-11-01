import React from "react";
import {useCurrentFrame} from "remotion";
import {progress} from "./motion";
import {ribbon, rng, type Pt, type Stroke} from "./HandStroke";
import {layout, smooth, type Placed, type Seg} from "./HandLetters";

/**
 * **Khat** — a word written by hand, while the narration says it.
 *
 * The client, on the empty stretch at 0:41–0:44 of m03: *"agent presentasi
 * harusnya abis masuk dengan sesuatu, entah animasi, entah animasi tulisan
 * tangan, grafik, atau apapun itu, tapi ini gak, penonton dibiarkan bengong
 * beberapa detik."* Two ways to fill a gap, and this is the second one: when the
 * voice is leaning on a word that is not on the page, write it down.
 *
 * It is not a font. A font would put a typographic glyph on a collage made of
 * torn paper and rubber stamps, and the seam would show at once. The strokes go
 * through `HandStroke`'s ribbon the same way a marker does — sampled densely,
 * widened by a pressure curve, filled — so the ink has the same wobble, the same
 * thin ends and the same fat middle as every mark in the film. The letterforms
 * themselves come from `HandLetters`, which stores them as pen passes rather
 * than as outlines.
 *
 * Each stroke is revealed by its own mask (`pathLength={1}`, `strokeDashoffset`
 * animated), and the strokes run in sequence — letter by letter, pass by pass —
 * so the word is *written*, not faded in. Time is shared out by stroke length,
 * so the pen moves at one speed instead of spending as long on an `i` as on an
 * `m`. A dot lands when the pen would have lifted.
 */

/** A stroke laid down in the word's own coordinates, plus when it belongs. */
type Item =
  | {kind: "stroke"; stroke: Stroke; letter: number; frac: [number, number]}
  | {kind: "dot"; at: Pt; r: number; letter: number; frac: number};

const RAD = Math.PI / 180;

/**
 * Put one letter's point where the hand actually held the pen.
 *
 * The jitter is baked into the coordinates rather than applied as an SVG
 * transform, because the reveal mask is in user space: a `<g transform>` around
 * the path would move the ink and leave the mask behind. Baking it keeps one
 * coordinate system for both, and it also means the letter can lean without the
 * stroke widths leaning with it.
 */
const place = (p: Pt, baseX: number, adv: number, j: Placed["jitter"]): Pt => {
  const lx = p[0] * j.scale;
  const ly = (p[1] - 92) * j.scale;
  const cx = (adv / 2) * j.scale;
  const cy = -46 * j.scale;
  const a = j.rot * RAD;
  const dx = lx - cx;
  const dy = ly - cy;
  return [
    baseX + j.dx + cx + dx * Math.cos(a) - dy * Math.sin(a),
    92 + j.dy + cy + dx * Math.sin(a) + dy * Math.cos(a),
  ];
};

export const Khat: React.FC<{
  /** The word to write. Any lowercase word; digits and `.` `,` `?` `!` too. */
  text?: string;
  /** Local frame the pen touches down. */
  at: number;
  /** Frames from first touch to the last dot. */
  duration?: number;
  color?: string;
  /** Box in normalised stage coords (0..1 of the frame). */
  x: number;
  y: number;
  w: number;
  h: number;
  /** Pen width in px, at the box's real size. */
  sw?: number;
  rotate?: number;
  seed?: number;
  /** Ink sits above the collage — a hand draws on the page, not under it. */
  z?: number;
}> = ({
  text = "ci",
  at,
  duration = 34,
  color = "crimson",
  x,
  y,
  w,
  h,
  sw = 15,
  rotate = 0,
  seed = 7,
  z = 99,
}) => {
  const frame = useCurrentFrame();
  const {placed, width} = layout(text, seed);

  // Every pen-down movement, in the order the hand makes them.
  const raw: {segs: Seg[]; letter: number; dot?: {at: Pt; r: number}}[] = [];
  placed.forEach((pl, li) => {
    const adv = pl.letter.adv;
    pl.letter.passes.forEach((pass) => {
      const pts = pass.map((p) => place(p, pl.x, adv, pl.jitter));
      const segs = smooth(pts);
      if (segs.length) raw.push({segs, letter: li});
    });
    (pl.letter.dots ?? []).forEach((d) => {
      raw.push({segs: [], letter: li, dot: {at: place(d.at, pl.x, adv, pl.jitter), r: d.r}});
    });
  });

  const strokes = raw.map((r, i) => ({
    ...r,
    stroke: r.dot ? ({pts: [r.dot.at], half: [0]} as Stroke) : strokeOf(r.segs, sw, seed + i * 31),
  }));

  // Time is shared out by length: the pen moves at one speed. A dot has no
  // length, so it gets a fixed slot at the end of its letter — it lands when the
  // hand lifts, not while it is still moving.
  const lens = strokes.map((s) => (s.dot ? 0 : s.stroke.pts.length));
  const total = lens.reduce((a, b) => a + b, 0) || 1;
  const DOTS = 6;
  const body = Math.max(4, duration - DOTS * strokes.filter((s) => s.dot).length);
  let acc = 0;
  const spans = lens.map((l) => {
    const from = acc / total;
    acc += l;
    return [from, acc / total] as [number, number];
  });

  // A dot is timed off the last stroke of its own letter, so an `i` never has
  // its tick arrive before its stem.
  let lastOfLetter: number[] = [];
  strokes.forEach((s, i) => {
    lastOfLetter[s.letter] = i;
  });

  const uid = `khat-${text}-${seed}`;
  const vbW = Math.max(1, width) + 16;
  return (
    <div
      style={{
        position: "absolute",
        left: `${x * 100}%`,
        top: `${y * 100}%`,
        width: `${w * 100}%`,
        height: `${h * 100}%`,
        transform: `rotate(${rotate}deg)`,
        transformOrigin: "50% 50%",
        mixBlendMode: "multiply",
        zIndex: z,
      }}
    >
      <svg
        viewBox={`-8 -14 ${vbW} 126`}
        preserveAspectRatio="xMidYMid meet"
        width="100%"
        height="100%"
        style={{overflow: "visible"}}
      >
        <defs>
          <mask id={uid} maskUnits="userSpaceOnUse" x="-20" y="-40" width={vbW + 40} height={200}>
            <rect x="-20" y="-40" width={vbW + 40} height={200} fill="black" />
            {strokes.map((s, i) => {
              if (s.dot) return null;
              const [from, to] = spans[i];
              const start = at + body * from;
              const p = progress(frame, start, start + Math.max(2, body * (to - from)), (v) => v);
              return (
                <path
                  key={i}
                  d={ribbon(s.stroke)}
                  fill="none"
                  stroke="white"
                  strokeWidth={sw * 1.9}
                  strokeLinecap="round"
                  pathLength={1}
                  strokeDasharray={1}
                  strokeDashoffset={1 - p}
                />
              );
            })}
            {strokes.map((s, i) => {
              if (!s.dot) return null;
              const [from] = spans[lastOfLetter[s.letter]];
              const ds = at + body * from + DOTS;
              const p = progress(frame, ds, ds + 4, (v) => v);
              return (
                <circle key={`d${i}`} cx={s.dot.at[0]} cy={s.dot.at[1]} r={s.dot.r * 1.9 * p} fill="white" />
              );
            })}
          </mask>
        </defs>
        <g mask={`url(#${uid})`}>
          {strokes.map((s, i) =>
            s.dot ? (
              <circle key={i} cx={s.dot.at[0]} cy={s.dot.at[1]} r={s.dot.r} fill={color} opacity={0.94} />
            ) : (
              <path key={i} d={ribbon(s.stroke)} fill={color} opacity={0.94} />
            ),
          )}
        </g>
      </svg>
    </div>
  );
};

/** A chain of segments as one centreline, widened into a pen ribbon. */
function strokeOf(segs: Seg[], sw: number, seed: number): Stroke {
  const r = rng(seed);
  const pts: Pt[] = [];
  segs.forEach((s, i) => {
    const part = bez(s);
    pts.push(...(i === 0 ? part : part.slice(1)));
  });
  const n = pts.length;
  const half = pts.map((_, i) => {
    const t = n === 1 ? 0.5 : i / (n - 1);
    // Pressure: a hand presses mid-stroke and lifts at both ends. The floor keeps
    // the tip from vanishing, which is what a constant taper does on a short word.
    const lift = Math.min(1, Math.min(t, 1 - t) / 0.16);
    return (sw / 2) * (0.55 + 0.45 * Math.pow(lift, 0.55)) * (0.93 + r() * 0.14);
  });
  return {pts, half};
}

const bez = ([p0, c1, c2, p1]: Seg, n = 14): Pt[] =>
  Array.from({length: n}, (_, i) => {
    const t = i / (n - 1);
    const u = 1 - t;
    return [
      u * u * u * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t * t * t * p1[0],
      u * u * u * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t * t * t * p1[1],
    ] as Pt;
  });
