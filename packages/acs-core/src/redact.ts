/**
 * Redaction of secrets (STANDARD v1.2.0 §6.7).
 *
 * A secret never enters a record, an evidence anchor, a notification, a
 * diagnostic, a trace or persisted data. A host that would write a value
 * holding one redacts it: each secret, or the part of a string that is one,
 * becomes the marker `[REDACTED]`. `redactJson` also returns the JSON
 * Pointers (RFC 6901) of the members it changed, which a canonical event may
 * list as `redactions` (§6.2).
 *
 * The values a host registers (`secrets`, four characters or more) are
 * replaced first, longest first; then what the default patterns recognise.
 * The patterns are those of the Python redactor,
 * `grounded_agency/state/redaction.py`, and
 * `tests/conformance/secrets/redact.json` pins both: `Authorization` and
 * `Proxy-Authorization` header values, `Bearer` tokens, a URL's userinfo
 * password, an assignment to a credential name (`password`, `token`,
 * `api_key`, ..., alone or ending a longer name) of four characters or more,
 * PEM private key bodies, AWS access key ids, GitHub and Slack tokens, `sk-`
 * keys and JWTs. In a JSON value, a string member whose name is a credential
 * name is redacted whole.
 *
 * The patterns are ASCII: no `u` flag, so `\b` and case-insensitive
 * matching are ASCII-only, as `re.ASCII` makes them in Python; whitespace is
 * spelled out, since `\s` differs between the two; and a value's length is
 * counted in characters (code points), as Python counts it.
 */
import type { Json } from './canonical.js';

/** What a redacted secret is replaced by. */
export const MARKER = '[REDACTED]';

/** Registered values shorter than this are ignored. */
export const MIN_SECRET_LENGTH = 4;

const NAMES =
  'password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key';
const WS = '[ \\t\\n\\r\\f\\v]';
const NOT_WS = ' \\t\\n\\r\\f\\v';
/** One character (code point) of a class: a unit that is not a surrogate, or a surrogate pair. */
const char = (excluded: string): string => `(?:[^${excluded}\\uD800-\\uDFFF]|[\\uD800-\\uDBFF][\\uDC00-\\uDFFF])`;

/** The default patterns; each marks the secret with the group `secret`. */
export const DEFAULT_PATTERNS: readonly RegExp[] = [
  // PEM private key blocks: the body.
  /-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----(?<secret>[\s\S]+?)-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----/dg,
  // Authorization and Proxy-Authorization header values (after a scheme).
  new RegExp(
    `(?<![A-Za-z0-9])(?:proxy-)?authorization["']?${WS}*[:=]${WS}*["']?` +
      `(?:(?:bearer|basic|token|digest|negotiate)${WS}+)?` +
      `(?<secret>[^${NOT_WS}"',;]+)`,
    'dgi',
  ),
  // Bearer tokens.
  new RegExp(`(?<![A-Za-z0-9])bearer${WS}+(?<secret>[A-Za-z0-9._~+/=-]{8,})`, 'dgi'),
  // The password of a URL's userinfo.
  new RegExp(`\\b[A-Za-z][A-Za-z0-9+.-]*://[^${NOT_WS}/:@]+:(?<secret>[^${NOT_WS}/@]+)@`, 'dg'),
  // Assignments to a credential name, in code, query strings and JSON text.
  new RegExp(
    `(?<![A-Za-z0-9])(?:${NAMES})["']?${WS}*[=:]${WS}*["']?` + `(?<secret>${char(`${NOT_WS}"'&,;`)}{4,})`,
    'dgi',
  ),
  // AWS access key ids.
  /\b(?<secret>(?:AKIA|ASIA)[A-Z0-9]{16})\b/dg,
  // GitHub tokens.
  /\b(?<secret>gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})/dg,
  // Slack tokens.
  /\b(?<secret>xox[abprs]-[A-Za-z0-9-]{10,})/dg,
  // sk- keys.
  /\b(?<secret>sk-[A-Za-z0-9_-]{20,})/dg,
  // JWTs: three base64url parts, the first a JSON object's encoding.
  /\b(?<secret>eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)/dg,
];

const SECRET_MEMBER = new RegExp(`^(?:[\\s\\S]*[_-])?(?:${NAMES})$`, 'i');

/** The registered values a redactor replaces: long enough, distinct, longest first. */
function registered(secrets: readonly string[]): string[] {
  const length = (s: string): number => [...s].length;
  const kept = [...new Set(secrets.filter((s) => length(s) >= MIN_SECRET_LENGTH))];
  // Longest first (in characters, as Python counts); a stable sort keeps
  // the order given among values of one length.
  return kept.sort((a, b) => length(b) - length(a));
}

/** `text` with each match's `secret` group replaced by the marker (a marker already there stays). */
function replaceSecrets(text: string, pattern: RegExp): string {
  const flags = [...new Set(`${pattern.flags}dg`)].join('');
  let out = '';
  let last = 0;
  for (const m of text.matchAll(new RegExp(pattern.source, flags))) {
    const span = m.indices?.groups?.['secret'];
    const secret = m.groups?.['secret'];
    if (span === undefined || secret === undefined || secret === MARKER) continue;
    out += text.slice(last, span[0]) + MARKER;
    last = span[1];
  }
  return out + text.slice(last);
}

function redactWith(text: string, values: readonly string[], patterns: readonly RegExp[]): string {
  let out = text;
  for (const v of values) out = out.split(v).join(MARKER);
  for (const p of patterns) out = replaceSecrets(out, p);
  return out;
}

/**
 * `text` with each secret replaced by {@link MARKER}: the registered
 * `secrets` (four characters or more) first, then the default patterns.
 */
export function redactText(text: string, secrets: readonly string[] = []): string {
  return redactWith(text, registered(secrets), DEFAULT_PATTERNS);
}

/** One JSON Pointer reference token (RFC 6901). */
function pointerToken(key: string): string {
  return key.replace(/~/g, '~0').replace(/\//g, '~1');
}

/**
 * A JSON value with every secret replaced, and the JSON Pointers (RFC 6901)
 * of the members changed, in document order (`""` when the value is itself
 * a string that changed). The value given is not modified.
 */
export function redactJson(value: Json, secrets: readonly string[] = []): { value: Json; pointers: string[] } {
  const values = registered(secrets);
  const pointers: string[] = [];
  const walk = (v: Json, pointer: string): Json => {
    if (typeof v === 'string') {
      const text = redactWith(v, values, DEFAULT_PATTERNS);
      if (text !== v) pointers.push(pointer);
      return text;
    }
    if (Array.isArray(v)) return v.map((item, i) => walk(item, `${pointer}/${i}`));
    if (v !== null && typeof v === 'object') {
      const out: { [key: string]: Json } = {};
      for (const [k, item] of Object.entries(v)) {
        const here = `${pointer}/${pointerToken(k)}`;
        if (
          typeof item === 'string' &&
          [...item].length >= MIN_SECRET_LENGTH &&
          item !== MARKER &&
          SECRET_MEMBER.test(k)
        ) {
          out[k] = MARKER;
          pointers.push(here);
        } else {
          out[k] = walk(item, here);
        }
      }
      return out;
    }
    return v;
  };
  return { value: walk(value, ''), pointers };
}

/** Whether {@link redactJson} would change `value`. */
export function holdsSecret(value: Json, secrets: readonly string[] = []): boolean {
  return redactJson(value, secrets).pointers.length > 0;
}
