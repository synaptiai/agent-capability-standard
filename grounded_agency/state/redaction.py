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
(:func:`encoded_forms`: JSON-escaped, once or twice, and percent-encoded),
then what its patterns recognise. The default
patterns (informative; ``tests/conformance/secrets/redact.json`` pins them,
and ``packages/acs-core/src/redact.ts`` holds the same ones) recognise:

- ``Authorization`` and ``Proxy-Authorization`` header values;
- ``Bearer`` tokens (8 or more token characters);
- the password of a URL's userinfo (``scheme://user:<secret>@``, the
  scheme a run of scheme characters that holds a letter, the user's name
  empty or not: ``redis://:<secret>@``);
- an assignment to a credential name (``password``, ``passwd``,
  ``passphrase``, ``pwd``, ``secret``, ``secret_key``, ``token``,
  ``api_key``, ``access_key``, ``client_secret``, ``private_key``, alone or
  at the end of a longer name such as ``DB_PASSWORD``, ``PGPASSWORD``,
  ``DJANGO_SECRET_KEY`` or ``access_token``) with ``=`` or ``:``, of 4 or
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
- PEM ``PRIVATE KEY`` blocks (the body);
- AWS access key ids, GitHub tokens, Slack tokens, ``sk-`` keys and JWTs;
- a header or credential given as a name/value pair or a ``[name, value]``
  tuple in JSON or code text (``"name": "Authorization", "value": "Basic
  ..."``, ``('Cookie', 'sid=...')``), its quotes escaped or not: its value,
  of 4 or more characters, read to its closing quote as above (a
  ``Cookie`` header's later cookies too).

Not read: a password given to a short option with no name attached
(``mysql -p<secret>``, ``sshpass -p <secret>``: ``-p`` means too many other
things to redact on its own), and a secret in base64 or another encoding
than those above, unless it is registered in that form too.

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
list (Node's ``rawHeaders``), a ``Cookie:`` header line in text. A member
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
credential-shaped values: a registered value, the key and token formats
above (PEM private keys, AWS, GitHub, Slack, ``sk-`` keys, JWTs, a bearer
token of 20 or more characters), the password of a URL's userinfo unless it
is a placeholder (``password``, ``<password>``, ``${DB_PASSWORD}``,
``****``), an ``Authorization`` or ``Proxy-Authorization`` header's value of
8 or more token characters mixing letters and digits (in a header line, or
given as a pair or tuple in text, as above), a command's user option's
password of 8 or more characters mixing letters and digits (``curl -u
admin:<value>``; ``docker run -u 1000:1000`` passes), and an assignment to
a credential name, or a credential option's value, that is quoted with no
whitespace and 8 or more characters, or unquoted, 12 or more characters,
mixing letters and digits (the quotes escaped or not, as above).
The plugin's ``hooks/secret_scan.sh`` applies the same rule to text, and
``tests/conformance/secrets/credentials.json`` pins it for the three. In
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

# Credential names: alone, or at the end of a longer name after `_` or `-`.
_NAMES = (
    r"password|passwd|passphrase|pwd|secret|secret[_-]?key|token|api[_-]?key"
    r"|access[_-]?key|client[_-]?secret|private[_-]?key"
)
# Whitespace, spelled out: `\s` differs between Python and ECMAScript, and
# the TypeScript redactor must agree with this one. Every pattern is ASCII
# (`re.ASCII`), so `\b` and case-insensitive matching are ASCII-only, as
# they are in an ECMAScript pattern without the `u` flag.
_WS = r"[ \t\n\r\f\v]"
_NOT_WS = r" \t\n\r\f\v"
# A URL's scheme: a run of scheme characters that holds a letter, read from
# the run's start (not after a scheme character), so a long run that is not
# followed by `://` is read once, not again from each letter in it.
_SCHEME = r"(?<![A-Za-z0-9+.-])[0-9+.-]*[A-Za-z][A-Za-z0-9+.-]*"
# A quote as JSON or code text writes it, or escaped (`\\"`, as JSON text
# inside a JSON string writes it, or escaped again: `\\\\\\"`).
_QUOTE = r"\\*[\"']"


def _value_char(excluded: str = "") -> str:
    """One character of a value: not whitespace, a quote, a backslash or one
    of ``excluded``, or a run of backslashes that no quote follows (an
    escaped quote ends the value, as a quote does)."""
    return rf"(?:[^{_NOT_WS}\"'\\{excluded}]|\\+(?![\\\"']))"


def _quoted_value(quote: str) -> str:
    """A value in ``quote`` quotes, whitespace and all, of 4 characters or
    more, read to its closing quote on its line (escaped or not), so a
    quoted passphrase is replaced whole. A character is not that quote, a
    backslash or a line break, or is a run of backslashes that no such quote
    follows (read once). With no closing quote on the line nothing matches,
    and the value is read as an unquoted one is."""
    return rf"(?P<secret>(?:[^{quote}\\\n\r]|\\+(?![\\{quote}])){{4,}})(?=\\*{quote})"


# A secret member's name (see _SECRET_MEMBER), quoted as JSON or code text
# quotes it.
_QUOTED_SECRET_NAME = (
    rf"[\"'][^{_NOT_WS}\"']*(?:{_NAMES}|authorization|cookies?){_QUOTE}"
)
# A header's scheme, which the value after it may start with.
_VALUE_SCHEME = rf"(?:(?:bearer|basic|token|digest|negotiate){_WS}+)?"
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
    rf"{_QUOTED_SECRET_NAME}{_WS}*,{_WS}*(?:{_QUOTE})?value(?:{_QUOTE})?{_WS}*[:=]"
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
    rf"(?<![A-Za-z0-9_-])(?:-[uU]{_OPTION_SEPARATOR}?|--(?:proxy-)?user"
    rf"{_OPTION_SEPARATOR})[^{_NOT_WS}:\"'\\]{{0,256}}:"
)
# ... and the same option up to the quote its value opens with.
_USER_OPTION_QUOTE_SEPARATOR = rf"(?:{_WS}+|=|(?:{_QUOTE})?{_WS}*,{_WS}*)"
_USER_OPTION_NAME = (
    rf"(?<![A-Za-z0-9_-])(?:-[uU]{_USER_OPTION_QUOTE_SEPARATOR}?|--(?:proxy-)?user"
    rf"{_USER_OPTION_QUOTE_SEPARATOR})"
)
# A command's option named for a credential (`--password`, `--api-key`,
# `--db-token`), and what separates it from a value given after blanks or as
# a list's next item; `--password=...` is an assignment.
_CREDENTIAL_OPTION_NAME = rf"(?<![A-Za-z0-9_-])--(?:[A-Za-z0-9]+[_-])*(?:{_NAMES})"
_CREDENTIAL_OPTION_SEPARATOR = rf"(?:{_WS}+|(?:{_QUOTE})?{_WS}*,{_WS}*)"
# ... up to its value, which is not another option.
_CREDENTIAL_OPTION = (
    rf"{_CREDENTIAL_OPTION_NAME}(?:{_WS}+(?:{_QUOTE})?|(?:{_QUOTE})?{_WS}*,{_WS}*"
    rf"{_QUOTE})(?!-)"
)
# An assignment to a credential name, up to its value.
_ASSIGN = rf"(?:{_NAMES})(?:{_QUOTE})?{_WS}*[:=]{_WS}*"


def _quoted_forms(
    prefix: str, after_quote: str = "", flags: re.RegexFlag = re.IGNORECASE
) -> tuple[re.Pattern[str], ...]:
    """The patterns of a value after ``prefix`` in double or single quotes
    (escaped or not), ``after_quote`` read first: the value is read to its
    closing quote, whitespace and all (see _quoted_value)."""
    return tuple(
        re.compile(
            rf"{prefix}\\*{quote}{after_quote}{_quoted_value(quote)}",
            re.ASCII | flags,
        )
        for quote in ('"', "'")
    )


DEFAULT_PATTERNS: tuple[re.Pattern[str], ...] = (
    # PEM private key blocks: the body. A header with no end after it
    # matches the rest of the text with no secret (nothing is replaced), so
    # the next header is not read again to the end of the text.
    re.compile(
        r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"
        r"(?:(?P<secret>[\s\S]+?)"
        r"-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----|[\s\S]*)",
        re.ASCII,
    ),
    # Authorization and Proxy-Authorization header values (after a scheme).
    re.compile(
        rf"(?<![A-Za-z0-9])(?:proxy-)?authorization(?:{_QUOTE})?{_WS}*[:=]{_WS}*"
        rf"(?:{_QUOTE})?(?:(?:bearer|basic|token|digest|negotiate){_WS}+)?"
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
    # Bearer tokens.
    re.compile(
        rf"(?<![A-Za-z0-9])bearer{_WS}+(?P<secret>[A-Za-z0-9._~+/=-]{{8,}})",
        re.ASCII | re.IGNORECASE,
    ),
    # The password of a URL's userinfo, the user's name empty or not
    # (`redis://:<secret>@`).
    re.compile(
        rf"{_SCHEME}://[^{_NOT_WS}/:@]*:(?P<secret>[^{_NOT_WS}/@]+)@",
        re.ASCII,
    ),
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
    re.compile(r"\b(?P<secret>(?:AKIA|ASIA)[A-Z0-9]{16})\b", re.ASCII),
    # GitHub tokens.
    re.compile(
        r"\b(?P<secret>gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})",
        re.ASCII,
    ),
    # Slack tokens.
    re.compile(r"\b(?P<secret>xox[abprs]-[A-Za-z0-9-]{10,})", re.ASCII),
    # sk- keys.
    re.compile(r"\b(?P<secret>sk-[A-Za-z0-9_-]{20,})", re.ASCII),
    # JWTs: three base64url parts, the first a JSON object's encoding,
    # starting at a word boundary. Read from the start of a run of base64url
    # characters to its first `eyJ` at a word boundary (the run's start or
    # after `-`), so a run is read once, not again from each `eyJ` in it.
    re.compile(
        r"(?<![A-Za-z0-9_-])(?:(?!eyJ)(?:[A-Za-z0-9_]|-(?!eyJ))*-)?"
        r"(?P<secret>eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)",
        re.ASCII,
    ),
)
"""The default patterns; each marks the secret with the group ``secret`` (a
match in which it takes no part replaces nothing). Each reads a text in time
in proportion to its length: no run of characters is read again from each of
its positions (tests/test_redaction.py times them on 1 MB)."""

# Credential shapes a refusal relies on (holds_credential): the formats of
# keys and tokens, no prose. hooks/secret_scan.sh holds the same ones.
_CREDENTIAL_SHAPES: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.ASCII),
    re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}", re.ASCII),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36}", re.ASCII),
    re.compile(r"github_pat_[A-Za-z0-9_]{22,}", re.ASCII),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}", re.ASCII),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}", re.ASCII),
    re.compile(rf"[Bb]earer{_WS}+[A-Za-z0-9._~+/=-]{{20,}}", re.ASCII),
    # Read from the start of a run to its first `eyJ` (whose first part is
    # the longest), so a run is read once.
    re.compile(
        r"(?<![A-Za-z0-9_-])(?:(?!eyJ)[A-Za-z0-9_-])*"
        r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
        re.ASCII,
    ),
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
    rf"{_SCHEME}://[^{_NOT_WS}/:@]*:(?P<value>[^{_NOT_WS}/@]+)@",
    re.ASCII,
)
# ... unless it is a placeholder (``password``, ``<password>``, ``${PW}``,
# ``****``).
_PLACEHOLDER = re.compile(
    r"[$<{*\[].*|password|passwd|pwd|pass|secret|token", re.ASCII | re.IGNORECASE
)
# An Authorization or Proxy-Authorization header's value, after its scheme:
# 8 or more token characters with letters and digits.
_AUTHORIZATION_VALUE = re.compile(
    rf"(?:proxy-)?authorization(?:{_QUOTE})?{_WS}*[:=]{_WS}*(?:{_QUOTE})?"
    rf"(?:(?:basic|bearer|token|digest|negotiate){_WS}+)?"
    r"(?P<value>[A-Za-z0-9._~+/=-]{8,})",
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


def _letters_and_digits(value: str) -> bool:
    return bool(re.search(r"[0-9]", value) and re.search(r"[A-Za-z]", value))


def _credential_text(text: str) -> bool:
    """Whether ``text`` holds a credential-shaped value."""
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
            _PAIR_VALUE_TEXT,
            _TUPLE_VALUE_TEXT,
        )
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


