---
name: estimate-risk
description: Approximate the current probability and potential impact of a risk. Use when assessing threats, evaluating vulnerabilities, or quantifying exposure.
argument-hint: "[risk] [--context <system>] [--factors]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Produce a quantitative risk estimate combining probability of occurrence and potential impact severity. This skill answers "how likely is this risk and how bad would it be if it occurred?" It assesses current risk posture based on present conditions, not future risk trajectories.

**Success criteria:**
- Risk probability is estimated with confidence bounds
- Impact severity is quantified or categorized
- Contributing risk factors are identified
- Risk score combines probability and impact appropriately

**Compatible schemas:**
- `docs/schemas/estimate_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `risk` | Yes | string | The risk to estimate (e.g., "data breach", "deployment failure", "budget overrun") |
| `context` | No | object | System, project, or environment where risk exists |
| `factors` | No | array | Known contributing factors to consider |
| `risk_matrix` | No | string | Risk framework to use (e.g., "5x5", "CVSS", "custom") |

## Procedure

1) **Define the risk precisely**: Clarify what adverse event is being assessed.
   - What is the risk event? (security breach, failure, loss, delay)
   - What is the scope of impact? (system, organization, users)
   - What time frame is relevant?

2) **Identify risk factors**: List conditions that influence likelihood and impact.
   - **Threat factors**: What could cause the risk to materialize?
   - **Vulnerability factors**: What weaknesses increase exposure?
   - **Control factors**: What mitigations reduce risk?
   - **Impact amplifiers**: What could worsen the outcome?

3) **Estimate probability**: Determine likelihood of the risk occurring.
   - Look for historical base rates of similar risks
   - Assess current threat landscape
   - Factor in existing controls and their effectiveness
   - Consider near-miss indicators

4) **Estimate impact severity**: Quantify the consequences if risk materializes.
   - Financial impact (direct costs, lost revenue)
   - Operational impact (downtime, disruption)
   - Reputational impact (trust, brand damage)
   - Compliance impact (fines, legal exposure)

5) **Combine into risk score**: Calculate overall risk level.
   - Risk = Probability x Impact (or use chosen risk matrix)
   - Categorize into risk tier (low, medium, high, critical)
   - Note which factors contribute most to the score

6) **Format output with grounding**: Structure per contract with evidence.

## Output Contract

Return a structured object:

```yaml
estimate:
  target_type: risk
  value: number | string  # Risk score or category
  unit: string | null     # Risk scale (1-25, percentage, category)
  range:
    low: number           # Optimistic risk estimate
    high: number          # Pessimistic risk estimate
risk_components:
  probability:
    value: number         # 0.0-1.0 or categorical
    rationale: string
  impact:
    value: number | string  # Severity score or category
    dimensions:
      - type: string      # financial, operational, reputational
        severity: string
methodology: string       # Risk assessment framework used
inputs_used:
  - string                # Factors and data sources
risk_factors:
  - factor: string
    direction: increases | decreases | neutral
    weight: low | medium | high
sensitivity:
  - factor: string
    impact: low | medium | high
confidence: number        # 0.0-1.0
evidence_anchors:
  - string
assumptions:
  - string
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `estimate.value` | number/string | Combined risk score (e.g., 15/25, "High") |
| `risk_components.probability` | object | Likelihood estimate with rationale |
| `risk_components.impact` | object | Severity estimate with dimensions |
| `risk_factors` | array | Factors that raise or lower the risk |
| `confidence` | number | Certainty in probability and impact estimates |

## Examples

### Example 1: Estimating Deployment Failure Risk

**Input:**
```yaml
risk: "production deployment failure causing user-facing outage"
context:
  system: "payment-service"
  deployment: "v2.4.0 release"
factors:
  - "large schema migration included"
  - "holiday weekend timing"
  - "recent team turnover"
```

