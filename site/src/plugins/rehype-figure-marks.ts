// Small figure marks added to rendered Markdown, where an Astro component
// cannot reach (visual spec 3.7 F-E4 and 3.9):
// - every Standard version: each "## N." chapter heading starts with its
//   chapter glyph at 3x, aria-hidden. Appendix headings get none.
// - the current Standard: each row of the §5.2 step field tables gets an id,
//   `step-field-<first field>`, so the step anatomy figure can link to it.
// - spec/EDGE_TYPES.md: the "Edge Type Summary" table gets the type's mark in
//   its first column, a check or cross beside each Yes or No in the
//   Transitive and Symmetric columns, and a right-hand column with the
//   ontology's count of that type as a pixel bar on one shared scale.
// Heading ids are set before this runs and are not changed; the glyphs are
// aria-hidden, so headings and table labels read as before.
import type { Element, ElementContent, Root } from 'hast';
import type { VFile } from 'vfile';
import { loadOntology } from '../data/ontology';
import { edgeTypeCount } from '../lib/views';
import { chapterKey } from '../pixel/keys';
import { glyphElement, pixelBarElement } from '../pixel/hast';
import { failWith, sourceOf } from './source';

export interface RehypeFigureMarksOptions {
  /** Repo paths of every Standard version (chapter glyphs). */
  standards: ReadonlySet<string>;
  /** Repo path of the current Standard (step field row ids). */
  current: string;
  /** Repo path of the edge types document (summary table). */
  edgeTypes: string;
}

const PLUGIN = 'rehype-figure-marks';

/** Text of a hast node, aria-hidden parts included (heading-anchor links hold no text). */
export function hastText(n: ElementContent | Root): string {
  if (n.type === 'text') return n.value;
  if (n.type !== 'element' && n.type !== 'root') return '';
  return n.children.map((c) => hastText(c as ElementContent)).join('');
}

const isEl = (n: unknown, tag?: string): n is Element =>
  typeof n === 'object' && n !== null && (n as Element).type === 'element' && (tag === undefined || (n as Element).tagName === tag);

/** Elements of the root between the heading that matches and the next heading of the same or a higher level. */
function sectionElements(tree: Root, match: (h: Element) => boolean): Element[] | null {
  const kids = tree.children.filter((n): n is Element => isEl(n));
  const i = kids.findIndex((n) => /^h[1-6]$/.test(n.tagName) && match(n));
  if (i === -1) return null;
  const level = Number(kids[i]!.tagName[1]);
  const out: Element[] = [];
  for (const n of kids.slice(i + 1)) {
    if (/^h[1-6]$/.test(n.tagName) && Number(n.tagName[1]) <= level) break;
    out.push(n);
  }
  return out;
}

function rowsOf(table: Element, part: 'thead' | 'tbody'): Element[] {
  const sec = table.children.find((c): c is Element => isEl(c, part));
  return sec ? sec.children.filter((c): c is Element => isEl(c, 'tr')) : [];
}

function cellsOf(tr: Element): Element[] {
  return tr.children.filter((c): c is Element => isEl(c, 'td') || isEl(c, 'th'));
}

/** Backticked code values in a cell, in order. */
function codesOf(n: Element): string[] {
  const out: string[] = [];
  const walk = (e: ElementContent) => {
    if (!isEl(e)) return;
    if (e.tagName === 'code') out.push(hastText(e));
    else e.children.forEach(walk);
  };
  n.children.forEach(walk);
  return out;
}

export function chapterGlyphs(tree: Root): number {
  let n = 0;
  for (const h of tree.children) {
    if (!isEl(h, 'h2')) continue;
    const key = chapterKey(hastText(h));
    if (!key || !/^\d+\.\s/.test(hastText(h).trim())) continue;
    h.children.unshift(glyphElement(key, { scale: 3, className: 'chapter-glyph' }));
    n++;
  }
  return n;
}

/** The id the step anatomy figure links to for a §5.2 field table row. */
export function stepFieldId(firstField: string): string {
  return `step-field-${firstField.replace(/[^A-Za-z0-9_-]/g, '-')}`;
}

