// Rect geometry shared by the figures (visual spec 1.2 and 2.4): straight
// runs, dashed and dotted runs, 3-step chevrons, brackets for lanes, glyphs
// placed inside a larger SVG, and the line style of each edge type. Every
// figure draws with these, so a diagram is made of the same rects as a glyph.
// Lines are axis-aligned; there are no diagonals, curves or dash arrays.
import type { Paint } from './grid';
import { glyph, placedRects } from './svg';

/** One rect of a figure, in CSS pixels. `ink` names the token it is painted with. */
export interface FigRect {
  x: number;
  y: number;
  w: number;
  h: number;
  ink: Ink;
}

/** The paints a figure rect may use: the text inks for lines, --bg for knock-outs, --accent for the current item. */
export type Ink = 'ink' | 'ink-2' | 'ink-3' | 'bg' | 'accent' | 'current';

/** Attributes for a FigRect: the colour comes from a token, never a hex value. */
export function inkAttrs(ink: Ink): Record<string, string> {
  if (ink === 'current') return { fill: 'currentColor' };
  return { style: `fill: var(--${ink})` };
}

/** The 2px line weight (--px) and the 4px emphasis weight. */
export const PX = 2;
export const HEAVY = 4;

export type Pattern = 'solid' | 'dashed' | 'dotted';

/** On and off lengths of a pattern: dashed is 6 on, 4 off; dotted is 2 on, 4 off. */
const DASH: Record<Exclude<Pattern, 'solid'>, [number, number]> = { dashed: [6, 4], dotted: [2, 4] };

/**
 * A horizontal or vertical run from (x1, y1) to (x2, y2), `weight` thick,
 * centred on the line. Throws on a diagonal.
 */
export function run(x1: number, y1: number, x2: number, y2: number, ink: Ink, weight = PX, pattern: Pattern = 'solid'): FigRect[] {
  if (x1 !== x2 && y1 !== y2) throw new Error(`lines: a run must be horizontal or vertical, got (${x1},${y1})-(${x2},${y2})`);
  const horizontal = y1 === y2;
  const from = horizontal ? Math.min(x1, x2) : Math.min(y1, y2);
  const len = horizontal ? Math.abs(x2 - x1) : Math.abs(y2 - y1);
  const half = weight / 2;
  const seg = (start: number, length: number): FigRect =>
    horizontal ? { x: start, y: y1 - half, w: length, h: weight, ink } : { x: x1 - half, y: start, w: weight, h: length, ink };
  if (len === 0) return [];
  if (pattern === 'solid') return [seg(from, len)];
  const [on, off] = DASH[pattern];
  const out: FigRect[] = [];
  for (let s = 0; s < len; s += on + off) out.push(seg(from + s, Math.min(on, len - s)));
  return out;
}

/** An orthogonal polyline through `points`, as runs. */
export function polyline(points: readonly (readonly [number, number])[], ink: Ink, weight = PX, pattern: Pattern = 'solid'): FigRect[] {
  const out: FigRect[] = [];
  for (let i = 1; i < points.length; i++) {
    const [ax, ay] = points[i - 1]!;
    const [bx, by] = points[i]!;
    out.push(...run(ax, ay, bx, by, ink, weight, pattern));
  }
  return out;
}

export type Direction = 'right' | 'left' | 'down' | 'up';

/**
 * A 3-step pixel chevron whose tip is at (x, y), pointing `dir`. Each step is
 * a `cell`-sized square, so the chevron is 3 cells deep and 5 cells across.
 */
export function chevron(x: number, y: number, dir: Direction, ink: Ink, cell = PX): FigRect[] {
  const steps: [number, number][] = [
    [0, 0],
    [-1, -1],
    [-1, 1],
    [-2, -2],
    [-2, 2],
  ];
  return steps.map(([back, side]) => {
    const along = back * cell;
    const across = side * cell;
    const [dx, dy] =
      dir === 'right' ? [along, across] : dir === 'left' ? [-along, across] : dir === 'down' ? [across, along] : [across, -along];
    return { x: x + dx - cell / 2, y: y + dy - cell / 2, w: cell, h: cell, ink };
  });
}

/** A hollow 5x5-cell triangle whose tip is at (x, y), pointing `dir` (the specializes end mark). */
export function hollowTriangle(x: number, y: number, dir: Direction, ink: Ink, cell = PX): FigRect[] {
  // Rows back from the tip: 1 cell, then 3 with a hole, then the 5-cell base.
  const rows: [number, number[]][] = [
    [0, [0]],
    [1, [-1, 1]],
    [2, [-2, -1, 0, 1, 2]],
  ];
  const out: FigRect[] = [];
  for (const [back, sides] of rows) {
    for (const side of sides) {
      const along = back * cell;
      const across = side * cell;
      const [dx, dy] =
        dir === 'right' ? [-along, across] : dir === 'left' ? [along, across] : dir === 'down' ? [across, -along] : [across, along];
      out.push({ x: x + dx - cell / 2, y: y + dy - cell / 2, w: cell, h: cell, ink });
    }
  }
  return out;
}

