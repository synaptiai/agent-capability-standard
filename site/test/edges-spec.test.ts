// The edge types page and the Standard's figures (visual spec 3.7 and 3.9).
// Expected values come from plain text scans of the sources (the Standard,
// spec/EDGE_TYPES.md, the ontology, the catalog schema) through
// test/independent.ts or local line scans, never from the code under test.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { renderRepoFile } from './pipeline';
import { claudeLayerTable, ontologyEdgeTriples, repoText, symmetricEdgeTypes } from './independent';
import { parseTokens, pairRatio } from '../scripts/check-contrast.mjs';
import { edgeChanges, exampleChains, heatRanges, heatStep, layerPairCounts, matrixCells, parseChains } from '../src/lib/edge-figures';
import { cutAfterHeadings } from '../src/lib/inject';
import { loadCatalogSchema } from '../src/data/catalog-schema';
import { annotationGrammar, bindingExamples, failureBranches, gateBranches, referenceParts, stepAnatomy, stepFieldRows } from '../src/lib/spec-figures';

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

describe('all edges matrix (F-E2)', () => {
  const triples = ontologyEdgeTriples();

  it('has one cell per (from, to) pair with every type of that pair, as a scan of the ontology edges gives', () => {
    const want = new Map<string, Set<string>>();
    for (const t of triples) want.set(`${t.from}>${t.to}`, (want.get(`${t.from}>${t.to}`) ?? new Set()).add(t.type));
    const got = new Map(matrixCells().map((c) => [`${c.from}>${c.to}`, new Set(c.types)]));
    expect(got).toEqual(want);
    // Spec 3.7 names two of the split cells.
    expect([...got.get('rollback>mutate')!].sort()).toEqual(['conflicts_with', 'specializes']);
    expect([...got.get('measure>predict')!].sort()).toEqual(['alternative_to', 'enables']);
  });

  it('counts edges between layer pairs by the layers CLAUDE.md lists, a symmetric pair once', () => {
    const layerOf = new Map(claudeLayerTable().flatMap((r) => r.capabilities.map((c) => [c, r.id] as const)));
    const sym = symmetricEdgeTypes();
    const seen = new Set<string>();
    const want = new Map<string, number>();
    for (const t of triples) {
      if (sym.includes(t.type)) {
        const k = `${t.type}|${[t.from, t.to].sort().join('|')}`;
        if (seen.has(k)) continue;
        seen.add(k);
      }
      const k = `${layerOf.get(t.from)}>${layerOf.get(t.to)}`;
      want.set(k, (want.get(k) ?? 0) + 1);
    }
    const { layers, counts } = layerPairCounts();
    const got = new Map<string, number>();
    layers.forEach((a, i) => layers.forEach((b, j) => counts[i]![j]! > 0 && got.set(`${a}>${b}`, counts[i]![j]!)));
    expect(got).toEqual(want);
  });

  it('puts counts on four heat steps that cover 1 to the maximum without gaps (fixture: max 11)', () => {
    expect([0, 1, 2, 3, 5, 6, 8, 9, 11].map((c) => heatStep(c, 11))).toEqual([0, 1, 1, 2, 2, 3, 3, 4, 4]);
    expect(heatRanges(11)).toEqual([
      { step: 1, from: 1, to: 2 },
      { step: 2, from: 3, to: 5 },
      { step: 3, from: 6, to: 8 },
      { step: 4, from: 9, to: 11 },
    ]);
  });

  it('uses the heat values of visual spec 1.2, whose light first step is 2.24:1 against the page', () => {
    const { light } = parseTokens(readFileSync('src/styles/tokens.css', 'utf8'));
    expect(Number(pairRatio({ kind: 'edge', label: '', fg: 'var(--heat-1)', bg: 'var(--bg)' }, light).toFixed(2))).toBe(2.24);
  });
});

describe('example chains (F-E3)', () => {
  it('reads the three fences of EDGE_TYPES.md as their lines say', () => {
    const pairs = (h: string) => exampleChains(h).map((c) => c.edges.map((e) => `${e.from} ${e.type} ${e.to}`));
    expect(pairs('Safety-Critical Precedes Chain')).toEqual([
      ['constrain precedes mutate'],
      ['checkpoint precedes mutate', 'mutate precedes verify', 'verify precedes audit'],
    ]);
    // The tree's child specializes its parent (the ontology's direction).
    expect(pairs('Specialization Hierarchy')).toEqual([['detect specializes observe', 'classify specializes detect']]);
    expect(exampleChains('Specialization Hierarchy')[0]!.form).toBe('tree');
    expect(pairs('Conflict Resolution').flat()).toHaveLength(2);
  });

  it('fails on a pair that is not an edge of the ontology (fixture)', () => {
    expect(() => parseChains('observe --precedes--> audit')).toThrow(/observe --precedes--> audit is not an edge/);
    expect(() => parseChains('observe\n  |\n  +--specializes-- audit')).toThrow(/is not an edge/);
  });
});

