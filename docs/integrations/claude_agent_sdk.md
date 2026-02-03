# Claude Agent SDK Integration

This guide explains how to integrate the Grounded Agency capability standard with the Claude Agent SDK, enabling SDK-based agents to operate with evidence-grounded decisions, checkpoint-before-mutation safety, and audit trails.

## Quick Start

```python
from claude_agent_sdk import ClaudeAgentOptions
from grounded_agency import grounded_query, GroundedAgentAdapter, GroundedAgentConfig

# 1. Create adapter with configuration
adapter = GroundedAgentAdapter(
    GroundedAgentConfig(
        strict_mode=True,           # Block mutations without checkpoint
        max_budget_usd=1.00,        # Cap spending at $1
    )
)

# 2. Create checkpoint before mutations
adapter.create_checkpoint(
    scope=["src/*.py"],
    reason="Before refactoring"
)

# 3. Use grounded_query() — drop-in replacement for query()
async for msg in grounded_query(
    "Refactor the authentication module",
    adapter=adapter,
):
    print(msg)

# 4. Check cost after completion
print(f"Total cost: ${adapter.cost_summary.total_usd:.4f}")
print(f"Evidence: {adapter.get_evidence()}")
```

### Using GroundedClient

For long-lived sessions where you send multiple queries:

```python
from grounded_agency import GroundedClient, GroundedAgentAdapter, GroundedAgentConfig

adapter = GroundedAgentAdapter(GroundedAgentConfig(strict_mode=True))
adapter.create_checkpoint(["*"], "Before changes")

async with GroundedClient(adapter) as client:
    await client.query("Refactor the authentication module")
    async for msg in client.receive_response():
        print(msg)

print(f"Cost: ${adapter.cost_summary.total_usd:.4f}")
```

### Using wrap_options() (Low-level)

For direct SDK usage without the `grounded_query()` wrapper:

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

adapter = GroundedAgentAdapter(GroundedAgentConfig(strict_mode=True))
adapter.create_checkpoint(["src/*.py"], "Before refactoring")

base_options = ClaudeAgentOptions(
    allowed_tools=["Read", "Write", "Edit", "Bash"],
    permission_mode="acceptEdits",
)
options = adapter.wrap_options(base_options)

async with ClaudeSDKClient(options) as client:
    await client.query("Refactor the authentication module")
    async for msg in client.receive_response():
        print(msg)
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    GroundedAgentAdapter                          │
├─────────────────────────────────────────────────────────────────┤
│  ┌───────────────┐  ┌────────────────┐  ┌────────────────────┐  │
│  │CapabilityReg- │  │ToolCapability- │  │ Permission         │  │
│  │istry          │  │Mapper          │  │ Callback           │  │
│  │               │  │                │  │                    │  │
│  │ Loads ontol-  │  │ Maps SDK tools │  │ Enforces           │  │
│  │ ogy YAML      │  │ to capabilities│  │ checkpoints        │  │
│  └───────────────┘  └────────────────┘  └────────────────────┘  │
│                                                                  │
│  ┌───────────────┐  ┌────────────────┐  ┌────────────────────┐  │
│  │Checkpoint-    │  │EvidenceStore   │  │ Pre/Post ToolUse   │  │
│  │Tracker        │  │                │  │ Hooks              │  │
│  │               │  │ Evidence       │  │                    │  │
│  │ Checkpoint    │  │ anchors        │  │ PreToolUse: block  │  │
│  │ lifecycle     │  │ storage        │  │ PostToolUse: audit │  │
│  └───────────────┘  └────────────────┘  └────────────────────┘  │
│                                                                  │
│  ┌───────────────┐  ┌────────────────┐                          │
│  │CostSummary    │  │Orchestration-  │                          │
│  │               │  │Runtime         │                          │
│  │ Tracks USD    │  │ (optional)     │                          │
│  │ cost and      │  │                │                          │
│  │ per-model     │  │ Exports agents │                          │
│  │ breakdown     │  │ to SDK format  │                          │
│  └───────────────┘  └────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
   │grounded_     │  │GroundedClient│  │wrap_options() │
   │query()       │  │              │  │ (low-level)   │
   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
          │                 │                 │
          └─────────────────┼─────────────────┘
                            ▼
               ┌────────────────────────┐
               │   Claude Agent SDK     │
               │   query() / Client     │
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

