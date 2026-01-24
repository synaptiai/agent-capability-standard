---
name: inspect
description: Examine a target (file, directory, URL, entity, system) and produce a structured observation covering identity, structure, properties, relationships, and condition. Use when exploring unknown artifacts, understanding system state, or gathering initial context.
argument-hint: "[target] [lens] [depth]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Live Context

Current environment context for inspection:

- Working directory: !`pwd`
- Directory contents: !`ls -la 2>/dev/null | head -20`
- Git branch: !`git branch --show-current 2>/dev/null || echo "Not a git repo"`
- File count: !`find . -type f -not -path './.git/*' 2>/dev/null | wc -l | tr -d ' '`
- Directory structure: !`find . -type d -not -path './.git/*' -maxdepth 2 2>/dev/null | head -15`

## Intent

Transform an unknown or partially known target into a **structured observation** that can be used by downstream capabilities. Inspection is read-only reconnaissance that answers: "What is this, how is it organized, what are its key properties, and what is its current condition?"

**Success criteria:**
- Target identity clearly established (type, name, namespace)
- Structure accurately mapped (organization, key parts)
- High-signal properties extracted
- Relationships to other entities documented
- Current condition assessed with health signals

**Compatible schemas:**
- `docs/schemas/event_schema.yaml`
- `docs/schemas/world_state_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | What to inspect (path, URI, entity reference, or inline content) |
| `depth` | No | string | `shallow` (surface only) or `deep` (recursive/exhaustive) - default: `deep` |
| `lens` | No | array[string] | Aspects to prioritize (e.g., ["schema", "errors", "dependencies", "security"]) |
| `context` | No | string | Background information to guide inspection |

## Procedure

1) **Resolve target**: Determine what is being inspected
   - Parse target reference (file path, URL, entity ID)
   - Verify target exists and is accessible
   - Determine target type (file, directory, endpoint, data structure, etc.)
   - Record access method used

2) **Extract identity**: Answer "What is this?"
   - Determine unique identifier (if applicable)
   - Classify type (programming language, file format, entity class)
   - Extract name and human-readable description
   - Identify namespace or context (project, organization, domain)

3) **Map structure**: Answer "How is it organized?"
   - Determine structural kind (tree, flat, nested, graph)
   - Describe overall shape and organization
   - Identify key structural parts (sections, components, layers)
   - Note structural patterns (symmetry, hierarchy, modularity)

4) **Extract properties**: Answer "What are its key attributes?"
   - Prioritize high-signal properties (those most useful for understanding)
   - Extract metadata (size, dates, versions, authors)
   - Note configuration values and settings
   - Separate essential vs incidental properties

5) **Map relationships**: Answer "What does it connect to?"
   - Identify dependencies (imports, references, requires)
   - Identify dependents (what uses/references this)
   - Map ownership and containment relationships
   - Note integration points and interfaces

6) **Assess condition**: Answer "What state is it in?"
   - Evaluate health status (healthy, degraded, unknown)
   - Identify positive signals (tests pass, valid schema, clean)
   - Identify risk signals (deprecated, outdated, warnings)
   - Note anomalies or unexpected findings

## Output Contract

Return a structured object:

```yaml
inspection:
  target_ref: string  # Original target reference
  resolved_to: string  # What was actually inspected
  inspected_at: string  # ISO timestamp
identity:
  id: string | null  # Unique identifier if applicable
  type: string  # file, directory, endpoint, entity, etc.
  name: string  # Human-readable name
  namespace: string | null  # Context/scope
  description: string | null  # Brief description
structure:
  kind: tree | flat | nested | graph | linear | unknown
  shape: string  # Description of organization
  key_parts:
    - name: string
      type: string
      location: string | null
      significance: string
  depth: integer | null  # Nesting depth if applicable
  size_metrics:
    total_elements: integer | null
    total_size: string | null  # Human-readable (e.g., "1.2 MB")
