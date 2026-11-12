# Workflow Patterns

**Document Status**: Reference
**Last Updated**: 2026-01-26
**Purpose**: Document how 36 atomic capabilities compose into reusable workflow patterns

---

## Overview

The 36 atomic capabilities are **primitives**. Real agent behaviors emerge by **composing** these primitives into workflow patterns. This document catalogs common patterns that can be implemented as Skills.

```mermaid
---
title: From capabilities to skills
---
flowchart TB
  accDescr: Skills implement workflow patterns, and workflow patterns are composed from the atomic capabilities.
  skills["Skills (packaged workflows): pdf-processing, data-analysis, code-review"]
  patterns["Workflow patterns (reusable compositions): analyze, mitigate, optimize, validate"]
  atoms["Atomic capabilities (primitives): detect, classify, plan, verify, execute"]
  skills -->|implement| patterns
  patterns -->|compose from| atoms
```

---

## Pattern Categories

| Category | Purpose | Example Patterns |
|----------|---------|------------------|
| **Analysis** | Understand data | analyze, profile, audit |
| **Planning** | Decide what to do | strategize, prioritize, schedule |
| **Execution** | Do the work | process, migrate, deploy |
| **Validation** | Ensure correctness | validate, test, review |
| **Optimization** | Make things better | optimize, refine, improve |
| **Coordination** | Work with others | orchestrate, negotiate, handoff |

---

## 1. Analysis Patterns

### 1.1 Analyze Pattern

**Purpose**: Comprehensive examination of a subject.

```yaml
analyze:
  description: Examine subject thoroughly and report findings
  capabilities:
    - retrieve       # Get the data
    - detect         # Find patterns
    - classify       # Categorize findings
    - measure        # Quantify metrics
    - compare        # Evaluate against baseline
    - explain        # Summarize findings

  flow:
    1. retrieve(target) → data
    2. detect(data, patterns) → occurrences
    3. classify(occurrences) → categories
    4. measure(data, metrics) → values
    5. compare(values, baseline) → assessment
    6. explain(assessment) → report
```

```mermaid
---
title: Analyze pattern flow
---
flowchart TB
  accDescr: The retrieved data goes two ways, to detect and classify for patterns and to measure and compare against a baseline, and explain reports the assessment.
  retrieve["retrieve(target)"] -->|data| detect["detect(data, patterns)"]
  detect -->|occurrences| classify["classify(occurrences)"]
  retrieve -->|data| measure["measure(data, metrics)"]
  measure -->|values| compare["compare(values, baseline)"]
  compare -->|assessment| explain["explain(assessment)"]
```

**Example uses**:
- Code analysis
- Data profiling
- Security audit
- Performance analysis

### 1.2 Diagnose Pattern

**Purpose**: Find root cause of a problem.

```yaml
diagnose:
  description: Identify root cause of observed issue
  capabilities:
    - observe        # See current state
    - detect         # Find anomalies
    - attribute      # Trace causation
    - explain        # Report findings

  flow:
    1. observe(system) → current_state
    2. detect(current_state, anomaly_patterns) → issues
    3. attribute(issues) → causes
    4. explain(causes) → diagnosis
```

### 1.3 Profile Pattern

**Purpose**: Build comprehensive picture of an entity.

```yaml
profile:
  description: Create detailed profile of subject
  capabilities:
    - retrieve       # Get data from multiple sources
    - integrate      # Merge data
    - classify       # Categorize attributes
    - state          # Create unified representation

  flow:
    1. retrieve(sources) → raw_data[]
    2. integrate(raw_data) → merged
    3. classify(merged, attributes) → categorized
    4. state(categorized) → profile
```

---

## 2. Planning Patterns

### 2.1 Strategize Pattern

**Purpose**: Create high-level plan for complex goal.

```yaml
strategize:
  description: Develop strategy to achieve goal
  capabilities:
    - observe        # Understand current state
    - predict        # Forecast outcomes
    - compare        # Evaluate options
    - decompose      # Break into phases
    - plan           # Create action plan

  flow:
    1. observe(environment) → current_state
    2. predict(scenarios) → outcomes[]
    3. compare(outcomes, criteria) → best_approach
    4. decompose(best_approach) → phases
    5. plan(phases) → strategy
```

