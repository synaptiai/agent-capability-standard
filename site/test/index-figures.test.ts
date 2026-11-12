// The figures of the index pages (visual spec 3.11). Expected values come
// from hand-written fixtures, and for one real document from a hand count of
// its citations (docs/compliance/iso42001/management_review.md cites
// Clause 9.3 five times, 9.2, 9.1 and 9 once each, and Clause 10 once).
import { describe, expect, it } from 'vitest';
import {
  backgroundLayerMatrix,
  conformanceSuite,
  pageSize,
  readingBars,
  suiteCoverage,
  euArticleMatrix,
  EU_MAX_COLUMNS,
  isoClauseMatrix,
  rfcLanes,
  type Doc,
} from '../src/lib/index-figures';
import type { RfcRow } from '../src/lib/rfcs';
import { readdirSync } from 'node:fs';
import path from 'node:path';
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

describe('/start/ reading times', () => {
  it('counts words outside fences, and code blocks that are not diagrams', () => {
    // Hand count: "One two three." and "Four five" are 5 words; the bash and the json fences are code
    // blocks; the mermaid fence and the box drawing are diagrams, not code; frontmatter is not text.
    const text = [
      '---',
      'title: x',
      '---',
      'One two three.',
      '```bash',
      'npm ci',
      '```',
      '```mermaid',
      'flowchart LR',
      '  a --> b',
      '```',
      '```',
      '┌─┐',
      '└─┘',
      '```',
      'Four five',
      '```json',
      '{}',
      '```',
    ].join('\n');
    expect(pageSize(text)).toEqual({ words: 5, codeBlocks: 2 });
  });

  it('rounds to whole minutes at 200 words a minute, with at least one', () => {
    const words = (n: number) => Array.from({ length: n }, () => 'word').join(' ');
    const b = readingBars([
      { label: 'Short', url: '/a/', text: words(20) },
      { label: 'Long', url: '/b/', text: `${words(700)}\n\n\`\`\`sh\nx\n\`\`\`` },
    ]);
    expect(b.rows.map((r) => [r.value, r.words])).toEqual([
      [1, '1 min, 0 code blocks'],
      [4, '4 min, 1 code block'],
    ]);
    expect(b.caption).toContain('take about 5 minutes in all');
  });
});

describe('/spec/ conformance coverage', () => {
  it('shares each family by its own size, and names the full and the smallest families', () => {
    const parts = [
      { label: 'A fixtures', count: 3, unit: 'fixtures', codes: new Set(['V101', 'B201']) },
      { label: 'B cases', count: 2, unit: 'cases', codes: new Set(['B202', 'V101']) },
    ];
    const fams = [
      { name: 'Validation', range: 'V1xx', codes: ['V101', 'V102', 'V103', 'V104'] },
      { name: 'Binding', range: 'B2xx', codes: ['B201', 'B202'] },
    ];
    const b = suiteCoverage(parts, fams);
    expect(b.rows).toEqual([
      { label: 'V1xx Validation', value: 1, max: 4, words: '1 of 4 codes' },
      { label: 'B2xx Binding', value: 2, max: 2, words: '2 of 2 codes' },
    ]);
    expect(b.caption).toBe(
      "The suite's 5 fixtures and cases (3 a fixtures and 2 b cases) expect 3 of the 6 diagnostic codes. Every Binding code is expected; Validation has the smallest share, 1 of 4.",
    );
  });

  it('reads the suite as spec/CONFORMANCE.md names it, by text scans of the fixture files', () => {
    const exp = repoText('tests/fixtures/EXPECTATIONS.json');
    const pass = (exp.match(/"should_pass":\s*true/g) ?? []).length;
    const fail = (exp.match(/"should_pass":\s*false/g) ?? []).length;
    const listed = (re: RegExp, text: string) => new Set([...text.matchAll(re)].flatMap((m) => m[1]!.match(/[A-Z]\d{3}/g) ?? []));
    const evalText = repoText('tests/conformance/expressions/eval.json');
    const checkText = repoText('tests/conformance/expressions/check.json');
    const dir = (d: string) => readdirSync(path.join('..', d)).filter((f) => f.endsWith('.json'));
    const ends = (d: string) =>
      new Set(
        dir(d).flatMap((f) => {
          const t = repoText(`${d}/${f}`);
          const end = t.slice(t.indexOf('"end":'), t.includes('"trace_kinds"') && t.indexOf('"trace_kinds"') > t.indexOf('"end":') ? t.indexOf('"trace_kinds"') : undefined);
          return [...end.matchAll(/"(?:code|cause)":\s*"([A-Z]\d{3})"/g)].map((m) => m[1]!);
        }),
      );
    const got = conformanceSuite();
    expect(got.map((p) => p.count)).toEqual([
      pass,
      fail,
      (evalText.match(/"id":/g) ?? []).length,
      (checkText.match(/"id":/g) ?? []).length,
      dir('tests/conformance/runtime').length,
      dir('tests/conformance/contrib').length,
    ]);
    expect(pass + fail).toBeGreaterThan(80);
    // All validator codes together (pass and fail fixtures), and each other part's codes.
    expect(new Set([...got[0]!.codes, ...got[1]!.codes])).toEqual(listed(/"expected_(?:error|warning)_codes":\s*\[([^\]]*)\]/g, exp));
    expect(got[2]!.codes).toEqual(listed(/"error":\s*"([A-Z]\d{3})"/g, evalText));
    expect(got[3]!.codes).toEqual(listed(/"expect":\s*\[([^\]]*)\]/g, checkText));
    expect(got[4]!.codes).toEqual(ends('tests/conformance/runtime'));
    expect(got[5]!.codes).toEqual(ends('tests/conformance/contrib'));
  });
});
