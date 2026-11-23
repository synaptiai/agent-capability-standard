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
 * replaced first, longest first, each also in the forms text carries it in
 * ({@link encodedForms}: JSON-escaped, once or twice, and percent-encoded);
 * then what the default patterns recognise.
 * The patterns are those of the Python redactor,
 * `grounded_agency/state/redaction.py`, and
 * `tests/conformance/secrets/redact.json` pins both: `Authorization` and
 * `Proxy-Authorization` header values, `Bearer` tokens, a URL's userinfo
 * password (the user's name empty or not: `redis://:<secret>@`), an
 * assignment to a credential name (`password`, `passphrase`, `token`,
 * `secret_key`, `api_key`, ..., alone or ending a longer name) of four
 * characters or more, a command's user option (`curl -u user:<secret>`,
 * `--user`, `-U`, `--proxy-user`) and an option named for a credential
 * with its value after blanks (`--password <secret>`, not another option),
 * also as a list's items (`['-u', 'user:<secret>']`), PEM private key
 * bodies, AWS access key ids, GitHub and Slack tokens, `sk-` keys and JWTs,
 * and a header or credential given as a name/value pair or a `[name, value]`
 * tuple in JSON or code text (`"name": "Authorization", "value": "Basic
 * ..."`, `('Cookie', 'sid=...')`); quotes around a name and a value may be
 * escaped (`{\"password\": \"...\"}`, JSON text inside a JSON string).
 * A quoted value (of an assignment, an option, a user option's password, a
 * pair or a tuple) is read to its closing quote on its line, whitespace and
 * all (`"passphrase": "correct horse battery staple"`, a `Cookie` header's
 * later cookies), and an unquoted one (or one whose quote does not close on
 * its line) to a blank or a quote (or `,` or `;` in a pair or tuple, and
 * `&`, `,` or `;` in an assignment).
 * Not read: a password given to a short option with no name attached
 * (`mysql -p<secret>`), and a secret in base64 or another encoding than
 * these, unless it is registered in that form too. In a JSON value, a member
 * whose name ends in a credential name (in any case, after any prefix:
 * `accessToken`, `dbPassword`, `x-api-key`) or in `authorization`, `cookie`
 * or `cookies` (the structured `Authorization`, `Proxy-Authorization`,
 * `Cookie` and `Set-Cookie` headers, a HAR's cookies) is a secret member,
 * and so is a header given as a pair: the `value` member of an object whose
 * `name`, `key` or `header` member (in any case) is a secret member's name
 * (HAR, Postman, Kubernetes `env`), and the second element of a two-element
 * array whose first is one (`[["Authorization", "Basic ..."]]`). A secret
 * member's value is redacted whole when it is a string of four characters or
 * more or a number, and when it is an array or an object, each such string
 * and number in it is. Booleans and null are kept. Not read as a pair: one
 * whose value comes before its name in text, a flat `[name, value, name,
 * value]` list (Node's `rawHeaders`), a `Cookie:` header line in text. A
 * member name is redacted as any
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
 * characters mixing letters and digits, a command's user option's password
 * of 8 or more characters mixing letters and digits (`curl -u
 * admin:<value>`; `docker run -u 1000:1000` passes), and an assignment to a
 * credential name, or a credential option's value, that is quoted with no
 * whitespace and 8 or more characters, or unquoted, 12 or more characters,
 * mixing letters and digits (quotes escaped or not), and such a
 * header's value of 8 or more token characters mixing letters and digits
 * given as a pair or tuple in text; prose such as `token: rotate monthly`
 * passes. `tests/conformance/secrets/credentials.json`
 * pins the rule for the three. In JSON data, which is not prose, it also
 * recognises what redaction replaces in a secret member, unless the string
 * is a placeholder: data holding a secret the host recognises is refused.
 */
import type { Json } from './canonical.js';

/** What a redacted secret is replaced by. */
export const MARKER = '[REDACTED]';

/** Registered values shorter than this are ignored. */
export const MIN_SECRET_LENGTH = 4;

const NAMES =
  'password|passwd|passphrase|pwd|secret|secret[_-]?key|token|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key';
const WS = '[ \\t\\n\\r\\f\\v]';
const NOT_WS = ' \\t\\n\\r\\f\\v';
/** One character (code point) of a class: a unit that is not a surrogate, or a surrogate pair. */
const char = (excluded: string): string => `(?:[^${excluded}\\uD800-\\uDFFF]|[\\uD800-\\uDBFF][\\uDC00-\\uDFFF])`;

/**
 * A URL's scheme: a run of scheme characters that holds a letter, read from
 * the run's start (not after a scheme character), so a long run that is not
 * followed by `://` is read once, not again from each letter in it.
 */
const SCHEME = '(?<![A-Za-z0-9+.-])[0-9+.-]*[A-Za-z][A-Za-z0-9+.-]*';

/**
 * A quote as JSON or code text writes it, or escaped (`\"`, as JSON text
 * inside a JSON string writes it, or escaped again: `\\\"`).
 */
const QUOTE = `\\\\*["']`;

/**
 * One character (code point) of a value: not whitespace, a quote, a
 * backslash or one of `excluded`, or a run of backslashes that no quote
 * follows (an escaped quote ends the value, as a quote does).
 */
const valueChar = (excluded = ''): string => `(?:${char(`${NOT_WS}"'\\\\${excluded}`)}|\\\\+(?![\\\\"']))`;

/**
 * A value in `quote` quotes, whitespace and all, of four characters or more,
 * read to its closing quote on its line (escaped or not), so a quoted
 * passphrase is replaced whole. A character (code point) is not that quote,
 * a backslash or a line break, or is a run of backslashes that no such quote
 * follows (read once). With no closing quote on the line nothing matches,
 * and the value is read as an unquoted one is.
 */
const quotedValue = (quote: string): string =>
  `(?<secret>(?:${char(`${quote}\\\\\\n\\r`)}|\\\\+(?![\\\\${quote}])){4,})(?=\\\\*${quote})`;

/** A secret member's name (see {@link SECRET_MEMBER}), quoted as JSON or code text quotes it. */
const QUOTED_SECRET_NAME = `["'][^${NOT_WS}"']*(?:${NAMES}|authorization|cookies?)${QUOTE}`;

/** A header's scheme, which the value after it may start with. */
const VALUE_SCHEME = `(?:(?:bearer|basic|token|digest|negotiate)${WS}+)?`;

/**
 * A header or credential given as a `[name, value]` tuple in JSON or code
 * text, up to its value: `["Authorization", "Basic ...`, `('Cookie', '...`.
 * Each attempt starts at a bracket and reads to the next quote or
 * whitespace, so a text is read once.
 */
const TUPLE_HEAD = `[\\[(]${WS}*\\\\*${QUOTED_SECRET_NAME}${WS}*,${WS}*`;
const TUPLE_TEXT = `${TUPLE_HEAD}${QUOTE}${VALUE_SCHEME}`;

/**
 * A header or credential given as a name/value pair in JSON or code text, up
 * to its value: `"Authorization", "value": "...`, as a HAR's `{"name": ...,
 * "value": ...}` reads. Each attempt starts at a quote.
 */
const PAIR_HEAD = `${QUOTED_SECRET_NAME}${WS}*,${WS}*(?:${QUOTE})?value(?:${QUOTE})?${WS}*[:=]${WS}*`;
const PAIR_TEXT = `${PAIR_HEAD}${QUOTE}${VALUE_SCHEME}`;

/**
 * What separates a command's option from its value: blanks, `=`, or the
 * next item of a list (`'-u', '...`, `"--token", "...`), the value quoted or
 * not.
 */
const OPTION_SEPARATOR = `(?:${WS}+(?:${QUOTE})?|=(?:${QUOTE})?|(?:${QUOTE})?${WS}*,${WS}*${QUOTE})`;

/**
 * A command's user option, up to the user's password: curl's `-u
 * user:<secret>` (also `-uuser:...`), `--user`, `--proxy-user` and `-U`.
 */
const USER_OPTION =
  `(?<![A-Za-z0-9_-])(?:-[uU]${OPTION_SEPARATOR}?|--(?:proxy-)?user${OPTION_SEPARATOR})` +
  `[^${NOT_WS}:"'\\\\]*:`;
/** ... and the same option up to the quote its value opens with. */
const USER_OPTION_QUOTE_SEPARATOR = `(?:${WS}+|=|(?:${QUOTE})?${WS}*,${WS}*)`;
const USER_OPTION_NAME =
  `(?<![A-Za-z0-9_-])(?:-[uU]${USER_OPTION_QUOTE_SEPARATOR}?|--(?:proxy-)?user` +
  `${USER_OPTION_QUOTE_SEPARATOR})`;

/**
 * A command's option named for a credential (`--password`, `--api-key`,
 * `--db-token`), and what separates it from a value given after blanks or
 * as a list's next item; `--password=...` is an assignment.
 */
const CREDENTIAL_OPTION_NAME = `(?<![A-Za-z0-9_-])--(?:[A-Za-z0-9]+[_-])*(?:${NAMES})`;
const CREDENTIAL_OPTION_SEPARATOR = `(?:${WS}+|(?:${QUOTE})?${WS}*,${WS}*)`;
/** ... up to its value, which is not another option. */
const CREDENTIAL_OPTION = `${CREDENTIAL_OPTION_NAME}(?:${WS}+(?:${QUOTE})?|(?:${QUOTE})?${WS}*,${WS}*${QUOTE})(?!-)`;

/** An assignment to a credential name, up to its value. */
const ASSIGN = `(?:${NAMES})(?:${QUOTE})?${WS}*[:=]${WS}*`;

/**
 * The patterns of a value after `prefix` in double or single quotes (escaped
 * or not), `afterQuote` read first: the value is read to its closing quote,
 * whitespace and all (see {@link quotedValue}).
 */
const quotedForms = (prefix: string, afterQuote = '', flags = 'dgi'): RegExp[] =>
  ['"', "'"].map((quote) => new RegExp(`${prefix}\\\\*${quote}${afterQuote}${quotedValue(quote)}`, flags));

/**
 * The default patterns; each marks the secret with the group `secret` (a
 * match in which it takes no part replaces nothing). Each reads a text in
 * time in proportion to its length: no run of characters is read again from
 * each of its positions (test/redact.test.ts times them on 1 MB).
 */
export const DEFAULT_PATTERNS: readonly RegExp[] = [
  // PEM private key blocks: the body. A header with no end after it matches
  // the rest of the text with no secret (nothing is replaced), so the next
  // header is not read again to the end of the text.
  /-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----(?:(?<secret>[\s\S]+?)-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----|[\s\S]*)/dg,
  // Authorization and Proxy-Authorization header values (after a scheme).
  new RegExp(
    `(?<![A-Za-z0-9])(?:proxy-)?authorization(?:${QUOTE})?${WS}*[:=]${WS}*(?:${QUOTE})?` +
      `(?:(?:bearer|basic|token|digest|negotiate)${WS}+)?` +
      `(?<secret>${valueChar(',;')}+)`,
    'dgi',
  ),
  // A header or credential given as a name/value pair or a [name, value]
  // tuple in text: its value, of four characters or more, read to its
  // closing quote (`"Cookie", "theme=dark; sid=..."`) ...
  ...quotedForms(`(?:${TUPLE_HEAD}|${PAIR_HEAD})`, VALUE_SCHEME),
  // ... or, with no closing quote on its line, to a blank, `,` or `;`.
  new RegExp(`(?:${TUPLE_TEXT}|${PAIR_TEXT})(?<secret>${valueChar(',;')}{4,})`, 'dgi'),
  // Bearer tokens.
  new RegExp(`(?<![A-Za-z0-9])bearer${WS}+(?<secret>[A-Za-z0-9._~+/=-]{8,})`, 'dgi'),
  // The password of a URL's userinfo, the user's name empty or not
  // (`redis://:<secret>@`).
  new RegExp(`${SCHEME}://[^${NOT_WS}/:@]*:(?<secret>[^${NOT_WS}/@]+)@`, 'dg'),
  // Assignments to a credential name, alone or at the end of a longer name
  // (DB_PASSWORD, PGPASSWORD), in code, query strings and JSON text, its
  // quotes escaped or not (`{\"password\": \"...\"}`): a quoted value
  // read to its closing quote (`"passphrase": "correct horse ..."`) ...
  ...quotedForms(ASSIGN),
  // ... or an unquoted one (or one with no closing quote on its line) to a
  // blank, a quote, `&`, `,` or `;`.
  new RegExp(`${ASSIGN}(?:${QUOTE})?(?<secret>${valueChar('&,;')}{4,})`, 'dgi'),
  // A command's user option: the password (`curl -u user:<secret>`), read to
  // its closing quote when the option's value is quoted ...
  ...quotedForms(USER_OPTION_NAME, `[^${NOT_WS}:"'\\\\]*:`, 'dg'),
  // ... or to a blank or a quote.
  new RegExp(`${USER_OPTION}(?<secret>${valueChar()}{4,})`, 'dg'),
  // A command's option named for a credential, its value after blanks
  // (`--password <secret>`, `--api-key <secret>`), quoted ...
  ...quotedForms(`${CREDENTIAL_OPTION_NAME}${CREDENTIAL_OPTION_SEPARATOR}`, '(?!-)'),
  // ... or not.
  new RegExp(`${CREDENTIAL_OPTION}(?<secret>${valueChar()}{4,})`, 'dgi'),
  // AWS access key ids.
  /\b(?<secret>(?:AKIA|ASIA)[A-Z0-9]{16})\b/dg,
  // GitHub tokens.
  /\b(?<secret>gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})/dg,
  // Slack tokens.
  /\b(?<secret>xox[abprs]-[A-Za-z0-9-]{10,})/dg,
  // sk- keys.
  /\b(?<secret>sk-[A-Za-z0-9_-]{20,})/dg,
  // JWTs: three base64url parts, the first a JSON object's encoding,
  // starting at a word boundary. Read from the start of a run of base64url
  // characters to its first `eyJ` at a word boundary (the run's start or
  // after `-`), so a run is read once, not again from each `eyJ` in it.
  /(?<![A-Za-z0-9_-])(?:(?!eyJ)(?:[A-Za-z0-9_]|-(?!eyJ))*-)?(?<secret>eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)/dg,
];

/** A member name that ends in a credential name, or names a header that carries one (or a HAR's cookies). */
const SECRET_MEMBER = new RegExp(`^[\\s\\S]*(?:${NAMES}|authorization|cookies?)$`, 'i');

/** The member of a name/value pair that holds its name (HAR `name`, Postman `key`), and the one that holds its value. */
const PAIR_NAME = /^(?:name|key|header)$/i;
const PAIR_VALUE = /^value$/i;

/**
 * Whether an object is a header or credential given as a name/value pair:
 * a `name`, `key` or `header` member holds a secret member's name, so its
 * `value` member is a secret member.
 */
function secretPair(value: { readonly [key: string]: Json }): boolean {
  return Object.entries(value).some(([k, v]) => PAIR_NAME.test(k) && typeof v === 'string' && SECRET_MEMBER.test(v));
}

/** Whether an array is a `[name, value]` tuple whose name is a secret member's: its second element is secret. */
function secretTuple(value: readonly Json[]): boolean {
  return value.length === 2 && typeof value[0] === 'string' && SECRET_MEMBER.test(value[0]);
}

/**
 * Whether a value in a secret member is redacted: a string of four
 * characters or more other than the marker, or a number.
 */
function secretScalar(value: Json): boolean {
  if (typeof value === 'string') return [...value].length >= MIN_SECRET_LENGTH && value !== MARKER;
  return typeof value === 'number';
}

const JSON_SHORT_ESCAPES: { readonly [ch: string]: string } = {
  '"': '\\"',
  '\\': '\\\\',
  '\b': '\\b',
  '\f': '\\f',
  '\n': '\\n',
  '\r': '\\r',
  '\t': '\\t',
};
const ALPHANUMERIC = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
/**
 * What each percent-encoding leaves as it is, and whether it writes a space
 * as `+`: RFC 3986's unreserved characters (a URL component), and `/` too (a
 * path), and `!*'()` too (`encodeURIComponent`); a form's body (Python's
 * `quote_plus`, the WHATWG URL Standard's urlencoded serializer).
 */
const PERCENT_ENCODINGS: readonly (readonly [string, boolean])[] = [
  [`${ALPHANUMERIC}-._~`, false],
  [`${ALPHANUMERIC}-._~/`, false],
  [`${ALPHANUMERIC}-._~!*'()`, false],
  [`${ALPHANUMERIC}-._~`, true],
  [`${ALPHANUMERIC}*-._`, true],
];
const hex4 = (n: number): string => n.toString(16).padStart(4, '0');

/**
 * `value` as a JSON string's contents: `"`, `\` and control characters
 * escaped (`\n` and the other short forms, else `\u00XX`), and, when
 * `asciiOnly`, each character past ASCII as `\uXXXX` (a pair of them past
 * the Basic Multilingual Plane).
 */
function jsonEscaped(value: string, asciiOnly: boolean): string {
  let out = '';
  for (const ch of value) {
    const cp = ch.codePointAt(0) ?? 0;
    const short = JSON_SHORT_ESCAPES[ch];
    if (short !== undefined) out += short;
    else if (cp < 0x20 || (asciiOnly && cp > 0x7f && cp <= 0xffff)) out += `\\u${hex4(cp)}`;
    else if (asciiOnly && cp > 0xffff) {
      const v = cp - 0x10000;
      out += `\\u${hex4(0xd800 + (v >> 10))}\\u${hex4(0xdc00 + (v & 0x3ff))}`;
    } else out += ch;
  }
  return out;
}

/** UTF-8 `data` percent-encoded: each byte outside `keep` as `%XX` (upper-case hex), a space as `+` when `plus`. */
function percentEncoded(data: Uint8Array, keep: string, plus: boolean): string {
  let out = '';
  for (const b of data) {
    const c = String.fromCharCode(b);
    if (b < 0x80 && keep.includes(c)) out += c;
    else if (plus && c === ' ') out += '+';
    else out += `%${b.toString(16).toUpperCase().padStart(2, '0')}`;
  }
  return out;
}

/** A lone surrogate: a string that holds one has no UTF-8. */
const LONE_SURROGATE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/;

/**
 * `value` and the forms text carries it in, each once, in this order: as it
 * is; JSON-escaped (a JSON string's contents, non-ASCII as it is and as
 * `\uXXXX`, then each with `/` as `\/`, then each of the first two escaped
 * again, as JSON text inside a JSON string holds it); and percent-encoded
 * (UTF-8, by each of the encodings of {@link PERCENT_ENCODINGS}, in
 * upper-case hex, then in lower-case hex). A value with a lone surrogate has no UTF-8 and so no
 * percent-encoded form. The Python redactor's `encoded_forms` gives the
 * same forms in the same order.
 */
export function encodedForms(value: string): string[] {
  const once = jsonEscaped(value, false);
  const asciiOnce = jsonEscaped(value, true);
  const forms = [
    value,
    once,
    asciiOnce,
    once.split('/').join('\\/'),
    asciiOnce.split('/').join('\\/'),
    jsonEscaped(once, false),
    jsonEscaped(asciiOnce, false),
  ];
  if (!LONE_SURROGATE.test(value)) {
    const data = new TextEncoder().encode(value);
    const upper = PERCENT_ENCODINGS.map(([keep, plus]) => percentEncoded(data, keep, plus));
    forms.push(...upper, ...upper.map((f) => f.replace(/%[0-9A-F]{2}/g, (m) => m.toLowerCase())));
  }
  return [...new Set(forms)];
}

/**
 * The registered values a redactor replaces, each with the forms text
 * carries it in ({@link encodedForms}): long enough, distinct, longest first.
 */
function registered(secrets: readonly string[]): string[] {
  const length = (s: string): number => [...s].length;
  const kept = [...new Set(secrets.filter((s) => length(s) >= MIN_SECRET_LENGTH).flatMap(encodedForms))];
  // Longest first (in characters, as Python counts); a stable sort keeps
  // the order given among values of one length.
  return kept.sort((a, b) => length(b) - length(a));
}

/**
 * `text` with each match's `secret` group replaced by the marker (a marker
 * already there, or a match with no `secret`, stays).
 */
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
  // `secret`: `v` is within a secret member, whose strings and numbers are
  // redacted whole.
  const walk = (v: Json, pointer: string, secret: boolean): Json => {
    if (typeof v === 'string') {
      const text = redactWith(v, values, DEFAULT_PATTERNS);
      if (text !== v) pointers.push(pointer);
      return text;
    }
    if (Array.isArray(v)) {
      // A `[name, value]` tuple whose name is a secret member's.
      const tuple = !secret && secretTuple(v);
      return v.map((item, i) => {
        const here = `${pointer}/${i}`;
        const itemSecret = secret || (tuple && i === 1);
        if (itemSecret && secretScalar(item)) {
          pointers.push(here);
          return MARKER;
        }
        return walk(item, here, itemSecret);
      });
    }
    if (v !== null && typeof v === 'object') {
      // A name/value pair whose name is a secret member's.
      const pair = !secret && secretPair(v);
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
        const memberSecret = secret || SECRET_MEMBER.test(k) || (pair && PAIR_VALUE.test(k));
        if (memberSecret && secretScalar(item)) {
          out[name] = MARKER;
          if (!renamed) pointers.push(here);
        } else {
          out[name] = walk(item, here, memberSecret);
        }
      }
      return out;
    }
    return v;
  };
  return { value: walk(value, '', false), pointers };
}

