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
| `requires` | Hard dependency -- source must run before the target | Rejects workflows where it does not (V102) |
| `soft_requires` | Recommended -- any one of the target's soft sources should run before it | Warns if none does (W601) |
| `enables` | Unlocks or makes possible another capability | Informational |
| `precedes` | Ordering only -- when both appear, source must run before target | Rejects a workflow where the target comes first (V102); does not require the source to be present |
| `conflicts_with` | Concurrency exclusion (symmetric) | Rejects the pair in the same `parallel_group` (F504); sequential use is allowed |
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

# Regenerate skill-local files (output schemas, vendored catalogs)
python tools/sync_skill_schemas.py
python tools/sync_skill_schemas.py --check   # what CI runs: exit 1 on drift
```

The sync creates `skills/correlate/schemas/output_schema.yaml` extracted from the ontology (and refreshes any other generated file the change affects, such as the vendored workflow catalogs).

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
    - "${violations_out.matches: array<object>}"    # Annotated type (quoted)
    - "${critique_out.suggestions: array<string>}"  # Annotated type (quoted)
```

A typed reference that is a whole list item must be quoted: unquoted, the `: ` inside it makes YAML read the item as a mapping, which the validator reports as W612 (`MANGLED_REFERENCE`).

Steps in the same `parallel_group` do not count as running before one another, so ordering edges (`requires`, `precedes`, `soft_requires`) between them are not satisfied by the group.

### Gates (Conditional Execution)

Gates let a step be skipped when it has nothing to do, or stop the run when it must not go on:

```yaml
- capability: critique
  store_as: critique_out
  gates:
  - when: ${violations_out} == null || ${violations_out.detected} == false
    action: skip                    # stop | rollback | skip | warn
    message: No assumption violation detected; the plan remains valid.
  - when: ${critique_out.issues} == []
    phase: after                    # before (default) | after
    action: warn
    message: No issues found.
- capability: mutate
  gates:
  - when: ${checkpoint_out.checkpoint_id} == null
    action: stop
    message: No checkpoint created. Do not mutate.
```

Gate actions:
- `stop`: The run must not go on: raises R403, which goes to the step's failure modes like any step error; with none that handles it, the run fails with R403. It is not a way to say "done": when a condition means there is nothing more to do, `skip` the steps that would act on it
- `rollback`: Roll back to the latest checkpoint (none: the run ends F503), then raise R403
- `skip`: Skip this step and continue with the next one (before-gates only); later references to its output read null and must be null-guarded
- `warn`: Record a trace warning and continue

Gate phase: `before` (default) gates run before the step and cannot read its own output (B202); `after` gates run after the step and may read it, but cannot `skip` (S303). Evaluation order is `condition` → before-gates → the step → after-gates.

### Failure Modes

Each step can declare failure modes. One fires when the step failed with a code in its `on_error`, or its `when` holds after the step; a failure mode with neither only documents the response:

```yaml
  failure_modes:
  - condition: The mutation failed or timed out
    on_error: [R401, R402]
    action: rollback                # stop | rollback | pause_and_checkpoint | request_more_context | escalate
    recovery: Roll back to the checkpoint; the run then ends with the step's error.
  - condition: State synchronization timeout
    on_error: R401
    action: pause_and_checkpoint
    recovery: Take a new checkpoint of the partial state; the run then ends with R401.
```

`rollback` rolls back to the latest checkpoint; `pause_and_checkpoint` takes a new checkpoint (it rolls nothing back); `stop` and `request_more_context` do nothing themselves. With prose `recovery` (no `goto_step` loop), the run then ends with the step's code (STANDARD v1.1.0 §5.12).

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

The project ships five main validators. Each checks a different aspect of consistency.

### 5.1 Workflow Validator (`validate_workflows.py`)

The checks run in the Rust core (`core/src/validate/`, built into `grounded_agency._core`); the script is a thin CLI, so the package must be installed (`pip install -e ".[dev]" -c constraints.txt`).

**What it checks:**
- All step capabilities exist in the ontology (V101)
- Edge semantics: `requires` and `precedes` order (V102), `soft_requires` any-of (W601), `conflicts_with` not in one `parallel_group` (F504)
- `${store_as.path}` binding references resolve to valid schema paths (unknown store: B202)
- Type annotations on bindings match producer output schemas (B203)
- Consumer input schemas are compatible with binding types
- Gate and condition expressions parse and type-check (V108, B206)
- Step safety flags do not weaken the ontology's (W602)
- `mapping_ref` and `output_conforms_to` file paths exist

