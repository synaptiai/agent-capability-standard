// Data and captions for the figures of the section index pages, the RFC
// index and the schemas page (visual spec 3.11). The pages and their Markdown
// copies both read these, so the words agree.
import { readRepoFile } from './repo';
import type { Route } from './routes';
import type { RfcRow } from './rfcs';
import { statusStyle } from './status';
import type { SchemaEntry } from './views';

// ------------------------------------------------------------ F-R1

export interface RfcLane {
  /** The Target line as written, or null for the "No target" lane. */
  target: string | null;
  /** The Standard version the target names, if any. */
  version: string | null;
  /** The page of that Standard version, when the site has one. */
  url: string | null;
  rfcs: (RfcRow & { tile: string; style: string })[];
}

const versionKey = (v: string) => v.split('.').map((n) => n.padStart(6, '0')).join('.');

/** A tile's label: the RFC number, or the first word of an unnumbered row's title (visual spec 3.11). */
export function rfcTileLabel(r: RfcRow): string {
  return r.numbered ? r.label.replace(/^RFC-/, '') : r.label.split(/\s+/)[0]!;
}

/** One lane per distinct target, ordered by version, then a final "No target" lane. */
export function rfcLanes(rows: readonly RfcRow[]): RfcLane[] {
  const lanes = new Map<string | null, RfcLane>();
  for (const r of rows) {
    let lane = lanes.get(r.target);
    if (!lane) {
      const version = r.target ? (/v(\d+\.\d+\.\d+)/.exec(r.target)?.[1] ?? null) : null;
      lane = { target: r.target, version, url: r.targetUrl, rfcs: [] };
      lanes.set(r.target, lane);
    }
    lane.rfcs.push({ ...r, tile: rfcTileLabel(r), style: statusStyle(r.status) });
  }
  return [...lanes.values()].sort((a, b) => {
    if (a.target === null || b.target === null) return a.target === null ? 1 : -1;
    return versionKey(a.version ?? a.target).localeCompare(versionKey(b.version ?? b.target));
  });
}

export const RFC_FIG_TITLE = 'RFCs by target version';

/** "4 RFCs and 1 proposal across 3 target versions; 3 are Accepted, 2 are Draft. Standard v1.2.0 has no published text yet." */
export function rfcLanesCaption(lanes: readonly RfcLane[]): string {
  const all = lanes.flatMap((l) => l.rfcs);
  const numbered = all.filter((r) => r.numbered).length;
  const other = all.length - numbered;
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  const targeted = lanes.filter((l) => l.target !== null);
  const byStatus = new Map<string, number>();
  for (const r of all) byStatus.set(r.status, (byStatus.get(r.status) ?? 0) + 1);
  const statuses = [...byStatus].map(([s, n]) => `${n} ${n === 1 ? 'is' : 'are'} ${s}`);
  const unpublished = targeted.filter((l) => l.version !== null && l.url === null).map((l) => l.target!);
  return [
    `${plural(numbered, 'RFC', 'RFCs')}${other ? ` and ${plural(other, 'proposal', 'proposals')}` : ''} across ${plural(targeted.length, 'target version', 'target versions')}; ${joinAnd(statuses)}.`,
    unpublished.length ? `${joinAnd(unpublished)} ${unpublished.length === 1 ? 'has' : 'have'} no published text on this site yet.` : '',
  ]
    .filter(Boolean)
    .join(' ');
}

function joinAnd(items: readonly string[]): string {
  return items.length <= 1 ? (items[0] ?? '') : `${items.slice(0, -1).join(', ')} and ${items.at(-1)}`;
}

// ------------------------------------------------------------ F-SC1

export interface ShelfTile {
  entry: SchemaEntry;
  /** File name without its folder. */
  file: string;
  format: 'JSON' | 'YAML';
  lines: number;
}

export interface Shelf {
  key: SchemaEntry['group'];
  label: string;
  tiles: ShelfTile[];
}

/** One shelf per non-empty schema group, in page order, each file with its line count. */
export function schemaShelves(entries: readonly SchemaEntry[], groups: readonly { key: SchemaEntry['group']; label: string }[]): Shelf[] {
  return groups
    .map((g) => ({
      key: g.key,
      label: g.label,
      tiles: entries
        .filter((e) => e.group === g.key)
        .map((e) => ({
          entry: e,
          file: e.source.split('/').at(-1)!,
          format: e.source.endsWith('.json') ? ('JSON' as const) : ('YAML' as const),
          lines: readRepoFile(e.source).replace(/\n$/, '').split('\n').length,
        })),
    }))
    .filter((s) => s.tiles.length > 0);
}

/**
 * A group's table is an information figure when it has at least this many
 * files (visual spec 4.2: an enriched table counts from three rows of bars);
 * a shorter group is a plain table.
 */
export const SHELF_MIN_ROWS = 3;

export function shelfTitle(sh: Shelf): string {
  return `${sh.label}: the files and their length`;
}

