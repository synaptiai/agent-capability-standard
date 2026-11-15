/** A capability output over a text-only channel (STANDARD 1.2.0 §5.18.9). */
import { describe, expect, it } from 'vitest';
import { CapabilityOutputError, decodeCapabilityOutput, encodeCapabilityOutput } from '../src/output.js';
import vectors from '../../../tests/conformance/output/vectors.json' with { type: 'json' };

type Expect = 'ok' | { refuse: string };

function outcome(run: () => unknown): Expect {
  try {
    run();
  } catch (e) {
    if (e instanceof CapabilityOutputError) return { refuse: e.code };
    throw e;
  }
  return 'ok';
}

const GOOD = {
  observation: { files: 3 },
  evidence_anchors: [{ ref: 'tool:Bash:t1', kind: 'tool_output' }],
  confidence: 0.9,
};

describe('encode and decode', () => {
  it('round-trips', () => {
    const text = encodeCapabilityOutput('observe', GOOD);
    expect(JSON.parse(text)).toEqual(GOOD);
    expect(decodeCapabilityOutput('observe', text)).toEqual(GOOD);
    expect(decodeCapabilityOutput('observe', ` \n${text}\n`)).toEqual(GOOD);
  });

  it.each([
    JSON.stringify({ observation: 1, evidence_anchors: [] }),
    JSON.stringify([GOOD]),
    `Here it is: ${JSON.stringify(GOOD)}`,
    `${JSON.stringify(GOOD)}\nDone.`,
    '```json\n' + JSON.stringify(GOOD) + '\n```',
    '{"observation": 1, "observation": 2, "evidence_anchors": [], "confidence": 1}',
    '{"observation": {"a": 1, "a": 2}, "evidence_anchors": [], "confidence": 1}',
    '{"observation": NaN, "evidence_anchors": [], "confidence": 1}',
    '{"observation": 9007199254740993, "evidence_anchors": [], "confidence": 1}',
    '{"observation": "\\ud800", "evidence_anchors": [], "confidence": 1}',
    '{"observation": 1, "evidence_anchors": {}, "confidence": 1}',
    '{"observation": 1, "evidence_anchors": [], "confidence": 2}',
    '{"observation": ' + '['.repeat(101) + ']'.repeat(101) + ', "evidence_anchors": [], "confidence": 1}',
  ])('decode refuses %s with R402', (text) => {
    let thrown: unknown;
    try {
      decodeCapabilityOutput('observe', text);
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(CapabilityOutputError);
    const error = thrown as CapabilityOutputError;
    expect(error.code).toBe('R402');
    expect(error.message).toMatch(/^R402 EXECUTION_FAILED: /);
    expect(error.diagnostic.location.capability).toBe('observe');
  });

  it.each([[[GOOD]], [{ observation: 1, evidence_anchors: [] }], [{ ...GOOD, observation: 2 ** 53 + 2 }], [{ ...GOOD, observation: NaN }], [{ ...GOOD, observation: '\ud800' }]])(
    'encode refuses %j with R402',
    (output) => {
      expect(() => encodeCapabilityOutput('observe', output)).toThrow(CapabilityOutputError);
    },
  );

  it('accepts integers within ±2^53 and 100 levels', () => {
    expect(decodeCapabilityOutput('observe', encodeCapabilityOutput('observe', { ...GOOD, observation: -(2 ** 53) }))).toBeTruthy();
    let nested: unknown = [];
    for (let i = 0; i < 98; i += 1) nested = [nested];
    expect(decodeCapabilityOutput('observe', encodeCapabilityOutput('observe', { ...GOOD, observation: nested }))).toBeTruthy();
    expect(decodeCapabilityOutput('observe', '{"observation": "a\\"{b", "evidence_anchors": [], "confidence": 1}')).toBeTruthy();
  });
});

describe('the shared vectors (tests/conformance/output/vectors.json)', () => {
  it.each(vectors.decode.map((v) => [v.name, v] as const))('decode %s', (_name, v) => {
    expect(outcome(() => decodeCapabilityOutput('observe', v.text))).toEqual(v.expect as Expect);
  });

  it.each(vectors.encode.map((v) => [v.name, v] as const))('encode %s', (_name, v) => {
    const value: unknown = JSON.parse(v.value_text);
    // What a producer sends, a consumer accepts.
    const run = () => decodeCapabilityOutput('observe', encodeCapabilityOutput('observe', value));
    expect(outcome(run)).toEqual(v.expect as Expect);
  });
});

describe('numbers as the text writes them', () => {
  it('decodes a large double written in exponent form', () => {
    for (const x of ['1.8e16', '1e300', '-1.8E+16']) {
      const text = `{"observation": ${x}, "evidence_anchors": [], "confidence": 1}`;
      expect(decodeCapabilityOutput('observe', text)['observation']).toBe(Number(x));
    }
  });

  it('refuses to encode a double it would write as an integer literal beyond 2^53', () => {
    // JSON.stringify(1.8e16) is "18000000000000000", which a consumer reads
    // as an integer it cannot hold; Python writes 1.8e+16 instead.
    expect(() => encodeCapabilityOutput('observe', { ...GOOD, observation: 1.8e16 })).toThrow(/outside ±2\^53/);
    expect(encodeCapabilityOutput('observe', { ...GOOD, observation: 1e21 })).toContain('1e+21');
  });
});

