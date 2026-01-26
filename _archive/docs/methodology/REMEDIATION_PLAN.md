# Remediation Plan: Strengthening the 99 Capabilities Claim

**Document Status**: Action Plan
**Last Updated**: 2026-01-26
**Version**: 1.0.0
**Purpose**: Concrete steps to address issues identified in HONEST_ASSESSMENT.md

---

## Executive Summary

The honest assessment identified 6 issues with the current 99-capability claim. This plan outlines specific, measurable actions to address each issue and strengthen the ontology's validity.

**Goal**: Move from "designed ontology" to "validated ontology" with defensible claims.

---

## 1. Issue Tracker

| Issue | Severity | Target Resolution | Status |
|-------|----------|-------------------|--------|
| #1 Untested capabilities | CRITICAL | Month 2 | Not Started |
| #2 No rejected candidates | HIGH | Month 1 | Not Started |
| #3 Potential redundancy | MEDIUM | Month 2 | Not Started |
| #4 Layer imbalance | MEDIUM | Month 2 | Not Started |
| #5 No external validation | MEDIUM | Month 4 | Not Started |
| #6 Weak completeness argument | HIGH | Month 3 | Not Started |

---

## 2. Issue #1: Untested Capabilities (CRITICAL)

### Problem
65 of 99 capabilities (66%) have never been used in any reference workflow.

### Root Cause
- Reference workflows focused on specific use cases (debugging, digital twins, gap analysis)
- No systematic effort to achieve coverage
- Capabilities added speculatively without immediate use case

### Remediation Actions

#### Action 1.1: Create MEMORY Layer Workflow
**Deadline**: Week 2
**Owner**: TBD
**Deliverable**: `workflows/personal_assistant.yaml`

```yaml
personal_assistant:
  goal: Demonstrate MEMORY layer capabilities
  capabilities_exercised: [persist, recall]
  steps:
    - capability: receive
    - capability: persist    # Store user preference
    - capability: recall     # Retrieve user preference
    - capability: plan
    - capability: act-plan
```

#### Action 1.2: Create COORDINATION Layer Workflow
**Deadline**: Week 3
**Owner**: TBD
**Deliverable**: `workflows/multi_agent_collab.yaml`

```yaml
multi_agent_collaboration:
  goal: Demonstrate COORDINATION layer capabilities
  capabilities_exercised: [delegate, synchronize, negotiate]
  steps:
    - capability: plan
    - capability: delegate      # Assign subtask
    - capability: synchronize   # Wait for completion
    - capability: negotiate     # Resolve conflicts
    - capability: integrate
```

#### Action 1.3: Create Domain-Specific Workflows
**Deadline**: Month 2
**Owner**: TBD
**Deliverable**: 5 new workflows per Issue #12

| Workflow | Target Capabilities |
|----------|---------------------|
| Manufacturing Predictive | forecast-*, estimate-duration, detect-drift |
| Content Generation | generate-text, generate-code, generate-report |
| Risk Assessment | estimate-risk, compare-risks, identify-risk |
| Data Quality | detect-anomaly, validate, identify-constraint |
| Decision Support | decide, recommend, evaluate, arbitrate |

#### Action 1.4: Coverage Gate
**Deadline**: Month 3
**Criterion**: All capabilities used in at least 1 workflow

**If capability cannot be exercised**:
- Document why it cannot be used
- Consider deprecation or merging

### Success Criteria
- [ ] MEMORY coverage: 2/2 (100%)
- [ ] COORDINATION coverage: 3/3 (100%)
- [ ] Overall coverage: 80/99 (80%+)

---

## 3. Issue #2: No Rejected Candidates Documentation (HIGH)

### Problem
No record exists of capabilities that were considered but rejected.

### Root Cause
- Design decisions made informally
- No documentation process during derivation

### Remediation Actions

#### Action 2.1: Retrospective Rejected Candidates Analysis
**Deadline**: Week 2
**Owner**: TBD
**Deliverable**: `docs/methodology/REJECTED_CANDIDATES.md`

Identify at least 15 candidates that could have been included but weren't:

| Category | Example Rejected | Rejection Reason |
|----------|------------------|------------------|
| Compositions | `search-and-replace` | = search + transform |
| Too specific | `query-graphql` | = retrieve with adapter |
| Too vague | `process` | No clear semantics |
| Framework-specific | `langchain-chain` | Not framework-agnostic |
| Duplicative | `analyze` | = detect + compare + explain |

#### Action 2.2: Document Decision Criteria
**Deadline**: Week 2
**Owner**: TBD
**Deliverable**: Section in CAPABILITY_DERIVATION.md

