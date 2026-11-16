"""Entity ids of the world state (STANDARD v1.2 §7.1).

An entity's id is written ``<class>:<namespace>/<local_id>``: the class is
the entity's ``type`` (a class name or alias of
``schemas/entity_taxonomy.yaml``, or a vendor class ``x-…``); the namespace
is one or more ``/``-separated segments, outermost first; a segment holds no
``/``, ``:``, white space (any character JSON Schema's ``\\s`` matches, so
U+00A0 and U+2028 too) or control character (U+0000-U+001F,
U+007F-U+009F). ``id_convention.pattern`` of
the taxonomy is the grammar, and ``tests/conformance/entities/ids.json`` fixes
it. Standard library only.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, NamedTuple

__all__ = ["ENTITY_ID", "EntityId", "parse_entity_id", "taxonomy_classes"]

# What a segment never holds besides "/" and ":": the control characters
# (U+0000-U+001F, U+007F-U+009F) and the white space JSON Schema's \s
# matches (ECMA-262's WhiteSpace and LineTerminator), named one by one so the
# pattern means the same in every dialect.
_NOT_IN_SEGMENT = (
    r"\x00-\x20\x7f-\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)

ENTITY_ID = re.compile(
    rf"[a-z][a-z0-9_-]*:[^/:{_NOT_IN_SEGMENT}]+(?:/[^/:{_NOT_IN_SEGMENT}]+)+"
)
"""The grammar of §7.1 (``id_convention.pattern`` without its anchors)."""

_VENDOR_CLASS = re.compile(r"x-[a-z0-9][a-z0-9_-]*", re.ASCII)


class EntityId(NamedTuple):
    """A parsed entity id."""

    cls: str
    """The class part: the entity's ``type``, a class name or an alias."""
    namespace: tuple[str, ...]
    """The namespace segments, outermost first."""
    local_id: str
    """The entity's identifier within the namespace."""


def taxonomy_classes(taxonomy: Mapping[str, Any]) -> frozenset[str]:
    """Every class name and alias of a loaded ``entity_taxonomy.yaml``, of
    both groups (``digital`` and ``real_world``)."""
    names: set[str] = set()
    for group in (taxonomy.get("classes") or {}).values():
        if not isinstance(group, Mapping):
            continue
        for name, spec in group.items():
            names.add(str(name))
            if isinstance(spec, Mapping):
                names.update(str(a) for a in spec.get("aliases") or [])
    return frozenset(names)


def parse_entity_id(text: str, classes: Iterable[str] | None = None) -> EntityId:
    """Parse an entity id (§7.1).

    Args:
        text: The id.
        classes: The class names and aliases allowed
            (:func:`taxonomy_classes`). ``None``: any class the grammar
            admits. A vendor class (``x-`` then a lower-case letter or digit)
            is always allowed.

    Raises:
        ValueError: ``text`` is not an id of the grammar, or its class is
            neither one of ``classes`` nor a vendor class.
    """
    if not isinstance(text, str) or ENTITY_ID.fullmatch(text) is None:
        raise ValueError(
            f"{text!r} is not an entity id <class>:<namespace>/<local_id> (§7.1)"
        )
    cls, rest = text.split(":", 1)
    if (
        classes is not None
        and cls not in set(classes)
        and not _VENDOR_CLASS.fullmatch(cls)
    ):
        raise ValueError(
            f"{cls!r} is not a class or alias of the entity taxonomy, nor a vendor class x-…"
        )
    *namespace, local_id = rest.split("/")
    return EntityId(cls, tuple(namespace), local_id)
