/**
 * Shared look-and-feel for the Vox cutout-collage style.
 *
 * Everything here is a CSS `filter` string, because the whole style is built on
 * drop-shadows: a cutout gets a thick coloured outline (stacked shadows in 8
 * directions) plus one soft contact shadow. Filters follow the PNG's alpha, so
 * the outline traces the real silhouette rather than a bounding box.
 */

export const YELLOW = "#F2C200";
export const INK = "#1A1A1A";
export const PAPER = "#EFE7D6";

/**
 * Thick outline that hugs the alpha edge.
 *
 * Eight hard shadows in a ring produce a stroke that follows every torn corner
 * and screw hole. More directions = rounder corners but a heavier render; 8 is
 * the practical sweet spot for 1080p.
 */
export const outline = (px = 5, color: string = YELLOW): string => {
  const d = px * 0.7;
  return [
    `drop-shadow(${px}px 0 0 ${color})`,
    `drop-shadow(${-px}px 0 0 ${color})`,
    `drop-shadow(0 ${px}px 0 ${color})`,
    `drop-shadow(0 ${-px}px 0 ${color})`,
    `drop-shadow(${d}px ${d}px 0 ${color})`,
    `drop-shadow(${-d}px ${d}px 0 ${color})`,
    `drop-shadow(${d}px ${-d}px 0 ${color})`,
    `drop-shadow(${-d}px ${-d}px 0 ${color})`,
  ].join(" ");
};

/** Soft shadow that makes a cutout sit on the paper. */
export const contactShadow = (y = 10, blur = 18, alpha = 0.28): string =>
  `drop-shadow(0 ${y}px ${blur}px rgba(0,0,0,${alpha}))`;

/** Outline + contact shadow — the default look for a paper element. */
export const cutoutLook = (px = 5, color: string = YELLOW): string =>
  `${outline(px, color)} ${contactShadow()}`;

/**
 * Die-cut sticker border built from filters.
 *
 * **Do not use this at render time.** It stacks 17 drop-shadows, which Chrome
 * cannot keep on the GPU; measured at 213 s for a single 1080p frame. Bake the
 * white margin into the PNG with `scripts/sticker_border.py` instead and use
 * `cutoutLook` for the keyline. Kept here only to document the trap.
 */
export const stickerLook = (border = 12, px = 5): string =>
  `${outline(border, "#FFFFFF")} ${outline(px, YELLOW)} ${contactShadow(14, 22, 0.32)}`;

/**
 * Lift a cutout off the page during a move. `depth` 0 = flat, 1 = mid-air.
 * Scale the numbers, not the shadow count — CSS has no blur animation here.
 */
export const liftShadow = (depth: number): string =>
  contactShadow(8 + 26 * depth, 16 + 34 * depth, 0.22 + 0.18 * depth);
