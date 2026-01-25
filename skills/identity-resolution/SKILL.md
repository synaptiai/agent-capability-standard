---
name: identity-resolution
description: Resolve entity identity across multiple sources, aliases, and records with conflict handling and confidence scoring. Use when merging data sources, deduplicating records, or establishing canonical entity references.
argument-hint: "[candidates] [resolution_strategy] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Perform **identity resolution** to determine when different references point to the same real-world entity. This is critical for data integration, world-state construction, and maintaining consistent entity tracking across sources.

**Success criteria:**
- Entities are correctly merged or kept separate based on evidence
- Canonical IDs are assigned to resolved entities
- Merge conflicts are documented with resolution rationale
- Confidence scores reflect match quality
- False positive merges are minimized

**Compatible schemas:**
- `docs/schemas/world_state_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `candidates` | Yes | array | Entity records from different sources to resolve |
| `resolution_strategy` | No | string | `deterministic`, `probabilistic`, `human_in_loop` (default: probabilistic) |
| `match_fields` | No | array | Fields to use for matching (default: all available) |
| `threshold` | No | number | Match confidence threshold for auto-merge (default: 0.8) |
| `constraints` | No | object | Known matches/non-matches, domain-specific rules |

## Procedure

1) **Normalize candidates**: Prepare entity records for comparison
   - Standardize field names across sources
   - Normalize values (case, whitespace, formatting)
   - Parse composite fields (full name -> first/last)
   - Handle missing values (null vs. empty vs. unknown)

2) **Extract matching features**: Identify attributes useful for identity
   - **Identifiers**: IDs, emails, SSNs, URLs (high signal)
   - **Names**: Entity names, aliases, labels (medium signal)
   - **Attributes**: Properties that distinguish entities (varies)
   - **Relationships**: Connected entities that provide context

3) **Generate candidate pairs**: Create pairs to compare
   - For small sets: all pairs (n choose 2)
   - For large sets: blocking on key fields to reduce comparisons
   - Include known matches and non-matches from constraints

4) **Compute similarity scores**: For each candidate pair
   - **Exact match**: Same identifier -> 1.0
   - **String similarity**: Jaro-Winkler, Levenshtein for names
   - **Phonetic similarity**: Soundex, Metaphone for name variants
   - **Semantic similarity**: Embeddings for descriptions
   - **Structural similarity**: Same relationships, attributes

5) **Apply resolution strategy**:

   For `deterministic`:
   - Exact match on key identifiers -> merge
   - Any conflict on key identifiers -> separate
   - Clear rules, no probabilistic scoring

   For `probabilistic`:
   - Combine feature scores with weights
   - Apply threshold: above -> merge, below -> separate
   - Zone of uncertainty triggers review

   For `human_in_loop`:
   - Flag uncertain cases for human review
   - Track human decisions for learning

6) **Resolve conflicts**: When merged entities have conflicting attributes
   - **Recency**: Prefer more recent value
   - **Authority**: Prefer more authoritative source
   - **Completeness**: Prefer non-null values
   - **Consensus**: Prefer value appearing in most sources
   - Document conflicts that cannot be auto-resolved

7) **Construct resolved entity**: Build canonical representation
   - Assign canonical ID (new UUID or prefer existing stable ID)
   - Merge attributes with conflict resolution
   - List all source aliases
   - Calculate overall confidence

8) **Ground decisions**: Document evidence for each merge
   - Which features matched
   - Similarity scores
   - Resolution rationale

## Output Contract

Return a structured object:

```yaml
resolved_entity:
  canonical_id: string  # Unique ID for the resolved entity
  type: string  # Entity type
  name: string  # Canonical name
  attributes: object  # Merged attributes
aliases:
  - source: string  # Source system/file
    id: string  # ID in that source
    name: string | null  # Name in that source
    confidence: number  # Match confidence 0.0-1.0
merge_conflicts:
  - attribute: string  # Conflicting attribute name
    values:
      - source: string
        value: any
    resolution: string  # How conflict was resolved
    resolved_value: any
provenance:
  sources: array[string]  # All source systems/files
  resolution_method: string  # Strategy used
  match_evidence:
    - feature: string  # What matched
      score: number  # Similarity score
      weight: number  # Weight in final score
  total_score: number  # Combined match score
confidence: number  # 0.0-1.0 overall confidence
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `resolved_entity` | object | The canonical merged entity |
| `aliases` | array | All source references that map to this entity |
| `merge_conflicts` | array | Attributes that conflicted and how resolved |
| `provenance.match_evidence` | array | Features that contributed to match |
| `confidence` | number | Overall confidence in the resolution |

## Examples

### Example 1: User Account Resolution

**Input:**
```yaml
candidates:
  - source: "github"
    id: "user_12345"
    email: "jsmith@company.com"
    name: "John Smith"
    created_at: "2020-01-15"
  - source: "slack"
    id: "U0ABC123"
    email: "john.smith@company.com"
    name: "John S."
    created_at: "2019-06-01"
  - source: "jira"
    id: "jsmith"
    email: "jsmith@company.com"
    name: "J. Smith"
    created_at: "2021-03-10"
resolution_strategy: probabilistic
threshold: 0.8
```

