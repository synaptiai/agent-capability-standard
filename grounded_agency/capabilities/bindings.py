"""
Tool binding records (STANDARD 1.2.0 section 5.18.1 to 5.18.4).

A tool binding states which ontology capability a tool performs and which
safety flags it declares (``schemas/interop/tool_binding.schema.json``). A
record describes; the code that loads it computes the effective flags from
its own ontology and enforces them. This module loads a set of records
(:func:`load_bindings`) and checks the tools a host offers a model against
them (:func:`check_offered`). The TypeScript package's ``checkBindings``
(``packages/acs-core/src/binding.ts``) implements the same rules in the same
order, and both pass the binding fixtures in ``tests/conformance/bindings/``.

Loading a set of records:

1. Each record is read in full (S303 for a member of the wrong type or
   value, or an unknown member whose name does not start with ``x-``; S304
   for a missing required one). A record that cannot be read is not loaded.
2. Two records for one tool are V110, and neither is loaded.
3. A cited ``standard`` this implementation does not support, or an
   ``ontology`` of another major, is V109.
4. A ``capability`` or ``additional_capabilities`` entry the ontology does
   not define is V101.
5. ``invokes``: a cycle is V105, a name that resolves to no loaded binding
   V107; the composite is not loaded.
6. The effective flags are the strictest, flag by flag, of the declared
   ``flags``, the ontology's flags of every capability the record names, and
   the effective flags of every binding it invokes, transitively. A declared
   flag weaker than its capabilities' is W602 and has no effect, except
   ``mutation: false`` on a single ``mutation_overridable`` capability.
7. The prerequisites are the ``from`` capabilities of the ``requires`` edges
   into every capability the record names (not those of its invokes: a
   nested call is checked on its own prerequisites).

A tool whose record is not loaded is unbound: the strictest case
(section 5.18.2).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..errors import ErrorCode, ValidationError
from .mapper import RISK_LEVELS, ToolMapping

__all__ = [
    "ApprovalPolicy",
    "ToolBinding",
    "check_offered",
    "duration_seconds",
    "load_bindings",
    "parse_record",
]

_RISK_ORDER: dict[str, int] = {level: n for n, level in enumerate(RISK_LEVELS)}
_FLAG_NAMES = ("risk", "mutation", "requires_checkpoint", "requires_approval")

# The members of a tool binding record, in the schema's order.
_MEMBERS: tuple[str, ...] = (
    "tool",
    "standard",
    "ontology",
    "destination",
    "capability",
    "domain",
    "flags",
    "additional_capabilities",
    "classifier",
    "invokes",
    "approval",
    "control",
)
# The members a control-only record may not have (section 5.18.3).
_NOT_WITH_CONTROL: tuple[str, ...] = (
    "capability",
    "domain",
    "flags",
    "additional_capabilities",
    "classifier",
    "invokes",
    "approval",
    "destination",
)
_VERSION = re.compile(r"^\d+\.\d+(\.\d+)?$")
_POINTER = re.compile(r"^(/([^~/]|~[01])*)*$")


@dataclass(frozen=True, slots=True)
class ApprovalPolicy:
    """How approval of a call is counted (section 5.18.7): a binding's
    ``approval`` member."""

    min_approvers: int = 1
    role: str | None = None
    expires_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class ToolBinding:
    """One tool binding record, read in full (section 5.18.1)."""

    tool: str
    ontology: str
    standard: str | None = None
    capability: str | None = None
    domain: str | None = None
    flags: Mapping[str, Any] = field(default_factory=dict)
    additional_capabilities: tuple[str, ...] = ()
    classifier: str | None = None
    invokes: tuple[str, ...] = ()
    approval: ApprovalPolicy | None = None
    control: bool = False
    destination: str | None = None

    @property
    def capabilities(self) -> tuple[str, ...]:
        """Every capability the record names, its primary one first."""
        if self.capability is None:
            return ()
        return (self.capability, *self.additional_capabilities)


def duration_seconds(text: str) -> float:
    """A duration of the section 5.10.1 grammar in seconds.

    Raises:
        ValueError: If ``text`` is not a duration.
    """
    from .. import _core

    if not isinstance(text, str):
        raise ValueError(f"{text!r} is not a duration")
    return float(_core.duration_ms(text)) / 1000.0


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_record(
    record: Any,
) -> tuple[ToolBinding | None, list[ValidationError]]:
    """Read one record in full, without the ontology.

    Returns the binding, or ``None`` and the S303 / S304 diagnostics that
    stop it loading. ``location`` holds ``tool`` (``""`` when the record has
    no readable name) and ``field``, the member's path.
    """
    errors: list[ValidationError] = []
    if not isinstance(record, Mapping):
        errors.append(
            ValidationError(
                ErrorCode.SCHEMA_VALIDATION_FAILED,
                "a tool binding must be a JSON object",
                {"tool": "", "field": ""},
            )
        )
        return None, errors

    raw_tool = record.get("tool")
    tool_name = raw_tool if isinstance(raw_tool, str) else ""

    def wrong(member: str, message: str) -> None:
        errors.append(
            ValidationError(
                ErrorCode.SCHEMA_VALIDATION_FAILED,
                f"tool binding '{tool_name}': {message}",
                {"tool": tool_name, "field": member},
            )
        )

    def missing(member: str, why: str = "") -> None:
        errors.append(
            ValidationError(
                ErrorCode.MISSING_REQUIRED_FIELD,
                f"tool binding '{tool_name}' has no '{member}'{why}",
                {"tool": tool_name, "field": member},
            )
        )

    for key in record:
        if not isinstance(key, str):
            wrong("", f"member name {key!r} is not a string")
        elif key not in _MEMBERS and not key.startswith("x-"):
            wrong(key, f"unknown member '{key}' (vendor data starts with 'x-')")

    if "tool" not in record:
        missing("tool")
    elif not isinstance(raw_tool, str) or not raw_tool:
        wrong("tool", "'tool' must be a non-empty string")

    for member in ("ontology", "standard"):
        if member not in record:
            if member == "ontology":
                missing("ontology")
            continue
        value = record[member]
        if not isinstance(value, str) or not _VERSION.match(value):
            wrong(
                member,
                f"'{member}' must be a version MAJOR.MINOR[.PATCH], not {value!r}",
            )

    if "destination" in record:
        value = record["destination"]
        if not isinstance(value, str) or not _POINTER.match(value):
            wrong("destination", "'destination' must be an RFC 6901 JSON pointer")

    if "capability" in record:
        value = record["capability"]
        # A string the ontology does not define is V101, reported with the
        # ontology (load_bindings); here only the type is checked.
        if not isinstance(value, str) or not value:
            wrong("capability", f"'capability' must be a capability id, not {value!r}")

    for member in ("domain", "classifier"):
        if member in record:
            value = record[member]
            if not isinstance(value, str) or not value:
                wrong(member, f"'{member}' must be a non-empty string")

    flags: dict[str, Any] = {}
    if "flags" in record:
        value = record["flags"]
        if not isinstance(value, Mapping):
            wrong("flags", "'flags' must be an object")
        else:
            for key, flag in value.items():
                path = f"flags/{key}"
                if key == "risk":
                    if not isinstance(flag, str) or flag not in _RISK_ORDER:
                        wrong(path, f"'risk' must be one of {', '.join(RISK_LEVELS)}")
                        continue
                elif key in _FLAG_NAMES:
                    if not isinstance(flag, bool):
                        wrong(path, f"'{key}' must be true or false, not {flag!r}")
                        continue
                else:
                    wrong(path, f"unknown flag '{key}'")
                    continue
                flags[key] = flag

    additional: tuple[str, ...] = ()
    if "additional_capabilities" in record:
        value = record["additional_capabilities"]
        if (
            not isinstance(value, list)
            or not value
            or not all(isinstance(v, str) and v for v in value)
        ):
            wrong(
                "additional_capabilities",
                "'additional_capabilities' must be a non-empty list of capability ids",
            )
        elif len(set(value)) != len(value):
            wrong("additional_capabilities", "'additional_capabilities' repeats an id")
        else:
            additional = tuple(value)

    invokes: tuple[str, ...] = ()
    if "invokes" in record:
        value = record["invokes"]
        if not isinstance(value, list) or not all(
            isinstance(v, str) and v for v in value
        ):
            wrong("invokes", "'invokes' must be a list of tool names")
        elif len(set(value)) != len(value):
            wrong("invokes", "'invokes' repeats a name")
        else:
            invokes = tuple(value)

    approval: ApprovalPolicy | None = None
    if "approval" in record:
        value = record["approval"]
        if not isinstance(value, Mapping):
            wrong("approval", "'approval' must be an object")
        else:
            ok = True
            for key in value:
                if key not in ("min_approvers", "role", "expires"):
                    wrong(f"approval/{key}", f"unknown member 'approval.{key}'")
                    ok = False
            min_approvers = value.get("min_approvers", 1)
            if not _is_int(min_approvers) or min_approvers < 1:
                wrong(
                    "approval/min_approvers",
                    "'approval.min_approvers' must be an integer of at least 1",
                )
                ok = False
            role = value.get("role")
            if role is not None and (not isinstance(role, str) or not role):
                wrong("approval/role", "'approval.role' must be a non-empty string")
                ok = False
            expires: float | None = None
            if "expires" in value:
                try:
                    expires = duration_seconds(value["expires"])
                except ValueError as e:
                    wrong("approval/expires", f"'approval.expires': {e}")
                    ok = False
                else:
                    if expires <= 0:
                        wrong(
                            "approval/expires",
                            "'approval.expires' must be a duration longer than zero",
                        )
                        ok = False
            if ok:
                approval = ApprovalPolicy(
                    min_approvers=min_approvers, role=role, expires_seconds=expires
                )

    control = False
    if "control" in record:
        if record["control"] is not True:
            wrong("control", "'control' must be true when present")
        else:
            control = True
            for member in _NOT_WITH_CONTROL:
                if member in record:
                    wrong(
                        member,
                        f"a control-only record (control: true) has no '{member}'",
                    )
    if not control and "capability" not in record and "control" not in record:
        missing("capability", " and is not control-only (control: true)")

    if errors:
        return None, errors
    return (
        ToolBinding(
            tool=tool_name,
            ontology=record["ontology"],
            standard=record.get("standard"),
            capability=record.get("capability"),
            domain=record.get("domain"),
            flags=flags,
            additional_capabilities=additional,
            classifier=record.get("classifier"),
            invokes=invokes,
            approval=approval,
            control=control,
            destination=record.get("destination"),
        ),
        [],
    )


@dataclass(frozen=True, slots=True)
class _Flags:
    risk: str
    mutation: bool
    requires_checkpoint: bool
    requires_approval: bool

    def join(self, other: _Flags) -> _Flags:
        return _Flags(
            risk=max(self.risk, other.risk, key=_RISK_ORDER.__getitem__),
            mutation=self.mutation or other.mutation,
            requires_checkpoint=self.requires_checkpoint or other.requires_checkpoint,
            requires_approval=self.requires_approval or other.requires_approval,
        )


_NO_FLAGS = _Flags("low", False, False, False)


def _flags_of(mapping: ToolMapping) -> _Flags:
    return _Flags(
        mapping.risk,
        mapping.mutation,
        mapping.requires_checkpoint,
        mapping.requires_approval,
    )


def _own_flags(
    binding: ToolBinding, nodes: Mapping[str, Any]
) -> tuple[_Flags, list[ValidationError]]:
    """The flags of the capabilities a record names, combined with its
    declaration (step 6, without ``invokes``), and the W602 reports."""
    caps = binding.capabilities
    base = _NO_FLAGS
    for cap in caps:
        node = nodes[cap]
        base = base.join(
            _Flags(
                node.risk if node.risk in _RISK_ORDER else "high",
                bool(node.mutation),
                bool(node.requires_checkpoint),
                bool(node.requires_approval),
            )
        )
    declared = binding.flags
    reports: list[ValidationError] = []

    def downgrade(flag: str, message: str) -> None:
        reports.append(
            ValidationError(
                ErrorCode.SAFETY_FLAG_DOWNGRADE,
                f"tool '{binding.tool}': {message}",
                {"tool": binding.tool, "capability": caps[0], "field": flag},
            )
        )

    risk = base.risk
    if "risk" in declared:
        if _RISK_ORDER[declared["risk"]] > _RISK_ORDER[risk]:
            risk = declared["risk"]
        elif _RISK_ORDER[declared["risk"]] < _RISK_ORDER[risk]:
            downgrade(
                "risk",
                f"the ontology declares risk={base.risk} but the tool declares "
                f"risk={declared['risk']}; the ontology value applies",
            )

    mutation = base.mutation
    if declared.get("mutation") is True:
        mutation = True
    elif declared.get("mutation") is False and base.mutation:
        node = nodes[caps[0]]
        if len(caps) == 1 and node.mutation_overridable:
            mutation = False  # the one weaker declaration honoured (section 4.4)
        else:
            downgrade(
                "mutation",
                "the ontology declares mutation=true but the tool declares "
                "mutation=false; the ontology value applies (the call is "
                "treated as a mutation)",
            )

    def boolean(flag: str, ontology: bool, why: str) -> bool:
        value = declared.get(flag)
        if value is False and ontology:
            downgrade(
                flag,
                f"the ontology declares {flag}=true but the tool declares "
                f"{flag}=false; the ontology value applies ({why})",
            )
        return ontology or value is True

    return (
        _Flags(
            risk,
            mutation,
            boolean(
                "requires_checkpoint",
                base.requires_checkpoint,
                "F501 if no checkpoint precedes it",
            ),
            boolean(
                "requires_approval",
                base.requires_approval,
                "F502 if it is not approved",
            ),
        ),
        reports,
    )


def _cycles(graph: Mapping[str, Sequence[str]]) -> list[list[str]]:
    """The strongly connected components of ``graph`` that hold a cycle,
    each in the order its members were first reached (Tarjan)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    found: list[list[str]] = []
    counter = 0

    def visit(node: str) -> None:
        nonlocal counter
        index[node] = low[node] = counter
        counter += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph.get(node, ()):
            if target not in graph:
                continue
            if target not in index:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in on_stack:
                low[node] = min(low[node], index[target])
        if low[node] == index[node]:
            component: list[str] = []
            while True:
                member = stack.pop()
                on_stack.discard(member)
                component.append(member)
                if member == node:
                    break
            if len(component) > 1 or node in graph.get(node, ()):
                found.append(sorted(component, key=index.__getitem__))

    for node in graph:
        if node not in index:
            visit(node)
    return found


