/**
 * I-JSON (RFC 7493) within the limits the reference executor applies
 * (STANDARD 1.2.0 §5.14): numbers finite, integers within ±2^53, strings and
 * member names without a lone surrogate, plain objects and arrays only,
 * nested at most 100 levels.
 *
 * JavaScript has one number type, so "an integer beyond ±2^53" is read off
 * the text a value is sent as: `JSON.stringify` writes an integral number
 * below 1e21 as an integer literal, which a receiver reads as an integer it
 * cannot hold exactly (Python's reads it as an `int` and refuses it), and
 * from 1e21 on in exponent form, which is an ordinary double. So
 * 18000000000000000 (1.8e16) is refused and 1e300 is not. Where the value
 * was parsed from text whose integer literals were already checked, the
 * number rule is left to that check (`integers: false`).
 */

/** The largest integer magnitude with an exact I-JSON form. */
export const INT_LIMIT = 2 ** 53;

/** The deepest nesting accepted, in levels below the value itself. */
export const MAX_DEPTH = 100;

/** A high surrogate not followed by a low one, or a low one not preceded by a high one. */
export const UNPAIRED_SURROGATE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/;

export interface IJsonOptions {
  /**
   * Refuse a number `JSON.stringify` writes as an integer literal beyond
   * ±2^53 (an integral value of magnitude above 2^53 and below 1e21).
   * Default true.
   */
  integers?: boolean;
}

/** A string as it can be shown in a message: JSON escapes, no quotes. */
function shown(text: string): string {
  return JSON.stringify(text).slice(1, -1);
}

/**
 * What makes `value` not I-JSON, as a phrase that follows "the value"
 * ("holds the integer 1152921504606846976 at $.n, outside ±2^53, ..."), or
 * null when it is I-JSON. `path` names the value in the phrase.
 */
export function iJsonProblem(value: unknown, options: IJsonOptions = {}, path = '$'): string | null {
  const integers = options.integers ?? true;
  const stack: [unknown, string, number][] = [[value, path, 0]];
  while (stack.length > 0) {
    const [v, at, depth] = stack.pop()!;
    if (depth > MAX_DEPTH) return `nests deeper than ${MAX_DEPTH} levels at ${at}`;
    if (v === null || typeof v === 'boolean') continue;
    if (typeof v === 'number') {
      if (!Number.isFinite(v)) return `holds ${v} at ${at}, which is not a JSON number`;
      if (integers && Number.isInteger(v) && Math.abs(v) > INT_LIMIT && Math.abs(v) < 1e21) {
        return `holds the integer ${v} at ${at}, outside ±2^53, which has no exact I-JSON form`;
      }
    } else if (typeof v === 'bigint') {
      // What `parseJsonExact` reads an integer literal beyond ±2^53 as.
      const beyond = v > BigInt(INT_LIMIT) || v < -BigInt(INT_LIMIT);
      return beyond
        ? `holds the integer ${v} at ${at}, outside ±2^53, which has no exact I-JSON form`
        : `holds a bigint at ${at}, not JSON`;
    } else if (typeof v === 'string') {
      if (UNPAIRED_SURROGATE.test(v)) return `holds a string with a lone surrogate at ${at}`;
    } else if (Array.isArray(v)) {
      for (let i = 0; i < v.length; i += 1) {
        if (!(i in v)) return `holds an array with a hole at ${at}`;
        stack.push([v[i], `${at}[${i}]`, depth + 1]);
      }
    } else if (typeof v === 'object' && (Object.getPrototypeOf(v) === Object.prototype || Object.getPrototypeOf(v) === null)) {
      for (const [key, x] of Object.entries(v as Record<string, unknown>)) {
        if (UNPAIRED_SURROGATE.test(key)) return `holds a key with a lone surrogate at ${at}`;
        stack.push([x, `${at}.${shown(key)}`, depth + 1]);
      }
    } else {
      return `holds a ${typeof v} at ${at}, not JSON`;
    }
  }
  return null;
}

/** An integer literal: no fraction, no exponent. */
const INTEGER_LITERAL = /^-?\d+$/;

/**
 * Parse JSON text without losing what an I-JSON check must see: an integer
 * literal of magnitude above 2^53, which `JSON.parse` would round to a
 * number a check accepts (9007199254740993 to 2^53), is read as a `bigint`
 * instead, which `iJsonProblem` refuses. Every other value is what
 * `JSON.parse` reads. Read JSON text this way wherever its values are then
 * checked as I-JSON (§5.14), as a fixture runner does; a value that arrives
 * already parsed has lost the literal, and is checked as it is.
 *
 * @throws SyntaxError when `text` is not JSON, and an Error when the runtime
 *   gives a reviver no source text (`JSON.parse` source text access) and the
 *   text holds such a literal.
 */
export function parseJsonExact(text: string): unknown {
  return JSON.parse(text, function (this: unknown, _key: string, value: unknown, context?: { source?: string }) {
    if (typeof value !== 'number' || !Number.isInteger(value) || Math.abs(value) < INT_LIMIT) return value;
    const source = context?.source;
    if (source === undefined) {
      throw new Error('parseJsonExact: this runtime gives no source text to a JSON.parse reviver');
    }
    return INTEGER_LITERAL.test(source) && (BigInt(source) > BigInt(INT_LIMIT) || BigInt(source) < -BigInt(INT_LIMIT))
      ? BigInt(source)
      : value;
  });
}
