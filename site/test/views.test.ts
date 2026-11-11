// Tests for what the generated pages show. Expected values on live data come
// from line scans of the YAML in test/independent.ts, the CLAUDE.md layer
// table and tools/validate_canonical_schemas.py, not from the loaders. Tests
// on fixtures state where each expected value comes from.
import { describe, expect, it } from 'vitest';
import { EDGE_TYPES, loadOntology } from '../src/data/ontology';
import { capabilityUsage, parseCatalog } from '../src/data/workflows';
import { inlineMarkdown, refSlugger } from '../src/lib/generated';
import { readRepoFile } from '../src/lib/repo';
import {
  crossLayerEdges,
  edgeGroups,
  governanceStatuses,
  layerUsage,
  producerSteps,
  schemaListing,
  schemaRows,
  sortedTrustWeights,
  standardSchemaNames,
  stepMarkers,
} from '../src/lib/views';
import {
  allCatalogSteps,
  canonicalSchemaNames,
  claudeLayerTable,
  ontologyEdgeTriples,
  repoText,
  standardFileVersions,
  symmetricEdgeTypes,
} from './independent';

const triples = ontologyEdgeTriples();
const symmetric = symmetricEdgeTypes();
const layerOf = new Map(claudeLayerTable().flatMap((l) => l.capabilities.map((c) => [c, l.id] as const)));
const catalogs = allCatalogSteps();

describe('edge grouping on capability pages', () => {
  it('reads the edges and symmetric types by line scan', () => {
    // Guards the scan itself: CLAUDE.md says checkpoint requires-edges run to mutate, send and rollback,
    // and spec/EDGE_TYPES.md describes conflicts_with and alternative_to as symmetric.
    expect(triples.filter((t) => t.type === 'requires').map((t) => `${t.from}>${t.to}`).sort()).toEqual([
      'checkpoint>mutate',
      'checkpoint>rollback',
      'checkpoint>send',
    ]);
    expect(symmetric.sort()).toEqual(['alternative_to', 'conflicts_with']);
  });

  it('groups every capability\'s edges by type, outgoing and incoming, as the YAML lists them', () => {
    const ontology = loadOntology();
    for (const cap of ontology.capabilities) {
      const want = EDGE_TYPES.flatMap((type) => {
        const outgoing = triples.filter((t) => t.type === type && t.from === cap.id).map((t) => t.to);
        const incoming = triples.filter((t) => t.type === type && t.to === cap.id).map((t) => t.from);
        if (outgoing.length === 0 && incoming.length === 0) return [];
        const sym = symmetric.includes(type);
        return [{ type, symmetric: sym, related: sym ? [...new Set([...outgoing, ...incoming])] : [], outgoing, incoming }];
      });
      expect(edgeGroups(cap, ontology), cap.id).toEqual(want);
    }
  });

  it('lists a symmetric edge once whichever end declares it', () => {
    const ontology = loadOntology();
    const t = triples.find((x) => x.type === 'conflicts_with')!;
    for (const end of [t.from, t.to]) {
      const g = edgeGroups(ontology.byId.get(end)!, ontology).find((x) => x.type === 'conflicts_with')!;
      const other = end === t.from ? t.to : t.from;
      expect(g.related.filter((c) => c === other)).toEqual([other]);
    }
  });

  it('lists exactly the edges that cross each layer boundary', () => {
    for (const layer of claudeLayerTable()) {
      const want = EDGE_TYPES.map((type) => ({
        type,
        edges: triples
          .filter((t) => t.type === type && (layerOf.get(t.from) === layer.id) !== (layerOf.get(t.to) === layer.id))
          .map((t) => `${t.from}>${t.to}`),
      })).filter((g) => g.edges.length > 0);
      const got = crossLayerEdges(layer.id).map((g) => ({ type: g.type, edges: g.edges.map((e) => `${e.from}>${e.to}`) }));
      expect(got, layer.id).toEqual(want);
    }
  });
});

