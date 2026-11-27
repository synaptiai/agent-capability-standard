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

:func:`check_merge` and :func:`check_split` are the merge and split checks
that RFC-0012 (a Draft for Standard 1.3.0) proposes for §7.3, held to
``tests/conformance/entities/merge.json``. Standard 1.2.0 states §7.3 as a
requirement on a host that merges or splits entities; no reference layer
merges or splits one, so nothing calls these checks for it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, NamedTuple

__all__ = [
    "ENTITY_ID",
    "EntityId",
    "IdentityCheck",
    "check_merge",
    "check_split",
    "class_index",
    "parse_entity_id",
    "taxonomy_classes",
]

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


# ---------------------------------------------------------------------------
# Merge and split checks (RFC-0012, proposed for Standard 1.3.0 §7.3)
# ---------------------------------------------------------------------------


class IdentityCheck(NamedTuple):
    """The outcome of a merge or split check.

    ``ok`` is true when the operation violates no constraint; ``lineage`` is
    then the record the host keeps of it. Otherwise ``reason`` is the token
    of the first constraint violated, in the order RFC-0012 lists them, and
    ``lineage`` is ``None``.
    """

    ok: bool
    reason: str | None
    message: str
    lineage: dict[str, Any] | None


def class_index(taxonomy: Mapping[str, Any]) -> dict[str, str]:
    """Map every class name and alias of a loaded ``entity_taxonomy.yaml`` to
    its class name: ``svc`` and ``service`` both give ``service``.

    Raises:
        ValueError: one name or alias belongs to two classes.
    """
    index: dict[str, str] = {}
    for group in (taxonomy.get("classes") or {}).values():
        if not isinstance(group, Mapping):
            continue
        for name, spec in group.items():
            names = [str(name)]
            if isinstance(spec, Mapping):
                names += [str(a) for a in spec.get("aliases") or []]
            for n in names:
                if index.setdefault(n, str(name)) != str(name):
                    raise ValueError(
                        f"{n!r} names both {index[n]!r} and {name!r} in the taxonomy"
                    )
    return index


