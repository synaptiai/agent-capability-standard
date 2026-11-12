// Tests on what the layer page's figures show (visual spec 3.2). Expected
// values come from line scans of the ontology edges, the CLAUDE.md layer
// table and the workflow catalogs (test/independent.ts), never from the
// functions under test.
import { describe, expect, it } from 'vitest';
import { loadOntology } from '../src/data/ontology';
import { layerLinks, stepsPerLayer } from '../src/lib/layer-figures';
import { allCatalogSteps, claudeLayerTable, ontologyEdgeTriples, symmetricEdgeTypes } from './independent';

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
