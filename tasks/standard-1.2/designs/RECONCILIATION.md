# RECONCILIATION — cross-stream pass over the ACS 1.2.0 designs

The seven designs (S1, S2a, S2b, S3, S4, S5, S6) were read against each
other for conflicts and overlaps: two designs changing the same Standard
section, ontology node, schema member, file or behaviour differently; shapes
defined twice; dependencies one design assumes and another does not
provide; and section numbers that collide. Each item below gives the
conflict, the resolution with its reason, and the design files edited so
that they agree. Every edited design now opens with a short "Reconciled"
note naming the items that touched it. `FOUNDATION.md` holds what lands
before the parallel phase. The pre-reconciliation files are kept in
`scratchpad/designs_pre_reconcile/` for diffing.

Totals: **38 items** (C1–C38), every one resolved in the design files;
**15 new diagnostic codes**; no item left for a human decision (the release
choices a maintainer may want to confirm are listed at the end).

---

## Numbering and codes

### C1. Section numbers

**Conflict.** Each design numbered its new sections provisionally. S3 had
given its *Domain Parameter* the number §5.2.3, which S2b uses for
*Parallel Groups*; S4's header still named S3's §5.2.3. S2a and S3 wrote the
host protocol as "§HP" (10 and 5 places). S6's part 2.10b titled §6.4
"Action Records", S2b "Audit Records".

**Resolution.** Final numbers, in document order (FOUNDATION D2): §4.1.1
(S4), §4.1.2 (S6), §4.4.1, §4.4.2, §4.5 (S5), §5.1.1 (S3), §5.2.2 (S1),
§5.2.3 (S2b), §5.2.4 (S3), §5.10.2 (S2b), §5.13.1 (S3), §5.14.1 (S2a),
§5.15.1–§5.15.3 (S3), §5.15.4 (S5), §5.18 (S1), §5.19 (S2b), §5.20 (S4),
§5.21 (S6), §6.4 (S2b, *Audit Records*), §6.5–§6.7 (S4), §8.4 (S2b), §10.4
(S1), §10.5 (S2b), §11.6–§11.7 (S6), Appendix D. No two designs now claim a
number. Each "§HP" is the §5.19 subsection it means (§5.19.1 actions and
responses, §5.19.2 run operations, §5.19.4 saving, §5.19.5 cancelling,
§5.19.7 reasons).
**Edited:** S2a (10 placeholders and the numbering note), S3 (5 and the
header note), S4 (header), S6 (2.10b title).

### C2. Diagnostic codes

**Conflict.** Each design drew codes from a provisional range, so the
numbers had gaps (S1 W617, S2b W623–W624, S3 W627–W630, S5 W637–W639) and
R412 for S2b's only R code while R408–R411 were unused. Designs cited each
other's provisional numbers (S2a R412; S3 W624, W637, W638; S6 W628, W629,
W637, W638).

**Resolution.** 15 new codes, allocated compactly in workstream order,
continuing the existing families. Provisional → final:

| Provisional | Final | Name | Owner |
|---|---|---|---|
| V110 | V110 | DUPLICATE_BINDING | S1 |
| V111 | V111 | TOOL_NAME_MISMATCH | S1 |
| R407 | R407 | SAFETY_CHECK_FAILED | S1 |
| R412 | **R408** | CANCELLED | S2b |
| F506 | F506 | GATED_CONTROL_ACTION | S1 |
| W617 | W617 | UNBOUND_TOOL | S1 |
| W623 | **W618** | UNKNOWN_JOIN | S2b |
| W624 | **W619** | GROUP_MATE_READ | S2b |
| W627 | **W620** | NONCANONICAL_NAME | S3 |
| W628 | **W621** | UNBOUNDED_DELEGATION | S3 |
| W629 | **W622** | UNDECLARED_DELEGATE | S3 |
| W630 | **W623** | CONCURRENT_RUN_CONFLICT | S3 |
| W637 | **W624** | UNCHECKED_ROLLBACK | S5 |
| W638 | **W625** | DESTINATION_NOT_SHOWN | S5 |
| W639 | **W626** | UNKNOWN_MEMORY_SCOPE | S5 |

