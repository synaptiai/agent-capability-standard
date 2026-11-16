# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

**Upgrading:**
- Python 3.14 or 3.15 is required (`requires-python = ">=3.14"`); 3.10–3.13
  are no longer supported. The extension's stable-ABI floor is 3.14.
- Building from source needs Rust 1.88 or newer (was 1.86), because `sha2`
  0.11 requires it.
- Python SDK: a tool the mapper does not know is now the strictest case (a
  high-risk mutation that needs a checkpoint and approval), not `observe`;
  register an MCP tool with its real capability. `GroundedAgentConfig.approval`
  defaults to `"ask"`, so a call whose capability requires approval (Write,
  Edit, a mutating Bash command, `execute`/`mutate`/`send` tools) is put to
  the host's permission flow; set `approval="off"` for the earlier behaviour.
  `ToolMapping` is frozen and has a required `requires_approval` field.
  `ToolCapabilityMapper(ontology_dict)` now takes every flag from the dict it
  is given: pass the full ontology, a `CapabilityRegistry`, or nothing for the
  packaged ontology; with an empty or partial dict `map_tool` raises V101. An
  MCP tool registered without a `risk` takes its capability's risk (was
  `"medium"`), so a `retrieve` or `search` tool counts against the low-risk
  rate limit.
- Python SDK, Bash: `sed`, `awk` and `env` are no longer read-only, since they
  can write a file or run another command; a call to one needs a checkpoint
  and approval like any other mutation.
- Plugin audit log: `.claude/audit.log` now holds one JSON line per tool call
  with a digest of the input in place of the input; `tools/verify_audit_log.py`
  verifies old and new lines in one chain.
- `schemas/interop/oasf_mapping.yaml`: `meta.grounded_agency_version` is
  replaced by `meta.agent_capability_standard.standard` and `.ontology`.
- Python SDK, tool calls (Standard 1.2.0 §5.18):
  - A checkpoint is used up when its call is allowed (at the permission
    callback's allow, or at PostToolUse for a call that did not pass the
    callback), and a call that fails uses it too. The newest valid checkpoint
    no other call holds is used, the earlier ones included. A hold that
    lapses, is found on reload or is unresolved when the turn ends counts as
    used. The Stop of any session the adapter serves ends every checkpoint's
    validity: take a checkpoint in the turn that needs it, and serve sessions
    that must not share this with separate adapters.
  - `expiry_minutes` (the adapter's and `CheckpointTracker.create_checkpoint`'s)
    must be more than 0 and at most 30; `checkpoint_reservation_seconds`, if
    set, at most the expiry. `GroundedAgentConfig` gains `call_record_limit`.
  - `CheckpointTracker(max_age_minutes=...)` (default 30; the adapter passes
    its `expiry_minutes`) bounds every checkpoint: one taken through
    `adapter.checkpoint_tracker.create_checkpoint()` with a longer
    `expiry_minutes` is stored with the maximum age as its expiry, and one
    read back from a state file stops authorising a call at its
    `created_at` plus the maximum age. A checkpoint dated after the clock
    (a crafted state file, a clock that stepped back) authorises nothing,
    counts as no checkpoint taken and names no restore point; one found
    dated after the load is dropped from the state.
  - `CheckpointTracker`: `can_reserve()` and `release_reservation_in_scope()`
    are removed. `resolve_holds_in_scope(scope)` replaces the latter, and
    counts the holds it ends as used instead of releasing them.
    `DEFAULT_RESERVATION_SECONDS` is `None` (was 600.0): a hold lasts until
    its checkpoint expires unless `reservation_seconds` is set.
    `has_valid_checkpoint()` now counts every valid checkpoint, those in the
    history included, whether or not a call holds it: use
    `valid_checkpoint_id()` for the one a call would hold, or
    `get_active_checkpoint_id()` for the active one.
  - `WorkflowEngine.ensure_checkpoint_before_step()` returns the valid
    checkpoint a step can use, one in the history included, and takes a new
    one only when every valid checkpoint is held; before, it took a new one
    whenever the active checkpoint had been used.
  - Approval is asked only in the permission modes `default`, `acceptEdits`
    and `plan`. In `bypassPermissions`, `auto`, `dontAsk` or any other mode,
    a call that requires approval is refused (F502), since nothing puts it to
    a person. A binding whose `approval` asks for more than one approver or a
    `role` is refused F502. Arguments the permission callback changes are
    classified again.
  - Every refusal reason is the text form `CODE NAME: message` (F501, F502,
    F503, F504, R407, V102), and the diagnostics are kept in
    `adapter.call_records`. A rate limit is F504; a failure of the safety
    check itself is R407.
  - A `rollback` call is refused (F503) unless a checkpoint was taken since
    the adapter started; it uses no checkpoint, and no longer invalidates
    the others.
  - `Skill` is always `invoke`, so `Skill(checkpoint)` takes no checkpoint:
    the call that saves the state does. `create_checkpoint_recorder`
    (`create_skill_tracker` stays as an alias) records one when a call
    classified `checkpoint`, such as `git stash create`, succeeds.
  - Bash: `git stash create` is `checkpoint`, `git stash list|show` only
    read, and a line of several commands takes the strictest flags and every
    prerequisite of all of them. `git stash pop|apply <commit>` is `rollback`
    only when `<commit>` is the full id of a commit a checkpoint of the
    adapter's scope recorded (`metadata["commit"]`); git applies any merge
    commit as if it were a stash, so any other `pop` or `apply`, a bare one
    included, is a gated mutation that needs a checkpoint and approval.
  - MCP: a tool registered or served with no capability is no longer
    `execute`: it is unbound, the strictest case, and reported as W617 in
    `mapper.warnings`. Tool `metadata` may be a tool binding record
    (`capability`, `flags`, `additional_capabilities`, `invokes`,
    `approval`, `control`); the flat keys still work, and `capability` and
    `capability_id` that disagree are S303.
    `create_grounded_mcp_server()` now defaults to `require_layer=True`:
    each tool it serves refuses (R407) a call the adapter's layer did not
    allow, so a session whose options were not wrapped with
    `adapter.wrap_options()` cannot run them. Pass `require_layer=False`
    for the earlier behaviour (outside class SL). A control-only tool
    (`control: true`) is served as it is: it is never refused.
  - Tool binding records: a record with a member that has no I-JSON form
    (an `x-` member holding an integer beyond 2^53, a lone surrogate or an
    object that is not JSON) is S303 and not loaded, and its tool stays
    unbound. A float that canonical JSON writes as an integer beyond ±2^53
    (1.8e16) has no I-JSON form either: in a record it is S303, and in the
    arguments of a call that requires approval F502, as in the TypeScript
    package (`grounded_agency.capabilities.bindings.i_json_problem`).
    `approval.min_approvers` written as `1.0` loads; `approval.role: null`
    is S303, and `approval.expires` longer than 2^53 - 1 ms is S303. A
    diagnostic's `location.field` is the member's path with keys joined by
    a dot (`approval.min_approvers`, `flags.risk`); W602 names
    `flags.<flag>`.
  - `adapter.recorded_by["config_sha256"]` also digests the rate limits
    (`config.rate_limit`), which decide F504 refusals, so its value differs
    from one computed without them.
- Plugin hooks (released with plugin 3.0.0): the PreToolUse hook reads only
  Claude Code's JSON payload and needs `jq`; anything else is blocked with
  R407, as is a failure of the hook. The checkpoint marker is used up by the
  gated call it authorises, so each such call needs its own; a successful
  `git stash create` writes the marker and the new Stop hook ends its
  validity when the turn ends. A marker whose validity ended unused (it
  expired, its turn ended, a newer one replaced it) is filed under
  `.claude/checkpoints/ended/`, as a used one is under `used/`. A read-only
  Bash command and `git stash list|show` need no marker, and `git stash
  pop|apply <commit>` needs none when a marker, live or filed, recorded
  `<commit>`; any other restore needs a marker like any write. The rollback
  skill's command hook refuses (F503) a `git stash pop|apply` that does not
  name such a commit, whatever `git stash list` holds; before, it refused a
  restore only when `git stash list` was empty. The rollback and send skills'
  command hooks open a refusal with its code and name (`F503
  ROLLBACK_FAILED:`, `F504 CONSTRAINT_VIOLATED:`, `R407
  SAFETY_CHECK_FAILED:`) in place of `BLOCK:`. The
  marker's `created_at` and `expires_at` must be whole seconds of at most 12
  digits, the first not in the future and the second at most 1800 seconds
  after it; otherwise the call is blocked with F501 and the marker removed. A
  gated call is answered `ask` with an F502 reason in the permission modes
  default, acceptEdits and plan, and blocked with F502 in the others;
  `ACS_HOOK_APPROVAL=off` leaves approval to Claude Code's permission rules.
  `ACS_CHECKPOINT_MAX_AGE` (seconds, at most 1800) sets the marker's expiry.
  Each audit line gains `recorded_by`. The composed skills take a checkpoint
  with `/checkpoint` instead of writing `.claude/checkpoint.ok`.
- Standard Agents binding: `STANDARD_VERSION` is 1.2.0 and the `acs`
  annotation carries the tool binding record (`tool`, declared `flags`,
  `additional_capabilities`, `invokes`, `approval`); the copies of the layer
  and flags are informative. `lintPromptTools` and `lintAgentBindings` report
  `W617`, `V111`, `V102` and `F506` in place of `unclassified`,
  `misnamed_tool` and `bound_gated_tool`. A prerequisite other than a
  checkpoint that has not run is refused with V102, and a check or record
  the binding cannot complete with R407. A tool's success result is the
  output's I-JSON text, and an output with an integer beyond 2^53, a
  non-finite number or a lone surrogate is refused with R402. A composite
  lists the tools it invokes in `invokes`, which also becomes its `uses`; an
  invocation outside the list is refused (F504). A call that needs approval
  whose arguments are not I-JSON is refused with F502 before anything is
  asked or used. An approval policy's `min_approvers` is at most
  `MAX_APPROVERS` (1000). A grounded tool's `recorded_by.config_sha256`
  digests `{annotation, settings: {checkpoint_max_age_ms}}`, not the
  annotation alone.
- TypeScript package: `decodeCapabilityOutput` accepts a number written in
  exponent form (1.8e16, 1e300), which it used to refuse, and checks integer
  literals in the text itself; `encodeCapabilityOutput` accepts a value it
  writes in exponent form (1e21 and above) and refuses one it would write as
  an integer literal beyond ±2^53 (1.8e16). A tool binding record's
  `location.field` follows the Python loader's dotted paths. `iJsonProblem`
  refuses a `bigint`, and the new `parseJsonExact` reads JSON text with an
  integer literal beyond ±2^53 as a `bigint` instead of rounding it (JSON.parse
  reads 9007199254740993 as 2^53): read text that is then checked as I-JSON
  with it.
