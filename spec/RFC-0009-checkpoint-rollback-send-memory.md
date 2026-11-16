# RFC-0009: Checkpoint, rollback, send and memory

**Status:** Accepted
**Target:** Standard v1.2.0
**Date:** 2026-11-15

## Summary

This RFC defines what a checkpoint holds and what a rollback restores, what
a transmission's checkpoint can and cannot do, how a delegation relates to
the delegator's checkpoints, and what a memory store guarantees. It settles
findings ACS-18, ACS-19, ACS-26, ACS-27, ACS-48 and ACS-52 of the Standard
Agents interoperability review in Standard 1.2.0 (§4.4.1, §4.4.2, §4.5,
§5.15.4) and capability ontology 2.2.0. It was accepted by the maintainer's
instruction that every remaining finding be implemented in 1.2.0, and is
implemented in the same change: the reference validator and executor, the
Python package, the Standard Agents binding, the skills and conformance
fixtures and vectors.

## Motivation

Standard 1.1 required a checkpoint before `mutate`, `send` and `rollback`
without saying what a checkpoint saves. The ontology's `rollback` returns a
required `restored`, which the Standard never mentioned, and a rollback step
that returned `restored: false` completed with no diagnostic. The skills
assumed git and a `.checkpoints/` directory, and the Python tracker stored
metadata and no content.

For `send`, restoring the checkpoint does nothing to data already delivered,
and nothing said so; §12.1 implied the opposite. The reference executor
retried a `send` after R401 with identical inputs under one approval, and the
host had nothing to tell the second attempt from a new transmission. The send
skill told the model to check an allow-list that no schema or setting
defined.

Across a delegation, nothing related the delegator's checkpoints or rollback
to what a delegate changes, so each binding decided alone.

`persist` and `recall` had no storage scope, `ttl` had no grammar (strict
validation accepted "five fortnights"), the two capabilities named the
storage time differently, and nothing said what `stored: true` guarantees.

## Goals

- Define a checkpoint, a rollback, `restored`, and what lies outside a
  rollback's reach, host-neutrally.
- Make a transmission safe where it can be: before it, and at most once per
  approval, with a defined way to report it after a rollback.
- Relate delegation to checkpoints and rollback.
- Give memory a scope, an expiry grammar, and testable guarantees.
- Define a destination policy with one grammar, normative vectors and a
  diagnostic, applied by executors, safety layers and profiles.
- Change no 1.1 workflow's validity or behaviour except by opt-in or a new
  warning.

## Non-goals

- Making `restored: false` or `stored: false` fail a step (a later major may;
  see Open questions).
- A delete operation for memory.
- How a host captures or restores state; the Standard defines the contract
  and the report, the host the mechanism.
- URL-aware destination matching (origins, case-insensitive hosts).
- How a domain profile is selected and applied in general (RFC-0010); this
  RFC defines only `allowed_destinations` and what it puts in force.
- Concurrency of conflicting steps across runs (RFC-0007, ACS-16).

## Key decisions

### 1) A checkpoint is the host's copy of the state within a scope

The `checkpoint` step's `scope` names what to capture in the host's naming;
an executor-requested checkpoint covers what the step may change, as far as
the host can tell. Optional outputs report `mechanism`, `captured`,
`excluded`, `digest` and `expires_at`. Retention (what can be restored) is
separate from validity (what is authorised), so a used checkpoint can still
be restored (§4.4.1).

### 2) `restored` and two lists

`restored: true` asserts that everything the rollback concerns is back;
`unrestored` (reasons `failed`, `conflict`, `discarded`, `not_captured`) is
then empty. An item the rollback's own `scope` names that the checkpoint
never captured is `not_captured`, so asking to restore what was never saved
is not a success. `not_covered` (reasons `transmitted`, `delegated`,
`outside_scope`) lists changes the checkpoint never covered and does not
affect `restored`. The executor's `RolledBack` may carry `not_covered`; an
in-scope failure is an `Error`, and the run ends F503 as in 1.1.

### 3) A rollback step completes; the workflow checks

`restored: false` is not F503: changing that would alter 1.1 runs, and F503
cannot be matched by `on_error`. §12.5 shows the check (a gate or an
escalating failure mode), and W624 reports an unchecked rollback in a
workflow that targets 1.2.

### 4) The record of what happened is outside a rollback's reach

Stores, trace, action records, approvals, evidence, audit records and the
transcript are never restored, nor the host's own records: its audit log,
checkpoint and approval state, idempotency keys and saved runs. A checkpoint
leaves them out even when its scope covers them, so a rollback can neither
erase the tail of an audit log, nor bring back a used checkpoint, nor let a
send go twice. Memory is restored only when a checkpoint captured it.