function stepFieldIds(tree: Root, problems: string[]): void {
  const els = sectionElements(tree, (h) => h.tagName === 'h3' && hastText(h).trim().startsWith('5.2 '));
  if (!els) {
    problems.push('the current Standard has no "5.2 " heading for the step field tables');
    return;
  }
  const tables = els.filter((e) => isEl(e, 'table'));
  if (tables.length === 0) problems.push('§5.2 has no field table');
  for (const t of tables) {
    for (const tr of rowsOf(t, 'tbody')) {
      const first = codesOf(cellsOf(tr)[0]!)[0];
      if (first) tr.properties = { ...tr.properties, id: stepFieldId(first) };
    }
  }
}

function edgeSummary(tree: Root, problems: string[]): void {
  const els = sectionElements(tree, (h) => h.tagName === 'h2' && hastText(h).trim() === 'Edge Type Summary');
  const table = els?.find((e) => isEl(e, 'table'));
  if (!table) {
    problems.push('no table under "Edge Type Summary"');
    return;
  }
  const ontology = loadOntology();
  const counts = new Map(ontology.edgeTypes.map((t) => [t.id, { n: edgeTypeCount(t), symmetric: t.symmetric }]));
  const max = Math.max(...[...counts.values()].map((c) => c.n));
  const head = rowsOf(table, 'thead')[0];
  if (!head) {
    problems.push('the edge type summary table has no header row');
    return;
  }
  const headers = cellsOf(head).map((c) => hastText(c).trim());
  const flagCols = ['Transitive', 'Symmetric'].map((h) => headers.indexOf(h));
  if (flagCols.includes(-1)) problems.push(`the edge type summary table has no ${['Transitive', 'Symmetric'].filter((_, i) => flagCols[i] === -1).join(' or ')} column`);
  head.children.push({ type: 'element', tagName: 'th', properties: {}, children: [{ type: 'text', value: 'Count' }] });
  const seen = new Set<string>();
  for (const tr of rowsOf(table, 'tbody')) {
    const cells = cellsOf(tr);
    const type = codesOf(cells[0]!)[0];
    const c = type ? counts.get(type as never) : undefined;
    if (!type || !c) {
      problems.push(`edge type summary row "${hastText(cells[0]!).trim()}" names no ontology edge type`);
      continue;
    }
    seen.add(type);
    tr.properties = { ...tr.properties, dataEdgeType: type };
    cells[0]!.children.unshift(glyphElement(`mark:${type}`, { className: 'edge-summary__mark' }));
    for (const col of flagCols) {
      const cell = cells[col];
      if (!cell) continue;
      const v = hastText(cell).trim();
      const g = /^Yes\b/.test(v) ? 'check' : /^No\b/.test(v) ? 'close' : null;
      if (g) cell.children.unshift(glyphElement(g, { className: 'edge-summary__flag' }));
    }
    const unit = c.symmetric ? (c.n === 1 ? 'pair' : 'pairs') : c.n === 1 ? 'edge' : 'edges';
    tr.children.push({
      type: 'element',
      tagName: 'td',
      properties: { className: ['edge-summary__count'] },
      children: [pixelBarElement(c.n, max, { label: `${c.n} ${unit}` })],
    });
  }
  for (const t of counts.keys()) if (!seen.has(t)) problems.push(`the edge type summary table has no row for ${t}`);
}

export default function rehypeFigureMarks(options: RehypeFigureMarksOptions) {
  return (tree: Root, file: VFile): void => {
    const { repoPath } = sourceOf(file, PLUGIN);
    const problems: string[] = [];
    if (options.standards.has(repoPath)) {
      if (chapterGlyphs(tree) === 0) problems.push(`${repoPath}: no "## N." chapter heading got a glyph`);
      if (repoPath === options.current) stepFieldIds(tree, problems);
    }
    if (repoPath === options.edgeTypes) edgeSummary(tree, problems);
    failWith(PLUGIN, problems.map((p) => `${repoPath}: ${p}`));
  };
}
