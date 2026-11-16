# Enhanced Skill Template

Use this template to create high-quality, production-ready Claude Code skills.

## Template

````markdown
---
name: <capability-name>
description: <verb phrase describing what this capability does>. Use when <trigger conditions/keywords>.
argument-hint: "[<required-arg>] [<optional-arg>] [constraints]"
disable-model-invocation: false
user-invocable: true
allowed-tools: <comma-separated list from ontology default_tools>
context: fork
agent: <explore|general-purpose>
---

## Intent

<Specific intent for THIS capability - not generic text>

**Success criteria:**
- <Specific measurable outcome 1>
- <Specific measurable outcome 2>

**Compatible schemas:** (if applicable)
- `schemas/output_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string\|object | <What this parameter represents for THIS capability> |
| `constraints` | No | object | <Capability-specific constraints> |
| `<other>` | No | <type> | <Description> |

## Procedure

<Numbered steps SPECIFIC to this capability - never use generic boilerplate>

1) **<Action verb>**: <Specific first step for what this capability does>
   - <Sub-detail if needed>

2) **<Action verb>**: <Specific second step with domain-specific guidance>
   - <What to look for>
   - <How to handle edge cases>

3) **Ground claims**: Attach evidence anchors to all non-trivial assertions (STANDARD v1.2 §3.1, §6.5)
   - Each anchor is `{ref, kind}`: `{ref: "file:src/app.py#L10-L20", kind: file}`, `{ref: "https://...", kind: url}`, `{ref: "tool:<tool_name>:<output_ref>", kind: tool}`; an output that reports an action cites its record, `{ref: "<action>:<id>", kind: record}`
   - Cite only evidence you had: what you read, what you were given, what a tool returned
   - An `excerpt` quotes the evidence; never quote a secret in one (§6.7)
   - With no evidence, mark the output inferred: `inference_method` (`model_knowledge`, `deduction`, `induction`, `abduction`, `analogy`, `statistical`, `simulation`, `assumption`) and `confidence` (§4.1.1)

4) **Format output**: Structure results according to the output contract below

5) **Assess confidence**: The probability, 0.0-1.0, that the output's claim is correct (§4.1.1), estimated from the evidence's quality and completeness

## Output Contract

Return a structured object:

```yaml
<primary_result_field>: <schema or type description>
<secondary_field>: <schema or type>
# Always include these standard fields:
confidence: 0..1  # probability that the output's claim is correct (STANDARD v1.2 §4.1.1)
evidence_anchors: [{ref: "file:src/app.py#L10-L20", kind: file}, {ref: "https://...", kind: url}, {ref: "tool:...", kind: tool}]  # evidence anchors (§6.5)
inference_method: string  # only when nothing grounds the output: how it was reached (§3.1, §4.1.1)
assumptions: []  # Explicit assumptions made
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `<primary_result_field>` | <type> | <What this field represents> |
| `confidence` | number | Probability, 0.0-1.0, that <the output's claim> (§4.1.1) |
| `evidence_anchors` | array of evidence anchors (§6.5) | What the output is based on: `{ref, kind}` per piece of evidence |
| `inference_method` | string | How an output not grounded in evidence was reached (§3.1, §4.1.1) |
| `assumptions` | array[string] | Explicitly stated assumptions |

## Examples

### Example 1: <Scenario Name>

**Input:**
```yaml
target: <concrete example value>
constraints:
  <key>: <value>
```

**Output:**
```yaml
<complete output matching the contract above>
```

**Evidence pattern:** <How evidence was gathered in this example>

---

### Example 2: <Alternative Scenario> (optional)

**Input:**
```yaml
target: <different example>
```

**Output:**
```yaml
<corresponding output>
```

## Verification

- [ ] <Specific verification check 1 - e.g., "Output contains at least one evidence anchor">
- [ ] <Specific verification check 2 - e.g., "Confidence is justified by evidence count">
- [ ] <Invariant to check - e.g., "All referenced files exist">

**Verification tools:** <List tools needed if not in allowed-tools>

## Safety Constraints

- `mutation`: <true|false from ontology>
- `requires_checkpoint`: <true|false from ontology>
- `requires_approval`: <true|false from ontology>
- `risk`: <low|medium|high from ontology>

**Capability-specific rules:**
- <Rule 1 - e.g., "Do not access paths outside the workspace">
- <Rule 2 - e.g., "Stop and request clarification if confidence < 0.3">

## Composition Patterns

**Commonly follows:**
- `<capability-1>` - <why this capability often comes after>
- `<capability-2>` - <context>

**Commonly precedes:**
- `<capability-3>` - <why this capability often comes before>

**Anti-patterns:**
- Never use with `<capability-x>` because <reason>
- Avoid combining with `<capability-y>` unless <condition>

**Workflow references:**
- See `workflow_catalog.json#<workflow_name>` for usage in context
````

---

## Template Usage Guidelines

### 1. Description Field

The description must include **trigger keywords** for skill discovery:

**Good:** `Detect whether a specific pattern or entity exists in the given data. Use when searching for patterns, checking existence, or validating presence.`

**Bad:** `Runs detection.`

### 2. Procedure Section

Never use generic boilerplate like:
```
1) Minimize context load
2) State assumptions
3) Perform the capability
4) Return output
```

Instead, write capability-specific steps that guide execution.

### 3. Output Contract

Always provide a concrete YAML schema, never placeholders like `<primary output>`.

### 4. Examples

Include at least one complete example with:
- Realistic input values
- Complete output matching the contract
- Evidence pattern explanation

### 5. Agent Selection

| Risk Level | Agent Type | Reason |
|------------|------------|--------|
| low | explore | Read-only, safer |
| medium | explore | Default to safer unless mutation needed |
| high | general-purpose | Needs Edit, Bash, Git access |
| mutation=true | general-purpose | Requires write access |

### 6. Allowed Tools by Layer

The table summarises the `allowed-tools` field of the shipped skills. Where a
row and a skill's own frontmatter differ, the frontmatter is correct.

| Layer | Default Tools |
|-------|--------------|
| PERCEIVE | Read (add Grep for search, observe and receive; Web for retrieve and search; Bash for observe) |
| UNDERSTAND | Read, Grep (add Bash for measure) |
| REASON | Read, Grep |
| MODEL | Read, Grep (add Bash for simulate) |
| SYNTHESIZE | Read, Grep |
| EXECUTE | Read, Bash (add Edit and Write for mutate, Grep for send) |
| VERIFY | Read (add Grep for verify, constrain and audit; Bash for verify, checkpoint, rollback and audit; Edit for checkpoint; Git for rollback) |
| REMEMBER | Read (add Grep for recall, Edit for persist) |
| COORDINATE | Read, Grep (add Bash, Edit and Write for invoke) |

---

## Checklist Before Finalizing

- [ ] Name is kebab-case and matches folder name
- [ ] Description includes trigger keywords
- [ ] Procedure has 4-6 capability-specific steps
- [ ] Output contract has complete YAML schema
- [ ] At least 1 example with complete input/output
- [ ] Safety constraints match capability_ontology.yaml
- [ ] Composition patterns reference valid capability IDs
- [ ] Skill is under 500 lines
