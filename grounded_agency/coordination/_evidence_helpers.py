"""
Shared evidence/audit helpers for coordination modules.

Internal module — not part of the public API.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..state.evidence_store import EvidenceAnchor, EvidenceStore
from .audit import CoordinationAuditLog


def record_coordination_evidence(
    evidence_store: EvidenceStore,
    audit_log: CoordinationAuditLog,
    *,
    ref_prefix: str,
    ref_id: str,
    event_type: str,
    source_agent_id: str,
    target_agent_ids: list[str],
    capability_id: str,
    metadata: dict[str, Any],
    audit_details: dict[str, Any] | None = None,
    evidence_refs_override: list[str] | None = None,
) -> EvidenceAnchor:
    """Create an evidence anchor and record an audit event.

    Args:
        evidence_store: Store to persist the anchor.
        audit_log: Log to record the audit event.
        ref_prefix: Prefix for the evidence ref (e.g. ``"sync"``).
        ref_id: Unique ID appended to the prefix.
        event_type: Audit event type string.
        source_agent_id: Agent that initiated the action.
        target_agent_ids: Agents affected by the action.
        capability_id: Ontology capability ID.
        metadata: Metadata stored on the evidence anchor.
        audit_details: Details for the audit event.  Defaults to
            *metadata* when not provided.
        evidence_refs_override: Override the evidence_refs list on the
            audit event.  When ``None``, uses ``[anchor.ref]``.
    """
    anchor = EvidenceAnchor(
        ref=f"{ref_prefix}:{ref_id}",
        kind="coordination",
        timestamp=datetime.now(timezone.utc).isoformat(),
        metadata=metadata,
    )
    evidence_store.add_anchor(anchor, capability_id=capability_id)
    audit_log.record(
        event_type=event_type,
        source_agent_id=source_agent_id,
        target_agent_ids=target_agent_ids,
        capability_id=capability_id,
        details=audit_details if audit_details is not None else metadata,
        evidence_refs=(
            evidence_refs_override
            if evidence_refs_override is not None
            else [anchor.ref]
        ),
    )
    return anchor
