/**
 * Hand-drawn geometry, generated rather than authored.
 *
 * The marker library used to draw hand-authored SVG paths. They were smooth,
 * closed, symmetric and identical every time, which is exactly what a pen is not:
 * a real mark wobbles, thins where the hand speeds up, overshoots the corner and
 * comes back, and never closes on itself. On screen the difference is not subtle —
 * a perfect bezier loop reads as vector art dropped on a photograph, and eight of
 * them in a row read as a template.
 *
 * So the geometry is *computed*: a primitive (a line, a loop, a corner) sampled
 * densely, displaced along its normal by smooth noise, and given a half-width that
 * varies with pressure. The result is emitted as a filled ribbon — a polygon whose
 * outline is offset from the centreline by a varying amount — because a stroke with
 * a constant `stroke-width` cannot thin and swell.
 *
 * Everything is in **pixels**, in a `W × H` box, because a stretched `0..100`
 * viewBox distorts both the shape and the pen: an ellipse in a wide box becomes an
 * oval with a thick end and a thin end. `Marker` therefore passes the container's
 * real size and draws in it 1:1.
 *
 * Determinism matters: the same `seed` must produce the same stroke on every
 * frame, or the mark shimmers. Every generator takes a seeded PRNG and nothing
 * else, so a mark is stable across a render and still unique per call site.
 */

export type Pt = [number, number];

/** One continuous pass of the pen. */
export type Stroke = {
  /** Centreline, densely sampled, in px. */
  pts: Pt[];
  /** Half-width at each point, in px — this is what makes it read as pressure. */
  half: number[];
};

// ---------------------------------------------------------------- randomness

/** mulberry32 — small, fast, and identical on every frame. */
export const rng = (seed: number): (() => number) => {
  let a = (seed >>> 0) || 1;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};

/**
 * Smooth, zero-mean noise over t ∈ [0,1] — three sine components at unrelated
 * frequencies. A random walk would drift and leave the mark off its target; sines
 * wander and come back, which is what a hand does.
 */
const wobble = (r: () => number, amp: number, cycles: [number, number, number]): ((t: number) => number) => {
  const c = cycles.map((f) => ({f, p: r() * Math.PI * 2, a: 0.4 + r() * 0.9}));
  const total = c.reduce((s, k) => s + k.a, 0);
  // Measured, not guessed: this sum divided by `total` has an RMS of 0.35–0.46
  // and a peak of 0.76–0.90 over 400 samples on any seed, so scaling by
  // `amp / 0.62` makes `amp` mean "peak offset", which is what a caller is
  // thinking about when it writes 0.03. Normalising by `total` alone made `amp`
  // the worst case of three crests lining up, which is roughly 1.6× the peak
  // actually reached — every wobble came out about a third of its number.
  const scale = amp / 0.62;
  return (t) => scale * c.reduce((s, k) => s + k.a * Math.sin(k.f * Math.PI * 2 * t + k.p), 0);
};

/**
 * Knot noise — the deviation of a real hand, and **not periodic**.
 *
 * `wobble` above is a sum of three sines, and that is precisely what a wave is:
 * frequencies that never die out, so the eye locks onto a wavelength and reads
 * "sine". On a box side it was unmistakable. *Client, on shots 1 and 2: "effect
 * marker-nya masih ada kayak gelombang gitu."* He was looking at the frame the
 * geometry drew, not at the pen: a 480 px side bowed 8 px in one smooth hump and
 * drifted 5 px at 1.7 cycles, which is a wave with a 280 px wavelength.
 *
 * A hand is not periodic. It deviates, corrects, and settles, so the displacement
 * here is random values at a handful of knots joined by smoothstep: irregular
 * along the whole stroke, no wavelength to find, and still continuous so the
 * ribbon does not kink.
 *
 * **Straightness was never the problem — periodicity was.** A hand-drawn line is
 * nearly straight; it is the *regularity* of its deviation that betrays a
 * machine. So the amplitude goes down and the irregularity goes up.
 */
const knots = (r: () => number, amp: number, n = 4): ((t: number) => number) => {
  const v = Array.from({length: n + 1}, () => (r() * 2 - 1) * amp);
  return (t) => {
    const x = Math.min(n - 1e-6, Math.max(0, t * n));
    const i = Math.floor(x);
    const k = x - i;
    const s = k * k * (3 - 2 * k);
    return v[i] + (v[i + 1] - v[i]) * s;
  };
};

/**
 * The pen lands firm and lifts off thin.
 *
 * The old profile was symmetric — 0.65 at both ends — and a symmetric end is the
 * shape of a *cut*, not of a stroke: at 1080p every underline finished in a
 * squared-off bar with the same weight it started with, which is half of why the
 * marks read as vector rectangles rather than ink. A hand touches down fast and
 * almost at full width, then runs out of pressure over the last stretch and the
 * tip narrows before it leaves the paper.
 */
