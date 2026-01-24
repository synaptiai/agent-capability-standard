---
name: generalize
description: Abstract patterns, templates, or principles from specific examples. Use when creating reusable components, extracting best practices, or building frameworks from instances.
argument-hint: "[examples] [abstraction_level] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Extract abstract patterns, templates, or principles from specific instances to create reusable generalizations. Enable knowledge transfer from concrete cases to new situations.

**Success criteria:**
- Pattern accurately represents commonalities
- Generalization applies to new cases
- Variability points identified
- Over-generalization avoided
- Under-generalization avoided

**Compatible schemas:**
- `docs/schemas/generalization_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `examples` | Yes | array | Specific instances to generalize from |
| `abstraction_level` | No | string | How abstract: pattern, template, principle |
| `domain` | No | string | Domain for generalization |
| `constraints` | No | object | Limits on generalization scope |
| `min_examples` | No | integer | Minimum examples to support generalization |

## Procedure

1) **Analyze examples**: Understand each instance
   - Parse structure of each example
   - Identify components and relationships
   - Note unique and common elements
   - Understand context of each

2) **Find commonalities**: Identify shared elements
   - Structural similarities
   - Behavioral patterns
   - Repeated sequences
   - Common relationships

3) **Identify variability**: Note differences
   - What varies across examples?
   - What remains constant?
   - Optional vs required elements
   - Range of variation

4) **Abstract pattern**: Create generalization
   - Extract invariant structure
   - Parameterize variable elements
   - Define placeholder semantics
   - Establish pattern boundaries

5) **Define constraints**: Specify applicability
   - When does this pattern apply?
   - What are the preconditions?
   - What are the limitations?
   - Edge cases and exceptions

6) **Validate generalization**: Test against examples
   - Does pattern match all examples?
   - Is anything lost in abstraction?
   - Can examples be derived from pattern?
   - Is pattern overly specific or general?

7) **Document rationale**: Explain the abstraction
   - Why these elements are constant
   - Why these elements vary
   - Trade-offs in the generalization
   - Alternative generalizations considered

## Output Contract

Return a structured object:

```yaml
generalization:
  name: string  # Name for the pattern/template
  type: pattern | template | principle | framework
  description: string  # What this generalization captures
  abstraction_level: concrete | intermediate | abstract
pattern:
  structure: string  # Abstract structure (with placeholders)
  invariants: array[string]  # Elements that don't change
  parameters:
    - name: string
      description: string
      type: string
      constraints: string | null
      default: any | null
  constraints: array[string]  # When this applies
examples_analysis:
  - example_id: string
    matches_pattern: boolean
    mapping:  # How example maps to pattern
      - parameter: string
        value: any
    gaps: array[string]  # Elements not captured
applicability:
  domains: array[string]  # Where this applies
  preconditions: array[string]  # Required conditions
  limitations: array[string]  # Known limitations
  anti_examples: array[string]  # When NOT to use
alternatives:
  - name: string
    description: string
    trade_off: string
confidence: 0..1
evidence_anchors: ["example:id"]
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `generalization` | object | Summary of the abstraction |
| `pattern` | object | The generalized pattern/template |
| `examples_analysis` | array | How each example maps to pattern |
| `applicability` | object | When and where to use |
| `alternatives` | array | Other possible generalizations |
| `confidence` | number | 0.0-1.0 based on coverage |

## Examples

### Example 1: API Error Handling Pattern

**Input:**
```yaml
examples:
  - name: "user_service_error"
    code: |
      try:
        user = get_user(id)
        return {"status": "success", "data": user}
      except NotFoundError:
        return {"status": "error", "code": 404, "message": "User not found"}
      except ValidationError as e:
        return {"status": "error", "code": 400, "message": str(e)}
  - name: "order_service_error"
    code: |
      try:
        order = create_order(data)
        return {"status": "success", "data": order}
      except NotFoundError:
        return {"status": "error", "code": 404, "message": "Resource not found"}
      except ValidationError as e:
        return {"status": "error", "code": 400, "message": str(e)}
      except PaymentError as e:
        return {"status": "error", "code": 402, "message": str(e)}
abstraction_level: "template"
domain: "API development"
```

