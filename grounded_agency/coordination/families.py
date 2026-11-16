"""Model families (STANDARD v1.2 §5.15).

A model family names a provider's line of models, without version, size,
date or variant. It is written in lowercase (``[a-z][a-z0-9_-]*``) and
compared by exact (code-point) equality wherever it appears. A host that
attests a family derives it from the identifier of the model the delegate
ran on, by :func:`model_family`; ``tests/conformance/families/derive.json``
pins the rule.
"""

from __future__ import annotations

import re

_FAMILY = re.compile(r"[a-z][a-z0-9_-]*", re.ASCII)
_LETTERS = re.compile(r"[A-Za-z]*", re.ASCII)
_STOP = re.compile(r"[0-9-]", re.ASCII)


def is_model_family(value: str) -> bool:
    """Whether ``value`` is written as a model family: ``[a-z][a-z0-9_-]*``."""
    return _FAMILY.fullmatch(value) is not None


def model_family(model_id: str) -> str | None:
    """The model family a host derives from a model identifier (§5.15):

    1. the part of the identifier after its last ``/``;
    2. of that, the part after the last ``.`` or ``:`` that comes before its
       first ASCII digit or ``-`` (any ``.`` or ``:`` when it has neither);
    3. the leading run of ASCII letters of the rest, lowercased.

    None when that run is empty: the host attests no family.
    """
    rest = model_id.rsplit("/", 1)[-1]
    stop = _STOP.search(rest)
    head = rest[: stop.start()] if stop else rest
    cut = max(head.rfind("."), head.rfind(":"))
    if cut >= 0:
        rest = rest[cut + 1 :]
    letters = _LETTERS.match(rest)
    family = letters.group(0).lower() if letters else ""
    return family or None
