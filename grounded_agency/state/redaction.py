"""Redaction of secrets (STANDARD v1.2 §6.7).

A secret never enters a record, an evidence anchor, a notification, a
diagnostic, a trace or persisted data. An implementation that would write a
value holding one redacts it: each secret, or the part of a string that is
one, becomes the marker ``[REDACTED]``. Redaction is a transform with
documented loss (§3.2); :meth:`Redactor.redact` returns the JSON Pointers
(RFC 6901) of the members it changed, which a canonical event may list as
``redactions`` (§6.2).

A :class:`Redactor` replaces the values registered with it (the host's own
secrets, longest first), then what its patterns recognise. The default
patterns (informative; ``tests/conformance/secrets/redact.json`` pins them,
and ``packages/acs-core/src/redact.ts`` holds the same ones) recognise:

- ``Authorization`` and ``Proxy-Authorization`` header values;
- ``Bearer`` tokens (8 or more token characters);
- the password of a URL's userinfo (``scheme://user:<secret>@``);
- an assignment to a credential name (``password``, ``passwd``, ``pwd``,
  ``secret``, ``token``, ``api_key``, ``access_key``, ``client_secret``,
  ``private_key``, alone or at the end of a longer name such as
  ``DB_PASSWORD`` or ``access_token``) with ``=`` or ``:``, of 4 or more
  characters, in assignments, query strings and JSON text;
- PEM ``PRIVATE KEY`` blocks (the body);
- AWS access key ids, GitHub tokens, Slack tokens, ``sk-`` keys and JWTs.

In a JSON value, a string member whose name is a credential name (as above)
is redacted whole. The assignment rule is deliberately broad: replacing a
word of prose costs little where a secret would cost much.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

__all__ = [
    "DEFAULT_PATTERNS",
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
    r"password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key"
    r"|client[_-]?secret|private[_-]?key"
)
# Whitespace, spelled out: `\s` differs between Python and ECMAScript, and
# the TypeScript redactor must agree with this one. Every pattern is ASCII
# (`re.ASCII`), so `\b` and case-insensitive matching are ASCII-only, as
# they are in an ECMAScript pattern without the `u` flag.
_WS = r"[ \t\n\r\f\v]"
_NOT_WS = r" \t\n\r\f\v"

DEFAULT_PATTERNS: tuple[re.Pattern[str], ...] = (
    # PEM private key blocks: the body.
    re.compile(
        r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"
        r"(?P<secret>[\s\S]+?)"
        r"-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----",
        re.ASCII,
    ),
    # Authorization and Proxy-Authorization header values (after a scheme).
    re.compile(
        rf"(?<![A-Za-z0-9])(?:proxy-)?authorization[\"']?{_WS}*[:=]{_WS}*[\"']?"
        rf"(?:(?:bearer|basic|token|digest|negotiate){_WS}+)?"
        rf"(?P<secret>[^{_NOT_WS}\"',;]+)",
        re.ASCII | re.IGNORECASE,
    ),
    # Bearer tokens.
    re.compile(
        rf"(?<![A-Za-z0-9])bearer{_WS}+(?P<secret>[A-Za-z0-9._~+/=-]{{8,}})",
        re.ASCII | re.IGNORECASE,
    ),
    # The password of a URL's userinfo.
    re.compile(
        rf"\b[A-Za-z][A-Za-z0-9+.-]*://[^{_NOT_WS}/:@]+:(?P<secret>[^{_NOT_WS}/@]+)@",
        re.ASCII,
    ),
    # Assignments to a credential name, in code, query strings and JSON text.
    re.compile(
        rf"(?<![A-Za-z0-9])(?:{_NAMES})[\"']?{_WS}*[=:]{_WS}*[\"']?"
        rf"(?P<secret>[^{_NOT_WS}\"'&,;]{{4,}})",
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
    # JWTs: three base64url parts, the first a JSON object's encoding.
    re.compile(
        r"\b(?P<secret>eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)", re.ASCII
    ),
)
"""The default patterns; each marks the secret with the group ``secret``."""

# A member name that is a credential name, alone or ending a longer name.
_SECRET_MEMBER = re.compile(
    rf"(?:.*[_-])?(?:{_NAMES})", re.ASCII | re.IGNORECASE | re.DOTALL
)


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
        """Register a secret value; one shorter than four characters is
        ignored."""
        if not isinstance(value, str):
            raise TypeError(f"a secret value is a string, not {type(value).__name__}")
        if len(value) < MIN_SECRET_LENGTH or value in self._values:
            return
        self._values.append(value)
        self._values.sort(key=len, reverse=True)

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

    def _walk(self, value: Any, pointer: str, pointers: list[str]) -> Any:
        if isinstance(value, str):
            text, changed = self.redact_text(value)
            if changed:
                pointers.append(pointer)
            return text
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for k, v in value.items():
                here = f"{pointer}/{_pointer_token(str(k))}"
                if (
                    isinstance(v, str)
                    and len(v) >= MIN_SECRET_LENGTH
                    and v != MARKER
                    and _SECRET_MEMBER.fullmatch(str(k))
                ):
                    out[k] = MARKER
                    pointers.append(here)
                else:
                    out[k] = self._walk(v, here, pointers)
            return out
        if isinstance(value, (list, tuple)):
            return [
                self._walk(v, f"{pointer}/{i}", pointers) for i, v in enumerate(value)
            ]
        return value


def _replace_secret(m: re.Match[str]) -> str:
    """The match with its ``secret`` group replaced by the marker (a marker
    already there stays as it is)."""
    secret = m.group("secret")
    if secret == MARKER:
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
