# RFC-0008: Evidence, grounding and secrets
**Status:** Accepted
**Target:** Standard v1.2.0
**Date:** 2026-11-15

## Summary

Standard 1.1.0 says every claim must be evidence-backed or marked as
inferred (§3.1), and gives that sentence nothing to stand on: the 36
capability outputs require `evidence_anchors` with no item schema, the
repository holds three anchor vocabularies, `inference_method` is in no
schema, F505 is reserved and never raised, nothing ties a citation to what
its producer saw, no rule keeps secrets out of evidence and records, the
evidence store has no contract, retention ignores where records live,
`confidence` is undefined and contradicted by the ontology's own
principle, and no notification exists for recorded evidence.

This RFC records the decisions Standard 1.2.0 makes on findings ACS-06,
ACS-21, ACS-22, ACS-23, ACS-40, ACS-51, ACS-53 and ACS-58 of the
[Standard Agents mapping](../docs/research/analysis/standard_agents_mapping/findings_agent_capability_standard.yaml).
It takes over decision 8 of [RFC-0005](RFC-0005-tool-calling-hosts.md)
(one anchor item, one kind vocabulary), withdrawn there, and answers its
open question 5. It is Accepted by the maintainer's instruction that every
remaining finding is implemented in 1.2.0; the text is in
[STANDARD-v1.2.0](STANDARD-v1.2.0.md) §3.1, §4.1.1, §5.20, §6.5, §6.6 and
§6.7.

## Motivation

This section's text is in the design: `tasks/standard-1.2/designs/S4.md`, part 9, "Motivation". Workstream S4 replaces this file with the design's text when it lands.

## Goals

This section's text is in the design: `tasks/standard-1.2/designs/S4.md`, part 9, "Goals". Workstream S4 replaces this file with the design's text when it lands.

## Non-goals

This section's text is in the design: `tasks/standard-1.2/designs/S4.md`, part 9, "Non-goals". Workstream S4 replaces this file with the design's text when it lands.

## Key decisions

This section's text is in the design: `tasks/standard-1.2/designs/S4.md`, part 9, "Key decisions". Workstream S4 replaces this file with the design's text when it lands.

## Backward compatibility

This section's text is in the design: `tasks/standard-1.2/designs/S4.md`, part 9, "Backward compatibility". Workstream S4 replaces this file with the design's text when it lands.

## Conformance test updates

This section's text is in the design: `tasks/standard-1.2/designs/S4.md`, part 9, "Conformance test updates". Workstream S4 replaces this file with the design's text when it lands.

## Alternatives considered

This section's text is in the design: `tasks/standard-1.2/designs/S4.md`, part 9, "Alternatives considered". Workstream S4 replaces this file with the design's text when it lands.

## Open questions

This section's text is in the design: `tasks/standard-1.2/designs/S4.md`, part 9, "Open questions". Workstream S4 replaces this file with the design's text when it lands.