**How to run:**

```bash
python tools/validate_workflows.py
python tools/validate_workflows.py --catalog path/to/catalog.yaml  # Validate another catalog
python tools/validate_workflows.py --strict      # Warnings count as errors
python tools/validate_workflows.py --emit-patch  # Also write the patch diff
```

**Successful output** (warnings, if any, are listed first and do not fail the run unless `--strict`):

```
WARNINGS:
 - [unplanned_execute] step 0 (execute): W601 'execute' should be preceded by 'constrain' (soft_requires)
VALIDATION PASS
Suggestions written to: /path/to/tools/validator_suggestions.json
```

**Failure output** (one line per error: `[workflow] step N (capability): CODE message — hint`, the hint only when there is one):

```
VALIDATION FAIL:
 - [classify_before_detect] step 0 (classify): V102 'classify' must come after 'detect' (precedes), but 'detect' first appears at step 1
 - [missing_store] step 0 (observe): B202 unknown reference store 'nonexistent_store' in ${nonexistent_store}
 - [type_mismatch_workflow] step 1 (measure): B203 type mismatch ${retrieve_out.evidence_anchors: number}: annotated number but schema has array<unknown>

Suggestions written to: /path/to/tools/validator_suggestions.json
Patch diff written to: /path/to/tools/validator_patch.diff
```

(The `Patch diff written to:` line appears only with `--emit-patch`.)

**Key output files:**
- `tools/validator_suggestions.json`: written on every run, pass or fail; keys `errors`, `warnings` (one-line strings), `structured_errors`, `structured_warnings` (diagnostic objects with `code`, `message`, `severity`, `location`) and `suggestions` (machine-usable fixes)
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

This is not strictly a validator but a generator. It keeps every skill-local file derived from a repository source in sync.

**How to run:**

```bash
python tools/sync_skill_schemas.py            # write what changed
python tools/sync_skill_schemas.py --dry-run  # list what would change
python tools/sync_skill_schemas.py --check    # exit 1 on drift (CI)
```

**What it produces:**
- For each capability with a skill, `skills/<name>/schemas/output_schema.yaml` containing the output schema from the ontology
- The 17 vendored `skills/<name>/reference/workflow_catalog.yaml` copies, regenerated from `schemas/workflow_catalog.yaml` with schema paths rewritten to co-located copies, plus those vendored schema copies (`world_state_schema.yaml`, `event_schema.yaml`, `transform_mapping_rawlog_to_observation.yaml`)

It also removes generated `output_schema.yaml` files the ontology no longer produces. CI runs it with `--check`, so commit the regenerated files together with the change to their source.

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

Test fixtures live in `tests/fixtures/` and follow the naming convention `<name>.workflow_catalog.yaml` (79 at the time of writing; count them with `ls tests/fixtures/*.workflow_catalog.yaml | wc -l`). Each fixture is a complete workflow catalog file designed to test a specific validation scenario. Names start with `pass_`, `fail_` or `patch_`.

Representative fixtures:

| Fixture | Expected Result | What It Tests |
|---------|----------------|---------------|
| `pass_reference.workflow_catalog.yaml` | PASS | Valid workflows with correct bindings |
| `pass_soft_requires_warn.workflow_catalog.yaml` | PASS, warning W601 | `soft_requires` unmet is a warning, not an error |
| `pass_safety_flag_downgrade.workflow_catalog.yaml` | PASS, warning W602 | A weaker step safety flag is ignored |
| `fail_unknown_capability.workflow_catalog.yaml` | FAIL (V101) | References to nonexistent capabilities |
| `fail_bad_binding_path.workflow_catalog.yaml` | FAIL (B201) | Invalid `${store.path}` references |
| `fail_missing_store_ref.workflow_catalog.yaml` | FAIL (B202) | Reference to an unknown store |
| `fail_precedes_order.workflow_catalog.yaml` | FAIL (V102) | `precedes` target placed before its source |
| `fail_conflicts_parallel.workflow_catalog.yaml` | FAIL (F504) | Conflicting capabilities in one `parallel_group` |
| `fail_expression_type.workflow_catalog.yaml` | FAIL (B206) | Ill-typed gate expression |
| `patch_string_to_number_coercion.workflow_catalog.yaml` | FAIL (B203) + suggestions | Type mismatch with a coercion patch suggestion |