S2a, S4 and S6 add none (S4 defines the reserved F505). The rewrite was one
simultaneous substitution (so W630 → W623 and W623 → W618 could not
collide), after the "allocated range … unused" sentences of all seven
designs were replaced by a pointer to FOUNDATION part C. Counts after the
pass: S2a 5, S2b 86, S3 129, S5 61 and S6 5 occurrences rewritten; no
provisional number remains in any design.
**Edited:** all seven.

---

## Host protocol and runs

### C3. The `start` operation (§5.19.2)

**Conflict.** Four designs edited S2b's **start** item: S6 replaced it
whole (header always given, profiles), S4 inserted grounding policies into
the old text, S5 inserted destination policies into the old text, and S3
needed catalogs of a set and agent manifests there. Applied in sequence, the
later replacement would have dropped the earlier insertions.

**Resolution.** One merged item, now in S2b's §5.19.2: catalogs (and, for a
set, each further catalog) with their header versions, always given; the
workflow, inputs, attendance, `run_id`, time; optionally actor, record mode,
agent manifests, destination policies, grounding policies (covering nested
runs) and domain profiles; the executor's start refusals (invalid pattern,
unknown capability in a grounding policy, profile errors).
**Edited:** S2b 2.11 (merged text), S5 2.8 and S6 2.10a (marked merged).

### C4. The catalog header at start

**Conflict.** S6 makes the header an explicit, required start value (a
host that loaded a file MUST pass it), and asked S2b to drop its statements
that "a catalog-wide version header is a comment the executor never sees".
S3 gave each catalog of a set an *optional* header and kept an open
question on whether an executor should refuse a catalog whose header it was
not given.

