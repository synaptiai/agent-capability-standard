---
name: identify-person
description: Identify and classify a person (role, identity proxy, or contributor) from available evidence. Use when determining who someone is, classifying roles, resolving identity references, or attributing actions to individuals.
argument-hint: "[target-person] [identification-context] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Classify and name a person based on available evidence, determining who they are within the given context. This answers "what/who is this person?" rather than just confirming person presence.

**Success criteria:**
- Clear identification with canonical name/identifier
- Match quality assessment (exact, probable, possible, no match)
- Alternative identifications with probabilities when uncertain
- Disambiguation signals explaining the identification rationale

**Compatible schemas:**
- `docs/schemas/identify_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | The person reference to identify (name, username, email, partial info) |
| `context` | No | string\|object | Context for identification (codebase, organization, project) |
| `constraints` | No | object | Identification parameters: max_alternatives, require_verification, privacy_level |

## Procedure

1) **Extract person signals**: Gather all available identifiers from the target
   - Names: full name, display name, aliases
   - Handles: usernames, email addresses, social identifiers
   - Metadata: timestamps, locations, affiliations
   - Relationships: mentioned alongside, co-authors, team references

2) **Search for matching identities**: Look for corresponding person records
   - Git history: commit authors, blame records
   - Configuration files: CODEOWNERS, MAINTAINERS, AUTHORS
   - Documentation: contributor lists, team pages
   - Comments: @mentions, signatures

3) **Correlate identity signals**: Match extracted signals to candidates
   - Email domain matching
   - Username pattern correlation
   - Name similarity scoring
   - Temporal overlap (active periods)

4) **Assess match quality**: Determine confidence in identification
   - Exact: multiple strong signals agree
   - Probable: primary signals match, minor ambiguities
   - Possible: weak signals or multiple candidates
   - No match: insufficient evidence for identification

5) **Generate alternatives**: List other possible identifications when uncertain
   - Rank by probability
   - Note distinguishing factors between candidates
   - Identify what additional information would resolve ambiguity

6) **Ground claims**: Attach evidence anchors to identification
   - Format: `file:line`, `git:commit:hash`, or `config:path`
   - Quote the specific evidence supporting identification

7) **Format output**: Structure results according to the output contract

## Output Contract

Return a structured object:

```yaml
entity:
  id: string  # Canonical identifier (email, username)
  type: person
  canonical_name: string  # Display name
  attributes:
    email: string | null
    username: string | null
    role: string | null
    organization: string | null
    active: boolean | null
  namespace: string | null  # Organization or project context
match_quality: exact | probable | possible | no_match
alternatives:
  - entity:
      id: string
      type: person
      canonical_name: string
      attributes: object
    probability: number  # 0.0-1.0
disambiguation_signals: array[string]  # Why this identification
confidence: number  # 0.0-1.0
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `entity` | object | The identified person with attributes |
| `match_quality` | enum | Confidence category for the identification |
| `alternatives` | array | Other possible identifications with probabilities |
| `disambiguation_signals` | array | Reasons supporting the primary identification |
| `confidence` | number | 0.0-1.0 numeric confidence score |
| `evidence_anchors` | array[string] | References to identification evidence |
| `assumptions` | array[string] | Stated assumptions about identity matching |

## Examples

### Example 1: Identifying Git Commit Author

**Input:**
```yaml
target:
  email: "jdoe@company.com"
  commit_hash: "abc123"
context: "/project/"
```

**Output:**
```yaml
entity:
  id: "jane.doe@company.com"
  type: person
  canonical_name: "Jane Doe"
  attributes:
    email: "jane.doe@company.com"
    username: "jdoe"
    role: "Senior Engineer"
    organization: "Company Inc."
    active: true
  namespace: "company/project"
match_quality: exact
alternatives: []
disambiguation_signals:
  - "Email jdoe@company.com is alias for jane.doe@company.com (mailmap)"
  - "Git author 'Jane Doe' matches CODEOWNERS entry"
  - "Consistent commit history over 2 years"
confidence: 0.96
evidence_anchors:
  - ".mailmap:12"
  - "CODEOWNERS:5"
  - "git:log:--author=jdoe"
assumptions:
  - ".mailmap contains authoritative email mappings"
  - "CODEOWNERS reflects current team structure"
```

**Evidence pattern:** Email correlation with mailmap and CODEOWNERS verification.

---

### Example 2: Identifying Ambiguous Contributor

**Input:**
```yaml
target:
  name: "Alex Chen"
context: "github.com/org/repo"
constraints:
  max_alternatives: 3
```

