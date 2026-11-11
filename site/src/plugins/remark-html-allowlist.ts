// Raw HTML in the sources must render the same on the site as on GitHub, so
// only a few harmless elements are allowed: details (with at most `open`),
// summary, br, sup and sub with no attributes, and an <a> that carries only a
// name or id (an anchor target). GitHub strips event handlers and styles, so
// an attribute that would only take effect on the site is refused. Well-formed
// HTML comments are allowed; a comment a browser would end early (`<!-->`,
// `<!--->`, one containing `--`) is refused, because what follows it is live
// HTML. Anything else, such as a bare <id> in prose that a browser would read
// as an element, fails the build with its path:line.
import type { Html, Root } from 'mdast';
import { visit } from 'unist-util-visit';
import type { VFile } from 'vfile';
import { failWith, lineOf, sourceOf } from './source';

export const ALLOWED_ELEMENTS: ReadonlySet<string> = new Set(['details', 'summary', 'br', 'sup', 'sub', 'a']);
/** The attributes each allowed element may carry. */
const ATTRIBUTES: Readonly<Record<string, ReadonlySet<string>>> = {
  a: new Set(['name', 'id']),
  details: new Set(['open']),
  summary: new Set(),
  br: new Set(),
  sup: new Set(),
  sub: new Set(),
};

// One left-to-right pass, as a browser reads it: whichever of a comment or a
// tag starts first wins, so a "<!--" inside a tag or a quoted attribute value
// is part of that tag. A comment counts only when the HTML parser reads it the
// same way: its text does not start with `>` or `->` and contains no `--`.
const TOKEN = /<!--(?!>|->)(?:(?!--)[\s\S])*-->|<(\/?)([A-Za-z][A-Za-z0-9-]*)((?:"[^"]*"|'[^']*'|[^'">])*)>/g;
// Anything left that a browser could read as markup: a tag with no closing
// ">", a malformed comment, a <!...> or <?...> construct.
const LEFTOVER = /<[A-Za-z/!?][^\n]*/;
const ATTR = /([^\s=/]+)(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'>]+))?/g;

/** Problems with one raw HTML string; empty when it is allowed. */
export function checkHtml(value: string): string[] {
  const problems: string[] = [];
  const leftover = LEFTOVER.exec(value.replace(TOKEN, ''));
  if (leftover) problems.push(`unclosed or malformed tag: ${leftover[0].slice(0, 60)}`);
  for (const m of value.matchAll(TOKEN)) {
    const [, closing, rawName, attrs] = m;
    if (rawName === undefined) continue; // a comment
    const name = rawName!.toLowerCase();
    if (!ALLOWED_ELEMENTS.has(name)) {
      problems.push(`<${closing}${rawName}> is not an allowed HTML element`);
      continue;
    }
    if (closing) continue;
    const names = [...attrs!.matchAll(ATTR)].map((a) => a[1]!.toLowerCase());
    const allowed = ATTRIBUTES[name]!;
    const bad = names.filter((n) => !allowed.has(n));
    if (name === 'a') {
      if (bad.length > 0 || names.length === 0) {
        problems.push(`<a> may carry only name or id, found: ${names.join(', ') || 'nothing'}`);
      }
    } else if (bad.length > 0) {
      problems.push(
        allowed.size === 0
          ? `<${name}> may carry no attributes, found: ${names.join(', ')}`
          : `<${name}> may carry only ${[...allowed].join(', ')}, found: ${names.join(', ')}`,
      );
    }
  }
  return problems;
}

export default function remarkHtmlAllowlist() {
  return (tree: Root, file: VFile): void => {
    const src = sourceOf(file, 'remark-html-allowlist');
    const problems: string[] = [];
    visit(tree, 'html', (node: Html) => {
      for (const p of checkHtml(node.value)) problems.push(`${lineOf(src, node)}: ${p}: ${node.value.trim().slice(0, 80)}`);
    });
    failWith('remark-html-allowlist', problems);
  };
}
