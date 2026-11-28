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

## Test a hook with the stdin its host really gives it

**What happened.** Replacing `$(cat)` with `$(</dev/stdin)` passed every test,
which feed the hook through a pipe. Claude Code gives hooks a socket on
Linux, and a socket cannot be opened by path, so the hook would have failed
on every tool call. A reviewer found it by running the real binary.

**Rule.** When a hook's input handling changes, test it with the host's
actual stdin (a `socket.socketpair()` end for Claude Code on Linux) or run it
under the host itself, not only through `subprocess.run(input=...)`.

## List every route a call takes before saying a layer enforces a rule (round 3)

**What happened.** Every workstream's reviews found the same defect class:
a rule a safety layer was said to enforce held on the main route and was
skipped on another. Profiles' grounding and destination rules were accepted
and never applied; a composite tool ran a nested call that a profile
required a person for, or carried none of the flags a profile raised for the
tools it invokes; unbound tools and composites passed a destination policy;
grounding skipped Claude Code's own tools without a word; arguments the
permission flow changed skipped the secret checks; a non-boolean `is_error`
skipped the output checks; a served tool that was not an `SdkMcpTool` ran
unguarded; an error while using a call's hold let PostToolUse pass the call.

**Rule.** Before writing that a layer applies a rule, list every route by
which a call reaches a tool (served tool, another server's tool, unbound
tool, composite and nested call, changed arguments, Bash, a failure inside
the check itself) and test each one: it applies the rule or refuses the
call. A configuration the layer accepts but does not enforce is a fail-open
path: refuse it when it is loaded (§5.21.4).

## A rule in two languages needs a shared vector at each boundary (round 3)

**What happened.** The Python and TypeScript implementations disagreed
again and again on edges no vector covered: numbers in exponent form and
integers beyond 2^53 (the output codec, the I-JSON check), `approval.role:
null`, `digest: null` against an absent digest, `acs:` indices above
2^53 − 1, model identifiers of the form `name:tag` (Rust, Python and
TypeScript all wrong the same way). Each was found by a reviewer, not by a
test.

**Rule.** Put a rule implemented in more than one language in a
language-neutral vector file first and run every implementation on it.
When one implementation changes, add vectors at the boundary it touched
(2^53 and one past it, exponent forms, null against absent, case, a
separator inside an identifier). Prefer one implementation in the core,
called from the others.

## Gate every new check on the workflow's target, and pin 1.1 with a fixture (round 3)

**What happened.** Several 1.2 checks first applied to every workflow and
broke valid 1.1 ones: `agents` in a 1.1 workflow was S303 (W604 before), the
`continues` checks, the memory `scope` echo and the `model_id` identity check
failed 1.0 and 1.1 runs, and `require_record` was read in a 1.1 run while
the other 1.2 features were gated.

**Rule.** A rule that 1.1 did not have applies only when the workflow
targets 1.2 or later (`>= (1, 2)`, never `== (1, 2)`), and lands with a
`*_v11_*` fixture that pins the 1.1 behaviour: same codes, actions and trace.
Replay the earlier fixtures on `main` and on the branch before calling the
change compatible.

## Leave margin under a measured limit, measured as CI measures (round 3)

**What happened.** The figure-gap sweep's limit is 1800px. Streams tuned
runs on the Standard's page to just under it with a full Chrome
(`ACS_CHROMIUM`), while CI measures with Playwright's headless shell, whose
line breaks differ: measured that way, three runs were over (up to 1822px)
and one sat at 1799.98px. The headless shell reproduces CI's numbers to the
pixel; the full Chrome does not. The timing
test `edge_checks_scale_linearly` "flaked under load" with a 1.7x margin;
measured against `main`, the validator had become twice as slow, because
each step deep-copied a capability schema that ontology 2.2.0 made four
times larger.

**Rule.** Measure a limit with the tool CI uses (the pinned Playwright
headless shell, `ACS_CHROMIUM` unset) and leave a margin of several lines,
not pixels. When a timing test fails under load, time it on `main` and on
the branch before blaming the load, and profile the difference (callgrind on
the test binary) when the branch is slower.

## A number typed into prose drifts; recount before closing (round 3)

**What happened.** Fixture counts, trace kinds and snapshot sizes written
into resolutions, RFCs, the CHANGELOG and guides went stale as later
streams added fixtures: "fifteen runtime fixtures" for seventeen, "sixteen
`resume_*`", "28 call-sequence fixtures" for 30 in a finding resolution and
the integration guide, after the review that added the two.

