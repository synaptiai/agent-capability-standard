"""Redaction of secrets (STANDARD v1.2 §6.7).

A secret never enters a record, an evidence anchor, a notification, a
diagnostic, a trace or persisted data. An implementation that would write a
value holding one redacts it: each secret, or the part of a string that is
one, becomes the marker ``[REDACTED]``. Redaction is a transform with
documented loss (§3.2); :meth:`Redactor.redact` returns the JSON Pointers
(RFC 6901) of the members it changed, which a canonical event may list as
``redactions`` (§6.2).

A :class:`Redactor` replaces the values registered with it (the host's own
secrets, longest first), each also in the forms text carries it in
(:func:`encoded_forms`: JSON-escaped, once or twice, as Python and
JavaScript write it and as encoders that keep JSON safe inside HTML write it,
and percent-encoded),
then what its patterns recognise. In a JSON value, a number whose JSON text
holds a registered value (a PIN, an account or card number given as a
number) is replaced whole, as the JSON text's redaction would replace it.
The default
patterns (informative; ``tests/conformance/secrets/redact.json`` pins them,
and ``packages/acs-core/src/redact.ts`` holds the same ones) recognise:

- ``Authorization`` and ``Proxy-Authorization`` header values: after a
  ``Bearer``, ``Basic``, ``Token``, ``Digest`` or ``Negotiate`` scheme, the
  credential; after any other first word (``ApiKey``, ``SSWS``, ``Bot``,
  ``Splunk``, a credential with no scheme), that word and the one after it
  on its line; and a quoted value (``"Authorization": "..."``, ``-H
  "Authorization: ..."``) read to its closing quote, whitespace and all,
  after a scheme of the five;
- ``Cookie`` and ``Set-Cookie`` header values, whole: a header line to the
  end of its line (``Cookie: a=1; sid=...``), a header line quoted whole
  (``-H 'Cookie: ...'``) or a quoted member (``{"Cookie": "..."}``) to its
  closing quote, an unquoted member or one whose quote does not close on
  its line to a blank, ``,`` or ``;``; and curl's cookie option given a
  cookie (``-b 'sid=...'``, ``--cookie sid=...``: a name and ``=`` within
  its first 64 characters, so a cookie file's name and another program's
  ``-b`` stay);
- ``Bearer`` tokens (8 or more token characters);
- the password of a URL's userinfo (``scheme://user:<secret>@``, the
  scheme a run of scheme characters that holds a letter, the user's name
  empty or not: ``redis://:<secret>@``, the slashes escaped or not:
  ``mysql:\\/\\/...``, as PHP writes a URL in JSON);
- a ``.netrc`` entry's password (``machine <host> login <user> password
  <secret>``);
- an assignment to a credential name (``password``, ``passwd``,
  ``passphrase``, ``pwd``, ``secret``, ``secret_key``, ``token``,
  ``api_key``, ``access_key``, ``client_secret``, ``private_key``,
  ``account_key``, ``signing_key``, ``encryption_key``, ``hmac_key``,
  ``master_key``, ``credential``, alone or at the end of a longer name such
  as ``DB_PASSWORD``, ``PGPASSWORD``, ``DJANGO_SECRET_KEY``,
  ``access_token``, ``AccountKey`` or ``AUDIT_HMAC_KEY``) with ``=`` or
  ``:`` (or ``=`` as its JSON escape, ``\\u003d``), of 4 or
  more characters, in assignments, query strings and JSON text, its quotes
  escaped or not (``{\\"password\\": \\"...\\"}``, JSON text inside a
  JSON string or a shell's double quotes); a quoted value is read to its
  closing quote on its line, whitespace and all (``"passphrase": "correct
  horse battery staple"``), and an unquoted one (or one whose quote does not
  close on its line) to a blank, a quote, ``&``, ``,`` or ``;``;
- a command's user option (``curl -u user:<secret>``, ``-uuser:...``,
  ``--user``, ``-U``, ``--proxy-user``) and an option named for a
  credential with its value after blanks (``--password <secret>``,
  ``--api-key <secret>``, not another option), also as a list's items
  (``['-u', 'user:<secret>']``, as an exception's text quotes a command),
  a quoted value or password read to its closing quote as above;
- PEM ``PRIVATE KEY`` and OpenPGP ``PRIVATE KEY BLOCK`` blocks: the body,
  or, after a header with no end (an excerpt, a truncated line), the rest of
  the text;
- AWS access key ids, GitHub tokens, Slack tokens, ``sk-`` keys, JWTs, and
  service tokens by their prefix: Stripe's ``sk_live_`` and ``rk_live_``
  (and ``_test_``), Google's ``AIza``, GitLab's ``glpat-``, npm's ``npm_``,
  Vault's ``hvs.``, SendGrid's ``SG.``, and a Slack webhook's path; each
  of these tokens starts where the character before it is not an ASCII
  letter or digit, so a token after ``_`` (``mcp__srv__ghp_...``, an MCP
  tool's name) is replaced and the prefix kept, and one glued after a
  letter or digit (``xghp_...``) is not;
- a signed URL's signature: the value, of 16 or more characters, of an
  ``X-Amz-Signature`` (S3 SigV4), ``X-Goog-Signature`` (Cloud Storage),
  ``sig`` (Azure SAS) or ``Signature`` (S3 SigV2, CloudFront) query
  parameter, after ``?`` or ``&`` (as themselves, percent-encoded or as
  their JSON escapes), so prose such as ``signature=`` is kept;
- a header or credential given as a name/value pair or a ``[name, value]``
  tuple in JSON or code text (``"name": "Authorization", "value": "Basic
  ..."``, ``('Cookie', 'sid=...')``), its quotes escaped or not: its value,
  of 4 or more characters, read to its closing quote as above (a
  ``Cookie`` header's later cookies too).

Wherever these read a quote, it may also be written as the JSON escape of
its code point (``\\u0022``, ``\\u0027``: .NET writes JSON text inside a
JSON string so), and a token or a name that starts a word may start right
after one.

Not read: a password given to a short option with no name attached
(``mysql -p<secret>``, ``sshpass -p <secret>``: ``-p`` means too many other
things to redact on its own), npm's ``_auth=`` and a Docker configuration's
``auth`` member (names too common to read alone), a name ending in
``_pass``, other vendors' token formats, and a secret in base64 or another
encoding than those above, unless it is registered in that form too.

In a JSON value, a member whose name ends in a credential name (as above,
in any case and after any prefix: ``accessToken``, ``dbPassword``,
``x-api-key``) or in ``authorization``, ``cookie`` or ``cookies`` (the
structured form of the ``Authorization``, ``Proxy-Authorization``,
``Cookie`` and ``Set-Cookie`` headers, a HAR's cookies) is a secret member,
and so is a header given as a pair: the ``value`` member of an object whose
``name``, ``key`` or ``header`` member (in any case) is a secret member's
name (HAR, Postman, Kubernetes ``env``), and the second element of a
two-element list whose first is one (``[["Authorization", "Basic ..."]]``).
A secret member's value is redacted whole when it is a string of 4 or more
characters or a number, and when it is a list or an object, each such
string and number in it is (a header's list of values, a ``{"value": ...}``
wrapper). Booleans and null are kept. Not read as a pair: one whose
value comes before its name in text, a flat ``[name, value, name, value]``
list (Node's ``rawHeaders``); a ``Cookie:`` header line in text is read by
the header rule above. A member
name is redacted as any
string is: a name that holds a secret is replaced by its redacted text, and
a name that would then repeat one already in its object gets `` (2)``,
`` (3)``, ... so that no member is lost. The assignment rule is
deliberately broad: replacing a word of prose costs little where a secret
would cost much.

A refusal is another matter: ``persist`` data or an ``audit`` record that
holds a secret is refused, not redacted (§6.7), and a refusal of ordinary
project knowledge (``token: rotate monthly``) would cost much.
:meth:`Redactor.holds_credential` therefore recognises only
credential-shaped values: a registered value (in a string, a member name
or a number's JSON text), the key and token formats above (PEM and OpenPGP
private keys, AWS, GitHub, Slack, ``sk-`` keys, JWTs, a bearer token of 20
or more characters; the longer prefixes anywhere, glued after a letter or
digit too, and ``sk-`` only where a token starts, since its two letters end
words such as ``task`` and ``risk``), a signed URL's signature as above,
the password of a URL's userinfo unless it is a
placeholder (``password``, ``<password>``, ``${DB_PASSWORD}``, ``****``),
an ``Authorization`` or ``Proxy-Authorization`` header's value of 8 or more
token characters mixing letters and digits, with no scheme or after any
scheme (``ApiKey``, ``SSWS``, ...; in a header line, or given as a pair or
tuple in text, as above), a cookie (``name=value``, a Set-Cookie attribute
aside) in a ``Cookie`` or ``Set-Cookie`` header's value or curl's cookie
option's whose value is 8 or more token characters mixing letters and
digits (``Cookie: none yet`` passes), a command's user option's password,
or a ``.netrc`` entry's, of 8 or more
characters mixing letters and digits (``curl -u
admin:<value>``; ``docker run -u 1000:1000`` passes), and an assignment to
a credential name, or a credential option's value, that is quoted with no
whitespace and 8 or more characters, or unquoted, 12 or more characters,
mixing letters and digits (the quotes escaped or not, as above). It reads
a text with the JSON escapes other encoders write for the characters it
reads decoded (:data:`_ESCAPED`: a quote's, ``&``'s, ``<``'s, ``>``'s,
``=``'s and ``+``'s ``\\u00XX``, and ``\\/``), so its rules read that text
as they read Python's JSON.
The plugin's ``hooks/secret_scan.sh`` applies the same rule to text,
except that it reads ``sk-`` anywhere and reads no signed URL's signature,
and ``tests/conformance/secrets/credentials.json`` pins it for the three. In
JSON data, which is not prose, it also recognises what redaction does in a
secret member (above), unless the string is a placeholder: data holding a
secret the host recognises is refused (§6.7), so ``{"password": "correct
horse battery staple"}`` is refused as it would be redacted.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .evidence_store import EvidenceAnchor

__all__ = [
    "DEFAULT_PATTERNS",
    "encoded_forms",
    "holds_credential",
    "DEFAULT_REDACTOR",
    "MARKER",
    "Redactor",
    "holds_secret",
    "redact",
    "redact_text",
]

MARKER = "[REDACTED]"
"""What a redacted secret is replaced by."""

MIN_SECRET_LENGTH = 4
"""Registered values shorter than this are ignored: replacing every
occurrence of a two-character value would destroy the text."""

# A text of at most _CLEAN_LENGTH characters that a redactor read and found
# clean (nothing to replace) is kept, up to _CLEAN_TEXTS of them, and not
# read again until a value or a pattern is added: an evidence store redacts
# the same member names and tool names in every anchor it keeps, and every
# pattern reads every text. A text that held a secret is never kept.
_CLEAN_LENGTH = 256
_CLEAN_TEXTS = 4096

# Credential names: alone, or at the end of a longer name after `_` or `-`.
_NAMES = (
    r"password|passwd|passphrase|pwd|secret|secret[_-]?key|token|api[_-]?key"
    r"|access[_-]?key|client[_-]?secret|private[_-]?key|account[_-]?key"
    r"|signing[_-]?key|encryption[_-]?key|hmac[_-]?key|master[_-]?key|credential"
)
# Whitespace, spelled out: `\s` differs between Python and ECMAScript, and
# the TypeScript redactor must agree with this one. Every pattern is ASCII
# (`re.ASCII`), so `\b` and case-insensitive matching are ASCII-only, as
# they are in an ECMAScript pattern without the `u` flag.
_WS = r"[ \t\n\r\f\v]"
_NOT_WS = r" \t\n\r\f\v"


def _after(chars: str) -> str:
    """Where a word may start: after a character outside ``chars`` (a
    character class's contents), or after a quote's JSON escape
    (``\\u0022sk-...``), whose last character is a digit."""
    return rf"(?:(?<![{chars}])|(?<=\\u00(?:22|27)))"


# A URL's scheme: a run of scheme characters that holds a letter, read from
# the run's start (not after a scheme character), so a long run that is not
# followed by `://` is read once, not again from each letter in it.
_SCHEME = rf"{_after('A-Za-z0-9+.-')}[0-9+.-]*[A-Za-z][A-Za-z0-9+.-]*"
# A quote as JSON or code text writes it, or escaped (`\\"`, as JSON text
# inside a JSON string writes it, or escaped again: `\\\\\\"`), or as the
# JSON escape of its code point (`\\u0022`, `\\u0027`, as .NET's encoder
# writes a quote inside a JSON string).
_QUOTE = r"(?:\\*[\"']|\\+u00(?:22|27))"
# The JSON escape of each quote's code point.
_QUOTE_CODES = {'"': "u0022", "'": "u0027"}
# What separates a name from its value: `:` or `=`, or `=` as its JSON
# escape (`\\u003d`, as Gson writes it).
_SEP = r"(?:[:=]|\\+u003[dD])"
# A run of blanks, read whole: a value after it starts after the run, so a
# value that may hold blanks is not read again from each blank of the run.
_BLANKS = rf"{_WS}*(?!{_WS})"


def _value_char(excluded: str = "") -> str:
    """One character of a value: not whitespace, a quote, a backslash or one
    of ``excluded``, or a run of backslashes that no quote follows (an
    escaped quote, or a quote's JSON escape, ends the value, as a quote
    does)."""
    return rf"(?:[^{_NOT_WS}\"'\\{excluded}]|\\+(?![\\\"']|u00(?:22|27)))"


def _open_quote(quote: str) -> str:
    """``quote`` as a value's opening quote: as written, escaped, or as its
    JSON escape (``\\u0022``)."""
    return rf"(?:\\*{quote}|\\+{_QUOTE_CODES[quote]})"


def _quoted_value(quote: str) -> str:
    """A value in ``quote`` quotes, whitespace and all, of 4 characters or
    more, read to its closing quote on its line (escaped or not, or its JSON
    escape), so a quoted passphrase is replaced whole. A character is not
    that quote, a backslash or a line break, or is a run of backslashes that
    no such quote follows (read once). With no closing quote on the line
    nothing matches, and the value is read as an unquoted one is."""
    code = _QUOTE_CODES[quote]
    return (
        rf"(?P<secret>(?:[^{quote}\\\n\r]|\\+(?![\\{quote}]|{code})){{4,}})"
        rf"(?=\\*{quote}|\\+{code})"
    )


# A secret member's name (see _SECRET_MEMBER), quoted as JSON or code text
# quotes it, the opening quote as written or as its JSON escape (read after
# the escape's backslash). A name holds no backslash, so an attempt reads to
# the next quote, backslash or blank.
_QUOTED_SECRET_NAME = (
    rf"(?:[\"']|(?<=\\)u00(?:22|27))[^{_NOT_WS}\"'\\]*"
    rf"(?:{_NAMES}|authorization|cookies?){_QUOTE}"
)
# The header schemes a redacted value keeps in view: what follows one is the
# credential. Any other first word may be the credential itself.
_SCHEMES = r"(?:bearer|basic|token|digest|negotiate)"
# A header's scheme, which the value after it may start with (the blanks
# after it read whole).
_VALUE_SCHEME = rf"(?:{_SCHEMES}{_WS}+(?!{_WS}))?"
# Any header scheme (`ApiKey`, `SSWS`, `Bot`, `AWS4-HMAC-SHA256`): a word
# and the spaces after it (RFC 9110 puts one or more there), before the
# credential; hooks/secret_scan.sh reads the same.
_ANY_SCHEME = r"[A-Za-z][A-Za-z0-9._-]* +"
# An Authorization or Proxy-Authorization header, up to its value (a JSON
# member's or a code's quote before the separator, and blanks).
_AUTHORIZATION = (
    rf"{_after('A-Za-z0-9')}(?:proxy-)?authorization(?:{_QUOTE})?{_WS}*{_SEP}{_WS}*"
)
# A Cookie or Set-Cookie header, up to its value, as the Authorization
# header above.
_COOKIE = rf"(?:set-)?cookie(?:{_QUOTE})?{_WS}*{_SEP}{_WS}*"
# A character of a header line's value, which may hold blanks (`a=1;
# sid=...`): not a line break, a quote or a backslash, or a run of
# backslashes that no quote follows.
_LINE_CHAR = r"(?:[^\n\r\"'\\]|\\+(?![\\\"']|u00(?:22|27)))"
# A header or credential given as a `[name, value]` tuple in JSON or code
# text, up to its value: `["Authorization", "Basic ...`, `('Cookie', '...`.
# Each attempt starts at a bracket and reads to the next quote or
# whitespace, so a text is read once.
_TUPLE_HEAD = rf"[\[(]{_WS}*\\*{_QUOTED_SECRET_NAME}{_WS}*,{_WS}*"
_TUPLE_TEXT = rf"{_TUPLE_HEAD}{_QUOTE}{_VALUE_SCHEME}"
# A header or credential given as a name/value pair in JSON or code text, up
# to its value: `"Authorization", "value": "...`, as a HAR's `{"name": ...,
# "value": ...}` reads. Each attempt starts at a quote.
_PAIR_HEAD = (
    rf"{_QUOTED_SECRET_NAME}{_WS}*,{_WS}*(?:{_QUOTE})?value(?:{_QUOTE})?{_WS}*{_SEP}"
    rf"{_WS}*"
)
_PAIR_TEXT = rf"{_PAIR_HEAD}{_QUOTE}{_VALUE_SCHEME}"
# What separates a command's option from its value: blanks, `=`, or the
# next item of a list (`'-u', '...`, `"--token", "...`), the value quoted
# or not.
_OPTION_SEPARATOR = (
    rf"(?:{_WS}+(?:{_QUOTE})?|=(?:{_QUOTE})?|(?:{_QUOTE})?{_WS}*,{_WS}*{_QUOTE})"
)
# A command's user option, up to the user's password: curl's `-u
# user:<secret>` (also `-uuser:...`), `--user`, `--proxy-user` and `-U`.
# The user's name is read for at most 256 characters: an attempt starts at
# each `-u` after a character that is not a name's, and a run such as
# `.-u.-u.-u...` holds one at each of its positions, so an unbounded name
# was read again from each to the run's end.
_USER_OPTION = (
    rf"{_after('A-Za-z0-9_-')}(?:-[uU]{_OPTION_SEPARATOR}?|--(?:proxy-)?user"
    rf"{_OPTION_SEPARATOR})[^{_NOT_WS}:\"'\\]{{0,256}}:"
)
# ... and the same option up to the quote its value opens with.
_USER_OPTION_QUOTE_SEPARATOR = rf"(?:{_WS}+|=|(?:{_QUOTE})?{_WS}*,{_WS}*)"
_USER_OPTION_NAME = (
    rf"{_after('A-Za-z0-9_-')}(?:-[uU]{_USER_OPTION_QUOTE_SEPARATOR}?|--(?:proxy-)?user"
    rf"{_USER_OPTION_QUOTE_SEPARATOR})"
)
# A command's option named for a credential (`--password`, `--api-key`,
# `--db-token`), and what separates it from a value given after blanks or as
# a list's next item; `--password=...` is an assignment.
_CREDENTIAL_OPTION_NAME = rf"{_after('A-Za-z0-9_-')}--(?:[A-Za-z0-9]+[_-])*(?:{_NAMES})"
_CREDENTIAL_OPTION_SEPARATOR = rf"(?:{_WS}+|(?:{_QUOTE})?{_WS}*,{_WS}*)"
# ... up to its value, which is not another option.
_CREDENTIAL_OPTION = (
    rf"{_CREDENTIAL_OPTION_NAME}(?:{_WS}+(?:{_QUOTE})?|(?:{_QUOTE})?{_WS}*,{_WS}*"
    rf"{_QUOTE})(?!-)"
)
# An assignment to a credential name, up to its value.
_ASSIGN = rf"(?:{_NAMES})(?:{_QUOTE})?{_WS}*{_SEP}{_WS}*"
# curl's cookie option (`-b`, `--cookie`), up to the quote its value opens
# with, and up to its value, quoted or not, as the user option's.
_COOKIE_OPTION_NAME = (
    rf"{_after('A-Za-z0-9_-')}(?:-b{_USER_OPTION_QUOTE_SEPARATOR}?"
    rf"|--cookie{_USER_OPTION_QUOTE_SEPARATOR})"
)
_COOKIE_OPTION = (
    rf"{_after('A-Za-z0-9_-')}(?:-b{_OPTION_SEPARATOR}?|--cookie{_OPTION_SEPARATOR})"
)
# A .netrc entry's password (`machine <host> login <user> password
# <secret>`, `default password <secret>`), up to its value: a netrc keyword,
# at most one word, `password` and blanks.
_NETRC = (
    rf"{_after('A-Za-z0-9_-')}(?:machine|login|account|default){_WS}+"
    rf"(?:[^{_NOT_WS}]+{_WS}+)?password{_WS}+"
)


def _quoted_forms(
    prefix: str, after_quote: str = "", flags: re.RegexFlag = re.IGNORECASE
) -> tuple[re.Pattern[str], ...]:
    """The patterns of a value after ``prefix`` in double or single quotes
    (escaped or not, or as their JSON escapes), ``after_quote`` read first:
    the value is read to its closing quote, whitespace and all (see
    _quoted_value)."""
    return tuple(
        re.compile(
            rf"{prefix}{_open_quote(quote)}{after_quote}{_quoted_value(quote)}",
            re.ASCII | flags,
        )
        for quote in ('"', "'")
    )


# Where a prefix-shaped token starts: after a character that is not an ASCII
# letter or digit (so after `_`, `-`, `.`, `/`, `:` or a quote: a token in
# an MCP tool's name, `mcp__srv__ghp_...`, is read), or after a quote's JSON
# escape. A token glued after a letter or digit (`xghp_...`) is not read
# here; the refusal rule (_CREDENTIAL_SHAPES) still refuses it.
_WORD = _after("A-Za-z0-9")
# A signed URL's signature: the value of an `X-Amz-Signature` (S3 SigV4),
# `X-Goog-Signature` (Cloud Storage), `sig` (Azure SAS) or `Signature` (S3
# SigV2, CloudFront) query parameter, read only after `?` or `&` (as
# themselves, percent-encoded or as their JSON escapes), so prose such as
# `signature=` is not read. The value is 16 or more characters; it stops
# at `&` and `?` in any of those forms, so no run is read again from each
# of its positions.
_SIGNED_URL_PARAMETER = (
    r"(?:[?&]|%3F|%26|\\u00(?:3F|26))"
    r"(?:x-amz-signature|x-goog-signature|sig|signature)(?:=|%3D|\\u003D)"
)
_SIGNATURE_VALUE = r"(?:[A-Za-z0-9._~+/=-]|%(?!26|3F)[0-9A-F]{2}){16,}"

DEFAULT_PATTERNS: tuple[re.Pattern[str], ...] = (
    # PEM private key blocks and OpenPGP private key blocks (`PRIVATE KEY
    # BLOCK`): the body, to the first end line. A header with no end after
    # it (an excerpt, a truncated line) keeps its body: the rest of the text
    # is replaced, so the next header is not read again to the end of the
    # text either.
    re.compile(
        r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----"
        r"(?P<secret>[\s\S]+?)"
        r"(?:-----END (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----|\Z)",
        re.ASCII,
    ),
    # Authorization and Proxy-Authorization header values: a quoted value
    # (`"Authorization": "..."`) read to its closing quote, whitespace and
    # all, after one of the five schemes ...
    *_quoted_forms(_AUTHORIZATION, _VALUE_SCHEME),
    # ... and a header line quoted whole (`-H "Authorization: ..."`, its
    # quotes escaped or not) read to its closing quote, the same way; an
    # attempt starts at the start of a run of backslashes, so a run is read
    # once, and the blanks after the colon are read whole, so the value is
    # not read again from each of them ...
    *_quoted_forms(
        r"(?<!\\)", rf"(?:proxy-)?authorization{_WS}*:{_BLANKS}{_VALUE_SCHEME}"
    ),
    # ... or, unquoted: after any other first word (a scheme such as
    # `ApiKey`, `SSWS` or `Bot`, or a credential with no scheme), that word
    # and the one after it on its line, so the credential is replaced
    # whether or not the word was a scheme ...
    re.compile(
        rf"{_AUTHORIZATION}(?:{_QUOTE})?(?!{_SCHEMES}{_WS})"
        rf"(?P<secret>{_value_char(',;')}+(?:[ \t]+{_value_char(',;')}+)?)",
        re.ASCII | re.IGNORECASE,
    ),
    # ... and after one of the five schemes, the credential.
    re.compile(
        rf"{_AUTHORIZATION}(?:{_QUOTE})?(?:{_SCHEMES}{_WS}+)?"
        rf"(?P<secret>{_value_char(',;')}+)",
        re.ASCII | re.IGNORECASE,
    ),
    # A header or credential given as a name/value pair or a [name, value]
    # tuple in text: its value, of four characters or more, read to its
    # closing quote (`"Cookie", "theme=dark; sid=..."`) ...
    *_quoted_forms(rf"(?:{_TUPLE_HEAD}|{_PAIR_HEAD})", _VALUE_SCHEME),
    # ... or, with no closing quote on its line, to a blank, `,` or `;`.
    re.compile(
        rf"(?:{_TUPLE_TEXT}|{_PAIR_TEXT})(?P<secret>{_value_char(',;')}{{4,}})",
        re.ASCII | re.IGNORECASE,
    ),
    # Cookie and Set-Cookie header values: a quoted value (`"Cookie":
    # "..."`, `{'Cookie': '...'}`) read to its closing quote, whitespace and
    # all ...
    *_quoted_forms(_COOKIE),
    # ... a header line quoted whole (`-H 'Cookie: ...'`) read to its closing
    # quote, the same way ...
    *_quoted_forms(r"(?<!\\)", rf"(?:set-)?cookie{_WS}*:{_BLANKS}"),
    # ... a header line, from its first character that is not a blank to the
    # end of its line (a cookie string holds blanks: `a=1; sid=...`; a
    # Set-Cookie line's attributes go with it) ...
    re.compile(
        rf"(?:set-)?cookie{_WS}*:{_WS}*(?P<secret>{_value_char()}{_LINE_CHAR}{{3,}})",
        re.ASCII | re.IGNORECASE,
    ),
    # ... or, after `=` or a quote that does not close on its line, to a
    # blank, `,` or `;`.
    re.compile(
        rf"{_COOKIE}(?:{_QUOTE})?(?P<secret>{_value_char(',;')}{{4,}})",
        re.ASCII | re.IGNORECASE,
    ),
    # curl's cookie option given a cookie string (`-b 'sid=...'`, `--cookie
    # sid=...`, not a cookie file's name: a name and `=` within its first 64
    # characters), quoted ...
    *_quoted_forms(_COOKIE_OPTION_NAME, r"(?=[^\n\r\"'\\=]{0,64}=)", re.NOFLAG),
    # ... or not.
    re.compile(
        rf"{_COOKIE_OPTION}(?=[^{_NOT_WS}\"'\\=]{{0,64}}=)"
        rf"(?P<secret>{_value_char()}{{4,}})",
        re.ASCII,
    ),
    # Bearer tokens.
    re.compile(
        rf"{_after('A-Za-z0-9')}bearer{_WS}+(?P<secret>[A-Za-z0-9._~+/=-]{{8,}})",
        re.ASCII | re.IGNORECASE,
    ),
    # The password of a URL's userinfo, the user's name empty or not
    # (`redis://:<secret>@`), its slashes escaped or not (`mysql:\\/\\/...`,
    # as PHP's json_encode writes a URL).
    re.compile(
        rf"{_SCHEME}:(?:\\*/){{2}}[^{_NOT_WS}/:@]*:(?P<secret>[^{_NOT_WS}/@]+)@",
        re.ASCII,
    ),
    # A .netrc entry's password (`machine <host> login <user> password
    # <secret>`).
    re.compile(rf"{_NETRC}(?P<secret>{_value_char()}{{4,}})", re.ASCII),
    # Assignments to a credential name, alone or at the end of a longer name
    # (DB_PASSWORD, PGPASSWORD), in code, query strings and JSON text, its
    # quotes escaped or not (`{\\"password\\": \\"...\\"}`): a quoted
    # value read to its closing quote (`"passphrase": "correct horse ..."`)
    # ...
    *_quoted_forms(_ASSIGN),
    # ... or an unquoted one (or one with no closing quote on its line) to a
    # blank, a quote, `&`, `,` or `;`.
    re.compile(
        rf"{_ASSIGN}(?:{_QUOTE})?(?P<secret>{_value_char('&,;')}{{4,}})",
        re.ASCII | re.IGNORECASE,
    ),
    # A command's user option: the password (`curl -u user:<secret>`), read
    # to its closing quote when the option's value is quoted ...
    *_quoted_forms(_USER_OPTION_NAME, rf"[^{_NOT_WS}:\"'\\]*:", re.NOFLAG),
    # ... or to a blank or a quote.
    re.compile(
        rf"{_USER_OPTION}(?P<secret>{_value_char()}{{4,}})",
        re.ASCII,
    ),
    # A command's option named for a credential, its value after blanks
    # (`--password <secret>`, `--api-key <secret>`), quoted ...
    *_quoted_forms(
        rf"{_CREDENTIAL_OPTION_NAME}{_CREDENTIAL_OPTION_SEPARATOR}", "(?!-)"
    ),
    # ... or not.
    re.compile(
        rf"{_CREDENTIAL_OPTION}(?P<secret>{_value_char()}{{4,}})",
        re.ASCII | re.IGNORECASE,
    ),
    # AWS access key ids.
    re.compile(rf"{_WORD}(?P<secret>(?:AKIA|ASIA)[A-Z0-9]{{16}})\b", re.ASCII),
    # GitHub tokens.
    re.compile(
        rf"{_WORD}(?P<secret>gh[pousr]_[A-Za-z0-9]{{36,}}|github_pat_[A-Za-z0-9_]{{22,}})",
        re.ASCII,
    ),
    # Slack tokens.
    re.compile(rf"{_WORD}(?P<secret>xox[abprs]-[A-Za-z0-9-]{{10,}})", re.ASCII),
    # sk- keys.
    re.compile(rf"{_WORD}(?P<secret>sk-[A-Za-z0-9_-]{{20,}})", re.ASCII),
    # Service tokens by their prefix: Stripe's secret and restricted keys,
    # Google API keys, GitLab personal access tokens, npm tokens, Vault
    # tokens and SendGrid keys ...
    re.compile(
        rf"{_WORD}(?P<secret>[rs]k_(?:live|test)_[A-Za-z0-9]{{16,}}|AIza[0-9A-Za-z_-]{{35}}"
        r"|glpat-[0-9A-Za-z_-]{20,}|npm_[A-Za-z0-9]{36}|hv[sbr]\.[A-Za-z0-9_-]{24,}"
        r"|SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,})",
        re.ASCII,
    ),
    # A signed URL's signature.
    re.compile(
        rf"{_SIGNED_URL_PARAMETER}(?P<secret>{_SIGNATURE_VALUE})",
        re.ASCII | re.IGNORECASE,
    ),
    # ... and a Slack webhook's path.
    re.compile(
        r"hooks\.slack\.com/services/(?P<secret>T[A-Za-z0-9]+/B[A-Za-z0-9]+/"
        r"[A-Za-z0-9]{16,})",
        re.ASCII,
    ),
    # JWTs: three base64url parts, the first a JSON object's encoding,
    # starting where a prefix-shaped token starts (_WORD). Read from the
    # start of a run of base64url characters to its first `eyJ` at a token
    # start (the run's start or after `_` or `-`), so a run is read once,
    # not again from each `eyJ` in it.
    re.compile(
        rf"{_after('A-Za-z0-9_-')}(?:(?!eyJ)(?:[A-Za-z0-9]|[_-](?!eyJ))*[_-])?"
        r"(?P<secret>eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)",
        re.ASCII,
    ),
)
"""The default patterns; each marks the secret with the group ``secret`` (a
match in which it takes no part replaces nothing). Each reads a text in time
in proportion to its length: no run of characters is read again from each of
its positions (tests/test_redaction.py times them on 1 MB)."""

# Credential shapes a refusal relies on (holds_credential): the formats of
# keys and tokens, no prose. hooks/secret_scan.sh holds the same ones, but
# for `sk-`, which it reads anywhere, and signed URLs, which it does not read.
_CREDENTIAL_SHAPES: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----", re.ASCII),
    re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}", re.ASCII),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36}", re.ASCII),
    re.compile(r"github_pat_[A-Za-z0-9_]{22,}", re.ASCII),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}", re.ASCII),
    # `sk-` only where a token starts (not after an ASCII letter or digit):
    # its two letters end common words (`task-...`, `risk-...`, `disk-...`).
    # The longer prefixes above and below are read anywhere.
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}", re.ASCII),
    re.compile(rf"[Bb]earer{_WS}+[A-Za-z0-9._~+/=-]{{20,}}", re.ASCII),
    # Read from the start of a run to its first `eyJ` (whose first part is
    # the longest), so a run is read once.
    re.compile(
        r"(?<![A-Za-z0-9_-])(?:(?!eyJ)[A-Za-z0-9_-])*"
        r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
        re.ASCII,
    ),
    # Service tokens by their prefix (Stripe, Google, GitLab, npm, Vault,
    # SendGrid) and a Slack webhook's path.
    re.compile(
        r"[rs]k_(?:live|test)_[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_-]{35}"
        r"|glpat-[0-9A-Za-z_-]{20,}|npm_[A-Za-z0-9]{36}|hv[sbr]\.[A-Za-z0-9_-]{24,}"
        r"|SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}"
        r"|hooks\.slack\.com/services/T[A-Za-z0-9]+/B[A-Za-z0-9]+/[A-Za-z0-9]{16,}",
        re.ASCII,
    ),
    # A signed URL's signature.
    re.compile(rf"{_SIGNED_URL_PARAMETER}{_SIGNATURE_VALUE}", re.ASCII | re.IGNORECASE),
)
# A quoted value with no whitespace, 8 or more characters (its quotes
# escaped or not), after an assignment or a credential option.
_QUOTED_CREDENTIAL = re.compile(
    rf"{_ASSIGN}{_QUOTE}[^{_NOT_WS}\"']{{8,}}[\"']"
    rf"|{_CREDENTIAL_OPTION_NAME}{_CREDENTIAL_OPTION_SEPARATOR}{_QUOTE}"
    rf"[^{_NOT_WS}\"'-][^{_NOT_WS}\"']{{7,}}[\"']",
    re.ASCII | re.IGNORECASE,
)
# An unquoted value of 12 or more characters with letters and digits, after
# an assignment or a credential option (not another option).
_UNQUOTED_VALUE = re.compile(
    rf"{_ASSIGN}(?P<value>[^{_NOT_WS}\"']{{12,}})", re.ASCII | re.IGNORECASE
)
_OPTION_VALUE = re.compile(
    rf"{_CREDENTIAL_OPTION_NAME}{_WS}+(?P<value>[^{_NOT_WS}\"'-][^{_NOT_WS}\"']{{11,}})",
    re.ASCII | re.IGNORECASE,
)
# A command's user option's password (``curl -u user:<value>``): 8 or more
# characters with letters and digits.
_USER_OPTION_VALUE = re.compile(
    rf"{_USER_OPTION}(?P<value>[^{_NOT_WS}\"'\\]{{8,}})", re.ASCII
)
# The password of a URL's userinfo (``scheme://user:<value>@``, the user's
# name empty or not) ...
_URL_PASSWORD = re.compile(
    rf"{_SCHEME}:(?:\\*/){{2}}[^{_NOT_WS}/:@]*:(?P<value>[^{_NOT_WS}/@]+)@",
    re.ASCII,
)
# ... unless it is a placeholder (``password``, ``<password>``, ``${PW}``,
# ``****``).
_PLACEHOLDER = re.compile(
    r"[$<{*\[].*|password|passwd|pwd|pass|secret|token", re.ASCII | re.IGNORECASE
)
# An Authorization or Proxy-Authorization header's value, with no scheme or
# after one of the five: 8 or more token characters with letters and
# digits ...
_AUTHORIZATION_VALUE = re.compile(
    rf"(?:proxy-)?authorization(?:{_QUOTE})?{_WS}*[:=]{_WS}*(?:{_QUOTE})?"
    rf"(?:{_SCHEMES}{_WS}+)?"
    r"(?P<value>[A-Za-z0-9._~+/=-]{8,})",
    re.ASCII | re.IGNORECASE,
)
# ... or after any other scheme (`ApiKey`, `SSWS`, `Bot`, `Splunk`). Both
# readings are tried: the first word of a value may be its scheme or its
# credential.
_AUTHORIZATION_SCHEME_VALUE = re.compile(
    rf"(?:proxy-)?authorization(?:{_QUOTE})?{_WS}*[:=]{_WS}*(?:{_QUOTE})?"
    rf"{_ANY_SCHEME}(?P<value>[A-Za-z0-9._~+/=-]{{8,}})",
    re.ASCII | re.IGNORECASE,
)
# A header's or credential's value given as a name/value pair, or as a
# tuple of exactly two (a list of names is not one), in text, after its
# scheme: 8 or more token characters with letters and digits.
_PAIR_VALUE_TEXT = re.compile(
    rf"{_PAIR_TEXT}(?P<value>[A-Za-z0-9._~+/=-]{{8,}})", re.ASCII | re.IGNORECASE
)
_TUPLE_VALUE_TEXT = re.compile(
    rf"{_TUPLE_TEXT}(?P<value>[A-Za-z0-9._~+/=-]{{8,}}){_QUOTE}{_WS}*[\])]",
    re.ASCII | re.IGNORECASE,
)
# ... and the same after any other scheme.
_PAIR_SCHEME_VALUE_TEXT = re.compile(
    rf"{_PAIR_HEAD}{_QUOTE}{_ANY_SCHEME}(?P<value>[A-Za-z0-9._~+/=-]{{8,}})",
    re.ASCII | re.IGNORECASE,
)
_TUPLE_SCHEME_VALUE_TEXT = re.compile(
    rf"{_TUPLE_HEAD}{_QUOTE}{_ANY_SCHEME}(?P<value>[A-Za-z0-9._~+/=-]{{8,}})"
    rf"{_QUOTE}{_WS}*[\])]",
    re.ASCII | re.IGNORECASE,
)
# A .netrc entry's password: 8 or more characters with letters and digits.
_NETRC_VALUE = re.compile(rf"{_NETRC}(?P<value>[^{_NOT_WS}\"']{{8,}})", re.ASCII)
# A Cookie or Set-Cookie header's value, to the end of its line or its
# closing quote (a control character, a quote or a backslash ends it) ...
_COOKIE_VALUE = re.compile(
    rf"(?:set-)?cookie(?:{_QUOTE})?{_WS}*[:=]{_WS}*(?:{_QUOTE})?"
    r"(?P<value>[^ \t\n\r\f\v\"'\\][^\x00-\x1f\x7f\"'\\]*)",
    re.ASCII | re.IGNORECASE,
)
# ... and the value of curl's cookie option holding a cookie (a name and `=`
# within its first 64 characters), quoted, to its closing quote ...
_COOKIE_OPTION_QUOTED = re.compile(
    rf"{_COOKIE_OPTION_NAME}{_QUOTE}"
    r"(?P<value>[^\x00-\x1f\x7f\"'\\=]{0,64}=[^\x00-\x1f\x7f\"'\\]*)",
    re.ASCII,
)
# ... or not, to a blank.
_COOKIE_OPTION_VALUE = re.compile(
    rf"{_COOKIE_OPTION}(?P<value>[^{_NOT_WS}\"'\\=]{{0,64}}=[^{_NOT_WS}\"'\\]*)",
    re.ASCII,
)
# The cookies of such a value: its pieces between `;`, `,` and blanks.
_COOKIE_PIECE = re.compile(r"[^;, ]+", re.ASCII)
# The attributes a Set-Cookie line gives after its cookie, which are not
# cookies.
_COOKIE_ATTRIBUTE = re.compile(
    r"path|domain|expires|max-age|samesite|secure|httponly|partitioned|priority",
    re.ASCII | re.IGNORECASE,
)
# A cookie's value a refusal relies on: 8 or more token characters (with
# `%`, a URL-encoded value's) with letters and digits.
_COOKIE_TOKEN = re.compile(r"[A-Za-z0-9._~+/=%-]{8,}", re.ASCII)
# JSON escapes some encoders write for ASCII characters the rules read: the
# HTML-safe escapes of Go's encoding/json, Gson and .NET's System.Text.Json
# (`&`, `<`, `>`, `=`, `+` and the quotes as `\\u00XX`), and PHP's `\\/`.
# The refusal rule reads a text with them decoded, a quote as an escaped
# quote (it stays a quote inside a JSON string).
_ESCAPED = re.compile(r"\\u00(?:22|27|26|2[bB]|3[cCdDeE])|\\/", re.ASCII)
_UNESCAPED = {
    "22": '\\"',
    "27": "\\'",
    "26": "&",
    "2b": "+",
    "3c": "<",
    "3d": "=",
    "3e": ">",
}


def _decoded(text: str) -> str:
    """``text`` with the JSON escapes of :data:`_ESCAPED` decoded, in one
    pass (hooks/secret_scan.sh decodes the same ones)."""
    if "\\" not in text:
        return text
    return _ESCAPED.sub(
        lambda m: "/" if m.group(0) == "\\/" else _UNESCAPED[m.group(0)[4:].lower()],
        text,
    )


def _cookie_credential(value: str) -> bool:
    """Whether a cookie header's or option's value holds a cookie (``name=
    value``, a Set-Cookie attribute aside) whose value is credential-shaped
    (:data:`_COOKIE_TOKEN`). A piece with no ``=`` is not read: prose after
    ``Cookie:`` is not one."""
    for piece in _COOKIE_PIECE.findall(value):
        name, eq, cookie = piece.partition("=")
        if (
            eq
            and not _COOKIE_ATTRIBUTE.fullmatch(name)
            and _COOKIE_TOKEN.fullmatch(cookie)
            and _letters_and_digits(cookie)
        ):
            return True
    return False


def _letters_and_digits(value: str) -> bool:
    return bool(re.search(r"[0-9]", value) and re.search(r"[A-Za-z]", value))


def _credential_text(text: str) -> bool:
    """Whether ``text`` holds a credential-shaped value, read with the JSON
    escapes of :data:`_ESCAPED` decoded."""
    text = _decoded(text)
    if any(p.search(text) for p in _CREDENTIAL_SHAPES):
        return True
    if _QUOTED_CREDENTIAL.search(text):
        return True
    if any(
        not _PLACEHOLDER.fullmatch(m.group("value"))
        for m in _URL_PASSWORD.finditer(text)
    ):
        return True
    return any(
        _letters_and_digits(m.group("value"))
        for pattern in (
            _UNQUOTED_VALUE,
            _OPTION_VALUE,
            _USER_OPTION_VALUE,
            _AUTHORIZATION_VALUE,
            _AUTHORIZATION_SCHEME_VALUE,
            _PAIR_VALUE_TEXT,
            _TUPLE_VALUE_TEXT,
            _PAIR_SCHEME_VALUE_TEXT,
            _TUPLE_SCHEME_VALUE_TEXT,
            _NETRC_VALUE,
        )
        for m in pattern.finditer(text)
    ) or any(
        _cookie_credential(m.group("value"))
        for pattern in (_COOKIE_VALUE, _COOKIE_OPTION_QUOTED, _COOKIE_OPTION_VALUE)
        for m in pattern.finditer(text)
    )


# A member name that ends in a credential name, or names a header that
# carries one (Authorization, Proxy-Authorization, Cookie, Set-Cookie), or
# a HAR's cookies.
_SECRET_MEMBER = re.compile(
    rf".*(?:{_NAMES}|authorization|cookies?)", re.ASCII | re.IGNORECASE | re.DOTALL
)
# The member of a name/value pair that holds its name (HAR `name`, Postman
# `key`), and the one that holds its value.
_PAIR_NAME = re.compile(r"name|key|header", re.ASCII | re.IGNORECASE)
_PAIR_VALUE = re.compile(r"value", re.ASCII | re.IGNORECASE)


def _secret_pair(value: Mapping[Any, Any]) -> bool:
    """Whether an object is a header or credential given as a name/value
    pair: a ``name``, ``key`` or ``header`` member holds a secret member's
    name, so its ``value`` member is a secret member."""
    return any(
        _PAIR_NAME.fullmatch(str(k))
        and isinstance(v, str)
        and _SECRET_MEMBER.fullmatch(v)
        for k, v in value.items()
    )


def _secret_tuple(value: Sequence[Any]) -> bool:
    """Whether a list is a ``[name, value]`` tuple whose name is a secret
    member's: its second element is secret."""
    return (
        len(value) == 2
        and isinstance(value[0], str)
        and bool(_SECRET_MEMBER.fullmatch(value[0]))
    )


def _member_secret(key: Any, secret: bool, pair: bool) -> bool:
    """Whether the member named ``key`` is a secret member: within one, a
    credential's or header's name, or the value of a pair (``pair``)."""
    name = str(key)
    return (
        secret
        or bool(_SECRET_MEMBER.fullmatch(name))
        or (pair and bool(_PAIR_VALUE.fullmatch(name)))
    )


def _secret_scalar(value: Any) -> bool:
    """Whether a value in a secret member is redacted: a string of 4 or more
    characters other than the marker, or a number (not a boolean)."""
    if isinstance(value, str):
        return len(value) >= MIN_SECRET_LENGTH and value != MARKER
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _secret_member_value(value: Any, secret: bool = False) -> bool:
    """Whether JSON data holds, in a secret member, a value redaction
    replaces that is not a placeholder (``holds_credential``'s rule for
    data)."""
    if secret and _secret_scalar(value):
        return not (isinstance(value, str) and _PLACEHOLDER.fullmatch(value))
    if isinstance(value, dict):
        pair = not secret and _secret_pair(value)
        return any(
            _secret_member_value(v, _member_secret(k, secret, pair))
            for k, v in value.items()
        )
    if isinstance(value, (list, tuple)):
        tuple_ = not secret and _secret_tuple(value)
        return any(
            _secret_member_value(v, secret or (tuple_ and i == 1))
            for i, v in enumerate(value)
        )
    return False


_JSON_SHORT_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}
_ALPHANUMERIC = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
# What each percent-encoding leaves as it is, and whether it writes a space
# as `+`: RFC 3986's unreserved characters (a URL component), and `/` too
# (a path), and `!*'()` too (ECMAScript's encodeURIComponent); a form's body
# (Python's quote_plus, the WHATWG URL Standard's urlencoded serializer).
_PERCENT_ENCODINGS: tuple[tuple[str, bool], ...] = (
    (_ALPHANUMERIC + "-._~", False),
    (_ALPHANUMERIC + "-._~/", False),
    (_ALPHANUMERIC + "-._~!*'()", False),
    (_ALPHANUMERIC + "-._~", True),
    (_ALPHANUMERIC + "*-._", True),
)


