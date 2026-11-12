// Figures placed inside rendered Markdown (visual spec 3.7 and 3.9). The page
// takes the source's rendered HTML, cuts it after the headings the anchor map
// names, and renders a figure component at each cut. A heading is found by
// its level and the start of its text; each anchor must match exactly one
// heading, or the build fails, so an edit to the source cannot move or drop
// a figure without notice.

export interface HtmlHeading {
  level: number;
  id: string;
  /** Visible text, tags removed, whitespace collapsed. */
  text: string;
  /** Index just after the closing tag. */
  end: number;
}

const HEADING = /<h([1-6])\b([^>]*)>([\s\S]*?)<\/h\1>/g;

const decode = (s: string) =>
  s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;|&#x27;/g, "'").replace(/&amp;/g, '&');

/** Every heading of an HTML string, in order. Text inside aria-hidden svg (chapter glyphs) is empty, so it is skipped by removing tags. */
export function htmlHeadings(html: string): HtmlHeading[] {
  return [...html.matchAll(HEADING)].map((m) => ({
    level: Number(m[1]),
    id: /\bid="([^"]*)"/.exec(m[2]!)?.[1] ?? '',
    text: decode(m[3]!.replace(/<[^>]+>/g, '')).replace(/\s+/g, ' ').trim(),
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
