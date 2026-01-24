---
name: translate
description: Convert between natural languages, formal notations, or technical registers while preserving meaning. Use when localizing content, converting specifications, or adapting communication style.
argument-hint: "[source] [target_format] [context]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Convert content from one language, notation, or register to another while preserving semantic meaning, intent, and key nuances. Handle both linguistic and technical translations.

**Success criteria:**
- Meaning preserved accurately
- Target format conventions followed
- Nuance and tone appropriate
- Ambiguities flagged or resolved
- Translation is usable without original

**Compatible schemas:**
- `docs/schemas/translation_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `source` | Yes | string | Content to translate |
| `source_format` | No | string | Format/language of source |
| `target_format` | Yes | string | Target format/language |
| `context` | No | object | Domain, audience, purpose |
| `preserve` | No | array | Elements to keep unchanged (names, code) |
| `style` | No | string | Target style (formal, casual, technical) |

## Procedure

1) **Analyze source**: Understand the original content
   - Identify source format/language
   - Parse structure and elements
   - Note key concepts and terminology
   - Identify idioms or domain-specific usage

2) **Understand context**: Calibrate translation approach
   - Target audience expertise level
   - Purpose of the translation
   - Required formality level
   - Domain-specific conventions

3) **Identify challenges**: Note translation difficulties
   - Ambiguous terms
   - Untranslatable concepts
   - Culture-specific references
   - Format mismatches

4) **Map concepts**: Find target equivalents
   - Direct translations for clear mappings
   - Paraphrases for complex concepts
   - Explanatory notes for untranslatable items
   - Preserve elements marked for preservation

5) **Execute translation**: Convert content
   - Maintain source structure where possible
   - Apply target format conventions
   - Adapt tone and style appropriately
   - Handle edge cases consistently

6) **Verify accuracy**: Check translation quality
   - Meaning preserved?
   - No information lost?
   - Target conventions followed?
   - Readability appropriate?

7) **Document decisions**: Note translation choices
   - Difficult translations and rationale
   - Alternatives considered
   - Limitations of the translation
   - Items needing review

## Output Contract

Return a structured object:

```yaml
translation:
  source_format: string
  target_format: string
  content: string  # Translated content
  style: string  # Style applied
translation_notes:
  - source_segment: string
    target_segment: string
    note: string  # Explanation of choice
    alternatives: array[string]
preserved_elements:
  - element: string
    reason: string
challenges:
  - type: ambiguity | untranslatable | format_mismatch | cultural
    description: string
    resolution: string
    confidence: number
quality:
  semantic_accuracy: number  # 0-100
  style_match: number  # 0-100
  completeness: number  # 0-100
  overall: number  # 0-100
verification:
  back_translation_sample: string | null
  key_terms_verified: boolean
confidence: 0..1
evidence_anchors: ["source:segment", "reference:glossary"]
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `translation` | object | Main translation output |
| `translation_notes` | array | Notable translation decisions |
| `preserved_elements` | array | Items kept unchanged |
| `challenges` | array | Difficulties encountered |
| `quality` | object | Quality metrics |
| `verification` | object | Verification information |
| `confidence` | number | 0.0-1.0 overall confidence |

## Examples

### Example 1: Technical Documentation Translation

**Input:**
```yaml
source: |
  The API endpoint accepts POST requests with JSON payloads.
  Authentication is via Bearer tokens in the Authorization header.
  Rate limiting: 100 requests per minute per API key.
source_format: "english_technical"
target_format: "spanish_technical"
context:
  audience: "developers"
  domain: "API documentation"
preserve: ["API", "POST", "JSON", "Bearer", "Authorization"]
```