/**
 * A lane bracket from y1 to y2 at x: a vertical run with a tick pointing at
 * the rows on `side` at each end. Used for checkpoint and rollback lanes.
 */
export function bracket(x: number, y1: number, y2: number, side: 'left' | 'right', ink: Ink, tick = 6, weight = PX): FigRect[] {
  const t = side === 'right' ? tick : -tick;
  return [...run(x, y1, x, y2, ink, weight), ...run(x, y1, x + t, y1, ink, weight), ...run(x, y2, x + t, y2, ink, weight)];
}

/** Lane width in CSS pixels (visual spec 3.0, Lane). */
export const LANE_W = 8;

/**
 * x offsets of the lanes that are drawn: a lane is drawn only when at least
 * one row uses it. Lanes are laid out left to right in the given order from
 * `x0`, `width` apart. Unused lanes are absent from the result.
 */
export function laneOffsets(lanes: readonly { id: string; used: boolean }[], x0 = 0, width = LANE_W): Map<string, number> {
  const out = new Map<string, number>();
  let x = x0;
  for (const l of lanes) {
    if (!l.used) continue;
    out.set(l.id, x);
    x += width;
  }
  return out;
}

const PAINT_INK: Record<Paint, Ink> = { fg: 'current', fg2: 'current', accent: 'accent', bg: 'bg' };

/**
 * A glyph's rects placed at (x, y) at `scale` pixels per cell, for drawing
 * inside a figure's SVG. `=` cells keep their 35% opacity through `opacity`.
 */
export function glyphRects(name: string, x: number, y: number, scale = PX): (FigRect & { opacity?: number })[] {
  return placedRects(glyph(name)).map((r) => ({
    x: x + r.x * scale,
    y: y + r.y * scale,
    w: r.w * scale,
    h: r.h * scale,
    ink: PAINT_INK[r.paint],
    ...(r.paint === 'fg2' ? { opacity: 0.35 } : {}),
  }));
}

/** How an edge type is drawn in a diagram (visual spec 2.4). */
export interface EdgeStyle {
  weight: number;
  pattern: Pattern;
  ink: Ink;
  /** The mark at the `to` end; `both` puts a chevron at each end. */
  end: 'chevron' | 'triangle' | 'both' | 'none';
  /** conflicts_with is broken at its midpoint by its mark. */
  midMark: boolean;
}

export const EDGE_STYLES: Readonly<Record<string, EdgeStyle>> = {
  requires: { weight: HEAVY, pattern: 'solid', ink: 'ink', end: 'chevron', midMark: false },
  soft_requires: { weight: PX, pattern: 'dashed', ink: 'ink-2', end: 'chevron', midMark: false },
  enables: { weight: PX, pattern: 'solid', ink: 'ink-2', end: 'chevron', midMark: false },
  precedes: { weight: PX, pattern: 'dotted', ink: 'ink-2', end: 'chevron', midMark: false },
  specializes: { weight: PX, pattern: 'solid', ink: 'ink-2', end: 'triangle', midMark: false },
  alternative_to: { weight: PX, pattern: 'solid', ink: 'ink-2', end: 'both', midMark: false },
  conflicts_with: { weight: PX, pattern: 'solid', ink: 'ink', end: 'none', midMark: true },
};

export function edgeStyle(type: string): EdgeStyle {
  const s = EDGE_STYLES[type];
  if (!s) throw new Error(`lines: no line style for edge type ${type}`);
  return s;
}

/**
 * A straight edge of `type` from (x1, y1) to (x2, y2), horizontal or
 * vertical, in its 2.4 style, with its end marks. A conflicts_with edge
 * leaves a 14px gap at its midpoint for its 2x mark, which the caller draws
 * at `mid`.
 */
export function edgeRects(type: string, x1: number, y1: number, x2: number, y2: number): { rects: FigRect[]; mid: [number, number] } {
  const s = edgeStyle(type);
  const horizontal = y1 === y2;
  const dir: Direction = horizontal ? (x2 >= x1 ? 'right' : 'left') : y2 >= y1 ? 'down' : 'up';
  const back: Record<Direction, Direction> = { right: 'left', left: 'right', down: 'up', up: 'down' };
  const mid: [number, number] = [(x1 + x2) / 2, (y1 + y2) / 2];
  const rects: FigRect[] = [];
  if (s.midMark) {
    const gap = 9;
    const [ax, ay, bx, by] = horizontal ? [mid[0] - gap, y1, mid[0] + gap, y2] : [x1, mid[1] - gap, x2, mid[1] + gap];
    rects.push(...run(x1, y1, ax, ay, s.ink, s.weight), ...run(bx, by, x2, y2, s.ink, s.weight));
  } else {
    rects.push(...run(x1, y1, x2, y2, s.ink, s.weight, s.pattern));
  }
  const cell = s.weight === HEAVY ? HEAVY : PX;
  if (s.end === 'chevron' || s.end === 'both') rects.push(...chevron(x2, y2, dir, s.ink, cell));
  if (s.end === 'both') rects.push(...chevron(x1, y1, back[dir], s.ink, cell));
  if (s.end === 'triangle') rects.push(...hollowTriangle(x2, y2, dir, s.ink, cell));
  return { rects, mid };
}
