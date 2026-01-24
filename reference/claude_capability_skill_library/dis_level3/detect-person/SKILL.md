---
name: detect-person
description: Detect whether a person or person-like subject exists in the given data. Use when searching for human presence, checking for user involvement, validating authorship, or confirming person references.
argument-hint: "[target-data] [person-type] [detection-threshold]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Determine whether one or more persons (human actors, users, authors, contributors) are present or referenced in the target data. This is an existence check that answers "is there a person here?" rather than identifying who they are.

**Success criteria:**
- Binary detection result (detected/not detected) with supporting signals
- Evidence anchors pointing to specific locations where person indicators were found
- Confidence score reflecting signal strength and false-positive risk

**Compatible schemas:**
- `docs/schemas/detect_output.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | The data to scan for person presence (file path, text content, structured data) |
| `person_type` | No | string | Type of person to detect: author, user, contributor, actor, any (default: any) |
| `constraints` | No | object | Detection parameters: min_confidence, exclude_bots, require_name |
| `context` | No | string | Additional context about what constitutes a "person" in this domain |

## Procedure

1) **Scan for person indicators**: Search the target data for signals of human presence
   - Names, usernames, handles, email addresses
   - Author/contributor metadata fields
   - Personal pronouns in first-person context
   - Signature patterns, sign-offs
   - Git blame/commit author information

2) **Filter bot and system actors**: Distinguish human actors from automated ones
   - Check for bot indicators: `[bot]`, `dependabot`, `github-actions`
   - Look for automated commit patterns
   - Validate email domains against known automation services

3) **Assess signal strength**: Evaluate the quality of detected indicators
   - Strong signals: explicit name fields, verified author metadata
   - Medium signals: username references, email addresses
   - Weak signals: pronouns, indirect references

4) **Ground claims**: Attach evidence anchors to all detections
   - Format: `file:line`, `url`, or `tool:Grep:<pattern>`
   - Quote the specific text that indicates person presence

5) **Calculate false-positive risk**: Consider potential misidentifications
   - Generic names that could be system names
   - Test data or placeholder values
   - Historical/archived references vs. active actors

6) **Format output**: Structure results according to the output contract

## Output Contract

Return a structured object:

```yaml
detected: boolean  # True if person presence confirmed
target_type: person
instances:
  - id: string | null  # Identifier if extractable (username, email)
    type: string  # author, contributor, user, mentioned, etc.
    attributes:
      name: string | null
      email: string | null
      role: string | null
    location: string  # file:line or path reference
    confidence: number  # 0.0-1.0 for this specific instance
signals:
  - signal: string  # What was found
    strength: low | medium | high
    location: string  # Where it was found
false_positive_risk: low | medium | high
confidence: number  # 0.0-1.0 overall
evidence_anchors: array[string]
assumptions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `detected` | boolean | Whether any person was found |
| `instances` | array | List of detected person instances with details |
| `signals` | array | Raw indicators that suggest person presence |
| `false_positive_risk` | enum | Risk that detection is incorrect |
| `confidence` | number | 0.0-1.0 based on signal strength and count |
| `evidence_anchors` | array[string] | File:line references where persons were detected |
| `assumptions` | array[string] | Stated assumptions about person indicators |

## Examples

### Example 1: Detecting Author in Git Repository

**Input:**
```yaml
target: "/project/src/auth.py"
person_type: "author"
constraints:
  exclude_bots: true
```

**Output:**
```yaml
detected: true
target_type: person
instances:
  - id: "jane.developer@company.com"
    type: author
    attributes:
      name: "Jane Developer"
      email: "jane.developer@company.com"
      role: "primary author"
    location: "git:blame:auth.py:1-50"
    confidence: 0.95
signals:
  - signal: "Author header: # Author: Jane Developer"
    strength: high
    location: "auth.py:3"
  - signal: "Git blame shows consistent authorship"
    strength: high
    location: "git:blame:auth.py"
false_positive_risk: low
confidence: 0.92
evidence_anchors:
  - "auth.py:3"
  - "tool:Grep:Author:"
  - "git:blame:auth.py"
assumptions:
  - "Git history is authentic and not rewritten"
  - "Author header reflects actual authorship"
```

**Evidence pattern:** Combined file header inspection with git blame verification.

---

### Example 2: Detecting User Mentions in Log File

**Input:**
```yaml
target: "/var/log/app/access.log"
person_type: "user"
constraints:
  min_confidence: 0.7
```

**Output:**
```yaml
detected: true
target_type: person
instances:
  - id: "user_12345"
    type: user
    attributes:
      name: null
      email: null
      role: "authenticated user"
    location: "access.log:142"
    confidence: 0.75
  - id: "admin_jane"
    type: user
    attributes:
      name: null
      email: null
      role: "administrator"
    location: "access.log:89"
    confidence: 0.85
signals:
  - signal: "User ID in session: user_id=user_12345"
    strength: medium
    location: "access.log:142"
  - signal: "Admin action logged: admin_jane performed GRANT"
    strength: high
    location: "access.log:89"
false_positive_risk: medium
confidence: 0.80
evidence_anchors:
  - "access.log:142"
  - "access.log:89"
assumptions:
  - "User IDs represent actual human users, not service accounts"
  - "Log entries are not fabricated or test data"
```

**Evidence pattern:** Log parsing with user identifier extraction.

---

### Example 3: No Person Detected (Automated System)

**Input:**
```yaml
target: "/config/cron-jobs.yaml"
person_type: "any"
```

**Output:**
```yaml
detected: false
target_type: person
instances: []
signals:
  - signal: "Contains scheduler definitions only"
    strength: low
    location: "cron-jobs.yaml:1-45"
  - signal: "No author metadata present"
    strength: medium
    location: "cron-jobs.yaml"
false_positive_risk: low
confidence: 0.85
evidence_anchors:
  - "cron-jobs.yaml:1-45"
assumptions:
  - "Absence of person indicators means no person involvement"
  - "File was potentially auto-generated"
```

**Evidence pattern:** Exhaustive scan with negative result.

## Verification

- [ ] Output contains `detected` boolean field
- [ ] If detected=true, at least one instance with location is provided
- [ ] All evidence_anchors reference valid file:line locations
- [ ] Confidence score is justified by signal count and strength
- [ ] Bot/automation actors are correctly filtered when exclude_bots=true

**Verification tools:** Read (for file inspection), Grep (for pattern search)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Do not expose personally identifiable information (PII) beyond what's necessary for detection
- Do not store or log detected person information unnecessarily
- If detecting persons in sensitive contexts (HR, medical), note elevated privacy concerns
- Stop and request clarification if the detection could enable unwanted surveillance

## Composition Patterns

**Commonly follows:**
- `retrieve` - After fetching data that may contain person references
- `inspect` - After examining file structure to locate person-related fields

**Commonly precedes:**
- `identify-person` - When detection confirms presence, next step is identification
- `estimate-activity` - When tracking person-related activities

**Anti-patterns:**
- Never use to build surveillance profiles without explicit authorization
- Avoid combining with `generate-text` to fabricate person presence

**Workflow references:**
- See `workflow_catalog.json#author-attribution` for usage in authorship workflows
- See `workflow_catalog.json#access-audit` for user detection in logs
