# Governance

## Goal
Keep the standard **stable**, **minimal**, and **composable**.

## Versioning
SemVer:
- MAJOR: breaking schema/DSL changes
- MINOR: backward-compatible additions
- PATCH: clarifications + tooling fixes

## Compatibility rules
- Workflows MUST declare spec version.
- Validator MUST support at least last 2 minor versions.
- Deprecated fields must remain accepted for 1 minor release before removal.

## Decision-making
- Open RFC process
- Changes require:
  - Motivation
  - Alternatives
  - Backward compatibility analysis
  - Conformance test updates

## Maintainers
- A small core team merges, community proposes via RFC.

