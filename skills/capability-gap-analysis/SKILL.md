---
name: gap-analysis-workflow
description: Identify capability gaps and propose new skills with prioritization. Use when analyzing missing capabilities, planning skill development, performing ontology expansion, or assessing coverage.
argument-hint: "[user_input]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Bash, Edit, Git, Web
context: fork
agent: general-purpose
---

## Intent

Run the composed workflow **capability_gap_analysis** (`reference/workflow_catalog.yaml`) using atomic capability skills to systematically identify what capabilities are missing and prioritize their development.

**Success criteria:**
- Missing capability list
- Prioritized backlog
- Proposed skill specs
- Every step output is grounded with evidence anchors
- Audit trail of analysis process

**Compatible schemas:**
- `reference/capability_ontology.yaml`
- `reference/workflow_catalog.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `user_input` | No | object | `domain` (the project/system to assess; step 1 observes it, so set it in practice). The catalog also accepts `constraints`, but no step binds it: the priority compare always ranks by the fixed criteria `leverage` and `risk_reduction` |

## Procedure

0) **Create checkpoint marker** if mutation might occur:
   - Create `.claude/checkpoint.ok` after confirming rollback strategy

1) **Invoke `/observe`** on `user_input.domain` and store output as `observe_out`
   - Read project docs and current skill coverage

2) **Invoke `/attribute`** (domain: dependencies) with `observe_out.observation` as the effect and store output as `attribute_out`
   - Map existing workflows vs capabilities

3) **Invoke `/discover`** on `attribute_out.causes` and store output as `discover_out`
   - Find hidden dependencies or unmodeled interactions

4) **Invoke `/compare`** (domain: architecture) on `discover_out.patterns` and store output as `compare_architecture_out`
   - Compare alternative skill architectures

5) **Invoke `/compare`** (domain: priority) on `compare_architecture_out.ranking` with criteria `leverage` and `risk_reduction`, and store output as `compare_priority_out`
   - Rank missing capabilities by leverage and risk reduction

6) **Invoke `/generate`** (domain: plan) from `compare_priority_out.ranking` and `compare_architecture_out.recommendation`, and store output as `generate_out`
   - Generate an implementation plan for new skills

7) **Invoke `/audit`** and store output as `audit_out`
   - Record rationale + decision lineage: the ranking and the plan

## Output Contract

Return a structured object:

```yaml
workflow_id: string  # Unique analysis execution ID
user_input: object  # The input as given
status: completed | partial | failed
steps:
  observe_out:
    observation: object
    evidence_anchors: array[string]
  attribute_out:
    causes: array[object]
    strengths: object  # Causal strength per cause
    evidence_anchors: array[string]
  discover_out:
    patterns: array[object]
    relationships: array[object]
    evidence_anchors: array[string]
  compare_architecture_out:
    ranking: array[object]
    recommendation: string  # The top choice
    evidence_anchors: array[string]
  compare_priority_out:
    ranking: array[object]
    evidence_anchors: array[string]
  generate_out:
    content: object  # The implementation plan
    evidence_anchors: array[string]
  audit_out:
    recorded: boolean
    audit_id: string
    evidence_anchors: array[string]
gaps_identified:
  total: integer
  by_priority:
    critical: array[string]
    high: array[string]
    medium: array[string]
    low: array[string]
  evidence_anchors: array[string]
audit_log_pointer: string  # Path to the audit record
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `workflow_id` | string | Unique identifier for this analysis |
| `status` | enum | Final workflow status |
| `steps` | object | Each step's output, keyed by its `store_as` |
| `gaps_identified` | object | Missing capabilities organized by priority (from `compare_priority_out`) |
| `audit_log_pointer` | string | Where the audit record was written |
| `confidence` | number | 0.0-1.0 based on evidence completeness |
| `evidence_anchors` | array | All evidence references collected |
| `assumptions` | array | Explicit assumptions made during analysis |

## Examples

### Example 1: Gap Analysis for Autonomous Code Review

**Input:**
```yaml
user_input:
  domain: "autonomous code review"
```