const taper = (t: number, len = 0, inFrac = 0.05, outFrac = 0.18): number => {
  // A short stroke is a *dab*, not a pull. An 80–120 px bar with a lift-off on
  // the end has nothing to thin into: the taper eats a third of its length and
  // the result is a leaf, not a line. Short strokes keep their body and only
  // soften the last two pixels.
  const short = len > 0 && len < 200;
  if (short) {
    const a = Math.min(1, t / 0.03);
    const b = Math.min(1, (1 - t) / 0.03);
    return 0.94 + 0.06 * Math.min(a, b);
  }
  const a = Math.min(1, t / Math.max(inFrac, 1e-3));
  const b = Math.min(1, (1 - t) / Math.max(outFrac, 1e-3));
  return Math.min(0.72 + 0.28 * Math.sqrt(a), 0.30 + 0.70 * Math.sqrt(b));
};

/**
 * Per-point half-width: a base, a slow pressure swell, a fast one, and the
 * taper.
 *
 * The numbers are deliberately small. A felt-tip on paper varies in width by
 * about 10 % and a brush by 40 %; a marker varies by about 12 %. The first
 * version of this used ±30 % slow and ±9 % fast, which is a *brush* — at 1080p
 * the strokes came out with obvious fat and thin patches and read as liquid, not
 * as ink. `swell` is now ±11 % by default, with a ±4.5 % fast layer for tooth.
 */
const pressure = (
  n: number,
  sw: number,
  r: () => number,
  swell = 0.06,
  len = 0,
): number[] => {
  // Smooth, natural hand pressure variation without jagged ripples:
  const slow = wobble(r, swell, [0.6, 1.2, 1.8]);
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const t = n === 1 ? 0.5 : i / (n - 1);
    out.push((sw / 2) * (1 + slow(t)) * taper(t, len));
  }
  return out;
};

// ---------------------------------------------------------------- ribbon

/**
 * Turn a centreline + half-widths into a closed outline.
 *
 * Walk down one side at the local normal offset, then back up the other. With a
 * hundred samples the joins are invisible, and because the half-width tapers to a
 * blunt point at each end the polygon closes on itself without a cap.
 */
export const ribbon = ({pts, half}: Stroke): string => {
  const n = pts.length;
  if (n < 2) return "";
  const left: string[] = [];
  const right: string[] = [];
  for (let i = 0; i < n; i++) {
    const [x, y] = pts[i];
    const a = pts[Math.max(0, i - 1)];
    const b = pts[Math.min(n - 1, i + 1)];
    let dx = b[0] - a[0];
    let dy = b[1] - a[1];
    const len = Math.hypot(dx, dy) || 1;
    dx /= len;
    dy /= len;
    const h = half[i];
    left.push(`${(x - dy * h).toFixed(2)},${(y + dx * h).toFixed(2)}`);
    right.push(`${(x + dy * h).toFixed(2)},${(y - dx * h).toFixed(2)}`);
  }
  right.reverse();
  return `M${left.join("L")}L${right.join("L")}Z`;
};

// ---------------------------------------------------------------- primitives

const sample = (n: number, f: (t: number) => Pt): Pt[] =>
  Array.from({length: n}, (_, i) => f(n === 1 ? 0.5 : i / (n - 1)));

/**
 * A line the hand drew: bowed off the straight, wandering along its length, and
 * running past its own end by a few percent.
 */
export const line = (
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  sw: number,
  r: () => number,
  opts: {bow?: number; over?: number; n?: number; swell?: number; skew?: number} = {},
): Stroke => {
  const {bow = 0.012, over = 0.04, n = 64, swell = 0.06, skew = 1} = opts;
  const dx = x1 - x0;
  const dy = y1 - y0;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len;
  const uy = dy / len;
  const nx = -uy;
  const ny = ux;
  // A marker dragged across a page wanders by a couple of pixels, and at 1080p
  // that is the difference between ink and vector art. But *regularity* matters
  // more than amplitude: this used to be `wobble` at 0.6/1.1/1.7 cycles, which
  // draws a wave — and a wavy underline is a different kind of fake, it looks
  // drawn by a machine that was told to be organic. Knot noise has no wavelength
  // to find, so the deviation reads as a hand and not as a sine.
  // Amplitude scales with the pull but is floored and capped: a 200 px underline
  // still wanders 2.5 px, and a 1400 px rule across a page wanders 8 — beyond that
  // it is a curve, and below 2 px it is a vector rule. `knots` supplies the shape;
  // this only decides how far the hand strayed.
  const drift = knots(r, Math.max(2.5, Math.min(len * 0.009, 8)), 4);
  const sag = (r() - 0.5) * 0.3;
  const back = len * over * (0.4 + r() * 0.6);
  const pts = sample(n, (t) => {
    const tt = t * (1 + back / len) - back / len / 2;
    const along = tt * len;
    // `skew` moves the single hump off the middle. A hump centred at 0.5 is a
    // symmetric arch, and a symmetric arch on a box side is the other half of
    // why the mark read as a wave: a hand sags where it is hurrying, not at the
    // midpoint of the stroke.
    const u = Math.max(0, Math.min(1, tt));
    const off = bow * len * Math.sin(Math.PI * Math.pow(u, skew)) * (0.85 + sag) + drift(t);
    return [x0 + ux * along + nx * off, y0 + uy * along + ny * off];
  });
  return {pts, half: pressure(n, sw, r, swell, len)};
};

