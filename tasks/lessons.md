# Lessons

Patterns from corrections, written as rules to prevent repeats.

## Read every edge before describing a set of edges (issue #114, S4)

**What happened.** When proposing how to re-interpret `soft_requires`, I
described six existing edges (plan→critique, mutate→persist, constrain→audit,
generate→verify, inquire→receive, execute→audit) as prerequisites. They are
follow-ups: each `from` capability makes the `to` capability useful
afterwards. The user had to be asked again, and the six edges became `enables`.

**Rule.** Before characterising a group of ontology edges in a question or a
decision, list each edge with its `rationale` and check that the proposed
reading fits *every* one. If a reading only fits most of them, say which do
not fit, and offer the conversion of those edges as an option.

## Measure the baseline before calling a failure new (issue #114, S4)

**What happened.** The domain workflow files under `schemas/workflows/`
produced ~170 diagnostics under the new validator. Running the validator from
`main` on the same files showed they already failed there (45/55/30/42
diagnostics). CI never validates them.

**Rule.** When a change surfaces failures in files it did not touch, run the
old tool on a `main` worktree first. Report what is new separately from what
was already broken, and do not silently widen the change to fix pre-existing
debt.
