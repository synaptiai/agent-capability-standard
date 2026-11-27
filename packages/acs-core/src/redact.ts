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
 * ({@link encodedForms}: JSON-escaped, once or twice, as JavaScript and
 * Python write it and as encoders that keep JSON safe inside HTML write it,
 * and percent-encoded);
 * then what the default patterns recognise. In a JSON value, a number whose
 * JSON text holds a registered value (a PIN, an account or card number given
 * as a number) is replaced whole, as the JSON text's redaction would replace
 * it.
 * The patterns are those of the Python redactor,
 * `grounded_agency/state/redaction.py`, and
 * `tests/conformance/secrets/redact.json` pins both: `Authorization` and
 * `Proxy-Authorization` header values (after a `Bearer`, `Basic`, `Token`,
 * `Digest` or `Negotiate` scheme, the credential; after any other first word,
 * such as `ApiKey`, `SSWS` or `Bot`, or a credential with no scheme, that
 * word and the one after it on its line; a quoted value, or a header line
 * quoted whole, `-H "Authorization: ..."`, read to its closing quote),
 * `Cookie` and `Set-Cookie` header values whole (a header line to the end
 * of its line, a header line quoted whole or a quoted member to its closing
 * quote, an unquoted member to a blank, `,` or `;`), curl's cookie option
 * given a cookie (`-b 'sid=...'`, `--cookie sid=...`: a name and `=` within
 * its first 64 characters), `Bearer` tokens, a URL's userinfo
 * password (the user's name empty or not: `redis://:<secret>@`, the slashes
 * escaped or not: `mysql:\/\/...`, as PHP writes a URL in JSON), a `.netrc`
 * entry's password, an assignment to a credential name (`password`,
 * `passphrase`, `token`, `secret_key`, `api_key`, `account_key`,
 * `hmac_key`, `credential`, ..., alone or ending a longer name, with `=` or
 * `:`, or `=` as its JSON escape `\u003d`) of four
 * characters or more, a command's user option (`curl -u user:<secret>`,
 * `--user`, `-U`, `--proxy-user`) and an option named for a credential
 * with its value after blanks (`--password <secret>`, not another option),
 * also as a list's items (`['-u', 'user:<secret>']`), PEM and OpenPGP
 * private key bodies (after a header with no end, an excerpt, the rest of the
 * text), AWS access key ids, GitHub and Slack tokens, `sk-` keys, JWTs,
 * service tokens by their prefix (Stripe's `sk_live_` and `rk_live_`,
 * Google's `AIza`, GitLab's `glpat-`, npm's `npm_`, Vault's `hvs.`,
 * SendGrid's `SG.`, a Slack webhook's path), each starting where the
 * character before it is not an ASCII letter or digit (so after `_`, as in
 * an MCP tool's name, `mcp__srv__ghp_...`, but not glued after a letter or
 * digit), a signed URL's signature (an `X-Amz-Signature`,
 * `X-Goog-Signature`, `sig` or `Signature` query parameter's value of 16
 * or more characters, after `?` or `&`, percent-encoded or as their JSON
 * escapes),
 * and a header or credential given as a name/value pair or a `[name, value]`
 * tuple in JSON or code text (`"name": "Authorization", "value": "Basic
 * ..."`, `('Cookie', 'sid=...')`); quotes around a name and a value may be
 * escaped (`{\"password\": \"...\"}`, JSON text inside a JSON string), or
 * written as their code point's JSON escape (`\u0022`, as .NET writes JSON
 * text inside a JSON string), and a token may start right after one.
 * A quoted value (of an assignment, an option, a user option's password, a
 * pair or a tuple) is read to its closing quote on its line, whitespace and
 * all (`"passphrase": "correct horse battery staple"`, a `Cookie` header's
 * later cookies), and an unquoted one (or one whose quote does not close on
 * its line) to a blank or a quote (or `,` or `;` in a pair or tuple, and
 * `&`, `,` or `;` in an assignment).
 * Not read: a password given to a short option with no name attached
 * (`mysql -p<secret>`), npm's `_auth=` and a Docker configuration's `auth`
 * member, a name ending in `_pass`, other vendors' token formats, and a
 * secret in base64 or another encoding than these, unless it is registered
 * in that form too. In a JSON value, a member
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
 * value]` list (Node's `rawHeaders`); a `Cookie:` header line in text is
 * read by the header rule above. A
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
 * `holds_credential` does (and the plugin's `hooks/secret_scan.sh`, except
 * that it reads `sk-` anywhere and reads no signed URL's signature): a
 * registered value (in a string, a member name or a number's JSON text), key
 * and token formats (PEM and OpenPGP private keys, AWS, GitHub,
 * Slack, `sk-` keys, JWTs, a bearer token of 20 or more characters; the
 * longer prefixes anywhere, glued after a letter or digit too, and `sk-`
 * only where a token starts, since its two letters end words such as `task`
 * and `risk`), a signed URL's signature as above, the
 * password of a URL's userinfo unless it is a placeholder, an
 * `Authorization` or `Proxy-Authorization` header's value of 8 or more token
 * characters mixing letters and digits, with no scheme or after any scheme
 * (`ApiKey`, `SSWS`, ...), a command's user option's password
 * of 8 or more characters mixing letters and digits (`curl -u
 * admin:<value>`; `docker run -u 1000:1000` passes), and an assignment to a
 * credential name, or a credential option's value, that is quoted with no
 * whitespace and 8 or more characters, or unquoted, 12 or more characters,
 * mixing letters and digits (quotes escaped or not), and such a
 * header's value of 8 or more token characters mixing letters and digits,
 * after any scheme or none, given as a pair or tuple in text, a cookie
 * (`name=value`, a Set-Cookie attribute aside) in a `Cookie` or
 * `Set-Cookie` header's value or curl's cookie option's whose value is 8 or
 * more token characters mixing letters and digits, and a `.netrc` entry's
 * password of 8 or more characters mixing letters and digits; prose such as
 * `token: rotate monthly` passes. It reads a text with the JSON escapes
 * other encoders write for the characters it reads decoded
 * ({@link ESCAPED}). `tests/conformance/secrets/credentials.json`
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
  'password|passwd|passphrase|pwd|secret|secret[_-]?key|token|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key' +
  '|account[_-]?key|signing[_-]?key|encryption[_-]?key|hmac[_-]?key|master[_-]?key|credential';
const WS = '[ \\t\\n\\r\\f\\v]';
const NOT_WS = ' \\t\\n\\r\\f\\v';
/** One character (code point) of a class: a unit that is not a surrogate, or a surrogate pair. */
const char = (excluded: string): string => `(?:[^${excluded}\\uD800-\\uDFFF]|[\\uD800-\\uDBFF][\\uDC00-\\uDFFF])`;

/**
 * Where a word may start: after a character outside `chars` (a character
 * class's contents), or after a quote's JSON escape (`\u0022sk-...`), whose
 * last character is a digit.
 */
const after = (chars: string): string => `(?:(?<![${chars}])|(?<=\\\\u00(?:22|27)))`;

/**
 * A URL's scheme: a run of scheme characters that holds a letter, read from
 * the run's start (not after a scheme character), so a long run that is not
 * followed by `://` is read once, not again from each letter in it.
 */