```mermaid
---
title: Strategize pattern flow
---
flowchart TB
  accDescr: Each step hands its result to the next, from the observed state through predicted outcomes and the best approach to phases and the strategy.
  observe["observe(environment)"] -->|current_state| predict["predict(scenarios)"]
  predict -->|outcomes| compare["compare(outcomes, criteria)"]
  compare -->|best_approach| decompose["decompose(best_approach)"]
  decompose -->|phases| plan["plan(phases)"]
```

### 2.2 Prioritize Pattern

**Purpose**: Order items by importance.

```yaml
prioritize:
  description: Rank items by criteria
  capabilities:
    - retrieve       # Get items
    - measure        # Score each item
    - compare        # Rank by scores
    - explain        # Justify ranking

  flow:
    1. retrieve(items) → list
    2. measure(list, criteria) → scores
    3. compare(scores) → ranking
    4. explain(ranking) → rationale
```

### 2.3 Schedule Pattern

**Purpose**: Assign temporal ordering to tasks.

```yaml
schedule:
  description: Create timeline for tasks
  capabilities:
    - retrieve       # Get tasks
    - measure        # Estimate durations
    - detect         # Find dependencies
    - plan           # Create schedule
    - constrain      # Apply constraints

  flow:
    1. retrieve(tasks) → task_list
    2. measure(tasks, duration) → estimates
    3. detect(tasks, dependencies) → deps
    4. plan(tasks, estimates, deps) → draft_schedule
    5. constrain(draft_schedule, resources) → schedule
```

```mermaid
---
title: Schedule pattern flow
---
flowchart TB
  accDescr: The task list feeds both a duration estimate and a dependency search, plan combines the tasks with both into a draft, and constrain fits the draft to the resources.
  retrieve["retrieve(tasks)"] -->|task_list| measure["measure(tasks, duration)"]
  retrieve -->|task_list| detect["detect(tasks, dependencies)"]
  measure -->|estimates| plan["plan(tasks, estimates, deps)"]
  detect -->|deps| plan
  plan -->|draft_schedule| constrain["constrain(draft_schedule, resources)"]
```

---

## 3. Execution Patterns

### 3.1 Process Pattern

**Purpose**: Transform input through defined steps.

```yaml
process:
  description: Transform data through pipeline
  capabilities:
    - retrieve       # Get input
    - transform      # Apply transformations
    - verify         # Check result
    - persist        # Save output

  flow:
    1. retrieve(input) → data
    2. checkpoint(data) → recovery_point
    3. transform(data, steps) → result
    4. verify(result, criteria) → valid?
    5. if valid: persist(result)
    6. else: rollback(recovery_point)
```

```mermaid
---
title: Process pattern flow
---
flowchart TB
  accDescr: A checkpoint is saved before the data is transformed; a valid result is persisted, and an invalid one is rolled back to the checkpoint's recovery point.
  retrieve["retrieve(input)"] -->|data| checkpoint["checkpoint(data)"]
  checkpoint --> transform["transform(data, steps)"]
  transform -->|result| verify{"verify(result, criteria)"}
  verify -->|valid| persist["persist(result)"]
  verify -->|not valid| rollback["rollback(recovery_point)"]
  checkpoint -.->|recovery_point| rollback
```


### 3.2 Migrate Pattern

**Purpose**: Move data/state from one system to another.

```yaml
migrate:
  description: Transfer data between systems
  capabilities:
    - retrieve       # Get source data
    - transform      # Convert format
    - verify         # Validate transformation
    - checkpoint     # Save recovery point
    - mutate         # Write to target
    - verify         # Confirm success

  flow:
    1. retrieve(source) → data
    2. transform(data, target_format) → converted
    3. verify(converted, schema) → valid?
    4. checkpoint(target_state) → recovery_point
    5. mutate(target, converted) → result
    6. verify(result, expectations) → success?
    7. if !success: rollback(recovery_point)
```

```mermaid
---
title: Migrate pattern flow
---
flowchart TB
  accDescr: The data is converted and checked against the schema before a checkpoint is saved and the target is written; if the result is not a success, rollback restores the recovery point.
  retrieve["retrieve(source)"] -->|data| transform["transform(data, target_format)"]
  transform -->|converted| check{"verify(converted, schema)"}
  check -->|valid| checkpoint["checkpoint(target_state)"]
  checkpoint --> mutate["mutate(target, converted)"]
  mutate -->|result| confirm{"verify(result, expectations)"}
  confirm -->|not success| rollback["rollback(recovery_point)"]
  checkpoint -.->|recovery_point| rollback
```