/** "5 files, all YAML; the longest is x at n lines. Bars share one scale across the page, up to m lines." */
export function shelfCaption(sh: Shelf, maxLines: number): string {
  const formats = [...new Set(sh.tiles.map((t) => t.format))];
  const longest = [...sh.tiles].sort((a, b) => b.lines - a.lines)[0]!;
  const shortest = [...sh.tiles].sort((a, b) => a.lines - b.lines)[0]!;
  return `${sh.tiles.length} files, ${formats.length === 1 ? `all ${formats[0]}` : formats.map((f) => `${sh.tiles.filter((t) => t.format === f).length} ${f}`).join(' and ')}; the longest is ${longest.file} at ${longest.lines} lines and the shortest ${shortest.file} at ${shortest.lines}. Every bar on this page is on one scale, up to ${maxLines} lines.`;
}

// ------------------------------------------------------------ listing figures

/**
 * A count matrix: rows are pages, columns are things the pages cite or name,
 * each cell how many times. Drawn as a table with heat cells.
 */
export interface CountMatrix {
  title: string;
  caption: string;
  /** What a row is, for the corner header. */
  rowHead: string;
  /** What the counts are, for the heat scale's name. */
  unit: string;
  columns: { key: string; label: string; layer?: string }[];
  /** A row links to its page when it has one, and may lead with a glyph. */
  rows: { label: string; url?: string; glyph?: string; counts: number[] }[];
}

/** Times `re` matches in a page's source, grouped by the key `key` makes of each match. */
function countIn(source: string, re: RegExp, key: (m: RegExpMatchArray) => string | null): Map<string, number> {
  const out = new Map<string, number>();
  for (const m of readRepoFile(source).matchAll(re)) {
    const k = key(m);
    if (k !== null) out.set(k, (out.get(k) ?? 0) + 1);
  }
  return out;
}

const sum = (xs: readonly number[]) => xs.reduce((a, b) => a + b, 0);

/** Pages of a listing group, with their source files. */
function groupPages(routes: readonly Route[], section: string, group: string | undefined): (Route & { source: string })[] {
  return routes.filter((r): r is Route & { source: string } => r.section === section && r.group === group && r.source !== null);
}

/**
 * The ISO/IEC 42001 documents against the clauses they cite ("Clause 6.1"
 * counts for clause 6). Columns are every clause any of them cites.
 */
export function isoClauseMatrix(routes: readonly Route[]): CountMatrix {
  const pages = groupPages(routes, 'compliance', 'ISO/IEC 42001');
  const per = pages.map((p) => countIn(p.source, /\bClause (\d+)(?:\.\d+)*/g, (m) => m[1]!));
  const clauses = [...new Set(per.flatMap((m) => [...m.keys()]))].sort((a, b) => Number(a) - Number(b));
  const rows = pages.map((p, i) => ({ label: p.title, url: p.url, counts: clauses.map((c) => per[i]!.get(c) ?? 0) }));
  const most = clauses.map((c, j) => ({ c, docs: rows.filter((r) => r.counts[j]! > 0).length })).sort((a, b) => b.docs - a.docs)[0]!;
  const widest = [...rows].sort((a, b) => b.counts.filter(Boolean).length - a.counts.filter(Boolean).length)[0]!;
  return {
    title: 'Which ISO/IEC 42001 clauses each document cites',
    caption: `${rows.length} documents cite clauses ${clauses[0]} to ${clauses.at(-1)}. Clause ${most.c} is cited by the most documents (${most.docs}); the ${widest.label.toLowerCase()} cites the most clauses (${widest.counts.filter(Boolean).length}).`,
    rowHead: 'Document',
    unit: 'citations',
    columns: clauses.map((c) => ({ key: c, label: `Clause ${c}` })),
    rows,
  };
}

/** At most this many article columns, so the matrix fits the text column. */
export const EU_MAX_COLUMNS = 10;

/**
 * The EU AI Act documents against the articles they cite ("Art. 17",
 * "Article 17"). Columns are the articles that at least `k` of the documents
 * cite, with `k` the smallest number from two up that leaves no more than
 * EU_MAX_COLUMNS columns, so the matrix shows what the documents share.
 */
export function euArticleMatrix(routes: readonly Route[]): CountMatrix {
  const pages = groupPages(routes, 'compliance', 'EU AI Act');
  const per = pages.map((p) => countIn(p.source, /\bArt(?:icle|\.)\s?(\d+)/g, (m) => m[1]!));
  const all = [...new Set(per.flatMap((m) => [...m.keys()]))];
  const docsCiting = (a: string) => per.filter((m) => m.has(a)).length;
  let k = 2;
  while (all.filter((a) => docsCiting(a) >= k).length > EU_MAX_COLUMNS) k++;
  const shared = all.filter((a) => docsCiting(a) >= k).sort((a, b) => Number(a) - Number(b));
  const rows = pages.map((p, i) => ({ label: p.title, url: p.url, counts: shared.map((a) => per[i]!.get(a) ?? 0) }));
  const totals = shared.map((a, j) => ({ a, n: sum(rows.map((r) => r.counts[j]!)) })).sort((x, y) => y.n - x.n);
  return {
    title: `EU AI Act articles cited by ${k} or more documents`,
    caption: `The ${rows.length} documents cite ${all.length} articles; the ${shared.length} that ${k} or more of them cite are shown. Article ${totals[0]!.a} is cited most often (${totals[0]!.n} times).`,
    rowHead: 'Document',
    unit: 'citations',
    columns: shared.map((a) => ({ key: a, label: `Art. ${a}` })),
    rows,
  };
}

