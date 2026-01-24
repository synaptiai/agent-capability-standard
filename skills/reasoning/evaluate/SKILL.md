---
name: evaluate
description: Score outputs against rubrics, metrics, or baselines to assess quality. Use when grading work, measuring performance, assessing compliance, or validating outcomes.
argument-hint: "[target] [rubric] [baseline]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Systematically assess the quality of an output, artifact, or result against defined criteria, rubrics, or baselines. Produce a quantified evaluation with actionable feedback.

**Success criteria:**
- All criteria evaluated consistently
- Scores are justified with evidence
- Comparison to baseline included
- Strengths and weaknesses identified
- Actionable improvement suggestions

**Compatible schemas:**
- `docs/schemas/evaluation_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string or object | What to evaluate |
| `rubric` | No | array | Evaluation criteria with weights |
| `baseline` | No | object | Reference point for comparison |
| `passing_threshold` | No | number | Minimum score to pass (0-100) |
| `context` | No | object | Background for evaluation |

## Procedure

1) **Understand the target**: Analyze what is being evaluated
   - Identify the type of artifact
   - Note the intended purpose
   - Understand success criteria
   - Gather context

2) **Define evaluation framework**: Establish criteria
   - Use provided rubric or derive from context
   - Weight criteria by importance
   - Define scoring scales
   - Clarify pass/fail thresholds

3) **Gather evidence**: Collect evaluation data
   - Examine target systematically
   - Compare to baseline if provided
   - Note observations for each criterion
   - Document supporting evidence

4) **Score each criterion**: Apply rubric
   - Score consistently across criteria
   - Justify each score with evidence
   - Note confidence in each score
   - Handle missing information appropriately

5) **Calculate overall score**: Aggregate results
   - Apply criterion weights
   - Calculate weighted average
   - Compare to passing threshold
   - Note score distribution

6) **Identify patterns**: Find themes
   - Strengths (high-scoring areas)
   - Weaknesses (low-scoring areas)
   - Trends across criteria
   - Comparison to baseline

7) **Generate feedback**: Provide actionable guidance
   - Specific improvements for each weakness
   - Priority ordering of improvements
   - Expected impact of improvements
   - Acknowledgment of strengths

## Output Contract

Return a structured object:

```yaml
evaluation:
  target: string  # What was evaluated
  rubric_used: string  # Rubric identifier or description
  overall_score: number  # 0-100
  grade: A | B | C | D | F | null
  passed: boolean
  passing_threshold: number
scores:
  - criterion: string
    weight: number
    score: number  # 0-100
    evidence: string
    rationale: string
    confidence: number
baseline_comparison:
  baseline_score: number | null
  delta: number | null
  trend: improved | stable | declined | null
strengths:
  - criterion: string
    score: number
    description: string
weaknesses:
  - criterion: string
    score: number
    description: string
    improvement: string
    priority: high | medium | low
recommendations:
  - action: string
    expected_impact: string
    effort: low | medium | high
    priority: integer
summary:
  one_line: string  # Single sentence assessment
  detailed: string  # Paragraph summary
confidence: 0..1
evidence_anchors: ["source:ref"]
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `evaluation` | object | Summary of evaluation |
| `scores` | array | Individual criterion scores |
| `baseline_comparison` | object | Comparison to reference |
| `strengths` | array | High-performing areas |
| `weaknesses` | array | Areas needing improvement |
| `recommendations` | array | Prioritized improvements |
| `summary` | object | Human-readable assessment |
| `confidence` | number | 0.0-1.0 based on evidence quality |

## Examples

### Example 1: Code Review Evaluation

**Input:**
```yaml
target:
  type: "pull_request"
  files: 12
  additions: 450
  deletions: 120
rubric:
  - criterion: "correctness"
    weight: 0.3
    description: "Code works as intended"
  - criterion: "readability"
    weight: 0.2
    description: "Code is easy to understand"
  - criterion: "test_coverage"
    weight: 0.2
    description: "Adequate test coverage"
  - criterion: "security"
    weight: 0.2
    description: "No security vulnerabilities"
  - criterion: "documentation"
    weight: 0.1
    description: "Adequate comments and docs"
passing_threshold: 70
```

