// Text taken out of HTML or Markdown by removing tags and comments. Both are
// character scans rather than regex replacements, so removing one piece can
// never join two fragments into a new tag or comment ("<scr<b>ipt>" leaves no
// "<script>"; CodeQL js/incomplete-multi-character-sanitization).
// The results are compared or counted, never written back into a page.
// No imports, so the check scripts can load this with plain Node.

/**
 * `html` with every tag replaced by `replacement` (default: removed). A "<"
 * followed by a letter, "/", "!" or "?" opens a tag, as in HTML, so "x < 5"
 * stays text; inside a tag any "<" nests, and text resumes only once every
 * open "<" has its ">". An unclosed tag drops the rest of the string.
 */
export function stripTags(html: string, replacement = ''): string {
  let out = '';
  let depth = 0;
  for (let i = 0; i < html.length; i++) {
    const ch = html[i]!;
    if (ch === '<' && (depth > 0 || /[A-Za-z/!?]/.test(html[i + 1] ?? ''))) {
      depth += 1;
    } else if (ch === '>' && depth > 0) {
      depth -= 1;
      if (depth === 0) out += replacement;
    } else if (depth === 0) {
      out += ch;
    }
  }
  return out;
}

/** `text` with every HTML comment removed; an unclosed "<!--" drops the rest. */
export function stripComments(text: string): string {
  let s = text;
  for (let i = s.indexOf('<!--'); i !== -1; i = s.indexOf('<!--')) {
    const end = s.indexOf('-->', i + 4);
    s = end === -1 ? s.slice(0, i) : s.slice(0, i) + s.slice(end + 3);
  }
  return s;
}
