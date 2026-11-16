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

A refusal is another matter: ``persist`` data or an ``audit`` record that
holds a secret is refused, not redacted (§6.7), and a refusal of ordinary
project knowledge (``token: rotate monthly``) would cost much.
:meth:`Redactor.holds_credential` therefore recognises only
credential-shaped values: a registered value, the key and token formats
above (PEM private keys, AWS, GitHub, Slack, ``sk-`` keys, JWTs, a bearer
token of 20 or more characters), and an assignment to a credential name
whose value is quoted with no whitespace and 8 or more characters, or
unquoted, 12 or more characters, mixing letters and digits. The plugin's
``hooks/secret_scan.sh`` applies the same rule.
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
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}", re.ASCII),
)
_ASSIGN = rf"(?:{_NAMES})[\"']?{_WS}*[:=]{_WS}*"
# A quoted value with no whitespace, 8 or more characters.
_QUOTED_CREDENTIAL = re.compile(
    rf"{_ASSIGN}[\"'][^{_NOT_WS}\"']{{8,}}[\"']", re.ASCII | re.IGNORECASE
)
# An unquoted value of 12 or more characters with letters and digits.
_UNQUOTED_VALUE = re.compile(
    rf"{_ASSIGN}(?P<value>[^{_NOT_WS}\"']{{12,}})", re.ASCII | re.IGNORECASE
)


def _credential_text(text: str) -> bool:
    """Whether ``text`` holds a credential-shaped value."""
    if any(p.search(text) for p in _CREDENTIAL_SHAPES):
        return True
    if _QUOTED_CREDENTIAL.search(text):
        return True
    return any(
        re.search(r"[0-9]", m.group("value"))
        and re.search(r"[A-Za-z]", m.group("value"))
        for m in _UNQUOTED_VALUE.finditer(text)
    )


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
        nothing changes, else a new (unfrozen) anchor."""
        ref, ref_changed = self.redact_text(anchor.ref)
        excerpt, excerpt_changed = (
            self.redact_text(anchor.excerpt)
            if anchor.excerpt is not None
            else (None, False)
        )
        metadata, pointers = self.redact(_plain(anchor.metadata))
        if not (ref_changed or excerpt_changed or pointers):
            return anchor
        return dataclasses.replace(anchor, ref=ref, excerpt=excerpt, metadata=metadata)

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


def holds_credential(value: Any) -> bool:
    """:meth:`Redactor.holds_credential` of :data:`DEFAULT_REDACTOR`."""
    return DEFAULT_REDACTOR.holds_credential(value)
