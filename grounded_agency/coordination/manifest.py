"""Agent manifests (STANDARD v1.2 §5.15.1, §5.15.2).

An agent manifest (``schemas/agent_manifest_schema.yaml#/agent_manifest``)
states what an agent a ``delegate`` step names may do: the ontology
capabilities it may exercise and the task inputs it accepts. Its *maxima*
are derived from the ontology, never stated: the highest ``risk`` and the OR
of ``mutation``, ``requires_checkpoint`` and ``requires_approval`` over its
capabilities; its *read-only maxima* the same over the capabilities whose
``mutation`` is false. ``tests/conformance/agents/maxima.json`` pins them.

The Rust core reads manifests itself (``_core.Validator.validate(...,
agents=...)``, ``_core.Run.start(..., agents=...)``); these helpers give the
SDK's own checks the same rules.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .. import _core

if TYPE_CHECKING:
    from ..capabilities.registry import CapabilityRegistry

Maxima = dict[str, Any]

_MEMBERS = frozenset(
    {"agent", "standard", "ontology", "capabilities", "task", "version", "description"}
)
_CAPABILITY = re.compile(r"[a-z][a-z0-9-]*", re.ASCII)
_RISK = {"low": 0, "medium": 1, "high": 2}
_NONE: Maxima = {
    "risk": "low",
    "mutation": False,
    "requires_checkpoint": False,
    "requires_approval": False,
}


def load_agent_manifest(path: str | Path) -> dict[str, Any]:
    """Read a manifest file (YAML or JSON) with the core's loader."""
    data = _core.load_yaml(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: an agent manifest must be a mapping")
    return data


def check_agent_manifest(
    manifest: Mapping[str, Any], registry: CapabilityRegistry
) -> None:
    """Refuse a manifest that cannot be used (§5.15.1), as the core refuses
    it when loaded: not shaped as the schema says, citing a standard this
    package does not support or another ontology major (V109). A capability
    the ontology does not define is not refused here; the validator reports
    it (V101) where the manifest is used.

    Raises:
        ValueError: Naming the agent and the member.
    """
    agent = manifest.get("agent")
    if not isinstance(agent, str) or not agent:
        raise ValueError("an agent manifest needs a non-empty string 'agent'")

    def fail(what: str) -> ValueError:
        return ValueError(f"agent manifest '{agent}': {what}")

    for key in manifest:
        if key not in _MEMBERS and not str(key).startswith("x-"):
            raise fail(f"unknown member '{key}'")
    for member in ("standard", "ontology"):
        if member not in manifest:
            raise fail(
                f"no '{member}': a manifest cites the versions it was written against"
            )
    problems = _core.check_cited_versions(
        manifest.get("standard"), manifest.get("ontology"), registry.version
    )
    if problems:
        p = problems[0]
        raise fail(f"{p['code']} {p['message']}")
    for member in ("version", "description"):
        if member in manifest and not isinstance(manifest[member], str):
            raise fail(f"'{member}' must be a string")
    caps = manifest.get("capabilities")
    if not isinstance(caps, list) or not all(isinstance(c, str) for c in caps):
        raise fail("'capabilities' must be a list of capability ids")
    if len(set(caps)) != len(caps):
        raise fail("'capabilities' lists a capability twice")
    for c in caps:
        if _CAPABILITY.fullmatch(c) is None:
            raise fail(f"'{c}' is not a capability id")
    task = manifest.get("task")
    if task is not None:
        if not isinstance(task, Mapping):
            raise fail("'task' must be a mapping of task inputs")
        for name, spec in task.items():
            problem = _task_input_problem(spec)
            if problem is not None:
                raise fail(f"task input '{name}': {problem}")


def _task_input_problem(spec: Any) -> str | None:
    """What makes a task input break ``agent_task_input`` (§5.15.1), or
    None: ``type`` a type name or a non-empty list of them, ``required`` a
    boolean, ``description`` and ``ref`` strings, ``properties`` a mapping.
    Refusing these keeps ``required: "yes"`` from reading as optional."""
    if not isinstance(spec, Mapping):
        return "must be a mapping"
    if "type" in spec:
        t = spec["type"]
        if not (
            isinstance(t, str)
            or (isinstance(t, list) and t and all(isinstance(x, str) for x in t))
        ):
            return "'type' must be a type name or a non-empty list of them"
    for key, ok, what in (
        ("required", lambda v: isinstance(v, bool), "a boolean"),
        ("description", lambda v: isinstance(v, str), "a string"),
        ("properties", lambda v: isinstance(v, Mapping), "a mapping"),
        ("ref", lambda v: isinstance(v, str), "a string"),
    ):
        if key in spec and not ok(spec[key]):
            return f"'{key}' must be {what}, found {type(spec[key]).__name__}"
    return None


def join_maxima(*maxima: Maxima | None) -> Maxima | None:
    """The join of several maxima: the highest risk and the OR of each
    boolean; None when any is None (unknown)."""
    out = dict(_NONE)
    for m in maxima:
        if m is None:
            return None
        if _RISK[m["risk"]] > _RISK[out["risk"]]:
            out["risk"] = m["risk"]
        for key in ("mutation", "requires_checkpoint", "requires_approval"):
            out[key] = out[key] or bool(m[key])
    return out


def manifest_maxima(
    manifest: Mapping[str, Any],
    registry: CapabilityRegistry,
    read_only: bool = False,
) -> Maxima | None:
    """A manifest's maxima, or with ``read_only`` its read-only maxima;
    None when it lists a capability the ontology does not define."""
    out = dict(_NONE)
    for cap_id in manifest.get("capabilities") or []:
        cap = registry.get_capability(cap_id)
        if cap is None:
            return None
        if read_only and cap.mutation:
            continue
        joined = join_maxima(
            out,
            {
                "risk": cap.risk,
                "mutation": cap.mutation,
                "requires_checkpoint": cap.requires_checkpoint,
                "requires_approval": cap.requires_approval,
            },
        )
        assert joined is not None
        out = joined
    return out


def target_maxima(
    workflow_agents: Sequence[str],
    step_bindings: Mapping[str, Any],
    manifests: Mapping[str, Mapping[str, Any]],
    registry: CapabilityRegistry,
) -> Maxima | None:
    """A ``delegate`` step's target maxima in a workflow that declares
    ``workflow_agents`` (§5.15.2): a literal agent's manifest maxima, or for
    a computed one the join over every listed agent; read-only maxima when
    the step binds a literal ``read_only: true``. None when a manifest
    concerned is missing or lists an unknown capability."""
    agent = step_bindings.get("agent")
    literal = isinstance(agent, str) and "${" not in agent
    read_only = step_bindings.get("read_only") is True
    concerned: Iterable[str] = [agent] if literal else workflow_agents  # type: ignore[list-item]
    found: list[Maxima | None] = []
    for name in concerned:
        manifest = manifests.get(name)
        found.append(
            None if manifest is None else manifest_maxima(manifest, registry, read_only)
        )
    return join_maxima(*found)


def check_task(
    manifest: Mapping[str, Any], task: Mapping[str, Any] | None
) -> tuple[list[str], list[str]]:
    """A task against the manifest's declared ``task`` (§5.15.2): the names
    it gives that are not declared, and the required inputs it lacks. A
    manifest that declares no ``task`` accepts any task."""
    declared = manifest.get("task")
    if not isinstance(declared, Mapping):
        return [], []
    given = list(task or {})
    undeclared = [n for n in given if n not in declared]
    missing = [
        n
        for n, spec in declared.items()
        if isinstance(spec, Mapping) and spec.get("required") is True and n not in given
    ]
    return undeclared, missing