# The characters encoders escape as ``\\u00XX`` so that JSON is safe inside
# HTML, and whether they write each character past ASCII as ``\\uXXXX``
# too: Go's encoding/json (the JSON of kubectl, docker, gh and terraform),
# Gson, and .NET's System.Text.Json (its quote ``\\u0022``, not ``\\"``).
_HTML_SAFE: tuple[tuple[str, bool], ...] = (
    ("&<>", False),
    ("&<>='", False),
    ("&<>'+\"`", True),
)


def _json_escaped(
    value: str, ascii_only: bool, html: str = "", upper: bool = False
) -> str:
    """``value`` as a JSON string's contents: ``"``, ``\\`` and control
    characters escaped (``\\n`` and the other short forms, else
    ``\\u00XX``), each character of ``html`` as ``\\u00XX``, and, when
    ``ascii_only``, each character past ASCII as ``\\uXXXX`` (a pair of
    them past the Basic Multilingual Plane); the hex digits in upper case
    when ``upper``."""
    hex4 = "{:04X}" if upper else "{:04x}"
    out: list[str] = []
    for ch in value:
        cp = ord(ch)
        if ch in html:
            out.append("\\u" + hex4.format(cp))
        elif ch in _JSON_SHORT_ESCAPES:
            out.append(_JSON_SHORT_ESCAPES[ch])
        elif cp < 0x20 or (ascii_only and 0x7F < cp <= 0xFFFF):
            out.append("\\u" + hex4.format(cp))
        elif ascii_only and cp > 0xFFFF:
            cp -= 0x10000
            out.append(
                "\\u"
                + hex4.format(0xD800 + (cp >> 10))
                + "\\u"
                + hex4.format(0xDC00 + (cp & 0x3FF))
            )
        else:
            out.append(ch)
    return "".join(out)


