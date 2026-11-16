"""Step domains (STANDARD v1.2 §5.2.4).

A step's ``domain`` names the variant of its capability the host runs. It is
a *domain id*: lowercase segments joined by ``.``, each
``[a-z0-9][a-z0-9_]*``. A host that serves a capability through
implementations each for one domain id, or for none, selects the one for a
step with :func:`select_implementation`; ``tests/conformance/domains/match.json``
pins the rule. A host's ``invoke_capability`` calls it with the action's
``domain``.
"""

from __future__ import annotations

import re
from collections.abc import Collection

DOMAIN_ID = re.compile(r"[a-z0-9][a-z0-9_]*(?:\.[a-z0-9][a-z0-9_]*)*", re.ASCII)


def is_domain_id(value: str) -> bool:
    """Whether ``value`` is a domain id."""
    return DOMAIN_ID.fullmatch(value) is not None


class UnsupportedDomain(LookupError):
    """No implementation serves the step's domain: the step fails (R402),
    and the host's ``Error`` response carries the reason
    ``unsupported_domain`` (§5.19.7)."""

    reason = "unsupported_domain"

    def __init__(self, domain: str | None) -> None:
        self.domain = domain
        what = f"domain '{domain}'" if domain is not None else "a step without a domain"
        super().__init__(f"no implementation serves {what}")


def select_implementation(
    domain: str | None, available: Collection[str | None]
) -> str | None:
    """The implementation a host selects for a step's ``domain`` among
    ``available`` (§5.2.4), by exact (code-point) comparison: the step's
    domain; else the longest proper prefix of it that ends before a ``.``;
    else the implementation for no domain (``None``, or ``""``, in
    ``available``). Returns the key selected, ``None`` for the domain-less
    implementation.

    Raises:
        UnsupportedDomain: When none serves the step.
    """
    keys = set(available)
    domainless = None in keys or "" in keys
    if domain is not None:
        candidate = domain
        while True:
            if candidate in keys:
                return candidate
            cut = candidate.rfind(".")
            if cut < 0:
                break
            candidate = candidate[:cut]
    if domainless:
        return None
    raise UnsupportedDomain(domain)
