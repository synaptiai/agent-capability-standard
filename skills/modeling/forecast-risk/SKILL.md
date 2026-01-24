---
name: forecast-risk
description: Predict how risk probability and impact will evolve over time. Use when projecting risk trajectories, anticipating threat evolution, or planning risk mitigation timing.
argument-hint: "[risk] [--horizon <period>] [--triggers]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Predict how a risk's probability and potential impact will change over time. This skill answers "how will this risk evolve?" Unlike estimate-risk (current posture), this projects risk trajectories forward to anticipate when risks may materialize or when mitigation windows close.

**Success criteria:**
- Risk trajectory over time is modeled
- Trigger events and thresholds are identified
- Critical decision points are highlighted
- Mitigation windows are specified

**Compatible schemas:**
- `docs/schemas/forecast_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `risk` | Yes | string | The risk to forecast (e.g., "security breach", "capacity exhaustion", "key person departure") |
| `time_horizon` | Yes | string | How far ahead to forecast |
| `current_risk` | No | object | Current risk assessment (probability, impact) |
| `known_events` | No | array | Scheduled events that will affect risk |

## Procedure

1) **Define the risk and its current state**: Establish baseline risk posture.
   - What is the risk event?
   - What is current probability and impact?
   - What factors currently influence the risk?

2) **Identify risk trajectory drivers**: Determine what will change risk over time.
   - **Threat evolution**: Will threat actors/sources change?
   - **Vulnerability changes**: Will exposure increase or decrease?
   - **Control changes**: Are mitigations being implemented or degrading?
   - **Context changes**: Will environment or stakes change?

3) **Map known events affecting risk**: Plot scheduled changes.
   - Planned system changes
   - Contract expirations or renewals
   - Regulatory deadlines
   - Resource changes (team, budget)

4) **Identify risk triggers**: Define events that would significantly change risk.
   - What signals indicate risk is increasing?
   - What events would cause probability spikes?
   - What would change impact severity?

5) **Model risk trajectory**: Project risk over time.
   - Plot probability evolution
   - Plot impact evolution
   - Identify crossing of risk thresholds
   - Calculate risk score trajectory

6) **Identify mitigation windows**: When can action reduce risk?
   - When is intervention most effective?
   - When do options close?
   - What is the cost of delay?

7) **Format output**: Structure with temporal risk projections.

## Output Contract

Return a structured object:

```yaml
forecast:
  target_type: risk
  risk: string              # What risk is being forecasted
  prediction: string        # Primary risk trajectory description
  time_horizon: string      # Forecast period
  probability: number       # Confidence in forecast (0-1)
  trajectory:
    - timestamp: string     # Point in time
      probability: number   # Risk probability at this point
      impact: string        # Impact severity at this point
      risk_score: number    # Combined risk score
      notes: string         # What's changing
  scenarios:
    - name: string
      probability: number
      outcome:
        trajectory: string
        peak_risk: string
triggers:
  - event: string           # What would spike risk
    probability_impact: string
    impact_impact: string
    likelihood: number      # How likely is this trigger
drivers:
  - factor: string
    direction: positive | negative | neutral
    magnitude: low | medium | high
mitigation_windows:
  - window: string          # Time period
    action: string          # What mitigation is possible
    effectiveness: string   # How much risk reduction
    deadline: string        # When window closes
confidence: number          # 0.0-1.0
evidence_anchors:
  - string
assumptions:
  - string
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `forecast.trajectory` | array | Risk level at multiple time points |
| `triggers` | array | Events that would significantly change risk |
| `mitigation_windows` | array | Time-bounded opportunities to reduce risk |
| `drivers` | array | Factors shaping risk evolution |
| `confidence` | number | Certainty in trajectory (lower for longer horizons) |

## Examples

### Example 1: Forecasting Technical Debt Risk

**Input:**
```yaml
risk: "system instability from accumulated technical debt"
time_horizon: "12 months"
current_risk:
  probability: 0.25
  impact: "high"
  debt_score: 42
known_events:
  - "major feature launch Q2"
  - "team expansion Q3"
  - "framework upgrade planned Q4"
```

