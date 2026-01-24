---
name: grounding
description: Attach claims and model elements to concrete evidence anchors with quality assessment. Use when validating assertions, ensuring traceability, or establishing the evidentiary basis for conclusions.
argument-hint: "[claims] [evidence_sources] [strength_threshold]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Perform **grounding** - connecting abstract claims to concrete evidence. Every assertion in a world model should trace back to observable reality. This prevents hallucination and enables trust.

**Success criteria:**
- Each claim has at least one evidence anchor
- Evidence quality is assessed (direct vs. inferred)
- Weak groundings are flagged with improvement suggestions
- Overall grounding percentage is calculated
- Ungroundable claims are explicitly marked

**Compatible schemas:**
- `docs/schemas/world_state_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `claims` | Yes | array\|object | Claims or model elements to ground |
| `evidence_sources` | No | array | Available sources to search for evidence |
| `strength_threshold` | No | number | Minimum evidence strength to accept (default: 0.5) |
| `constraints` | No | object | Required evidence types, forbidden sources |

## Procedure

1) **Parse claims**: Extract discrete assertions to ground
   - For structured models: Each entity attribute, relationship, rule
   - For text: Each factual statement
   - For predictions: Each assumption underlying the prediction
   - Tag each claim with a unique ID for tracking

2) **Classify claims**: Determine grounding requirements
   - **Definitional**: True by definition (e.g., "the sky is blue when cloudless")
   - **Observable**: Can be directly verified (e.g., "file X exists")
   - **Inferential**: Derived from other claims (e.g., "therefore Y is true")
   - **Predictive**: About future/counterfactual (e.g., "X will cause Y")

3) **Search for evidence**: For each claim, find supporting evidence
   - **Files**: Code, configs, documentation at specific lines
   - **Tool outputs**: Results from Grep, Read, Bash commands
   - **URLs**: External references, documentation links
   - **Observations**: Direct observations during inspection
   - **Citations**: References to authoritative sources

4) **Assess evidence quality**: For each piece of evidence
   - **Direct**: Evidence directly states the claim (strength: 0.9-1.0)
   - **Strongly supportive**: Evidence strongly implies the claim (0.7-0.9)
   - **Supportive**: Evidence is consistent with claim (0.5-0.7)
   - **Weak**: Evidence only tangentially related (0.3-0.5)
   - **Inferred**: Claim derived from other grounded claims (varies)

5) **Format evidence anchors**: Create standardized references
   - File evidence: `{filepath}:{line_number}` or `{filepath}:{start}-{end}`
   - Tool evidence: `tool:{tool_name}:{output_reference}`
   - URL evidence: Full URL, preferably with fragment
   - Citation: `{source_name}:{section/page}`

6) **Handle weak groundings**: For claims below threshold
   - Document why grounding is weak
   - Suggest evidence that would strengthen it
   - Consider if claim should be marked as assumption

7) **Identify ungroundable claims**: Some claims cannot be grounded
   - Predictions about the future
   - Counterfactual statements
   - Claims about unmeasurable quantities
   - Mark these explicitly as assumptions

8) **Calculate grounding coverage**: Aggregate statistics
   - Percentage of claims grounded above threshold
   - Average grounding strength
   - Number of ungrounded claims

## Output Contract

Return a structured object:

```yaml
claims:
  - id: string  # Claim identifier
    claim: string  # The assertion being grounded
    type: definitional | observable | inferential | predictive
    grounded: boolean  # Above threshold?
    evidence:
      - anchor: string  # Evidence reference (file:line, url, tool:...)
        type: direct | inferred | cited
        source: string  # Where evidence came from
        snippet: string | null  # Relevant excerpt
        confidence: number  # 0.0-1.0 strength of this evidence
    combined_confidence: number  # Overall grounding strength
    ungrounded_reason: string | null  # Why not grounded if applicable
overall_grounding:
  grounded_count: integer  # Claims meeting threshold
  total_claims: integer  # All claims processed
  percentage: number  # Grounded percentage
  average_strength: number  # Mean confidence across claims
weak_groundings:
  - claim_id: string
    issue: string  # What's weak about the grounding
    suggestion: string  # How to improve
    priority: low | medium | high
ungroundable:
  - claim_id: string
    claim: string
    reason: string  # Why it can't be grounded
    treat_as: assumption | hypothesis | speculation
confidence: number  # 0.0-1.0 overall confidence in grounding analysis
evidence_anchors: array[string]  # Meta: evidence for the grounding itself
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `claims` | array | Each claim with its grounding status |
| `evidence` | array | Evidence supporting each claim |
| `overall_grounding` | object | Aggregate grounding statistics |
| `weak_groundings` | array | Claims that need better evidence |
| `ungroundable` | array | Claims that cannot be grounded |

## Examples

### Example 1: Grounding World State Claims

**Input:**
```yaml
claims:
  - id: "c1"
    claim: "The api-gateway service is running on port 3000"
  - id: "c2"
    claim: "The api-gateway depends on the auth service"
  - id: "c3"
    claim: "The system can handle 10,000 requests per second"
evidence_sources:
  - "docker-compose.yml"
  - "package.json"
  - "src/"
strength_threshold: 0.6
```

