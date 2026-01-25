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

See `skills/` for composed workflow examples:
- `debug-workflow/` - Debug and fix code issues
- `gap-analysis-workflow/` - Identify missing capabilities
- `world-model-workflow/` - Initialize world model
- `digital-twin-sync-workflow/` - Continuous world model synchronization

## Using Skills via Claude Code

```bash
# Invoke a skill
claude> /agent-capability-standard:detect-anomaly input.json

# List available skills
claude> /agent-capability-standard:help
```