def _percent_encoded(data: bytes, keep: str, plus: bool) -> str:
    """UTF-8 ``data`` percent-encoded: each byte outside ``keep`` as
    ``%XX`` (upper-case hex), a space as ``+`` when ``plus``."""
    out: list[str] = []
    for b in data:
        c = chr(b)
        if c in keep:
            out.append(c)
        elif plus and c == " ":
            out.append("+")
        else:
            out.append(f"%{b:02X}")
    return "".join(out)


def encoded_forms(value: str) -> list[str]:
    """``value`` and the forms text carries it in, each once, in this
    order: as it is; JSON-escaped (a JSON string's contents, non-ASCII as it
    is and as ``\\uXXXX``, then each with ``/`` as ``\\/``, then each of
    the first two escaped again, as JSON text inside a JSON string holds
    it); HTML-safe JSON-escaped (by each encoder of :data:`_HTML_SAFE`, in
    lower-case hex, then in upper-case hex, then each of those escaped
    again); and percent-encoded (UTF-8, by each of the encodings of
    :data:`_PERCENT_ENCODINGS`, in upper-case hex, then in lower-case hex).
    A value with a lone surrogate has no UTF-8 and so no percent-encoded
    form. ``packages/acs-core``'s
    ``encodedForms`` gives the same forms in the same order."""
    once = _json_escaped(value, ascii_only=False)
    ascii_once = _json_escaped(value, ascii_only=True)
    html = [
        _json_escaped(value, ascii_only, chars, upper)
        for upper in (False, True)
        for chars, ascii_only in _HTML_SAFE
    ]
    forms = [
        value,
        once,
        ascii_once,
        once.replace("/", "\\/"),
        ascii_once.replace("/", "\\/"),
        _json_escaped(once, ascii_only=False),
        _json_escaped(ascii_once, ascii_only=False),
        *html,
        *(_json_escaped(form, ascii_only=False) for form in html),
    ]
    try:
        data = value.encode("utf-8")
    except UnicodeEncodeError:
        data = None
    if data is not None:
        upper = [
            _percent_encoded(data, keep, plus) for keep, plus in _PERCENT_ENCODINGS
        ]
        forms += upper
        forms += [
            re.sub(r"%[0-9A-F]{2}", lambda m: m.group(0).lower(), f) for f in upper
        ]
    return list(dict.fromkeys(forms))


