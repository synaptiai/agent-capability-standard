---
status: complete
priority: p2
issue_id: "007"
tags: [coordination, security, audit, immutability]
dependencies: []
---

# Deep-copy audit event details and fix AgentDescriptor metadata mutability

## Problem Statement

Two immutability violations exist: (1) `CoordinationAuditLog.record()` uses `MappingProxyType(dict(details))` which is only a shallow copy — nested mutable objects (lists, dicts) within details can be mutated after the event is created, violating audit trail integrity. (2) `AgentDescriptor` is `frozen=True` but its `metadata: dict[str, Any]` field is mutable, allowing post-creation mutation.

## Findings

- `audit.py:121` — `MappingProxyType(dict(details))` is shallow; nested objects share references
- `orchestrator.py:527-534` — "audit" step passes full user context without sanitization
- `registry.py:23,38` — `AgentDescriptor(frozen=True)` with mutable `metadata` dict
- SEC-05 (MEDIUM): Audit context passed without deep copy
- SEC-08 (LOW): Mutable metadata on frozen AgentDescriptor
- Data Integrity Finding 11 (MEDIUM): Same metadata issue

## Proposed Solutions

### Option 1: json.loads(json.dumps()) for audit details + MappingProxyType for metadata

**Approach:** In `record()`, replace `dict(details)` with `json.loads(json.dumps(details, default=str))` for full isolation. In `register()`, wrap metadata in `MappingProxyType`.

**Pros:**
- Complete isolation of audit event details from caller
- Consistent with existing MappingProxyType pattern in CoordinationEvent
- No external dependencies

**Cons:**
- json round-trip slightly slower than dict() for large details
- MappingProxyType makes metadata read-only (may surprise callers)

**Effort:** Small

**Risk:** Low

## Recommended Action

(1) In `CoordinationAuditLog.record()`, replace `dict(details)` with `json.loads(json.dumps(details, default=str))` for full deep-copy isolation. (2) In `AgentRegistry.register()`, wrap metadata in `types.MappingProxyType(dict(metadata) if metadata else {})`. Update `AgentDescriptor.metadata` type hint accordingly.

## Technical Details

**Affected files:**
- `grounded_agency/coordination/audit.py:115-125` — `record()` method, deep-copy details
- `grounded_agency/coordination/registry.py:95-104` — `register()`, wrap metadata in MappingProxyType
- `grounded_agency/coordination/registry.py:38` — Change type hint to `MappingProxyType`

## Acceptance Criteria

- [ ] Audit event details cannot be mutated after creation (including nested objects)
- [ ] AgentDescriptor.metadata is read-only (MappingProxyType)
- [ ] Test: mutating nested list in details after record() does not affect stored event
- [ ] Test: mutating descriptor.metadata raises TypeError

## Work Log

### 2026-02-02 - Initial Discovery

**By:** Claude Code (PR #98 Review)

**Actions:**
- Verified MappingProxyType is shallow via code analysis
- Confirmed CoordinationEvent already uses MappingProxyType for its own details (partial fix)
- Identified metadata as the remaining mutable field on frozen AgentDescriptor

### 2026-02-03 - Approved for Work

**By:** Claude Triage System

**Actions:**
- Issue approved during triage session
- Status changed from pending to ready

**Learnings:**
- CoordinationEvent already uses MappingProxyType — extend same pattern to AgentDescriptor
