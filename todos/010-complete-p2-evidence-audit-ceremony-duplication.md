---
status: complete
priority: p2
issue_id: "010"
tags: [coordination, code-quality, duplication]
dependencies: []
---

# Extract duplicated evidence-audit ceremony into shared helper

## Problem Statement

The pattern of "create EvidenceAnchor + record audit event" is repeated 6 times across coordination modules (~80 lines of duplication). Each site constructs an anchor with `kind="coordination"`, adds it to the evidence store, and records an audit event with similar boilerplate. Additionally, `EvidenceAnchor` inline serialization (`{"ref": a.ref, "kind": a.kind, "timestamp": a.timestamp}`) appears in 4 files.

## Findings

- Pattern Recognition: 6 occurrences of evidence-audit ceremony (~80 lines duplicated)
- `delegation.py:225-253` — delegation evidence + audit
- `synchronization.py:253-279` — sync evidence + audit
- `orchestrator.py:405-420, 545-560, 580-600` — orchestration/invoke/inquire evidence + audit
- EvidenceAnchor serialization duplicated in 4 `to_dict()` methods
- Python Review P2-2: `orchestrate()` too long due to inline boilerplate

## Proposed Solutions

### Option 1: Extract `_record_with_evidence()` helper

**Approach:** Add a private helper method on a shared base or utility module that takes (event_type, source_agent_id, target_agent_ids, evidence_ref, evidence_kind, metadata) and handles both anchor creation and audit recording.

**Pros:**
- Single source of truth for evidence-audit ceremony
- Reduces each call site from ~15 lines to ~3 lines
- Consistent metadata formatting

**Cons:**
- Introduces coupling to a shared utility

**Effort:** Small-Medium

**Risk:** Low

## Recommended Action

Extract `_record_with_evidence(event_type, source_agent_id, target_agent_ids, ref_prefix, ref_id, capability_id, metadata)` as a private helper that creates the `EvidenceAnchor`, stores it, and records the audit event. Place on a mixin or standalone utility. Also add `EvidenceAnchor.to_dict()` method to centralize the `{"ref": a.ref, "kind": a.kind, "timestamp": a.timestamp}` pattern.

## Technical Details

**Affected files:**
- `grounded_agency/coordination/delegation.py` — 1 ceremony site
- `grounded_agency/coordination/synchronization.py` — 1 ceremony site
- `grounded_agency/coordination/orchestrator.py` — 3 ceremony sites
- New or existing utility for shared helper

## Acceptance Criteria

- [ ] Evidence-audit ceremony extracted to reusable helper
- [ ] All 6 call sites use the helper
- [ ] EvidenceAnchor serialization centralized
- [ ] Existing tests pass unchanged

## Work Log

### 2026-02-02 - Initial Discovery

**By:** Claude Code (PR #98 Review)

**Actions:**
- Identified 6 evidence-audit ceremony sites via pattern analysis
- Measured ~80 lines of duplication across modules
- Noted consistent structure across all sites

### 2026-02-03 - Approved for Work

**By:** Claude Triage System

**Actions:**
- Issue approved during triage session
- Status changed from pending to ready
