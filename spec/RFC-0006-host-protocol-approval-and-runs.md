# RFC-0006: Host protocol, approval and runs
**Status:** Accepted
**Target:** Standard v1.2.0
**Date:** 2026-11-15

## Summary

Standard 1.1.0 places duties on "the host" in several sections but never
defines the protocol between an executor and its host: the actions, the
responses and the run operations existed only as the reference executor's
Rust types and a guide. This RFC brings that protocol into the Standard and
settles what depends on it.

Part A (approval, deferral and run identity) settles what an approval request
is and how a deferred action is carried out. It states the request for a step
without an `approval` field, the exact input and form of the approval digest,
the number rule and the meaning of `in_session` and `out_of_band` in §5.14;
lets a host attest who approved, with `identity@1`, and lets a workflow that
targets 1.2 require authenticated approvers (§5.17); defines resumption of a
run that ended `deferred`, including which steps run again so that nothing
runs against stale results, and what becomes of the queued actions of runs
that cannot be resumed (new §5.14.1); and states that a run keeps its actor
while it continues, that a host cancels it at a handoff, and that only a
resumption may change it (§5.17). It answers findings ACS-10, ACS-11, ACS-12,
ACS-13, ACS-35 and ACS-44.

Part B (host protocol, runs and audit records) adds §5.19 Host Protocol, with
a schema for every action and response (`schemas/host_protocol.schema.json`),
the time rules, the host's obligations for saving and continuing a run,
cancellation (R408), protocol traffic, error reasons and the run record every
host keeps; a conformance class EX for executors, for which the runtime
fixtures become normative once every member they pin is stated in the text;
§5.10.2, which assigns trigger evaluation to the host and defines event
acceptance, fire times, the `every` anchor and `overlap`; §5.2.3, the run-time
meaning of `parallel_group` and `join`; §6.4, the canonical audit record, with
the executor's record mode `actions`; and §8.4, manual trust overrides. It
answers findings ACS-14, ACS-15, ACS-20, ACS-30, ACS-31, ACS-32, ACS-33,
ACS-34, ACS-37, ACS-45 and ACS-62.

The findings are those of the
[Standard Agents mapping](../docs/research/analysis/standard_agents_mapping/findings_agent_capability_standard.yaml).
By the maintainer's decision this RFC is Accepted and ships in Standard 1.2.0.

## Motivation

This section's text is in the design: Part A: `tasks/standard-1.2/designs/S2a.md`, part 9; Part B: `tasks/standard-1.2/designs/S2b.md`, part 9, "Motivation". Workstream S2b (header, summary and Part B) with S2a (Part A) replaces this file with the design's text when it lands.

## Goals

This section's text is in the design: Part A: `tasks/standard-1.2/designs/S2a.md`, part 9; Part B: `tasks/standard-1.2/designs/S2b.md`, part 9, "Goals". Workstream S2b (header, summary and Part B) with S2a (Part A) replaces this file with the design's text when it lands.

## Non-goals

This section's text is in the design: Part A: `tasks/standard-1.2/designs/S2a.md`, part 9; Part B: `tasks/standard-1.2/designs/S2b.md`, part 9, "Non-goals". Workstream S2b (header, summary and Part B) with S2a (Part A) replaces this file with the design's text when it lands.

## Key decisions

This section's text is in the design: Part A: `tasks/standard-1.2/designs/S2a.md`, part 9; Part B: `tasks/standard-1.2/designs/S2b.md`, part 9, "Key decisions". Workstream S2b (header, summary and Part B) with S2a (Part A) replaces this file with the design's text when it lands.

## Backward compatibility

This section's text is in the design: Part A: `tasks/standard-1.2/designs/S2a.md`, part 9; Part B: `tasks/standard-1.2/designs/S2b.md`, part 9, "Backward compatibility". Workstream S2b (header, summary and Part B) with S2a (Part A) replaces this file with the design's text when it lands.

## Conformance test updates

This section's text is in the design: Part A: `tasks/standard-1.2/designs/S2a.md`, part 9; Part B: `tasks/standard-1.2/designs/S2b.md`, part 9, "Conformance test updates". Workstream S2b (header, summary and Part B) with S2a (Part A) replaces this file with the design's text when it lands.

## Alternatives considered

This section's text is in the design: Part A: `tasks/standard-1.2/designs/S2a.md`, part 9; Part B: `tasks/standard-1.2/designs/S2b.md`, part 9, "Alternatives considered". Workstream S2b (header, summary and Part B) with S2a (Part A) replaces this file with the design's text when it lands.

## Open questions

This section's text is in the design: Part A: `tasks/standard-1.2/designs/S2a.md`, part 9; Part B: `tasks/standard-1.2/designs/S2b.md`, part 9, "Open questions". Workstream S2b (header, summary and Part B) with S2a (Part A) replaces this file with the design's text when it lands.