**Output:**
```yaml
resolved_entity:
  canonical_id: "person_jsmith_company"
  type: "person"
  name: "John Smith"
  attributes:
    email: "jsmith@company.com"
    company: "company.com"
    first_seen: "2019-06-01"
    last_seen: "2025-01-24"
aliases:
  - source: "github"
    id: "user_12345"
    name: "John Smith"
    confidence: 1.0
  - source: "slack"
    id: "U0ABC123"
    name: "John S."
    confidence: 0.92
  - source: "jira"
    id: "jsmith"
    name: "J. Smith"
    confidence: 0.95
merge_conflicts:
  - attribute: "email"
    values:
      - source: "github"
        value: "jsmith@company.com"
      - source: "slack"
        value: "john.smith@company.com"
      - source: "jira"
        value: "jsmith@company.com"
    resolution: "consensus - 2 of 3 sources agree"
    resolved_value: "jsmith@company.com"
  - attribute: "name"
    values:
      - source: "github"
        value: "John Smith"
      - source: "slack"
        value: "John S."
      - source: "jira"
        value: "J. Smith"
    resolution: "completeness - prefer most complete form"
    resolved_value: "John Smith"
provenance:
  sources: ["github", "slack", "jira"]
  resolution_method: "probabilistic"
  match_evidence:
    - feature: "email_domain"
      score: 1.0
      weight: 0.3
    - feature: "email_local_part"
      score: 0.85
      weight: 0.3
    - feature: "name_similarity"
      score: 0.78
      weight: 0.2
    - feature: "company_overlap"
      score: 1.0
      weight: 0.2
  total_score: 0.91
confidence: 0.91
evidence_anchors:
  - "github_api:users/user_12345"
  - "slack_api:users/U0ABC123"
  - "jira_api:users/jsmith"
assumptions:
  - "Email domain indicates same organization"
  - "Name variations are aliases, not different people"
  - "No two employees share exact email local part"
```

**Evidence pattern:** Matched on email domain (same company), high string similarity on email local parts, name variations consistent with abbreviations.

---

### Example 2: Service Identity Resolution (Code vs. Infrastructure)

**Input:**
```yaml
candidates:
  - source: "package.json"
    id: "api-gateway"
    type: "npm_package"
    description: "API Gateway Service"
  - source: "kubernetes"
    id: "api-gateway-deployment"
    type: "deployment"
    labels:
      app: "api-gateway"
  - source: "datadog"
    id: "service:api-gateway-prod"
    type: "apm_service"
    environment: "production"
resolution_strategy: deterministic
```

**Output:**
```yaml
resolved_entity:
  canonical_id: "service_api_gateway"
  type: "service"
  name: "API Gateway"
  attributes:
    package_name: "api-gateway"
    k8s_deployment: "api-gateway-deployment"
    apm_service: "api-gateway-prod"
    environment: "production"
aliases:
  - source: "package.json"
    id: "api-gateway"
    name: null
    confidence: 1.0
  - source: "kubernetes"
    id: "api-gateway-deployment"
    name: "api-gateway"
    confidence: 1.0
  - source: "datadog"
    id: "service:api-gateway-prod"
    name: null
    confidence: 1.0
merge_conflicts: []
provenance:
  sources: ["package.json", "kubernetes", "datadog"]
  resolution_method: "deterministic"
  match_evidence:
    - feature: "name_exact_match"
      score: 1.0
      weight: 1.0
  total_score: 1.0
confidence: 1.0
evidence_anchors:
  - "package.json:name"
  - "k8s:deployments/api-gateway-deployment"
  - "datadog:services/api-gateway-prod"
assumptions:
  - "Package name matches Kubernetes app label"
  - "Datadog service name follows convention: {app}-{env}"
```

## Verification

- [ ] No entity is mapped to multiple canonical IDs
- [ ] All source records are accounted for (merged or separate)
- [ ] Confidence scores are within [0.0, 1.0]
- [ ] Merge conflicts have documented resolutions
- [ ] Known matches/non-matches from constraints are respected

**Verification tools:** Duplicate detection, constraint validation

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not merge entities when confidence is below threshold
- Flag potential false positives (high-confidence matches with conflicting key attributes)
- Preserve source record IDs for traceability
- When in doubt, keep entities separate (prefer false negatives over false positives)

## Composition Patterns

**Commonly follows:**
- `retrieve` - Get data from multiple sources before resolution
- `inspect` - Observe entity attributes before matching
- `search` - Find candidate matches

**Commonly precedes:**
- `world-state` - Build state with resolved entities
- `integrate` - Merge data after identity resolution
- `provenance` - Track lineage of resolved entities

**Anti-patterns:**
- Never merge without evidence (at least one matching feature)
- Avoid auto-merging when key identifiers conflict

**Workflow references:**
- See `composition_patterns.md#world-model-build` for entity resolution in model construction
- See `composition_patterns.md#digital-twin-sync-loop` for ongoing identity maintenance