def _pointer_token(key: str) -> str:
    """One JSON Pointer reference token (RFC 6901)."""
    return key.replace("~", "~0").replace("/", "~1")


class Redactor:
    """Replaces secrets with :data:`MARKER`: registered values first
    (longest first), then each pattern's ``secret`` group. A short text it
    found clean is not read again until a value or a pattern is added."""

    def __init__(
        self,
        secret_values: Iterable[str] = (),
        patterns: Sequence[re.Pattern[str]] = DEFAULT_PATTERNS,
    ) -> None:
        self._values: list[str] = []
        # The short texts found clean with the current values and patterns.
        # A change replaces the set rather than clearing it, so a reading
        # that began before the change adds its text to the old set only.
        self._clean: set[str] = set()
        self._patterns = tuple(patterns)
        for p in self._patterns:
            if "secret" not in p.groupindex:
                raise ValueError(f"pattern {p.pattern!r} has no group 'secret'")
        for v in secret_values:
            self.add_secret(v)

    def add_secret(self, value: str) -> None:
        """Register a secret value, and the forms text carries it in
        (:func:`encoded_forms`: JSON-escaped, percent-encoded); one shorter
        than four characters is ignored."""
        if not isinstance(value, str):
            raise TypeError(f"a secret value is a string, not {type(value).__name__}")
        if len(value) < MIN_SECRET_LENGTH:
            return
        for form in encoded_forms(value):
            if form not in self._values:
                self._values.append(form)
        self._values.sort(key=len, reverse=True)
        self._clean = set()

    def include(self, other: Redactor) -> None:
        """Recognise what ``other`` recognises too: its registered values,
        in every form it registered them, and its patterns. ``other`` is not
        changed. A component that writes records on behalf of another (an
        idempotency log a runner's host keeps) takes that one's secrets this
        way (§6.7)."""
        if other is self:
            return
        for form in other._values:
            if form not in self._values:
                self._values.append(form)
        self._values.sort(key=len, reverse=True)
        for p in other._patterns:
            if p not in self._patterns:
                self._patterns = (*self._patterns, p)
        self._clean = set()

    def redact_text(self, text: str) -> tuple[str, bool]:
        """``text`` with each secret replaced, and whether anything was."""
        # Taken before the values and patterns are read (see __init__).
        clean = self._clean
        short = len(text) <= _CLEAN_LENGTH
        if short and text in clean:
            return text, False
        out = text
        for v in self._values:
            out = out.replace(v, MARKER)
        for p in self._patterns:
            out = p.sub(_replace_secret, out)
        if short and out == text:
            if len(clean) >= _CLEAN_TEXTS:
                clean.clear()
            clean.add(text)
        return out, out != text

    def redact(self, value: Any) -> tuple[Any, list[str]]:
        """A JSON value with every secret replaced, and the JSON Pointers
        (RFC 6901) of the members changed, in document order (``""`` when
        the value is itself a string that changed). The value given is not
        modified."""
        pointers: list[str] = []
        return self._walk(value, "", pointers), pointers

    def holds_secret(self, value: Any) -> bool:
        """Whether :meth:`redact` would change ``value``."""
        return bool(self.redact(value)[1])

    def holds_credential(self, value: Any) -> bool:
        """Whether ``value`` (a string or JSON data) holds a registered
        value or a credential-shaped value (the module's rule for refusals:
        no prose such as ``token: rotate monthly``). A JSON value is read as
        its JSON text, so ``{"api_key": "..."}`` is an assignment, and a
        registered value is looked for in its strings, its member names and
        the JSON text of its numbers (``{"card": 4111111111111111}``)."""
        strings: list[str] = []
        numbers: list[str] = []
        _strings_in(value, strings, numbers)
        if any(v in s for v in self._values for s in (*strings, *numbers)):
            return True
        if any(_credential_text(s) for s in strings):
            return True
        if isinstance(value, str):
            return False
        # Data, not prose: what redaction replaces in a secret member.
        if _secret_member_value(value):
            return True
        # A member whose name is a credential name: its JSON text is an
        # assignment.
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except TypeError, ValueError:
            return False
        return _credential_text(text)

    def redact_anchor(self, anchor: EvidenceAnchor) -> EvidenceAnchor:
        """``anchor`` with every secret in its ``ref``, ``excerpt`` and
        metadata values replaced (§6.5, §6.7): the anchor itself when
        nothing changes, else a new (unfrozen) anchor.

        An anchor that held a secret keeps no digest of what it cites: its
        ``digest`` and its metadata's ``hash`` go, and the metadata says
        ``digest_omitted: secret``, as the evidence collector says of a
        response that holds one. The cited content holds the secret too and
        may be no more than it, or than it and the text the redacted
        excerpt still shows around the marker, so a digest of it could be
        inverted by guessing (§6.7)."""
        ref, ref_changed = self.redact_text(anchor.ref)
        excerpt, excerpt_changed = (
            self.redact_text(anchor.excerpt)
            if anchor.excerpt is not None
            else (None, False)
        )
        metadata, pointers = self.redact(_plain(anchor.metadata))
        if not (ref_changed or excerpt_changed or pointers):
            return anchor
        if anchor.digest is not None or "hash" in metadata:
            metadata.pop("hash", None)
            metadata["digest_omitted"] = "secret"
        return dataclasses.replace(
            anchor, ref=ref, excerpt=excerpt, metadata=metadata, digest=None
        )

    def redact_anchor_data(self, value: Any) -> tuple[Any, list[str]]:
        """An evidence anchor in its JSON form (§6.5), redacted as
        :meth:`redact_anchor` redacts an anchor, and the JSON Pointers of the
        members changed (as :meth:`redact` gives them): once it held a
        secret, its ``digest`` and ``metadata.hash`` go and its ``metadata``
        says ``digest_omitted: secret``. ``packages/acs-core``'s
        ``redactAnchor`` does the same. A value that is not an object is
        redacted as any JSON value is."""
        out, pointers = self.redact(value)
        if not pointers or not isinstance(out, dict):
            return out, pointers
        metadata = out.get("metadata")
        meta = metadata if isinstance(metadata, dict) else None
        if "digest" in out or (meta is not None and "hash" in meta):
            out.pop("digest", None)
            kept = {k: v for k, v in (meta or {}).items() if k != "hash"}
            kept["digest_omitted"] = "secret"
            out["metadata"] = kept
        return out, pointers

    def _walk(
        self, value: Any, pointer: str, pointers: list[str], secret: bool = False
    ) -> Any:
        """``secret``: ``value`` is within a secret member, whose strings and
        numbers are redacted whole."""
        if isinstance(value, str):
            text, changed = self.redact_text(value)
            if changed:
                pointers.append(pointer)
            return text
        if isinstance(value, dict):
            # A name/value pair whose name is a secret member's.
            pair = not secret and _secret_pair(value)
            out: dict[str, Any] = {}
            for k, v in value.items():
                name, renamed = self.redact_text(str(k))
                if renamed:
                    # A name that holds a secret: never repeat another.
                    unique, n = name, 1
                    while unique in out or unique in value:
                        n += 1
                        unique = f"{name} ({n})"
                    name = unique
                here = f"{pointer}/{_pointer_token(name)}"
                if renamed:
                    pointers.append(here)
                member_secret = _member_secret(k, secret, pair)
                if member_secret and _secret_scalar(v):
                    out[name] = MARKER
                    if not renamed:
                        pointers.append(here)
                else:
                    out[name] = self._walk(v, here, pointers, member_secret)
            return out
        if isinstance(value, (list, tuple)):
            # A `[name, value]` tuple whose name is a secret member's.
            tuple_ = not secret and _secret_tuple(value)
            items = []
            for i, v in enumerate(value):
                here = f"{pointer}/{i}"
                item_secret = secret or (tuple_ and i == 1)
                if item_secret and _secret_scalar(v):
                    items.append(MARKER)
                    pointers.append(here)
                else:
                    items.append(self._walk(v, here, pointers, item_secret))
            return items
        # A number whose JSON text holds a registered value: replaced whole,
        # as the redaction of the JSON text would replace it.
        number = _number_text(value)
        if number is not None and any(v in number for v in self._values):
            pointers.append(pointer)
            return MARKER
        return value