**Output:**
```yaml
translation:
  source_format: "english_technical"
  target_format: "spanish_technical"
  content: |
    El endpoint del API acepta solicitudes POST con cargas JSON.
    La autenticacion se realiza mediante tokens Bearer en el encabezado Authorization.
    Limite de velocidad: 100 solicitudes por minuto por clave de API.
  style: "technical_formal"
translation_notes:
  - source_segment: "Rate limiting"
    target_segment: "Limite de velocidad"
    note: "Common technical translation; 'limitacion de tasa' also acceptable"
    alternatives: ["limitacion de tasa", "control de velocidad"]
  - source_segment: "payloads"
    target_segment: "cargas"
    note: "'cargas utiles' is more literal but 'cargas' is common in tech Spanish"
    alternatives: ["cargas utiles", "datos de carga"]
preserved_elements:
  - element: "API"
    reason: "Universal technical term"
  - element: "POST"
    reason: "HTTP method name (preserve exactly)"
  - element: "JSON"
    reason: "Technical standard name"
  - element: "Bearer"
    reason: "OAuth token type (preserve exactly)"
  - element: "Authorization"
    reason: "HTTP header name (preserve exactly)"
challenges:
  - type: format_mismatch
    description: "Diacritics needed in Spanish (autenticacion)"
    resolution: "Added proper Spanish diacritics"
    confidence: 0.95
quality:
  semantic_accuracy: 95
  style_match: 90
  completeness: 100
  overall: 93
verification:
  back_translation_sample: "The API endpoint accepts POST requests with JSON payloads..."
  key_terms_verified: true
confidence: 0.92
evidence_anchors:
  - "source:api-documentation"
  - "reference:tech-spanish-glossary"
assumptions:
  - "Target audience familiar with English technical terms"
  - "Latin American Spanish preferred over Castilian"
```

**Evidence pattern:** Preserved terms documented, translation choices explained.

---

### Example 2: Code Comment to Formal Specification

**Input:**
```yaml
source: |
  // Make sure user is logged in before doing anything
  // Also check they have permission for this action
  // Return 403 if not, 200 if ok
source_format: "code_comment_informal"
target_format: "formal_specification"
context:
  domain: "access control"
  style: "specification"
```

**Output:**
```yaml
translation:
  source_format: "code_comment_informal"
  target_format: "formal_specification"
  content: |
    ## Access Control Requirements

    ### Preconditions
    1. User MUST be authenticated (valid session exists)
    2. User MUST possess required permission for the requested action

    ### Behavior
    - On authentication failure: Return HTTP 403 Forbidden
    - On authorization failure: Return HTTP 403 Forbidden
    - On success: Return HTTP 200 OK

    ### Notes
    - Authentication check MUST precede authorization check
    - Specific permission requirements defined per-endpoint
  style: "formal_specification"
translation_notes:
  - source_segment: "logged in"
    target_segment: "authenticated (valid session exists)"
    note: "Clarified informal 'logged in' to formal authentication terminology"
    alternatives: []
  - source_segment: "doing anything"
    target_segment: "requested action"
    note: "Vague 'anything' specified as 'requested action'"
    alternatives: ["subsequent operations", "protected resource access"]
  - source_segment: "have permission"
    target_segment: "possess required permission"
    note: "Added 'required' to emphasize action-specific permissions"
    alternatives: []
preserved_elements: []
challenges:
  - type: ambiguity
    description: "'doing anything' is vague about scope"
    resolution: "Interpreted as 'requested action' based on context"
    confidence: 0.8
  - type: format_mismatch
    description: "Comments lack structure; spec requires sections"
    resolution: "Added Preconditions, Behavior, Notes structure"
    confidence: 0.9
quality:
  semantic_accuracy: 85
  style_match: 95
  completeness: 90
  overall: 88
verification:
  back_translation_sample: null
  key_terms_verified: true
confidence: 0.85
evidence_anchors:
  - "source:code-comment"
assumptions:
  - "'logged in' means session-based authentication"
  - "Both conditions return same error code (403)"
```

## Verification

- [ ] Meaning preserved
- [ ] Target format conventions followed
- [ ] Preserved elements unchanged
- [ ] Challenges documented
- [ ] Quality scores reasonable

**Verification tools:** Read (for reference materials)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Never invent meaning not in source
- Flag ambiguities rather than guess
- Preserve technical terms when appropriate
- Note cultural adaptations
- Indicate confidence on difficult translations

## Composition Patterns

**Commonly follows:**
- `retrieve` - Translate retrieved content
- `explain` - Translate explanations
- `summarize` - Translate summaries

**Commonly precedes:**
- `send` - Translate before sending
- `persist` - Translate before storing
- `validate` - Validate translated content

**Anti-patterns:**
- Never translate without understanding context
- Never assume meaning in ambiguous cases
- Never discard source in case of review need

**Workflow references:**
- Localization workflows
- Documentation translation workflows
