# Replanning and Goal Uncertainty Capabilities

> Research documentation for Issue #9: Investigating atomic capabilities for re-planning and goal uncertainty handling.

## Executive Summary

This document investigates whether the Grounded Agency framework needs new atomic capabilities to handle **world change detection** (replanning) and **goal uncertainty** (intent clarification). After analyzing literature from classical AI planning, modern LLM agent architectures, and major agent frameworks, we conclude:

### Key Findings

| Finding | Recommendation |
|---------|----------------|
| World change detection | **Workflow pattern** using existing capabilities (not new atomic) |
| Goal uncertainty handling | **One new atomic capability**: `inquire` |
| Continuous monitoring | **Workflow pattern** using existing capabilities |
| Re-planning triggers | Extend `detect` with `domain: plan-invalidation` |

### Summary Recommendation

Add **1 new atomic capability** (`inquire`) and document **2 workflow patterns** (`monitor-and-replan`, `clarify-intent`). The framework grows from 35 to **36 atomic capabilities** while remaining philosophically minimal, gaining the ability to handle dynamic environments and ambiguous goals.

---

## 1. Problem Statement

### 1.1 Current State

The Grounded Agency framework handles three types of uncertainty:

| Uncertainty Type | How Handled |
|------------------|-------------|
| Data uncertainty | `uncertainty-model` with epistemic/aleatoric typing |
| Source conflicts | Trust model with authority weights |
| Capability uncertainty | Dependency graph blocks invalid compositions |

### 1.2 Gap Identified

Two critical uncertainty types are **not explicitly addressed**:

1. **World change**: Environment changes mid-execution, invalidating the current plan
2. **Goal uncertainty**: Agent is unsure what the user actually wants

