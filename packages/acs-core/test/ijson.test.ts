/**
 * The package's one I-JSON check (`iJsonProblem`) and the exact reader of
 * JSON text (`parseJsonExact`), which keeps an integer literal beyond 2^53
 * from being rounded into a value the check accepts.
 */
import { describe, expect, it } from 'vitest';
import { iJsonProblem, parseJsonExact } from '../src/ijson.js';

describe('parseJsonExact', () => {
  it('reads an integer literal beyond 2^53 as a bigint, which the check refuses', () => {
    const value = parseJsonExact('{"n": 9007199254740993, "m": -9007199254740993}') as Record<string, unknown>;
    expect(value).toEqual({ n: 9007199254740993n, m: -9007199254740993n });
    expect(iJsonProblem(value)).toMatch(/outside ±2\^53/);
    // JSON.parse would have rounded it to 2^53, which the check accepts.
    expect(iJsonProblem(JSON.parse('{"n": 9007199254740993}'))).toBeNull();
  });

  it('reads every other value as JSON.parse does', () => {
    for (const text of ['9007199254740992', '-9007199254740992', '1e21', '1.8e16', '18000000000000000.5', '1.5', '[1, "a", null, true]']) {
      expect(parseJsonExact(text)).toEqual(JSON.parse(text));
    }
  });

  it('leaves the number rule for what the text holds', () => {
    expect(iJsonProblem(parseJsonExact('9007199254740992'))).toBeNull();
    expect(iJsonProblem(parseJsonExact('1e21'))).toBeNull();
    // An integral number below 1e21 is written back as an integer literal.
    expect(iJsonProblem(parseJsonExact('1.8e16'))).toMatch(/outside ±2\^53/);
  });

  it('refuses text that is not JSON', () => {
    expect(() => parseJsonExact('{"n": 1,}')).toThrow(SyntaxError);
  });
});

describe('iJsonProblem', () => {
  it('refuses a bigint, which is not a JSON value', () => {
    expect(iJsonProblem({ n: 1n })).toBe('holds a bigint at $.n, not JSON');
    expect(iJsonProblem({ n: 2n ** 60n })).toBe(
      'holds the integer 1152921504606846976 at $.n, outside ±2^53, which has no exact I-JSON form',
    );
  });
});