**Output:**
```yaml
estimate:
  target_type: risk
  value: 12
  unit: "risk score (1-25 scale, probability x impact)"
  range:
    low: 8
    high: 18
risk_components:
  probability:
    value: 0.30
    rationale: "Schema migrations have 25% historical failure rate, elevated by team turnover reducing institutional knowledge"
  impact:
    value: "High (4/5)"
    dimensions:
      - type: financial
        severity: "high - payment processing affects revenue"
      - type: operational
        severity: "high - manual intervention required for rollback"
      - type: reputational
        severity: "medium - holiday outage more visible"
methodology: "5x5 risk matrix. Probability based on historical deployment failure rates adjusted for contextual factors. Impact based on business criticality assessment."
inputs_used:
  - "historical_deployments: 4/16 schema migrations failed in past year"
  - "system_criticality: Tier-1 (payment processing)"
  - "rollback_procedure: documented but not recently tested"
  - "monitoring_coverage: 85% of critical paths"
risk_factors:
  - factor: "schema migration complexity"
    direction: increases
    weight: high
  - factor: "holiday weekend (reduced staff)"
    direction: increases
    weight: medium
  - factor: "recent team turnover"
    direction: increases
    weight: medium
  - factor: "feature flags for gradual rollout"
    direction: decreases
    weight: medium
sensitivity:
  - factor: "rollback procedure reliability"
    impact: high
  - factor: "migration testing coverage"
    impact: high
  - factor: "on-call response time"
    impact: medium
confidence: 0.65
evidence_anchors:
  - "deployments/history.csv:schema_migrations"
  - "runbooks/payment-service-deploy.md:rollback"
  - "oncall/roster_holiday.json"
assumptions:
  - "Historical failure rates are predictive of future failures"
  - "Current controls are operating as documented"
  - "No additional unknown changes in this release"
```

**Evidence pattern:** Historical base rate with contextual risk factor adjustment.

---

### Example 2: Estimating Data Breach Risk

**Input:**
```yaml
risk: "unauthorized access to customer PII"
context:
  system: "customer database"
  security_posture: "last audit 6 months ago"
risk_matrix: "5x5"
```

**Output:**
```yaml
estimate:
  target_type: risk
  value: "Medium-High (15/25)"
  unit: "5x5 risk matrix score"
  range:
    low: 10
    high: 20
risk_components:
  probability:
    value: 0.15
    rationale: "Industry base rate of ~10% for similar systems, adjusted upward for aging security audit and known phishing attempts"
  impact:
    value: "Critical (5/5)"
    dimensions:
      - type: financial
        severity: "critical - regulatory fines up to $10M, remediation costs"
      - type: reputational
        severity: "critical - customer trust erosion"
      - type: compliance
        severity: "critical - GDPR/CCPA violations"
methodology: "5x5 risk matrix per NIST framework. Probability from threat intelligence and vulnerability assessment. Impact from data classification and regulatory exposure."
inputs_used:
  - "data_classification: PII for 2.3M customers"
  - "last_security_audit: 6 months ago, 3 medium findings unresolved"
  - "threat_intel: 12 phishing attempts targeting employees last quarter"
  - "access_controls: MFA enabled, but 15% exceptions granted"
risk_factors:
  - factor: "unresolved audit findings"
    direction: increases
    weight: high
  - factor: "MFA exceptions"
    direction: increases
    weight: medium
  - factor: "encryption at rest"
    direction: decreases
    weight: high
  - factor: "active threat intelligence monitoring"
    direction: decreases
    weight: medium
sensitivity:
  - factor: "audit finding remediation"
    impact: high
  - factor: "insider threat potential"
    impact: high
  - factor: "third-party access scope"
    impact: medium
confidence: 0.58
evidence_anchors:
  - "security/audit_report_q2.pdf:findings"
  - "iam/mfa_exceptions.csv"
  - "threat_intel/quarterly_report.md"
  - "compliance/data_inventory.json"
assumptions:
  - "Current threat landscape continues at similar intensity"
  - "No zero-day vulnerabilities in deployed software"
  - "Security controls are functioning as configured"
```

**Evidence pattern:** Security framework assessment with threat intelligence.

## Verification

- [ ] Both probability and impact are estimated
- [ ] Risk factors are identified with direction (increases/decreases)
- [ ] Risk score methodology is stated
- [ ] Evidence supports probability and impact claims
- [ ] Assumptions about controls and threats are explicit

**Verification tools:** Read, Grep

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not understate security risks without strong evidence
- If risk involves safety-critical systems, recommend expert review
- Clearly distinguish between risk of occurrence and worst-case scenarios

## Composition Patterns

**Commonly follows:**
- `detect-anomaly` - When anomaly triggers risk assessment
- `inspect` - To understand system context for risk
- `retrieve` - To gather threat intelligence or historical data

**Commonly precedes:**
- `compare` - To compare risk levels across options
- `plan` - To develop risk mitigation plan
- `forecast-risk` - To project risk trajectory over time

**Anti-patterns:**
- Never use for future risk predictions (use forecast-risk instead)
- Avoid for highly speculative risks without evidence base

**Workflow references:**
- See `workflow_catalog.json#security_assessment` for security risk context