describe('workflow usage on capability and layer pages', () => {
  it('scans one workflow per catalog key, and the core catalog has debug_code_change', () => {
    expect(catalogs.get('debug_code_change')?.length).toBeGreaterThan(0);
  });

  it('lists, for every capability, each workflow using it with its 1-based step numbers', () => {
    for (const cap of loadOntology().capabilities) {
      const want = [...catalogs].flatMap(([wf, caps]) => {
        const steps = caps.flatMap((c, i) => (c === cap.id ? [i + 1] : []));
        return steps.length > 0 ? [{ workflowId: wf, steps }] : [];
      });
      expect(
        capabilityUsage(cap.id).map((u) => ({ workflowId: u.workflowId, steps: u.steps })),
        cap.id,
      ).toEqual(want);
    }
  });

  it('lists, for every layer, the workflows that use its capabilities', () => {
    for (const layer of claudeLayerTable()) {
      const want = [...catalogs].flatMap(([wf, caps]) => {
        const used = [...new Set(caps.filter((c) => layerOf.get(c) === layer.id))];
        return used.length > 0 ? [{ wf, used }] : [];
      });
      expect(layerUsage(layer.id).map((u) => ({ wf: u.workflow.id, used: u.capabilities })), layer.id).toEqual(want);
    }
  });
});

describe('contract tables', () => {
  // Hand-written schema: `required` as a parent list (the ontology's form) and
  // as a field boolean (workflow inputs), a nested object and a deeper one.
  const props = {
    a: { type: 'string', description: 'A field', enum: ['x', 'y'] },
    b: {
      type: 'object',
      required: ['inner'],
      properties: {
        inner: { type: 'number', minimum: 0, maximum: 1 },
        deep: { type: 'object', properties: { leaf: { type: 'string' } } },
      },
    },
    c: { type: 'array', items: { type: 'string' }, required: true, default: [] },
    d: { type: 'object', ref: 'schemas/world_state_schema.yaml#/world_state' },
  };
  const rows = schemaRows(props, ['a']);

  it('makes one row per top-level field and per field of a top-level object', () => {
    expect(rows.map((r) => [r.path, r.depth])).toEqual([
      ['a', 0],
      ['b', 0],
      ['b.inner', 1],
      ['b.deep', 1],
      ['c', 0],
      ['d', 0],
    ]);
  });

  it('reads required from the parent list and from a field boolean', () => {
    expect(rows.map((r) => [r.path, r.required])).toEqual([
      ['a', true],
      ['b', false],
      ['b.inner', true],
      ['b.deep', false],
      ['c', true],
      ['d', false],
    ]);
  });

  it('shows types, constraints, refs, and deeper schema as YAML', () => {
    const by = new Map(rows.map((r) => [r.path, r]));
    expect(by.get('a')!.constraints).toEqual(['One of: x, y']);
    expect(by.get('b.inner')!.constraints).toEqual(['From 0 to 1']);
    expect(by.get('c')!.type).toBe('array of string');
    expect(by.get('c')!.constraints).toEqual(['Default: []']);
    expect(by.get('d')!.ref).toBe('schemas/world_state_schema.yaml#/world_state');
    expect(by.get('b.deep')!.nested).toBe('properties:\n  leaf:\n    type: string');
    expect(by.get('b')!.nested).toBeUndefined();
  });
});

