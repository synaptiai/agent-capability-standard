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

/**
 * Silhouette families for the glyph sheet's headings (visual spec 5.2): the
 * outline a glyph is built on, so shapes a reader could confuse sit under
 * one heading. Families are listed in sheet order; a grid named in no family
 * goes under the last heading, "Other shapes", so a new glyph shows on the
 * sheet before anyone files it.
 */
export const GLYPH_FAMILIES: readonly { title: string; keys: readonly string[] }[] = [
  { title: 'Layers', keys: ['PERCEIVE', 'UNDERSTAND', 'REASON', 'MODEL', 'SYNTHESIZE', 'EXECUTE', 'VERIFY', 'REMEMBER', 'COORDINATE'] },
  {
    title: 'Frames and boxes',
    keys: [
      'nested', 'note', 'copy', 'status:proposed', 'empty', 'folder', 'group', 'skill:capability', 'flow:store', 'flow:read',
      'policy:always', 'type:boolean', 'type:list', 'type:record', 'status:candidate', 'fail:request_more_context',
      'tool:executor', 'source:system_log', 'source:document', 'section:rfcs', 'section:spec', 'chapter:scope',
      'domain:multimodal', 'domain:personal_assistant', 'group:skill-authoring',
    ],
  },
  {
    title: 'Arrows and chevrons',
    keys: [
      'chevron-left', 'chevron-right', 'mark:requires', 'mark:soft_requires', 'mark:enables', 'mark:precedes', 'mark:conflicts_with',
      'mark:alternative_to', 'undo', 'external', 'gate:end', 'gate:skip', 'fail:escalate', 'source:api', 'status:superseded', 'code',
    ],
  },
  {
    title: 'Crosses, stars and rays',
    keys: ['close', 'status:rejected', 'type:open', 'sun', 'hash', 'status:analysis', 'chapter:design-principles', 'domain:healthcare'],
  },
  {
    title: 'Bars and stacks',
    keys: [
      'menu', 'risk:low', 'risk:medium', 'risk:high', 'status:normative', 'fail:pause_and_checkpoint', 'count:layers',
      'source:database', 'chapter:canonical-schemas', 'domain:data_analysis', 'domain:audio', 'section:workflows',
      'section:capabilities', 'section:background', 'principle:safety-by-construction',
    ],
  },
  {
    title: 'Rings and round shapes',
    keys: [
      'eye', 'half', 'moon', 'stop', 'caution', 'search', 'section:domains', 'domain:vision', 'domain:manufacturing', 'source:sensor',
      'group:standard-cert', 'chapter:identity-resolution-policy',
    ],
  },
  {
    title: 'Triangles, wedges and diamonds',
    keys: ['warning', 'diamond', 'mark:specializes', 'status:historical', 'tool:validator', 'tool:conformance', 'group:methodology'],
  },
  {
    title: 'Objects',
    keys: [
      'flag', 'pencil', 'status:draft', 'stamp', 'check', 'status:accepted', 'approve:blocked', 'status:reference',
      'status:normative-reference', 'agent:general-purpose', 'type:text', 'type:number', 'fork', 'flow:join', 'source:human',
      'tool:plugin', 'tool:sdk', 'section:start', 'section:guides', 'section:compliance', 'section:community', 'chapter:terms',
      'chapter:authority-trust-model', 'chapter:diagnostic-model', 'chapter:versioning-and-compatibility',
      'chapter:decision-frameworks', 'principle:grounded-claims', 'principle:auditable-transforms', 'principle:composable-atoms',
      'principle:explicit-contracts', 'group:regulation',
    ],
  },
];

export interface SheetFamily {
  title: string;
  glyphs: SheetGlyph[];
}

/**
 * Every 7x7 and 9x9 grid under its family heading, each family in
 * nearest-neighbour order (silhouetteOrder), and the grids no family names
 * under "Other shapes" at the end. A key a family names that has no grid is
 * dropped.
 */
export function familyOrder(
  grids: Readonly<Record<string, readonly string[]>> = ALL_GRIDS,
  families: readonly { title: string; keys: readonly string[] }[] = GLYPH_FAMILIES,
): SheetFamily[] {
  const sized = (k: string) => k in grids && (grids[k]!.length === 7 || grids[k]!.length === 9);
  const placed = new Set<string>();
  const out: SheetFamily[] = [];
  for (const f of families) {
    const keys = f.keys.filter((k) => sized(k) && !placed.has(k));
    keys.forEach((k) => placed.add(k));
    if (keys.length > 0) out.push({ title: f.title, glyphs: silhouetteOrder(Object.fromEntries(keys.map((k) => [k, grids[k]!]))) });
  }
  const rest = Object.keys(grids).filter((k) => sized(k) && !placed.has(k));
  if (rest.length > 0) out.push({ title: 'Other shapes', glyphs: silhouetteOrder(Object.fromEntries(rest.map((k) => [k, grids[k]!]))) });
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
