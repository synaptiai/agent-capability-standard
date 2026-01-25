---
name: discover
description: Find latent patterns, relationships, anomalies, or insights not explicitly specified. Use when exploring unknown structure, finding hidden connections, or uncovering emergent phenomena.
argument-hint: "[search-space] [discovery-type] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Explore data or systems to find patterns, relationships, or anomalies that were not explicitly requested or expected. Discovery is open-ended exploration that surfaces novel insights rather than confirming hypotheses.

**Success criteria:**
- At least one non-obvious finding surfaced
- Significance level assigned to each discovery
- Novelty classified (known, suspected, surprising)
- Methodology documented for reproducibility

**Compatible schemas:**
- `docs/schemas/discovery_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `search_space` | Yes | string\|object | Where to look (files, data, systems, domains) |
| `discovery_type` | No | string | What kind of discovery: relationship, pattern, anomaly, gap, opportunity |
| `constraints` | No | object | Bounds on exploration (time, scope, depth) |
| `seed_observations` | No | array | Initial observations that may hint at discoveries |

## Procedure

1) **Define search space boundaries**: Establish what is in and out of scope
   - File patterns, directories, or data sources
   - Conceptual boundaries (domain, time range)
   - Depth limits (how many hops of relationships)

2) **Apply discovery heuristics**: Use exploration strategies systematically
   - **Pattern mining**: Look for recurring structures, naming conventions, code patterns
   - **Relationship mapping**: Find connections between entities (imports, calls, references)
   - **Anomaly detection**: Identify outliers, inconsistencies, unusual structures
   - **Gap analysis**: Find missing elements, broken links, incomplete patterns

3) **Assess significance**: Evaluate each finding's importance
   - High: Directly actionable or explains important behavior
   - Medium: Useful context or potential issue
   - Low: Interesting but not actionable

4) **Classify novelty**: Determine how surprising each discovery is
   - Known: Documented or widely understood
   - Suspected: Hypothesized but not confirmed
   - Surprising: Unexpected or counter to assumptions

5) **Identify entities involved**: Link discoveries to specific entities
   - Files, functions, classes, modules
   - People, teams, systems
   - Concepts, patterns, architectures

6) **Ground claims**: Attach evidence anchors to all discoveries
   - Exact locations where patterns occur
   - References to related documentation

7) **Synthesize findings**: Connect individual discoveries into coherent insights

## Output Contract

Return a structured object:

```yaml
discoveries:
  - type: string  # relationship, pattern, anomaly, gap, opportunity
    description: string  # What was discovered
    significance: low | medium | high
    novelty: known | suspected | surprising
    entities_involved: array[string]
    location: string  # Where found (file:line, path, or reference)
methodology: string  # How discovery was conducted
search_space: string  # What was explored
confidence: number  # 0.0-1.0 confidence in discoveries
evidence_anchors: array[string]  # References to supporting evidence
assumptions: array[string]  # Conditions that affect findings
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `discoveries` | array | List of findings with metadata |
| `discoveries[].type` | string | Category of discovery |
| `discoveries[].significance` | enum | Importance level |
| `discoveries[].novelty` | enum | How unexpected the finding is |
| `methodology` | string | Exploration approach used |
| `search_space` | string | Scope of exploration |
| `confidence` | number | 0.0-1.0 overall discovery confidence |
| `evidence_anchors` | array[string] | References to evidence |
| `assumptions` | array[string] | Conditions that could change findings |

## Examples

### Example 1: Discover Hidden Dependencies

**Input:**
```yaml
search_space: "src/"
discovery_type: "relationship"
constraints:
  max_depth: 3
  focus: "imports and function calls"
```