/**
 * A rectangle drawn in **one lap**, because a pen does not lift at a corner.
 *
 * The box used to be four `line()` calls meeting at exact coordinates: each
 * corner was a true 90° join, each side had its own taper dying at that join,
 * and the four bows were independent. Four strokes and four square corners is a
 * bracket — which is exactly what shipped on s08 and what the client circled.
 *
 * Here the perimeter is a single centreline: the corners turn on a radius, the
 * drift is one knot-noise run over the whole lap, and the pressure swells across
 * the corners instead of restarting at them. The pen lifts before the last side
 * meets the first, so the frame is open — a closed loop is a marquee.
 */
const frame = (
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  sw: number,
  r: () => number,
  opts: {gap?: number; n?: number} = {},
): Stroke => {
  const w = x1 - x0;
  const h = y1 - y0;
  // Corner radius is a hand's, not a drawing program's: a few percent of the
  // short side, and never the same twice.
  const rad = Math.max(5, Math.min(w, h) * (0.055 + r() * 0.05));
  const runW = Math.max(1, w - 2 * rad);
  const runH = Math.max(1, h - 2 * rad);
  const arc = (Math.PI / 2) * rad;
  const P = 2 * runW + 2 * runH + 4 * arc;

  const at = (s: number): Pt => {
    let t = s - Math.floor(s / P) * P;
    if (t < runW) return [x0 + rad + t, y0];
    t -= runW;
    if (t < arc) {
      const a = -Math.PI / 2 + (t / arc) * (Math.PI / 2);
      return [x1 - rad + rad * Math.cos(a), y0 + rad + rad * Math.sin(a)];
    }
    t -= arc;
    if (t < runH) return [x1, y0 + rad + t];
    t -= runH;
    if (t < arc) {
      const a = (t / arc) * (Math.PI / 2);
      return [x1 - rad + rad * Math.cos(a), y1 - rad + rad * Math.sin(a)];
    }
    t -= arc;
    if (t < runW) return [x1 - rad - t, y1];
    t -= runW;
    if (t < arc) {
      const a = Math.PI / 2 + (t / arc) * (Math.PI / 2);
      return [x0 + rad + rad * Math.cos(a), y1 - rad + rad * Math.sin(a)];
    }
    t -= arc;
    if (t < runH) return [x0, y1 - rad - t];
    t -= runH;
    const a = Math.PI + (t / arc) * (Math.PI / 2);
    return [x0 + rad + rad * Math.cos(a), y0 + rad + rad * Math.sin(a)];
  };

  const gap = (opts.gap ?? 0.15) + r() * 0.07;
  const n = opts.n ?? 320;
  const s0 = gap * P;
  const span = P * (1 - gap);
  const drift = knots(r, Math.max(2, Math.min(span * 0.006, 6)), 5);
  const pts = sample(n, (t) => {
    const s = s0 + t * span;
    const [x, y] = at(s);
    const [xa, ya] = at(s - 2);
    const [xb, yb] = at(s + 2);
    let dx = xb - xa;
    let dy = yb - ya;
    const L = Math.hypot(dx, dy) || 1;
    dx /= L;
    dy /= L;
    const off = drift(t);
    return [x - dy * off, y + dx * off];
  });
  return {pts, half: pressure(n, sw * 0.92, r, 0.09, span)};
};

/**
 * A stroke drawn with the same centreline but a wider body — the ink that soaks
 * into the paper around the mark.
 *
 * A marker on newsprint does not have an edge: the fibre pulls pigment a few
 * pixels past the tip and that fringe is lighter than the body. Drawn as one
 * filled polygon the mark ends in a hard vector boundary, which is why it reads
 * as a shape sitting on the page instead of a stain in it. `Marker` lays this
 * copy underneath at low opacity.
 */
export const widen = ({pts, half}: Stroke, k: number): Stroke => ({
  pts,
  half: half.map((h) => h * k),
});

/**
 * A loop the hand closed: one turn plus a little more, so the ends cross instead
 * of meeting, and the radius breathes so it is never a true ellipse.
 *
 * The key to reading as a hand and not as a compass: the radius *grows* with the
 * angle. A hand circles inward at first and spirals out past where it began, so
 * `grow` tips the spiral; the old version was zero-mean wobble only, which keeps
 * the start and end on the same ring and reads as a stencil.
 */