### 5) A transmission's checkpoint restores the agent's own state

§3.3, §4.4.2 and §12.1 say so; a rollback lists transmissions as
`not_covered`, `transmitted`; a `compensation` in the form of
`TransitionRule.rollback` may be reported, and is performed only by an
explicit step.

### 6) At most one effect per approval: an executor-issued idempotency key

Every `InvokeCapability` carries `idempotency_key` = `<run_id>:<n>`, `n` the
`id` of the pass's first `InvokeCapability`: one key per pass, kept across
retries and restores, new for loops, invoked runs and replacing delegations.
A host MUST NOT transmit twice per key; when unsure, it answers `Error`
reason `outcome_unknown`. Keys are unique because `run_id` is (§5.19.2, a
MUST for a host that keeps records or keys); a host never replays a key
whose capability or inputs differ from the first use (`key_conflict`), and
a host that saves runs keeps its keys as long. A pending action restored
from a version-1 state gets `<run_id>:<id>`.

### 7) Delegation

A run's checkpoints never authorise a delegate's changes, except where a
safety layer orders the delegate's calls in the delegator's scope; before
each change a delegate needs a checkpoint valid in the scope where that
change is checked (its own, or in a shared scope one no other change has
used), and its host may attest it (`effective.checkpointed`); a rollback
restores what its checkpoint captured, whoever changed it, and reaches
nothing else; all-or-nothing needs `read_only: true` or an explicit undo
step (§5.15.4).

### 8) Memory scopes, `ttl`, guarantees

`run` (the run the host started and every run nested in it), `session`,
`user`, `project`, `global` and `x-` names, defined by visibility and
lifetime, echoed in the output and enforced by the executor when a step
of a 1.2 workflow binds a scope (below 1.2, `scope` is W616 and passed on).
`ttl` is a §5.10.1 duration (W614 otherwise). `stored: true`
means read-after-write and an I-JSON round trip; `stored: false` means
nothing changed. Data holding a secret the host recognises is refused
(`secret_in_data`, §6.7). `stored_at` is the shared name; `persist`'s
`timestamp` is deprecated (W603). Hosts state durability, retention and
limits and pass the memory vectors (§4.5).

### 9) Destination policy

Patterns of three forms (exact; `<prefix>*` after a delimiter, with a
complete authority when the prefix holds `//`; `*<suffix>` from `@` or `.`,
preceded only by host-name or local-part characters), normative vectors
including every known bypass, intersection of the policies in force (the
host's at start plus each applied profile's `allowed_destinations`). The
executor fails a disallowed `send` with F504 before approval or checkpoint
whenever a policy is in force; safety layers refuse calls with F504, and
the TypeScript binding applies a layer-wide policy to every `send` tool;
W625 reports a 1.2 `send` whose approval hides a referenced destination;
credentials scoped to allowed origins are recommended.

## Backward compatibility

