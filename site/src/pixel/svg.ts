// Lookup and SVG output for the grids in glyphs.ts.
import { parseGrid, toRects, type Grid, type Paint, type Rect } from './grid';
import { MARK } from './glyphs';
import { ALL_GRIDS, resolveGlyphKey } from './keys';

const GRIDS: ReadonlyMap<string, Grid> = new Map(Object.entries(ALL_GRIDS).map(([name, rows]) => [name, parseGrid(name, rows)]));

/** Every drawn grid's name: the layer ids, the inline glyphs, then the concept glyphs. */
export const GLYPH_NAMES: readonly string[] = [...GRIDS.keys()];

/** The grid for a glyph key, following GLYPH_ALIASES (so `gate:stop` draws `stop`). */
export function glyph(name: string): Grid {
  const key = resolveGlyphKey(name);
  const g = key === null ? undefined : GRIDS.get(key);
  if (!g) throw new Error(`pixel: no glyph named ${name}`);
  return g;
}

export const MARK_GRID: Grid = parseGrid('mark', MARK);

/** SVG attributes that paint a rectangle with the page's tokens. */
export function paintAttrs(paint: Paint): Record<string, string> {
  switch (paint) {
    case 'fg':
      return { fill: 'currentColor' };
    case 'fg2':
      return { fill: 'currentColor', 'fill-opacity': '0.35' };
    case 'accent':
      return { style: 'fill: var(--accent)' };
    case 'bg':
      return { style: 'fill: var(--bg)' };
  }
}

export interface PlacedRect extends Rect {
  attrs: Record<string, string>;
}

export function placedRects(grid: Grid): PlacedRect[] {
  return toRects(grid).map((r) => ({ ...r, attrs: paintAttrs(r.paint) }));
}

/** The rectangles of a grid as SVG markup, painted with fixed colours (for files outside the page). */
export function rectsMarkup(rects: Rect[], colours: Record<Paint, string>, dx = 0, dy = 0): string {
  return rects
    .map((r) => `<rect x="${r.x + dx}" y="${r.y + dy}" width="${r.w}" height="${r.h}" fill="${colours[r.paint]}"/>`)
    .join('');
}
