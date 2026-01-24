---
name: summarize
description: Compress information into a decision-ready brief with key points and next actions. Use when condensing documents, creating executive summaries, or extracting actionable insights.
argument-hint: "[content] [max_length] [focus]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Compress content into a concise, decision-ready summary that preserves essential information while reducing volume. Highlight key points, actionable items, and critical context.

**Success criteria:**
- Essential information preserved
- Significant compression achieved
- Key points clearly highlighted
- Actionable items extracted
- Nothing critical omitted

**Compatible schemas:**
- `docs/schemas/summary_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `content` | Yes | string or object | Content to summarize (document, conversation, data) |
| `max_length` | No | string | Target length: sentence, paragraph, page (default: paragraph) |
| `focus` | No | string | What to emphasize (decisions, actions, risks, etc.) |
| `audience` | No | string | Who the summary is for |
| `preserve` | No | array | Specific topics that must be included |

## Procedure

1) **Analyze content structure**: Understand what is being summarized
   - Identify content type (document, conversation, analysis)
   - Determine hierarchical structure
   - Note length and complexity
   - Identify main sections or themes

2) **Extract key information**: Find essential content
   - Main conclusions or decisions
   - Critical data points
   - Action items and owners
   - Deadlines and constraints
   - Risks and concerns

3) **Identify themes**: Group related information
   - Cluster related points
   - Find overarching patterns
   - Note recurring concerns
   - Identify primary vs secondary topics

4) **Prioritize for inclusion**: Select what to keep
   - Mandatory: conclusions, decisions, actions
   - High priority: supporting evidence, risks
   - Lower priority: background, context, alternatives
   - Omit: redundancy, tangents, boilerplate

5) **Compress content**: Reduce while preserving meaning
   - Eliminate redundancy
   - Use concise phrasing
   - Combine related points
   - Remove filler words

6) **Structure output**: Organize for quick consumption
   - Lead with most important point
   - Group by theme or priority
   - Use parallel structure
   - Enable scanning

7) **Document omissions**: Note what was left out
   - Topics excluded and why
   - Nuance that was simplified
   - Details available in source

## Output Contract

Return a structured object:

```yaml
summary:
  brief: string  # 1-2 sentences capturing essence
  detailed: string  # Full summary at requested length
  key_points: array[string]  # Bullet points of main takeaways
  structure: string  # How content was organized
key_takeaways:
  - point: string  # Key takeaway
    importance: high | medium | low
    source_ref: string  # Where this came from
action_items:
  - action: string  # What needs to be done
    owner: string | null  # Who is responsible
    deadline: string | null  # When it's due
    priority: high | medium | low
omitted:
  - topic: string  # What was left out
    reason: string  # Why it was omitted
    source_ref: string  # Where to find full detail
metrics:
  original_length: integer  # Source length in words
  summary_length: integer  # Summary length in words
  compression_ratio: number  # Summary/original
  topics_covered: integer  # Number of topics
  topics_omitted: integer  # Number skipped
confidence: 0..1
evidence_anchors: ["source:section"]
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `summary` | object | Summarized content at multiple lengths |
| `key_takeaways` | array | Most important points |
| `action_items` | array | Extracted actions with owners |
| `omitted` | array | What was left out |
| `metrics` | object | Compression statistics |
| `confidence` | number | 0.0-1.0 based on completeness |
| `evidence_anchors` | array | Source references |

## Examples

### Example 1: Meeting Summary

**Input:**
```yaml
content: |
  Meeting: Q1 Planning Review
  Attendees: Alice (PM), Bob (Eng Lead), Carol (Design)
  Date: 2024-01-15

  Alice opened with Q1 roadmap review. Main items are auth service rewrite
  (Bob's team, 6 weeks), mobile redesign (Carol, 8 weeks), and API
  performance improvements (Bob, 4 weeks, lower priority).

  Bob raised concern about auth timeline - new requirements from security
  team add 2 weeks. Alice asked for formal estimate update by Friday.

  Carol presented mobile designs. Team liked direction but suggested
  simplifying onboarding flow. Carol will revise and present next week.

  Discussion about hiring - need 2 more engineers for Q2. Bob to draft
  job descriptions. Carol offered to help with portfolio review.

  Action: Alice to sync with security team on auth requirements.
  Action: Bob to send estimate update by Friday.
  Action: Carol to revise mobile designs for next meeting.
  Action: Bob to draft engineer job descriptions by end of month.
max_length: paragraph
focus: actions
```

