// The "On this page" entries of a rendered page: its h2 and h3 headings, in
// order, read from the page body HTML. Works the same for Markdown pages and
// generated pages, which have no heading list of their own.

export interface TocEntry {
  depth: 2 | 3;
  id: string;
  text: string;
}

const ENTITIES: Readonly<Record<string, string>> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' };

export function decodeEntities(s: string): string {
  return s.replace(/&(#x[0-9a-fA-F]+|#\d+|[a-zA-Z]+);/g, (m, e: string) => {
    if (e.startsWith('#x')) return String.fromCodePoint(parseInt(e.slice(2), 16));
    if (e.startsWith('#')) return String.fromCodePoint(Number(e.slice(1)));
    return ENTITIES[e] ?? m;
  });
}

export function tocEntries(html: string): TocEntry[] {
  const out: TocEntry[] = [];
  for (const m of html.matchAll(/<h([23])\b([^>]*)>([\s\S]*?)<\/h\1>/g)) {
    const id = /\sid="([^"]+)"/.exec(m[2]!)?.[1];
    if (!id) continue;
    const text = decodeEntities(m[3]!.replace(/<[^>]*>/g, '')).replace(/\s+/g, ' ').trim();
    if (text) out.push({ depth: Number(m[1]) as 2 | 3, id, text });
  }
  return out;
}
