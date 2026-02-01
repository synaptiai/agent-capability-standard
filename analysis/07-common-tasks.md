# Common Tasks Reference

This guide covers the day-to-day operations you will perform when working with the Agent Capability Standard. Each section provides step-by-step instructions, concrete code examples, and troubleshooting advice.

---

## Table of Contents

1. [Adding a New Atomic Capability](#1-adding-a-new-atomic-capability)
2. [Creating a Workflow Pattern](#2-creating-a-workflow-pattern)
3. [Creating a Domain Profile](#3-creating-a-domain-profile)
4. [Using the Python SDK](#4-using-the-python-sdk)
5. [Running Validators with Output Interpretation](#5-running-validators-with-output-interpretation)
6. [Writing Skills (SKILL.md Format)](#6-writing-skills-skillmd-format)
7. [Running Benchmarks and Creating Scenarios](#7-running-benchmarks-and-creating-scenarios)
8. [Extending the Transform Registry](#8-extending-the-transform-registry)
9. [Debugging Validation Errors](#9-debugging-validation-errors)

---

## 1. Adding a New Atomic Capability

Adding a new atomic capability is a multi-step process that touches multiple files. Every step is mandatory. Skipping any step will cause validator failures or inconsistent documentation.

### Step 1: Update the Capability Ontology

Open `schemas/capability_ontology.yaml` and add a new node to the `nodes` array. Every node requires at minimum: `id`, `layer`, `description`, `risk`, `mutation`, and both `input_schema` and `output_schema`.

```yaml
# schemas/capability_ontology.yaml — append to the nodes array
- id: correlate
  layer: UNDERSTAND
  description: Find statistical or causal correlations between datasets
  risk: low
  mutation: false
  input_schema:
    type: object
    required:
    - dataset_a
    - dataset_b
    properties:
      dataset_a:
        type: any
        description: First dataset or variable
      dataset_b:
        type: any
        description: Second dataset or variable
      method:
        type: string
        description: Correlation method (pearson, spearman, etc.)
      threshold:
        type: number
        description: Minimum correlation threshold
  output_schema:
    type: object
    required:
    - correlation
    - evidence_anchors
    - confidence
    properties:
      correlation:
        type: number
        description: Correlation coefficient
      p_value:
        type: number
        description: Statistical significance
      method:
        type: string
      evidence_anchors:
        type: array
      confidence:
        type: number
        minimum: 0
        maximum: 1
```

For high-risk capabilities, add the safety flags:

```yaml
- id: my_high_risk_cap
  layer: EXECUTE
  risk: high
  mutation: true
  requires_checkpoint: true
  requires_approval: true
  # ... schemas ...
```

The risk and mutation flags follow these rules:

| Risk Level | `mutation` | `requires_checkpoint` | `requires_approval` |
|------------|-----------|----------------------|---------------------|
| low        | false     | false                | false               |
| medium     | false     | false                | true                |
| high       | true      | true                 | true                |

Also update the `meta.description` count:

```yaml
meta:
  description: 37 atomic capabilities derived from first principles  # was 36
```

### Step 2: Add Edges

In the `edges` array of the same file, add relationships connecting your new capability to existing ones. The seven edge types are:

| Edge Type | Meaning | Validator Enforcement |
|-----------|---------|----------------------|
| `requires` | Hard dependency -- must be satisfied before execution | Rejects workflows violating order |
| `soft_requires` | Recommended -- should be satisfied when available | Warns if missing |
| `enables` | Unlocks or makes possible another capability | Informational |
| `precedes` | Temporal ordering -- must complete before target | Enforces execution order |
| `conflicts_with` | Mutual exclusivity -- cannot coexist (symmetric) | Rejects workflows with both |
| `alternative_to` | Substitutability -- can replace (symmetric) | Used for capability selection |
| `specializes` | Inheritance -- more specific variant of parent | Inherits contracts |

```yaml
# schemas/capability_ontology.yaml — append to the edges array
- from: retrieve
  to: correlate
  type: enables
  rationale: Retrieved data provides input for correlation analysis
- from: measure
  to: correlate
  type: enables
  rationale: Measurements provide quantified data for correlation
- from: correlate
  to: ground
  type: soft_requires
  rationale: Correlation claims should be grounded in evidence
- from: correlate
  to: predict
  type: enables
  rationale: Correlations inform predictive models
```

Important: Symmetric edge types (`conflicts_with`, `alternative_to`) require edges in both directions. The ontology validator will warn about asymmetric pairs.

### Step 3: Update the Layer Capabilities Array

Still in `schemas/capability_ontology.yaml`, add the new capability to the appropriate layer:

```yaml
layers:
  UNDERSTAND:
    description: Making sense of information
    cognitive_mapping: 'BDI: Belief formation'
    capabilities:
    - detect
    - classify
    - measure
    - predict
    - compare
    - discover
    - correlate  # <-- add here
```

### Step 4: Create the Skill File

Create the skill file at `skills/<name>/SKILL.md` using the enhanced template. The filename must use kebab-case matching the capability `id`.

```bash
mkdir -p skills/correlate
cp templates/SKILL_TEMPLATE_ENHANCED.md skills/correlate/SKILL.md
```

Then edit `skills/correlate/SKILL.md` to fill in the template with capability-specific content. The YAML frontmatter must include:

```yaml
---
name: correlate
description: Find statistical or causal correlations between datasets. Use when comparing variables, detecting relationships, or measuring association strength.
argument-hint: "[dataset_a] [dataset_b] [method]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---
```

Refer to [Section 6](#6-writing-skills-skillmd-format) for full details on skill file structure.

### Step 5: Update Capability Count in All Files

This is the most commonly missed step. The count "36 atomic capabilities" appears in 11+ files. Use grep to find every occurrence:

```bash
grep -r "36 atomic capabilit" . --include="*.md" --include="*.json" --include="*.yaml"
grep -r "36 capabilities" . --include="*.md" --include="*.json"
```

Files that must be updated (replace 36 with 37):

| File | Section to Update |
|------|-------------------|
| `CLAUDE.md` | Architecture section, layer table |
| `README.md` | Multiple references throughout |
| `spec/WHITEPAPER.md` | Summary and derivation sections |
| `docs/GROUNDED_AGENCY.md` | Capability ontology section |
| `docs/FAQ.md` | Capability count references |
| `docs/GLOSSARY.md` | Layer descriptions |
| `docs/WORKFLOW_PATTERNS.md` | Pattern references |
| `docs/TUTORIAL.md` | Tutorial references |
| `docs/methodology/EXTENSION_GOVERNANCE.md` | Governance references |
| `skills/README.md` | Layer counts and totals |
| `.claude-plugin/plugin.json` | Description field |

### Step 6: Run Validators and Sync Schemas

Run the full validation suite and generate the skill-local schema:

```bash
# Validate YAML parse
python -c "import yaml; yaml.safe_load(open('schemas/capability_ontology.yaml'))"

# Validate workflows still pass
python tools/validate_workflows.py

# Validate domain profiles
python tools/validate_profiles.py

# Validate ontology graph (checks for orphans, cycles, symmetry)
python tools/validate_ontology.py

# Validate skill file references
python tools/validate_skill_refs.py

# Generate skill-local output schema
python tools/sync_skill_schemas.py
```

This last command creates `skills/correlate/schemas/output_schema.yaml` extracted from the ontology.

---

## 2. Creating a Workflow Pattern

Workflows compose atomic capabilities into multi-step patterns. They are defined in `schemas/workflow_catalog.yaml`.

### Workflow Structure

Every workflow has these top-level fields:

```yaml
my_workflow_name:
  goal: One-sentence description of what this workflow achieves.
  risk: low|medium|high           # Highest risk of any step
  description: |
    Multi-line description of when and how to use this workflow.
  success:
  - Success criterion 1
  - Success criterion 2
  inputs:
    input_param:
      type: object
      required: true
      description: Description of workflow input
      properties:
        field1: {type: string}
  steps:
  - capability: <capability_id>   # Must exist in ontology nodes
    purpose: What this step accomplishes
    # ... step details ...
```

### Defining Steps

Each step references a capability from the ontology and optionally specifies domain specialization, bindings, gates, and failure modes:

```yaml
steps:
- capability: observe
  purpose: Capture current system state for analysis.
  risk: low
  mutation: false
  requires_checkpoint: false
  requires_approval: false
  timeout: null
  retry: null
  store_as: observe_out        # Name used in subsequent ${} references
  failure_modes:
  - condition: Unable to observe relevant state
    action: request_more_context
    recovery: Request specific state aspects to monitor.
```

### Input Bindings with ${step_out.field} Syntax

Steps can consume outputs from previous steps using the `${store_as.field}` binding syntax:

```yaml
- capability: compare
  purpose: Compare current state against expected state.
  domain: assumption_validation
  store_as: comparison_out
  input_bindings:
    options:
    - ${world_state_out}             # Entire output of a previous step
    - ${plan.assumed_state}          # Field from workflow input
    criteria:
    - assumption_validity
    - state_divergence
```

You can add type annotations to bindings when the type is ambiguous:

```yaml
  input_bindings:
    constraints:
    - ${violations_out.matches: array<object>}    # Annotated type
    - ${critique_out.suggestions: array<string>}  # Annotated type
```

### Gates (Conditional Execution)

Gates allow steps to be skipped or the workflow to stop early based on conditions:

```yaml
- capability: detect
  store_as: violations_out
  gates:
  - when: ${comparison_out.confidence} > 0.9
    action: stop                    # stop | skip
    message: No significant divergence detected, plan remains valid.
```

Gate actions:
- `stop`: Halt the entire workflow (condition met, no further steps needed)
- `skip`: Skip this step and continue with the next one

### Failure Modes

Each step can declare failure modes with recovery strategies:

```yaml
  failure_modes:
  - condition: Unable to find viable plan
    action: stop                    # stop | pause_and_checkpoint | request_more_context
    recovery: Escalate to human with violation details.
  - condition: Unexpected side effects
    action: pause_and_checkpoint
    recovery: Checkpoint and require human approval.
```

### Parallel Groups

Steps that can execute concurrently are grouped with `parallel_group`:

```yaml
- capability: search
  parallel_group: data_gathering
  store_as: search_out

- capability: observe
  parallel_group: data_gathering
  store_as: observe_out

- capability: integrate
  # No parallel_group -- waits for all prior parallel steps
  store_as: merged_out
  input_bindings:
    sources:
    - ${search_out.results}
    - ${observe_out.observation}
```

### Complete Example

```yaml
assess_code_quality:
  goal: Evaluate code quality and generate improvement recommendations.
  risk: low
  description: |
    Analyzes a codebase for quality issues including complexity,
    duplication, naming, and test coverage.
  success:
  - Quality metrics computed for target code
  - Improvement recommendations generated with evidence
  steps:
  - capability: retrieve
    purpose: Load the target source files.
    risk: low
    mutation: false
    requires_checkpoint: false
    requires_approval: false
    store_as: source_out
    failure_modes:
    - condition: Files not found
      action: stop
      recovery: Verify file paths and retry.
  - capability: measure
    purpose: Compute quality metrics (complexity, duplication).
    domain: code_quality
    risk: low
    mutation: false
    requires_checkpoint: false
    requires_approval: false
    store_as: metrics_out
    input_bindings:
      target: ${source_out.data}
      metric: complexity
  - capability: critique
    purpose: Identify improvement opportunities from metrics.
    risk: low
    mutation: false
    requires_checkpoint: false
    requires_approval: false
    store_as: critique_out
    input_bindings:
      target: ${metrics_out}
      criteria:
      - maintainability
      - readability
  - capability: explain
    purpose: Generate human-readable quality report.
    risk: low
    mutation: false
    requires_checkpoint: false
    requires_approval: false
    store_as: report_out
    input_bindings:
      target: ${critique_out}
  inputs:
    target_path:
      type: string
      required: true
      description: Path to the code to analyze
```

### Validation

After adding a workflow, run the validator:

```bash
python tools/validate_workflows.py
```

To also generate suggested patches for type mismatches:

```bash
python tools/validate_workflows.py --emit-patch
```

---

## 3. Creating a Domain Profile

Domain profiles customize the ontology's behavior for a specific industry or use case by defining trust weights, risk thresholds, checkpoint policies, and evidence requirements.

### Step-by-Step

1. Create a new YAML file at `schemas/profiles/<domain>.yaml` (kebab-case name).
2. Include all required fields defined in `schemas/profiles/profile_schema.yaml`.
3. Run the profile validator.

### Required Fields

The profile schema (`schemas/profiles/profile_schema.yaml`) requires these fields:

| Field | Type | Description |
|-------|------|-------------|
| `domain` | string | Domain identifier, kebab-case |
| `version` | string | Semantic version (e.g., `"1.0.0"`) |
| `trust_weights` | object | Source-name-to-float map (0.0 to 1.0) |
| `risk_thresholds` | object | Automated action risk tolerance levels |
| `checkpoint_policy` | object | When to create checkpoints |
| `evidence_policy` | object | Evidence requirements for claims |

Optional fields: `description`, `domain_sources`, `workflows`.

### Complete Example: Financial Trading Profile

```yaml
# schemas/profiles/financial-trading.yaml

domain: financial-trading
version: "1.0.0"
description: |
  Profile for automated trading analysis and decision support.
  Emphasizes data accuracy, risk management, and audit compliance.

trust_weights:
  market_data_feed: 0.95       # Real-time market data
  historical_database: 0.92    # Historical price/volume data
  risk_engine: 0.90            # Internal risk calculation
  news_feed: 0.70              # Financial news sources
  social_sentiment: 0.45       # Social media sentiment
  analyst_report: 0.80         # Professional analyst reports
  regulatory_filing: 0.98      # SEC/regulatory filings

risk_thresholds:
  auto_approve: low            # Only low-risk actions auto-approved
  require_review: medium       # Medium risk needs human review
  require_human: high          # High risk needs human execution
  block_autonomous:
    - mutate                   # Never modify records autonomously
    - send                     # Never send orders autonomously
    - execute                  # Never execute trades autonomously

checkpoint_policy:
  before_trade_analysis: always
  before_risk_assessment: always
  before_recommendation: always
  before_data_export: high_risk

evidence_policy:
  required_anchor_types:
    - market_data_point
    - risk_calculation
    - audit_trail
    - timestamp
  minimum_confidence: 0.85     # High confidence for financial decisions
  require_grounding:
    - predict                  # Forecasts need evidence
    - measure                  # Risk measurements need evidence
    - compare                  # Comparisons need citations
    - classify                 # Classifications need criteria

domain_sources:
  - name: Market Data Feed
    type: api
    default_trust: 0.95
  - name: Historical Database
    type: database
    default_trust: 0.92
  - name: Risk Engine
    type: api
    default_trust: 0.90
  - name: Compliance Officer
    type: human
    default_trust: 0.96

workflows:
  - market_analysis
  - risk_assessment
  - portfolio_review
```

### Field Details

**trust_weights**: Each key is a source name, each value a float from 0.0 (no trust) to 1.0 (full trust). These affect how evidence from different sources is weighted during conflict resolution.

**risk_thresholds**:
- `auto_approve`: Maximum risk level that can proceed without human review. Values: `none`, `low`, `medium`, `high`.
- `require_review`: Minimum risk level requiring human review. Values: `low`, `medium`, `high`.
- `require_human`: Minimum risk level requiring human execution. Values: `low`, `medium`, `high`, `critical`.
- `block_autonomous`: List of capability IDs that must never run autonomously.

**checkpoint_policy**: Keys are arbitrary event names, values are one of: `always`, `high_risk`, `medium_risk`, `never`.

**evidence_policy**:
- `required_anchor_types`: Array of strings naming the types of evidence expected in this domain.
- `minimum_confidence`: Float from 0.0 to 1.0 -- the minimum confidence score for actions.
- `require_grounding`: Array of capability IDs that require explicit evidence grounding.

**domain_sources**: Array of objects, each with:
- `name`: Human-readable source name
- `type`: One of `api`, `sensor`, `database`, `human`, `document`, `system_log`
- `default_trust`: Float from 0.0 to 1.0

### Validation

```bash
python tools/validate_profiles.py
```

For verbose output showing each profile being checked:

```bash
python tools/validate_profiles.py --verbose
```

---

## 4. Using the Python SDK

The `grounded_agency/` package provides Python integration with the Claude Agent SDK.

### Installation

```bash
# From the repository root
pip install -e ".[sdk]"
```

### Basic Setup with GroundedAgentAdapter

```python
from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

# Create adapter with default settings (auto-detects ontology path)
config = GroundedAgentConfig(strict_mode=True)
adapter = GroundedAgentAdapter(config)

# Check ontology version
print(f"Ontology version: {adapter.ontology_version}")
print(f"Capability count: {adapter.capability_count}")
```

The `GroundedAgentConfig` accepts these parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ontology_path` | str | auto-detected | Path to `capability_ontology.yaml` |
| `strict_mode` | bool | `True` | Block mutations without checkpoint (False = warn only) |
| `audit_log_path` | str | `.claude/audit.log` | Path for audit log |
| `checkpoint_dir` | str | `.checkpoints` | Directory for checkpoint metadata |
| `expiry_minutes` | int | 30 | Default checkpoint expiry time |

### Creating and Consuming Checkpoints

```python
from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

adapter = GroundedAgentAdapter(GroundedAgentConfig(strict_mode=True))

# Create a checkpoint before mutations
checkpoint_id = adapter.create_checkpoint(
    scope=["src/*.py", "config/*.yaml"],  # File patterns to cover
    reason="Before refactoring database layer"
)
print(f"Created checkpoint: {checkpoint_id}")

# Check if a valid checkpoint exists
if adapter.has_valid_checkpoint():
    print("Ready for mutations")

# After successful mutation, consume the checkpoint
consumed_id = adapter.consume_checkpoint()
print(f"Consumed checkpoint: {consumed_id}")

# Checkpoint tracker provides detailed lifecycle management
tracker = adapter.checkpoint_tracker

# Check scope coverage
if tracker.has_checkpoint_for_scope("src/database.py"):
    print("Checkpoint covers database.py")

# View checkpoint history
history = tracker.get_history(limit=5)
for chk in history:
    print(f"  {chk.id}: {chk.reason} (consumed={chk.consumed})")

# Clean up expired checkpoints
cleared = tracker.clear_expired()
print(f"Cleared {cleared} expired checkpoints")
```

### Querying the Capability Registry

```python
from grounded_agency.capabilities.registry import CapabilityRegistry

registry = CapabilityRegistry("schemas/capability_ontology.yaml")

# Get a specific capability
mutate = registry.get_capability("mutate")
print(f"Risk: {mutate.risk}")                      # "high"
print(f"Requires checkpoint: {mutate.requires_checkpoint}")  # True
print(f"Layer: {mutate.layer}")                    # "EXECUTE"

# Get all high-risk capabilities
high_risk = registry.get_high_risk_capabilities()
for cap in high_risk:
    print(f"  {cap.id}: {cap.description}")

# Get capabilities by layer
verify_caps = registry.get_capabilities_in_layer("VERIFY")
for cap in verify_caps:
    print(f"  {cap.id}: risk={cap.risk}")

# Query edge relationships
edges = registry.get_edges("mutate")
for edge in edges:
    print(f"  {edge.from_cap} --{edge.edge_type}--> {edge.to_cap}")

# Get required prerequisites for a capability
required = registry.get_required_capabilities("mutate")
print(f"Mutate requires: {required}")  # ["checkpoint"]

# Find conflicting capabilities
conflicts = registry.get_conflicting_capabilities("mutate")

# Find alternative capabilities
alternatives = registry.get_alternatives("search")
```

### Mapping Tools to Capabilities

```python
from grounded_agency.capabilities.mapper import ToolCapabilityMapper

mapper = ToolCapabilityMapper()

# Map SDK tools to capability metadata
write_mapping = mapper.map_tool("Write", {"file_path": "/tmp/test.txt"})
print(f"Capability: {write_mapping.capability_id}")     # "mutate"
print(f"Risk: {write_mapping.risk}")                     # "high"
print(f"Requires checkpoint: {write_mapping.requires_checkpoint}")  # True

# Bash commands are classified by content analysis
read_cmd = mapper.map_tool("Bash", {"command": "ls -la /tmp"})
print(f"ls maps to: {read_cmd.capability_id}")  # "observe" (read-only)

write_cmd = mapper.map_tool("Bash", {"command": "rm -rf /tmp/test"})
print(f"rm maps to: {write_cmd.capability_id}")  # "mutate" (destructive)

# Convenience methods
print(mapper.is_high_risk("Edit", {}))           # True
print(mapper.requires_checkpoint("Read", {}))    # False
print(mapper.is_mutation("Write", {}))           # True
```

### Collecting Evidence

```python
from grounded_agency.state.evidence_store import EvidenceStore, EvidenceAnchor

store = EvidenceStore(max_anchors=1000)

# Add evidence from different sources
tool_anchor = EvidenceAnchor.from_tool_output(
    tool_name="Read",
    tool_use_id="abc123",
    tool_input={"path": "/src/main.py"}
)
store.add_anchor(tool_anchor, capability_id="retrieve")

file_anchor = EvidenceAnchor.from_file(
    file_path="src/config.yaml",
    file_hash="sha256:abc...",
    operation="read"
)
store.add_anchor(file_anchor)

mutation_anchor = EvidenceAnchor.from_mutation(
    target="src/database.py",
    operation="edit",
    checkpoint_id="chk_20260130_abc123"
)
store.add_anchor(mutation_anchor, capability_id="mutate")

# Query evidence
recent = store.get_recent(5)                   # List of ref strings
mutations = store.get_mutations()              # All mutation anchors
tool_outputs = store.get_tool_outputs()        # All tool output anchors
retrieve_evidence = store.get_for_capability("retrieve")

# Search evidence
read_anchors = store.search_by_ref_prefix("tool:Read")
py_anchors = store.search_by_metadata("path", "/src/main.py")

# Export for audit
evidence_list = store.to_list()  # List of dicts
```

### Using the OASF Adapter

The OASF (Open Agentic Schema Framework) adapter translates external skill codes to Grounded Agency capabilities:

```python
from grounded_agency.adapters.oasf import OASFAdapter

adapter = OASFAdapter("schemas/interop/oasf_mapping.yaml")

# Translate an OASF skill code
result = adapter.translate("109")  # Text Classification
print(f"Capabilities: {result.mapping.capabilities}")  # ("classify",)
print(f"Domain hint: {result.mapping.domain_hint}")     # "text"
print(f"Max risk: {result.max_risk}")
print(f"Requires checkpoint: {result.requires_checkpoint}")

# Get raw mapping without resolving nodes
mapping = adapter.get_mapping("801")
print(f"Skill: {mapping.skill_name}")
print(f"Type: {mapping.mapping_type}")  # "direct", "domain", "composition", etc.

# Reverse lookup: find OASF codes for a capability
codes = adapter.reverse_lookup("detect")
print(f"OASF codes mapping to 'detect': {codes}")

# List all mappings
all_mappings = adapter.list_all_mappings()
print(f"Total mappings: {adapter.total_mapping_count}")
print(f"OASF version: {adapter.oasf_version}")
```

### Wrapping SDK Options (Full Integration)

```python
from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

adapter = GroundedAgentAdapter(GroundedAgentConfig(strict_mode=True))

# Create checkpoint before mutations
adapter.create_checkpoint(["*.py"], "Before code changes")

# Wrap SDK options -- injects safety callbacks and hooks
# base_options is a ClaudeAgentOptions instance
options = adapter.wrap_options(base_options)

# The wrapped options include:
# - enable_file_checkpointing=True
# - can_use_tool callback (checkpoint enforcement)
# - PostToolUse hooks (evidence collection, skill tracking, mutation consumption)
# - Skill tool in allowed_tools
# - "project" in setting_sources
```

---

## 5. Running Validators with Output Interpretation

The project ships five validators. Each checks a different aspect of consistency.

### 5.1 Workflow Validator (`validate_workflows.py`)

**What it checks:**
- All step capabilities exist in the ontology
- Required prerequisites are satisfied before each step
- `${store_as.path}` binding references resolve to valid schema paths
- Type annotations on bindings match producer output schemas
- Consumer input schemas are compatible with binding types
- `mapping_ref` and `output_conforms_to` file paths exist

**How to run:**

```bash
python tools/validate_workflows.py
python tools/validate_workflows.py --emit-patch  # Also generate patch suggestions
```

**Successful output:**

```
VALIDATION PASS
Suggestions written to: /path/to/tools/validator_suggestions.json
```

**Failure output:**

```
VALIDATION FAIL:
 - [monitor_and_replan] step 3 'detect' missing required prereq 'search' before it
 - Bad reference ${missing_store.field}: Unknown reference store 'missing_store'
 - Type mismatch ${violations_out.matches: array<string>}: expected array<string> but schema has array<object>

Suggestions written to: /path/to/tools/validator_suggestions.json
Patch diff written to: /path/to/tools/validator_patch.diff
```

**Key output files:**
- `tools/validator_suggestions.json`: Machine-readable fix suggestions
- `tools/validator_patch.diff`: Unified diff with transform step insertions (when `--emit-patch` is used)

### 5.2 Profile Validator (`validate_profiles.py`)

**What it checks:**
- Required fields present (domain, version, trust_weights, risk_thresholds, checkpoint_policy, evidence_policy)
- `version` follows semantic versioning (`X.Y.Z`)
- Trust weight values are between 0.0 and 1.0
- Risk threshold enums match allowed values
- Checkpoint policy values match allowed enums (`always`, `high_risk`, `medium_risk`, `never`)
- Evidence policy structure and value types
- Domain source types match allowed enums (`api`, `sensor`, `database`, `human`, `document`, `system_log`)

**How to run:**

```bash
python tools/validate_profiles.py
python tools/validate_profiles.py --verbose
```

**Successful output:**

```
PROFILE VALIDATION PASS: 8 profiles validated
```

**Failure output:**

```
PROFILE VALIDATION FAIL:
  - [my-profile] Missing required field: 'evidence_policy'
  - [my-profile] trust_weights.sensor_data: value 1.5 is outside valid range [0.0, 1.0]
  - [my-profile] risk_thresholds.auto_approve: invalid value 'extreme', must be one of ['none', 'low', 'medium', 'high']
  - [my-profile] Invalid version format '1.0': expected semantic version (e.g., '1.0.0')

Validated 8 profiles with 4 errors
```

### 5.3 Ontology Graph Validator (`validate_ontology.py`)

**What it checks:**
- All edge references point to valid capability IDs
- No orphan capabilities (capabilities with zero edges)
- Symmetric edge types (`conflicts_with`, `alternative_to`) have bidirectional edges
- No cycles in hard dependency edges (`requires`, `precedes`)
- Optionally detects multiple edge types between the same capability pair

**How to run:**

```bash
python tools/validate_ontology.py
python tools/validate_ontology.py --verbose
python tools/validate_ontology.py --check-duplicates
```

**Successful output:**

```
Validating ontology: schemas/capability_ontology.yaml
============================================================
Total capabilities: 36
Total edges: 42

Graph statistics:
  - Capabilities with outgoing edges: 30/36
  - Capabilities with incoming edges: 28/36
  - Orphan capabilities: 0

VALIDATION PASSED
```

**Failure output:**

```
Errors (2):
  - Found 1 orphan capabilities (no edges): ['correlate']
  - Edge references unknown capability: nonexistent_cap

VALIDATION FAILED
```

**Verbose mode** shows per-capability edge counts:

```
Edge distribution:
  checkpoint: 0 incoming, 2 outgoing [OK]
  correlate: 0 incoming, 0 outgoing [ORPHAN]
  detect: 3 incoming, 2 outgoing [OK]
```

### 5.4 Skill Reference Validator (`validate_skill_refs.py`)

**What it checks:**
- File paths referenced in SKILL.md structured sections resolve to existing files
- Checks "Compatible schemas", "References", "Located at", and "Workflow references" sections
- Resolves paths relative to repo root and skill directory
- Skips URLs and code block contents

**How to run:**

```bash
python tools/validate_skill_refs.py
python tools/validate_skill_refs.py --verbose
```

**Successful output:**

```
SKILL REFERENCE VALIDATION PASS: 36 skills validated
```

**Failure output:**

```
SKILL REFERENCE VALIDATION FAIL:
  - [detect] line 42: reference `schemas/output_schema.yaml` in Compatible schemas does not resolve to an existing file

Validated 36 skills with 1 errors
```

### 5.5 Schema Sync Tool (`sync_skill_schemas.py`)

This is not strictly a validator but a generator. It extracts `output_schema` from the ontology and writes it to each skill's local schema directory.

**How to run:**

```bash
python tools/sync_skill_schemas.py
```

**What it produces:** For each capability with a skill, it creates `skills/<name>/schemas/output_schema.yaml` containing the output schema from the ontology.

---

## 6. Writing Skills (SKILL.md Format)

Skills are the implementation layer for capabilities. Each skill lives at `skills/<name>/SKILL.md`.

### YAML Frontmatter

```yaml
---
name: detect
description: Find patterns or occurrences in data. Use when searching for patterns, checking existence, or validating presence.
argument-hint: "[data] [pattern] [threshold]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Capability ID, kebab-case, matches directory name |
| `description` | Yes | Must include trigger keywords for skill discovery |
| `argument-hint` | No | Hint shown to users for invocation syntax |
| `disable-model-invocation` | No | Whether the model can invoke this skill |
| `user-invocable` | No | Whether users can invoke this skill directly |
| `allowed-tools` | Yes | Comma-separated list of Claude Code tools this skill may use |
| `context` | No | Execution context (`fork` for isolation) |
| `agent` | Yes | Agent type: `explore` (read-only) or `general-purpose` (write access) |

Agent selection rules:

| Risk Level | Agent Type | Reason |
|------------|------------|--------|
| low | `explore` | Read-only, safer |
| medium | `explore` | Default to safer unless mutation needed |
| high | `general-purpose` | Needs Edit, Bash, Git access |
| mutation=true | `general-purpose` | Requires write access |

### Required Sections

**Intent**: What the capability does and when to use it.

```markdown
## Intent

Detect whether specific patterns or entities exist within the provided data,
returning match locations with evidence anchors.

**Success criteria:**
- All matching patterns identified with locations
- Confidence score reflects evidence quality
- At least one evidence anchor per match
```

**Inputs**: Typed input contract.

```markdown
## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `data` | Yes | any | Data to analyze for patterns |
| `pattern` | Yes | string\|object | Pattern specification to detect |
| `domain` | No | string | Domain specialization (e.g., "anomaly", "entity") |
| `threshold` | No | number | Detection sensitivity threshold (0.0-1.0) |
```

**Procedure**: Numbered, capability-specific steps (never generic boilerplate).

```markdown
## Procedure

1) **Identify search scope**: Determine which data segments to scan based on pattern type
   - For file patterns: identify relevant file types and directories
   - For text patterns: tokenize input appropriately

2) **Apply pattern matching**: Execute detection using the specified pattern
   - Use exact match first, then fuzzy if no exact results
   - Track match locations precisely (file:line or index)

3) **Ground claims**: Attach evidence anchors to all detections
   - Format: `file:line`, `url`, or `tool:<tool_name>:<output_ref>`

4) **Assess confidence**: Rate 0.0-1.0 based on match specificity and count
   - 1.0: Exact match found
   - 0.7-0.9: Fuzzy match with high similarity
   - <0.5: Weak or ambiguous matches

5) **Format output**: Structure results according to the output contract
```

**Output Contract**: Concrete YAML schema.

```markdown
## Output Contract

Return a structured object:

```yaml
detected: boolean           # Whether pattern was found
matches:                    # Array of match details
  - location: string        # Where the match was found
    content: string         # Matched content
    score: number           # Match quality (0.0-1.0)
confidence: 0..1            # Overall confidence score
evidence_anchors: ["file:line", "tool:Grep:id123"]
assumptions: []             # Explicit assumptions made
```
```

**Safety Constraints**: Inherited from ontology.

```markdown
## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not access paths outside the workspace
- Stop and request clarification if confidence < 0.3
```

**Composition Patterns**: How this skill relates to others.

```markdown
## Composition Patterns

**Commonly follows:**
- `retrieve` - Detection operates on retrieved data
- `search` - Broad search narrows to specific detection

**Commonly precedes:**
- `classify` - Detected items are classified
- `attribute` - Detections inform causal analysis
```

### Domain Parameterization

Instead of creating separate skills for domain variants, use the `domain` input parameter:

```markdown
## Procedure

1) **Check domain specialization**: If `domain` is provided, adapt detection strategy:
   - `domain: anomaly` -- Look for statistical outliers and unusual patterns
   - `domain: entity` -- Find named entities (people, organizations, locations)
   - `domain: vulnerability` -- Scan for security vulnerability patterns
   - (no domain) -- General pattern detection
```

### Evidence Grounding Requirements

Every non-trivial assertion in skill output must have an evidence anchor:

- `file:path:line` -- Reference to a specific file and line number
- `url:https://...` -- External URL reference
- `tool:<tool_name>:<output_ref>` -- Tool execution output reference
- `command:<id>` -- Command execution reference

---

## 7. Running Benchmarks and Creating Scenarios

The conformance test suite validates the workflow validator itself by running it against known-good and known-bad fixture files.

### Conformance Test Fixtures

Test fixtures live in `tests/` and follow the naming convention `<name>.workflow_catalog.yaml`. Each fixture is a complete workflow catalog file designed to test a specific validation scenario.

Current fixtures:

| Fixture | Expected Result | What It Tests |
|---------|----------------|---------------|
| `pass_reference.workflow_catalog.yaml` | PASS | Valid workflows with correct bindings |
| `fail_unknown_capability.workflow_catalog.yaml` | FAIL | References to nonexistent capabilities |
| `fail_bad_binding_path.workflow_catalog.yaml` | FAIL | Invalid `${store.path}` references |
| `fail_ambiguous_untyped.workflow_catalog.yaml` | FAIL | Ambiguous types without annotations |
| `fail_consumer_contract_mismatch.workflow_catalog.yaml` | FAIL | Type mismatch at consumer input |

### EXPECTATIONS.json Format

The `tests/EXPECTATIONS.json` file declares expected outcomes for each fixture:

```json
{
  "pass_reference": {
    "should_pass": true
  },
  "fail_unknown_capability": {
    "should_pass": false
  },
  "fail_consumer_contract_mismatch": {
    "should_pass": false,
    "should_emit_suggestions": true
  }
}
```

Fields:
- `should_pass` (required): Whether the validator should return exit code 0
- `should_emit_suggestions` (optional): Whether the validator should produce fix suggestions

### Running the Conformance Suite

```bash
python scripts/run_conformance.py
```

**How it works:**
1. For each entry in `EXPECTATIONS.json`, locates `tests/<name>.workflow_catalog.yaml`
2. Temporarily swaps `schemas/workflow_catalog.yaml` with the fixture content
3. Runs `tools/validate_workflows.py --emit-patch` against the fixture
4. Compares exit code against `should_pass`
5. Restores the original `workflow_catalog.yaml`
6. Writes `conformance_results.json` to the repo root

**Successful output:**

```
PASS: pass_reference
PASS: fail_unknown_capability
PASS: fail_bad_binding_path
PASS: fail_ambiguous_untyped
PASS: fail_consumer_contract_mismatch

Conformance PASSED
```

**Failure output:**

```
PASS: pass_reference
FAIL: fail_unknown_capability expected should_pass=False got ok=True
PASS: fail_bad_binding_path

Conformance FAILED (1 failures)
```

### Creating New Fixtures

To create a new conformance test:

1. Create the fixture workflow file:

```bash
# Name must be <name>.workflow_catalog.yaml
touch tests/fail_cycle_dependency.workflow_catalog.yaml
```

2. Write a minimal workflow that exercises the scenario:

```yaml
# tests/fail_cycle_dependency.workflow_catalog.yaml
cyclic_workflow:
  goal: Test that cyclic dependencies are caught.
  risk: low
  steps:
  - capability: verify
    purpose: Verify something.
    store_as: verify_out
    # verify requires mutate, but mutate hasn't occurred yet
  - capability: mutate
    purpose: Mutate something.
    store_as: mutate_out
    input_bindings:
      target: ${verify_out.result}
```

3. Add the expectation to `tests/EXPECTATIONS.json`:

```json
{
  "fail_cycle_dependency": {
    "should_pass": false
  }
}
```

4. Run the conformance suite to verify:

```bash
python scripts/run_conformance.py
```

---

## 8. Extending the Transform Registry

The transform coercion registry provides automatic type coercion suggestions when the workflow validator detects type mismatches between step outputs and consumer inputs.

### Registry Structure

The registry lives at `schemas/transforms/transform_coercion_registry.yaml`:

```yaml
registry:
  name: transform_coercion_registry
  version: 1.0.0
  description: Canonical coercion mappings for type mismatches
  principles:
  - Never drop raw payload
  - Always emit evidence_anchors if inference occurs
  - Prefer deterministic transformations
  - If lossy, record transformation_loss explicitly

coercions:
- from: string
  to: number
  mapping_ref: docs/schemas/transform_mapping_coerce_string_to_number.yaml
- from: number
  to: string
  mapping_ref: docs/schemas/transform_mapping_coerce_number_to_string.yaml
- from: object
  to: string
  mapping_ref: docs/schemas/transform_mapping_stringify_object.yaml
- from: array<object>
  to: array<string>
  mapping_ref: docs/schemas/transform_mapping_project_array_object_to_array_string.yaml
- from: array<any>
  to: array<object>
  mapping_ref: docs/schemas/transform_mapping_wrap_any_to_object.yaml
```

### Creating a New Transform Mapping

Each coercion entry points to a transform mapping file. To add a new coercion:

1. **Create the mapping YAML** at `schemas/transforms/transform_mapping_<name>.yaml`:

```yaml
# schemas/transforms/transform_mapping_coerce_boolean_to_string.yaml
mapping_id: coerce_boolean_to_string
version: 1.0.0
determinism_contract:
  pure: true                          # No side effects
  drop_raw_payload: false             # Preserves original data
  anchors_required_on_inference: true  # Must produce evidence anchors
rules:
- id: r1_boolean_to_string
  description: Convert boolean value to string representation ("true"/"false").
  input: raw.value
  output: canonical.value_string
  strategy: to_string
- id: r2_null_handling
  description: If input is null, output empty string with warning anchor.
  input: raw.value
  output: canonical.value_string
  strategy: null_to_empty
```

Key fields in the determinism contract:
- `pure`: Whether the transform is a pure function (no side effects)
- `drop_raw_payload`: Whether the original data is discarded (should be `false`)
- `anchors_required_on_inference`: Whether evidence anchors are emitted for inferred values

2. **Register in the coercion registry**:

Add an entry to `schemas/transforms/transform_coercion_registry.yaml`:

```yaml
coercions:
# ... existing entries ...
- from: boolean
  to: string
  mapping_ref: docs/schemas/transform_mapping_coerce_boolean_to_string.yaml
```

3. **How the workflow validator uses coercions**:

When `validate_workflows.py` detects a consumer input type mismatch, it:

1. Extracts the `from_type` (actual) and `to_type` (expected)
2. Looks up the `(from_type, to_type)` pair in the coercion registry
3. If a mapping exists, suggests inserting a `transform` step before the consumer
4. Writes the suggestion to `tools/validator_suggestions.json`
5. With `--emit-patch`, generates a unified diff adding the transform step

Example suggestion from `validator_suggestions.json`:

```json
{
  "kind": "consumer_input_type_mismatch",
  "workflow": "monitor_and_replan",
  "step_index": 5,
  "capability": "plan",
  "input_key": "constraints",
  "binding_ref": "violations_out.matches",
  "from_type": "array<object>",
  "to_type": "array<string>",
  "suggested_mapping_ref": "docs/schemas/transform_mapping_project_array_object_to_array_string.yaml",
  "patch": {
    "action": "insert_transform_before_step",
    "insert_at_step_index": 5,
    "new_step": {
      "capability": "transform",
      "purpose": "Coerce constraints to array<string> for consumer input contract",
      "mapping_ref": "docs/schemas/transform_mapping_project_array_object_to_array_string.yaml",
      "input_bindings": {"source": "${violations_out.matches}"},
      "store_as": "coerce_monitor_and_replan_5_constraints"
    }
  }
}
```

---

## 9. Debugging Validation Errors

This section covers the most common error patterns you will encounter and how to resolve them.

### "Unknown capability referenced"

**Error message:**
```
[workflow_name] step N: unknown capability 'nonexistent_cap'
```

**Cause:** A workflow step references a capability ID that does not exist in `schemas/capability_ontology.yaml`.

**Fix:**
1. Check spelling of the capability ID against the `nodes` array in the ontology.
2. If the capability is new, follow the [Adding a New Atomic Capability](#1-adding-a-new-atomic-capability) procedure.
3. If the capability was renamed, update all references in the workflow catalog.

```bash
# Find the correct capability name
grep "^- id:" schemas/capability_ontology.yaml
```

### "Binding path not found" / "Bad reference"

**Error message:**
```
Bad reference ${store_name.field}: path field not in schema for store_name
```

**Cause:** A `${store_as.field}` binding references a field path that does not exist in the producer capability's output schema.

**Fix:**
1. Check the `store_as` name matches a previous step's `store_as` value.
2. Check the field path exists in the producer capability's `output_schema`:

```bash
# Find the output schema for a capability
grep -A 30 "^- id: observe" schemas/capability_ontology.yaml | grep -A 20 "output_schema"
```

3. If accessing a nested field, verify each path segment exists in the schema hierarchy.

### "Type mismatch"

**Error message:**
```
Type mismatch ${ref: expected_type}: expected array<string> but schema has array<object>
```

**Cause:** An explicit type annotation on a binding does not match the inferred type from the producer's output schema.

**Fix options:**
1. **Correct the annotation**: Update the type annotation to match the actual schema type.
2. **Add a transform step**: Insert a `transform` capability step between the producer and consumer to coerce the type.
3. **Use the coercion registry**: Check if `schemas/transforms/transform_coercion_registry.yaml` has a mapping for this type pair. If not, create one following [Section 8](#8-extending-the-transform-registry).
4. **Run with --emit-patch**: The validator can suggest transform insertions automatically:

```bash
python tools/validate_workflows.py --emit-patch
# Review tools/validator_suggestions.json for fix details
```

### "Ambiguous type" / "Ambiguous type for ${ref}"

**Error message:**
```
Ambiguous type for ${ref}: inferred unknown is ambiguous/unknown. Add a typed annotation.
```

**Cause:** The validator cannot determine the type of a binding because the producer's output schema is too loose (e.g., `type: any`, `type: object` without properties).

**Fix:** Add an explicit type annotation to the binding:

```yaml
# Before (ambiguous)
input_bindings:
  data: ${previous_out.result}

# After (annotated)
input_bindings:
  data: ${previous_out.result: array<object>}
```

### "Consumer input type mismatch"

**Error message:**
```
Consumer input type mismatch in workflow 'name' step N (capability): input 'key' expects string but got number from ${ref}
```

**Cause:** The inferred type of a binding does not match the consumer capability's `input_schema` for that parameter.

**Fix:**
1. Insert a `transform` step between the producer and consumer:

```yaml
# Insert before the consumer step
- capability: transform
  purpose: Coerce value to expected type
  mapping_ref: docs/schemas/transform_mapping_coerce_number_to_string.yaml
  store_as: coerced_value
  input_bindings:
    source: ${producer_out.value}

# Update consumer binding
- capability: consumer_cap
  input_bindings:
    target: ${coerced_value.transformed: string}
```

2. Or fix the producer's output schema if the type was incorrectly declared.

### "Orphan capability"

**Error message (from validate_ontology.py):**
```
Found 1 orphan capabilities (no edges): ['my_new_cap']
```

**Cause:** A capability in the ontology has no edges connecting it to any other capability.

**Fix:** Add at least one edge in the `edges` array of `schemas/capability_ontology.yaml`:

```yaml
edges:
- from: some_existing_cap
  to: my_new_cap
  type: enables
  rationale: Description of relationship
```

### "Profile validation failed"

Common profile validation errors and their fixes:

| Error | Cause | Fix |
|-------|-------|-----|
| `Missing required field: 'X'` | Required field not in profile YAML | Add the field |
| `value X is outside valid range [0.0, 1.0]` | Trust weight or confidence out of range | Set value between 0.0 and 1.0 |
| `invalid value 'X', must be one of [...]` | Invalid enum value | Use one of the listed values |
| `Invalid version format` | Version not in `X.Y.Z` format | Use semantic version string |
| `expected number, got string` | Wrong type for a numeric field | Remove quotes from numeric values |
| `domain_sources[N].type: invalid value` | Invalid source type | Use: `api`, `sensor`, `database`, `human`, `document`, or `system_log` |

### "Missing required prereq"

**Error message:**
```
[workflow_name] step N 'capability' missing required prereq 'other_cap' before it
```

**Cause:** The ontology defines a `requires` edge from `other_cap` to `capability`, but `other_cap` does not appear earlier in the workflow.

**Fix:** Either add the prerequisite capability as an earlier step in the workflow, or verify the edge is correct in the ontology. `requires` edges are hard dependencies -- the validator will reject workflows that violate them.

### "Asymmetric edge warning"

**Warning message (from validate_ontology.py):**
```
Asymmetric 'conflicts_with' edge: cap_a -> cap_b (missing reverse: cap_b -> cap_a)
```

**Cause:** Symmetric edge types (`conflicts_with`, `alternative_to`) require edges in both directions.

**Fix:** Add the reverse edge:

```yaml
edges:
- from: cap_a
  to: cap_b
  type: conflicts_with
- from: cap_b          # Add this reverse edge
  to: cap_a
  type: conflicts_with
```

### "YAML parse error"

**Error message:**
```
[profile_name] YAML parse error: ...
```

**Cause:** Malformed YAML syntax (incorrect indentation, missing colons, unclosed quotes).

**Fix:** Validate YAML syntax separately:

```bash
python -c "import yaml; yaml.safe_load(open('schemas/profiles/my-profile.yaml'))"
```

Common YAML pitfalls:
- Strings containing colons must be quoted: `description: "Note: this needs quotes"`
- Version numbers must be quoted: `version: "1.0.0"` (not `version: 1.0.0` which becomes a float)
- Multiline strings use `|` or `>` block scalars
- Indentation must be consistent (spaces only, no tabs)

---

## Quick Reference: Validator Commands

| Validator | Command | Checks |
|-----------|---------|--------|
| Workflows | `python tools/validate_workflows.py` | Bindings, types, prereqs, file refs |
| Profiles | `python tools/validate_profiles.py` | Schema conformance, value ranges |
| Ontology | `python tools/validate_ontology.py` | Orphans, cycles, symmetry |
| Skill Refs | `python tools/validate_skill_refs.py` | Phantom file paths in SKILL.md |
| Schema Sync | `python tools/sync_skill_schemas.py` | Generates skill-local schemas |
| Conformance | `python scripts/run_conformance.py` | Runs validator against test fixtures |

Run the full validation suite in sequence:

```bash
python -c "import yaml; yaml.safe_load(open('schemas/capability_ontology.yaml'))" && \
python tools/validate_ontology.py && \
python tools/validate_workflows.py && \
python tools/validate_profiles.py && \
python tools/validate_skill_refs.py && \
python tools/sync_skill_schemas.py
```
