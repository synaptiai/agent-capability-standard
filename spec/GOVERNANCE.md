# Governance

## Goal
Keep the standard **stable**, **minimal**, and **composable**.

## Versioning
SemVer:
- MAJOR: breaking schema/DSL changes
- MINOR: backward-compatible additions
- PATCH: clarifications + tooling fixes

## Compatibility rules
- Workflows SHOULD declare the spec version (`spec_version`, or a `# Standard version:` header for a whole catalog file). Validators report a missing declaration as a warning (W605) and an unsupported version as an error (V109) (STANDARD §11.5).
- Validator MUST support at least last 2 minor versions.
- Deprecated features remain accepted, with a W603 warning, until the next MAJOR release, and for at least 6 months after the deprecation (STANDARD §11.2).

## Decision-making
- Open RFC process. An RFC's status is Draft, Accepted (including once
  its target version has shipped), Rejected or Superseded.
- Changes require:
  - Motivation
  - Alternatives
  - Backward compatibility analysis
  - Conformance test updates

## Maintainers
- A small core team merges, community proposes via RFC.

