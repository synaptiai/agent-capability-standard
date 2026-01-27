# Personal Assistant Domain

This document describes how to use the Grounded Agency framework for personal productivity assistants.

## Overview

The personal assistant domain profile is calibrated for environments where:
- **User intent is paramount** — Explicit user instructions have highest trust
- **Communication is sensitive** — All messages require user approval before sending
- **Preferences evolve** — Learned patterns inform but don't override user
- **Privacy matters** — User data sharing requires explicit consent

## Domain Profile

**Profile location:** `schemas/profiles/personal_assistant.yaml`

### Trust Weights

Personal assistants trust user signals over external sources:

| Source | Trust Weight | Rationale |
|--------|-------------|-----------|
| User Explicit | 0.98 | Direct user instruction |
| User Calendar | 0.95 | User's own data |
| User Preference | 0.92 | Learned patterns |
| Calendar API | 0.90 | System data, verified |
| Email System | 0.88 | User's communications |
| Task System | 0.88 | User's task data |
| Pattern Inference | 0.72 | Inferred, less certain |
| Public API | 0.70 | External, general trust |
| Web Search | 0.60 | Internet, varying quality |
| News Feed | 0.55 | News aggregation, potential bias |

### Risk Thresholds

```yaml
auto_approve: low       # Low-risk can be auto-approved
require_review: medium  # Medium requires user confirmation
require_human: high     # High-risk requires explicit user action
block_autonomous:
  - send                # Never send communications autonomously
  - mutate              # Never modify external systems autonomously
```

### Checkpoint Policy

Personal assistants require checkpoints before:
- Sending any message or communication
- Modifying calendar events
- Delegating tasks to others
- Making purchases
- Sharing user data with third parties

## Available Workflows

### 1. Schedule Management

**Goal:** Analyze scheduling requests, resolve conflicts, and propose calendar changes.

**Capabilities used:**
- `retrieve` — Get user's current calendar
- `critique` — Analyze request for ambiguity
- `inquire` — Clarify if needed
- `detect` — Identify conflicts
- `search` — Find available slots
- `compare` — Rank by user preference
- `plan` — Create modification plan
- `generate` — Create event draft
- `explain` — Summarize for user
- `audit` — Record interaction

**Trigger:** User scheduling request

**Output:** Calendar event draft for user approval

### 2. Information Research

**Goal:** Research a topic and synthesize findings with citations.

**Capabilities used:**
- `decompose` — Break into sub-questions
- `search` — Query web and local documents
- `retrieve` — Fetch full content
- `classify` — Assess source credibility
- `detect` — Identify key facts
- `compare` — Cross-reference sources
- `integrate` — Merge verified facts
- `ground` — Anchor to citations
- `generate` — Synthesize summary
- `audit` — Record research session

**Trigger:** User question or research request

**Output:** Grounded summary with citations

### 3. Task Delegation

**Goal:** Decompose complex tasks and prepare delegation requests.

**Capabilities used:**
- `decompose` — Break into subtasks
- `classify` — Identify executor type
- `search` — Find available executors
- `compare` — Rank by suitability
- `plan` — Create delegation plan
- `generate` — Create delegation requests
- `checkpoint` — Checkpoint before action
- `explain` — Summarize plan for user
- `audit` — Record planning session

**Trigger:** Complex task from user

**Output:** Delegation plan for user approval

### 4. Communication Drafting

**Goal:** Draft messages based on user intent and context.

**Capabilities used:**
- `critique` — Analyze communication intent
- `inquire` — Clarify if ambiguous
- `search` — Find prior communications
- `retrieve` — Get recipient info
- `recall` — Get user style preferences
- `generate` — Draft the message
- `critique` — Review draft quality
- `transform` — Apply corrections
- `checkpoint` — Checkpoint before presenting
- `audit` — Record drafting session

**Trigger:** User communication request

**Output:** Message draft for user approval

## Customization Guide

### Personalizing Trust Weights

Adjust based on your data source reliability:

```yaml
trust_weights:
  # If you heavily rely on a specific calendar service
  calendar_api: 0.95

  # If you trust your note-taking app
  notes_app: 0.88

  # If you have a curated news source
  trusted_news: 0.75
```

### Communication Preferences

Set default communication style:

```yaml
communication_preferences:
  tone: professional  # or casual, friendly, formal
  formality: medium   # low, medium, high
  signature: true
  default_format: plain_text  # or html
```

### Privacy Settings

Control what data can be shared:

```yaml
privacy_policy:
  share_calendar: ask_always   # or allow_trusted, deny
  share_contacts: ask_always
  share_location: deny
  share_documents: ask_always
```

## Integration Examples

### With Calendar Services

```yaml
# Google Calendar integration
retrieve:
  target: google_calendar://primary
  format: calendar_events
  range: ${request.date_range}
```

### With Email

```yaml
# Email context for communication drafting
search:
  query: ${recipient}
  scope: email_threads
  limit: 10
```

### With Task Managers

```yaml
# Todoist integration
search:
  query: pending_tasks
  scope: todoist://projects/*
```

## Privacy Considerations

1. **Never auto-send** any communication without user approval
2. **Never share** user data without explicit consent
3. **Ground claims** about user preferences to actual data
4. **Audit all** interactions for user review
5. **Allow user** to correct learned preferences

## User Experience Patterns

### Clarification Best Practices

When using `inquire`:
- Limit to 2-3 questions maximum
- Provide default suggestions
- Explain why clarification helps

### Draft Presentation

When presenting drafts:
- Show the full draft
- Highlight uncertain elements
- Offer easy edit affordances
- Never auto-send on timeout

## Related Documentation

- [Profile Schema](../../../schemas/profiles/profile_schema.yaml)
- [Personal Assistant Workflows](../../../schemas/workflows/personal_assistant_workflows.yaml)
- [Capability Ontology](../../../schemas/capability_ontology.yaml)
