import { describe, expect, it } from 'vitest';
import type { Json } from '../src/canonical.js';
import { DEFAULT_PATTERNS, holdsCredential, holdsSecret, MARKER, redactJson, redactText } from '../src/redact.js';
// The redaction vectors, read in place; the Python redactor
// (grounded_agency/state/redaction.py) is held to the same file.
import vectors from '../../../tests/conformance/secrets/redact.json' with { type: 'json' };

interface Vector {
  name: string;
  input: Json;
  secret_values: string[];
  expect: { output: Json; pointers: string[] };
}

const cases = vectors.vectors as Vector[];

describe('redaction vectors (STANDARD v1.2.0 §6.7)', () => {
  it('has vectors', () => {
    expect(vectors.standard).toBe('1.2.0');
    expect(cases.length).toBeGreaterThanOrEqual(20);
  });

  it.each(cases.map((v) => [v.name, v] as const))('%s', (_name, vector) => {
    const given = structuredClone(vector.input);
    const { value, pointers } = redactJson(given, vector.secret_values);
    expect(value).toEqual(vector.expect.output);
    expect(pointers).toEqual(vector.expect.pointers);
    // The value given is not modified, and redacting again changes nothing.
    expect(given).toEqual(vector.input);
    expect(redactJson(value, vector.secret_values)).toEqual({ value, pointers: [] });
    expect(holdsSecret(vector.input, vector.secret_values)).toBe(pointers.length > 0);
    if (typeof vector.input === 'string') {
      expect(redactText(vector.input, vector.secret_values)).toBe(vector.expect.output);
    }
  });
});

describe('redactor', () => {
  it('marks every secret with the group secret, and finds it again', () => {
    expect(MARKER).toBe('[REDACTED]');
    for (const p of DEFAULT_PATTERNS) {
      expect(p.source).toContain('(?<secret>');
      expect(p.flags).toContain('g');
    }
    // The patterns are global; a second call finds the same secrets.
    expect(redactText('password=hunter22')).toBe('password=[REDACTED]');
    expect(redactText('password=hunter22')).toBe('password=[REDACTED]');
  });

  it('replaces registered values longest first, and ignores short ones', () => {
    expect(redactText('hunter22 and hunter', ['hunter', 'hunter22', 'abc'])).toBe('[REDACTED] and [REDACTED]');
    expect(redactText('abc', ['abc'])).toBe('abc');
  });

  it('escapes pointers', () => {
    const { pointers } = redactJson({ 'a~b': ['Bearer abcdefgh12345678'], c: { client_secret: 's3cr3t!' } });
    expect(pointers).toEqual(['/a~0b/0', '/c/client_secret']);
  });
});

describe('reading a long text (security round 1, batch 5)', () => {
  // Runs a pattern could read again from each of their positions: a URL
  // scheme's characters, JWT starts (`eyJ`, after `-`), PEM headers with no
  // end, base64url and hex text. Each took minutes or more at 1 MB before
  // the patterns read a run once.
  const units = [
    'a.',
    'a-',
    'a+',
    'f0',
    'x',
    'eyJ',
    'eyJ-',
    'a-eyJ',
    'eyJaaaaaaaa.',
    '-----BEGIN PRIVATE KEY-----',
    '-----BEGIN RSA PRIVATE KEY-----x',
    'a://b:',
    // Pairs and tuples in text (security round 1, batch 6).
    '"x',
    '"token", "',
    "['token', '",
    '"cookie", "value": "Basic ',
    '["',
  ];
  it.each(units)('reads 1 MB of %j in time in proportion to its length', (unit) => {
    const text = unit.repeat(Math.ceil(1_000_000 / unit.length)).slice(0, 1_000_000);
    const started = performance.now();
    holdsCredential({ data: text });
    redactText(text);
    holdsSecret({ data: text });
    // Well under a second here; the old patterns took 10 s at 100 KB.
    expect(performance.now() - started).toBeLessThan(20_000);
  });

  it('matches as before, and reads a URL scheme inside a word', () => {
    // A JWT starts at a word boundary: the run's start or after `-`.
    expect(redactText('abc-eyJhbGciOi.eyJzdWIi.sig1')).toBe('abc-[REDACTED]');
    expect(redactText('aeyJhbGciOi.eyJzdWIi.sig1')).toBe('aeyJhbGciOi.eyJzdWIi.sig1');
    expect(redactText('aeyJ-eyJhbGciOi.x.y')).toBe('aeyJ-[REDACTED]');
    // A PEM header with no end: nothing is replaced; a key after it is read
    // as before, from the first header to the first end.
    expect(redactText('-----BEGIN PRIVATE KEY----- x')).toBe('-----BEGIN PRIVATE KEY----- x');
    expect(
      redactText('-----BEGIN PRIVATE KEY-----a-----BEGIN PRIVATE KEY-----b-----END PRIVATE KEY-----'),
    ).toBe('-----BEGIN PRIVATE KEY-----[REDACTED]-----END PRIVATE KEY-----');
    // A URL's scheme is a run of scheme characters holding a letter.
    expect(redactText('x_https://deploy:hunter22@h')).toBe('x_https://deploy:[REDACTED]@h');
    expect(redactText('12://deploy:hunter22@h')).toBe('12://deploy:hunter22@h');
    expect(holdsCredential('x_https://deploy:hunter22@h')).toBe(true);
  });
});
