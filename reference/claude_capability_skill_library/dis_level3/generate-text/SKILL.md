---
name: generate-text
description: Generate text artifacts under constraints including tone, format, audience, and safety requirements. Use when creating documents, messages, content, or any textual output.
argument-hint: "[purpose] [constraints] [format]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Create textual content that satisfies specified constraints around purpose, audience, tone, format, and safety while maintaining quality and appropriateness standards.

**Success criteria:**
- Generated text meets all explicit constraints
- Tone and style appropriate for audience
- Format follows specified structure
- Safety considerations addressed and documented

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `purpose` | Yes | string | What the text is for (email, documentation, marketing, etc.) |
| `constraints` | No | object | Requirements: tone, length, format, forbidden topics |
| `audience` | No | string | Target audience for the text |
| `context` | No | string\|object | Background information to inform content |
| `examples` | No | array[string] | Example texts for style matching |
| `template` | No | string | Template or structure to follow |

## Procedure

1) **Clarify purpose and constraints**: Understand the request fully
   - What is the text for?
   - Who is the audience?
   - What tone is appropriate?
   - What must be included/excluded?

2) **Gather relevant context**: If context sources provided
   - Read reference materials
   - Extract key facts and themes
   - Note style patterns from examples

3) **Plan structure**: Outline before writing
   - Identify main sections/points
   - Determine logical flow
   - Allocate approximate length per section

4) **Generate content**: Write following constraints
   - Match specified tone and voice
   - Include required elements
   - Avoid forbidden topics or approaches
   - Maintain consistency throughout

5) **Verify constraints**: Check all requirements met
   - Length within bounds
   - Tone consistent
   - All required elements present
   - No constraint violations

6) **Document safety considerations**: Note what was avoided
   - Potentially sensitive topics handled carefully
   - Audience-inappropriate content excluded
   - Misleading or harmful content avoided

## Output Contract

Return a structured object:

```yaml
artifact:
  type: text
  content: string  # The generated text
  format: string  # markdown, plain, html, etc.
  metadata:
    word_count: integer
    reading_level: string | null
    sections: array[string] | null
constraints_used:
  - constraint: string
    satisfied: boolean
    notes: string | null
rationale: string  # Why this approach was chosen
alternatives_considered: array[string]
quality_signals:
  - metric: string
    value: string | number
confidence: number
evidence_anchors: array[string]
assumptions: array[string]
safety_notes: array[string]
next_actions: array[string]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `artifact` | object | Generated text with metadata |
| `constraints_used` | array | How each constraint was addressed |
| `rationale` | string | Explanation of generation approach |
| `alternatives_considered` | array | Other approaches not taken |
| `quality_signals` | array | Quality metrics |
| `confidence` | number | 0.0-1.0 confidence in output quality |
| `evidence_anchors` | array[string] | Source references used |
| `assumptions` | array[string] | Explicitly stated assumptions |
| `safety_notes` | array[string] | Safety considerations addressed |
| `next_actions` | array[string] | Suggested follow-ups |

## Examples

### Example 1: Generating Technical Documentation

**Input:**
```yaml
purpose: "API endpoint documentation"
constraints:
  format: "OpenAPI-style markdown"
  tone: "technical but accessible"
  length: "200-400 words"
  required_sections:
    - "Description"
    - "Parameters"
    - "Response"
    - "Example"
audience: "Developers integrating with the API"
context:
  endpoint: "POST /api/v1/users"
  functionality: "Creates a new user account"
  auth_required: true