Add section: "What We Rejected and Why"
- List 15+ rejected candidates
- State rejection reason for each
- Reference atomicity/domain-general criteria

### Success Criteria
- [ ] 15+ rejected candidates documented
- [ ] Each has clear rejection reason
- [ ] Rejection reasons consistent with stated criteria

---

## 4. Issue #3: Potential Redundancy (MEDIUM)

### Problem
Some capabilities may overlap or be decomposable into others.

### Root Cause
- Systematic domain expansion without redundancy checking
- No formal redundancy analysis

### Remediation Actions

#### Action 3.1: Redundancy Analysis
**Deadline**: Month 2
**Owner**: TBD
**Deliverable**: `docs/methodology/REDUNDANCY_ANALYSIS.md`

Analyze each capability pair for redundancy:

| Candidate | Potential Redundancy | Analysis | Verdict |
|-----------|---------------------|----------|---------|
| detect-drift | detect-change + temporal | Different semantics: drift is gradual pattern | Keep separate |
| diff-world-state | compare-states | Different: diff is structured, compare is judgment | Keep separate |
| generate-report | generate-text + template | Different: report has structure semantics | Keep separate |
| estimate-risk | estimate-prob × estimate-impact | Possibly redundant: risk IS prob × impact | **Review** |

#### Action 3.2: Resolve Identified Redundancies
**Deadline**: Month 2
**Owner**: TBD

For each redundancy identified:
1. If truly redundant: Merge capabilities
2. If distinct: Document the distinction clearly
3. Update schemas and skills accordingly

#### Action 3.3: Add Redundancy Check to Governance
**Deadline**: Month 2
**Owner**: TBD

Add to EXTENSION_GOVERNANCE.md:
- Redundancy check requirement for new capabilities
- Formal process for analyzing overlap

### Success Criteria
- [ ] All capability pairs analyzed
- [ ] Redundancies resolved or documented
- [ ] Process prevents future redundancy

---

## 5. Issue #4: Layer Imbalance (MEDIUM)

### Problem
MODELING has 45 capabilities (45.5%) while MEMORY has 2 (2%).

### Root Cause
- MODELING domain is inherently complex (many belief types)
- MEMORY operations are genuinely simpler

### Remediation Actions

#### Action 4.1: Justify MODELING Size
**Deadline**: Month 1
**Owner**: TBD
**Deliverable**: Section in LAYER_DERIVATION.md

Document why MODELING requires more capabilities:
- Enumerate the belief types (entity, activity, state, relationship, etc.)
- Show each detect-*/identify-*/estimate-* is distinct
- Reference DIS '23 framework expansion

#### Action 4.2: Audit Small Layers for Gaps
**Deadline**: Month 2
**Owner**: TBD
**Deliverable**: Gap analysis for MEMORY, COORDINATION

| Layer | Current | Possible Missing |
|-------|---------|------------------|
| MEMORY | persist, recall | index? query? expire? |
| COORDINATION | delegate, sync, negotiate | broadcast? vote? arbitrate? |

For each possible missing:
- If genuinely needed: Propose via RFC
- If composition: Document the composition

### Success Criteria
- [ ] MODELING size justified in documentation
- [ ] Small layers audited for gaps
- [ ] Any missing capabilities proposed or composition documented

---

## 6. Issue #5: No External Validation (MEDIUM)

### Problem
The ontology has not been reviewed by external experts.

### Root Cause
- Early-stage project
- No formal review process established

### Remediation Actions

#### Action 5.1: Identify Reviewers
**Deadline**: Month 2
**Owner**: TBD
**Deliverable**: List of 3 potential reviewers

Criteria:
- Expertise in AI agent architectures
- Familiarity with capability taxonomies
- Independence from the project

#### Action 5.2: Prepare Review Package
**Deadline**: Month 2
**Owner**: TBD
**Deliverable**: Review package document

Contents:
- Executive summary
- Core claims to evaluate
- Schema and workflow examples
- Specific questions for reviewers

#### Action 5.3: Conduct Reviews
**Deadline**: Month 4
**Owner**: TBD
**Deliverable**: 2-3 written reviews

Process:
1. Send review package
2. Allow 2-3 weeks for review
3. Collect feedback
4. Address concerns

#### Action 5.4: Respond to Feedback
**Deadline**: Month 5
**Owner**: TBD
**Deliverable**: Response document and updates

For each piece of feedback:
- Accept and update, OR
- Reject with documented reasoning