These gaps were also identified in the [failure taxonomy](./failure_taxonomy.md) (Issue #8):
- **Gap 1**: World Change Detection — no single capability detects when external world changes invalidate the current plan
- **Gap 2**: Goal Uncertainty Handling — no explicit capability for clarifying ambiguous user intent

---

## 2. Literature Review

### 2.1 Classical AI Planning Approaches

Classical planning systems (STRIPS, PDDL) handle plan invalidation through:

1. **Execution Monitoring**: Compare expected state against actual state after each action
2. **Plan Repair**: Modify the existing plan minimally to handle new conditions
3. **Replanning**: Discard current plan and generate a new one from scratch

Key insight from [classical planning research](https://cw.fel.cvut.cz/old/_media/courses/a3b33kui/knihy/artificial_intelligence_a_modern_approach_3rd_edition_chapter_10.pdf):

> "When executing plans, assumptions are usually not met. Since replanning has to replan every time there is a change in the environment, the total planning time is a burden compared to the short time required to perform repairs in the plan."

**Implications for Grounded Agency**: Plan repair is typically more efficient than full replanning. This suggests:
- Detecting plan invalidation should be cheap (continuous monitoring)
- The response should be proportional (repair small issues, replan for large)

### 2.2 Modern LLM Agent Architectures

Research from [The Rise of Agentic AI survey](https://www.mdpi.com/1999-5903/17/9/404) (2025) identifies four major agent reasoning patterns:

| Pattern | Description | Replanning Approach |
|---------|-------------|---------------------|
| **ReAct** | Interleave reasoning and action | None (action-by-action) |
| **Reflexion** | Self-reflection after failures | Episodic memory + verbal feedback |
| **Plan-and-Execute** | Generate full plan, then execute | Re-plan on failure |
| **ReflAct** | Goal-state reflection at each step | Continuous alignment checking |

The [ReflAct paper](https://aclanthology.org/2025.emnlp-main.1697/) (EMNLP 2025) directly addresses our gap:

> "ReAct often produces ungrounded or incoherent reasoning steps, leading to misalignment between the agent's actual state and goal. ReflAct introduces a backbone that shifts reasoning from merely planning next actions to continuously reflecting on the agent's state relative to its goal."

**Key mechanism**: ReflAct achieves 93.3% success rate vs 65.6% for ReAct by:
1. Explicitly grounding decisions in current state
2. Comparing state against goal at every step
3. Triggering replanning when divergence exceeds threshold

### 2.3 Agent Framework Analysis

| Framework | Replanning Support | Mechanism |
|-----------|-------------------|-----------|
| **LangGraph** | ✓ State checkpoints | Graph-based workflow with branching |
| **AutoGen** | ✓ Conversational | Agents negotiate through dialogue |
| **CrewAI** | ✓ Flows layer | Event-driven task orchestration |
| **Reflexion** | ✓ Memory-based | Verbal reflection in episodic memory |

From [Agent Orchestration Guide 2026](https://iterathon.tech/blog/ai-agent-orchestration-frameworks-2026):

> "LangGraph provides state-based memory with checkpointing for workflow continuity... Agents make decisions based on evolving conversations, often resembling how human collaborators brainstorm and iterate."

**Key insight**: Modern frameworks don't have explicit "replan" primitives. Instead, they:
1. Persist state between steps
2. Allow conditional branching based on observed state
3. Let the agent reasoning layer decide when to deviate

### 2.4 Goal Uncertainty and Clarification Research

Recent research on [Structured Uncertainty-guided Clarification](https://arxiv.org/html/2511.08798) (2025) introduces:

> "ClarifyBench evaluates three distinct query types: Explicit Queries (well-specified requests), Ambiguous Queries (requests requiring clarification), and Infeasible Queries (requests that would generate errors)."

The [Value of Information framework](https://arxiv.org/html/2601.06407) (2026) formalizes:

> "The adaptive communication task as a sequential decision-making process where an LLM agent interacts with a user to select an optimal action... allowing the agent to dynamically resolve ambiguity before committing to an action."

**Key mechanisms for goal clarification**:

1. **Ambiguity Detection**: Classify whether the request has sufficient information
2. **Question Generation**: Generate targeted clarifying questions
3. **Intent Inference**: Use context to disambiguate when clarification isn't possible
4. **Confidence Threshold**: Act only when confidence exceeds threshold

From [Training LLMs to Ask Clarifying Questions](https://openreview.net/forum?id=cwuSAR7EKd):

> "Existing LLMs often respond by presupposing a single interpretation of such ambiguous requests, frustrating users who intended a different interpretation."

---

## 3. Analysis: Atomic vs. Workflow

### 3.1 Atomicity Criteria

From the [First Principles Reassessment](../methodology/FIRST_PRINCIPLES_REASSESSMENT.md), a capability is atomic if:

1. Cannot be decomposed into simpler capabilities
2. Has a single, clear purpose
3. Has a well-defined I/O contract
4. Is domain-general (not tool-specific)

### 3.2 Candidate: `monitor` (World Change Detection)

**Proposed operation**: Continuously observe world state and detect when assumptions are violated.

**Decomposition analysis**:
```
monitor = observe → state → compare(current_state, expected_state) → detect(divergence)
```

| Criterion | Assessment |
|-----------|------------|
| Cannot decompose? | ❌ NO — Clearly decomposes into observe, state, compare, detect |
| Single purpose? | ✓ YES — Detect assumption violations |
| Well-defined I/O? | ✓ YES — Input: assumptions; Output: violations |
| Domain-general? | ✓ YES — Applies to any monitored system |

**Verdict**: `monitor` is a **workflow pattern**, not an atomic capability. The existing `observe`, `state`, `compare`, and `detect` capabilities can be composed to achieve this.

However, we should extend `detect` to recognize "plan-invalidation" as a valid domain:

```yaml
detect:
  domain: plan-invalidation
  input:
    plan: {type: object, description: "Current plan with assumptions"}
    world_state: {type: object, description: "Current world state"}
  output:
    detected: {type: boolean}
    violations: {type: array, description: "List of violated assumptions"}
    severity: {type: string, enum: [minor, moderate, critical]}
```

### 3.3 Candidate: `replan` (Re-planning)

**Proposed operation**: Generate a new plan when the current plan is invalidated.

**Decomposition analysis**:
```
replan = critique(current_plan, violations) → plan(revised_goal, new_constraints)
```

| Criterion | Assessment |
|-----------|------------|
| Cannot decompose? | ❌ NO — It's critique + plan |
| Single purpose? | ✓ YES — Create revised plan |
| Well-defined I/O? | ✓ YES — Input: invalidation; Output: new plan |
| Domain-general? | ✓ YES — Applies to any planning context |

**Verdict**: `replan` is **not atomic**. It's a composition of `critique` (identify what's wrong) and `plan` (create new approach).

### 3.4 Candidate: `inquire` (Goal Clarification)

**Proposed operation**: Generate clarifying questions when goal is ambiguous.

**Decomposition analysis**:
```
inquire = measure(ambiguity) → generate(clarifying_questions) → receive(clarification)
```

Wait — let's reconsider. The generation of clarifying questions is specialized:
- It requires analyzing what information is missing
- It requires understanding what answers would resolve ambiguity
- It requires formulating questions the user can answer

Can `critique` do this?
- `critique`: "Identify weaknesses in the plan/goal"
- `inquire`: "Generate questions to resolve the weakness"

These are different! `critique` identifies problems; `inquire` requests the specific information needed to resolve them.

Can `generate` do this?
- `generate`: "Produce new content" (general purpose)
- `inquire`: "Produce clarifying questions targeting specific ambiguity"

The specialization matters. Clarifying questions have structure:
- They target specific missing parameters
- They offer bounded options when possible
- They are designed to elicit actionable responses

| Criterion | Assessment |
|-----------|------------|
| Cannot decompose? | ⚠️ DEBATABLE — Could be measure + generate + receive |
| Single purpose? | ✓ YES — Request clarification |
| Well-defined I/O? | ✓ YES — Input: ambiguous request; Output: clarifying questions |
| Domain-general? | ✓ YES — Applies to any ambiguous goal |

**Analysis**: While technically decomposable, `inquire` represents a **fundamental agent operation** that:
1. Is common enough to warrant naming (appears in every major framework)
2. Has specific semantics that differ from general generation
3. Is a core part of the agent-user interaction loop

**Verdict**: `inquire` should be added as a **new atomic capability**.

### 3.5 Candidate: `infer-goal` (Goal Inference)

**Proposed operation**: Use context to disambiguate underspecified requests without asking.

**Decomposition analysis**:
```
infer-goal = observe(context) → classify(likely_intents) → compare(intents) → ground(selected_intent)
```

| Criterion | Assessment |
|-----------|------------|
| Cannot decompose? | ❌ NO — Clearly decomposes |
| Single purpose? | ✓ YES — Infer intent from context |
| Well-defined I/O? | ✓ YES — Input: ambiguous request + context; Output: resolved intent |
| Domain-general? | ✓ YES — Applies to any goal inference |

**Verdict**: `infer-goal` is a **workflow pattern** using `observe`, `classify`, `compare`, and `ground`.

---

## 4. Recommendations

### 4.1 New Atomic Capability: `inquire`

Add `inquire` to the COORDINATE layer:

```yaml
id: inquire
layer: COORDINATE
description: "Request clarification when input is ambiguous"
risk: low
mutation: false

input_schema:
  type: object
  required: [ambiguous_input]
  properties:
    ambiguous_input:
      type: any
      description: "The underspecified request or goal"
    context:
      type: object
      description: "Available context for question generation"
    max_questions:
      type: integer
      default: 3
      description: "Maximum clarifying questions to generate"

output_schema:
  type: object
  required: [questions, ambiguity_analysis, evidence_anchors, confidence]
  properties:
    questions:
      type: array
      items:
        type: object
        properties:
          question: {type: string}
          parameter: {type: string, description: "What parameter this resolves"}
          options: {type: array, description: "Suggested answers if bounded"}
      description: "Clarifying questions to resolve ambiguity"
    ambiguity_analysis:
      type: object
      properties:
        missing_parameters: {type: array}
        conflicting_interpretations: {type: array}
        confidence_without_clarification: {type: number}
    evidence_anchors:
      type: array
      description: "Evidence supporting the ambiguity assessment"
    confidence:
      type: number
      minimum: 0
      maximum: 1
      description: "Confidence that clarification is needed"
```

**Edges to add**:
- `critique` enables `inquire` (critique identifies what's unclear)
- `inquire` soft_requires `receive` (agent needs to accept the response)

**Why COORDINATE layer?**: `inquire` is fundamentally about agent-user coordination, similar to `delegate` (agent-agent coordination).

### 4.2 Workflow Pattern: `monitor-and-replan`

Document as a reference workflow in `schemas/workflow_catalog.yaml`:

```yaml
monitor-and-replan:
  description: "Detect world changes and trigger replanning when needed"
  steps:
    - capability: observe
      purpose: "Capture current world state"
      store_as: current_state

    - capability: state
      purpose: "Create state representation"
      input_bindings:
        scope: ${plan.scope}
      store_as: world_state

    - capability: compare
      purpose: "Compare against plan assumptions"
      input_bindings:
        options:
          - ${world_state}
          - ${plan.assumed_state}
        criteria: [assumption_validity]
      store_as: comparison

    - capability: detect
      purpose: "Detect assumption violations"
      input_bindings:
        data: ${comparison}
        pattern: assumption_violation
        domain: plan-invalidation
      store_as: violations

    - capability: critique
      purpose: "Assess impact on current plan"
      input_bindings:
        target: ${plan}
        criteria:
          - step_validity
          - goal_achievability
      gates:
        - when: ${violations.detected} == false
          action: stop
          message: "No violations detected, plan remains valid"
      store_as: plan_assessment

    - capability: plan
      purpose: "Generate revised plan if needed"
      input_bindings:
        goal: ${plan.goal}
        constraints:
          - ${violations}
          - ${plan_assessment.suggestions}
      gates:
        - when: ${plan_assessment.severity} == "minor"
          action: skip
          message: "Minor violation, continue with current plan"
      store_as: revised_plan
```

### 4.3 Workflow Pattern: `clarify-intent`

Document as a reference workflow:

```yaml
clarify-intent:
  description: "Resolve ambiguous user requests through clarification"
  steps:
    - capability: critique
      purpose: "Analyze request for ambiguity"
      input_bindings:
        target: ${user_request}
        criteria:
          - parameter_completeness
          - interpretation_uniqueness
      store_as: ambiguity_analysis

    - capability: inquire
      purpose: "Generate clarifying questions"
      input_bindings:
        ambiguous_input: ${user_request}
        context: ${conversation_context}
        max_questions: 3
      gates:
        - when: ${ambiguity_analysis.confidence} > 0.85
          action: skip
          message: "Request is sufficiently clear"
      store_as: clarification_request

    - capability: send
      purpose: "Present questions to user"
      input_bindings:
        destination: user
        payload: ${clarification_request.questions}
      store_as: sent_questions

    - capability: receive
      purpose: "Accept user clarification"
      input_bindings:
        channel: user
        timeout: "5m"
      store_as: clarification

    - capability: integrate
      purpose: "Merge clarification with original request"
      input_bindings:
        sources:
          - ${user_request}
          - ${clarification.data}
        strategy: parameter_merge
      store_as: resolved_request
```

### 4.4 Domain Extensions

Extend existing capabilities with new domain parameters:

**`detect` with `domain: plan-invalidation`**:
```yaml
detect:
  domain: plan-invalidation
  input:
    plan: {type: object}
    current_state: {type: object}
  output:
    detected: {type: boolean}
    violations:
      type: array
      items:
        assumption: {type: string}
        expected: {type: any}
        actual: {type: any}
        severity: {type: string, enum: [minor, moderate, critical]}
```

**`measure` with `domain: ambiguity`**:
```yaml
measure:
  domain: ambiguity
  input:
    request: {type: string}
    context: {type: object}
  output:
    value: {type: number, description: "Ambiguity score 0-1"}
    missing_parameters: {type: array}
    conflicting_interpretations: {type: array}
```

---

## 5. Integration with Safety Model

### 5.1 Checkpoint and Rollback Interaction

When replanning occurs mid-execution:

1. **Before replanning**: `checkpoint` the current state
2. **Generate new plan**: Use `plan` with constraint injection
3. **Execute new plan**: Begin execution
4. **On failure**: `rollback` to checkpoint and escalate

```
checkpoint → detect(plan-invalidation) → critique → plan → execute
                                                        ↓
                                              verify → (rollback if failed)
```

### 5.2 Audit Trail for Replanning

Every replan should be audited:

```yaml
audit:
  event:
    type: replan_triggered
    original_plan: ${plan.id}
    violations: ${violations}
    new_plan: ${revised_plan.id}
  context:
    reason: "World state diverged from assumptions"
    confidence: ${violations.confidence}
```

### 5.3 Risk Classification

| Capability/Pattern | Risk Level | Rationale |
|-------------------|------------|-----------|
| `inquire` | low | Read-only, user interaction |
| `monitor-and-replan` | medium | May trigger plan changes |
| `clarify-intent` | low | Read-only, user interaction |

---

## 6. Research Questions Answered

### Q1: Are proposed capabilities truly atomic, or compositions?

| Proposed | Verdict | Rationale |
|----------|---------|-----------|
| `detect-plan-invalidation` | **Domain** | Use `detect` with domain parameter |
| `trigger-replan` | **Composition** | `critique` + `plan` |
| `monitor-assumptions` | **Workflow** | `observe` + `state` + `compare` + `detect` |
| `clarify-intent` | **Workflow** | `critique` + `inquire` + `receive` |
| `infer-goal` | **Workflow** | `observe` + `classify` + `compare` + `ground` |
| `negotiate-goal` | **Workflow** | Multiple rounds of `inquire` + `receive` |
| **`inquire`** | **Atomic** | Unique operation for requesting clarification |

### Q2: What evidence anchors support goal clarification?

For `inquire`, evidence anchors should reference:
- The original request text (what was said)
- Identified ambiguous parameters
- Context used for ambiguity assessment
- Similar past requests and their resolutions

### Q3: How does re-planning interact with checkpoints/rollback?

1. **Checkpoint before high-risk plan modifications**
2. **Preserve rollback capability** during transition
3. **Audit all replanning decisions** with full provenance
4. **Gate execution** on checkpoint existence for safety

---

## 7. Updated Capability Count

### Before (35 capabilities)

```
PERCEIVE (4): retrieve, search, observe, receive
UNDERSTAND (6): detect, classify, measure, predict, compare, discover
REASON (4): plan, decompose, critique, explain
MODEL (5): state, transition, attribute, ground, simulate
SYNTHESIZE (3): generate, transform, integrate
EXECUTE (3): execute, mutate, send
VERIFY (5): verify, checkpoint, rollback, constrain, audit
REMEMBER (2): persist, recall
COORDINATE (3): delegate, synchronize, invoke
```

### After (36 capabilities)

```
PERCEIVE (4): retrieve, search, observe, receive
UNDERSTAND (6): detect, classify, measure, predict, compare, discover
REASON (4): plan, decompose, critique, explain
MODEL (5): state, transition, attribute, ground, simulate
SYNTHESIZE (3): generate, transform, integrate
EXECUTE (3): execute, mutate, send
VERIFY (5): verify, checkpoint, rollback, constrain, audit
REMEMBER (2): persist, recall
COORDINATE (4): delegate, synchronize, invoke, **inquire**  ← NEW
```

**Net change**: 35 → 36 (+1 atomic capability)

---

## 8. Implementation Checklist

- [x] Research document complete (`docs/research/replanning_capabilities.md`)
- [x] Add `inquire` to `schemas/capability_ontology.json`
- [x] Add edges: `critique → inquire`, `inquire ~> receive`
- [x] Document `monitor-and-replan` workflow in `schemas/workflow_catalog.yaml`
- [x] Document `clarify-intent` workflow in `schemas/workflow_catalog.yaml`
- [x] Create skill for `inquire` at `skills/inquire/SKILL.md`
- [x] Update GLOSSARY.md with new terms
- [x] Run validator: `python tools/validate_workflows.py`

---

## 9. References

### Academic Literature

1. Yildirim et al. [Creating Design Resources to Scaffold the Ideation of AI Concepts](https://doi.org/10.1145/3563657.3596058). DIS '23.

2. [The Rise of Agentic AI: A Review of Definitions, Frameworks, Architectures](https://www.mdpi.com/1999-5903/17/9/404). MDPI Future Internet, 2025.

3. [ReflAct: World-Grounded Decision Making in LLM Agents](https://aclanthology.org/2025.emnlp-main.1697/). EMNLP 2025.

4. [Structured Uncertainty guided Clarification for LLM Agents](https://arxiv.org/html/2511.08798). arXiv, 2025.

5. [Value of Information: A Framework for Human–Agent Communication](https://arxiv.org/html/2601.06407). arXiv, 2026.

6. [Beyond Single Models: Enhancing LLM Detection of Ambiguity](https://arxiv.org/html/2507.12370). arXiv, 2025.

7. Shinn et al. [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366). NeurIPS 2023.

8. [A Modern Survey of LLM Planning Capabilities](https://aclanthology.org/2025.acl-long.958.pdf). ACL 2025.

9. [Deep Research: A Survey of Autonomous Research Agents](https://arxiv.org/html/2508.12752v1). arXiv, 2025.

### Framework Documentation

10. [LangGraph Documentation](https://langchain-ai.github.io/langgraph/). LangChain, 2025.

11. [AutoGen Framework](https://microsoft.github.io/autogen/). Microsoft Research, 2024.

12. [CrewAI Documentation](https://docs.crewai.com/). CrewAI, 2025.

13. [Agent Orchestration 2026 Guide](https://iterathon.tech/blog/ai-agent-orchestration-frameworks-2026). Iterathon, 2026.

### Classical Planning

14. Russell & Norvig. [Classical Planning](https://cw.fel.cvut.cz/old/_media/courses/a3b33kui/knihy/artificial_intelligence_a_modern_approach_3rd_edition_chapter_10.pdf). AIMA Chapter 10.

15. [Robust Plan Execution with Unexpected Observations](https://arxiv.org/pdf/2003.09401). arXiv, 2020.

### Related Documentation

- [Failure Taxonomy](./failure_taxonomy.md) — Issue #8 analysis
- [First Principles Reassessment](../methodology/FIRST_PRINCIPLES_REASSESSMENT.md) — Capability derivation methodology
- [Grounded Agency](../GROUNDED_AGENCY.md) — Main framework documentation

---

*Research completed for Issue #9*
*Agent Capability Standard v2.1.0 (proposed)*
