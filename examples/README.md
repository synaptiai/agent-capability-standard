# Examples

This directory contains usage examples for the Agent Capability Standard.

## Quick Start

### Run the Workflow Validator

Validate workflow definitions against the capability ontology:

```bash
# From repository root
python tools/validate_workflows.py

# Emit suggested patch diffs for type coercions
python tools/validate_workflows.py --emit-patch
```

### Run Conformance Tests

```bash
# From repository root
python scripts/run_conformance.py
```

## Example Workflows

See `skills/workflows/` for composed workflow examples:
- `debug_code_change/` - Debug and fix code issues
- `capability_gap_analysis/` - Identify missing capabilities
- `digital_twin_bootstrap/` - Initialize world model
- `digital_twin_sync_loop/` - Continuous world model synchronization

## Using Skills via Claude Code

```bash
# Invoke a skill
claude> /agent-capability-standard:detect-anomaly input.json

# List available skills
claude> /agent-capability-standard:help
```