Expression evaluation and type-checking fixtures are separate: `tests/conformance/expressions/eval.json` and `check.json` (also compared against cel-go in CI's `cel-differential` job).

### EXPECTATIONS.json Format

The `tests/fixtures/EXPECTATIONS.json` file declares expected outcomes for each fixture:

```json
{
  "pass_reference": {
    "should_pass": true,
    "level": "L1",
    "category": "structural",
    "expected_warning_codes": []
  },
  "pass_soft_requires_warn": {
    "should_pass": true,
    "level": "L1",
    "category": "edges",
    "expected_warning_codes": ["W601"]
  },
  "fail_precedes_order": {
    "should_pass": false,
    "level": "L1",
    "category": "edges",
    "expected_error_codes": ["V102"]
  },
  "patch_string_to_number_coercion": {
    "should_pass": false,
    "should_emit_suggestions": true,
    "level": "L4",
    "category": "patches",
    "expected_error_codes": ["B203"]
  }
}
```

Fields:
- `should_pass` (required): Whether the validator should return exit code 0
- `expected_error_codes` (optional): Error codes that must be emitted (checked for failing fixtures)
- `expected_warning_codes` (optional): Warning codes that must be emitted; an empty list means no warning may be emitted
- `level`, `category` (informational): Conformance level (L1-L4) and test category
- `should_emit_suggestions` (optional): Whether the validator should produce fix suggestions

### Running the Conformance Suite

```bash
python scripts/run_conformance.py
```

The runner needs the built package, since the validator runs in the Rust core (`pip install -e .`).

**How it works:**
1. For each entry in `EXPECTATIONS.json`, locates `tests/fixtures/<name>.workflow_catalog.yaml`
2. Runs `tools/validate_workflows.py --catalog <fixture>` (the production catalog is never swapped or modified)
3. Compares the exit code against `should_pass`
4. Reads `tools/validator_suggestions.json` and checks `expected_error_codes` / `expected_warning_codes` against `structured_errors` / `structured_warnings`
5. Writes `build/conformance_results.json`

**Successful output:**

```
PASS: pass_reference
PASS: pass_minimal_single_step
...
PASS: fail_precedes_order

Conformance PASSED
```

**Failure output:**

```
PASS: pass_reference
FAIL: fail_unknown_capability expected should_pass=False got ok=True
FAIL: pass_soft_requires_warn missing expected warning codes: ['W601'] (emitted: [])

Conformance FAILED (2 failures)
```

### Creating New Fixtures

To create a new conformance test:

1. Create the fixture workflow file:

```bash
# Name must be <name>.workflow_catalog.yaml
touch tests/fixtures/fail_mutate_without_checkpoint.workflow_catalog.yaml
```

2. Write a minimal workflow that exercises the scenario:

```yaml
# tests/fixtures/fail_mutate_without_checkpoint.workflow_catalog.yaml
# Standard version: 1.1.0
mutate_first:
  goal: Test that a missing required prerequisite is caught.
  risk: high
  steps:
  - capability: mutate
    purpose: Mutate something.
    store_as: mutate_out
    # checkpoint requires mutate: no checkpoint runs before it (V102)
```

3. Add the expectation to `tests/fixtures/EXPECTATIONS.json`:

```json
{
  "fail_mutate_without_checkpoint": {
    "should_pass": false,
    "level": "L1",
    "category": "edges",
    "expected_error_codes": ["V102"]
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
  mapping_ref: schemas/transforms/transform_mapping_coerce_string_to_number.yaml
- from: number
  to: string
  mapping_ref: schemas/transforms/transform_mapping_coerce_number_to_string.yaml
- from: object
  to: string
  mapping_ref: schemas/transforms/transform_mapping_stringify_object.yaml
- from: array<object>
  to: array<string>
  mapping_ref: schemas/transforms/transform_mapping_project_array_object_to_array_string.yaml
- from: array<any>
  to: array<object>
  mapping_ref: schemas/transforms/transform_mapping_wrap_any_to_object.yaml
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
  mapping_ref: schemas/transforms/transform_mapping_coerce_boolean_to_string.yaml
```

3. **How the workflow validator uses coercions**:

When the workflow validator (the Rust core behind `validate_workflows.py`) detects a consumer input type mismatch, it:

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
  "suggested_mapping_ref": "schemas/transforms/transform_mapping_project_array_object_to_array_string.yaml",
  "patch": {
    "action": "insert_transform_before_step",
    "insert_at_step_index": 5,
    "new_step": {
      "capability": "transform",
      "purpose": "Coerce constraints to array<string> for consumer input contract",
      "mapping_ref": "schemas/transforms/transform_mapping_project_array_object_to_array_string.yaml",
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
[workflow_name] step N (nonexistent_cap): V101 capability 'nonexistent_cap' not found in ontology
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
[workflow_name] step N (capability): B201 bad reference ${store_name.field}: path field not in schema for store_name
```

(A reference to a store that no earlier step defines is B202: `unknown reference store 'store_name' in ${store_name}`.)

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
[workflow_name] step N (capability): B203 type mismatch ${ref: array<string>}: annotated array<string> but schema has array<object>
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
[workflow_name] step N (capability): B204 ambiguous type for ${ref}: inferred unknown is ambiguous or unknown; add a typed annotation
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

As a whole list item, a typed reference must be quoted (`- "${previous_out.result: array<object>}"`), or YAML reads it as a mapping (W612).

### "Consumer input type mismatch"

**Error message:**
```
[workflow_name] step N (capability): B203 consumer input type mismatch: input 'key' expects string but got number from ${ref}
```

**Cause:** The inferred type of a binding does not match the consumer capability's `input_schema` for that parameter.

**Fix:**
1. Insert a `transform` step between the producer and consumer:

```yaml
# Insert before the consumer step
- capability: transform
  purpose: Coerce value to expected type
  mapping_ref: schemas/transforms/transform_mapping_coerce_number_to_string.yaml
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

### "Missing required prerequisite" / "must come after"

**Error message:**
```
[workflow_name] step N (capability): V102 capability 'capability' missing required prerequisite 'other_cap' before it
[workflow_name] step N (capability): V102 'capability' must come after 'other_cap' (precedes), but 'other_cap' first appears at step M
```

**Cause:** The first form: the ontology defines a `requires` edge from `other_cap` to `capability`, but `other_cap` does not run earlier in the workflow. The second form: a `precedes` edge, where both capabilities appear but the target comes first (or runs concurrently in the same `parallel_group`).

**Fix:** Either add (or move) the prerequisite capability as an earlier step outside the step's parallel group, or verify the edge is correct in the ontology. `requires` edges are hard dependencies; `precedes` edges only constrain order when both capabilities are present -- the validator rejects workflows that violate either.

### "should be preceded by" (warning)

**Warning message:**
```
[workflow_name] step N (execute): W601 'execute' should be preceded by 'constrain' (soft_requires)
```

**Cause:** None of the capability's `soft_requires` sources runs before it. This is a warning: the run still passes unless `--strict` is used.

**Fix:** Add one of the listed capabilities earlier in the workflow if the recommendation applies.

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
| Workflows | `python tools/validate_workflows.py` | Bindings, types, expressions, edge semantics, safety flags, file refs (Rust core; needs the built package) |
| Profiles | `python tools/validate_profiles.py` | Schema conformance, value ranges |
| Ontology | `python tools/validate_ontology.py` | Orphans, cycles, symmetry |
| Skill Refs | `python tools/validate_skill_refs.py` | Phantom file paths in SKILL.md |
| Schema Sync | `python tools/sync_skill_schemas.py` (`--check` in CI) | Generates skill-local schemas and vendored catalogs |
| Conformance | `python scripts/run_conformance.py` | Runs validator against test fixtures |

Run the full validation suite in sequence:

```bash
python -c "import yaml; yaml.safe_load(open('schemas/capability_ontology.yaml'))" && \
python tools/validate_ontology.py && \
python tools/validate_workflows.py && \
python tools/validate_profiles.py && \
python tools/validate_skill_refs.py && \
python tools/sync_skill_schemas.py --check
```
