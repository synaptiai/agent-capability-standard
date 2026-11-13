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

## Report a version change as a choice, not a side effect (dependency bump)

**What happened.** Installing with the constraints file moved pytest from
9.0.2 to 8.4.2 and pytest-asyncio from 1.3.0 to 0.26.0. I reported that as a
neutral detail. The user's answer was to raise the caps to the latest
releases and fix whatever broke.

**Rule.** When an install moves a package to an older version, treat it as a
finding: name the cap that caused it and offer to raise it. Do not accept
the older version silently.

## Ask which Python versions are supported before testing old ones

**What happened.** I started a Python 3.10 test run because
`requires-python` said `>=3.10`. The user supports only 3.14 and 3.15.

**Rule.** `requires-python` and the CI matrix may lag the project's real
support policy. Before spending work on an old interpreter, confirm the
supported versions with the user.

## Judge a visual deliverable against its references, not only its checks

**What happened.** The documentation site shipped with every functional
check green: links, contrast, accessibility, tests, rendering at three
widths. The user found it text heavy, with too few diagrams, icons and
pixel art. The request had named two reference sites for the look, but no
step compared the built pages with them; review agents checked function and
correctness only.

**Rule.** For anything people look at, add a review step that compares the
built pages with the references the user named: how often a visual appears,
what kinds, how much space. Show the user a few exemplar pages before
building the rest. Passing checks say the page works, not that it meets the
brief.
