---
name: compare-documents
description: Compare documents for differences, alignment, and gaps to identify inconsistencies or evolution. Use when reviewing document versions, comparing specs to implementations, or analyzing policy alignment.
argument-hint: "[doc_a] [doc_b] [comparison_type] [focus_areas]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Systematically compare two or more documents to identify differences, alignments, gaps, and contradictions with precise location references and significance assessment.

**Success criteria:**
- All significant differences are identified with precise locations
- Differences are categorized by type and significance
- Alignment and gaps are explicitly documented
- Comparison preserves provenance for audit trails

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `documents` | Yes | array[string\|object] | Documents to compare (paths, URLs, or content) |
| `comparison_type` | No | string | Type: diff, alignment, gap_analysis, contradiction (default: diff) |
| `focus_areas` | No | array[string] | Sections or topics to focus comparison on |
| `baseline` | No | string | Which document is the reference/source of truth |
| `ignore_patterns` | No | array[string] | Patterns to ignore (whitespace, formatting, etc.) |

## Procedure

1) **Parse documents**: Extract structured content from each document
   - Identify sections, headings, and logical units
   - Normalize formatting for comparison
   - Create section mappings between documents

2) **Align sections**: Match corresponding sections across documents
   - Use headings, numbering, or content similarity
   - Identify sections present in one but not others
   - Handle renamed or restructured sections

3) **Detect differences**: For aligned sections
   - Textual changes (additions, deletions, modifications)
   - Semantic changes (meaning shifts even if words similar)
   - Structural changes (reordering, nesting)

4) **Classify differences**: Categorize each difference
   - Type: addition, deletion, modification, reorder, contradiction
   - Significance: cosmetic, substantive, critical
   - Impact: informational, behavioral, legal

5) **Analyze gaps**: Identify missing coverage
   - Topics in one document absent from others
   - Incomplete sections compared to baseline
   - Implicit vs explicit content differences

6) **Generate provenance**: Track document lineage
   - Version relationships if known
   - Author/date metadata if available
   - Change history reconstruction

## Output Contract

Return a structured object:

```yaml
documents:
  - id: string
    path: string
    type: string  # policy, spec, contract, code, etc.
    version: string | null
    sections_count: integer
comparison_summary:
  total_differences: integer
  by_type:
    additions: integer
    deletions: integer
    modifications: integer
    contradictions: integer
  by_significance:
    cosmetic: integer
    substantive: integer
    critical: integer
differences:
  - id: string
    type: addition | deletion | modification | reorder | contradiction
    significance: cosmetic | substantive | critical
    location_a: string  # doc_id:section:line or null
    location_b: string
    content_a: string | null
    content_b: string | null
    description: string
    impact: string | null
alignments:
  - section_topic: string
    aligned_across: array[string]  # doc IDs where aligned
    alignment_quality: exact | semantic | partial
gaps:
  - document_id: string
    missing_topic: string
    present_in: array[string]  # doc IDs where present
    significance: low | medium | high
contradictions:
  - description: string
    document_a: object  # id, location, claim
    document_b: object
    resolution_needed: boolean
recommendation:
  summary: string
  action_items: array[string]
  priority_differences: array[string]  # IDs of critical differences
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
provenance:
  comparison_timestamp: string
  documents_hash: object  # doc_id -> content hash
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `documents` | array | Documents compared with metadata |
| `comparison_summary` | object | Aggregate statistics |
| `differences` | array | Individual differences with locations |
| `alignments` | array | Sections that align across documents |
| `gaps` | array | Content present in some but not all documents |
| `contradictions` | array | Conflicting statements between documents |
| `recommendation` | object | Summary and action items |
| `provenance` | object | Audit trail information |
| `confidence` | number | 0.0-1.0 based on parsing quality |
| `evidence_anchors` | array[string] | Document locations referenced |
| `assumptions` | array[string] | Explicitly stated assumptions |

## Examples

### Example 1: Comparing API Specification Versions

**Input:**
```yaml
documents:
  - path: "docs/api-spec-v1.yaml"
    version: "1.0"
  - path: "docs/api-spec-v2.yaml"
    version: "2.0"
comparison_type: "diff"
focus_areas:
  - "endpoints"
  - "authentication"
  - "error_codes"
baseline: "docs/api-spec-v1.yaml"
ignore_patterns:
  - "whitespace"
  - "comments"
```

**Output:**
```yaml
documents:
  - id: "api-v1"
    path: "docs/api-spec-v1.yaml"
    type: "api_specification"
    version: "1.0"
    sections_count: 15
  - id: "api-v2"
    path: "docs/api-spec-v2.yaml"
    type: "api_specification"
    version: "2.0"
    sections_count: 18
comparison_summary:
  total_differences: 12
  by_type:
    additions: 5
    deletions: 1
    modifications: 4
    contradictions: 2
  by_significance:
    cosmetic: 3
    substantive: 7
    critical: 2
