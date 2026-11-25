# Handoff: after Standard 1.2.0 (pull request #132)

Written 2026-11-25 at the end of a cloud session, to continue on a Mac.
Read this file and `tasks/lessons.md` first. The plan and every round's
review are in `tasks/todo.md`.

## Where things stand

- **main is at `a4cb1ae`**, the merge of pull request #132. CI and the Site
  workflow (including the Cloudflare Pages deploy) passed on it.
- **What main holds:**
  - Standard 1.2.0 as a Candidate and ontology 2.2.0.
  - RFC-0005 to RFC-0010, Accepted. RFC-0002 is still a Draft.
  - The reference implementation in the Rust core (validator and executor,
    built for Python and for WebAssembly), the Python SDK
    (`grounded_agency`), the plugin hooks, the skills' command hooks, the
    TypeScript package `@synaptiai/acs-core` and the Standard Agents
    binding (`examples/standard_agents/`).
  - All 64 ACS findings fixed, the security loop's 130 fixes, and the PVC
    review.
- **Version files are unchanged on purpose** until the release:
  `.claude-plugin/plugin.json` 2.0.0, `pyproject.toml` and
  `grounded_agency.__version__` 0.1.0, `packages/acs-core/package.json`
  0.1.0. The release that carries this work is plugin 3.0.0.
- **The branch `claude/gallant-hypatia-wbucn3`** was merged. It now holds
  this file on top of main, nothing else. Start new work from main.
- **Open work** is in GitHub issues, gathered under the tracking issue
  #133. The table at the end lists them.

## Set up the Mac

