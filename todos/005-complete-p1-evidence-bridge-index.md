---
status: complete
priority: p1
issue_id: "005"
tags: [coordination, performance, evidence-bridge]
dependencies: []
---

# Add secondary index to CrossAgentEvidenceBridge for O(1) prior-sharing lookup

## Problem Statement

`_find_prior_sharing_unlocked()` performs an O(N*M) full scan of ALL shared evidence across ALL target agents. This runs under `self._lock` during every `share_evidence()` call, blocking all concurrent operations. With 100 agents each holding 1000 shared evidence entries, this scans 100K objects per call.

## Findings

- `evidence_bridge.py:166-178` — Nested loop iterates all `_shared.values()` then all entries per agent
- Same pattern in `get_evidence_lineage()` at lines 200-208
- Both methods hold `self._lock` for the entire scan
- Performance CRITICAL-1: "100x-10,000x speedup for share_evidence at scale"
- Lock contention amplified by LOCK-1.B (extended lock hold time)

## Proposed Solutions

### Option 1: Add `_by_ref` secondary index

**Approach:** Maintain `self._by_ref: dict[str, SharedEvidence] = {}` mapping evidence refs to their first SharedEvidence entry. Update during `share_evidence()`.

**Pros:**
- O(1) lookup replaces O(N*M) scan
- Negligible memory overhead (one dict entry per unique evidence ref)
- Two-line implementation change

**Cons:**
- Additional dict to maintain during cleanup/eviction

**Effort:** Small

**Risk:** Low

## Recommended Action

Add `self._by_ref: dict[str, SharedEvidence] = {}` in `__init__`. In `share_evidence()`, after creating the first SharedEvidence for a ref, store it: `if anchor.ref not in self._by_ref: self._by_ref[anchor.ref] = se`. Replace `_find_prior_sharing_unlocked()` body with `return self._by_ref.get(evidence_ref)`. For `get_evidence_lineage()`, add `self._lineage: dict[str, list[SharedEvidence]] = defaultdict(list)` and append each SharedEvidence during sharing.

## Technical Details

**Affected files:**
- `grounded_agency/coordination/evidence_bridge.py:65-85` — Constructor, add `_by_ref` dict
- `grounded_agency/coordination/evidence_bridge.py:91-160` — `share_evidence()`, update index
- `grounded_agency/coordination/evidence_bridge.py:166-178` — Replace scan with dict lookup

## Resources

- **PR:** #98
- **Related:** CRITICAL-1, LOCK-1.B

## Acceptance Criteria

- [ ] `_find_prior_sharing_unlocked()` replaced with O(1) dict lookup
- [ ] `get_evidence_lineage()` also uses the index (or a separate per-ref list)
- [ ] Existing tests pass unchanged
- [ ] New test verifies O(1) behavior with large datasets

## Work Log

### 2026-02-02 - Initial Discovery

**By:** Claude Code (PR #98 Review)

**Actions:**
- Profiled _find_prior_sharing_unlocked algorithm complexity
- Identified it runs under lock, amplifying contention
- Confirmed same O(N*M) pattern in get_evidence_lineage()

**Learnings:**
- The fix is the classic "add a secondary index" pattern — same approach used in evidence_store with _by_kind and _by_capability dicts

### 2026-02-03 - Approved for Work

**By:** Claude Triage System

**Actions:**
- Issue approved during triage session
- Status changed from pending to ready
- Highest ROI fix: 2-line change for 100x-10,000x speedup

**Learnings:**
- Same index pattern already exists in evidence_store (_by_kind, _by_capability)