**Output:**
```yaml
discoveries:
  - type: "relationship"
    description: "Circular dependency between UserService and AuthService"
    significance: high
    novelty: surprising
    entities_involved:
      - "src/services/UserService.ts"
      - "src/services/AuthService.ts"
    location: "src/services/UserService.ts:12 imports AuthService; src/services/AuthService.ts:8 imports UserService"
  - type: "pattern"
    description: "All repository classes follow identical initialization pattern with DI container lookup"
    significance: medium
    novelty: known
    entities_involved:
      - "src/repositories/*.ts"
    location: "src/repositories/"
  - type: "anomaly"
    description: "PaymentService bypasses standard error handling pattern used by all other services"
    significance: high
    novelty: suspected
    entities_involved:
      - "src/services/PaymentService.ts"
    location: "src/services/PaymentService.ts:45-78"
  - type: "gap"
    description: "No unit tests for critical OrderValidation module"
    significance: high
    novelty: surprising
    entities_involved:
      - "src/validation/OrderValidation.ts"
    location: "tests/ - no corresponding test file"
methodology: "Static analysis of import statements, grep for class instantiation patterns, comparison against test file naming conventions"
search_space: "src/ directory (156 TypeScript files)"
confidence: 0.85
evidence_anchors:
  - "src/services/UserService.ts:12"
  - "src/services/AuthService.ts:8"
  - "src/services/PaymentService.ts:45"
  - "tests/:directory-listing"
assumptions:
  - "Standard TypeScript import resolution"
  - "Test files follow *Spec.ts or *.test.ts convention"
  - "All production code is in src/"
```

**Evidence pattern:** Grep for import statements, build dependency graph, compare patterns across files.

---

### Example 2: Discover Architecture Patterns

**Input:**
```yaml
search_space: "entire codebase"
discovery_type: "pattern"
seed_observations:
  - "Some endpoints seem to share similar structure"
```

**Output:**
```yaml
discoveries:
  - type: "pattern"
    description: "Three distinct architectural styles coexist: MVC in /admin, DDD in /core, and script-style in /legacy"
    significance: high
    novelty: suspected
    entities_involved:
      - "/admin/*"
      - "/core/*"
      - "/legacy/*"
    location: "Repository-wide directory structure"
  - type: "relationship"
    description: "DDD bounded contexts in /core share a common anti-corruption layer for legacy integration"
    significance: medium
    novelty: surprising
    entities_involved:
      - "/core/adapters/legacy/"
    location: "/core/adapters/legacy/*.ts"
  - type: "opportunity"
    description: "MVC controllers in /admin could be consolidated - 12 controllers have nearly identical CRUD patterns"
    significance: medium
    novelty: known
    entities_involved:
      - "/admin/controllers/*.ts"
    location: "/admin/controllers/"
methodology: "Directory structure analysis, pattern matching on file organization, code similarity detection"
search_space: "Full repository (312 files, 4 top-level directories)"
confidence: 0.75
evidence_anchors:
  - "/admin/controllers/:pattern-sample"
  - "/core/domain/:ddd-structure"
  - "/core/adapters/legacy/LegacyAdapter.ts:1-50"
assumptions:
  - "Directory structure reflects intentional architecture"
  - "Pattern differences are deliberate, not accidental"
```

## Verification

- [ ] Each discovery has type, significance, and novelty classified
- [ ] At least one discovery has evidence_anchors
- [ ] Methodology is documented and reproducible
- [ ] Search space boundaries are clearly defined
- [ ] Surprising discoveries are supported by multiple evidence points

**Verification tools:** Read (to verify locations), Grep (to confirm patterns exist)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not modify any files during discovery
- Respect scope boundaries - do not explore outside search_space
- Flag discoveries that may reveal sensitive information
- Report uncertainty when findings could be coincidental

## Composition Patterns

**Commonly follows:**
- `inspect` - Discovery often follows initial system observation
- `search` - Discovery extends search results
- `identify` - Discovery finds relationships between identified entities

**Commonly precedes:**
- `identify` - Discovered entities may need identification
- `estimate` - Discovered patterns may need quantification
- `compare` - Discovered options may need comparison
- `plan` - Discoveries may trigger action planning

**Anti-patterns:**
- Never use discover for known-item retrieval (use `search`)
- Avoid discover for existence checking (use `detect`)
- Do not use discover when you already know what to find

**Workflow references:**
- See `composition_patterns.md#capability-gap-analysis` for discover-relationship usage
- See `composition_patterns.md#world-model-build` for discovery in modeling
