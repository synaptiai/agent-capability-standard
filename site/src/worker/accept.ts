// Reading the Accept request header (RFC 9110, section 12.5.1).
//
// A media range matches a type exactly ("text/markdown"), by its top-level
// type ("text/*") or as anything ("*/*"). The quality a type gets is the q of
// the most specific range that matches it, and 0 when none does.

export interface MediaRange {
  type: string;
  subtype: string;
  q: number;
  /** Position in the header, for breaking ties. */
  index: number;
}

/** The media ranges of an Accept header, in header order. Unreadable entries are left out. */
export function parseAccept(header: string | null | undefined): MediaRange[] {
  if (!header) return [];
  const out: MediaRange[] = [];
  header.split(',').forEach((part, index) => {
    const [range, ...params] = part.split(';').map((s) => s.trim());
    const m = /^([a-z0-9!#$%&'*+.^_`|~-]+)\/([a-z0-9!#$%&'*+.^_`|~-]+)$/i.exec(range ?? '');
    if (!m) return;
    let q = 1;
    for (const p of params) {
      const qm = /^q\s*=\s*([0-9.]+)$/i.exec(p);
      if (qm) {
        const v = Number(qm[1]);
        q = Number.isFinite(v) ? Math.min(Math.max(v, 0), 1) : 0;
      }
    }
    out.push({ type: m[1]!.toLowerCase(), subtype: m[2]!.toLowerCase(), q, index });
  });
  return out;
}

/** How specific a range is: 2 exact, 1 "type/*", 0 "*\/*". */
function specificity(r: MediaRange): number {
  return r.type === '*' ? 0 : r.subtype === '*' ? 1 : 2;
}

export interface Match {
  q: number;
  /** 2 exact, 1 "type/*", 0 "*\/*", -1 no range matched. */
  specificity: number;
  index: number;
}

/** The quality `mediaType` gets from `ranges`: the q of the most specific matching range. */
export function quality(ranges: readonly MediaRange[], mediaType: string): Match {
  const [type, subtype] = mediaType.toLowerCase().split('/');
  let best: MediaRange | null = null;
  for (const r of ranges) {
    const matches = (r.type === '*' && r.subtype === '*') || (r.type === type && (r.subtype === '*' || r.subtype === subtype));
    if (!matches) continue;
    if (best === null || specificity(r) > specificity(best)) best = r;
  }
  return best === null ? { q: 0, specificity: -1, index: -1 } : { q: best.q, specificity: specificity(best), index: best.index };
}

/**
 * Whether the client prefers the Markdown copy of a page to the HTML page.
 *
 * True when text/markdown has a higher q than text/html. On equal q (above
 * 0), the type named by the more specific range wins, so "text/markdown, *\/*"
 * gets Markdown and "*\/*" or "text/*" alone get HTML; when both are named
 * exactly with the same q, the one listed first wins. No Accept header, or
 * one that names neither, gets HTML.
 */
export function prefersMarkdown(header: string | null | undefined): boolean {
  const ranges = parseAccept(header);
  const md = quality(ranges, 'text/markdown');
  const html = quality(ranges, 'text/html');
  if (md.q <= 0) return false;
  if (md.q !== html.q) return md.q > html.q;
  if (md.specificity !== html.specificity) return md.specificity > html.specificity;
  return md.specificity === 2 && md.index < html.index;
}

/** Whether the client accepts text/html at all (q above 0 through any range). */
export function acceptsHtml(header: string | null | undefined): boolean {
  return quality(parseAccept(header), 'text/html').q > 0;
}

/**
 * Whether the Accept header names text/html itself. Browsers do on every
 * page load; curl ("*\/*"), HTTP libraries and most agents do not.
 */
export function namesHtml(header: string | null | undefined): boolean {
  const m = quality(parseAccept(header), 'text/html');
  return m.specificity === 2 && m.q > 0;
}

/** Whether the client accepts `mediaType` (q above 0 through any range); no header accepts everything. */
export function accepts(header: string | null | undefined, mediaType: string): boolean {
  if (!header || header.trim() === '') return true;
  return quality(parseAccept(header), mediaType).q > 0;
}