**Output:**
```yaml
claims:
  - id: "c1"
    claim: "The api-gateway service is running on port 3000"
    type: observable
    grounded: true
    evidence:
      - anchor: "docker-compose.yml:15"
        type: direct
        source: "docker-compose.yml"
        snippet: "ports:\n  - \"3000:3000\""
        confidence: 1.0
      - anchor: "src/api-gateway/index.ts:42"
        type: direct
        source: "src/api-gateway/index.ts"
        snippet: "app.listen(3000, () => {"
        confidence: 1.0
    combined_confidence: 1.0
    ungrounded_reason: null
  - id: "c2"
    claim: "The api-gateway depends on the auth service"
    type: observable
    grounded: true
    evidence:
      - anchor: "package.json:25"
        type: inferred
        source: "package.json"
        snippet: "\"@company/auth-client\": \"^2.0.0\""
        confidence: 0.7
      - anchor: "src/api-gateway/middleware/auth.ts:5"
        type: direct
        source: "src/api-gateway/middleware/auth.ts"
        snippet: "import { AuthService } from '@company/auth-client'"
        confidence: 0.9
      - anchor: "docker-compose.yml:20"
        type: direct
        source: "docker-compose.yml"
        snippet: "depends_on:\n  - auth"
        confidence: 1.0
    combined_confidence: 0.95
    ungrounded_reason: null
  - id: "c3"
    claim: "The system can handle 10,000 requests per second"
    type: predictive
    grounded: false
    evidence:
      - anchor: "docs/performance.md:45"
        type: cited
        source: "docs/performance.md"
        snippet: "Benchmark results: 8,500 RPS under test conditions"
        confidence: 0.4
    combined_confidence: 0.4
    ungrounded_reason: "Evidence shows 8,500 RPS, not 10,000. Benchmark conditions may differ from production."
overall_grounding:
  grounded_count: 2
  total_claims: 3
  percentage: 66.7
  average_strength: 0.78
weak_groundings:
  - claim_id: "c3"
    issue: "Benchmark shows 8,500 RPS, claim states 10,000 RPS"
    suggestion: "Run production load test or revise claim to 8,500 RPS"
    priority: high
ungroundable: []
confidence: 0.9
evidence_anchors:
  - "docker-compose.yml:1-50"
  - "package.json:1-100"
  - "src/api-gateway/"
assumptions:
  - "Code reflects deployed configuration"
  - "docker-compose matches production setup"
```

**Evidence pattern:** Searched config files for port and dependency declarations, traced imports in source code, found performance benchmark documentation.

---

### Example 2: Grounding Causal Claims

**Input:**
```yaml
claims:
  - id: "causal_1"
    claim: "Deployments cause error rate increases"
  - id: "causal_2"
    claim: "Error rate increases are caused by buggy code"
evidence_sources:
  - "deployment_log.json"
  - "error_metrics.json"
  - "incident_reports/"
```

**Output:**
```yaml
claims:
  - id: "causal_1"
    claim: "Deployments cause error rate increases"
    type: inferential
    grounded: true
    evidence:
      - anchor: "incident_reports/INC-2025-001.md:15-25"
        type: cited
        source: "incident_reports/INC-2025-001.md"
        snippet: "Root cause: deployment of v2.3 introduced null pointer exception"
        confidence: 0.8
      - anchor: "tool:correlation_analysis:deployment_errors"
        type: inferred
        source: "correlation analysis"
        snippet: "72% of error spikes occur within 1 hour of deployment"
        confidence: 0.7
    combined_confidence: 0.75
    ungrounded_reason: null
  - id: "causal_2"
    claim: "Error rate increases are caused by buggy code"
    type: inferential
    grounded: true
    evidence:
      - anchor: "incident_reports/INC-2025-001.md:30"
        type: direct
        source: "incident_reports/INC-2025-001.md"
        snippet: "Bug fix: added null check in UserService.getProfile()"
        confidence: 0.9
      - anchor: "incident_reports/INC-2025-003.md:22"
        type: direct
        source: "incident_reports/INC-2025-003.md"
        snippet: "Code defect in payment validation logic"
        confidence: 0.9
    combined_confidence: 0.85
    ungrounded_reason: null
overall_grounding:
  grounded_count: 2
  total_claims: 2
  percentage: 100
  average_strength: 0.80
weak_groundings:
  - claim_id: "causal_1"
    issue: "Correlation (72%) supports but doesn't prove causation"
    suggestion: "Conduct A/B test with staged rollouts to establish causation"
    priority: medium
ungroundable: []
confidence: 0.8
evidence_anchors:
  - "incident_reports/"
  - "tool:correlation_analysis"
assumptions:
  - "Incident reports accurately identify root causes"
  - "Correlation analysis controlled for confounders"
```

## Verification

- [ ] Every grounded claim has at least one evidence anchor
- [ ] Evidence anchors use correct format (file:line, url, tool:...)
- [ ] Combined confidence is computed correctly from individual evidence
- [ ] Weak groundings have actionable suggestions
- [ ] Ungroundable claims are properly classified

**Verification tools:** Evidence anchor validator, file existence checks

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not fabricate evidence anchors
- Mark inferred evidence clearly distinct from direct evidence
- When grounding is impossible, say so rather than inventing weak evidence
- If confidence < 0.3, consider the claim ungrounded

## Composition Patterns

**Commonly follows:**
- `world-state` - Ground the claims in the state model
- `causal-model` - Ground causal relationships
- `inspect` - Gather evidence during inspection

**Commonly precedes:**
- `verify` - Grounding feeds verification
- `provenance` - Grounding and provenance complement each other
- `summarize` - Report grounding status in summaries

**Anti-patterns:**
- Never accept claims without grounding attempt
- Avoid circular grounding (A grounds B, B grounds A)

**Workflow references:**
- See `composition_patterns.md#world-model-build` for grounding in model construction
- See all workflows - grounding is a universal requirement
