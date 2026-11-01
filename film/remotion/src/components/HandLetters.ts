import type {Pt} from "./HandStroke";

/**
 * **A hand, not a font.**
 *
 * `Khat` could only write the two words someone had drawn by hand — `ci` and
 * `chi` — and fell back to `ci` for anything else. That made the presenter's
 * `write` gesture a lie: it decided the voice was leaning on a word and asked
 * the renderer to write it, and the renderer wrote "ci" instead. On a page about
 * *pengumbahan* that is worse than leaving the page still.
 *
 * So here is the alphabet. Every letterform is a set of **pen passes** — the
 * movements a hand actually makes, not the contours a type designer would
 * build: `a` is a bowl and then a stem laid down the right side of it, `e` is
 * one open loop that starts at the waist, `k` is a stem and two diagonals that
 * leave it, `t` is a stem with a bar across it drawn after the stem is down.
 *
 * Each pass is a short polyline. `smooth` turns it into cubics through the
 * points (Catmull–Rom), so the ink curves the way a wrist curves while the
 * points themselves stay a little uneven — which is where the handwriting comes
 * from. Nothing here is regular: the baseline drifts, the x-height is not
 * constant, the bowls are not circles.
 *
 * Coordinates are in a 100-unit box: x-height runs 36 → 92, ascenders reach 14,
 * descenders fall to 100. `adv` is the pen's advance — how far right the next
 * letter starts. The renderer jitters each letter's angle and size a little, so
 * two `a`s in one word are never the same `a`.
 */

export type Seg = [Pt, Pt, Pt, Pt];

export type Letter = {
  /** One entry per time the pen touches down. */
  passes: Pt[][];
  /** Dots: the `i`'s tick, the `j`'s, the `:` — they land after the pen lifts. */
  dots?: {at: Pt; r: number}[];
  /** How far the pen advances, in the same 100-unit box. */
  adv: number;
};

const dot = (at: Pt, r = 4): {at: Pt; r: number} => ({at, r});

/**
 * The alphabet. Uppercase is drawn from the lowercase forms (a Vox page has no
 * time for a second set), and digits share the same x-height so a number reads
 * as part of the sentence rather than as a label pasted on.
 */
