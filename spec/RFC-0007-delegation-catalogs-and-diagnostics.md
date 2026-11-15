# RFC-0007: Delegation, catalogs and validator diagnostics
**Status:** Accepted
**Target:** Standard v1.2.0
**Date:** 2026-11-15

## Summary

This RFC records the decisions behind eleven changes in Standard 1.2.0, made
on the maintainer's instruction to implement every remaining finding of the
Standard Agents mapping
(`docs/research/analysis/standard_agents_mapping/findings_agent_capability_standard.yaml`:
ACS-04, ACS-09, ACS-16, ACS-17, ACS-24, ACS-29, ACS-46, ACS-47, ACS-49,
ACS-50, ACS-54). It adds an agent manifest (`schemas/agent_manifest_schema.yaml`)
and a workflow field `agents`, with which a `delegate` step takes the safety
flags of what its target may do, is not delegated without its target's
manifest, and has its task checked; enforcement of `read_only` in 1.2
workflows; a `delegate` input `continues`; a catalog manifest with qualified
workflow ids for `invoke`; a grammar and a host selection rule for a step's
`domain`; typed answers to `inquire`; a defined diagnostic `location` with an
RFC 6901 `path`; the scope of `conflicts_with`; and the comparison and
derivation of model families. Four warnings are new (W620–W623); no error
code is. Every behaviour change is opt-in or a warning; the text is in
`spec/STANDARD-v1.2.0.md` §4.3, §5.1, §5.1.1, §5.2, §5.2.4, §5.13.1,
§5.15–§5.17 and §9.

## Motivation

This section's text is in the design: `tasks/standard-1.2/designs/S3.md`, part 9, "Motivation". Workstream S3 replaces this file with the design's text when it lands.

## Goals

This section's text is in the design: `tasks/standard-1.2/designs/S3.md`, part 9, "Goals". Workstream S3 replaces this file with the design's text when it lands.

## Non-goals

This section's text is in the design: `tasks/standard-1.2/designs/S3.md`, part 9, "Non-goals". Workstream S3 replaces this file with the design's text when it lands.

## Key decisions

This section's text is in the design: `tasks/standard-1.2/designs/S3.md`, part 9, "Key decisions". Workstream S3 replaces this file with the design's text when it lands.

## Backward compatibility

This section's text is in the design: `tasks/standard-1.2/designs/S3.md`, part 9, "Backward compatibility". Workstream S3 replaces this file with the design's text when it lands.

## Conformance test updates

This section's text is in the design: `tasks/standard-1.2/designs/S3.md`, part 9, "Conformance test updates". Workstream S3 replaces this file with the design's text when it lands.

## Alternatives considered

This section's text is in the design: `tasks/standard-1.2/designs/S3.md`, part 9, "Alternatives considered". Workstream S3 replaces this file with the design's text when it lands.

## Open questions

This section's text is in the design: `tasks/standard-1.2/designs/S3.md`, part 9, "Open questions". Workstream S3 replaces this file with the design's text when it lands.
