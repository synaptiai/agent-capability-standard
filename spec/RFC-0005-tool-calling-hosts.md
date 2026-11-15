# RFC-0005: Tool-calling hosts
**Status:** Draft
**Target:** Standard v1.2.0
**Date:** 2026-11-14

## Summary

Standard 1.1.0 states its safety rules over the steps of a workflow. For a
host where a model chooses one tool call after another and no workflow runs,
it has one sentence, in [§5.2.1](STANDARD-v1.1.0.md#521-safety-flags):
"Validators, executors and safety layers MUST act on effective flags." It does
not define a safety layer, and the word "tool" does not occur in it.

This RFC proposes how the Standard applies to such a host. It answers findings
ACS-01 (decisions 1, 3 and 9), ACS-02 (4), ACS-03 (5), ACS-06 (8), ACS-08
(6), ACS-38, ACS-39 and ACS-57 (2) and ACS-41 (7) of the
[Standard Agents mapping](../docs/research/analysis/standard_agents_mapping/findings_agent_capability_standard.yaml).
Each numbered rule can be accepted, amended or rejected on its own. None is
normative until a Standard version carries it.

## Motivation

When the mapping was reviewed, four pieces of code in this repository
enforced the safety flags and disagreed:

| Code | Checkpoint use | Lifetime | With none valid |
|---|---|---|---|
| Reference executor (`core/src/exec/machine.rs`) | One per step, used up before it runs | Until a wait or delay ends | Asks the host |
| TypeScript binding (`examples/standard_agents/src/acs/grounded.ts`) | One per call, used up before it runs | One execution, ten minutes | Refuses |
| Python adapter (`grounded_agency/adapter.py`) | One per call, used up after success | 30 minutes | Refuses in strict mode |
| Plugin hook (`hooks/pretooluse_require_checkpoint.sh`) | A marker file, never used up | The marker's expiry | Blocks |

The ontology requires approval for `execute`, `mutate` and `send`. Neither the
hook nor the adapter then asked for it, and a call has no step and no `shows`,
so each binding chooses what to hash. A refusal was prose in one layer and a
§9.8 object in another. The adapter now asks (5.6). The levels of
[§10](STANDARD-v1.1.0.md#10-conformance) cover validators only, so a binding
has nothing to conform to.

## Goals

- Rules over calls that a safety layer on any tool-calling host can
  implement.
- The same effective flags, codes and approval digest as for a workflow; no
  new diagnostic code or capability.
- Fixtures that any language can run.
- No change to what a validator accepts, except through 8.5.

## Non-goals

Not covered here; the findings named stay open:

- Delegation: a `delegate` call's flags, checkpoints across a delegation, and
  an agent manifest (ACS-04, ACS-18, ACS-29).
- Domain profiles, including `required_anchor_types` (ACS-05).
- A schema for the executor's host protocol (ACS-37).

Also left out: standing mandates, `skip` and `defer_to_queue` for a call,
and how a host stores records or authenticates approvers.

## Key decisions

### 1) Three terms are defined

Added to [§2](STANDARD-v1.1.0.md#2-terms):

- **Tool-calling host**: a runtime in which a model chooses each tool call
  and its arguments, and no workflow's step list determines the next action.
- **Tool binding**: a record that states which capability a tool performs and
  which safety flags it declares.
- **Safety layer**: the code that decides, before a tool's effect, whether a
  call may run under decisions 2 to 6: a pre-call hook, a permission callback
  or a wrapper around the tool's own code.

A **call** is one invocation of one tool. Reason: §5.2.1 places a MUST on
safety layers without defining one.

### 2) One host-neutral binding record

A JSON Schema, `tool_binding.schema.json`, under `schemas/interop/`:

| Field | Required | Meaning |
|---|---|---|
| `tool` | yes | The tool's name on the host |
| `capability` | yes | An ontology capability id |
| `domain` | no | The capability's domain parameter |
| `flags` | no | Declared safety flags (§5.2.1) |
| `additional_capabilities` | no | Other capabilities the same call performs |
| `invokes` | no | Names of the bindings the tool calls |
| `ontology` | yes | The ontology version used |

- **2.1** An unknown capability id is V101, as for a step, and the binding is
  not loaded.
- **2.2** Effective flags are the stricter of declaration and ontology, as
  for a step: a weaker declaration has no effect and is W602, except
  `mutation: false` on a `mutation_overridable` capability. Reason: a tool's
  author gets no power a workflow's author lacks.
- **2.3** A tool with no binding is treated as the strictest case: `risk:
  high`, and `mutation`, `requires_checkpoint` and `requires_approval` true.
  Reason: a layer cannot know that an unknown tool only reads.
- **2.4** A tool that performs several capabilities takes the strictest flags
  across them, flag by flag, and the `requires` edges of each. Reason: one
  call can comment on an issue and close it.
- **2.5** A layer may classify a call from its arguments, as the Python
  mapper reads a shell command. The classifier narrows only for input it
  recognises; otherwise, and when it fails, the declared worst case applies.
  Reason: without it every shell call needs a checkpoint and an approval,
  and with an allow-list the weaker class is never the default.
- **2.6** A tool takes the strictest flags over its own and, transitively,
  those of the bindings in `invokes`. A host SHOULD refuse an invocation
  outside the list. The list bounds named invocation, not storage or network
  calls, so the result is a lower bound.
- **2.7** The record describes; the enforcing code is authoritative. A layer
  computes effective flags from the ontology and the declared flags, and
  ignores copies a carrier holds, such as the annotation's `layer`. A record
  is not evidence of enforcement. Reason: an annotation cannot enforce, and
  a copy can be stale.

The Python SDK's tool `metadata` and the `acs` annotation
(`schemas/interop/standard_agents_annotation.schema.json`) become carriers of
the record. Neither is an instance today: each names its members its own
way, and `tool` is the tool's name on the host.

### 3) Over a call sequence, only `requires` refuses

- **3.1 Scope.** History counts within one scope: the host's unit of
  conversation state, such as a thread or session, in which calls are ordered
  and the layer's records last. The layer names it. A delegate is another
  scope.
- **3.2 `requires`.** A `to` call is refused unless a `from` call completed
  successfully earlier in the scope. A call that started while the other was
  running did not come before it, as in a `parallel_group`
  ([§4.3](STANDARD-v1.1.0.md#43-edge-types-and-dependency-semantics)). A
  missing `checkpoint` is F501, or F503 for `rollback`: the codes the
  executor raises when it cannot take a checkpoint or has none to roll back
  to. Decision 4 says when a checkpoint counts. Any other `requires` edge is
  V102; ontology 2.1.0 has none.
- **3.3 `soft_requires`** never refuses. A layer MAY report W601.
- **3.4 `precedes` is not enforced.** §4.3 applies it "when both are present"
  in a closed step list. A call sequence is open: at the `to` call the layer
  cannot know whether a `from` call will follow, and when one does the
  earlier call has had its effect, so a refusal protects nothing.
- **3.5 `conflicts_with` is not enforced.** It forbids two capabilities in
  one `parallel_group` and allows them in sequence, so a host that runs a
  scope's calls one at a time cannot violate it. Concurrency across calls,
  runs and agents is ACS-16, which stays open.

### 4) One checkpoint per call, until a boundary

- **4.1** One checkpoint authorises one call whose effective
  `requires_checkpoint` is true; overlapping calls never share one. The same
  rule is added for steps. Reason: it is the executor's rule
  ([Running workflows](../docs/guides/RUNNING_WORKFLOWS.md#what-the-executor-enforces)),
  which the Standard does not state: a catalog with one checkpoint before two
  `mutate` steps validates.
- **4.2 When it is used up.** The executor and the TypeScript binding use
  the checkpoint up once every check has passed, before the effect; a call
  that then fails does not get it back. The Python adapter reserves it before
  the call and uses it up after success; a failed call releases it. This RFC
  proposes the first: a layer may never learn a call's outcome, a call that
  reports an error may still have changed something, and a crash between
  effect and record would leave the checkpoint valid for a second change. For
  the adapter's rule: a call that failed and changed nothing costs a
  checkpoint, and the executor runs a step's `retry` attempts under the
  checkpoint the step used. That rule needs the adapter's reservation, so
  that overlapping calls cannot share one.
- **4.3 Validity ends at a boundary.** Under
  [§5.13](STANDARD-v1.1.0.md#513-waiting-for-events) a checkpoint taken
  before a wait "no longer authorises the step". A tool-calling host has no
  `wait` step; its counterpart is a point where the scope stops and later
  resumes, such as a thread that goes idle while a person decides. A prompt
  answered while the call waits (5.6) is not one: in the executor an approval
  is not a wait. A layer states an **execution boundary**, where the host
  exposes one, and a **maximum age**, which also bounds a long prompt. A
  checkpoint authorises a call only before the next boundary and within that
  age.
- **4.4 Rollback.** A `rollback` call needs a checkpoint to exist in the
  scope, valid or not, and uses none up; with none it is F503. Reason, as in
  the executor, whose gates and failure modes roll back to the latest
  checkpoint, valid or not: validity limits what a checkpoint authorises, not
  what it restores.
- **4.5 Refusal.** With no valid checkpoint the call is refused with F501. A
  refused call uses nothing up. The executor asks its host for one here;
  whether a layer may is an open question.
- **4.6 Fail closed.** A layer that cannot read its records or complete a
  check refuses; one that cannot classify a call applies 2.3 or 2.5. A mode
  that only logs is outside the conformance class.

### 5) Approval binds to tool, capability and arguments

- **5.1** A call whose effective `requires_approval` is true runs only on a
  valid [§5.14](STANDARD-v1.1.0.md#514-approval) decision; otherwise F502.
  Approval is checked first, as in the executor and the TypeScript binding,
  so a restore point can be taken after the wait for a person. The Python
  adapter checks the checkpoint first.
- **5.2 What is shown and hashed.** The array `[{"action": <tool name>,
  "capability": <id>, "args": <validated arguments>}]`, which the TypeScript
  binding uses, with §5.14's digest: SHA-256 of its RFC 8785 canonical JSON.
  For a step with no `shows` the executor shows the resolved inputs in an
  array, `[inputs]`. The proposed object carries that value as `args` and
  adds the tool's name and the capability. Reason: the executor's request
  names its step, and a call has no such position; with `[args]` alone one
  decision fits every tool that takes the same arguments.
- **5.3 One decision per call.** The call that runs under a decision uses it
  up; an identical later call needs a new one. Reason: §5.14 requires that a
  decision "has not been used before".
- **5.4** A decision expires after the period the layer states for the tool,
  and counts only when at least `min_approvers` (default 1) distinct
  approvers, as the host authenticated them, agree.
- **5.5** A rejection must not be lost to a concurrent approval: once any
  approver rejects, the request is rejected.
- **5.6 The host's own prompt.** A permission prompt that shows a person
  the tool and the inputs the call will run with, and decides that call
  alone, satisfies 5.1 and 5.3 `in_session` with one approver; binding the
  decision to the call replaces the digest. Every such call goes to the
  prompt, even one an allow-list would pass; a remembered "always allow" is
  not a decision per call. A prompt that is skipped, cannot be shown, or
  shows other inputs than those that run gives F502.
- **5.7** With no one to ask the call is refused with F502, as under
  `when_unattended: fail`.

### 6) A refusal is a §9.8 diagnostic

A refusal is the [§9.8](STANDARD-v1.1.0.md#98-diagnostic-format) diagnostic.
Its `location` holds `tool` and `capability`, and no `workflow` or `step`. On
a text-only channel the text opens with the code and name: `F501
CHECKPOINT_REQUIRED: ...`. Reason: a client can tell which rule refused
without parsing prose, and §9.8 does not change.

### 7) A text-only result carries I-JSON text

Where a tool's result is a string, a capability output is the I-JSON text of
the output object with nothing around it. The consumer parses it and checks
the fields the output contract requires, as the executor does (R402
otherwise). Where the host has validated structure, such as a submit tool's
arguments, that is preferred. A producer checks §5.14's I-JSON limits first.
Reason: each binding otherwise asserts its own encoding and check.

### 8) One anchor item, one kind vocabulary

Every capability output requires `evidence_anchors`, an array with no `items`.
Three `kind` vocabularies exist:

| Where | `kind` values |
|---|---|
| `schemas/event_schema.yaml`, `Anchor` | `file`, `url`, `tool`, `log`, `sensor`, `human_note`, `api` |
| `schemas/world_state_schema.yaml`, `Anchor` | `file`, `url`, `tool`, `log`, `sensor`, `human_note` |
| Python SDK, `EvidenceAnchor` (a free string; the values its code writes) | `tool_output`, `file`, `command`, `mutation`, `coordination` |

- **8.1** One `EvidenceAnchor`, from the event schema's `Anchor`: `ref` and
  `kind` required, `timestamp` and `excerpt` optional.
- **8.2** One `kind` vocabulary, the event schema's seven values, for both
  schemas and the SDK.
- **8.3** A host's own kind carries an `x-` prefix, as vendor fields do.
  `ref` is an opaque string whose schemes the host documents.
- **8.4** An optional `digest`: `sha256:` and the hex digest of the anchored
  content, so a consumer can tell whether it changed.
- **8.5** Outputs gain `items` only once every catalog in the repository
  validates with it in strict mode.

Reason: a consumer cannot check an anchor whose shape each producer chooses.

### 9) A conformance class for safety layers

- **9.1 A class for safety layers**, beside validator levels L1 to L4. A
  layer conforms when, for the calls it covers, it applies decisions 2 to 6
  and passes the fixtures. Its statement names the host, the calls it covers
  and those it cannot see, its scope, boundary and maximum age, and how
  approval is obtained, with its expiry.
- **9.2 Call-sequence fixtures**, language-neutral JSON under
  `tests/conformance/calls/`:

```json
{
  "description": "One checkpoint authorises one call.",
  "ontology": "2.1.0",
  "bindings": [
    {"tool": "save", "capability": "checkpoint"},
    {"tool": "write", "capability": "mutate"}
  ],
  "sequence": [
    {"call": "save", "expect": "run"},
    {"call": "write", "args": {"key": "a"}, "approve": ["alice"], "expect": "run"},
    {"call": "write", "args": {"key": "b"}, "approve": ["alice"], "expect": {"refuse": "F501"}}
  ]
}
```

A fixture is one scope with a person present. Each `bindings` entry is a
record under the fixture's `ontology`; a tool not listed is unbound. A bound
tool succeeds and returns what its output contract requires, and a
`checkpoint` call that runs takes a checkpoint. A `sequence` entry is a call
or an event. A call has `args` (default `{}`), `approve` or `reject` naming
who decided on it beforehand, on its 5.2 value or at the prompt of 5.6
(neither: undecided; one approver needed, no expiry), and `expect`: `"run"`
or `{"refuse": <code>}`. An event is `{"boundary": true}`, or
`{"expire": true}` when the checkpoint maximum age passes. Six sequences,
with `save` bound to `checkpoint`, `write` to `mutate`, `undo` to
`rollback`, and `other` unbound:

| Fixture | Sequence | Expected |
|---|---|---|
| `checkpoint_single_use` | `save`; `write` approved; `write` approved | run; run; F501 |
| `refused_call_keeps_checkpoint` | `save`; `write` undecided; same `write`, approved | run; F502; run |
| `checkpoint_stale_after_boundary` | `save`; boundary; `write` approved | run; F501 |
| `rollback_needs_checkpoint` | `undo`; `save`; `write` approved; `undo` | F503; run; run; run |
| `unbound_tool_is_strictest` | `other` approved; `save`; `other`, new arguments, undecided; same `other`, approved | F501; run; F502; run |
| `decision_single_use` | `save`; `write` approved; `save`; same `write`, undecided | run; run; run; F502 |

No expectation depends on the order of 5.1. A fixture for a failed call waits
for 4.2.

- **9.3 Reference implementations.** The Python adapter and the TypeScript
  binding ([`examples/standard_agents/`](../examples/standard_agents/README.md))
  run the same fixtures: one from a hook before each tool, one from inside
  it. The TypeScript binding sees only the tools it wraps, so
  `unbound_tool_is_strictest` is outside what it covers.

## Backward compatibility

- Validators accept what they accept today, except under 8.5. No code is
  added; existing codes gain a `location` that §9.8 permits.
- The terms, section, class, schema and fixtures are additions: MINOR under
  [GOVERNANCE](GOVERNANCE.md#versioning).
- 4.1, stated for steps, makes the executor's behaviour normative; an
  executor that lets one checkpoint authorise several steps must change.
- The Python adapter changes under 3.2 (it checks no `requires` edge, so a
  `rollback` call with no checkpoint runs), 4.2 and 4.3 (it states no
  boundary). 4.6 puts its non-strict mode outside the class.
- 2.3: a deployment whose unregistered tools ran unchecked must bind them,
  and the SDK's `execute` default for an MCP tool without metadata goes.
- The plugin hook would not conform: its marker is never used up, and it
  asks for no approval.
- 8.2 adds an enum value to the world state schema and 8.4 an optional field,
  both compatible ([§11.4](STANDARD-v1.1.0.md#114-schema-evolution)).
  Renaming the SDK's kinds changes the Python package's anchors. 8.5 can
  reject bare-string anchors, which the skill template writes.
- Existing `acs` annotations and SDK metadata stay valid as carriers (2.7).

## Conformance test updates

- A JSON Schema for the binding record, with instances that fail (V101) and
  warn (W602).
- The fixtures of 9.2, a schema for their format and a runner per reference
  implementation, generated with a `--check` mode like
  `scripts/gen_runtime_fixtures.py`.
- Digest vectors of the 5.2 shape in
  `tests/conformance/approval/digests.json`.
- Refusal fixtures for decision 6.
- §10 gains the class and names the fixtures as normative for it.
- Not testable by fixture: that a host's prompt showed what ran (5.6), and
  that a layer sees every call it claims to cover. Both go in the conformance
  statement.

## Alternatives considered

- **Leave tool-calling hosts to each binding's documentation.** Rejected:
  §5.2.1 already binds safety layers, and this repository's layers diverged.
- **Treat a call sequence as a workflow built as it runs.** Rejected:
  `precedes`, W608 and other static checks need a closed step list.
- **Hash `[args]`, the executor's default.** Simpler, but the digest does not
  say which tool it approves.
- **Classify an unbound tool as `observe`, or refuse it.** The first fails
  open. The second makes a layer unusable on a host with many built-in tools;
  under 2.3 a person can still approve.
- **New diagnostic codes for calls.** Rejected: the existing codes name the
  rule that refused.

## Open questions

1. **Scope and edges (decision 3, ACS-Q01).** Does history count over the
   scope's lifetime or one execution? Is a `precedes` violation, visible only
   at the later call, reported or ignored?
2. **Checkpoints (decision 4, ACS-Q02).** Is one checkpoint per call
   normative for every host? Used up before the effect or after success? May
   a layer take a checkpoint itself in place of refusing? Does the Standard
   cap the maximum age?
3. **Approval (decision 5, ACS-Q03).** `[{action, capability, args}]` or
   `[args]`? One decision per call, or per digest until it expires? Which
   check comes first?
4. **Unbound tools (2.3, ACS-Q04).** The strictest case, `observe` at medium
   risk, or refusal? Does a definition-time report, such as the TypeScript
   binding's `unclassified`, need a code?
5. **Anchors (decision 8, ACS-Q05).** May an item be a bare string? Does an
   empty list satisfy §3.1? How do the SDK's five kinds map to the seven?
6. **Which capability (decision 2, ACS-Q07).** A write to a remote system
   through an API: `mutate` or `send`? A write to the host's own durable
   store: `persist` or `mutate`? A message to an existing delegate:
   `delegate` or `send`? A tool that only signals control, such as a stop
   tool?
7. **Classifiers (2.5, ACS-Q08).** Does "cannot weaken" (§3.3, §5.2.1) extend
   to a tool's declaration, so that no call is classified below its tool's
   worst case?
8. **Placement.** A section of the Standard or a separate profile? A fifth
   level or a separate class?