properties:
  high_signal:  # Most important attributes
    <key>: <value>
  metadata:
    created: string | null
    modified: string | null
    version: string | null
    author: string | null
  other:  # Secondary attributes
    <key>: <value>
relationships:
  - src: string
    relation: string  # depends_on, owns, located_in, calls, implements, etc.
    dst: string
    direction: outbound | inbound | bidirectional
    strength: weak | normal | strong
    attributes: object | null
condition:
  status: healthy | degraded | unhealthy | unknown
  health_signals:
    - signal: string
      polarity: positive | negative | neutral
      evidence: string
  risks:
    - risk: string
      severity: low | medium | high
      evidence: string
  anomalies:
    - finding: string
      expected: string | null
      actual: string
      significance: string
lens_findings:  # Results specific to requested lens
  <lens_name>:
    <findings>
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `identity.type` | string | Classification of what the target is |
| `structure.kind` | enum | General organizational pattern |
| `structure.key_parts` | array | Most significant structural components |
| `condition.status` | enum | Overall health assessment |
| `lens_findings` | object | Focused analysis based on requested lenses |

## Examples

### Example 1: Python Module Inspection

**Input:**
```yaml
target: "src/auth/handlers.py"
depth: deep
lens: ["dependencies", "errors"]
```

**Output:**
```yaml
inspection:
  target_ref: "src/auth/handlers.py"
  resolved_to: "/project/src/auth/handlers.py"
  inspected_at: "2024-01-15T10:00:00Z"
identity:
  id: "src.auth.handlers"
  type: "Python module"
  name: "handlers.py"
  namespace: "src.auth"
  description: "HTTP request handlers for authentication endpoints"
structure:
  kind: flat
  shape: "Module with function and class definitions"
  key_parts:
    - name: "LoginHandler"
      type: "class"
      location: "line 15-45"
      significance: "Main login endpoint handler"
    - name: "LogoutHandler"
      type: "class"
      location: "line 47-62"
      significance: "Session termination handler"
    - name: "validate_token"
      type: "function"
      location: "line 64-78"
      significance: "JWT validation utility"
  depth: 1
  size_metrics:
    total_elements: 3
    total_size: "2.4 KB"
properties:
  high_signal:
    line_count: 78
    has_type_hints: true
    docstring_coverage: 0.67
  metadata:
    created: "2024-01-01T00:00:00Z"
    modified: "2024-01-14T15:30:00Z"
    version: null
    author: "jsmith"
  other:
    encoding: "utf-8"
    has_shebang: false
relationships:
  - src: "src.auth.handlers"
    relation: "imports"
    dst: "flask"
    direction: outbound
    strength: strong
    attributes: { modules: ["Flask", "request", "jsonify"] }
  - src: "src.auth.handlers"
    relation: "imports"
    dst: "src.auth.models"
    direction: outbound
    strength: strong
    attributes: { classes: ["User", "Session"] }
  - src: "src.auth.handlers"
    relation: "imports"
    dst: "jwt"
    direction: outbound
    strength: normal
    attributes: null
  - src: "src.api.routes"
    relation: "imports"
    dst: "src.auth.handlers"
    direction: inbound
    strength: strong
    attributes: { classes: ["LoginHandler", "LogoutHandler"] }
condition:
  status: healthy
  health_signals:
    - signal: "Type hints present"
      polarity: positive
      evidence: "All function signatures have type annotations"
    - signal: "Docstrings present"
      polarity: positive
      evidence: "Module and class docstrings found"
    - signal: "No syntax errors"
      polarity: positive
      evidence: "AST parsing successful"
  risks:
    - risk: "Incomplete error handling"
      severity: medium
      evidence: "bare except clause at line 42"
  anomalies: []
lens_findings:
  dependencies:
    direct_imports: ["flask", "jwt", "src.auth.models"]
    transitive_count: 12
    external_ratio: 0.67
  errors:
    syntax_errors: []
    linting_warnings:
      - line: 42
        message: "bare except clause"
        rule: "E722"
confidence: 0.95
evidence_anchors:
  - "src/auth/handlers.py:1-78"
  - "tool:Grep:import_search"
assumptions:
  - "Python 3.8+ syntax"
  - "Flask web framework"
```

