# Quickstart Guide

Get up and running with the Agent Capability Standard in 10 minutes.

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
- Prerequisites are satisfied (e.g., `act-plan` requires `plan` and `checkpoint`)
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
  - capability: inspect
    purpose: Observe failing behavior, logs, and relevant code paths.
    store_as: inspect_out
  - capability: search
    purpose: Find related code, configs, and error patterns.
    store_as: search_out
  - capability: map-relationships
    purpose: Build dependency graph around failing component.
    store_as: map_relationships_out
  - capability: model-schema
    purpose: Define invariants/spec expectations for the component.
    store_as: model_schema_out
  - capability: critique
    purpose: List likely failure modes + edge cases.
    store_as: critique_out
  - capability: plan
    purpose: Produce minimal fix plan with checkpoints.
    store_as: plan_out
  - capability: checkpoint           # <-- Safety: checkpoint before mutation
    purpose: Create checkpoint before mutation.
    store_as: checkpoint_out
  - capability: act-plan             # <-- Requires checkpoint (enforced)
    purpose: Apply fix, run tests, and produce diff summary.
    requires_checkpoint: true
    store_as: act_plan_out
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
- **Safety by construction**: `checkpoint` before `act-plan` is required
- **Outputs are named**: `store_as` enables later steps to reference outputs

## Step 5: Explore the Capability Ontology (2 min)

Open `schemas/capability_ontology.json` and find the `act-plan` capability:

```json
{
  "id": "act-plan",
  "layer": "ACTION",
  "description": "Execute a planned action...",
  "input_schema": {
    "type": "object",
    "properties": {
      "plan": { "type": "object" },
      "context": { "type": "object" }
    },
    "required": ["plan"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "result": { "type": "object" },
      "side_effects": { "type": "array" }
    }
  },
  "requires": ["plan", "checkpoint"],
  "soft_requires": ["verify"]
}
```

Key observations:
- **Layer classification**: ACTION layer (causes side effects)
- **I/O schemas**: Typed contracts for inputs and outputs
- **Prerequisites**: `requires` defines hard dependencies
- **Soft dependencies**: `soft_requires` are recommended but not mandatory

## What's Next?

| Goal | Document |
|------|----------|
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