### 3.3 Execute-Verify-Retry Pattern

**Purpose**: Run operation with validation and retry.

```yaml
execute_verify_retry:
  description: Execute with validation loop
  capabilities:
    - checkpoint     # Save state
    - execute        # Run operation
    - verify         # Check result
    - rollback       # Restore on failure
    - explain        # Report outcome

  flow:
    loop max_attempts:
      1. checkpoint(state) → recovery
      2. execute(operation) → result
      3. verify(result, criteria) → valid?
      4. if valid: break with success
      5. rollback(recovery)
      6. plan(failure, adjustments) → retry_plan
    7. explain(outcome) → report
```

```mermaid
---
title: Execute-verify-retry loop
---
flowchart TB
  accDescr: Each attempt saves a checkpoint, executes and verifies; a failed check rolls back and plans the next attempt, and explain reports the outcome on success or once the attempts run out.
  subgraph attempt [Up to max_attempts tries]
    checkpoint["checkpoint(state)"] -->|recovery| execute["execute(operation)"]
    execute -->|result| verify{"verify(result, criteria)"}
    verify -->|not valid| rollback["rollback(recovery)"]
    rollback --> replan["plan(failure, adjustments)"]
    replan -->|retry_plan| checkpoint
  end
  verify -->|valid: success| explain["explain(outcome)"]
  replan -->|attempts used up| explain
```


---

## 4. Validation Patterns

### 4.1 Validate Pattern

**Purpose**: Comprehensive validation against criteria.

```yaml
validate:
  description: Check subject meets all criteria
  capabilities:
    - retrieve       # Get subject
    - verify         # Check conditions
    - detect         # Find violations
    - explain        # Report results

  flow:
    1. retrieve(subject) → data
    2. verify(data, criteria) → results
    3. detect(results, violations) → issues
    4. explain(issues) → report
```

```mermaid
---
title: Validate pattern flow
---
flowchart TB
  accDescr: The subject is checked against the criteria, the results are searched for violations, and explain reports the issues found.
  retrieve["retrieve(subject)"] -->|data| verify["verify(data, criteria)"]
  verify -->|results| detect["detect(results, violations)"]
  detect -->|issues| explain["explain(issues)"]
```

### 4.2 Test Pattern

**Purpose**: Execute tests and report results.

```yaml
test:
  description: Run tests against subject
  capabilities:
    - retrieve       # Get test cases
    - execute        # Run tests
    - compare        # Check against expected
    - measure        # Calculate metrics
    - generate       # Create report

  flow:
    1. retrieve(test_suite) → tests
    2. for each test:
       a. execute(test.code) → actual
       b. compare(actual, test.expected) → result
    3. measure(results, coverage) → metrics
    4. generate(results, metrics) → report
```

```mermaid
---
title: Test pattern flow
---
flowchart TB
  accDescr: Each test is executed and its actual result compared with the expected one; the results are measured for coverage and generate writes the report.
  retrieve["retrieve(test_suite)"]
  subgraph each [For each test]
    execute["execute(test.code)"] -->|actual| compare["compare(actual, test.expected)"]
  end
  retrieve -->|tests| execute
  compare -->|results| measure["measure(results, coverage)"]
  measure -->|metrics| generate["generate(results, metrics)"]
```

### 4.3 Review Pattern

**Purpose**: Human-in-the-loop validation.

```yaml
review:
  description: Present for review and incorporate feedback
  capabilities:
    - generate       # Create review artifact
    - send           # Present to reviewer
    - receive        # Get feedback
    - critique       # Analyze feedback
    - plan           # Plan changes

  flow:
    1. generate(subject, format) → artifact
    2. send(artifact, reviewer) → submitted
    3. receive(feedback) → comments
    4. critique(comments) → actionable
    5. plan(actionable) → changes
```

---

## 5. Optimization Patterns

### 5.1 Optimize Pattern

**Purpose**: Iteratively improve toward objective.

