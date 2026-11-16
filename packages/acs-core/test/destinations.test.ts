// The destination policy vectors (Standard 1.2.0 section 4.4.2), read in
// place: the grammar here is held to the same file as the core's.
import { describe, expect, it } from 'vitest';
import vectors from '../../../tests/conformance/destinations/match.json' with { type: 'json' };
import { allowed, checkPattern, checkPolicies, matches } from '../src/destinations.js';

const raw = import.meta.glob<string>('../../../tests/conformance/destinations/match.json', {
  eager: true,
  import: 'default',
  query: '?raw',
});

describe('destination policy vectors (STANDARD 1.2.0 section 4.4.2)', () => {
  it('is ASCII, so the NFC and NFD cases stay distinct', () => {
    const text = Object.values(raw)[0] as string;
    expect(text.length).toBeGreaterThan(0);
    expect(/^[\x00-\x7f]*$/.test(text)).toBe(true);
  });
  it.each(vectors.patterns.map((c) => [JSON.stringify(c.pattern), c] as const))('pattern %s', (_n, c) => {
    expect(checkPattern(c.pattern) === null).toBe(c.valid);
    expect(checkPolicies([[c.pattern]]) === null).toBe(c.valid);
    // An invalid pattern matches nothing.
    if (!c.valid) expect(matches(c.pattern, c.pattern)).toBe(false);
  });
  it.each(vectors.matches.map((c) => [`${JSON.stringify(c.policies)} ${JSON.stringify(c.destination)}`, c] as const))(
    'match %s',
    (_n, c) => {
      expect(allowed(c.policies, c.destination)).toBe(c.allowed);
    },
  );
  it('names the first invalid pattern', () => {
    expect(checkPolicies([['ok'], ['ok', '**']])).toMatch(/^policy 1, pattern 1: /);
  });
});
