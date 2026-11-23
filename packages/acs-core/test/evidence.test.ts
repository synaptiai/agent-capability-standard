import { describe, expect, it } from 'vitest';
import type { Json } from '../src/canonical.js';
import {
  checkGrounding,
  covers,
  groundingPolicies,
  isEvidenceAnchor,
  isKind,
  isMethod,
  parseRef,
  refsIn,
  shownValue,
} from '../src/evidence.js';
import { holdsCredential } from '../src/redact.js';
// The grounding vectors (normative for §5.20), read in place; the Rust core
// and the Python package are held to the same file.
import vectors from '../../../tests/conformance/grounding/check.json' with { type: 'json' };
// The refusal rule's credential vectors (informative), which the Python
// redactor and hooks/secret_scan.sh run too.
import credentials from '../../../tests/conformance/secrets/credentials.json' with { type: 'json' };

interface Vector {
  name: string;
  output: Json;
  policy: { kinds: string[] | null; attested: boolean };
  bound_refs: string[];
  evidence_seen: string[] | null;
  expect: { status: string; code: string | null; counted?: number; legacy?: number };
}

const cases = vectors.vectors as Vector[];

describe('grounding vectors (STANDARD v1.2.0 §5.20)', () => {
  it('has the normative vectors', () => {
    expect(vectors.status).toBe('normative');
    expect(cases.length).toBeGreaterThanOrEqual(45);
  });

  it.each(cases.map((v) => [v.name, v] as const))('%s', (_name, v) => {
    const got = checkGrounding(
      v.output,
      { ...(v.policy.kinds === null ? {} : { kinds: v.policy.kinds }), attested: v.policy.attested },
      { bound: v.bound_refs, seen: v.evidence_seen },
    );
    expect([got.status, got.code]).toEqual([v.expect.status, v.expect.code]);
    if (v.expect.status !== 'refused') {
      expect([got.counted, got.legacy]).toEqual([v.expect.counted, v.expect.legacy]);
    } else {
      expect(got.message).not.toBe('');
    }
  });
});

describe('references and coverage', () => {
  const yes: Array<[string, string]> = [
    ['r', 'r.data'],
    ['r.data', 'r.data[0].x'],
    ['r.items[2:5]', 'r.items[4].url'],
    ['r.items[2:]', 'r.items[40]'],
    ['r.items[:3]', 'r.items[0]'],
    ['r.items[0:10]', 'r.items[2:4]'],
  ];
  const no: Array<[string, string]> = [
    ['r', 's'],
    ['r.data', 'r'],
    ['r.data.x', 'r.secret'],
    ['r.items[2:5]', 'r.items[5]'],
    ['r.items[0:3]', 'r.items[1:5]'],
    ['r.items[0:3]', 'r.items[1:]'],
    ['r.items[1]', 'r.items[1:2]'],
    ['search_out.results[0]', 'search_out.results'],
  ];
  it.each(yes)('%s covers %s', (b, c) => expect(covers(parseRef(b), parseRef(c))).toBe(true));
  it.each(no)('%s does not cover %s', (b, c) => expect(covers(parseRef(b), parseRef(c))).toBe(false));

  it('parses as §5.3 does', () => {
    expect(parseRef('r.data[0:3]: array<object>')).toEqual({
      root: 'r',
      path: [{ field: 'data' }, { slice: [0, 3] }],
      annotation: 'array<object>',
    });
    for (const bad of ['', 'r.[', 'r[01]', 'r[]', '1r', 'r.x:']) expect(() => parseRef(bad)).toThrow();
  });

  it('refuses a bound reference that is not a body', () => {
    expect(() => checkGrounding({ evidence_anchors: [] }, {}, { bound: ['r: string'] })).toThrow(/reference body/);
  });
});

describe('anchors, kinds and methods', () => {
  it('knows the kinds and methods', () => {
    expect(isKind('record') && isKind('x-lab_result')).toBe(true);
    expect(isKind('tool_output') || isKind('File') || isKind('x-')).toBe(false);
    // A digest member that is undefined is absent (its JSON text has none);
    // null is present and malformed.
    const a = { ref: 'file:a', kind: 'file', digest: undefined };
    expect(isEvidenceAnchor(a)).toBe(true);
    expect(isEvidenceAnchor({ ref: 'file:a', kind: 'file', digest: null })).toBe(false);
    const out = { evidence_anchors: [a] };
    expect(checkGrounding(out, {}).status).toBe('grounded');
    expect(checkGrounding(JSON.parse(JSON.stringify(out)), {}).status).toBe('grounded');
    expect(isMethod('model_knowledge') && isMethod('x-acme.rules')).toBe(true);
    expect(isMethod('llm-reasoning')).toBe(false);
    expect(isEvidenceAnchor({ ref: 'file:a', kind: 'file', digest: `sha256:${'0'.repeat(64)}` })).toBe(true);
    expect(isEvidenceAnchor({ ref: 'file:a', kind: 'file', digest: null })).toBe(false);
    expect(isEvidenceAnchor('file:a')).toBe(false);
  });

  it('lists the anchors inside arguments', () => {
    expect(
      refsIn({
        doc: { ref: 'file:a', kind: 'file' },
        list: [{ ref: 'url:x', kind: 'url' }, 'file:legacy', { ref: 'file:a', kind: 'file' }],
      }),
    ).toEqual(['file:a', 'url:x']);
  });
});

