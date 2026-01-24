---
name: identify
description: Classify which entity, type, or label best matches observed evidence. Use when categorizing, naming, disambiguating, or resolving entity identity.
argument-hint: "[entity] [candidates] [disambiguation-context]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Determine the specific identity, type, or classification of an observed entity by matching evidence against known categories or candidates. Identification goes beyond detection to assign a specific label or identity.

**Success criteria:**
- Entity matched to a specific identity or classification
- Match quality assessment (exact/probable/possible/no_match)
- Alternative candidates listed with probabilities
- Disambiguation signals documented

**Compatible schemas:**
- `docs/schemas/identification_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | The entity or data to identify (reference, description, or raw data) |
| `candidates` | No | array[string] | Known entities/types to match against |
| `context` | No | object | Additional context for disambiguation (namespace, domain, timeframe) |
| `match_threshold` | No | number | Minimum confidence for positive identification (default: 0.5) |

## Procedure

1) **Extract identifying features**: Analyze the target to find distinguishing characteristics
   - Names, identifiers, unique attributes
   - Structural signatures (API shape, file patterns)
   - Behavioral characteristics (usage patterns, relationships)

2) **Search for matching candidates**: Compare features against known entities
   - Exact matches: identifier or name matches precisely
   - Fuzzy matches: similar names, overlapping attributes
   - Structural matches: same pattern, different naming

3) **Disambiguate conflicts**: When multiple candidates match, apply resolution
   - Namespace context: which domain is this from?
   - Temporal context: which version or era?
   - Relational context: what does it connect to?

4) **Rank alternatives**: Order candidates by match probability
   - Calculate probability based on feature overlap
   - Document which features drove each ranking

5) **Ground claims**: Attach evidence anchors to identification
   - Link each matching feature to its source location
   - Format: `file:line`, `url`, or `tool:<tool_name>:<output_ref>`

6) **Assess match quality**: Rate the identification confidence
   - Exact: single candidate, all features match
   - Probable: strong match with minor uncertainty
   - Possible: plausible but unconfirmed
   - No match: no candidates sufficiently match

## Output Contract

Return a structured object:

```yaml
entity:
  id: string  # Resolved identifier
  type: string  # Entity type/category
  canonical_name: string  # Standard name for this entity
  attributes: object  # Key attributes of the identified entity
match_quality: exact | probable | possible | no_match
alternatives:
  - entity: object  # Alternative candidate
    probability: number  # 0.0-1.0 likelihood
disambiguation_signals: array[string]  # What distinguished the winner
confidence: number  # 0.0-1.0 overall confidence
evidence_anchors: array[string]  # File:line references
assumptions: array[string]  # Explicitly stated assumptions
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `entity` | object | The identified entity with its attributes |
| `match_quality` | enum | Strength of the identification |
| `alternatives` | array | Other possible matches with probabilities |
| `disambiguation_signals` | array | Evidence that resolved ambiguity |
| `confidence` | number | 0.0-1.0 based on evidence quality |
| `evidence_anchors` | array[string] | References supporting identification |
| `assumptions` | array[string] | Explicitly stated assumptions |

## Examples

### Example 1: Identify Error Type from Stack Trace

**Input:**
```yaml
target: |
  TypeError: Cannot read property 'map' of undefined
    at UserList (src/components/UserList.jsx:15)
    at renderWithHooks (node_modules/react-dom/...)
candidates:
  - "null reference error"
  - "type mismatch error"
  - "undefined property access"
```

**Output:**
```yaml
entity:
  id: "undefined-property-access"
  type: "runtime-error"
  canonical_name: "Undefined Property Access Error"
  attributes:
    property: "map"
    expected_type: "array"
    actual_type: "undefined"
    location: "src/components/UserList.jsx:15"
match_quality: exact
alternatives:
  - entity:
      id: "null-reference-error"
      type: "runtime-error"
    probability: 0.2
disambiguation_signals:
  - "Error message explicitly mentions 'undefined'"
  - "'map' is array method, indicating expected array type"
confidence: 0.95
evidence_anchors:
  - "stack_trace:line1"
  - "src/components/UserList.jsx:15"
assumptions:
  - "Stack trace is accurate and unmodified"
  - "Error occurred at runtime, not build time"
```

**Evidence pattern:** Parse error message structure, match against error type taxonomy, use stack trace for location grounding.

---

### Example 2: Identify Package from Import Statement

**Input:**
```yaml
target: "import { useState, useEffect } from 'react'"
context:
  file: "src/App.tsx"
  package_manager: "npm"
```

**Output:**
```yaml
entity:
  id: "react@18.2.0"
  type: "npm-package"
  canonical_name: "React"
  attributes:
    registry: "npmjs.org"
    hooks_version: "16.8+"
    typescript_support: true
match_quality: exact
alternatives: []
disambiguation_signals:
  - "Import uses 'react' package name"
  - "useState/useEffect are React hooks (v16.8+)"
confidence: 0.98
evidence_anchors:
  - "src/App.tsx:import-line"
  - "package.json:dependencies"
assumptions:
  - "Standard npm/node_modules resolution"
  - "No aliased imports in bundler config"
```

## Verification

- [ ] Entity ID is unique and follows naming conventions
- [ ] Match quality reflects actual evidence strength
- [ ] Alternatives are ranked by probability (descending)
- [ ] All disambiguation signals are grounded in evidence
- [ ] Confidence score is justified by evidence count and quality

**Verification tools:** Read (to verify referenced locations), Grep (to search for confirming patterns)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not make identification claims without evidence
- Report ambiguity when multiple candidates have similar probability
- Stop and request clarification if target is too vague to identify
- Use "no_match" when confidence is below match_threshold

## Composition Patterns

**Commonly follows:**
- `detect` - Identification typically follows positive detection
- `search` - Search results often need identity resolution
- `inspect` - Observed entities need classification

**Commonly precedes:**
- `estimate` - Identified entities can have properties estimated
- `compare` - Identified entities can be compared
- `plan` - Identified issues can trigger remediation planning

**Anti-patterns:**
- Never use identify for existence checking (use `detect` instead)
- Avoid identify for quantitative assessment (use `estimate` instead)
- Do not use identify when you need relationship discovery (use `discover` instead)

**Workflow references:**
- See `composition_patterns.md#world-model-build` for identity-resolution in context
- See `composition_patterns.md#enrichment-pipeline` for identification in data pipelines