const SCHEME = `${after('A-Za-z0-9+.-')}[0-9+.-]*[A-Za-z][A-Za-z0-9+.-]*`;

/**
 * A quote as JSON or code text writes it, or escaped (`\"`, as JSON text
 * inside a JSON string writes it, or escaped again: `\\\"`), or as the JSON
 * escape of its code point (`\u0022`, `\u0027`, as .NET's encoder writes a
 * quote inside a JSON string).
 */
const QUOTE = `(?:\\\\*["']|\\\\+u00(?:22|27))`;

/** The JSON escape of each quote's code point. */
const QUOTE_CODES: { readonly [quote: string]: string } = { '"': 'u0022', "'": 'u0027' };

/** What separates a name from its value: `:` or `=`, or `=` as its JSON escape (`\u003d`, as Gson writes it). */
const SEP = '(?:[:=]|\\\\+u003[dD])';

/**
 * A run of blanks, read whole: a value after it starts after the run, so a
 * value that may hold blanks is not read again from each blank of the run.
 */
const BLANKS = `${WS}*(?!${WS})`;

/**
 * One character (code point) of a value: not whitespace, a quote, a
 * backslash or one of `excluded`, or a run of backslashes that no quote
 * follows (an escaped quote, or a quote's JSON escape, ends the value, as a
 * quote does).
 */
const valueChar = (excluded = ''): string =>
  `(?:${char(`${NOT_WS}"'\\\\${excluded}`)}|\\\\+(?![\\\\"']|u00(?:22|27)))`;

/** `quote` as a value's opening quote: as written, escaped, or as its JSON escape (`\u0022`). */
const openQuote = (quote: string): string => `(?:\\\\*${quote}|\\\\+${QUOTE_CODES[quote]})`;

/**
 * A value in `quote` quotes, whitespace and all, of four characters or more,
 * read to its closing quote on its line (escaped or not, or its JSON
 * escape), so a quoted passphrase is replaced whole. A character (code point)
 * is not that quote, a backslash or a line break, or is a run of backslashes
 * that no such quote follows (read once). With no closing quote on the line
 * nothing matches, and the value is read as an unquoted one is.
 */
