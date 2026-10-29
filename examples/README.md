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

`digital_twin_sync_loop.workflow_catalog.yaml` holds the digital twin
workflows of the reference catalog (`world_model_build`,
`digital_twin_sync_loop`, `digital_twin_bootstrap`), copied verbatim; a test
keeps them identical. CI validates it in strict mode:

```bash
python tools/validate_workflows.py --catalog examples/digital_twin_sync_loop.workflow_catalog.yaml --strict
```

The workflow skills run the reference catalog's workflows step by step:
- `skills/debug-workflow/` - Diagnose and fix a bug (`debug_code_change`)
- `skills/capability-gap-analysis/` - Identify missing capabilities (`capability_gap_analysis`)
- `skills/digital-twin-bootstrap/` - Build a world model and run a first sync (`digital_twin_bootstrap`)
- `skills/digital-twin-sync-loop/` - Keep a digital twin in sync (`digital_twin_sync_loop`)

To run a workflow on the reference executor from Python, see
[Running workflows](../docs/guides/RUNNING_WORKFLOWS.md).

## SDK Demos

| Script | Shows |
|--------|-------|
| `grounded_agent_demo.py` | `GroundedAgentAdapter` wrapping SDK options with the safety layer |
| `checkpoint_enforcement_demo.py` | Mutations blocked until a checkpoint exists |
| `capability_skills_demo.py` | Capability metadata for SDK tools |
| `grounded_query_demo.py` | `grounded_query` and `GroundedClient` |
| `structured_output_demo.py` | Structured output and budget enforcement |
| `discovery_demo.py` | Capability discovery |
| `mcp_tools_demo.py` | Capability-aware MCP tools |
| `subagent_bridge_demo.py` | Subagent bridge |

```bash
python examples/grounded_agent_demo.py
```

## Using Skills via Claude Code

```bash
# Invoke a capability skill
claude> /agent-capability-standard:detect

# Invoke a workflow skill
claude> /agent-capability-standard:debug-workflow
```
