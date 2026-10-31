import React from "react";
import {useCurrentFrame} from "remotion";
import {progress} from "./motion";
import {ribbon, rng, type Pt, type Stroke} from "./HandStroke";

/**
 * **Khat** — a word written by hand, while the narration says it.
 *
 * The client, on the empty stretch at 0:15.5–0:17 of m03: *"kalau belum waktunya
 * masuk object juga jangan dipaksakan, mending generate card baru yang sesuai
 * kalimat atau kata yang kosong, atau animasi khat tulisan tangan untuk nutup gap
 * itu."* Two ways to fill a gap, and this is the second one: when the words are
 * naming the very thing that is not on the page yet, write it.
 *
 * It is not a font. A font would put a typographic glyph on a collage that is made
 * of torn paper and rubber stamps, and the seam would show at once. The strokes go
 * through `HandStroke`'s ribbon the same way a marker does — sampled densely,
 * widened by a pressure curve, and filled — so the ink has the same wobble, the
 * same thin ends and the same fat middle as every mark in the film.
 *
 * Each stroke is revealed by its own mask (`pathLength={1}`, `strokeDashoffset`
 * animated), and the strokes run in sequence so the word is *written*, not faded
 * in. A dot is a circle that lands when the pen would have lifted.
 */

type Seg = [Pt, Pt, Pt, Pt]; // start, control, control, end

type Glyph = {
  /** One entry per pass of the pen, each a chain of cubic segments. */
  strokes: Seg[][];
  dots?: {at: Pt; r: number}[];
};

/**
 * Letterforms in a 100 × 100 box, drawn as a hand would: the `c` is one open
 * bowl that overshoots its own end, the `i` is a stem that leans and a dot that
 * lands after the pen lifts.
 */
const GLYPHS: Record<string, Glyph> = {
  ci: {
    strokes: [
      // c — one pass, opening to the right, ending past the start of the bowl
      [
        [[66, 30], [46, 16], [20, 32], [22, 56]],
        [[22, 56], [24, 82], [48, 94], [68, 80]],
      ],
      // i — stem, leaning slightly as it descends
      [
        [[79, 34], [77, 52], [75, 72], [74, 92]],
      ],
    ],
    dots: [{at: [81, 22], r: 3.6}],
  },
  /**
   * `chi` — the district's spelling of the syllable, written on the page where
   * the narration says "unsur Chi" and nothing on the sheet says it. The `h`
   * carries the ascender, so the word sits taller than the `ci` above it: the
   * bowl and the stem share one x-height (y 34–92) and the ascender runs up to
   * y 16, which is what makes it read as a word and not three letters in a row.
   */
  chi: {
    strokes: [
      // c
      [
        [[36, 34], [22, 20], [6, 36], [8, 56]],
        [[8, 56], [10, 80], [26, 92], [40, 78]],
      ],
      // h — ascender and stem in one pass down, then the arch off the stem
      [
        [[46, 16], [46, 44], [47, 70], [48, 92]],
      ],
      [
        [[46, 48], [50, 38], [60, 34], [64, 44]],
        [[64, 44], [67, 58], [66, 76], [65, 92]],
      ],
      // i
      [
        [[74, 42], [73, 62], [72, 80], [71, 94]],
      ],
    ],
    dots: [{at: [77, 30], r: 3.2}],
  },
};

const bez = ([p0, c1, c2, p1]: Seg, n = 26): Pt[] =>
  Array.from({length: n}, (_, i) => {
    const t = i / (n - 1);
    const u = 1 - t;
    return [
      u * u * u * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t * t * t * p1[0],
      u * u * u * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t * t * t * p1[1],
    ] as Pt;
  });

/** A chain of segments as one centreline, widened into a pen ribbon. */
const strokeOf = (segs: Seg[], sw: number, seed: number): Stroke => {
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
};

export const Khat: React.FC<{
  /** Which letterforms to write. Only the words in `GLYPHS` exist. */
  text?: string;
  /** Local frame the pen touches down. */
  at: number;
  /** Frames from first touch to the dot. */
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
}) => {
  const frame = useCurrentFrame();
  const glyph = GLYPHS[text] ?? GLYPHS.ci;
  const strokes = glyph.strokes.map((s, i) => strokeOf(s, sw, seed + i * 31));
  const W = w * 1920;
  const H = h * 1080;

  // Strokes share the time in proportion to how long they are, so the pen moves
  // at one speed rather than spending as long on the `i` as on the `c`.
  const lens = strokes.map((s) => s.pts.length);
  const total = lens.reduce((a, b) => a + b, 0) || 1;
  let acc = 0;
  const spans = lens.map((l) => {
    const from = acc / total;
    acc += l;
    return [from, acc / total] as [number, number];
  });

  const uid = `khat-${text}-${seed}`;
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
      }}
    >
      <svg viewBox="0 0 100 100" width="100%" height="100%" style={{overflow: "visible"}}>
        <defs>
          <mask id={uid} maskUnits="userSpaceOnUse" x="-10" y="-10" width="120" height="120">
            <rect x="-10" y="-10" width="120" height="120" fill="black" />
            {strokes.map((s, i) => {
              const [from, to] = spans[i];
              const start = at + duration * from;
              const p = progress(frame, start, start + Math.max(2, duration * (to - from)), (v) => v);
              return (
                <path
                  key={i}
                  d={ribbon(s)}
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
            {(glyph.dots ?? []).map((d, i) => {
              const ds = at + duration * 0.86;
              const p = progress(frame, ds, ds + 4, (v) => v);
              return (
                <circle
                  key={`d${i}`}
                  cx={d.at[0]}
                  cy={d.at[1]}
                  r={d.r * 1.9 * p}
                  fill="white"
                />
              );
            })}
          </mask>
        </defs>
        <g mask={`url(#${uid})`}>
          {strokes.map((s, i) => (
            <path key={i} d={ribbon(s)} fill={color} opacity={0.94} />
          ))}
          {(glyph.dots ?? []).map((d, i) => (
            <circle key={`d${i}`} cx={d.at[0]} cy={d.at[1]} r={d.r} fill={color} opacity={0.94} />
          ))}
        </g>
      </svg>
    </div>
  );
};
