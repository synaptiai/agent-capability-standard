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

## Check hook contracts against the SDK, not against our own tests (S4)

**What happened.** The PreToolUse checkpoint hook returned a top-level
`{"permissionDecision": "deny"}`. The SDK only reads a decision from
`hookSpecificOutput`, so the deny never took effect; the tests asserted the
same wrong shape and passed. The first reservation fix also assumed
PostToolUse reports failures, but Claude Code sends those to
`PostToolUseFailure`.

**Rule.** For any hook or callback contract, read the SDK's own type
definitions (`claude_agent_sdk.types`) before writing or reviewing it, and
assert the SDK's shape in tests. Ask "which events fire, and when?" before
relying on a cleanup path.

## Let reviews finish before committing (S4)

**What happened.** I committed and pushed S4 while three reviews were still
running, to keep the work safe in an ephemeral container. The reviews then
found real defects, so the branch carried a known-flawed commit until the
fix commit.

**Rule.** When the user asks for review before commit, wait for the reviews.
If the work must be saved first, say so explicitly and name the follow-up
commit that will carry the review fixes.

## Read back what you post to GitHub (#114 follow-up)

**What happened.** The #114 reply was posted with a markdown link followed
directly by a period; the stored comment had the link wrapped in backticks,
so it rendered broken. I only noticed while reading the next reply.

**Rule.** After posting or editing a GitHub comment or issue, read it back
and check the stored body (links, tables, code spans). Avoid ending a
sentence with a bare `](url).`; put text after the link instead.
