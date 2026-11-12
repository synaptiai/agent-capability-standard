// Blocks of a Markdown file read by section, for figures drawn from the
// table, list or fence of the section they sit in (visual spec 1.1 rule 3).
// A section is a heading and everything up to the next heading of the same
// or a higher level. Headings are matched by the start of their text, so
// "5.2 " finds "5.2 Step Definition" and nothing else.
import type { Code, Heading, List, Root, RootContent, Table } from 'mdast';
import { toString } from 'mdast-util-to-string';
import { headingText, parseMarkdown } from './anchors';

const trees = new Map<string, Root>();

function tree(text: string): Root {
  let t = trees.get(text);
  if (!t) {
    t = parseMarkdown(text);
    trees.set(text, t);
  }
  return t;
}

/** The blocks under the one heading whose text starts with `prefix`. Throws on no match or several. */
export function sectionBlocks(text: string, prefix: string, where: string): RootContent[] {
  const nodes = tree(text).children;
  const starts = nodes.flatMap((n, i) => (n.type === 'heading' && headingText(n).trim().startsWith(prefix) ? [i] : []));
  if (starts.length !== 1) throw new Error(`${where}: expected one heading starting "${prefix}", found ${starts.length}`);
  const i = starts[0]!;
  const depth = (nodes[i] as Heading).depth;
  const end = nodes.findIndex((n, j) => j > i && n.type === 'heading' && n.depth <= depth);
  return nodes.slice(i + 1, end === -1 ? undefined : end);
}

/** Rows of a table as plain cell text, header row first. */
export function tableRows(t: Table): string[][] {
  return t.children.map((row) => row.children.map((c) => toString(c).trim()));
}

/** Rows of a table with each cell's backticked code spans, header row first. */
export function tableCodes(t: Table): string[][][] {
  return t.children.map((row) =>
    row.children.map((c) => {
      const out: string[] = [];
      const walk = (n: { type: string; value?: string; children?: unknown[] }) => {
        if (n.type === 'inlineCode' && typeof n.value === 'string') out.push(n.value);
        for (const ch of (n.children ?? []) as (typeof n)[]) walk(ch);
      };
      walk(c as never);
      return out;
    }),
  );
}

/** The k-th (0-based) table of a section. */
export function sectionTable(text: string, prefix: string, k: number, where: string): Table {
  const tables = sectionBlocks(text, prefix, where).filter((n): n is Table => n.type === 'table');
  const t = tables[k];
  if (!t) throw new Error(`${where}: section "${prefix}" has ${tables.length} table(s), no table ${k + 1}`);
  return t;
}

/** The table of a section whose header row starts with `firstHeader`. */
export function sectionTableByHeader(text: string, prefix: string, firstHeader: string, where: string): Table {
  const tables = sectionBlocks(text, prefix, where).filter((n): n is Table => n.type === 'table');
  const hits = tables.filter((t) => tableRows(t)[0]?.[0] === firstHeader);
  if (hits.length !== 1) throw new Error(`${where}: section "${prefix}" has ${hits.length} table(s) headed "${firstHeader}", expected one`);
  return hits[0]!;
}

/** The k-th (0-based) fenced code block of a section. */
export function sectionFence(text: string, prefix: string, k: number, where: string): Code {
  const fences = sectionBlocks(text, prefix, where).filter((n): n is Code => n.type === 'code');
  const f = fences[k];
  if (!f) throw new Error(`${where}: section "${prefix}" has ${fences.length} fence(s), no fence ${k + 1}`);
  return f;
}

/** The text of a section's paragraphs, joined by blank lines. */
export function sectionParagraphs(text: string, prefix: string, where: string): string[] {
  return sectionBlocks(text, prefix, where)
    .filter((n) => n.type === 'paragraph')
    .map((n) => toString(n));
}

/**
 * The items of the ordered lists directly under a section, in order, each as
 * the text of its first strong span (its title, or null) and its whole text.
 */
export function sectionOrderedItems(text: string, prefix: string, where: string): { title: string | null; text: string }[] {
  return sectionBlocks(text, prefix, where)
    .filter((n): n is List => n.type === 'list' && n.ordered === true)
    .flatMap((l) => l.children)
    .map((item) => {
      const first = item.children[0];
      const strong = first?.type === 'paragraph' ? first.children.find((c) => c.type === 'strong') : undefined;
      return { title: strong ? toString(strong).trim() : null, text: toString(item) };
    });
}