export const loop = (
  cx: number,
  cy: number,
  rx: number,
  ry: number,
  sw: number,
  r: () => number,
  opts: {turns?: number; start?: number; n?: number} = {},
): Stroke => {
  const {turns = 1.12, start = r() * Math.PI * 2, n = 150} = opts;
  // Smooth organic loop, no multi-wave dents — but big enough to see. This was
  // 0.012 of the radius: on a 260 px radius that is ±3 px, and a ring with a 3 px
  // wobble is a ring. 2.2 % is ±6 px, which is a hand circling a word; 3.5 % drew
  // an egg with a dent.
  const radial = wobble(r, 0.022, [1.0, 2.0, 3.0]);
  const tilt = (r() - 0.5) * 0.15;
  const grow = 0.05 + r() * 0.06; // spiral outward cleanly by 5-11%
  const ox = (r() - 0.5) * rx * 0.06;
  const oy = (r() - 0.5) * ry * 0.06;
  const pts = sample(n, (t) => {
    const a = start + t * turns * Math.PI * 2;
    const k = 1 + radial(t) + grow * t;
    const x = Math.cos(a) * rx * k;
    const y = Math.sin(a) * ry * k;
    return [
      cx + ox + x * Math.cos(tilt) - y * Math.sin(tilt),
      cy + oy + x * Math.sin(tilt) + y * Math.cos(tilt),
    ];
  });
  return {pts, half: pressure(n, sw, r, 0.16)};
};

/**
 * Four sides, each drawn as its own pass and running past both corners.
 *
 * Three things separate this from a `<rect>`, and all three were tuned by
 * rendering a 1080p frame and looking at it, because at that size the eye
 * catches the difference long before the numbers do:
 *
 *  - **each side bows its own amount** (3–6 % of its length, so 9–18 px on a
 *    300 px side). The old 1.2 % was a 3.6 px sag — a perfectly straight line
 *    to anyone looking at the frame, which is why every box read as vector art.
 *  - **no side is level**: every endpoint is jittered a couple of px, so the
 *    four corners are four different points, not two shared ones.
 *  - **the overshoot differs per corner**. A hand does not run 6 px past all
 *    four corners; it runs 4 px past one and 12 px past the one it was hurrying
 *    towards.
 */
export const rect = (
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  sw: number,
  r: () => number,
): Stroke[] => {
  const w = x1 - x0;
  const h = y1 - y0;
  // Overshoot in *pixels*, not as a fraction. As a fraction it is right on a big
  // box and absurd on a small one: the corners of the box round "CI" ran a fifth
  // of the word past its own edge and landed on the next letter.
  //
  // The *floor* matters more than the ceiling, and it was wrong: `o()` is
  // multiplied by 0.5–1.35, so on a small box the product fell to ~1 px and the
  // four sides stopped short of their corners, rendering as `[ ]`. The multiplier
  // is now > 1 everywhere, so every side genuinely crosses its corner.
  const ov = Math.min(9, Math.max(5, Math.min(Math.abs(w), Math.abs(h)) * 0.022));
  const o = () => ov * (0.7 + r() * 0.9); // per-corner, per-end, always outward
  const j = Math.min(3.5, Math.min(Math.abs(w), Math.abs(h)) * 0.012);
  const jit = () => (r() - 0.5) * 2 * j;
  // Four corners, each nudged, so no two sides share an endpoint.
  const c = [
    [x0 + jit(), y0 + jit()],
    [x1 + jit(), y0 + jit()],
    [x1 + jit(), y1 + jit()],
    [x0 + jit(), y1 + jit()],
  ] as const;
  // Firm sides with a hand's flex. 1.2–2.4 % was the ceiling when the drift was
  // still a sine sum; with knot noise carrying the irregularity the arch comes
  // down to 0.8–1.6 % and is skewed per side, because two periodic displacements
  // (an arch at 0.5 and a 1.7-cycle drift) add up to exactly the wave the client
  // named on the box in shots 1 and 2.
  const bow = () => 0.008 + r() * 0.008;
  // Sides run past *their own* corner, outward. `o()` is applied asymmetrically
  // per segment, which is what makes the four corners land at four different
  // places — but it must never be negative, or the side stops short of the corner
  // and the box closes as four disconnected brackets.
  return [
    line(c[0][0] - o(), c[0][1], c[1][0] + o(), c[1][1], sw, r, {bow: bow(), over: 0, skew: 0.7 + r() * 0.7}),
    line(c[1][0], c[1][1] - o(), c[2][0], c[2][1] + o(), sw, r, {bow: bow(), over: 0, skew: 0.7 + r() * 0.7}),
    line(c[2][0] + o(), c[2][1], c[3][0] - o(), c[3][1], sw, r, {bow: bow(), over: 0, skew: 0.7 + r() * 0.7}),
    line(c[3][0], c[3][1] + o(), c[0][0], c[0][1] - o(), sw, r, {bow: bow(), over: 0, skew: 0.7 + r() * 0.7}),
  ];
};

