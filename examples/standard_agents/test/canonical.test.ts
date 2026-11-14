import { describe, expect, it } from 'vitest';
import { canonicalize, digest, NotCanonicalizableError } from '../src/acs/canonical.js';
// Digests the reference executor computed for these shown values; see
// tools/gen_standard_agents_ontology.py --digests.
import fixture from './fixtures/approval-digests.json' with { type: 'json' };

describe('canonical JSON (RFC 8785)', () => {
  it('sorts members by UTF-16 code units and drops whitespace', () => {
    expect(canonicalize({ b: 2, a: 1, A: 0, '': null })).toBe('{"":null,"A":0,"a":1,"b":2}');
  });

  it('writes numbers as ECMAScript does', () => {
    expect(canonicalize([0, -0, 1.5, 1e21, 1e-7, 100, 4.5e-10])).toBe('[0,0,1.5,1e+21,1e-7,100,4.5e-10]');
  });

  it('rejects values that are not JSON', () => {
    expect(() => canonicalize(Number.NaN)).toThrow(NotCanonicalizableError);
    expect(() => canonicalize(undefined)).toThrow(NotCanonicalizableError);
    expect(() => canonicalize(new Date(0))).toThrow(NotCanonicalizableError);
    expect(() => canonicalize({ f: () => 1 })).toThrow(NotCanonicalizableError);
  });
});

describe('approval digest (STANDARD v1.1.0 §5.14)', () => {
  it('has vectors from the reference executor', () => {
    expect(fixture.vectors.length).toBeGreaterThanOrEqual(10);
  });

  it.each(fixture.vectors.map((v, i) => [i, v] as const))(
    'matches the reference executor on vector %i',
    async (_i, vector) => {
      expect(await digest(vector.shown)).toBe(vector.digest);
    },
  );
});
