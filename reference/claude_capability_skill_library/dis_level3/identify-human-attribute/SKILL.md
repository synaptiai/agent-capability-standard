---
name: identify-human-attribute
description: Identify and classify a human-related attribute from available evidence, such as roles, skills, preferences, or non-sensitive characteristics. Use when determining professional attributes, team roles, expertise areas, or organizational relationships.
argument-hint: "[target-person] [attribute-type] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Classify and determine human attributes based on available evidence, focusing on professional and organizational characteristics. This answers "what is this person's role/skill/attribute?" rather than personal or sensitive attributes.

**Success criteria:**
- Clear attribute identification with value and category
- Match quality assessment (exact, probable, possible, no match)
- Evidence-based attribution with confidence scoring
- Alternative interpretations when uncertain

**Compatible schemas:**
- `docs/schemas/identify_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | The person whose attribute to identify (username, email, person reference) |
| `attribute_type` | No | string | Type of attribute: role, skill, team, expertise, preference (default: any) |
| `context` | No | string\|object | Context for identification (organization, project, codebase) |
| `constraints` | No | object | Identification parameters: require_evidence, confidence_threshold |

## Procedure

1) **Locate person context**: Find information sources about the person
   - Team documentation: team pages, org charts, role definitions
   - Code context: CODEOWNERS, MAINTAINERS, contribution patterns
   - Communication: PR reviews, issue comments, discussions
   - Metadata: user profiles, commit signatures, author headers

2) **Extract attribute signals**: Gather evidence of the specific attribute
   - Role indicators: title mentions, responsibility descriptions
   - Skill indicators: code languages used, areas modified, tools referenced
   - Team indicators: group memberships, communication channels
   - Expertise indicators: review patterns, depth of contributions

3) **Classify attribute value**: Determine the attribute's value
   - Match against known taxonomies (job titles, skill categories)
   - Infer from behavioral patterns
   - Cross-reference multiple sources

4) **Validate attribute assignment**: Confirm the attribution
   - Check for recency (attributes may have changed)
   - Verify consistency across sources
   - Consider explicit vs. inferred attributes

5) **Assess identification confidence**: Determine match quality
   - Exact: explicit attribute declaration in authoritative source
   - Probable: strong behavioral signals, consistent patterns
   - Possible: inferred from limited evidence
   - No match: insufficient evidence for attribution

6) **Ground claims**: Attach evidence anchors to identification
   - Format: `source:location` or `pattern:description`
   - Quote the specific evidence supporting attribution

7) **Format output**: Structure results according to the output contract

## Output Contract

Return a structured object:

```yaml
entity:
  id: string  # Person identifier
  type: human-attribute
  canonical_name: string  # Attribute name/value
  attributes:
    person_id: string  # Person this attribute belongs to
    attribute_type: string  # role, skill, team, expertise, preference
    attribute_value: string | array  # The identified value(s)
    scope: string | null  # Where this attribute applies
    confidence_level: string  # explicit, inferred, uncertain
    last_verified: string | null  # When attribute was last confirmed
  namespace: string | null  # Organization or project context
match_quality: exact | probable | possible | no_match
alternatives:
  - entity:
      canonical_name: string
      attributes:
        attribute_value: string
    probability: number  # 0.0-1.0
disambiguation_signals: array[string]  # Why this identification
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `entity` | object | The identified attribute with metadata |
| `match_quality` | enum | Confidence category for the identification |
| `alternatives` | array | Other possible attribute values |
| `disambiguation_signals` | array | Reasons supporting the identification |
| `confidence` | number | 0.0-1.0 numeric confidence score |
| `evidence_anchors` | array[string] | References to attribution evidence |
| `assumptions` | array[string] | Stated assumptions about the person |

## Examples

### Example 1: Identifying Team Role

**Input:**
```yaml
target: "jane.doe@company.com"
attribute_type: "role"
context: "/project/"
```

**Output:**
```yaml
entity:
  id: "jane.doe:role"
  type: human-attribute
  canonical_name: "Tech Lead"
  attributes:
    person_id: "jane.doe@company.com"
    attribute_type: "role"
    attribute_value: "Tech Lead"
    scope: "project/backend"
    confidence_level: "explicit"
    last_verified: "2024-01-10"
  namespace: "company/project"
match_quality: exact
alternatives:
  - entity:
      canonical_name: "Senior Engineer"
      attributes:
        attribute_value: "Senior Engineer"
    probability: 0.10
disambiguation_signals:
  - "CODEOWNERS lists jane.doe as tech lead for /backend"
  - "Team page shows 'Tech Lead - Backend' role"
  - "Approves all backend PRs"
confidence: 0.95
evidence_anchors:
  - "CODEOWNERS:15"
  - "docs/team.md:23"
  - "github:pulls:reviewer:jane.doe"
assumptions:
  - "CODEOWNERS reflects current team structure"
  - "Documentation is up to date"
```

**Evidence pattern:** Multi-source role verification.

---

### Example 2: Identifying Technical Skills

**Input:**
```yaml
target: "alex_dev"
attribute_type: "skill"
context: "github.com/org/repo"
```