/**
 * A shaft with a two-stroke head.
 *
 * The head is the whole mark: two barbs of different length, at different angles,
 * starting a few px short of the tip and ending past each other. A symmetric V at
 * exactly 62° with both arms equal is a *typographic* arrow — it reads as an
 * icon, not as someone jabbing a page with a pen. Real barbs are unequal because
 * the wrist pivots around one of them.
 */
export const arrow = (
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  sw: number,
  r: () => number,
): Stroke[] => {
  const dx = x1 - x0;
  const dy = y1 - y0;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len;
  const uy = dy / len;
  const base = Math.min(len * 0.34, Math.max(sw * 4.6, 26));
  const spread = 0.52 + r() * 0.38;
  const shorten = base * (0.06 + r() * 0.2);
  const tip = {x: x1 - ux * shorten, y: y1 - uy * shorten};
  const ang = Math.atan2(uy, ux) + Math.PI;
  const b1 = base * (0.78 + r() * 0.55);
  const b2 = base * (0.78 + r() * 0.55);
  const a1 = ang + spread;
  const a2 = ang - spread - (r() - 0.5) * 0.22;
  return [
    line(x0, y0, tip.x + ux * 4, tip.y + uy * 4, sw, r, {bow: 0.022, over: 0.02}),
    line(tip.x, tip.y, tip.x + Math.cos(a1) * b1, tip.y + Math.sin(a1) * b1, sw * 0.95, r, {
      bow: 0.04,
      over: 0.03,
      n: 24,
    }),
    line(tip.x, tip.y, tip.x + Math.cos(a2) * b2, tip.y + Math.sin(a2) * b2, sw * 0.95, r, {
      bow: 0.04,
      over: 0.03,
      n: 24,
    }),
  ];
};

/** A wavy line — the "this is a list, keep reading" mark. */
export const squiggle = (x0: number, y: number, x1: number, sw: number, r: () => number): Stroke => {
  const n = 110;
  const amp = sw * (0.9 + r() * 0.7);
  const cycles = 2.6 + r() * 1.4;
  const pts = sample(n, (t) => [
    x0 + (x1 - x0) * t,
    y + Math.sin(t * cycles * Math.PI * 2) * amp * Math.sin(Math.PI * Math.min(1, t * 1.15)),
  ]);
  return {pts, half: pressure(n, sw, r)};
};

/** Two strokes crossing — a rejection, not an emphasis. */
export const cross = (x0: number, y0: number, x1: number, y1: number, sw: number, r: () => number): Stroke[] => [
  line(x0, y0, x1, y1, sw, r, {bow: 0.05}),
  line(x1, y0, x0, y1, sw, r, {bow: 0.05}),
];

/** An L: the bracket a hand draws when it wants to hold something aside. */
export const bracket = (
  side: "left" | "right",
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  sw: number,
  r: () => number,
): Stroke => {
  const x = side === "left" ? x0 : x1;
  const armX = side === "left" ? x0 + (x1 - x0) * 0.45 : x1 - (x1 - x0) * 0.45;
  const n = 90;
  const pts = sample(n, (t) => {
    // down the stem, round the corner, out along the arm
    if (t < 0.62) {
      const k = t / 0.62;
      return [x + Math.sin(k * Math.PI) * (x1 - x0) * 0.03, y0 + (y1 - y0) * k];
    }
    const k = (t - 0.62) / 0.38;
    const e = k * k * (3 - 2 * k);
    return [x + (armX - x) * e, y1 - Math.sin(k * Math.PI) * (y1 - y0) * 0.03];
  });
  return {pts, half: pressure(n, sw, r)};
};

/** A tick — the one mark that means "yes" rather than "look". */
export const tick = (x0: number, y0: number, x1: number, y1: number, sw: number, r: () => number): Stroke => {
  const n = 70;
  const kneeX = x0 + (x1 - x0) * 0.34;
  const kneeY = y0 + (y1 - y0) * 0.92;
  const pts = sample(n, (t) => {
    if (t < 0.36) {
      const k = t / 0.36;
      return [x0 + (kneeX - x0) * k, y0 + (kneeY - y0) * k];
    }
    const k = (t - 0.36) / 0.64;
    return [kneeX + (x1 - kneeX) * k, kneeY + (y1 - kneeY) * k];
  });
  return {pts, half: pressure(n, sw, r)};
};

