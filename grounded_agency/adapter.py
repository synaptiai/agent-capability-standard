"""
Grounded Agent Adapter

Main entry point for integrating Grounded Agency safety patterns
with the Claude Agent SDK. The adapter is a safety layer on a tool-calling
host (STANDARD 1.2.0 section 5.18, class SL in section 10.4). Wraps SDK
options to inject:

- A PreToolUse hook that applies the rate limit, the prerequisites, the
  checkpoint rule (F501, F503) and the approval rule (F502) to every tool
  call, and refuses with R407 when it cannot complete a check
- A permission callback that re-checks the call (arguments the host
  changed are classified again) and uses its checkpoint up when the call is
  allowed, after passing the decision to the host's own ``can_use_tool``
- PostToolUse hooks for evidence collection, the checkpoint recorder (a
  successful state-saving call takes a checkpoint) and the use of a held
  checkpoint by a call that ran
- A Stop hook: the end of a turn is an execution boundary

The layer's scope is the adapter instance: every session and subagent it
serves shares one set of records, and the Stop of any of them ends the
validity of every checkpoint the adapter holds. Serve sessions that must not
share boundaries with separate adapters. The conformance statement is
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
import threading
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ._types import FallbackPermissionAllow, FallbackPermissionDeny, HookContext
from .capabilities.mapper import UNCLASSIFIED_TOOL, ToolCapabilityMapper, ToolMapping
from .capabilities.registry import CapabilityRegistry
from .errors import ErrorCode, ValidationError, text_form
from .hooks.evidence_collector import create_evidence_collector
from .hooks.skill_tracker import create_checkpoint_recorder
from .state.checkpoint_tracker import MAX_AGE_MINUTES, CheckpointTracker
from .state.evidence_store import EvidenceAnchor, EvidenceStore
from .state.rate_limiter import RateLimitConfig, RateLimiter

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
        checkpoint_dir: Directory for checkpoint storage
        expiry_minutes: The layer's checkpoint maximum age, in minutes:
            more than 0 and at most 30 (STANDARD 1.2.0 section 5.18.6).
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
            metadata. Off by default: inputs can hold credentials.
        call_record_limit: How many call records (and refusals) the adapter
            keeps in memory (``call_records``, ``diagnostics``).
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

    def __post_init__(self) -> None:
        """Refuse a setting this adapter cannot honour."""
        if self.approval not in ("ask", "off"):
            raise ValueError(f"approval must be 'ask' or 'off', got {self.approval!r}")
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
        f"checkpoint tool, or adapter.checkpoint_tracker.create_checkpoint()) "
        f"before using {tool_name}."
    )


def _approval_request(mapping: ToolMapping, tool_name: str) -> str:
    """Why a tool call is put to the host's permission flow (F502)."""
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
        adapter.checkpoint_tracker.create_checkpoint(
            scope=["*.py"],
            reason="Before refactoring"
        )

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
    evidence_store: EvidenceStore = field(init=False)
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
        self.mapper = ToolCapabilityMapper(self.registry)
        now: Callable[[], datetime] = self.clock or (lambda: datetime.now(UTC))
        self._now = now
        self.checkpoint_tracker = CheckpointTracker(
            self.config.checkpoint_dir,
            reservation_seconds=self.config.checkpoint_reservation_seconds,
            clock=now,
        )
        self.evidence_store = EvidenceStore()
        self.rate_limiter = RateLimiter(self.config.rate_limit)
        # The layer's records (STANDARD 1.2.0 section 5.18.8). History
        # counts from the adapter's start: one adapter is one scope.
        self._started_at = now()
        self._state_lock = threading.Lock()
        self._executed: set[str] = set()
        # Calls this layer allowed, by (tool, digest of the arguments), not
        # yet run: what a grounded MCP tool checks (take_allowed).
        self._allowed: Counter[tuple[str, str]] = Counter()
        self.call_records: deque[dict[str, Any]] = deque(
            maxlen=self.config.call_record_limit
        )
        self.diagnostics: deque[ValidationError] = deque(
            maxlen=self.config.call_record_limit
        )

        # Lazy-initialized by _get_or_create_workflow_engine
        self._workflow_engine: Any = None

        # Initialize cost tracking (import here to avoid circular import)
        from .query import CostSummary

        self.cost_summary = CostSummary()

    # ------------------------------------------------------------------
    # Records (STANDARD 1.2.0 section 5.18.8)
    # ------------------------------------------------------------------

    @property
    def recorded_by(self) -> dict[str, Any]:
        """The layer and its configuration, as every record names it: name,
        version and ``config_sha256``, the SHA-256 of the canonical JSON of
        the settings and bindings that decide a call."""
        from . import __version__, _core

        config = {
            "strict_mode": self.config.strict_mode,
            "approval": self.config.approval,
            "expiry_minutes": self.config.expiry_minutes,
            "checkpoint_reservation_seconds": self.config.checkpoint_reservation_seconds,
            "ontology_version": self.registry.version,
            "prompting_modes": sorted(PROMPTING_PERMISSION_MODES),
            "bindings": self.mapper.records,
        }
        digest = hashlib.sha256(
            _core.canonical_json(config).encode("utf-8")
        ).hexdigest()
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
        if call is not None:
            entry["call"] = call
        entry["decision"] = decision
        entry.update({k: v for k, v in details.items() if v is not None})
        entry["recorded_by"] = self.recorded_by
        with self._state_lock:
            self.call_records.append(entry)

    def _refuse(
        self,
        code: ErrorCode,
        mapping: ToolMapping,
        tool: str,
        call: str | None,
        message: str,
        **details: Any,
    ) -> str:
        """A refusal (section 5.18.8): the §9.8 diagnostic, kept in
        ``diagnostics`` and a call record; returns its text form."""
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
                "refused",
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
            ValueError: If the arguments are not I-JSON.
        """
        from . import _core

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

    def _allow_token(self, tool: str, args: Any, delta: int = 1) -> None:
        key = (tool, _args_key(args))
        with self._state_lock:
            self._allowed[key] += delta
            if self._allowed[key] <= 0:
                del self._allowed[key]

    def take_allowed(self, tool: str, args: Any) -> bool:
        """Use up this layer's decision for a call of ``tool`` with ``args``.

        A grounded MCP tool calls this before it runs
        (``create_grounded_mcp_server(require_layer=True)``): False means
        the call reached the tool without the layer allowing it, and the
        tool refuses with R407 (section 5.18.8).
        """
        key = (tool, _args_key(args))
        with self._state_lock:
            if self._allowed.get(key, 0) <= 0:
                return False
            self._allowed[key] -= 1
            if self._allowed[key] <= 0:
                del self._allowed[key]
            return True

    def _get_or_create_workflow_engine(self) -> Any:
        """Lazy-create a WorkflowEngine for discovery integration."""
        if self._workflow_engine is None:
            from .workflows.engine import WorkflowEngine

            self._workflow_engine = WorkflowEngine(
                ontology_path=self.config.ontology_path,
                checkpoint_tracker=self.checkpoint_tracker,
            )
        return self._workflow_engine

    def wrap_options(self, base: Any) -> Any:
        """
        Wrap SDK options with grounded agency safety layer.

        Injects:
        - enable_file_checkpointing=True for SDK-level rollback
        - a PreToolUse hook for the rate limit, the prerequisites, the
          checkpoint rule and the approval rule
        - a can_use_tool callback that passes the decision to the
          ``can_use_tool`` callback of ``base``, if it has one, re-checks the
          call (arguments the host changed are classified again) and uses
          its checkpoint up when the call is allowed
        - PostToolUse hooks for evidence collection, the checkpoint recorder
          (registered for every tool) and the use of a held checkpoint by a
          call that ran; a PostToolUseFailure hook that uses it too
        - a Stop hook (the end of a turn is an execution boundary) and a
          SubagentStop hook (a finished subagent's holds count as used)

        The layer's scope is this adapter: every session and subagent it
        serves, ordered by its lock. The Stop of any of them ends the
        validity of every checkpoint it holds; serve sessions that must not
        share boundaries with separate adapters. Its maximum age is
        ``config.expiry_minutes``; it relies on a permission prompt only in
        the permission modes of :data:`PROMPTING_PERMISSION_MODES`, read
        from the hook input, else from ``base.permission_mode``.

        ``allowed_tools`` is passed through unchanged; ``Skill`` is not
        added. The SDK approves a tool listed there without consulting
        ``can_use_tool`` (and warns that the callback is shadowed). The
        checks run in the PreToolUse hook, so they apply to listed tools too.

        Where ``base`` names a ``permission_prompt_tool_name``, no
        ``can_use_tool`` callback is installed: the SDK refuses the two
        together, and that tool is then the permission flow that answers
        the hook's ``"ask"``. The PreToolUse hook holds the call's
        checkpoint; a call the prompt tool refuses is never reported, so its
        hold counts as used when it lapses or the turn ends.

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
            options_mode=getattr(base, "permission_mode", None)
        )
        safety_pre_hook._grounded_adapter = self  # see _already_wrapped
        pre_hooks.append(self._wrap_hook(safety_pre_hook))

        # Stop: an execution boundary. SubagentStop: that agent's holds are
        # unresolved and count as used.
        stop_hooks = list(existing_hooks.get("Stop", []))
        stop_hooks.append(self._wrap_hook(self._make_boundary()))
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
    ) -> Any:
        """
        Wrap a hook function in the SDK's expected format.

        For simple integration, returns a dict with the hook.
        For advanced integration with SDK types, would use HookMatcher.

        Args:
            hook_fn: Async hook callback
            matcher: Optional tool matcher string

        Returns:
            Hook configuration dict or HookMatcher
        """
        # Try to use SDK's HookMatcher if available
        try:
            from claude_agent_sdk import HookMatcher

            if matcher:
                return HookMatcher(matcher=matcher, hooks=[hook_fn])
            return HookMatcher(hooks=[hook_fn])
        except ImportError:
            # Fallback: return dict format
            config: dict[str, Any] = {"hooks": [hook_fn]}
            if matcher:
                config["matcher"] = matcher
            return config

    def _make_boundary(self) -> Any:
        """
        Create the Stop hook: the end of a turn is an execution boundary
        (STANDARD 1.2.0 section 5.18.6).

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
                ended = tracker.end_validity(f"turn ended in session {session}")
                with self._state_lock:
                    self._allowed.clear()
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
                logger.error("Turn-end boundary failed: %s", e)
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

    def _make_pretooluse_safety_hook(self, options_mode: str | None = None) -> Any:
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
           none cannot hold one: R407).
        6. Approval (F502), with ``approval="ask"``: a binding that needs
           more than one approver or an approver's role is refused; in a
           permission mode outside :data:`PROMPTING_PERMISSION_MODES` the
           call is refused; otherwise the digest of the shown value is
           recorded and the hook answers ``permissionDecision: "ask"``.
           Each refusal releases the hold step 5 took.

        With ``strict_mode=False`` the checks of steps 4 and 5 log instead
        of refusing (outside class SL); approval still applies. Any other
        error refuses with R407 in strict mode.

        A refusal is ``hookSpecificOutput`` with ``permissionDecision:
        "deny"``, whose reason is the diagnostic's text form
        (``F501 CHECKPOINT_REQUIRED: ...``).

        Args:
            options_mode: The wrapped options' ``permission_mode``: used
                when the hook input carries none.

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

                try:
                    mapping = mapper.map_tool(tool_name, tool_input)
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

                refusal = self._prerequisite_refusal(mapping, tool_name, call)
                if refusal is not None:
                    if strict:
                        return deny(refusal)
                    logger.warning("PreToolUse warning (non-strict): %s", refusal)

                if mapping.requires_checkpoint:
                    scope = (input_data.get("session_id"), input_data.get("agent_id"))
                    if call is None:
                        message = self._refuse(
                            ErrorCode.SAFETY_CHECK_FAILED,
                            mapping,
                            tool_name,
                            call,
                            f"{tool_name} has no tool_use_id, so this layer "
                            f"cannot hold a checkpoint for it",
                        )
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
                    message = _approval_request(mapping, tool_name)
                    self._allow_token(tool_name, tool_input)
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

                self._allow_token(tool_name, tool_input)
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
                return decide("ask", _approval_request(mapping, tool_name))
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
            tool_name = input_data.get("tool_name", "")
            try:
                checkpoint_id = None
                if holder:
                    checkpoint_id = tracker.consume_checkpoint(holder)
                    if checkpoint_id is not None:
                        logger.info(
                            "Checkpoint %s used by %s", checkpoint_id, tool_name
                        )
                mapping = mapper.map_tool(tool_name, input_data.get("tool_input", {}))
                tool_response = input_data.get("tool_response")
                is_error = False
                if isinstance(tool_response, dict):
                    is_error = bool(tool_response.get("is_error", False))
                elif tool_response is not None and hasattr(tool_response, "is_error"):
                    is_error = bool(getattr(tool_response, "is_error", False))
                if not is_error and mapping is not UNCLASSIFIED_TOOL:
                    with self._state_lock:
                        self._executed.update(mapping.capabilities)
                self._record(
                    "failed" if is_error else "ran",
                    tool_name,
                    mapping,
                    holder,
                    checkpoint_id=checkpoint_id,
                )
            except Exception as e:
                logger.warning("Post-call recorder failed: %s", e)
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
            tool_name = input_data.get("tool_name", "")
            try:
                checkpoint_id = tracker.consume_checkpoint(holder) if holder else None
                if checkpoint_id is not None:
                    logger.info(
                        "%s failed; checkpoint %s is used all the same",
                        tool_name,
                        checkpoint_id,
                    )
                self._record(
                    "failed",
                    tool_name,
                    None,
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
           not approved: <the host's message>``. An allow whose
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

        async def check_permission(
            tool_name: str,
            input_data: dict[str, Any],
            context: HookContext | None,
        ) -> Any:
            """
            Permission callback: the checkpoint check, the host's decision,
            the re-check of changed arguments, then the use of the
            checkpoint.

            Args:
                tool_name: Name of tool being invoked
                input_data: Tool input parameters
                context: ToolPermissionContext from SDK

            Returns:
                PermissionResultAllow or PermissionResultDeny, or whatever
                the host's callback returned
            """
            holder = getattr(context, "tool_use_id", None)
            try:
                mapping0 = mapper.map_tool(tool_name, input_data)
                if mapping0.control:
                    return allow(input_data)

                if mapping0.requires_checkpoint:
                    if holder is None:
                        message = self._refuse(
                            ErrorCode.SAFETY_CHECK_FAILED,
                            mapping0,
                            tool_name,
                            None,
                            f"{tool_name} has no tool_use_id, so this layer "
                            f"cannot hold a checkpoint for it",
                        )
                        if strict:
                            return deny(message, None)
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
                                return deny(message, holder)
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
                        self._allow_token(tool_name, input_data, -1)
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
                        )
                    checkpoint_id, refusal = use_checkpoint(mapping0, tool_name, holder)
                    if refusal is not None:
                        self._allow_token(tool_name, input_data, -1)
                        return deny(refusal, None)
                    self._record(
                        "allowed",
                        tool_name,
                        mapping0,
                        holder,
                        checkpoint_id=checkpoint_id,
                    )
                    return allow(input_data)

                # The host's permission flow decides what it is asked.
                result = host_can_use_tool(tool_name, input_data, context)
                if inspect.isawaitable(result):
                    result = await result
                if not _is_allow(result):
                    self._allow_token(tool_name, input_data, -1)
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
                        )
                    release(holder)
                    return result

                updated = getattr(result, "updated_input", None)
                args1 = updated if isinstance(updated, dict) else input_data
                mapping1 = mapping0
                if _args_key(args1) != _args_key(input_data):
                    # Section 5.18.7, changed arguments: classify again.
                    mapping1 = mapper.map_tool(tool_name, args1)
                    refusal = self._prerequisite_refusal(mapping1, tool_name, holder)
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
                        self._allow_token(tool_name, input_data, -1)
                        return deny(refusal, holder)
                    self._allow_token(tool_name, input_data, -1)
                    self._allow_token(tool_name, args1)
                    if (
                        mapping0.requires_checkpoint
                        and not mapping1.requires_checkpoint
                    ):
                        release(holder)

                checkpoint_id, refusal = use_checkpoint(mapping1, tool_name, holder)
                if refusal is not None:
                    self._allow_token(tool_name, args1, -1)
                    return deny(refusal, None)
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
                return result

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
                return deny(message, holder)

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
        return self.checkpoint_tracker.create_checkpoint(
            scope=scope,
            reason=reason,
            expiry_minutes=self.config.expiry_minutes,
        )

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
        return self.evidence_store.get_recent(n)

    def get_mutations(self) -> list[EvidenceAnchor]:
        """Get all mutation evidence anchors."""
        return self.evidence_store.get_mutations()

    @property
    def ontology_version(self) -> str:
        """Get the capability ontology version."""
        return self.registry.version

    @property
    def capability_count(self) -> int:
        """Get the number of capabilities in the ontology."""
        return self.registry.capability_count