### MCP Tool Mapping

MCP tools are dynamically registered via `create_grounded_mcp_server()`:

```python
from claude_agent_sdk import tool
from grounded_agency import GroundedAgentAdapter, create_grounded_mcp_server

@tool
def deploy_service(service_name: str) -> str:
    """Deploy a service to production."""
    return f"Deployed {service_name}"

deploy_service.metadata = {
    "capability_id": "execute",
    "risk": "high",
}

adapter = GroundedAgentAdapter()
server = create_grounded_mcp_server(
    name="deploy-tools",
    version="1.0.0",
    tools=[deploy_service],
    adapter=adapter,
)
# deploy_service now requires checkpoint before use
```

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

## PreToolUse Hook Enforcement

The adapter injects both PreToolUse and PostToolUse hooks:

- **PreToolUse**: Blocks mutation tools (Write, Edit, Bash with destructive commands) when no valid checkpoint exists. Returns `{"permissionDecision": "deny"}` in strict mode.
- **PostToolUse**: Collects evidence anchors and auto-consumes checkpoints after successful mutations.

This provides defense-in-depth alongside the `can_use_tool` permission callback:

```python
# Both enforcement layers are active:
# 1. PreToolUse hook checks checkpoint before tool runs
# 2. can_use_tool callback provides fine-grained permission control
# 3. PostToolUse hook collects evidence after tool runs
```

## Structured Output

Use `output_format` to get structured JSON responses:

```python
adapter = GroundedAgentAdapter(
    GroundedAgentConfig(
        output_format={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "changes": {"type": "array", "items": {"type": "string"}},
                "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["summary", "changes", "risk_level"],
        }
    )
)

# Structured output is auto-injected into SDK options
options = adapter.wrap_options(base_options)
```

## Budget Enforcement

Set a maximum cost budget:

```python
adapter = GroundedAgentAdapter(
    GroundedAgentConfig(
        max_budget_usd=5.00,  # Cap at $5
        model="sonnet",       # Default model
        max_turns=20,         # Limit turns
    )
)

async for msg in grounded_query("Complex task", adapter=adapter):
    print(msg)

# Check actual cost
print(f"Total: ${adapter.cost_summary.total_usd:.4f}")
print(f"By model: {adapter.cost_summary.by_model}")
print(f"Turns: {adapter.cost_summary.turn_count}")
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

## Multi-Agent Coordination

Bridge the orchestration runtime to SDK subagents:

```python
from grounded_agency import (
    GroundedAgentAdapter,
    GroundedAgentConfig,
    OrchestrationRuntime,
    OrchestrationConfig,
)

# Set up orchestration
adapter = GroundedAgentAdapter(GroundedAgentConfig())
runtime = OrchestrationRuntime(
    capability_registry=adapter.registry,
    evidence_store=adapter.evidence_store,
)

# Register agents with capabilities
runtime.register_agent(
    "analyst",
    capabilities={"search", "retrieve", "classify"},
    metadata={
        "description": "Research and analysis agent",
        "model": "sonnet",
        "allowed_tools": ["Read", "Grep", "WebSearch"],
    },
)
runtime.register_agent(
    "writer",
    capabilities={"generate", "mutate"},
    metadata={
        "description": "Content generation agent",
        "model": "sonnet",
        "allowed_tools": ["Read", "Write", "Edit"],
    },
)

