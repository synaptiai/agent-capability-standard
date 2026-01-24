# Security

## Core safety invariants
This standard is designed so **unsafe actions are hard by construction**.

1. **Mutation requires checkpoint**
   - Any step with `mutation: true` MUST be preceded by a valid checkpoint capability.
2. **Actions require a plan**
   - `act-plan` requires `plan` (hard requirement) and SHOULD require `verify`.
3. **Claims must be auditable**
   - All outputs SHOULD include evidence anchors and provenance.
4. **Identity merges are constrained**
   - Hard constraints prevent catastrophic entity conflation.

## Threat model (high level)
- Prompt injection and tool misuse
- Incorrect identity merges causing data corruption
- Trust manipulation (spoofed sources)
- Silent drift via unbounded state updates
- Schema spoofing / invalid binding references

## Mitigations
- Schema-validated workflows with compiler-grade validator
- Trust + decay model for conflict resolution
- Deterministic transforms + retention controls
- Recovery loops + rollback strategies

## Responsible disclosure
- Please report vulnerabilities privately to the maintainers.
- Provide reproduction steps, scope, and suggested remediation.