---

### Example 2: Directory Structure Inspection

**Input:**
```yaml
target: "src/components"
depth: shallow
lens: ["schema"]
```

**Output:**
```yaml
inspection:
  target_ref: "src/components"
  resolved_to: "/project/src/components"
  inspected_at: "2024-01-15T11:00:00Z"
identity:
  id: null
  type: "directory"
  name: "components"
  namespace: "src"
  description: "React component library"
structure:
  kind: tree
  shape: "Feature-organized component directory"
  key_parts:
    - name: "Button/"
      type: "directory"
      location: "src/components/Button"
      significance: "Reusable button component"
    - name: "Form/"
      type: "directory"
      location: "src/components/Form"
      significance: "Form-related components"
    - name: "Layout/"
      type: "directory"
      location: "src/components/Layout"
      significance: "Page layout components"
    - name: "index.ts"
      type: "file"
      location: "src/components/index.ts"
      significance: "Barrel export file"
  depth: 2
  size_metrics:
    total_elements: 15
    total_size: "45 KB"
properties:
  high_signal:
    component_count: 12
    test_coverage: "tests found for 10/12 components"
    typescript: true
  metadata:
    created: "2023-06-15T00:00:00Z"
    modified: "2024-01-14T09:00:00Z"
    version: null
    author: null
  other:
    gitignore_patterns: ["*.test.tsx.snap"]
relationships:
  - src: "src/components"
    relation: "exports_to"
    dst: "src/pages"
    direction: outbound
    strength: strong
    attributes: null
  - src: "src/components"
    relation: "depends_on"
    dst: "src/styles"
    direction: outbound
    strength: normal
    attributes: null
condition:
  status: healthy
  health_signals:
    - signal: "Consistent structure"
      polarity: positive
      evidence: "All components follow Component/index.tsx pattern"
    - signal: "Tests present"
      polarity: positive
      evidence: "*.test.tsx files in most directories"
  risks: []
  anomalies:
    - finding: "Mixed naming conventions"
      expected: "All PascalCase directories"
      actual: "Found 'utils' in lowercase"
      significance: "Minor inconsistency"
lens_findings:
  schema:
    pattern: "{ComponentName}/index.tsx + {ComponentName}.test.tsx"
    conforming: 10
    non_conforming: 2
    notes: "Button and Form missing test files"
confidence: 0.9
evidence_anchors:
  - "src/components/:directory_listing"
  - "src/components/index.ts:1-20"
assumptions:
  - "React/TypeScript project"
  - "Standard component library structure"
```

## Verification

- [ ] Target successfully resolved and accessed
- [ ] Identity accurately determined
- [ ] Structure correctly mapped
- [ ] High-signal properties extracted
- [ ] Relationships have evidence
- [ ] Condition reflects observable state
- [ ] Confidence reflects information completeness

**Verification tools:** File system access, Grep for content search, WebFetch for URLs

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Never modify the target being inspected
- Do not fabricate evidence anchors
- If confidence < 0.5, explicitly request missing artifacts
- Respect access controls and permissions
- Do not follow redirects without noting them
- Sanitize sensitive data in output (passwords, tokens)

## Composition Patterns

**Commonly follows:**
- `search` - Inspect search results
- `retrieve` - Inspect retrieved content
- Start of any exploration task

**Commonly precedes:**
- `detect-*` - Detect patterns in inspected content
- `identify-*` - Identify entities found during inspection
- `compare-*` - Compare inspected artifacts
- `validate` - Validate against requirements

**Anti-patterns:**
- Never inspect and modify in same operation
- Avoid deep inspection of very large targets without filtering
- Do not recursively inspect without depth limits

**Workflow references:**
- See `workflow_catalog.json#codebase-exploration` for systematic code inspection
- See `workflow_catalog.json#incident-investigation` for system state inspection