### Success Criteria
- [ ] 2+ external reviews completed
- [ ] All feedback addressed
- [ ] Major concerns resolved

---

## 7. Issue #6: Weak Completeness Argument (HIGH)

### Problem
The claim "sufficient for any agent task" is asserted without proof.

### Root Cause
- Completeness is hard to prove formally
- No systematic attempt to challenge the claim

### Remediation Actions

#### Action 6.1: Challenge Workflow Development
**Deadline**: Month 2
**Owner**: TBD
**Deliverable**: 10+ challenge workflows

Actively try to construct workflows that cannot be built:
1. Complex reasoning chains
2. Multi-modal interactions
3. Long-term learning
4. Real-time control
5. Natural language generation
6. Code synthesis
7. Image understanding
8. Audio processing
9. Physical world interaction
10. Social interaction

For each:
- If buildable: Document the composition
- If not buildable: Identify missing capability

#### Action 6.2: Weaken or Strengthen Claim
**Deadline**: Month 3
**Owner**: TBD

Based on challenge results:

**If all challenges pass**:
- Document the challenges and compositions
- Strengthen claim: "Demonstrated sufficient for X challenge domains"

**If challenges fail**:
- Option A: Add missing capabilities (via RFC)
- Option B: Weaken claim to explicit scope

#### Action 6.3: Formal Sufficiency Argument
**Deadline**: Month 3
**Owner**: TBD
**Deliverable**: Section in WHY_99.md

Write informal proof:
1. Enumerate agent operation categories
2. Map each to layers
3. Map each to capabilities
4. Show coverage is complete

### Success Criteria
- [ ] 10+ challenge workflows attempted
- [ ] Failures addressed or claim scoped
- [ ] Sufficiency argument documented

---

## 8. Documentation Updates

Based on remediation, update messaging:

### Current Messaging (Avoid)
> "99 atomic capabilities form the complete periodic table for AI agents."

### Interim Messaging (Until Validated)
> "99 capabilities derived from AI taxonomy research, designed to cover common agent patterns. Coverage validated for X workflow domains."

### Target Messaging (After Validation)
> "99 capabilities validated against Y challenge workflows spanning Z domains. No workflow has required a capability outside this set."

---

## 9. Timeline Summary

| Week | Focus | Deliverables |
|------|-------|--------------|
| 1-2 | Rejected candidates, MEMORY workflow | REJECTED_CANDIDATES.md, personal_assistant.yaml |
| 3-4 | COORDINATION workflow, justify layers | multi_agent_collab.yaml, LAYER_DERIVATION.md update |
| 5-8 | Domain workflows, redundancy analysis | 5 new workflows, REDUNDANCY_ANALYSIS.md |
| 9-12 | Challenge workflows, sufficiency argument | 10 challenge workflows, WHY_99.md update |
| 13-16 | External review | Review package, 2 reviews received |
| 17-20 | Address feedback | Updates, response document |

---

## 10. Success Metrics

| Metric | Current | Month 3 Target | Month 6 Target |
|--------|---------|----------------|----------------|
| Capability coverage | 34% | 80% | 95% |
| Rejected candidates documented | 0 | 15+ | 20+ |
| Challenge workflows | 0 | 10 | 15 |
| External reviews | 0 | 1 | 3 |
| Honest Assessment Score | 2.8/5 | 3.5/5 | 4.0/5 |

---

## 11. Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Cannot exercise some capabilities | Medium | High | Document reason, consider deprecation |
| Challenges reveal missing capabilities | Medium | Medium | Add via RFC if atomic, else document composition |
| External reviewers unavailable | Low | Medium | Expand candidate pool, offer compensation |
| Remediation reveals fundamental flaws | Low | High | Be willing to restructure; honesty > ego |

---

## 12. Conclusion

This plan addresses the 6 issues identified in the honest assessment:

1. **Untested capabilities** → Create workflows for 80%+ coverage
2. **No rejected candidates** → Document 15+ rejected with reasons
3. **Potential redundancy** → Formal redundancy analysis
4. **Layer imbalance** → Justify or rebalance
5. **No external validation** → Get 2+ external reviews
6. **Weak completeness** → Challenge workflows + sufficiency argument

**Commitment**: We will update the honest assessment quarterly and adjust claims based on evidence accumulated.

---

## References

- [HONEST_ASSESSMENT.md](HONEST_ASSESSMENT.md) — Issue identification
- [EXTENSION_GOVERNANCE.md](EXTENSION_GOVERNANCE.md) — RFC process
- [GitHub Issue #12](https://github.com/synaptiai/agent-capability-standard/issues/12) — Domain workflows