const quotedValue = (quote: string): string => {
  const code = QUOTE_CODES[quote] ?? '';
  return (
    `(?<secret>(?:${char(`${quote}\\\\\\n\\r`)}|\\\\+(?![\\\\${quote}]|${code})){4,})` +
    `(?=\\\\*${quote}|\\\\+${code})`
  );
};

/**
 * A secret member's name (see {@link SECRET_MEMBER}), quoted as JSON or code
 * text quotes it, the opening quote as written or as its JSON escape (read
 * after the escape's backslash). A name holds no backslash, so an attempt
 * reads to the next quote, backslash or blank.
 */
const QUOTED_SECRET_NAME =
  `(?:["']|(?<=\\\\)u00(?:22|27))[^${NOT_WS}"'\\\\]*(?:${NAMES}|authorization|cookies?)${QUOTE}`;

/**
 * The header schemes a redacted value keeps in view: what follows one is the
 * credential. Any other first word may be the credential itself.
 */
const SCHEMES = '(?:bearer|basic|token|digest|negotiate)';

/** A header's scheme, which the value after it may start with (the blanks after it read whole). */
const VALUE_SCHEME = `(?:${SCHEMES}${WS}+(?!${WS}))?`;

/**
 * Any header scheme (`ApiKey`, `SSWS`, `Bot`, `AWS4-HMAC-SHA256`): a word and
 * the spaces after it (RFC 9110 puts one or more there), before the
 * credential; hooks/secret_scan.sh reads the same.
 */
const ANY_SCHEME = '[A-Za-z][A-Za-z0-9._-]* +';

/**
 * An Authorization or Proxy-Authorization header, up to its value (a JSON
 * member's or a code's quote before the separator, and blanks).
 */
const AUTHORIZATION = `${after('A-Za-z0-9')}(?:proxy-)?authorization(?:${QUOTE})?${WS}*${SEP}${WS}*`;

/** A Cookie or Set-Cookie header, up to its value, as the Authorization header above. */
const COOKIE = `(?:set-)?cookie(?:${QUOTE})?${WS}*${SEP}${WS}*`;

/**
 * A character of a header line's value, which may hold blanks (`a=1;
 * sid=...`): not a line break, a quote or a backslash, or a run of
 * backslashes that no quote follows.
 */
const LINE_CHAR = `(?:${char(`\\n\\r"'\\\\`)}|\\\\+(?![\\\\"']|u00(?:22|27)))`;

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
const PAIR_HEAD = `${QUOTED_SECRET_NAME}${WS}*,${WS}*(?:${QUOTE})?value(?:${QUOTE})?${WS}*${SEP}${WS}*`;
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
 * The user's name is read for at most 256 characters: an attempt starts at
 * each `-u` after a character that is not a name's, and a run such as
 * `.-u.-u.-u...` holds one at each of its positions, so an unbounded name
 * was read again from each to the run's end.
 */
const USER_OPTION =
  `${after('A-Za-z0-9_-')}(?:-[uU]${OPTION_SEPARATOR}?|--(?:proxy-)?user${OPTION_SEPARATOR})` +
  `[^${NOT_WS}:"'\\\\]{0,256}:`;
/** ... and the same option up to the quote its value opens with. */
const USER_OPTION_QUOTE_SEPARATOR = `(?:${WS}+|=|(?:${QUOTE})?${WS}*,${WS}*)`;
const USER_OPTION_NAME =
  `${after('A-Za-z0-9_-')}(?:-[uU]${USER_OPTION_QUOTE_SEPARATOR}?|--(?:proxy-)?user` +
  `${USER_OPTION_QUOTE_SEPARATOR})`;

/**
 * A command's option named for a credential (`--password`, `--api-key`,
 * `--db-token`), and what separates it from a value given after blanks or
 * as a list's next item; `--password=...` is an assignment.
 */
const CREDENTIAL_OPTION_NAME = `${after('A-Za-z0-9_-')}--(?:[A-Za-z0-9]+[_-])*(?:${NAMES})`;
const CREDENTIAL_OPTION_SEPARATOR = `(?:${WS}+|(?:${QUOTE})?${WS}*,${WS}*)`;
/** ... up to its value, which is not another option. */
const CREDENTIAL_OPTION = `${CREDENTIAL_OPTION_NAME}(?:${WS}+(?:${QUOTE})?|(?:${QUOTE})?${WS}*,${WS}*${QUOTE})(?!-)`;

/** An assignment to a credential name, up to its value. */
const ASSIGN = `(?:${NAMES})(?:${QUOTE})?${WS}*${SEP}${WS}*`;

/**
 * curl's cookie option (`-b`, `--cookie`), up to the quote its value opens
 * with, and up to its value, quoted or not, as the user option's.
 */
