// Text taken out of HTML or Markdown by removing tags and comments. Each
// removal repeats until nothing changes, so a removal cannot join two
// fragments into a new tag or comment ("<scr<b>ipt>" leaves no "<script>").
// The results are compared or counted, never written back into a page.
// No imports, so the check scripts can load this with plain Node.

function untilStable(s: string, step: (s: string) => string): string {
  let prev: string;
  do {
    prev = s;
    s = step(s);
  } while (s !== prev);
  return s;
}

/** `html` with every tag replaced by `replacement` (default: removed). */
export function stripTags(html: string, replacement = ''): string {
  return untilStable(html, (s) => s.replace(/<[^<>]*>/g, replacement));
}

/** `text` with every HTML comment removed. */
export function stripComments(text: string): string {
  return untilStable(text, (s) => s.replace(/<!--[\s\S]*?-->/g, ''));
}
