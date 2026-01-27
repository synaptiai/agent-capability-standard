# Quickstart Guide

Get up and running with the Agent Capability Standard in 10 minutes.

---

## What You'll Gain

After completing this quickstart, you'll be able to:

- **Validate workflows before runtime** — Catch type mismatches, missing prerequisites, and invalid bindings before they cause production failures
- **Understand conformance levels** — Know what safety guarantees your workflows provide
- **Use the toolchain** — Run the validator on your own workflows
- **Read workflow definitions** — Understand how capabilities compose into reliable pipelines

### Why Validation Matters

Without validation, workflow errors surface at runtime—often in production, often at 2 AM.

The validator catches issues that would otherwise fail silently:
- **Missing capability prerequisites** — `act-plan` without `checkpoint` means no rollback
- **Type mismatches** — Passing an array where an object is expected
- **Invalid bindings** — Referencing outputs that don't exist
- **Ungrounded claims** — Data flowing without provenance

Fixing these statically saves hours of runtime debugging and prevents data corruption from half-executed workflows.

---

## Prerequisites

- Python 3.9+
- Git

## Step 1: Clone and Setup (2 min)

```bash
# Clone the repository
git clone https://github.com/synaptiai/agent-capability-standard.git
cd agent-capability-standard

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install pyyaml
```

## Step 2: Validate the Reference Workflows (2 min)

The standard includes 5 production-ready workflows. Let's validate them:

```bash
python tools/validate_workflows.py
```

Expected output:
```
VALIDATION PASS
Suggestions written to: tools/validator_suggestions.json
```

The validator checks:
- All capabilities exist in the ontology
- Prerequisites are satisfied (e.g., `mutate` requires `checkpoint`)
- Binding references point to valid step outputs
- Types are compatible between producers and consumers

## Step 3: Run Conformance Tests (2 min)

The conformance suite tests both valid and intentionally invalid fixtures:

```bash
python scripts/run_conformance.py
```

Expected output:
```
PASS: pass_reference
PASS: fail_unknown_capability
PASS: fail_bad_binding_path
PASS: fail_ambiguous_untyped
PASS: fail_consumer_contract_mismatch

Conformance PASSED
```

Each test verifies a specific validation behavior:

| Test | Purpose |
|------|---------|
| `pass_reference` | Valid workflows should pass |
| `fail_unknown_capability` | Unknown capabilities should fail |
| `fail_bad_binding_path` | Invalid binding paths should fail |
| `fail_ambiguous_untyped` | Ambiguous types without annotations should fail |
| `fail_consumer_contract_mismatch` | Type mismatches should fail |

## Step 4: Explore a Workflow (2 min)

Open `schemas/workflow_catalog.yaml` and examine the `debug_code_change` workflow:

```yaml
debug_code_change:
  goal: Safely diagnose and fix a bug/regression in a codebase.
  risk: medium
  steps:
  - capability: observe
    purpose: Observe failing behavior, logs, and relevant code paths.
    store_as: observe_out
  - capability: search
    purpose: Find related code, configs, and error patterns.
    store_as: search_out
  - capability: attribute
    purpose: Build dependency graph and identify causal relationships.
    store_as: attribute_out
  - capability: constrain
    purpose: Define invariants/spec expectations for the component.
    store_as: constrain_out
  - capability: critique
    purpose: List likely failure modes + edge cases.
    store_as: critique_out
  - capability: plan
    purpose: Produce minimal fix plan with checkpoints.
    store_as: plan_out
  - capability: checkpoint           # <-- Safety: checkpoint before mutation
    purpose: Create checkpoint before mutation.
    store_as: checkpoint_out
  - capability: execute              # <-- Requires checkpoint (enforced)
    purpose: Apply fix, run tests, and produce diff summary.
    requires_checkpoint: true
    store_as: execute_out
  - capability: verify
    purpose: Run targeted verification and return PASS/FAIL.
    store_as: verify_out
  - capability: audit
    purpose: Record what changed and why.
    store_as: audit_out
  - capability: rollback
    purpose: If verify FAIL, revert safely.
    store_as: rollback_out
```

Key observations:
- **Capabilities are atomic**: Each step does one thing
- **Safety by construction**: `checkpoint` before `execute` is required
- **Outputs are named**: `store_as` enables later steps to reference outputs

## Step 5: Explore the Capability Ontology (2 min)

Open `schemas/capability_ontology.json` and find the `mutate` capability:

```json
{
  "id": "mutate",
  "layer": "EXECUTE",
  "description": "Change persistent state",
  "risk": "high",
  "mutation": true,
  "requires_checkpoint": true,
  "requires_approval": true,
  "input_schema": {
    "type": "object",
    "required": ["target", "operation"],
    "properties": {
      "target": {"type": "string", "description": "What to modify"},
      "operation": {"type": "object", "description": "Modification to apply"},
      "checkpoint_id": {"type": "string", "description": "Recovery checkpoint"}
    }
  },
  "output_schema": {
    "type": "object",
    "required": ["success", "evidence_anchors"],
    "properties": {
      "success": {"type": "boolean"},
      "previous_state": {"type": "any", "description": "State before mutation"},
      "new_state": {"type": "any", "description": "State after mutation"},
      "evidence_anchors": {"type": "array"}
    }
  }
}
```

Key observations:
- **Layer classification**: EXECUTE layer (causes state changes)
- **Safety flags**: `mutation: true`, `requires_checkpoint: true`
- **I/O schemas**: Typed contracts for inputs and outputs
- **Evidence anchors**: Required in output for grounded agency

## Step 6: Choose Your Domain (2 min)

The framework includes domain-specific templates to accelerate adoption. Choose the domain closest to your use case:

### Manufacturing
For production monitoring, quality control, predictive maintenance, and supply chain.

```bash
# View the manufacturing profile
cat schemas/profiles/manufacturing.yaml

# Explore manufacturing workflows
cat schemas/workflows/manufacturing_workflows.yaml
```

**Key characteristics:**
- High trust for sensors (0.92-0.95)
- Checkpoints before all actuator commands
- Human required for all mutations

**Documentation:** [docs/domains/manufacturing/](domains/manufacturing/README.md)

### Personal Assistant
For scheduling, research, task delegation, and communication drafting.

```bash
cat schemas/profiles/personal_assistant.yaml
cat schemas/workflows/personal_assistant_workflows.yaml
```

**Key characteristics:**
- Highest trust for user input (0.98)
- Never auto-send communications
- Learned preferences inform but don't override

**Documentation:** [docs/domains/personal-assistant/](domains/personal-assistant/README.md)

### Data Analysis
For pipeline validation, anomaly investigation, reporting, and ML monitoring.

```bash
cat schemas/profiles/data_analysis.yaml
cat schemas/workflows/data_analysis_workflows.yaml
```

**Key characteristics:**
- High trust for certified data (0.95)
- Required data lineage grounding
- Statistical uncertainty in measurements

**Documentation:** [docs/domains/data-analysis/](domains/data-analysis/README.md)

### Healthcare (Clinical Decision Support)
For patient monitoring, alert triage, care plan review, and handoffs.

```bash
cat schemas/profiles/healthcare.yaml
cat schemas/workflows/healthcare_workflows.yaml
```

**Key characteristics:**
- NO autonomous clinical actions
- 7-year audit retention
- All outputs include clinical disclaimers

**Documentation:** [docs/domains/healthcare/](domains/healthcare/README.md)

### Domain Selection Guide

| If you're building... | Start with... |
|-----------------------|---------------|
| Factory automation agents | Manufacturing |
| Personal productivity tools | Personal Assistant |
| Data pipelines/ML systems | Data Analysis |
| Clinical decision support | Healthcare |
| Something else | Pick the closest, then customize |

Each domain provides:
- **Profile** — Pre-calibrated trust weights, risk thresholds, checkpoint policies
- **Workflows** — Ready-to-use workflow patterns
- **Documentation** — Customization and integration guidance

## What's Next?

| Goal | Document |
|------|----------|
| Explore domain templates | [docs/domains/](domains/README.md) |
| Build your own workflow | [TUTORIAL.md](TUTORIAL.md) |
| Understand key terms | [GLOSSARY.md](GLOSSARY.md) |
| Read the full spec | [STANDARD-v1.0.0.md](../spec/STANDARD-v1.0.0.md) |
| Understand conformance levels | [CONFORMANCE.md](../spec/CONFORMANCE.md) |

## Common Issues

### "ModuleNotFoundError: No module named 'yaml'"

Install the dependency:
```bash
pip install pyyaml
```

### "FileNotFoundError: schemas/..."

Make sure you're running from the repository root:
```bash
cd agent-capability-standard
python tools/validate_workflows.py
```

### Validator reports errors

Read the error message carefully. Common issues:
- Unknown capability: Check spelling against `schemas/capability_ontology.json`
- Missing prerequisite: Add the required step before the one that needs it
- Invalid binding: Ensure the referenced `store_as` exists in a prior step

---

**Time to complete:** ~10 minutes