const COOKIE_OPTION_NAME =
  `${after('A-Za-z0-9_-')}(?:-b${USER_OPTION_QUOTE_SEPARATOR}?|--cookie${USER_OPTION_QUOTE_SEPARATOR})`;
const COOKIE_OPTION = `${after('A-Za-z0-9_-')}(?:-b${OPTION_SEPARATOR}?|--cookie${OPTION_SEPARATOR})`;

/**
 * A .netrc entry's password (`machine <host> login <user> password
 * <secret>`, `default password <secret>`), up to its value: a netrc keyword,
 * at most one word, `password` and blanks.
 */
const NETRC = `${after('A-Za-z0-9_-')}(?:machine|login|account|default)${WS}+(?:[^${NOT_WS}]+${WS}+)?password${WS}+`;

/**
 * Where a prefix-shaped token starts: after a character that is not an ASCII
 * letter or digit (so after `_`, `-`, `.`, `/`, `:` or a quote: a token in an
 * MCP tool's name, `mcp__srv__ghp_...`, is read), or after a quote's JSON
 * escape. A token glued after a letter or digit (`xghp_...`) is not read
 * here; the refusal rule ({@link CREDENTIAL_SHAPES}) still refuses it.
 */
const WORD = after('A-Za-z0-9');

/**
 * A signed URL's signature: the value of an `X-Amz-Signature` (S3 SigV4),
 * `X-Goog-Signature` (Cloud Storage), `sig` (Azure SAS) or `Signature` (S3
 * SigV2, CloudFront) query parameter, read only after `?` or `&` (as
 * themselves, percent-encoded or as their JSON escapes), so prose such as
 * `signature=` is not read. The value is 16 or more characters; it stops at
 * `&` and `?` in any of those forms, so no run is read again from each of its
 * positions.
 */
const SIGNED_URL_PARAMETER =
  '(?:[?&]|%3F|%26|\\\\u00(?:3F|26))(?:x-amz-signature|x-goog-signature|sig|signature)(?:=|%3D|\\\\u003D)';
const SIGNATURE_VALUE = '(?:[A-Za-z0-9._~+/=-]|%(?!26|3F)[0-9A-F]{2}){16,}';

/**
 * The patterns of a value after `prefix` in double or single quotes (escaped
 * or not, or as their JSON escapes), `afterQuote` read first: the value is
 * read to its closing quote, whitespace and all (see {@link quotedValue}).
 */
const quotedForms = (prefix: string, afterQuote = '', flags = 'dgi'): RegExp[] =>
  ['"', "'"].map((quote) => new RegExp(`${prefix}${openQuote(quote)}${afterQuote}${quotedValue(quote)}`, flags));

/**
 * The default patterns; each marks the secret with the group `secret` (a
 * match in which it takes no part replaces nothing). Each reads a text in
 * time in proportion to its length: no run of characters is read again from
 * each of its positions (test/redact.test.ts times them on 1 MB).
 */