export const LETTERS: Record<string, Letter> = {
  a: {
    passes: [
      [[64, 42], [48, 35], [32, 46], [31, 66], [44, 86], [61, 79], [64, 50]],
      [[64, 40], [64, 62], [64, 80], [69, 90]],
    ],
    adv: 64,
  },
  b: {
    passes: [
      [[36, 14], [35, 48], [35, 76], [36, 92]],
      [[36, 52], [52, 37], [70, 49], [70, 69], [54, 87], [36, 80]],
    ],
    adv: 66,
  },
  c: {
    passes: [[[70, 44], [54, 35], [37, 44], [31, 62], [38, 80], [56, 89], [70, 80]]],
    adv: 60,
  },
  d: {
    passes: [
      [[40, 43], [57, 35], [71, 48], [70, 70], [54, 87], [39, 78], [38, 56]],
      [[70, 14], [69, 50], [70, 78], [70, 92]],
    ],
    adv: 66,
  },
  e: {
    passes: [[[31, 64], [63, 59], [62, 43], [48, 36], [33, 47], [30, 68], [41, 84], [59, 88], [69, 80]]],
    adv: 60,
  },
  f: {
    passes: [
      [[65, 18], [52, 13], [46, 25], [46, 56], [46, 92]],
      [[34, 44], [59, 40]],
    ],
    adv: 50,
  },
  g: {
    passes: [
      [[62, 44], [44, 37], [30, 50], [32, 70], [48, 84], [62, 76], [64, 48]],
      [[64, 40], [64, 76], [59, 96], [44, 100], [34, 94]],
    ],
    adv: 64,
  },
  h: {
    passes: [
      [[36, 14], [35, 50], [35, 74], [36, 92]],
      [[36, 54], [50, 39], [62, 46], [63, 66], [63, 92]],
    ],
    adv: 64,
  },
  i: {
    passes: [[[46, 40], [46, 68], [45, 92]]],
    dots: [dot([47, 25], 3.8)],
    adv: 32,
  },
  j: {
    passes: [[[55, 40], [54, 70], [52, 94], [43, 100], [35, 94]]],
    dots: [dot([57, 25], 3.8)],
    adv: 40,
  },
  k: {
    passes: [
      [[36, 14], [35, 52], [35, 74], [36, 92]],
      [[62, 44], [50, 58], [39, 67]],
      [[45, 61], [55, 77], [65, 92]],
    ],
    adv: 60,
  },
  l: {
    passes: [[[44, 14], [43, 52], [43, 78], [50, 92]]],
    adv: 34,
  },
  m: {
    passes: [
      [[28, 44], [28, 68], [28, 92]],
      [[28, 55], [38, 39], [49, 46], [49, 68], [49, 92]],
      [[49, 55], [59, 39], [70, 46], [70, 68], [70, 92]],
    ],
    adv: 88,
  },
  n: {
    passes: [
      [[33, 44], [33, 68], [33, 92]],
      [[33, 54], [45, 39], [58, 46], [58, 68], [58, 92]],
    ],
    adv: 64,
  },
  o: {
    passes: [[[48, 36], [31, 47], [29, 66], [42, 87], [59, 86], [70, 65], [67, 47], [53, 36], [46, 38]]],
    adv: 64,
  },
  p: {
    passes: [
      [[35, 44], [35, 72], [35, 100]],
      [[35, 54], [51, 39], [68, 51], [68, 72], [52, 87], [35, 80]],
    ],
    adv: 66,
  },
  q: {
    passes: [
      [[44, 43], [61, 37], [73, 51], [71, 72], [55, 87], [42, 78], [40, 54]],
      [[71, 44], [71, 72], [71, 100]],
    ],
    adv: 68,
  },
  r: {
    passes: [
      [[35, 44], [35, 68], [35, 92]],
      [[35, 56], [45, 41], [58, 38]],
    ],
    adv: 46,
  },
  s: {
    passes: [[[66, 44], [50, 37], [38, 44], [41, 56], [57, 64], [66, 74], [59, 88], [42, 90], [32, 82]]],
    adv: 58,
  },
  t: {
    passes: [
      [[48, 20], [47, 54], [48, 82], [57, 90]],
      [[34, 44], [62, 42]],
    ],
    adv: 50,
  },
  u: {
    passes: [[[33, 42], [33, 66], [36, 82], [48, 90], [59, 84], [60, 62], [60, 42]]],
    adv: 64,
  },
  v: {
    passes: [[[31, 42], [40, 68], [48, 90], [57, 68], [65, 42]]],
    adv: 60,
  },
  w: {
    passes: [[[26, 42], [33, 68], [42, 90], [50, 63], [58, 90], [67, 68], [73, 42]]],
    adv: 84,
  },
  x: {
    passes: [
      [[33, 42], [47, 62], [64, 90]],
      [[64, 42], [47, 65], [33, 90]],
    ],
    adv: 60,
  },
  y: {
    passes: [
      [[33, 42], [40, 66], [48, 84]],
      [[65, 42], [52, 74], [42, 96], [33, 100]],
    ],
    adv: 60,
  },
  z: {
    passes: [[[33, 44], [55, 41], [65, 44], [36, 87], [65, 87]]],
    adv: 58,
  },

  // ------------------------------------------------------------- digits
  // A number on a Vox page is written in the margin, at speed, often larger
  // than the letters beside it. These sit on the same baseline and share the
  // same x-height so a figure never looks like a different typeface arrived.
  "0": {
    passes: [[[52, 14], [35, 30], [33, 62], [46, 91], [61, 86], [67, 57], [62, 29], [51, 14]]],
    adv: 62,
  },
  "1": {
    passes: [
      [[39, 30], [52, 16], [52, 58], [52, 92]],
      [[37, 92], [67, 92]],
    ],
    adv: 52,
  },
  "2": {
    passes: [[[33, 34], [52, 21], [67, 34], [62, 55], [33, 90], [68, 90]]],
    adv: 62,
  },
  "3": {
    passes: [
      [[33, 31], [54, 20], [67, 35], [50, 54]],
      [[50, 54], [68, 63], [64, 85], [44, 91], [31, 82]],
    ],
    adv: 60,
  },
  "4": {
    passes: [
      [[58, 15], [33, 66], [70, 66]],
      [[58, 44], [58, 74], [58, 92]],
    ],
    adv: 64,
  },
  "5": {
    passes: [[[66, 21], [40, 21], [35, 50], [54, 43], [68, 58], [62, 85], [40, 91], [30, 82]]],
    adv: 62,
  },
  "6": {
    passes: [[[62, 19], [44, 39], [35, 64], [40, 87], [56, 92], [66, 77], [58, 61], [42, 61], [35, 70]]],
    adv: 62,
  },
  "7": {
    passes: [[[31, 24], [63, 21], [46, 60], [42, 92]]],
    adv: 58,
  },
  "8": {
    passes: [[[52, 20], [37, 31], [45, 47], [60, 56], [64, 74], [50, 90], [35, 76], [44, 54], [58, 42], [52, 21]]],
    adv: 62,
  },
  "9": {
    passes: [[[62, 38], [50, 21], [35, 33], [39, 52], [58, 54], [64, 38], [57, 63], [49, 85], [45, 96]]],
    adv: 62,
  },

  // ------------------------------------------------------------ marks
  // Punctuation is written too, because a written word followed by a printed
  // full stop is the seam that gives the whole thing away.
  ".": {passes: [], dots: [dot([46, 88], 4.4)], adv: 26},
  ",": {passes: [[[48, 86], [46, 92], [40, 100]]], adv: 26},
  "?": {
    passes: [
      [[34, 34], [50, 20], [65, 33], [56, 52], [50, 62], [49, 74]],
    ],
    dots: [dot([49, 90], 4.2)],
    adv: 58,
  },
  "!": {passes: [[[50, 16], [49, 52], [48, 70]]], dots: [dot([48, 88], 4.2)], adv: 32},
  "'": {passes: [[[48, 18], [46, 34]]], adv: 24},
  "-": {passes: [[[32, 62], [62, 60]]], adv: 54},
  ":": {passes: [], dots: [dot([46, 52], 3.8), dot([46, 88], 3.8)], adv: 26},
};

