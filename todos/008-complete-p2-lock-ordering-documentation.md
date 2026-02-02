---
status: complete
priority: p2
issue_id: "008"
tags: [coordination, concurrency, documentation]
dependencies: []
---

# Document lock ordering hierarchy across coordination modules

## Problem Statement

The coordination runtime has 6 independent `threading.Lock()` instances across modules. While locks are currently acquired/released sequentially (not nested), there is no documented ordering contract. Future modifications that introduce nested locking could create deadlocks. Additionally, the delegation depth limit and cycle detection are missing for delegation chains.

## Findings

- 6 locks: `evidence_store._lock`, `audit._lock`, `registry._lock`, `delegation._lock`, `synchronization._lock`, `evidence_bridge._lock`
- `delegate()` acquires 4 locks in sequence: registry -> evidence_store -> delegation -> audit
- `share_evidence()` acquires 3 locks: registry -> evidence_bridge -> audit
- SEC-06 (MEDIUM): Lock ordering not documented
- Performance SCALE-3: No delegation depth limit or cycle detection

## Proposed Solutions

### Option 1: Document lock ordering + add delegation depth limit

**Approach:** Add a comment block in each module's class docstring establishing the lock hierarchy. Add `max_delegation_depth` parameter to DelegationProtocol.

**Pros:**
- Prevents future deadlocks through convention
- Delegation depth limit prevents infinite loops in delegation chains

**Cons:**
- Documentation-only change for lock ordering (no runtime enforcement)

**Effort:** Small

**Risk:** Low

## Recommended Action

Document lock hierarchy in each module docstring: `registry` < `evidence_store` < `delegation` < `synchronization` < `evidence_bridge` < `audit` (acquire in this order only). Add `max_delegation_depth=10` parameter to `DelegationProtocol` — track current depth per delegation chain and reject if exceeded.

## Technical Details

**Affected files:**
- All coordination modules — docstring additions
- `grounded_agency/coordination/delegation.py` — Add `max_delegation_depth` param

## Acceptance Criteria

- [ ] Lock ordering hierarchy documented in module docstrings
- [ ] Delegation depth limit enforced in `delegate()`
- [ ] No circular delegation chains possible

## Work Log

### 2026-02-02 - Initial Discovery

**By:** Claude Code (PR #98 Review)

**Actions:**
- Mapped all 6 locks and their acquisition sequences
- Confirmed no nested locking exists currently (locks released before next acquired)
- Identified delegation chains as potential infinite loops

### 2026-02-03 - Approved for Work

**By:** Claude Triage System

**Actions:**
- Issue approved during triage session
- Status changed from pending to ready
