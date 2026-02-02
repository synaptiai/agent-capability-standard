---
status: complete
priority: p2
issue_id: "006"
tags: [coordination, security, trust, evidence-bridge]
dependencies: []
---

# Validate trust_decay in CrossAgentEvidenceBridge and enforce trust floor

## Problem Statement

`CrossAgentEvidenceBridge.__init__()` does not validate the `trust_decay` parameter. A caller can pass `trust_decay=0.0` (all shared evidence gets zero trust) or `trust_decay=-0.5` (negative trust scores). `OrchestrationConfig.__post_init__()` validates `0.0 < trust_decay <= 1.0`, but direct construction of the bridge bypasses this. Additionally, there is no minimum trust floor — near-zero trust evidence accumulates without value.

## Findings

- `evidence_bridge.py:72-82` — Constructor accepts trust_decay without validation
- `orchestrator.py:50-65` — OrchestrationConfig validates trust_decay correctly
- SEC-03 (MEDIUM): Trust decay floor not enforced
- Negative trust_decay creates nonsensical negative trust scores

## Proposed Solutions

### Option 1: Mirror OrchestrationConfig validation + add trust floor

**Approach:** Add `__post_init__`-style validation in the bridge (or validate in `__init__`). Add a `min_trust_floor` parameter (default 0.01) below which evidence is discarded rather than stored.

**Pros:**
- Prevents negative/zero trust_decay
- Reduces memory waste from near-zero trust evidence
- Consistent with OrchestrationConfig validation

**Cons:**
- Minor API addition (min_trust_floor param)

**Effort:** Small

**Risk:** Low

## Recommended Action

Add validation in `__init__()`: `if not (0.0 < trust_decay <= 1.0): raise ValueError(f"trust_decay must be in (0.0, 1.0], got {trust_decay}")`. Mirror the exact validation from `OrchestrationConfig.__post_init__()`. Add optional `min_trust_floor` param (default 0.01) — skip storing evidence with `propagated_trust < min_trust_floor` in `share_evidence()`.

## Technical Details

**Affected files:**
- `grounded_agency/coordination/evidence_bridge.py:72-82` — Constructor validation
- `grounded_agency/coordination/evidence_bridge.py:116-128` — Trust computation, add floor

## Acceptance Criteria

- [ ] `CrossAgentEvidenceBridge.__init__()` raises `ValueError` for `trust_decay <= 0.0` or `trust_decay > 1.0`
- [ ] Evidence with propagated trust below `min_trust_floor` is not stored
- [ ] Tests cover negative, zero, and boundary trust_decay values

## Work Log

### 2026-02-02 - Initial Discovery

**By:** Claude Code (PR #98 Review)

**Actions:**
- Compared validation between OrchestrationConfig and CrossAgentEvidenceBridge
- Confirmed OrchestrationConfig validates but bridge does not

### 2026-02-03 - Approved for Work

**By:** Claude Triage System

**Actions:**
- Issue approved during triage session
- Status changed from pending to ready
