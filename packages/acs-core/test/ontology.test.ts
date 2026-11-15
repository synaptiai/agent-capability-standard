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
