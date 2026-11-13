// Data and captions for the figures of the section index pages, the RFC
// index and the schemas page (visual spec 3.11). The pages and their Markdown
// copies both read these, so the words agree.
import { codeLines } from './md-sections';
import { releaseHeading } from './release-figures';
import { readRepoFile, trackedUnder } from './repo';
import type { Route } from './routes';
import type { RfcRow } from './rfcs';
import { statusStyle } from './status';
import type { SchemaEntry } from './views';
import { currentStandardText } from './spec-figures';
import { diagnosticFamilies } from './spec-tail-figures';
import { andList, plural } from './words';

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
  const targeted = lanes.filter((l) => l.target !== null);
  const byStatus = new Map<string, number>();
  for (const r of all) byStatus.set(r.status, (byStatus.get(r.status) ?? 0) + 1);
  const statuses = [...byStatus].map(([s, n]) => `${n} ${n === 1 ? 'is' : 'are'} ${s}`);
  const unpublished = targeted.filter((l) => l.version !== null && l.url === null).map((l) => l.target!);
  return [
    `${plural(numbered, 'RFC', 'RFCs')}${other ? ` and ${plural(other, 'proposal', 'proposals')}` : ''} across ${plural(targeted.length, 'target version', 'target versions')}; ${andList(statuses)}.`,
    unpublished.length ? `${andList(unpublished)} ${unpublished.length === 1 ? 'has' : 'have'} no published text on this site yet.` : '',
  ]
    .filter(Boolean)
    .join(' ');
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

/** F-SC1's title: every schema file, one column per group (visual spec 3.11). */
export const SHELF_OVERVIEW_TITLE = 'Schema files by group';

/** "20 schema files in 6 groups; 5 are required by the Standard; the largest group is Transforms, with 7." */
export function shelfOverviewCaption(shelves: readonly Shelf[]): string {
  const files = sum(shelves.map((s) => s.tiles.length));
  const required = shelves.find((s) => s.key === 'required')?.tiles.length ?? 0;
  const largest = [...shelves].sort((a, b) => b.tiles.length - a.tiles.length)[0]!;
  return `${plural(files, 'schema file', 'schema files')} in ${plural(shelves.length, 'group', 'groups')}; ${required === 0 ? 'none is' : `${required} ${required === 1 ? 'is' : 'are'}`} required by the Standard, marked with a stamp; the largest group is ${largest.label}, with ${largest.tiles.length}.`;
}

export function shelfTitle(sh: Shelf): string {
  return `${sh.label}: the files and their length`;
}

/** The top of a group's bar scale: its longest file. */
export function shelfMax(sh: Shelf): number {
  return Math.max(...sh.tiles.map((t) => t.lines));
}