/**
 * The background pages against the layers of the capabilities they name in
 * code spans (`mutate`). A plain word such as "plan" is not counted, since it
 * may not mean the capability.
 */
export function backgroundLayerMatrix(routes: readonly Route[], layers: readonly { id: string; capabilities: string[] }[]): CountMatrix {
  const pages = routes.filter((r): r is Route & { source: string } => r.section === 'background' && r.source !== null);
  const layerOf = new Map(layers.flatMap((l) => l.capabilities.map((c) => [c, l.id] as const)));
  const ids = [...layerOf.keys()].sort((a, b) => b.length - a.length);
  const re = new RegExp('`(' + ids.join('|') + ')`', 'g');
  const per = pages.map((p) => countIn(p.source, re, (m) => layerOf.get(m[1]!) ?? null));
  const rows = pages.map((p, i) => ({ label: p.title, url: p.url, counts: layers.map((l) => per[i]!.get(l.id) ?? 0) }));
  const totals = layers.map((l, j) => ({ id: l.id, n: sum(rows.map((r) => r.counts[j]!)) })).sort((a, b) => b.n - a.n);
  const top = [...rows].sort((a, b) => sum(b.counts) - sum(a.counts))[0]!;
  const none = rows.filter((r) => sum(r.counts) === 0).map((r) => r.label);
  return {
    title: 'How often each page names a capability, by layer',
    caption: `Across the ${rows.length} pages, capabilities of ${totals[0]!.id} are named most (${totals[0]!.n} times) and of ${totals.at(-1)!.id} least (${totals.at(-1)!.n}). The ${top.label} names the most (${sum(top.counts)}).${none.length ? ` ${joinAnd(none)} ${none.length === 1 ? 'names' : 'name'} none.` : ''}`,
    rowHead: 'Page',
    unit: 'mentions',
    columns: layers.map((l) => ({ key: l.id, label: l.id, layer: l.id })),
    rows,
  };
}

/** The listing figures of a section: where each goes (the page top, or under a group's heading, before its cards) and what it draws. */
export type ListingFigure =
  | { at: 'top' | string; kind: 'matrix'; matrix: CountMatrix }
  | { at: string; kind: 'skills' };

export function listingFigures(section: string, routes: readonly Route[], layers: readonly { id: string; capabilities: string[] }[]): ListingFigure[] {
  switch (section) {
    case 'guides':
      return [{ at: 'Skills', kind: 'skills' }];
    case 'compliance':
      return [
        { at: 'EU AI Act', kind: 'matrix', matrix: euArticleMatrix(routes) },
        { at: 'ISO/IEC 42001', kind: 'matrix', matrix: isoClauseMatrix(routes) },
      ];
    case 'background':
      return [{ at: 'Methodology', kind: 'matrix', matrix: backgroundLayerMatrix(routes, layers) }];
    default:
      return [];
  }
}

export const SKILLS_FIG_TITLE = 'The workflow each composed skill runs';

/** "4 of the 6 composed skills run a catalog workflow, from 5 to 9 steps; 2 run none." */
export function skillsCaption(rows: readonly { steps: number | null }[]): string {
  const runs = rows.filter((r) => r.steps !== null).map((r) => r.steps!);
  const none = rows.length - runs.length;
  return `${runs.length} of the ${rows.length} composed skills run a catalog workflow, of ${Math.min(...runs)} to ${Math.max(...runs)} steps${none ? `; ${none} run${none === 1 ? 's' : ''} none` : ''}.`;
}

// ------------------------------------------------------------ F-CI1

/**
 * F-CI1 Risk by layer: how many of each layer's capabilities sit at each risk
 * level, from the ontology. Rows are the risk levels from low to high.
 */
export function riskByLayerMatrix(
  layers: readonly { id: string; capabilities: string[] }[],
  riskOf: (id: string) => string,
  risks: readonly string[],
): CountMatrix {
  const rows = risks.map((risk) => ({
    label: risk,
    glyph: `risk:${risk}`,
    counts: layers.map((l) => l.capabilities.filter((c) => riskOf(c) === risk).length),
  }));
  const top = risks.at(-1)!;
  const topRow = rows.at(-1)!;
  const where = layers.filter((_, j) => topRow.counts[j]! > 0).map((l) => `${l.id} (${topRow.counts[layers.indexOf(l)]})`);
  const total = sum(topRow.counts);
  return {
    title: 'Risk by layer',
    caption: `${total} capabilities are ${top} risk, all in ${joinAnd(where)}; ${layers.filter((_, j) => rows.every((r, i) => i === 0 || r.counts[j] === 0)).length} of the ${layers.length} layers hold only ${risks[0]}-risk capabilities.`,
    rowHead: 'Risk',
    unit: 'capabilities',
    columns: layers.map((l) => ({ key: l.id, label: l.id, layer: l.id })),
    rows,
  };
}
