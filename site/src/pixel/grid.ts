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