**Output:**
```yaml
forecast:
  target_type: risk
  risk: "system instability from accumulated technical debt"
  prediction: "Risk increases through Q2 peak, then improves with Q4 upgrade"
  time_horizon: "12 months"
  probability: 0.65
  trajectory:
    - timestamp: "Q1 end"
      probability: 0.30
      impact: "high"
      risk_score: 15
      notes: "Steady accumulation; team focused on feature development"
    - timestamp: "Q2 end"
      probability: 0.45
      impact: "high"
      risk_score: 22
      notes: "Peak risk; major feature adds complexity without refactoring"
    - timestamp: "Q3 end"
      probability: 0.40
      impact: "high"
      risk_score: 20
      notes: "New team members learning; some tech debt addressed"
    - timestamp: "Q4 end"
      probability: 0.20
      impact: "medium"
      risk_score: 10
      notes: "Framework upgrade addresses major debt sources"
  scenarios:
    - name: "debt_accelerates"
      probability: 0.25
      outcome:
        trajectory: "Feature pressure prevents any debt reduction; Q4 upgrade delayed"
        peak_risk: "probability 0.60, impact critical"
    - name: "managed"
      probability: 0.55
      outcome:
        trajectory: "Planned trajectory; upgrade executes successfully"
        peak_risk: "probability 0.45, impact high (Q2)"
    - name: "proactive"
      probability: 0.20
      outcome:
        trajectory: "Team allocates 20% time to debt; risk peaks lower"
        peak_risk: "probability 0.35, impact high"
triggers:
  - event: "major production outage"
    probability_impact: "+0.15 probability"
    impact_impact: "escalates to critical"
    likelihood: 0.25
  - event: "key engineer departure"
    probability_impact: "+0.10 probability"
    impact_impact: "unchanged"
    likelihood: 0.15
  - event: "Q4 upgrade complications"
    probability_impact: "+0.20 probability in Q4"
    impact_impact: "unchanged"
    likelihood: 0.30
drivers:
  - factor: "feature development pressure"
    direction: negative
    magnitude: high
  - factor: "team expansion"
    direction: positive
    magnitude: medium
  - factor: "framework upgrade"
    direction: positive
    magnitude: high
  - factor: "code review standards"
    direction: positive
    magnitude: low
mitigation_windows:
  - window: "Q1"
    action: "Allocate 15% sprint capacity to debt reduction"
    effectiveness: "reduce Q2 peak by 30%"
    deadline: "before Q2 feature crunch"
  - window: "Q3"
    action: "Onboard new team with debt-reduction projects"
    effectiveness: "accelerate Q4 improvements"
    deadline: "first 6 weeks of Q3"
  - window: "Q4 pre-upgrade"
    action: "Comprehensive testing of upgrade path"
    effectiveness: "reduce upgrade trigger risk by 50%"
    deadline: "2 weeks before upgrade"
confidence: 0.58
evidence_anchors:
  - "engineering/tech_debt_tracker.md"
  - "project/q2_roadmap.md:features"
  - "hr/hiring_plan.xlsx:engineering"
  - "architecture/upgrade_plan.md:framework"
assumptions:
  - "Feature roadmap is accurate"
  - "Hiring plan executes on schedule"
  - "Framework upgrade is feasible as planned"
  - "No major market shifts requiring pivot"
```

**Evidence pattern:** Event-driven risk trajectory with known milestones.

---

### Example 2: Forecasting Regulatory Compliance Risk

**Input:**
```yaml
risk: "GDPR non-compliance penalty"
time_horizon: "6 months"
current_risk:
  probability: 0.15
  impact: "severe (up to 4% annual revenue)"
known_events:
  - "EU regulator audit scheduled Q2"
  - "new consent management system launching month 3"
```