def load_bindings(
    records: Iterable[Any],
    nodes: Mapping[str, Any],
    requires: Iterable[tuple[str, str]],
    ontology_version: str,
    known: Mapping[str, ToolMapping] | None = None,
) -> tuple[dict[str, ToolMapping], list[ValidationError]]:
    """Load a set of tool binding records against an ontology.

    Args:
        records: The records of the set.
        nodes: The ontology's capability nodes by id (objects with ``risk``,
            ``mutation``, ``requires_checkpoint``, ``requires_approval`` and
            ``mutation_overridable``).
        requires: The ontology's ``requires`` edges as ``(from, to)``.
        ontology_version: The ontology's ``meta.version``.
        known: Mappings already loaded, which an ``invokes`` name may
            resolve to.

    Returns:
        The loaded mappings by tool name, and every diagnostic: errors for
        the records that were not loaded, W602 for those that were.
    """
    from .. import _core

    known = known or {}
    records = list(records)
    requires = list(requires)
    diagnostics: list[ValidationError] = []
    parsed: list[ToolBinding] = []
    for record in records:
        binding, errors = parse_record(record)
        diagnostics.extend(errors)
        if binding is not None:
            parsed.append(binding)

    # 2. Two records for one tool: neither is loaded. A record that could not
    # be read counts too, since it could have declared something stricter.
    counts: dict[str, int] = {}
    for record in records:
        tool = record.get("tool") if isinstance(record, Mapping) else None
        if isinstance(tool, str) and tool:
            counts[tool] = counts.get(tool, 0) + 1
    for binding in parsed:
        counts.setdefault(binding.tool, 1)
    candidates: dict[str, ToolBinding] = {}
    for binding in parsed:
        if counts[binding.tool] > 1:
            diagnostics.append(
                ValidationError(
                    ErrorCode.DUPLICATE_BINDING,
                    f"two tool bindings name the tool '{binding.tool}'; "
                    f"neither is loaded",
                    {"tool": binding.tool, "field": "tool"},
                )
            )
            continue
        # 3. Versions it cites.
        cited = _core.check_cited_versions(
            binding.standard, binding.ontology, ontology_version
        )
        if cited:
            for d in cited:
                diagnostics.append(
                    ValidationError(
                        ErrorCode(d["code"]),
                        f"tool binding '{binding.tool}': {d['message']}",
                        {"tool": binding.tool, **(d.get("location") or {})},
                    )
                )
            continue
        # 4. Capabilities the ontology defines.
        unknown = [c for c in binding.capabilities if c not in nodes]
        if unknown:
            for cap in unknown:
                member = (
                    "capability"
                    if cap == binding.capability
                    else "additional_capabilities"
                )
                diagnostics.append(
                    ValidationError(
                        ErrorCode.UNKNOWN_CAPABILITY,
                        f"tool '{binding.tool}' declares capability {cap!r}, "
                        f"which the ontology does not define",
                        {"tool": binding.tool, "field": member},
                    )
                )
            continue
        candidates[binding.tool] = binding

    # 5. invokes: cycles (V105), then names that resolve to no loaded
    # binding (V107), until nothing changes.
    graph = {tool: list(b.invokes) for tool, b in candidates.items()}
    for component in _cycles(graph):
        for tool in component:
            diagnostics.append(
                ValidationError(
                    ErrorCode.CIRCULAR_DEPENDENCY,
                    f"tool '{tool}' is part of an invokes cycle "
                    f"({' -> '.join([*component, component[0]])}); it is not loaded",
                    {"tool": tool, "field": "invokes"},
                )
            )
            del candidates[tool]
    changed = True
    while changed:
        changed = False
        for tool, binding in list(candidates.items()):
            unresolved = [
                name
                for name in binding.invokes
                if name not in candidates and name not in known
            ]
            if unresolved:
                for name in unresolved:
                    diagnostics.append(
                        ValidationError(
                            ErrorCode.UNRESOLVED_TARGET,
                            f"tool '{tool}' invokes '{name}', which no loaded "
                            f"binding of the set names; it is not loaded",
                            {"tool": tool, "field": "invokes"},
                        )
                    )
                del candidates[tool]
                changed = True

    # 6. Effective flags, then the invoked bindings' (memoised).
    own: dict[str, _Flags] = {}
    for tool, binding in candidates.items():
        if binding.control:
            own[tool] = _NO_FLAGS
            continue
        flags, reports = _own_flags(binding, nodes)
        own[tool] = flags
        diagnostics.extend(reports)
    effective: dict[str, _Flags] = {}

    def resolve(tool: str) -> _Flags:
        if tool in effective:
            return effective[tool]
        if tool not in candidates:
            return _flags_of(known[tool])
        flags = own[tool]
        for name in candidates[tool].invokes:
            flags = flags.join(resolve(name))
        effective[tool] = flags
        return flags

    # 7. Prerequisites of the capabilities each record names.
    loaded: dict[str, ToolMapping] = {}
    for tool, binding in candidates.items():
        flags = resolve(tool)
        caps = binding.capabilities
        prerequisites = frozenset(
            source for source, target in requires if target in caps
        )
        loaded[tool] = ToolMapping(
            capability_id=binding.capability or "",
            risk=flags.risk,
            mutation=flags.mutation,
            requires_checkpoint=flags.requires_checkpoint,
            requires_approval=flags.requires_approval,
            domain=binding.domain,
            capabilities=caps,
            invokes=binding.invokes,
            prerequisites=prerequisites,
            approval=binding.approval,
            control=binding.control,
            classifier=binding.classifier,
            destination=binding.destination,
        )
    return loaded, diagnostics


