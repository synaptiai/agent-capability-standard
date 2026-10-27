# Governance

## Goal
Keep the standard **stable**, **minimal**, and **composable**.

## Versioning
SemVer:
- MAJOR: breaking schema/DSL changes
- MINOR: backward-compatible additions
- PATCH: clarifications + tooling fixes

## Compatibility rules
- Workflows MUST declare spec version (`spec_version`, or a `# Standard version:` header for a whole catalog file). Validators report a missing declaration as a warning (W605) and an unsupported version as an error (V109).
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

