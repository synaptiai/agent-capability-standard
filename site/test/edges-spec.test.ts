// The edge types page and the Standard's figures (visual spec 3.7 and 3.9).
// Expected values come from plain text scans of the sources (the Standard,
// spec/EDGE_TYPES.md, the ontology, the catalog schema) through
// test/independent.ts or local line scans, never from the code under test.
import { describe, expect, it } from 'vitest';
import { renderRepoFile } from './pipeline';
import { ontologyEdgeTriples, repoText, symmetricEdgeTypes } from './independent';

const STANDARDS = ['spec/STANDARD-v1.1.0.md', 'spec/STANDARD-v1.0.0.md'];

describe('chapter glyphs (spec 3.9)', () => {
  it.each(STANDARDS)('puts one glyph on each numbered H2 of %s and none on an appendix', async (p) => {
    const want = [...repoText(p).matchAll(/^## (\d+)\. /gm)].length;
    const html = (await renderRepoFile(p)).code;
    const h2s = [...html.matchAll(/<h2\b[^>]*>([\s\S]*?)<\/h2>/g)].map((m) => m[1]!);
    expect(want).toBeGreaterThan(0);
    expect(h2s.filter((h) => h.includes('chapter-glyph'))).toHaveLength(want);
    for (const h of h2s.filter((x) => /Appendix/.test(x))) expect(h).not.toContain('chapter-glyph');
    for (const h of h2s.filter((x) => x.includes('chapter-glyph'))) expect(h).toMatch(/<svg[^>]*aria-hidden="true"/);
  });
});

describe('edge type summary table (F-E4)', () => {
  it('adds a mark and a count for each edge type, counting symmetric types by pair', async () => {
    const html = (await renderRepoFile('spec/EDGE_TYPES.md')).code;
    const triples = ontologyEdgeTriples();
    const types = [...new Set(triples.map((t) => t.type))];
    expect(types.length).toBeGreaterThan(0);
    for (const type of types) {
      const row = new RegExp(`<tr data-edge-type="${type}"[^>]*>([\\s\\S]*?)</tr>`).exec(html)?.[1];
      expect(row, type).toBeDefined();
      expect(row).toContain(`data-glyph="mark:${type}"`);
      const ofType = triples.filter((t) => t.type === type);
      const pairs = new Set(ofType.map((t) => [t.from, t.to].sort().join('|'))).size;
      const symmetric = symmetricEdgeTypes().includes(type);
      const n = symmetric ? pairs : ofType.length;
      expect(row).toMatch(new RegExp(`data-value="${n}"`));
    }
  });
});