def check_offered(
    offered: Mapping[str, str | None],
    mappings: Mapping[str, ToolMapping],
    host_actions: Iterable[tuple[str, str]] = (),
    *,
    host_takes_checkpoints: bool = False,
) -> list[ValidationError]:
    """Check the tools a host offers a model (section 5.18.2).

    Args:
        offered: Each name the host offers a tool under, mapped to the
            ``tool`` of the record it carries, or ``None`` for none.
        mappings: The loaded bindings by record ``tool``
            (:func:`load_bindings`).
        host_actions: ``(action, tool)`` pairs: a host action that takes
            effect whenever ``tool`` is called, such as ending the turn.
        host_takes_checkpoints: The host takes checkpoints itself, so
            ``checkpoint`` counts as performed.

    Returns:
        W617 for each offered tool that is unbound; V111 for each one whose
        record names another tool; V102 for each bound tool that requires a
        capability no offered bound tool can perform (an offered tool with a
        ``classifier`` counts as able to perform any); F506 for each host
        action tied to a tool that is not control-only and is unbound, has
        a prerequisite, or requires a checkpoint or approval.
    """
    diagnostics: list[ValidationError] = []

    def bound(name: str) -> ToolMapping | None:
        carried = offered.get(name, name)
        if carried != name:
            return None
        return mappings.get(name)

    performable: set[str] = set()
    any_capability = False
    for name in offered:
        mapping = bound(name)
        if mapping is None or mapping.control:
            continue
        performable.update(mapping.capabilities)
        if mapping.classifier is not None:
            any_capability = True
    if host_takes_checkpoints:
        performable.add("checkpoint")

    for name, carried in offered.items():
        if carried is not None and carried != name:
            diagnostics.append(
                ValidationError(
                    ErrorCode.TOOL_NAME_MISMATCH,
                    f"the host offers '{name}' with the binding of '{carried}'; "
                    f"a binding's tool must be the name the tool is offered under",
                    {"tool": name, "field": "tool"},
                )
            )
            continue
        mapping = bound(name)
        if mapping is None:
            diagnostics.append(
                ValidationError(
                    ErrorCode.UNBOUND_TOOL,
                    f"the host offers '{name}', which has no loaded binding; "
                    f"its calls are treated as the strictest case",
                    {"tool": name},
                )
            )
            continue
        if mapping.control or any_capability:
            continue
        needed = sorted(mapping.prerequisites)
        if mapping.requires_checkpoint and "checkpoint" not in needed:
            needed.append("checkpoint")
        for capability in needed:
            if capability not in performable:
                diagnostics.append(
                    ValidationError(
                        ErrorCode.MISSING_PREREQUISITE,
                        f"tool '{name}' ({mapping.capability_id}) requires "
                        f"'{capability}', and no offered tool performs it, "
                        f"so its calls could never run",
                        {
                            "tool": name,
                            "capability": mapping.capability_id,
                            "prerequisite": capability,
                        },
                    )
                )

    for action, name in host_actions:
        mapping = bound(name)
        if mapping is not None and (
            mapping.control
            or not (
                mapping.prerequisites
                or mapping.requires_checkpoint
                or mapping.requires_approval
            )
        ):
            continue
        why = (
            "is unbound"
            if mapping is None
            else "can be refused for want of a checkpoint, approval or a prerequisite"
        )
        diagnostics.append(
            ValidationError(
                ErrorCode.GATED_CONTROL_ACTION,
                f"host action '{action}' takes effect whenever '{name}' is "
                f"called, and '{name}' {why}; tie it to a control-only tool",
                {"tool": name, "action": action},
            )
        )
    return diagnostics
