"""
Grounded Agent Adapter

Main entry point for integrating Grounded Agency safety patterns
with the Claude Agent SDK. The adapter is a safety layer on a tool-calling
host (STANDARD 1.2.0 section 5.18, class SL in section 10.4). Wraps SDK
options to inject:

- A PreToolUse hook that applies the rate limit, the prerequisites, the
  checkpoint rule (F501, F503) and the approval rule (F502) to every tool
  call, and refuses with R407 when it cannot complete a check; its
  matcher's ``on_failure`` is ``"block"``, so a callback that fails or
  gives no verdict in time, as the CLI sees it, blocks the call too
- A permission callback that re-checks the call (arguments the host
  changed are classified again) and uses its checkpoint up when the call is
  allowed, after passing the decision to the host's own ``can_use_tool``
- PostToolUse hooks for evidence collection, the checkpoint recorder (a
  successful state-saving call takes a checkpoint), the use of a held
  checkpoint by a call that ran, and the output check of a bound tool of
  another MCP server (R402, F505, F504), whose refused result it replaces
- A Stop and a UserPromptSubmit hook: the end of a turn and the start of
  the next are execution boundaries

The layer's scope is the adapter instance: every session and subagent it
serves shares one set of records, and the Stop or the next prompt of any of
them ends the validity of every checkpoint the adapter holds. Serve sessions
that must not share boundaries with separate adapters. A checkpoint the
adapter reads back from its ``checkpoint_dir`` (taken by an earlier process,
or by another adapter on that directory) authorises none of its calls. The
conformance statement is
``tests/conformance/calls/statements/grounded_agency_adapter.json``.

Example:
    from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

    adapter = GroundedAgentAdapter(GroundedAgentConfig(strict_mode=True))
    options = adapter.wrap_options(base_options)

    async with ClaudeSDKClient(options) as client:
        await client.query("Edit the config file...")
"""

from __future__ import annotations

import hashlib
import hmac
import inspect
import json
import logging
import os
import re
import threading
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from . import _core
from ._types import FallbackPermissionAllow, FallbackPermissionDeny, HookContext
from .capabilities.mapper import UNCLASSIFIED_TOOL, ToolCapabilityMapper, ToolMapping
from .capabilities.registry import CapabilityRegistry
from .errors import ErrorCode, ValidationError, text_form
from .grounding import GroundingPolicy, as_policies, check_output
from .hooks.evidence_collector import create_evidence_collector
from .hooks.skill_tracker import create_checkpoint_recorder
from .profiles import AppliedProfiles
from .state.checkpoint_tracker import MAX_AGE_MINUTES, CheckpointTracker
from .state.evidence_store import (
    EvidenceAnchor,
    EvidenceStore,
    EvidenceStoreProtocol,
)
from .state.rate_limiter import RateLimitConfig, RateLimiter
from .state.redaction import DEFAULT_REDACTOR, Redactor
from .state.snapshots import FileSnapshotStore

if TYPE_CHECKING:
    from .coordination.orchestrator import OrchestrationRuntime
    from .query import CostSummary

logger = logging.getLogger("grounded_agency.adapter")

# The Claude Code permission modes in which this adapter relies on a
# PreToolUse "ask" reaching a person through can_use_tool (or the
# permission prompt tool), STANDARD 1.2.0 section 5.18.7. Not configurable:
# adding a mode would let a call that requires approval run on a decision no
# person made. `dontAsk` denies the call anyway (the adapter's F502 says
# why); in `bypassPermissions` the documentation does not say that an ask
# reaches the callback; in `auto` a classifier, not a person, can answer
# the prompt; and a mode the adapter does not know is not relied on.
PROMPTING_PERMISSION_MODES: frozenset[str] = frozenset(
    {"default", "acceptEdits", "plan"}
)

# A call argument an `acs:` anchor can cite (a §5.3 identifier).
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


class _Fault(NamedTuple):
    """Why a call's result is refused (R402, F505 or F504), before it is
    recorded: the arguments of :meth:`GroundedAgentAdapter._fail_call`."""

    code: ErrorCode
    mapping: ToolMapping
    tool: str
    message: str
    reason: str | None = None


def _mcp_tool_result(response: Any) -> Any:
    """An MCP tool's result as a PostToolUse hook receives it
    (``tool_response``), in the form
    :func:`~grounded_agency.capabilities.output.tool_result_output` reads:
    Claude Code passes the result's content items, or a result that holds
    them; a text is the one text item the session reads."""
    if isinstance(response, list):
        return {"content": response}
    if isinstance(response, str):
        return {"content": [{"type": "text", "text": response}]}
    return response


