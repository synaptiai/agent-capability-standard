// The words of a search, shared by the build and the worker: the build writes
// each page's search terms into /api/v1/pages.json with these functions, and
// the MCP server's search_standard tool turns a query into terms with the same
// ones, so the two always agree. No imports: the worker bundle and the build
// both load this file.

/** The words of a text, lower case: runs of letters and digits. */
export function words(s: string): string[] {
  return s.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? [];
}

/** Words too common to narrow a search. */
export const STOPWORDS = new Set(
  'a an and are as at be before by can do does for from how i in into is it its of on or should that the then this to what when where which who why with'.split(' '),
);

/**
 * A crude stem, so "mutation", "mutates" and "mutate" meet at "mutat", and
 * "verifies", "verified", "verifying" and "verify" meet at "verifi": "-ies"
 * becomes "-y", and a final "-y" becomes "-i".
 */
export function stem(word: string): string {
  let w = word;
  for (const suffix of ['ations', 'ation', 'ions', 'ion', 'ing', 'ies', 'ed', 'es', 's', 'e']) {
    if (w.endsWith(suffix) && w.length - suffix.length >= 4) {
      w = suffix === 'ies' ? `${w.slice(0, -3)}y` : w.slice(0, -suffix.length);
      break;
    }
  }
  return w.endsWith('y') && w.length >= 5 ? `${w.slice(0, -1)}i` : w;
}

/** The search terms of a query: its words without stopwords (all of them when every word is one), stemmed. */
export function searchTerms(query: string): string[] {
  const all = words(query);
  const kept = all.filter((w) => !STOPWORDS.has(w));
  return [...new Set((kept.length > 0 ? kept : all).map(stem))];
}

/** A diagnostic code such as V102 or W602, as words() returns it. */
const CODE_RE = /^[a-z][0-9]{3}$/;

/** True for a search term that is a diagnostic code, such as "w602". */
export function isCode(term: string): boolean {
  return CODE_RE.test(term);
}

/** How many of a page's own terms it keeps, besides its diagnostic codes. */
export const TERMS_PER_PAGE = 40;

/** The stems of a page's body text, with how often each occurs. Link targets and bare URLs are left out. */
export function termCounts(markdown: string): Map<string, number> {
  const text = markdown.replace(/\]\([^)\s]*\)/g, '] ').replace(/https?:\/\/\S+/g, ' ');
  const counts = new Map<string, number>();
  for (const w of words(text)) {
    if (STOPWORDS.has(w) || (w.length < 3 && !CODE_RE.test(w)) || /^[0-9]+$/.test(w)) continue;
    const s = stem(w);
    counts.set(s, (counts.get(s) ?? 0) + 1);
  }
  return counts;
}

/**
 * The search terms of each page: every diagnostic code it names, then the
 * TERMS_PER_PAGE stems that best set it apart (most frequent in the page,
 * weighed by how few pages use them: tf-idf), sorted. One space-separated
 * string per page, in the order of `bodies`.
 */
export function pageSearchTerms(bodies: readonly string[]): string[] {
  const counts = bodies.map(termCounts);
  const df = new Map<string, number>();
  for (const c of counts) for (const t of c.keys()) df.set(t, (df.get(t) ?? 0) + 1);
  const n = bodies.length;
  return counts.map((c) => {
    const codes = [...c.keys()].filter((t) => CODE_RE.test(t));
    const top = [...c.entries()]
      .filter(([t]) => !CODE_RE.test(t))
      .map(([t, tf]) => ({ t, w: tf * Math.log((n + 1) / df.get(t)!) }))
      .sort((a, b) => b.w - a.w || a.t.localeCompare(b.t))
      .slice(0, TERMS_PER_PAGE)
      .map((x) => x.t);
    return [...new Set([...codes, ...top])].sort().join(' ');
  });
}
