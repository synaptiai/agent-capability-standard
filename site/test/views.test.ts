// Tests for what the generated pages show. Expected values on live data come
// from line scans of the YAML in test/independent.ts, the CLAUDE.md layer
// table and tools/validate_canonical_schemas.py, not from the loaders. Tests
// on fixtures state where each expected value comes from.
import { describe, expect, it } from 'vitest';
import { governanceStatuses as scriptGovernanceStatuses } from '../scripts/check-design-data.mjs';
import { governanceStatuses } from '../src/lib/governance';
import { EDGE_TYPES, loadOntology } from '../src/data/ontology';
import { capabilityUsage, loadWorkflows, parseCatalog } from '../src/data/workflows';
import { inlineMarkdown, pageHref, refSlugger } from '../src/lib/generated';
import { readRepoFile } from '../src/lib/repo';
import {
  crossLayerEdges,
  edgeGroups,
  layerUsage,
  producerSteps,
  schemaDescription,
  schemaListing,
  schemaRows,
  sortedTrustWeights,
  standardSchemaNames,
  capabilitySymbols,
  diagramRuns,
  diagramSteps,
  failureRows,
  splitAtFirstH2,
} from '../src/lib/views';
import {
  allCatalogSteps,
  canonicalSchemaNames,
  catalogFiles,
  catalogOnErrorCodes,
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

  it('lists exactly the edges that cross each layer boundary, a symmetric pair once', () => {
    // Expected: the line-scanned triples; for a symmetric type the first declaration of each unordered pair.
    for (const layer of claudeLayerTable()) {
      const want = EDGE_TYPES.map((type) => {
        const seen = new Set<string>();
        const edges = triples
          .filter((t) => t.type === type && (layerOf.get(t.from) === layer.id) !== (layerOf.get(t.to) === layer.id))
          .filter((t) => {
            if (!symmetric.includes(type)) return true;
            const pair = [t.from, t.to].sort().join('|');
            if (seen.has(pair)) return false;
            seen.add(pair);
            return true;
          })
          .map((t) => `${t.from}>${t.to}`);
        return { type, edges };
      }).filter((g) => g.edges.length > 0);
      const got = crossLayerEdges(layer.id).map((g) => ({ type: g.type, edges: g.edges.map((e) => `${e.from}>${e.to}`) }));
      expect(got, layer.id).toEqual(want);
    }
  });

  it('declares both directions of some cross-layer symmetric pair, so the test above can tell', () => {
    const both = triples.filter(
      (t) =>
        symmetric.includes(t.type) &&
        layerOf.get(t.from) !== layerOf.get(t.to) &&
        triples.some((u) => u.type === t.type && u.from === t.to && u.to === t.from),
    );
    expect(both.map((t) => `${t.from}>${t.to}`)).toContain('rollback>persist');
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

describe('workflow diagram roles', () => {
  // A hand-written catalog. Expected roles follow design notes, design-system
  // section 12; expected flags follow Standard 1.1.0 §5.2.1 and the ontology
  // values CLAUDE.md "Safety Model" lists (mutate and send need a checkpoint,
  // rollback needs one through its requires edge, audit is mutation_overridable).
  const yaml = `
fixture_flow:
  goal: test
  risk: high
  steps:
    - capability: send
      store_as: early
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
    - capability: persist
    - capability: constrain
      parallel_group: g
    - capability: observe
      parallel_group: g
      join: all
`;
  const wf = parseCatalog('fixture.yaml', yaml, 'core', loadOntology())[0]!;
  const steps = diagramSteps(wf);

  it('gives each step its role', () => {
    expect(steps.map((d) => d.role)).toEqual([
      'mutating', // send
      'checkpoint',
      'mutating',
      'verify',
      'rollback',
      'plain', // audit with mutation: false
      'plain', // persist mutates, but only records
      'verify', // constrain
      'plain',
    ]);
  });

  it('points mutating and rollback steps at the nearest earlier checkpoint', () => {
    expect(steps.map((d) => d.checkpointStep)).toEqual([null, null, 2, null, 2, null, null, null, null]);
  });

  it('flags a step that needs a checkpoint when none comes before it', () => {
    // send has a requires edge from checkpoint, so the code is V102 (flags.ts, Standard §4.3).
    expect(steps.map((d) => d.missingCheckpoint)).toEqual(['V102', null, null, null, null, null, null, null, null]);
  });

  it('draws steps with gates or a condition as branches', () => {
    expect(steps.map((d) => d.branch)).toEqual([false, false, false, true, true, false, false, false, false]);
  });

  it('boxes consecutive steps of one parallel group together', () => {
    expect(diagramRuns(steps).map((r) => [r.group, r.steps.map((d) => d.step.index), r.join])).toEqual([
      ...[1, 2, 3, 4, 5, 6, 7].map((i) => [null, [i], undefined]),
      ['g', [8, 9], 'all'],
    ]);
  });

  it('finds the step that produced each output a step reads, bindings before the condition', () => {
    // workflows.ts scans input_bindings, then gates, then condition.
    expect(producerSteps(wf, wf.steps[4]!)).toEqual([
      { name: 'cp', index: 2 },
      { name: 'checked', index: 4 },
    ]);
  });
});

describe('periodic table symbols', () => {
  it('gives the symbols the design lists, in layer order', () => {
    // Design notes, design-system section 11, "Symbol rule".
    const listed = 'Rt Sr Ob Rc Dt Cl Ms Pr Cm Ds Pl Dc Cr Ex St Tr At Gr Sm Gn Tn In Ec Mt Sn Vr Ch Rl Cn Ad Ps Re Dl Sy Iv Iq'.split(' ');
    const order = claudeLayerTable().flatMap((l) => l.capabilities);
    expect([...capabilitySymbols(order).values()]).toEqual(listed);
  });

  it('falls back to a vowel when every consonant symbol is taken, and fails when nothing is left', () => {
    // Hand computed: rot -> R + t; rote -> Rt is taken and has no other consonant, so R + o.
    expect([...capabilitySymbols(['rot', 'rote']).values()]).toEqual(['Rt', 'Ro']);
    expect(() => capabilitySymbols(['rot', 'rote', 'root'])).toThrow(/no unused symbol for root/);
  });
});

describe('schemas listing', () => {
  const spec = repoText(`spec/STANDARD-v${standardFileVersions()[0]}.md`);

  it('takes the required schemas from §6.1, as the canonical schema validator lists them', () => {
    expect(standardSchemaNames(spec).required.sort()).toEqual(canonicalSchemaNames().sort());
  });

  it('reads the supporting schemas from the sentence after the table', () => {
    const text = '### 6.1 Required Schema Files\n\n| Schema | Purpose |\n|---|---|\n| `a.yaml` | A |\n\nSupporting schemas that some sections use: `b.yaml` (§1) and\n`c.yaml` (§2).\n\n### 6.2 Next\n| `d.yaml` | D |\n';
    expect(standardSchemaNames(text)).toEqual({
      required: ['a.yaml'],
      supporting: ['b.yaml', 'c.yaml'],
      purposes: { 'a.yaml': 'A' },
    });
  });

  it('puts every required schema in the required group and leaves out catalogs and profiles', () => {
    const entries = schemaListing(spec);
    expect(entries.filter((e) => e.group === 'required').map((e) => e.name).sort()).toEqual(canonicalSchemaNames().sort());
    expect(entries.some((e) => e.source.startsWith('schemas/workflows/'))).toBe(false);
    expect(entries.filter((e) => e.source.startsWith('schemas/profiles/')).map((e) => e.name)).toEqual(['profiles/profile_schema.yaml']);
  });
});

describe('schema descriptions', () => {
  // Hand-written inputs in the three header forms the files under schemas/ use.
  it('reads the description under a top-level mapping', () => {
    expect(schemaDescription('x.yaml', 'schema:\n  name: n\n  description: Who a party\n    is.\n')).toBe('Who a party is.');
  });
  it('reads the first comment line that is not a Key: value line, not a workflow description', () => {
    const text = '# Standard version: 1.1.0\n# Workflow Catalog\n# More\nflow:\n  goal: g\n  description: A workflow\n';
    expect(schemaDescription('x.yaml', text)).toBe('Workflow Catalog');
  });
  it('reads a JSON schema description', () => {
    expect(schemaDescription('x.schema.json', '{"title": "T", "description": "D  two"}')).toBe('D two');
  });
});

describe('other page helpers', () => {
  it('reads the four RFC statuses from GOVERNANCE.md (design notes, ia-home 6.7)', () => {
    expect(governanceStatuses(readRepoFile('spec/GOVERNANCE.md'))).toEqual(['Draft', 'Accepted', 'Rejected', 'Superseded']);
  });

  it('reads the RFC statuses with or without an Oxford comma', () => {
    const want = ['Draft', 'Accepted', 'Rejected', 'Superseded'];
    for (const sentence of [
      "An RFC's status is Draft, Accepted, Rejected, or Superseded.",
      "An RFC's status is Draft, Accepted, Rejected or Superseded.",
      "An RFC's status is Draft,Accepted , Rejected,  or\n Superseded (by a later RFC).",
    ]) {
      expect(governanceStatuses(sentence), sentence).toEqual(want);
      expect(scriptGovernanceStatuses(sentence), sentence).toEqual(want);
    }
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

describe('failure modes on workflow pages', () => {
  // Expected: the on_error values of every catalog by line scan, which reads
  // both the single-code and the list form that Standard 1.1.0 allows.
  const { core, domain } = catalogFiles();
  const scanned = new Map<string, string[]>();
  for (const f of [core, ...domain]) for (const [k, v] of catalogOnErrorCodes(f)) scanned.set(k, v);

  it('reads single codes as well as lists in the scan', () => {
    expect(scanned.get('monitor_and_replan')).toContain('R402');
  });

  it('shows every on_error code of every workflow, in file order', () => {
    const workflows = loadWorkflows();
    for (const [id, want] of scanned) {
      const wf = workflows.byId.get(id);
      expect(wf, id).toBeDefined();
      expect(wf!.steps.flatMap((s) => failureRows(s).flatMap((r) => r.codes)), id).toEqual(want);
    }
  });
});

describe('links to a part of a page', () => {
  // Expected: the "## Decision-making" heading of spec/GOVERNANCE.md, slugged by hand as GitHub does
  // (lower case, spaces to hyphens).
  it('accepts a fragment that is a heading of the page source', () => {
    expect(repoText('spec/GOVERNANCE.md').split('\n')).toContain('## Decision-making');
    expect(pageHref('/community/governance/#decision-making')).toBe('/community/governance/#decision-making');
  });

  it('rejects a fragment that no heading of the page source has', () => {
    expect(() => pageHref('/community/governance/#decision-process')).toThrow(/decision-process/);
  });
});

describe('domain page order', () => {
  it('splits rendered Markdown before the first H2 and not at an H1, H3 or header element', () => {
    const html = '<h1 id="t">T</h1><header>x</header><p>Lead</p><h2 id="a">A</h2><h3 id="b">B</h3><h2 id="c">C</h2>';
    expect(splitAtFirstH2(html)).toEqual({
      head: '<h1 id="t">T</h1><header>x</header><p>Lead</p>',
      rest: '<h2 id="a">A</h2><h3 id="b">B</h3><h2 id="c">C</h2>',
    });
    expect(splitAtFirstH2('<h1>T</h1><p>x</p>')).toEqual({ head: '<h1>T</h1><p>x</p>', rest: '' });
  });
});
