# Claude Agent SDK Integration

This guide explains how to integrate the Grounded Agency capability standard with the Claude Agent SDK, enabling SDK-based agents to operate with evidence-grounded decisions, checkpoint-before-mutation safety, and audit trails.

## Quick Start

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

# 1. Create adapter with configuration
adapter = GroundedAgentAdapter(
    GroundedAgentConfig(
        strict_mode=True,           # Block mutations without checkpoint
        ontology_path="schemas/capability_ontology.json",
    )
)

# 2. Create checkpoint before mutations
adapter.create_checkpoint(
    scope=["src/*.py"],
    reason="Before refactoring"
)

# 3. Wrap SDK options with safety layer
base_options = ClaudeAgentOptions(
    allowed_tools=["Read", "Write", "Edit", "Bash"],
    permission_mode="acceptEdits",
)
options = adapter.wrap_options(base_options)

# 4. Use SDK as normal - safety is enforced automatically
async with ClaudeSDKClient(options) as client:
    await client.query("Refactor the authentication module")
    async for msg in client.receive_response():
        print(msg)
```

## Architecture

The integration consists of four main components:

```
┌─────────────────────────────────────────────────────────────┐
│                    GroundedAgentAdapter                      │
├─────────────────────────────────────────────────────────────┤
│  ┌───────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │CapabilityReg- │  │ToolCapability- │  │ Permission     │  │
│  │istry          │  │Mapper          │  │ Callback       │  │
│  │               │  │                │  │                │  │
│  │ Loads ontol-  │  │ Maps SDK tools │  │ Enforces       │  │
│  │ ogy JSON      │  │ to capabilities│  │ checkpoints    │  │
│  └───────────────┘  └────────────────┘  └────────────────┘  │
│                                                              │
│  ┌───────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │Checkpoint-    │  │EvidenceStore   │  │ PostToolUse    │  │
│  │Tracker        │  │                │  │ Hooks          │  │
│  │               │  │                │  │                │  │
│  │ Checkpoint    │  │ Evidence       │  │ Collect evi-   │  │
│  │ lifecycle     │  │ anchors        │  │ dence, track   │  │
│  │ management    │  │ storage        │  │ skills         │  │
│  └───────────────┘  └────────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                 ┌────────────────────────┐
                 │   Claude Agent SDK     │
                 │   ClaudeSDKClient      │
                 └────────────────────────┘
```

## Tool-to-Capability Mapping

The adapter automatically maps SDK tools to Grounded Agency capabilities:

| SDK Tool | Capability | Risk | Requires Checkpoint |
|----------|-----------|------|---------------------|
| Read | retrieve | low | No |
| Glob | search | low | No |
| Grep | search | low | No |
| LS | observe | low | No |
| WebFetch | retrieve | low | No |
| WebSearch | search | low | No |
| **Write** | **mutate** | **high** | **Yes** |
| **Edit** | **mutate** | **high** | **Yes** |
| **MultiEdit** | **mutate** | **high** | **Yes** |
| Task | delegate | medium | No |
| Skill | invoke | medium | No |

### Bash Command Classification

Bash commands are analyzed to determine their capability:

| Pattern | Capability | Risk | Checkpoint |
|---------|-----------|------|------------|
| `ls`, `cat`, `head`, `pwd` | observe | low | No |
| `git status`, `git log` | observe | low | No |
| `rm`, `mv`, `chmod` | mutate | high | Yes |
| `sed -i`, `git push` | mutate | high | Yes |
| `curl -X POST`, `ssh` | send | high | Yes |

## Checkpoint Lifecycle

Checkpoints are the core safety mechanism. They must exist before mutations:

```
                        ┌──────────────────┐
                        │  Create          │
                        │  Checkpoint      │
                        └────────┬─────────┘
                                 │
                                 ▼
                   ┌─────────────────────────┐
            ┌──────│  Checkpoint Valid       │──────┐
            │      │  (not expired/consumed) │      │
            │      └─────────────────────────┘      │
            │                                       │
            ▼                                       ▼
  ┌─────────────────┐                   ┌─────────────────┐
  │  Mutation       │                   │  Mutation       │
  │  ALLOWED        │                   │  BLOCKED        │
  └────────┬────────┘                   └─────────────────┘
           │
           ▼
  ┌─────────────────┐
  │  Consume        │
  │  Checkpoint     │
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │  Next mutation  │
  │  needs new      │
  │  checkpoint     │
  └─────────────────┘