class _Refused(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


def _resolve(name: Any, classes: Mapping[str, str]) -> str:
    """The class a ``type`` or an id's class part denotes."""
    if isinstance(name, str):
        if name in classes:
            return classes[name]
        if _VENDOR_CLASS.fullmatch(name):
            return name
    raise _Refused(
        "unknown_class",
        f"{name!r} is not a class or alias of the entity taxonomy, nor a vendor class x-…",
    )


def _id_class(entity_id: Any, classes: Mapping[str, str]) -> str:
    """Parse an id and give the class its class part denotes.

    The parser refuses a class part that is neither in ``classes`` nor a
    vendor class, so such an id is ``invalid_entity_id``, never
    ``unknown_class``.
    """
    try:
        parsed = parse_entity_id(entity_id, classes)
    except ValueError as exc:
        raise _Refused("invalid_entity_id", str(exc)) from None
    return classes.get(parsed.cls, parsed.cls)


def _entity_class(entity: Any, classes: Mapping[str, str]) -> str:
    """The class of an entity record, whose id and ``type`` must agree."""
    if not isinstance(entity, Mapping):
        raise _Refused("invalid_entity", f"{entity!r} is not an entity record")
    of_id = _id_class(entity.get("id"), classes)
    of_type = _resolve(entity.get("type"), classes)
    if of_id != of_type:
        raise _Refused(
            "class_mismatch",
            f"{entity.get('id')!r} names class {of_id!r} but its type "
            f"{entity.get('type')!r} is {of_type!r}",
        )
    return of_type


def _json_equal(a: Any, b: Any) -> bool:
    """Equality of JSON values: a boolean is not a number, and numbers are
    equal when their values are (``1`` and ``1.0``)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, int | float) and isinstance(b, int | float):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(
            _json_equal(x, y) for x, y in zip(a, b, strict=True)
        )
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        return a.keys() == b.keys() and all(_json_equal(a[k], b[k]) for k in a)
    return a is None and b is None


def _distinct_ids(ids: list[Any], what: str) -> None:
    seen: set[str] = set()
    for i in ids:
        if isinstance(i, str):
            if i in seen:
                raise _Refused("duplicate_id", f"{i!r} is named twice in {what}")
            seen.add(i)


def check_merge(
    entities: Iterable[Mapping[str, Any]],
    into: str,
    *,
    classes: Mapping[str, str],
    unique_attributes: Iterable[str],
) -> IdentityCheck:
    """Check a merge of entity records into one (RFC-0012, §7.3 for 1.3.0).

    Args:
        entities: The records merged, each with ``id``, ``type`` and
            ``attributes`` (world-state ``Entity``); at least two, with
            distinct ids.
        into: The id of the merged entity: one of the merged ids, or a new
            id of the same class.
        classes: Class names and aliases to class names
            (:func:`class_index`).
        unique_attributes: The attribute keys whose values identify an
            entity uniquely; the host supplies them.

    Returns:
        An :class:`IdentityCheck`. The constraints, checked in this order:
        ``too_few_entities``; each record valid (``invalid_entity``,
        ``invalid_entity_id``, ``unknown_class``, ``class_mismatch``);
        ``duplicate_id``; ``incompatible_types`` (the records resolve to
        different classes); ``conflicting_identifier`` (two records give a
        unique attribute different values; a missing or null value
        conflicts with none); ``into`` valid and of the records' class
        (``invalid_entity_id``, ``class_mismatch``).
    """
    records = list(entities)
    keys = list(unique_attributes)
    try:
        if len(records) < 2:
            raise _Refused(
                "too_few_entities", "a merge combines at least two entity records"
            )
        found = [_entity_class(e, classes) for e in records]
        ids = [e["id"] for e in records]
        _distinct_ids(ids, "the merge")
        if len(set(found)) > 1:
            raise _Refused(
                "incompatible_types",
                "the records are of different classes: "
                + ", ".join(sorted(set(found))),
            )
        for key in keys:
            first: tuple[str, Any] | None = None
            for e in records:
                attributes = e.get("attributes")
                value = attributes.get(key) if isinstance(attributes, Mapping) else None
                if value is None:
                    continue
                if first is None:
                    first = (e["id"], value)
                elif not _json_equal(first[1], value):
                    raise _Refused(
                        "conflicting_identifier",
                        f"{first[0]!r} and {e['id']!r} give the unique attribute "
                        f"{key!r} different values",
                    )
        cls = found[0]
        if _id_class(into, classes) != cls:
            raise _Refused("class_mismatch", f"{into!r} is not an id of class {cls!r}")
    except _Refused as refused:
        return IdentityCheck(False, refused.reason, refused.message, None)
    lineage = {"operation": "merge", "class": cls, "from": ids, "into": [into]}
    return IdentityCheck(True, None, f"merge into {into!r} allowed", lineage)


def check_split(
    entity: Mapping[str, Any],
    into: Iterable[Mapping[str, Any]],
    *,
    classes: Mapping[str, str],
) -> IdentityCheck:
    """Check a split of one entity record into several (RFC-0012, §7.3 for
    1.3.0).

    Args:
        entity: The record split (``id`` and ``type``).
        into: The records it becomes: at least two, with distinct new ids.
        classes: Class names and aliases to class names
            (:func:`class_index`).

    Returns:
        An :class:`IdentityCheck`. The constraints, checked in this order:
        the record split valid; ``too_few_entities``; each new record valid;
        ``duplicate_id``; ``reused_id`` (a new record keeps the split
        record's id); ``incompatible_types`` (a new record is of another
        class than the one split).
    """
    children = list(into)
    try:
        cls = _entity_class(entity, classes)
        if len(children) < 2:
            raise _Refused(
                "too_few_entities", "a split gives at least two entity records"
            )
        found = [_entity_class(c, classes) for c in children]
        ids = [c["id"] for c in children]
        _distinct_ids(ids, "the split")
        if entity["id"] in ids:
            raise _Refused(
                "reused_id",
                f"a record of the split keeps the split record's id {entity['id']!r}",
            )
        for child, child_cls in zip(children, found, strict=True):
            if child_cls != cls:
                raise _Refused(
                    "incompatible_types",
                    f"{child['id']!r} is of class {child_cls!r}, not {cls!r}",
                )
    except _Refused as refused:
        return IdentityCheck(False, refused.reason, refused.message, None)
    lineage = {"operation": "split", "class": cls, "from": [entity["id"]], "into": ids}
    return IdentityCheck(True, None, f"split of {entity['id']!r} allowed", lineage)