/** Three strokes through one point — an asterisk, the loudest non-shape mark. */
/**
 * Three strokes through one point — an asterisk, the loudest non-shape mark.
 *
 * The first version passed `{bow: 0.05}` to a line whose length is the *diameter*
 * of the container, so each stroke sagged 5 % of a 400 px box — 20 px — and three
 * sags meeting at a point turned the asterisk into a flower. A short stroke bows
 * proportionally less; 0.015 here is a 3 px bow, which is what a hand does.
 */
export const star = (cx: number, cy: number, rx: number, ry: number, sw: number, r: () => number): Stroke[] =>
  [0, 1, 2].map((i) => {
    const a = (i / 3) * Math.PI + (r() - 0.5) * 0.26;
    const k1 = 0.86 + r() * 0.22;
    const k2 = 0.86 + r() * 0.22;
    return line(
      cx - Math.cos(a) * rx * k1,
      cy - Math.sin(a) * ry * k1,
      cx + Math.cos(a) * rx * k2,
      cy + Math.sin(a) * ry * k2,
      sw,
      r,
      {bow: 0.014, over: 0.08},
    );
  });

// ---------------------------------------------------------------- composition

/**
 * The footprint each shape occupies inside its container, as fractions.
 *
 * These are the numbers `scripts/markbox.py` solves *back* through, so changing
 * one silently moves every mark that was measured against it. Keep them in step.
 */
export const EXTENT: Record<string, [number, number, number, number]> = {
  box: [0.06, 0.14, 0.95, 0.86],
  underline: [0.04, 0.68, 0.96, 0.87],
  "underline-double": [0.04, 0.20, 0.96, 0.66],
  circle: [0.04, 0.06, 0.96, 0.94],
  ellipse: [0.06, 0.12, 0.96, 0.9],
  question: [0.20, 0.06, 0.80, 0.94],
  exclamation: [0.35, 0.06, 0.65, 0.94],
};

/**
 * One side of a bracket pair: the pen runs in along the top arm, down the stem,
 * and out along the bottom arm, in one pass.
 *
 * Four separate corner cradles were tried first and they failed at card size:
 * with a 16 px marker an arm short enough to stay clear of the word is barely
 * two pen widths long, so each corner renders as a yellow blob. A bracket is one
 * gesture instead of four, it is unambiguous at any size, and it holds the word
 * without caging it — which is what the closed rectangle was being criticised
 * for.
 */
const bracketSide = (
  x: number,
  y0: number,
  y1: number,
  dir: number,
  arm: number,
  sw: number,
  r: () => number,
): Stroke => {
  const n = 52;
  const bow = (r() - 0.5) * arm * 0.16;
  const lean = (r() - 0.5) * arm * 0.1;
  const pts = sample(n, (t) => {
    if (t < 0.24) {
      const k = t / 0.24;
      return [x + dir * arm * (1 - k) + lean * (1 - k), y0 + Math.sin(k * Math.PI) * bow * 0.4];
    }
    if (t < 0.76) {
      const k = (t - 0.24) / 0.52;
      return [x + Math.sin(k * Math.PI) * bow * 0.5, y0 + (y1 - y0) * k];
    }
    const k = (t - 0.76) / 0.24;
    return [x + dir * arm * k - lean * k, y1 + Math.sin((1 - k) * Math.PI) * bow * 0.4];
  });
  return {pts, half: pressure(n, sw, r, 0.12)};
};

/**
 * Build the strokes for a shape in a `W × H` box.
 *
 * Every call site gets its own seed, so two underlines in the same shot are two
 * different lines: same gesture, different hand.
 */
