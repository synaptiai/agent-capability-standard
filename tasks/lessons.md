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

## "Figure out if and how" two standards fit means doing the mapping

**What happened.** Asked whether and how the Standard Agent Specification and
this standard could work together, I read about half of their specification
through summaries, answered with a one-screen verdict and offered to draft the
mapping. The user's reply: do it thoroughly, write the integration document,
show a grounded agent built on their standard, and prepare upstream issues.

**Rule.** For a public interoperability question, the answer is the work:
read both specifications from source (clone the repository, read the
published types), map them concern by concern with citations, build the
smallest thing that proves the combination works, and write it up. Give the
short verdict as the summary of that work, not in place of it. Say up front
what cannot be done from the session (for example filing issues in a
repository it cannot write to) and prepare it for the user instead.

## Keep the documents under review out of the corpus they are checked against

**What happened.** A script checked that every quotation in the integration
document occurs in the source repositories. The corpus globbed `docs/**`, so
it included the document itself and every quotation passed. Excluding the
document exposed five quotations with a changed capital letter or added
emphasis.

**Rule.** When a check compares a text with its sources, build the source
set first and assert the text under review is not in it. Then prove the check
can fail, with a deliberately wrong input, before trusting a clean run.

## Do not fan out more agents than the usage budget can finish

**What happened.** The mapping ran as ten mappers, twenty reviewers and ten
reconcilers. The mappers used most of the budget; the limit arrived while the
reviewers ran, so seven concerns were never reviewed and none was reconciled.

**Rule.** Size a multi-stage workflow so the later stages are certain to run:
fewer, narrower first-stage agents, or run verification on the first
concern end to end before starting the rest. Unreviewed output is working
material, not a deliverable; do not publish it.

## Run every check the pull request's CI runs, not only the ones the guide lists

**What happened.** The first CI run on the Standard Agents pull request failed
in the site job: `npm run check:axe`, which runs after the build, found a
table header cell with no text on the new guide page. The local runs had
covered `npm run check`, `npm test` and `npm run build`, the three commands
CLAUDE.md lists, and not the accessibility step in `.github/workflows/site.yml`.

**Rule.** Before the first push of a branch, read the workflow files and run
each step that can run locally. For the site: after `npm run build`, run
`ACS_CHROMIUM=<chromium> node scripts/check-axe.mjs --paths <changed pages>`.
A Markdown table needs text in every header cell.

## `check:axe` is two checks: axe and the figure-gap sweep

**What happened.** After the axe fix, the full `npm run check:axe` failed on
`check-runs.mjs`: lengthening the SDK guide and the domains index had left
stretches of over two viewport heights with no figure on enforced pages. The
targeted run that followed the earlier lesson had called `check-axe.mjs`
alone, which does not run the sweep.

**Rule.** For a page an edit lengthens, run both scripts on it after the
build: `check-axe.mjs --paths …` and `check-runs.mjs --paths …`. Fix a long
stretch with a figure that shows the mechanism, or by moving or tightening
text; exempt a run only when it is one of the categories in `runs.ts`.

## Probe a safety guarantee with hostile input before documenting it

**What happened.** The pull request documented that every mutating Bash
command needs a checkpoint and approval, and that the plugin hook blocks a
call without a valid marker. The final review broke both in minutes:
`env rm -rf x` and `ls | sh` were classified read-only (the classifier read
only the first word), and a marker of `ok` made the hook exit 5, which Claude
Code treats as non-blocking. The unit tests checked only cooperative inputs.

**Rule.** Before writing that a check blocks something, try the inputs an
adversary would: wrappers (`env`, `xargs`, `sh -c`), every shell operator and
redirection, quoting, case, path tricks (`//`, `..`), malformed state files,
and a failing command inside the check. A hook must fail closed: any exit
code other than the blocking one lets the call run.

## Use the kernel's lock; do not build one from mkdir and timeouts

**What happened.** A `mkdir` lock with a five-second give-up broke the audit
log's chain on slow CI runners (a waiter appended beside a slow holder and
removed its lock). Each patch to it (an age rule, a PID file, a turn to
break stale locks) was broken again by reviewers: `kill -0` misreads holders
in another uid or PID namespace, a FIFO planted as the PID file hangs the
hook, check-then-act races remove fresh locks, and iteration counts are not
time. flock(2) through `flock` or `perl` removed the whole class: the kernel
releases the lock when its holder exits.

**Rule.** For mutual exclusion in a shell script, use flock(2) (with a
portable way to call it) before inventing a lock. Bound every wait by wall
clock, and make the timeout path degrade to something detectable, not to
silence. Test a lock under CPU load and with a slow holder, not only idle.
