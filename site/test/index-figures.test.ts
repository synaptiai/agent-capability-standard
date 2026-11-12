// The figures of the index pages (visual spec 3.11). Expected values come
// from hand-written fixtures, and for one real document from a hand count of
// its citations (docs/compliance/iso42001/management_review.md cites
// Clause 9.3 five times, 9.2, 9.1 and 9 once each, and Clause 10 once).
import { describe, expect, it } from 'vitest';
import {
  backgroundLayerMatrix,
  euArticleMatrix,
  EU_MAX_COLUMNS,
  isoClauseMatrix,
  rfcLanes,
  type Doc,
} from '../src/lib/index-figures';
import type { RfcRow } from '../src/lib/rfcs';
import { repoText } from './independent';

const rfc = (label: string, status: string, target: string | null, numbered = true): RfcRow => ({
  url: `/rfcs/${label}/`,
  label,
  title: label,
  status,
  target,
  targetUrl: null,
  date: null,
  numbered,
});

describe('F-R1 RFCs by target version', () => {
  it('orders lanes by version number, not by text, and puts no target last', () => {
    const lanes = rfcLanes([
      rfc('RFC-0003', 'Draft', 'Standard v1.10.0'),
      rfc('OASF safety extensions', 'Draft Proposal', null, false),
      rfc('RFC-0001', 'Accepted', 'Standard v1.9.0'),
      rfc('RFC-0002', 'Accepted', 'Standard v1.9.0'),
    ]);
    expect(lanes.map((l) => l.target)).toEqual(['Standard v1.9.0', 'Standard v1.10.0', null]);
    expect(lanes[0]!.rfcs.map((r) => r.tile)).toEqual(['0001', '0002']);
    // An unnumbered row's tile is the first word of its title (visual spec 3.11).
    expect(lanes[2]!.rfcs[0]!.tile).toBe('OASF');
  });
});

describe('compliance citation matrices', () => {
  it('counts sub-clauses under their clause', () => {
    const m = isoClauseMatrix([
      { label: 'A', url: '/a/', text: 'See Clause 6.1 and Clause 6, then Clause 10.2.' },
      { label: 'B', url: '/b/', text: 'Clause 4.2 only.' },
    ]);
    expect(m.columns.map((c) => c.key)).toEqual(['4', '6', '10']);
    expect(m.rows.map((r) => r.counts)).toEqual([
      [0, 2, 1],
      [1, 0, 0],
    ]);
  });

  it('agrees with a hand count of the management review', () => {
    const doc: Doc = { label: 'Management review', url: '/x/', text: repoText('docs/compliance/iso42001/management_review.md') };
    const m = isoClauseMatrix([doc]);
    const at = (clause: string) => m.rows[0]!.counts[m.columns.findIndex((c) => c.key === clause)];
    expect(at('9')).toBe(8);
    expect(at('10')).toBe(1);
  });

  it('raises the shared-article threshold until the columns fit', () => {
    // Articles 1 to 12 are each cited by two documents; article 99 by three.
    const docs: Doc[] = [
      { label: 'A', url: '/a/', text: `${Array.from({ length: 12 }, (_, i) => `Art. ${i + 1}`).join(' ')} Art. 99` },
      { label: 'B', url: '/b/', text: `${Array.from({ length: 12 }, (_, i) => `Article ${i + 1}`).join(' ')} Art. 99 Art. 99` },
      { label: 'C', url: '/c/', text: 'Art. 99 and Art. 50' },
    ];
    expect(12).toBeGreaterThan(EU_MAX_COLUMNS);
    const m = euArticleMatrix(docs);
    expect(m.title).toBe('EU AI Act articles cited by 3 or more documents');
    expect(m.columns.map((c) => c.key)).toEqual(['99']);
    expect(m.rows.map((r) => r.counts)).toEqual([[1], [2], [1]]);
  });

  it('keeps every article two documents share when they fit', () => {
    const m = euArticleMatrix([
      { label: 'A', url: '/a/', text: 'Art. 17, Art. 9' },
      { label: 'B', url: '/b/', text: 'Article 17' },
    ]);
    expect(m.title).toBe('EU AI Act articles cited by 2 or more documents');
    expect(m.columns.map((c) => c.key)).toEqual(['17']);
  });
});

describe('background layer matrix', () => {
  it('counts only capability ids in code spans', () => {
    const layers = [
      { id: 'REASON', capabilities: ['plan'] },
      { id: 'EXECUTE', capabilities: ['mutate'] },
    ];
    const m = backgroundLayerMatrix([{ label: 'P', url: '/p/', text: 'We `plan`, then plan again, then `mutate` and `mutate`.' }], layers);
    expect(m.rows[0]!.counts).toEqual([1, 2]);
  });
});