# Bridge to SDK format
adapter.orchestrator = runtime
options = adapter.wrap_options(base_options)
# options.agents now contains SDK-compatible AgentDefinition dicts
```

## Configuration Options

```python
@dataclass
class GroundedAgentConfig:
    # Path to capability ontology
    ontology_path: str = "schemas/capability_ontology.yaml"

    # If True, block mutations without checkpoint
    # If False, log warning but allow
    strict_mode: bool = True

    # Audit log location
    audit_log_path: str = ".claude/audit.log"

    # Checkpoint storage directory
    checkpoint_dir: str = ".checkpoints"

    # Default checkpoint expiry (minutes)
    expiry_minutes: int = 30

    # SDK features
    output_format: dict | None = None   # JSON schema for structured output
    max_budget_usd: float | None = None # Cost budget cap
    model: str | None = None            # Default model
    max_turns: int | None = None        # Turn limit
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
PreToolUse hook checks → Checkpoint exists → PASS
          ↓
Permission callback checks → Checkpoint valid → ALLOWED
          ↓
Evidence collector captures output
```

## Validation

After implementation, validate the integration:

```bash
# Run unit tests
pytest tests/test_sdk_integration.py -v
pytest tests/test_grounded_query.py -v
pytest tests/test_structured_output.py -v
pytest tests/test_pretooluse_hooks.py -v
pytest tests/test_mcp_integration.py -v

# Run examples
python examples/grounded_agent_demo.py
python examples/grounded_query_demo.py
python examples/structured_output_demo.py
python examples/mcp_tools_demo.py
python examples/subagent_bridge_demo.py

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
`grounded_query()` and `GroundedClient` require the SDK.

```bash
pip install claude-agent-sdk
```

## API Reference

### grounded_query()

```python
async def grounded_query(
    prompt: str,
    *,
    options: ClaudeAgentOptions | None = None,
    config: GroundedAgentConfig | None = None,
    adapter: GroundedAgentAdapter | None = None,
) -> AsyncIterator[AssistantMessage | ResultMessage | SystemMessage]:
    """Drop-in replacement for query() with grounded safety."""
```

### GroundedClient

```python
class GroundedClient:
    def __init__(
        self,
        adapter: GroundedAgentAdapter | None = None,
        config: GroundedAgentConfig | None = None,
        options: ClaudeAgentOptions | None = None,
    ) -> None: ...

    async def __aenter__(self) -> GroundedClient: ...
    async def __aexit__(self, *args) -> None: ...
    async def query(self, prompt: str) -> None: ...
    async def receive_response(self) -> AsyncIterator[Any]: ...
```

### GroundedAgentAdapter

```python
class GroundedAgentAdapter:
    config: GroundedAgentConfig
    orchestrator: OrchestrationRuntime | None
    registry: CapabilityRegistry
    mapper: ToolCapabilityMapper
    checkpoint_tracker: CheckpointTracker
    evidence_store: EvidenceStore
    cost_summary: CostSummary

    def wrap_options(self, base: ClaudeAgentOptions) -> ClaudeAgentOptions: ...
    def create_checkpoint(self, scope: list[str], reason: str) -> str: ...
    def consume_checkpoint(self) -> str | None: ...
    def has_valid_checkpoint(self) -> bool: ...
    def get_evidence(self, n: int = 10) -> list[str]: ...
    def get_mutations(self) -> list[EvidenceAnchor]: ...
```

### CostSummary

```python
@dataclass
class CostSummary:
    total_usd: float = 0.0
    by_model: dict[str, float] = field(default_factory=dict)
    turn_count: int = 0
```

### create_grounded_mcp_server()

```python
def create_grounded_mcp_server(
    *,
    name: str,
    version: str,
    tools: list,
    adapter: GroundedAgentAdapter,
) -> Any:
    """Create MCP server with capability-aware tool mappings."""
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

## OASF Interoperability

The `grounded_agency.adapters.oasf` module provides bidirectional mapping between
OASF skill codes and Grounded Agency capabilities. See
[schemas/interop/oasf_mapping.yaml](../../schemas/interop/oasf_mapping.yaml) for the
mapping data and the [OASF comparison doc](../comparisons/OASF_COMPARISON.md) for
design rationale.
