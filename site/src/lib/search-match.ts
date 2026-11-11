// Loose matches in site search. When no indexed word starts with a query
// word, Pagefind still returns pages, matched on a much shorter prefix:
// "zzzqqq" finds pages that hold a lone "z". The search dialog keeps a
// result only when, for every query word, one of the words the result
// matched shares at least MIN_SHARED leading letters with it (or all of the
// query word, when it is shorter). Stemmed and prefix matches pass:
// "checkpoints" matches "checkpoint." and "check" matches "checkpoint".
// This file runs in the browser.

export const MIN_SHARED = 3;

/** Lower case, letters and digits only: "(V102);" -> "v102". */
export function normalWord(word: string): string {
  return word.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
}

function shared(a: string, b: string): number {
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  return i;
}

/** The query split into normalised words, as the dialog compares them. */
export function queryWords(query: string): string[] {
  return query.split(/\s+/).map(normalWord).filter((w) => w !== '');
}

/**
 * True when every query word shares enough leading letters with one of the
 * matched words. `matched` are the page's words at Pagefind's match locations.
 * An identifier joined by underscores or other marks ("debug_code_change")
 * is compared with those marks removed on both sides; a path or file name
 * in the page ("spec/WHITEPAPER.md") is also compared part by part.
 */
export function isRealMatch(query: string, matched: readonly string[]): boolean {
  const words = queryWords(query);
  if (words.length === 0) return false;
  // Each matched word whole ("debug_code_change" -> "debugcodechange") and in
  // its parts ("spec/WHITEPAPER.md" -> "spec", "whitepaper", "md").
  const found = matched
    .flatMap((w) => [normalWord(w), ...w.split(/[^\p{L}\p{N}]+/u).map(normalWord)])
    .filter((w) => w !== '');
  return words.every((q) => found.some((w) => shared(q, w) >= Math.min(MIN_SHARED, q.length)));
}

/** The words of `content` at Pagefind's word `locations`. */
export function wordsAt(content: string, locations: readonly number[]): string[] {
  const words = content.split(/\s+/).filter((w) => w !== '');
  return locations.map((i) => words[i] ?? '');
}
