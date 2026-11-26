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

## Standard versions
Each version of the Standard is one document, `spec/STANDARD-vX.Y.Z.md`, and
its header states its status. A Standard document's status is Candidate
Standard, Standard, Supported or Unsupported.

| Status | Meaning | Entered when | The `**Date:**` line gives |
|--------|---------|--------------|----------------------------|
| Candidate Standard | Accepted by its RFCs and implemented on `main`; no release carries it | Every RFC it rests on is Accepted | The date the last of those RFCs was Accepted |
| Standard | The latest released version | It meets the release criteria below | Its release date: the date of its section in the [specification changelog](CHANGELOG.md) |
| Supported | A released version that a newer released version supersedes, and that validators must still accept | The next version is released | Its release date, unchanged |
| Unsupported | A released version outside the support window; validators may refuse it | It leaves the support window | Its release date, unchanged |

A Candidate Standard is released, and becomes Standard, when all of these
hold:
- Every RFC it rests on is Accepted.
- The reference validator and executor pass the conformance suites, and each
  safety layer passes the class SL fixtures its statement covers.
- Each open question in those RFCs is answered or has an issue.
- The [specification changelog](CHANGELOG.md) has its release section, with
  the release date.
- A plugin release tag carries it, and the
  [roadmap](ROADMAP.md)'s sentence "Plugin X implements Standard Y" names
  that plugin version and this Standard version.

The plugin and the Standard are numbered separately. A plugin tag `vX.Y.Z`
names a plugin version, never a Standard version: plugin 2.0.0 carries
Standard 1.1.0, and the plugin tag `v1.2.0` does not carry Standard 1.2.0.

When a Standard is released, the version that was Standard becomes
Supported. The support window is the list of versions that the latest
released Standard's §11.5 requires a validator to support; under
"Compatibility rules" it holds at least the last two minor versions. A
Supported version that a newer release leaves out of that list becomes
Unsupported.

The status of each version, with the date its header gives, is listed in the
Standard table of the [roadmap](ROADMAP.md).

## Maintainers
- A small core team merges, community proposes via RFC.