- Conformance statement schema: `approval.expires` is a duration or null;
  the new `not_applied` lists the §5.18.10 checks a layer does not apply,
  and a layer that lists any does not conform to class SL until it applies
  them; the new `calls_without_output` names the covered calls whose
  results carry no capability output, to which no output check applies
  (§10.4). Both reference layers list nothing in `not_applied` and claim
  class SL: the Python SDK adapter checks the output contract of the
  results it receives as capability outputs, those of every MCP tool bound
  to a capability, in the form the session reads them (R402), and its
  statement names the calls whose results come in other forms (Claude
  Code's own tools) in `calls_without_output`; the Standard Agents binding
  checks every grounded tool's output.
- **Breaking (plugin):** two composed skills take their directory names
  (Agent Skills requires `name` to equal the directory): the slash commands
  `/gap-analysis-workflow` and `/digital-twin-sync-workflow` become
  `/capability-gap-analysis` and `/digital-twin-sync-loop`. The plugin
  release that carries this is a MAJOR version (3.0.0). No workflow,
  ontology or schema changes. The `layer` frontmatter key is removed from
  the 13 skills that had it (the ontology gives a capability's layer).
- Domain profiles (Standard 1.2.0 §5.21) are now applied where they are
  given, and refused when malformed: a `checkpoint_policy` key must be a
  capability id or `"*"` (a label such as `before_send` is V101), the
  members of `risk_thresholds` and `evidence_policy` are closed (another is
  S303), and `required_anchor_types` lists anchor kinds. A third-party
  profile written for 1.1, which nothing applied, is refused where it is
  applied now: migrate it as the shipped profiles were (each to 2.0.0).
  `tools/validate_profiles.py` checks profiles with the core and fails on
  any diagnostic; its old helper functions are gone. A profile that sets a
  rule an implementation does not put in force is refused too, rather than
  applied without it (§5.21.4): the adapter, with `strict_mode=False`
  (which only logs a missing checkpoint), a `checkpoint_policy` that raises
  `requires_checkpoint`. A profile's grounding policy (`require_grounding`,
  every shipped profile's) and its `minimum_confidence` are applied: an
  output they cover that is not grounded fails with F505, one not confident
  enough with F504, in runs, in the adapter (on the outputs of the tools
  `create_grounded_mcp_server` serves) and in the binding. A member without
  an exact JSON form (an integer beyond 2^53) is S303. An unknown top-level
  profile member stays a warning (W604) and is now reported with the member
  meant: logged at WARNING by the Python layers, and passed by the
  binding's `bindingProfiles` to its `onWarning` (`console.warn` by
  default).
- Python SDK: `OASFAdapter.translate` raises `UnknownCapabilityError` (V101,
  with the closest id) for an entry that names a capability the ontology
  does not define; it logged a warning and translated the entry without it,
  so its `max_risk` and `requires_checkpoint` could be too low. Catch it
  where a mapping written against a later ontology may be loaded.
- Python SDK: `grounded_agency.trust.decay_factor` counts an age below zero
  as zero (it raised `ValueError`), and `TrustModel` reads its field
  authorities from `field_authority.fields`, refusing a malformed entry or
  an unknown tie-breaker. `_core.Run.start(profiles=...)` and
  `Validator.validate(profiles=...)` apply profiles (they were refused);
  `GroundedAgentConfig(profiles=...)` needs `approval="ask"`.
- An ontology whose capability contract keeps a `$ref` that names nothing,
  is cyclic or nests deeper than 12 is refused when it is loaded (it was
  kept silently): by the validator CLI, the executor and WebAssembly, and in
  Python by `_core.Validator`, `WorkflowEngine` and `GroundedAgentAdapter`,
  which now loads its ontology through the core as well. An adapter whose
  ontology is not at `<root>/schemas/` names the directory its `$ref`s are
  relative to with `GroundedAgentConfig(schema_root=...)`. A same-file
  `$ref` (`#<pointer>`) names a node of the ontology itself (§4.1.2).
- TypeScript package: `npm test` replays the fixtures through the
  WebAssembly core, so run `npm run build:wasm` (which needs the
  `wasm32-unknown-unknown` target) and `npm run build` first; the binding
  needs only `npm run build:ts`.
- Standard Agents binding: a trace entry's `approval.approvers` (and
  `GroundedCall.approvers`) are now the approvers' principals,
  `sa-user:<id>`, not bare `ThreadUser` ids, and the entry carries
  `approval.approver_identities`; compare approvers by principal. They list
  only the approvers whose approvals counted when the call ran
  (`countedDecisions`): one that had lapsed under `expires_ms` is left out.
  `POST acs/approvals` takes the digest in either case.
  `decideApproval` takes an optional last argument, `ApproverOptions`
  (`kind`, `ownerId`). Decisions stored by an earlier version have no
  identity, and a call that uses one records no `approver_identities`.
- Reference executor: the saved state of a run that deferred steps holds two
  more members (`ahead`, and `parked` for a nested run that ended deferred);
  a state with deferrals that an earlier version saved still restores, but
  cannot be resumed (`Run.resume` refuses it): cancel such a run and start a
  new one. The state of a run that never deferred holds neither.
- Reference executor, host protocol (Standard 1.2.0 §5.19): snapshots are
  version 2. The terminal action is derived from the state rather than
  stored with copies of the records and outputs, every action carries
  `run_id`, and the state may hold the record mode and the chain heads of
  what a host took; version-1 snapshots still restore (a finished run's
  stored terminal action must equal the one derived). Actions and records
  gain members (`run_id`; on records `run_id`, `frame`, `step`,
  `capability`, `checkpoint_id`, `code`, `approval.decision_id`); code that
  compares whole actions or records must allow them. `_core.Run.next()`
  returns a fresh dict each time, `Run.tick` returns whether it changed the
  run, and `Run::next` in Rust returns an owned `Action`.
- Reference executor, starting a run (Standard 1.2.0 §11.5): the catalog's
  version header is a start member every caller states. `_core.Run.start`
  takes a required keyword-only `header`, the version the catalog's
  `# Standard version:` header declares or `None` for a catalog without
  one; a call without it raises `TypeError`. In Rust, `StartOptions` gains
  `header`, `records`, `profiles`, `grounding` and `destinations`, which
  every construction names. `WorkflowRunner` states the header itself.
- `WorkflowRunner`: `run` and `start` take `attendance=None` (the trigger's
  attendance, else attended, as before) and refuse a caller-given `run_id`
  the runner has already started (`RunStartError`): a `run_id` must be
  unique among the runs whose records or keys the host keeps (§5.19.2).
  `drive` is now a loop of `advance` turns: it sleeps until the run's
  wake-up time (`run.wake_at()`) instead of a deadline it computed, and
  calls `Host.withdraw` for an action the run timed out. `RunResult` gains
  `run_id`, `reason`, `checkpoint_id` and `run_record`.
- Coordination: the orchestrator's `audit` step returns the `audit`
  contract's output (`recorded`, `audit_id`, `record`, `timestamp`,
  `evidence_anchors`) instead of `{"audited": true}`, and records only the
  step's `event`, `context` and `retention`, the event under
  `details.event` of a record of the log's own (Standard 1.2.0 §6.4).
- Plugin audit log: each line of `.claude/audit.log` is now an action
  record (Standard 1.2.0 §6.4): `action_id`, `timestamp`, `actor`,
  `intent`, `status`, `tool`, `call_id`, `details` (`event`, `skill`,
  `input_sha256`), `recorded_by`, `prev_hmac`, `hmac`. Logs that mix old and
  new lines still verify. The hook now reports, as a non-blocking error
  (exit 1, the reason on standard error), every call it does not log or
  cannot sign: no `jq`, a symlinked log, no `openssl` (it no longer writes a
  line with `hmac: "no-hmac-available"`, which broke the chain), a line that
  could not be built, an unreadable last line, an unavailable digest.
