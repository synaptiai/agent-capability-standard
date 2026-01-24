# Safety Hooks

This directory contains hooks that implement the SAFETY layer capabilities from the Agent Capability Standard.

## Spec-Aligned Hooks

These hooks directly implement capabilities defined in the standard's SAFETY layer:

| Hook | Capability | Purpose |
|------|------------|---------|
| `pretooluse_require_checkpoint.sh` | `checkpoint` | Require checkpoint marker before mutation operations |
| `posttooluse_log_tool.sh` | `audit` | Log tool usage for audit trail and provenance |

## How Hooks Work

### Pre-Tool-Use Hooks

Run **before** a tool executes and can block operations.

```bash
# Exit 0 = allow, non-zero = block
./pretooluse_require_checkpoint.sh "$payload"
```

### Post-Tool-Use Hooks

Run **after** a tool executes for logging and audit.

```bash
./posttooluse_log_tool.sh "$payload"
```

## Configuration

Hooks are configured in `settings.json`:

```json
{
  "hooks": {
    "pretooluse_require_checkpoint": {
      "enabled": true,
      "configurable": true
    },
    "posttooluse_log_tool": {
      "enabled": true,
      "configurable": true
    }
  }
}
```

## Checkpoint System

The `pretooluse_require_checkpoint.sh` hook enforces the `checkpoint` capability requirement:
- Expects a marker file at `.claude/checkpoint.ok` before allowing mutation operations
- Enables workflows to enforce explicit confirmation before risky changes
- Maps to the spec's `requires_checkpoint: true` field on capabilities

Create checkpoint:
```bash
mkdir -p .claude && touch .claude/checkpoint.ok
```

## Audit Trail

The `posttooluse_log_tool.sh` hook implements the `audit` capability:
- Logs all tool invocations with timestamps
- Records what was executed for provenance tracking
- Enables post-hoc analysis of agent behavior

## Relationship to Spec

These hooks implement runtime enforcement of SAFETY layer requirements:

| Spec Field | Hook Implementation |
|------------|---------------------|
| `requires_checkpoint: true` | `pretooluse_require_checkpoint.sh` blocks without checkpoint |
| `audit` capability | `posttooluse_log_tool.sh` records tool usage |

See `schemas/capability_ontology.json` for full capability definitions.