**Output:**
```yaml
entity:
  id: "alex_dev:skills"
  type: human-attribute
  canonical_name: "Technical Skills"
  attributes:
    person_id: "alex_dev"
    attribute_type: "skill"
    attribute_value:
      - "Python (expert)"
      - "TypeScript (proficient)"
      - "PostgreSQL (proficient)"
      - "Docker (familiar)"
    scope: "github.com/org/repo"
    confidence_level: "inferred"
    last_verified: null
  namespace: "github/org"
match_quality: probable
alternatives:
  - entity:
      canonical_name: "Full Stack Developer"
      attributes:
        attribute_value: ["Python", "JavaScript", "SQL"]
    probability: 0.30
disambiguation_signals:
  - "75% of commits are Python files"
  - "15% of commits are TypeScript files"
  - "Database migrations and queries in contributions"
  - "Dockerfile modifications in 3 PRs"
confidence: 0.78
evidence_anchors:
  - "git:shortlog:--author=alex_dev"
  - "git:log:--stat:--author=alex_dev"
assumptions:
  - "Commit language distribution reflects skill level"
  - "More commits = higher proficiency"
  - "Recent activity more relevant than historical"
next_actions:
  - "Review user profile for self-declared skills"
  - "Check PR reviews for additional expertise indicators"
```

**Evidence pattern:** Contribution analysis for skill inference.

---

### Example 3: Identifying Team Membership

**Input:**
```yaml
target: "sam.security@company.com"
attribute_type: "team"
context: "organization"
```

**Output:**
```yaml
entity:
  id: "sam.security:team"
  type: human-attribute
  canonical_name: "Security Team"
  attributes:
    person_id: "sam.security@company.com"
    attribute_type: "team"
    attribute_value: "Security & Compliance"
    scope: "company-wide"
    confidence_level: "explicit"
    last_verified: "2024-01-15"
  namespace: "company"
match_quality: exact
alternatives:
  - entity:
      canonical_name: "Platform Team"
      attributes:
        attribute_value: "Platform Engineering"
    probability: 0.15
disambiguation_signals:
  - "Email domain pattern: security@company.com"
  - "Listed in security team directory"
  - "SECURITY.md contact for security issues"
  - "Reviews security-labeled PRs"
confidence: 0.94
evidence_anchors:
  - "SECURITY.md:contact"
  - "docs/teams/security.md:members"
assumptions:
  - "Email naming convention indicates team"
  - "Team directory is current"
```

**Evidence pattern:** Organizational documentation with naming pattern.

---

### Example 4: Identifying Expertise Area

**Input:**
```yaml
target: "maria.data"
attribute_type: "expertise"
context: "/data-platform/"
```

**Output:**
```yaml
entity:
  id: "maria.data:expertise"
  type: human-attribute
  canonical_name: "Data Engineering Expertise"
  attributes:
    person_id: "maria.data"
    attribute_type: "expertise"
    attribute_value:
      primary: "Data Pipeline Architecture"
      secondary: ["Apache Spark", "Airflow", "Data Modeling"]
    scope: "data-platform"
    confidence_level: "inferred"
    last_verified: null
  namespace: "company/data-platform"
match_quality: probable
alternatives:
  - entity:
      canonical_name: "ML Engineering"
      attributes:
        attribute_value:
          primary: "Machine Learning"
    probability: 0.20
disambiguation_signals:
  - "90% of contributions in /pipelines and /etl directories"
  - "Authored data pipeline design documents"
  - "Reviewed 85% of Spark-related PRs"
  - "Mentioned as subject matter expert in RFCs"
confidence: 0.82
evidence_anchors:
  - "git:log:--author=maria.data:pipelines/"
  - "docs/rfcs/data-pipeline-v2.md:author"
  - "github:pulls:reviewer:maria.data:label:spark"
assumptions:
  - "Contribution patterns indicate expertise"
  - "RFC authorship indicates deep expertise"
```

**Evidence pattern:** Deep contribution analysis with document attribution.

---

### Example 5: Unable to Identify Attribute

**Input:**
```yaml
target: "new.hire@company.com"
attribute_type: "expertise"
context: "/project/"
```

**Output:**
```yaml
entity:
  id: "new.hire:expertise"
  type: human-attribute
  canonical_name: "Unknown Expertise"
  attributes:
    person_id: "new.hire@company.com"
    attribute_type: "expertise"
    attribute_value: null
    scope: "project"
    confidence_level: "uncertain"
    last_verified: null
  namespace: "company/project"
match_quality: no_match
alternatives: []
disambiguation_signals:
  - "Only 2 commits in codebase (too few for analysis)"
  - "No PR reviews assigned"
  - "Not listed in team documentation"
  - "Account created recently"
confidence: 0.15
evidence_anchors:
  - "git:log:--author=new.hire"
assumptions:
  - "Limited history prevents accurate attribution"
  - "May be new team member"
next_actions:
  - "Wait for more contributions to analyze"
  - "Check onboarding documentation for role"
  - "Ask team lead for attribute information"
```

**Evidence pattern:** Insufficient data handling.

## Verification

- [ ] Attribute type is valid classification category
- [ ] Attribute value is derived from evidence
- [ ] Confidence level matches evidence quality
- [ ] Alternatives listed for probable/possible matches
- [ ] Scope is appropriate for the attribute

**Verification tools:** Read (for documentation inspection), Grep (for pattern search)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not identify sensitive personal attributes (health, religion, political views)
- Focus only on professional/organizational attributes
- Respect privacy preferences if explicitly stated
- Do not infer protected characteristics from available data
- If attribute identification could enable discrimination, stop and clarify purpose

## Composition Patterns

**Commonly follows:**
- `identify-person` - After identifying who someone is, determine their attributes
- `detect-person` - After confirming person presence, identify their characteristics

**Commonly precedes:**
- `compare-people` - When comparing attributes across individuals
- `estimate-activity` - When attributing activities based on expertise
- `plan` - When assigning tasks based on skills

**Anti-patterns:**
- Never use to identify attributes for discriminatory purposes
- Avoid attributing characteristics without sufficient evidence
- Do not infer sensitive attributes from professional data

**Workflow references:**
- See `workflow_catalog.json#team-mapping` for organizational attribute identification
- See `workflow_catalog.json#skill-matching` for expertise identification