```

**Output:**
```yaml
artifact:
  type: text
  content: |
    ## POST /api/v1/users

    ### Description

    Creates a new user account in the system. This endpoint requires authentication
    and appropriate permissions. The newly created user will receive a verification
    email to the provided address.

    ### Authentication

    Required. Include a valid Bearer token in the Authorization header:
    ```
    Authorization: Bearer <your_api_token>
    ```

    ### Parameters

    | Parameter | Type | Required | Description |
    |-----------|------|----------|-------------|
    | `email` | string | Yes | User's email address (must be unique) |
    | `name` | string | Yes | User's display name (2-100 characters) |
    | `role` | string | No | Initial role assignment (default: "member") |
    | `metadata` | object | No | Custom key-value pairs for user |

    ### Response

    **Success (201 Created)**
    ```json
    {
      "id": "usr_abc123",
      "email": "user@example.com",
      "name": "Jane Developer",
      "role": "member",
      "created_at": "2024-01-15T10:30:00Z",
      "verified": false
    }
    ```

    **Error Responses**
    - `400 Bad Request` - Invalid parameters
    - `401 Unauthorized` - Missing or invalid token
    - `409 Conflict` - Email already exists

    ### Example

    ```bash
    curl -X POST https://api.example.com/api/v1/users \
      -H "Authorization: Bearer your_token" \
      -H "Content-Type: application/json" \
      -d '{"email": "new@example.com", "name": "New User"}'
    ```
  format: markdown
  metadata:
    word_count: 287
    reading_level: "technical"
    sections:
      - "Description"
      - "Authentication"
      - "Parameters"
      - "Response"
      - "Example"
constraints_used:
  - constraint: "format: OpenAPI-style markdown"
    satisfied: true
    notes: "Used standard API documentation structure with tables and code blocks"
  - constraint: "tone: technical but accessible"
    satisfied: true
    notes: "Balanced technical accuracy with clear explanations"
  - constraint: "length: 200-400 words"
    satisfied: true
    notes: "287 words within specified range"
  - constraint: "required_sections present"
    satisfied: true
    notes: "All required sections included, plus Authentication section"
rationale: "Followed industry-standard API documentation format. Added Authentication section since endpoint requires auth. Used tables for parameters for easy scanning."
alternatives_considered:
  - "More verbose descriptions - rejected for conciseness"
  - "Multiple example scenarios - deferred to keep within length"
  - "Error code explanations - kept minimal, can expand if needed"
quality_signals:
  - metric: "Completeness"
    value: "high - covers all standard API doc sections"
  - metric: "Scannability"
    value: "high - clear headers, tables, code blocks"
  - metric: "Copy-paste readiness"
    value: "high - curl example is executable"
confidence: 0.9
evidence_anchors:
  - "context:endpoint specification"
assumptions:
  - "Standard REST API conventions apply"
  - "Bearer token authentication is the auth mechanism"
  - "Email verification is automatic on creation"
safety_notes:
  - "Did not include actual API tokens or credentials"
  - "Used placeholder URLs and tokens"
  - "No sensitive data in examples"
next_actions:
  - "Add rate limiting documentation if applicable"
  - "Create additional error scenario examples"
  - "Link to authentication setup guide"
```

**Evidence pattern:** Context extraction + constraint application + format templating

## Verification

- [ ] All required sections present
- [ ] Length within specified bounds
- [ ] Tone appropriate for audience
- [ ] No forbidden content included
- [ ] Format matches specification

**Verification tools:** Read (for context sources)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Never generate content that could mislead or harm
- Avoid generating credentials, PII, or sensitive data
- Flag when requested content may be inappropriate
- Maintain accuracy for factual content
- Clearly mark speculative or creative content
- Stop if asked to generate deceptive content

## Composition Patterns

**Commonly follows:**
- `retrieve` - to gather context for generation
- `summarize` - to condense source material
- `search` - to find relevant examples or templates

**Commonly precedes:**
- `verify` - to check generated content accuracy
- `critique` - to review generated content quality
- `transform` - to convert format

**Anti-patterns:**
- Never generate without understanding purpose
- Avoid generating sensitive content without explicit approval

**Workflow references:**
- See `workflow_catalog.json#documentation_creation` for doc workflows
- See `workflow_catalog.json#content_pipeline` for content generation
