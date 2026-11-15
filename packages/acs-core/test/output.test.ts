/** A capability output over a text-only channel (STANDARD 1.2.0 §5.18.9). */
import { describe, expect, it } from 'vitest';
import { CapabilityOutputError, decodeCapabilityOutput, encodeCapabilityOutput } from '../src/output.js';

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