describe('grounding policies', () => {
  it('normalises one or several', () => {
    const one = groundingPolicies({ require: ['search'] });
    expect(one).toEqual([{ require: ['search'] }]);
    expect(Object.isFrozen(one[0])).toBe(true);
    expect(groundingPolicies([{ require: ['search'], kinds: ['file'], attested: true }])).toHaveLength(1);
    // An extension member is allowed, and not kept.
    expect(groundingPolicies({ require: ['search'], 'x-note': 'audit' } as never)).toEqual([{ require: ['search'] }]);
  });

  it.each([
    [{ require: ['clasify'] }, /V101.*clasify/],
    [{ require: [] }, /non-empty/],
    [{ require: ['search', 'search'] }, /twice/],
    [{ require: ['search'], kinds: [] }, /non-empty/],
    [{ require: ['search'], kinds: ['tool_output'] }, /not an evidence anchor kind/],
    [{ require: ['search'], attested: 'yes' }, /boolean/],
    [{ require: ['retrieve'], kind: ['file'] }, /'kind' is not a member of a grounding policy/],
    [{ require: ['retrieve'], atested: true }, /^S303 SCHEMA_VALIDATION_FAILED: grounding\[0\]: 'atested'/],
  ])('refuses %j', (policy, message) => {
    expect(() => groundingPolicies(policy as never)).toThrow(message);
  });
});

describe('grounding messages repeat nothing an anchor cites (§6.7)', () => {
  // A presigned URL, a signed URL and a URL with a password: a message names
  // the anchor by its index and kind, as the core's does.
  const SECRET = 'wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY99';
  const refs = [
    `https://bucket.s3.amazonaws.com/r.csv?X-Amz-Credential=AKIAIOSFODNN7EXAMPLE&X-Amz-Signature=${SECRET}`,
    `https://acct.blob.core.windows.net/c/r.csv?sv=2022-11-02&sig=${SECRET}`,
    `https://user:${SECRET}@example.com/r.csv`,
  ];
  const policy = { attested: true };

  it.each(refs)('an anchor evidence_seen does not list: %s', (ref) => {
    for (const kind of ['url', 'x-signed']) {
      const r = checkGrounding({ evidence_anchors: [{ ref, kind }] }, policy, { seen: [] });
      expect(r.code).toBe('F505');
      expect(r.message).not.toContain(SECRET);
      expect(r.message).not.toContain('AKIA');
      expect(r.message).not.toContain(kind === 'url' ? 'x-signed' : 'signed');
      expect(r.message.startsWith('evidence_anchors[0] (')).toBe(true);
    }
  });

  it('an acs: anchor, and the inference marking', () => {
    for (const [anchor, bound] of [
      [{ ref: `acs:inputs.${SECRET}`, kind: 'url' }, []],
      [{ ref: `acs:inputs.${SECRET}`, kind: SECRET }, []],
      [{ ref: `acs:inputs.k ${SECRET}`, kind: 'record' }, []],
      [{ ref: `acs:inputs.${SECRET}`, kind: 'record' }, ['inputs.other']],
    ] as const) {
      const r = checkGrounding({ evidence_anchors: [anchor] }, policy, { bound: [...bound] });
      expect(r.code).toBe('F505');
      expect(r.message).not.toContain(SECRET);
      expect(r.message.startsWith('evidence_anchors[0] ')).toBe(true);
    }
    const r = checkGrounding({ evidence_anchors: [], inference_method: SECRET, confidence: SECRET }, policy);
    expect(r.message).not.toContain(SECRET);
    expect(r.message).toContain('a confidence (a string)');
  });

  it('names a value by its type unless it is a number, a boolean or null', () => {
    expect([SECRET, [SECRET], { k: SECRET }, 1.5, true, null, undefined].map(shownValue)).toEqual([
      'a string',
      'an array',
      'an object',
      '1.5',
      'true',
      'null',
      'absent',
    ]);
  });
});

describe('credentials a refusal recognises (§6.7)', () => {
  interface CredentialVector {
    name: string;
    input: Json;
    secret_values: string[];
    expect: { holds: boolean };
  }
  const all = credentials.vectors as CredentialVector[];
  const text = all.filter((v) => typeof v.input === 'string' && v.secret_values.length === 0);
  const blocked = text.filter((v) => v.expect.holds).map((v) => v.input as string);
  const allowed = text.filter((v) => !v.expect.holds).map((v) => v.input as string);
  it('has both kinds of vector', () => {
    expect(blocked.length).toBeGreaterThan(0);
    expect(allowed.length).toBeGreaterThan(0);
  });
  it.each(all.map((v) => [v.name, v] as const))('vector %s', (_name, v) => {
    expect(holdsCredential(v.input, v.secret_values)).toBe(v.expect.holds);
    if (typeof v.input === 'string') {
      expect(holdsCredential({ todos: [{ content: v.input }] }, v.secret_values)).toBe(v.expect.holds);
    }
  });
  it.each(blocked)('blocks %s', (t) => {
    expect(holdsCredential(t)).toBe(true);
    expect(holdsCredential({ todos: [{ content: t }] })).toBe(true);
  });
  it.each(allowed)('lets %s pass', (t) => {
    expect(holdsCredential(t)).toBe(false);
    expect(holdsCredential({ todos: [{ content: t }] })).toBe(false);
  });
  it('reads a member name as an assignment, and registered values', () => {
    expect(holdsCredential({ api_key: 'abc123def456ghi' })).toBe(true);
    expect(holdsCredential({ note: 'deploy with s3cr3t-value' }, ['s3cr3t-value'])).toBe(true);
  });
});