def _json_escaped(value: str, ascii_only: bool) -> str:
    """``value`` as a JSON string's contents: ``"``, ``\\`` and control
    characters escaped (``\\n`` and the other short forms, else
    ``\\u00XX``), and, when ``ascii_only``, each character past ASCII as
    ``\\uXXXX`` (a pair of them past the Basic Multilingual Plane)."""
    out: list[str] = []
    for ch in value:
        cp = ord(ch)
        if ch in _JSON_SHORT_ESCAPES:
            out.append(_JSON_SHORT_ESCAPES[ch])
        elif cp < 0x20 or (ascii_only and 0x7F < cp <= 0xFFFF):
            out.append(f"\\u{cp:04x}")
        elif ascii_only and cp > 0xFFFF:
            cp -= 0x10000
            out.append(f"\\u{0xD800 + (cp >> 10):04x}\\u{0xDC00 + (cp & 0x3FF):04x}")
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
    it); and percent-encoded (UTF-8, by each of the encodings of
    :data:`_PERCENT_ENCODINGS`, in upper-case hex, then in lower-case hex).
    A value with a lone surrogate has no UTF-8 and so no percent-encoded
    form. ``packages/acs-core``'s
    ``encodedForms`` gives the same forms in the same order."""
    once = _json_escaped(value, ascii_only=False)
    ascii_once = _json_escaped(value, ascii_only=True)
    forms = [
        value,
        once,
        ascii_once,
        once.replace("/", "\\/"),
        ascii_once.replace("/", "\\/"),
        _json_escaped(once, ascii_only=False),
        _json_escaped(ascii_once, ascii_only=False),
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
    (longest first), then each pattern's ``secret`` group."""

    def __init__(
        self,
        secret_values: Iterable[str] = (),
        patterns: Sequence[re.Pattern[str]] = DEFAULT_PATTERNS,
    ) -> None:
        self._values: list[str] = []
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

    def redact_text(self, text: str) -> tuple[str, bool]:
        """``text`` with each secret replaced, and whether anything was."""
        out = text
        for v in self._values:
            out = out.replace(v, MARKER)
        for p in self._patterns:
            out = p.sub(_replace_secret, out)
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
        its JSON text, so ``{"api_key": "..."}`` is an assignment."""
        strings: list[str] = []
        _strings_in(value, strings)
        if any(v in s for v in self._values for s in strings):
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
        return value


def _strings_in(value: Any, out: list[str]) -> None:
    """Every string in a JSON value, member names included."""
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, Mapping):
        for k, v in value.items():
            out.append(str(k))
            _strings_in(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _strings_in(v, out)


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