/**
 * An evidence anchor (§6.5) with every secret replaced, as an evidence store
 * or a trace keeps it, and the JSON Pointers of the members changed (as
 * {@link redactJson} gives them). An anchor that held a secret keeps no
 * digest of what it cites: its `digest` and its `metadata.hash` go, and its
 * `metadata` says `digest_omitted: "secret"`. The cited content holds the
 * secret too and may be no more than it, or than it and the text the
 * redacted excerpt still shows around the marker, so a digest of it could
 * be inverted by guessing (§6.7). The Python redactor's `redact_anchor`
 * does the same. A value that is not an object is redacted as any JSON
 * value is.
 */
export function redactAnchor(anchor: Json, secrets: readonly string[] = []): { value: Json; pointers: string[] } {
  const out = redactJson(anchor, secrets);
  const value = out.value;
  if (out.pointers.length === 0 || value === null || typeof value !== 'object' || Array.isArray(value)) return out;
  const metadata = value['metadata'];
  const meta = metadata !== null && typeof metadata === 'object' && !Array.isArray(metadata) ? metadata : undefined;
  if (Object.hasOwn(value, 'digest') || (meta !== undefined && Object.hasOwn(meta, 'hash'))) {
    delete value['digest'];
    const kept: { [key: string]: Json } = { ...(meta ?? {}) };
    delete kept['hash'];
    kept['digest_omitted'] = 'secret';
    value['metadata'] = kept;
  }
  return out;
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
  // Read from the start of a run to its first `eyJ` (whose first part is
  // the longest), so a run is read once.
  /(?<![A-Za-z0-9_-])(?:(?!eyJ)[A-Za-z0-9_-])*eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/,
];
// A quoted value with no whitespace, 8 or more characters (its quotes
// escaped or not), after an assignment or a credential option.
const QUOTED_CREDENTIAL = new RegExp(
  `${ASSIGN}${QUOTE}[^${NOT_WS}"']{8,}["']` +
    `|${CREDENTIAL_OPTION_NAME}${CREDENTIAL_OPTION_SEPARATOR}${QUOTE}[^${NOT_WS}"'-][^${NOT_WS}"']{7,}["']`,
  'i',
);
// An unquoted value of 12 or more characters with letters and digits, after
// an assignment or a credential option (not another option).
const UNQUOTED_VALUE = new RegExp(`${ASSIGN}(?<value>[^${NOT_WS}"']{12,})`, 'gi');
const OPTION_VALUE = new RegExp(
  `${CREDENTIAL_OPTION_NAME}${WS}+(?<value>[^${NOT_WS}"'-][^${NOT_WS}"']{11,})`,
  'gi',
);
// A command's user option's password (`curl -u user:<value>`): 8 or more
// characters with letters and digits.
const USER_OPTION_VALUE = new RegExp(`${USER_OPTION}(?<value>[^${NOT_WS}"'\\\\]{8,})`, 'g');
// The password of a URL's userinfo (`scheme://user:<value>@`, the user's
// name empty or not), unless it is a placeholder (`password`, `<password>`,
// `${DB_PASSWORD}`, `****`).
const URL_PASSWORD = new RegExp(`${SCHEME}://[^${NOT_WS}/:@]*:(?<value>[^${NOT_WS}/@]+)@`, 'g');
const PLACEHOLDER = /^(?:[$<{*[].*|password|passwd|pwd|pass|secret|token)$/i;
// An Authorization or Proxy-Authorization header's value, after its scheme:
// 8 or more token characters with letters and digits.
const AUTHORIZATION_VALUE = new RegExp(
  `(?:proxy-)?authorization(?:${QUOTE})?${WS}*[:=]${WS}*(?:${QUOTE})?` +
    `(?:(?:basic|bearer|token|digest|negotiate)${WS}+)?(?<value>[A-Za-z0-9._~+/=-]{8,})`,
  'gi',
);
// A header's or credential's value given as a name/value pair, or as a
// tuple of exactly two (a list of names is not one), in text, after its
// scheme: 8 or more token characters with letters and digits.
const PAIR_VALUE_TEXT = new RegExp(`${PAIR_TEXT}(?<value>[A-Za-z0-9._~+/=-]{8,})`, 'gi');
const TUPLE_VALUE_TEXT = new RegExp(`${TUPLE_TEXT}(?<value>[A-Za-z0-9._~+/=-]{8,})${QUOTE}${WS}*[\\])]`, 'gi');

const lettersAndDigits = (v: string): boolean => /[0-9]/.test(v) && /[A-Za-z]/.test(v);

function credentialText(text: string): boolean {
  if (CREDENTIAL_SHAPES.some((p) => p.test(text))) return true;
  if (QUOTED_CREDENTIAL.test(text)) return true;
  for (const m of text.matchAll(URL_PASSWORD)) {
    if (!PLACEHOLDER.test(m.groups?.['value'] ?? '')) return true;
  }
  for (const pattern of [
    UNQUOTED_VALUE,
    OPTION_VALUE,
    USER_OPTION_VALUE,
    AUTHORIZATION_VALUE,
    PAIR_VALUE_TEXT,
    TUPLE_VALUE_TEXT,
  ]) {
    for (const m of text.matchAll(pattern)) {
      if (lettersAndDigits(m.groups?.['value'] ?? '')) return true;
    }
  }
  return false;
}

/**
 * Whether JSON data holds, in a secret member, a value redaction replaces
 * that is not a placeholder.
 */
function secretMemberValue(value: Json, secret: boolean): boolean {
  if (secret && secretScalar(value)) return !(typeof value === 'string' && PLACEHOLDER.test(value));
  if (Array.isArray(value)) {
    const tuple = !secret && secretTuple(value);
    return value.some((v, i) => secretMemberValue(v, secret || (tuple && i === 1)));
  }
  if (value !== null && typeof value === 'object') {
    const pair = !secret && secretPair(value);
    return Object.entries(value).some(([k, v]) =>
      secretMemberValue(v, secret || SECRET_MEMBER.test(k) || (pair && PAIR_VALUE.test(k))),
    );
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
  if (typeof value === 'string') return false;
  // Data, not prose: what redaction replaces in a secret member.
  if (secretMemberValue(value, false)) return true;
  return credentialText(JSON.stringify(value));
}