- Audit skill: each line it appends to `.claude/audit/records.jsonl` is now
  an action record of its own (Standard 1.2.0 §6.4), with the event under
  `details.event`, the collected `audit_record`, `changes` and `provenance`
  under `details`, and `prev_hmac` and `hmac` under `AUDIT_HMAC_KEY` (else
  the hook's default key), so `tools/verify_audit_log.py --log-file
  .claude/audit/records.jsonl` checks the file. Lines an earlier version
  wrote (`audit_id`, `timestamp`, `event`, `context`, `retention`,
  `audit_record`, `changes`, `provenance`) carry no chain and do not verify:
  move an existing file aside and let the skill start a new one (it does so
  itself when the last line has no `hmac`), and read the old members under
  `details` in new lines.
- Reference executor: an approved step that fails now has a `failed`
  record, with the step's code, also when its failure mode's rollback or
  checkpoint then fails (F503, F501) or finds no checkpoint to roll back
  to; 1.1 left that record `approved`, which a cancellation would then turn
  into `cancelled` and which held back `take_records` for the rest of the
  run. A record a resumed run reuses no longer keeps the `checkpoint_id` of
  an earlier pass.
- Python SDK, evidence (Standard 1.2.0 §6.5, §6.6):
  - Anchor kinds are §6.5's: `tool_output` and `command` anchors are now
    `tool`, `mutation` and coordination anchors `record`. The old names are
    accepted with a `DeprecationWarning` (`kind` reads back the new one; a
    former `mutation` keeps its high priority), any other free kind becomes
    a vendor kind `x-...`, and a query by an old name (`get_by_kind("command")`)
    returns what it returned before, by ref prefix, with the warning; a query
    by a free kind (`get_by_kind("observation")`) is answered by its vendor
    kind (`x-observation`), with the warning.
    `get_for_capability_output()` warns: use `evidence_anchors_for()`, which
    returns §6.5 objects. An empty `ref` or a malformed `digest` is a
    `ValueError`, and `EvidenceAnchor.from_dict` refuses a `digest` of
    `null` too.
  - A store keeps a frozen copy of each anchor: assigning to an anchor read
    back from a store, or calling `mark_critical()` on it, raises
    `FrozenInstanceError`, and its metadata is read-only. Your own anchor is
    not frozen. `add_anchor` returns the record kept.
  - Record ids are never reused: `clear()` no longer resets the sequence,
    and the records it drops count in `info().removed`.
  - Every store redacts what it keeps (§6.7). With
    `evidence_include_tool_input=True` a call's input is kept redacted, not
    as given; the collector keeps no `digest` of a response that holds a
    recognised secret.
  - `CoordinationAuditLog.record` redacts `details`; the runner redacts the
    message of every `Error` it submits; the adapter redacts its call
    records and refusal messages.
  - `GroundedAgentAdapter.create_checkpoint` records the checkpoint's anchor
    (`checkpoint:<id>`, kind `record`, capability `checkpoint`) in the
    adapter's evidence store: `len(evidence_store)` and `get_evidence()`
    count it, and subscribers are notified.
  - `OrchestrationRuntime.execute_workflow_step` returns the contracts'
    outputs, grounded in the record of the action (§6.5): `invoke` and
    `inquire` give `evidence_anchors` as §6.5 objects (were ref strings: read
    `anchor["ref"]`); `audit` gives `{ref: "audit:<audit_id>", kind:
    "record"}` and its `store`; `delegate` gains `evidence_anchors`; and
    `synchronize` gives `{synchronized, agreed_state, participants,
    evidence_anchors}` instead of the agreed state itself (read
    `output["agreed_state"]`).
- Python SDK, tool calls: a `persist` call (`TodoWrite`, a tool bound to
  `persist`) or an `audit` call whose data holds a credential-shaped value
  (a key or token format, a credential assignment, a URL's userinfo
  password, an `Authorization` header's value) is refused with F504
  (Standard 1.2.0 §5.18.10, §6.7), also when the host's permission flow
  changes the call's arguments.
- Standard Agents binding: `fileAnchor` returns `{ref, kind: 'file', digest:
  'sha256:...'}` instead of `metadata.sha256`; every trace entry's
  `evidence_anchors` and `error` are stored redacted (default patterns,
  plus the tool's `secrets`), as are the notifications; a `persist` or
  `audit` tool refuses data that holds a credential (F504), a URL's
  userinfo password and an `Authorization` header's value included.
- Plugin: the `persist` skill refuses content that holds a credential-shaped
  value (a URL's userinfo password and an `Authorization` header's value
  included), and the `audit` skill an append to
  `.claude/audit/records.jsonl` that holds one (F504); both hooks' refusals
  now open with the Standard's
  code and name (`F504 CONSTRAINT_VIOLATED:`, `R407 SAFETY_CHECK_FAILED:`).
- Validator: an `audit` step's literal `retention` outside the duration
  grammar is W614 (`P1Y` is not a duration: write `P365D` or `365d`); a
  1.1 workflow that uses `grounding@1` or F505 in `on_error` gets W616.
- Validator (every Standard version): W620 for a workflow name that is not
  an identifier or is `catalog`, a step `domain` that is not a domain id
  (`schemas/workflow_catalog.yaml`'s `plan-invalidation` is now
  `plan_invalidation`; rename yours the same way) and a literal model family
  outside `[a-z][a-z0-9_-]*`; W623 for a schedule trigger with `overlap:
  allow_all` on a workflow that exercises both capabilities of a
  `conflicts_with` pair. A top-level `catalog` mapping without `steps` is
  now the catalog's manifest, no longer a malformed workflow (S304).
  Diagnostics gain `location.path` (RFC 6901) and, in a catalog set,
  `location.catalog`; `column` counts code points (it counted bytes).
- Validator and executor, workflows that target 1.2: a `delegate` step
  that may act on the world unchecked is W621 and one with a computed agent
  and no `agents` is W622; an accepted `read_only` delegation whose host
  does not attest `effective.read_only` fails the step (R402), not retried.
  A delegation that binds `continues` and attests a fresh context, or
  returns the `task_id` it continues, fails (R402). An attested identity's
  `model_id` must equal `effective.model_id` (R402). An identity's
  `model_id` is a string, as `agent_identity_schema.yaml` 1.1.0 says: an
  identity whose `model_id` is not is malformed, so it refuses the run's
  start as the actor identity and fails what reports it, like an identity
  with a non-string `role`. Below 1.2 the executor reads no identity's
  `model_id`, as 1.1 did not (schema 1.0.0 does not define it).
- Validator, workflows that target 1.0 or 1.1: the workflow field `agents`
  and the `delegate` input `continues` are W616 where 1.1 reported W604
  (with no version, W605 alone); the executor still ignores `agents` and
  passes `continues` on unread there. A qualified `invoke` target
  (`<catalog id>/<name>` naming no workflow of the caller's catalog) is W616
  too, whatever catalogs are given. Every W616 about a step member (1.1
  features such as gate `phase` included) now carries the step's `step` and
  `capability` with `field` relative to the step (`gates[0].phase`, not
  `steps[0].gates[0].phase`), and is sorted with that step's findings; its
  code and `location.path` are unchanged.
- Python SDK: `AgentDescriptor.identity()` refuses a `model_family` not
  written `[a-z][a-z0-9_-]*` (`ValueError`) and derives one from a
  `model_id` in its metadata; `DelegationProtocol.delegate()` refuses a task
  that does not fit the agent's declared `task_inputs`;
  `WorkflowEngine.effective_flags(step, workflow)` raises
  `UnboundedDelegation` for a delegate step of a 1.2 workflow that declares
  `agents` whose target manifests were not added. The orchestrator's
  `inquire` output gives questions as objects with `id`, `parameter` and
  `answer_type`, `inquiry_id`, and `ambiguity_analysis` as an object (it
  gave strings, against the contract). `_core.Run.start`/`restore` accept
  `catalogs` and `agents` (they were refused as not implemented).
- Standard Agents binding: `LintDiagnostic.code` gains `V107` and
  `location` a variant `{workflow, field, path}` (`lintDelegationTargets`).
- Checkpoints, rollbacks, sends and memory (Standard 1.2.0 §4.4.1, §4.4.2,
  §4.5; RFC-0009):
  - Every `InvokeCapability` action carries `idempotency_key`
    (`<run_id>:<n>`, the same for every attempt of one pass), and the
    pass's action record carries it too. A host that keeps no keys can
    ignore it; a pending action restored from a state saved before it gets
    `<run_id>:<id>`.
  - A host or an applied profile that gives destination policies puts them
    in force: a `send` step whose destination one does not allow fails F504
    (`destination_not_allowed`) before approval or a checkpoint. A domain
    profile with `allowed_destinations` is no longer refused by the
    executor, `WorkflowRunner`, `GroundedAgentAdapter` or the Standard
    Agents binding: it is applied. `_core.Run.start(destinations=...)`,
    `WorkflowRunner.start/run(destinations=...)`,
    `GroundedAgentConfig(allowed_destinations=...)` and the binding's
    `configureLayer({destinations})` give the host's own; an invalid
    pattern is refused, and a `WorkflowRunner` policy given as a string
    rather than a list of patterns raises `TypeError`. While a policy is in
    force, `GroundedAgentAdapter` also refuses (F504) a call of an unbound
    tool, which it cannot tell sends or not, and of a composite whose
    `invokes` reach a binding that performs `send`: it does not see nested
    calls, so it cannot tell where they go. In the Standard Agents binding,
    the `allowed_destinations` of profiles given to a composite reach the
    sends its code invokes, at any depth.
  - A `persist` or `recall` step of a workflow that targets 1.2 and binds
    `scope` fails R402 (`unsupported_scope`) unless the output echoes the
    scope. Steps that do not bind it, and those of a 1.0 or 1.1 workflow
    (where `scope` is W616 and passed on), are unchanged.
  - `RolledBack` may carry `not_covered`, which the executor validates (a
    malformed one, `null` included, is refused), traces and records. An
    item's members other than `item`, `reason` and a string `detail` are
    ignored, not refused.
  - Validator: W624 (a 1.2 `rollback` step whose `restored` nothing
    checks), W625 (a 1.2 `send` approval whose `shows` hides its
    destination), W626 (an unknown literal memory scope), W614 for a
    literal `persist` `ttl` outside the duration grammar or zero, W603 for
    a reference to `persist`'s deprecated `timestamp` (read `stored_at`),
    and W616 for a 1.0 or 1.1 workflow that binds the memory `scope`.
  - Python SDK: `WorkflowRunner.run/advance/drive(save=...)` refuses a host
    whose `IdempotencyLog` is in memory (give it a path); a rollback by
    `Host` lists a send whose outcome is unknown as transmitted
    (`detail: "outcome unknown"`); with a
    `MemoryStore`, a run's `run` scope ends with the run, in the host's
    store and in `WorkflowRunner(memory=...)`'s (so `cancel` without a host
    ends it too). `MemoryStore` stores and returns copies of values, and
    refuses (`unsupported_ttl`, nothing stored) a `ttl` that would end an
    entry after 9999-12-31T23:59:59.999Z, as the binding's `memoryTools`
    do; `Host` gives a `persist` with no `key` one derived from the pass's
    `idempotency_key`. `FileSnapshotStore` reads a scope item that names a
    directory (`src`, `src/`, `./src`, an absolute path under the root) as
    everything under it, lists an item outside the root in `excluded`,
    never captures or restores `.audit/`, reports a rollback pattern that
    names nothing captured as `not_captured` unless the checkpoint's scope
    covers it, and computes `verification` over everything the checkpoint
    captured; `GroundedAgentAdapter` and `WorkflowRunner` keep a file
    evidence store out of every checkpoint. `Host.__init__`
    takes keyword-only `memory`, `idempotency`, `session_id`, `user`,
    `project` and `protected_paths`; a subclass that calls
    `super().__init__(tracker)` is unaffected.
  - Plugin: the `checkpoint` skill takes a git checkpoint with a plain
    `git stash create` (and `HEAD` on a clean tree) instead of `git stash
    push`, which the safety layers count as a gated `mutate`; the
    `rollback` skill restores with `git restore`.
- Python SDK, the output contract of a tool's result (Standard 1.2.0
  §5.18.9, §5.18.10): an MCP tool bound to a capability, one that
  `create_grounded_mcp_server` serves or one of another server bound with
  `register_mcp_tool` or `load_bindings`, must return that capability's
  output as the I-JSON text of the output object, its one text content
  item, with every field the capability's output contract requires. The
  SDK's server delivers a result's content and `is_error` to the session,
  not its `structuredContent`, so the text is what is checked: a result
  that carries its output only as `structuredContent` is refused, and a
  `structuredContent` beside the text is not read. A result that does not
  carry the output (prose, a partial object, an integer beyond ±2^53, a
  confidence outside 0 to 1) fails the call that ran with R402, and the
  call's record is `failed` with R402: a served tool returns an error
  result whose text opens with `R402 EXECUTION_FAILED:`, and for another
  server's tool the PostToolUse hook replaces the result the session reads
  with that text (`updatedMCPToolOutput`). Such a call has failed: a
  `checkpoint` tool's call takes no checkpoint, and no call counts as a
  prerequisite that ran. A result is an error, passed on as before, only
  when its `is_error` is `True`; any other value is checked. Return the
  output's JSON text, or set `GroundedAgentConfig(check_outputs=False)`
  (outside class SL; the configuration's `config_sha256` then records it),
  which skips only this check: the grounding policies and a minimum
  confidence read the output the one text item carries. The check runs
  before the grounding policies and the profiles' minimum confidence, as
  the executor's does, and those apply to the output it read.
  `create_grounded_mcp_server` guards every tool with a callable `handler`,
  whatever its class, and refuses one without (`ValueError`, R407) unless
  `require_layer=False`.

### Added
- Standard 1.2.0, host protocol, runs and audit records
  ([RFC-0006](spec/RFC-0006-host-protocol-approval-and-runs.md), Part B;
  findings ACS-14, ACS-15, ACS-20, ACS-30, ACS-31, ACS-32, ACS-33, ACS-34,
  ACS-37, ACS-45, ACS-62):
  - §5.19 Host Protocol: every action and response, the members the
    executor computes and the outputs it composes, the run operations, the
    tick boundaries and wake-up time, the host's obligations (one writer,
    save before acting, at-least-once delivery keyed by `run_id` and `id`,
    a unique `run_id`, integrity and a key where others can change stored
    states), cancellation (R408), protocol traffic, error reasons and the
    run record every host keeps; `schemas/host_protocol.schema.json`
    requires `run_id` on every action. Class EX (§10.5): the runtime
    fixtures are normative for executors, after an audit of every member
    they pin (the generator refuses a fixture that pins an unlisted one).
  - Reference executor: `Run::cancel`, `wake_at`, `take_trace`,
    `take_records`, `taken_heads` (SHA-256 chain heads over what was taken)
    and `run_record`; record mode `actions` (`StartOptions.records`,
    `records="actions"`), with a record for every step that runs, every
    failure-mode checkpoint and every rollback; an `audit` step that binds
    `require_record: true` fails R402, reason `not_recorded`, when it did not
    record. Python: `_core.Run` gains the same operations, `_core.next_fire`;
    `WorkflowRunner.advance`, `cancel`, `archive=`, `save=`/`key=` (on
    `run`, `drive`, `advance`, `resume` and `cancel`), `run_ids=` and
    `event_seen=` (host stores for used `run_id`s and seen `event_id`s),
    `start(records=, trigger=, event=)`; `Host.withdraw`, `HostCannotServe`,
    `RunArchiveError`, `Turn`; `grounded_agency.workflows.protocol` (typed
    actions and responses) and `grounded_agency.workflows.triggers`
    (`OverlapGate`, `EventGate`, `trigger_attendance`, `next_fire`).
    `CoordinationEvent` keeps its record's `intent`, so the orchestrator's
    `audit` step returns the record its log exports.
  - §5.10.2 Evaluating Triggers: the host's duties, event acceptance with
    one run per `event_id`, fire times in the schedule's time zone (RFC 5545
    for clock changes), `every` anchored at the Unix epoch, `overlap` and
    missed fire times; a run an `invoke` step starts always has its
    invoker's attendance, whatever its `invoke` trigger declares; normative
    trigger vectors (`tests/conformance/triggers/`, from
    `scripts/gen_trigger_vectors.py`).
  - §5.2.3 Parallel Groups: members are unordered and the reference executor
    runs them in list order; W618 (`UNKNOWN_JOIN`) and W619
    (`GROUP_MATE_READ`).
  - §6.4 Audit Records and §8.4 Manual Overrides: the action record and the
    canonical event are the audit records; `CoordinationEvent.to_action_record`,
    `CoordinationAuditLog.export_action_records`,
    `grounded_agency.trust.manual_override` and
    `TrustModel.manual_override`; the evidence collector's `required=True`
    reports a capture that failed; the audit skill writes a record of its own
    with the event under `details.event`; the safety layers export their
    records of calls as action records, each with the `recorded_by` of the
    layer that decided the call: the Python SDK adapter's
    `export_action_records(scope)` (each call record gains `seq`, its number
    in the scope) and the Standard Agents binding's `actionRecord(entry,
    scope)`.
  - 44 runtime fixtures (`cancel_*`, `wake_at_*`, `records_*`,
    `run_record_*`, `parallel_group_*`, `audit_*`, `error_reason_*`,
    `invoke_trigger_attendance_*`,
    `response_extra_members_ignored`, `action_has_run_id`,
    `approval_record_decision_id`), whose script may hold `tick` with
    `changed`, `wake_at` and `cancel` entries and whose fixture may state
    `records` and `run_record`; four validator fixtures (W618, W619,
    `require_record`).
- Standard 1.2.0, approval, deferral and run identity
  ([RFC-0006](spec/RFC-0006-host-protocol-approval-and-runs.md), Part A;
  findings ACS-10, ACS-11, ACS-12, ACS-13, ACS-35, ACS-44):
  - §5.14 states the request for a step with no or a partial `approval`
    field, what the approval digest is computed over (the shown array,
    RFC 8785, lowercase hexadecimal, compared regardless of case), the
    integer bound as the executor applies it, that whatever reads values
    from JSON text refuses a member name twice in one object (the core's
    `exec::read_json` does), and the meaning of `in_session` and
    `out_of_band`. `tests/conformance/approval/digests.json`
    is normative under §10.3, with a vector for a `shows` reference that
    resolves to nothing.
  - Resuming a deferred run (§5.14.1): `_core.Run.resume`,
    `WorkflowRunner.resume` and `RunResult.resumable`. The deferred steps
    run again as the same run, with the steps that ran ahead of them that
    they read and a checkpoint step a queued mutation binds; a nested run
    that ended deferred continues; a queued step is asked afresh (of a
    person when attended), every request of the step names
    `queued_action_id` (a re-ask after a recheck and a retry included) until
    its action is carried out, and its `planned` record is updated in place
    with each decision and refusal; a queued record the resumption decides
    or supersedes takes the time and actor of then. A recovery loop during
    a resumption runs again only the steps from its target to the step that
    looped, a deferred handler among them keeping its nested run, and the
    resumption then goes on, so nothing that ran ahead runs twice. Trace
    kinds `run_resumed` and `invoke_resumed`.
  - With `identity@1`, an approval decision may attest its approvers
    (`approver_identities`); approvers are then counted by principal and
    checked against the requested kind and role, and the record lists the
    approvers that counted (`ActionRecord.approval.approver_identities`). In
    a workflow that targets 1.2, the approver may require `sender_check`
    and `accept_trust_classes` (V106 without `identity@1`, S303 when
    malformed); in an earlier target they stay unknown fields (W604) and
    get W616.
  - A run keeps its actor (§5.17): `Run.restore` and
    `WorkflowRunner.restore` take `actor_identity` and refuse another
    principal; a resumption may name a new actor, which the trace and later
    records show.
  - 41 runtime fixtures (`approval_*`, `approver_*`, `resume_*`; a script's
    `resume` entry and the `{{digest_upper}}` placeholder) and four
    validator fixtures (`*approver_identity*`). Each `step` digest vector
    gives what its step shows from (`bindings`, `recheck_read`), so an
    executor can be checked against the file alone.
- [Standard Agents interoperability](docs/integrations/standard_agents.md):
  a mapping of this standard against the Standard Agent Specification 0.2.0,
  how to build a grounded agent on it, and the changes proposed to each
  standard.
- `docs/research/analysis/standard_agents_mapping/`: the row-level mapping
  behind that document (319 rows in ten concerns, each with references and
  verbatim quotes from both sides), the findings it produced about each
  standard (83 and 64) and the questions the texts leave open. `tests/test_standard_agents_mapping.py` keeps the index, the
  files and their references to this repository in agreement.
- `examples/standard_agents/`: a reference binding in TypeScript and a worked
  example. `groundedTool` classifies a Standard Agents tool by an ontology
  capability and enforces the capability's checkpoint, approval and output
  rules inside the tool; approvals are recorded through an authenticated
  thread endpoint and bound to the §5.14 digest, which is tested against the
  reference executor's. A rejection cannot be lost to an approval made at the
  same moment and stops a call that is starting on that approval, a decision
  applies only to the round of the request it was made on (`POST
  acs/approvals` takes `{ digest, round, decision }`), a call is recorded
  before its tool runs, a checkpoint or an approval authorises a call only
  inside an execution and a checkpoint for ten minutes at most, and canonical
  JSON refuses unpaired surrogates. `lintPromptTools` and `lintAgentBindings` check a prompt's
  tools and an agent's stop and session bindings before anything runs. CI
  type-checks it against the published `@standardagents/spec` types and runs
  its tests.
- `schemas/interop/standard_agents_annotation.schema.json`: the schema of
  the `acs` annotation the binding puts on a tool.
- `scripts/gen_standard_agents_binding.py` generates the binding's ontology
  table, the annotation schema and the digest fixtures from the ontology and
  the reference executor; `--check` fails on drift (CI).
- `tasks/standard-agents-upstream/`: nine issue texts for the Standard Agent
  Specification, and `file-issues.sh`, which files them in order with the
  GitHub CLI.
- [RFC-0005](spec/RFC-0005-tool-calling-hosts.md) (Accepted, Standard
  1.2.0): how the Standard applies to a host where a model chooses tool
  calls, with a tool binding record, checkpoint and approval rules for a
  sequence of calls, a conformance class and call-sequence fixtures.
- `schemas/interop/standard_agents_mapping.yaml`: the Standard Agents
  binding's conventions as data (capability rulings, anchor forms, identity
  map), checked against the ontology and the mapping rows.
- `schemas/generated/capability_contracts.schema.json`: the 72 capability
  contracts as strict JSON Schema 2020-12, generated by
  `scripts/gen_capability_json_schemas.py` (`--check` in CI).
- Conformance vectors (informative): approval digests in
  `tests/conformance/approval/`, trust scores in `tests/conformance/trust/`,
  and `grounded_agency.trust`, a reference of the section 8 arithmetic.
- `spec/ROADMAP.md` lists the four version lines and where each is declared;
  `tests/test_version_lines.py` keeps them in agreement.
- `docs/guides/RUNNING_WORKFLOWS.md` lists the executor's trace event fields
  and kinds, tested against the core.
- Standard 1.2.0 §5.18, Tool-Calling Hosts: the tool binding record
  (`schemas/interop/tool_binding.schema.json`), unbound tools, classification
  by effect, composite and control-only tools, the scope, order and
  concurrency of calls, one checkpoint and one decision per call, refusals as
  §9.8 diagnostics, records that name the layer, and capability outputs on a
  text-only channel; §5.2.2 states the executor's checkpoint use for steps.
  §10.4 adds the safety-layer conformance class SL.
- Safety-layer conformance fixtures: 33 binding fixtures in
  `tests/conformance/bindings/` and 28 call-sequence fixtures in
  `tests/conformance/calls/`, with their schemas and the statements of the
  two reference layers, generated by `scripts/gen_call_fixtures.py`
  (`--check` in CI). The Python SDK adapter and the Standard Agents binding
  run them.
- Python SDK: `load_bindings`, `check_offered` and `ToolBinding` (binding
  records, W617, V111, V102, F506); `encode_capability_output`,
  `decode_capability_output` and `CapabilityOutputError` (§5.18.9);
  `grounded_agency.errors.text_form`.
- Python SDK: `GroundedAgentAdapter.check_call_result` checks the result of
  a call of an MCP tool bound to a capability (the output contract, R402;
  then grounding, F505, and a minimum confidence, F504): a tool
  `create_grounded_mcp_server` serves calls it with its result, and the
  PostToolUse hook with another server's; `GroundedAgentConfig.check_outputs`;
  `tool_result_output` in `grounded_agency.capabilities`, the output an MCP
  result carries (§5.18.10); `create_checkpoint_recorder(refuses_output=...)`.
- TypeScript package: `checkBindings`, `annotationRecord`,
  `encodeCapabilityOutput`, `decodeCapabilityOutput`, `effectiveFlagsOf`,
  `prerequisitesOf`. The Standard Agents binding adds `controlTool`,
  `additional_capabilities` and `invokes` with one-shot nesting tokens.
- Standard 1.2.0, evidence, grounding and secrets
  ([RFC-0008](spec/RFC-0008-evidence-grounding-and-secrets.md); findings
  ACS-06, ACS-21, ACS-22, ACS-23, ACS-40, ACS-51, ACS-53, ACS-58):
  - §3.1 defines grounded and inferred outputs; §4.1.1 defines
    `confidence`, `inference_method` and `uncertainty`; §6.5 one evidence
    anchor (`ref`, `kind`, `timestamp`, `excerpt`, `digest`; kinds with
    `record` and `x-...`; the `acs:` ref scheme; bare strings and other
    objects deprecated), the evidence available to a producer, and how an
    output reporting an action is grounded (a `record` anchor); §6.6 evidence
    records, stores and the `acs.evidence_recorded` notification; §6.7
    secrets in records; §6.3 retention follows the store, and `audit`
    reports its `store`.
  - §5.20 Grounding: the extension `grounding@1` and host policies (a list,
    covering nested runs) make the reference executor check host outputs:
    `acs:` citations covered by a bound reference, the `Output` response's
    `evidence_seen`, `attested`; F505 is raised and can fire a failure
    mode; with `grounding@1` an `invoke` step carries its nested run's
    anchors. In a 1.2 target `grounding` without the extension is V106.
    Python: `_core.check_grounding`, `Run.trace(since=...)`,
    `Run.trace_seq`, `grounded_agency.grounding` (`GroundingPolicy`,
    `check_grounding_output`), `WorkflowRunner.run(grounding=...)`,
    `GroundedAgentConfig.grounding` (applied to the outputs of the MCP
    tools bound to a capability; a refused output's call record is
    `failed` with F505 and the call id, and a policy that requires the
    capability of a call whose output the adapter cannot see, Claude
    Code's own tools, is warned about once per tool). TypeScript
    package: `evidence.ts` (`checkGrounding`, `groundingPolicies`, `covers`,
    `refsIn`) and `holdsCredential`; the binding's `grounding`, `seen` and
    `secrets` options. A host policy with a member other than `require`,
    `kinds`, `attested` and `x-...` is refused in all three languages; an
    `acs:` reference holds no index above 2^53 - 1.
  - Vectors: `tests/conformance/grounding/check.json` (normative, run in
    Rust, Python and TypeScript); `tests/conformance/secrets/credentials.json`
    (informative: the credential shapes the refusals of `persist` and
    `audit` data recognise, run in Python, TypeScript and the plugin's shell
    scan); 23 `grounding_*` runtime fixtures and
    `error_reason_secret_in_data`; seven workflow fixtures.
  - Evidence stores: `EvidenceStoreProtocol`, `EvidenceRecord`, `StoreInfo`,
    a durable `JsonlEvidenceStore` (repairs a torn last line),
    `subscribe()`, `record_capture_failure()`; the runner's
    `evidence_store` records the evidence of outputs the core kept, and its
    `redactor` registers the host's secrets; `GroundedAgentConfig` gains
    `evidence_store` and `secret_values`; `EvidenceAnchor.from_checkpoint`,
    and `create_checkpoint` records it. Binding: `exportEvidence`,
    `getEvidence`, `findEvidence`, `exportEvidenceJsonl`,
    `EVIDENCE_STORE_INFO`, `checkpointAnchor`.
  - `schemas/interop/evidence.schema.json` is listed in §6.1; the catalog
    schema accepts `grounding@1`.
  - Plugin: `hooks/secret_scan.sh`, the one scan the `persist` and `audit`
    skills' hooks copy; every skill's `evidence_anchors` examples are §6.5
    anchors, and the capability skills gloss `confidence` as §4.1.1 defines
    it.
- Standard 1.2.0, delegation, catalogs and validator diagnostics
  ([RFC-0007](spec/RFC-0007-delegation-catalogs-and-diagnostics.md);
  findings ACS-04, ACS-09, ACS-16, ACS-17, ACS-24, ACS-29, ACS-46, ACS-47,
  ACS-49, ACS-50, ACS-54):
  - §5.1.1 catalog manifests (`id`, `version`, `ontology`, `exports`),
    catalog sets and qualified workflow ids `<catalog id>/<name>` for
    `invoke`, resolved by one resolver in the validator and the executor
    (`core/src/catalogs.rs`); V107 for a hidden or missing workflow of a
    loaded catalog, W607 otherwise, V105 across catalogs.
  - §5.15.1 agent manifests (`schemas/agent_manifest_schema.yaml` 1.0.0) with
    derived maxima; §5.15.2 the workflow field `agents` (1.2 only): a
    literal unlisted agent is V107, a delegate step takes its target maxima
    (F501, approval, W602), the executor refuses an unlisted, unmanifested
    or task-refused delegation before approval or a checkpoint (R402, not
    retried), a literal task is checked (S303/S304); §5.15.3 `continues`.
  - §5.15 model families compared exactly and derived from a model
    identifier by one rule; `model_id` on identities and `effective`.
  - §5.2.4 domain ids and the host's selection rule; §5.13.1 typed,
    correlatable answers to `inquire`; §4.3 the scope of `conflicts_with`;
    §9.8 every location key, `path` and `catalog`.
  - §11.5: `agents`, `continues`, a catalog manifest and an `invoke` target
    that is a qualified id are 1.2 features (W616 in a workflow or catalog
    that targets 1.0 or 1.1, located at the step for a step member).
  - Rust: `names`, `agents` and `catalogs` modules; `validate::validate_set`,
    `validate_with` takes `catalogs` and `agents` beside the profiles;
    `Run::start_set`, `Run::restore_set` and `SetOptions`;
    `_core.model_family`; the WebAssembly interface's `validate`,
    `run.start` (in `options`) and `run.restore` take `catalogs` (each
    `{catalog, header}`) and `agents`. CLI:
    `tools/validate_workflows.py --with-catalog PATH --agents PATH`.
  - Python SDK: `WorkflowEngine.load_library`, `libraries`,
    `add_agent_manifest`, `load_agents`, `agent_manifests`; the runner
    passes them to the executor; `coordination.manifest`
    (`check_agent_manifest`, `manifest_maxima`, `join_maxima`,
    `target_maxima`, `check_task`), `coordination.families`
    (`model_family`), `coordination.inquiry` (`match_answers`),
    `workflows.domains` (`select_implementation`, `UnsupportedDomain`);
    `AgentDescriptor.from_manifest`, `.manifest()`, `.maxima()`,
    `AgentRegistry.register_manifest`.
  - TypeScript package: `manifestMaxima`, `joinMaxima`, `checkTask`,
    `workflowTarget`, `agentsApply`,
    `modelFamily`, `isModelFamily`, `selectImplementation`,
    `UnsupportedDomainError`, `isDomainId`, `issuePath`; `CoreContext`'s
    `validate`, `start` and `restore` take `catalogs` and `agents`
    (`SetArgs`). Binding:
    `deriveAgentManifest` (loads each `acs` annotation as a binding record,
    as the layer does, and follows `invokes`, with `invoked` for helper
    tools the prompts do not offer; refuses unannotated tools, annotations
    that do not load, invoked tools not given, declared flags stricter than
    a tool's capabilities and missing subagent manifests), `taskRefusal`,
    `declaredAgents` and `lintDelegationTargets` (both take the catalog's
    version header; `agents` has effect only in a workflow that targets
    1.2); `AgentIdentity.model_id`.
  - Conformance: 38 workflow fixtures with `catalogs`, `agents` and
    `expected_locations` (a `code` and its `path`, or for a finding with no
    `path` its `catalog`, `workflow` and `field`); 20 runtime fixtures (two
    of them, `agents_maxima_with_profile_person` and
    `agents_read_only_maxima_with_profile_checkpoint`, with a profile
    applied; `delegate_continues_v11_unchecked` and
    `delegate_identity_model_id_v11_unchecked` pin 1.1); normative vectors
    `tests/conformance/domains/match.json`, `agents/maxima.json`,
    `families/derive.json` and `inquiry/answers.json`.
- Approval digest vectors of kind `tool_call` for a call's shown values.
- Capability output vectors (informative), `tests/conformance/output/vectors.json`,
  which the Python and TypeScript codecs of §5.18.9 both pass. TypeScript
  package: `iJsonProblem`. Python SDK: `CheckpointTracker.valid_checkpoint_id()`,
  `has_commit()` and `max_age_minutes`.

- Domain profiles (Standard 1.2.0 §5.21, RFC-0010): the core loads and
  checks them (`profile::Policy`), the validator and the executor apply
  them (raised flags, a person for `require_human` and `block_autonomous`
  with `person_required` on records and in the trace, F504
  `below_minimum_confidence` and `invalid_confidence`, W606 for a
  mandate-only step), and they are saved with a run. Python:
  `AppliedProfiles`, `ProfileError`, `load_profile`,
  `GroundedAgentConfig(profiles=...)`, `WorkflowRunner(profiles=...)`,
  `_core.Validator.check_profiles`, `profile_flags`, `profile_policy`;
  `tools/validate_workflows.py --profile`. Normative profile vectors
  (`tests/conformance/profiles/`), 17 runtime fixtures and validator
  fixtures with profiles (`EXPECTATIONS.json` gains `profiles`). A runtime
  fixture's script entry may list `absent` members, which the pending
  action must not hold. The adapter's records digest (`config_sha256`)
  covers the applied profiles; `GroundedAgentConfig(schema_root=...)`. When
  a profile requires a person for a call, the adapter's ask reason says
  `requires approval by a person`, and an unbound tool's record carries
  `person_required` when a profile requires one for `mutate`
  (`ToolCapabilityMapper.person_required`).
- Trust (§8): `grounded_agency.trust.resolve` with the six strategies of
  §8.2 and tie-breaking (a single candidate is chosen whatever the
  strategy), `Candidate`, `Resolution`, `merge_trust_weights`;
  the trust vectors are normative, with `resolve.json`. The
  conflicting-sources benchmark resolves with `resolve` (same results).
- Entity ids (§7.1): `grounded_agency.entities.parse_entity_id`,
  `tests/conformance/entities/ids.json`; `entity_taxonomy.yaml`'s pattern
  is checked against its examples, and names every white space and control
  character a segment cannot hold (U+00A0, U+2028 and U+0085 among them),
  so it means the same in every regular expression dialect.
- Cited versions (§11.6): `grounded_agency.versions.check_cited` and
  `CitedVersionError`; the OASF adapter refuses a mapping that cites
  another ontology major or an unsupported Standard.
- WebAssembly (ACS-42): the core's `wasm` feature (`core/src/wasm.rs`, a
  JSON interface over three C-ABI exports) and the TypeScript package's
  `./wasm` entry (`AcsCore`, `CoreContext`, `CoreRun`, `loadDocuments`),
  which runs the validator and executor, profiles included, in process,
  with the host protocol's run operations (`run.resume`, `run.cancel`,
  `run.wake_at`, `run.take_trace`, `run.take_records`, `run.run_record`,
  `run.trace` since a `seq`; `CoreRun.resume`, `cancel`, `wakeAt`, ...);
  `Context::from_values` with an in-memory schema store.
  `.github/workflows/publish-npm.yml` publishes `@synaptiai/acs-core` from
  a tag `acs-core-vX.Y.Z` on `main` when `NPM_PUBLISH_ENABLED` and
  `NPM_TOKEN` are both set (a dry run otherwise).
- Domain profiles in every reference layer (§5.21.3): a profile's grounding
  policy is checked by the executor's grounding check (§5.20) and by
  `GroundedAgentAdapter.check_call_output`, which also applies the
  profiles' minimum confidence (`_core.check_confidence`) to the outputs of
  the tools `create_grounded_mcp_server` serves, with or without
  `config.grounding`; an exported call record carries `reason_code` and
  `person_required` (a failed call's record too). A composite tool takes
  the flags a profile raises for each binding it `invokes`, and its person
  requirement, transitively (§5.18.4), in the adapter
  (`ToolCapabilityMapper.map_tool`) as in the binding, so no profile rule
  is bypassed through a composite. The Standard Agents binding applies
  profiles through `groundedTool({profiles})` and `bindingProfiles` (raised
  flags at the call's effective risk with its `invokes`, and for what the
  tools it invokes perform; a person's approval, also for a composite whose
  approval covers a call needing one; grounding; minimum confidence;
  loading warnings such as W604 reported to `onWarning`), and a TypeScript
  host's `CoreContext.start` reports those warnings likewise (the
  WebAssembly interface's `run.start` answers them as `warnings`).
  Runtime fixtures `profile_grounding_*` and the header fixtures
  `header_1_2_sender_check_needs_identities` and
  `header_null_sender_check_not_read`; validator fixtures
  `warn_version_feature_1_2`, `warn_version_feature_1_2_grounding`
  (`grounding@1` and F505 in `on_error`) and
  `warn_version_feature_1_2_trust_classes` (`accept_trust_classes`), with
  the other streams' `pass_approver_identity_1_1_warn` and `*_v11_warn`
  fixtures one for every 1.2 feature of §11.5's table.
- `skills/README.md` lists each frontmatter key's owner (Agent Skills,
  Claude Code, ACS), checked by `tests/test_skill_frontmatter.py`.
- Standard 1.2.0 text of §4.1.2 (schema dialect), §5.21, §7.1, §8.1–§8.3,
  §11.5–§11.7 and Appendix D.7; RFC-0010.

- Standard 1.2.0, checkpoints, rollbacks, sends and memory
  ([RFC-0009](spec/RFC-0009-checkpoint-rollback-send-memory.md); findings
  ACS-18, ACS-19, ACS-26, ACS-27, ACS-48, ACS-52): §4.4.1 (what a
  checkpoint holds, what `restored` asserts, what a rollback never
  reaches), §4.4.2 (transmissions, idempotency keys, compensation,
  destination policies), §4.5 (memory scopes, `ttl`, what `stored: true`
  guarantees), §5.15.4 (checkpoints across a delegation), the §12.5
  patterns Guarded Send and Checked Rollback, Appendix D.6. Ontology
  outputs `checkpoint.mechanism/captured/excluded/digest/expires_at`,
  `rollback.unrestored/not_covered/changes_reverted/verification`,
  `send.compensation`, `persist`/`recall` `scope`, `stored_at`,
  `expires_at`, `delegate.effective.checkpointed`.
- Normative vectors `tests/conformance/destinations/match.json` (run by the
  core, Python and TypeScript) and `tests/conformance/memory/store.json`;
  22 runtime fixtures (idempotency keys, destination refusals, rollback
  reports, memory scope echo) and 8 validator fixtures.
- Python SDK: `FileSnapshotStore` (checkpoint content that never captures
  the host's own records; `CheckpointTracker(snapshots=...)`,
  `restore_checkpoint`, `checkpoint_output`), `MemoryStore`
  (`MemoryContext`, `MemoryStoreError`), `IdempotencyLog`,
  `Host.send_once`, and `Host` defaults that perform `checkpoint`,
  `rollback`, `persist` and `recall` and answer `Rollback` with these
  stores; `GroundedAgentConfig(allowed_destinations=..., snapshots=...)`.
- TypeScript package: `destinations.ts` (`checkPattern`, `allowed`, ...)
  and `duration.ts` (`parseDurationMs`). Standard Agents binding:
  `configureLayer`, a `send` tool's `destination` option, `memoryTools`.

### Changed
- The shipped domain profiles are version 2.0.0, cite Standard 1.2.0 and
  ontology 2.2.0, key `checkpoint_policy` by capability id or `"*"`, and
  list anchor kinds as `required_anchor_types`. The documentation and the
  compliance documents say a profile setting is enforced where a profile
  is applied, and which rules the reference implementation refuses until
  it checks them; the site's domain figures follow §5.21.3. A profile's
  `checkpoint_policy` `never` for `rollback` is W602, as for `mutate` and
  `send` (a `checkpoint` `requires` edge needs a checkpoint before it).
- Direct dependencies are at their latest releases. Python: the dev ranges are
  pytest 8.4.2–9, pytest-asyncio 1.x, mypy 1.19.1–2 and ruff 0.17 (CI runs
  ruff 0.17.4).
  Rust: `hmac` 0.13, `sha2` 0.11, `saphyr`/`saphyr-parser` 0.3.3; CI builds
  with Rust 1.99.1. Two indirect crates stay behind: `encoding_rs` (capped
  by `saphyr`) and `ordered-float` (5.5 needs Rust 1.90). Go: cel-go 0.33.2
  for the CEL differential check, which now needs Go 1.26.
  GitHub Actions: checkout v7, setup-python v7, cache v6, upload-artifact
  v7, setup-go v7.
- CI tests Python 3.14 and 3.15.
- The rate limit (SEC-010) is enforced in the adapter's PreToolUse hook
  instead of the permission callback. The SDK approves a tool in
  `allowed_tools` without calling the callback, so listed tools used to skip
  the rate limit; the hook runs for every call. **Tools you pre-approve in
  `allowed_tools` now count against the limit**: by default 10 high-risk
  calls a minute (Write, Edit, destructive Bash), 30 medium and 120 low,
  with a 1.5x burst. Raise them with `GroundedAgentConfig(rate_limit=...)`
  if an agent needs more. A rate-limited call is denied before it reserves
  a checkpoint, and an error inside the rate check denies the call.
- The adapter's PreToolUse safety check no longer lets a call through
  when it hits an error. For a tool in `allowed_tools` that hook is the
  only check that runs, so an error used to skip both the rate limit and
  the checkpoint. A tool the mapper cannot classify is now treated as a
  high-risk mutation (rate-limited, needs a checkpoint) in both modes; any
  other error denies the call in strict mode and is logged in non-strict
  mode. Deny reasons are generic; the detail and traceback go to the log.
- `wrap_options()` adds Stop and SubagentStop hooks. A checkpoint hold left
  behind by a call another PreToolUse hook denied used to block every other
  mutation for up to 10 minutes; now it counts as used when the turn ends,
  and the Stop of any session the adapter serves ends every checkpoint's
  validity (Standard 1.2.0 §5.18.6).
- `wrap_options()` no longer adds `Skill` to `allowed_tools`, so `Skill`
  calls reach the permission callback (the SDK warned that it was shadowed).
- `SyncStrategy`, `Severity` and `StepStatus` are `StrEnum`s, so `str()` of
  a member is its value.
- `schemas/interop/standard_agents_annotation.schema.json` describes the
  annotation as a carrier of the tool binding record: `standard` and
  `ontology` are required, the copies of the layer and flags optional, and a
  copy that names another layer or a weaker flag than the capability's is
  invalid.
- `schemas/interop/standard_agents_mapping.yaml` cites Standard 1.2.0 and
  ontology 2.2.0.
- The `send`, `rollback`, `checkpoint`, `persist` and `transform` skills'
  prompt hooks no longer judge what code decides (approval, a checkpoint,
  rate limits, expiry); what they still judge is labelled a model-judged
  addition (Standard 1.2.0 §5.18.10). `spec/SECURITY.md` §5.4 maps every
  condition of the skills' hooks, and §5.5 says why the plugin's hooks do
  not claim class SL.

### Fixed
- A reference index beyond the platform's `usize` (`${a[18446744073709551615]}`)
  was a parse error on a 32-bit target and a missing index on a 64-bit one;
  it is a missing index everywhere.
- Python SDK: `register_mcp_tool` accepted an unknown capability and a
  declared risk below the ontology's (`mutate` with `risk="low"` needed no
  checkpoint). It now refuses the first (V101) and ignores and reports the
  second (W602), as STANDARD 5.2.1 requires of a step.
- Python SDK: evidence anchors stored a tool's input, which can hold
  credentials; they now store it only with `evidence_include_tool_input`.
- Python SDK: `OrchestrationRuntime(evidence_store=...)` given an empty store
  (falsy, `len` 0) used a new one instead; it now uses the store it is
  given.
- Python SDK: `wrap_options` replaced the host's `can_use_tool` callback; it
  now chains to it.
- Plugin hooks: the persist, rollback and send skills' command hooks exited 1,
  which Claude Code does not treat as a block; they now exit 2 with the reason
  on stderr. The audit hook logged only Skill calls, with their arguments; it
  logs every call with a digest of the input. Refusals open with the
  diagnostic code (`F501 CHECKPOINT_REQUIRED:`).
- Documentation no longer says that a domain profile setting is enforced
  where no shipped component applied a profile; the compliance documents say
  which component enforces what (Standard 1.2.0 applies profiles, see
  Changed).
- A Bash call whose input is not a dictionary, or whose `command` is not
  text, made the tool mapper raise, and the PreToolUse hook then let the
  call through. It is now treated as an unknown, checkpoint-gated mutation.
- Passing options that `wrap_options()` already returned to it again (as
  `GroundedClient` does with the options it is given) returns them
  unchanged instead of adding a second set of hooks.
- Python SDK: the Bash classifier read only the first word of each part of a
  line split at `&&`, `||` and `; ` followed by a letter, so `env rm -rf x`,
  `ls | sh`, `ls & rm x`, `ls ;/bin/rm x`, `echo x >~/.bashrc` and
  `find . -delete` counted as read-only and needed neither a checkpoint nor
  approval. The line is now read with the shell's quoting rules and split at
  every control operator; it is read-only only when every command in it is
  allow-listed, by its exact name, with no option that writes, and it has no
  output redirection except to `/dev/null`, no subshell and no here-document.
  A quoted operator is now data: `grep -E "a|b" f` is read-only.
- Python SDK: with a `permission_prompt_tool_name`, a call the prompt tool
  denied kept the checkpoint reserved, so the next mutation was refused with
  F501 for up to ten minutes. The adapter no longer reserves for a call it
  asks about in that mode; the call takes the checkpoint once it has run.
- Plugin checkpoint hook: a marker that was not a JSON object made `jq` exit
  5, which Claude Code treats as a non-blocking error, so every Write, Edit
  and Bash call ran. Any failure in the hook now blocks the call (exit 2).
- Skill hooks: the persist hook's protected paths could be reached through
  `//`, `/./` or `..` segments, which it now refuses; the send hook matched
  `localhost` case-sensitively and blocked URLs that only contained an
  internal-looking number, such as a version in a path. It now matches host
  names in any case, and an address only where a host stands.
- Plugin audit hook: where `flock` is not installed (macOS), concurrent runs
  appended without a lock and could break the HMAC chain. Every run now takes
  flock(2) on the log file itself, through `perl` or else `flock` (any
  implementation), so sessions using either exclude each other and the kernel
  releases the lock of a run that dies; `.claude/audit.log.lock` is no longer
  used. A held lock delays a run by at most `AUDIT_LOCK_WAIT` seconds
  (default 40, at most 55); the entry is then written, and the verifier
  reports it if it is out of chain order.
- `tools/verify_audit_log.py` split lines on U+0085, U+2028 and U+2029 as well
  as newlines, so a log with such a character in a logged name failed
  verification. It splits on newlines only.
- Standard Agents binding: an approval accepted after the deadline extended
  the request, so with enough approvers it never expired. No approval is now
  accepted more than `expires_ms` after the request, and one stored later
  counts for nothing; a rejection is still accepted until the request is used
  or expires.

## [v2.0.0] — 2026-10-29

Implements Standard v1.1.0 (Candidate Standard) with RFC-0003 and RFC-0004
(#114, #116) and replaces the 1.0 validator and engine with one Rust core
(#115). The Standard's version (v1.1.0; v1.0.0 still supported) is separate
from this plugin release.

**Upgrading from v1.2.0:**
- Building from source needs a Rust toolchain (rustc >= 1.86): the validator
  and executor are the `grounded_agency._core` extension, built by maturin
  with `pip install -e ".[dev]" -c constraints.txt`.
- `transform.output` is `object|array` (ontology 2.1.0); a reference to it
  without an annotation is now B204.
- Validation is stricter: catalogs that passed 1.0 may now get errors or
  warnings (unknown fields W604, unbound required inputs W615, literal type
  mismatches B203, among others listed below).
- A quorum's model families count only when the host attests them.

### Added
- **Release workflow.** `.github/workflows/release.yml` publishes a GitHub
  Release with the tag's CHANGELOG section as its notes, for a pushed `v*`
  tag or, run by hand on `main`, for a tag it creates there;
  `scripts/release_notes.py` refuses a tag that does not match `plugin.json`
  or has no section
- **Delegate identity (#114, RFC-0004 amendment).** With `identity@1` a
  host may attest who took a delegation (`effective.identity`); a waiting
  delegate keeps only results from that principal (others dropped as
  `delegate_identity`), a malformed or contradicting identity is R402, and
  `quorum.require_distinct_identities` counts one verdict per attested
  principal. Quorum model families now count only as attested. Validator,
  executor, schema, eleven runtime fixtures and docs
- **Standard changes from the orchestrator fixtures (#114).** Gates can
  `end` a run successfully (`RunResult.ended`); a step can `delay` before
  it goes on (`wait@1`), without a fake event to wait on; an `accept_from`
  or `correlate` built from a missing value fails the step at once (R402)
  instead of dropping every sender, or matching every event that lacks the
  key; and
  `after_deferral: run` (`approval@1`) lets a step that does not depend on
  a deferred one, such as an escalation, run anyway. Validator, executor,
  Python runner, schema, runtime fixtures and docs
- **W616 `VERSION_FEATURE_MISMATCH`.** A workflow that declares standard
  1.0 but uses a 1.1 feature (`workflow_extensions.requires`, gate
  `phase` or `end`, the `in` operator, failure-mode `when` or `on_error`)
  warns once per feature, so a forgotten version bump no longer passes
  silently
- **The #114 author's orchestrator workflows as conformance fixtures.** The
  nine workflows they ported to the v1.1 candidate (revision 1.1e, which
  uses gate `end`, `delay`, `after_deferral` and a waiting `delegate` per
  reviewer) are a static fixture (`pass_orchestrator_port`, kept as
  contributed), and fifteen runtime fixtures (`orchestrator_*`) script runs of
  them: routing into a nested delegation, a liveness recovery, a quorum
  that passes and one that loops after a RETHINK, a self-merge and a red
  base that escalates to incident triage, an owner-approved and an
  unattended (deferred) message, an owner answer with a foreign one
  dropped, a question ended for more research, a scheduled sweep where
  only the reminder is deferred, an escalation that interrupts the owner,
  a prod notice then an early end, and both kinds of daily report
- **Contributed runtime fixtures.** Twenty scripted runs the #114 author
  wrote from the spec (`gap1_*` standing mandates, `gap2_*` verdict scope
  and `min_full`, `gap3_*` R406 and R401 around the deadline, `gap5_*` the
  authenticated principal) are kept as sent in
  `tests/conformance/contrib/`; the generator checks and copies them
- **Read-only reviewers and per-reviewer waits (#114).** `delegate` takes
  `read_only` (attested in `effective`), and `quorum.require_read_only`
  requires it of every reviewer. `wait` is allowed on `delegate`: the step
  delegates, then waits for that delegation's result, so a `retry` replaces
  a reviewer that went silent without asking the others again; a quorum's
  `verdicts` may list one reference per reviewer step. Host or device
  placement of a delegated step is recorded as an open question in
  RFC-0003
- **Agent identity, `identity@1` (RFC-0004, #114).** A new
  `schemas/agent_identity_schema.yaml` says who a party is (principal, kind,
  role, model family, owner, how it was authenticated, trust class).
  `receive`/`synchronize` take `sender_check`, `accept_trust_classes` and
  `always_ask_trust_classes`: the executor drops items whose sender's
  identity fails a check, keeps the identity on each kept item, and asks a
  person (never a standing mandate) to approve any step that requires
  approval and uses, directly or through other steps, an item from an
  "always ask" class (or one with no trust class). Runs can carry an
  actor identity onto every action record (`WorkflowRunner.run(...,
  actor_identity=...)`), and `AgentDescriptor.identity()` produces one.
  `world_state_schema.yaml` 1.1.0 and `authority_trust_model.yaml` 1.1.0
  (default weights per trust class) follow; `validate_canonical_schemas.py`
  keeps the trust classes and the world state's identity type in step with
  the identity schema
- **`in` in condition expressions (#114).** `x in y` tests membership in a
  list or the keys of a map, as in CEL (STANDARD v1.1 §5.8); the cel-go
  differential covers it
- **Rust core (`core/`, #114).** The workflow validator now lives in a Rust
  crate compiled into `grounded_agency._core` (maturin build; Rust >= 1.86).
  It brings a hardened YAML 1.2 loader (size and depth limits, alias budget,
  no symlinks, unique string keys) with a PyYAML parity test, the condition
  expression language of Standard v1.1 §5.8, and the v1.1 edge, safety-flag,
  unknown-field and version rules. `tools/validate_workflows.py` and the
  Python `WorkflowEngine` both call it, so they can no longer disagree. CI
  gains a `rust-core` job (fmt, clippy, tests, MSRV) and a `cel-differential`
  job that checks the expression fixtures against cel-go
- **Orchestration extensions, first part (#114):** `workflow_extensions.requires`
  is validated (unknown extensions and undeclared extension fields are V106),
  `triggers` (schedule with 5-field cron or interval and IANA time zone,
  event, manual, invoke) are validated under `triggers@1`, and a step
  `timeout` outside the duration grammar warns (W614). Recovery is validated
  under `recovery@1`: `goto_step` resolves to a `store_as` (V107 otherwise;
  a capability id is deprecated, W603), `on_error` triggers, escalation to
  `handler: true` invoke steps through `action: escalate` and
  `on_exhausted`, injected `${_recovery.*}` context, untriggered recoveries
  (W609), unreachable handlers (W613), unknown invoke targets (W607) and
  invoke cycles (V105). `wait@1` validates waits on `receive` and
  `synchronize` (required duration timeout, liveness that can fire before
  it, W608 for a checkpoint taken before a wait), and `approval@1`
  validates structured approvals (approver, digest binding, recheck,
  expiry, unattended behaviour; W606 when an unattended run would reach an
  approval with no plan). `delegation@1` covers delegation hints
  (`fresh_context`, `model_family`, `role`) and sender filtering
  (`accept_from`), and `quorum@1` validates review quorums on blocking
  `constrain` steps: reviewers are earlier, distinct delegate steps,
  vocabulary and thresholds are consistent, and reviewers stay independent
  of forbidden inputs (checked transitively, including through context a
  recovery loop injects), fresh context and model families (F504). Declaring an extension the validator
  does not check is refused (V106). New guide:
  [docs/guides/ORCHESTRATION_EXTENSIONS.md](docs/guides/ORCHESTRATION_EXTENSIONS.md)
- **Reference executor (#114).** A deterministic, sans-IO executor in the
  Rust core runs validated workflows: conditions and gates, checkpoint
  authorisation and invalidation after waits, digest-bound approvals with
  expiry and rechecks, unattended behaviour, waits with event matching,
  retries with backoff, deadlines, failure modes, recovery loops,
  escalation to handlers, nested invocations and review quorums. Runs
  snapshot to canonical JSON (RFC 8785) with a SHA-256 and optional HMAC,
  and resume anywhere. Python drives it with
  `grounded_agency.workflows.WorkflowRunner` and a `Host`
  ([guide](docs/guides/RUNNING_WORKFLOWS.md)); runtime conformance fixtures
  in `tests/conformance/runtime/`
- `docs/research/analysis/validator-engine-disagreements-1.0.md`: minimal
  reproductions of the 22 cases where the 1.0 validator and engine judged
  the same workflow differently, and how each behaves now (#114, question 3)
- A step that raises `requires_checkpoint` above the ontology is now held to
  it: F501 when no checkpoint runs before it
- `world_state_schema.yaml` 1.1.0: action records gain status `rejected`
  and `expired`, an optional `approval` record (digest, decision,
  approvers) and an optional `reason`
- `schemas/review_verdict_schema.yaml` for quorum verdicts; ontology inputs
  and outputs for delegation and quorums (`delegate.fresh_context`,
  `.model_family`, `.role`, `.effective`; `receive`/`synchronize`
  `accept_from`; `constrain.tally`)
- `spec/STANDARD-v1.1.0.md` (Candidate Standard) and `spec/RFC-0003-orchestration-extensions.md`
  (Accepted) answering #114; see the [specification changelog](spec/CHANGELOG.md)
- Validator warnings: `tools/validate_workflows.py` reports warnings (W6xx)
  separately and passes unless `--strict` is given;
  `tools/validator_suggestions.json` gains `warnings` and
  `structured_warnings`, and hints such as "did you mean" are printed
- `WorkflowEngine.validate_report()`, `add_workflow()` and `effective_flags()`;
  `ErrorCode` gains the v1.1 codes and `Severity` is exported
- `python tools/sync_skill_schemas.py --check`, run in CI, fails when a
  generated skill file (output schemas, the 17 bundled workflow catalogs and
  their schema copies) has drifted from its source
- Conformance fixtures for the v1.1 edge, flag, unknown-field and version
  rules; `expected_warning_codes` in `tests/fixtures/EXPECTATIONS.json`
  (empty means none allowed); language-neutral expression fixtures under
  `tests/conformance/expressions/`
- `tools/validate_canonical_schemas.py` and a CI job covering the five canonical
  schemas designated by spec §6.1, which no validator checked before. It asserts
  §6.2/§6.3 required fields, trust-model internal consistency, alias-threshold
  ordering, and cross-file agreement with the benchmark fixture. Every defect
  from #105 and #106 is covered by a negative test proving the validator now
  catches it (#107)
- `spec/RFC-0002-agent-reliability-profile.md` proposing cross-session agent
  behavioural reliability as a first-class concept, and naming the prerequisite
  that blocks it: the standard has no agent identity object to attach a profile
  to (#104)
- `tools/validate_rfcs.py` and a CI job enforcing what `spec/GOVERNANCE.md`
  already required of RFCs — motivation, alternatives, backward-compatibility
  analysis and conformance test updates — plus header metadata, unique RFC
  numbers, and that cited repository paths exist. RFC-0001 was missing two of
  the required sections and now carries them (#104)
- `tools/validate_constraints.py` and a CI job asserting that every pin in
  `constraints.txt` names a package `pyproject.toml` declares and falls inside
  the range declared for it. The two files state overlapping facts about the
  same packages; this is what makes disagreement fail loudly instead of
  surfacing as an opaque pip resolution error
- `tools/validate_doc_links.py` and a CI job asserting that documentation
  cross-references resolve. Markdown links were the one reference kind nothing
  checked, which is how `docs/integrations/claude_agent_sdk.md` came to cite a
  `comparisons/` directory that has never existed. It reads every link form
  CommonMark allows — titles, angle brackets, images, and links whose text
  contains nested brackets — because anchoring on the opening `[` cannot see a
  badge, which had left the README's links to `LICENSE`, `spec/STANDARD-v1.0.0.md`
  and `CHANGELOG.md` unvalidated. Code-span paths are checked in `CLAUDE.md` and
  `README.md` only: repo-wide that check produces ~109 findings of which
  essentially none are defects (package-relative paths, tutorial placeholders,
  roadmap deliverables), and a validator that cries wolf gets ignored

### Changed
- **`transform.output` is `object|array`** (ontology 2.1.0), so a
  transform can return records as a list. **Breaking:** an unannotated
  reference to it is now B204, as for any union; the reference, domain,
  example and test catalogs annotate theirs.
- **`retrieve` and `search` are soft prerequisites of `ground`** (ontology
  2.1.0): a retrieved source or a search result is evidence to ground a
  claim in, so grounding generated text against them no longer warns
  W601.
- **Catalog failure modes all fire.** Of the 23 in the reference,
  manufacturing and digital-twin example catalogs that had neither `when`
  nor `on_error`, 15 gained a trigger (a step error, or an empty or
  failing output) and 8 were removed: they described a normal outcome (no
  vulnerabilities, nothing to decompose, conflicts `integrate` resolved),
  a check a later step or gate already makes (compliance, the cleaned
  data's quality), or a threshold the step does not have. An empty batch
  in the digital twin sync loop now ends the run early (gate `end`)
  instead. Runtime fixtures `domain_twin_no_events` and
  `domain_rag_no_passages` run two of them.
- **`schedule_management` with no free slot completes.** Ranking, planning
  and drafting are skipped, and the explanation (now given the slots and
  conflicts) and the audit still run; before, a `stop` gate ended the run
  R403 with neither. A runtime fixture (`domain_schedule_no_slot`) runs
  this path.
- **Unattended runs ask standing mandates, and deferral continues (#114).**
  A `standing_mandate` approver is asked even when nobody is present; the
  host answers `approved`, or `unavailable` when no mandate covers the
  action, and only then does `when_unattended` apply. `defer_to_queue`
  defers the step and every later step that depends on it (reads its
  output, may act on the world, or follows it in the ontology), runs the
  steps that only read, reason or record, and ends the run `deferred`, so a scheduled sweep
  finishes its other work. `RunResult.deferred` lists the deferrals, and the
  default `Host` answers `unavailable` for a standing mandate
- **Quorum independence per reviewer (#114).** `forbidden_inputs`
  takes a per-reviewer mapping, verdicts carry `scope: full | delta`,
  and `quorum.min_full` requires passing full sweeps
  (`review_verdict_schema.yaml` 1.1.0; `tally.full_passes`)
- **Lost liveness is R406, separate from the R401 timeout (#114).**
  Lost liveness is now R406 (`LIVENESS_LOST`); failure modes (`on_error`)
  and `retry` take it, so a workflow can re-check a quiet worker and
  escalate only when the wait expires. A failure mode that handled lost
  liveness through `on_error: R401` must add R406
- **Migration:** binding `fresh_context`, `model_family` or `role` on
  `delegate`, or `accept_from` on `receive`/`synchronize`, now needs
  `delegation@1` in `workflow_extensions.requires` (V106). These inputs were
  previously unknown to the ontology and silently ignored; a consumer that
  ignored them would reuse a reviewer's context or accept anyone's items
- **Workflow catalog (#114).** Declares `# Standard version: 1.1.0`; approval
  flags no longer understate the ontology; `clarify_intent` asks through
  `inquire` and receives the answer only when questions were asked;
  `model_deployment` checks artifacts with `constrain` before deploying;
  `monitor_and_replan` critiques the detected violations at major severity;
  gates that read their own step declare `phase: after`;
  `digital_twin_sync_loop`'s verification loop fires on
  `${verify_out.passed} == false` and targets `plan_out`
- **Ontology edges (#114).** Five follow-up edges are `enables` instead of
  `soft_requires`, a redundant one is removed, and `constrain` is the soft
  prerequisite of `execute`, `mutate` and `send`; `audit` is
  `mutation_overridable`
- **`WorkflowEngine` safety fields are effective values** (the stricter of the
  step's declaration and the ontology); what the source declared is in
  `WorkflowStep.declared`. `validate_*` methods return errors only; an unknown
  store reference maps to B202 (`MISSING_PRODUCER`) instead of B201
- **`schemas/workflow_catalog.schema.json`** requires only the fields Standard
  §5 requires, and describes gate `phase`, failure-mode `when` and
  `spec_version`
- The 17 bundled `skills/*/reference/workflow_catalog.yaml` copies are
  regenerated from `schemas/workflow_catalog.yaml`; they had drifted.
  `sync_skill_schemas.py` also maintains schema copies a skill vendors
  without a bundled catalog (`skills/receive/reference/event_schema.yaml`)
- `schemas/event_schema.yaml` 1.1.0: `source.kind` gains `agent`
- Development dependencies are version-bounded instead of open-ended, and each
  cap names the major this repo is verified against rather than the next
  unreleased one: `mypy>=1.0,<2`, `pytest>=7.0,<9`, `pytest-asyncio>=0.21,<1`.
  A cap set at the next unreleased major would not have changed what CI
  installs — `mypy>=1.0,<3` admits mypy 2.x, which is precisely the upgrade the
  bound exists to make deliberate. Raising a cap now means running the suite on
  that major first
- Exact tool versions moved to a new `constraints.txt`, installed via
  `pip install -e ".[dev]" -c constraints.txt`. `ruff` is pinned there rather
  than in the `dev` extra: formatting is not semver-safe (0.16.5 began
  formatting Python blocks inside Markdown and turned CI red on a commit
  touching only `.gitignore`), but an exact pin in package metadata would
  conflict with a consumer's own ruff. The bounds describe what the package
  supports; the constraints file describes what a green check attests to
- The `claude-agent-sdk` floor is `>=0.1.52`, the oldest release whose
  `ToolPermissionContext` carries the `tool_use_id` that keys the checkpoint
  reservation in `can_use_tool`, rather than the newest release available. It
  was briefly `>=0.2.148`, which excluded working installs without cause, and
  then `>=0.1.25`, which admitted releases where the permission callback
  could not name its own reservation
- `pyyaml` carries an upper bound (`>=6.0,<7`) like everything else, and the two
  CI jobs that installed it directly now install the package instead, so the
  constraint is declared once rather than in three places
- RFC-0002 downgrades `delivery_score` from "derivable now" to provisional. The
  original proposal and the RFC's first draft both overstated it: `actor` is a
  bare string documented as `agent/human` so the population cannot be restricted
  to agents, no terminal-status subset is defined, and `rolled_back` has no
  agreed sign — §3.3 requires rollback be possible and §4.4 requires a
  checkpoint before one, but neither says how a rollback should be scored, so
  counting it as failure marks an agent down for exercising a capability the
  standard requires it to have (#104)
- RFC-0002 makes it normative that an implementation MUST NOT infer that
  `ProvenanceRecord.agent` and `ActionRecord.actor` denote the same principal,
  with a conformance fixture required for the rule (#104)
- RFC-0002's citation of the *PDR in Production* preprint now records that its
  author has stated they do not have a reproducible dataset supporting the
  "6,342 cycles" or independent-convergence claims, replacing an unresolved
  caveat with the author's own agreement that it is design context, not
  validation evidence. The wording is deliberate: "I do not have one" is not
  "none exists", and a document whose argument rests on §3.1 must not convert
  the one into the other (#104)

### Fixed
- **W608 sees waits in invoked workflows.** An `invoke` of a catalog
  workflow that can wait (any of its steps, handlers included, or one it
  invokes) counts as a wait, so a checkpoint taken before it no longer silently covers a later
  `mutate` or `send`. The #114 port's checkin_recovery mutate was the first
  case found; revision 1.1e checkpoints again after the escalation.
- **A recovery loop replaces every waiting delegate it runs again.** A loop
  from a later step (a blocked quorum, say) back to before the reviewers
  delegated them again without `replaces`, so the host could not cancel
  the earlier delegations; only a loop from the delegate itself named
  them. A pending replacement is kept until the delegate next delegates,
  also across a pass that skips it. Runtime fixtures
  `delegate_wait_replaced_by_later_loop` and
  `delegate_wait_replacement_survives_skip`.
- **Whole-branch review (#114): executor.** Forged snapshots that passed the
  state check and then panicked are refused at restore; resolved inputs
  deeper than I-JSON allows fail the step (R402) instead of breaking
  snapshots; a huge `min_approvers` still snapshots; `correlate` matches in
  a stable key order across restores; the executor's own refusals of an
  invocation are not retried; a recovery loop back to a waiting delegate
  carries `replaces`, also when the loop targets an earlier step or a
  retry's re-delegation failed first; clock values are capped at year 9999; a re-asked
  approval's record says why
- **Whole-branch review (#114): validator.** The YAML loader stops deep
  compact sequences at its nesting limit instead of overflowing the stack;
  same-file `#/...` `$ref`s and chains of refs resolve (only hops count
  toward the limit), and the schemas one validation resolves share a budget
  of 200,000 nodes, so refs that fan out are refused (S302) rather than
  exhausting memory; literal and template bindings are type-checked
  (B203), an explicit null included (except `invoke`'s `input`, where it
  means no inputs); reference syntax errors have one code everywhere (B201, B205 for
  an empty annotation); W606 follows `invoke`; an invoke cycle is reported
  once per workflow, not once per edge; diagnostics come in catalog order
  (workflow, then step); B202 has one wording. The stricter rules are
  listed in the [spec changelog](spec/CHANGELOG.md)
- **Whole-branch review (#114): catalogs.** `digital_twin_sync_loop` rolled
  back twice on a failed verification (an after-gate and a failure mode on
  the same condition); it rolls back once. `stop` gates that ended healthy
  cycles as failures are skips or conditions, so their audits run. Literal
  types (`plan.constraints`, `detect.threshold`, `search.scope`,
  `ground.claim`) match their inputs, steps bind the outputs they reason
  about, and failure modes on effectful steps have `on_error` triggers.
  The clarification workflows gate on what the analysis found, not on its
  confidence
- **The checkpoint hook did not block anything (#114).**
  `pretooluse_require_checkpoint.sh` read its payload from an argument,
  but Claude Code passes it on stdin, and it signalled a block with exit 1,
  which Claude Code treats as a non-blocking error. It reads stdin now (an
  argument still works), blocks with exit 2 and the reason on stderr, and
  still fails closed: every `Write`, `Edit`, `MultiEdit`, `NotebookEdit` and
  `Bash` call needs a valid marker
- **Whole-branch review (#114): catalogs, second pass.** Rollback steps no
  longer require a checkpoint of their own (the one before the mutation
  was spent, so the executor took a new one of the broken state first).
  A verify or verification step that errors rolls the mutation back;
  nothing is rolled back when nothing was mutated, and audits run after
  the rollback so they record it. `data_quality_pipeline` writes nothing,
  so it no longer checkpoints or rolls back and its risk is low
- **Whole-branch review (#114): skills.** Every capability skill's output
  contract, field table and examples use the ontology's field names and
  types (`verify` returns `passed`, `checkpoint` `checkpoint_id`, `detect`
  `matches`, and so on), and their safety constraints match the
  ontology's flags and risk
- **Whole-branch review (#114): Python.** The permission callback releases
  a denied call's checkpoint reservation, and without a `tool_use_id` only
  checks for a valid checkpoint. `WorkflowRunner` turns a host response the
  run refuses into R402 for a capability or `HostResponseError` otherwise,
  bounds the unanswered polls of each action (`max_polls`), and raises `RunStartError` from
  `restore` and for inputs that are not JSON data. The validator raises
  `FileNotFoundError` and the other `OSError` types for a missing or
  unreadable catalog or ontology, as `load_yaml` does. Boolean and NaN
  weights are rejected in profiles. The bundled ontology copies are kept in sync. The
  `acs` console script, which only worked inside a checkout, is removed:
  run `python tools/scaffold.py`
- **Whole-branch review (#114): tooling.** The conformance runner compares
  each fixture's codes exactly and gives each run its own suggestions file
  (`validate_workflows.py --suggestions-out`); four negative fixtures that
  were 780-line copies tripping unrelated checks are minimal now. CI runs
  the YAML-sync and transform-ref validators, installs with the
  constraints file everywhere, and checks the formatting of `tools/`
- **Unbound required inputs were silent (#114).** A step that does not
  bind an input its capability requires is W615. The reference catalog
  left 60 required inputs unbound across eight workflows; they are bound
  now, and `debug_code_change` gains a `bug` input to bind them from.
  Binding `checkpoint_id` exposed that the rollback steps of
  `debug_code_change` and `digital_twin_sync_loop` ran even when
  verification passed; they are skipped then, as in the other workflows.
  `digital_twin_bootstrap` read a skipped step's output when a world state
  was passed in; it now syncs from that state instead. `retry.max` and
  `retry.backoff` are validated (S303)
- **The example catalog used the v1 capability names (#114).**
  `examples/digital_twin_sync_loop.workflow_catalog.yaml` now holds the
  digital twin workflows of the reference catalog verbatim (a test keeps
  them identical) and is validated in CI with `--strict`
- **Runtime fixtures are generated in the repository.**
  `scripts/gen_runtime_fixtures.py` writes `tests/conformance/runtime/*.json`,
  and CI checks they are up to date
- **Skill docs named inputs the capabilities do not have.** The procedure
  text, examples and `argument-hint` lines of the capability skills now use
  the ontology's input names
- **Mistyped `input_bindings` keys were silent (#114).** A key the
  capability does not define is now W604 with a did-you-mean hint, and an
  `invoke` step's literal `input` is checked against the invoked workflow's
  inputs (S303 undeclared, S304 missing required). This found
  `digital_twin_bootstrap` passing `inputs:` (which the executor ignores) with
  names its targets do not declare; it now passes `input` with
  `user_input` and `previous_world_state`. Catalog bindings outside the
  ontology were renamed to its inputs, and the ontology gained six optional
  inputs that catalogs relied on. The skill docs' input tables now match the
  ontology, and the tutorial and doc examples validate cleanly
- **Domain workflow catalogs.** The four catalogs under `schemas/workflows/`
  failed validation before this release (mostly untyped references, plus
  ordering and binding errors) and nothing checked them. They now pass in
  strict mode, and CI validates them
- **The Python PreToolUse checkpoint hook never blocked anything.** It
  returned a top-level `permissionDecision`, which the Claude Agent SDK
  ignores; it now denies through `hookSpecificOutput` (#114)
- **Checkpoint reservation race (SEC-007).** `validate_and_reserve()` did not
  reserve: two concurrent mutations could pass on one checkpoint. A
  reservation now belongs to one tool call (`tool_use_id`), is taken in
  PreToolUse (so pre-approved tools are covered too), is consumed on success
  and released by a new PostToolUseFailure hook on failure or interrupt, and
  lapses after `GroundedAgentConfig.checkpoint_reservation_seconds` (#114)
- `templates/SKILL_TEMPLATE_ENHANCED.md` nested a ```` ```markdown ```` block
  containing ```` ```yaml ```` blocks of the same fence length. Per CommonMark
  the outer block closes at the first bare fence, so the document's structure
  from that point on was not what it appeared to be. The outer fence is now four
  backticks. Found by the new link validator, which reported the resulting
  unclosed fence
- `grounded_query` now closes the SDK's generator when a caller breaks out of
  iteration. `async for` does not close its iterator on `break` (PEP 533 was
  deferred), so re-yielding from `sdk_query` without an explicit `aclose`
  deferred the SDK's `finally: await query.close()` — the call that terminates
  the CLI subprocess — to garbage collection, leaving the process alive past
  its consumer
- `test_grounded_query_callable` no longer drives an unbounded billable API
  call. It still exercises the real SDK with no mock and no skip, but stops
  after the first message and runs under a timeout. The timeout bounds the
  query, not total wall time: `wait_for` cancels the task and then awaits
  teardown, so the ceiling is the budget plus SDK cleanup
- `test_grounded_query_callable` can now fail. It previously had no assertion
  and caught `ValueError`, which is raised only when `wrap_options` produces a
  contradictory options object — a wrapper defect that read as an environment
  outcome. It now asserts that either a message arrived or a genuine
  environment error was raised, so a wrapper yielding nothing is a failure
- Trust decay is now a true half-life: `recency_factor` is `0.5 ** (age/half_life)`,
  which returns exactly 0.5 at `age == half_life`. The previous
  `exp(-age/half_life)` treated `half_life` as an exponential time constant and
  decayed 1/ln(2) ≈ 1.44x too fast. `decay_model.half_life` is correspondingly
  set to `P10D`, the value that reproduces the curve the benchmark suite
  actually validated — the former `P14D` was a mislabelled ~9.7-day half-life,
  not a 14-day one (#105)
- Benchmark metrics suffixed `_percent` are no longer scaled a second time by
  the reporter, which printed a +63% accuracy improvement as +6304.3% (#105)
- Documentation and compliance artifacts that asserted a 14-day trust half-life
  now state the value the schema implements (#105)
- Removed an unverified "85%+ GA accuracy" claim from the benchmark README in
  favour of the command that reports the measured figure (#105)
- Corrected NIST AI RMF profile reference to a trust source (`unverified: 0.20`)
  that does not exist in `authority_trust_model.yaml` (#105)
- `decay_model.min_trust` is now enforced: the recency factor is floored rather
  than decaying asymptotically to zero. It was declared in the schema and cited
  by the ISO 42001, EU AI Act and NIST AI RMF artifacts as an implemented
  control, but was read by nothing (#106)
- `tools/sync_skill_schemas.py` is idempotent and self-healing: its comment
  rewrite reapplied itself to already-rewritten text, so each run stacked
  another `(repo-level)` prefix onto the 17 bundled workflow catalogs. CLAUDE.md
  documents the command, so following the project's own instructions corrupted
  those files. The rewrite now strips every existing prefix before re-applying
  exactly one, so a tree a previous run had already doubled is repaired rather
  than left stable-but-corrupt (#107)
- `skills/receive/reference/event_schema.yaml` was an orphan copy that
  `sync_skill_schemas.py` could not reach, because the sync only bundles into
  skills that carry a `reference/workflow_catalog.yaml`. It is now resynced and
  the canonical-schema validator asserts every vendored copy matches its
  source (#107)

## [v1.2.0] — 2026-02-04

The full list is in the
[v1.2.0 release](https://github.com/synaptiai/agent-capability-standard/releases/tag/v1.2.0).

### Added
- `CapabilityRegistry.all_edges()` public method for enumerating ontology edges
- Benchmark drift-prevention validator (`tools/validate_benchmark_deps.py`) and CI job
- Multi-agent coordination runtime with delegate, synchronize, and invoke patterns (#98)
- NIST AI RMF 1.0 profile with tier assessments and maturity roadmap (#59)
- EU AI Act conformity assessment preparation (#58, #97)
- ISO 42001 gap analysis and certification readiness documentation (#96)
- Workflow execution engine (TD-006) (#94)
- OASF GA extension mechanism for unmapped capabilities (TD-010) (#95)
- Comprehensive analysis documentation package (13 documents, ~570KB)
- Perspective validation checklist (PVC) system (#34)
- OASF-to-Grounded-Agency capability mapping file (#32)
- OASF compatibility adapter with full test suite (#33)
- OASF-inspired workflow patterns added to catalog (#31)
- Modality handling guide for vision, audio, and multimodal domains (#30)
- Modality-specific domain profiles for vision, audio, and multi-modal (#28)
- OASF safety extensions proposal (#29)
- OASF coverage report and comparison documentation

### Changed
- Enhanced CLAUDE.md with workflow orchestration guidelines and core principles

### Fixed
- Remediate benchmark suite drift from ontology and SDK (#100)
- Use public `all_edges()` API in benchmark validator instead of private `_loaded_edges` (#100)
- Install real SDK, remove all mock/skip patterns (#99)
- Skills made self-contained with bundled transitive dependencies (#36)

## [v1.1.1] — 2026-01-27

### Changed
- Migrated capability ontology from JSON to YAML format
- Updated capability count references from 35 to 36
- Expanded the FAQ with the rationale for rejected layer proposals

## [v1.1.0] — 2026-01-27

### Added
- Domain-specific workflow templates and default profiles (#12, #17)
- Automated validation for domain profiles (#18, #19)
- Claude Agent SDK integration with safety patterns (#11, #16)
- Benchmark suite for Grounded Agency validation (#10, #15)
- Agent failure taxonomy research (#8, #13)
- Replanning and goal uncertainty capabilities (#9, #14)
- Missing edge types to ontology (#2, #20)
- Reference list of the 99 v1 capabilities (#6, #7)
- Practitioner adoption appendix in Grounded Agency

### Fixed
- Complete edge graph for 5 orphan capabilities (#1, #21)

### Changed
- Migrated from 99 to 36 atomic capabilities with domain parameterization
- Grounded Agency evaluation section reports the 51 steps in the reference
  workflows

## [v1.0.5] — 2026-01-25

### Changed
- Flattened skills directory structure for Claude Code compatibility: skills
  moved from `skills/<category>/<skill>/` to `skills/<skill>/`

### Fixed
- The PostToolUse hook reads its JSON from stdin instead of command-line
  arguments, and its matcher is `Skill` instead of `*`

## [v1.0.4] — 2026-01-25

### Fixed
- Removed the hooks reference from `plugin.json`, which made Claude Code
  report a duplicate hooks file

## [v1.0.3] — 2026-01-25

### Fixed
- Removed the `$schema` key from `plugin.json`, which failed validation
  when the plugin was installed

### Changed
- README installs the plugin from the Synapti marketplace

## [v1.0.2] — 2026-01-25

### Changed
- README shows the Claude Code plugin as the main way to install

## [v1.0.1] — 2026-01-25

### Added
- `docs/GROUNDED_AGENCY.md`: the Grounded Agency paper in Markdown

### Changed
- README, quickstart, tutorial, FAQ, glossary, Grounded Agency, whitepaper
  and Standard 1.0.0 explain why and when to use each feature
- Grounded Agency layer counts corrected and its academic references checked

### Removed
- The LaTeX source and PDF of the Grounded Agency paper, replaced by the
  Markdown version
- `spec/RELEASE_CHECKLIST.md`

## [v1.0.0] — 2026-01-24

### Added
- Initial publication candidate
- Capability ontology with 99 atomic capabilities across 8 layers
- Typed I/O contracts and explicit dependencies for all capabilities
- Workflow DSL spec v2 with bindings, conditions, gates, recovery loops, parallel groups
- Canonical world state and event schemas (provenance, uncertainty, retention, lineage)
- Identity taxonomy and identity resolution policy
- Authority trust model (weights, decay, field-specific authority)
- Compiler-grade validator with $ref resolution, type inference, consumer input schema checking, and patch suggestions
- 5 reference workflows in workflow catalog
- Safety hooks (checkpoint enforcement, audit logging)
- Conformance test suite with 5 fixture tests