Every ontology and canonical schema change is an optional field or a
description (§11.4). The executor's behaviour for a 1.1 workflow is unchanged
unless a host opts in by giving destination policies: a 1.1 step that binds
the new `scope` input (a key that was W604 in 1.1) gets W616, and the
executor passes the input on without checking the echo, as 1.1 did. W624 and W625 apply
only to workflows that target 1.2; W626 and the new W614 and W603 cases apply
to all versions and hit nothing in the repository. New host duties
(at-most-once per key and no replay under a reused key, memory guarantees
and the refusal of secrets, a delegate's checkpoint in the scope its change
is checked in, a checkpoint that never captures the host's own records)
are MINOR: they constrain hosts, not workflows. A destination policy
applies only when a host or an applied profile supplies one; the tightened
pattern grammar is new in 1.2, so no existing policy changes meaning. No repository catalog needs
migrating: none targets 1.2. A catalog that moves to 1.2 clears W624 with an
after-gate on each `rollback` step (`when: ${rollback_out.restored} ==
false`, `phase: after`, `action: stop`), and W625 by adding each referenced
destination to its `send` step's `approval.shows`.

## Conformance test updates

- Runtime fixtures (normative for class EX): one key across a retry, a new
  key per loop and per replacing delegation, `outcome_unknown`, destination
  refusals (F504, before approval and checkpoint; policy intersection; a
  profile policy with no host policy; a URL against a suffix pattern;
  `on_error: F504`), rollback steps that do not restore (complete; checked
  by a gate), `RolledBack` with `not_covered` (transmitted, delegated),
  memory scope echo and its absence, no check in a 1.1 workflow, `stored:
  false`.
- Validator fixtures for W624, W625, W626, the W614 `ttl` case and the W603
  `timestamp` case, and their exemptions; and the W616 for `scope` in a 1.1
  workflow, located at its first step.
- `tests/conformance/destinations/match.json` (normative for any destination
  policy) and `tests/conformance/memory/store.json` (normative for a host that
  states it implements §4.5), run by the Rust core, the Python package and
  the TypeScript binding.
- Unit tests for the snapshot store (a rollback leaves the audit log, the
  tracker state, the marker, the idempotency log and saved runs
  byte-identical; secret paths excluded; private modes; `not_captured`),
  the idempotency log (`key_conflict`, durability, the run's own keys), the
  memory store (`secret_in_data`), the Python host's defaults, the
  executor's version-1 restore, the adapter's shared-scope checkpoint and
  destination checks, and the binding's layer-wide destination policy.

## Alternatives considered

- **`restored: false` as F503**, always or for `spec_version: "1.2"`:
  rejected (1.1 runs would change; F503 is not matchable by `on_error`;
  when this was decided, the executor could not rely on a header, which
  RFC-0010 §5a has the start operation pass). **A `require_restored` input**: rejected
  as unnecessary; a gate is the existing mechanism, and W624 makes the
  omission visible.
- **One `unrestored` list with mixed reasons**: rejected; two lists keep
  `restored` ⇔ `unrestored` empty.
- **An author-supplied `send.idempotency_key` input** as the fix: rejected;
  it helps only when bound and a workflow cannot name its run or pass. **A
  key from run, frame and step**: repeats across loops and invocations. **A
  pass counter**: would oblige every executor to count passes alike; the
  first action's `id` is already normative.
- **Automatic compensation on rollback**: rejected; a compensation is a
  transmission needing its own checks.
- **"A delegator's checkpoint never covers a delegate's effects"** as a flat
  rule: false for a subagent in the same working tree; stated instead in
  terms of what the checkpoint captured. **Requiring
  `effective.checkpointed`**: deferred.
- **Scope as a closed enum**: cannot admit `x-` names. An enum with a
  `pattern` for them, which the dialect allows (STANDARD §4.1.2), would be
  the only `pattern` keyword in the ontology's contracts. **Renaming `timestamp`**: breaking; aliased and deprecated.
- **Profiles as the only source of a destination policy**: a host without a
  profile needs one too. **Glob patterns**: `*` anywhere lets
  `https://*.example.com/*` match another host. **Unrestricted suffix and
  prefix forms** (this RFC's first draft): a suffix matched any string
  ending with it (`https://evil.net/?.example.com`,
  `a@evil.net,b@example.com`) and a prefix could stop inside an authority
  (`https://hooks.example.com:*` allowed userinfo to another host); both
  restricted. **A per-tool policy in TypeScript**: a tool defined without it
  escaped; a layer-wide policy instead. **W625 for every version**: would
  hit a contributed 1.1 fixture kept as sent.
- **Recording a git checkpoint with `git update-ref` and counting it as a
  checkpoint**: it names any commit the caller chooses, as `git stash
  store` does, and would use up the marker of the `git stash create` before
  it; the one plain `git stash create`, with `HEAD` on a clean tree, is the
  checkpoint.
- **A reused key answered `outcome_unknown`**: the host knows the key was
  reused, and the remedy differs; `key_conflict`.
- **Keying the `run` memory scope by frame instance**: the protocol does not
  identify frame instances, and a nested run is part of its parent's work.

## Open questions

1. Should a future major release make `restored: false` (and `stored:
   false`) fail the step, retiring W624?
2. Should `send` take an author-supplied idempotency key for
   de-duplication across runs (the same invoice never sent twice by two
   runs)?
3. Should a workflow or profile be able to require
   `effective.checkpointed: true` of a delegation, as quorum's
   `require_read_only` requires `read_only`?
4. Should memory gain a delete operation, or is expiry with retention
   enough?
5. Should destination patterns gain URL-aware matching (scheme and host
   normalisation, ports, internationalised names)? The 1.2 forms are
   deliberately ASCII and fail closed: an internationalised host must be
   written in its ASCII (punycode) form, and an address whose local part
   uses characters outside letters, digits, `.`, `-`, `_` and `+` needs an
   exact pattern.
6. Should the Standard say how a version-control checkpoint is kept for its
   retention (a ref the host pins outside the agent's commands), or is the
   tool's own pruning, reported as `expires_at` when known, enough?
