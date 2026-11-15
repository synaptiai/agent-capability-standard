import { describe, expect, it } from 'vitest';
import { canonicalize, digest, NotCanonicalizableError } from '../src/acs/canonical.js';

describe('values RFC 8785 refuses', () => {
  // §3.2.2.2: data with an unpaired surrogate "MUST cause a compliant JCS
  // implementation to terminate with an appropriate error". The reference
  // executor cannot hold such a string, so no digest could agree with it.
  it.each([
    ['a lone high surrogate', '\ud83d'],
    ['a lone low surrogate', '\ude00'],
    ['a low surrogate before a high one', '\ude00\ud83d'],
    ['a high surrogate at the end of text', 'ok \ud800'],
  ])('refuses a string with %s', (_name, text) => {
    expect(() => canonicalize(text)).toThrow(NotCanonicalizableError);
    expect(() => canonicalize({ [text]: 1 })).toThrow(NotCanonicalizableError);
    expect(() => canonicalize([{ key: text }])).toThrow(NotCanonicalizableError);
  });

  it('keeps a paired surrogate', () => {
    expect(canonicalize('😀')).toBe('"😀"');
    expect(canonicalize({ '😀': 1 })).toBe('{"😀":1}');
  });

  it('refuses an array with a hole, which no JSON text produces', async () => {
    expect(() => canonicalize([1, , 3])).toThrow(NotCanonicalizableError);
    expect(() => canonicalize([,])).toThrow(NotCanonicalizableError);
    expect(() => canonicalize(new Array(2))).toThrow(NotCanonicalizableError);
    await expect(digest([1, , 3])).rejects.toThrow(NotCanonicalizableError);
  });
});
