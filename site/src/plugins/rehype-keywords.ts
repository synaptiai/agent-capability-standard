// Marks the requirement keywords on normative pages: each whole-word, uppercase
// keyword from the Standard's Notation section (§1.2) becomes
// <span class="kw kw--must|should|may">. The longest match wins, so "MUST NOT"
// is one span. Text inside code, pre and headings is left alone, and the
// sources and Markdown copies are not changed.
import type { Element, ElementContent, Root, Text } from 'hast';
import { visitParents } from 'unist-util-visit-parents';
import type { VFile } from 'vfile';
import { sourceOf } from './source';

/** STANDARD-v1.1.0.md §1.2 Notation, and the style each keyword gets. */
export const KEYWORDS: Readonly<Record<string, 'must' | 'should' | 'may'>> = {
  'MUST NOT': 'must',
  'SHALL NOT': 'must',
  'SHOULD NOT': 'should',
  MUST: 'must',
  SHALL: 'must',
  SHOULD: 'should',
  MAY: 'may',
};

const PATTERN = new RegExp(
  `(?<![\\w-])(${Object.keys(KEYWORDS)
    .sort((a, b) => b.length - a.length)
    .map((k) => k.replace(' ', '\\s+'))
    .join('|')})(?![\\w-])`,
  'g',
);

const SKIP = new Set(['code', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'script', 'style']);

export interface RehypeKeywordsOptions {
  /** Repo paths of the pages that get keyword marking. */
  sources: ReadonlySet<string>;
}

/** Split one text value into text and keyword spans; null if nothing matched. */
export function markKeywords(value: string): ElementContent[] | null {
  const out: ElementContent[] = [];
  let last = 0;
  for (const m of value.matchAll(PATTERN)) {
    const word = m[1]!;
    const level = KEYWORDS[word.replace(/\s+/g, ' ')]!;
    if (m.index > last) out.push({ type: 'text', value: value.slice(last, m.index) });
    out.push({
      type: 'element',
      tagName: 'span',
      properties: { className: ['kw', `kw--${level}`] },
      children: [{ type: 'text', value: word }],
    });
    last = m.index + word.length;
  }
  if (last === 0) return null;
  if (last < value.length) out.push({ type: 'text', value: value.slice(last) });
  return out;
}

export default function rehypeKeywords(options: RehypeKeywordsOptions) {
  return (tree: Root, file: VFile): void => {
    const { repoPath } = sourceOf(file, 'rehype-keywords');
    if (!options.sources.has(repoPath)) return;
    const edits: { parent: Element | Root; node: Text; replacement: ElementContent[] }[] = [];
    visitParents(tree, 'text', (node: Text, ancestors) => {
      if (ancestors.some((a) => a.type === 'element' && SKIP.has(a.tagName))) return;
      const replacement = markKeywords(node.value);
      if (replacement) edits.push({ parent: ancestors.at(-1) as Element | Root, node, replacement });
    });
    for (const { parent, node, replacement } of edits) {
      const i = parent.children.indexOf(node);
      parent.children.splice(i, 1, ...replacement);
    }
  };
}