/** "5 files, all YAML; the longest is x at n lines and the shortest y at m. Each bar is on this group's scale, up to n lines." */
export function shelfCaption(sh: Shelf): string {
  const formats = [...new Set(sh.tiles.map((t) => t.format))];
  const longest = [...sh.tiles].sort((a, b) => b.lines - a.lines)[0]!;
  const shortest = [...sh.tiles].sort((a, b) => a.lines - b.lines)[0]!;
  return `${sh.tiles.length} files, ${formats.length === 1 ? `all ${formats[0]}` : formats.map((f) => `${sh.tiles.filter((t) => t.format === f).length} ${f}`).join(' and ')}; the longest is ${longest.file} at ${longest.lines} lines and the shortest ${shortest.file} at ${shortest.lines}. The bars are on this group's scale, up to ${shelfMax(sh)} lines.`;
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

/** A page as the matrices read it: its card title, its URL and its Markdown source text. */
export interface Doc {
  label: string;
  url: string;
  text: string;
}

/** Times `re` matches in a text, grouped by the key `key` makes of each match. */
function countIn(text: string, re: RegExp, key: (m: RegExpMatchArray) => string | null): Map<string, number> {
  const out = new Map<string, number>();
  for (const m of text.matchAll(re)) {
    const k = key(m);
    if (k !== null) out.set(k, (out.get(k) ?? 0) + 1);
  }
  return out;
}

const sum = (xs: readonly number[]) => xs.reduce((a, b) => a + b, 0);

/**
 * The text with its ```mermaid fences removed. A diagram restates what the
 * prose around it says, so a citation in its labels or caption is the same
 * citation again and is not counted twice.
 */
export function withoutDiagrams(text: string): string {
  return text.replace(/^([ \t]*)```mermaid[^\n]*\n[\s\S]*?^\1```[ \t]*$/gm, '');
}

/** The pages of a section (of one group of it, when `group` is given), in route order, with their source text. */
export function sectionDocs(routes: readonly Route[], section: string, group?: string): Doc[] {
  return routes
    .filter((r): r is Route & { source: string } => r.section === section && r.source !== null && (group === undefined || r.group === group))
    .sort((a, b) => a.order - b.order)
    .map((r) => ({ label: r.title, url: r.url, text: readRepoFile(r.source) }));
}

/**
 * The ISO/IEC 42001 documents against the clauses they cite ("Clause 6.1"
 * counts for clause 6). Columns are every clause any of them cites.
 */
export function isoClauseMatrix(pages: readonly Doc[]): CountMatrix {
  const per = pages.map((p) => countIn(withoutDiagrams(p.text), /\bClause (\d+)(?:\.\d+)*/g, (m) => m[1]!));
  const clauses = [...new Set(per.flatMap((m) => [...m.keys()]))].sort((a, b) => Number(a) - Number(b));
  const rows = pages.map((p, i) => ({ label: p.label, url: p.url, counts: clauses.map((c) => per[i]!.get(c) ?? 0) }));
  const most = clauses.map((c, j) => ({ c, docs: rows.filter((r) => r.counts[j]! > 0).length })).sort((a, b) => b.docs - a.docs)[0]!;
  const widest = [...rows].sort((a, b) => b.counts.filter(Boolean).length - a.counts.filter(Boolean).length)[0]!;
  return {
    title: 'Which ISO/IEC 42001 clauses each document cites',
    caption: `The ${rows.length} documents cite ${clauses.length} clauses: ${andList(clauses)}. Clause ${most.c} is cited by the most documents (${most.docs}); the ${widest.label.toLowerCase()} cites the most clauses (${widest.counts.filter(Boolean).length}).`,
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
export function euArticleMatrix(pages: readonly Doc[]): CountMatrix {
  const per = pages.map((p) => countIn(withoutDiagrams(p.text), /\bArt(?:icle|\.)\s?(\d+)/g, (m) => m[1]!));
  const all = [...new Set(per.flatMap((m) => [...m.keys()]))];
  const docsCiting = (a: string) => per.filter((m) => m.has(a)).length;
  let k = 2;
  while (all.filter((a) => docsCiting(a) >= k).length > EU_MAX_COLUMNS) k++;
  const shared = all.filter((a) => docsCiting(a) >= k).sort((a, b) => Number(a) - Number(b));
  const rows = pages.map((p, i) => ({ label: p.label, url: p.url, counts: shared.map((a) => per[i]!.get(a) ?? 0) }));
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
 * A section's pages against the layers of the capabilities they name in
 * code spans (`mutate`). A plain word such as "plan" is not counted, since it
 * may not mean the capability; the title and caption say so.
 */
export function backgroundLayerMatrix(pages: readonly Doc[], layers: readonly { id: string; capabilities: string[] }[]): CountMatrix {
  const layerOf = new Map(layers.flatMap((l) => l.capabilities.map((c) => [c, l.id] as const)));
  const ids = [...layerOf.keys()].sort((a, b) => b.length - a.length);
  const re = new RegExp('`(' + ids.join('|') + ')`', 'g');
  const per = pages.map((p) => countIn(p.text, re, (m) => layerOf.get(m[1]!) ?? null));
  const rows = pages.map((p, i) => ({ label: p.label, url: p.url, counts: layers.map((l) => per[i]!.get(l.id) ?? 0) }));
  const totals = layers.map((l, j) => ({ id: l.id, n: sum(rows.map((r) => r.counts[j]!)) })).sort((a, b) => b.n - a.n);
  const top = [...rows].sort((a, b) => sum(b.counts) - sum(a.counts))[0]!;
  const none = rows.filter((r) => sum(r.counts) === 0).map((r) => r.label);
  return {
    title: 'How often each page names a capability as code, by layer',
    caption: `Only a capability name set as code counts, since a plain word such as "plan" may not mean the capability. Across the ${rows.length} pages, capabilities of ${totals[0]!.id} are named most (${totals[0]!.n} times) and of ${totals.at(-1)!.id} least (${totals.at(-1)!.n}). The ${top.label} names the most (${sum(top.counts)}).${none.length ? ` ${andList(none)} ${none.length === 1 ? 'names' : 'name'} none as code, so ${none.length === 1 ? 'it has' : 'they have'} no row.` : ''}`,
    rowHead: 'Page',
    unit: 'mentions',
    columns: layers.map((l) => ({ key: l.id, label: l.id, layer: l.id })),
    // A page that names no capability as code has an empty row; the caption names it instead.
    rows: rows.filter((r) => sum(r.counts) > 0),
  };
}


/**
 * Bars: a label (linked when it has a page), a value and its printed words.
 * The bars share one scale, the largest value, unless a row gives its own
 * `max` (a share of a whole, such as 6 of 8 codes).
 */
export interface BarList {
  title: string;
  caption: string;
  /** Column headings for the table in the Markdown copy: the label, then the words. */
  head: [string, string];
  rows: { label: string; url?: string; value: number; max?: number; words: string }[];
}

/**
 * The releases in CHANGELOG.md, newest first: each "## [vX.Y.Z] — date" (any dash)
 * section with the number of change items (list lines) under it.
 */
export function releaseBars(changelog: string): BarList {
  const lines = changelog.split('\n');
  const rows: { label: string; value: number; words: string }[] = [];
  let cur: { label: string; value: number; date: string } | null = null;
  const flush = () => cur && rows.push({ label: cur.label, value: cur.value, words: `${plural(cur.value, 'change', 'changes')}, ${cur.date}` });
  const code = codeLines(changelog);
  for (const [i, l] of lines.entries()) {
    const h = code[i] ? null : releaseHeading(l);
    if (h && /^v\d+\.\d+\.\d+/.test(h.version) && h.date) {
      flush();
      cur = { label: h.version, value: 0, date: h.date };
      continue;
    }
    if (!code[i] && /^## /.test(l)) {
      flush();
      cur = null;
      continue;
    }
    if (cur && !code[i] && /^\s*[-*+] /.test(l)) cur.value += 1;
  }
  flush();
  if (rows.length === 0) throw new Error('CHANGELOG.md: no "## [vX.Y.Z] — date" section');
  const top = [...rows].sort((a, b) => b.value - a.value)[0]!;
  return {
    title: 'Changes in each release, newest first',
    head: ['Release', 'Changes'],
    caption: `${plural(rows.length, 'release', 'releases')} from ${rows.at(-1)!.label} to ${rows[0]!.label}; ${top.label} has the most changes (${top.value}), counted as list items in the release notes.`,
    rows,
  };
}

// ------------------------------------------------------------ /start/

/** The reading speed the start pages' reading times assume. */
export const WORDS_PER_MINUTE = 200;

/**
 * A page's words outside fenced blocks, and its fenced blocks other than
 * diagrams (mermaid, or two or more lines of box-drawing characters): the
 * commands and code to read or run.
 */
export function pageSize(text: string): { words: number; codeBlocks: number } {
  let codeBlocks = 0;
  const prose = text
    .replace(/^---\n[\s\S]*?\n---\n/, '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/^( {0,3})(`{3,}|~{3,})([^\n]*)\n[\s\S]*?^\1\2[ \t]*$/gm, (f: string, _i, _t, info: string) => {
      const drawing = f.split('\n').filter((l) => /[\u2500-\u257f]/.test(l)).length >= 2;
      if (!/^\s*mermaid\b/.test(info) && !drawing) codeBlocks += 1;
      return '';
    })
    // A link counts as its text; a destination, an image and an HTML tag are not words.
    .replace(/^\s*\[[^\]]+\]:\s*\S+.*$/gm, '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/<[^>]+>/g, ' ');
  return { words: (prose.match(/[A-Za-z0-9][\w'’.-]*/g) ?? []).length, codeBlocks };
}

/** The start pages' reading times, at WORDS_PER_MINUTE, with their code blocks. */
export function readingBars(pages: readonly Doc[]): BarList {
  const rows = pages.map((p) => {
    const { words, codeBlocks } = pageSize(p.text);
    const minutes = Math.max(1, Math.round(words / WORDS_PER_MINUTE));
    return { label: p.label, url: p.url, value: minutes, words: `${minutes} min, ${plural(codeBlocks, 'code block', 'code blocks')}`, codeBlocks };
  });
  const total = sum(rows.map((r) => r.value));
  const short = [...rows].sort((a, b) => a.value - b.value)[0]!;
  const long = [...rows].sort((a, b) => b.value - a.value)[0]!;
  const code = [...rows].sort((a, b) => b.codeBlocks - a.codeBlocks)[0]!;
  return {
    title: 'How long each page takes to read',
    caption: `At ${WORDS_PER_MINUTE} words a minute, not counting code, the ${rows.length} pages take about ${total} minutes in all; the ${short.label} is the shortest (${short.value} min) and the ${long.label} the longest (${long.value} min). The ${code.label} has the most code blocks to read or run (${code.codeBlocks}).`,
    head: ['Page', 'Reading time and code blocks'],
    rows: rows.map(({ codeBlocks: _c, ...r }) => r),
  };
}

// ------------------------------------------------------------ /spec/

const CODE = /^[A-Z]\d{3}$/;
const codesIn = (xs: unknown[]): string[] => xs.filter((x): x is string => typeof x === 'string' && CODE.test(x));

/** One part of the conformance suite: how many fixtures or cases it has, and the diagnostic codes they expect. */
export interface SuitePart {
  label: string;
  count: number;
  unit: string;
  codes: Set<string>;
}

export const EXPECTATIONS_SOURCE = 'tests/fixtures/EXPECTATIONS.json';
export const EVAL_SOURCE = 'tests/conformance/expressions/eval.json';
export const CHECK_SOURCE = 'tests/conformance/expressions/check.json';
export const RUNTIME_DIR = 'tests/conformance/runtime';
export const CONTRIB_DIR = 'tests/conformance/contrib';

/**
 * The parts of the conformance suite that spec/CONFORMANCE.md names, and the
 * codes each expects: a validator fixture's expected error and warning
 * codes, an evaluation case's error, a check case's diagnostics, and the code
 * and cause a runtime or contributed fixture's run ends with.
 */
export function conformanceSuite(): SuitePart[] {
  type Exp = { should_pass?: boolean; expected_error_codes?: unknown[]; expected_warning_codes?: unknown[] };
  const exp = Object.values(JSON.parse(readRepoFile(EXPECTATIONS_SOURCE)) as Record<string, Exp>);
  const validator = (pass: boolean): SuitePart => {
    const set = exp.filter((v) => (v.should_pass === true) === pass);
    return {
      label: `Validator fixtures that must ${pass ? 'pass' : 'fail'}`,
      count: set.length,
      unit: 'fixtures',
      codes: new Set(set.flatMap((v) => codesIn([...(v.expected_error_codes ?? []), ...(v.expected_warning_codes ?? [])]))),
    };
  };
  const cases = (source: string) => (JSON.parse(readRepoFile(source)) as { cases: { expect: unknown }[] }).cases;
  const evalCases = cases(EVAL_SOURCE);
  const checkCases = cases(CHECK_SOURCE);
  const runs = (dir: string, label: string): SuitePart => {
    const files = trackedUnder(dir, '.json');
    const codes = files.flatMap((f) => {
      const end = (JSON.parse(readRepoFile(f)) as { end?: { code?: unknown; cause?: unknown } }).end ?? {};
      return codesIn([end.code, end.cause]);
    });
    return { label, count: files.length, unit: 'fixtures', codes: new Set(codes) };
  };
  return [
    validator(true),
    validator(false),
    {
      label: 'Expression evaluation cases',
      count: evalCases.length,
      unit: 'cases',
      codes: new Set(evalCases.flatMap((c) => codesIn([(c.expect as { error?: unknown } | null)?.error]))),
    },
    { label: 'Expression check cases', count: checkCases.length, unit: 'cases', codes: new Set(checkCases.flatMap((c) => (Array.isArray(c.expect) ? codesIn(c.expect) : []))) },
    runs(RUNTIME_DIR, 'Runtime fixtures'),
    runs(CONTRIB_DIR, 'Contributed fixtures'),
  ];
}

/** A diagnostic family as the coverage figure reads it: its name, range and codes. */
export interface FamilyCodes {
  name: string;
  range: string;
  codes: string[];
}

/** The diagnostic families of the current Standard's §9.1, with their codes. */
export function specFamilies(): FamilyCodes[] {
  const { source, text } = currentStandardText();
  return diagnosticFamilies(text, source).map((f) => ({ name: f.name, range: f.range, codes: f.codes.map((d) => d.code) }));
}

export const COVERAGE_FIG_TITLE = 'Diagnostic codes the conformance suite expects, by family';

/** Each family's share of codes that at least one fixture or case of the suite expects. */
export function suiteCoverage(parts: readonly SuitePart[], families: readonly FamilyCodes[]): BarList {
  const expected = new Set(parts.flatMap((p) => [...p.codes]));
  const rows = families.map((f) => {
    const hit = f.codes.filter((c) => expected.has(c));
    return { label: `${f.range} ${f.name}`, value: hit.length, max: f.codes.length, words: `${hit.length} of ${f.codes.length} codes`, f };
  });
  const all = sum(families.map((f) => f.codes.length));
  const hit = sum(rows.map((r) => r.value));
  const share = (r: (typeof rows)[number]) => r.value / r.max;
  const full = rows.filter((r) => r.value === r.max).map((r) => r.f.name);
  const low = [...rows].sort((a, b) => share(a) - share(b))[0]!;
  const fixtures = sum(parts.map((p) => p.count));
  const missing = families.flatMap((f) => f.codes.filter((c) => !expected.has(c)));
  return {
    title: COVERAGE_FIG_TITLE,
    caption: `The suite's ${fixtures} fixtures and cases (${andList(parts.map((p) => `${p.count} ${p.label.charAt(0).toLowerCase()}${p.label.slice(1)}`))}) expect ${hit} of the ${all} diagnostic codes. ${
      full.length > 0 ? `Every ${andList(full)} code is expected; ` : ''
    }${low.f.name} has the smallest share, ${low.value} of ${low.max}.${missing.length === 0 ? '' : ` No fixture or case expects ${andList(missing)}.`}`,
    head: ['Family', 'Codes the suite expects'],
    rows: rows.map(({ f: _f, ...r }) => r),
  };
}

/** The listing figures of a section: where each goes (the page top, or under a group's heading, before its cards) and what it draws. */
export type ListingFigure =
  | { at: 'top' | string; kind: 'matrix'; matrix: CountMatrix }
  | { at: 'top' | string; kind: 'bars'; bars: BarList }
  | { at: string; kind: 'skills' };

export function listingFigures(section: string, routes: readonly Route[], layers: readonly { id: string; capabilities: string[] }[]): ListingFigure[] {
  switch (section) {
    case 'guides':
      return [{ at: 'Skills', kind: 'skills' }];
    // The count matrices are tables; every section index also gets a drawn
    // figure (scripts/check-dist.mjs, "drawn"), here how long each page takes
    // to read, as on the start index.
    case 'compliance':
      return [
        { at: 'top', kind: 'bars', bars: readingBars(sectionDocs(routes, 'compliance')) },
        { at: 'EU AI Act', kind: 'matrix', matrix: euArticleMatrix(sectionDocs(routes, 'compliance', 'EU AI Act')) },
        { at: 'ISO/IEC 42001', kind: 'matrix', matrix: isoClauseMatrix(sectionDocs(routes, 'compliance', 'ISO/IEC 42001')) },
      ];
    case 'background':
      return [
        { at: 'top', kind: 'bars', bars: readingBars(sectionDocs(routes, 'background')) },
        { at: 'Methodology', kind: 'matrix', matrix: backgroundLayerMatrix(sectionDocs(routes, 'background'), layers) },
      ];
    // The start pages are read in order by a newcomer, so the figure is how long each takes; counting
    // capability names in code spans scored the overview, which shows all 36 in a drawing, as 0.
    case 'start':
      return [{ at: 'top', kind: 'bars', bars: readingBars(sectionDocs(routes, 'start')) }];
    // The specification pages name few capabilities as code; what they share is the conformance suite.
    case 'spec':
      return [{ at: 'top', kind: 'bars', bars: suiteCoverage(conformanceSuite(), specFamilies()) }];
    case 'community':
      return [{ at: 'top', kind: 'bars', bars: releaseBars(readRepoFile('CHANGELOG.md')) }];
    default:
      return [];
  }
}

export const SKILLS_FIG_TITLE = 'The workflow each composed skill runs';

/** "4 of the 6 composed skills run a catalog workflow, from 5 to 9 steps; 2 run none." */
export function skillsCaption(rows: readonly { steps: number | null }[]): string {
  const runs = rows.filter((r) => r.steps !== null).map((r) => r.steps!);
  const none = rows.length - runs.length;
  if (runs.length === 0) return `None of the ${plural(rows.length, 'composed skill', 'composed skills')} runs a catalog workflow.`;
  const min = Math.min(...runs);
  const max = Math.max(...runs);
  const size = min === max ? plural(min, 'step', 'steps') : `${min} to ${max} steps`;
  return `${runs.length} of the ${rows.length} composed skills run a catalog workflow, of ${size}${none ? `; ${none} run${none === 1 ? 's' : ''} none` : ''}.`;
}
