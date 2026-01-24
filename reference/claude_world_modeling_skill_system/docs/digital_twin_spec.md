# Digital twin spec (rigorous)

A digital twin is a world model with **synchronization + control**.

## 1) Twin requirements

### 1.1 Sync loop
- Observe: ingest signals (logs/sensors/APIs)
- Update: reconcile to world-state
- Detect drift: compare expected vs observed
- Actuate: propose or execute actions
- Verify: check the outcome
- Rollback: revert if unsafe

### 1.2 Drift detection
Drift exists when:
- state variables diverge beyond tolerance
- transitions occur without corresponding observations
- identity-resolution collisions increase
- uncertainty rises over time

### 1.3 Control policy
Control is constrained by:
- permissions
- safety constraints
- cost/latency limits
- human approval gates

---

## 2) Twin atoms mapping

- Observation: `inspect`
- State update: `world-state`
- Identity: `identity-resolution`
- Dynamics: `state-transition`
- Causality: `causal-model`
- Uncertainty: `uncertainty-model`
- Drift: `detect-anomaly` + `estimate-risk` + `forecast-risk`
- Control plan: `plan` + `schedule`
- Actuation: `act-plan`
- Assurance: `verify` + `audit` + `rollback`

---

## 3) Reference architecture (conceptual)

1) Ingest (signals)
2) Normalize (schema)
3) Resolve identity
4) Update state store
5) Apply transition rules
6) Run drift detectors
7) Decide actuation
8) Execute + verify
9) Log provenance

Outputs:
- twin snapshot
- drift report
- action report
- audit log