**Output:**
```yaml
summary:
  brief: "Q1 planning reviewed auth rewrite (6+2 weeks due to security requirements), mobile redesign (8 weeks), and API improvements (4 weeks). Four action items assigned."
  detailed: |
    The Q1 planning meeting reviewed three main initiatives: auth service rewrite
    (6 weeks, Bob, plus 2 weeks for new security requirements), mobile redesign
    (8 weeks, Carol), and API performance improvements (4 weeks, lower priority).
    The auth timeline concern requires Alice to sync with security and Bob to
    provide updated estimates by Friday. Carol will revise simplified mobile
    designs for next week. Team also agreed to hire 2 engineers for Q2, with
    Bob drafting job descriptions.
  key_points:
    - "Auth rewrite timeline extended by 2 weeks for security requirements"
    - "Mobile redesign approved in concept, onboarding simplification requested"
    - "Need 2 engineers for Q2"
    - "API improvements deprioritized to lower priority"
  structure: "Organized by initiative, then actions"
key_takeaways:
  - point: "Auth rewrite now 8 weeks total (was 6)"
    importance: high
    source_ref: "Bob's timeline concern"
  - point: "Mobile design direction approved with revisions needed"
    importance: medium
    source_ref: "Carol's presentation"
  - point: "Q2 hiring need identified"
    importance: medium
    source_ref: "Hiring discussion"
action_items:
  - action: "Sync with security team on auth requirements"
    owner: "Alice"
    deadline: null
    priority: high
  - action: "Send updated auth estimate"
    owner: "Bob"
    deadline: "Friday"
    priority: high
  - action: "Revise mobile designs (simplify onboarding)"
    owner: "Carol"
    deadline: "Next meeting"
    priority: medium
  - action: "Draft engineer job descriptions"
    owner: "Bob"
    deadline: "End of month"
    priority: medium
omitted:
  - topic: "Specific mobile design feedback details"
    reason: "Summarized as 'simplify onboarding'"
    source_ref: "Carol's presentation discussion"
  - topic: "Carol's offer to help with portfolio review"
    reason: "Minor detail, not action item"
    source_ref: "Hiring discussion"
metrics:
  original_length: 187
  summary_length: 89
  compression_ratio: 0.48
  topics_covered: 4
  topics_omitted: 2
confidence: 0.95
evidence_anchors:
  - "meeting:q1-planning:2024-01-15"
assumptions:
  - "All stated deadlines are firm"
  - "Priorities reflect consensus"
```

**Evidence pattern:** Actions extracted with owners and deadlines, compression ratio documented.

---

### Example 2: Document Summary

**Input:**
```yaml
content: "[Technical RFC document - 2500 words about API versioning strategy]"
max_length: paragraph
focus: decisions
preserve: ["breaking changes", "timeline"]
```

**Output:**
```yaml
summary:
  brief: "RFC proposes URL-based API versioning (v1, v2) with 6-month deprecation windows. Breaking changes require new major version."
  detailed: |
    The RFC recommends URL-based versioning (e.g., /api/v1/, /api/v2/) over header-based
    approaches for clarity and caching benefits. Breaking changes—defined as removed
    endpoints, changed field types, or new required parameters—trigger new major versions.
    Non-breaking additions can occur within versions. Deprecated versions receive 6-month
    sunset windows with 90-day advance notice. Migration guides will accompany each
    major version. Implementation targets Q2 2024 with v2 launch.
  key_points:
    - "URL-based versioning chosen over headers for simplicity"
    - "Breaking changes require new major version"
    - "6-month deprecation window with 90-day notice"
    - "v2 launch targeted for Q2 2024"
  structure: "Organized by decision hierarchy"
key_takeaways:
  - point: "URL versioning is the chosen approach"
    importance: high
    source_ref: "RFC section 3.1"
  - point: "Breaking changes strictly defined"
    importance: high
    source_ref: "RFC section 4"
  - point: "6-month deprecation window is policy"
    importance: high
    source_ref: "RFC section 5"
action_items:
  - action: "Implement v2 infrastructure"
    owner: "Platform team"
    deadline: "Q2 2024"
    priority: high
  - action: "Create migration guide template"
    owner: "Docs team"
    deadline: "Before v2 launch"
    priority: medium
omitted:
  - topic: "Header versioning analysis"
    reason: "Alternative not chosen, details not relevant to decision"
    source_ref: "RFC section 3.2"
  - topic: "Historical versioning issues"
    reason: "Background context, not decision-relevant"
    source_ref: "RFC section 1"
metrics:
  original_length: 2500
  summary_length: 120
  compression_ratio: 0.048
  topics_covered: 5
  topics_omitted: 4
confidence: 0.9
evidence_anchors:
  - "rfc:api-versioning:section-3.1"
  - "rfc:api-versioning:section-4"
  - "rfc:api-versioning:section-5"
assumptions:
  - "Decisions in RFC are final"
```

## Verification

- [ ] Summary captures main points
- [ ] Compression meets target length
- [ ] No critical information omitted
- [ ] Action items extracted correctly
- [ ] Omissions documented

**Verification tools:** Read (for source comparison)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Never omit safety-critical information
- Always note if summary may miss nuance
- Flag if content seems incomplete
- Preserve precise numbers and dates
- Do not inject opinions into factual summaries

## Composition Patterns

**Commonly follows:**
- `retrieve` - Summarize retrieved content
- `explain` - Condense explanations
- `critique` - Summarize findings
- `analyze` - Summarize analysis

**Commonly precedes:**
- `decide` - Use summary to inform decisions
- `send` - Share summary externally
- `persist` - Store summary for reference

**Anti-patterns:**
- Never summarize without reading full content
- Avoid over-compression that loses meaning
- Never assume context the reader won't have

**Workflow references:**
- See `composition_patterns.md#world-model-build` for summarize as final step