**Output:**
```yaml
workflow_id: "gap_20240115_120000_codereview"
user_input:
  domain: "autonomous code review"
status: completed
steps:
  observe_out:
    observation:
      capabilities: 36
      workflows: 12
      review_related_skills: ["critique", "verify", "detect"]
    evidence_anchors:
      - "file:schemas/capability_ontology.yaml"
      - "file:skills/critique/SKILL.md"
  attribute_out:
    causes:
      - id: no_merge_gate
        cause: "No workflow composes critique with an automated merge gate"
      - id: no_regression_domain
        cause: "verify has no regression domain"
    strengths:
      no_merge_gate: 0.8
      no_regression_domain: 0.7
    evidence_anchors:
      - "file:schemas/workflow_catalog.yaml"
  discover_out:
    patterns:
      - pattern: "Review loops repeat critique → plan without verify"
      - pattern: "Security findings are detected but never classified"
    relationships:
      - from: "detect"
        to: "critique"
        note: "Code smells inform critique priorities"
    evidence_anchors:
      - "file:schemas/capability_ontology.yaml:edges"
  compare_architecture_out:
    ranking:
      - option: "Domain profiles on existing capabilities"
        score: 0.85
      - option: "New atomic capabilities"
        score: 0.4
    recommendation: "Domain profiles on existing capabilities"
    evidence_anchors:
      - "file:schemas/profiles/profile_schema.yaml"
  compare_priority_out:
    ranking:
      - gap: "verify (domain: regression)"
        priority: critical
      - gap: "classify (domain: security_pattern)"
        priority: critical
      - gap: "detect (domain: code_smell)"
        priority: high
      - gap: "constrain (domain: auto_merge)"
        priority: high
      - gap: "generate (domain: review_comment)"
        priority: medium
    evidence_anchors:
      - "file:schemas/capability_ontology.yaml:nodes"
  generate_out:
    content:
      phases:
        - phase: 1
          name: "Security Foundation"
          items: ["classify (domain: security_pattern)", "verify (domain: regression)"]
        - phase: 2
          name: "Detection Enhancement"
          items: ["detect (domain: code_smell)", "constrain (domain: auto_merge)"]
        - phase: 3
          name: "Automation Expansion"
          items: ["generate (domain: review_comment)"]
      estimated_effort: "2-3 sprints"
    evidence_anchors:
      - "file:templates/SKILL_TEMPLATE_ENHANCED.md"
  audit_out:
    recorded: true
    audit_id: "audit_20240115_121500"
    evidence_anchors:
      - "file:.claude/audit/gap_20240115_120000_codereview.log"
gaps_identified:
  total: 5
  by_priority:
    critical:
      - "verify (domain: regression)"
      - "classify (domain: security_pattern)"
    high:
      - "detect (domain: code_smell)"
      - "constrain (domain: auto_merge)"
    medium:
      - "generate (domain: review_comment)"
    low: []
  evidence_anchors:
    - "file:schemas/capability_ontology.yaml:nodes"
audit_log_pointer: ".claude/audit/gap_20240115_120000_codereview.log"
confidence: 0.85
evidence_anchors:
  - "file:schemas/capability_ontology.yaml"
  - "file:schemas/workflow_catalog.yaml"
  - "file:.claude/audit/gap_20240115_120000_codereview.log"
assumptions:
  - "Reference ontology is current and complete"
  - "Existing skills are correctly implemented"
  - "Leverage and risk reduction reflect actual business needs"
```

**Evidence pattern:** Ontology comparison, dependency graph analysis, impact-based prioritization.

## Verification

- [ ] **Step Completeness**: All 7 workflow steps executed with output
- [ ] **Evidence Grounding**: Every step output includes evidence_anchors
- [ ] **Relationships Mapped**: attribute_out and discover_out document dependencies and missing connections
- [ ] **Architecture Compared**: compare_architecture_out has a recommendation
- [ ] **Gaps Prioritized**: compare_priority_out ranks every gap
- [ ] **Plan Generated**: generate_out.content is a phased plan
- [ ] **Audit Trail**: audit_out.recorded is true

**Verification tools:** Read (for ontology files), Grep (for capability search), Bash (for validation)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low (the catalog declares low; `max_step_risk` computes medium from the `audit` step)

**Capability-specific rules:**
- Do not create new skills during analysis (discovery only)
- Validate all capability references against ontology
- Prefer a domain parameter on an existing capability over a new capability
- Document assumptions about missing capabilities
- Flag potential security implications of gaps
- Preserve existing ontology structure

## Composition Patterns

**Commonly follows:**
- `observe` - After initial codebase exploration
- `retrieve` - After fetching reference documentation

**Commonly precedes:**
- `generate` (domain: plan) - To create detailed skill specifications
- `compare` (domain: priority) - To refine gap prioritization
- `explain` - To create executive summary

**Anti-patterns:**
- Never skip relationship mapping before prioritization
- Never propose skills without checking ontology for existing alternatives
- Never prioritize without defined criteria
- Never generate roadmap without dependency analysis

**Workflow references:**
- See `reference/workflow_catalog.yaml#capability_gap_analysis` for step definitions
- See `reference/capability_ontology.yaml` for reference structure
