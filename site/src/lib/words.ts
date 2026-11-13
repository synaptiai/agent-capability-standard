// Small helpers for the sentences the site writes from data (captions,
// titles, summaries), shared so every page counts and lists the same way.

/** "1 step", "3 steps"; `many` defaults to `one` + "s". */
export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** "a", "a and b", "a, b and c"; "" for none. */
export function andList(xs: readonly string[]): string {
  return xs.length <= 1 ? (xs[0] ?? '') : `${xs.slice(0, -1).join(', ')} and ${xs.at(-1)}`;
}
