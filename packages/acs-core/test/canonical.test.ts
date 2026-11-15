import { describe, expect, it } from 'vitest';
import { canonicalize, digest, NotCanonicalizableError } from '../src/canonical.js';
// The reference executor's approval digest vectors, read in place
// (written by scripts/gen_standard_agents_binding.py).
import fixture from '../../../tests/conformance/approval/digests.json' with { type: 'json' };

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

describe('approval digest (STANDARD v1.2.0 §5.14)', () => {
  it('has vectors from the reference executor', () => {
    expect(fixture.vectors.length).toBeGreaterThanOrEqual(10);
  });

  it.each(fixture.vectors.map((v) => [v.name, v] as const))(
    'matches the reference executor on vector %s',
    async (_name, vector) => {
      expect(canonicalize(vector.shown)).toBe(vector.canonical);
      expect(await digest(vector.shown)).toBe(vector.digest);
    },
  );
});