describe('workflow step markers', () => {
  // A hand-written catalog. Expected flags follow Standard 1.1.0 §5.2.1 and
  // the ontology's node values for each capability (CLAUDE.md "Safety Model":
  // mutate is mutation + approval; audit is mutation_overridable).
  const yaml = `
fixture_flow:
  goal: test
  risk: high
  steps:
    - capability: checkpoint
      store_as: cp
    - capability: mutate
      store_as: changed
      input_bindings:
        target: \${cp.id}
    - capability: verify
      store_as: checked
      gates:
        - when: \${changed.ok} == false
          action: stop
    - capability: rollback
      condition: \${checked.passed} == false
      input_bindings:
        checkpoint: \${cp.id}
    - capability: audit
      mutation: false
`;
  const wf = parseCatalog('fixture.yaml', yaml, 'core', loadOntology())[0]!;
  const kinds = wf.steps.map((s) => stepMarkers(s).map((m) => m.kind));

  it('marks checkpoint, state changes, verify and rollback', () => {
    expect(kinds).toEqual([
      ['checkpoint', 'mutate'], // checkpoint has mutation: true (CLAUDE.md "Other mutation capabilities")
      ['mutate', 'approval'],
      ['verify', 'gate'],
      ['mutate', 'rollback', 'condition'],
      [], // audit with mutation: false is honoured (mutation_overridable)
    ]);
  });

  it('finds the step that produced each output a step reads', () => {
    expect(producerSteps(wf, wf.steps[3]!)).toEqual([
      { name: 'cp', index: 1 },
      { name: 'checked', index: 3 },
    ]);
  });
});

describe('schemas listing', () => {
  const spec = repoText(`spec/STANDARD-v${standardFileVersions()[0]}.md`);

  it('takes the required schemas from §6.1, as the canonical schema validator lists them', () => {
    expect(standardSchemaNames(spec).required.sort()).toEqual(canonicalSchemaNames().sort());
  });

  it('reads the supporting schemas from the sentence after the table', () => {
    const text = '### 6.1 Required Schema Files\n\n| Schema | Purpose |\n|---|---|\n| `a.yaml` | A |\n\nSupporting schemas that some sections use: `b.yaml` (§1) and\n`c.yaml` (§2).\n\n### 6.2 Next\n| `d.yaml` | D |\n';
    expect(standardSchemaNames(text)).toEqual({ required: ['a.yaml'], supporting: ['b.yaml', 'c.yaml'] });
  });

  it('puts every required schema in the required group and leaves out catalogs and profiles', () => {
    const entries = schemaListing(spec);
    expect(entries.filter((e) => e.group === 'required').map((e) => e.name).sort()).toEqual(canonicalSchemaNames().sort());
    expect(entries.some((e) => e.source.startsWith('schemas/workflows/'))).toBe(false);
    expect(entries.filter((e) => e.source.startsWith('schemas/profiles/')).map((e) => e.name)).toEqual(['profiles/profile_schema.yaml']);
  });
});

describe('other page helpers', () => {
  it('reads the four RFC statuses from GOVERNANCE.md (design notes, ia-home 6.7)', () => {
    expect(governanceStatuses(readRepoFile('spec/GOVERNANCE.md'))).toEqual(['Draft', 'Accepted', 'Rejected', 'Superseded']);
  });

  it('sorts trust weights highest first and keeps file order on ties', () => {
    expect(sortedTrustWeights({ trust_weights: { a: 0.5, b: 0.9, c: 0.5, d: 1 } })).toEqual([
      { source: 'd', weight: 1 },
      { source: 'b', weight: 0.9 },
      { source: 'a', weight: 0.5 },
      { source: 'c', weight: 0.5 },
    ]);
  });

  it('splits a table cell into text and code spans, and rejects other Markdown', () => {
    expect(inlineMarkdown('A `requires` or `precedes` edge (§4.3)')).toEqual([
      { code: false, text: 'A ' },
      { code: true, text: 'requires' },
      { code: false, text: ' or ' },
      { code: true, text: 'precedes' },
      { code: false, text: ' edge (§4.3)' },
    ]);
    expect(() => inlineMarkdown('see [x](y)')).toThrow(/other than code spans/);
    expect(() => inlineMarkdown('an `open span')).toThrow(/unbalanced/);
  });

  it('gives generated headings ref- ids that stay unique on a page', () => {
    const id = refSlugger();
    expect([id('Inputs'), id('Inputs'), id('Used in workflows')]).toEqual(['ref-inputs', 'ref-inputs-1', 'ref-used-in-workflows']);
  });
});