```yaml
optimize:
  description: Find best solution through iteration
  capabilities:
    - observe        # Current state
    - discover       # Find candidates
    - measure        # Evaluate each
    - compare        # Rank options
    - mutate         # Apply improvement
    - verify         # Confirm improvement

  flow:
    loop until_converged:
      1. observe(state) → current
      2. discover(current, possibilities) → candidates
      3. measure(candidates, objective) → scores
      4. compare(scores) → best
      5. if best > current:
         a. checkpoint(state)
         b. mutate(state, best) → new_state
         c. verify(new_state) → improved?
         d. if !improved: rollback()
```

```mermaid
---
title: Optimize pattern loop
---
flowchart TB
  accDescr: Each round scores candidate changes against the objective; when the best beats the current state it is applied after a checkpoint and verified, and rolled back if it did not improve.
  subgraph round [Loop until converged]
    observe["observe(state)"] -->|current| discover["discover(current, possibilities)"]
    discover -->|candidates| measure["measure(candidates, objective)"]
    measure -->|scores| compare["compare(scores)"]
    compare -->|best beats current| checkpoint["checkpoint(state)"]
    checkpoint --> mutate["mutate(state, best)"]
    mutate -->|new_state| verify{"verify(new_state)"}
    verify -->|not improved| rollback["rollback()"]
  end
```

### 5.2 Refine Pattern

**Purpose**: Incrementally improve quality.

```yaml
refine:
  description: Iteratively improve artifact
  capabilities:
    - critique       # Find weaknesses
    - plan           # Plan improvements
    - transform      # Apply changes
    - verify         # Check improvement

  flow:
    loop until_satisfactory:
      1. critique(artifact) → issues
      2. if no issues: break
      3. plan(issues) → improvements
      4. transform(artifact, improvements) → refined
      5. verify(refined, criteria) → better?
      6. artifact = refined
```

### 5.3 Mitigate Pattern

**Purpose**: Reduce risk through intervention.

```yaml
mitigate:
  description: Identify and reduce risks
  capabilities:
    - detect         # Find risks
    - measure        # Quantify severity
    - compare        # Prioritize
    - plan           # Create mitigation
    - execute        # Apply mitigation
    - verify         # Confirm reduction

  flow:
    1. detect(subject, risk_patterns) → risks
    2. measure(risks, impact × probability) → scored
    3. compare(scored) → prioritized
    4. for high_priority_risks:
       a. plan(risk, mitigation_options) → action
       b. checkpoint(state)
       c. execute(action) → result
       d. verify(result, risk_reduced) → success?
       e. if !success: rollback()
```

---

## 6. Coordination Patterns

### 6.1 Orchestrate Pattern

**Purpose**: Coordinate multiple agents/workflows.

```yaml
orchestrate:
  description: Coordinate parallel work streams
  capabilities:
    - decompose      # Break into parts
    - delegate       # Assign to agents
    - synchronize    # Wait for completion
    - integrate      # Merge results

  flow:
    1. decompose(task) → subtasks
    2. for each subtask:
       delegate(subtask, agent) → task_id
    3. synchronize(task_ids) → results
    4. integrate(results) → final
```

```mermaid
---
title: Orchestrate pattern flow
---
flowchart TB
  accDescr: The task is split into subtasks, each subtask is delegated to an agent, synchronize waits for every task, and integrate merges their results.
  decompose["decompose(task)"]
  subgraph each [For each subtask]
    delegate["delegate(subtask, agent)"]
  end
  decompose -->|subtasks| delegate
  delegate -->|task_ids| synchronize["synchronize(task_ids)"]
  synchronize -->|results| integrate["integrate(results)"]
```

### 6.2 Handoff Pattern

**Purpose**: Transfer work between agents.

```yaml
handoff:
  description: Transfer context and work to another agent
  capabilities:
    - state          # Capture current state
    - generate       # Create handoff package
    - delegate       # Transfer to agent
    - receive        # Get acknowledgment

  flow:
    1. state(work_context) → snapshot
    2. generate(snapshot, handoff_format) → package
    3. delegate(package, target_agent) → task_id
    4. receive(acknowledgment) → confirmed
```

### 6.3 Consensus Pattern

**Purpose**: Achieve agreement among multiple parties.

