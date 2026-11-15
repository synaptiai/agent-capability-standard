# Conformance

Normative requirements are in [STANDARD-v1.2.0 §10](STANDARD-v1.2.0.md#10-conformance);
this page summarises them.

## Conformance levels
- **L1 Structural Conformance**
  - validates required fields and field types
  - validates capability existence
  - enforces `requires`, `precedes` and `conflicts_with`; warns on unmet
    `soft_requires`
  - resolves effective safety flags; warns on downgrades
  - reports unknown fields and the declared standard version

- **L2 Type Conformance**
  - resolves `$ref` schemas
  - infers binding types, checking each binding's root and path
  - requires typed annotations only when ambiguous
  - validates typed annotations

- **L3 Contract Conformance**
  - validates binding types against consumer input_schema
  - parses and type-checks condition expressions
  - emits coercion hints

- **L4 Patch Conformance**
  - emits patch suggestions JSON
  - emits optional diff patch (`--emit-patch`)
  - uses coercion registry when available

Every diagnostic has a fixed severity: errors make a workflow invalid,
warnings (W6xx) do not, unless the validator runs in strict mode
(`--strict`).

```mermaid
---
title: What a diagnostic does to a workflow
---
flowchart TB
  accDescr: An error makes the workflow invalid; a W6xx warning does not, unless the validator runs with --strict.
  d[Diagnostic] -->|error| inv[Workflow invalid]
  d -->|warning W6xx| strict{"--strict?"}
  strict -->|yes| inv
  strict -->|no| ok[Workflow still valid]
```

**Reference implementation:** L4 (`tools/validate_workflows.py`, backed by
the Rust core in `core/`).

## Required artifacts
- Capability ontology file
- Workflow catalog file
- Schema bundle + policies
- Validator CLI

## Test suite requirements
- Positive fixtures: valid workflows (`tests/fixtures/pass_*`)
- Negative fixtures: invalid references, type mismatches, ambiguous nodes,
  edge and version violations, and malformed or undeclared extensions
  (`tests/fixtures/fail_*`)
- Patch fixtures: expected patch suggestions and diff output
- Expectations in `tests/fixtures/EXPECTATIONS.json`: `should_pass`,
  `expected_error_codes`, and `expected_warning_codes`. The codes a fixture
  emits must equal the listed set exactly; an absent or empty warning list
  means no warning may be emitted
- Expression fixtures, language-neutral:
  `tests/conformance/expressions/eval.json` (evaluation results and runtime
  errors) and `tests/conformance/expressions/check.json` (static
  diagnostics). `tools/cel_differential` runs them against cel-go to check
  CEL compatibility.
- Runtime fixtures, language-neutral: `tests/conformance/runtime/*.json`,
  scripted runs of the reference executor (catalog, inputs, the expected
  actions and the responses to them, the expected end and trace). Run by
  `cargo test --test runtime` (each also replayed through a snapshot and
  restore before every step) and `tests/test_runner.py`. Fifteen of them
  (`orchestrator_*`) script runs of the workflows an adopter ported to the
  candidate (reduced from production, generic names; revision 1.1e), kept
  as contributed
  (`tests/fixtures/pass_orchestrator_port.workflow_catalog.yaml`). The
  `domain_*` ones run reference domain workflows. Twenty (`gap*`) are an
  adopter's own scripted runs, kept as contributed in
  `tests/conformance/contrib/` and copied by the generator.

```mermaid
---
title: How a workflow fixture is checked
---
flowchart TB
  accDescr: The error and warning codes a fixture emits are compared with the expected_error_codes and expected_warning_codes EXPECTATIONS.json lists for it; the fixture passes only when they are exactly equal.
  fx["Fixture: pass_* or fail_*"] --> codes[Emitted error and warning codes]
  ex["EXPECTATIONS.json: expected_error_codes, expected_warning_codes"] --> eq{"Exactly equal?"}
  codes --> eq
  eq -->|yes| pass[Fixture passes]
  eq -->|no| fail[Fixture fails]
```

Running the suite:

| Fixtures | Command |
|----------|---------|
| Workflow fixtures (`tests/fixtures/`) | `python scripts/run_conformance.py` |
| Runtime fixtures | `cargo test --test runtime` (in `core/`), `pytest tests/test_runner.py` |
| Expression fixtures | `cargo test --test expressions` (in `core/`); `tools/cel_differential` against cel-go |
| Approval digest vectors | `pytest tests/test_approval_vectors.py`; `npm test` in `examples/standard_agents/` |
| Trust vectors | `pytest tests/test_trust.py` |

`scripts/run_conformance.py` runs only the workflow fixtures.

Coverage gaps: no conformance fixture yet exercises V103, S301, S302, W607
or W612; the reference implementation's unit tests cover them. F505 is
reserved and not checked by the reference implementation, so nothing
tests it.

## Informative vectors

These files are language-neutral and informative: STANDARD-v1.1.0 §10.3 does
not name them. Each is JSON, describes its own fields, and has one named
entry per case.

- Approval digests: `tests/conformance/approval/digests.json`. Each vector
  is one approval request of the reference executor (§5.14): the shown
  values, their canonical JSON (RFC 8785) and the SHA-256 digest of that
  text in lowercase hexadecimal. The vectors cover member order, nesting,
  number forms, text outside ASCII, an empty list, a step that declares no
  `shows`, and a step asked again after a recheck. Three things the vectors
  pin are the reference executor's behaviour and are not stated in the
  Standard: a step with no `shows` shows its resolved inputs wrapped in an
  array, a step asked again shows one more object, whose `recheck` member
  holds the previous and the current value of the source, and the digest is
  written in lowercase hexadecimal. The `numbers` vector holds 2^53
  (9007199254740992), the bound §5.14 writes as "within ±2^53"; RFC 7493
  §2.2 gives the range of integers a receiver can treat as exact as
  ±(2^53 - 1).
  `scripts/gen_standard_agents_binding.py` writes the file from runs of the
  executor, and CI fails when it is out of date.
  `tests/test_approval_vectors.py` replays each vector on the executor and
  recomputes the canonical JSON and the digest with a serializer of its
  own. The Standard Agents binding tests its digest against a copy,
  `examples/standard_agents/test/fixtures/approval-digests.json`.
- Trust: `tests/conformance/trust/decay.json` (the decay factor of §8.1:
  0.5 at one half-life, which §8.1 requires, `0.5 ** (age / half_life)` at
  other ages, which it recommends, and not below `decay_model.min_trust`),
  `tests/conformance/trust/weight.json` (the static weight of §8.3: the lower
  of the class weight and the source weight, with a domain profile's
  `trust_weights` overrides) and `tests/conformance/trust/score.json` (the
  product that `conflict_resolution_function.formula` in
  `schemas/authority_trust_model.yaml` names). Each file states the absolute
  tolerance its expected values are given to. §8.3 states the profile
  override of a class weight only; the vectors in which a profile key
  replaces or adds a source weight rest on a comment in the schema and say
  so. Each file lists under `not_covered` the cases whose result the
  Standard does not state, such as a `min_trust` above 0.5, where §8.1
  requires 0.5 at one half-life and also floors the factor at `min_trust`;
  no vector covers them, and each entry says what the reference
  implementation does. `tests/test_trust.py` runs the reference
  implementation, `grounded_agency/trust.py`, against the vectors.

Among the runtime fixtures, `checkpoint_per_mutation` pins what the
reference executor asks for a step that needs approval and has no `approval`
field: approver `{kind: human}`, mode `in_session`, the step's resolved
inputs wrapped in an array, and no expiry. §5.14 does not state this
request. A fixture's expectation matches by subset, so
`tests/test_approval_vectors.py` also checks that the approver has no other
member.