describe('1.1.0 edge changes (F-E5)', () => {
  it('has one row per target named in the table, by a line scan', () => {
    const lines = repoText('spec/EDGE_TYPES.md').split('\n');
    const start = lines.findIndex((l) => l.startsWith("## Changes to the ontology's edges in 1.1.0"));
    const rows = lines.slice(start).filter((l) => /^\| [a-z_]+ → /.test(l));
    const targets = rows.flatMap((r) => r.split('|')[1]!.split('→')[1]!.split(',').map((x) => x.trim()));
    expect(targets.length).toBeGreaterThan(0);
    expect(edgeChanges().map((c) => c.to)).toEqual(targets);
  });
});

describe('figure anchors', () => {
  const html = '<h2 id="a">A one</h2><p>x</p><h3 id="b">B <code>two</code><a class="heading-anchor"></a></h3><p>y</p>';
  it('cuts after the matching heading', () => {
    const s = cutAfterHeadings(html, [{ key: 'k', level: 3, startsWith: 'B two' }], 'fixture');
    expect(s.map((x) => x.key)).toEqual(['k', null]);
    expect(s[0]!.html.endsWith('</h3>')).toBe(true);
  });
  it('fails when an anchor matches no heading', () => {
    expect(() => cutAfterHeadings(html, [{ key: 'k', level: 2, startsWith: 'Nope' }], 'fixture')).toThrow(/matches 0 headings/);
  });
});

describe('Standard figures from the catalog schema (F-S5, F-S9, F-S10)', () => {
  const schema = JSON.parse(repoText('schemas/workflow_catalog.schema.json'));
  const std = 'spec/STANDARD-v1.1.0.md';
  const text = repoText(std);

  it('groups every step property of the schema exactly once, required ones as the schema lists them', () => {
    const props = Object.keys(schema.$defs.step.properties);
    const groups = stepAnatomy();
    const names = groups.flatMap((g) => g.slots.map((s) => s.name));
    expect([...names].sort()).toEqual([...props].sort());
    expect(groups.flatMap((g) => g.slots).filter((s) => s.required).map((s) => s.name).sort()).toEqual([...schema.$defs.step.required].sort());
  });

  it('links a field to the §5.2 table row that names it', () => {
    // The row "| `risk`, `mutation`, `requires_checkpoint`, `requires_approval` | ..." of §5.2.
    const rows = stepFieldRows(text, std);
    expect(rows.get('requires_approval')).toBe('risk');
    expect(rows.get('capability')).toBe('capability');
    expect(rows.has('delay')).toBe(false);
  });

  it('branches on every gate action before the step, and after it on all but what the schema forbids', () => {
    const actions = schema.$defs.gate.properties.action.enum as string[];
    const forbidden = schema.$defs.gate.then.properties.action.not.const as string;
    expect(gateBranches()).toEqual([
      { phase: 'before', actions },
      { phase: 'after', actions: actions.filter((a) => a !== forbidden) },
    ]);
    expect(loadCatalogSchema().failureActions).toEqual(schema.$defs.failure_mode.properties.action.enum);
  });

  it('gives each failure action the effect of its §5.12 table row, by a line scan', () => {
    const lines = text.split('\n');
    const start = lines.findIndex((l) => /^\| `action` \| Effect before recovery \|$/.test(l));
    const effect = new Map<string, string>();
    for (const l of lines.slice(start + 2)) {
      if (!l.startsWith('|')) break;
      const [, names, eff] = l.split('|').map((c) => c.trim());
      for (const m of names!.matchAll(/`([a-z_]+)`/g)) effect.set(m[1]!, eff!.replace(/`/g, ''));
    }
    expect(effect.size).toBeGreaterThan(0);
    for (const b of failureBranches(text, std)) expect(b.effect).toBe(effect.get(b.action));
  });
});

describe('Standard figures from §5.3 (F-S7, F-S8)', () => {
  const std = 'spec/STANDARD-v1.1.0.md';
  const text = repoText(std);

  it('splits references into root, segments and annotation (fixtures)', () => {
    expect(referenceParts('${search_out.results[0:5]}')).toEqual({
      root: 'search_out',
      segments: [
        { kind: 'field', text: '.results' },
        { kind: 'slice', text: '[0:5]' },
      ],
      annotation: null,
    });
    expect(referenceParts('${a.b[2].c : map<string, number>}')).toEqual({
      root: 'a',
      segments: [
        { kind: 'field', text: '.b' },
        { kind: 'index', text: '[2]' },
        { kind: 'field', text: '.c' },
      ],
      annotation: 'map<string, number>',
    });
    expect(() => referenceParts('${a[01]}')).toThrow();
  });

  it('reads every line of the Examples fence', () => {
    const fence = /Examples:\n```yaml\n([\s\S]*?)```/.exec(text)![1]!.trim().split('\n');
    expect(bindingExamples(text, std).map((e) => e.line)).toEqual(fence.map((l) => l.trim()));
  });

  it('reads the annotation grammar names as the sentence lists them', () => {
    const sentence = /\*\*Annotation grammar:\*\*([\s\S]*?)\. `integer` is a subtype/.exec(text)![1]!;
    const want = [...sentence.matchAll(/`([^`]+)`/g)].map((m) => m[1]!);
    const g = annotationGrammar(text, std);
    expect(g.names).toEqual(want);
    expect(g.subtype).toEqual({ sub: 'integer', of: 'number' });
  });
});
