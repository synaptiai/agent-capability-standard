// Figures placed inside rendered Markdown (visual spec 3.7 and 3.9). The page
// takes the source's rendered HTML, cuts it after the headings the anchor map
// names, and renders a figure component at each cut. A heading is found by
// its level and the start of its text; each anchor must match exactly one
// heading, or the build fails, so an edit to the source cannot move or drop
// a figure without notice.

import { decodeEntities } from './toc';
import { stripTags } from './strip';

export interface HtmlHeading {
  level: number;
  id: string;
  /** Visible text, tags removed, whitespace collapsed. */
  text: string;
  /** Index just after the closing tag. */
  end: number;
}

const HEADING = /<h([1-6])\b([^>]*)>([\s\S]*?)<\/h\1>/g;


/** Every heading of an HTML string, in order. Text inside aria-hidden svg (chapter glyphs) is empty, so it is skipped by removing tags. */
export function htmlHeadings(html: string): HtmlHeading[] {
  return [...html.matchAll(HEADING)].map((m) => ({
    level: Number(m[1]),
    id: /\bid="([^"]*)"/.exec(m[2]!)?.[1] ?? '',
    text: decodeEntities(stripTags(m[3]!)).replace(/\s+/g, ' ').trim(),
    end: m.index + m[0].length,
  }));
}

export interface Anchor<K> {
  key: K;
  level: number;
  /** The heading text starts with this. */
  startsWith: string;
}

export interface Segment<K> {
  html: string;
  /** The figure to render after this HTML, or null after the last piece. */
  key: K | null;
}

/**
 * The HTML cut after each anchored heading, in document order. Throws, naming
 * every problem, when an anchor matches no heading or more than one.
 */
export function cutAfterHeadings<K>(html: string, anchors: readonly Anchor<K>[], where: string): Segment<K>[] {
  const heads = htmlHeadings(html);
  const problems: string[] = [];
  const cuts: { at: number; key: K }[] = [];
  for (const a of anchors) {
    const hits = heads.filter((h) => h.level === a.level && h.text.startsWith(a.startsWith));
    if (hits.length !== 1) {
      problems.push(`h${a.level} starting "${a.startsWith}" matches ${hits.length} headings`);
      continue;
    }
    cuts.push({ at: hits[0]!.end, key: a.key });
  }
  if (problems.length > 0) throw new Error(`${where}: figure anchors: ${problems.join('; ')}`);
  cuts.sort((x, y) => x.at - y.at);
  const out: Segment<K>[] = [];
  let last = 0;
  for (const c of cuts) {
    out.push({ html: html.slice(last, c.at), key: c.key });
    last = c.at;
  }
  out.push({ html: html.slice(last), key: null });
  return out;
}

/**
 * The end (just after its closing tag) of the `tag` element that opens at
 * `start`, found by counting the `tag` elements nested in it. Throws when the
 * element is not closed.
 */
export function elementEnd(html: string, start: number, tag: string, where: string): number {
  const re = new RegExp(`<(/?)${tag}\\b[^>]*>`, 'gi');
  re.lastIndex = start;
  let depth = 0;
  for (let m = re.exec(html); m; m = re.exec(html)) {
    depth += m[1] ? -1 : 1;
    if (depth === 0) return m.index + m[0].length;
  }
  throw new Error(`${where}: the <${tag}> at ${start} is not closed`);
}

/**
 * The element that opens at the first match of `open` (a regex for its
 * opening tag, of element `tag`), wrapped in a <details class="fig-details">
 * under `summary`. Throws `<where>: no <what> to fold` when there is none:
 * a caller folds a block it knows is there.
 */
export function foldFirst(html: string, open: RegExp, tag: string, summary: string, what: string, where: string, inner: (block: string) => string = (b) => b): string {
  const m = open.exec(html);
  if (!m) throw new Error(`${where}: no ${what} to fold`);
  const end = elementEnd(html, m.index, tag, where);
  const esc = summary.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  return `${html.slice(0, m.index)}<details class="fig-details"><summary>${esc}</summary>${inner(html.slice(m.index, end))}</details>${html.slice(end)}`;
}

/**
 * The first table (in its .table-wrap) of `html`, folded into a <details>
 * with `summary`, for a source table whose figure, placed just before it,
 * already shows everything it says.
 */
export function foldFirstTable(html: string, summary: string, where: string): string {
  return foldFirst(html, /<div class="table-wrap"[^>]*>/, 'div', summary, 'table', where);
}

/**
 * The first task list of rendered HTML folded into a <details> under
 * `summary`: a checklist that a figure above it already shows item by item.
 * A list nested in an item stays inside.
 */
export function foldFirstTaskList(html: string, summary: string, where: string): string {
  return foldFirst(html, /<ul class="contains-task-list">/, 'ul', summary, 'task list', where);
}
