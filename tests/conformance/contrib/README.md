# Contributed runtime fixtures

Scripted runs written by adopters, kept as they sent them.
`scripts/gen_runtime_fixtures.py` checks each file's keys and copies it to
`tests/conformance/runtime/`, where both runners play it. A contributed
name must not clash with a generated one. Each run was checked against the
standard by hand before it was added.

| Files | Source | What they cover |
|-------|--------|-----------------|
| `gap1_*` (6) | #114, gap 1 | Standing mandates in unattended runs: approved, `skip`, `defer_to_queue` and what it defers, a human approver, attended and unavailable (F502), no `when_unattended` (F502) (§5.14) |
| `gap2_*` (5) | #114, gap 2 | Verdict `scope` and `min_full`: full and delta, absent scopes, an unknown scope value, `min_full: 2` met and not met (§5.16) |
| `gap3_*` (4) | #114, gap 3 | R406 and R401 on a wait with liveness: lost twice (R404 to the handler), silence until the deadline, lost after the deadline (R401), an R401-only failure mode (R406) (§5.12, §5.13) |
| `gap5_*` (5) | #114, gap 5 | The authenticated principal: a relayed answer dropped, the owner's kept, relayed then owner, no principal, a principal that differs in case (§5.15) |