differences:
  - id: "diff-001"
    type: addition
    significance: substantive
    location_a: null
    location_b: "api-v2:paths:/users/{id}/preferences:42"
    content_a: null
    content_b: "GET /users/{id}/preferences - Returns user preferences"
    description: "New endpoint added for user preferences"
    impact: "Clients can now retrieve user preferences"
  - id: "diff-002"
    type: modification
    significance: critical
    location_a: "api-v1:paths:/auth/token:28"
    location_b: "api-v2:paths:/auth/token:32"
    content_a: "token_type: bearer"
    content_b: "token_type: Bearer (case-sensitive)"
    description: "Token type changed to case-sensitive"
    impact: "BREAKING: Existing clients using lowercase may fail"
  - id: "diff-003"
    type: addition
    significance: substantive
    location_a: null
    location_b: "api-v2:components:securitySchemes:85"
    content_a: null
    content_b: "oauth2 security scheme with PKCE flow"
    description: "Added OAuth2 with PKCE authentication option"
    impact: "Enhanced security for mobile/SPA clients"
  - id: "diff-004"
    type: deletion
    significance: critical
    location_a: "api-v1:paths:/legacy/sync:156"
    location_b: null
    content_a: "POST /legacy/sync - Synchronizes legacy data"
    content_b: null
    description: "Legacy sync endpoint removed"
    impact: "BREAKING: Clients using legacy sync will fail"
  - id: "diff-005"
    type: modification
    significance: cosmetic
    location_a: "api-v1:info:description:5"
    location_b: "api-v2:info:description:5"
    content_a: "API for user management"
    content_b: "API for user management and preferences"
    description: "Updated API description"
    impact: "Documentation only"
alignments:
  - section_topic: "Authentication basics"
    aligned_across: ["api-v1", "api-v2"]
    alignment_quality: semantic
  - section_topic: "User CRUD endpoints"
    aligned_across: ["api-v1", "api-v2"]
    alignment_quality: exact
  - section_topic: "Error response format"
    aligned_across: ["api-v1", "api-v2"]
    alignment_quality: exact
gaps:
  - document_id: "api-v1"
    missing_topic: "Rate limiting headers"
    present_in: ["api-v2"]
    significance: medium
  - document_id: "api-v1"
    missing_topic: "Pagination cursors"
    present_in: ["api-v2"]
    significance: medium
contradictions:
  - description: "Maximum page size differs between versions"
    document_a:
      id: "api-v1"
      location: "api-v1:parameters:page_size:89"
      claim: "maximum: 100"
    document_b:
      id: "api-v2"
      location: "api-v2:parameters:page_size:95"
      claim: "maximum: 50"
    resolution_needed: true
  - description: "Error code 4001 has different meanings"
    document_a:
      id: "api-v1"
      location: "api-v1:errors:4001:210"
      claim: "4001: Invalid token format"
    document_b:
      id: "api-v2"
      location: "api-v2:errors:4001:225"
      claim: "4001: Token expired"
    resolution_needed: true
recommendation:
  summary: "v2 has 2 breaking changes requiring migration guide; 2 contradictions need resolution"
  action_items:
    - "Create migration guide for token_type case sensitivity"
    - "Notify clients of /legacy/sync deprecation timeline"
    - "Resolve contradiction on max page_size"
    - "Resolve error code 4001 meaning"
  priority_differences:
    - "diff-002"
    - "diff-004"
confidence: 0.9
evidence_anchors:
  - "docs/api-spec-v1.yaml:28"
  - "docs/api-spec-v1.yaml:89"
  - "docs/api-spec-v1.yaml:156"
  - "docs/api-spec-v1.yaml:210"
  - "docs/api-spec-v2.yaml:32"
  - "docs/api-spec-v2.yaml:42"
  - "docs/api-spec-v2.yaml:85"
  - "docs/api-spec-v2.yaml:95"
  - "docs/api-spec-v2.yaml:225"
assumptions:
  - "YAML parsing is complete and accurate"
  - "Semantic analysis based on common API conventions"
  - "Breaking changes defined as client-incompatible modifications"
provenance:
  comparison_timestamp: "2024-01-15T10:30:00Z"
  documents_hash:
    api-v1: "sha256:a1b2c3..."
    api-v2: "sha256:d4e5f6..."
```

**Evidence pattern:** Document parsing + section alignment + diff analysis

## Verification

- [ ] All sections in both documents are accounted for
- [ ] Differences include precise file:line locations
- [ ] Breaking changes correctly identified as critical
- [ ] Contradictions flagged for resolution
- [ ] Document hashes recorded for provenance

**Verification tools:** Read (for document content), Grep (for searching sections)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Preserve original document content in quotes
- Do not alter document interpretation without explicit assumptions
- Flag when document formats prevent accurate comparison
- Maintain provenance for audit requirements

## Composition Patterns

**Commonly follows:**
- `retrieve` - to fetch document content
- `search` - to find relevant documents
- `identify-entity` - to determine document types

**Commonly precedes:**
- `summarize` - to create change summary
- `generate-plan` - to plan document updates
- `critique` - to analyze document quality

**Anti-patterns:**
- Never compare without specifying comparison type
- Avoid comparing documents of fundamentally different types

**Workflow references:**
- See `workflow_catalog.json#document_review` for review workflows
- See `workflow_catalog.json#api_versioning` for API lifecycle