**Output:**
```yaml
evaluation:
  target: "Pull Request #456"
  rubric_used: "standard_code_review_v2"
  overall_score: 78
  grade: C
  passed: true
  passing_threshold: 70
scores:
  - criterion: "correctness"
    weight: 0.3
    score: 90
    evidence: "All tests pass, manual testing confirms functionality"
    rationale: "Logic is correct, handles main cases and edge cases"
    confidence: 0.95
  - criterion: "readability"
    weight: 0.2
    score: 75
    evidence: "Most functions under 30 lines, variable names descriptive"
    rationale: "Generally readable but some complex nested conditionals"
    confidence: 0.85
  - criterion: "test_coverage"
    weight: 0.2
    score: 65
    evidence: "Coverage report shows 68% line coverage"
    rationale: "Happy path covered, some edge cases missing"
    confidence: 0.9
  - criterion: "security"
    weight: 0.2
    score: 85
    evidence: "No SQL injection, XSS properly escaped"
    rationale: "Good security practices, one minor info disclosure risk"
    confidence: 0.8
  - criterion: "documentation"
    weight: 0.1
    score: 60
    evidence: "JSDoc on public functions, no README update"
    rationale: "Public API documented, internal logic lacks comments"
    confidence: 0.9
baseline_comparison:
  baseline_score: 72
  delta: 6
  trend: improved
strengths:
  - criterion: "correctness"
    score: 90
    description: "Code handles all requirements correctly with proper edge case handling"
  - criterion: "security"
    score: 85
    description: "Good security practices throughout"
weaknesses:
  - criterion: "documentation"
    score: 60
    description: "Internal logic lacks explanatory comments"
    improvement: "Add comments explaining the 'why' for complex logic"
    priority: medium
  - criterion: "test_coverage"
    score: 65
    description: "Edge cases not fully tested"
    improvement: "Add tests for null inputs and boundary conditions"
    priority: high
recommendations:
  - action: "Add tests for error cases in UserService"
    expected_impact: "Increase coverage to 80%+"
    effort: low
    priority: 1
  - action: "Refactor nested conditionals in processOrder()"
    expected_impact: "Improve readability score by 10 points"
    effort: medium
    priority: 2
  - action: "Add inline comments for business logic in calculateDiscount()"
    expected_impact: "Improve documentation score"
    effort: low
    priority: 3
summary:
  one_line: "Solid PR that passes review with minor improvements recommended for test coverage and documentation."
  detailed: |
    This pull request demonstrates good correctness and security practices.
    The code is functionally sound and handles edge cases well. Areas for
    improvement include test coverage (currently 68%, recommend 80%+) and
    documentation of internal logic. The nested conditionals in processOrder()
    could be refactored for better readability. Overall, this is a passing
    submission that would benefit from the recommended improvements.
confidence: 0.85
evidence_anchors:
  - "pr:456:files"
  - "coverage:report:68%"
assumptions:
  - "Tests represent actual functionality"
  - "Coverage report is current"
```

**Evidence pattern:** Each criterion scored with specific evidence, recommendations prioritized.

## Verification

- [ ] All criteria scored
- [ ] Scores have evidence
- [ ] Overall score calculated correctly
- [ ] Pass/fail determined correctly
- [ ] Recommendations are actionable

**Verification tools:** Read (for artifact examination)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Always justify scores with evidence
- Be consistent across criteria
- Note confidence in each score
- Provide constructive feedback
- Acknowledge strengths, not just weaknesses

## Composition Patterns

**Commonly follows:**
- `retrieve` - Gather evaluation targets
- `inspect` - Examine target in detail
- `verify` - Check specific assertions

**Commonly precedes:**
- `decide` - Use evaluation to inform decisions
- `improve` - Act on evaluation feedback
- `explain` - Communicate evaluation results
- `summarize` - Condense evaluation

**Anti-patterns:**
- Never evaluate without defined criteria
- Never score without evidence
- Never provide only negative feedback

**Workflow references:**
- Quality assurance workflows
- Performance review workflows
