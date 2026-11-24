import { describe, expect, it } from 'vitest';
import type { Json } from '../src/canonical.js';
import {
  DEFAULT_PATTERNS,
  encodedForms,
  holdsCredential,
  holdsSecret,
  MARKER,
  redactAnchor,
  redactJson,
  redactText,
} from '../src/redact.js';
// The redaction vectors, read in place; the Python redactor
// (grounded_agency/state/redaction.py) is held to the same file.
import vectors from '../../../tests/conformance/secrets/redact.json' with { type: 'json' };

interface Vector {
  name: string;
  /** Redacted as an evidence anchor (`redactAnchor`). */
  anchor?: boolean;
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
    const { value, pointers } = (vector.anchor ? redactAnchor : redactJson)(given, vector.secret_values);
    expect(value).toEqual(vector.expect.output);
    // An anchor's pointers are those of the input read as a JSON value.
    if (vector.anchor) expect(redactJson(vector.input, vector.secret_values).pointers).toEqual(pointers);
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

describe('registered values in the forms text carries them (security round 1, batch 8)', () => {
  // The forms of a registered value, in order: tests/test_redaction.py pins
  // the same list for the Python redactor's encoded_forms.
  const pinned: string[] = JSON.parse(String.raw`["p@ss/w~rd é!\"", "p@ss/w~rd é!\\\"", "p@ss/w~rd \\u00e9!\\\"", "p@ss\\/w~rd é!\\\"", "p@ss\\/w~rd \\u00e9!\\\"", "p@ss/w~rd é!\\\\\\\"", "p@ss/w~rd \\\\u00e9!\\\\\\\"", "p@ss/w~rd \\u00e9!\\u0022", "p@ss/w~rd \\u00E9!\\u0022", "p@ss/w~rd \\\\u00e9!\\\\u0022", "p@ss/w~rd \\\\u00E9!\\\\u0022", "p%40ss%2Fw~rd%20%C3%A9%21%22", "p%40ss/w~rd%20%C3%A9%21%22", "p%40ss%2Fw~rd%20%C3%A9!%22", "p%40ss%2Fw~rd+%C3%A9%21%22", "p%40ss%2Fw%7Erd+%C3%A9%21%22", "p%40ss%2fw~rd%20%c3%a9%21%22", "p%40ss/w~rd%20%c3%a9%21%22", "p%40ss%2fw~rd%20%c3%a9!%22", "p%40ss%2fw~rd+%c3%a9%21%22", "p%40ss%2fw%7erd+%c3%a9%21%22"]`);
  const value = 'p@ss/w~rd \u00e9!"';

  it('gives the forms in the Python redactor\'s order', () => {
    expect(encodedForms(value)).toEqual(pinned);
    // A value with a lone surrogate has no UTF-8: its JSON forms only (.NET
    // writes the escape in upper-case hex).
    expect(encodedForms('ab\ud800cd')).toEqual([
      'ab\ud800cd',
      'ab\\ud800cd',
      'ab\\\\ud800cd',
      'ab\\uD800cd',
      'ab\\\\uD800cd',
    ]);
    // A value of letters and digits has one form.
    expect(encodedForms('s3cr3tValue')).toEqual(['s3cr3tValue']);
  });

  // As encoders that keep JSON safe inside HTML write a value (security round
  // 5, batch 6: a registered value holding &, <, >, ', + or = was kept).
  it.each([
    ['Go', "Zq8\\u0026mK\\u003c41\\u003epX'+w=="],
    ['Gson', 'Zq8\\u0026mK\\u003c41\\u003epX\\u0027+w\\u003d\\u003d'],
    ['.NET', 'Zq8\\u0026mK\\u003C41\\u003EpX\\u0027\\u002Bw=='],
    ['Go, twice', "Zq8\\\\u0026mK\\\\u003c41\\\\u003epX'+w=="],
  ])('replaces a registered value as %s writes it', (_, encoded) => {
    const html = "Zq8&mK<41>pX'+w==";
    expect(encodedForms(html)).toContain(encoded);
    const text = `terraform output failed: {"db_conn":{"value":"${encoded}"}}`;
    expect(redactText(text, [html])).toBe('terraform output failed: {"db_conn":{"value":"[REDACTED]"}}');
    expect(holdsCredential({ note: text }, [html])).toBe(true);
    expect(holdsCredential({ note: text })).toBe(false);
  });

  it.each([
    ['JSON.stringify', JSON.stringify(value).slice(1, -1)],
    ['JSON.stringify twice', JSON.stringify(JSON.stringify(value).slice(1, -1)).slice(1, -1)],
    ['encodeURIComponent', encodeURIComponent(value)],
    ['URLSearchParams', new URLSearchParams({ k: value }).toString().slice(2)],
  ])('replaces the value as %s gives it', (_, encoded) => {
    expect(encodedForms(value)).toContain(encoded);
    expect(redactText(`x=${encoded};`, [value])).toBe(`x=${MARKER};`);
    expect(holdsCredential({ note: `x=${encoded}` }, [value])).toBe(true);
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
    '-----BEGIN PGP PRIVATE KEY BLOCK-----',
    'a://b:',
    // Pairs and tuples in text (security round 1, batch 6).
    '"x',
    '"token", "',
    "['token', '",
    '"cookie", "value": "Basic ',
    '["',
    // Escaped quotes, empty userinfo users and command options (security
    // round 1, batch 8): a run of backslashes is read once, and an option's
    // attempt starts at its dashes.
    '\\',
    'password=\\',
    '\\"token\\", \\"value\\": \\"',
    '[\\"token\\", \\"',
    'a://:',
    '-u ',
    "'-u', '",
    '-ua:',
    '--a-',
    '--password ',
    '--password --',
    // A user option's name, read for at most 256 characters: `.-u` starts
    // an attempt at each of its positions, each read to the run's end
    // (security round 4, batch 1).
    '.-u',
    '.-U=',
    '!-u ',
    // Quoted values read to their closing quote, whitespace and all: a run
    // ends at the next quote of its kind or a line break, and a run with no
    // closing quote is read once more as an unquoted value (security round
    // 1, batch 8's verification).
    'password: "a ',
    'password=\'a password="a ',
    'password: "\\ ',
    'password=\'\\"a ',
    '"cookie", "value": "a ',
    "['token', 'a ",
    "-u 'a:b ",
    '--password "a ',
    // Authorization headers with any scheme, quoted or not (security round
    // 4, batch 5): an attempt starts at the header's name, or at the start
    // of a run of backslashes before its quote.
    'authorization: a b ',
    '"authorization: a',
    '\\"authorization: ',
    'authorization: "a ',
    "['authorization', 'a ",
    // Cookie headers, curl's cookie option, netrc entries, the JSON escapes
    // of quotes and slashes, and words after a quote's escape (security
    // round 5, batch 6).
    'cookie: a ',
    'set-cookie:',
    '"cookie": "a ',
    "'cookie: a ",
    'cookie=a ',
    '.-b',
    "-b 'a ",
    '--cookie a',
    '-ba',
    'login a ',
    'machine password ',
    '\\u0022',
    '\\u0022a',
    'password\\u0022:\\u0022a ',
    '[\\u0022token\\u0022, \\u0022',
    'a:\\/\\/b:',
    'token\\u003d',
    '\\/',
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

  // A text that opens a quoted value and never closes it (on one line): the
  // run is read to its end once for the quoted reading and once more as an
  // unquoted value, not again from each of its positions.
  const unclosed: [string, string][] = [
    ['password: "', 'a '],
    ["password: '", 'password: "a '],
    ['"passphrase": "', '\\ '],
    ['[\'cookie\', "', 'a ; '],
    ["-u 'a:", 'b c '],
    ['--password "', 'x\\y '],
    ['"Authorization: ', 'a '],
    ['Authorization: "', 'a b '],
    // A run of blanks after a quoted header line's colon, read once (security
    // round 5, batch 6), and a Cookie header's the same way.
    ['"Authorization:', ' '],
    ['"Authorization: Basic', ' '],
    ["'Cookie:", ' '],
    ['"Cookie": "', 'a; '],
    ['Cookie: a', ' '],
    ["-b '", 'a=b '],
    ['password\\u0022: \\u0022', 'a '],
  ];
  it.each(unclosed)('reads 1 MB of %j then %j with no closing quote in linear time', (prefix, tail) => {
    const text = (prefix + tail.repeat(Math.ceil(1_000_000 / tail.length))).slice(0, 1_000_000);
    const started = performance.now();
    holdsCredential({ data: text });
    redactText(text);
    holdsSecret({ data: text });
    expect(performance.now() - started).toBeLessThan(20_000);
  });

  it('replaces a quoted credential value whole', () => {
    // A passphrase's later words are no longer kept (security round 1,
    // batch 8's verification: only its first word was replaced).
    expect(redactText('ValueError: bad config {"passphrase": "correct horse battery staple"}')).toBe(
      'ValueError: bad config {"passphrase": "[REDACTED]"}',
    );
    // The refusal rule is unchanged: prose with a quoted phrase passes.
    expect(holdsCredential('token: "rotate monthly"')).toBe(false);
  });

  it('matches as before, and reads a URL scheme inside a word', () => {
    // A JWT starts at a word boundary: the run's start or after `-`.
    expect(redactText('abc-eyJhbGciOi.eyJzdWIi.sig1')).toBe('abc-[REDACTED]');
    expect(redactText('aeyJhbGciOi.eyJzdWIi.sig1')).toBe('aeyJhbGciOi.eyJzdWIi.sig1');
    expect(redactText('aeyJ-eyJhbGciOi.x.y')).toBe('aeyJ-[REDACTED]');
    // A PEM header with no end: the rest of the text is replaced, since an
    // excerpt of a key keeps its body (security round 4, batch 5: nothing
    // was replaced); a key after it is read as before, from the first header
    // to the first end.
    expect(redactText('-----BEGIN PRIVATE KEY----- x')).toBe('-----BEGIN PRIVATE KEY-----[REDACTED]');
    expect(
      redactText('-----BEGIN PRIVATE KEY-----a-----BEGIN PRIVATE KEY-----b-----END PRIVATE KEY-----'),
    ).toBe('-----BEGIN PRIVATE KEY-----[REDACTED]-----END PRIVATE KEY-----');
    // A URL's scheme is a run of scheme characters holding a letter.
    expect(redactText('x_https://deploy:hunter22@h')).toBe('x_https://deploy:[REDACTED]@h');
    expect(redactText('12://deploy:hunter22@h')).toBe('12://deploy:hunter22@h');
    expect(holdsCredential('x_https://deploy:hunter22@h')).toBe(true);
  });
});