def _number_text(value: Any) -> str | None:
    """A number's JSON text (``json.dumps``, as a store writes it), or None
    for anything that is not a number (a boolean is not one)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return json.dumps(value)


def _strings_in(value: Any, out: list[str], numbers: list[str] | None = None) -> None:
    """Every string in a JSON value, member names included; and, given
    ``numbers``, the JSON text of every number in it."""
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, Mapping):
        for k, v in value.items():
            out.append(str(k))
            _strings_in(v, out, numbers)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _strings_in(v, out, numbers)
    elif numbers is not None:
        text = _number_text(value)
        if text is not None:
            numbers.append(text)


def _plain(value: Any) -> Any:
    """JSON data from a read-only copy (mappings to dicts, tuples to
    lists), so that :meth:`Redactor.redact` walks it."""
    if isinstance(value, Mapping):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _replace_secret(m: re.Match[str]) -> str:
    """The match with its ``secret`` group replaced by the marker (a marker
    already there, or a match with no ``secret``, stays as it is)."""
    secret = m.group("secret")
    if secret is None or secret == MARKER:
        return m.group(0)
    start, end = m.start("secret") - m.start(), m.end("secret") - m.start()
    whole = m.group(0)
    return whole[:start] + MARKER + whole[end:]


DEFAULT_REDACTOR = Redactor()
"""A redactor with the default patterns and no registered value."""


def redact_text(text: str) -> tuple[str, bool]:
    """:meth:`Redactor.redact_text` of :data:`DEFAULT_REDACTOR`."""
    return DEFAULT_REDACTOR.redact_text(text)


def redact(value: Any) -> tuple[Any, list[str]]:
    """:meth:`Redactor.redact` of :data:`DEFAULT_REDACTOR`."""
    return DEFAULT_REDACTOR.redact(value)


def holds_secret(value: Any) -> bool:
    """:meth:`Redactor.holds_secret` of :data:`DEFAULT_REDACTOR`."""
    return DEFAULT_REDACTOR.holds_secret(value)


def holds_credential(value: Any) -> bool:
    """:meth:`Redactor.holds_credential` of :data:`DEFAULT_REDACTOR`."""
    return DEFAULT_REDACTOR.holds_credential(value)