**Resolution.** S6's rule, extended to sets: every catalog the executor is
given carries its header's version or an explicit null, required in the
start operation, the host protocol's `run_options.catalogs[]` and the
fixture format's `catalogs[]`. Reason: S6's fail-open argument (a 1.2-by-
header catalog run under 1.1 rules ignores S2a's approver requirements)
applies to every catalog of a set, since S3's 1.2-only features can sit in
any of them. S3's open question 7 is resolved; S2b's two statements are
corrected (the executor receives the target; the record-mode rationale
stands on the author/operator argument alone).
**Edited:** S3 (§10.3 paragraph, dependency list, OQ7), S2b (ACS-30
rationale and alternatives).

### C5. Error reasons (§5.19.7) and `$defs.reason`

**Conflict.** S2b defined three reason tokens; S5 added seven rows in a
separate edit, S6 two F504 reasons "for S2b's table", S4 left the persist
token open. The schema pattern and the table's closing sentence were each
written three times.

**Resolution.** One table of 12 tokens in S2b's §5.19.7
(`unsupported_capability`, `unsupported_domain`, `not_recorded`,
`outcome_unknown`, `key_conflict`, `destination_not_allowed`,
`unsupported_scope`, `unsupported_ttl`, `over_capacity`, `secret_in_data`,
`below_minimum_confidence`, `invalid_confidence`) and one closing sentence
naming the reasons the executor raises itself (`not_recorded`,
`destination_not_allowed` F504, `unsupported_scope` R402, the two
confidence reasons F504). `$defs.reason` lists the same (FOUNDATION B8).
S4's §6.7 persist refusal names `secret_in_data`. `unsupported_domain`
cites §5.2.4.
**Edited:** S2b 2.11, S5 2.8 (marked merged), S4 §6.7.

### C6. The `retry` row of §5.2

**Conflict.** S2b replaced the row (adding the backoff schedule); S3
replaced its "not after" parenthesis (delegate target refusals, unattested
`read_only`); S3 also expected S4 to extend it for F505.

**Resolution.** One row in S2b's 2.5 with S3's parenthesis. F505 needs no
text: only R401, R402 and R406 are retried.
**Edited:** S2b 2.5, S3 2.6.

### C7. The §10.1 sentence after the table

**Conflict.** S1 and S2b each added a sentence after the conformance-level
table; S2b's supersedes S1's but dropped S1's reason.

**Resolution.** One sentence (FOUNDATION D3): "Levels L1–L4 rank
validators; SL (§10.4) and EX (§10.5) are separate classes: a layer
validates no catalog, a validator checks no call and runs no workflow, and
an implementation claims each level or class it meets."
**Edited:** S1 2.10, S2b 2.17.

### C8. Runtime fixtures in §10.3 and §10.5

**Conflict.** S2b's text made runtime fixtures normative "for the runtime
semantics of §5.6–§5.19 and §6.4" and listed the fixture keys, but S4, S5
and S6 add runtime fixtures for §4.4.1–§4.5, §5.20 and §5.21 and new keys
(`grounding`, `destinations`, `header`, `profiles`), and S3 adds `catalogs`
and `agents`; the fixture schema had `additionalProperties: false`, so
fixtures with the new keys would fail it.

**Resolution.** §10.3's range reads "§4.4–§4.5, §5.2, §5.6–§5.21 and §6.4";
§10.5's fixture paragraph names every key; the "every other member a
fixture pins" list adds §4.4.1, §4.4.2, §4.5, §5.20, §5.21. The fixture
schema gains the six keys, with `header` required (FOUNDATION B9).
**Edited:** S2b 2.17.

### C28. Delivery key and idempotency key

**Conflict.** S2b's §5.19.4 calls (`run_id`, `id`) "the key" under which a
host makes an action idempotent, and §5.19.2 speaks of "idempotency keys
(§5.19.4)"; S5 defines **Idempotency key** in §2 as the pass key
`<run_id>:<n>`, the same for every attempt. Two different things under one
name.

**Resolution.** (`run_id`, `id`) is a **delivery key** (one action, for
re-delivery after a restore); the idempotency key is S5's (one pass, so a
retry does not repeat an effect). Both are kept per run, so §5.19.2's
`run_id` uniqueness covers delivery keys and idempotency keys.
**Edited:** S2b §5.19.2, §5.19.4.

### C33. Required members of the host protocol schema

**Conflict.** S5 makes `InvokeCapability.idempotency_key` required; S2b's
new `tests/test_host_protocol_schema.py` validates every action of every
fixture replay. With S2b merging before S5, the required member would fail
S2b's test until S5's executor emits it.

**Resolution.** In the foundation, a member is declared optional until the
workstream that implements it merges; that workstream adds it to
`required`. So S5 makes `idempotency_key` required, and S2b makes the
head's `run_id` required.
**Edited:** S5 note; FOUNDATION B8.

### C34. Saved state

**Conflict.** S2a and S2b both bump `SNAPSHOT_VERSION` to 2; S3 adds
catalogs and agents to the digest, S5 keys and policies, S6 the header and
profiles, S4 grounding policies — in tracks that merge at different times.

**Resolution.** The version becomes 2 once, in S2b. Every member any track
adds to the saved state is optional with a default that gives 1.1
behaviour, so a state saved on either side of any merge restores.
**Edited:** FOUNDATION F5 (rule); the designs already state the single
bump.

---

## Standard text

### C9. §8.1's confidence row

**Conflict.** S4 replaced §8.1's "Confidence weight" row; S6 replaces §8.1
whole.

