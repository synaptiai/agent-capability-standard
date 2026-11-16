# RFC-0005: Tool-calling hosts
**Status:** Accepted
**Target:** Standard v1.2.0
**Date:** 2026-11-15

## Summary

Standard 1.1.0 states its safety rules over the steps of a workflow. For a
host where a model chooses one tool call after another and no workflow runs,
it had one sentence, in [§5.2.1](STANDARD-v1.1.0.md#521-safety-flags):
"Validators, executors and safety layers MUST act on effective flags." It
did not define a safety layer, and the word "tool" did not occur in it.

This RFC decides how the Standard applies to such a host. Standard 1.2.0
carries the decisions as §5.18 (Tool-Calling Hosts), §5.2.2 (Checkpoint Use)
and class SL (§10.4) of [STANDARD-v1.2.0](STANDARD-v1.2.0.md). It answers
findings ACS-01, ACS-02, ACS-03, ACS-07, ACS-08, ACS-36, ACS-38, ACS-39,
ACS-41, ACS-55 and ACS-57, and questions ACS-Q01 to ACS-Q04, ACS-Q07 and
ACS-Q08 of the
[Standard Agents mapping](../docs/research/analysis/standard_agents_mapping/findings_agent_capability_standard.yaml).
The maintainers accepted it on 2026-11-15, with every remaining finding to
be implemented in 1.2.0; the open questions of the Draft are decided below.

## Motivation

When the mapping was reviewed, four pieces of code in this repository
enforced the safety flags and disagreed:

| Code | Checkpoint use | Lifetime | With none valid |
|---|---|---|---|
| Reference executor (`core/src/exec/machine.rs`) | One per step, used up before it runs | Until a wait or delay ends | Asks the host |
| TypeScript binding (`examples/standard_agents/src/acs/grounded.ts`) | One per call, used up before it runs | One execution, ten minutes | Refuses |
| Python adapter (`grounded_agency/adapter.py`) | One per call, used up after success | 30 minutes | Refuses in strict mode |
| Plugin hook (`hooks/pretooluse_require_checkpoint.sh`) | A marker file, never used up | The marker's expiry | Blocks |

The ontology requires approval for `execute`, `mutate` and `send`; the hook
asked for none, and a call has no step and no `shows`, so each binding chose
what to hash. A refusal was prose in one layer and a §9.8 object in another.
No record said which capability a tool performs, a tool with no metadata
became `execute`, and skill-level hooks asked a model whether the user had
approved. The levels of [§10](STANDARD-v1.1.0.md#10-conformance) cover
validators only, so a binding had nothing to conform to.

## Goals

- Rules over calls that a safety layer on any tool-calling host can
  implement, with the same effective flags, codes and approval digest as a
  workflow.
- One host-neutral binding record, with the existing carriers as instances.
- Language-neutral fixtures, run by two reference layers.
- No change to what a validator accepts or what the executor does.

## Non-goals

- Delegation semantics beyond scope: a `delegate` call's flags, checkpoints
  across a delegation and agent descriptors (ACS-04, ACS-18, ACS-29) are
  decided elsewhere in 1.2.0.
- Evidence anchors (ACS-06): decision 8 of the Draft is withdrawn from this
  RFC; the evidence rules of 1.2.0 decide it.
- The executor's host protocol (ACS-37), the send destination policy
  (ACS-52) and the secrets rule (ACS-23), which §5.18.10 references.
- Standing mandates, `skip` and `defer_to_queue` for a call, and how a host
  stores records or authenticates approvers.

## Key decisions

### 1) Terms and placement

§2 defines tool-calling host, call, tool binding, safety layer, layer scope
and execution boundary. The rules are a section of the Standard (§5.18), where
§5.2.1's MUST already points, and conformance is a separate class, SL
(§10.4), not a fifth level: a layer validates no catalog and a validator
checks no call. (Draft open question 8.)

### 2) One host-neutral binding record

`schemas/interop/tool_binding.schema.json`: `tool`, `ontology`, `standard`,
`capability` (or `control`), `domain`, `flags`, `additional_capabilities`,
`classifier`, `invokes`, `approval`, and, for a `send` tool, `destination`
(the argument a destination policy checks, §4.4.2).

- **2.1** An unknown capability is V101; a malformed record S303/S304; an
  unsupported ontology major or cited standard V109; two records for one
  tool V110. A record
  that does not load leaves its tool unbound.
- **2.2** Effective flags are the strictest of declaration and ontology,
  flag by flag; a weaker declaration is W602 and has no effect, except
  `mutation: false` on a single `mutation_overridable` capability. A host
  may refuse such a record; the TypeScript binding does.
- **2.3** An unbound tool is the strictest case: high risk, mutation,
  checkpoint and approval. A host that knows the tools it offers reports
  each unbound one as W617. (Draft open question 4: neither `observe` at
  medium risk, which fails open, nor refusal, which makes a layer unusable
  on a host with many built-in tools; a person can still approve.)
- **2.4** Several capabilities: `additional_capabilities`, strictest flags
  and every capability's prerequisites.
- **2.5** Classifiers narrow per call only for arguments they recognise; the
  record is the worst case. A classification can be weaker than the worst
  case, never weaker than its own capability's ontology flags. (Draft open
  question 7: "cannot weaken" bounds a capability, not a tool's worst case.)
- **2.6** Composites: `invokes`, strictest flags transitively; V107 for an
  unresolved name, V105 for a cycle. A nested call is covered by the
  composite's approval and checkpoint where the layer can attribute it, and
  checked on its own where it cannot; its prerequisites are checked either
  way. Attribution needs evidence that the composite's own code made the
  call (the TypeScript binding's one-shot nesting token), not merely the
  same thread or execution. A nested call outside the list is F504. The
  list bounds named invocation only: the flags it gives are a lower
  bound.
- **2.7** The record describes; the enforcing code is authoritative, and
  copies in a carrier are ignored. The Python SDK's tool `metadata` and the
  `acs` annotation are carriers; the annotation schema now rejects copies
  inconsistent with the capability.
- **2.8** Classification by effect, with a table: a change to a resource
  that can be read back, local or remote, is `mutate`; delivering a
  message, notification or event, or a request of unknown effect, is
  `send`; a write to the agent's own memory store is `persist`, anywhere
  else `mutate`; a restore of a checkpoint taken in the scope, which the
  call names, is `rollback`, and restoring any other state is `mutate`;
  further instructions on a delegated task are `delegate`; a tool that only
  signals the host is control-only. One call a classifier
  reads as several actions takes the strictest flags and every
  prerequisite of all of them. (Draft open question 6.)
- **2.9** Control-only tools are never refused (no gate, no host policy; a
  failure to record one is reported). A host action that follows any call
  of a tool (a stop tool) must not be tied to a tool that is not
  control-only and is unbound, has a prerequisite, or requires a checkpoint
  or approval: F506.

### 3) Over a call sequence, only `requires` refuses

- **3.1** History counts over the scope's lifetime; a checkpoint's power to
  authorise ends at a boundary or its maximum age (decision 4). A delegate's
  calls are another scope unless the layer orders them together and says
  so. (Draft open question 1, first part.)
- **3.2** `requires`: F501 for a missing checkpoint, F503 for `rollback`,
  V102 for any other prerequisite; §9.1 says a V-code keeps its meaning
  when a layer uses it for a call.
- **3.3** `soft_requires` never refuses; W601 may be reported.
- **3.4** `precedes` is neither enforced nor reported: at the earlier call
  nothing is known, and at the later one a refusal protects nothing. (Draft
  open question 1, second part.)
- **3.5** `conflicts_with` is not enforced over calls.
- **3.6** Check and use are atomic per scope: a lock or reservation, or a
  host that runs the scope's calls one at a time, as stated.

### 4) One checkpoint per call, until a boundary

- **4.1** One checkpoint authorises one gated call, and one gated step
  (§5.2.2, the executor's rule): the most recently taken of the valid
  ones, so an earlier valid checkpoint serves once the latest is used. A
  checkpoint is taken by the call that saves the state, not by a call that
  only leads to one (a skill's instructions).
- **4.2** It is used up when the call is allowed to start, before the
  effect, whatever the outcome. A checkpoint held while a host prompt is
  open is re-checked and used in one atomic step when the call is allowed.
  A hold the layer cannot resolve (it lapses, the layer restarts, the host
  never reports a refusal) counts as used. (Draft open question 2: before
  the effect, for every host.)
- **4.3** Validity ends at the next execution boundary the layer names and
  at its maximum age, at most 30 minutes. A prompt answered within the call
  is not a boundary. (Draft open question 2: the Standard caps the age.)
- **4.4** A `rollback` call needs a checkpoint taken earlier, valid or
  not, and uses none; else F503. For workflows, a gate or failure-mode
  rollback restores the latest checkpoint (F503 with none) and a `rollback`
  step restores the checkpoint its input names, as the executor does.
- **4.5** With no valid checkpoint a call is refused with F501; a layer does
  not take one itself. The executor keeps having its host take one for a
  step (§5.2.2). (Draft open question 2.)
- **4.6** Fail closed: R407 when a check cannot complete; a host claiming a
  conforming layer runs no covered call without its decision, or names the
  gap.

### 5) Approval binds to tool, capability and arguments

- **5.1** A gated call runs only on a valid §5.14 decision; else F502.
- **5.2** Shown and hashed: `[{action, capability, args}]`, `capability`
  null for an unbound tool. (Draft open question 3.)
- **5.3** One decision per call, used up when the call starts. (Draft open
  question 3.)
- **5.4** Expiry and `min_approvers` come from the binding's `approval`;
  any rejection rejects.
- **5.5** The order of the approval and checkpoint checks is the layer's;
  neither is used up until both pass. (Draft open question 3.)
- **5.6** A host prompt showing the tool and the arguments, deciding that
  call alone, is a one-approver `in_session` decision; every gated call
  goes to it; the layer records the digest. It cannot meet
  `min_approvers` above 1, nor a `role` the host does not authenticate to
  the layer. A layer relies on a prompt only in host configurations it
  knows to put it to a person, and names them; in any other (a mode that
  approves calls itself or lets a classifier answer) it refuses with F502.
- **5.6a** Arguments the host changes while answering a prompt are
  classified again; the call is refused if it then needs approval, or a
  checkpoint or prerequisite it does not hold.
- **5.7** No one to ask: F502.

### 6) A refusal is a §9.8 diagnostic

`location` holds `tool`, `capability` (absent when unbound) and optionally
`call`; on a text-only channel the text opens with the code and name. A
host policy such as a rate limit is F504; a failure of the layer itself is
R407.

### 7) A text-only result carries I-JSON text

A capability output on a string channel is the I-JSON text of the output
object, nothing around it; the consumer checks required fields (R402); the
producer checks I-JSON limits first (R402); validated structure is
preferred. The rule binds every producer and consumer of a string output,
whether or not a safety layer runs, a host that answers an executor's
capability call from a model's or a sub-prompt's string included.

### 8) (Withdrawn) Evidence anchors

Moved out of this RFC: ACS-06 is decided with the evidence rules of
Standard 1.2.0.

### 9) A conformance class for safety layers

- **9.1** Class SL (§10.4): a layer loads bindings as §5.18.1–§5.18.4
  state, applies §5.18.5–§5.18.9 and the capability checks of §5.18.10,
  and fails closed; it passes the binding fixtures and call-sequence
  fixtures whose needs it supports, and publishes a conformance statement
  naming the host, the calls covered and not seen, scope, boundaries,
  maximum age, approval (with the host configurations in which a prompt is
  relied on, and whether roles can be verified), concurrency, fixture
  features, host gaps, the covered calls whose results carry no capability
  output, and any §5.18.10 check it does not apply (a conforming layer has
  none). Both reference layers list none and claim the class. The
  output-contract row applies to the results a layer receives as capability
  outputs, in the form its host delivers them: the Python adapter checks
  the text of each result of an MCP tool bound to a capability (R402), a
  tool `create_grounded_mcp_server` serves as it returns and another
  server's at PostToolUse, and its statement names the calls whose results
  come in other forms (Claude Code's own tools). A call whose output a
  layer refuses has failed: it takes no checkpoint and is no prerequisite
  that ran.
- **9.2** Fixtures: `tests/conformance/bindings/` and
  `tests/conformance/calls/`, generated by `scripts/gen_call_fixtures.py`
  with a `--check` mode, with schemas beside them. A fixture's `needs`
  (`unbound_calls`, `nested_calls`, `recorded_approval`, and for binding
  fixtures `offered_tools`, since §5.18.2's offered-tool checks are a
  SHOULD) names features a layer may lack and state.
- **9.3** Reference layers: the Python adapter (a hook before each tool)
  and the TypeScript binding (inside each tool) run every fixture whose
  needs they support. The plugin's shell hooks are aligned with the rules
  Claude Code lets them apply and do not claim the class.

### 10) Capability checks are host-neutral

§5.18.10 states the checks of `checkpoint`, `mutate`, `send`, `execute`,
`rollback`, `persist`, `audit` and `transform` as requirements of the
capabilities, citing the destination policy (§4.4.2) and the secrets rule
(§6.7). A check the Standard requires is decided by code; a model's
judgement may add a refusal but never satisfies one. Skill-level hooks are
one implementation; SECURITY.md §5.4 maps every condition of the six
skills' hooks to a row or to "model-judged addition, not required", and the
prompt hooks no longer ask a model about approval, checkpoints or rate
limits. With §5.18.8's required layer, this is the answer to ACS-55's
"required hook": a host that claims the class runs no covered call without
the layer, and a host that does not run a skill's hooks applies their
checks by other means or does not cover those calls. No frontmatter key is
added.

### 11) Records name the layer and its configuration

Every record a layer writes names the layer, its version and a digest of
the bindings and settings it applied, or the settings listed; the plugin's
audit lines carry the sha256 of `hooks/hooks.json` and the effective
environment settings that change its decisions.

## Backward compatibility

- Validators accept what they accept today, and the executor behaves as
  today: §5.2.2 states its behaviour. No repository catalog is affected and
  CI's strict validation is unchanged.
- The terms, sections, class, schemas, fixtures and the codes V110, V111,
  R407, F506 and W617 are additions: MINOR under
  [GOVERNANCE](GOVERNANCE.md#versioning). Existing codes gain meanings for
  bindings and calls with their severities unchanged.
- The annotation schema accepts every annotation it accepted, and rejects
  copies inconsistent with the capability, of which the repository has
  none.
- Implementations change: the Python adapter uses a checkpoint up when a
  call is allowed (re-checked atomically), also for a failed call, counts
  an unresolved hold as used, ends validity when any session it serves
  ends a turn, caps the maximum age at 30 minutes, refuses a `rollback`
  with no checkpoint, counts only state-saving calls as checkpoints,
  refuses gated calls in permission modes that do not reach a person,
  treats a tool with no capability as unbound, and guards its MCP tools;
  the plugin hook reads only JSON payloads, uses its marker once and asks
  for approval; the TypeScript binding reports its lint findings with
  Standard codes and attributes nested calls by nesting tokens.

## Conformance test updates

- Binding fixtures (35; the nine that check offered tools and host
  actions need the `offered_tools` feature) and call-sequence fixtures
  (30), their schemas, two conformance statements, and runners in Python
  and TypeScript.
- Capability output vectors, `tests/conformance/output/vectors.json`, which
  both reference codecs of §5.18.9 read.
- Approval digest vectors `tool_call` and `tool_call_unbound` in
  `tests/conformance/approval/digests.json`.
- Unit tests for the plugin hooks (and a test that their lists are a
  subset of the SDK mapper's), the adapter (permission modes, the callback's
  re-check, holds), the mapper, the nesting tokens, V102 with a test
  ontology in both layers, the output helpers and the annotation schema.
- §10.3 names the binding and call fixtures normative for class SL.
- Not testable by fixture, and stated in a conformance statement instead:
  that a prompt shows what runs, that a layer sees every call it claims to
  cover, and its host gaps.

## Alternatives considered

- **Leave tool-calling hosts to each binding's documentation.** Rejected:
  §5.2.1 already binds safety layers, and this repository's layers
  diverged.
- **A separate profile and a fifth level L5.** Rejected: §5.2.1's MUST
  points into the Standard, and a level implies the levels below it.
- **Treat a call sequence as a workflow built as it runs.** Rejected:
  `precedes`, W608 and other static checks need a closed step list.
- **Use a checkpoint up after success (the Python adapter's rule).**
  Rejected: a crash between effect and record leaves it valid for a second
  change, and a failed call may have changed something.
- **Let a layer take a checkpoint on a call's behalf, as the executor does
  for a step.** Rejected: a layer cannot know what the call will change;
  the executor's host is given the step.
- **Hash `[args]`, the executor's default.** Simpler, but one decision would
  fit every tool that takes the same arguments.
- **Classify an unbound tool as `observe`, or refuse it.** The first fails
  open; the second makes a layer unusable on hosts with many built-in tools.
- **A new code for every refusal kind (rate limit, undeclared invocation).**
  Rejected: F504 already names a policy constraint; one new runtime code,
  R407, covers the layer's own failure.
- **Check a composite's nested calls on their own.** Rejected where the
  layer can attribute them: the composite would use the checkpoint and its
  nested `mutate` call would be refused, so no composite could change
  anything.
- **Attribute a nested call to whatever composite runs on the thread (and
  execution).** Rejected: an endpoint, an effect or a parallel tool call of
  the same step could call a listed tool at that moment and pass with no
  checkpoint and no approval. The binding issues a one-shot token per
  invocation instead.
- **Waive a nested call's prerequisites too.** Rejected: a composite's
  prerequisites exclude its invokes', so a nested `rollback` could run
  with no checkpoint ever taken.
- **Release a hold that lapses, so the checkpoint can serve another call.**
  Rejected: the layer does not know the held call did not run.
- **One scope per session in the Python adapter.** Rejected for now: it
  would need per-session checkpoints throughout the tracker; the adapter
  states one scope per instance and treats any session's Stop as a
  boundary.
- **A frontmatter key that declares a hook required (ACS-55).** Rejected:
  §5.18.8 and §5.18.10 already require every host claiming the class to
  apply each capability check, whatever declares it; a key would add a
  second, weaker statement of the same rule.
- **Classify `git restore --source=<sha>` as `rollback`** (asked by the
  checkpoint/rollback workstream). Rejected: `<sha>` can name any commit
  (an old one, or one the model made), so a layer cannot tell that it is a
  restore point, and an ungated `rollback` would then overwrite the working
  tree with any commit's content. It stays a gated `mutate`; `git stash
  apply <sha>` is `rollback` only when `<sha>` is a commit a checkpoint of
  the scope recorded (decision 2.8).
- **Count `git stash store <sha>` as the checkpoint** (the first
  revision). Rejected: it names a commit the caller chooses, so it can
  mint a restore point that is not the current state, and it fails on a
  clean tree, where a model could then never take a checkpoint. `git stash
  create` captures the current state (or confirms `HEAD` is it) and is
  counted instead.
- **Trust Claude Code's prompt in every permission mode.** Rejected: in
  `bypassPermissions` the documentation does not say the prompt is shown,
  and in `auto` a classifier can answer it, so a gated call could run on
  no person's decision.

## Open questions

1. **Upstream hook.** The Standard Agent Specification has no hook that can
   refuse a call before it runs, so a runtime-level layer cannot cover plain
   `defineTool` tools. Should this project propose one upstream, so the
   class can cover every tool of a Standard Agents runtime?
2. **Machine-readable statements.** Statements are JSON files beside the
   fixtures. Should a later version publish a registry of conformance
   statements, and require one for any implementation that claims SL?
3. **Claude Code host gaps.** A command hook that cannot start, or times
   out, lets Claude Code run the call. If Claude Code offers a fail-closed
   hook mode, should the plugin's hooks then claim class SL?
4. **Permission modes.** The SDK adapter and the plugin rely on an `ask`
   reaching a person in Claude Code's `default`, `acceptEdits` and `plan`
   modes, on the documentation's word. Should a later version ask Claude
   Code to state, per mode, whether a hook's `ask` reaches the permission
   callback, so the list can be tested rather than cited?
5. **What a checkpoint captured.** A layer counts a successful checkpoint
   call without verifying what the restore point holds (a stored commit may
   not be the current state). Should a checkpoint output carry a digest of
   what it captured, so a layer can check it against the scope before it
   counts the call?
6. **Per-session scopes.** Should the Python adapter offer one scope per
   session, so that one session's turn end does not end another's
   checkpoints?