```yaml
consensus:
  description: Reach agreement among agents
  capabilities:
    - generate       # Create proposal
    - send           # Distribute proposal
    - receive        # Collect votes
    - compare        # Evaluate consensus
    - synchronize    # Finalize agreement

  flow:
    1. generate(options) → proposal
    loop until_consensus:
      2. send(proposal, agents) → distributed
      3. receive(votes) → responses
      4. compare(responses) → agreement_level
      5. if agreement_level < threshold:
         generate(revised_proposal) → proposal
    6. synchronize(agents, final_proposal) → consensus
```

```mermaid
---
title: Consensus loop
---
flowchart TB
  accDescr: The proposal is sent to the agents and their votes compared; while agreement is below the threshold a revised proposal goes out again, and at consensus synchronize shares the final proposal.
  generate["generate(options)"]
  subgraph round [Loop until consensus]
    send["send(proposal, agents)"] -->|distributed| receive["receive(votes)"]
    receive -->|responses| compare["compare(responses)"]
    compare -->|agreement_level| check{Below threshold?}
    check -->|yes| revise["generate(revised_proposal)"]
  end
  generate -->|proposal| send
  revise -->|proposal| send
  check -->|consensus| sync["synchronize(agents, final_proposal)"]
```


---

## 7. Compound Patterns

### 7.1 Research Pattern

**Purpose**: Investigate a topic and synthesize findings.

```yaml
research:
  description: Investigate topic and produce synthesis
  composes: [analyze, profile, explain]

  flow:
    1. search(topic) → sources
    2. analyze(sources) → findings
    3. profile(findings) → structured
    4. ground(structured, sources) → grounded
    5. explain(grounded) → synthesis
```

```mermaid
---
title: Research pattern flow
---
flowchart TB
  accDescr: Research runs two other patterns, analyze and profile, between a search for sources and a grounded explanation; the double-edged boxes are patterns, not capabilities.
  search["search(topic)"] -->|sources| analyze[["analyze pattern"]]
  analyze -->|findings| profile[["profile pattern"]]
  profile -->|structured| ground["ground(structured, sources)"]
  ground -->|grounded| explain["explain(grounded)"]
```

### 7.2 Build Pattern

**Purpose**: Create artifact through iterative development.

```yaml
build:
  description: Create artifact with validation
  composes: [plan, process, test, refine]

  flow:
    1. plan(requirements) → design
    2. decompose(design) → components
    3. for each component:
       a. generate(component_spec) → artifact
       b. test(artifact) → results
       c. if !passed: refine(artifact) → artifact
    4. integrate(artifacts) → product
    5. test(product) → final_results
```

```mermaid
---
title: Build pattern flow
---
flowchart TB
  accDescr: Plan turns the requirements into a design and decompose splits it into components; each component is generated and tested, and refined when it fails, then the artifacts are integrated and the product is tested.
  plan["plan(requirements)"] -->|design| decompose["decompose(design)"]
  subgraph each [For each component]
    generate["generate(component_spec)"] -->|artifact| test["test(artifact)"]
    test -->|not passed| refine["refine(artifact)"]
  end
  decompose -->|components| generate
  test -->|passed| integrate["integrate(artifacts)"]
  refine -->|artifact| integrate
  integrate -->|product| final["test(product)"]
```

### 7.3 Monitor Pattern

**Purpose**: Continuous observation with alerting.

```yaml
monitor:
  description: Watch for conditions and respond
  composes: [observe, detect, mitigate]

  flow:
    loop continuously:
      1. observe(system) → state
      2. detect(state, alert_conditions) → alerts
      3. if alerts:
         a. classify(alerts) → severity
         b. if critical:
            mitigate(alerts) → response
         c. audit(alerts, response) → logged
      4. persist(state) → history
```

```mermaid
---
title: Monitor pattern loop
---
flowchart TB
  accDescr: The loop observes the system and checks the state for alert conditions; alerts are classified, critical ones are mitigated, and every alert is audited; the state is persisted to history on each pass.
  observe["observe(system)"] -->|state| detect["detect(state, alert_conditions)"]
  detect -->|alerts| classify["classify(alerts)"]
  classify -->|critical| mitigate["mitigate(alerts)"]
  classify -->|not critical| audit["audit(alerts, response)"]
  mitigate -->|response| audit
  detect -->|no alerts| persist["persist(state)"]
  audit -->|logged| persist
  persist -->|history, loop again| observe
```

