"""
Grounded Agent Adapter

Main entry point for integrating Grounded Agency safety patterns
with the Claude Agent SDK. Wraps SDK options to inject:

- Permission callbacks for checkpoint enforcement
- PostToolUse hooks for evidence collection
- Skill tracking for autonomous checkpoint creation

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
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._types import FallbackPermissionAllow, FallbackPermissionDeny, HookContext
from .capabilities.mapper import ToolCapabilityMapper
from .capabilities.registry import CapabilityRegistry
from .hooks.evidence_collector import create_evidence_collector
from .hooks.skill_tracker import create_skill_tracker
from .state.checkpoint_tracker import CheckpointTracker
from .state.evidence_store import EvidenceAnchor, EvidenceStore
from .state.rate_limiter import RateLimitConfig, RateLimiter

if TYPE_CHECKING:
    from .coordination.orchestrator import OrchestrationRuntime
    from .query import CostSummary

logger = logging.getLogger("grounded_agency.adapter")


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
    except (ImportError, FileNotFoundError, TypeError, OSError):
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
        strict_mode: If True, block mutations without checkpoint.
                    If False, log warning but allow.
        audit_log_path: Path for audit log file
        checkpoint_dir: Directory for checkpoint storage
        expiry_minutes: Default checkpoint expiry in minutes
        rate_limit: Per-risk-level rate limit configuration (SEC-010).
        ontology_hash: Expected SHA-256 hash for ontology integrity check (SEC-012).
                      If None, checks for a .sha256 sidecar file.
        output_format: JSON schema for structured output (SDK ``output_format``).
        max_budget_usd: Maximum cost budget in USD (SDK ``max_budget_usd``).
        model: Default model name (SDK ``model``).
        max_turns: Maximum agent turns (SDK ``max_turns``).
        enable_discovery: If True, inject a PreToolUse hook that runs
            capability discovery on user prompts automatically.
    """

    ontology_path: str = field(default_factory=get_default_ontology_path)
    strict_mode: bool = True
    audit_log_path: str = ".claude/audit.log"
    checkpoint_dir: str = ".checkpoints"
    expiry_minutes: int = 30
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    ontology_hash: str | None = None
    output_format: dict[str, Any] | None = None
    max_budget_usd: float | None = None
    model: str | None = None
    max_turns: int | None = None
    enable_discovery: bool = False


