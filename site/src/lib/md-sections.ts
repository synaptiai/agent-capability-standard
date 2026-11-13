// Blocks of a Markdown file read by section, for figures drawn from the
// table, list or fence of the section they sit in (visual spec 1.1 rule 3).
// A section is a heading and everything up to the next heading of the same
// or a higher level. Headings are matched by the start of their text, so
// "5.2 " finds "5.2 Step Definition" and nothing else.
import type { Code, Heading, List, Root, RootContent, Table } from 'mdast';
import { toString } from 'mdast-util-to-string';
import { visit } from 'unist-util-visit';
import { headingText, parseMarkdown, stripFrontmatter } from './anchors';

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

/** Index of the depth-`depth` heading titled exactly `title` among the root's children and of the node that ends its section (-1: none). */
function titled(text: string, title: string, depth: number, where: string): { at: number; end: number } | null {
  const nodes = tree(text).children;
  const starts = nodes.flatMap((n, i) => (n.type === 'heading' && n.depth === depth && headingText(n).trim() === title ? [i] : []));
  if (starts.length === 0) return null;
  if (starts.length > 1) throw new Error(`${where}: ${starts.length} headings "${'#'.repeat(depth)} ${title}", expected one`);
  const at = starts[0]!;
  return { at, end: nodes.findIndex((n, j) => j > at && n.type === 'heading' && n.depth <= depth) };
}

/**
 * The blocks under the depth-`depth` heading whose text is exactly `title`,
 * or null when there is none. Throws when several match. Headings are the
 * parsed tree's, so a "## " line inside a code fence neither opens nor ends
 * a section.
 */
export function sectionByTitle(text: string, title: string, depth: number, where: string): RootContent[] | null {
  const s = titled(text, title, depth, where);
  return s && tree(text).children.slice(s.at + 1, s.end === -1 ? undefined : s.end);
}

/**
 * Blocks split at their headings of `depth`: the blocks before the first
 * such heading (`title` null), then each heading's text with the blocks up
 * to the next heading of that depth or higher.
 */
export function splitAtHeadings(blocks: RootContent[], depth: number): { title: string | null; blocks: RootContent[] }[] {
  const out: { title: string | null; blocks: RootContent[] }[] = [{ title: null, blocks: [] }];
  for (const b of blocks) {
    if (b.type === 'heading' && b.depth <= depth) out.push({ title: b.depth === depth ? headingText(b).trim() : null, blocks: [] });
    else out.at(-1)!.blocks.push(b);
  }
  return out;
}

/** Every code block in `blocks`, those inside lists and quotes included, in order. */
export function codeBlocks(blocks: RootContent[]): Code[] {
  const out: Code[] = [];
  for (const b of blocks) visit(b, 'code', (c: Code) => void out.push(c));
  return out;
}

/**
 * The source lines of the section under the depth-`depth` heading whose text
 * is exactly `title` (the heading line excluded), each flagged when it lies in
 * a code block; null when there is no such heading.
 */
export function sectionLines(text: string, title: string, depth: number, where: string): { text: string; code: boolean }[] | null {
  const s = titled(text, title, depth, where);
  if (s === null) return null;
  const nodes = tree(text).children;
  const body = stripFrontmatter(text).split('\n');
  const code = codeLineSet(text);
  // Lines are 1-based: the heading's last line number is the 0-based index of the line after it.
  const from = nodes[s.at]!.position!.end.line;
  const to = s.end === -1 ? body.length : nodes[s.end]!.position!.start.line - 1;
  return body.slice(from, to).map((l, k) => ({ text: l, code: code.has(from + k + 1) }));
}

/** 1-based line numbers, in the text with any frontmatter removed, that lie in a code block. */
function codeLineSet(text: string): Set<number> {
  const out = new Set<number>();
  visit(tree(text), 'code', (c: Code) => {
    for (let l = c.position!.start.line; l <= c.position!.end.line; l++) out.add(l);
  });
  return out;
}

/**
 * Per line of `text` (0-based, frontmatter included), whether it lies in a
 * fenced or indented code block, for the parsers that read a file line by
 * line: a heading test must skip these lines.
 */
export function codeLines(text: string): boolean[] {
  const lines = text.split('\n');
  const offset = lines.length - stripFrontmatter(text).split('\n').length;
  const code = codeLineSet(text);
  return lines.map((_, i) => i >= offset && code.has(i - offset + 1));
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
 * The text of a block node with its child blocks (paragraphs, sub-lists,
 * sub-items) joined by newlines. `toString` joins them with nothing, so a
 * word that ends one line runs into the first word of the next.
 */
export function blockText(n: RootContent | Root): string {
  if (n.type === 'list' || n.type === 'listItem' || n.type === 'blockquote' || n.type === 'root') {
    return (n.children as RootContent[]).map((c) => blockText(c)).join('\n');
  }
  return toString(n);
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
      return { title: strong ? toString(strong).trim() : null, text: blockText(item) };
    });
}