**Resolution.** S6's §8.1 already carries S4's wording ("The confidence the
source reports (§4.1.1), from 0 to 1; 1 when it reports none"). S4's edit is
withdrawn.
**Edited:** S4 2.17.

### C10. §6.1's supporting-schemas sentence

**Conflict.** S2b, S3, S4 and S6 each rewrote or extended the one sentence;
S1's schema was mentioned only in S2b's note.

**Resolution.** One sentence written by the foundation (FOUNDATION D3),
listing `review_verdict_schema.yaml`, `agent_identity_schema.yaml` 1.1.0,
`agent_manifest_schema.yaml` 1.0.0, `host_protocol.schema.json` (EX),
`interop/tool_binding.schema.json` (SL), `interop/evidence.schema.json` and
`profiles/profile_schema.yaml`.
**Edited:** none needed in the designs (each says "merge").

### C11. §9 rows that several designs extend

**Conflict.** V101 (S1, S3, S4, S6), V105 (S1, S3), V106 (S2a, S4), V107
(S1, S3), V109 (S1, S3, S6), F501–F504 (S1, S5, S6, S4), W602 (S1, S3, S6),
W603 (S5, S6), W614 (S4, S5), R402 (S1, S2b) were each rewritten by more
than one design, and S4 and S5 both planned the W614 helper ("whichever
lands first adds it").

**Resolution.** One merged row per code (FOUNDATION C3), keeping every case.
`extensions::literal_duration` lands in the foundation, so neither S4 nor
S5 races for it. S4's W614 row now shows the merged text.
**Edited:** S4 2.18; FOUNDATION C3.

### C12. Features new in 1.2 (W616 list, §11.5)

**Conflict.** S6's 1.2 row listed the workflow field `agents`; S3 makes
`agents` S303 in a workflow that does not target 1.2 (so an older consumer
refuses it with V109) and asked S6 to remove it, keeping S6's fixture from
expecting W616 for it. By S6's own criterion ("an input that the executor
itself reads" is a feature), S2b's `audit.require_record` and S5's
`persist`/`recall` `scope` are features, but S2b had said its list needed
none and S5 did not list `scope`.

**Resolution.** The 1.2 row is: approver `sender_check` and
`accept_trust_classes`; `continues`; a qualified invoke target and a catalog
manifest; `grounding@1` and `grounding`; F505 in `on_error`;
`require_record`; `scope`. `agents` is not on it; S3's sentence after the
table says it is S303 outside 1.2 targets. S6's fixture
`warn_version_feature_1_2` uses `continues`. The FEATURES table gains S2b's
and S5's entries.
**Edited:** S6 2.18, its FEATURES contributor list and fixture table; S2b
part 10; S5 part 8.

### C13. `ActionRecord.status` description

**Conflict.** S2a wrote a description that ends "A planned record in the
terminal record of a run that did not end deferred is abandoned and never
carried out."; S2b merged S2a's text with its own `cancelled` and run-record
cases but dropped that sentence.

**Resolution.** The merged description keeps it (FOUNDATION B1).
**Edited:** S2b 3.2, S2a 3.2 (points to the merged text).

### C15. §5.18.10's `audit` row

**Conflict.** S4 asked S1 for two code-decided rows, `persist` and
`audit`, each "holds no secret the layer recognises (§6.7) | F504", and adds
an `audit` Bash hook that refuses with F504. S1 added only the `persist`
row, so by S1's own rule ("a condition a skill's hook adds that this table
does not list is a model-judged or host-specific addition") S4's audit
check would have been optional.

**Resolution.** S1's table gains the `audit` row.
**Edited:** S1 §5.18.10.

### C18. The term "Scope"

**Conflict.** S1 defined **Scope** in §2 as the call sequence a safety layer
orders; S5 uses *scope* for what a checkpoint captures (the ontology's
`checkpoint.scope` input, §4.4.1) and defines **Memory scope**. One bold
term for three things. S1's **Execution boundary** said nothing of S2a's
resumption (a boundary) or of restoring a saved run (which S2b says is not
one).

**Resolution.** S1's term is **Layer scope** ("in §5.18, *scope* means a
layer scope"). An execution boundary is the end of a wait or delay, the
resumption of a deferred run, and a point a safety layer names; restoring a
saved run is not one.
**Edited:** S1 2.3.

### C19. §5.2.2 validity and resumption

**Conflict.** S1's §5.2.2 ended a checkpoint's validity only when a wait or
delay ends; S2a's §5.14.1 invalidates every checkpoint taken before a
resumption, and S5 relies on that.

**Resolution.** §5.2.2: "…when a wait or delay ends (§5.13) or its run is
resumed (§5.14.1) … Saving and restoring a run (§5.19.4) changes nothing."
**Edited:** S1 2.6.

### C24. Order of the executor's checks in a step

**Conflict.** S5 checks a `send` destination once inputs are resolved,
before approval and checkpoint use; S3 put its delegate target and task
refusals in `execute()`, after approval, so a person could be asked to
approve a delegation the executor then refuses, and S1's §5.2.2 would have
the step use its checkpoint first. The output-side order was agreed only
pairwise (S4–S6).

**Resolution.** Before the call: condition, before-gates, delay or wait,
then the executor's refusals that need no host answer (S3's delegate target
and task checks, S5's destination check), then approval (S2a, with S6's
person requirement), then checkpoint use (S1), then `InvokeCapability`
(S5's key). After the output: R402 checks (required fields, S3's delegate
output checks, S5's scope echo), then grounding (S4, F505), then minimum
confidence (S6, F504), then after-gates. A refused delegation is never put
to an approver and uses no checkpoint.
**Edited:** S3 §5.15.2 (new **When** bullet) and its `machine.rs` plan.

### C29. Counting approvers of a call

**Conflict.** S1's §5.18.7 counts "distinct approvers, as the host
authenticated them"; S2a counts by principal when identities are attested
and records `approval.approver_identities` for tool calls too.

**Resolution.** S1's text adds S2a's rule.
**Edited:** S1 §5.18.7.

### C30. Location keys in §9.8

**Conflict.** S2b and S5 each appended a one-line sentence on their
warning's `location` (`ref`, `mate`), while S3 replaces §9.8 with a full
table that already defines `ref` and `mate`.

**Resolution.** S3's table only; the two sentences are dropped. S1's
paragraph on refusals stays after the table.
**Edited:** S2b 2.16, S5 2.10.

### C38. Protocol traffic on a tool-calling host

**Conflict.** S2b's §5.19.6 says protocol traffic is not a `send`, and
asked S1's §5.18.3 to classify a tool that only carries it accordingly; S1's
table classified "any request to another system whose effect the binding
does not know" as `send`.

**Resolution.** §5.18.3 gains a row: a call that carries only the values of
an executor's host-protocol action to the party that performs or decides
it is protocol traffic, covered by the step whose action it performs.
**Edited:** S1 §5.18.3.

---

## Records, schemas and shapes

### C14. The layer's identity in records

**Conflict.** S1 puts `layer: {name, version, config_sha256, settings}` on
plugin audit lines and `layer: {name, version, config}` on adapter and
TypeScript records; S2b makes the plugin line an `ActionRecord` with
`recorded_by: {name, version, config_sha256}` ("S1's layer object,
renamed"), which drops S1's `settings`, the part ACS-55's review asked for.

**Resolution.** `ActionRecord.recorded_by` gains an optional `settings`
object. Every record a layer writes (plugin line, adapter call records,
TypeScript trace entries) carries `recorded_by` with `config_sha256` (not
`config`) and, where the settings are few, `settings`. The plugin line is
S2b's `ActionRecord` line; S1's `skill` and `input_sha256` sit under
`details`.
**Edited:** S1 (ACS-55 decision, §5.18.8, 5.2 adapter state, 5.5 hooks,
tests, docs, part 8 row, part 10), S2b 3.2 and 5.14.

### C20. Rendering the contracts (JSON Schema and skill-local schemas)

**Conflict.** S4 rendered its `$ref` slots as `{"$ref": "#/$defs/Anchor"}`
in `capability_contracts.schema.json` and added an `inline_refs` helper to
`tools/sync_skill_schemas.py`; S6 rewrites both generators to render from
the core's resolved contracts (`_core.Validator.contracts()`), with no
`$ref` left. Both changed the same functions differently.

**Resolution.** S6's approach. Reasons: the rendering rules are S6's
normative §4.1.2; resolved contracts are what every consumer validates
against, so the rendering cannot drift from the core; S6's rules already
cover S4's slots (pattern carried, `nullable` as a type list). S4 keeps only
the vendored-ontology `$ref` rewrite. Because the ontology's new `$ref`s
need them, `contracts()`, both generators and that rewrite land in the
foundation with the ontology.
**Edited:** S4 5.4.

### C25. The tool binding record's citation and destination

**Conflict.** S6's §11.6 says a tool binding record cites `standard` and
`ontology` (each `MAJOR.MINOR[.PATCH]`); S1's schema had only `ontology`,
with a three-part pattern. S5's `destination` member was a delta to S1's
file that S1's text did not show.

**Resolution.** S1's schema gains an optional `standard`, the two-or-three
part pattern for both, and S5's `destination` (refused together with
`control`), so the schema has one text.
**Edited:** S1 3.3.

### C26. Record anchors for `send`

**Conflict.** S4's skill docs ground a `send` output with
`sent:<message id>`; S5's `send` output defines no message id.

**Resolution.** `sent:<the pass's idempotency_key>` (S5's key, carried by
every `InvokeCapability`).
**Edited:** S4 7.

### C27. One canonical-JSON function

**Conflict.** S1 adds `_core.canonical_json` and `_core.approval_digest`;
S4 used "`_core.approval_digest` or a `_core.canonical_digest`" for
evidence digests; S5 used `_core.canonical_json`.

**Resolution.** The two S1 functions only, landed by the foundation; any
other digest is `sha256(_core.canonical_json(value))`. No
`_core.canonical_digest`.
**Edited:** S4 5.2 and part 10.

### C32. The ontology change classification

**Conflict.** S6's §11.6 table of 2.2.0 changes, which the foundation must
check, missed S5's `delegate.effective.checkpointed` and S3's
`conflicts_with` edge-type text.

**Resolution.** Two rows added (MINOR; PATCH). Every 2.2.0 change remains
MINOR or PATCH.
**Edited:** S6 3.1.

### C36. The approval digest vectors

**Conflict.** S2a restructures `tests/conformance/approval/digests.json`
(a `kind` per vector) and regenerates "the binding copy"; S1 adds
`tool_call` vectors to the same generator function; S6 deletes the binding
copy and has the package's tests read the canonical file.

**Resolution.** S6's deletion; the `kind` member and the generator's
branching land in the foundation; S1 and S2a each add their vectors.
**Edited:** S2a 5.10; FOUNDATION B15, F3.

---

## Code, packaging and process

### C16. How the rollback skill restores a git checkpoint

**Conflict.** S1 (part 10, in its changed git shape) said the rollback
skill restores a stash checkpoint with `git stash apply <sha>`, classified
`rollback`; S5 verified that `git stash apply` aborts once a file it touches
has changed (the usual case for a rollback) and restores with `git restore
--source=<sha> …`, a gated `mutate`. S1's rollback prompt-hook text named
only the `rollback` path (F503).

**Resolution.** S5's restore. S1's classifier keeps `git stash apply <sha>`
as `rollback` (valid on an unchanged tree), and the rollback skill's hook
text names both paths: `git stash apply` (`rollback`, F503) and the skill's
`git restore` line (`mutate`: a fresh checkpoint, F501, and approval, F502).
**Edited:** S1 5.6 and part 10.

### C17. Read-only commands

**Conflict.** S1 makes the plugin's read-only shell list a subset of the
mapper's `_READ_ONLY_COMMANDS` and so dropped `git rev-parse` (not on the
mapper's list); S5's checkpoint and rollback skills rely on `git rev-parse
HEAD` and `git ls-files` being read-only on S1's list.

**Resolution.** The mapper's list gains `git rev-parse` and `git ls-files`
(neither has an option that writes; `--output` stays refused on every git
form), and the plugin's list keeps both. The subset test holds.
**Edited:** S1 5.2 and 5.5.

### C21. Where TypeScript lives

**Conflict.** S6 moves the binding's ontology table, flags and canonical
JSON into a new package `packages/acs-core/` and deletes the binding's
copies, and asked that S1's host-neutral modules live there; S1 edited the
binding's `ontology.ts` and `ontology.gen.ts` (multi-capability flags) and
put `binding.ts` and `output.ts` in the binding; S4 edited `ontology.ts` and
put `redact.ts` in the binding; S5 put its matcher in the package. Run in
parallel, the move and the edits would conflict as rename/modify pairs. S1
and S4 also copied conformance files into the binding's `test/fixtures/`,
while S6 removes such copies.

**Resolution.** The foundation creates the package and moves the files
(FOUNDATION F3). Host-neutral modules go in the package (S1 `binding.ts`,
`output.ts`, the flag functions; S4 `redact.ts`, the grounding part of
`evidence.ts`, `FieldTypes`; S5 `destinations.ts`, `duration.ts`); code
that reads Standard Agents state stays in the binding. Tests read
`tests/conformance/` in place; no copies.
**Edited:** S1 5.3, 5.4; S4 5.3; S6 5.4 and part 1 (ACS-42).

### C22. Profiles and destination policies in TypeScript

**Conflict.** S6 (revision 2) checks and applies profiles only through the
core's WebAssembly interface and keeps the plain-TypeScript entry to the
ontology, flags and canonical JSON; S5's `destinations.ts` lives in that
entry and claimed "S6's `checkProfiles` uses `checkPattern`", and S5's
`LayerConfig.profiles` took `Profile` values from a TypeScript
`checkProfiles` that no longer exists.

**Resolution.** The plain entry also holds the host-neutral modules of C21
(none loads a profile). `checkPattern` serves `configureLayer` and every
`send` call with no WebAssembly; profile patterns are checked by the core
(Rust `destination::Policy::parse`), both held to `match.json`.
`LayerConfig` takes `profilePolicy`, the result of
`CoreContext.profilePolicy(profiles)`, and reads its `destinations`.
**Edited:** S5 5.3, its layer test text and part 10; S6 5.4.

### C23. Shared code spine moved to the foundation

**Conflict.** Several tracks running in parallel would each need code
another track owns: S6's version helpers (`target`, `check_cited`, the
generalised W616) are used by S2a, S3, S4, S5; S3's `Flags` by S6; S5's
`destination.rs` by S6's profile loader; S4's grounding `Policy` and kind
grammar by S6; S4's redactors by S5; S2b's reason plumbing by S5 and S6;
S2a's `read_json` by S6; S1's `_core.canonical_json` by S2a, S4, S5; S2b's
`refs::executable_roots` by S5; the duration helper by S4 and S5; the
start options and validator options by everyone; the fixture generator by
six tracks; and S3 and S6 named the cited-version parser differently
(`names::parse_cited`, `semantics::check_cited`).

**Resolution.** Each lands in the foundation as a shape or a pure function
with its vectors (FOUNDATION F1, 16 items), specified by the owning design,
which fills in behaviour later. The parser is `semantics::parse_version` +
`semantics::check_cited`. The runtime fixture generator is split into one
registration module per workstream.
**Edited:** every design's "Reconciled" note; FOUNDATION F1.

### C31. The plugin's version

**Conflict.** S1 recorded its plugin behaviour change as "plugin minor
release"; S6 makes the release a MAJOR, 3.0.0, for two renamed
user-invocable skills.

**Resolution.** One release, 3.0.0; S1's change rides on it.
**Edited:** S1 part 8.

### C35. Merge order and integration points

**Conflict.** Each design assumed some others' code was present (C23 covers
the shapes); the remaining dependencies are behavioural and pairwise
circular in places (S4 expected S6 to add profile policies to its grounding
check, S6 expected S4's check to exist; S3 and S5 both insert at the
executor's pre-call point).

**Resolution.** Merge order S1 → S2a → S2b → S4 → S6 → S3 → S5
(FOUNDATION F5), and the workstream that merges second wires each
integration point: S6 adds profile grounding policies to S4's check and
`person_required` to S2a's request path and S2b's records; S3 places its
refusals at the pre-call point; S5 adds profile destinations, its check
beside S3's, and `details.not_covered` to S2b's rollback records. Shared
files have a primary owner and named regions (FOUNDATION F4); generated
files are regenerated, never hand-merged.
**Edited:** every design's "Reconciled" note.

### C37. RFC-0002

**Conflict.** `spec/ROADMAP.md` lists RFC-0002 (cross-session agent
reliability, Draft, target 1.2.0) as a draft proposal for 1.2.0, but no
workstream implements it and the 1.2.0 header names RFC-0005 to RFC-0010.

**Resolution.** RFC-0002 stays Draft and is not part of 1.2.0; ROADMAP moves
it to a later 1.x (FOUNDATION E1). It is not one of the ACS findings this
round covers.
**Edited:** FOUNDATION E1.

---

## Overlaps checked and found consistent

- §5.14: S2a replaces it; S3's exception for a `delegate` step with
  `agents` and S6's profile-required person are clauses to S2a's text; S4's
  rule that the digest is over the unredacted values sits in §6.7 and agrees.
- §5.17: S2a's approver paragraphs and S3's `model_id` edits touch
  different sentences.
- §5.9: S2a's `identity@1` row, S4's `grounding@1` row and closing sentence,
  S3's sentence after the table.
- §6.3: S4's row and paragraph, S2a's last paragraph, S2b's appended
  sentence.
- §12.1: S5 replaces the tree and table; S1's note after the table still
  applies.
- §4.4.1 (S5) and §5.2.2 (S1): validity vs retention, gate rollback of the
  latest checkpoint vs a step's named checkpoint, the host-taken checkpoint.
- §5.15.2 (S3) and §5.15.4 (S5): a delegate step consumes the delegator's
  checkpoint; the delegate's own changes need their own.
- §5.18.5 (S1) and §5.15.4 (S5): the Python adapter is one scope for its
  subagents.
- The git checkpoint form: S1 and S5 agree on one plain `git stash create`
  call; neither counts `store` or `update-ref`.
- Ontology: the `audit` node (S2b + S4), `delegate` (S3 + S5 + S4), the
  five nodes S5 replaces (+ S4 templates) merge without overlap; the merged
  file loads and changes no diagnostic of the repository's 89 catalogs.
- `workflow_catalog.schema.json`: five designs, eleven distinct members
  (FOUNDATION B7).
- `world_state_schema.yaml` 1.2.0: six designs, one bump (FOUNDATION B1).
- Evidence records reuse `ActionRecord`'s correlation names (S4, S2b).
- Profile grounding and destination policies are lists of the same shapes
  the host gives (S4, S5, S6).

## For a maintainer to confirm (no decision is left open)

Decided here, with the reason, and worth a glance before release:

- The plugin release is **3.0.0** (S6: two slash commands renamed), not a
  minor.
- The Python package goes to **0.2.0** (breaking SDK changes under 0.x).
- **RFC-0002** is not part of 1.2.0.
- Publishing `@synaptiai/acs-core` to npm needs the repository variable
  `NPM_PUBLISH_ENABLED` and the secret `NPM_TOKEN` (S6); without them the
  publish job ends with a dry run.

The open questions in each design's RFC are for later versions and block
nothing in 1.2.0.