@dataclass
class GroundedAgentAdapter:
    """
    Adapts Claude Agent SDK to use Grounded Agency safety patterns.

    The adapter wraps SDK options to inject:
    1. Permission callbacks that enforce checkpoint-before-mutation
    2. PostToolUse hooks that collect evidence anchors
    3. Skill tracking that updates checkpoint state

    This enables SDK-based agents to operate with:
    - Evidence-grounded decisions
    - Checkpoint-before-mutation safety
    - Typed capability contracts
    - Audit trails

    Example:
        adapter = GroundedAgentAdapter(GroundedAgentConfig(strict_mode=True))

        # Create checkpoint before mutations
        adapter.checkpoint_tracker.create_checkpoint(
            scope=["*.py"],
            reason="Before refactoring"
        )

        # Wrap SDK options
        options = adapter.wrap_options(base_options)

        # Now mutations are allowed
        async with ClaudeSDKClient(options) as client:
            await client.query("Refactor the handler...")
    """

    config: GroundedAgentConfig = field(default_factory=GroundedAgentConfig)
    orchestrator: OrchestrationRuntime | None = None
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
        self.mapper = ToolCapabilityMapper(self.registry.ontology)
        self.checkpoint_tracker = CheckpointTracker(self.config.checkpoint_dir)
        self.evidence_store = EvidenceStore()
        self.rate_limiter = RateLimiter(self.config.rate_limit)

        # Lazy-initialized by _get_or_create_workflow_engine
        self._workflow_engine: Any = None

        # Initialize cost tracking (import here to avoid circular import)
        from .query import CostSummary

        self.cost_summary = CostSummary()

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
        - can_use_tool callback for checkpoint enforcement
        - PostToolUse hooks for evidence collection
        - Skill tool in allowed_tools for autonomous checkpoints

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
        post_hooks = list(existing_hooks.get("PostToolUse", []))

        # Add evidence collector
        evidence_hook = create_evidence_collector(
            store=self.evidence_store,
            mapper=self.mapper,
        )
        post_hooks.append(self._wrap_hook(evidence_hook))

        # Add skill tracker
        skill_hook = create_skill_tracker(self.checkpoint_tracker)
        post_hooks.append(self._wrap_hook(skill_hook, matcher="Skill"))

        # Add mutation consumer to auto-consume checkpoints after mutations
        mutation_hook = self._make_mutation_consumer()
        post_hooks.append(self._wrap_hook(mutation_hook))

        # Build PreToolUse hooks for checkpoint enforcement in Python layer
        pre_hooks = list(existing_hooks.get("PreToolUse", []))
        checkpoint_pre_hook = self._make_pretooluse_checkpoint_hook()
        pre_hooks.append(self._wrap_hook(checkpoint_pre_hook))

        # Add discovery injector if enabled
        if self.config.enable_discovery:
            from .discovery.pipeline import DiscoveryPipeline
            from .hooks.discovery_injector import create_discovery_injector

            discovery_pipeline = DiscoveryPipeline(
                registry=self.registry,
                engine=self._get_or_create_workflow_engine(),
                evidence_store=self.evidence_store,
            )
            discovery_hook = create_discovery_injector(
                pipeline=discovery_pipeline,
                store=self.evidence_store,
            )
            pre_hooks.append(self._wrap_hook(discovery_hook))

        merged_hooks = {
            **existing_hooks,
            "PreToolUse": pre_hooks,
            "PostToolUse": post_hooks,
        }

        # Ensure Skill tool is allowed
        allowed_tools = list(getattr(base, "allowed_tools", None) or [])
        if "Skill" not in allowed_tools:
            allowed_tools.append("Skill")

        # Ensure setting_sources includes project (for skills)
        setting_sources = getattr(base, "setting_sources", None) or ["project"]
        if "project" not in setting_sources:
            setting_sources = list(setting_sources) + ["project"]

        # Build kwargs for dataclasses.replace
        kwargs: dict[str, Any] = {
            "enable_file_checkpointing": True,
            "can_use_tool": self._make_permission_callback(),
            "hooks": merged_hooks,
            "allowed_tools": allowed_tools,
            "setting_sources": setting_sources,
        }

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

    def _make_pretooluse_checkpoint_hook(self) -> Any:
        """
        Create PreToolUse hook that enforces checkpoint-before-mutation.

        This is the Python-layer equivalent of the shell hook
        ``pretooluse_require_checkpoint.sh``, providing defense-in-depth
        for environments where shell hooks are not active (e.g., when
        using the SDK programmatically).

        Returns a ``permissionDecision: "deny"`` when a mutation tool
        is invoked without a valid checkpoint.

        Returns:
            Async hook callback function
        """
        tracker = self.checkpoint_tracker
        mapper = self.mapper
        strict = self.config.strict_mode

        async def check_checkpoint_before_tool(
            input_data: dict[str, Any],
            tool_use_id: str | None,
            context: HookContext | None,
        ) -> dict[str, Any]:
            """PreToolUse hook to enforce checkpoint before mutations."""
            try:
                tool_name = input_data.get("tool_name", "")
                tool_input = input_data.get("tool_input", {})

                mapping = mapper.map_tool(tool_name, tool_input)

                if not mapping.requires_checkpoint:
                    return {}

                if tracker.has_valid_checkpoint():
                    return {}

                message = (
                    f"PreToolUse: {tool_name} requires checkpoint. "
                    f"Capability '{mapping.capability_id}' is {mapping.risk}-risk. "
                    f"Create a checkpoint before proceeding."
                )

                if strict:
                    logger.warning("PreToolUse denied: %s", message)
                    return {"permissionDecision": "deny", "message": message}

                logger.warning("PreToolUse warning (non-strict): %s", message)

            except Exception as e:
                logger.warning("PreToolUse checkpoint check failed: %s", e)

            return {}

        return check_checkpoint_before_tool

    def _make_mutation_consumer(self) -> Any:
        """
        Create PostToolUse hook that auto-consumes checkpoints after mutations.

        This enforces one-checkpoint-per-mutation semantics: after a mutation
        completes successfully, the checkpoint is consumed, requiring a new
        checkpoint for subsequent mutations.

        Returns:
            Async hook callback function
        """
        tracker = self.checkpoint_tracker
        mapper = self.mapper

        async def consume_after_mutation(
            input_data: dict[str, Any],
            tool_use_id: str | None,
            context: HookContext | None,
        ) -> dict[str, Any]:
            """
            PostToolUse hook to consume checkpoint after successful mutation.
            """
            try:
                tool_name = input_data.get("tool_name", "")
                tool_input = input_data.get("tool_input", {})

                # Check if this was a mutation
                mapping = mapper.map_tool(tool_name, tool_input)
                if not mapping.mutation:
                    return {}

                # Check if mutation was successful (no error in response)
                tool_response = input_data.get("tool_response")
                is_error = False
                if isinstance(tool_response, dict):
                    is_error = tool_response.get("is_error", False)
                elif tool_response is not None and hasattr(tool_response, "is_error"):
                    is_error = getattr(tool_response, "is_error", False)

                if is_error:
                    # Mutation failed - don't consume checkpoint
                    logger.info("Mutation %s failed, checkpoint preserved", tool_name)
                    return {}

                # Mutation succeeded — consume checkpoint directly.
                # No has_valid_checkpoint() guard: consume_checkpoint() is
                # already atomic and returns None if nothing to consume,
                # avoiding a TOCTOU race between check and consume.
                consumed_id = tracker.consume_checkpoint()
                if consumed_id is not None:
                    logger.info(
                        "Checkpoint %s consumed after %s", consumed_id, tool_name
                    )

            except Exception as e:
                # Log but don't fail - this is observational
                logger.warning("Mutation consumer failed: %s", e)

            return {}

        return consume_after_mutation

    def _make_permission_callback(self) -> Any:
        """
        Create permission callback that enforces checkpoint requirements
        and rate limits.

        This is the core safety mechanism - mutations are blocked
        unless a valid checkpoint exists and rate limits are not exceeded.

        Returns:
            Async permission callback function
        """
        # Capture state in closure
        tracker = self.checkpoint_tracker
        mapper = self.mapper
        strict = self.config.strict_mode
        limiter = self.rate_limiter

        # Try to import SDK permission types
        try:
            from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

            has_sdk_types = True
        except ImportError:
            has_sdk_types = False

        async def check_permission(
            tool_name: str,
            input_data: dict[str, Any],
            context: HookContext | None,
        ) -> Any:
            """
            Permission callback for checkpoint enforcement and rate limiting.

            Args:
                tool_name: Name of tool being invoked
                input_data: Tool input parameters
                context: ToolPermissionContext from SDK

            Returns:
                PermissionResultAllow or PermissionResultDeny
            """
            try:
                # Map tool to capability
                mapping = mapper.map_tool(tool_name, input_data)

                # SEC-010: Rate limit check
                if not limiter.allow(mapping.risk):
                    message = (
                        f"Rate limited: {mapping.risk}-risk capability "
                        f"'{mapping.capability_id}' via {tool_name}. "
                        f"Too many invocations — please wait."
                    )
                    if has_sdk_types:
                        return PermissionResultDeny(message=message)
                    return FallbackPermissionDeny(message=message)

                # Check if checkpoint required
                if mapping.requires_checkpoint:
                    # SEC-007: Use atomic validate_and_reserve to prevent TOCTOU
                    is_valid, checkpoint_id = tracker.validate_and_reserve()
                    if not is_valid:
                        message = (
                            f"Capability '{mapping.capability_id}' requires checkpoint. "
                            f"Create checkpoint before using {tool_name}. "
                            f"Use the 'checkpoint' skill or call "
                            f"adapter.checkpoint_tracker.create_checkpoint()."
                        )

                        if strict:
                            if has_sdk_types:
                                return PermissionResultDeny(message=message)
                            return FallbackPermissionDeny(message=message)

                        # Non-strict: warn but allow
                        logger.warning("%s executing without checkpoint", tool_name)

                    else:
                        # Log checkpoint usage
                        logger.info(
                            "%s allowed with checkpoint %s", tool_name, checkpoint_id
                        )

                # Allow the tool
                if has_sdk_types:
                    return PermissionResultAllow(updated_input=input_data)
                return FallbackPermissionAllow(updated_input=input_data)

            except Exception as e:
                # Fail-closed: deny access on error (secure default)
                # In security-critical code, unknown states should deny access
                logger.error("Permission check failed: %s", e)
                message = f"Permission check failed due to internal error: {e}"
                if has_sdk_types:
                    return PermissionResultDeny(message=message)
                return FallbackPermissionDeny(message=message)

        return check_permission

    def create_checkpoint(
        self,
        scope: list[str] | str = "*",
        reason: str = "Pre-mutation checkpoint",
    ) -> str:
        """
        Convenience method to create a checkpoint.

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

        Call after successful mutation to require a new checkpoint
        for subsequent mutations.

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
