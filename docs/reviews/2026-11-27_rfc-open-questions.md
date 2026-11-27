# Open RFC questions: proposed dispositions

This table proposes a disposition for each of the 57 open questions that
issue #151 lists, from RFC-0001 to RFC-0010. Every disposition is a
proposal. The maintainer decides each one, and may approve the table in one
pass and override single rows. No RFC is marked as answered until the
maintainer has approved the table.

The table was checked against `main` at commit 18c38b74 (2026-11-27). Issue
numbers refer to issues in this repository. Their state was read the same
day.

## What a disposition says

| Disposition | Meaning |
|-------------|---------|
| **1.3.0, *name*** | Standard 1.3.0 carries it, in a new RFC under that working name (listed below). The change is backward compatible. |
| **2.0.0** | The next MAJOR version carries it, because it would refuse workflows, records or profiles that 1.2.0 accepts. |
| **Issue #N** | An existing issue in this repository tracks it. |
| **New issue** | It concerns this repository rather than the Standard, and needs an issue of its own. |
| **RFC-0002** | RFC-0002 is still a Draft; it settles the question when it goes forward. |
| **Declined** | No change is planned, for the reason given. A new RFC can raise it again. |

Proposed RFCs for Standard 1.3.0, by working name:

| Working name | Rows |
|--------------|------|
| Runs and triggers | RFC-0006 A1, B4, B6, B8; RFC-0007 Q6 |
| Audit records | RFC-0006 B7, B9 |
| Checkpoint and send | RFC-0005 Q5; RFC-0009 Q2 |
| Delegation and inquiry | RFC-0007 Q3; RFC-0008 Q6; RFC-0009 Q3; RFC-0004 Q2 |
| Evidence and grounding | RFC-0008 Q4; RFC-0010 Q2 |
| Taint marking (#169) | RFC-0008 Q1 |
| Retention (#173) | RFC-0008 Q2; RFC-0009 Q4, Q6 |

The maintainer's decisions of 2026-11-27 already place taint marking (#169)
and retention (#173) in Standard 1.3.0, so those rows join RFCs that are
planned anyway.

## RFC-0005: tool-calling hosts

| Q | Question | Proposed disposition | Reason |
|---|----------|----------------------|--------|
| 1 | Propose upstream a hook that can refuse a Standard Agents tool call before it runs | **Issue #139** | This is a proposal to the Standard Agent Specification, not a change to this Standard. Upstream text 01 drafts it, and #139 files it. |
| 2 | Publish a registry of conformance statements, and require one for an SL claim | **Declined** | Both statements that exist ship in this repository beside the fixtures, so a registry would list only them. Raise it again with #84 (certification) when a third party claims class SL. |
| 3 | Whether the plugin's hooks claim SL once Claude Code offers a fail-closed hook mode | **Issue #144** | The hooks set `onFailure: "block"` on main, and `spec/SECURITY.md` §5.5 lists the host gaps that remain. #144 closes or accepts each gap, and whether the hooks claim SL follows from that. |
| 4 | Ask Claude Code to state, per permission mode, whether a hook's `ask` reaches a person (implementation) | **Issue #144** | #144 lists it as a gap of the SDK adapter: that an `ask` reaches the permission callback in modes `default`, `acceptEdits` and `plan` rests on Claude Code's documentation. Closing it means a request to Claude Code, which needs the maintainer's go-ahead to file in Claude Code's repository. |
| 5 | A digest of what a checkpoint captured, so a layer can check it against the scope | **1.3.0, Checkpoint and send** | An optional output member is backward compatible. A layer that checks the digest before it counts the call is new behaviour, so it needs Standard text. |
| 6 | One checkpoint scope per session in the Python adapter (implementation) | **New issue** | It changes only the Python adapter. No issue tracks it. |

## RFC-0006: host protocol, approval and runs

| Q | Question | Proposed disposition | Reason |
|---|----------|----------------------|--------|
| A1 | A queue expiry for a queued action whose run is not resumed | **1.3.0, Runs and triggers** | An optional bound that a workflow or host sets is backward compatible. Without one, a queued action can wait without limit. |
| A2 | Naming the actor on restore as a MUST in the next major | **2.0.0** | It would refuse a restore record that 1.2.0 accepts. #162 adds an actor rule for overrides, not for restores, so it does not answer this. |
| A3 | Whether an identity without `authenticated_by` counts for a `human` approver when no `sender_check` is set | **2.0.0** | Counting such an identity no longer would refuse approvals that 1.2.0 accepts. Until then, a workflow that needs it sets `sender_check`. |
| A4 | Refreshing the inputs of a nested run a resumption continues, such as a checkpoint id | **Declined** | Rewriting an input changes what the calling workflow bound. Taking the checkpoint inside the workflow that mutates, as RFC-0006 advises, avoids the stale id. |
| A5 | A runtime fixture form for a refused response | **New issue** | It is a new form in the runtime fixture schema, which this repository keeps. It changes no requirement on an executor. |
| B1 | Concurrent dispatch: several pending actions with a join, `any_complete`, and withdrawing a running member's action | **Declined** | No open issue in this repository asks for it, and it changes the host protocol's model of one pending action per run. A new RFC can raise it again when a host needs it. |
| B2 | `actions` as the default record mode in the next major | **2.0.0** | Changing a default changes what 1.2.0 workflows record. |
| B3 | `require_record` true by default in the next major | **2.0.0** | An audit that did not record would fail where 1.2.0 lets it pass. |
| B4 | Failure modes that match an error `reason` | **1.3.0, Runs and triggers** | An optional match key is backward compatible. The question's example is falling back to another domain on `unsupported_domain`. |
| B5 | A host conformance class with fixtures for trigger evaluation and the save-and-act order, once a second host binding exists | **New issue** | The class waits on its stated condition, a second host binding. An issue keeps the condition and the fixtures it would need in one place. RFC-0007 Q4 joins it. |
| B6 | A schedule's own `every` anchor, or a host policy for missed fire times | **1.3.0, Runs and triggers** | Both are optional members. The trigger vectors would gain cases for them. |
| B7 | One serialisation (RFC 8785) for the MAC of the audit-record chain | **1.3.0, Audit records** | 1.3.0 can let a store declare that it uses RFC 8785, so any reader can verify that store's chain with the key. Requiring it of every store would be a 2.0.0 change. |
| B8 | How long a host must remember the `event_id`s that started runs | **1.3.0, Runs and triggers** | A stated minimum window, measured from the event's `timestamp`, bounds what a host must keep. Only events older than the window could start a second run. |
| B9 | The chain heads of the host's records in the run record | **1.3.0, Audit records** | An optional member of the run record is backward compatible. It lets an auditor holding only the archive check the records. #143, which exports the plugin log's head to a witness, is related. |

## RFC-0007: delegation, catalogs and diagnostics

| Q | Question | Proposed disposition | Reason |
|---|----------|----------------------|--------|
| 1 | Catalog manifests that declare the catalogs they depend on, with version ranges, and how a host resolves them | **Issue #79** | The domain profile marketplace is the use that needs it, and its design will say how dependencies resolve. The roadmap already ties #79 to this question. |
| 2 | W621 and W622 as errors in a later major, and publishing a host's agent manifests for validators | **2.0.0** | Turning the warnings into errors is breaking. Publishing manifests is a separate question: no reference host publishes its agent manifests, and that part can come back as its own RFC. |
| 3 | More `answer_type` values, or a JSON Schema for a question's answer | **1.3.0, Delegation and inquiry** | New answer types and an optional answer schema are backward compatible. |
| 4 | Cross-run serialisation of `rollback` against `mutate` and `persist` as a MUST of a host class | **New issue** (with RFC-0006 B5) | It is a requirement of the host conformance class that RFC-0006 B5 asks for, so the two belong together. |
| 5 | The step `domain` grammar as S303 in Standard 2.0, and a domain registry | **2.0.0** | Refusing a step `domain` that 1.2.0 reports as warning W620 is breaking. The registry is declined: domains are open by design, and a registry would need an owner and a process this project does not have. |
| 6 | An `overlap` policy for event triggers, so that W623 covers their runs | **1.3.0, Runs and triggers** | Schedules already have an `overlap` policy. Giving event triggers the same optional member is backward compatible. |
| 8 | The model family rule for a provider line whose identifiers do not start with its name, and for a tag that starts with a letter and holds a digit | **Declined** | The model family vectors hold no case of either form; the question's `acme:v1.6` is an example, not a vector. Changing the rule could change the families that existing vectors compute. A new RFC can raise it with a real provider line that the rule groups wrongly. |

## RFC-0008: evidence, grounding and secrets

| Q | Question | Proposed disposition | Reason |
|---|----------|----------------------|--------|
| 1 | Workflow inputs marked `secret`, kept out of traces, records and snapshots | **1.3.0, Taint marking (#169)** | Both mark a workflow input and change how the executor carries it, so one RFC can define the marks together. |
| 2 | A keyword for indefinite `audit.retention` | **1.3.0, Retention (#173)** | The retention member that #173 adds in 1.3.0 is where a "keep until removed" value belongs. |
| 3 | A machine-readable statement of how a host's confidences are calibrated | **Issue #78** | A statement needs a calibration method to describe, and trust calibration tooling (#78) is where one would come from. |
| 4 | Anchors that name the output field they support | **1.3.0, Evidence and grounding** | An optional `field` on an anchor is backward compatible. The grounding check would then read it for outputs that mix grounded and inferred parts. |
| 5 | `evidence_anchors` with `minItems: 1` in 2.0 for capabilities whose outputs are always about external evidence | **2.0.0** | It would refuse outputs that 1.2.0 accepts. It goes with the removal of the legacy anchor forms, which is also a 2.0.0 change. |
| 6 | Checking a waiting `delegate`'s result against the delegate's own anchors | **1.3.0, Delegation and inquiry** | A policy that requires `delegate` covers only delegations that do not wait. Extending the check to waiting ones fits with the other delegation changes. |
| 7 | The plugin's `PreToolUse` hook refusing a write to `.claude/audit/records.jsonl` that does not carry the record as a literal (implementation) | **New issue** | It changes only the plugin's hook. #181 protects the layer's own records with deny rules, but the audit skill must still append to this file, so a deny rule cannot replace the check. |

## RFC-0009: checkpoint, rollback, send and memory

| Q | Question | Proposed disposition | Reason |
|---|----------|----------------------|--------|
| 1 | `restored: false` and `stored: false` failing the step in a future major, retiring W624 | **2.0.0** | It would fail steps that 1.2.0 lets succeed with a warning. |
| 2 | An author-supplied idempotency key for `send` across runs | **1.3.0, Checkpoint and send** | An optional input is backward compatible. Today the key is per pass, so two runs can send the same invoice. |
| 3 | Requiring `effective.checkpointed: true` of a delegation | **1.3.0, Delegation and inquiry** | It is an opt-in requirement, as quorum's `require_read_only` is, so it is backward compatible. |
| 4 | A memory delete operation | **1.3.0, Retention (#173)** | A request to erase personal data is a retention question, and expiry alone cannot serve it. It belongs with the retention member. |
| 5 | URL-aware destination patterns: scheme and host normalisation, ports, internationalised names | **Declined** | The 1.2.0 patterns are ASCII and fail closed: a host the pattern does not name exactly is refused. URL normalisation is where matching mistakes come from. A new RFC can raise it with a host that cannot write its destinations in the 1.2.0 forms. |
| 6 | How a version-control checkpoint is kept for its retention | **1.3.0, Retention (#173)**, after **issue #166** | #166 documents the plugin's restore window first and then adds a ref that expires with the retention. The Standard text follows in the retention RFC. |

## RFC-0010: profiles, trust, versioning and dialect

| Q | Question | Proposed disposition | Reason |
|---|----------|----------------------|--------|
| 1 | Dropping the deprecated profile threshold `critical`, and an unknown top-level profile member as an error, in 2.0 | **2.0.0** | Both refuse profiles that 1.2.0 loads with a warning. Deprecated features stay until the next MAJOR. |
| 2 | A domain profile carrying its own grounding `attested` flag | **1.3.0, Evidence and grounding** | An optional profile member is backward compatible. Today every profile keeps the default. |
| 3 | The repository's reference catalogs on a 1.2 header (implementation) | **Issue #155**, and a **new issue** for the domain catalogs | #155 moves `schemas/workflow_catalog.yaml`. The four catalogs under `schemas/workflows/` still declare 1.1.0 on main and need their own migration. |
| 4 | The skills' `allowed-tools`, written comma-separated and naming `Git` and `Web`, which are not Claude Code tool names (implementation) | **New issue** | On main, all 42 skills write the list comma-separated, and 8 of them name `Git` or `Web`. Correcting the names changes what those skills may run, so it needs its own review. |
| 5 | Trust arithmetic and entity ids in the TypeScript package (implementation) | **New issue** | #83 covers SDKs in other languages in general, and the release plan closes it with release 3.0.0, so this needs an issue of its own. The merge and split checks of RFC-0012 would go with entity ids. |
| 6 | A plain-TypeScript profile loader, held to the same vectors (implementation) | **Declined** | The TypeScript package applies profiles through the WebAssembly core, so there is one loader. The question's condition, a TypeScript layer without WebAssembly, does not hold. |
| 7 | Recursive types in the schema dialect, and `nullable` in §5.4 | **Declined** | An ontology whose contracts hold a `$ref` cycle is refused when it loads, so no capability uses a recursive type today. A new RFC can raise it with a capability that needs one. |

## RFC-0002: cross-session agent reliability (Draft, #104)

RFC-0002 is a Draft, so its questions are part of its own design. Each row
states the answer the RFC could take when it goes forward. RFC-0002 and
issue #151 name #104 as its tracking issue, but #104 could not be read on
2026-11-27: it resolves to no issue, pull request or discussion of this
repository.

| Q | Question | Proposed disposition | Suggested answer |
|---|----------|----------------------|------------------|
| 1 | Whether the Standard defines a session, or expresses windows in observations and durations it already has | **RFC-0002** | Express windows as durations over observations. A session would be a new concept that every host would have to agree on. |
| 2 | Which relation joins a claim to the action it informed | **RFC-0002** | An action record's `anchors` cite the `claim_id` of the provenance record it relied on. Both fields exist. |
| 3 | Which `ActionRecord.status` values constitute delivery | **RFC-0002** | `executed` counts as delivered. `planned` and `approved` are excluded as not final. `rolled_back` is counted on its own, neither as a failure nor as a delivery. |
| 4 | Where the prohibition on joining `ProvenanceRecord.agent` to `ActionRecord.actor` lives; partly answered by RFC-0004 (§5.17), with no fixture yet | **RFC-0002** | The rule stays in §5.17. A fixture needs a world-state fixture form, which RFC-0002 defines if it needs the rule. |
| 5 | `adaptation_score` as a reserved optional field, or omitted | **RFC-0002** | Omit it until the telemetry to compute it exists. |
| 6 | Regression detection as a Standard field or a deployment alert | **RFC-0002** | A deployment alert. The Standard gives the scores, and a deployment chooses how to watch them. |

## RFC-0001, RFC-0003 and RFC-0004

| RFC | Question | Proposed disposition | Reason |
|-----|----------|----------------------|--------|
| RFC-0001 | Standardising a multi-agent coordination protocol, and canonical adapters for common toolchains | **Declined** (both) | Coordination: RFC-0003, RFC-0004, RFC-0006 and RFC-0007 define delegation, identity, synchronisation and the host protocol. A wire protocol between agents belongs to host specifications. Adapters: the Python SDK adapter and the Standard Agents binding are the reference adapters, and further adapters are implementations rather than Standard text. |
| RFC-0003 | Host or device placement of a delegated step | **Declined** | Deployment stays outside the Standard, as RFC-0003 itself concludes: a placement hint would mean nothing to the validator or the executor. A new RFC can raise it with a host that can act on one. |
| RFC-0004 | Whether a future MAJOR replaces `ActionRecord.actor` and `ProvenanceRecord.agent` with identities outright | **2.0.0** | Removing the string fields is breaking. The identity fields already sit beside them. |
| RFC-0004 | Whether a delegation is refused up front when the assignee's attested `trust_class` is not acceptable | **1.3.0, Delegation and inquiry** | An opt-in list of acceptable trust classes for the assignee is backward compatible. Today the check runs only on the delegate's events. |

## Count by disposition

Each row counts once, under the first disposition it names. RFC-0010 Q3
also needs a new issue, and RFC-0009 Q6 waits on issue #166.

| Disposition | Rows |
|-------------|------|
| 1.3.0 (a new RFC) | 19 |
| 2.0.0 | 10 |
| An existing issue | 6 |
| A new issue | 7 |
| RFC-0002 | 6 |
| Declined | 9 |
| **Total** | **57** |

## After approval

Once the maintainer approves the table, with any overrides:

- Each RFC's "Open questions" section marks its rows with the decision,
  as RFC-0007 marks question 7 "(Resolved.)".
- The new issues are filed in this repository, and the rows that name an
  existing issue link to it from the RFC.
- `tasks/todo.md` records the decisions in its list of open work.
