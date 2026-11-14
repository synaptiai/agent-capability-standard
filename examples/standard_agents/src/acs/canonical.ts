/**
 * Canonical JSON (RFC 8785, JCS) and the SHA-256 digest built on it.
 *
 * STANDARD v1.1.0 §5.14 binds an approval to "the SHA-256 digest of the
 * canonical JSON of the shown values". This module computes the same digest
 * as the reference executor (`core/src/exec/canonical.rs`), so an approval
 * recorded by a Standard Agents tool and one recorded by the executor agree
 * on what was approved. `test/canonical.test.ts` checks that against digests
 * the executor produced.
 */

/** A value that survives a JSON round trip unchanged (I-JSON, RFC 7493). */
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

/** Thrown for a value RFC 8785 cannot serialize. */
export class NotCanonicalizableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'NotCanonicalizableError';
  }
}

/** Order two strings by their UTF-16 code units (RFC 8785 §3.2.3). */
function byCodeUnits(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

/**
 * The RFC 8785 serialization of `value`: members sorted by UTF-16 code
 * units, no insignificant whitespace, strings and numbers as ECMAScript's
 * `JSON.stringify` writes them.
 */
export function canonicalize(value: unknown): string {
  if (value === null) return 'null';
  switch (typeof value) {
    case 'boolean':
      return value ? 'true' : 'false';
    case 'string':
      return JSON.stringify(value);
    case 'number':
      if (!Number.isFinite(value)) {
        throw new NotCanonicalizableError(`not a JSON number: ${value}`);
      }
      // JSON.stringify(-0) is "0", as RFC 8785 §3.2.2.3 requires.
      return JSON.stringify(value);
    case 'object': {
      if (Array.isArray(value)) {
        return `[${value.map((item) => canonicalize(item)).join(',')}]`;
      }
      const proto: unknown = Object.getPrototypeOf(value);
      if (proto !== Object.prototype && proto !== null) {
        throw new NotCanonicalizableError('not a plain JSON object');
      }
      const record = value as Record<string, unknown>;
      const members = Object.keys(record)
        .sort(byCodeUnits)
        .map((key) => `${JSON.stringify(key)}:${canonicalize(record[key])}`);
      return `{${members.join(',')}}`;
    }
    default:
      throw new NotCanonicalizableError(`not a JSON value: ${typeof value}`);
  }
}

/** SHA-256 of `text` as lowercase hex, using Web Crypto. */
export async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash), (b) => b.toString(16).padStart(2, '0')).join('');
}

/** SHA-256 (lowercase hex) of the canonical JSON of `value`. */
export async function digest(value: unknown): Promise<string> {
  return sha256Hex(canonicalize(value));
}