---

## Pattern Composition Rules

### 1. Capability Dependencies

Only `requires` edges force another capability to be present: every `mutate`, `send` and `rollback` step needs a `checkpoint` step running before it (V102). `precedes` edges only order capabilities that both appear in a workflow (V102 when the target has no source step before it); they never demand the source. `constrain` is a soft prerequisite of `execute`, `mutate` and `send`: a workflow without it still validates, with warning W601. A step in the same `parallel_group` does not count as running before another.

```
requires (presence and order, V102):
  checkpoint → mutate | send | rollback

precedes (order when both are present, V102), for example:
  checkpoint → mutate, send
  plan → execute, mutate
  constrain → execute, mutate, send, generate
  execute | mutate | send → verify → audit
  observe → detect → classify

soft_requires (one source first, else W601):
  constrain → execute | mutate | send
  observe | detect | predict | attribute | explain → ground

enables (informational):
  retrieve → detect
  decompose → delegate
```

```mermaid
---
title: What requires demands
---
flowchart LR
  accDescr: A checkpoint step must run before every mutate, send and rollback step, or the workflow fails with V102.
  checkpoint ==>|must run first| mutate & send & rollback
```

```mermaid
---
title: What soft_requires asks for
---
flowchart LR
  accDescr: A constrain step should run before execute, mutate and send steps; without it the workflow still validates, with warning W601.
  constrain -.->|should run first| execute & mutate & send
```


### 2. Safety Requirements

High-risk patterns must include safety capabilities:

| Pattern Risk | Required Capabilities |
|--------------|----------------------|
| Low | verify |
| Medium | checkpoint, verify |
| High | checkpoint, verify, rollback, audit |

```mermaid
---
title: Safety capabilities by pattern risk
---
flowchart LR
  accDescr: A low-risk pattern needs verify; a medium-risk one adds checkpoint, and a high-risk one adds rollback and audit as well.
  low["Low: verify"] -->|adds checkpoint| medium["Medium: checkpoint, verify"]
  medium -->|adds rollback, audit| high["High: checkpoint, verify, rollback, audit"]
```

### 3. Evidence Requirements

All patterns should maintain evidence chain:

```
Every capability output includes:
  - evidence_anchors: array
  - confidence: number (0-1)

Pattern outputs should aggregate:
  - All evidence from component capabilities
  - Lowest confidence from chain
```

```mermaid
---
title: How a pattern carries evidence
---
flowchart LR
  accDescr: Each capability output carries evidence anchors and a confidence from 0 to 1; the pattern output gathers all the evidence and takes the lowest confidence in the chain.
  caps["Each capability output: evidence_anchors, confidence (0-1)"] -->|aggregated| out["Pattern output: all the evidence, the lowest confidence in the chain"]
```

---

## Implementing Patterns as Skills

To implement a workflow pattern as a Claude Skill:

```yaml
# SKILL.md structure

---
name: pattern-name
description: What the pattern does and when to use it
---

# Pattern Name

## Quick Start

[Minimal example]

## Workflow

1. **Step 1**: [capability] - purpose
2. **Step 2**: [capability] - purpose
...

## Inputs

- `input_name`: description

## Outputs

- `output_name`: description

## Error Handling

- On failure at step N: [recovery action]

## Examples

[Concrete examples]
```

---

## Summary

| Layer | Patterns |
|-------|----------|
| Analysis | analyze, diagnose, profile |
| Planning | strategize, prioritize, schedule |
| Execution | process, migrate, execute-verify-retry |
| Validation | validate, test, review |
| Optimization | optimize, refine, mitigate |
| Coordination | orchestrate, handoff, consensus |
| Compound | research, build, monitor |

All patterns compose from the **36 atomic capabilities**. New patterns can be created by combining existing capabilities in new ways.

---

## References

- [capability_ontology.yaml](../schemas/capability_ontology.yaml) — The 36 atomic capabilities
- [FIRST_PRINCIPLES_REASSESSMENT.md](methodology/FIRST_PRINCIPLES_REASSESSMENT.md) — Derivation methodology
- [Claude Skills Overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
