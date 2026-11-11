// The Markdown helpers the page copies are written with. Expected values come
// from the CommonMark spec (code spans, section 6.1): a span closes on a
// backtick run of the same length as the one that opens it, and one leading
// and one trailing space are stripped when both are present.
import { describe, expect, it } from 'vitest';
import type { InlineCode, Paragraph } from 'mdast';
import { parseMarkdown } from '../src/lib/anchors';
import { code } from '../src/twins/md';

/** The code span(s) a Markdown parser reads from `md`. */
function spans(md: string): string[] {
  const p = parseMarkdown(md).children[0] as Paragraph;
  return p.children.filter((c): c is InlineCode => c.type === 'inlineCode').map((c) => c.value);
}

describe('code()', () => {
  it('writes a span that reads back as exactly the text', () => {
    for (const text of ['plain', 'a `b` c', 'a ``b', '```', '`start', 'end`', 'x `` y ``` z', ' lead', 'trail ', '${step.ok} == false']) {
      const md = code(text);
      expect(spans(md), `${JSON.stringify(text)} -> ${md}`).toEqual([text]);
    }
  });
});