The work so far ran on Linux only. CI runs on `ubuntu-latest`, and the
plugin hooks have never run on macOS (#134). Expect some failures
on the first run; see "Run the checks" below.

1. **Get the code.**
   ```bash
   git clone git@github.com:synaptiai/agent-capability-standard.git
   cd agent-capability-standard
   git switch main && git pull
   ```
   The site build reads `git log` for the sitemap, so do not use a shallow
   clone.
2. **Install the tools** (Homebrew). These are the versions CI pins:
   ```bash
   brew install uv rustup jq bash go node openssl
   rustup-init -y   # if rustup is not set up yet
   rustup toolchain install 1.99.1 --profile minimal \
     --component rustfmt,clippy --target wasm32-unknown-unknown
   rustup toolchain install 1.88.0 --profile minimal   # the MSRV check
   ```
   - **Python 3.14.** CI also runs 3.15. Use `uv python install 3.14`.
   - **Rust 1.99.1.** This is `RUST_TOOLCHAIN` in
     `.github/workflows/ci.yml`; the MSRV is 1.88.0.
     `npm run build:wasm` reads the toolchain from `RUSTUP_TOOLCHAIN`.
   - **Node 26.13.0** (`site/.nvmrc`) through nvm, fnm or Volta. The
     package needs Node 20 or later, the site 22.23.4 or later.
   - **Go 1.26.0** for the CEL differential test (`tools/cel_differential`).
   - **bash 5 ahead of `/bin` on `PATH`.** The hooks and many tests run
     the first `bash` on `PATH`. macOS's `/bin/bash` is 3.2, which nothing
     here has been run with. Check with `bash --version`.
   - **jq.** The tests follow the installed jq's depth limits: 1.7 and 1.8
     both pass.
   - **openssl.** The checkpoint hook uses it to record a commit; macOS's
     own is LibreSSL, which has not been tried.
   - **Chromium for the site's checks:** `cd site && npx playwright install
     chromium`. That is the build that the pinned `playwright` names; CI
     measures the figure gaps with it.
3. **Make the Python environment.** It is built with uv, so the
   environment has no pip; use `uv pip`:
   ```bash
   uv venv --python 3.14 .venv && source .venv/bin/activate
   uv pip install -e ".[dev]" -c constraints.txt
   ```
   This compiles the Rust core into `grounded_agency/_core.abi3.so`. Run it
   again after every change to `core/`: a stale extension fails tests in
   ways that look like code bugs. Here, a `KeyError: 'idempotency_key'`
   came from a build 9 days older than the core.

## Run the checks

CLAUDE.md lists every command. In the order that finds problems soonest:

```bash
# Python: the whole lint job, as CI runs it
ruff check grounded_agency/ tests/ tools/ scripts/ benchmarks/
ruff format --check grounded_agency/ tests/ tools/ benchmarks/ scripts/gen_runtime_fixtures.py scripts/runtime_fixtures/ scripts/gen_trigger_vectors.py scripts/gen_standard_agents_binding.py scripts/gen_capability_json_schemas.py scripts/gen_call_fixtures.py
mypy grounded_agency/
# Validators and generators
python tools/validate_workflows.py --strict
for c in schemas/workflows/*.yaml examples/*.workflow_catalog.yaml; do python tools/validate_workflows.py --catalog "$c" --strict; done
for t in tools/validate_*.py; do python "$t" || echo "FAILED $t"; done
python tools/sync_skill_schemas.py --check
for g in gen_runtime_fixtures gen_call_fixtures gen_trigger_vectors gen_standard_agents_binding gen_capability_json_schemas; do python scripts/$g.py --check; done
# Tests (about 25 minutes; the hook tests take the most time)
pytest tests/ -q
pytest benchmarks/tests -q && python scripts/run_conformance.py
# Rust (cd core)
cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test
# TypeScript package, then the binding
(cd packages/acs-core && npm ci && npm run build:wasm && npm run build && npm run check && npm test)
(cd examples/standard_agents && npm ci && npm run check && npm test)
# Site
(cd site && npm ci && npm run check && npm test && npm run build)
```

On the first macOS run, record each failure in #134 before fixing
it. A failure there is a portability defect of the hooks or the tests,
unless it is a missing tool. The hooks run on users' Macs.

## Where the records are

| What | Where |
|---|---|
| The plan, each round's review, and the list of what stays open | `tasks/todo.md` (newest round first; the section "Pull request #132" holds the open list) |
| Rules learned from mistakes; read before working | `tasks/lessons.md` |
| Designs of the 1.2.0 workstreams | `tasks/standard-1.2/designs/` (FOUNDATION, S1 to S6) |
| What each workstream did, its reviews and checks | `tasks/standard-1.2/progress/` (S1 to S6, PHASE4, FINISH) |
| The security loop: every defect, fix and test | `tasks/standard-1.2/progress/SECURITY-LOOP.md` |
| The perspective review: 15 checks, 58 actions | `docs/reviews/pvc/2026-11-24_standard-1-2-0.pvc.yaml` |
| The mapping against the Standard Agent Specification, and the findings | `docs/research/analysis/standard_agents_mapping/` |
| The upstream issue texts and the script that files them | `tasks/standard-agents-upstream/` |
| What changed for users | `CHANGELOG.md` [Unreleased], with "Upgrading" |

## Lessons worth knowing before the next change

These are in `tasks/lessons.md`, with the reasons.

- **Lint:** run the whole lint job before a push, mypy included, not only
  ruff.
- **Rust:** rebuild the extension after Rust changes.
- **Push protection:** a made-up token in a provider's format (Stripe,
  Slack, Discord) is refused by GitHub's push protection. Escape one
  character with a JSON `\u` escape; a test guards the secrets vectors.
- **CI runner versions:** the runner's tools change under you. bash 5.3,
  jq 1.8 and a larger C stack each changed results in November 2026. The
  tests ask the installed tool what it does instead of assuming a version,
  and the hooks' brace reading takes the union of the bash readings.
- **CodeQL:** its summary check can read "neutral" ("1 configuration not
  found: rust") when it finishes before the Rust analysis uploads. Check
  the "Analyze (rust)" job itself.
- **Figure gaps:** the site's figure-gap sweep runs within a few pixels of
  its limit on several pages (#157). A small edit to
  `spec/STANDARD-v1.2.0.md` can fail it.
- **Workflow conventions:** commit messages use conventional prefixes
  (`fix(hooks):`, `test(state):`, `docs(tasks):`) and explain the why. The
  plan lives in `tasks/todo.md`, and lessons go in `tasks/lessons.md`
  after any correction (CLAUDE.md, "Task Management").

## Suggested order

1. **Set up the Mac and run the checks** (#134): this tells you
   whether the hooks work for macOS users at all.
2. **Settle the decisions that block publishing:**
   - the annotation key (#135);
   - what a Standard's statuses are (#136);
   - then the release (#137). Two things found while writing it up: the
     release notes (CHANGELOG `[Unreleased]`) are 163,120 characters,
     over GitHub's 125,000 limit for a release body, so `release.yml`
     would fail at its last step; and the hooks bullet of `CLAUDE.md`
     says `Skill` and `Agent` need nothing, while the hook gates them;
   - then npm (#138).
3. **File the upstream issues** (#139). Their texts link to
   main, which now has the work they cite.
4. **Then** the safety-layer design work (#141) and the PVC
   actions, P1 first.

To pick this up with Claude Code on the Mac, start with: "Read
tasks/HANDOFF.md and tasks/lessons.md, then work on issue #N."

## Open issues

All are sub-issues of #133, which lists them in the same groups.

**Mac and the decisions that block publishing**

| Issue | Priority | Title |
|---|---|---|
| #134 | P1 | Run the plugin hook and Bash classification tests on macOS in CI |
| #135 | P1 | Decide ACS-Q15: whether `acs` stays the Standard Agents annotation key |
| #136 | P1 | Define the statuses of a Standard version and the criteria to move between them |
| #137 | P1 | Cut plugin release 3.0.0 carrying Standard 1.2.0 and ontology 2.2.0 |
| #138 | P2 | Publish @synaptiai/acs-core to npm |

**Upstream (Standard Agent Specification)**

| Issue | Priority | Title |
|---|---|---|
| #139 | P1 | File the nine drafted proposals in the Standard Agent Specification repo |
| #140 | P2 | Triage undrafted Standard Agents findings and questions SA-Q01 to SA-Q30 |

**Safety layers**

| Issue | Priority | Title |
|---|---|---|
| #141 | P1 | Classify shell commands by a small accepted grammar, worst case outside it |
| #142 | P1 | Continue the security review loop on non-shell safety layers until it converges |
| #143 | P1 | Export the audit log head to a witness store the agent cannot write |
| #144 | P2 | Close or accept each host gap of the plugin hooks, SDK adapter and binding |
| #145 | P2 | Bound the rollback skill hook's git calls in time, as the plugin hooks do |
| #146 | P2 | Settle bash 5.3's brace-expansion rule in the records guard and skill hooks |
| #147 | P2 | Recognise signed-URL signatures in default redaction and the secret scan |
| #148 | P2 | Give token patterns one start rule: redact `mcp__x__ghp_...`, pass `task-...` |
| #149 | P2 | Update SECURITY.md §9.1 Planned Enhancements to match what ships |

**The Standard and its RFCs**

| Issue | Priority | Title |
|---|---|---|
| #150 | P1 | Implement Standard 1.2.0 §7.2 and §7.3 or make them informative |
| #151 | P2 | Decide the open questions of RFC-0001 to RFC-0010 |
| #152 | P2 | Answer ACS-Q10: attendance of a model-driven run that no trigger started |

**Standard Agents binding and mapping**

| Issue | Priority | Title |
|---|---|---|
| #153 | P2 | Run the Standard Agents binding in a real Standard Agents runtime |
| #154 | P2 | Redo or re-date the 319-row Standard Agents mapping against Standard 1.2.0 |
| #155 | P2 | Replace the digital twin example's copied workflows with qualified invokes |

**Site, documentation and compliance**

| Issue | Priority | Title |
|---|---|---|
| #156 | P2 | Upgrade astro in the docs site past advisory GHSA-r3h5-4585-7x3w |
| #157 | P2 | Give the docs site's figure-gap runs real margin under the 1800px limit |
| #158 | P2 | Define or drop the 12 proposed vision, audio and multimodal workflows |
| #159 | P2 | Close or assign an owner to each NIST AI RMF profile gap (G-01 to G-10) |
| #160 | P2 | Align the OASF safety proposal with Standard 1.2.0 and decide on submission |

**PVC review actions**

| Issue | Priority | Title |
|---|---|---|
| #161 | P1 | PVC HF-101: Give operators an incident view, a runbook and a tabletop recipe |
| #162 | P1 | PVC HF-102: Gate manual overrides and make approval bypasses visible |
| #163 | P1 | PVC HF-103: Measure explanation faithfulness and ground explain outputs |
| #164 | P1 | PVC ORG-201: Name policy owners, enforce review and define policy rollback |
| #165 | P1 | PVC GOV-202: Record refusals and define an audit review procedure |
| #166 | P1 | PVC ECON-301: Publish hook latency budgets, timeouts, storage and restore window |
| #167 | P1 | PVC ECON-302: Rank defects by failure class and benchmark 1.2 safety controls |
| #168 | P1 | PVC SEC-401: Add protected-path and allowed-capability policies for calls |
| #169 | P1 | PVC SEC-402: Separate data from instructions and gate tainted input |
| #170 | P1 | PVC CTRL-501: Add loop cooldowns, a run budget and a liveness watcher |
| #171 | P1 | PVC ASSUR-601: Write a linked safety case and state residual risks |
| #172 | P1 | PVC ASSUR-602: Monitor audit invariants and verify logs at session end |
| #173 | P1 | PVC DG-701: Set retention by risk tier and restrict audit file access |
| #174 | P1 | PVC ETH-801: Document who sets trust weights, harm scenarios and appeals |
| #175 | P1 | PVC ECO-901: Publish one staged 1.2 adoption path and per-domain starters |

