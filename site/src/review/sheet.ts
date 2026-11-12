// Data for the glyph sheet (visual spec 5.2): every grid, ordered so that
// similar shapes sit next to each other, the closest pairs by mask distance,
// and the reuse aliases.
import { GLYPH_ALIASES } from '../pixel/glyphs';
import { gridMask, gridPairs, maskDistance, type GridPair } from '../pixel/grid';
import { ALL_GRIDS } from '../pixel/keys';

/** Where review pages are built: under dist/_review/, never deployed (see .github/workflows/site.yml). */
export { REVIEW_DIR } from '../lib/review';

export interface SheetGlyph {
  key: string;
  size: number;
  /** Mask distance to the glyph before it in the order (null for the first). */
  stepDistance: number | null;
}

/**
 * Every grid in a nearest-neighbour chain: start from the first layer glyph,
 * then repeatedly take the unplaced grid closest to the last placed one (ties
 * by key). Similar silhouettes end up side by side, which is what the sheet
 * is for.
 */
export function silhouetteOrder(grids: Readonly<Record<string, readonly string[]>> = ALL_GRIDS): SheetGlyph[] {
  const entries = Object.entries(grids).filter(([, rows]) => rows.length === 7 || rows.length === 9);
  const masks = new Map(entries.map(([k, rows]) => [k, gridMask(rows, 9)]));
  const left = new Set(masks.keys());
  const out: SheetGlyph[] = [];
  let current = entries[0]![0];
  left.delete(current);
  out.push({ key: current, size: grids[current]!.length, stepDistance: null });
  while (left.size > 0) {
    let best: string | null = null;
    let bestD = Infinity;
    for (const k of [...left].sort()) {
      const d = maskDistance(masks.get(current)!, masks.get(k)!);
      if (d < bestD) {
        best = k;
        bestD = d;
      }
    }
    left.delete(best!);
    out.push({ key: best!, size: grids[best!]!.length, stepDistance: bestD });
    current = best!;
  }
  return out;
}

/** The `n` pairs closest to their minimum distance (visual spec 2.1), closest first. */
export function closestPairs(n = 20): GridPair[] {
  return gridPairs(ALL_GRIDS).slice(0, n);
}

/** Alias key and the grid it draws with, sorted by key. */
export function aliasRows(): { key: string; grid: string }[] {
  return Object.entries(GLYPH_ALIASES)
    .map(([key, grid]) => ({ key, grid }))
    .sort((a, b) => a.key.localeCompare(b.key));
}
