"""
Evidence Store

Collects and provides access to evidence anchors from tool executions.
Evidence anchors form the provenance chain for grounded decisions.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Metadata validation constants
_MAX_METADATA_SIZE_BYTES = 1024  # 1KB max per anchor
_MAX_METADATA_DEPTH = 2  # No deeply nested structures
_VALID_KEY_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_metadata_key(key: str) -> bool:
    """Check if metadata key is safe (alphanumeric + underscore)."""
    return bool(_VALID_KEY_PATTERN.match(key))


def _validate_metadata_depth(value: Any, current_depth: int = 0) -> bool:
    """Check if metadata value doesn't exceed max depth."""
    if current_depth > _MAX_METADATA_DEPTH:
        return False
    if isinstance(value, dict):
        return all(
            _validate_metadata_depth(v, current_depth + 1)
            for v in value.values()
        )
    if isinstance(value, list):
        return all(
            _validate_metadata_depth(v, current_depth + 1)
            for v in value
        )
    return True


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitize metadata to prevent injection attacks.

    - Validates key names (alphanumeric + underscore)
    - Limits nesting depth
    - Enforces size limit by truncating values
    """
    if not metadata:
        return {}

    sanitized: dict[str, Any] = {}

    for key, value in metadata.items():
        # Skip invalid keys
        if not _validate_metadata_key(str(key)):
            continue

        # Skip values that are too deeply nested
        if not _validate_metadata_depth(value):
            # Flatten to string representation
            value = str(value)[:100]

        sanitized[str(key)] = value

    # Check size and truncate if needed
    try:
        serialized = json.dumps(sanitized, default=str)
        if len(serialized.encode("utf-8")) > _MAX_METADATA_SIZE_BYTES:
            # Truncate by removing largest values until under limit
            while len(json.dumps(sanitized, default=str).encode("utf-8")) > _MAX_METADATA_SIZE_BYTES:
                if not sanitized:
                    break
                # Remove the key with largest value
                largest_key = max(sanitized.keys(), key=lambda k: len(str(sanitized[k])))
                sanitized[largest_key] = "[truncated]"
    except (TypeError, ValueError):
        # If serialization fails, return minimal safe metadata
        return {"_error": "metadata_serialization_failed"}

    return sanitized


@dataclass(slots=True)
class EvidenceAnchor:
    """
    A single piece of evidence from tool execution.

    Evidence anchors track the provenance of information,
    enabling verification that decisions are grounded in
    actual observations rather than hallucination.

    Attributes:
        ref: Reference string (e.g., "tool:Read:abc123", "file:src/main.py")
        kind: Type of evidence ("tool_output", "file", "command", "mutation")
        timestamp: When the evidence was captured
        metadata: Additional context (tool input, file hash, etc.)
    """

    ref: str
    kind: str
    timestamp: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and sanitize metadata after initialization."""
        self.metadata = _sanitize_metadata(self.metadata)

    @classmethod
    def from_tool_output(
        cls,
        tool_name: str,
        tool_use_id: str,
        tool_input: dict[str, Any],
        tool_response: Any = None,
    ) -> EvidenceAnchor:
        """
        Create an evidence anchor from a tool output.

        Args:
            tool_name: Name of the tool (e.g., "Read", "Bash")
            tool_use_id: Unique ID for this tool use
            tool_input: Input parameters to the tool
            tool_response: Optional response data to include

        Returns:
            EvidenceAnchor for this tool execution
        """
        return cls(
            ref=f"tool:{tool_name}:{tool_use_id}",
            kind="tool_output",
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={
                "tool_name": tool_name,
                "tool_input": tool_input,
                "has_response": tool_response is not None,
            },
        )

    @classmethod
    def from_file(
        cls,
        file_path: str,
        file_hash: str | None = None,
        operation: str = "read",
    ) -> EvidenceAnchor:
        """
        Create an evidence anchor for a file reference.

        Args:
            file_path: Path to the file
            file_hash: Optional content hash for integrity
            operation: What was done ("read", "write", "edit")

        Returns:
            EvidenceAnchor for this file reference
        """
        return cls(
            ref=f"file:{file_path}",
            kind="file",
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={
                "path": file_path,
                "hash": file_hash,
                "operation": operation,
            },
        )

    @classmethod
    def from_command(
        cls,
        command: str,
        exit_code: int,
        tool_use_id: str | None = None,
    ) -> EvidenceAnchor:
        """
        Create an evidence anchor for a command execution.

        Args:
            command: The command that was run
            exit_code: Exit code from the command
            tool_use_id: Optional tool use ID

        Returns:
            EvidenceAnchor for this command execution
        """
        ref_id = tool_use_id or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return cls(
            ref=f"command:{ref_id}",
            kind="command",
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={
                "command": command,
                "exit_code": exit_code,
            },
        )

    @classmethod
    def from_mutation(
        cls,
        target: str,
        operation: str,
        checkpoint_id: str | None = None,
    ) -> EvidenceAnchor:
        """
        Create an evidence anchor for a state mutation.

        Args:
            target: What was mutated (file path, resource ID)
            operation: Type of mutation (write, edit, delete)
            checkpoint_id: Associated checkpoint ID

        Returns:
            EvidenceAnchor for this mutation
        """
        return cls(
            ref=f"mutation:{target}",
            kind="mutation",
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={
                "target": target,
                "operation": operation,
                "checkpoint_id": checkpoint_id,
            },
        )

    def __str__(self) -> str:
        return self.ref