```

### Creating Checkpoints

```python
# Method 1: Direct API
checkpoint_id = adapter.create_checkpoint(
    scope=["src/*.py", "tests/*.py"],
    reason="Before refactoring authentication"
)

# Method 2: Via CheckpointTracker
checkpoint_id = adapter.checkpoint_tracker.create_checkpoint(
    scope=["*"],
    reason="Full backup before changes",
    expiry_minutes=60,
    metadata={"task": "issue-123"}
)

# Method 3: Autonomous (Claude invokes checkpoint skill)
# Claude: "I'll create a checkpoint before editing"
# [Invokes Skill tool with skill="checkpoint"]
# skill_tracker hook updates CheckpointTracker
```

### Consuming Checkpoints

After a successful mutation, consume the checkpoint:

```python
# Mutations complete successfully
adapter.consume_checkpoint()

# Now subsequent mutations need a new checkpoint
assert not adapter.has_valid_checkpoint()
```

## Evidence Anchors

Evidence anchors track provenance for grounded decisions:

```python
# Access collected evidence
recent = adapter.get_evidence(10)
# ['tool:Read:abc123', 'tool:Grep:def456', 'file:src/main.py']

# Get evidence by type
mutations = adapter.evidence_store.get_mutations()
tool_outputs = adapter.evidence_store.get_tool_outputs()

# Get evidence for a capability
retrieve_evidence = adapter.evidence_store.get_for_capability("retrieve")
```

### Evidence Format

```
tool:Read:tool_use_id_123      # Tool output evidence
file:src/main.py               # File reference
command:20240115143022         # Bash command execution
mutation:config.yaml           # State mutation
```

## Configuration Options

```python
@dataclass
class GroundedAgentConfig:
    # Path to capability ontology
    ontology_path: str = "schemas/capability_ontology.json"

    # If True, block mutations without checkpoint
    # If False, log warning but allow
    strict_mode: bool = True

    # Audit log location
    audit_log_path: str = ".claude/audit.log"

    # Checkpoint storage directory
    checkpoint_dir: str = ".checkpoints"

    # Default checkpoint expiry (minutes)
    expiry_minutes: int = 30
```

## Using with Capability Skills

The Grounded Agency skills (in `skills/`) can be invoked by Claude:

```python
# Configure SDK to load skills from project
options = adapter.wrap_options(
    ClaudeAgentOptions(
        cwd=Path("/path/to/agent-capability-standard"),
        setting_sources=["project"],  # Loads skills
        allowed_tools=["Skill", "Read", "Write", "Bash"],
    )
)

# Now Claude can autonomously invoke skills:
# "Create a checkpoint before modifying the config"
# Claude invokes: Skill(skill="checkpoint", scope=["config/*"])
```

### Skill → Checkpoint Flow

```
User: "Make a backup before editing the config"
          ↓
Claude: Invokes Skill(skill="checkpoint")
          ↓
Checkpoint skill executes (git stash, file backup)
          ↓
skill_tracker hook detects invocation
          ↓
CheckpointTracker.create_checkpoint() called
          ↓
User: "Now update config with new settings"
          ↓
Claude: Invokes Write tool
          ↓
Permission callback checks → Checkpoint exists → ALLOWED
          ↓
Evidence collector captures output
```

## Examples

### Basic Usage

```python
import asyncio
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