export const DEFAULT_PATTERNS: readonly RegExp[] = [
  // PEM private key blocks and OpenPGP private key blocks (`PRIVATE KEY
  // BLOCK`): the body, to the first end line. A header with no end after it
  // (an excerpt, a truncated line) keeps its body: the rest of the text is
  // replaced, so the next header is not read again to the end of the text
  // either.
  /-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----(?<secret>[\s\S]+?)(?:-----END (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----|$)/dg,
  // Authorization and Proxy-Authorization header values: a quoted value
  // (`"Authorization": "..."`) read to its closing quote, whitespace and all,
  // after one of the five schemes ...
  ...quotedForms(AUTHORIZATION, VALUE_SCHEME),
  // ... and a header line quoted whole (`-H "Authorization: ..."`, its quotes
  // escaped or not) read to its closing quote, the same way; an attempt
  // starts at the start of a run of backslashes, so a run is read once, and
  // the blanks after the colon are read whole, so the value is not read
  // again from each of them ...
  ...quotedForms('(?<!\\\\)', `(?:proxy-)?authorization${WS}*:${BLANKS}${VALUE_SCHEME}`),
  // ... or, unquoted: after any other first word (a scheme such as `ApiKey`,
  // `SSWS` or `Bot`, or a credential with no scheme), that word and the one
  // after it on its line, so the credential is replaced whether or not the
  // word was a scheme ...
  new RegExp(
    `${AUTHORIZATION}(?:${QUOTE})?(?!${SCHEMES}${WS})` +
      `(?<secret>${valueChar(',;')}+(?:[ \\t]+${valueChar(',;')}+)?)`,
    'dgi',
  ),
  // ... and after one of the five schemes, the credential.
  new RegExp(`${AUTHORIZATION}(?:${QUOTE})?(?:${SCHEMES}${WS}+)?(?<secret>${valueChar(',;')}+)`, 'dgi'),
  // A header or credential given as a name/value pair or a [name, value]
  // tuple in text: its value, of four characters or more, read to its
  // closing quote (`"Cookie", "theme=dark; sid=..."`) ...
  ...quotedForms(`(?:${TUPLE_HEAD}|${PAIR_HEAD})`, VALUE_SCHEME),
  // ... or, with no closing quote on its line, to a blank, `,` or `;`.
  new RegExp(`(?:${TUPLE_TEXT}|${PAIR_TEXT})(?<secret>${valueChar(',;')}{4,})`, 'dgi'),
  // Cookie and Set-Cookie header values: a quoted value (`"Cookie": "..."`,
  // `{'Cookie': '...'}`) read to its closing quote, whitespace and all ...
  ...quotedForms(COOKIE),
  // ... a header line quoted whole (`-H 'Cookie: ...'`) read to its closing
  // quote, the same way ...
  ...quotedForms('(?<!\\\\)', `(?:set-)?cookie${WS}*:${BLANKS}`),
  // ... a header line, from its first character that is not a blank to the
  // end of its line (a cookie string holds blanks: `a=1; sid=...`; a
  // Set-Cookie line's attributes go with it) ...
  new RegExp(`(?:set-)?cookie${WS}*:${WS}*(?<secret>${valueChar()}${LINE_CHAR}{3,})`, 'dgi'),
  // ... or, after `=` or a quote that does not close on its line, to a
  // blank, `,` or `;`.
  new RegExp(`${COOKIE}(?:${QUOTE})?(?<secret>${valueChar(',;')}{4,})`, 'dgi'),
  // curl's cookie option given a cookie string (`-b 'sid=...'`, `--cookie
  // sid=...`, not a cookie file's name: a name and `=` within its first 64
  // characters), quoted ...
  ...quotedForms(COOKIE_OPTION_NAME, `(?=[^\\n\\r"'\\\\=]{0,64}=)`, 'dg'),
  // ... or not.
  new RegExp(`${COOKIE_OPTION}(?=[^${NOT_WS}"'\\\\=]{0,64}=)(?<secret>${valueChar()}{4,})`, 'dg'),
  // Bearer tokens.
  new RegExp(`${after('A-Za-z0-9')}bearer${WS}+(?<secret>[A-Za-z0-9._~+/=-]{8,})`, 'dgi'),
  // The password of a URL's userinfo, the user's name empty or not
  // (`redis://:<secret>@`), its slashes escaped or not (`mysql:\/\/...`, as
  // PHP's json_encode writes a URL).
  new RegExp(`${SCHEME}:(?:\\\\*/){2}[^${NOT_WS}/:@]*:(?<secret>[^${NOT_WS}/@]+)@`, 'dg'),
  // A .netrc entry's password (`machine <host> login <user> password <secret>`).
  new RegExp(`${NETRC}(?<secret>${valueChar()}{4,})`, 'dg'),
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
  new RegExp(`${WORD}(?<secret>(?:AKIA|ASIA)[A-Z0-9]{16})\\b`, 'dg'),
  // GitHub tokens.
  new RegExp(`${WORD}(?<secret>gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})`, 'dg'),
  // Slack tokens.
  new RegExp(`${WORD}(?<secret>xox[abprs]-[A-Za-z0-9-]{10,})`, 'dg'),
  // sk- keys.
  new RegExp(`${WORD}(?<secret>sk-[A-Za-z0-9_-]{20,})`, 'dg'),
  // Service tokens by their prefix: Stripe's secret and restricted keys,
  // Google API keys, GitLab personal access tokens, npm tokens, Vault tokens
  // and SendGrid keys ...
  new RegExp(
    `${WORD}(?<secret>[rs]k_(?:live|test)_[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_-]{35}` +
      '|glpat-[0-9A-Za-z_-]{20,}|npm_[A-Za-z0-9]{36}|hv[sbr]\\.[A-Za-z0-9_-]{24,}' +
      '|SG\\.[A-Za-z0-9_-]{16,}\\.[A-Za-z0-9_-]{16,})',
    'dg',
  ),
  // A signed URL's signature.
  new RegExp(`${SIGNED_URL_PARAMETER}(?<secret>${SIGNATURE_VALUE})`, 'dgi'),
  // ... and a Slack webhook's path.
  /hooks\.slack\.com\/services\/(?<secret>T[A-Za-z0-9]+\/B[A-Za-z0-9]+\/[A-Za-z0-9]{16,})/dg,
  // JWTs: three base64url parts, the first a JSON object's encoding,
  // starting where a prefix-shaped token starts (WORD). Read from the start
  // of a run of base64url characters to its first `eyJ` at a token start
  // (the run's start or after `_` or `-`), so a run is read once, not again
  // from each `eyJ` in it.
  new RegExp(
    `${after('A-Za-z0-9_-')}(?:(?!eyJ)(?:[A-Za-z0-9]|[_-](?!eyJ))*[_-])?` +
      '(?<secret>eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+)',
    'dg',
  ),
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
 * The characters encoders escape as `\u00XX` so that JSON is safe inside
 * HTML, and whether they write each character past ASCII as `\uXXXX` too:
 * Go's encoding/json (the JSON of kubectl, docker, gh and terraform), Gson,
 * and .NET's System.Text.Json (its quote `\u0022`, not `\"`).
 */
const HTML_SAFE: readonly (readonly [string, boolean])[] = [
  ['&<>', false],
  ["&<>='", false],
  ['&<>\'+"`', true],
];

/**
 * `value` as a JSON string's contents: `"`, `\` and control characters
 * escaped (`\n` and the other short forms, else `\u00XX`), each character
 * of `html` as `\u00XX`, and, when `asciiOnly`, each character past ASCII
 * as `\uXXXX` (a pair of them past the Basic Multilingual Plane); the hex
 * digits in upper case when `upper`.
 */
function jsonEscaped(value: string, asciiOnly: boolean, html = '', upper = false): string {
  const hex = (n: number): string => (upper ? hex4(n).toUpperCase() : hex4(n));
  let out = '';
  for (const ch of value) {
    const cp = ch.codePointAt(0) ?? 0;
    const short = JSON_SHORT_ESCAPES[ch];
    if (html.includes(ch)) out += `\\u${hex(cp)}`;
    else if (short !== undefined) out += short;
    else if (cp < 0x20 || (asciiOnly && cp > 0x7f && cp <= 0xffff)) out += `\\u${hex(cp)}`;
    else if (asciiOnly && cp > 0xffff) {
      const v = cp - 0x10000;
      out += `\\u${hex(0xd800 + (v >> 10))}\\u${hex(0xdc00 + (v & 0x3ff))}`;
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
 * again, as JSON text inside a JSON string holds it); HTML-safe JSON-escaped
 * (by each encoder of {@link HTML_SAFE}, in lower-case hex, then in
 * upper-case hex, then each of those escaped again); and percent-encoded
 * (UTF-8, by each of the encodings of {@link PERCENT_ENCODINGS}, in
 * upper-case hex, then in lower-case hex). A value with a lone surrogate has
 * no UTF-8 and so no percent-encoded form. The Python redactor's
 * `encoded_forms` gives the same forms in the same order.
 */
export function encodedForms(value: string): string[] {
  const once = jsonEscaped(value, false);
  const asciiOnce = jsonEscaped(value, true);
  const html = [false, true].flatMap((upper) =>
    HTML_SAFE.map(([chars, asciiOnly]) => jsonEscaped(value, asciiOnly, chars, upper)),
  );
  const forms = [
    value,
    once,
    asciiOnce,
    once.split('/').join('\\/'),
    asciiOnce.split('/').join('\\/'),
    jsonEscaped(once, false),
    jsonEscaped(asciiOnce, false),
    ...html,
    ...html.map((form) => jsonEscaped(form, false)),
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

/** Whether `text` holds one of the registered `values` (their forms included). */
function holdsRegistered(text: string, values: readonly string[]): boolean {
  return values.some((v) => text.includes(v));
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
    // A number whose JSON text holds a registered value: replaced whole, as
    // the redaction of the JSON text would replace it.
    if (typeof v === 'number' && holdsRegistered(JSON.stringify(v), values)) {
      pointers.push(pointer);
      return MARKER;
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
// prose (grounded_agency/state/redaction.py holds the same, and
// hooks/secret_scan.sh too but for `sk-`, which it reads anywhere, and
// signed URLs, which it does not read).
const CREDENTIAL_SHAPES: readonly RegExp[] = [
  /-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----/,
  /(?:AKIA|ASIA)[0-9A-Z]{16}/,
  /gh[pousr]_[A-Za-z0-9]{36}/,
  /github_pat_[A-Za-z0-9_]{22,}/,
  /xox[abprs]-[A-Za-z0-9-]{10,}/,
  // `sk-` only where a token starts (not after an ASCII letter or digit):
  // its two letters end common words (`task-...`, `risk-...`, `disk-...`).
  // The longer prefixes above and below are read anywhere.
  /(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}/,
  new RegExp(`[Bb]earer${WS}+[A-Za-z0-9._~+/=-]{20,}`),
  // Read from the start of a run to its first `eyJ` (whose first part is
  // the longest), so a run is read once.
  /(?<![A-Za-z0-9_-])(?:(?!eyJ)[A-Za-z0-9_-])*eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/,
  // Service tokens by their prefix (Stripe, Google, GitLab, npm, Vault,
  // SendGrid) and a Slack webhook's path.
  /[rs]k_(?:live|test)_[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_-]{35}|glpat-[0-9A-Za-z_-]{20,}|npm_[A-Za-z0-9]{36}|hv[sbr]\.[A-Za-z0-9_-]{24,}|SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}|hooks\.slack\.com\/services\/T[A-Za-z0-9]+\/B[A-Za-z0-9]+\/[A-Za-z0-9]{16,}/,
  // A signed URL's signature.
  new RegExp(`${SIGNED_URL_PARAMETER}${SIGNATURE_VALUE}`, 'i'),
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
const URL_PASSWORD = new RegExp(`${SCHEME}:(?:\\\\*/){2}[^${NOT_WS}/:@]*:(?<value>[^${NOT_WS}/@]+)@`, 'g');
const PLACEHOLDER = /^(?:[$<{*[].*|password|passwd|pwd|pass|secret|token)$/i;
// An Authorization or Proxy-Authorization header's value, with no scheme or
// after one of the five: 8 or more token characters with letters and digits
// ...
const AUTHORIZATION_VALUE = new RegExp(
  `(?:proxy-)?authorization(?:${QUOTE})?${WS}*[:=]${WS}*(?:${QUOTE})?` +
    `(?:${SCHEMES}${WS}+)?(?<value>[A-Za-z0-9._~+/=-]{8,})`,
  'gi',
);
// ... or after any other scheme (`ApiKey`, `SSWS`, `Bot`, `Splunk`). Both
// readings are tried: the first word of a value may be its scheme or its
// credential.
const AUTHORIZATION_SCHEME_VALUE = new RegExp(
  `(?:proxy-)?authorization(?:${QUOTE})?${WS}*[:=]${WS}*(?:${QUOTE})?${ANY_SCHEME}(?<value>[A-Za-z0-9._~+/=-]{8,})`,
  'gi',
);
// A header's or credential's value given as a name/value pair, or as a
// tuple of exactly two (a list of names is not one), in text, after its
// scheme: 8 or more token characters with letters and digits.
const PAIR_VALUE_TEXT = new RegExp(`${PAIR_TEXT}(?<value>[A-Za-z0-9._~+/=-]{8,})`, 'gi');
const TUPLE_VALUE_TEXT = new RegExp(`${TUPLE_TEXT}(?<value>[A-Za-z0-9._~+/=-]{8,})${QUOTE}${WS}*[\\])]`, 'gi');
// ... and the same after any other scheme.
const PAIR_SCHEME_VALUE_TEXT = new RegExp(`${PAIR_HEAD}${QUOTE}${ANY_SCHEME}(?<value>[A-Za-z0-9._~+/=-]{8,})`, 'gi');
const TUPLE_SCHEME_VALUE_TEXT = new RegExp(
  `${TUPLE_HEAD}${QUOTE}${ANY_SCHEME}(?<value>[A-Za-z0-9._~+/=-]{8,})${QUOTE}${WS}*[\\])]`,
  'gi',
);

// A .netrc entry's password: 8 or more characters with letters and digits.
const NETRC_VALUE = new RegExp(`${NETRC}(?<value>[^${NOT_WS}"']{8,})`, 'g');
// A Cookie or Set-Cookie header's value, to the end of its line or its
// closing quote (a control character, a quote or a backslash ends it) ...
const COOKIE_VALUE = new RegExp(
  `(?:set-)?cookie(?:${QUOTE})?${WS}*[:=]${WS}*(?:${QUOTE})?` +
    `(?<value>${char(`${NOT_WS}"'\\\\`)}${char('\\x00-\\x1f\\x7f"\'\\\\')}*)`,
  'gi',
);
// ... and the value of curl's cookie option holding a cookie (a name and `=`
// within its first 64 characters), quoted, to its closing quote ...
const COOKIE_OPTION_QUOTED = new RegExp(
  `${COOKIE_OPTION_NAME}${QUOTE}` +
    `(?<value>${char('\\x00-\\x1f\\x7f"\'\\\\=')}{0,64}=${char('\\x00-\\x1f\\x7f"\'\\\\')}*)`,
  'g',
);
// ... or not, to a blank.
const COOKIE_OPTION_VALUE = new RegExp(
  `${COOKIE_OPTION}(?<value>${char(`${NOT_WS}"'\\\\=`)}{0,64}=${char(`${NOT_WS}"'\\\\`)}*)`,
  'g',
);
// The cookies of such a value: its pieces between `;`, `,` and blanks.
const COOKIE_PIECE = /[^;, ]+/g;
// The attributes a Set-Cookie line gives after its cookie, which are not
// cookies.
const COOKIE_ATTRIBUTE = /^(?:path|domain|expires|max-age|samesite|secure|httponly|partitioned|priority)$/i;
// A cookie's value a refusal relies on: 8 or more token characters (with
// `%`, a URL-encoded value's) with letters and digits.
const COOKIE_TOKEN = /^[A-Za-z0-9._~+/=%-]{8,}$/;
// JSON escapes some encoders write for ASCII characters the rules read: the
// HTML-safe escapes of Go's encoding/json, Gson and .NET's System.Text.Json
// (`&`, `<`, `>`, `=`, `+` and the quotes as `\u00XX`), and PHP's `\/`. The
// refusal rule reads a text with them decoded, a quote as an escaped quote
// (it stays a quote inside a JSON string).
const ESCAPED = /\\u00(?:22|27|26|2[bB]|3[cCdDeE])|\\\//g;
const UNESCAPED: { readonly [code: string]: string } = {
  '22': '\\"',
  '27': "\\'",
  '26': '&',
  '2b': '+',
  '3c': '<',
  '3d': '=',
  '3e': '>',
};

/** `text` with the JSON escapes of {@link ESCAPED} decoded, in one pass (hooks/secret_scan.sh decodes the same ones). */
function decoded(text: string): string {
  if (!text.includes('\\')) return text;
  return text.replace(ESCAPED, (m) => (m === '\\/' ? '/' : (UNESCAPED[m.slice(4).toLowerCase()] ?? m)));
}

const lettersAndDigits = (v: string): boolean => /[0-9]/.test(v) && /[A-Za-z]/.test(v);

/**
 * Whether a cookie header's or option's value holds a cookie (`name=value`,
 * a Set-Cookie attribute aside) whose value is credential-shaped
 * ({@link COOKIE_TOKEN}). A piece with no `=` is not read: prose after
 * `Cookie:` is not one.
 */
function cookieCredential(value: string): boolean {
  for (const [piece] of value.matchAll(COOKIE_PIECE)) {
    const at = piece.indexOf('=');
    if (at < 0) continue;
    const cookie = piece.slice(at + 1);
    if (!COOKIE_ATTRIBUTE.test(piece.slice(0, at)) && COOKIE_TOKEN.test(cookie) && lettersAndDigits(cookie)) {
      return true;
    }
  }
  return false;
}

/** Whether `text` holds a credential-shaped value, read with the JSON escapes of {@link ESCAPED} decoded. */
function credentialText(raw: string): boolean {
  const text = decoded(raw);
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
    AUTHORIZATION_SCHEME_VALUE,
    PAIR_VALUE_TEXT,
    TUPLE_VALUE_TEXT,
    PAIR_SCHEME_VALUE_TEXT,
    TUPLE_SCHEME_VALUE_TEXT,
    NETRC_VALUE,
  ]) {
    for (const m of text.matchAll(pattern)) {
      if (lettersAndDigits(m.groups?.['value'] ?? '')) return true;
    }
  }
  for (const pattern of [COOKIE_VALUE, COOKIE_OPTION_QUOTED, COOKIE_OPTION_VALUE]) {
    for (const m of text.matchAll(pattern)) {
      if (cookieCredential(m.groups?.['value'] ?? '')) return true;
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

/**
 * Every string in a JSON value, member names included; and, given
 * `numbers`, the JSON text of every number in it.
 */
function stringsIn(value: Json, out: string[], numbers?: string[]): void {
  if (typeof value === 'string') out.push(value);
  else if (typeof value === 'number') numbers?.push(JSON.stringify(value));
  else if (Array.isArray(value)) value.forEach((v) => stringsIn(v, out, numbers));
  else if (value !== null && typeof value === 'object') {
    for (const [k, v] of Object.entries(value)) {
      out.push(k);
      stringsIn(v, out, numbers);
    }
  }
}

/**
 * Whether `value` holds a registered secret or a credential-shaped value:
 * the rule for refusing `persist` data and `audit` records (§6.7,
 * §5.18.10). A JSON value is read string by string and as its JSON text,
 * so `{"api_key": "..."}` is an assignment, and a registered value is
 * looked for in its strings, its member names and the JSON text of its
 * numbers (`{"card": 4111111111111111}`).
 */
export function holdsCredential(value: Json, secrets: readonly string[] = []): boolean {
  const strings: string[] = [];
  const numbers: string[] = [];
  stringsIn(value, strings, numbers);
  const values = registered(secrets);
  if ([...strings, ...numbers].some((s) => holdsRegistered(s, values))) return true;
  if (strings.some(credentialText)) return true;
  if (typeof value === 'string') return false;
  // Data, not prose: what redaction replaces in a secret member.
  if (secretMemberValue(value, false)) return true;
  return credentialText(JSON.stringify(value));
}
