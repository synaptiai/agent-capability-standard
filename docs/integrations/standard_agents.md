# Standard Agents interoperability

The [Standard Agent Specification](https://standardagentspec.org) defines how
an agent is written, run and packaged. The Agent Capability Standard defines
what an agent's actions mean, which of them are risky, and what must be true
before a risky one runs. This document maps the two, shows how to build a
grounded agent on Standard Agents today, and lists what each standard would
have to change for the combination to be complete.

| Standard | Compared here |
|---|---|
| Agent Capability Standard (ACS) | [Standard 1.1.0](../../spec/STANDARD-v1.1.0.md), ontology 2.1.0 |
| Standard Agent Specification (SA) | 0.2.0, [`standardagents/spec`](https://github.com/standardagents/spec) at commit `faccc8b` (12 November 2026), and the published `@standardagents/spec` 0.45.10 types |

Statements about Standard Agents cite the page and section they come from.
Where the specification text and the published types differ, the difference
is noted. [How this analysis was done](#how-this-analysis-was-done) says what
was checked and what was not.

## Summary

- **The two standards fit together and barely overlap.** Standard Agents has
  no notion of risk, checkpoints, approval records, evidence or audit; ACS has
  no notion of prompts, models, threads or packaging.
- **A grounded Standard Agent can be built today** on what SA 0.2.0
  specifies. [`examples/standard_agents/`](../../examples/standard_agents/README.md)
  is a working reference: a tool is classified by an ontology capability, and
  the capability's rules are enforced inside the tool. The example compiles
  against the published SA types and its rules are tested.
- **Enforcement is cooperative, not imposed.** SA has no hook that can refuse
  a tool call before it runs, so a safety rule holds only for tools written
  with the binding. A tool written without it is not covered, and no hook
  lets a runtime or a composing agent add the rule from outside. The indirect
  routes SA does have are [listed below](#enforce-inside-the-tool), with what
  each costs.
- **Approval can be recorded without a model in between**, through an
  authenticated thread endpoint, bound to a digest of exactly what was shown.
  The digest is the same one the ACS reference executor computes. SA
  authenticates a caller; that the caller is a person is for the deployment
  to ensure.
- **ACS workflows cannot yet run inside an SA runtime.** The reference
  executor is Rust with Python bindings and SA definitions are TypeScript. The
  core compiles to WebAssembly unchanged; it lacks a JavaScript interface, and
  SA does not say that definition code can load WebAssembly.
- **Changes are proposed to both standards**, listed at the end. The most
  important is a hook in SA that can decline a tool call before it runs.

## What each standard covers

```mermaid
---
title: Where the two standards sit
---
flowchart TB
  accDescr: The Agent Capability Standard says what an action is, how risky it is, what must precede it and what evidence it returns; the Standard Agent Specification says how an agent is defined, run and packaged; a grounded Standard Agent is defined, run and shipped by the second and classified and constrained by the first.
  acs["Agent Capability Standard: what an action is, its risk, what must precede it, its evidence"]
  sa["Standard Agent Specification: how an agent is defined, run and packaged"]
  ga(["A grounded Standard Agent"])
  acs -->|classifies and constrains| ga
  sa -->|defines, runs and ships| ga
```

| Question | Standard Agents answers | ACS answers |
|----------|------------------------|-------------|
| How do I write an agent? | `defineAgent`, `definePrompt`, `defineTool` and the other definitions, in TypeScript | Not covered |
| What runs it? | A runtime that executes threads one step at a time and persists every message | Not covered for model-driven agents; a deterministic executor for workflows |
| How do I ship it? | An npm package with a `standardagent` field | Not covered |
| What does this tool do to the world? | Not covered: a tool is a description, an argument schema and a function | One of 36 capabilities, each with an input and output contract |
| Is this action risky? | Not covered | `risk`, `mutation`, `requires_checkpoint`, `requires_approval` on every capability |
| What must happen before it? | Not covered | Typed edges between capabilities, checked before a workflow runs and enforced while it runs |
| Who approved it, and what exactly? | A waiting state for a human-backed side; no approval record | A decision bound to a digest of what the approver saw |
| What is the claim based on? | Not covered | Evidence anchors on every capability output |

SA states its own boundary in the same terms. Its packaging page says: "When
an agent category needs a new runtime primitive, that primitive belongs in the
specification and its conformance surface rather than in a product-private
package/runtime agreement."
([Packaging, Portability requirements](https://standardagentspec.org/0.2.0/distribution/packaging#portability-requirements))
The proposals at the end of this document follow from that sentence.

### Words the two standards use differently

| Word | In ACS | In Standard Agents |
|---|---|---|
| Capability | One of the 36 verbs of the ontology | A feature or limit of a model (`ModelCapabilities`) |
| Step | One entry of a workflow | One model request and response: `stepCount` is "Total LLM request/response cycles" |
| Handler | A workflow step that runs only as an escalation target (`handler: true`, [§5.11](../../spec/STANDARD-v1.1.0.md#511-handler-steps)) | "a function that takes one side's turns in a conversation" ([Handlers](https://standardagentspec.org/0.2.0/specification/handlers)) |
| Hook | A Claude Code hook: the plugin's, or one a skill declares | A thread hook defined with `defineHook` |
| Skill | A `SKILL.md`: one per capability, and one per composed workflow | An entry in the thread owner's Agent Skills library (`state.skills`) |
| Invoke | The `invoke` capability: run another workflow as a nested run | `state.invokeTool()`: call a tool, a prompt or an agent by name from code |
| Host, runtime | The host performs the actions the executor names | The runtime executes threads |

Below, a handler is always the Standard Agents kind.

## How the concepts map

Each table sets an ACS concept beside the nearest Standard Agents concept.
The tables summarise the
[row-level mapping](../research/analysis/standard_agents_mapping/index.yaml):
319 rows in ten files, each with the passages it rests on. **Fit** is one of:

- *Partial*: one covers part of the other.
- *Fits*: they address different layers and combine without conflict.
- *ACS only* / *SA only*: the other standard has nothing comparable.

No row is a conflict: nowhere does following one standard as written break a
requirement of the other.

### Capabilities and tools

| ACS | Standard Agents | Fit | Combined |
|---|---|---|---|
| A capability: one of 36 verbs with an input contract, an output contract and safety flags ([§4.1](../../spec/STANDARD-v1.1.0.md#41-capability-definition)) | A function tool: a description, an argument schema and an `execute` function ([Tools §2](https://standardagentspec.org/0.2.0/specification/tools#2-function-tool-definition)) | Fits | A tool performs one capability and says which in `annotations.acs` |
| Domain parameter (`detect` with `domain: anomaly`) | Nothing comparable | ACS only | A `domain` field in the annotation |
| Input contract as JSON Schema, checked when a workflow is validated ([§5.5](../../spec/STANDARD-v1.1.0.md#55-consumer-contract-checking)) | `args` as a Zod schema, validated on every call ([Tools §9](https://standardagentspec.org/0.2.0/specification/tools#9-conformance-notes)) | Partial | The tool's `args` are the tool's contract; they specialise the capability's inputs and need not equal them |
| Output contract with required fields, `evidence_anchors` among them | A result is a status and one string; there is no output schema | ACS only | The output object is JSON in `result`; the binding checks the required fields |
| Cognitive capabilities (`classify`, `critique`, `plan`, ...) | A prompt tool: a prompt named in another prompt's `tools` ([Tools §1](https://standardagentspec.org/0.2.0/specification/tools#1-tool-categories)) | Partial | Prompts cannot carry annotations, so the classification goes on the function tools the prompt can call |
| `classify`, `detect`, `measure`: typed judgements with a confidence | `state.decide()`: typed questions answered with probabilities ([Decisions](https://standardagentspec.org/0.2.0/specification/threads/decisions)) | Partial | A grounded tool calls `decide()` and maps the answer to the capability's output |
| One capability per step ([§3.4](../../spec/STANDARD-v1.1.0.md#34-composable-atoms)) | A tool is arbitrary code and may call other tools through `uses` | Partial | Classify by the strictest capability a tool performs, or split the tool |
| Every action passes through the safety layer | Provider tools "execute server-side" at the model provider ([Providers §10](https://standardagentspec.org/0.2.0/specification/providers#10-provider-tools)) | SA only | Per the published types such a call is "not" to "be re-executed locally"; the 0.2.0 text does not say whether its `execute` runs. It does not pass through a grounded wrapper. Offer one only where its capability needs neither checkpoint nor approval |
| Capability skills: one `SKILL.md` per capability | `state.skills`, an Agent Skills library ([Threads §7.4](https://standardagentspec.org/0.2.0/specification/threads#74-agent-skills)) | Partial | A user or an administrator could install the ACS skills in their own library as guidance. A package cannot ship them: the library belongs to the thread's owner. Whether a runtime's frontmatter check accepts their extra keys is not stated |

### Safety flags and enforcement

| ACS | Standard Agents | Fit | Combined |
|---|---|---|---|
| `risk`, `mutation`, `requires_checkpoint`, `requires_approval` on every capability | Nothing comparable. Tool `annotations` are hints with no defined keys | ACS only | The effective flags travel in `annotations.acs` |
| "Validators, executors and safety layers MUST act on effective flags" ([§5.2.1](../../spec/STANDARD-v1.1.0.md#521-safety-flags)) | A runtime must "never let them affect execution" ([Tools §9](https://standardagentspec.org/0.2.0/specification/tools#9-conformance-notes)) | Fits | The annotation may publish the flags; enforcement may not be keyed on it by a runtime. The binding enforces in the tool's own code |
| A check that refuses a step before it runs | No hook can refuse a tool call. `tool_call_started` is observational; the others run afterwards ([Hooks §5](https://standardagentspec.org/0.2.0/specification/hooks#5-tool-execution-hooks)) | ACS only | Enforcement in the tool's own `execute`. [Proposed to SA](#changes-proposed-to-the-standard-agent-specification) |
| A gate whose expression errors fires, except an `end` gate ([§5.8.2](../../spec/STANDARD-v1.1.0.md#582-evaluation)) | A hook's "failures are non-fatal to the decorated turn" | Partial | Nothing safety-relevant is placed in a hook |
| `requires` edges, checked before a workflow runs (V102) | The model chooses the calls; the runtime runs them in order | Fits | Checked per call by the tool, and per prompt by `lintPromptTools` |
| `conflicts_with`: not in the same `parallel_group` (F504) | "Tool calls **MUST** execute sequentially in the returned order" ([Runtime §5.1](https://standardagentspec.org/0.2.0/infrastructure/runtime#51-ordering)) | Partial | Cannot arise between the tool calls of one thread. Effects and endpoints run apart from them |
| Safety diagnostics with fixed codes ([§9.6](../../spec/STANDARD-v1.1.0.md#96-safety-errors)) | A tool error is a persisted result, never a halt ([Runtime §5.2](https://standardagentspec.org/0.2.0/infrastructure/runtime#52-error-handling)) | Fits | A refusal is an error result carrying the ACS code |
| Bounds on repetition: `retry.max`, `max_loops` | `maxSteps`, `maxSessionTurns`, runtime hard caps | Fits | Both apply. A model that repeats a refused call is stopped only by a cap the agent sets (`maxSteps` and `maxSessionTurns` have no default) or by a runtime's own |

### Checkpoints, state and memory

| ACS | Standard Agents | Fit | Combined |
|---|---|---|---|
| `checkpoint`: save state for recovery | No snapshot primitive | ACS only | A grounded `checkpoint` tool saves what a rollback needs, in the thread's files or key-value store |
| `rollback`: restore a checkpoint | No restore or undo. The one statement on the subject concerns a handler that throws: "Nothing is rolled back." ([Handlers §5](https://standardagentspec.org/0.2.0/specification/handlers#5-error-semantics)) | ACS only | A grounded `rollback` tool restores what the checkpoint tool saved |
| A checkpoint record that authorises one later step | A durable, per-thread key-value store ([Runtime, Durable Key-Value Store](https://standardagentspec.org/0.2.0/infrastructure/runtime#14-durable-key-value-store)) | Fits | The record lives in the store; a later call reads it |
| A wait invalidates earlier checkpoints (W608) | `execution.flowId`, the "Unique execution ID" | Fits | A checkpoint counts only in the execution that took it |
| `persist`, `recall` | `setValue`, `getValue`; user-scope values in the Draft Users page | Partial | Thread scope maps directly. The ontology gives `persist` and `recall` no scope; the `recall` skill names `session`, `project` and `global` |
| World state: `state`, `transition`, the world state schema ([§6.3](../../spec/STANDARD-v1.1.0.md#63-world-state-requirements)) | Nothing comparable: a thread holds messages, files and values | ACS only | A world model is data a grounded agent keeps in the thread |
| Run snapshot and restore (canonical JSON, SHA-256, optional HMAC) | Messages and tool results persisted before the runtime advances | Fits | Different things: SA persists the conversation, ACS the position in a workflow |

### Approval and identity

| ACS | Standard Agents | Fit | Combined |
|---|---|---|---|
| `requires_approval` on `execute`, `mutate`, `send` | No tool, prompt or agent property says an action needs approval | ACS only | The flag is in the annotation and enforced in the tool |
| Structured approval: who, what they see, digest, expiry ([§5.14](../../spec/STANDARD-v1.1.0.md#514-approval)) | The approval gate: a child with a human-backed side that parks in `awaiting_human` ([Agents §7](https://standardagentspec.org/0.2.0/specification/agents#7-human-in-the-loop-composition)) | Partial | SA defines the waiting; ACS defines what a decision is. The binding uses an authenticated endpoint rather than the gate |
| The decision binds to a digest of the shown values | Nothing comparable | ACS only | Computed by the tool from its own arguments |
| The approver, by role and number | `auth.caller` in a thread endpoint, with application `roles` ([Thread Endpoints §4](https://standardagentspec.org/0.2.0/specification/threads/endpoints#4-access-and-authentication)) | Fits | The endpoint records the authenticated caller |
| A person's answer in the conversation | A message with `role: 'user'`, which a parent or package code can also create | Partial | Not usable as proof of a decision. [Proposed to SA](#changes-proposed-to-the-standard-agent-specification) |
| `expires`; an unanswered request | A parked human turn has no deadline | ACS only | Expiry is checked by the tool when it runs and by the approval endpoint when a decision arrives |
| `standing_mandate`: pre-approval with nobody present | Nothing comparable for actions | ACS only | Not implemented in the binding |
| Agent identity and trust class ([§5.17](../../spec/STANDARD-v1.1.0.md#517-sender-identity), [RFC-0004](../../spec/RFC-0004-agent-identity.md)) | `ThreadUser`: id, role, optional application roles; the Users page is a Draft | Partial | A caller maps to a principal; trust classes have no SA counterpart |

### Evidence, provenance and audit

| ACS | Standard Agents | Fit | Combined |
|---|---|---|---|
| `evidence_anchors` on every capability output | A result is one string; `HookToolResult` has no metadata field | ACS only | Anchors travel inside `result` as JSON |
| Evidence collected after each tool call | `tool_call_done`: fires once per call, success or failure ([Hooks §5.5](https://standardagentspec.org/0.2.0/specification/hooks#55-tool_call_done)) | Partial | Where it is in the active hook set, the hook observes each tool call the model issues; the text does not say whether it fires for `invokeTool`, `queueTool`, lifecycle or provider-executed calls. The tool records what a hook cannot see |
| An anchor that names its tool call | The call id is passed to hooks, not to the tool | Partial | Joined afterwards by the audit hook |
| An audit trail: the `audit` capability, action records | No audit or trace surface. Hooks are for "logging, validation, transformation" | ACS only | The binding's trace in the thread's key-value store |
| Append-only, tamper-evident records | Thread storage is mutable and deletable by code in the thread | ACS only | Not achievable inside the thread. Export the trace to a store outside it |
| Provenance of a received item: `sender`, trust class | `metadata.subagent_id`, `metadata.forwarded_from`: "conventions, not requirements" ([Messages §1.1](https://standardagentspec.org/0.2.0/specification/threads/messages#11-provenance-metadata-conventions)) | Partial | Not usable as a guarantee |
| Auditable transforms ([§3.2](../../spec/STANDARD-v1.1.0.md#32-auditable-transforms)) | Hooks may rewrite a result before it is stored, and filter history before each model call | Partial | A hook that rewrites results can remove evidence. A grounded agent should list its hooks and know what each changes |
| The authority trust model ([§8](../../spec/STANDARD-v1.1.0.md#8-authority-trust-model)) | Nothing comparable | ACS only | Stays in ACS |

### Composition across agents

| ACS | Standard Agents | Fit | Combined |
|---|---|---|---|
| `delegate`: assign a task to another agent | A subagent relationship and the injected `subagent_create` tool ([Subagents §5](https://standardagentspec.org/0.2.0/specification/subagents#5-lifecycle-tools)) | Partial | `subagent_create` is a `delegate`. It is injected by the runtime, so it has no `execute` to wrap |
| A waiting delegate ([§5.13](../../spec/STANDARD-v1.1.0.md#513-waiting-for-events)) | `blocking: true` on a relationship | Partial | The same shape; SA has no timeout on the wait. A host can also wait on a non-blocking child: see [How a `delegate` step maps to a host](#how-a-delegate-step-maps-to-a-host) |
| `fresh_context`, attested in `effective` | A child is its own thread, and persists: a later call may continue it | Partial | Fresh only when a new instance was created |
| `read_only` delegation | No read-only mode for a child | ACS only | Cannot be attested. A grounded child enforces its own rules |
| `invoke`: a nested run that shares the caller's checkpoints | Prompt tools, in the same thread | Partial | A prompt tool is classified by what it does, not as `invoke` |
| `synchronize`, quorum ([§5.16](../../spec/STANDARD-v1.1.0.md#516-quorum)) | No agreement or voting construct | ACS only | Built from several children and code that counts |
| `inquire` | A human-backed side: the session parks until input arrives | Fits | A tool returns the questions and the model puts them to the person in a reply that hands over the turn |
| Nothing comparable | `parentHooks`: hooks a child requires of its parent, failing closed ([Agents §6](https://standardagentspec.org/0.2.0/specification/agents#6-required-parent-hooks)) | SA only | A grounded child can require its audit hook on whoever composes it |
| Nothing comparable | Handoff: another agent takes over the same thread | SA only | The end of one actor's run and the start of another's |
| Safety flags of what a delegate may do | No machine-readable statement of a child's effects | ACS only | A parent cannot know that a child mutates. Each agent grounds its own tools |

### Workflows

| ACS | Standard Agents | Fit | Combined |
|---|---|---|---|
| A workflow catalog: declared steps, validated before they run ([§5](../../spec/STANDARD-v1.1.0.md#5-workflow-dsl)) | No declarative format. A model, or handler code, decides the order at run time | ACS only | See [Running ACS workflows](#running-acs-workflows-with-standard-agents) |
| The executor: a state machine that does no I/O and is driven by a host | A handler-backed side: code the runtime calls once per inbound message ([Handlers](https://standardagentspec.org/0.2.0/specification/handlers)) | Fits | A handler could be the host |
| `InvokeCapability` | `state.invokeTool(name, args)` | Partial | Needs a map from capability inputs to tool arguments |
| `RequestApproval` | An authenticated endpoint, or a human-backed child | Partial | As in the binding |
| `AwaitEvent`, `Sleep` | Inbound messages and endpoints; `scheduleEffect(name, args, delay)` | Partial | A handler resumes on a message; an effect resumes after a delay |
| Triggers: schedule, event ([§5.10](../../spec/STANDARD-v1.1.0.md#510-triggers)) | A user message, a queued message or tool, a scheduled effect. No recurring schedule | Partial | Recurrence is rebuilt from one-shot effects |
| Conditions, gates, failure modes, retries | None of these; a tool error is returned to the model | ACS only | Stay in the executor |
| `parallel_group` | One execution per thread; concurrency only across threads | Partial | Members run in order. The reference executor issues one action at a time, so running each member as a child thread needs a host that schedules the group itself |

### Packaging, versions and conformance

| ACS | Standard Agents | Fit | Combined |
|---|---|---|---|
| A Claude Code plugin and a Python package | A packed agent: an npm package with a `standardagent` field ([Packaging](https://standardagentspec.org/0.2.0/distribution/packaging)) | Fits | A grounded agent ships as an SA package; its tools carry their annotations |
| Classification is data, readable without running code | `package.json` lists entry agents, effects, endpoints and required parent hooks; nothing about tools | Partial | A tool's annotation is readable only by loading the package |
| Workflow catalogs and domain profiles | Nothing comparable; configuration is `env` | ACS only | Shipped as data files; nothing in SA reads them |
| Conformance levels L1 to L4, for validators ([§10](../../spec/STANDARD-v1.1.0.md#10-conformance)) | Requirement lists per page and a runtime summary; no public test suite was found | Fits | Neither covers a grounded agent yet |
| Diagnostics: `code`, `name`, `severity`, `message`, `location` ([§9.8](../../spec/STANDARD-v1.1.0.md#98-diagnostic-format)) | Definition issues: `code`, `severity`, `message`, `path` | Partial | Close enough to convert; SA's codes are listed only in the published types |
| Semantic versioning, a version declared in each document ([§11](../../spec/STANDARD-v1.1.0.md#11-versioning-and-compatibility)) | Versioned folders: older versions are frozen, the current one (0.2.0) is still edited. The types package is 0.45.10 for specification 0.2.0 | Partial | A binding pins both: the specification version and the types version |
| RFCs ([Governance](../../spec/GOVERNANCE.md)) | "A conversation or a pull request is enough to propose a change" | Partial | Proposals to SA go as issues |

### What needs no mapping

Models, providers, prompts, context assembly, threads, the client API, the
file system and code execution have no ACS counterpart. A grounded agent uses
them as Standard Agents defines them. There is one point of contact: ACS asks
a host to attest a delegate's `model_family`
([§5.15](../../spec/STANDARD-v1.1.0.md#515-delegation)), and SA reports no
model family for a child. Two of them touch evidence:

- **Context hooks can hide history from the model.** `filter_messages` and
  `prefilter_llm_history` change what one model request sees, and must leave
  the stored history untouched. Evidence stays on record, but a model can be
  shown less than the record holds.
- **Secrets.** A tool declares which of its variables are `secret`. ACS has no
  normative rule keeping secret values out of evidence anchors (some skills
  say so in prose), so the author of a grounded tool has to.

## A grounded Standard Agent today

[`examples/standard_agents/`](../../examples/standard_agents/README.md) holds
a reference binding and an agent built with it. Its enforcement rests on four
surfaces SA 0.2.0 specifies:

| The binding needs | Standard Agents provides | Requirement |
|---|---|---|
| A place to describe a tool | Tool `annotations` | "`defineTool()` **MUST** return `annotations` unchanged" ([Tools §8](https://standardagentspec.org/0.2.0/specification/tools#8-annotations)) |
| Code that runs before the side effect | The tool's own `execute` | Tool calls run "sequentially in the order they were returned" ([Tools §9](https://standardagentspec.org/0.2.0/specification/tools#9-conformance-notes)) |
| State that outlives a tool call | The thread's key-value store | A write "**MUST** be visible to every subsequent `getValue(key)` on the same thread, across any execution context (tools, hooks, endpoints)" ([Runtime, Durable Key-Value Store](https://standardagentspec.org/0.2.0/infrastructure/runtime#14-durable-key-value-store)) |
| A way for a person to decide, with their identity | An authenticated thread endpoint | "The runtime **MUST** authenticate the request and enforce its thread access policy before invoking the handler" ([Thread Endpoints §4](https://standardagentspec.org/0.2.0/specification/threads/endpoints#4-access-and-authentication)) |

The first three are required of every runtime. Thread endpoints are specified
on their own page, and the Runtime page's conformance summary does not list
them, so the approval path needs a runtime that serves them. Around those
four the example also uses a `tool_call_done` hook for the audit trail,
`state.execution.flowId` to tell one execution from the next, `queueMessage`
to wake the thread after a decision, and the thread file system for its
restore point.

### Classify: the `acs` annotation

A tool is classified by one ontology capability, optionally with a domain:

```typescript
annotations: {
  acs: {
    standard: '1.1.0',
    ontology: '2.1.0',
    capability: 'mutate',
    layer: 'EXECUTE',
    domain: 'config',
    risk: 'high',
    mutation: true,
    requires_checkpoint: true,
    requires_approval: true,
  },
}
```

The flags are the capability's **effective** flags
([Standard §5.2.1](../../spec/STANDARD-v1.1.0.md#521-safety-flags)): a tool
may declare stricter flags than the ontology's, never weaker ones. The schema
is
[`standard_agents_annotation.schema.json`](../../schemas/interop/standard_agents_annotation.schema.json),
generated from the ontology.

SA says annotations are "implementation-specific hints, keyed by the runtime
or tool that reads them", that the specification "defines no annotation
keys", and that a runtime "**MUST** ignore keys it does not" understand. So
`acs` is a key this binding owns, other owners' keys are left alone, and a
runtime that has never heard of ACS carries the classification untouched.

The annotation describes; it cannot enforce. SA is explicit:

> Annotations **MUST NOT** change argument validation, execution, the tool's
> results, or what is sent to the model. A tool behaves identically in a
> runtime that ignores them.

A runtime that changed its behaviour because of `acs` would not conform.
Enforcement therefore has to live somewhere else.

### Which construct for which capability

Any capability can be a function tool. The table gives the construct that
suits each layer, as the
[row-level mapping](../research/analysis/standard_agents_mapping/index.yaml)
works it out.

| Layer | Capabilities | On Standard Agents |
|---|---|---|
| PERCEIVE | `retrieve`, `search`, `observe`, `receive` | Function tools over the thread's own reads (`readFile`, `grepFiles`, `getMessages`, `status()`). `receive` is inbound traffic: a client's message, a thread endpoint, a child's completion. A search the model's provider executes passes through no tool, so nothing anchors its sources |
| UNDERSTAND | `detect`, `classify`, `measure`, `predict`, `compare`, `discover` | A prompt tool, or a function tool that asks `state.decide()` for a typed judgement and maps the answer to the capability's output |
| REASON | `plan`, `decompose`, `critique`, `explain` | Prompt tools. Every capability in the layer is low risk, so no flag needs enforcing |
| MODEL | `state`, `transition`, `attribute`, `ground`, `simulate` | The world model is data the agent keeps in thread files or values, one version per change. `ground` is a function tool that resolves the cited records and asks `state.decide()` whether they support the claim |
| SYNTHESIZE | `generate`, `transform`, `integrate` | A model step that must call one output tool whose arguments mirror the capability's output. The tool checks that each anchor resolves |
| EXECUTE | `execute`, `mutate`, `send` | Grounded function tools, behind approval and, for `mutate` and `send`, a checkpoint. `execute` can run on `state.runCode` where the runtime has it. A `send` scheduled as an effect can still be cancelled before it goes out |
| VERIFY | `verify`, `checkpoint`, `rollback`, `constrain`, `audit` | Grounded function tools. A quorum on `constrain` is counted by code, from one child per reviewer. `audit` is a tool, backed by the audit hook |
| REMEMBER | `persist`, `recall` | Function tools over `setValue` and `getValue`, under a key prefix of their own, with expiry checked on read |
| COORDINATE | `delegate`, `synchronize`, `invoke`, `inquire` | `delegate` is the injected `subagent_create`, or a grounded tool that creates the child. `synchronize` is code over several children. `invoke` is a nested ACS workflow and stays inside the executor; a prompt tool is classified by what it does. `inquire` is a tool whose questions the model then puts to the person |

### Enforce: inside the tool

The Hooks page defines fourteen thread hooks. None is specified to stop a
tool call:

| Hook | When | What it can do |
|---|---|---|
| `tool_call_started` | When the call appears in the model's output | Observe. "The return value **MUST** be ignored; the hook cannot modify the tool call", and its arguments "**MAY** be an incomplete JSON fragment" |
| `after_tool_call_success`, `after_tool_call_failure` | After the tool ran | Replace the result |
| `before_store_tool_result` | Before the result is stored | Replace the result |
| `tool_call_done` | After the tool ran | Observe |

([Hooks §5](https://standardagentspec.org/0.2.0/specification/hooks#5-tool-execution-hooks).)
One message hook comes close. `before_create_message` runs before the
assistant message that carries the calls is stored, and "Failures **SHOULD**
prevent message creation", but the text does not say what then happens to the
calls. The published types add that a runtime "can still perform an insertion
that an execution cannot go on without, such as the message of a model step",
so a failure there does not stop the calls. A hook also cannot be relied on to
fail closed: a hook's "failures are non-fatal to the decorated turn".

SA gives an author's code three other positions ahead of a tool call. Each
has a cost:

- **A provider extension.** An override of `generate` or `stream` returns
  the response that carries the tool calls
  ([Providers §1.3](https://standardagentspec.org/0.2.0/specification/providers#13-provider-extension-factories)),
  so it could drop or replace a call. It receives the thread's `state` only
  "when the runtime has one"
  ([Infrastructure: Providers](https://standardagentspec.org/0.2.0/infrastructure/providers#method-overrides)).
  It belongs to a model definition, not to an agent. It does not see calls made through `invokeTool` or `queueTool`, or
  by a child's models, and the text does not say that a runtime executes only
  the calls an override returns.
- **A handler-backed side.** Code takes that side's turns and can be the only
  caller of the tools that mutate. This changes the agent's shape: the model
  proposes and the handler acts.
- **A guard tool.** A grounded tool can front a tool it did not write and
  reach it through `state.invokeTool()` under `uses`. The model must then be
  unable to call the fronted tool directly, and the 0.2.0 text does not say
  what a runtime does with a call to a tool the prompt did not offer.

The one place where code is certain to run before a tool's side effect is the
tool's own `execute`. `groundedTool` wraps it:

```mermaid
---
title: What a grounded tool checks before it runs
---
flowchart TB
  accDescr: A call to a grounded tool is refused with F502 until a person has approved exactly that call, then refused with F501 or F503 until a checkpoint exists; only when every check passes are the approval and the checkpoint used up and the tool run, and every outcome is written to the thread's trace.
  call[The model calls a grounded tool] --> appr{"Approved, if the capability needs approval?"}
  appr -->|no| f502["Refused: F502, with the digest to approve"]
  appr -->|yes| cp{"Checkpoint present, if the capability needs one?"}
  cp -->|no| f501["Refused: F501 or F503"]
  cp -->|yes| run["Approval and checkpoint used up; the tool runs"]
  run --> out{"Output has the fields the ontology requires?"}
  out -->|no| failed["Error result"]
  out -->|yes| ok["Success result with evidence anchors"]
  f502 --> trace[(Thread trace)]
  f501 --> trace
  failed --> trace
  ok --> trace
```

A refusal is an ordinary SA error result, so the runtime stores it and the
model reads it like any other tool error ("persist tool errors as tool result
messages rather than halting execution"). It carries the ACS code and a
diagnostic in the format of
[Standard §9.8](../../spec/STANDARD-v1.1.0.md#98-diagnostic-format):

```json
{
  "status": "error",
  "error": "F501 CHECKPOINT_REQUIRED: Every earlier checkpoint has been used; each call that requires a checkpoint needs its own. Call a 'checkpoint' tool, then call write_config again.",
  "error_code": "F501",
  "error_data": {
    "code": "F501",
    "name": "CHECKPOINT_REQUIRED",
    "severity": "error",
    "message": "Every earlier checkpoint has been used; each call that requires a checkpoint needs its own.",
    "location": { "tool": "write_config", "capability": "mutate" },
    "suggestion": "Call a 'checkpoint' tool, then call write_config again."
  }
}
```

`error_code` and `error_data` are defined only in the published `ToolResult`
type. The 0.2.0 text uses `error_code` once, in a Runtime Streams example, and
defines neither, so the code is also the first word of `error`.

The rules, and where each comes from:

| ACS rule | In the binding |
|---|---|
| A `checkpoint` must have run before `mutate`, `send` and `rollback` (`requires` edges, [§4.3](../../spec/STANDARD-v1.1.0.md#43-edge-types-and-dependency-semantics)) | A call is refused until a `checkpoint` tool has executed in the thread |
| One checkpoint authorises one step that requires one ([Running workflows](../guides/RUNNING_WORKFLOWS.md#what-the-executor-enforces)) | The newest valid checkpoint is marked used when the call runs; the next call needs its own |
| A checkpoint taken before a wait "no longer authorises the step" ([§5.13](../../spec/STANDARD-v1.1.0.md#513-waiting-for-events), W608) | A checkpoint counts only in the execution it was taken in (`state.execution.flowId`), and for ten minutes at most. A thread that went idle, for instance to wait for a person, needs a new one |
| An action that requires approval runs only on a valid decision ([§5.14](../../spec/STANDARD-v1.1.0.md#514-approval)) | See [Approval](#approval) |
| A refused or skipped step leaves the checkpoint valid | Nothing is used up until every check has passed |
| A capability's output has the fields its contract requires | The return type of `execute` is the capability's output contract. At run time the wrapper checks that every required field is present, that `evidence_anchors` is an array and that a required `confidence` is a number from 0 to 1 |
| A step cannot weaken a capability's flags (W602) | The `requires_*` flags can only be declared `true`; a weaker `risk` or `mutation` fails the definition |

`precedes` and `conflicts_with` edges are not enforced at run time.
`precedes` orders the steps of one workflow, and a thread has no fixed list of
steps to order. `conflicts_with` forbids two capabilities in one
`parallel_group`, and SA runs a thread's tool calls one at a time, so within a
thread the conflict cannot arise.

### Checkpoints

A checkpoint is a `checkpoint` tool like any other grounded tool: its code
saves whatever a rollback would need, and returns a `checkpoint_id`. The
wrapper records the id in the thread's key-value store, where later calls
find it.

Approval is checked before the checkpoint, as in the reference executor, and
a checkpoint counts only in the execution it was taken in, and for ten minutes
at most. The time limit is the rule the binding guarantees. The execution rule
rests on each execution of a thread having its own `flowId`; the 0.2.0 text
calls it the "Unique execution ID" and says no more, so that rule holds as far
as a runtime issues a new id when an idle thread runs again. A call made
outside an execution, as from a thread endpoint, has no `flowId`, and
neither a checkpoint nor an approval authorises it: SA runs one execution of a
thread at a time and does not serialise endpoint requests with it. Where the executor
finds no valid checkpoint it asks its host to take one; a tool has nobody to
ask, so it refuses and names what is missing. The order that works is
therefore: ask, wait for the approval, then take the restore point and make
the change in the same execution. The restore point then describes the state
just before the change, however long the approval took.

What a checkpoint can restore is what its tool saved. In the example that is a
file in the thread's file system. SA has no snapshot or undo of its own. Of a
handler turn that fails, it says: "The inbound message stays persisted.
Nothing is rolled back."
([Handlers §5](https://standardagentspec.org/0.2.0/specification/handlers#5-error-semantics))
For an effect outside the thread, such as a sent email, a checkpoint tool can
only record enough to compensate. This is the same limit ACS has everywhere:
the standard requires that a restore point exists, and the host decides what
restoring means.

### Approval

SA's own pattern for a person's decision is the approval gate: a child agent
with a human-backed side, which "parks in `awaiting_human` until the approver
responds"
([Agents §7](https://standardagentspec.org/0.2.0/specification/agents#7-human-in-the-loop-composition)).
The specification defines "only the waiting state and its fulfillment". In
that pattern a model reads the person's reply and records the decision by
calling a tool, so what gets recorded is the model's reading of the reply.

The binding records the decision without a model in between:

```mermaid
---
title: How an approval reaches a grounded tool
---
flowchart TB
  accDescr: The tool stores what must be approved under its digest and is refused; the person's client reads the pending request and its round from an authenticated endpoint and posts a decision on that round; the runtime authenticates the caller, the endpoint records the decision under the same digest and wakes the thread; the model calls the tool again and the tool finds the decision by recomputing the digest from its own arguments.
  t1["Tool call: write_config"] --> rec[("Thread key-value store: request, keyed by digest")]
  t1 --> refused["Refused: F502"]
  rec --> get["GET acs/approvals: what is pending, what it covers, its round"]
  get --> person([A person decides])
  person --> post["POST acs/approvals: digest, round and decision"]
  post --> auth{"Runtime authenticates the caller"}
  auth -->|caller identity| dec[("Decision recorded under the digest")]
  dec --> wake["Thread woken by a queued message"]
  wake --> t2["Tool call again, same arguments"]
  t2 -->|recomputes the digest| dec
  dec --> runs["The tool runs; the approval is marked used"]
```

- **What is approved.** The shown values are
  `[{ action, capability, args }]`: the tool's name, its capability and its
  validated arguments. Their digest is the SHA-256 of their RFC 8785 canonical
  JSON, as [§5.14](../../spec/STANDARD-v1.1.0.md#514-approval) defines it. The
  binding's digest is tested against digests the reference executor computed.
- **Who approves.** `auth.caller` in the endpoint is "the authenticated
  identity when the request presented credentials the runtime verified". The
  model cannot produce it, and the endpoint never reads model output. Outside
  the Draft Users page, a thread endpoint is the only place in the 0.2.0 text
  where package code is handed an authenticated caller.
- **A caller is not necessarily a person.** A runtime may authenticate an API
  key as well as a session, and `ThreadUser` does not say which kind of party
  it describes. `approver.kind: human` is therefore asserted by the
  deployment, not attested by SA. A deployment has to keep every credential
  the runtime accepts out of reach of the agent's tools; a tool that can make
  an HTTP request with such a credential could approve its own request.
- **Why the model cannot shortcut it.** The tool reads the decision from the
  key-value store by recomputing the digest from the arguments it was actually
  called with. A message saying "approved" changes nothing, and an approval
  for one set of arguments does not match another.
- **Single use, expiry, several approvers, roles.** As in §5.14, a decision is
  used once, may expire and may need several distinct approvers. The binding
  also checks `approver.role`, which §5.14 names without saying how it is
  checked, against the caller's application roles. A decision is made on one
  round of a request. Once a round is rejected, expired or used, a call with the
  same values opens the next round, and a decision sent for a closed round (one
  made on a list loaded before another approver rejected, or a client's retry
  after the approval was used) is refused with 409. The same decision sent
  again for its own round is answered as the first was.
- **The settings are part of the tool.** The role, the number of approvers
  and the expiry are fixed in the tool's definition. They are not read from
  `state.env()`, which code in the thread can set. `groundedTool` refuses,
  when the tool is defined, a `min_approvers` that is not an integer of at
  least 1 and an `expires_ms` that is not a number of milliseconds above zero.
- **Decisions that arrive together.** Nothing serialises two endpoint
  requests, and the key-value store has no conditional write. A decision
  therefore never rewrites the request: a rejection sets one fixed key, and
  each approval is stored under the approver's own key. A request can lose an
  approval that way, and never a rejection. A rejection can also arrive while a
  call that read the request as approved is starting. The tool marks the
  approval used and then looks for a rejection; the endpoint stores the
  rejection and then looks for that mark. At least one of the two sees the
  other, so a rejection the endpoint answers as recorded always stops the
  call, and one that arrives after the call used the approval is answered 409.

| §5.14 field | In the binding |
|---|---|
| `approver.kind: human` | The authenticated caller of the endpoint. That the caller is a person is the deployment's assertion |
| `approver.role` | `approval.role`, checked against the caller's `roles` |
| `approver.min_approvers` | `approval.min_approvers`, an integer of at least 1, counting distinct callers whose approval has not expired |
| `mode` | Not distinguished: the Standard names `in_session` and `out_of_band` without defining them. The decision always arrives through the endpoint, not the conversation |
| `shows`, `binds_to: digest` | The action, capability and arguments; the digest of their canonical JSON |
| `recheck` | Implicit: the digest is recomputed from the arguments at the moment the tool runs |
| `expires` | `approval.expires_ms`. As in the reference executor, no decision is accepted later than `expires_ms` after the request. Each approval then counts for `expires_ms` after it was given: the executor uses a decision when it arrives, a tool when the model calls again, so a request can be used up to twice `expires_ms` after it was made |
| `approver.kind: standing_mandate`, `when_unattended` | Not implemented: an unapproved call is refused, which is `when_unattended: fail` |

### Evidence and audit trail

Every ACS capability returns `evidence_anchors`. A grounded tool's `execute`
must return them as an array, and the wrapper refuses an output without them. The result
the model sees is the capability's output as JSON, anchors included.

Each call, refused ones too, becomes an entry in a trace kept in the thread's
key-value store: the tool, its capability, a digest of its arguments, the
outcome, the checkpoint and approval it used, and its evidence anchors. The
entry is written as `started` before the tool's own code runs and completed
when it returns, so a call that is cut off in between (the client API's stop
route "**MUST** abort the execution in flight") still shows what it used.

Two SA limits shape this part:

- **A tool is not told which call it is serving.** `execute` receives the
  thread state and the arguments; hooks receive the call. A tool can look for
  its call in the last assistant message on `state.execution.messageHistory`,
  which is ambiguous for two identical calls and has nothing for `invokeTool`
  or `queueTool`. The binding's `tool_call_done` hook therefore joins the two,
  giving each trace entry the id of the call that produced it, and adding an
  entry for any call it is told about that no grounded tool recorded. It
  matches by tool name among the entries of its own execution and model step,
  oldest first. An entry of an earlier step or execution, whose hook did not
  run, keeps no id; within one step, the next call of the same tool gives its
  id to such an entry.
- **A tool result has no metadata slot.** `HookToolResult` is `status`,
  `result`, `error`, `stack` and `attachments`. Evidence has to travel inside
  `result`, as text the model also reads.

### Checking a prompt before it runs

The ACS validator checks a workflow against the ontology before anything
runs. A prompt has no steps, but it has a fixed list of tools, and
`lintPromptTools` checks what can be checked from that list: every tool is
classified, each grounded tool states the name the prompt offers it under (the
name an approver is shown and the trace records), and no tool needs a
capability the prompt never offers. A prompt
with a `mutate` tool and no `checkpoint` tool is an error, because the model
could never get the call accepted.

`lintAgentBindings` checks an agent definition. `stopTool`, `sessionStop`,
`sessionFail` and `sessionStatus` act when the named tool is called
([Agents §1.2](https://standardagentspec.org/0.2.0/specification/agents#12-sideconfig)),
and the text does not make any of them depend on the call's result. A refused
call to a bound tool could therefore end the turn or the session, and hand a
parent the model's text for an action that never ran. Binding a tool that can
be refused is an error; bind a separate tool that the model calls once the
gated one has succeeded.

### What this guarantees, and what it does not

| It holds | It does not hold |
|---|---|
| A grounded tool never runs its side effect without the checkpoint and approval its capability requires | A tool defined with plain `defineTool` is not covered. No hook lets the binding, a runtime or a composing agent add the check from outside, and the [indirect routes](#enforce-inside-the-tool) each reshape the agent or rest on behaviour the text does not state |
| An approval applies to exactly the arguments shown, once, and only to a call made in an execution | The trace, the checkpoint records and the approval decisions are as trustworthy as the thread's key-value store. Any code running in the thread can write them, including a hook that a composed child requires of it. The binding stops a model from skipping a checkpoint or an approval; it is not a boundary against other code in the thread. Two calls that a tool's own code starts together through `state.invokeTool()` are taken one at a time only where the runtime runs them in one JavaScript realm; the 0.2.0 text does not say where an invoked tool runs |
| The approver's identity is the one the runtime authenticated | Identity is as strong as the runtime's authentication, which SA leaves "implementation-defined", and an authenticated caller need not be a person |
| Every grounded call is recorded, including refusals. A call cut off while its tool runs stays recorded as `started`, with the approval and checkpoint it used. A store write that fails after an approval or checkpoint was used leaves a `failed` entry naming them, if the store accepts that entry | The audit hook is best effort: a hook failure is "non-fatal", and a runtime "**SHOULD**" time hooks out. A call whose hook did not run keeps no call id, and within one model step the next call of the same tool takes its entry |
| A checkpoint older than ten minutes is not accepted, and none is accepted outside an execution | That a checkpoint taken before the thread last went idle is refused sooner than that rests on each execution having its own `flowId`, which the 0.2.0 text does not state |
| The classification survives packaging and any conforming runtime | No runtime acts on it |
| | A provider-executed tool does not pass through a grounded wrapper, so it cannot be grounded this way |
| | A write made by an effect, a hook, a handler or a thread endpoint does not pass through any tool's `execute`. Code that runs in an execution can route its writes through a grounded tool with `state.invokeTool()`. In an endpoint `state.execution` is null, and the text does not say what it is in an effect; a tool that needs a checkpoint or an approval refuses there, so a deferred write is checked when it is scheduled |
| A rejection is never lost to an approval made at the same moment, and a rejection the endpoint answers as recorded stops a call that is starting on that approval | The store has no conditional write, and SA does not serialise endpoint requests with one another or with a running tool call. Two approvals that arrive together can lose one, which leaves the request pending until that approver decides again. A rejection that arrives after the call used the approval is answered 409, and the change runs |

The example has been type-checked against `@standardagents/spec` 0.45.10 and
its rules are tested against an in-memory `ThreadState`. It has not been run
in a Standard Agents runtime.

## Running ACS workflows with Standard Agents

Standard Agents has no workflow format. What runs next is decided by whatever
backs a side: a model following a prompt, or handler code. ACS has a workflow
format and an executor that "does no I/O": it names the next action, a host
performs it and reports back
([Running workflows](../guides/RUNNING_WORKFLOWS.md)). The two fit as
executor and host. Three arrangements are possible, and one needs nothing new
from either standard.

```mermaid
---
title: Three ways to run an ACS workflow with Standard Agents
---
flowchart TB
  accDescr: With the executor in Python, outside Standard Agents, an agent is reached through the Thread Client API and performs one capability, which needs nothing new from either standard; running the executor inside a thread, with a handler as its host or a tool the model calls advancing the run, needs a JavaScript build of the executor that does not exist yet.
  q{"Where does the ACS executor run?"}
  q -->|outside, in Python| out["A Standard Agent performs one capability, through the Thread Client API"]
  out --> today(["Needs nothing new"])
  q -->|inside a thread| inside["Needs a JavaScript build of the executor"]
  inside --> h["A handler-backed side is the host"]
  inside --> t["A tool the model calls advances the run"]
```

| Arrangement | How | State |
|---|---|---|
| The executor outside, an SA agent as one capability | The Python host answers `InvokeCapability` by creating a thread, sending the inputs as a message and reading the result, through the [Thread Client API](https://standardagentspec.org/0.2.0/specification/threads/client-api) | Needs nothing new, with any runtime that exposes that API (a runtime "**SHOULD**"). It has not been built or run here. The result is the agent's last message, parsed as JSON |
| A handler as the host | A handler-backed side restores the run from the thread's key-value store on each inbound message, answers the pending action, performs the next ones and saves the run | Needs the executor in JavaScript |
| A tool the model calls | A function tool submits the model's output for the pending step and returns the next step | Needs the executor in JavaScript. Order is advisory unless every tool that can mutate guards itself, as grounded tools do |

With a handler as host, each executor action has a Standard Agents mechanism:

| Executor action | In a Standard Agents thread |
|---|---|
| `InvokeCapability` | `state.invokeTool(name, inputs)`, or a child agent for `delegate`. The result string is parsed and checked against the capability's output contract |
| `CreateCheckpoint`, `Rollback` | A grounded `checkpoint` or `rollback` tool |
| `RequestApproval` | An approval record and an authenticated endpoint, as in the binding. The executor supplies the shown values and the digest |
| `AwaitEvent` | The handler returns. An inbound message, a child's completion, or an authenticated endpoint that queues the event wakes it |
| `Sleep`, deadlines | `scheduleEffect(name, args, delay)` with an effect that queues a message. SA requires only that an effect is enqueued and its arguments kept, so the handler also calls `run.tick(now)` on every inbound message |
| `Completed`, `Failed` | `state.stopSession({ result })`. SA gives code no way to end a session as failed, so a `Failed` run is a successful stop whose `result` carries the code |
| The run between turns | `run.snapshot()` in the key-value store or a file, restored at the start of the next turn |

What stands in the way is the language, not the design. The reference core is
a Rust crate with Python bindings. It compiles for `wasm32-unknown-unknown`
without source changes, but exports no JavaScript interface, and its context
loads the ontology from file paths. A WebAssembly build also needs a runtime
whose definition code can load WebAssembly, which SA 0.2.0 does not say; a
plain TypeScript build of what a tool-calling binding needs (the ontology
table, effective flags, canonical JSON, the digest) has no such dependency. See
[Changes proposed to ACS](#changes-proposed-to-the-agent-capability-standard).

Until then, the rules a workflow would enforce by position are enforced per
call by grounded tools. That covers the checkpoint and approval rules. It does
not cover the `precedes` ordering of
[§3.3](../../spec/STANDARD-v1.1.0.md#33-safety-by-construction), or what only a
workflow has: gates, conditions, typed bindings between steps, failure modes
and recovery.

## Composing grounded agents

A Standard Agents child runs in its own thread, with its own key-value store
and files. The store's rules say: "Values **MUST NOT** be automatically
copied, inherited, or synchronized between threads when subagents are
spawned." The records the binding keeps are therefore per thread, and three
things follow.

- **Each agent grounds its own tools.** A parent's checkpoint does not cover
  what a child changes, and a parent's approval does not reach a child's
  tools. A child that mutates takes its own checkpoints and asks for its own
  approvals, in its own thread.
- **A parent cannot see what a child may do.** Nothing in a child's definition
  that a parent can read says whether it mutates. `subagent_create` is
  injected by the runtime and has no `execute` to wrap. A parent that wants to
  gate a delegation has to spawn the child from its own code, a grounded tool
  or a handler, with every relationship on that side `hidden`. The rule is
  "For a prompt-backed side with non-hidden relationships, runtimes inject
  three built-in tools", so one visible relationship brings them back. This
  also relies on the runtime refusing a `subagent_create` call the model was
  not offered; the text requires that for "undeclared or disabled"
  relationships and does not mention hidden ones. Nor does it yet say how
  code names that call.
- **A child can require its audit hook of its parent.** `parentHooks` lets an
  exposed child name hooks that the composing agent must run, and a missing
  one "**MUST** fail composition closed". A grounded child can use this so
  that whoever composes it also records its use. No hook can refuse a tool
  call, so this carries observation, not enforcement.

One limit applies inside a single agent too. An agent's `hooks` are a
fallback: "If the prompt has no hooks, the agent's `hooks` array is the
parent's fallback base set"
([Hooks §1.3](https://standardagentspec.org/0.2.0/specification/hooks#13-hook-scoping)).
A prompt that lists hooks of its own drops the agent's. The audit hook has to
be listed on every prompt that lists hooks of its own, and on the agent for
the prompts that list none.

### How a `delegate` step maps to a host

When the reference executor runs a workflow, a `delegate` step reaches the
host as an `InvokeCapability` action, and what a delegation is on the host is
the host's to decide. The Standard distinguishes a delegate that waits from
one that does not
([§5.13](../../spec/STANDARD-v1.1.0.md#513-waiting-for-events)) and has the
host report what it did
([§5.15](../../spec/STANDARD-v1.1.0.md#515-delegation)). The table gives the
host's part in each case and where it lands on Standard Agents. Its statements
come from rows `coord-01` to `coord-03`, `coord-05`, `coord-21` and `coord-22`
of the
[multi-agent mapping](../research/analysis/standard_agents_mapping/multi-agent.yaml)
and rows `wf-16` and `wf-20` of the
[workflow mapping](../research/analysis/standard_agents_mapping/workflow-execution.yaml).

| In the workflow | What the host does | On Standard Agents |
|---|---|---|
| A waiting delegate: a `delegate` step with `wait` and a `timeout`, in a workflow that declares `wait@1`. It "first delegates (an ordinary capability call), then waits for that delegate's result" | Answers the call with `accepted: true` and a string `task_id` (without one the step is R402). The executor then issues `AwaitEvent`, and the host answers it with that delegation's result when it arrives. The result is something the host waits for; one `timeout` bounds the call and the wait | A non-blocking relationship: the host records the child's reference under the `task_id` and reads the result from the child's own thread. A `blocking: true` relationship also returns the result, as the return value of the call, but SA sets no bound on that wait and the host is inside the call when the deadline passes ([Subagents §3.3](https://standardagentspec.org/0.2.0/specification/subagents#33-blocking-and-create-or-continue)) |
| A plain delegate: a `delegate` step without `wait` | Answers the call once the delegation is made. The step completes and the run goes on. A later `receive` step with `wait` and `correlate` can collect the result | A non-blocking child. Behind a blocking relationship the step would look instantaneous to the executor while the child ran, and checkpoints taken before it would stay valid across that time |
| A delegation the host refuses, for example over an instance cap | Reports `accepted: false` in the output, or answers the call with an `Error` | `maxInstances` is the "Cap on simultaneous instances" of a relationship, and creation beyond it returns a tool error (a MUST in [Runtime §7.2](https://standardagentspec.org/0.2.0/infrastructure/runtime#72-lifecycle-tooling), a SHOULD in [Subagents §1](https://standardagentspec.org/0.2.0/specification/subagents#1-subagentrelationship)). The host turns that error into one of the two answers |

What a refusal does depends on the form of the step.

- **On a waiting delegate it fails the step.** "A delegation the host did not
  accept (`accepted` not `true`) is R402." The step's retries and failure
  modes then apply.
- **On a plain delegate it fails nothing.** `accepted: false` is an ordinary
  output: the step completes and the next step runs. The refusal has an effect
  only where the workflow tests the value in a gate or a failure mode, as the
  reference catalog's `multi_agent_orchestration` does with
  `when: ${delegate_out.accepted} == false`. A host that wants the refusal to
  fail the step answers `Error` instead; any code other than R401 is read as
  R402 ([Running workflows](../guides/RUNNING_WORKFLOWS.md#actions-and-responses)).

Two Standard Agents behaviours limit what the host may report.

- **Create-or-continue is not a fresh context.** With `blocking: true` and
  `maxInstances: 1`, `subagent_create` on an existing instance continues it
  instead of creating one. A continued instance holds the history of its
  earlier sessions, so the host reports `effective.fresh_context: true` only
  for an instance it created for this call.
- **A retry needs room under the cap.** A retry of a waiting delegate
  "delegates again, and the new capability call names the delegation it
  replaces (`replaces`, its `task_id`) so the host can cancel it". The host
  terminates the old child and creates a new one. SA does not say whether a
  terminated instance still counts toward `maxInstances`, so a relationship
  whose delegations may be retried or replaced leaves it unset.

**The step's flags do not follow the target.** The ontology gives `delegate`
`risk: medium` and `mutation: false`, and neither `requires_checkpoint` nor
`requires_approval`. A `delegate` step therefore validates and runs with no
checkpoint and no approval, whatever the target agent does. Until the Standard
relates the step's flags to its target (the change on what crosses a
delegation, [proposed below](#changes-proposed-to-the-agent-capability-standard)),
the workflow author raises them on a step whose target can change state: a
declaration stricter than the ontology "is allowed and takes effect"
([§5.2.1](../../spec/STANDARD-v1.1.0.md#521-safety-flags)).

```yaml
- capability: checkpoint
  purpose: Save a restore point before handing the change over.
  store_as: checkpoint_out
  input_bindings:
    scope: service_config
- capability: delegate
  purpose: Hand the change to the deploy agent.
  requires_checkpoint: true
  requires_approval: true
  store_as: delegate_out
  input_bindings:
    task: {apply: rotate_certificate}
    agent: deployer
```

With `requires_approval: true` the executor asks for approval before it
delegates, as the reference catalog's `multi_agent_orchestration` does. With
`requires_checkpoint: true` the step needs a `checkpoint` step before it
(F501 without one) and uses that checkpoint up. A target that must change
nothing is bound `read_only: true` instead; the host attests it in
`effective.read_only`, and the Standard "does not say how a host enforces
`read_only`". The raised flags act in the delegating workflow only. Its
checkpoint covers its own state, not what the child changes, as the first
point under [Composing grounded agents](#composing-grounded-agents) says.

## Packaging and conformance

A grounded agent is an ordinary Standard Agents package. The example's
[`src/package.ts`](../../examples/standard_agents/src/package.ts) exports the
registries the Packaging page describes, and a test loads each tool through
them and finds its annotation intact. The binding uses only surfaces the
specification defines (tools, the key-value store, thread endpoints, hooks),
so it meets the rule that packed definitions "MUST NOT require private runtime
RPCs". One dependency lies outside the specification: the digest uses Web
Crypto (`crypto.subtle`), and the endpoints use `Request` and `Response`. SA
0.2.0 does not say which platform globals definition code may use, so a
runtime without Web Crypto would need a bundled SHA-256.

Three things a consumer of such a package cannot yet do:

- **Read the classification without running code.** Annotations are on tool
  definitions, behind loaders. `package.json` names a package's entry agents,
  effects, endpoints and required parent hooks, and says nothing about its
  tools.
- **Claim conformance.** ACS conformance levels describe validators. Nothing
  in either standard says what it means for an agent, or a runtime, to be
  grounded.
- **Rely on a version pair.** The specification is 0.2.0; the types package
  that an agent compiles against is 0.45.10 and declares
  `SPEC_VERSION = "0.2.0"`. The two version independently, and the types
  contain members the 0.2.0 text does not define. A binding has to pin both.

## Changes proposed to the Standard Agent Specification

Each is written up as an issue for `standardagents/spec`, under the headings
a recent pull request there uses (problem, proposed rule, alternatives,
conformance impact). The texts are in this repository under
`tasks/standard-agents-upstream/`. None has been filed yet.

| Proposal | What it would allow |
|---|---|
| **A hook that runs before a tool executes and can decline the call.** `before_tool_call` returns a result to use in place of running the tool, or nothing to let it run. A hook that fails declines the call | A safety rule imposed on tools one did not write, by an agent on itself or by a child on its parent. This is the one change that turns cooperative enforcement into imposed enforcement, for an agent's own prompts and for a child's parent. It would not let a composing agent gate the calls inside a packaged child |
| **Record the authenticated caller on a message sent through the Thread Client API.** A read-only `user_id` on the message record, set by the runtime and `null` on every other message | Telling a client's answer from a message a model or a parent queued. An approval gate built on messages cannot be trusted without it |
| **Let a tool know which call it is serving.** The call's id and name on `state.execution` while `execute` runs | Evidence, audit entries and idempotency keys tied to the stored tool result, without matching by order |
| **Specify what `execute` returns, and add a metadata field.** Define `ToolResult` in the text, carry `error_code` and `error_data` through hooks and storage, and add `metadata` that is stored but not sent to the model | Refusal codes that clients can act on, and evidence that is not model-facing text |
| **Annotations on agents and prompts, and on the call a hook receives.** The same inert field on `defineAgent` and then `definePrompt`, a tool's annotations passed to its hooks, and a stated subject for the rule, so that it reads as a requirement on runtimes | A composed agent that carries a classification, and hooks that can read a tool's |
| **What a runtime does with a tool call the request did not offer.** Such a call, and any call under `toolChoice: 'none'`, is not executed and gets an error result; the same for a model's lifecycle call that targets a hidden relationship | A prompt's tool list and `hidden` as boundaries. A read-only prompt, a guard tool and a gated delegation rest on it |
| **The lifecycle operations code calls to create and message a child.** The call, its arguments, how the caller gets the new reference, what a child without a side A prompt accepts, and which user a child thread has | A delegation that is checked first: the injected `subagent_create` has no `execute` to wrap, so the child has to be created from code |
| **What may run alongside an execution, and when `flowId` changes.** A definition of a flow, what is serialized with a running execution, and a `flowId` that is unique per execution | Records that are read and rewritten without a conditional write, and a checkpoint rule keyed on `flowId` |
| **Editorial.** Ten places where two passages disagree, such as two sections numbered 14 on the Runtime page | Nothing for grounding; found while checking references |

The nine come out of 83 findings about the specification, none of which
stops a grounded agent from being built and 29 of which leave a rule
enforceable only cooperatively or with a workaround. They are listed, with
evidence and with the issue that covers each, in
[`findings_standard_agents.yaml`](../research/analysis/standard_agents_mapping/findings_standard_agents.yaml).
Among those not written up as proposals: which tool calls fire the tool
hooks; no way for code to end a session as failed; scheduled effects have no
delivery guarantee; the thread file system has no durability or isolation
rules like the key-value store's; a parked human turn has no deadline; and a
child returns text and files but no structured data.

## Changes proposed to the Agent Capability Standard

The mapping tested ACS against a host it was not designed around, and found
gaps of its own: 64 findings, listed with their evidence and their status in
[`findings_agent_capability_standard.yaml`](../research/analysis/standard_agents_mapping/findings_agent_capability_standard.yaml).
What could be fixed without changing the Standard's text has been fixed in
this repository. The rules a binding needs are proposed in
[RFC-0005](../../spec/RFC-0005-tool-calling-hosts.md), a Draft for Standard
1.2.0. The rest waits for the maintainers' decision, as
[GOVERNANCE](../../spec/GOVERNANCE.md) requires for normative changes.

### Fixed in this repository

- **The Python SDK fails closed and follows the ontology.**
  `ToolCapabilityMapper` used to classify a tool it did not know as `observe`
  with no checkpoint, and `register_mcp_tool` accepted an unknown capability
  and a declared risk below the ontology's. An unknown tool now gets the
  strictest classification, an unknown capability is refused (V101), and a
  weaker declaration has no effect and is reported (W602). The adapter asks
  the host's permission flow for the approval the ontology requires of
  `execute`, `mutate` and `send`, and its refusals open with the diagnostic
  code. Evidence anchors no longer store a tool's input unless asked to.
- **The plugin's hooks.** The audit hook logs every tool call, with a digest
  of the input in place of the input. The skills' command hooks block with
  the exit code Claude Code blocks on; they used one that blocked nothing.
- **Data a binding can load.**
  [`standard_agents_mapping.yaml`](../../schemas/interop/standard_agents_mapping.yaml)
  holds this binding's conventions, and
  [`capability_contracts.schema.json`](../../schemas/generated/capability_contracts.schema.json)
  renders the 72 capability contracts as strict JSON Schema 2020-12.
- **Vectors other implementations can test against**: the reference
  executor's approval digests and the trust score arithmetic of §8, listed in
  [CONFORMANCE.md](../../spec/CONFORMANCE.md).
- **Documents that say what is enforced.** Domain profiles are presented as
  informative data, which they are: no shipped component applies one. The
  executor's trace kinds are listed and tested.

### Proposed in RFC-0005

1. **How the rules apply to a stream of tool calls.** The Standard defines
   its rules over the steps of a workflow and does not define a safety layer.
   The RFC says what a `requires` edge means over a sequence of calls, how
   long a checkpoint stays valid and when it is used up, what an approval for
   a call shows and binds, and how a refusal is reported. The reference
   implementations disagreed on several of these.
2. **A tool binding record.** The word "tool" does not occur in the
   Standard. The RFC proposes one record (capability, domain, declared flags,
   ontology version) and the rules for an unclassified tool, a tool that
   performs several capabilities and a tool whose capability depends on its
   arguments.
3. **One evidence anchor item.** `evidence_anchors` has no item schema, and
   the schemas and the Python SDK use three different vocabularies of anchor
   kinds.

### Still open

- **A JavaScript build of the core.** A published TypeScript package of what
  a tool-calling binding needs (the ontology table, effective flags,
  canonical JSON, the digest) would replace the private copy this binding
  keeps. A WebAssembly interface to the validator and executor would let ACS
  workflows run inside a Standard Agents thread; the crate already compiles
  for `wasm32-unknown-unknown` unchanged. This is the roadmap's
  [multi-language SDKs](https://github.com/synaptiai/agent-capability-standard/issues/83)
  item.
- **What crosses a delegation.** A delegate's effects are outside its
  delegator's checkpoints, and the ontology gives `delegate` no checkpoint or
  approval flag whatever the target may do. The Standard should say so, and
  an agent manifest would let a validator derive a `delegate` step's flags
  from its target. Until then a workflow author raises the step's flags
  ([How a delegate step maps to a host](#how-a-delegate-step-maps-to-a-host)).
- **What applying a domain profile changes**, and **a rule that keeps
  secrets out of evidence, audit records and stored data**, both normative.
- **The host protocol as a published schema**, with a conformance class for
  executors; today it is described in a guide and defined in Rust types.

Standard Agents also does several things ACS could learn from: numbered,
testable runtime rules for storage; `uses`, a declared and enforced list of
what a composite unit may call; `parentHooks`, by which a component states
what it needs of whoever composes it; and persistent delegations that can be
continued instead of restarted.

## How this analysis was done

- **Sources.** The Standard Agent Specification was read from its repository
  at commit `faccc8b`, all 24 pages of `content/0.2.0`, with the published
  `@standardagents/spec` 0.45.10 type declarations. ACS was read from this
  repository: Standard 1.1.0, the ontology, the RFCs, the reference executor
  and the Python SDK.
- **Mapping.** Ten concerns were mapped separately, each from the full text
  of both sides. Each mapping was then read by two independent reviewers.
  One, told to refute, checked every reference and quotation and searched
  again for everything a row said was absent. The other checked that every
  combination relies only on what the specification requires of every
  runtime, and compiled what it could against the published types. A third
  pass reconciled each mapping with both reviews.
- **Across the concerns.** Two further checks read the ten mappings together.
  One compared rows that rest on the same passage and settled, from the
  sources, every place where two rows would lead two implementers to build
  different things: it changed the text of 43 rows and the relation of 16.
  The other went through every section of both standards looking for
  anything no row accounted for, and added two rows. The result is 319 rows,
  published with their references and quotations in
  [`standard_agents_mapping/`](../research/analysis/standard_agents_mapping/index.yaml).
- **Findings.** The gaps the ten concerns recorded, 259 in all, were merged
  into 83 findings about the Standard Agent Specification and 64 about ACS.
  Each was checked against the sources again, by running code where that was
  the way to check. The 221 questions the concerns left open were checked the
  same way: 22 turned out to be answered by the texts, and the 45 that an
  implementer most needs answered are listed with the findings.
- **This document.** After the reviews, a separate reader checked every
  factual statement here and in the first six proposals against the sources.
  It confirmed 340 and found 6 errors, 18 imprecise statements and 11
  omissions, all corrected. The three later proposals were each drafted from
  verified findings and then given to a reader told to find what was wrong,
  whose corrections are in the texts. Every quoted passage is compared
  mechanically with the source files.
- **The binding.** The example compiles against the published types under
  TypeScript's strict settings. Its rules are tested against an in-memory
  `ThreadState`, and its approval digest is tested against digests produced by
  the ACS reference executor. Three of its rules changed because of the
  mapping: a rejection can no longer be lost to an approval made at the same
  moment, a call is recorded before its tool runs, and a checkpoint is valid
  for ten minutes at most and never outside an execution. A later review of
  its code changed more: a decision applies only to the round it was made on, a
  rejection the endpoint records while a call is starting stops that call, a
  call that needs an approval is refused outside an execution, an approval
  counts for `expires` after it was given and none is accepted after the
  request expired, the audit hook links a call id only within its own
  execution and model step, and canonical JSON refuses unpaired surrogates.
- **What was not done.** The example was not run in a Standard Agents runtime,
  so nothing here is a statement about how any runtime behaves beyond what the
  specification requires of it. No runtime's source and no conformance suite
  was examined. The specification is at 0.2.0 and its maintainers edit that
  version in place; a passage quoted here may have changed since the commit
  above.
