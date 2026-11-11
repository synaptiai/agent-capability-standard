// Page facts read from the Markdown itself, handed to the layout through
// `remarkPluginFrontmatter.page`:
// - title: the text of the first H1, or the frontmatter `name` of a SKILL.md.
//   The H1 stays in the body, so its own anchor and the duplicate-heading
//   suffixes after it do not change.
// - description: the frontmatter `description`, or else the first paragraph
//   after the H1 that has text (a row of badges does not count), cut at a
//   sentence end before 200 characters. A paragraph ending in a colon takes
//   the list after it along.
// - meta: the block of `**Key:** value` lines directly after the H1 (the spec's
//   Version, Status and Date; an RFC's Status; a methodology document's
//   `**Document Status**: Normative`). Only that block counts: a Status line
//   further down the page is ordinary text. The block is turned into a
//   `<dl class="page-meta">` in place, so links inside a value still render.
// Runs after remark-repo-links, so links in the block are already rewritten.
import type { Paragraph, PhrasingContent, Root, RootContent } from 'mdast';
import { toString } from 'mdast-util-to-string';
import type { VFile } from 'vfile';
import { headingText } from '../lib/anchors';
import { sourceOf } from './source';

export interface PageMeta {
  title: string | null;
  description: string | null;
  /** Every key of the header block, in order, as plain text. */
  meta: { key: string; value: string }[];
  version: string | null;
  status: string | null;
  documentStatus: string | null;
  date: string | null;
}

const KEY = /^([A-Z][A-Za-z0-9 ./()-]{0,40}?)\s*:?$/;
const MAX_DESCRIPTION = 200;

/** Split a paragraph's inline nodes into lines at hard and soft breaks. */
function splitLines(p: Paragraph): PhrasingContent[][] {
  const lines: PhrasingContent[][] = [[]];
  for (const child of p.children) {
    if (child.type === 'break') {
      lines.push([]);
      continue;
    }
    if (child.type === 'text' && child.value.includes('\n')) {
      const parts = child.value.split('\n');
      parts.forEach((part, i) => {
        if (i > 0) lines.push([]);
        if (part !== '') lines.at(-1)!.push({ type: 'text', value: part });
      });
      continue;
    }
    lines.at(-1)!.push(child);
  }
  return lines.filter((l) => l.length > 0);
}

interface Entry {
  key: string;
  value: PhrasingContent[];
}

/** `**Key:** value` or `**Key**: value`; null when the line is not one. */
function keyLine(line: PhrasingContent[]): Entry | null {
  const [first, ...rest] = line;
  if (first?.type !== 'strong') return null;
  const strongText = toString(first).trim();
  const m = KEY.exec(strongText);
  if (!m) return null;
  const colonInside = strongText.endsWith(':');
  const value = [...rest];
  const head = value[0];
  if (!colonInside) {
    if (head?.type !== 'text' || !head.value.startsWith(':')) return null;
    value[0] = { type: 'text', value: head.value.slice(1) };
  }
  const v0 = value[0];
  if (v0?.type === 'text') value[0] = { type: 'text', value: v0.value.replace(/^\s+/, '') };
  const last = value.at(-1);
  if (last?.type === 'text') value[value.length - 1] = { type: 'text', value: last.value.replace(/\s+$/, '') };
  return { key: m[1]!.trim(), value };
}

/** The header block's entries, or null if the paragraph is not one. */
export function parseHeaderBlock(p: Paragraph): Entry[] | null {
  const entries: Entry[] = [];
  for (const line of splitLines(p)) {
    const e = keyLine(line);
    if (e) {
      entries.push(e);
      continue;
    }
    const prev = entries.at(-1);
    if (!prev) return null;
    prev.value.push({ type: 'text', value: ' ' }, ...line);
  }
  return entries.length > 0 ? entries : null;
}

function plain(nodes: PhrasingContent[]): string {
  return nodes.map((n) => toString(n)).join('').replace(/\s+/g, ' ').trim();
}

/** Cut at the last sentence end before the limit, or at a word boundary. */
export function shortDescription(text: string, max = MAX_DESCRIPTION): string {
  const t = text.replace(/\s+/g, ' ').trim();
  if (t.length <= max) return t;
  const window = t.slice(0, max);
  const ends = [...window.matchAll(/[.!?](?=\s)/g)];
  const lastEnd = ends.at(-1);
  if (lastEnd?.index !== undefined && lastEnd.index > 40) return window.slice(0, lastEnd.index + 1);
  const space = window.lastIndexOf(' ');
  return `${window.slice(0, space > 0 ? space : max).replace(/[,;:]$/, '')}...`;
}

function toDl(entries: Entry[]): RootContent {
  return {
    type: 'paragraph',
    data: { hName: 'dl', hProperties: { className: ['page-meta'] } },
    children: entries.map(
      (e) =>
        ({
          type: 'emphasis',
          data: { hName: 'div' },
          children: [
            { type: 'emphasis', data: { hName: 'dt' }, children: [{ type: 'text', value: e.key }] },
            { type: 'emphasis', data: { hName: 'dd' }, children: e.value },
          ],
        }) as PhrasingContent,
    ),
  };
}

function str(v: unknown): string | null {
  return typeof v === 'string' && v.trim() !== '' ? v.trim() : null;
}

export default function remarkPageMeta() {
  return (tree: Root, file: VFile): void => {
    sourceOf(file, 'remark-page-meta');
    const astro = ((file.data as { astro?: { frontmatter?: Record<string, unknown> } }).astro ??= {});
    const fm = (astro.frontmatter ??= {});

    const h1Index = tree.children.findIndex((n) => n.type === 'heading' && n.depth === 1);
    const h1 = h1Index === -1 ? undefined : tree.children[h1Index];
    const title = h1?.type === 'heading' ? headingText(h1).trim() : str(fm.name);

    let entries: Entry[] = [];
    let headerIndex = -1;
    const next = h1Index === -1 ? undefined : tree.children[h1Index + 1];
    if (next?.type === 'paragraph') {
      const parsed = parseHeaderBlock(next);
      if (parsed) {
        entries = parsed;
        headerIndex = h1Index + 1;
      }
    }
    const meta = entries.map((e) => ({ key: e.key, value: plain(e.value) }));
    const get = (k: string): string | null => meta.find((m) => m.key.toLowerCase() === k)?.value ?? null;

    let description = str(fm.description);
    if (description === null) {
      const start = h1Index === -1 ? 0 : h1Index + 1;
      // Skip the header block and rows of badges (paragraphs of images only).
      const at = tree.children.findIndex(
        (n, i) =>
          i >= start &&
          i !== headerIndex &&
          n.type === 'paragraph' &&
          toString(n, { includeImageAlt: false }).trim() !== '',
      );
      const para = tree.children[at];
      if (para) {
        let text = toString(para, { includeImageAlt: false }).trim();
        // "This standard specifies:" introduces a list; the list is the substance.
        const list = tree.children[at + 1];
        if (text.endsWith(':') && list?.type === 'list') {
          text = `${text} ${list.children.map((item) => toString(item).replace(/\s+/g, ' ').trim()).join('; ')}`;
        }
        description = shortDescription(text);
      }
    } else {
      description = shortDescription(description);
    }

    if (headerIndex !== -1) tree.children[headerIndex] = toDl(entries);

    const page: PageMeta = {
      title,
      description,
      meta,
      version: get('version'),
      status: get('status'),
      documentStatus: get('document status'),
      date: get('date'),
    };
    fm.page = page;
  };
}