**Output:**
```yaml
generalization:
  name: "Standard API Response Pattern"
  type: template
  description: "Consistent error handling and response format for API endpoints"
  abstraction_level: intermediate
pattern:
  structure: |
    try:
        result = {operation}({parameters})
        return {"status": "success", "data": result}
    except NotFoundError:
        return {"status": "error", "code": 404, "message": "{not_found_message}"}
    except ValidationError as e:
        return {"status": "error", "code": 400, "message": str(e)}
    except {domain_specific_errors}:
        return {"status": "error", "code": {error_code}, "message": str(e)}
  invariants:
    - "Response format: {status, data} or {status, code, message}"
    - "NotFoundError maps to 404"
    - "ValidationError maps to 400"
    - "try/except structure"
  parameters:
    - name: "operation"
      description: "The main business operation to execute"
      type: "callable"
      constraints: "Must return serializable result"
      default: null
    - name: "parameters"
      description: "Arguments to the operation"
      type: "any"
      constraints: null
      default: null
    - name: "not_found_message"
      description: "Message for NotFoundError"
      type: "string"
      constraints: null
      default: "Resource not found"
    - name: "domain_specific_errors"
      description: "Additional exceptions to handle"
      type: "list[tuple[Exception, int]]"
      constraints: "Each maps to HTTP status code"
      default: "[]"
  constraints:
    - "Use for synchronous API endpoints"
    - "Exceptions must be well-defined"
    - "Response must be JSON-serializable"
examples_analysis:
  - example_id: "user_service_error"
    matches_pattern: true
    mapping:
      - parameter: "operation"
        value: "get_user"
      - parameter: "not_found_message"
        value: "User not found"
      - parameter: "domain_specific_errors"
        value: "[]"
    gaps: []
  - example_id: "order_service_error"
    matches_pattern: true
    mapping:
      - parameter: "operation"
        value: "create_order"
      - parameter: "not_found_message"
        value: "Resource not found"
      - parameter: "domain_specific_errors"
        value: "[(PaymentError, 402)]"
    gaps: []
applicability:
  domains: ["API development", "web services", "microservices"]
  preconditions:
    - "Using Python or similar exception-based language"
    - "Returning JSON responses"
    - "HTTP-based API"
  limitations:
    - "Does not handle async operations"
    - "Does not include retry logic"
    - "No logging included in pattern"
  anti_examples:
    - "Streaming responses"
    - "WebSocket endpoints"
    - "Non-HTTP protocols"
alternatives:
  - name: "Decorator-based error handling"
    description: "Use decorator to wrap operations"
    trade_off: "Less explicit, more DRY"
  - name: "Middleware error handling"
    description: "Handle errors at middleware level"
    trade_off: "Centralized but less granular"
confidence: 0.9
evidence_anchors:
  - "example:user_service_error"
  - "example:order_service_error"
assumptions:
  - "All API errors should return JSON"
  - "HTTP status codes are appropriate response"
```

**Evidence pattern:** Each example analyzed for pattern match, parameters extracted.

---

### Example 2: Document Structure Principle

**Input:**
```yaml
examples:
  - "SKILL.md files have: frontmatter, Intent, Inputs, Procedure, Output, Examples, Safety"
  - "README.md files have: Title, Description, Installation, Usage, Examples, Contributing"
  - "RFC documents have: Abstract, Motivation, Specification, Security, References"
abstraction_level: "principle"
domain: "technical documentation"
```