def _replace_result(text: str) -> dict[str, Any]:
    """A PostToolUse answer that replaces the MCP result the session reads
    with ``text``, a refusal (section 5.18.8)."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedMCPToolOutput": [{"type": "text", "text": text}],
        }
    }


def _find_ontology_path() -> str:
    """
    Find the capability ontology path.

    SEC-012: Resolves to an absolute, real path (no symlinks) to prevent
    path substitution attacks.

    Priority:
    1. Package-relative path (for installed package)
    2. Project-relative path (for development)
    """
    # Try package-relative path first
    try:
        # Python 3.9+ importlib.resources approach
        from importlib.resources import as_file, files

        package_path = files("grounded_agency").joinpath(
            "../schemas/capability_ontology.yaml"
        )
        # Check if it exists
        with as_file(package_path) as path:
            if path.exists():
                resolved = path.resolve(strict=True)
                return str(resolved)
    except ImportError, FileNotFoundError, TypeError, OSError:
        pass

    # Fallback: look relative to this file
    module_dir = Path(__file__).resolve().parent
    for relative in [
        "../schemas/capability_ontology.yaml",  # Development layout
        "schemas/capability_ontology.yaml",  # Alternative layout
    ]:
        candidate = (module_dir / relative).resolve()
        if candidate.exists():
            return str(candidate)

    # Final fallback: assume cwd-relative (original behavior)
    return str(Path("schemas/capability_ontology.yaml").resolve())


def verify_ontology_integrity(
    ontology_path: str,
    expected_hash: str | None = None,
) -> bool:
    """Verify ontology file integrity via SHA-256 checksum.

    SEC-012: Detects content substitution attacks on the ontology file.

    Args:
        ontology_path: Path to the ontology YAML file.
        expected_hash: Expected SHA-256 hex digest. If None, checks for a
                      .sha256 sidecar file next to the ontology.

    Returns:
        True if integrity check passes or no expected hash is available.
        False if hash mismatch detected.
    """
    path = Path(ontology_path)
    if not path.exists():
        return False

    # Compute actual hash
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    actual_hash = sha.hexdigest()

    # Look for expected hash
    if expected_hash is None:
        sidecar = path.with_suffix(".yaml.sha256")
        if sidecar.exists():
            parts = sidecar.read_text(encoding="utf-8").strip().split()
            if parts:
                expected_hash = parts[0]

    if expected_hash is None:
        # No hash to verify against — pass by default
        return True

    if not hmac.compare_digest(actual_hash, expected_hash):
        logger.error(
            "SEC-012: Ontology integrity check FAILED. Expected %s, got %s for %s",
            expected_hash,
            actual_hash,
            ontology_path,
        )
        return False

    return True


# Cache the resolved path
_DEFAULT_ONTOLOGY_PATH: str | None = None


def get_default_ontology_path() -> str:
    """Get the default ontology path (cached)."""
    global _DEFAULT_ONTOLOGY_PATH
    if _DEFAULT_ONTOLOGY_PATH is None:
        _DEFAULT_ONTOLOGY_PATH = _find_ontology_path()
    return _DEFAULT_ONTOLOGY_PATH


@dataclass(slots=True)
class GroundedAgentConfig:
    """
    Configuration for the Grounded Agent Adapter.

    Attributes:
        ontology_path: Path to capability_ontology.yaml (auto-detected if not specified)
        strict_mode: If True, refuse a call that fails a check. If False,
            log a warning and let the checkpoint, prerequisite and internal
            checks pass (outside class SL; approval still applies).
        audit_log_path: Path for audit log file
        checkpoint_dir: Directory for checkpoint storage. Adapters that
            share it share its state file (merged under a file lock), not
            their checkpoints: each authorises only its own adapter's calls
        expiry_minutes: The layer's checkpoint maximum age, in minutes:
            more than 0 and at most 30 (STANDARD 1.2.0 section 5.18.6). The
            checkpoint tracker applies it to every checkpoint, one taken
            through ``adapter.checkpoint_tracker`` directly included.
        rate_limit: Per-risk-level rate limit configuration (SEC-010).
        ontology_hash: Expected SHA-256 hash for ontology integrity check (SEC-012).
                      If None, checks for a .sha256 sidecar file.
        output_format: JSON schema for structured output (SDK ``output_format``).
        max_budget_usd: Maximum cost budget in USD (SDK ``max_budget_usd``).
        model: Default model name (SDK ``model``).
        max_turns: Maximum agent turns (SDK ``max_turns``).
        enable_discovery: If True, inject a PreToolUse hook that runs
            capability discovery on user prompts automatically.
        checkpoint_reservation_seconds: How long a call holds the checkpoint
            it reserved if it never reports back. ``None`` (default): until
            the checkpoint expires. A value must be more than 0 and at most
            ``expiry_minutes * 60``. A hold that lapses counts as used.
        approval: What happens to a tool call whose effective
            ``requires_approval`` is true (in the reference ontology:
            ``execute``, ``mutate``, ``send`` and unbound tools), once the
            other checks pass. ``"ask"`` (default): in the permission modes
            of :data:`PROMPTING_PERMISSION_MODES` the PreToolUse hook answers
            ``permissionDecision: "ask"`` with a reason that begins
            ``F502 APPROVAL_REQUIRED:``, so a person decides the call through
            the host's permission flow; in any other mode, and with no
            ``can_use_tool`` callback, the call is refused with F502.
            ``"off"``: the adapter asks for no approval (outside class SL).
        evidence_include_tool_input: If True, evidence anchors keep each
            tool call's input, and a Bash command's text, in their
            metadata, redacted by the store (STANDARD v1.2 §6.7). Off by
            default: inputs can hold credentials.
        evidence_store: The evidence store the adapter writes to (§6.6):
            any :class:`EvidenceStoreProtocol`, such as a durable
            ``JsonlEvidenceStore``. None: a new in-memory ``EvidenceStore``.
        secret_values: The host's own secrets (§6.7), registered with the
            evidence store's and the coordination audit log's redactor so
            they never reach an anchor or a record. Never part of
            ``recorded_by``.
        grounding: Grounding policies the layer applies to the output of
            each call whose capability one requires (§5.20): one
            :class:`GroundingPolicy` or several. A call's argument names are
            what its ``acs:`` anchors may cite; the layer gives no
            ``evidence_seen`` (a hook does not see the model's request). An
            output that fails is refused with F505, and the call's record is
            ``failed``. They apply to the output of every MCP tool bound to
            a capability (a tool ``create_grounded_mcp_server`` serves
            checks its own result, and the PostToolUse hook checks another
            server's); Claude Code's own tools return no capability output,
            so no policy checks their calls (a warning is logged once per
            such tool).
        call_record_limit: How many call records (and refusals) the adapter
            keeps in memory (``call_records``, ``diagnostics``).
        profiles: Domain profiles applied to every tool call the adapter
            covers (STANDARD 1.2.0 section 5.21), each a loaded profile or
            the path of a profile file (``adapter.profiles``): their
            ``risk_thresholds`` and ``checkpoint_policy`` raise the flags of
            the call's capability, and ``require_human`` and
            ``block_autonomous`` require a person's approval (records carry
            ``person_required``). Their grounding policies
            (``evidence_policy.require_grounding``, with
            ``required_anchor_types`` as kinds) join ``grounding``, and
            their ``minimum_confidence`` fails an output below it with F504:
            both apply to the output of every MCP tool bound to a
            capability (a tool ``create_grounded_mcp_server`` serves checks
            its own result, and the PostToolUse hook checks another
            server's); Claude Code's own tools return no capability output,
            and a warning is logged once for each such tool they would
            cover. Their
            ``allowed_destinations`` are destination policies in force
            beside ``allowed_destinations`` (section 4.4.2). A profile with
            an error refuses the configuration
            (:class:`~grounded_agency.profiles.ProfileError`). Profiles need
            ``approval="ask"``: with approvals off, the approvals they
            require would be skipped. With ``strict_mode=False``, which
            only logs a missing checkpoint, a profile whose
            ``checkpoint_policy`` raises ``requires_checkpoint`` (a value
            other than ``never``) refuses the configuration too.
        snapshots: Where the layer's checkpoints keep their content
            (STANDARD 1.2.0 section 4.4.1): with a
            :class:`~grounded_agency.state.snapshots.FileSnapshotStore`, each
            checkpoint copies the files in its scope, and
            ``adapter.checkpoint_tracker.restore_checkpoint`` puts them back.
            The tracker's state, its marker and the audit log are protected
            in it. None: checkpoints record metadata only.
        allowed_destinations: A destination policy (STANDARD 1.2.0 section
            4.4.2): the patterns a ``send`` call's destination must match.
            With the applied profiles' ``allowed_destinations``, the
            policies in force: a call of a tool that performs ``send`` is
            refused with F504, before approval and the checkpoint, when one
            does not allow the destination its binding's ``destination``
            pointer names, or when the binding names none (the layer cannot
            tell where it sends). None: no policy of the host's own. An
            invalid pattern is a ``ValueError``.
        schema_root: The directory the ontology's ``$ref`` paths are
            relative to (STANDARD 1.2.0 section 4.1.2). Default: the
            directory above the ontology's (the repository root for
            ``schemas/capability_ontology.yaml``). A contract whose ``$ref``
            names nothing there, is cyclic or nests too deep refuses the
            configuration (``ValueError``).
        check_outputs: Whether the result of a call of an MCP tool bound to
            a capability must carry that capability's output and satisfy its
            output contract (STANDARD 1.2.0 sections 5.18.9 and 5.18.10): the
            I-JSON text of the output object as its one text content item,
            with every field the contract requires. A tool that
            ``create_grounded_mcp_server`` serves is checked as it returns;
            a bound tool of another MCP server (``register_mcp_tool``,
            ``load_bindings``) at PostToolUse, which replaces a refused
            result with the refusal. The SDK's server delivers only a
            result's content (and ``is_error``) to the session, so the text is
            the output; a ``structuredContent`` member is not read. A result
            that does not carry the output is the failure of the call that
            ran, R402, recorded against the call. On (default). ``False``
            skips only that check (outside class SL): the grounding policies
            and a minimum confidence still read the output the one text item
            carries. Claude Code's own tools return results in their own
            forms, which carry no capability output, and are never checked.
    """

    ontology_path: str = field(default_factory=get_default_ontology_path)
    strict_mode: bool = True
    audit_log_path: str = ".claude/audit.log"
    checkpoint_dir: str = ".checkpoints"
    expiry_minutes: int = MAX_AGE_MINUTES
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    ontology_hash: str | None = None
    output_format: dict[str, Any] | None = None
    max_budget_usd: float | None = None
    model: str | None = None
    max_turns: int | None = None
    enable_discovery: bool = False
    checkpoint_reservation_seconds: float | None = None
    approval: Literal["ask", "off"] = "ask"
    evidence_include_tool_input: bool = False
    call_record_limit: int = 10000
    profiles: Sequence[Mapping[str, Any] | str | os.PathLike[str]] = ()
    schema_root: str | None = None
    evidence_store: EvidenceStoreProtocol | None = None
    secret_values: tuple[str, ...] = ()
    grounding: tuple[GroundingPolicy, ...] = ()
    allowed_destinations: Sequence[str] | None = None
    snapshots: FileSnapshotStore | None = None
    check_outputs: bool = True

    def __post_init__(self) -> None:
        """Refuse a setting this adapter cannot honour."""
        if self.approval not in ("ask", "off"):
            raise ValueError(f"approval must be 'ask' or 'off', got {self.approval!r}")
        if self.profiles and self.approval == "off":
            raise ValueError(
                "domain profiles need approval='ask': with approvals off, the "
                "approvals a profile requires would be skipped (STANDARD 1.2.0 "
                "section 5.21)"
            )
        minutes = self.expiry_minutes
        if (
            isinstance(minutes, bool)
            or not isinstance(minutes, (int, float))
            or not 0 < minutes <= MAX_AGE_MINUTES
        ):
            raise ValueError(
                f"expiry_minutes must be more than 0 and at most {MAX_AGE_MINUTES}, "
                f"got {minutes!r}: STANDARD 1.2.0 §5.18.6 caps a checkpoint's "
                f"maximum age at 30 minutes"
            )
        seconds = self.checkpoint_reservation_seconds
        if seconds is not None and not 0 < seconds <= minutes * 60:
            raise ValueError(
                f"checkpoint_reservation_seconds must be more than 0 and at most "
                f"expiry_minutes * 60 ({minutes * 60}), got {seconds!r}"
            )
        if not isinstance(self.call_record_limit, int) or self.call_record_limit < 1:
            raise ValueError(
                f"call_record_limit must be a positive integer, got "
                f"{self.call_record_limit!r}"
            )
        # One policy or several; each was checked against the ontology when
        # it was made (an unknown id is a ValueError naming V101).
        self.grounding = as_policies(self.grounding)  # type: ignore[arg-type]
        if isinstance(self.secret_values, str) or not all(
            isinstance(v, str) for v in self.secret_values
        ):
            raise ValueError("secret_values must be a sequence of strings")
        self.secret_values = tuple(self.secret_values)
        if self.allowed_destinations is not None:
            if isinstance(self.allowed_destinations, str) or not all(
                isinstance(p, str) for p in self.allowed_destinations
            ):
                raise ValueError("allowed_destinations must be a sequence of strings")
            for pattern in self.allowed_destinations:
                try:
                    _core.check_destination_pattern(pattern)
                except ValueError as e:
                    raise ValueError(f"allowed_destinations: {e}") from None
            self.allowed_destinations = tuple(self.allowed_destinations)


def _json_pointer(value: Any, pointer: str) -> tuple[bool, Any]:
    """The member of ``value`` an RFC 6901 pointer names: ``(found, member)``."""
    if pointer == "":
        return True, value
    node = value
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and token in node:
            node = node[token]
        elif isinstance(node, list) and token.isdigit() and int(token) < len(node):
            node = node[int(token)]
        else:
            return False, None
    return True, node


def _error(code: ErrorCode, message: str, location: dict[str, Any]) -> ValidationError:
    return ValidationError(code=code, message=message, location=location)


def _subject(mapping: ToolMapping, tool_name: str) -> str:
    """What a rule applies to: the tool and the capability it performs, or,
    for an unbound tool, the case it is treated as.

    The tool is the subject because a flag can come from the tool's
    declaration and not from the capability (an ``execute`` tool declared
    high-risk needs a checkpoint; ``execute`` does not).
    """
    if mapping is UNCLASSIFIED_TOOL:
        return (
            f"{tool_name} has no binding (STANDARD 1.2.0 §5.18.2) and is treated "
            f"as the strictest case, which"
        )
    return f"{tool_name} (capability '{mapping.capability_id}')"


def _checkpoint_message(
    mapping: ToolMapping, tool_name: str, held_checkpoint: str | None
) -> str:
    """Why a checkpoint-gated tool call may not proceed (F501)."""
    if held_checkpoint is not None:
        return (
            f"{_subject(mapping, tool_name)} requires checkpoint, and checkpoint "
            f"{held_checkpoint} is held by another call in flight. "
            f"Retry {tool_name} after it completes, or take a new checkpoint."
        )
    return (
        f"{_subject(mapping, tool_name)} requires checkpoint, and no valid "
        f"checkpoint is left: each gated call needs its own, and a turn's end "
        f"or its maximum age ends one. Take a checkpoint (git stash create, a "
        f"checkpoint tool, or adapter.create_checkpoint()) "
        f"before using {tool_name}."
    )


def _approval_request(mapping: ToolMapping, tool_name: str, person: bool) -> str:
    """Why a tool call is put to the host's permission flow (F502). When an
    applied profile requires a person (``person``), the reason says so: a
    host's ``can_use_tool`` callback reads it, and only a person's decision
    counts for such a call (STANDARD 1.2.0 section 5.21.3)."""
    if person:
        return text_form(
            _error(
                ErrorCode.APPROVAL_REQUIRED,
                f"{_subject(mapping, tool_name)} requires approval by a person: "
                f"an applied domain profile requires one for it or for a "
                f"binding it invokes (require_human or block_autonomous, "
                f"STANDARD 1.2.0 §5.21.3), so no automatic decision counts. "
                f"It runs only if a person approves this call.",
                {},
            )
        )
    return text_form(
        _error(
            ErrorCode.APPROVAL_REQUIRED,
            f"{_subject(mapping, tool_name)} requires approval. "
            f"It runs only if this call is approved.",
            {},
        )
    )


def _is_allow(result: Any) -> bool:
    """Whether a permission result allows the call: the SDK's
    ``PermissionResultAllow`` (``behavior``) or the fallback type
    (``allowed``). Anything else is not an allow."""
    return (
        getattr(result, "behavior", None) == "allow"
        or getattr(result, "allowed", None) is True
    )


def _cwd_of(input_data: Any) -> str | None:
    """A hook input's `cwd` (the directory the call runs in), when it is a
    non-empty string."""
    cwd = input_data.get("cwd") if isinstance(input_data, dict) else None
    return cwd if isinstance(cwd, str) and cwd else None


def _args_key(args: Any) -> str:
    """A digest of a call's arguments: SHA-256 of their RFC 8785 canonical
    JSON, or, for arguments that are not I-JSON, of a sorted JSON text."""
    from . import _core

    try:
        text = _core.canonical_json(args)
    except ValueError, TypeError:
        text = json.dumps(args, sort_keys=True, default=repr)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso(clock: Callable[[], datetime]) -> str:
    return clock().isoformat()


# A call record's decision as an audit record's status (STANDARD 1.2.0
# section 6.4): an allowed call that has no outcome yet is approved, a call
# put to the host's permission flow is planned until it is decided, and a
# refusal is rejected with its code. A boundary records no action.
_CALL_STATUS = {
    "allowed": "approved",
    "asked": "planned",
    "refused": "rejected",
    "ran": "executed",
    "failed": "failed",
}

# The call record members an audit record holds as its own members; every
# other member is kept under ``details``.
_CALL_MAPPED = frozenset(
    {"seq", "at", "tool", "capability", "call", "checkpoint_id", "recorded_by"}
)


def call_action_record(entry: dict[str, Any], scope: str) -> dict[str, Any] | None:
    """One of the adapter's ``call_records`` as an audit record (STANDARD
    1.2.0 section 6.4), the shape the layer exports its records in.

    ``scope`` names the layer scope (section 5.18.5): it is the record's
    ``run_id`` and prefixes its ``action_id``, ``<scope>/<seq>``. A refusal is
    ``rejected`` with its diagnostic's ``code``; a call the host's permission
    flow approved in its session has ``approval`` with ``mode: in_session``
    and the digest of what was shown (section 5.18.7). A call an applied
    domain profile required a person for has ``person_required`` (section
    5.21.3), and a failure's reason is ``reason_code`` (section 5.19.7).
    ``recorded_by`` is the layer's, as the call record holds it. Every other
    member of the call record (``decision``, ``permission_mode``,
    ``diagnostic``, ...) is kept under ``details``. Returns None for a
    boundary entry, which records no action.
    """
    status = _CALL_STATUS.get(entry.get("decision", ""))
    if status is None:
        return None
    tool = entry["tool"]
    record: dict[str, Any] = {
        "action_id": f"{scope}/{entry['seq']}",
        "run_id": scope,
        "timestamp": entry["at"],
        "actor": "agent",
        "intent": f"{tool} call",
        "status": status,
        "tool": tool,
    }
    if entry.get("capability"):
        record["capability"] = entry["capability"]
    if entry.get("call"):
        record["call_id"] = entry["call"]
    if entry.get("checkpoint_id"):
        record["checkpoint_id"] = entry["checkpoint_id"]
    diagnostic = entry.get("diagnostic")
    if isinstance(diagnostic, dict) and diagnostic.get("code"):
        record["code"] = diagnostic["code"]
    mapped = set(_CALL_MAPPED)
    if isinstance(entry.get("reason"), str):
        # The failure's reason token (section 5.19.7), as a step's record
        # holds it.
        record["reason_code"] = entry["reason"]
        mapped.add("reason")
    if entry.get("person_required") is True:
        # An applied domain profile required a person for the call
        # (section 5.21.3): an ActionRecord member, as a step's record holds it.
        record["person_required"] = True
        mapped.add("person_required")
    if entry.get("approvers") == ["in_session"] and entry.get("digest"):
        record["approval"] = {
            "digest": entry["digest"],
            "decision": "approved",
            "mode": "in_session",
        }
        mapped |= {"approvers", "digest"}
    details = {k: v for k, v in entry.items() if k not in mapped}
    if details:
        record["details"] = details
    record["recorded_by"] = dict(entry["recorded_by"])
    return record


@dataclass
class GroundedAgentAdapter:
    """
    Adapts Claude Agent SDK to use Grounded Agency safety patterns.

    The adapter is a safety layer (STANDARD 1.2.0 section 5.18). It wraps
    SDK options to inject:
    1. A PreToolUse hook and a permission callback that apply the rate
       limit (F504), prerequisites (F501, F503, V102), the checkpoint rule
       (F501, one checkpoint per gated call) and approval (F502) to every
       call, and refuse with R407 when a check cannot complete
    2. PostToolUse hooks that collect evidence anchors, record the
       checkpoint a successful state-saving call took, and use up a
       checkpoint a call that ran still held
    3. A Stop hook: the end of any served session's turn is an execution
       boundary

    Every call the layer allows or refuses is recorded in ``call_records``
    with ``recorded_by`` (the layer's name, version and a digest of its
    configuration and bindings); every refusal is a §9.8 diagnostic in
    ``diagnostics`` and reaches the model as its text form,
    ``F501 CHECKPOINT_REQUIRED: ...``.

    Example:
        adapter = GroundedAgentAdapter(GroundedAgentConfig(strict_mode=True))

        # Create checkpoint before mutations
        adapter.create_checkpoint(["*.py"], "Before refactoring")

        # Wrap SDK options. base_options carries the host's can_use_tool
        # callback, which decides the calls that require approval.
        options = adapter.wrap_options(base_options)

        # Now a mutation that callback approves is allowed
        async with ClaudeSDKClient(options) as client:
            await client.query("Refactor the handler...")
    """

    config: GroundedAgentConfig = field(default_factory=GroundedAgentConfig)
    orchestrator: OrchestrationRuntime | None = None
    clock: Callable[[], datetime] | None = None
    registry: CapabilityRegistry = field(init=False)
    mapper: ToolCapabilityMapper = field(init=False)
    checkpoint_tracker: CheckpointTracker = field(init=False)
    evidence_store: EvidenceStoreProtocol = field(init=False)
    rate_limiter: RateLimiter = field(init=False)
    cost_summary: CostSummary = field(init=False)

    def __post_init__(self) -> None:
        """Initialize components after dataclass creation."""
        # SEC-012: Verify ontology integrity before loading
        if not verify_ontology_integrity(
            self.config.ontology_path, self.config.ontology_hash
        ):
            raise ValueError(
                f"SEC-012: Ontology integrity check failed for "
                f"{self.config.ontology_path}. File may have been tampered with."
            )
        self.registry = CapabilityRegistry(self.config.ontology_path)
        # Load now, so an ontology that cannot be read fails here and not
        # at the first tool call.
        _ = self.registry.ontology
        self._schema_root = (
            Path(self.config.schema_root)
            if self.config.schema_root is not None
            else Path(self.config.ontology_path).resolve().parent.parent
        )
        # The core loads the ontology too, resolving every contract's $ref:
        # one outside the schema dialect refuses the configuration, as it
        # refuses the validator and the executor (STANDARD 1.2.0 section
        # 4.1.2).
        core = _core.Validator(str(self.config.ontology_path), str(self._schema_root))
        # Domain profiles (STANDARD 1.2.0 section 5.21), checked against the
        # adapter's ontology; an error refuses the configuration, and so
        # does (strict_mode=False only logs a missing checkpoint) a raised
        # checkpoint requirement (section 5.21.4). A grounding policy and a
        # minimum confidence are in force on the outputs the layer receives
        # (the MCP tools' bound to a capability), and reported for each other
        # tool whose calls they would check (_warn_unchecked_output, section
        # 5.21.4).
        self.profiles = AppliedProfiles(self.config.profiles, validator=core)
        # The destination policies in force for send calls (section 4.4.2):
        # the configuration's, then each applied profile's (5.21.3).
        self._destinations: list[list[str]] = [
            *(
                [list(self.config.allowed_destinations)]
                if self.config.allowed_destinations is not None
                else []
            ),
            *(list(p) for p in self.profiles.destinations),
        ]
        if not self.config.strict_mode:
            self.profiles.refuse_unapplied(
                ("checkpoints",), "this adapter with strict_mode=False"
            )
        self.mapper = ToolCapabilityMapper(self.registry, profiles=self.profiles)
        # The grounding policies the layer applies to call outputs (section
        # 5.20): the configuration's, then one per applied profile with
        # require_grounding, whose kinds are its required_anchor_types
        # (section 5.21.3).
        from_profiles = (
            GroundingPolicy.from_profile(g) for g in self.profiles.grounding
        )
        self._grounding: tuple[GroundingPolicy, ...] = (
            *self.config.grounding,
            *(p for p in from_profiles if p is not None),
        )
        now: Callable[[], datetime] = self.clock or (lambda: datetime.now(UTC))
        self._now = now
        # The tracker enforces the layer's maximum age on every checkpoint,
        # one taken through its own API or read back from its state file
        # included (STANDARD 1.2.0 section 5.18.6).
        self.checkpoint_tracker = CheckpointTracker(
            self.config.checkpoint_dir,
            reservation_seconds=self.config.checkpoint_reservation_seconds,
            clock=now,
            max_age_minutes=self.config.expiry_minutes,
            snapshots=self.config.snapshots,
        )
        # The layer's redactor (STANDARD v1.2 §6.7): what it recognises as a
        # secret, the host's own values included. Its records, refusals and
        # evidence are redacted with it, and persist and audit calls whose
        # data holds a credential are refused (§5.18.10).
        self.redactor = Redactor(self.config.secret_values)
        # ``is None``, not ``or``: an empty store is falsy (``len`` 0) and is
        # still the store the host gave.
        self.evidence_store = (
            self.config.evidence_store
            if self.config.evidence_store is not None
            else EvidenceStore(redactor=self.redactor)
        )
        if self.config.snapshots is not None:
            # The record of what happened is never within a rollback's
            # reach (section 4.4.1): the plugin's .claude/ and .audit/
            # always are out of it; this covers an audit log the
            # configuration moved elsewhere and an evidence store kept in a
            # file (a restore would rewind it and swap the file under the
            # store's open descriptor, losing every later record).
            self.config.snapshots.protect(self.config.audit_log_path)
            evidence_path = getattr(self.evidence_store, "path", None)
            if isinstance(evidence_path, (str, os.PathLike)):
                self.config.snapshots.protect(os.fspath(evidence_path))
        self._register_secrets()
        self.rate_limiter = RateLimiter(self.config.rate_limit)
        # The layer's records (STANDARD 1.2.0 section 5.18.8). History
        # counts from the adapter's start: one adapter is one scope.
        self._started_at = now()
        started_at = self._started_at
        # `git stash pop|apply <commit>` is a rollback only for a commit a
        # checkpoint of this scope recorded (section 5.18.3).
        self.mapper.is_checkpoint_commit = lambda commit: (
            self.checkpoint_tracker.has_commit(commit, since=started_at)
        )
        self._state_lock = threading.Lock()
        self._executed: set[str] = set()
        # Calls this layer allowed, by (tool, digest of the arguments), not
        # yet run, each with its call id (tool_use_id) when it has one, in
        # the order allowed: what a grounded MCP tool checks (take_allowed).
        # A call enters only when it is allowed: the PreToolUse hook's pass,
        # or the permission callback's allow of a call the hook asked about,
        # never the ask itself (section 5.18.7).
        self._allowed: dict[tuple[str, str], list[str | None]] = {}
        # Calls the PreToolUse hook asked about and no decision has reached
        # this layer for yet, keyed as _allowed: the permission callback
        # allows only a call the hook passed or asked about.
        self._asked_calls: dict[tuple[str, str], list[str | None]] = {}
        # Calls whose outcome a grounded MCP tool recorded (an F505 refusal
        # of its output, section 5.20): the post-call hooks do not record
        # it again.
        self._outcome_recorded: set[str] = set()
        # The directory each call runs in (its hook input's `cwd`), by call
        # id, from the PreToolUse hook until the call reports back: the
        # permission callback, whose context carries none, classifies the
        # call there too, so a git read that may fetch from another host
        # (a partial clone) is classified alike in both.
        self._call_dirs: dict[str, str] = {}
        # When the layer asked for a decision on a call whose binding sets
        # approval.expires, by call id (the PreToolUse hook's "ask"): the
        # permission callback refuses a decision that arrives later than
        # that after the request (section 5.18.7).
        self._asked_at: dict[str, datetime] = {}
        # The tools create_grounded_mcp_server serves, which check their own
        # output (section 5.20); the PostToolUse hook checks other servers'
        # bound MCP tools. Tools a policy would check but whose results carry
        # no capability output (Claude Code's own), warned about once each.
        self._grounded_tools: set[str] = set()
        self._ungrounded_warned: set[str] = set()
        self.call_records: deque[dict[str, Any]] = deque(
            maxlen=self.config.call_record_limit
        )
        # Each call record's number in this scope, from 1: the audit
        # record's action_id (export_action_records).
        self._record_seq = 0
        self.diagnostics: deque[ValidationError] = deque(
            maxlen=self.config.call_record_limit
        )

        # recorded_by's digest, by what it was computed from.
        self._config_digest: tuple[tuple[int, str], str] | None = None

        # Lazy-initialized by _get_or_create_workflow_engine
        self._workflow_engine: Any = None

        # Initialize cost tracking (import here to avoid circular import)
        from .query import CostSummary

        self.cost_summary = CostSummary()
        if self.profiles:
            # Every record's digest covers the profiles: one that has no
            # I-JSON form refuses the configuration here, not at a record.
            _ = self.recorded_by

    def _register_secrets(self) -> None:
        """Register ``config.secret_values`` with the evidence store's and
        the coordination audit log's redactor (§6.7). A component that uses
        the shared default redactor gets the layer's, so the values never
        reach a redactor other adapters share."""
        values = self.config.secret_values
        if not values:
            return
        components: list[Any] = [self.evidence_store]
        if self.orchestrator is not None:
            components.append(self.orchestrator.audit_log)
        for component in components:
            redactor = getattr(component, "redactor", None)
            if redactor is None:
                logger.warning(
                    "%s has no redactor; the registered secrets do not reach it",
                    type(component).__name__,
                )
                continue
            if redactor is DEFAULT_REDACTOR:
                component.redactor = self.redactor
            elif redactor is not self.redactor:
                for v in values:
                    redactor.add_secret(v)

    def _destination_refusal(
        self, mapping: ToolMapping, tool: str, call: str | None, args: Any
    ) -> str | None:
        """The F504 refusal of a call of a tool that performs ``send`` whose
        destination a destination policy in force does not allow, or whose
        destination this layer cannot tell (section 4.4.2, 5.18.10): read
        at the binding's ``destination`` pointer. A call of an unbound tool
        is refused too: this layer cannot tell whether or where it sends
        (section 5.18.2). So is a composite that invokes, transitively, a
        binding that performs ``send`` or an unbound tool: this layer does
        not see a tool's nested calls (section 5.18.4), so it cannot tell
        where they send.
        None for any other call, and when no policy is in force. The
        destination is not repeated: it is in the call's input (section
        6.7)."""
        if not self._destinations:
            return None
        if mapping is UNCLASSIFIED_TOOL:
            return self._refuse(
                ErrorCode.CONSTRAINT_VIOLATED,
                mapping,
                tool,
                call,
                f"{tool} has no binding, so this layer cannot tell whether or "
                f"where it sends, and no destination policy in force can allow "
                f"it (STANDARD 1.2.0 §4.4.2, §5.18.2)",
            )
        if "send" in mapping.capabilities:
            refusal = self._direct_destination_refusal(mapping, tool, call, args)
            if refusal is not None:
                return refusal
        senders = self.mapper.invoked_senders(mapping)
        if not senders:
            return None
        return self._refuse(
            ErrorCode.CONSTRAINT_VIOLATED,
            mapping,
            tool,
            call,
            f"{tool} invokes {', '.join(senders)}, which may send, and this "
            f"layer does not see a tool's nested calls, so it cannot tell where "
            f"they go and no destination policy in force can allow them "
            f"(STANDARD 1.2.0 §4.4.2, §5.18.4)",
        )

    def _direct_destination_refusal(
        self, mapping: ToolMapping, tool: str, call: str | None, args: Any
    ) -> str | None:
        """:meth:`_destination_refusal` for the call's own ``send``."""
        found, value = (
            _json_pointer(args, mapping.destination)
            if mapping.destination is not None
            else (False, None)
        )
        if not found or not isinstance(value, str):
            if tool == "Bash":
                # The classifier's worst case includes send (section 5.18.3).
                sends, why = "may send", "a command line names no destination it reads"
            elif mapping.destination is None:
                sends, why = "sends", "its binding names no destination argument"
            else:
                sends = "sends"
                why = f"its argument at {mapping.destination!r} is not a string"
            return self._refuse(
                ErrorCode.CONSTRAINT_VIOLATED,
                mapping,
                tool,
                call,
                f"{tool} {sends}, and this layer cannot tell where: {why}, so no "
                f"destination policy in force can allow it (STANDARD 1.2.0 §4.4.2)",
            )
        if _core.destination_allowed(self._destinations, value):
            return None
        return self._refuse(
            ErrorCode.CONSTRAINT_VIOLATED,
            mapping,
            tool,
            call,
            f"{tool} sends to a destination the destination policies in force do "
            f"not allow (STANDARD 1.2.0 §4.4.2)",
        )

    def _secret_refusal(
        self, mapping: ToolMapping, tool: str, call: str | None, args: Any
    ) -> str | None:
        """The F504 refusal of a ``persist`` call whose data, or an
        ``audit`` call whose record, holds a secret the layer recognises
        (§5.18.10, §6.7): refused, not redacted, since memory is read back
        as fact. None for any other call."""
        capabilities = set(mapping.capabilities) & {"persist", "audit"}
        if not capabilities or not self.redactor.holds_credential(args):
            return None
        what = (
            "the data it would store"
            if "persist" in capabilities
            else "the record it would append"
        )
        return self._refuse(
            ErrorCode.CONSTRAINT_VIOLATED,
            mapping,
            tool,
            call,
            f"{what} holds what looks like a credential; persist where the "
            f"secret is kept, or cite it by reference, not the secret "
            f"(STANDARD v1.2 §6.7)",
        )

    # ------------------------------------------------------------------
    # Grounding of call outputs (STANDARD v1.2 section 5.20)
    # ------------------------------------------------------------------

    @property
    def _checks_call_outputs(self) -> bool:
        """Whether :meth:`check_call_output` applies any rule: a grounding
        policy (the configuration's or an applied profile's, section 5.21.3)
        or the profiles' minimum confidence."""
        return bool(self._grounding) or self.profiles.minimum_confidence is not None

    def check_call_output(
        self,
        tool: str,
        args: Any,
        output: Any,
        call: str | None = None,
    ) -> str | None:
        """Apply the grounding policies (``config.grounding``, then the
        applied profiles', section 5.21.3) and the profiles' minimum
        confidence to a call's output (§5.20 *Hosts outside a workflow*).
        The call's argument names are the references it binds (an
        ``acs:<argument>`` anchor may cite one), and no ``evidence_seen`` is
        given. Returns the refusal's text form (F505, or F504 with reason
        ``below_minimum_confidence`` or ``invalid_confidence``, kept in
        ``diagnostics`` and a call record) when the output fails, else None.
        Grounding is checked first, as the executor checks it. ``output``
        that is not an object fails a grounding policy as an output with no
        anchors; it has no confidence for a minimum to check."""
        fault = self._output_fault(tool, args, output)
        return None if fault is None else self._fail_call(*fault, call=call)

    def _output_fault(self, tool: str, args: Any, output: Any) -> _Fault | None:
        """What :meth:`check_call_output` refuses ``output`` with, without
        recording it."""
        if not self._checks_call_outputs:
            return None
        minimum = self.profiles.minimum_confidence
        mapping = self.mapper.map_tool(tool, args if isinstance(args, dict) else {})
        capability = mapping.capability_id if mapping is not UNCLASSIFIED_TOOL else None
        if not capability:
            return None
        policies = [p for p in self._grounding if p.requires(capability)]
        if not policies and minimum is None:
            return None
        bound = [
            k
            for k in (args if isinstance(args, dict) else {})
            if isinstance(k, str) and _IDENTIFIER.fullmatch(k)
        ]
        message: str | None = None
        code = ErrorCode.PROVENANCE_MISSING
        reason: str | None = None
        if policies and not isinstance(output, dict):
            message = (
                f"{tool}'s result holds no {capability} output (section 5.18.9), "
                "so nothing grounds it, and a grounding policy requires "
                f"{capability} (section 5.20)"
            )
        else:
            for policy in policies:
                result = check_output(output, policy, bound_refs=bound)
                if not result.ok:
                    message = f"{tool}'s output: {result.message}"
                    break
        if message is None and minimum is not None:
            fault = _core.check_confidence(output, minimum)
            if fault is not None:
                message = f"{tool}'s output: {fault['message']} (section 5.21.3)"
                code = ErrorCode.CONSTRAINT_VIOLATED
                reason = fault["reason"]
        if message is None:
            return None
        return _Fault(code, mapping, tool, message, reason)

    def check_call_result(
        self,
        tool: str,
        args: Any,
        result: Any,
        call: str | None = None,
    ) -> str | None:
        """Check the result of a call that has run, as the session reads
        it: its capability output and the output rules (STANDARD 1.2.0
        sections 5.18.9, 5.18.10, 5.20, 5.21.3), in the executor's order.
        ``create_grounded_mcp_server``'s tools call it with their result; the
        PostToolUse hook calls it for a bound tool of another MCP server
        (:meth:`_host_result_fault`).

        1. With ``config.check_outputs``, the result must carry the
           capability's output as the session reads it
           (:func:`~grounded_agency.capabilities.output.tool_result_output`:
           the I-JSON text of the output object as its one text item; the
           SDK's server does not deliver ``structuredContent``) and satisfy
           the capability's output contract; otherwise R402.
        2. Then :meth:`check_call_output`: the grounding policies (F505) and
           the profiles' minimum confidence (F504), on that output.

        An error result carries no output and is passed on: the call
        failed, and the post-call hooks record it. A result is an error
        only when its ``is_error`` is ``True``, as the session receives it;
        any other value is checked. A tool with no capability (unbound) has
        no output contract. With ``check_outputs`` off (outside class SL)
        step 1 is skipped, and step 2 reads the output the one text item
        carries, the text the session reads (:meth:`_unchecked_output`).
        Returns the refusal's text form, recorded against ``call`` as the
        failure of the call that ran (decision ``failed``), or None."""
        fault = self._result_fault(tool, args, result)
        return None if fault is None else self._fail_call(*fault, call=call)

    def _result_fault(self, tool: str, args: Any, result: Any) -> _Fault | None:
        """What :meth:`check_call_result` refuses ``result`` with, without
        recording it. The same result gives the same answer, so hooks that
        run side by side on one result agree on it."""
        if isinstance(result, dict) and result.get("is_error") is True:
            return None
        if not self.config.check_outputs:
            if not self._checks_call_outputs or not isinstance(result, dict):
                return None
            return self._output_fault(
                tool, args, self._unchecked_output(tool, args, result)
            )
        mapping = self.mapper.map_tool(tool, args if isinstance(args, dict) else {})
        capability = mapping.capability_id if mapping is not UNCLASSIFIED_TOOL else None
        if not capability:
            return None
        from .capabilities.output import CapabilityOutputError, tool_result_output

        try:
            output = tool_result_output(capability, result, self.registry)
        except CapabilityOutputError as e:
            return _Fault(
                ErrorCode.EXECUTION_FAILED,
                mapping,
                tool,
                f"{tool}'s result: {e.error.message} (section 5.18.9)",
            )
        return self._output_fault(tool, args, output)

    def _unchecked_output(
        self, tool: str, args: Any, result: dict[str, Any]
    ) -> dict[str, Any] | None:
        """The output of a result with ``check_outputs`` off: the capability
        output its one text item carries, the text the session reads, else
        None. A ``structuredContent`` member is not delivered to the session
        and is not read."""
        texts = [
            c.get("text")
            for c in result.get("content") or []
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        mapping = self.mapper.map_tool(tool, args if isinstance(args, dict) else {})
        capability = mapping.capability_id if mapping is not UNCLASSIFIED_TOOL else None
        if len(texts) != 1 or not isinstance(texts[0], str) or not capability:
            return None
        from .capabilities.output import CapabilityOutputError, decode_capability_output

        try:
            return decode_capability_output(capability, texts[0], self.registry)
        except CapabilityOutputError:
            return None

    def _checks_host_result(self, tool: str, mapping: ToolMapping) -> bool:
        """Whether this layer checks the result of a call of ``tool`` at
        PostToolUse: a tool of an MCP server that ``create_grounded_mcp_server``
        does not serve (another server, or one served with
        ``require_layer=False``), bound to a capability. Its result reaches
        the hook as the MCP result the session reads, and the hook can
        replace it (sections 5.18.9, 5.18.10). A served tool checks its own
        result (:meth:`check_call_result`); a control-only or unbound tool
        has no output contract; Claude Code's own tools return results in
        their own forms, which carry no capability output."""
        if not tool.startswith("mcp__"):
            return False
        if mapping is UNCLASSIFIED_TOOL or mapping.control or not mapping.capability_id:
            return False
        with self._state_lock:
            return tool not in self._grounded_tools

    def _may_check_host_result(self, tool: str, args: Any) -> bool:
        """:meth:`_checks_host_result` for a call whose mapping may not be
        readable: an MCP tool whose mapping fails counts as checked, so a
        hook that cannot finish fails closed (section 5.18.8)."""
        if not tool.startswith("mcp__"):
            return False
        try:
            mapping = self.mapper.map_tool(tool, args if isinstance(args, dict) else {})
            return self._checks_host_result(tool, mapping)
        except Exception:
            return True

    def _host_result_fault(self, tool: str, args: Any, response: Any) -> _Fault | None:
        """What the PostToolUse hook refuses the result of a call with
        (:meth:`_checks_host_result`), without recording it: the result as
        the hook receives it (``tool_response``: the content items, or a
        result that holds them) checked as :meth:`check_call_result` checks
        a served tool's. The same input gives the same answer, so the hooks
        that run side by side on one result (the checkpoint recorder and the
        post-call recorder) agree on it."""
        mapping = self.mapper.map_tool(tool, args if isinstance(args, dict) else {})
        if not self._checks_host_result(tool, mapping):
            return None
        return self._result_fault(tool, args, _mcp_tool_result(response))

    def _refuses_host_result(self, tool: str, args: Any, response: Any) -> bool:
        """Whether the PostToolUse hook refuses this result: the checkpoint
        recorder's test (a call whose output is refused takes no
        checkpoint, section 5.18.6)."""
        return self._host_result_fault(tool, args, response) is not None

    def _fail_call(
        self,
        code: ErrorCode,
        mapping: ToolMapping,
        tool: str,
        message: str,
        reason: str | None = None,
        *,
        call: str | None,
        checkpoint_id: str | None = None,
    ) -> str:
        """Refuse the output of a call that has run (sections 5.18.10,
        5.20): its outcome is a failure with the code, recorded against the
        call, not a refusal of a call that did not run. The post-call hooks
        do not record it again. A call whose output is refused has failed:
        it takes no checkpoint (§5.18.6) and is not a prerequisite that ran
        (§5.18.5)."""
        text = self._refuse(
            code,
            mapping,
            tool,
            call,
            message,
            outcome="failed",
            reason=reason,
            checkpoint_id=checkpoint_id,
        )
        if call is not None:
            with self._state_lock:
                self._outcome_recorded.add(call)
        return text

    def _unheld_call_refusal(self, mapping: ToolMapping, tool: str) -> str:
        """The refusal of a call that needs a checkpoint and carries no
        ``tool_use_id``: F501 when no valid checkpoint exists, as for any
        call; else R407, since this layer cannot hold one for a call it
        cannot name (section 5.18.6)."""
        if not self.checkpoint_tracker.has_valid_checkpoint():
            return self._refuse(
                ErrorCode.CHECKPOINT_REQUIRED,
                mapping,
                tool,
                None,
                _checkpoint_message(mapping, tool, None),
            )
        return self._refuse(
            ErrorCode.SAFETY_CHECK_FAILED,
            mapping,
            tool,
            None,
            f"{tool} has no tool_use_id, so this layer cannot hold a checkpoint for it",
        )

    def _take_outcome_recorded(self, call: str | None) -> bool:
        """Whether a grounded MCP tool already recorded ``call``'s outcome
        (and forget it)."""
        if call is None:
            return False
        with self._state_lock:
            if call in self._outcome_recorded:
                self._outcome_recorded.discard(call)
                return True
            return False

    # ------------------------------------------------------------------
    # Records (STANDARD 1.2.0 section 5.18.8)
    # ------------------------------------------------------------------

    @property
    def recorded_by(self) -> dict[str, Any]:
        """The layer and its configuration, as every record names it: name,
        version and ``config_sha256``, the SHA-256 of the canonical JSON of
        the settings and bindings that decide a call.

        The digest is computed again only when a setting or a binding
        changed, not for every record."""
        from . import __version__, _core

        settings: dict[str, Any] = {
            "strict_mode": self.config.strict_mode,
            "approval": self.config.approval,
            "expiry_minutes": self.config.expiry_minutes,
            "checkpoint_reservation_seconds": self.config.checkpoint_reservation_seconds,
            # The host policy behind F504 refusals (section 5.18.8).
            "rate_limit": {
                "high_rpm": self.config.rate_limit.high_rpm,
                "medium_rpm": self.config.rate_limit.medium_rpm,
                "low_rpm": self.config.rate_limit.low_rpm,
                "burst_multiplier": self.config.rate_limit.burst_multiplier,
            },
            "ontology_version": self.registry.version,
            "prompting_modes": sorted(PROMPTING_PERMISSION_MODES),
        }
        if self.profiles:
            # The applied profiles decide calls too (section 5.21).
            settings["profiles"] = self.profiles.documents
        if self.config.grounding:
            # The policies behind F505 refusals (section 5.20); no secret
            # value is ever part of the configuration's digest.
            settings["grounding"] = [p.to_dict() for p in self.config.grounding]
        if self.config.allowed_destinations is not None:
            # The host policy behind F504 refusals of sends (section 4.4.2).
            settings["allowed_destinations"] = list(self.config.allowed_destinations)
        if not self.config.check_outputs:
            # Results pass on unchecked (no R402, section 5.18.10); the
            # default, checked, leaves the digest as it was.
            settings["check_outputs"] = False
        key = (self.mapper.records_revision, _core.canonical_json(settings))
        cached = self._config_digest
        if cached is not None and cached[0] == key:
            digest = cached[1]
        else:
            # Every loaded binding is I-JSON (section 5.14): a record that is
            # not does not load (S303), so this cannot fail on one.
            config = {**settings, "bindings": self.mapper.records}
            digest = hashlib.sha256(
                _core.canonical_json(config).encode("utf-8")
            ).hexdigest()
            self._config_digest = (key, digest)
        return {
            "name": "grounded_agency.adapter",
            "version": __version__,
            "config_sha256": digest,
        }

    def _record(
        self,
        decision: str,
        tool: str,
        mapping: ToolMapping | None,
        call: str | None,
        **details: Any,
    ) -> None:
        """Append one call record."""
        entry: dict[str, Any] = {"at": _now_iso(self._now), "tool": tool}
        if mapping is not None and mapping is not UNCLASSIFIED_TOOL:
            entry["capability"] = mapping.capability_id or None
            if mapping.control:
                entry["control"] = True
        else:
            entry["capability"] = None
        # An applied profile required a person (section 5.21.3), for an
        # unbound tool too: it is treated as mutate (section 5.18.2).
        if mapping is not None and self.mapper.person_required(mapping):
            entry["person_required"] = True
        if call is not None:
            entry["call"] = call
        entry["decision"] = decision
        kept = {k: v for k, v in details.items() if v is not None}
        # A record of a call carries no secret (§6.7).
        kept, _ = self.redactor.redact(kept)
        entry.update(kept)
        entry["recorded_by"] = self.recorded_by
        with self._state_lock:
            self._record_seq += 1
            entry["seq"] = self._record_seq
            self.call_records.append(entry)

    def export_action_records(self, scope: str) -> list[dict[str, Any]]:
        """The call records still kept, as audit records (STANDARD 1.2.0
        section 6.4), in the order written; ``scope`` names the layer scope
        (see ``call_action_record``). A boundary entry has none."""
        with self._state_lock:
            entries = list(self.call_records)
        records = (call_action_record(entry, scope) for entry in entries)
        return [record for record in records if record is not None]

    def _refuse(
        self,
        code: ErrorCode,
        mapping: ToolMapping,
        tool: str,
        call: str | None,
        message: str,
        *,
        outcome: Literal["refused", "failed"] = "refused",
        **details: Any,
    ) -> str:
        """A refusal (section 5.18.8): the §9.8 diagnostic, kept in
        ``diagnostics`` and a call record; returns its text form. Its message
        is redacted (§6.7): a diagnostic carries no secret. ``outcome`` is
        the record's decision: ``refused`` for a call that does not run,
        ``failed`` for one that ran and whose result is refused (R402, F505,
        F504)."""
        message, _ = self.redactor.redact_text(message)
        location: dict[str, Any] = {"tool": tool}
        if mapping is not UNCLASSIFIED_TOOL and mapping.capability_id:
            location["capability"] = mapping.capability_id
        if call is not None:
            location["call"] = call
        error = _error(code, message, location)
        with self._state_lock:
            self.diagnostics.append(error)
        try:
            self._record(
                outcome,
                tool,
                mapping,
                call,
                diagnostic={
                    "code": error.code_str,
                    "name": error.name,
                    "severity": error.severity.value,
                    "message": error.message,
                    "location": error.location,
                },
                **details,
            )
        except Exception:
            logger.exception("Could not record the refusal of %s", tool)
        text = text_form(error)
        logger.warning("Refused: %s", text)
        return text

    def _shown_digest(self, tool: str, mapping: ToolMapping, args: Any) -> str:
        """The §5.14 digest of what a call's approvers are shown
        (section 5.18.7): ``[{"action", "capability", "args"}]``.

        Raises:
            ValueError: If the arguments are not I-JSON (section 5.14), a
                float that canonical JSON writes as an integer beyond ±2^53
                included.
        """
        from . import _core
        from .capabilities.bindings import i_json_problem

        problem = i_json_problem(args)
        if problem is not None:
            raise ValueError(f"the value {problem}")
        capability = (
            None
            if mapping is UNCLASSIFIED_TOOL or not mapping.capability_id
            else mapping.capability_id
        )
        return str(
            _core.approval_digest(
                [{"action": tool, "capability": capability, "args": args}]
            )
        )

    def _prerequisite_refusal(
        self, mapping: ToolMapping, tool: str, call: str | None
    ) -> str | None:
        """The refusal for a prerequisite that has not run in this scope
        (section 5.18.5), or None: a missing checkpoint is F501, or F503 for
        a call of ``rollback``; any other prerequisite V102."""
        for needed in sorted(mapping.prerequisites):
            if needed == "checkpoint":
                if self.checkpoint_tracker.has_taken_since(self._started_at):
                    continue
                if "rollback" in mapping.capabilities:
                    return self._refuse(
                        ErrorCode.ROLLBACK_FAILED,
                        mapping,
                        tool,
                        call,
                        f"{_subject(mapping, tool)} restores a checkpoint, and "
                        f"no checkpoint was taken in this scope; there is "
                        f"nothing to roll back to.",
                    )
                return self._refuse(
                    ErrorCode.CHECKPOINT_REQUIRED,
                    mapping,
                    tool,
                    call,
                    f"{_subject(mapping, tool)} requires checkpoint, and no "
                    f"checkpoint was taken in this scope. Take a checkpoint, "
                    f"then call {tool} again.",
                )
            with self._state_lock:
                ran = needed in self._executed
            if not ran:
                return self._refuse(
                    ErrorCode.MISSING_PREREQUISITE,
                    mapping,
                    tool,
                    call,
                    f"{_subject(mapping, tool)} requires a '{needed}' call to "
                    f"have completed first in this scope. Call a '{needed}' "
                    f"tool, then call {tool} again.",
                )
        return None

    def _call_dir(self, call: str | None, input_data: dict[str, Any]) -> str | None:
        """The directory a call that reported back ran in (its hook input's
        `cwd`), forgetting the one its PreToolUse hook kept."""
        with self._state_lock:
            kept = self._call_dirs.pop(call, None) if call else None
        return _cwd_of(input_data) or kept

    @staticmethod
    def _take_entry(
        table: dict[tuple[str, str], list[str | None]],
        key: tuple[str, str],
        call: str | None,
    ) -> tuple[bool, str | None]:
        """Remove ``call``'s own entry under ``key`` when it has one, else
        the oldest: (whether one was there, the call id it named). The
        caller holds the state lock."""
        calls = table.get(key)
        if not calls:
            return False, None
        if call in calls:
            calls.remove(call)
            taken = call
        else:
            taken = calls.pop(0)
        if not calls:
            del table[key]
        return True, taken

    def _allow_token(
        self, tool: str, args: Any, delta: int = 1, call: str | None = None
    ) -> None:
        """Grant (``delta`` > 0) or withdraw (``delta`` < 0) the decision for
        a call of ``tool`` with ``args``; a withdrawal takes ``call``'s own
        grant when it has one, else the oldest. A call already granted is
        not granted twice."""
        key = (tool, _args_key(args))
        with self._state_lock:
            if delta > 0:
                calls = self._allowed.setdefault(key, [])
                if call is None or call not in calls:
                    calls.extend([call] * delta)
            for _ in range(-delta):
                if not self._take_entry(self._allowed, key, call)[0]:
                    break

    def _ask_token(self, tool: str, args: Any, call: str | None) -> None:
        """Note that the PreToolUse hook asked about a call of ``tool``
        with ``args``: no decision yet, so nothing is granted."""
        key = (tool, _args_key(args))
        with self._state_lock:
            calls = self._asked_calls.setdefault(key, [])
            if call is None or call not in calls:
                calls.append(call)

    def _settle_decision(
        self,
        tool: str,
        args: Any,
        call: str | None,
        allowed_args: dict[str, Any] | None = None,
    ) -> bool:
        """Settle the permission callback's decision on a call of ``tool``
        with ``args``: what the PreToolUse hook left for it (its ask, or
        its pass's grant) is withdrawn; on an allow (``allowed_args``, the
        arguments the call runs with), the call is granted for those, but
        only when the hook passed or asked about it. Returns whether it
        was granted."""
        key = (tool, _args_key(args))
        with self._state_lock:
            asked, asked_id = self._take_entry(self._asked_calls, key, call)
            passed, passed_id = self._take_entry(self._allowed, key, call)
            if allowed_args is None or not (asked or passed):
                return False
            grant = call if call is not None else (asked_id if asked else passed_id)
            calls = self._allowed.setdefault((tool, _args_key(allowed_args)), [])
            if grant is None or grant not in calls:
                calls.append(grant)
            return True

    def _forget_call(self, call: str | None) -> None:
        """Forget a call that reported back (it ran, or failed): a decision
        it left that no grounded MCP tool took, and its ask, authorise
        nothing more."""
        if call is None:
            return
        with self._state_lock:
            for table in (self._allowed, self._asked_calls):
                for key in [k for k, calls in table.items() if call in calls]:
                    calls = table[key]
                    calls.remove(call)
                    if not calls:
                        del table[key]

    def _take_allowed(self, tool: str, args: Any) -> tuple[bool, str | None]:
        """:meth:`take_allowed`, and the call id of the decision used."""
        key = (tool, _args_key(args))
        with self._state_lock:
            calls = self._allowed.get(key)
            if not calls:
                return False, None
            call = calls.pop(0)
            if not calls:
                del self._allowed[key]
            return True, call

    def take_allowed(self, tool: str, args: Any) -> bool:
        """Use up this layer's decision for a call of ``tool`` with ``args``.

        A grounded MCP tool calls this before it runs
        (``create_grounded_mcp_server(require_layer=True)``): False means
        the call reached the tool without the layer allowing it, and the
        tool refuses with R407 (section 5.18.8). A decision is granted
        only when a call is allowed: the PreToolUse hook's pass, or the
        permission callback's allow of a call the hook asked about; an
        ask grants nothing, and every refusal the layer makes, a call
        that reports back, and a boundary withdraw it.
        """
        return self._take_allowed(tool, args)[0]

    def _register_grounded_tool(self, tool: str) -> None:
        """Note that ``create_grounded_mcp_server`` serves ``tool``: its
        output reaches this layer, so a grounding policy checks it, and
        it runs only a call this layer allowed."""
        with self._state_lock:
            self._grounded_tools.add(tool)

    def _is_grounded_tool(self, tool: str) -> bool:
        """Whether ``create_grounded_mcp_server`` serves ``tool``."""
        with self._state_lock:
            return tool in self._grounded_tools

    def _warn_unchecked_output(self, mapping: ToolMapping, tool: str) -> None:
        """Warn, once per tool, that a grounding policy (the
        configuration's or an applied profile's) requires the capability of
        a call whose output this layer never sees, or that a profile sets a
        minimum confidence for it (a tool whose result carries no capability
        output: Claude Code's own tools, which return results in their own
        forms): section 5.20, and the minimum of section 5.21.3, are not
        applied to it. The tools ``create_grounded_mcp_server`` serves and
        the bound tools of other MCP servers are checked
        (:meth:`check_call_result`, :meth:`_checks_host_result`)."""
        if mapping is UNCLASSIFIED_TOOL or not self._checks_call_outputs:
            return
        required = sorted(
            {c for c in mapping.capabilities for p in self._grounding if p.requires(c)}
        )
        if not required and self.profiles.minimum_confidence is None:
            return
        if self._checks_host_result(tool, mapping):
            return
        with self._state_lock:
            if tool in self._grounded_tools or tool in self._ungrounded_warned:
                return
            self._ungrounded_warned.add(tool)
        rules = []
        if required:
            rules.append(f"a grounding policy requires {', '.join(required)}")
        if self.profiles.minimum_confidence is not None:
            rules.append("an applied profile sets a minimum confidence")
        logger.warning(
            "For %s, %s; but its result is not a capability output this "
            "layer sees (it is not the result of an MCP tool bound to a "
            "capability), so neither section 5.20 nor the minimum of section "
            "5.21.3 is applied to its calls",
            tool,
            " and ".join(rules),
        )

    def _get_or_create_workflow_engine(self) -> Any:
        """Lazy-create a WorkflowEngine for discovery integration."""
        if self._workflow_engine is None:
            from .workflows.engine import WorkflowEngine

            self._workflow_engine = WorkflowEngine(
                ontology_path=self.config.ontology_path,
                checkpoint_tracker=self.checkpoint_tracker,
                schema_root=self._schema_root,
            )
        return self._workflow_engine

    def wrap_options(self, base: Any) -> Any:
        """
        Wrap SDK options with grounded agency safety layer.

        Injects:
        - enable_file_checkpointing=True for SDK-level rollback
        - a PreToolUse hook for the rate limit, the prerequisites, the
          checkpoint rule and the approval rule, whose matcher has
          ``on_failure="block"`` (the SDK then refuses to connect to a
          Claude Code that does not honour it)
        - a can_use_tool callback that passes the decision to the
          ``can_use_tool`` callback of ``base``, if it has one, re-checks the
          call (arguments the host changed are classified again) and uses
          its checkpoint up when the call is allowed
        - PostToolUse hooks for evidence collection, the checkpoint recorder
          (registered for every tool) and the use of a held checkpoint by a
          call that ran; a PostToolUseFailure hook that uses it too
        - a Stop hook (the end of a turn is an execution boundary), a
          UserPromptSubmit hook (the start of a turn is one too: it ends
          what a turn left when its Stop never came, after an API error or
          an interrupt) and a SubagentStop hook (a finished subagent's
          holds count as used)

        The layer's scope is this adapter: every session and subagent it
        serves, ordered by its lock. The Stop or the next prompt of any of
        them ends the validity of every checkpoint it holds; serve sessions
        that must not share boundaries with separate adapters. Only the
        checkpoints it took authorise its calls, not those its tracker reads
        back from ``checkpoint_dir``. Its maximum
        age is ``config.expiry_minutes``; it relies on a permission prompt only in
        the permission modes of :data:`PROMPTING_PERMISSION_MODES`, read
        from the hook input, else from ``base.permission_mode``.

        ``allowed_tools`` is passed through unchanged; ``Skill`` is not
        added. The SDK approves a tool listed there without consulting
        ``can_use_tool`` (and warns that the callback is shadowed). The
        checks run in the PreToolUse hook, so they apply to listed tools too.

        Where ``base`` names a ``permission_prompt_tool_name``, no
        ``can_use_tool`` callback is installed: the SDK refuses the two
        together, and that tool is then the permission flow that answers
        the hook's ``"ask"``. This layer then never sees a call allowed, so
        it cannot check again, at the allow, that a held checkpoint is
        still valid, nor when a decision arrived (STANDARD 1.2.0 sections
        5.18.6, 5.18.7): the PreToolUse hook refuses a call that requires a
        checkpoint (R407) and one whose binding sets ``approval.expires``
        (F502), and so is a call that requires approval of a tool
        ``create_grounded_mcp_server`` serves (R407: that tool runs only a
        call this layer saw allowed). The prompt tool decides the other
        calls that require approval.

        Args:
            base: ClaudeAgentOptions instance

        Returns:
            Modified ClaudeAgentOptions with safety layer

        Note:
            The type is Any to avoid hard dependency on claude_agent_sdk.
            At runtime, expects a ClaudeAgentOptions dataclass.
        """
        # Build hooks dict
        existing_hooks = getattr(base, "hooks", None) or {}
        # Options this adapter already wrapped keep their hooks (adding a
        # second safety hook would charge the rate limit twice per call);
        # everything else below is applied again.
        already_wrapped = self._already_wrapped(existing_hooks)
        post_hooks = list(existing_hooks.get("PostToolUse", []))

        # Add evidence collector
        evidence_hook = create_evidence_collector(
            store=self.evidence_store,
            mapper=self.mapper,
            include_tool_input=self.config.evidence_include_tool_input,
        )
        post_hooks.append(self._wrap_hook(evidence_hook))

        # The checkpoint recorder: every tool, since any call classified
        # checkpoint takes one (STANDARD 1.2.0 section 5.18.6).
        recorder = create_checkpoint_recorder(
            self.checkpoint_tracker,
            self.mapper,
            expiry_minutes=self.config.expiry_minutes,
            refuses_output=self._refuses_host_result,
        )
        post_hooks.append(self._wrap_hook(recorder))

        # A call that ran uses the checkpoint it still holds.
        post_hooks.append(self._wrap_hook(self._make_mutation_consumer()))

        # A failed or interrupted call uses it too: it may have changed
        # something before it failed.
        failure_hooks = list(existing_hooks.get("PostToolUseFailure", []))
        failure_hooks.append(self._wrap_hook(self._make_failure_recorder()))

        # PreToolUse hook: every check of section 5.18
        pre_hooks = list(existing_hooks.get("PreToolUse", []))
        safety_pre_hook = self._make_pretooluse_safety_hook(
            options_mode=getattr(base, "permission_mode", None),
            prompt_tool=bool(getattr(base, "permission_prompt_tool_name", None)),
        )
        safety_pre_hook._grounded_adapter = self  # see _already_wrapped
        # It refuses with R407 when a check fails inside it; a callback that
        # fails or gives no verdict in time, seen from the CLI, blocks the
        # call too (section 5.18.8), where the SDK can say so.
        pre_hooks.append(self._wrap_hook(safety_pre_hook, on_failure="block"))

        # Stop and UserPromptSubmit: execution boundaries (a turn's end, and
        # the next turn's start, which also ends what a turn left when its
        # Stop never came). SubagentStop: that agent's holds are unresolved
        # and count as used.
        stop_hooks = list(existing_hooks.get("Stop", []))
        stop_hooks.append(self._wrap_hook(self._make_boundary()))
        prompt_hooks = list(existing_hooks.get("UserPromptSubmit", []))
        prompt_hooks.append(self._wrap_hook(self._make_boundary("turn started")))
        subagent_stop_hooks = list(existing_hooks.get("SubagentStop", []))
        subagent_stop_hooks.append(self._wrap_hook(self._make_subagent_end()))

        # Add discovery injector if enabled
        if self.config.enable_discovery:
            from .discovery.pipeline import DiscoveryPipeline
            from .hooks.discovery_injector import create_discovery_injector

            discovery_pipeline = DiscoveryPipeline(
                registry=self.registry,
                engine=self._get_or_create_workflow_engine(),
                evidence_store=self.evidence_store,
                evidence_include_tool_input=self.config.evidence_include_tool_input,
            )
            discovery_hook = create_discovery_injector(
                pipeline=discovery_pipeline,
                store=self.evidence_store,
            )
            pre_hooks.append(self._wrap_hook(discovery_hook))

        merged_hooks = (
            existing_hooks
            if already_wrapped
            else {
                **existing_hooks,
                "PreToolUse": pre_hooks,
                "PostToolUse": post_hooks,
                "PostToolUseFailure": failure_hooks,
                "Stop": stop_hooks,
                "UserPromptSubmit": prompt_hooks,
                "SubagentStop": subagent_stop_hooks,
            }
        )

        # Ensure setting_sources includes project (for skills)
        setting_sources = getattr(base, "setting_sources", None) or ["project"]
        if "project" not in setting_sources:
            setting_sources = list(setting_sources) + ["project"]

        # Build kwargs for dataclasses.replace
        kwargs: dict[str, Any] = {
            "enable_file_checkpointing": True,
            "hooks": merged_hooks,
            "setting_sources": setting_sources,
        }

        # The permission callback. The SDK refuses can_use_tool beside a
        # permission prompt tool, so a host that decides permissions with
        # one keeps it; the PreToolUse hook still runs for every call.
        if not getattr(base, "permission_prompt_tool_name", None):
            host_callback = getattr(base, "can_use_tool", None)
            if getattr(host_callback, "_grounded_adapter", None) is self:
                # Options this adapter already wrapped: chain to the
                # callback they came with, not to this adapter's own.
                host_callback = getattr(host_callback, "_host_can_use_tool", None)
            permission_callback = self._make_permission_callback(host_callback)
            permission_callback._grounded_adapter = self
            permission_callback._host_can_use_tool = host_callback
            kwargs["can_use_tool"] = permission_callback

        # Inject output_format if configured and not already set
        if (
            self.config.output_format is not None
            and getattr(base, "output_format", None) is None
        ):
            kwargs["output_format"] = self.config.output_format

        # Inject max_budget_usd if configured and not already set
        if (
            self.config.max_budget_usd is not None
            and getattr(base, "max_budget_usd", None) is None
        ):
            kwargs["max_budget_usd"] = self.config.max_budget_usd

        # Inject model if configured and not already set
        if self.config.model is not None and getattr(base, "model", None) is None:
            kwargs["model"] = self.config.model

        # Inject max_turns if configured and not already set
        if (
            self.config.max_turns is not None
            and getattr(base, "max_turns", None) is None
        ):
            kwargs["max_turns"] = self.config.max_turns

        # Inject agents from orchestrator if available and not already set
        if self.orchestrator and not getattr(base, "agents", None):
            if hasattr(self.orchestrator, "to_sdk_agents"):
                sdk_agents = self.orchestrator.to_sdk_agents()
                if sdk_agents:
                    kwargs["agents"] = sdk_agents

        return replace(base, **kwargs)

    def _already_wrapped(self, hooks: dict[str, Any]) -> bool:
        """Whether ``hooks`` already holds this adapter's safety hook."""
        for entry in hooks.get("PreToolUse") or []:
            if isinstance(entry, dict):
                fns = entry.get("hooks") or []
            else:
                fns = getattr(entry, "hooks", None) or []
            if any(getattr(fn, "_grounded_adapter", None) is self for fn in fns):
                return True
        return False

    def _wrap_hook(
        self,
        hook_fn: Any,
        matcher: str | None = None,
        on_failure: str | None = None,
    ) -> Any:
        """
        Wrap a hook function in the SDK's expected format.

        For simple integration, returns a dict with the hook.
        For advanced integration with SDK types, would use HookMatcher.

        Args:
            hook_fn: Async hook callback
            matcher: Optional tool matcher string
            on_failure: ``"block"``: the CLI blocks the action when the
                callback fails, as it sees it (an error, or no answer
                within the matcher's timeout). Set where the SDK's
                ``HookMatcher`` has ``on_failure``; an older SDK has no way
                to ask, and a warning says so. With it, connecting to a
                Claude Code that does not honour it raises
                ``CLIConnectionError``.

        Returns:
            Hook configuration dict or HookMatcher
        """
        # Try to use SDK's HookMatcher if available
        try:
            from claude_agent_sdk import HookMatcher
        except ImportError:
            # Fallback: return dict format (the SDK's internal form)
            config: dict[str, Any] = {"hooks": [hook_fn]}
            if matcher:
                config["matcher"] = matcher
            if on_failure is not None:
                config["on_failure"] = on_failure
            return config
        kwargs: dict[str, Any] = {"hooks": [hook_fn]}
        if matcher:
            kwargs["matcher"] = matcher
        if on_failure is not None:
            if "on_failure" in getattr(HookMatcher, "__dataclass_fields__", {}):
                kwargs["on_failure"] = on_failure
            else:
                logger.warning(
                    "This claude-agent-sdk's HookMatcher has no on_failure: a "
                    "safety hook that fails or times out in the CLI is no "
                    "decision there, so the call is not blocked. Update "
                    "claude-agent-sdk."
                )
        return HookMatcher(**kwargs)

    def _make_boundary(self, what: str = "turn ended") -> Any:
        """
        Create the Stop hook: the end of a turn is an execution boundary
        (STANDARD 1.2.0 section 5.18.6). With ``what`` "turn started", the
        UserPromptSubmit hook: the start of the next turn is one too, and it
        ends what a turn left when its Stop never came (Claude Code runs
        StopFailure in its place after an API error, and an interrupted
        turn may run neither).

        A hold still kept by a call of the stopping session is unresolved
        (the call never reported back), so its checkpoint counts as used.
        Then every checkpoint the adapter holds stops authorising anything,
        whatever session took it: one adapter is one scope. Holds of other
        sessions' calls in flight stay with them; one still waiting at a
        prompt is refused with F501 when it is allowed. The calls this layer
        allowed and that did not run are forgotten.

        Returns:
            Async hook callback function
        """
        tracker = self.checkpoint_tracker

        async def end_of_turn(
            input_data: dict[str, Any],
            tool_use_id: str | None,
            context: HookContext | None,
        ) -> dict[str, Any]:
            try:
                session = input_data.get("session_id")
                scope = (session, input_data.get("agent_id"))
                holders = tracker.resolve_holds_in_scope(scope)
                if holders:
                    logger.info("Turn ended: unresolved holds of %s used", holders)
                ended = tracker.end_validity(f"{what} in session {session}")
                with self._state_lock:
                    self._allowed.clear()
                    self._asked_calls.clear()
                    self._outcome_recorded.clear()
                    self._call_dirs.clear()
                    self._asked_at.clear()
                self._record(
                    "boundary",
                    "",
                    None,
                    None,
                    session=session,
                    ended=ended or None,
                    unresolved=holders or None,
                )
            except Exception as e:
                logger.error("Boundary (%s) failed: %s", what, e)
            return {}

        return end_of_turn

    def _make_subagent_end(self) -> Any:
        """Create the SubagentStop hook: a hold the finished subagent's calls
        still keep is unresolved and counts as used. Not a boundary."""
        tracker = self.checkpoint_tracker

        async def subagent_end(
            input_data: dict[str, Any],
            tool_use_id: str | None,
            context: HookContext | None,
        ) -> dict[str, Any]:
            try:
                scope = (input_data.get("session_id"), input_data.get("agent_id"))
                holders = tracker.resolve_holds_in_scope(scope)
                if holders:
                    logger.info("Subagent ended: unresolved holds of %s used", holders)
            except Exception as e:
                logger.warning("Subagent-end resolver failed: %s", e)
            return {}

        return subagent_end

    def _make_pretooluse_safety_hook(
        self, options_mode: str | None = None, prompt_tool: bool = False
    ) -> Any:
        """
        Create the PreToolUse hook that applies STANDARD 1.2.0 section 5.18
        to every tool call.

        PreToolUse runs for every tool call, including pre-approved ones in
        ``allowed_tools`` that never reach ``can_use_tool``, so the checks
        live here, in this order:

        1. Classify (a tool the mapper cannot classify is unbound: the
           strictest case).
        2. A control-only tool is allowed and recorded: no check applies.
        3. Rate limit (SEC-010): a call over its risk level's limit is
           refused with F504; a limiter failure with R407.
        4. Prerequisites (section 5.18.5): a checkpoint never taken in this
           scope is F501 (F503 for a ``rollback`` call); any other missing
           prerequisite V102.
        5. Checkpoint (F501): a gated call holds the newest valid checkpoint
           no other call holds, keyed by its ``tool_use_id`` (a call with
           none cannot hold one: R407). With ``prompt_tool`` the call is
           refused with R407 instead: a permission prompt tool may decide
           it, and this layer cannot check its hold again when it is
           allowed (section 5.18.6).
        6. Approval (F502), with ``approval="ask"``: a binding that needs
           more than one approver or an approver's role is refused, and so,
           with ``prompt_tool``, is one that sets ``approval.expires`` (this
           layer cannot see when that tool's decision arrives), and one of
           a tool ``create_grounded_mcp_server`` serves (R407: it runs only
           a call this layer saw allowed); in a
           permission mode outside :data:`PROMPTING_PERMISSION_MODES` the
           call is refused; otherwise the digest of the shown value is
           recorded, the time of the request noted for a binding that sets
           ``approval.expires``, and the hook answers ``permissionDecision:
           "ask"``. Each refusal releases the hold step 5 took.

        With ``strict_mode=False`` the checks of steps 4 and 5 log instead
        of refusing (outside class SL); approval still applies. Any other
        error refuses with R407 in strict mode.

        A refusal is ``hookSpecificOutput`` with ``permissionDecision:
        "deny"``, whose reason is the diagnostic's text form
        (``F501 CHECKPOINT_REQUIRED: ...``).

        Args:
            options_mode: The wrapped options' ``permission_mode``: used
                when the hook input carries none.
            prompt_tool: The wrapped options name a
                ``permission_prompt_tool_name``, so no permission callback
                sees a call allowed.

        Returns:
            Async hook callback function
        """
        tracker = self.checkpoint_tracker
        mapper = self.mapper
        strict = self.config.strict_mode
        limiter = self.rate_limiter
        # Anything but an explicit "off" asks.
        asks = self.config.approval != "off"

        def decide(decision: str, message: str) -> dict[str, Any]:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": message,
                }
            }

        def deny(message: str) -> dict[str, Any]:
            return decide("deny", message)

        async def check_before_tool(
            input_data: dict[str, Any],
            tool_use_id: str | None,
            context: HookContext | None,
        ) -> dict[str, Any]:
            """PreToolUse hook: every check of section 5.18, in order."""
            tool_name = ""
            # Until the call is classified, assume the strictest case.
            mapping = UNCLASSIFIED_TOOL
            call: str | None = None
            held = False
            tool_input: Any = {}

            def release() -> None:
                if held and call is not None:
                    try:
                        tracker.release_reservation(call)
                    except Exception as e:
                        logger.error("Could not release the hold of %s: %s", call, e)

            try:
                tool_name = input_data.get("tool_name", "")
                tool_input = input_data.get("tool_input", {})
                call = tool_use_id or input_data.get("tool_use_id")
                cwd = _cwd_of(input_data)
                if call is not None and cwd is not None:
                    with self._state_lock:
                        self._call_dirs[call] = cwd

                try:
                    mapping = mapper.map_tool(tool_name, tool_input, cwd)
                except Exception:
                    logger.exception(
                        "Could not classify %s; treating it as unbound", tool_name
                    )
                    mapping = UNCLASSIFIED_TOOL

                if mapping.control:
                    try:
                        self._record("allowed", tool_name, mapping, call)
                    except Exception:
                        logger.exception(
                            "Could not record control-only call %s", tool_name
                        )
                    return {}

                try:
                    within_limit = limiter.allow(mapping.risk)
                except Exception:
                    logger.exception("PreToolUse rate limit check failed")
                    return deny(
                        self._refuse(
                            ErrorCode.SAFETY_CHECK_FAILED,
                            mapping,
                            tool_name,
                            call,
                            f"the rate limit check of {tool_name} failed, so "
                            f"the call is refused",
                        )
                    )
                if not within_limit:
                    return deny(
                        self._refuse(
                            ErrorCode.CONSTRAINT_VIOLATED,
                            mapping,
                            tool_name,
                            call,
                            f"rate limit: {mapping.risk}-risk capability "
                            f"'{mapping.capability_id}' via {tool_name}. "
                            f"Too many invocations — please wait.",
                        )
                    )

                refusal = self._secret_refusal(
                    mapping, tool_name, call, tool_input
                ) or self._destination_refusal(mapping, tool_name, call, tool_input)
                if refusal is not None:
                    return deny(refusal)
                self._warn_unchecked_output(mapping, tool_name)

                refusal = self._prerequisite_refusal(mapping, tool_name, call)
                if refusal is not None:
                    if strict:
                        return deny(refusal)
                    logger.warning("PreToolUse warning (non-strict): %s", refusal)

                if mapping.requires_checkpoint and prompt_tool:
                    message = self._refuse(
                        ErrorCode.SAFETY_CHECK_FAILED,
                        mapping,
                        tool_name,
                        call,
                        f"{_subject(mapping, tool_name)} requires a checkpoint, "
                        f"and a permission prompt tool decides this session's "
                        f"calls: this layer never sees the call allowed, so it "
                        f"cannot check again then that the checkpoint is still "
                        f"valid (STANDARD 1.2.0 §5.18.6). {tool_name} did not "
                        f"run; the host can pass a can_use_tool callback "
                        f"instead of the prompt tool.",
                    )
                    if strict:
                        return deny(message)
                    logger.warning("PreToolUse warning (non-strict): %s", message)
                elif mapping.requires_checkpoint:
                    scope = (input_data.get("session_id"), input_data.get("agent_id"))
                    if call is None:
                        message = self._unheld_call_refusal(mapping, tool_name)
                        if strict:
                            return deny(message)
                        logger.warning("PreToolUse warning (non-strict): %s", message)
                    else:
                        held, checkpoint_id = tracker.validate_and_reserve(
                            call, scope=scope
                        )
                        if not held:
                            message = self._refuse(
                                ErrorCode.CHECKPOINT_REQUIRED,
                                mapping,
                                tool_name,
                                call,
                                _checkpoint_message(mapping, tool_name, checkpoint_id),
                            )
                            if strict:
                                return deny(message)
                            logger.warning(
                                "PreToolUse warning (non-strict): %s", message
                            )

                if asks and mapping.requires_approval:
                    policy = mapping.approval
                    if policy is not None and policy.min_approvers > 1:
                        release()
                        return deny(
                            self._refuse(
                                ErrorCode.APPROVAL_REQUIRED,
                                mapping,
                                tool_name,
                                call,
                                f"{_subject(mapping, tool_name)} needs "
                                f"{policy.min_approvers} approvers; this layer "
                                f"obtains one per call",
                            )
                        )
                    if policy is not None and policy.role is not None:
                        release()
                        return deny(
                            self._refuse(
                                ErrorCode.APPROVAL_REQUIRED,
                                mapping,
                                tool_name,
                                call,
                                f"{_subject(mapping, tool_name)} needs an "
                                f"approver with role '{policy.role}'; a "
                                f"permission prompt cannot show this layer the "
                                f"person's role",
                            )
                        )
                    expires = policy.expires_seconds if policy is not None else None
                    if expires is not None and prompt_tool:
                        release()
                        return deny(
                            self._refuse(
                                ErrorCode.APPROVAL_REQUIRED,
                                mapping,
                                tool_name,
                                call,
                                f"{_subject(mapping, tool_name)} takes a "
                                f"decision only within {expires:g} s of the "
                                f"request (its binding's approval.expires), and "
                                f"a permission prompt tool decides this "
                                f"session's calls: this layer cannot see when "
                                f"its decision arrives (STANDARD 1.2.0 §5.18.7). "
                                f"{tool_name} did not run.",
                            )
                        )
                    if prompt_tool and self._is_grounded_tool(tool_name):
                        release()
                        return deny(
                            self._refuse(
                                ErrorCode.SAFETY_CHECK_FAILED,
                                mapping,
                                tool_name,
                                call,
                                f"{_subject(mapping, tool_name)} requires "
                                f"approval, and a permission prompt tool decides "
                                f"this session's calls: this layer never sees "
                                f"the call allowed, so the grounded MCP tool "
                                f"cannot tell an allowed call from one that "
                                f"was refused or never decided (STANDARD 1.2.0 "
                                f"§5.18.8). {tool_name} did not run; the host "
                                f"can pass a can_use_tool callback instead of "
                                f"the prompt tool.",
                            )
                        )
                    mode = (
                        input_data.get("permission_mode") or options_mode or "default"
                    )
                    if mode not in PROMPTING_PERMISSION_MODES:
                        release()
                        return deny(
                            self._refuse(
                                ErrorCode.APPROVAL_REQUIRED,
                                mapping,
                                tool_name,
                                call,
                                f"permission mode '{mode}' does not put this "
                                f"call to a person; STANDARD 1.2.0 §5.18.7. "
                                f"{tool_name} did not run.",
                                permission_mode=mode,
                            )
                        )
                    try:
                        digest = self._shown_digest(tool_name, mapping, tool_input)
                    except (ValueError, TypeError) as e:
                        release()
                        return deny(
                            self._refuse(
                                ErrorCode.APPROVAL_REQUIRED,
                                mapping,
                                tool_name,
                                call,
                                f"the arguments of {tool_name} are not I-JSON, "
                                f"so no decision can bind to them: {e}",
                            )
                        )
                    message = _approval_request(
                        mapping, tool_name, self.mapper.person_required(mapping)
                    )
                    if expires is not None and call is not None:
                        with self._state_lock:
                            self._asked_at[call] = self._now()
                    # No decision yet: a grounded MCP tool runs the call only
                    # once the permission callback allows it.
                    self._ask_token(tool_name, tool_input, call)
                    self._record(
                        "asked",
                        tool_name,
                        mapping,
                        call,
                        digest=digest,
                        permission_mode=mode,
                        checkpoint_id=tracker.held_by(call) if held and call else None,
                    )
                    logger.info("PreToolUse asks: %s", message)
                    return decide("ask", message)

                self._allow_token(tool_name, tool_input, call=call)
                self._record(
                    "allowed",
                    tool_name,
                    mapping,
                    call,
                    checkpoint_id=tracker.held_by(call) if held and call else None,
                )
                return {}

            except Exception:
                # The detail stays in the log: the deny reason goes back to
                # the model.
                logger.exception("PreToolUse safety check failed")
                # Whatever this hook left for the call authorises nothing.
                try:
                    self._settle_decision(tool_name, tool_input, call)
                except Exception:
                    logger.exception("Could not withdraw the decision on %s", call)
                if strict:
                    release()
                    try:
                        return deny(
                            self._refuse(
                                ErrorCode.SAFETY_CHECK_FAILED,
                                mapping,
                                tool_name,
                                call,
                                "the PreToolUse safety check failed, so the "
                                "call is refused",
                            )
                        )
                    except Exception:
                        return deny(
                            "R407 SAFETY_CHECK_FAILED: the PreToolUse safety "
                            "check failed, so the call is refused"
                        )

            # Non-strict, after an error: approval is a rule of its own and
            # still applies.
            if asks and mapping.requires_approval:
                try:
                    person = self.mapper.person_required(mapping)
                except Exception:
                    # The request must still go out: say a person decides.
                    person = True
                return decide("ask", _approval_request(mapping, tool_name, person))
            return {}

        return check_before_tool

    def _make_mutation_consumer(self) -> Any:
        """
        Create the PostToolUse hook for a call that ran.

        A call that still holds a checkpoint ran without its use passing
        the permission callback (a tool in ``allowed_tools``, a call that
        needed no approval, or a permission prompt tool's decision): it
        uses the checkpoint now, whatever the call's outcome (STANDARD
        1.2.0 section 5.18.6). A call that succeeded counts each of its
        capabilities as run, for the prerequisites of later calls.

        The result of a call of a bound tool of another MCP server is
        checked here (:meth:`_host_result_fault`, sections 5.18.9, 5.18.10):
        a refused output fails the call that ran (R402, F505 or F504,
        recorded against the call), which then counts as no prerequisite,
        and the hook replaces the result the session reads with the
        refusal (``updatedMCPToolOutput``). A check that cannot be completed
        is R407, and the result is replaced the same way (section 5.18.8):
        so is a result this hook checks when the hook itself fails. A hold
        that cannot be used is logged and does not keep the result from
        being checked.

        Returns:
            Async hook callback function
        """
        tracker = self.checkpoint_tracker
        mapper = self.mapper

        async def record_after_call(
            input_data: dict[str, Any],
            tool_use_id: str | None,
            context: HookContext | None,
        ) -> dict[str, Any]:
            """PostToolUse hook: use the call's hold, record that it ran."""
            holder = tool_use_id or input_data.get("tool_use_id")
            if holder:
                with self._state_lock:
                    self._asked_at.pop(holder, None)
                self._forget_call(holder)
            tool_name = input_data.get("tool_name", "")
            tool_input = input_data.get("tool_input", {})
            try:
                checkpoint_id = None
                if holder:
                    # The call has run: its result is checked whether or
                    # not its hold can be used (section 5.18.8).
                    try:
                        checkpoint_id = tracker.consume_checkpoint(holder)
                    except Exception as e:
                        logger.error(
                            "Could not use the checkpoint the %s call held: %s",
                            tool_name,
                            e,
                        )
                    if checkpoint_id is not None:
                        logger.info(
                            "Checkpoint %s used by %s", checkpoint_id, tool_name
                        )
                mapping = mapper.map_tool(
                    tool_name, tool_input, self._call_dir(holder, input_data)
                )
                tool_response = input_data.get("tool_response")
                try:
                    fault = self._host_result_fault(
                        tool_name, tool_input, tool_response
                    )
                except Exception as e:
                    # Fail closed (section 5.18.8): the output check could
                    # not be completed, so the result is not passed on.
                    fault = _Fault(
                        ErrorCode.SAFETY_CHECK_FAILED,
                        mapping,
                        tool_name,
                        f"{tool_name}'s result could not be checked: {e}",
                    )
                refusal = (
                    None
                    if fault is None
                    else self._fail_call(
                        *fault, call=holder, checkpoint_id=checkpoint_id
                    )
                )
                is_error = refusal is not None
                if isinstance(tool_response, dict):
                    is_error = is_error or bool(tool_response.get("is_error", False))
                elif tool_response is not None and hasattr(tool_response, "is_error"):
                    is_error = is_error or bool(
                        getattr(tool_response, "is_error", False)
                    )
                if not is_error and mapping is not UNCLASSIFIED_TOOL:
                    with self._state_lock:
                        self._executed.update(mapping.capabilities)
                recorded = self._take_outcome_recorded(holder)
                if refusal is None and not recorded:
                    self._record(
                        "failed" if is_error else "ran",
                        tool_name,
                        mapping,
                        holder,
                        checkpoint_id=checkpoint_id,
                    )
                if refusal is not None:
                    return _replace_result(refusal)
            except Exception as e:
                logger.error("Post-call recorder failed: %s", e)
                # Fail closed (section 5.18.8): a result this layer checks,
                # or one it cannot tell whether it checks, is not passed on
                # when the check or its record could not be completed.
                if self._may_check_host_result(tool_name, tool_input):
                    message = f"{tool_name}'s result could not be checked: {e}"
                    try:
                        refusal = self._fail_call(
                            ErrorCode.SAFETY_CHECK_FAILED,
                            UNCLASSIFIED_TOOL,
                            tool_name,
                            message,
                            call=holder,
                        )
                    except Exception:
                        refusal = f"R407 SAFETY_CHECK_FAILED: {message}"
                    return _replace_result(refusal)
            return {}

        return record_after_call

    def _make_failure_recorder(self) -> Any:
        """
        Create the PostToolUseFailure hook: a failed or interrupted call
        started, so it uses the checkpoint it held (it may have changed
        something before it failed), and its failure is recorded.

        Returns:
            Async hook callback function
        """
        tracker = self.checkpoint_tracker

        async def record_failure(
            input_data: dict[str, Any],
            tool_use_id: str | None,
            context: HookContext | None,
        ) -> dict[str, Any]:
            """PostToolUseFailure hook: use the call's hold."""
            holder = tool_use_id or input_data.get("tool_use_id")
            if holder:
                with self._state_lock:
                    self._asked_at.pop(holder, None)
                self._forget_call(holder)
            tool_name = input_data.get("tool_name", "")
            try:
                checkpoint_id = tracker.consume_checkpoint(holder) if holder else None
                if checkpoint_id is not None:
                    logger.info(
                        "%s failed; checkpoint %s is used all the same",
                        tool_name,
                        checkpoint_id,
                    )
                if not self._take_outcome_recorded(holder):
                    # Mapped as the PostToolUse recorder maps it: the record
                    # names the capability and keeps the call's
                    # person_required (section 5.21.3). A mapping that fails
                    # loses neither the record nor the failure.
                    try:
                        mapping: ToolMapping | None = self.mapper.map_tool(
                            tool_name,
                            input_data.get("tool_input", {}),
                            self._call_dir(holder, input_data),
                        )
                    except Exception as e:
                        logger.warning("Failure recorder cannot map: %s", e)
                        mapping = None
                    self._record(
                        "failed",
                        tool_name,
                        mapping,
                        holder,
                        checkpoint_id=checkpoint_id,
                    )
            except Exception as e:
                logger.warning("Failure recorder failed: %s", e)
            return {}

        return record_failure

    def _make_permission_callback(self, host_can_use_tool: Any = None) -> Any:
        """
        Create the permission callback (``can_use_tool``).

        Claude Code calls it for a tool call its permission rules do not
        settle, and for one a PreToolUse hook answered with ``"ask"``. The
        callback:

        1. Allows a control-only call.
        2. For a gated call, holds its checkpoint (the same hold as the
           PreToolUse hook's; F501 when none is left; R407 when the call has
           no ``tool_use_id``). The checkpoint is checked before a person is
           asked.
        3. Hands the decision to ``host_can_use_tool`` when there is one.
           A result that is not an allow releases the hold; for a call that
           requires approval it becomes ``F502 APPROVAL_REQUIRED: <tool> was
           not approved: <the host's message>``. So does an allow that
           arrives later than the binding's ``approval.expires`` after the
           request (the PreToolUse hook's ask, or this callback's call of
           the host's, whichever came first; STANDARD 1.2.0 section
           5.18.7). An allow whose
           ``updated_input`` differs from the input is classified again
           (STANDARD 1.2.0 section 5.18.7): refused if the new arguments need
           a prerequisite (F501, F503, V102) or a checkpoint (F501) the call
           does not hold, or approval (F502: the decision was on other
           arguments).
        4. With no host callback: refuses a call that requires approval
           (F502), since no one can give it.
        5. Uses the held checkpoint when the call is allowed, re-checking in
           one atomic step that it is still valid (F501 otherwise: it
           expired, or a boundary passed, while the call waited).
        6. Grants a grounded MCP tool the decision for the call (with the
           arguments it runs with) only on its allow, and only for a call
           the PreToolUse hook passed or asked about; any other answer,
           an error included, withdraws what the hook left for the call.

        Args:
            host_can_use_tool: The ``can_use_tool`` callback of the options
                being wrapped, or None. It receives the tool name, the
                input and the SDK's ``ToolPermissionContext``, whose
                ``decision_reason`` holds the hook's ``F502`` reason.

        Returns:
            Async permission callback function
        """
        tracker = self.checkpoint_tracker
        mapper = self.mapper
        strict = self.config.strict_mode
        # Anything but an explicit "off" asks.
        asks = self.config.approval != "off"

        # Try to import SDK permission types
        try:
            from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

            has_sdk_types = True
        except ImportError:
            has_sdk_types = False

        def release(holder: str | None) -> None:
            # A refused call never runs: the layer learns of the refusal
            # here, so the checkpoint stays valid for another call.
            if holder is not None:
                try:
                    tracker.release_reservation(holder)
                except Exception as e:  # refuse regardless; the hold lapses
                    logger.error("Could not release the hold of %s: %s", holder, e)

        def deny(message: str, holder: str | None, interrupt: bool = False) -> Any:
            release(holder)
            if has_sdk_types:
                return PermissionResultDeny(message=message, interrupt=interrupt)
            return FallbackPermissionDeny(message=message)

        def allow(updated_input: dict[str, Any]) -> Any:
            if has_sdk_types:
                return PermissionResultAllow(updated_input=updated_input)
            return FallbackPermissionAllow(updated_input=updated_input)

        def use_checkpoint(
            mapping: ToolMapping, tool_name: str, holder: str | None
        ) -> tuple[str | None, str | None]:
            """Use the held checkpoint: (checkpoint id, refusal text)."""
            if not mapping.requires_checkpoint or holder is None:
                return None, None
            checkpoint_id = tracker.consume_if_valid(holder)
            if checkpoint_id is None:
                refusal = self._refuse(
                    ErrorCode.CHECKPOINT_REQUIRED,
                    mapping,
                    tool_name,
                    holder,
                    f"the checkpoint {tool_name} held expired, or an execution "
                    f"boundary passed, while the call waited; take a new "
                    f"checkpoint",
                )
                if strict:
                    return None, refusal
                logger.warning("Permission warning (non-strict): %s", refusal)
            return checkpoint_id, None

        async def decide_permission(
            tool_name: str,
            input_data: dict[str, Any],
            context: HookContext | None,
            holder: str | None,
        ) -> tuple[Any, dict[str, Any] | None]:
            """The decision on a call, and, on an allow, the arguments it
            runs with (None on a refusal)."""
            # The request: this layer's ask, else the host's prompt, which
            # this callback starts.
            requested = self._now()
            try:
                with self._state_lock:
                    cwd = self._call_dirs.get(holder) if holder else None
                    asked = self._asked_at.pop(holder, None) if holder else None
                if asked is not None and asked < requested:
                    requested = asked
                mapping0 = mapper.map_tool(tool_name, input_data, cwd)
                if mapping0.control:
                    return allow(input_data), input_data

                if mapping0.requires_checkpoint:
                    if holder is None:
                        message = self._unheld_call_refusal(mapping0, tool_name)
                        if strict:
                            return deny(message, None), None
                    else:
                        ok, checkpoint_id = tracker.validate_and_reserve(holder)
                        if not ok:
                            message = self._refuse(
                                ErrorCode.CHECKPOINT_REQUIRED,
                                mapping0,
                                tool_name,
                                holder,
                                _checkpoint_message(mapping0, tool_name, checkpoint_id),
                            )
                            if strict:
                                return deny(message, holder), None
                            logger.warning("%s executing without checkpoint", tool_name)

                if host_can_use_tool is None:
                    # No one to ask. An approval no one can give is a
                    # refusal (STANDARD 1.2.0 section 5.18.7, F502).
                    if asks and mapping0.requires_approval:
                        logger.warning(
                            "%s requires approval and the wrapped options have "
                            "no can_use_tool callback; denying. Pass one, or "
                            "set GroundedAgentConfig(approval='off').",
                            tool_name,
                        )
                        return deny(
                            self._refuse(
                                ErrorCode.APPROVAL_REQUIRED,
                                mapping0,
                                tool_name,
                                holder,
                                f"{_subject(mapping0, tool_name)} requires "
                                f"approval, and no one can give it: the options "
                                f"this session was started with have no "
                                f"can_use_tool callback. {tool_name} did not run.",
                            ),
                            holder,
                        ), None
                    checkpoint_id, refusal = use_checkpoint(mapping0, tool_name, holder)
                    if refusal is not None:
                        return deny(refusal, None), None
                    self._record(
                        "allowed",
                        tool_name,
                        mapping0,
                        holder,
                        checkpoint_id=checkpoint_id,
                    )
                    return allow(input_data), input_data

                # The host's permission flow decides what it is asked.
                result = host_can_use_tool(tool_name, input_data, context)
                if inspect.isawaitable(result):
                    result = await result
                if not _is_allow(result):
                    if asks and mapping0.requires_approval:
                        reason = getattr(result, "message", "") or "denied"
                        return deny(
                            self._refuse(
                                ErrorCode.APPROVAL_REQUIRED,
                                mapping0,
                                tool_name,
                                holder,
                                f"{tool_name} was not approved: {reason}",
                            ),
                            holder,
                            interrupt=bool(getattr(result, "interrupt", False)),
                        ), None
                    release(holder)
                    return result, None

                policy = mapping0.approval
                expires = policy.expires_seconds if policy is not None else None
                if asks and mapping0.requires_approval and expires is not None:
                    waited = (self._now() - requested).total_seconds()
                    if waited > expires:
                        return deny(
                            self._refuse(
                                ErrorCode.APPROVAL_REQUIRED,
                                mapping0,
                                tool_name,
                                holder,
                                f"the decision on {tool_name} arrived "
                                f"{waited:.0f} s after the request, later than "
                                f"the {expires:g} s its binding's "
                                f"approval.expires allows; {tool_name} did not "
                                f"run, and needs a new decision",
                            ),
                            holder,
                        ), None

                updated = getattr(result, "updated_input", None)
                args1 = updated if isinstance(updated, dict) else input_data
                mapping1 = mapping0
                if _args_key(args1) != _args_key(input_data):
                    # Section 5.18.7, changed arguments: classify again.
                    mapping1 = mapper.map_tool(tool_name, args1, cwd)
                    refusal = (
                        self._secret_refusal(mapping1, tool_name, holder, args1)
                        or self._destination_refusal(mapping1, tool_name, holder, args1)
                        or self._prerequisite_refusal(mapping1, tool_name, holder)
                    )
                    if refusal is None and (
                        mapping1.requires_checkpoint
                        and not mapping0.requires_checkpoint
                    ):
                        refusal = self._refuse(
                            ErrorCode.CHECKPOINT_REQUIRED,
                            mapping1,
                            tool_name,
                            holder,
                            f"the host changed the arguments of {tool_name}, and "
                            f"the call they make requires a checkpoint the call "
                            f"does not hold",
                        )
                    if refusal is None and asks and mapping1.requires_approval:
                        refusal = self._refuse(
                            ErrorCode.APPROVAL_REQUIRED,
                            mapping1,
                            tool_name,
                            holder,
                            f"the host changed the arguments of {tool_name}, and "
                            f"the decision was on other arguments",
                        )
                    if refusal is not None:
                        return deny(refusal, holder), None
                    if (
                        mapping0.requires_checkpoint
                        and not mapping1.requires_checkpoint
                    ):
                        release(holder)

                checkpoint_id, refusal = use_checkpoint(mapping1, tool_name, holder)
                if refusal is not None:
                    return deny(refusal, None), None
                digest = None
                if mapping1.requires_approval:
                    try:
                        digest = self._shown_digest(tool_name, mapping1, args1)
                    except ValueError, TypeError:
                        digest = None
                self._record(
                    "allowed",
                    tool_name,
                    mapping1,
                    holder,
                    digest=digest,
                    approvers=(
                        ["in_session"] if asks and mapping1.requires_approval else None
                    ),
                    checkpoint_id=checkpoint_id,
                )
                return result, args1

            except Exception as e:
                # Fail-closed: refuse on error (secure default)
                logger.error("Permission check failed: %s", e)
                try:
                    message = self._refuse(
                        ErrorCode.SAFETY_CHECK_FAILED,
                        UNCLASSIFIED_TOOL,
                        tool_name,
                        holder,
                        f"the permission check failed due to an internal error: {e}",
                    )
                except Exception:
                    message = (
                        "R407 SAFETY_CHECK_FAILED: the permission check failed "
                        f"due to an internal error: {e}"
                    )
                return deny(message, holder), None

        async def check_permission(
            tool_name: str,
            input_data: dict[str, Any],
            context: HookContext | None,
        ) -> Any:
            """
            Permission callback: the checkpoint check, the host's decision,
            the re-check of changed arguments, then the use of the
            checkpoint. Only an allow grants a grounded MCP tool the
            decision for the call (with the arguments it runs with), and
            every other answer withdraws what the PreToolUse hook left for
            it (section 5.18.8).

            Args:
                tool_name: Name of tool being invoked
                input_data: Tool input parameters
                context: ToolPermissionContext from SDK

            Returns:
                PermissionResultAllow or PermissionResultDeny, or whatever
                the host's callback returned
            """
            holder = getattr(context, "tool_use_id", None)
            result, runs_with = await decide_permission(
                tool_name, input_data, context, holder
            )
            try:
                self._settle_decision(tool_name, input_data, holder, runs_with)
            except Exception as e:
                # The decision cannot be handed to a grounded MCP tool, so
                # the call is refused (section 5.18.8).
                logger.error("Could not settle the decision on %s: %s", tool_name, e)
                return deny(
                    "R407 SAFETY_CHECK_FAILED: the permission check failed "
                    f"due to an internal error: {e}",
                    holder,
                )
            return result

        return check_permission

    def create_checkpoint(
        self,
        scope: list[str] | str = "*",
        reason: str = "Pre-mutation checkpoint",
    ) -> str:
        """
        Convenience method to create a checkpoint: the host's own checkpoint
        operation, which counts as taken in the layer's scope.

        Args:
            scope: Files/patterns to checkpoint ("*" for all)
            reason: Human-readable reason

        Returns:
            Checkpoint ID
        """
        if isinstance(scope, str):
            scope = [scope]
        checkpoint_id = self.checkpoint_tracker.create_checkpoint(
            scope=scope,
            reason=reason,
            expiry_minutes=self.config.expiry_minutes,
        )
        # The record of the action grounds the checkpoint's output (§3.1).
        try:
            self.evidence_store.append(
                EvidenceAnchor.from_checkpoint(checkpoint_id), capability="checkpoint"
            )
        except Exception as e:  # noqa: BLE001 - best-effort capture (§6.4)
            logger.warning("Could not record the checkpoint's evidence: %s", e)
            report = getattr(self.evidence_store, "record_capture_failure", None)
            if callable(report):
                report(None, str(e))
        return checkpoint_id

    def consume_checkpoint(self) -> str | None:
        """
        Mark the active checkpoint as consumed.

        Returns:
            ID of consumed checkpoint, or None
        """
        return self.checkpoint_tracker.consume_checkpoint()

    def has_valid_checkpoint(self) -> bool:
        """Check if a valid checkpoint exists."""
        return self.checkpoint_tracker.has_valid_checkpoint()

    def get_evidence(self, n: int = 10) -> list[str]:
        """
        Get recent evidence anchors.

        Args:
            n: Number of anchors to return

        Returns:
            List of evidence reference strings
        """
        recent = getattr(self.evidence_store, "get_recent", None)
        if callable(recent):
            return list(recent(n))
        records = self.evidence_store.records()
        return [r.anchor.ref for r in records[max(0, len(records) - n) :]]

    def get_mutations(self) -> list[EvidenceAnchor]:
        """Get all mutation evidence anchors (refs ``mutation:``)."""
        return [
            r.anchor
            for r in self.evidence_store.records()
            if r.anchor.ref.startswith("mutation:")
        ]

    @property
    def ontology_version(self) -> str:
        """Get the capability ontology version."""
        return self.registry.version

    @property
    def capability_count(self) -> int:
        """Get the number of capabilities in the ontology."""
        return self.registry.capability_count