/** A space is not a letter, but the pen still moves. */
export const SPACE_ADV = 30;

/**
 * A polyline as cubics through its points.
 *
 * Catmull–Rom, because it passes *through* every point — the points are the
 * hand's own stops, and a curve that misses them is a curve that was designed
 * rather than written. The tension is a little slack (0.9 of a full Catmull–Rom
 * tangent) so the loops of `e` and `o` do not overshoot into a knot.
 */
export const smooth = (pts: Pt[], tension = 0.9): Seg[] => {
  if (pts.length < 2) return [];
  const out: Seg[] = [];
  const at = (i: number): Pt => pts[Math.max(0, Math.min(pts.length - 1, i))];
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = at(i - 1);
    const p1 = at(i);
    const p2 = at(i + 1);
    const p3 = at(i + 2);
    const c1: Pt = [p1[0] + ((p2[0] - p0[0]) / 6) * tension, p1[1] + ((p2[1] - p0[1]) / 6) * tension];
    const c2: Pt = [p2[0] - ((p3[0] - p1[0]) / 6) * tension, p2[1] - ((p3[1] - p1[1]) / 6) * tension];
    out.push([p1, c1, c2, p2]);
  }
  return out;
};

export type Placed = {
  /** Index of the letter in the word, so timing can run letter by letter. */
  i: number;
  ch: string;
  /** Left edge of the letter's cell, in word units. */
  x: number;
  /** How the hand was holding the pen when it wrote this one. */
  jitter: {dx: number; dy: number; rot: number; scale: number};
  letter: Letter;
};

/**
 * Lay a word out as a row of letters, each one written where the previous one
 * left the pen.
 *
 * The jitter is per letter and deterministic in the seed, because the point of
 * it is that no two letters agree — a row of identical `a`s reads as a font no
 * matter how much wobble each stroke has on its own.
 */
export const layout = (word: string, seed: number): {placed: Placed[]; width: number} => {
  const text = (word || "").toLowerCase();
  let x = 0;
  let n = 0;
  const placed: Placed[] = [];
  let s = seed >>> 0;
  const rnd = () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
  // Tracking. The letterform table advances about 62 units per letter, which is
  // a fair hand when it is written slowly; at speed a person closes the gaps.
  const TRACK = 0.88;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === " ") {
      x += SPACE_ADV;
      continue;
    }
    const letter = LETTERS[ch];
    if (!letter) continue;
    placed.push({
      i: n++,
      ch,
      x,
      jitter: {
        dx: (rnd() - 0.5) * 3,
        dy: (rnd() - 0.5) * 6,
        rot: (rnd() - 0.5) * 5,
        scale: 0.95 + rnd() * 0.09,
      },
      letter,
    });
    x += letter.adv * TRACK + 2;
  }
  return {placed, width: Math.max(1, x - 2)};
};
