// Reading part of a page's Markdown copy: one section by its heading, and at
// most PAGE_CHUNK characters per call, so a long page (the Standard is over
// 100,000 characters) never fills a client's limit on tool output. The MCP
// server's read_page tool and the in-page WebMCP read_page tool both use it.
// No imports: the worker bundle and the browser script both load this file.

/** The most characters one read returns. */
export const PAGE_CHUNK = 25_000;

export interface Heading {
  level: number;
  text: string;
  /** Character offset of the heading line in the Markdown. */
  start: number;
}

/** The ATX headings (## and deeper; # is the page title) of a Markdown text, skipping fenced code. */
export function markdownHeadings(markdown: string): Heading[] {
  const out: Heading[] = [];
  let fence: string | null = null;
  let at = 0;
  for (const line of markdown.split('\n')) {
    const f = /^\s{0,3}(`{3,}|~{3,})/.exec(line);
    if (f) {
      const mark = f[1]!;
      if (fence === null) fence = mark;
      else if (mark[0] === fence[0] && mark.length >= fence.length && line.trim() === mark) fence = null;
    } else if (fence === null) {
      const h = /^(#{2,6})\s+(.*?)\s*#*\s*$/.exec(line);
      if (h) out.push({ level: h[1]!.length, text: plainHeading(h[2]!), start: at });
    }
    at += line.length + 1;
  }
  return out;
}

/** A heading's text without Markdown: links become their text, code marks and emphasis go. */
function plainHeading(s: string): string {
  return s
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[`*_]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function same(a: string, b: string): boolean {
  return a.toLowerCase() === b.toLowerCase();
}

export type PagePart =
  | {
      ok: true;
      /** The text returned: the section asked for (or the page), from offset, at most PAGE_CHUNK characters. */
      markdown: string;
      offset: number;
      /** Where the next read starts, or null when this one reached the end. */
      nextOffset: number | null;
      /** The length of the section asked for, or of the page. */
      totalLength: number;
    }
  | { ok: false; message: string; headings: string[] };

/**
 * The part of `markdown` to return: the section whose heading is `section`
 * (from the heading to the next heading of the same or a higher level), or
 * the whole text; then from `offset`, at most `max` characters, cut at the
 * end of a line when the text goes on.
 */
export function pagePart(markdown: string, opts: { section?: string; offset?: number; max?: number } = {}): PagePart {
  const max = opts.max ?? PAGE_CHUNK;
  let text = markdown;
  if (opts.section !== undefined) {
    const heads = markdownHeadings(markdown);
    // Each heading's path: the headings above it, then itself ("Contract > Inputs").
    const paths: string[][] = [];
    heads.forEach((h, j) => {
      let parent = -1;
      for (let k = j - 1; k >= 0; k--) if (heads[k]!.level < h.level) { parent = k; break; }
      paths.push([...(parent === -1 ? [] : paths[parent]!), h.text]);
    });
    // "Inputs" names a heading; "Claude Code skill > Inputs" names it under a parent.
    const want = opts.section.split('>').map((x) => x.trim()).filter((x) => x.length > 0);
    const hits = heads
      .map((_, j) => j)
      .filter((j) => {
        const p = paths[j]!;
        return want.length > 0 && want.length <= p.length && want.every((w, k) => same(w, p[p.length - want.length + k]!));
      });
    if (hits.length === 0) {
      return { ok: false, message: `The page has no section headed "${opts.section}".`, headings: heads.map((h) => h.text) };
    }
    if (hits.length > 1) {
      const names = hits.map((j) => paths[j]!.join(' > '));
      return {
        ok: false,
        message: `The page has ${hits.length} sections headed "${opts.section}". Name one with the headings above it: ${names.map((n) => `"${n}"`).join(', ')}.`,
        headings: names,
      };
    }
    const i = hits[0]!;
    const h = heads[i]!;
    const next = heads.slice(i + 1).find((n) => n.level <= h.level);
    text = markdown.slice(h.start, next ? next.start : markdown.length);
  }
  const offset = opts.offset ?? 0;
  if (offset > text.length) {
    return { ok: false, message: `offset ${offset} is past the end of the text (${text.length} characters).`, headings: [] };
  }
  let end = Math.min(text.length, offset + max);
  if (end < text.length) {
    const nl = text.lastIndexOf('\n', end - 1);
    if (nl >= offset) end = nl + 1;
  }
  return { ok: true, markdown: text.slice(offset, end), offset, nextOffset: end < text.length ? end : null, totalLength: text.length };
}

/** The H2 headings of a Markdown text: the sections a caller can ask for by name. */
export function sectionNames(markdown: string): string[] {
  return markdownHeadings(markdown)
    .filter((h) => h.level === 2)
    .map((h) => h.text);
}