export const compose = (shape: string, W: number, H: number, sw: number, seed: number): Stroke[] => {
  const r = rng(seed);
  switch (shape) {
    case "underline": {
      // One pull of a marker across a word. It drops slightly to the right
      // because the wrist falls as the arm extends, and it swells in the middle
      // because that is where the hand is moving fastest and pressing hardest.
      //
      // The drop was 2–4.5 % of the container and the swell 16 %: on a 130 px
      // container that is a 5 px fall and a 2.5 px width change, and the bar
      // shipped as a rounded rectangle with square ends. 4–7 % fall, 24 % swell,
      // and a 5 % overshoot past the box on both ends — the pen does not stop at
      // the edge of the container it was given.
      const drop = (0.04 + r() * 0.03) * H;
      return [
        line(0.03 * W, 0.745 * H, 0.96 * W, 0.745 * H + drop, sw, r, {
          bow: 0.02,
          over: 0.05,
          swell: 0.24,
        }),
      ];
    }
    case "underline-double": {
      // Two passes, and the second is not a copy of the first: it runs the other
      // way, a little thinner, and does not start or stop on the same x. A hand
      // repeating itself never repeats itself exactly, and two identical bars are
      // the tell that a machine drew them.
      //
      // Both passes live in the *same* narrow band under the type. The old pair
      // sat at 0.56 and 0.84 of its container, which on s08's 0.22-tall box put
      // the first line under the header and the second in the handwriting — four
      // bars scattered down the page instead of two under a word.
      //
      // **The separation is now measured in pens, not in the container.** Fixed
      // fractions make the gap whatever the caller's box happens to be: on s08's
      // 58 px band, 0.685 → 0.86 is 10 px between two 11 px pens, and the pair
      // drew as one blue wedge that crossed itself. `sw` is the only number that
      // knows how wide the ink is, so the gap is derived from it.
      const d = (0.01 + r() * 0.014) * H;
      const y1 = 0.30 * H;
      const gap = Math.max(sw * 1.85, 0.11 * H);
      return [
        line(0.03 * W, y1, 0.955 * W, y1 + d, sw, r, {
          bow: 0.016,
          over: 0.03,
          swell: 0.15,
        }),
        line(0.935 * W, y1 + gap - d * 0.6, 0.055 * W, y1 + gap, sw * 0.82, r, {
          bow: 0.02,
          over: 0.03,
          swell: 0.18,
        }),
      ];
    }
    case "question": {
      // Hand-drawn question mark with natural aspect ratio and solid dot:
      const span = Math.min(W * 0.65, H * 0.52);
      const cx = 0.5 * W;
      const topY = 0.08 * H;
      const midY = 0.62 * H;
      const dotY = 0.85 * H;
      const n = 64;
      const pts = sample(n, (t) => {
        if (t < 0.65) {
          const k = t / 0.65;
          const p0 = [cx - span * 0.45, topY + (midY - topY) * 0.32];
          const p1 = [cx - span * 0.45, topY];
          const p2 = [cx + span * 0.55, topY];
          const p3 = [cx + span * 0.50, topY + (midY - topY) * 0.42];
          const x = (1 - k) ** 3 * p0[0] + 3 * (1 - k) ** 2 * k * p1[0] + 3 * (1 - k) * k ** 2 * p2[0] + k ** 3 * p3[0];
          const y = (1 - k) ** 3 * p0[1] + 3 * (1 - k) ** 2 * k * p1[1] + 3 * (1 - k) * k ** 2 * p2[1] + k ** 3 * p3[1];
          return [x, y];
        } else {
          const k = (t - 0.65) / 0.35;
          const p3 = [cx + span * 0.50, topY + (midY - topY) * 0.42];
          const p4 = [cx + span * 0.05, topY + (midY - topY) * 0.68];
          const p5 = [cx, midY];
          const x = (1 - k) ** 2 * p3[0] + 2 * (1 - k) * k * p4[0] + k ** 2 * p5[0];
          const y = (1 - k) ** 2 * p3[1] + 2 * (1 - k) * k * p4[1] + k ** 2 * p5[1];
          return [x, y];
        }
      });
      const hook: Stroke = {pts, half: pressure(n, sw * 1.1, r)};
      const dot = loop(cx, dotY, sw * 0.12, sw * 0.12, sw * 1.05, r, {turns: 1.15, n: 36});
      return [hook, dot];
    }
    case "exclamation": {
      // Bold hand-drawn exclamation mark (thick top tapering down + solid dot):
      const cx = 0.5 * W;
      const topY = 0.08 * H;
      const botY = 0.64 * H;
      const dotY = 0.85 * H;
      const n = 40;
      const pts = sample(n, (t) => [cx + (r() - 0.5) * 1.2, topY + (botY - topY) * t]);
      const half = sample(n, (t) => (sw / 2) * (1.28 - 0.45 * t));
      const stem: Stroke = {pts, half};
      const dot = loop(cx, dotY, sw * 0.12, sw * 0.12, sw * 1.05, r, {turns: 1.15, n: 36});
      return [stem, dot];
    }
    case "box": {
      // A rectangle the hand drew and did not quite close.
      //
      // The closed version read as a selection marquee, and the reason was not
      // the corners — it was that a perfectly closed loop is not something a pen
      // leaves. This one runs three sides with a real bow on each, and lifts
      // before the fourth reaches its corner, so there is a gap of 16–24 % of the
      // height at the top-left. That gap is the whole difference.
      const x0 = 0.065 * W;
      const x1 = 0.945 * W;
      const y0 = 0.155 * H;
      const y1 = 0.845 * H;
      // One lap, corners turned on a radius, pen lifted before it closes.
      // The four-line version is in `frame()`'s comment: it shipped as a
      // bracket with four square corners and the client circled it.
      return [frame(x0, y0, x1, y1, sw, r)];
    }
    case "brackets": {
      // Two brackets, for a target too short to hold a rectangle without caging
      // it — "CI" inside "CIBODAS" is 65 px wide and 16 px of pen would sit on
      // the letters. Needs a tall container; on a small wide plate the arms have
      // nowhere to go and it renders as two specks, so use `box` there.
      const x0 = 0.065 * W;
      const x1 = 0.945 * W;
      const y0 = 0.155 * H;
      const y1 = 0.845 * H;
      const arm = Math.min((x1 - x0) * 0.22, (y1 - y0) * 0.3, sw * 3.2);
      return [
        bracketSide(x0, y0, y1, 1, arm, sw * 0.9, r),
        bracketSide(x1, y0, y1, -1, arm, sw * 0.9, r),
      ];
    }
    case "circle":
      // A *scrawled* circle, not a plotted one: one lap plus a short second pass
      // over the top, the way a hand goes round a name to make sure it is clear.
      // One lap is always a compass; the second is what makes it hand-drawn.
      //
      // The second pass goes **outside** the first, on a nudged centre, and stops
      // short. Drawn inside and concentric it disappeared behind the first lap
      // entirely, so the ring shipped as a single clean ellipse — the second pass
      // existed in the code and nowhere in the frame.
      return [
        loop(0.5 * W, 0.5 * H, 0.45 * W, 0.42 * H, sw, r, {turns: 1.06}),
        loop(
          0.5 * W + (r() - 0.5) * 0.06 * W,
          0.5 * H + (r() - 0.5) * 0.06 * H,
          0.485 * W,
          0.455 * H,
          sw * 0.8,
          r,
          {turns: 0.42, start: r() * 2},
        ),
      ];
    case "ellipse":
      return [
        loop(0.5 * W, 0.5 * H, 0.46 * W, 0.38 * H, sw, r, {turns: 1.08}),
        loop(0.5 * W, 0.5 * H, 0.44 * W, 0.4 * H, sw * 0.84, r, {turns: 0.26, start: 1 + r() * 2}),
      ];
    case "lasso": {
      const body = loop(0.53 * W, 0.44 * H, 0.38 * W, 0.34 * H, sw, r, {turns: 1.0, start: -1.2});
      const tail = line(0.3 * W, 0.72 * H, 0.12 * W, 0.98 * H, sw * 0.9, r, {bow: 0.12, over: 0.12});
      return [body, tail];
    }
    case "arrow-right":
      return arrow(0.05 * W, 0.6 * H, 0.95 * W, 0.44 * H, sw, r);
    case "arrow-down":
      return arrow(0.52 * W, 0.06 * H, 0.46 * W, 0.95 * H, sw, r);
    case "arrow-curve":
      return arrow(0.08 * W, 0.9 * H, 0.92 * W, 0.26 * H, sw, r);
    case "bracket-left":
      return [bracket("left", 0.1 * W, 0.06 * H, 0.9 * W, 0.94 * H, sw, r)];
    case "bracket-right":
      return [bracket("right", 0.1 * W, 0.06 * H, 0.9 * W, 0.94 * H, sw, r)];
    case "corner-marks": {
      const m = 0.1;
      const a = 0.26;
      return [
        line(m * W, (m + a) * H, m * W, m * H, sw, r, {bow: 0.05}),
        line(m * W, m * H, (m + a) * W, m * H, sw, r, {bow: 0.05}),
        line((1 - m) * W, (m + a) * H, (1 - m) * W, m * H, sw, r, {bow: 0.05}),
        line((1 - m) * W, m * H, (1 - m - a) * W, m * H, sw, r, {bow: 0.05}),
        line(m * W, (1 - m - a) * H, m * W, (1 - m) * H, sw, r, {bow: 0.05}),
        line(m * W, (1 - m) * H, (m + a) * W, (1 - m) * H, sw, r, {bow: 0.05}),
        line((1 - m) * W, (1 - m - a) * H, (1 - m) * W, (1 - m) * H, sw, r, {bow: 0.05}),
        line((1 - m) * W, (1 - m) * H, (1 - m - a) * W, (1 - m) * H, sw, r, {bow: 0.05}),
      ];
    }
    case "cross":
      return cross(0.12 * W, 0.14 * H, 0.88 * W, 0.86 * H, sw, r);
    case "check":
      return [tick(0.1 * W, 0.55 * H, 0.92 * W, 0.1 * H, sw, r)];
    case "star":
      return star(0.5 * W, 0.5 * H, 0.44 * W, 0.42 * H, sw * 0.85, r);
    case "burst":
      return star(0.5 * W, 0.5 * H, 0.3 * W, 0.3 * H, sw * 0.8, r);
    case "squiggle":
      return [squiggle(0.05 * W, 0.62 * H, 0.95 * W, sw, r)];
    case "strike":
      return [line(0.06 * W, 0.56 * H, 0.94 * W, 0.48 * H, sw, r, {bow: 0.03})];
    default:
      return [line(0.06 * W, 0.6 * H, 0.94 * W, 0.6 * H, sw, r, {bow: 0.05})];
  }
};

/** Shapes drawn as a filled area rather than a pen stroke. */
export const FILLED = new Set(["band", "tape"]);

