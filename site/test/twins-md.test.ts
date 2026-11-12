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

describe('Standard Markdown copies', () => {
  // Visual spec 6.1: every figure's information is also in the page's
  // Markdown copy. Each Standard page draws one figure per slot of its
  // version, so its copy has one "**Figure: ...**" block per slot.
  it('has one figure block per figure the page draws, for every Standard with figures', async () => {
    const { SLOTS_BY_VERSION } = await import('../src/lib/spec-slots');
    const { specFigureBlocks } = await import('../src/twins/edges-spec');
    const { specOlderBlocks } = await import('../src/twins/spec-figures');
    const count = (blocks: string[]) => blocks.filter((b) => b.startsWith('**Figure: ')).length;
    expect(count(specFigureBlocks())).toBe(SLOTS_BY_VERSION['1.1.0']!.length);
    expect(count(specOlderBlocks('spec/STANDARD-v1.0.0.md', SLOTS_BY_VERSION['1.0.0']!))).toBe(SLOTS_BY_VERSION['1.0.0']!.length);
  });

  it("states the 1.0.0 world-state field count and the decision tree's outcomes", async () => {
    const { SLOTS_BY_VERSION } = await import('../src/lib/spec-slots');
    const { specOlderBlocks } = await import('../src/twins/spec-figures');
    const { readRepoFile } = await import('../src/lib/repo');
    const md = specOlderBlocks('spec/STANDARD-v1.0.0.md', SLOTS_BY_VERSION['1.0.0']!).join('\n\n');
    // Counted here by a plain scan of §6.3's table rows: lines starting "| `".
    const src = readRepoFile('spec/STANDARD-v1.0.0.md');
    const sec = src.slice(src.indexOf('### 6.3 '), src.indexOf('\n### ', src.indexOf('### 6.3 ') + 1));
    const fields = sec.split('\n').filter((l) => /^\| `/.test(l)).length;
    expect(fields).toBeGreaterThan(0);
    expect(md).toContain(`${fields} fields`);
    // The §12.1 tree's leaf lines contain "REQUIRED" or "NOT REQUIRED"; both appear in the copy.
    expect(md).toMatch(/Checkpoint decision tree[^\n]*\n[\s\S]*REQUIRED/);
  });
});