class EvidenceStore:
    """
    In-memory store for evidence anchors with bounded size.

    Collects evidence anchors from tool executions and provides
    methods to query them for provenance and verification.

    Uses FIFO eviction when max_anchors is exceeded to prevent
    unbounded memory growth.

    Example:
        store = EvidenceStore(max_anchors=1000)

        # Add evidence from tool use
        anchor = EvidenceAnchor.from_tool_output("Read", "abc123", {"path": "/tmp/x"})
        store.add_anchor(anchor)

        # Query recent evidence
        recent = store.get_recent(5)

        # Get evidence for a capability
        read_evidence = store.get_for_capability("retrieve")
    """

    DEFAULT_MAX_ANCHORS = 10000

    def __init__(self, max_anchors: int | None = None) -> None:
        """
        Initialize the evidence store.

        Args:
            max_anchors: Maximum number of anchors to store (default: 10000).
                        When exceeded, oldest anchors are evicted (FIFO).
        """
        self._max_anchors = max_anchors if max_anchors is not None else self.DEFAULT_MAX_ANCHORS
        self._anchors: list[EvidenceAnchor] = []
        self._by_kind: dict[str, list[EvidenceAnchor]] = defaultdict(list)
        self._by_capability: dict[str, list[EvidenceAnchor]] = defaultdict(list)

    def add_anchor(
        self,
        anchor: EvidenceAnchor,
        capability_id: str | None = None,
    ) -> None:
        """
        Add an evidence anchor to the store.

        If max_anchors is exceeded, the oldest anchor is evicted (FIFO).

        Args:
            anchor: The evidence anchor to add
            capability_id: Optional capability ID to associate with
        """
        # Evict oldest if at capacity
        if len(self._anchors) >= self._max_anchors:
            self._evict_oldest()

        self._anchors.append(anchor)
        self._by_kind[anchor.kind].append(anchor)

        if capability_id:
            self._by_capability[capability_id].append(anchor)

    def _evict_oldest(self) -> None:
        """Evict the oldest anchor from all indexes."""
        if not self._anchors:
            return

        oldest = self._anchors.pop(0)

        # Remove from kind index
        kind_list = self._by_kind.get(oldest.kind, [])
        if oldest in kind_list:
            kind_list.remove(oldest)

        # Remove from capability indexes
        for cap_list in self._by_capability.values():
            if oldest in cap_list:
                cap_list.remove(oldest)
                break  # Anchor can only be in one capability list

    def get_recent(self, n: int = 10) -> list[str]:
        """
        Get references for the N most recent evidence anchors.

        Args:
            n: Number of anchors to return

        Returns:
            List of evidence reference strings
        """
        return [anchor.ref for anchor in self._anchors[-n:]]

    def get_recent_anchors(self, n: int = 10) -> list[EvidenceAnchor]:
        """
        Get the N most recent evidence anchors.

        Args:
            n: Number of anchors to return

        Returns:
            List of EvidenceAnchor objects
        """
        return list(self._anchors[-n:])

    def get_by_kind(self, kind: str) -> list[EvidenceAnchor]:
        """
        Get all evidence anchors of a specific kind.

        Args:
            kind: Evidence kind ("tool_output", "file", "command", "mutation")

        Returns:
            List of matching anchors
        """
        return list(self._by_kind.get(kind, []))

    def get_for_capability(self, capability_id: str) -> list[EvidenceAnchor]:
        """
        Get evidence anchors associated with a capability.

        Args:
            capability_id: Capability ID from the ontology

        Returns:
            List of associated anchors
        """
        return list(self._by_capability.get(capability_id, []))

    def get_for_capability_output(self, capability_id: str) -> list[str]:
        """
        Get evidence references for a capability's outputs.

        This is the format expected by capability output contracts.

        Args:
            capability_id: Capability ID from the ontology

        Returns:
            List of evidence reference strings
        """
        return [anchor.ref for anchor in self.get_for_capability(capability_id)]

    def get_mutations(self) -> list[EvidenceAnchor]:
        """Get all mutation evidence anchors."""
        return self.get_by_kind("mutation")

    def get_tool_outputs(self) -> list[EvidenceAnchor]:
        """Get all tool output evidence anchors."""
        return self.get_by_kind("tool_output")

    def search_by_ref_prefix(self, prefix: str) -> list[EvidenceAnchor]:
        """
        Search for evidence anchors by reference prefix.

        Args:
            prefix: Reference prefix to match (e.g., "tool:Read", "file:")

        Returns:
            List of matching anchors
        """
        return [a for a in self._anchors if a.ref.startswith(prefix)]

    def search_by_metadata(
        self,
        key: str,
        value: Any,
    ) -> list[EvidenceAnchor]:
        """
        Search for evidence anchors by metadata key-value.

        Args:
            key: Metadata key to match
            value: Value to match

        Returns:
            List of matching anchors
        """
        return [
            a for a in self._anchors
            if a.metadata.get(key) == value
        ]

    def clear(self) -> None:
        """Clear all evidence from the store."""
        self._anchors.clear()
        self._by_kind.clear()
        self._by_capability.clear()

    def __len__(self) -> int:
        return len(self._anchors)

    def __iter__(self) -> Iterator[EvidenceAnchor]:
        return iter(self._anchors)

    def to_list(self) -> list[dict[str, Any]]:
        """
        Export all evidence as a list of dicts.

        Returns:
            List of anchor dictionaries
        """
        return [
            {
                "ref": a.ref,
                "kind": a.kind,
                "timestamp": a.timestamp,
                "metadata": a.metadata,
            }
            for a in self._anchors
        ]
