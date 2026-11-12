// Tests on what the layer page's figures show (visual spec 3.2). Expected
// values come from line scans of the ontology edges, the CLAUDE.md layer
// table and the workflow catalogs (test/independent.ts), never from the
// functions under test.
import { describe, expect, it } from 'vitest';
import { loadOntology } from '../src/data/ontology';
import { layerLinks, riskByLayer, riskByLayerCaption, stepsPerLayer, usageMatrix } from '../src/lib/layer-figures';
import { allCatalogSteps, claudeLayerTable, ontologyEdgeTriples, repoText, symmetricEdgeTypes } from './independent';

const layerOf = new Map(claudeLayerTable().flatMap((r) => r.capabilities.map((c) => [c, r.id] as const)));

describe('layerLinks (F-L2)', () => {
  // Cross-layer edges by a scan; a symmetric pair counts once, on the side its first line declares.
  const sym = new Set(symmetricEdgeTypes());
  const seen = new Set<string>();
  const cross = ontologyEdgeTriples().filter((t) => {
    if (layerOf.get(t.from) === layerOf.get(t.to)) return false;
    if (!sym.has(t.type)) return true;
    const pair = `${t.type} ${[t.from, t.to].sort().join(' ')}`;
    if (seen.has(pair)) return false;
    seen.add(pair);
    return true;
  });

  it.each(claudeLayerTable().map((r) => r.id))('%s: edge counts and types to each other layer, by direction', (layer) => {
    const got = layerLinks(layer);
    const want = (dir: 'into' | 'out') => {
      const m = new Map<string, { n: number; types: Set<string> }>();
      for (const t of cross) {
        const here = dir === 'into' ? layerOf.get(t.to) : layerOf.get(t.from);
        const there = dir === 'into' ? layerOf.get(t.from) : layerOf.get(t.to);
        if (here !== layer) continue;
        const e = m.get(there!) ?? { n: 0, types: new Set() };
        e.n++;
        e.types.add(t.type);
        m.set(there!, e);
      }
      return Object.fromEntries([...m].map(([k, v]) => [k, `${v.n} ${[...v.types].sort().join(',')}`]));
    };
    const shown = (ls: ReturnType<typeof layerLinks>['into']) => Object.fromEntries(ls.map((l) => [l.layer, `${l.edges.length} ${[...l.types].sort().join(',')}`]));
    expect(shown(got.into)).toEqual(want('into'));
    expect(shown(got.out)).toEqual(want('out'));
  });
});

describe('stepsPerLayer (F-L4)', () => {
  it('counts every catalog step by its capability layer, highest first', () => {
    const want = new Map<string, number>();
    for (const caps of allCatalogSteps().values()) for (const c of caps) want.set(layerOf.get(c)!, (want.get(layerOf.get(c)!) ?? 0) + 1);
    const got = stepsPerLayer();
    expect(got).toHaveLength(loadOntology().layers.length);
    expect(Object.fromEntries(got.filter((r) => r.steps > 0).map((r) => [r.layer, r.steps]))).toEqual(Object.fromEntries(want));
    for (let i = 1; i < got.length; i++) expect(got[i - 1]!.steps).toBeGreaterThanOrEqual(got[i]!.steps);
  });
});

describe('usageMatrix (F-L3)', () => {
  const steps = allCatalogSteps();

  it.each(claudeLayerTable().map((r) => r.id))('%s: one row per workflow that runs a capability of the layer, with its step count per capability', (layer) => {
    const caps = claudeLayerTable().find((r) => r.id === layer)!.capabilities;
    const want = [...steps.entries()]
      .map(([wf, list]) => [wf, caps.map((c) => list.filter((x) => x === c).length)] as const)
      .filter(([, counts]) => counts.some((n) => n > 0));
    const got = usageMatrix(layer);
    expect(got.capabilities).toEqual(caps);
    expect(got.rows.map((r) => [r.workflow.id, r.counts])).toEqual(want.map(([wf, c]) => [wf, c]));
    expect(got.max).toBe(Math.max(0, ...want.flatMap(([, c]) => c)));
  });
});

describe('riskByLayer (F-CI1)', () => {
  /** Risk of each capability by a scan of the ontology's nodes block. */
  const risks = (() => {
    const out = new Map<string, string>();
    let id: string | null = null;
    for (const l of repoText('schemas/capability_ontology.yaml').split('\n')) {
      const m = /^- id: (\S+)/.exec(l);
      if (m) id = m[1]!;
      const r = /^ {2}risk: (\w+)/.exec(l);
      if (r && id) out.set(id, r[1]!);
    }
    return out;
  })();

  it('counts each layer\'s capabilities at each risk, as the nodes block gives them', () => {
    const m = riskByLayer();
    expect(m.layers).toEqual(claudeLayerTable().map((r) => r.id));
    for (const row of m.rows) {
      expect(row.counts).toEqual(claudeLayerTable().map((l) => l.capabilities.filter((c) => risks.get(c) === row.risk).length));
    }
    expect(m.rows.flatMap((r) => r.counts).reduce((a, b) => a + b, 0)).toBe(risks.size);
  });

  it('names where the high- and medium-risk capabilities sit', () => {
    // Hand-read from the ontology on 2026-11-12: mutate and send are high risk (EXECUTE);
    // execute (EXECUTE), rollback (VERIFY), delegate, synchronize and invoke (COORDINATE) are medium.
    expect(riskByLayerCaption(riskByLayer())).toBe(
      '29 of the 36 capabilities are low risk; there are 2 high-risk capabilities (2 in EXECUTE) and 5 medium-risk capabilities (1 in EXECUTE, 1 in VERIFY and 3 in COORDINATE).',
    );
  });
});