**Output:**
```yaml
entity:
  id: "alex.chen.dev@gmail.com"
  type: person
  canonical_name: "Alex Chen"
  attributes:
    email: "alex.chen.dev@gmail.com"
    username: "alexc-dev"
    role: "contributor"
    organization: null
    active: true
  namespace: "github.com/org/repo"
match_quality: probable
alternatives:
  - entity:
      id: "achen@company.org"
      type: person
      canonical_name: "Alexander Chen"
      attributes:
        email: "achen@company.org"
        username: "achen"
        role: "maintainer"
        organization: "Company Org"
        active: true
    probability: 0.25
  - entity:
      id: "alex.chen@university.edu"
      type: person
      canonical_name: "Alex Chen"
      attributes:
        email: "alex.chen@university.edu"
        username: "alexchen"
        role: "contributor"
        organization: "University"
        active: false
    probability: 0.10
disambiguation_signals:
  - "Most recent commits (last 30 days) use alex.chen.dev@gmail.com"
  - "Username alexc-dev appears in issue discussions"
  - "Alternative achen@company.org has no commits in past 6 months"
confidence: 0.70
evidence_anchors:
  - "git:log:--since=30d:--author=Alex"
  - "github:issues:mentions:alexc-dev"
  - "CONTRIBUTORS.md:23"
assumptions:
  - "Most recent activity indicates current identity"
  - "Multiple Alex Chens may contribute to this repo"
next_actions:
  - "Check PR author for specific contribution to confirm"
  - "Review GitHub profile for definitive identification"
```

**Evidence pattern:** Name disambiguation with activity analysis.

---

### Example 3: No Match Found

**Input:**
```yaml
target:
  username: "ghost_user_xyz"
context: "/project/"
```

**Output:**
```yaml
entity:
  id: null
  type: person
  canonical_name: "Unknown (ghost_user_xyz)"
  attributes:
    email: null
    username: "ghost_user_xyz"
    role: null
    organization: null
    active: null
  namespace: null
match_quality: no_match
alternatives: []
disambiguation_signals:
  - "Username not found in git history"
  - "No matching entry in CODEOWNERS or CONTRIBUTORS"
  - "No @mentions in issues or pull requests"
confidence: 0.15
evidence_anchors:
  - "tool:Grep:ghost_user_xyz:."
  - "git:log:--all"
assumptions:
  - "Username should appear somewhere if person contributed"
  - "May be deleted account or typo"
next_actions:
  - "Check if username is a typo (similar usernames exist?)"
  - "Search organization directory if available"
  - "Verify username source is accurate"
```

**Evidence pattern:** Exhaustive search with negative result.

---

### Example 4: Identifying Role from Code Pattern

**Input:**
```yaml
target:
  file_pattern: "security/*.py"
  action: "primary maintainer"
context: "/project/"
```

**Output:**
```yaml
entity:
  id: "security-lead@company.com"
  type: person
  canonical_name: "Sam Security"
  attributes:
    email: "security-lead@company.com"
    username: "samsec"
    role: "Security Lead"
    organization: "Company Security Team"
    active: true
  namespace: "company/project/security"
match_quality: probable
alternatives:
  - entity:
      id: "dev2@company.com"
      type: person
      canonical_name: "Junior Dev"
      attributes:
        email: "dev2@company.com"
        username: "jdev"
        role: "developer"
    probability: 0.15
disambiguation_signals:
  - "80% of commits to security/*.py by samsec"
  - "Listed as security team lead in CODEOWNERS"
  - "Approves all security-related PRs"
confidence: 0.85
evidence_anchors:
  - "git:shortlog:security/"
  - "CODEOWNERS:security/*"
  - "github:pulls:reviewer:samsec"
assumptions:
  - "Commit frequency indicates maintainership"
  - "CODEOWNERS accurately reflects responsibility"
```

**Evidence pattern:** Ownership analysis from contribution patterns.

## Verification

- [ ] Entity has valid id or explicit null with explanation
- [ ] Match quality accurately reflects evidence strength
- [ ] Alternatives listed when match_quality is not "exact"
- [ ] Disambiguation signals explain the identification rationale
- [ ] Evidence anchors reference actual identity sources

**Verification tools:** Read (for file inspection), Grep (for identity search)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not expose sensitive personal information beyond what's necessary for identification
- Do not attempt to identify persons in contexts where privacy is expected
- Distinguish between public identities (open source contributors) and private individuals
- If identification could enable unwanted contact or harassment, stop and request clarification
- Respect "do not contact" or privacy preferences if found

## Composition Patterns

**Commonly follows:**
- `detect-person` - After confirming person presence, identify who they are
- `retrieve` - After fetching data containing person references

**Commonly precedes:**
- `estimate-activity` - When attributing activities to identified persons
- `compare-people` - When comparing identified individuals

**Anti-patterns:**
- Never use to build profiles for unauthorized surveillance
- Avoid identifying persons for purposes of harassment or discrimination

**Workflow references:**
- See `workflow_catalog.json#contributor-attribution` for authorship identification
- See `workflow_catalog.json#team-mapping` for organizational identification
