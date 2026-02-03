# API Reference -- Grounded Agency Python SDK

> **Package**: `grounded_agency`
> **Version**: `0.1.0`
> **Python**: 3.9+
> **License**: See repository root

This document provides the complete API reference for the Grounded Agency Python SDK. Every public class, method, property, constant, and type alias exported by the `grounded_agency` package is documented here with full signatures, parameter descriptions, return types, and usage examples.

---

## Table of Contents

1. [Package Exports](#1-package-exports)
2. [GroundedAgentConfig](#2-groundedagentconfig)
3. [GroundedAgentAdapter](#3-groundedagentadapter)
4. [CapabilityRegistry](#4-capabilityregistry)
5. [CapabilityNode](#5-capabilitynode)
6. [CapabilityEdge](#6-capabilityedge)
7. [ToolCapabilityMapper](#7-toolcapabilitymapper)
8. [ToolMapping](#8-toolmapping)
9. [CheckpointTracker](#9-checkpointtracker)
10. [Checkpoint](#10-checkpoint)
11. [EvidenceStore](#11-evidencestore)
12. [EvidenceAnchor](#12-evidenceanchor)
13. [OASFAdapter](#13-oasfadapter)
14. [OASFMapping & OASFSkillResult](#14-oasfmapping--oasfskillresult)
15. [Hook Factory Functions](#15-hook-factory-functions)
16. [Type Aliases & Constants](#16-type-aliases--constants)
17. [CLI Tools Reference](#17-cli-tools-reference)

---

## 1. Package Exports

**Module**: `grounded_agency/__init__.py`

The top-level package re-exports all primary public symbols:

```python
from grounded_agency import (
    # Main adapter
    GroundedAgentAdapter,
    GroundedAgentConfig,
    # Capabilities
    CapabilityRegistry,
    ToolCapabilityMapper,
    ToolMapping,
    # State management
    CheckpointTracker,
    Checkpoint,
    EvidenceStore,
    EvidenceAnchor,
    # Types
    HookCallback,
    # Logging
    logger,
)
```

The package logger is pre-configured with `NullHandler` so consumers control their own logging setup:

```python
import logging
logging.getLogger("grounded_agency").setLevel(logging.DEBUG)
```

---

## 2. GroundedAgentConfig

**Module**: `grounded_agency/adapter.py`
**Decorators**: `@dataclass(slots=True)`

Configuration dataclass for the `GroundedAgentAdapter`. All fields have defaults so the config can be instantiated with no arguments.

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `ontology_path` | `str` | Auto-detected | Path to `capability_ontology.yaml`. Auto-detected via `get_default_ontology_path()` which searches package-relative, project-relative, and cwd-relative locations. |
| `strict_mode` | `bool` | `True` | If `True`, block mutations without a valid checkpoint. If `False`, log a warning but allow execution. |
| `audit_log_path` | `str` | `".claude/audit.log"` | Path for the audit log file written by hooks. |
| `checkpoint_dir` | `str` | `".checkpoints"` | Directory for checkpoint metadata storage. |
| `expiry_minutes` | `int` | `30` | Default checkpoint expiry in minutes. After this period, a checkpoint is no longer valid. |

### Example

```python
from grounded_agency import GroundedAgentConfig

# Default configuration (strict mode, 30-minute checkpoints)
config = GroundedAgentConfig()

# Permissive configuration for development
dev_config = GroundedAgentConfig(
    strict_mode=False,
    expiry_minutes=120,
    checkpoint_dir="/tmp/checkpoints",
)
```

### Helper Function: `get_default_ontology_path()`

```python
def get_default_ontology_path() -> str
```

Returns the cached default ontology path. Resolution order:

1. Package-relative path via `importlib.resources` (installed package)
2. `../schemas/capability_ontology.yaml` relative to module directory (development)
3. `schemas/capability_ontology.yaml` relative to module directory (alternative layout)
4. `schemas/capability_ontology.yaml` relative to cwd (fallback)

---

## 3. GroundedAgentAdapter

**Module**: `grounded_agency/adapter.py`
**Decorators**: `@dataclass`

The main entry point for integrating Grounded Agency safety patterns with the Claude Agent SDK. Wraps SDK options to inject permission callbacks, evidence-collection hooks, and skill-tracking hooks.

### Constructor

```python
GroundedAgentAdapter(config: GroundedAgentConfig = GroundedAgentConfig())
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `GroundedAgentConfig` | `GroundedAgentConfig()` | Adapter configuration. |

During `__post_init__`, the adapter creates:

- `self.registry` -- `CapabilityRegistry` loaded from `config.ontology_path`
- `self.mapper` -- `ToolCapabilityMapper` initialized with the raw ontology dict
- `self.checkpoint_tracker` -- `CheckpointTracker` initialized with `config.checkpoint_dir`
- `self.evidence_store` -- `EvidenceStore` (default 10,000 anchor capacity)

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `config` | `GroundedAgentConfig` | The configuration this adapter was created with. |
| `registry` | `CapabilityRegistry` | Capability ontology registry. |
| `mapper` | `ToolCapabilityMapper` | Tool-to-capability mapper. |
| `checkpoint_tracker` | `CheckpointTracker` | Checkpoint lifecycle manager. |
| `evidence_store` | `EvidenceStore` | Evidence anchor storage. |

---

### `wrap_options(base: Any) -> Any`

Wraps SDK `ClaudeAgentOptions` with the grounded agency safety layer.

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `base` | `Any` | A `ClaudeAgentOptions` instance. Typed as `Any` to avoid hard dependency on `claude_agent_sdk`. |

**Returns**: Modified `ClaudeAgentOptions` with safety layer injected.

**Injected modifications**:

- `enable_file_checkpointing=True` for SDK-level rollback support
- `can_use_tool` callback for checkpoint enforcement (see permission callback below)
- `PostToolUse` hooks: evidence collector, skill tracker, mutation consumer
- `Skill` added to `allowed_tools` if not present
- `"project"` added to `setting_sources` if not present

**Example**:

```python
adapter = GroundedAgentAdapter(GroundedAgentConfig(strict_mode=True))
options = adapter.wrap_options(base_options)

async with ClaudeSDKClient(options) as client:
    await client.query("Edit the config file...")
```

**Internal behavior of the permission callback**:

When `strict_mode=True` and a tool requiring a checkpoint is invoked without one, the callback returns `PermissionResultDeny` (or a dict `{"allowed": False, "message": ...}` if the SDK is not installed). When `strict_mode=False`, a warning is logged but execution proceeds. On any internal error during the permission check, access is denied (fail-closed security).

**Internal behavior of the mutation consumer hook**:

After a mutation tool completes successfully, the active checkpoint is automatically consumed, enforcing one-checkpoint-per-mutation semantics. If the mutation fails (indicated by `is_error` in the response), the checkpoint is preserved.

---

### `create_checkpoint(scope: list[str] | str = "*", reason: str = "Pre-mutation checkpoint") -> str`

Convenience method to create a checkpoint. Delegates to `self.checkpoint_tracker.create_checkpoint()`.

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `scope` | `list[str] \| str` | `"*"` | File patterns to checkpoint. `"*"` means all files. A string is auto-wrapped in a list. |
| `reason` | `str` | `"Pre-mutation checkpoint"` | Human-readable reason for creating the checkpoint. |

**Returns**: `str` -- The generated checkpoint ID (format: `chk_YYYYMMDD_HHMMSS_<32hex>`).

**Example**:

```python
checkpoint_id = adapter.create_checkpoint(
    scope=["src/*.py", "config/*.yaml"],
    reason="Before refactoring handler module"
)
# checkpoint_id => "chk_20250115_143022_a1b2c3d4..."
```

---

### `consume_checkpoint() -> str | None`

Marks the active checkpoint as consumed. Call after a successful mutation to require a new checkpoint for subsequent mutations.

**Returns**: `str | None` -- ID of the consumed checkpoint, or `None` if no active checkpoint exists.

---

### `has_valid_checkpoint() -> bool`

Checks whether a valid (non-consumed, non-expired) checkpoint exists.

**Returns**: `bool` -- `True` if there is a valid active checkpoint.

---

### `get_evidence(n: int = 10) -> list[str]`

Returns reference strings for the most recent evidence anchors.

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `n` | `int` | `10` | Maximum number of anchor references to return. |

**Returns**: `list[str]` -- Evidence reference strings (e.g., `"tool:Read:abc123"`, `"file:src/main.py"`).

---

### `get_mutations() -> list[EvidenceAnchor]`

Returns all evidence anchors of kind `"mutation"`.

**Returns**: `list[EvidenceAnchor]` -- All mutation evidence anchors recorded in the store.

---

### Properties

#### `ontology_version -> str`

Returns the version string from the ontology's `meta.version` field.

#### `capability_count -> int`

Returns the total number of capabilities loaded from the ontology.

---

## 4. CapabilityRegistry

**Module**: `grounded_agency/capabilities/registry.py`

Loads `capability_ontology.yaml` and provides typed, indexed access to capabilities, edges, and layers. Uses lazy loading -- the ontology is read from disk on first access.

### Constructor

```python
CapabilityRegistry(ontology_path: str | Path)
```

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `ontology_path` | `str \| Path` | Path to `capability_ontology.yaml`. |

**Raises**: `FileNotFoundError` if the ontology file does not exist (raised on first access, not on construction).

---

### `get_capability(cap_id: str) -> CapabilityNode | None`

Retrieves a capability by its ID.

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `cap_id` | `str` | Capability identifier (e.g., `"mutate"`, `"checkpoint"`, `"retrieve"`). |

**Returns**: `CapabilityNode | None` -- The capability node, or `None` if not found.

**Example**:

```python
registry = CapabilityRegistry("schemas/capability_ontology.yaml")
node = registry.get_capability("mutate")
assert node.requires_checkpoint is True
assert node.risk == "high"
```

---

### `get_edges(cap_id: str) -> list[CapabilityEdge]`

Returns all edges involving a capability, both outgoing and incoming. Avoids duplicates from self-referential edges.

**Parameters**: `cap_id: str` -- Capability identifier.

**Returns**: `list[CapabilityEdge]` -- Combined outgoing and incoming edges.

---

### `get_outgoing_edges(cap_id: str) -> list[CapabilityEdge]`

Returns edges where `cap_id` is the source (`from_cap`).

**Parameters**: `cap_id: str` -- Capability identifier.

**Returns**: `list[CapabilityEdge]` -- Outgoing edges. O(1) lookup via pre-built index.

---

### `get_incoming_edges(cap_id: str) -> list[CapabilityEdge]`

Returns edges where `cap_id` is the target (`to_cap`).

**Parameters**: `cap_id: str` -- Capability identifier.

**Returns**: `list[CapabilityEdge]` -- Incoming edges. O(1) lookup via pre-built index.

---

### `get_required_capabilities(cap_id: str) -> list[str]`

Returns capability IDs that are hard requirements for `cap_id`. Only returns edges with `edge_type == "requires"` (not `"soft_requires"`).

**Parameters**: `cap_id: str` -- Capability identifier.

**Returns**: `list[str]` -- IDs of capabilities that must be satisfied before `cap_id` can execute.

---

### `get_preceding_capabilities(cap_id: str) -> list[str]`

Returns capability IDs that must temporally precede `cap_id`. Filters for edges with `edge_type == "precedes"`.

**Parameters**: `cap_id: str` -- Capability identifier.

**Returns**: `list[str]` -- IDs of capabilities that must complete before `cap_id` starts.

---

### `get_conflicting_capabilities(cap_id: str) -> list[str]`

Returns capability IDs that cannot coexist with `cap_id` in the same workflow. Uses symmetric edge lookup (checks both directions) for `edge_type == "conflicts_with"`.

**Parameters**: `cap_id: str` -- Capability identifier.

**Returns**: `list[str]` -- IDs of conflicting capabilities.

---

### `get_alternatives(cap_id: str) -> list[str]`

Returns capability IDs that can substitute for `cap_id`. Uses symmetric edge lookup for `edge_type == "alternative_to"`.

**Parameters**: `cap_id: str` -- Capability identifier.

**Returns**: `list[str]` -- IDs of alternative capabilities.

---

### `get_specialized_by(cap_id: str) -> list[str]`

Returns capability IDs that specialize (are more specific variants of) `cap_id`. Looks for incoming `"specializes"` edges.

**Parameters**: `cap_id: str` -- Capability identifier.

**Returns**: `list[str]` -- IDs of specializing capabilities.

---

### `get_generalizes_to(cap_id: str) -> str | None`

Returns the more general capability that `cap_id` specializes. Looks for outgoing `"specializes"` edges.

**Parameters**: `cap_id: str` -- Capability identifier.

**Returns**: `str | None` -- The generalized capability ID, or `None`.

---

### `get_layer(layer_name: str) -> dict[str, Any]`

Returns metadata for a cognitive layer.

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `layer_name` | `str` | Layer identifier (e.g., `"VERIFY"`, `"EXECUTE"`, `"PERCEIVE"`). |

**Returns**: `dict[str, Any]` -- Layer metadata dict from the ontology, or empty dict if not found.

---

### `get_capabilities_in_layer(layer_name: str) -> list[CapabilityNode]`

Returns all capabilities belonging to a specific cognitive layer.

**Parameters**: `layer_name: str` -- Layer identifier.

**Returns**: `list[CapabilityNode]` -- Capabilities whose `layer` field matches `layer_name`.

**Example**:

```python
execute_caps = registry.get_capabilities_in_layer("EXECUTE")
for cap in execute_caps:
    print(f"{cap.id}: risk={cap.risk}, mutation={cap.mutation}")
```

---

### `get_high_risk_capabilities() -> list[CapabilityNode]`

Returns all capabilities with `risk == "high"`.

**Returns**: `list[CapabilityNode]` -- High-risk capability nodes.

---

### `get_checkpoint_required_capabilities() -> list[CapabilityNode]`

Returns all capabilities where `requires_checkpoint == True`.

**Returns**: `list[CapabilityNode]` -- Capabilities requiring a checkpoint before execution.

---

### `all_capabilities() -> list[CapabilityNode]`

Returns all capabilities in the ontology.

**Returns**: `list[CapabilityNode]` -- Every capability node.

---

### `all_edges() -> list[CapabilityEdge]`

Returns all edges (relationships) in the ontology.

**Returns**: `list[CapabilityEdge]` -- Every edge in the ontology graph.

---

### Properties

#### `version -> str`

The ontology version from `meta.version`. Returns `"unknown"` if not set.

#### `capability_count -> int`

Total number of capabilities loaded from the ontology.

#### `ontology -> dict[str, Any]`

The raw, lazy-loaded ontology dictionary. Triggers loading from disk on first access.

---

## 5. CapabilityNode

**Module**: `grounded_agency/capabilities/registry.py`
**Decorators**: `@dataclass(slots=True)`

Represents a single capability from the ontology.

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | *required* | Unique capability identifier (e.g., `"mutate"`, `"retrieve"`). |
| `layer` | `str` | *required* | Cognitive layer (e.g., `"EXECUTE"`, `"PERCEIVE"`). |
| `description` | `str` | *required* | Human-readable description. |
| `risk` | `str` | *required* | Risk level: `"low"`, `"medium"`, or `"high"`. |
| `mutation` | `bool` | *required* | Whether this capability modifies persistent state. |
| `requires_checkpoint` | `bool` | `False` | Whether a checkpoint is required before execution. |
| `requires_approval` | `bool` | `False` | Whether human approval is required. |
| `input_schema` | `dict[str, Any]` | `{}` | JSON Schema for capability inputs. |
| `output_schema` | `dict[str, Any]` | `{}` | JSON Schema for capability outputs. |

### Class Method: `from_dict(data: dict[str, Any]) -> CapabilityNode`

Factory method to create a `CapabilityNode` from an ontology YAML node dictionary.

---

## 6. CapabilityEdge

**Module**: `grounded_agency/capabilities/registry.py`
**Decorators**: `@dataclass(slots=True)`

Represents a relationship between two capabilities in the ontology graph.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `from_cap` | `str` | Source capability ID. |
| `to_cap` | `str` | Target capability ID. |
| `edge_type` | `str` | Relationship type. One of: `requires`, `soft_requires`, `enables`, `precedes`, `conflicts_with`, `alternative_to`, `specializes`. |

---

## 7. ToolCapabilityMapper

**Module**: `grounded_agency/capabilities/mapper.py`

Maps Claude Agent SDK tool invocations to capability metadata from the Grounded Agency ontology. For Bash commands, performs additional content analysis to classify the command as read-only or mutating.

### Constructor

```python
ToolCapabilityMapper(ontology: dict[str, Any] | None = None)
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ontology` | `dict[str, Any] \| None` | `None` | Raw ontology dict for validation (optional). |

---

### `map_tool(tool_name: str, tool_input: dict[str, Any]) -> ToolMapping`

Maps a tool invocation to its capability metadata. This is the primary method.

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `tool_name` | `str` | SDK tool name (e.g., `"Write"`, `"Bash"`, `"Read"`). |
| `tool_input` | `dict[str, Any]` | Tool input parameters. |

**Returns**: `ToolMapping` -- Capability metadata for this tool invocation.

**Mapping logic**:

1. If `tool_name == "Bash"`: delegates to `_classify_bash_command()` for content-based analysis
2. If `tool_name` is in `_TOOL_MAPPINGS`: returns the static mapping
3. Otherwise: returns a default `ToolMapping` with `capability_id="observe"`, `risk="medium"`

**Example**:

```python
mapper = ToolCapabilityMapper(ontology)

# Static mapping
mapping = mapper.map_tool("Write", {"file_path": "/tmp/test.txt"})
assert mapping.capability_id == "mutate"
assert mapping.requires_checkpoint is True

# Bash command analysis
mapping = mapper.map_tool("Bash", {"command": "ls -la"})
assert mapping.capability_id == "observe"
assert mapping.risk == "low"
```

---

### `is_high_risk(tool_name: str, tool_input: dict[str, Any]) -> bool`

Convenience method. Returns `True` if the tool's risk level is `"high"`.

---

### `requires_checkpoint(tool_name: str, tool_input: dict[str, Any]) -> bool`

Convenience method. Returns `True` if the tool invocation requires a checkpoint.

---

### `is_mutation(tool_name: str, tool_input: dict[str, Any]) -> bool`

Convenience method. Returns `True` if the tool invocation is a mutation (modifies state).

---

### `get_capability_id(tool_name: str, tool_input: dict[str, Any]) -> str`

Convenience method. Returns the ontology capability ID for this tool invocation.

---

### Static Tool Mappings (`_TOOL_MAPPINGS`)

The module defines 15 static tool-to-capability mappings:

| Tool Name | Capability ID | Layer | Risk | Mutation | Checkpoint Required |
|-----------|--------------|-------|------|----------|-------------------|
| `Read` | `retrieve` | PERCEIVE | low | No | No |
| `Glob` | `search` | PERCEIVE | low | No | No |
| `Grep` | `search` | PERCEIVE | low | No | No |
| `LS` | `observe` | PERCEIVE | low | No | No |
| `WebFetch` | `retrieve` | PERCEIVE | low | No | No |
| `WebSearch` | `search` | PERCEIVE | low | No | No |
| `Write` | `mutate` | EXECUTE | high | Yes | Yes |
| `Edit` | `mutate` | EXECUTE | high | Yes | Yes |
| `MultiEdit` | `mutate` | EXECUTE | high | Yes | Yes |
| `NotebookEdit` | `mutate` | EXECUTE | high | Yes | Yes |
| `Task` | `delegate` | COORDINATE | medium | No | No |
| `Skill` | `invoke` | COORDINATE | medium | No | No |
| `AskUser` | `inquire` | COORDINATE | low | No | No |
| `TodoRead` | `recall` | REMEMBER | low | No | No |
| `TodoWrite` | `persist` | REMEMBER | low | Yes | No |

---

### Bash Command Classification (`_classify_bash_command`)

Private method `_classify_bash_command(tool_input: dict[str, Any]) -> ToolMapping` classifies Bash commands using a fail-safe security model: unknown commands are treated as high-risk until explicitly allowlisted.

**Classification order** (first match wins):

1. **Empty command**: High-risk mutation (fail-safe)
2. **Shell injection patterns** (`_SHELL_INJECTION_PATTERNS`): High-risk mutation
3. **Network send patterns** (`_NETWORK_SEND_PATTERNS`): Mapped to `send` capability, high-risk
4. **Destructive patterns** (`_DESTRUCTIVE_PATTERNS`): High-risk mutation
5. **Read-only allowlist** (`_READ_ONLY_COMMANDS`): Low-risk `observe`
6. **Default**: High-risk mutation (fail-safe for unknown commands)

### Pattern Constants

#### `_DESTRUCTIVE_PATTERNS` (compiled regex)

Matches file system destructive operations, in-place edits, and VCS/container mutations:

- File ops: `rm`, `rmdir`, `mv`, `cp ... /`, `chmod`, `chown`, `ln`, `unlink`, `shred`
- Redirects: `>`, `>>`
- Piped destructive: `| rm`, `| tee`, `| dd`
- In-place sed: `sed -i`
- Git mutations: `push`, `reset`, `checkout --`, `clean`, `stash drop`, `branch -d/-D`
- npm: `publish`, `unpublish`
- Docker: `rm`, `rmi`, `prune`, `push`
- Kubernetes: `delete`, `apply`, `patch`, `edit`

#### `_NETWORK_SEND_PATTERNS` (compiled regex)

Matches outbound network operations:

- curl with POST/PUT/PATCH/DELETE or data flags
- wget with `--post`
- `ssh`, `scp`, `rsync`, `nc`, `telnet`, `ftp`

#### `_SHELL_INJECTION_PATTERNS` (compiled regex)

Matches shell injection and obfuscation techniques:

- Command substitution: `$(...)` and backticks
- Variable expansion: `${...}`
- Command chaining: `;`, `||`, `&&`
- Dangerous commands: `eval`, `exec`, `source`
- `xargs -I` (command injection vector)
- Control characters, hex/unicode escape sequences

#### `_READ_ONLY_COMMANDS` (frozenset of 40+ strings)

Allowlist of known safe, read-only commands:

- File inspection: `ls`, `cat`, `head`, `tail`, `less`, `more`, `file`, `stat`, `du`, `df`
- System info: `pwd`, `whoami`, `hostname`, `uname`, `date`, `cal`, `env`, `printenv`
- Text output: `echo`, `printf`, `which`, `whereis`, `locate`
- Search/transform: `find`, `grep`, `awk`, `sed`, `cut`, `sort`, `uniq`, `wc`, `diff`, `cmp`, `comm`, `tr`
- Git read-only: `git status`, `git log`, `git show`, `git diff`, `git branch`, `git remote`
- Package managers: `npm list`, `npm view`, `pip list`, `pip show`
- Docker read-only: `docker ps`, `docker images`, `docker logs`
- Kubernetes read-only: `kubectl get`, `kubectl describe`, `kubectl logs`

Note: two-word commands (e.g., `git status`) are checked by joining the first two tokens of the command.

---

## 8. ToolMapping

**Module**: `grounded_agency/capabilities/mapper.py`
**Decorators**: `@dataclass(slots=True)`

Result of mapping a tool invocation to its Grounded Agency capability.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `capability_id` | `str` | The ontology capability ID (e.g., `"mutate"`, `"retrieve"`, `"send"`). |
| `risk` | `str` | Risk level: `"low"`, `"medium"`, or `"high"`. |
| `mutation` | `bool` | Whether this tool modifies persistent state. |
| `requires_checkpoint` | `bool` | Whether a checkpoint is required before use. |

### `__str__() -> str`

Returns a human-readable string, e.g., `"mutate (risk=high) [CHECKPOINT REQUIRED]"`.

---

## 9. CheckpointTracker

**Module**: `grounded_agency/state/checkpoint_tracker.py`

Manages the checkpoint lifecycle for mutation safety. Before any mutation (Write, Edit, destructive Bash), a checkpoint must exist. The tracker manages creation, validity checking, consumption, history, and expiry.

### Class Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `DEFAULT_EXPIRY_MINUTES` | `30` | Default checkpoint expiry in minutes. |
| `DEFAULT_MAX_HISTORY` | `100` | Maximum checkpoints retained in history. |

### Constructor

```python
CheckpointTracker(
    checkpoint_dir: str | Path = ".checkpoints",
    max_history: int | None = None,
)
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `checkpoint_dir` | `str \| Path` | `".checkpoints"` | Directory for checkpoint metadata storage. |
| `max_history` | `int \| None` | `None` | Maximum checkpoints to keep in history. Defaults to `DEFAULT_MAX_HISTORY` (100). Oldest checkpoints are pruned when the limit is exceeded. |

---

### `create_checkpoint(scope: list[str], reason: str, expiry_minutes: int | None = None, metadata: dict[str, Any] | None = None) -> str`

Creates a new checkpoint. If an active checkpoint already exists, it is moved to history.

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `scope` | `list[str]` | *required* | File patterns to checkpoint (e.g., `["src/*.py"]`). Use `["*"]` for all files. |
| `reason` | `str` | *required* | Human-readable reason for the checkpoint. |
| `expiry_minutes` | `int \| None` | `None` | Override expiry in minutes. `None` uses `DEFAULT_EXPIRY_MINUTES`. |
| `metadata` | `dict[str, Any] \| None` | `None` | Additional metadata to attach to the checkpoint. |

**Returns**: `str` -- Checkpoint ID in format `chk_YYYYMMDD_HHMMSS_<32hex>`.

**ID generation**: Uses `SHA-256(os.urandom(16))[:32]` for 128 bits of cryptographic entropy, combined with a UTC timestamp prefix.

**Example**:

```python
tracker = CheckpointTracker()
cp_id = tracker.create_checkpoint(
    scope=["src/*.py", "tests/*.py"],
    reason="Before refactoring auth module",
    expiry_minutes=60,
)
```

---

### `has_valid_checkpoint() -> bool`

Checks if there is a valid (not consumed, not expired) active checkpoint.

**Returns**: `bool`

---

### `has_checkpoint_for_scope(target: str) -> bool`

Checks if there is a valid checkpoint covering a specific file or resource.

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `target` | `str` | File path or resource identifier to check against the checkpoint's scope. |

**Returns**: `bool` -- `True` if a valid checkpoint covers this target via exact match, wildcard `"*"`, or `fnmatch` glob pattern matching.

**Example**:

```python
tracker.create_checkpoint(scope=["src/*.py"], reason="test")
assert tracker.has_checkpoint_for_scope("src/main.py") is True
assert tracker.has_checkpoint_for_scope("docs/README.md") is False
```

---

### `get_active_checkpoint() -> Checkpoint | None`

Returns the currently active checkpoint if it is still valid (not consumed, not expired). Returns `None` if no valid checkpoint exists.

---

### `get_active_checkpoint_id() -> str | None`

Returns the ID of the active checkpoint, or `None` if no valid checkpoint exists.

---

### `consume_checkpoint() -> str | None`

Marks the active checkpoint as consumed. Called after a successful mutation to indicate the checkpoint has been "used up" and a new one is needed.

**Returns**: `str | None` -- ID of the consumed checkpoint, or `None` if no active checkpoint exists.

**Side effects**:

- Sets `consumed = True` and `consumed_at` on the checkpoint
- Moves the checkpoint to history
- Sets `_active_checkpoint = None`

---

### `get_checkpoint_by_id(checkpoint_id: str) -> Checkpoint | None`

Looks up a checkpoint by ID. Searches both the active checkpoint and the history.

**Parameters**: `checkpoint_id: str` -- The checkpoint ID to find.

**Returns**: `Checkpoint | None`

---

### `get_history(limit: int = 10) -> list[Checkpoint]`

Returns recent checkpoint history, sorted by creation time (most recent first). Includes the active checkpoint if one exists.

**Parameters**: `limit: int` -- Maximum number of checkpoints to return. Default: `10`.

**Returns**: `list[Checkpoint]` -- Sorted by `created_at` descending.

---

### `clear_expired() -> int`

Removes expired checkpoints from history. Also moves the active checkpoint to history if it has expired.

**Returns**: `int` -- Number of checkpoints cleared.

---

### `invalidate_all() -> None`

Invalidates all checkpoints. Used in rollback scenarios. Marks the active checkpoint as consumed and moves it to history.

---

### Properties

#### `checkpoint_count -> int`

Total number of checkpoints (active + history).

---

## 10. Checkpoint

**Module**: `grounded_agency/state/checkpoint_tracker.py`
**Decorators**: `@dataclass(slots=True)`

Represents a single checkpoint in the safety lifecycle.

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | *required* | Unique checkpoint identifier (format: `chk_YYYYMMDD_HHMMSS_<32hex>`). |
| `scope` | `list[str]` | *required* | File patterns covered by this checkpoint. |
| `reason` | `str` | *required* | Human-readable reason for the checkpoint. |
| `created_at` | `datetime` | *required* | UTC timestamp of creation. |
| `expires_at` | `datetime \| None` | `None` | UTC timestamp of expiry. `None` means no expiry. |
| `consumed` | `bool` | `False` | Whether the checkpoint has been consumed by a mutation. |
| `consumed_at` | `datetime \| None` | `None` | UTC timestamp when consumed. |
| `metadata` | `dict[str, Any]` | `{}` | Additional metadata attached to the checkpoint. |

### `is_valid() -> bool`

Returns `True` if the checkpoint is not consumed and not expired.

**Logic**:
- If `consumed == True`: returns `False`
- If `expires_at` is set and `datetime.now(UTC) > expires_at`: returns `False`
- Otherwise: returns `True`

### `matches_scope(target: str) -> bool`

Checks if a target file/resource is covered by this checkpoint's scope.

**Parameters**: `target: str` -- File path or resource to check.

**Returns**: `bool`

**Matching rules** (in order, first match wins):
1. If any scope pattern is `"*"`: matches everything
2. If any scope pattern is an exact string match: matches
3. If any scope pattern matches via `fnmatch.fnmatch()`: matches
4. Otherwise: no match

---

## 11. EvidenceStore

**Module**: `grounded_agency/state/evidence_store.py`

In-memory, bounded-size store for evidence anchors. Collects provenance records from tool executions, enabling verification that decisions are grounded in actual observations.

Uses a `deque` with `maxlen` for O(1) append and FIFO eviction. Maintains secondary indexes by `kind` and `capability_id` for efficient queries.

### Class Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `DEFAULT_MAX_ANCHORS` | `10000` | Default maximum number of anchors before FIFO eviction. |

### Constructor

```python
EvidenceStore(max_anchors: int | None = None)
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_anchors` | `int \| None` | `None` | Maximum anchors to store. `None` uses `DEFAULT_MAX_ANCHORS` (10,000). |

---

### `add_anchor(anchor: EvidenceAnchor, capability_id: str | None = None) -> None`

Adds an evidence anchor to the store. If `max_anchors` is exceeded, the oldest anchor is evicted (FIFO) from both the primary store and secondary indexes.

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `anchor` | `EvidenceAnchor` | *required* | The evidence anchor to store. |
| `capability_id` | `str \| None` | `None` | Optional capability ID to associate with this anchor for indexed lookup. |

---

### `get_recent(n: int = 10) -> list[str]`

Returns reference strings for the `n` most recent evidence anchors.

**Parameters**: `n: int` -- Number of anchors. Default: `10`.

**Returns**: `list[str]` -- Reference strings (e.g., `"tool:Read:abc123"`).

---

### `get_recent_anchors(n: int = 10) -> list[EvidenceAnchor]`

Returns the `n` most recent evidence anchors as full objects.

**Parameters**: `n: int` -- Number of anchors. Default: `10`.

**Returns**: `list[EvidenceAnchor]`

---

### `get_by_kind(kind: str) -> list[EvidenceAnchor]`

Returns all evidence anchors of a specific kind.

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `kind` | `str` | Evidence kind: `"tool_output"`, `"file"`, `"command"`, or `"mutation"`. |

**Returns**: `list[EvidenceAnchor]`

---

### `get_for_capability(capability_id: str) -> list[EvidenceAnchor]`

Returns evidence anchors associated with a capability via the secondary index.

**Parameters**: `capability_id: str` -- Capability ID from the ontology.

**Returns**: `list[EvidenceAnchor]`

---

### `get_for_capability_output(capability_id: str) -> list[str]`

Returns evidence reference strings for a capability's outputs. This is the format expected by capability output contracts.

**Parameters**: `capability_id: str` -- Capability ID from the ontology.

**Returns**: `list[str]` -- Evidence reference strings.

---

### `get_mutations() -> list[EvidenceAnchor]`

Shorthand for `get_by_kind("mutation")`. Returns all mutation evidence anchors.

---

### `get_tool_outputs() -> list[EvidenceAnchor]`

Shorthand for `get_by_kind("tool_output")`. Returns all tool output evidence anchors.

---

### `search_by_ref_prefix(prefix: str) -> list[EvidenceAnchor]`

Searches for evidence anchors whose reference string starts with the given prefix. Linear scan over all anchors.

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `prefix` | `str` | Reference prefix to match (e.g., `"tool:Read"`, `"file:"`, `"mutation:"`). |

**Returns**: `list[EvidenceAnchor]`

**Example**:

```python
read_anchors = store.search_by_ref_prefix("tool:Read")
file_anchors = store.search_by_ref_prefix("file:src/")
```

---

### `search_by_metadata(key: str, value: Any) -> list[EvidenceAnchor]`

Searches for evidence anchors with a specific metadata key-value pair. Linear scan over all anchors.

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | `str` | Metadata key to match. |
| `value` | `Any` | Value to match (exact equality). |

**Returns**: `list[EvidenceAnchor]`

**Example**:

```python
python_ops = store.search_by_metadata("operation", "write")
```

---

### `clear() -> None`

Removes all evidence from the store, including all secondary indexes.

---

### `to_list() -> list[dict[str, Any]]`

Exports all evidence as a list of dictionaries. Useful for serialization and audit logging.

**Returns**: `list[dict[str, Any]]` -- Each dict contains `ref`, `kind`, `timestamp`, and `metadata`.

---

### `__len__() -> int`

Returns the current number of anchors in the store.

### `__iter__() -> Iterator[EvidenceAnchor]`

Iterates over all anchors in insertion order (oldest first).

---

## 12. EvidenceAnchor

**Module**: `grounded_agency/state/evidence_store.py`
**Decorators**: `@dataclass(slots=True)`

A single piece of evidence from tool execution. Evidence anchors track the provenance of information, enabling verification that decisions are grounded in actual observations.

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `ref` | `str` | *required* | Reference string (e.g., `"tool:Read:abc123"`, `"file:src/main.py"`, `"mutation:config.yaml"`). |
| `kind` | `str` | *required* | Type of evidence: `"tool_output"`, `"file"`, `"command"`, or `"mutation"`. |
| `timestamp` | `str` | *required* | ISO 8601 UTC timestamp when the evidence was captured. |
| `metadata` | `dict[str, Any]` | `{}` | Additional context. Automatically sanitized via `_sanitize_metadata()` in `__post_init__`. |

### `__str__() -> str`

Returns `self.ref`.

### `__post_init__() -> None`

Automatically sanitizes metadata after construction:
- Validates key names (alphanumeric + underscore only, regex: `^[a-zA-Z_][a-zA-Z0-9_]*$`)
- Limits nesting depth to `_MAX_METADATA_DEPTH` (2 levels)
- Enforces size limit of `_MAX_METADATA_SIZE_BYTES` (1024 bytes) by truncating largest values
- Invalid keys are silently dropped; deeply nested values are flattened to truncated strings

---

### Class Method: `from_tool_output(tool_name, tool_use_id, tool_input, tool_response=None) -> EvidenceAnchor`

Creates an evidence anchor from a tool output.

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tool_name` | `str` | *required* | Name of the tool (e.g., `"Read"`, `"Bash"`). |
| `tool_use_id` | `str` | *required* | Unique ID for this tool use. |
| `tool_input` | `dict[str, Any]` | *required* | Input parameters to the tool. |
| `tool_response` | `Any` | `None` | Optional response data. |

**Returns**: `EvidenceAnchor` with `ref="tool:{tool_name}:{tool_use_id}"`, `kind="tool_output"`.

---

### Class Method: `from_file(file_path, file_hash=None, operation="read") -> EvidenceAnchor`

Creates an evidence anchor for a file reference.

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | `str` | *required* | Path to the file. |
| `file_hash` | `str \| None` | `None` | Optional content hash for integrity verification. |
| `operation` | `str` | `"read"` | Operation performed: `"read"`, `"write"`, or `"edit"`. |

**Returns**: `EvidenceAnchor` with `ref="file:{file_path}"`, `kind="file"`.

---

### Class Method: `from_command(command, exit_code, tool_use_id=None) -> EvidenceAnchor`

Creates an evidence anchor for a command execution.

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `command` | `str` | *required* | The command that was executed. |
| `exit_code` | `int` | *required* | Exit code from the command. |
| `tool_use_id` | `str \| None` | `None` | Optional tool use ID. Falls back to a timestamp-based ID. |

**Returns**: `EvidenceAnchor` with `ref="command:{ref_id}"`, `kind="command"`.

---

### Class Method: `from_mutation(target, operation, checkpoint_id=None) -> EvidenceAnchor`

Creates an evidence anchor for a state mutation.

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `target` | `str` | *required* | What was mutated (file path, resource ID). |
| `operation` | `str` | *required* | Type of mutation: `"write"`, `"edit"`, `"delete"`. |
| `checkpoint_id` | `str \| None` | `None` | Associated checkpoint ID for audit linkage. |

**Returns**: `EvidenceAnchor` with `ref="mutation:{target}"`, `kind="mutation"`.

---

## 13. OASFAdapter

**Module**: `grounded_agency/adapters/oasf.py`

Translates OASF (Open Agentic Schema Framework) skill invocations to Grounded Agency capabilities. Enables systems using OASF to invoke capabilities with full safety guarantees: evidence anchors, checkpoint enforcement, and audit trails.

### Constructor

```python
OASFAdapter(
    mapping_path: str | Path,
    registry: CapabilityRegistry | None = None,
)
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mapping_path` | `str \| Path` | *required* | Path to `schemas/interop/oasf_mapping.yaml`. |
| `registry` | `CapabilityRegistry \| None` | `None` | Optional registry instance. If not provided, auto-loads from `schemas/capability_ontology.yaml` relative to the mapping file's parent directory. |

**Raises**: `FileNotFoundError` if the mapping file does not exist (raised on first access).

---

### `translate(skill_code: str) -> OASFSkillResult`

Translates an OASF skill code to Grounded Agency capabilities with full safety metadata.

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `skill_code` | `str` | OASF skill code (e.g., `"109"`, `"801"`, `"6"`). |

**Returns**: `OASFSkillResult` with mapping, resolved capability nodes, checkpoint requirement, and max risk level.

**Raises**: `UnknownSkillError` (subclass of `KeyError`) if the skill code has no mapping.

**Example**:

```python
adapter = OASFAdapter("schemas/interop/oasf_mapping.yaml")
result = adapter.translate("109")

print(result.mapping.skill_name)        # "Text Classification"
print(result.mapping.capabilities)       # ("classify",)
print(result.mapping.domain_hint)        # "text"
print(result.requires_checkpoint)        # False
print(result.max_risk)                   # "low"
print(len(result.capability_nodes))      # 1
```

---

### `get_mapping(skill_code: str) -> OASFMapping | None`

Retrieves the mapping for an OASF skill code without resolving capability nodes. Lighter weight than `translate()`.

**Parameters**: `skill_code: str` -- OASF skill code.

**Returns**: `OASFMapping | None`

---

### `list_categories() -> list[OASFMapping]`

Returns all top-level OASF category mappings (not subcategories).

**Returns**: `list[OASFMapping]`

---

### `list_all_mappings() -> list[OASFMapping]`

Returns all mappings (categories and subcategories) in YAML source order. Order is deterministic on Python 3.7+.

**Returns**: `list[OASFMapping]`

---

### `reverse_lookup(capability_id: str) -> list[str]`

Finds all OASF skill codes that map to a given Grounded Agency capability. Uses a computed reverse mapping cached after first computation.

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `capability_id` | `str` | Grounded Agency capability ID (e.g., `"detect"`, `"classify"`). |

**Returns**: `list[str]` -- OASF skill codes that include this capability.

**Example**:

```python
codes = adapter.reverse_lookup("classify")
# => ["1", "109", ...]  (all OASF codes that use the classify capability)
```

---

### Properties

#### `oasf_version -> str`

The OASF version this mapping was built for, from `meta.oasf_version`.

#### `mapping_version -> str`

Version of the mapping file itself, from `meta.version`.

#### `category_count -> int`

Number of top-level OASF categories mapped.

#### `total_mapping_count -> int`

Total number of mapped entries (categories + subcategories).

---

## 14. OASFMapping & OASFSkillResult

**Module**: `grounded_agency/adapters/oasf.py`

### OASFMapping

**Decorators**: `@dataclass(frozen=True, slots=True)`

A resolved mapping from an OASF skill code to Grounded Agency capabilities. Immutable.

| Field | Type | Description |
|-------|------|-------------|
| `skill_code` | `str` | OASF skill code (e.g., `"109"`). |
| `skill_name` | `str` | Human-readable skill name. |
| `capabilities` | `tuple[str, ...]` | Grounded Agency capability IDs (immutable tuple). |
| `mapping_type` | `Literal["direct", "domain", "composition", "workflow"]` | How the mapping was derived. |
| `domain_hint` | `str \| None` | Domain parameter hint (e.g., `"text"`, `"risk"`). |
| `workflow` | `str \| None` | Associated workflow name, if any. |
| `notes` | `str \| None` | Additional notes about the mapping. |

### OASFSkillResult

**Decorators**: `@dataclass(frozen=True, slots=True)`

Result of translating an OASF skill invocation. Immutable.

| Field | Type | Description |
|-------|------|-------------|
| `mapping` | `OASFMapping` | The resolved mapping. |
| `capability_nodes` | `list[CapabilityNode]` | Resolved capability nodes from the registry. |
| `requires_checkpoint` | `bool` | Whether any mapped capability requires a checkpoint. |
| `max_risk` | `str` | Highest risk level among mapped capabilities (`"low"`, `"medium"`, `"high"`). |
| `evidence_anchors` | `list[dict[str, Any]]` | Evidence anchors (default: empty list). |

### UnknownSkillError

**Inherits**: `KeyError`

Raised when an OASF skill code has no mapping. Contains the `skill_code` attribute.

```python
try:
    result = adapter.translate("999")
except UnknownSkillError as e:
    print(e.skill_code)  # "999"
```

---

## 15. Hook Factory Functions

**Module**: `grounded_agency/hooks/evidence_collector.py` and `grounded_agency/hooks/skill_tracker.py`

### `create_evidence_collector(store, mapper=None) -> HookCallback`

Creates a `PostToolUse` hook that collects evidence anchors from every tool execution.

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `store` | `EvidenceStore` | *required* | Evidence store to add anchors to. |
| `mapper` | `ToolCapabilityMapper \| None` | `None` | Optional mapper to associate anchors with capability IDs. Creates a default mapper if `None`. |

**Returns**: `HookCallback` -- An async function with signature `(input_data: dict, tool_use_id: str | None, context: Any) -> dict[str, Any]`.

**Behavior**:

The returned hook:
1. Creates a `tool_output` anchor for every tool invocation
2. For file tools (`Read`, `Write`, `Edit`, `MultiEdit`): also creates a `file` anchor
3. For `Bash` tool: also creates a `command` anchor with exit code
4. Associates each anchor with its capability ID via the mapper
5. Never modifies execution (returns empty dict)
6. Fails silently on errors (logs warning)

---

### `create_skill_tracker(checkpoint_tracker) -> HookCallback`

Creates a `PostToolUse` hook that tracks Skill invocations and updates checkpoint state.

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `checkpoint_tracker` | `CheckpointTracker` | Tracker to update when checkpoint skills are invoked. |

**Returns**: `HookCallback` -- An async function with the same signature as above.

**Behavior**:

The returned hook:
1. Only processes `Skill` tool invocations (ignores all other tools)
2. When `skill == "checkpoint"`:
   - Extracts `scope` from tool input or response (default: `["*"]`)
   - Extracts `reason` from tool input or response (default: `"Checkpoint created via skill invocation"`)
   - Calls `checkpoint_tracker.create_checkpoint(scope, reason)`
3. When `skill == "rollback"`:
   - Calls `checkpoint_tracker.invalidate_all()`
4. Returns empty dict (passive observation)
5. Logs errors but does not fail

---

## 16. Type Aliases & Constants

### HookCallback

**Module**: `grounded_agency/__init__.py`

```python
HookCallback = Callable[
    [dict[str, Any], str | None, Any],
    Coroutine[Any, Any, dict[str, Any]],
]
```

Type alias for async hook callback functions used by the Claude Agent SDK integration. The three parameters are:

1. `input_data: dict[str, Any]` -- Contains `tool_name`, `tool_input`, `tool_response`
2. `tool_use_id: str | None` -- Unique identifier for this tool use
3. `context: Any` -- SDK hook context (`HookContext`)

Returns a `dict[str, Any]` (typically empty for passive hooks).

### Constants

**CheckpointTracker constants** (`grounded_agency/state/checkpoint_tracker.py`):

| Constant | Value | Description |
|----------|-------|-------------|
| `DEFAULT_EXPIRY_MINUTES` | `30` | Default checkpoint expiry in minutes. |
| `DEFAULT_MAX_HISTORY` | `100` | Maximum number of checkpoints kept in history. |

**EvidenceStore constants** (`grounded_agency/state/evidence_store.py`):

| Constant | Value | Description |
|----------|-------|-------------|
| `DEFAULT_MAX_ANCHORS` | `10000` | Maximum number of evidence anchors before FIFO eviction. |
| `_MAX_METADATA_SIZE_BYTES` | `1024` | Maximum serialized size of anchor metadata (1 KB). |
| `_MAX_METADATA_DEPTH` | `2` | Maximum nesting depth for metadata values. |

**Metadata validation** (`grounded_agency/state/evidence_store.py`):

| Symbol | Value | Description |
|--------|-------|-------------|
| `_VALID_KEY_PATTERN` | `re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")` | Regex for valid metadata keys. |

### Internal Helper Functions (evidence_store.py)

These are private but affect public behavior:

- `_validate_metadata_key(key: str) -> bool` -- Checks key matches `_VALID_KEY_PATTERN`.
- `_validate_metadata_depth(value: Any, current_depth: int = 0) -> bool` -- Checks depth does not exceed `_MAX_METADATA_DEPTH`.
- `_sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]` -- Full sanitization pipeline: key validation, depth checking, size enforcement.

---

## 17. CLI Tools Reference

The project ships five CLI validator tools under `tools/`. All tools require `pyyaml` and run from the repository root.

---

### 17.1 validate_workflows.py

**File**: `tools/validate_workflows.py`

Validates workflow definitions in `schemas/workflow_catalog.yaml` against the capability ontology. Performs structural validation, reference validation, type system checking, consumer-side type checking, and patch suggestion generation.

**Usage**:

```bash
python tools/validate_workflows.py
python tools/validate_workflows.py --emit-patch
```

**Flags**:

| Flag | Description |
|------|-------------|
| `--emit-patch` | Write a unified diff patch file (`tools/validator_patch.diff`) with suggested transform insertions for type mismatches. |

**Exit codes**:

| Code | Meaning |
|------|---------|
| `0` | All workflows pass validation. |
| `1` | One or more validation errors found. |

**Output files** (always written):

- `tools/validator_suggestions.json` -- Machine-readable errors and suggestions with patch plans.

**Output files** (with `--emit-patch`):

- `tools/validator_patch.diff` -- Unified diff of suggested workflow modifications.

**Validation checks**:

1. **Structural**: Capability exists in ontology; prerequisites satisfied; `mapping_ref` and `output_conforms_to` files exist.
2. **Reference**: `${store.path}` references resolve; external `inputs.*.ref` resolved.
3. **Type system**: Inferred types for untyped bindings; typed annotations validated against schema; ambiguous types flagged.
4. **Consumer type checking**: Binding types validated against consumer capability's `input_schema`.
5. **Patch suggestions**: Transform insertion suggestions with coercion registry lookup.

**Example output (pass)**:

```
VALIDATION PASS
Suggestions written to: /path/to/tools/validator_suggestions.json
```

**Example output (fail)**:

```
VALIDATION FAIL:
 - [anomaly_detection] step 2 'predict': missing required prereq 'ground' before it
 - Consumer input type mismatch in workflow 'anomaly_detection' step 3: ...

Suggestions written to: /path/to/tools/validator_suggestions.json
```

---

### 17.2 validate_ontology.py

**File**: `tools/validate_ontology.py`

Validates the capability ontology graph for structural integrity: orphan capabilities, edge reference validity, symmetric edge consistency, cycle detection, and optional duplicate edge checking.

**Usage**:

```bash
python tools/validate_ontology.py
python tools/validate_ontology.py --verbose
python tools/validate_ontology.py --check-duplicates
python tools/validate_ontology.py --ontology path/to/ontology.yaml
```

**Flags**:

| Flag | Description |
|------|-------------|
| `--verbose`, `-v` | Show detailed edge distribution per capability with incoming/outgoing counts. |
| `--check-duplicates` | Warn about multiple edge types between the same capability pair. |
| `--ontology PATH` | Override ontology file path. Default: `schemas/capability_ontology.yaml`. |

**Exit codes**:

| Code | Meaning |
|------|---------|
| `0` | Ontology graph is valid. |
| `1` | Validation errors found (orphans, invalid references, cycles). |

**Validation checks**:

1. **Edge references**: All `from` and `to` fields reference valid capability IDs.
2. **Orphan detection**: Capabilities with no incoming or outgoing edges.
3. **Symmetric edges**: `conflicts_with` and `alternative_to` edges have bidirectional counterparts.
4. **Cycle detection**: DFS cycle detection in `requires` and `precedes` edges.
5. **Duplicate edges** (optional): Multiple edge types between the same pair.

**Example output (pass)**:

```
Validating ontology: schemas/capability_ontology.yaml
============================================================
Total capabilities: 36
Total edges: 85

Graph statistics:
  - Capabilities with outgoing edges: 32/36
  - Capabilities with incoming edges: 34/36
  - Orphan capabilities: 0

VALIDATION PASSED
```

---

### 17.3 validate_profiles.py

**File**: `tools/validate_profiles.py`

Validates all domain profile YAML files in `schemas/profiles/` against the profile schema. Ensures consistency, correct value ranges, and valid enum values.

**Usage**:

```bash
python tools/validate_profiles.py
python tools/validate_profiles.py --verbose
```

**Flags**:

| Flag | Description |
|------|-------------|
| `--verbose`, `-v` | Show each profile being validated. |

**Exit codes**:

| Code | Meaning |
|------|---------|
| `0` | All profiles pass validation. |
| `1` | One or more validation errors found. |

**Validation checks**:

1. **Required fields**: `domain`, `version`, `trust_weights`, `risk_thresholds`, `checkpoint_policy`, `evidence_policy`.
2. **Version format**: Semantic versioning (`X.Y.Z`).
3. **Trust weights**: All values between 0.0 and 1.0.
4. **Risk thresholds**: `auto_approve` in `[none, low, medium, high]`; `require_review` in `[low, medium, high]`; `require_human` in `[low, medium, high, critical]`; `block_autonomous` is list of strings.
5. **Checkpoint policy**: Values in `[always, high_risk, medium_risk, never]`.
6. **Evidence policy**: `required_anchor_types` is list of strings; `minimum_confidence` between 0.0 and 1.0; `require_grounding` is list of strings.
7. **Domain sources**: `type` in `[api, sensor, database, human, document, system_log]`; `default_trust` between 0.0 and 1.0.
8. **Workflows**: Must be list of strings.

**Example output (pass)**:

```
PROFILE VALIDATION PASS: 4 profiles validated
```

---

### 17.4 validate_skill_refs.py

**File**: `tools/validate_skill_refs.py`

Validates that file path references in SKILL.md dependency sections resolve to existing files. Prevents phantom references to files that were never created or have been removed.

**Usage**:

```bash
python tools/validate_skill_refs.py
python tools/validate_skill_refs.py --verbose
```

**Flags**:

| Flag | Description |
|------|-------------|
| `--verbose`, `-v` | Show all checked references, including successful matches. |

**Exit codes**:

| Code | Meaning |
|------|---------|
| `0` | All references resolve to existing files. |
| `1` | One or more references point to missing files. |

**Validation scope**:

Only checks backtick-quoted file paths (matching extensions: `.yaml`, `.yml`, `.md`, `.py`, `.json`, `.sh`) in these structural sections:

- `Compatible schemas:`
- `References:`
- `Located at:`
- `Workflow references:`

**Resolution order**: Repo root first, then skill-local directory.

**Excluded**: URLs (`http://`, `https://`), `CLAUDE.md`, paths inside fenced code blocks.

**Example output (pass)**:

```
SKILL REFERENCE VALIDATION PASS: 36 skills validated
```

---

### 17.5 sync_skill_schemas.py

**File**: `tools/sync_skill_schemas.py`

Generates skill-local output schemas from the capability ontology and bundles transitive dependencies for workflow catalogs.

**Usage**:

```bash
python tools/sync_skill_schemas.py
python tools/sync_skill_schemas.py --dry-run
```

**Flags**:

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview what would be generated without writing any files. |

**Exit codes**:

| Code | Meaning |
|------|---------|
| `0` | Sync completed successfully. |
| `1` | Warnings or errors encountered (missing skill directories, missing transitive deps). |

**Operations performed**:

**Phase 1 -- Schema sync**:
- Reads `schemas/capability_ontology.yaml`
- For each capability node, writes `skills/<name>/schemas/output_schema.yaml`
- Generated files include a `DO NOT EDIT` header with regeneration instructions

**Phase 2 -- Workflow catalog dependency bundling**:
- For skills with `reference/workflow_catalog.yaml`, copies transitive dependencies:
  - `schemas/world_state_schema.yaml`
  - `schemas/event_schema.yaml`
  - `schemas/transforms/transform_mapping_rawlog_to_observation.yaml`
- Rewrites internal `schemas/` paths in bundled workflow catalogs to use co-located relative filenames

**Example output**:

```
SCHEMA SYNC: 36 schemas generated, 0 skipped
WORKFLOW CATALOG DEPS: 12 files bundled, 4 catalogs rewritten

SYNC COMPLETE
```

---

## Appendix: Module Dependency Graph

```
grounded_agency/
    __init__.py              <-- Package root, exports all public symbols
    adapter.py               <-- GroundedAgentAdapter, GroundedAgentConfig
    |
    +-- capabilities/
    |   __init__.py
    |   registry.py          <-- CapabilityRegistry, CapabilityNode, CapabilityEdge
    |   mapper.py            <-- ToolCapabilityMapper, ToolMapping
    |
    +-- state/
    |   __init__.py
    |   checkpoint_tracker.py <-- CheckpointTracker, Checkpoint
    |   evidence_store.py     <-- EvidenceStore, EvidenceAnchor
    |
    +-- hooks/
    |   __init__.py
    |   evidence_collector.py <-- create_evidence_collector()
    |   skill_tracker.py      <-- create_skill_tracker()
    |
    +-- adapters/
        __init__.py
        oasf.py              <-- OASFAdapter, OASFMapping, OASFSkillResult
```

**Dependency flow** (no circular dependencies):

- `adapter.py` depends on: `capabilities.registry`, `capabilities.mapper`, `state.checkpoint_tracker`, `state.evidence_store`, `hooks.evidence_collector`, `hooks.skill_tracker`
- `hooks.evidence_collector` depends on: `capabilities.mapper`, `state.evidence_store`
- `hooks.skill_tracker` depends on: `state.checkpoint_tracker`
- `adapters.oasf` depends on: `capabilities.registry`
- `state` modules have no internal cross-dependencies
- `capabilities` modules have no internal cross-dependencies

---

## Appendix: Quick Reference Table

| Class / Function | Method Count | Module |
|-----------------|-------------|--------|
| `GroundedAgentAdapter` | 8 methods + 2 properties | `adapter.py` |
| `GroundedAgentConfig` | 5 fields (dataclass) | `adapter.py` |
| `CapabilityRegistry` | 16 methods + 3 properties | `capabilities/registry.py` |
| `CapabilityNode` | 9 fields + 1 class method | `capabilities/registry.py` |
| `CapabilityEdge` | 3 fields | `capabilities/registry.py` |
| `ToolCapabilityMapper` | 5 public methods | `capabilities/mapper.py` |
| `ToolMapping` | 4 fields + `__str__` | `capabilities/mapper.py` |
| `CheckpointTracker` | 10 methods + 1 property | `state/checkpoint_tracker.py` |
| `Checkpoint` | 8 fields + 2 methods | `state/checkpoint_tracker.py` |
| `EvidenceStore` | 14 methods + `__len__`/`__iter__` | `state/evidence_store.py` |
| `EvidenceAnchor` | 4 fields + 4 class methods | `state/evidence_store.py` |
| `OASFAdapter` | 5 methods + 4 properties | `adapters/oasf.py` |
| `OASFMapping` | 7 fields (frozen dataclass) | `adapters/oasf.py` |
| `OASFSkillResult` | 5 fields (frozen dataclass) | `adapters/oasf.py` |
| `create_evidence_collector` | Factory function | `hooks/evidence_collector.py` |
| `create_skill_tracker` | Factory function | `hooks/skill_tracker.py` |
| CLI tools | 5 validators | `tools/*.py` |
