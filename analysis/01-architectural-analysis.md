# Architectural Analysis

**Project**: Agent Capability Standard (Grounded Agency)
**Version**: Plugin v1.0.5 / SDK v0.1.0
**Repository**: `synaptiai/agent-capability-standard`
**Generated**: 2026-01-30

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Six Subsystems](#2-six-subsystems)
3. [Cognitive Layer Architecture](#3-cognitive-layer-architecture)
4. [Safety Architecture](#4-safety-architecture)
5. [Technology Stack](#5-technology-stack)
6. [Design Patterns](#6-design-patterns)
7. [Extension Points](#7-extension-points)
8. [Dependency Map](#8-dependency-map)
9. [Key Metrics](#9-key-metrics)

---

## 1. Executive Summary

The Agent Capability Standard defines a **formal capability ontology** for AI agents, implementing 36 atomic capabilities across 9 cognitive layers with a Python SDK, safety hooks, domain profiles, and OASF interoperability. The architecture follows a **safety-by-construction** philosophy where mutation safety, evidence grounding, and auditability are enforced structurally — not by convention.

The system decomposes into **six subsystems**: Schema (formal definitions), SDK (Python integration), Hook (safety enforcement), Skill (Claude Code interface), Validation (design-time checking), and Interop (OASF compatibility). These subsystems communicate through typed YAML contracts and Python dataclasses with explicit I/O schemas.

**Key Differentiators**:
- Domain parameterization (36 atomic capabilities replace 99 domain-specific variants)
- Dual-layer checkpoint enforcement (shell hooks + Python SDK permission callbacks)
- Evidence-first design (every capability returns `evidence_anchors` + `confidence`)
- Fail-closed security model (unknown operations default to high-risk)
- Formal type system with inference and coercion for workflow composition

---

## 2. Six Subsystems

### 2.1 Schema Subsystem

**Purpose**: Formal definitions of capabilities, workflows, world state, entities, trust, and identity resolution.

**Core Files** (28 YAML files):

| File | Lines | Role |
|------|-------|------|
| `schemas/capability_ontology.yaml` | 1,912 | Master ontology: 36 nodes, 80+ edges, 7 edge types, I/O contracts |
| `schemas/workflow_catalog.yaml` | 1,909 | 12 reference workflows with step bindings, gates, failure modes |
| `schemas/world_state_schema.yaml` | 491 | World model: entities, relationships, state variables, observations, transitions |
| `schemas/entity_taxonomy.yaml` | 193 | 24 entity classes (11 digital + 13 physical), 57 subtypes, 10 core relations |
| `schemas/authority_trust_model.yaml` | 58 | 6 source authority ranks with temporal decay (half-life: 14 days) |
| `schemas/identity_resolution_policy.yaml` | 87 | 8-feature confidence scoring, merge/split thresholds |
| `schemas/event_schema.yaml` | 176 | Canonical event structure with anchors and uncertainty |
| `schemas/profiles/profile_schema.yaml` | 102 | Profile schema: trust weights, risk thresholds, checkpoint/evidence policies |
| `schemas/interop/oasf_mapping.yaml` | 730 | 15 OASF categories mapped to capability compositions |
| `schemas/transforms/*.yaml` | ~350 | 7 coercion mappings for type mismatch resolution |
| `schemas/profiles/*.yaml` | ~800 | 7 domain profiles (vision, audio, healthcare, manufacturing, etc.) |
| `schemas/workflows/*.yaml` | ~600 | Domain-specific workflow extensions |

**Architecture**:
- All schemas use YAML with explicit type annotations
- Cross-references use `schema_ref: "path#/fragment"` notation
- Capability I/O contracts define required/optional fields with types
- Workflow steps bind to capability outputs via `${step_name_out.field}` syntax
- Transform registry provides deterministic type coercions

**Key Design Decision**: Schemas are the **single source of truth**. The SDK loads them at runtime; validators check them at design time; skills reference them for contracts. This avoids schema drift between documentation and implementation.

---

### 2.2 SDK Subsystem

**Purpose**: Python package (`grounded_agency`, ~2,568 LOC) integrating safety patterns with Claude Agent SDK.

**Module Structure**:

```
grounded_agency/
├── __init__.py                    # Public API: 10 exports + HookCallback type alias
├── adapter.py                     # GroundedAgentAdapter: 7 methods, 2 properties (455 LOC)
├── capabilities/
│   ├── __init__.py                # Re-exports: ToolCapabilityMapper, ToolMapping, CapabilityRegistry
│   ├── registry.py                # CapabilityRegistry: 15+ query methods (352 LOC)
│   └── mapper.py                  # ToolCapabilityMapper: 3 regex sets, Bash classifier (352 LOC)
├── state/
│   ├── __init__.py                # Re-exports: CheckpointTracker, Checkpoint, EvidenceStore, EvidenceAnchor
│   ├── checkpoint_tracker.py      # CheckpointTracker: 12+ methods, Checkpoint dataclass
│   └── evidence_store.py          # EvidenceStore: 14+ methods, EvidenceAnchor with 4 class factories
├── adapters/
│   ├── __init__.py                # Re-exports: OASFAdapter, OASFMapping, OASFSkillResult, UnknownSkillError
│   └── oasf.py                    # OASFAdapter: 6+ methods, bidirectional mapping
├── hooks/
│   ├── __init__.py                # Re-exports: create_evidence_collector, create_skill_tracker
│   ├── evidence_collector.py      # PostToolUse hook factory for evidence capture
│   └── skill_tracker.py           # PostToolUse hook factory for checkpoint skill tracking
└── py.typed                       # PEP 561 typed package marker
```

**Key Classes**:

| Class | Methods | Role |
|-------|---------|------|
| `GroundedAgentAdapter` | 7 public + 3 private | Main entry point: wraps SDK options with safety layer |
| `GroundedAgentConfig` | 5 fields | Configuration: ontology_path, strict_mode, audit_log_path, checkpoint_dir, expiry_minutes |
| `CapabilityRegistry` | 15+ query | Loads/queries capability ontology YAML with dual-indexed edge graph |
| `ToolCapabilityMapper` | 5 public | Maps SDK tools to capability metadata; classifies Bash commands |
| `ToolMapping` | 4 fields | Immutable result: capability_id, risk, mutation, requires_checkpoint |
| `CheckpointTracker` | 12+ methods | Checkpoint lifecycle: create, consume, validate, expire, prune |
| `Checkpoint` | 8 fields | State: id, scope, reason, timestamps, consumed flag, metadata |
| `EvidenceStore` | 14+ methods | Bounded FIFO collection with dual secondary indexes |
| `EvidenceAnchor` | 4 class factories | Factory methods: from_tool_output, from_file, from_command, from_mutation |
| `OASFAdapter` | 6+ methods | Bidirectional OASF skill-code-to-capability translation |
| `OASFMapping` | 7 fields | Frozen mapping: skill_code, capabilities, mapping_type, domain_hint |

**Integration Pattern**: The adapter uses `dataclasses.replace()` to cleanly merge safety hooks into existing SDK options without mutation, following a decorator pattern:

```python
adapter = GroundedAgentAdapter(GroundedAgentConfig(strict_mode=True))
options = adapter.wrap_options(base_options)  # Injects hooks, permissions, settings
```

---

### 2.3 Hook Subsystem

**Purpose**: Dual-layer safety enforcement — shell hooks for Claude Code CLI, Python hooks for SDK.

**Shell Layer** (`hooks/`):

| Hook | Trigger | Script | Purpose |
|------|---------|--------|---------|
| PreToolUse | Write\|Edit | `pretooluse_require_checkpoint.sh` | Blocks mutations without `.claude/checkpoint.ok` marker |
| PostToolUse | Skill | `posttooluse_log_tool.sh` | Appends timestamped entry to `.claude/audit.log` |

**Python Layer** (`grounded_agency/hooks/`):

| Factory | Type | Purpose |
|---------|------|---------|
| `create_evidence_collector(store, mapper)` | PostToolUse | Captures evidence anchors from all tool executions |
| `create_skill_tracker(tracker)` | PostToolUse | Tracks checkpoint/rollback skill invocations |
| `_make_permission_callback()` | CanUseTool | **Core safety gate**: denies mutations without valid checkpoint |
| `_make_mutation_consumer()` | PostToolUse | Auto-consumes checkpoints after successful mutations |

**Enforcement Chain** (for a mutation like Write):
1. Shell PreToolUse hook checks `.claude/checkpoint.ok` file exists
2. Python `can_use_tool` callback checks `CheckpointTracker.has_valid_checkpoint()`
3. If both pass: tool executes
4. Python PostToolUse evidence collector captures evidence
5. Python PostToolUse mutation consumer auto-consumes checkpoint
6. Shell PostToolUse audit hook logs the invocation

**Error Handling Philosophy**:
- Shell hooks: Exit 0 on tooling errors (non-fatal), exit 1 only on policy violations
- Python permission callback: **Fail-closed** — any exception denies access
- Python observational hooks: **Fail-safe** — silently swallow errors and log warnings

---

### 2.4 Skill Subsystem

**Purpose**: 41 SKILL.md files providing Claude Code with structured capability invocations.

**Breakdown**:
- 36 atomic skills (one per capability, organized by layer)
- 5 composed workflow skills (debug-workflow, capability-gap-analysis, digital-twin-bootstrap, digital-twin-sync-loop, perspective-validation)

**Skill Structure** (from `templates/SKILL_TEMPLATE_ENHANCED.md`):

```yaml
---
name: <capability-name>
description: <one-line description>
allowed-tools: [Read, Grep, Glob, ...]
agent: general-purpose | Explore | Plan | Bash
layer: PERCEIVE | UNDERSTAND | REASON | MODEL | SYNTHESIZE | EXECUTE | VERIFY | REMEMBER | COORDINATE
---
```

Followed by markdown sections: Intent, Success Criteria, Input Contract, Procedure (with evidence grounding steps), Output Contract, Safety Constraints, Examples.

**Key Design Decision**: Skills are the **user-facing API** of the ontology. Each skill file maps 1:1 to a capability node and inherits its I/O contract, risk level, and edge constraints from the ontology. This ensures the Claude Code interface stays synchronized with formal definitions.

---

### 2.5 Validation Subsystem

**Purpose**: Five Python validators for design-time checking of schemas, workflows, profiles, skills, and ontology graph.

| Tool | LOC | Stages | What It Validates |
|------|-----|--------|-------------------|
| `validate_workflows.py` | ~800 | 5 | Capability refs, bindings, type inference, consumer contracts, patch suggestions |
| `validate_ontology.py` | ~300 | 5 | Orphan nodes, symmetric edges, cycles, valid refs, duplicate edges |
| `validate_profiles.py` | ~400 | 5 | Required fields, trust weight ranges, enum values, semver format, source types |
| `validate_skill_refs.py` | ~250 | 4 | Path existence for schemas, references, locations, workflow refs |
| `sync_skill_schemas.py` | ~300 | 3 | Extracts output schemas from ontology, bundles transitive deps, syncs to skills |

**Type System** (in `validate_workflows.py`):
- Supports: `string`, `number`, `boolean`, `object`, `nullable<T>`, `array<T>`, `map<K,V>`
- Type inference: Resolves `${step_out.field}` bindings to producer capability's output schema
- Coercion integration: Suggests `transform_coercion_registry.yaml` entries for type mismatches
- Consumer-side checking: Validates binding types against consumer capability's input schema
- Patch generation: Emits `tools/validator_patch.diff` for auto-fixable issues

**Conformance Testing** (`scripts/run_conformance.py`):
- 5 fixture files: 1 passing, 4 failing (ambiguous types, bad bindings, contract mismatch, unknown capability)
- Temporarily swaps workflow catalog for fixture, runs validator, checks expectations
- Results output to `conformance_results.json`

---

### 2.6 Interop Subsystem

**Purpose**: Bidirectional mapping between OASF (Open Agent Skill Framework) v0.8.0 and Grounded Agency capabilities.

**Architecture**:

```
OASF Skill Code (e.g., "109")
        ↓
  OASFAdapter.translate()
        ↓
  OASFMapping (skill_code → capabilities tuple)
        ↓
  CapabilityNode[] (from CapabilityRegistry)
        ↓
  OASFSkillResult (nodes + requires_checkpoint + max_risk)
```

**Coverage**:
- 15 OASF categories mapped (NLP, Vision, Audio, Tabular, Analytical, RAG, Multimodal, Security, Data Engineering, Agent Orchestration, Evaluation, DevOps/MLOps, Governance, Tool Interaction, Advanced Reasoning)
- 4 mapping types: `direct`, `domain`, `composition`, `workflow`
- 6 GA capabilities with no OASF equivalent: `attribute`, `integrate`, `recall`, `receive`, `send`, `transition`
- Reverse lookup: capability_id → list of OASF skill codes

**Proposed Extensions**: `docs/proposals/OASF_SAFETY_EXTENSIONS.md` proposes adding checkpoint, evidence, and risk metadata to the OASF standard.

---

## 3. Cognitive Layer Architecture

The 36 capabilities are organized into 9 cognitive layers inspired by BDI (Belief-Desire-Intention) agent architectures and cognitive science:

| # | Layer | Purpose | Count | Capabilities | Risk Range |
|---|-------|---------|-------|--------------|------------|
| 1 | **PERCEIVE** | Information acquisition | 4 | retrieve, search, observe, receive | low |
| 2 | **UNDERSTAND** | Making sense of information | 6 | detect, classify, measure, predict, compare, discover | low |
| 3 | **REASON** | Planning and analysis | 4 | plan, decompose, critique, explain | low |
| 4 | **MODEL** | World representation | 5 | state, transition, attribute, ground, simulate | low |
| 5 | **SYNTHESIZE** | Content creation | 3 | generate, transform, integrate | low |
| 6 | **EXECUTE** | Changing the world | 3 | execute, mutate, send | medium-high |
| 7 | **VERIFY** | Correctness assurance | 5 | verify, checkpoint, rollback, constrain, audit | low-medium |
| 8 | **REMEMBER** | State persistence | 2 | persist, recall | low |
| 9 | **COORDINATE** | Multi-agent interaction | 4 | delegate, synchronize, invoke, inquire | low-medium |

**Information Flow**: Layers are not strictly sequential. The typical flow is PERCEIVE → UNDERSTAND → REASON → EXECUTE → VERIFY, but feedback loops (VERIFY → REASON, EXECUTE → PERCEIVE) enable reflection and self-correction. MODEL and REMEMBER provide cross-cutting state that any layer can read or update.

**Layer Derivation** (from `docs/methodology/FIRST_PRINCIPLES_REASSESSMENT.md`):
- PERCEIVE: Required for any agent that interacts with external world
- UNDERSTAND: Required to make sense of perceptual data
- REASON: Required for goal-directed behavior
- MODEL: Required for maintaining coherent world representation
- SYNTHESIZE: Required for producing outputs
- EXECUTE: Required for affecting external state
- VERIFY: Required for safety assurance
- REMEMBER: Required for learning and continuity
- COORDINATE: Required for multi-agent systems

**Domain Parameterization**: Instead of creating domain-specific capabilities (e.g., `detect-anomaly`, `detect-entity`), the 36-capability model uses a `domain` parameter. This keeps the ontology fixed while allowing domain-specific behavior:

```yaml
# Same capability, different domains
detect(domain: anomaly)    # Returns anomaly matches
detect(domain: entity)     # Returns entity matches
measure(domain: risk)      # Returns risk score
measure(domain: quality)   # Returns quality metrics
```

---

## 4. Safety Architecture

### 4.1 Three-Tier Risk Classification

| Risk | Capabilities | Enforcement |
|------|-------------|-------------|
| **High** | mutate, send | `requires_checkpoint: true`, `mutation: true`, dual-layer enforcement |
| **Medium** | execute, delegate, synchronize, invoke, rollback | `requires_approval: true`, permission callback check |
| **Low** | All 30 remaining | No special enforcement; evidence still collected |

### 4.2 Checkpoint-Apply-Verify-Recover (CAVR) Pattern

The core safety pattern for mutations:

```
1. CHECKPOINT  → Create checkpoint (scope, reason, 30-min expiry)
2. APPLY       → Execute mutation (file write, API call)
3. VERIFY      → Check mutation succeeded (tests, assertions)
4. RECOVER     → Rollback if verification fails
```

**Implementation**:
- `CheckpointTracker.create_checkpoint(scope, reason)` generates a 128-bit ID (`chk_YYYYMMDD_HHMMSS_<32hex>`)
- `CheckpointTracker.has_valid_checkpoint()` checks: exists AND not consumed AND not expired
- `Checkpoint.matches_scope(target)` validates target covered by scope patterns (supports `*` and fnmatch globs)
- `CheckpointTracker.consume_checkpoint()` marks consumed with timestamp, moves to history
- `CheckpointTracker.invalidate_all()` clears all checkpoints (for rollback)

### 4.3 Dual-Layer Enforcement

```
Layer 1: Shell Hooks (Claude Code CLI)
  └─ pretooluse_require_checkpoint.sh
     └─ Checks .claude/checkpoint.ok file exists
     └─ Blocks Write|Edit without marker

Layer 2: Python SDK (Permission Callback)
  └─ adapter._make_permission_callback()
     └─ Maps tool → capability via ToolCapabilityMapper
     └─ Checks requires_checkpoint flag
     └─ Queries CheckpointTracker.has_valid_checkpoint()
     └─ strict_mode=True → PermissionResultDeny
     └─ strict_mode=False → Warning + Allow
```

### 4.4 Evidence Grounding

Every capability returns:
- `evidence_anchors`: Array of source references (file:line, URL, tool-output-id)
- `confidence`: Float [0, 1] indicating certainty

The `EvidenceStore` collects anchors from all tool executions via PostToolUse hooks:
- `from_tool_output()`: Generic tool execution evidence
- `from_file()`: File read/write/edit evidence with optional hash
- `from_command()`: Bash command evidence with exit code
- `from_mutation()`: State change evidence with checkpoint reference

**Bounded Collection**: Deque with maxlen=10,000 provides FIFO eviction. Secondary indexes (`_by_kind`, `_by_capability`) are manually cleaned on eviction.

### 4.5 Metadata Sanitization

The `EvidenceStore` enforces strict metadata constraints to prevent injection:
- Key validation: alphanumeric + underscore only (regex: `^[a-zA-Z_][a-zA-Z0-9_]*$`)
- Depth limit: 2 levels maximum nesting
- Size limit: 1KB per anchor
- Fallback: Returns minimal safe metadata dict on serialization failure

### 4.6 Bash Command Classification

The `ToolCapabilityMapper._classify_bash_command()` method uses a priority-ordered security analysis:

1. **Shell injection** (highest priority): `$()`, backticks, `${...}`, `;`, `||`, `&&`, `eval`, `exec`, `source` → high-risk mutate
2. **Network send**: curl POST/PUT/PATCH/DELETE, wget POST, ssh, scp, rsync → high-risk send
3. **Destructive**: rm, mv, chmod, git push/reset, docker rm, kubectl delete → high-risk mutate
4. **Read-only allowlist**: 50+ commands (ls, cat, grep, git status, etc.) → low-risk observe
5. **Unknown** (default): → high-risk mutate (fail-closed)

---

## 5. Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Language** | Python | >=3.10 | `\|` union types, `slots=True` dataclasses, `match` statements |
| **Build** | hatchling | latest | PEP 517 build backend for `grounded-agency` package |
| **Schema** | YAML | 1.2 | All ontology, workflow, profile, and mapping definitions |
| **YAML Parser** | PyYAML | >=6.0 | Only runtime dependency; uses `yaml.safe_load()` exclusively |
| **Testing** | pytest | >=7.0 | Unit tests with async support |
| **Async Testing** | pytest-asyncio | >=0.21 | `auto` mode for async test functions |
| **Type Checking** | mypy | >=1.0 | Strict mode, Python 3.10+ target |
| **Linting** | ruff | >=0.1.0 | pycodestyle, pyflakes, isort, bugbear, comprehensions, pyupgrade |
| **SDK** | claude-agent-sdk | >=0.1.0 | Optional dependency (`pip install grounded-agency[sdk]`) |
| **Plugin** | Claude Code | CLI | Hooks, skills, audit logging |
| **Shell** | Bash | 4+ | Hook scripts with jq for JSON parsing |
| **SCM** | Git | 2+ | Version control, checkpoint integration |

**Dependency Minimalism**: The core package has exactly **one** runtime dependency (`pyyaml>=6.0`). The SDK integration is an optional extra. This keeps the attack surface minimal and installation lightweight.

---

## 6. Design Patterns

### 6.1 Lazy Loading

Both `CapabilityRegistry` and `OASFAdapter` defer YAML parsing until first property access:

```python
class CapabilityRegistry:
    def __init__(self, ontology_path):
        self._ontology = None  # Not loaded yet

    def _ensure_loaded(self):
        if self._ontology is None:
            self._load_ontology()  # Load on first access
```

**Rationale**: Import-time I/O is a code smell. Lazy loading means the SDK can be imported without disk access, and the ontology is only parsed when actually needed.

### 6.2 Factory Pattern

Multiple factory patterns for object creation:

| Factory | Creates | Context |
|---------|---------|---------|
| `EvidenceAnchor.from_tool_output()` | EvidenceAnchor | PostToolUse hook |
| `EvidenceAnchor.from_file()` | EvidenceAnchor | File operation evidence |
| `EvidenceAnchor.from_command()` | EvidenceAnchor | Bash command evidence |
| `EvidenceAnchor.from_mutation()` | EvidenceAnchor | State change evidence |
| `CapabilityNode.from_dict()` | CapabilityNode | YAML parsing |
| `create_evidence_collector()` | HookCallback | Hook registration |
| `create_skill_tracker()` | HookCallback | Hook registration |

### 6.3 Fail-Closed Security

The permission callback in `adapter.py` uses fail-closed semantics:

```python
async def check_permission(tool_name, input_data, context):
    try:
        mapping = mapper.map_tool(tool_name, input_data)
        if mapping.requires_checkpoint and not tracker.has_valid_checkpoint():
            return PermissionResultDeny(...)
        return PermissionResultAllow()
    except Exception:
        return PermissionResultDeny(...)  # DENY on any error
```

Similarly, unknown Bash commands default to high-risk mutate, not low-risk observe.

### 6.4 Bounded Collections with FIFO Eviction

`EvidenceStore` uses `collections.deque(maxlen=10000)` for automatic FIFO eviction:

```python
self._anchors = deque(maxlen=max_anchors)  # Auto-evicts oldest
self._by_kind = defaultdict(list)          # Secondary index
self._by_capability = defaultdict(list)    # Secondary index
```

Secondary indexes require manual cleanup via `_evict_oldest_from_indexes()` before new insertions when at capacity.

### 6.5 Dataclass with Slots

All dataclasses use `slots=True` for memory efficiency and `frozen=True` for immutability where appropriate:

```python
@dataclass(slots=True)           # Mutable (Checkpoint, CapabilityNode)
@dataclass(frozen=True, slots=True)  # Immutable (OASFMapping, OASFSkillResult)
```

### 6.6 Closure-Based Hook Factories

Hook functions capture state via closures rather than class instances:

```python
def create_evidence_collector(store, mapper):
    async def collect_evidence(input_data, tool_use_id, context):
        # Closes over `store` and `mapper`
        anchor = EvidenceAnchor.from_tool_output(...)
        store.add_anchor(anchor)
    return collect_evidence
```

**Rationale**: Simpler than class-based hooks; the async function signature matches the SDK's `HookCallback` type alias directly.

### 6.7 Dual Indexing

Both `CapabilityRegistry` and `EvidenceStore` maintain multiple indexes for O(1) lookups:

**CapabilityRegistry**:
- `_outgoing_edges[cap_id]` → list of edges FROM capability
- `_incoming_edges[cap_id]` → list of edges TO capability

**EvidenceStore**:
- `_by_kind[kind]` → list of anchors by evidence type
- `_by_capability[cap_id]` → list of anchors by capability

### 6.8 Graceful SDK Degradation

The adapter handles missing SDK imports gracefully:

```python
try:
    from claude_agent_sdk import HookMatcher
    return HookMatcher(hook_fn, matcher)
except ImportError:
    return {"hook": hook_fn, "matcher": matcher}  # Dict fallback
```

This allows the package to be used without the full SDK installed (e.g., for schema queries only).

---

## 7. Extension Points

### 7.1 Adding a New Capability

1. Add node to `schemas/capability_ontology.yaml` with I/O contracts
2. Add edges connecting to related capabilities
3. Create `skills/<name>/SKILL.md` from template
4. Update layer capabilities array
5. Update capability count in 10+ files
6. Run `python tools/sync_skill_schemas.py` to generate local schema
7. Run all 4 validators

### 7.2 Adding a Workflow Pattern

1. Add workflow to `schemas/workflow_catalog.yaml`
2. Define steps with capability references and input bindings
3. Add gates, failure modes, and recovery loops
4. Run `python tools/validate_workflows.py`

### 7.3 Adding a Domain Profile

1. Create `schemas/profiles/<domain>.yaml` following `profile_schema.yaml`
2. Define trust weights, risk thresholds, checkpoint policy, evidence policy
3. Optionally add domain-specific workflows
4. Run `python tools/validate_profiles.py`

### 7.4 Adding an OASF Mapping

1. Add category/subcategory to `schemas/interop/oasf_mapping.yaml`
2. Map to capability tuple with mapping type
3. Test via `OASFAdapter.translate(skill_code)`

### 7.5 Adding a Tool Mapping

1. Add entry to `_TOOL_MAPPINGS` dict in `mapper.py`
2. Specify capability_id, risk, mutation, requires_checkpoint
3. For Bash commands: update `_READ_ONLY_COMMANDS` or regex patterns

### 7.6 Adding a Transform Coercion

1. Create `schemas/transforms/transform_mapping_<name>.yaml`
2. Register in `schemas/transforms/transform_coercion_registry.yaml`
3. Workflow validator will suggest coercions for type mismatches

---

## 8. Dependency Map

### Internal Dependencies

```
capability_ontology.yaml
    ↑ loaded by
CapabilityRegistry ←── ToolCapabilityMapper (uses ontology for validation)
    ↑                       ↑
    │                       │
GroundedAgentAdapter ───────┘
    │
    ├── CheckpointTracker (manages checkpoint lifecycle)
    ├── EvidenceStore (collects evidence anchors)
    ├── create_evidence_collector() (PostToolUse hook factory)
    ├── create_skill_tracker() (PostToolUse hook factory)
    └── OASFAdapter (loads oasf_mapping.yaml + uses CapabilityRegistry)
```

### Schema Cross-References

```
capability_ontology.yaml ──→ workflow_catalog.yaml (capability nodes in steps)
                         ──→ profiles/*.yaml (capability IDs in block_autonomous)
                         ──→ interop/oasf_mapping.yaml (capability IDs in mappings)

workflow_catalog.yaml ──→ world_state_schema.yaml (world_state type refs)
                      ──→ event_schema.yaml (event type refs)
                      ──→ transforms/*.yaml (coercion refs)

world_state_schema.yaml ──→ entity_taxonomy.yaml (entity type refs)
                        ──→ authority_trust_model.yaml (source rankings)
                        ──→ identity_resolution_policy.yaml (alias resolution)

event_schema.yaml ──→ world_state_schema.yaml (observation event mapping)
```

### External Dependencies

```
grounded-agency (Python package)
    └── pyyaml>=6.0 (only runtime dependency)
    └── [optional] claude-agent-sdk>=0.1.0

Claude Code Plugin
    └── Claude Code CLI (hooks, skills)
    └── bash 4+ (hook scripts)
    └── jq (JSON parsing in audit hook)
```

---

## 9. Key Metrics

| Metric | Value |
|--------|-------|
| Atomic capabilities | 36 |
| Cognitive layers | 9 |
| Capability edges | 80+ |
| Edge types | 7 |
| Workflow patterns | 12 |
| Domain profiles | 7 |
| Skills (total) | 41 (36 atomic + 5 composed) |
| YAML schema files | 28 |
| Python SDK LOC | ~2,568 |
| Validator LOC | ~2,050 |
| Test LOC | ~1,400 |
| Runtime dependencies | 1 (pyyaml) |
| OASF categories mapped | 15 |
| Entity classes | 24 (11 digital + 13 physical) |
| Trust source ranks | 6 |
| Transform coercions | 7 |
| Conformance fixtures | 5 |
| Plugin version | 1.0.5 |
| SDK version | 0.1.0 |
| Python requirement | >=3.10 |

---

*Next: [02-system-diagrams-and-features.md](02-system-diagrams-and-features.md) for visual architecture diagrams and complete feature inventory.*
