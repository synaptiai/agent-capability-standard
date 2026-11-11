// Raw HTML in the sources must render the same on the site as on GitHub, so
// only a few harmless elements are allowed: details, summary, br, sup, sub, and
// an <a> that carries only a name or id (an anchor target). HTML comments are
// allowed. Anything else, such as a bare <id> in prose that a browser would
// read as an element, fails the build with its path:line.
import type { Html, Root } from 'mdast';
import { visit } from 'unist-util-visit';
import type { VFile } from 'vfile';
import { failWith, lineOf, sourceOf } from './source';

export const ALLOWED_ELEMENTS: ReadonlySet<string> = new Set(['details', 'summary', 'br', 'sup', 'sub', 'a']);
const A_ATTRIBUTES: ReadonlySet<string> = new Set(['name', 'id']);

const COMMENT = /<!--[\s\S]*?-->/g;
const TAG = /<(\/?)([A-Za-z][A-Za-z0-9-]*)([^>]*)>/g;
const ATTR = /([^\s=/]+)(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'>]+))?/g;

/** Problems with one raw HTML string; empty when it is allowed. */
export function checkHtml(value: string): string[] {
  const problems: string[] = [];
  const html = value.replace(COMMENT, '');
  for (const m of html.matchAll(TAG)) {
    const [, closing, rawName, attrs] = m;
    const name = rawName!.toLowerCase();
    if (!ALLOWED_ELEMENTS.has(name)) {
      problems.push(`<${closing}${rawName}> is not an allowed HTML element`);
      continue;
    }
    if (name === 'a' && !closing) {
      const names = [...attrs!.matchAll(ATTR)].map((a) => a[1]!.toLowerCase());
      const bad = names.filter((n) => !A_ATTRIBUTES.has(n));
      if (bad.length > 0 || names.length === 0) {
        problems.push(`<a> may carry only name or id, found: ${names.join(', ') || 'nothing'}`);
      }
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
