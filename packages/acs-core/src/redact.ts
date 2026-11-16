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
 * keys and JWTs. In a JSON value, a string member whose name ends in a
 * credential name (in any case, after any prefix: `accessToken`,
 * `dbPassword`, `x-api-key`) or in `authorization` or `cookie` (the
 * structured `Authorization`, `Proxy-Authorization`, `Cookie` and
 * `Set-Cookie` headers) is redacted whole. A member name is redacted as any
 * string is: a name that holds a secret is replaced by its redacted text, and
 * one that would then repeat a name already in its object gets ` (2)`,
 * ` (3)`, ... so that no member is lost.
 *
 * The patterns are ASCII: no `u` flag, so `\b` and case-insensitive
 * matching are ASCII-only, as `re.ASCII` makes them in Python; whitespace is
 * spelled out, since `\s` differs between the two; and a value's length is
 * counted in characters (code points), as Python counts it.
 *
 * A refusal is another matter: `persist` data or an `audit` record that
 * holds a secret is refused, not redacted (§6.7), so {@link holdsCredential}
 * recognises only credential-shaped values, as the Python redactor's
 * `holds_credential` and the plugin's `hooks/secret_scan.sh` do: a
 * registered value, key and token formats (PEM private keys, AWS, GitHub,
 * Slack, `sk-` keys, JWTs, a bearer token of 20 or more characters), the
 * password of a URL's userinfo unless it is a placeholder, an
 * `Authorization` or `Proxy-Authorization` header's value of 8 or more token
 * characters mixing letters and digits, and an assignment to a credential
 * name whose value is quoted with no whitespace and 8 or more characters, or
 * unquoted, 12 or more characters, mixing letters and digits; prose such as
 * `token: rotate monthly` passes. `tests/conformance/secrets/credentials.json`
 * pins the rule for the three.
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

/** A member name that ends in a credential name, or names a header that carries one. */
const SECRET_MEMBER = new RegExp(`^[\\s\\S]*(?:${NAMES}|authorization|cookie)$`, 'i');

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
        let name = redactWith(k, values, DEFAULT_PATTERNS);
        const renamed = name !== k;
        if (renamed) {
          // A name that holds a secret: never repeat another.
          let unique = name;
          for (let n = 2; Object.hasOwn(out, unique) || Object.hasOwn(v, unique); n++) {
            unique = `${name} (${n})`;
          }
          name = unique;
        }
        const here = `${pointer}/${pointerToken(name)}`;
        if (renamed) pointers.push(here);
        if (
          typeof item === 'string' &&
          [...item].length >= MIN_SECRET_LENGTH &&
          item !== MARKER &&
          SECRET_MEMBER.test(k)
        ) {
          out[name] = MARKER;
          if (!renamed) pointers.push(here);
        } else {
          out[name] = walk(item, here);
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

// Credential shapes a refusal relies on: the formats of keys and tokens, no
// prose (grounded_agency/state/redaction.py and hooks/secret_scan.sh hold
// the same).
const CREDENTIAL_SHAPES: readonly RegExp[] = [
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
  /(?:AKIA|ASIA)[0-9A-Z]{16}/,
  /gh[pousr]_[A-Za-z0-9]{36}/,
  /github_pat_[A-Za-z0-9_]{22,}/,
  /xox[abprs]-[A-Za-z0-9-]{10,}/,
  /sk-[A-Za-z0-9_-]{20,}/,
  new RegExp(`[Bb]earer${WS}+[A-Za-z0-9._~+/=-]{20,}`),
  /eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/,
];
const ASSIGN = `(?:${NAMES})["']?${WS}*[:=]${WS}*`;
const QUOTED_CREDENTIAL = new RegExp(`${ASSIGN}["'][^${NOT_WS}"']{8,}["']`, 'i');
const UNQUOTED_VALUE = new RegExp(`${ASSIGN}(?<value>[^${NOT_WS}"']{12,})`, 'gi');
// The password of a URL's userinfo (`scheme://user:<value>@`), unless it is a
// placeholder (`password`, `<password>`, `${DB_PASSWORD}`, `****`).
const URL_PASSWORD = new RegExp(`[A-Za-z][A-Za-z0-9+.-]*://[^${NOT_WS}/:@]+:(?<value>[^${NOT_WS}/@]+)@`, 'g');
const PLACEHOLDER = /^(?:[$<{*[].*|password|passwd|pwd|pass|secret|token)$/i;
// An Authorization or Proxy-Authorization header's value, after its scheme:
// 8 or more token characters with letters and digits.
const AUTHORIZATION_VALUE = new RegExp(
  `(?:proxy-)?authorization["']?${WS}*[:=]${WS}*["']?` +
    `(?:(?:basic|bearer|token|digest|negotiate)${WS}+)?(?<value>[A-Za-z0-9._~+/=-]{8,})`,
  'gi',
);

const lettersAndDigits = (v: string): boolean => /[0-9]/.test(v) && /[A-Za-z]/.test(v);

function credentialText(text: string): boolean {
  if (CREDENTIAL_SHAPES.some((p) => p.test(text))) return true;
  if (QUOTED_CREDENTIAL.test(text)) return true;
  for (const m of text.matchAll(URL_PASSWORD)) {
    if (!PLACEHOLDER.test(m.groups?.['value'] ?? '')) return true;
  }
  for (const pattern of [UNQUOTED_VALUE, AUTHORIZATION_VALUE]) {
    for (const m of text.matchAll(pattern)) {
      if (lettersAndDigits(m.groups?.['value'] ?? '')) return true;
    }
  }
  return false;
}

/** Every string in a JSON value, member names included. */
function stringsIn(value: Json, out: string[]): void {
  if (typeof value === 'string') out.push(value);
  else if (Array.isArray(value)) value.forEach((v) => stringsIn(v, out));
  else if (value !== null && typeof value === 'object') {
    for (const [k, v] of Object.entries(value)) {
      out.push(k);
      stringsIn(v, out);
    }
  }
}

/**
 * Whether `value` holds a registered secret or a credential-shaped value:
 * the rule for refusing `persist` data and `audit` records (§6.7,
 * §5.18.10). A JSON value is read string by string and as its JSON text,
 * so `{"api_key": "..."}` is an assignment.
 */
export function holdsCredential(value: Json, secrets: readonly string[] = []): boolean {
  const strings: string[] = [];
  stringsIn(value, strings);
  const values = registered(secrets);
  if (strings.some((s) => values.some((v) => s.includes(v)))) return true;
  if (strings.some(credentialText)) return true;
  return typeof value !== 'string' && credentialText(JSON.stringify(value));
}
