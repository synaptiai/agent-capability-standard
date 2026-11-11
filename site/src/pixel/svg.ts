// Lookup and SVG output for the grids in glyphs.ts.
import { parseGrid, toRects, type Grid, type Paint, type Rect } from './grid';
import { LAYER_GLYPHS, MARK, UI_GLYPHS } from './glyphs';

const GRIDS: ReadonlyMap<string, Grid> = new Map(
  [...Object.entries(LAYER_GLYPHS), ...Object.entries(UI_GLYPHS)].map(([name, rows]) => [name, parseGrid(name, rows)]),
);

/** Every glyph name: the layer ids, then the UI glyphs. */
export const GLYPH_NAMES: readonly string[] = [...GRIDS.keys()];

export function glyph(name: string): Grid {
  const g = GRIDS.get(name);
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