**Output:**
```yaml
generalization:
  name: "Technical Document Structure Principle"
  type: principle
  description: "Technical documents follow a problem-solution-details-reference pattern"
  abstraction_level: abstract
pattern:
  structure: |
    1. CONTEXT (What is this? Why does it exist?)
    2. INTERFACE (How do you use it?)
    3. IMPLEMENTATION (How does it work?)
    4. EXAMPLES (What does it look like?)
    5. METADATA (Supporting information)
  invariants:
    - "Context before details"
    - "Interface before implementation"
    - "Examples after specification"
    - "Metadata at boundaries (start or end)"
  parameters:
    - name: "context_section"
      description: "Establishes purpose and scope"
      type: "section"
      constraints: "Must answer 'what' and 'why'"
      default: "Introduction/Abstract/Intent"
    - name: "interface_section"
      description: "How to interact with the subject"
      type: "section"
      constraints: "Must be actionable"
      default: "Usage/Inputs/API"
    - name: "implementation_section"
      description: "How it works internally"
      type: "section"
      constraints: "Level of detail varies by audience"
      default: "Procedure/Specification/Details"
    - name: "examples_section"
      description: "Concrete instances"
      type: "section"
      constraints: "At least one complete example"
      default: "Examples"
    - name: "metadata_sections"
      description: "Supporting information"
      type: "sections"
      constraints: null
      default: "References/Safety/Contributing"
  constraints:
    - "Document has clear, single purpose"
    - "Audience is defined"
    - "Technical subject matter"
examples_analysis:
  - example_id: "SKILL.md"
    matches_pattern: true
    mapping:
      - parameter: "context_section"
        value: "Intent"
      - parameter: "interface_section"
        value: "Inputs"
      - parameter: "implementation_section"
        value: "Procedure, Output"
      - parameter: "examples_section"
        value: "Examples"
      - parameter: "metadata_sections"
        value: "Safety"
    gaps: []
  - example_id: "README.md"
    matches_pattern: true
    mapping:
      - parameter: "context_section"
        value: "Title, Description"
      - parameter: "interface_section"
        value: "Installation, Usage"
      - parameter: "implementation_section"
        value: "(implicit in Usage)"
      - parameter: "examples_section"
        value: "Examples"
      - parameter: "metadata_sections"
        value: "Contributing"
    gaps: ["Implementation details often minimal"]
  - example_id: "RFC"
    matches_pattern: true
    mapping:
      - parameter: "context_section"
        value: "Abstract, Motivation"
      - parameter: "interface_section"
        value: "(part of Specification)"
      - parameter: "implementation_section"
        value: "Specification"
      - parameter: "examples_section"
        value: "(within Specification)"
      - parameter: "metadata_sections"
        value: "Security, References"
    gaps: ["Examples often inline not separate"]
applicability:
  domains: ["technical documentation", "software projects", "specifications"]
  preconditions:
    - "Technical audience"
    - "Document serves as reference"
  limitations:
    - "Marketing documents differ"
    - "Tutorial style may vary sequence"
  anti_examples:
    - "Marketing copy"
    - "Personal blog posts"
    - "Creative writing"
alternatives:
  - name: "Narrative structure"
    description: "Tell a story from problem to solution"
    trade_off: "More engaging, less scannable"
confidence: 0.8
evidence_anchors:
  - "example:SKILL.md"
  - "example:README.md"
  - "example:RFC"
assumptions:
  - "Documents are meant as references"
  - "Readers may jump to sections"
```

## Verification

- [ ] Pattern matches all input examples
- [ ] Variability points are parameterized
- [ ] Constraints are well-defined
- [ ] Alternative generalizations considered
- [ ] Over/under generalization avoided

**Verification tools:** Read (for example analysis)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Require minimum examples before generalizing
- Note confidence based on example count
- Flag when generalization may be premature
- Document limitations clearly
- Avoid over-fitting to examples

## Composition Patterns

**Commonly follows:**
- `retrieve` - Gather examples to generalize
- `compare` - Understand differences before abstracting
- `analyze` - Deep analysis before generalization

**Commonly precedes:**
- `template` - Create templates from patterns
- `generate` - Use patterns to generate new instances
- `explain` - Explain the abstraction
- `persist` - Store reusable patterns

**Anti-patterns:**
- Never generalize from single example
- Never ignore outliers without documenting
- Never claim pattern without testing against examples

**Workflow references:**
- Knowledge extraction workflows
- Best practice documentation workflows