**Rule.** Where a count can be computed, let a test or the site compute it.
Where prose must state one, grep for the old number in every document when
a change alters it, and recount every stated number before the records are
closed.

## Bound every probe an agent runs; a restart loses all work in flight (security loop)

**What happened.** The cloud container restarted three times during the
security loop while attack agents ran unbounded probes: a nested Claude Code
client started through `claude_agent_sdk`, timing probes on inputs of many
megabytes. Each restart lost every agent in flight. The third came while
two lenses ran whose prompts lacked the probe limits the others had.

**Rule.** Put the limits in every agent's prompt, not only some: no nested
Claude Code process or SDK client; every probe, hook run and test command
under `timeout` and `prlimit --as` (or `ulimit -v`); generated inputs at or
under 1 MB, timing measured on bounded inputs and extrapolated; no command
whose input or output can grow without bound; stop every server started.

## A workflow resumes only up to its first failed call (security loop)

**What happened.** A resume replays cached agent results only up to the
first call that ever failed in the run, even when an in-script retry of it
later succeeded; everything after it runs live. Resuming a five-round loop
whose round-2 verifier had once failed (a safety-classifier flag returns
`null`, like a terminal API error) started round 2's verifiers again. It
was stopped at once: verifiers are read-only, fixers are not.

**Rule.** Retry an agent call that returns `null`, and count what is still
lost or unverified after the retries instead of dropping it. To continue a
long run with an early failed call, write a continuation script that starts
at the next stage and seeds its state (the findings seen, the confirmed
ones) from the journal, rather than resuming. Check the journal for failed
entries before choosing.

## Keep made-up tokens out of a provider's format in files you push (security loop)

**What happened.** The loop's merge was refused at the push by the host's
secret scanning: the redaction vectors held a Discord bot token, a Stripe
live key and a Slack webhook URL, made up but in each provider's own
format. Formats with no checksum are matched on shape alone. In a public
repository they also reach the providers' programs that revoke leaked
tokens. The loop's commits had to be rewritten before the push.

**Rule.** Write an example token in a provider's format with one character
escaped (a JSON `\u` escape, which every reader decodes), and say why in the
file. `test_the_vector_files_hold_no_raw_provider_token` checks the secrets
vectors; scan a new fixture of another kind for these shapes before
committing it. Never ask for the push protection to be bypassed for test
data that can be written another way.

## Before a push, run the whole lint job, not only the step you changed for

**Pattern.** A fix to the newer CI runner's failures went out with ruff
clean (on CI's paths) and the affected tests passing, but not mypy: a
validator that returns the parsed JSON after a `bool` guard returned `Any`
where the function promises a dict, and `Lint & type-check` failed.

**Rule.** Before pushing Python changes, run every step of the lint job as
`ci.yml` writes it: `ruff check`, `ruff format --check` (both on CI's
paths), and `mypy grounded_agency/`. A guard that checks a parsed value's
shape returns `TypeIs[...]`, so the checked value has the type the caller
promises without a cast.

## Run the whole suite on each platform, not the files that look related

**Pattern.** For the macOS fix (#134), the hook suites were run on bash 3.2
and bash 5.3, and the whole suite only on bash 5.3. The macOS CI job ran
the whole suite on both, and found a bash 3.2 bug in a file outside those
suites: `resolve_path` in the pre-tool-use hook rebuilt its path list with
`"${parts[@]:i}"`, which bash 3.2 joins into one word while IFS is `/`. A
path into the records through a link was then asked for approval rather
than refused.

**Rule.** When a change is about a platform or a shell, run the whole
suite on each platform or shell it names before pushing, not a chosen
subset. Run it from a shell whose PATH holds no other plugin's shims (a
Claude Code session can put a `git` shim first on PATH).

## The Standard's figures are drawn by the site, never written into it

**Pattern.** RFC-0011 lengthened §5.18.3, and the site's figure-gap sweep
failed on the Standard's page. A mermaid diagram was added to
`spec/STANDARD-v1.2.0.md` to break the run. `site/test/mermaid.test.ts`
forbids mermaid in every version of the Standard, because a Standard is a
release text; its figures come from data in `site/src/lib/spec-slots.ts`
and the figure code beside it.

**Rule.** When a change to `spec/STANDARD-v*.md` fails the figure-gap
sweep, add a slot and a site-drawn figure (`spec-slots.ts`,
`spec-tail-figures.ts` or a module like `spec-tool-figures.ts`), never a
diagram in the Standard's text. Run `npm test` in `site/` before
measuring, not only the build and the sweep.
