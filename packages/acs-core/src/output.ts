/**
 * A capability output over a text-only channel (STANDARD 1.2.0 §5.18.9).
 *
 * Where a host carries a capability output as a string (a tool's result, a
 * sub-prompt's or a model's reply, the string a host turns into the output
 * of an executor's capability call), it travels as the I-JSON text (RFC
 * 7493) of the output object, with nothing before or after it. A consumer
 * parses the text and checks that it is an object with every field the
 * capability's output contract requires; a producer checks the I-JSON limits
 * before it sends. Either failure is R402 EXECUTION_FAILED.
 *
 * The Python package's `encode_capability_output` and
 * `decode_capability_output` (`grounded_agency.capabilities.output`) apply
 * the same rules; both pass the shared vectors,
 * `tests/conformance/output/vectors.json`. The I-JSON limits apply to the
 * text: the decoder checks integer literals in the text itself, and the
 * encoder refuses a number it would write as an integer literal beyond
 * ±2^53 (see `ijson.ts`).
 */
import type { Json } from './canonical.js';
import { INT_LIMIT, iJsonProblem } from './ijson.js';
import { CAPABILITIES, type CapabilityId } from './ontology.js';

/** The §9.8 diagnostic of a capability output that breaks §5.18.9. */
export interface OutputDiagnostic {
  code: 'R402';
  name: 'EXECUTION_FAILED';
  severity: 'error';
  message: string;
  location: { capability: string; field?: string };
}

/** Thrown for a capability output that breaks §5.18.9 (R402). */
export class CapabilityOutputError extends Error {
  readonly code = 'R402';
  readonly diagnostic: OutputDiagnostic;

  /** `message` follows "the '<capability>' output", as in "is not a JSON object". */
  constructor(capability: string, message: string, field?: string) {
    const text = `the '${capability}' output${message.startsWith("'s ") ? '' : ' '}${message}`;
    super(`R402 EXECUTION_FAILED: ${text}`);
    this.name = 'CapabilityOutputError';
    this.diagnostic = {
      code: 'R402',
      name: 'EXECUTION_FAILED',
      severity: 'error',
      message: text,
      location: { capability, ...(field !== undefined ? { field } : {}) },
    };
  }
}

/**
 * Check `output` against the capability's output contract and the I-JSON
 * limits. `integers: false` when `output` was parsed from text whose
 * integer literals `scan` already checked: a parsed number no longer shows
 * how it was written (1.8e16 and 18000000000000000 parse the same).
 */
function checkContract(capability: CapabilityId, output: unknown, integers = true): Record<string, Json> {
  if (typeof output !== 'object' || output === null || Array.isArray(output)) {
    throw new CapabilityOutputError(capability, 'is not a JSON object');
  }
  const record = output as Record<string, unknown>;
  const required: readonly string[] = CAPABILITIES[capability].output_required;
  const missing = required.filter((field) => !Object.hasOwn(record, field));
  if (missing.length > 0) throw new CapabilityOutputError(capability, `is missing ${missing.join(', ')}`, missing[0]);
  if (Object.hasOwn(record, 'evidence_anchors') && !Array.isArray(record['evidence_anchors'])) {
    throw new CapabilityOutputError(capability, "'s evidence_anchors is not an array", 'evidence_anchors');
  }
  if (required.includes('confidence')) {
    const confidence = record['confidence'];
    if (typeof confidence !== 'number' || !(confidence >= 0 && confidence <= 1)) {
      throw new CapabilityOutputError(capability, "'s confidence is not a number from 0 to 1", 'confidence');
    }
  }
  const problem = iJsonProblem(record, { integers });
  if (problem !== null) throw new CapabilityOutputError(capability, problem);
  return record as Record<string, Json>;
}

/**
 * The text a capability output travels as on a string channel: the I-JSON
 * text of the object, nothing around it.
 *
 * @throws CapabilityOutputError (R402) if `output` is not an object, lacks a
 *   required field, or is not I-JSON: a number this text would write as an
 *   integer literal beyond ±2^53 (an integral value below 1e21, such as
 *   1.8e16) included, since a consumer would read it as an integer it
 *   cannot hold.
 */
export function encodeCapabilityOutput(capability: CapabilityId, output: unknown): string {
  return JSON.stringify(checkContract(capability, output));
}

/**
 * Scan JSON text for what `JSON.parse` lets through: a duplicate member
 * name (the last would silently win) and an integer literal beyond 2^53
 * (which would silently round). The text is already known to parse.
 */
function scan(capability: string, text: string): void {
  const objects: (Set<string> | null)[] = [];
  let expectKey = false;
  let i = 0;
  while (i < text.length) {
    const c = text[i]!;
    if (c === '"') {
      let j = i + 1;
      while (text[j] !== '"') j += text[j] === '\\' ? 2 : 1;
      const token = text.slice(i, j + 1);
      const keys = objects.at(-1);
      if (expectKey && keys) {
        const key = JSON.parse(token) as string;
        if (keys.has(key)) throw new CapabilityOutputError(capability, `has the member '${key}' twice`);
        keys.add(key);
        expectKey = false;
      }
      i = j + 1;
    } else if (c === '{') {
      objects.push(new Set());
      expectKey = true;
      i += 1;
    } else if (c === '[') {
      objects.push(null);
      i += 1;
    } else if (c === '}' || c === ']') {
      objects.pop();
      i += 1;
    } else if (c === ',') {
      expectKey = objects.at(-1) instanceof Set;
      i += 1;
    } else if (c === '-' || (c >= '0' && c <= '9')) {
      const m = /^-?\d+(\.\d+)?([eE][+-]?\d+)?/.exec(text.slice(i))!;
      if (m[1] === undefined && m[2] === undefined) {
        const digits = m[0].replace('-', '');
        if (digits.length > 16 || BigInt(digits) > BigInt(INT_LIMIT)) {
          throw new CapabilityOutputError(capability, `holds the integer ${m[0]}, outside ±2^53, which has no exact I-JSON form`);
        }
      }
      i += m[0].length;
    } else {
      i += 1;
    }
  }
}

/**
 * Read a capability output carried as a string (§5.18.9). The text must be
 * the I-JSON text of one object and nothing else: no prose, fence or second
 * value around it, no duplicate member, every field the capability's output
 * contract requires.
 *
 * @throws CapabilityOutputError (R402) otherwise. A host that answers an
 *   executor's capability call answers it with an error then.
 */
export function decodeCapabilityOutput(capability: CapabilityId, text: string): Record<string, Json> {
  if (typeof text !== 'string') throw new CapabilityOutputError(capability, `arrived as a ${typeof text}, not as text`);
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch (cause) {
    const why = cause instanceof Error ? cause.message : String(cause);
    throw new CapabilityOutputError(capability, `is not the JSON text of one object and nothing else: ${why}`);
  }
  scan(capability, text);
  return checkContract(capability, value, false);
}
