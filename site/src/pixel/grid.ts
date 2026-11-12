// Pixel art stored as rows of characters, turned into SVG rectangles at build
// time. This module has no imports, so the check scripts can load it with
// plain `node` as well as through Vite.
//
// Characters:
//   '.'  empty
//   '#'  fg      currentColor
//   '='  fg2     currentColor at a lower opacity
//   'a'  accent  the accent fill
//   'o'  bg      the page colour (punches a hole over a fill)

export type Paint = 'fg' | 'fg2' | 'accent' | 'bg';

export interface Grid {
  id: string;
  w: number;
  h: number;
  rows: readonly string[];
}

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
  paint: Paint;
}

const PAINTS: Readonly<Record<string, Paint>> = { '#': 'fg', '=': 'fg2', a: 'accent', o: 'bg' };

/**
 * Check a grid and return it with its size. Throws when it has no rows, rows
 * of different widths, an unknown character, or no painted cell.
 */
export function parseGrid(id: string, rows: readonly string[]): Grid {
  if (rows.length === 0) throw new Error(`grid ${id}: no rows`);
  const w = rows[0]!.length;
  if (w === 0) throw new Error(`grid ${id}: empty row`);
  rows.forEach((row, y) => {
    if (row.length !== w) throw new Error(`grid ${id}: row ${y + 1} is ${row.length} wide, expected ${w}`);
    for (const ch of row) {
      if (ch !== '.' && !(ch in PAINTS)) throw new Error(`grid ${id}: row ${y + 1} has an unknown character "${ch}"`);
    }
  });
  if (rows.every((row) => /^\.+$/.test(row))) throw new Error(`grid ${id}: nothing is painted`);
  return { id, w, h: rows.length, rows };
}

/**
 * The rectangles that draw a grid. Runs of one character in a row become one
 * rectangle; then rectangles in consecutive rows with the same x, width and
 * paint are joined. Sorted by y, then x.
 */
export function toRects(grid: Grid): Rect[] {
  const done: Rect[] = [];
  let open: Rect[] = [];
  grid.rows.forEach((row, y) => {
    const runs: Rect[] = [];
    let x = 0;
    while (x < row.length) {
      const ch = row[x]!;
      let end = x + 1;
      while (end < row.length && row[end] === ch) end++;
      const paint = PAINTS[ch];
      if (paint) runs.push({ x, y, w: end - x, h: 1, paint });
      x = end;
    }
    const next: Rect[] = [];
    for (const r of runs) {
      const above = open.find((o) => o.x === r.x && o.w === r.w && o.paint === r.paint && o.y + o.h === y);
      if (above) {
        above.h += 1;
        next.push(above);
      } else next.push(r);
    }
    for (const o of open) if (!next.includes(o)) done.push(o);
    open = next;
  });
  done.push(...open);
  return done.sort((a, b) => a.y - b.y || a.x - b.x);
}

// ------------------------------------------------------------ distinctness

/**
 * The foreground mask of a grid centred in a square frame of `size` cells:
 * true where the cell is `#`, `=` or `a` (`o` and `.` are off). A grid wider
 * or taller than the frame is an error.
 */
export function gridMask(rows: readonly string[], size: number): boolean[] {
  const h = rows.length;
  const w = rows[0]?.length ?? 0;
  if (w > size || h > size) throw new Error(`grid of ${w}x${h} does not fit a ${size}x${size} frame`);
  const ox = Math.floor((size - w) / 2);
  const oy = Math.floor((size - h) / 2);
  const out: boolean[] = new Array(size * size).fill(false);
  rows.forEach((row, y) => {
    for (let x = 0; x < row.length; x++) {
      const ch = row[x]!;
      if (ch === '#' || ch === '=' || ch === 'a') out[(y + oy) * size + x + ox] = true;
    }
  });
  return out;
}

/** The number of cells two masks of the same size disagree on. */
export function maskDistance(a: readonly boolean[], b: readonly boolean[]): number {
  if (a.length !== b.length) throw new Error('masks of different sizes');
  let d = 0;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) d++;
  return d;
}

/**
 * Minimum mask distances between two glyph grids (visual spec 2.1): two 7x7
 * grids, two 9x9 grids, and a 7x7 grid centred in a 9x9 frame against a 9x9
 * grid.
 */
export const MIN_DISTANCE = { inline: 10, concept: 14, mixed: 12 } as const;

export interface GridPair {
  a: string;
  b: string;
  distance: number;
  /** The distance this pair must reach. */
  min: number;
}

/**
 * Every pair of the named grids with its mask distance and the minimum it
 * must reach, closest first (ties by name). Grids of other sizes than 7x7 and
 * 9x9 are skipped.
 */
export function gridPairs(grids: Readonly<Record<string, readonly string[]>>): GridPair[] {
  const sized = Object.entries(grids)
    .map(([name, rows]) => ({ name, size: rows.length === (rows[0]?.length ?? 0) ? rows.length : 0, rows }))
    .filter((g) => g.size === 7 || g.size === 9)
    .map((g) => ({ ...g, mask: gridMask(g.rows, 9) }));
  const out: GridPair[] = [];
  for (let i = 0; i < sized.length; i++) {
    for (let j = i + 1; j < sized.length; j++) {
      const a = sized[i]!;
      const b = sized[j]!;
      const min = a.size === 7 && b.size === 7 ? MIN_DISTANCE.inline : a.size === 9 && b.size === 9 ? MIN_DISTANCE.concept : MIN_DISTANCE.mixed;
      out.push({ a: a.name, b: b.name, distance: maskDistance(a.mask, b.mask), min });
    }
  }
  return out.sort((p, q) => p.distance - p.min - (q.distance - q.min) || p.distance - q.distance || p.a.localeCompare(q.a) || p.b.localeCompare(q.b));
}