async def main():
    adapter = GroundedAgentAdapter(GroundedAgentConfig())

    # Create checkpoint
    adapter.create_checkpoint(["*.py"], "Before changes")

    options = adapter.wrap_options(
        ClaudeAgentOptions(allowed_tools=["Read", "Write"])
    )

    async with ClaudeSDKClient(options) as client:
        await client.query("Add docstrings to all functions")
        async for msg in client.receive_response():
            print(msg)

    # Show evidence
    print("Evidence:", adapter.get_evidence())

asyncio.run(main())
```

### Non-Strict Mode (Warnings Only)

```python
adapter = GroundedAgentAdapter(
    GroundedAgentConfig(strict_mode=False)
)

# Mutations will proceed with warning but not block
# [WARN] Write executing without checkpoint
```

### Custom Checkpoint Expiry

```python
adapter = GroundedAgentAdapter(
    GroundedAgentConfig(expiry_minutes=120)  # 2 hours
)

# Or per-checkpoint:
adapter.checkpoint_tracker.create_checkpoint(
    scope=["*"],
    reason="Long-running task",
    expiry_minutes=480,  # 8 hours
)
```

## Validation

After implementation, validate the integration:

```bash
# Run unit tests
pytest tests/test_sdk_integration.py -v

# Run examples
python examples/grounded_agent_demo.py
python examples/checkpoint_enforcement_demo.py

# Verify ontology is valid
python tools/validate_workflows.py
```

## Troubleshooting

### "Capability requires checkpoint" Error

The adapter is blocking a mutation because no valid checkpoint exists.

```python
# Solution 1: Create checkpoint before mutation
adapter.create_checkpoint(["*"], "Before changes")

# Solution 2: Use non-strict mode (not recommended)
adapter = GroundedAgentAdapter(GroundedAgentConfig(strict_mode=False))
```

### Checkpoint Expired

Checkpoints expire after `expiry_minutes` (default: 30).

```python
# Check checkpoint status
checkpoint = adapter.checkpoint_tracker.get_active_checkpoint()
if checkpoint:
    print(f"Expires at: {checkpoint.expires_at}")
    print(f"Still valid: {checkpoint.is_valid()}")
```

### SDK Types Not Found

If `claude_agent_sdk` isn't installed, the adapter falls back to dict-based types.

```bash
pip install claude-agent-sdk
```

## API Reference

### GroundedAgentAdapter

```python
class GroundedAgentAdapter:
    config: GroundedAgentConfig
    registry: CapabilityRegistry
    mapper: ToolCapabilityMapper
    checkpoint_tracker: CheckpointTracker
    evidence_store: EvidenceStore

    def wrap_options(self, base: ClaudeAgentOptions) -> ClaudeAgentOptions: ...
    def create_checkpoint(self, scope: list[str], reason: str) -> str: ...
    def consume_checkpoint(self) -> str | None: ...
    def has_valid_checkpoint(self) -> bool: ...
    def get_evidence(self, n: int = 10) -> list[str]: ...
    def get_mutations(self) -> list[EvidenceAnchor]: ...
```

### CheckpointTracker

```python
class CheckpointTracker:
    def create_checkpoint(
        self,
        scope: list[str],
        reason: str,
        expiry_minutes: int | None = None,
    ) -> str: ...

    def has_valid_checkpoint(self) -> bool: ...
    def consume_checkpoint(self) -> str | None: ...
    def get_active_checkpoint_id(self) -> str | None: ...
    def get_checkpoint_by_id(self, checkpoint_id: str) -> Checkpoint | None: ...
```

### EvidenceStore

```python
class EvidenceStore:
    def add_anchor(self, anchor: EvidenceAnchor, capability_id: str | None = None): ...
    def get_recent(self, n: int = 10) -> list[str]: ...
    def get_by_kind(self, kind: str) -> list[EvidenceAnchor]: ...
    def get_for_capability(self, capability_id: str) -> list[EvidenceAnchor]: ...
    def get_mutations(self) -> list[EvidenceAnchor]: ...
```
