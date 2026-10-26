# Issue #114 — orchestration extensions + validator/engine unification

Branch: `claude/gifted-albattani-qwnlo3`. Base: `9e2f65b`.

Source analysis: 9 investigators + 9 adversarial verifiers + synthesis +
completeness critic (workflow run `wf_b4bf993c-1bd`). Decisions below were
agreed with the maintainer in the interview; each records the option chosen.

## Agreed decisions

| # | Question | Decision |
|---|----------|----------|
| D-scope | What this branch delivers | Everything: tooling unification, safety fixes, RFC-0003, E1–E6 |
| D-rfc | RFC-0003 status | **Accepted**, target **Standard v1.1.0** (MINOR) |
| D-mech | Extension mechanism (issue Q1) | Optional DSL fields + monotonic-restriction rule + must-understand `workflow_extensions.requires` |
| D-appr | Step-level `requires_approval: false` downgrades | Bug: **warn** (W-code), fix catalog + fixtures |
| D-prec | `precedes` | Ordering-only when both present; add `soft_requires` constrain→{execute,mutate,send}, plan→{execute,mutate} |
| D-conf | `conflicts_with` | Concurrency exclusion (same `parallel_group`), de-duplicated |
| D-audit | audit mutation override | Ontology node field `mutation_overridable: true` (audit only) |
| D-arch | Validator vs engine | **CLI wraps the engine**: one implementation in `grounded_agency/workflows/` |
| D-norm | Normative artifact | STANDARD §5 normative; omitted safety flags **inherit** the ontology value; JSON schema relaxed to §5 |
| D-warn | Warnings | `severity` on structured errors + W6xx codes; `--strict` promotes warnings |
| D-dur | Durations | Dual grammar: shorthand `^\d+(ms|s|m|h|d)$` or ISO-8601 dayTime subset |
| D-E1 | Durable wait | `wait` block on `receive` (and `synchronize` with ≥2 agents) |
| D-E2 | Agent reference / Q2 | Split: delegate hints + `effective` attestation + `accept_from` now; identity later |
| D-E3 | Approval | Structured, fail-closed `approval` block |
| D-E4 | Verdict quorum | `quorum` on `constrain`, typed verdicts |
| D-E5 | Escalation | `recovery.on_exhausted` → invoke step; `action: escalate`; goto_step resolution |
| D-E6 | Triggers | `triggers[]` list |
| D-decl | Declaration | `workflow_extensions.requires` + optional `spec_version` |
| D-del | Delivery | One branch, staged commits, no PR; draft (not post) Q3 issue + #114 reply |
| D-E5h | Escalation target in normal flow | Step flag `handler: true` (invoke only; skipped in sequence; terminal) |
| D-clar | clarify_intent send downgrade | Replace checkpoint+send with inquire → receive |
| D-tz | Timezone validation | Add `tzdata` dependency (pyproject + constraints) |
| D-vend | 17 vendored catalog copies | Regenerate via `sync_skill_schemas.py` + drift check |
| D-rev | E4 reviewer identification | Explicit `quorum.reviewers: [store_as]` |
| D-unk | Unknown keys | W604 UNKNOWN_FIELD + did-you-mean; `x-` keys exempt |
| D-lang | Core language | **Rust + PyO3**, maturin mixed project (`core/` → `grounded_agency._core`), no Python fallback |
| D-yaml | YAML parsing | Core parses YAML too (saphyr, YAML 1.2), ports safe_yaml guards + alias limit; PyYAML parity test |
| D-exec | Runtime scope | **Full executor in the core**, sans-IO state machine (`next(now)` → Action, `submit(result, now)`) |
| D-fm | When a failure mode fires | `on_error` code match or new optional `when` expression; `condition` stays prose |
| D-expr | Expression grammar | Pending: CEL vs minimal ACS grammar evaluation (workflow `wf_3087ac31-67f`) |

## Stages (one commit each, validated before commit)

- [ ] S1 Engine becomes the single validator; CLI wraps it (behaviour-preserving
      port of the validator's inference, $ref resolution, consumer checks, L4
      patches) + warnings channel + error-code fixes (B202 for missing producer,
      V104 in engine, V103 instead of KeyError, B205 unknown annotation, integer
      type, self-reference, non-dict top-level keys, S304 for §5 MUST fields).
      Differential/parity tests over every fixture + catalog.
- [ ] S2 Edge + flag semantics: precedes ordering-only, conflicts concurrency,
      soft_requires warnings + new soft edges, flag inheritance, downgrade
      warnings (W602), `mutation_overridable`, catalog/fixture honest flags,
      model_deployment reorder, JSON schema relaxed to §5, unknown-field
      warnings (W604), checkpoint `validate_and_reserve` race fix.
- [ ] S3 RFC-0003 + STANDARD v1.1.0 text (mechanism, durations, W-codes,
      V106/V107, §5.7 recovery semantics, edge errata, conformance gap note).
- [ ] S4 E6 triggers + durations module.
- [ ] S5 E5 recovery/escalation.
- [ ] S6 E1 wait + resume safety.
- [ ] S7 E3 approval + ApprovalLedger + ActionRecord.
- [ ] S8 E2 delegation hints + accept_from.
- [ ] S9 E4 quorum + review_verdict schema + evaluator.
- [ ] S10 Docs, changelogs, counts, doc errata; Q3 issue + #114 reply drafts.

Each stage: ruff, mypy, full pytest, every `tools/validate_*.py`,
`scripts/run_conformance.py`, then independent code + test review, fixes, commit.

## Review

(filled in at the end)