**Output:**
```yaml
forecast:
  target_type: risk
  risk: "GDPR non-compliance penalty"
  prediction: "Risk spikes during audit, then reduces significantly with new system"
  time_horizon: "6 months"
  probability: 0.70
  trajectory:
    - timestamp: "month 1"
      probability: 0.15
      impact: "severe"
      risk_score: 19
      notes: "Baseline risk; known gaps in consent records"
    - timestamp: "month 2"
      probability: 0.25
      impact: "severe"
      risk_score: 31
      notes: "Audit preparation reveals additional gaps"
    - timestamp: "month 3 (audit)"
      probability: 0.35
      impact: "severe"
      risk_score: 44
      notes: "Peak risk during active audit scrutiny"
    - timestamp: "month 4"
      probability: 0.20
      impact: "severe"
      risk_score: 25
      notes: "New consent system live; addressing audit findings"
    - timestamp: "month 6"
      probability: 0.10
      impact: "severe"
      risk_score: 13
      notes: "Remediation complete; improved compliance posture"
  scenarios:
    - name: "audit_findings_severe"
      probability: 0.20
      outcome:
        trajectory: "Audit uncovers systemic issues; enforcement action initiated"
        peak_risk: "probability 0.60 for penalty"
    - name: "managed_audit"
      probability: 0.60
      outcome:
        trajectory: "Audit identifies gaps but accepts remediation plan"
        peak_risk: "probability 0.35 during audit"
    - name: "clean_audit"
      probability: 0.20
      outcome:
        trajectory: "Audit finds minor issues only; no enforcement risk"
        peak_risk: "probability 0.15 (unchanged)"
triggers:
  - event: "customer data breach"
    probability_impact: "+0.40 probability immediately"
    impact_impact: "escalates to critical"
    likelihood: 0.10
  - event: "consent system launch delay"
    probability_impact: "+0.15 probability for months 4-6"
    impact_impact: "unchanged"
    likelihood: 0.25
  - event: "competitor penalty announcement"
    probability_impact: "+0.05 (increased regulator attention)"
    impact_impact: "unchanged"
    likelihood: 0.30
drivers:
  - factor: "regulator audit"
    direction: negative
    magnitude: high
  - factor: "new consent management system"
    direction: positive
    magnitude: high
  - factor: "industry compliance trends"
    direction: neutral
    magnitude: low
  - factor: "legal team readiness"
    direction: positive
    magnitude: medium
mitigation_windows:
  - window: "months 1-2 (pre-audit)"
    action: "Proactive gap remediation and documentation"
    effectiveness: "reduce audit finding severity by 40%"
    deadline: "before audit start"
  - window: "during audit"
    action: "Transparent communication and remediation commitment"
    effectiveness: "increase probability of warning vs penalty"
    deadline: "throughout audit"
  - window: "post-audit"
    action: "Accelerated implementation of consent system"
    effectiveness: "reduce enforcement probability by 50%"
    deadline: "within 60 days of audit findings"
confidence: 0.62
evidence_anchors:
  - "compliance/gdpr_gap_analysis.pdf"
  - "legal/audit_notification.pdf"
  - "product/consent_system_roadmap.md"
  - "regulatory/eu_enforcement_trends.md"
assumptions:
  - "Audit proceeds on scheduled timeline"
  - "Consent system launches on schedule"
  - "No data breaches occur during period"
  - "Regulator approach follows recent precedents"
```

**Evidence pattern:** Event-centered risk modeling with regulatory timeline.

## Verification

- [ ] Risk trajectory covers multiple time points
- [ ] Triggers are identified with likelihood
- [ ] Mitigation windows have deadlines
- [ ] Scenarios cover range of risk evolution paths
- [ ] Current risk state is baseline for projection

**Verification tools:** Read, Grep

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Never minimize security or compliance risks without evidence
- Clearly note when risk could spike suddenly (trigger events)
- Distinguish between risk probability and impact changes

## Composition Patterns

**Commonly follows:**
- `estimate-risk` - Current risk is baseline for projection
- `retrieve` - Historical risk data and trends
- `forecast-outcome` - When outcome affects risk trajectory

**Commonly precedes:**
- `plan` - To develop risk mitigation plan
- `compare` - To compare risk trajectories across options
- `forecast-impact` - When risk mitigation impact is needed

**Anti-patterns:**
- Never assume risks remain static over time
- Avoid forecasting without identifying trigger events

**Workflow references:**
- See `workflow_catalog.json#risk_management` for risk forecasting context
