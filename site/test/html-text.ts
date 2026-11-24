/**
 * Text out of the site's own built HTML, for tests. Each function reads its
 * input once from left to right with indexOf; none rewrites markup with a
 * regular expression, so nothing is "sanitised" twice or in part. They read
 * HTML this repository builds, never input from elsewhere.
 */

const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr']);

/** `html` with every tag (`<` to the next `>`) dropped; an unclosed `<` and what follows it stay. */
export function withoutTags(html: string): string {
  let out = '';
  let at = 0;
  for (;;) {
    const lt = html.indexOf('<', at);
    if (lt < 0) return out + html.slice(at);
    const gt = html.indexOf('>', lt + 1);
    if (gt < 0) return out + html.slice(at);
    out += html.slice(at, lt);
    at = gt + 1;
  }
}

/**
 * The text of `html` a reader is given: tags dropped, and nothing inside an
 * `<svg>` element or an element marked `aria-hidden="true"`. Elements nest
 * by name; void elements and `/>` open nothing.
 */
export function visibleText(html: string): string {
  let out = '';
  const open: { name: string; hidden: boolean }[] = [];
  const hidden = () => open.some((e) => e.hidden);
  let at = 0;
  for (;;) {
    const lt = html.indexOf('<', at);
    const gt = lt < 0 ? -1 : html.indexOf('>', lt + 1);
    if (gt < 0) {
      if (!hidden()) out += html.slice(at);
      return out;
    }
    if (!hidden()) out += html.slice(at, lt);
    at = gt + 1;
    const tag = html.slice(lt + 1, gt);
    const name = /^\/?([A-Za-z][\w-]*)/.exec(tag)?.[1]?.toLowerCase();
    if (name === undefined) continue;
    if (tag.startsWith('/')) {
      const i = open.map((e) => e.name).lastIndexOf(name);
      if (i >= 0) open.length = i;
    } else if (!tag.endsWith('/') && !VOID.has(name)) {
      open.push({ name, hidden: name === 'svg' || /(^|\s)aria-hidden="true"/.test(tag) });
    }
  }
}

/** The URLs `llms-full.txt` marks its pages with: each a line `<!-- URL -->`. */
export function markerUrls(text: string): string[] {
  return text
    .split('\n')
    .filter((l) => l.startsWith('<!-- ') && l.endsWith(' -->'))
    .map((l) => l.slice('<!-- '.length, -' -->'.length))
    .filter((url) => url.length > 0 && !/\s/.test(url));
}
