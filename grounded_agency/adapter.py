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

import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .capabilities.mapper import ToolCapabilityMapper
from .capabilities.registry import CapabilityRegistry
from .hooks.evidence_collector import create_evidence_collector
from .hooks.skill_tracker import create_skill_tracker
from .state.checkpoint_tracker import CheckpointTracker
from .state.evidence_store import EvidenceAnchor, EvidenceStore

logger = logging.getLogger("grounded_agency.adapter")


def _find_ontology_path() -> str:
    """
    Find the capability ontology path.

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
                return str(path)
    except (ImportError, FileNotFoundError, TypeError):
        pass

    # Fallback: look relative to this file
    module_dir = Path(__file__).parent
    for relative in [
        "../schemas/capability_ontology.yaml",  # Development layout
        "schemas/capability_ontology.yaml",  # Alternative layout
    ]:
        candidate = module_dir / relative
        if candidate.exists():
            return str(candidate.resolve())

    # Final fallback: assume cwd-relative (original behavior)
    return "schemas/capability_ontology.yaml"


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
    """

    ontology_path: str = field(default_factory=get_default_ontology_path)
    strict_mode: bool = True
    audit_log_path: str = ".claude/audit.log"
    checkpoint_dir: str = ".checkpoints"
    expiry_minutes: int = 30


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
    registry: CapabilityRegistry = field(init=False)
    mapper: ToolCapabilityMapper = field(init=False)
    checkpoint_tracker: CheckpointTracker = field(init=False)
    evidence_store: EvidenceStore = field(init=False)

    def __post_init__(self) -> None:
        """Initialize components after dataclass creation."""
        self.registry = CapabilityRegistry(self.config.ontology_path)
        self.mapper = ToolCapabilityMapper(self.registry.ontology)
        self.checkpoint_tracker = CheckpointTracker(self.config.checkpoint_dir)
        self.evidence_store = EvidenceStore()

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

        merged_hooks = {**existing_hooks, "PostToolUse": post_hooks}

        # Ensure Skill tool is allowed
        allowed_tools = list(getattr(base, "allowed_tools", None) or [])
        if "Skill" not in allowed_tools:
            allowed_tools.append("Skill")

        # Ensure setting_sources includes project (for skills)
        setting_sources = getattr(base, "setting_sources", None) or ["project"]
        if "project" not in setting_sources:
            setting_sources = list(setting_sources) + ["project"]

        # Use dataclasses.replace for clean option merging
        return replace(
            base,
            enable_file_checkpointing=True,
            can_use_tool=self._make_permission_callback(),
            hooks=merged_hooks,
            allowed_tools=allowed_tools,
            setting_sources=setting_sources,
        )

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
            context: Any,
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

                # Mutation succeeded - consume checkpoint
                if tracker.has_valid_checkpoint():
                    consumed_id = tracker.consume_checkpoint()
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
        Create permission callback that enforces checkpoint requirements.

        This is the core safety mechanism - mutations are blocked
        unless a valid checkpoint exists.

        Returns:
            Async permission callback function
        """
        # Capture state in closure
        tracker = self.checkpoint_tracker
        mapper = self.mapper
        strict = self.config.strict_mode

        # Try to import SDK permission types
        try:
            from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

            has_sdk_types = True
        except ImportError:
            has_sdk_types = False

        async def check_permission(
            tool_name: str,
            input_data: dict[str, Any],
            context: Any,
        ) -> Any:
            """
            Permission callback for checkpoint enforcement.

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

                # Check if checkpoint required
                if mapping.requires_checkpoint:
                    if not tracker.has_valid_checkpoint():
                        message = (
                            f"Capability '{mapping.capability_id}' requires checkpoint. "
                            f"Create checkpoint before using {tool_name}. "
                            f"Use the 'checkpoint' skill or call "
                            f"adapter.checkpoint_tracker.create_checkpoint()."
                        )

                        if strict:
                            if has_sdk_types:
                                return PermissionResultDeny(message=message)
                            # Fallback: return dict
                            return {"allowed": False, "message": message}

                        # Non-strict: warn but allow
                        logger.warning("%s executing without checkpoint", tool_name)

                    else:
                        # Log checkpoint usage
                        checkpoint_id = tracker.get_active_checkpoint_id()
                        logger.info(
                            "%s allowed with checkpoint %s", tool_name, checkpoint_id
                        )

                # Allow the tool
                if has_sdk_types:
                    return PermissionResultAllow(updated_input=input_data)
                return {"allowed": True, "updated_input": input_data}

            except Exception as e:
                # Fail-closed: deny access on error (secure default)
                # In security-critical code, unknown states should deny access
                logger.error("Permission check failed: %s", e)
                message = f"Permission check failed due to internal error: {e}"
                if has_sdk_types:
                    return PermissionResultDeny(message=message)
                return {"allowed": False, "message": message}

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
