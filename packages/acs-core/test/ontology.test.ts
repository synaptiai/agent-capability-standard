import { describe, expect, it } from 'vitest';
import {
  CAPABILITIES,
  effectiveFlags,
  isCapability,
  ONTOLOGY_VERSION,
  prerequisites,
  SPEC_VERSIONS,
  STANDARD_VERSION,
  TRUST_CLASSES,
} from '../src/index.js';

describe('the ontology table', () => {
  it('names the versions', () => {
    expect(STANDARD_VERSION).toMatch(/^\d+\.\d+\.\d+$/);
    expect(ONTOLOGY_VERSION).toMatch(/^2\.\d+\.\d+$/);
    // The Standard version this package implements is one a workflow may target.
    expect(SPEC_VERSIONS).toContain(STANDARD_VERSION.split('.').slice(0, 2).join('.'));
    expect(SPEC_VERSIONS).toEqual(['1.0', '1.1', '1.2']);
  });

  it('lists the capabilities and their flags', () => {
    expect(Object.keys(CAPABILITIES)).toHaveLength(36);
    expect(isCapability('mutate')).toBe(true);
    expect(isCapability('teleport')).toBe(false);
    expect(CAPABILITIES.send.requires_approval).toBe(true);
    expect(prerequisites('mutate')).toEqual(['checkpoint']);
    expect(prerequisites('retrieve')).toEqual([]);
    expect(TRUST_CLASSES).toContain('owner');
  });
});

describe('effective flags (STANDARD v1.2.0 §5.2.1)', () => {
  it('takes the stricter of the declaration and the ontology', () => {
    expect(effectiveFlags('retrieve', { risk: 'high', requires_approval: true })).toEqual({
      flags: { risk: 'high', mutation: false, requires_checkpoint: false, requires_approval: true },
      warnings: [],
    });
  });

  it('reports a weaker declaration (W602), which has no effect', () => {
    const { flags, warnings } = effectiveFlags('mutate', { risk: 'low', mutation: false });
    expect(flags).toEqual({ risk: 'high', mutation: true, requires_checkpoint: true, requires_approval: true });
    expect(warnings).toHaveLength(2);
    expect(warnings.every((w) => w.startsWith('W602'))).toBe(true);
  });

  it('honours mutation: false where the ontology allows it', () => {
    expect(effectiveFlags('audit', { mutation: false }).flags.mutation).toBe(false);
  });
});

describe('the generated table agrees with the ontology', () => {
  it('as the core parses it: flags, layers, required outputs and requires edges', async () => {
    const { loadCore } = await import('./core.js');
    const { REQUIRES } = await import('../src/ontology.js');
    const core = await loadCore();
    const texts = import.meta.glob<string>('../../../schemas/capability_ontology.yaml', {
      eager: true,
      import: 'default',
      query: '?raw',
    });
    const onto = core.parseYaml(Object.values(texts)[0] as string, 8 * 1024 * 1024) as {
      nodes: { id: string; layer: string; risk?: string; mutation?: boolean; requires_checkpoint?: boolean; requires_approval?: boolean; mutation_overridable?: boolean; output_schema?: { required?: string[] } }[];
      edges: { from: string; to: string; type: string }[];
    };
    expect(Object.keys(CAPABILITIES)).toEqual(onto.nodes.map((n) => n.id));
    for (const n of onto.nodes) {
      const row = CAPABILITIES[n.id as keyof typeof CAPABILITIES];
      expect(row.layer, n.id).toBe(n.layer);
      expect(row.risk, n.id).toBe(n.risk ?? 'low');
      expect(row.mutation, n.id).toBe(n.mutation ?? false);
      expect(row.requires_checkpoint, n.id).toBe(n.requires_checkpoint ?? false);
      expect(row.requires_approval, n.id).toBe(n.requires_approval ?? false);
      expect(row.mutation_overridable, n.id).toBe(n.mutation_overridable ?? false);
      expect([...row.output_required], n.id).toEqual(n.output_schema?.required ?? []);
    }
    const requires = onto.edges.filter((e) => e.type === 'requires').map((e) => [e.from, e.to]);
    const sorted = (pairs: readonly (readonly string[])[]) => pairs.map((p) => p.join(' -> ')).sort();
    expect(sorted(REQUIRES)).toEqual(sorted(requires));
    for (const [from, to] of requires) expect(prerequisites(to as keyof typeof CAPABILITIES), `${from} -> ${to}`).toContain(from);
  });
});
