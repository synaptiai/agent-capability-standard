# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Validate workflows against the ontology (CI runs this in strict mode)
```bash
python tools/validate_workflows.py --strict
```

### Validate the domain workflow catalogs and examples (CI runs these in strict mode)
```bash
for c in schemas/workflows/*.yaml examples/*.workflow_catalog.yaml; do python tools/validate_workflows.py --catalog "$c" --strict; done
```

### Validate domain profiles against schema
```bash
python tools/validate_profiles.py
```

### Validate skill file references (no phantom paths)
```bash
python tools/validate_skill_refs.py
```

### Validate ontology graph (orphans, cycles, symmetry)
```bash
python tools/validate_ontology.py
```

### Validate the five canonical schemas designated by spec §6.1
```bash
python tools/validate_canonical_schemas.py
```

### Validate RFC structure against GOVERNANCE requirements
```bash
python tools/validate_rfcs.py
```

### Print the deny rules that keep the agent from the layer's records
```bash
python3 -I grounded_agency/layer_records.py [PROJECT_DIR]
```
It prints `permissions.deny` and `sandbox.filesystem.denyWrite` settings
for the project, every path literal and absolute; make them again after
`git worktree add` or a submodule's first checkout.

### Validate constraints.txt agrees with pyproject.toml
```bash
python tools/validate_constraints.py
```

### Validate documentation links (no dangling cross-references)
```bash
python tools/validate_doc_links.py
```

### Validate YAML utility sync (safe_yaml.py ↔ yaml_util.py)
```bash
python tools/validate_yaml_util_sync.py
```

### Validate transform mapping_ref paths (no broken refs)
```bash
python tools/validate_transform_refs.py
```

### Validate benchmark deps against ontology
```bash
python tools/validate_benchmark_deps.py
```

### Sync skill-local schemas and bundled catalogs from their sources
```bash
python tools/sync_skill_schemas.py          # write what changed
python tools/sync_skill_schemas.py --check  # CI: fail on drift
```

### Regenerate the runtime conformance fixtures
```bash
python scripts/gen_runtime_fixtures.py          # after editing the fixtures there
python scripts/gen_runtime_fixtures.py --check  # CI: fail on drift
```
The 1.1 fixtures are defined in that script; each Standard 1.2 workstream
adds its fixtures in its own `scripts/runtime_fixtures/<workstream>.py`
(`register(add)`). Every fixture states its catalog's `header` (a version or
`null`) and is checked against
`tests/conformance/runtime/schema/fixture.schema.json`.

### Regenerate the call-sequence and binding conformance fixtures
```bash
python scripts/gen_call_fixtures.py          # after editing the fixtures there
python scripts/gen_call_fixtures.py --check  # CI: fail on drift
```
These are the safety-layer fixtures of class SL (Standard 1.2.0 §10.4),
`tests/conformance/bindings/*.json` and `tests/conformance/calls/*.json`;
the Python runners (`tests/test_binding_fixtures.py`,
`tests/test_call_fixtures.py`) and the Standard Agents binding's tests read
them in place.

### Regenerate the trigger vectors
```bash
python scripts/gen_trigger_vectors.py          # after editing the cases there
python scripts/gen_trigger_vectors.py --check  # CI: fail on drift
```
The vectors of `tests/conformance/triggers/` (fire times, overlap, attendance,
event acceptance; STANDARD v1.2 §5.10.2) are computed with Python's zoneinfo,
independently of the core; `fire_times.json` names its tzdata release, and
`--check` ignores a different release name when every value agrees.

### Regenerate the TypeScript package's ontology table and the approval digest vectors
```bash
python scripts/gen_standard_agents_binding.py          # after changing the ontology
python scripts/gen_standard_agents_binding.py --check  # CI: fail on drift
```
It writes `packages/acs-core/src/ontology.gen.ts`, the Standard Agents
annotation schema and the approval digest vectors,
`tests/conformance/approval/digests.json`, from the reference executor; the
package's tests read the vectors in place.

### Regenerate the strict JSON Schema rendering of the capability contracts
```bash
python scripts/gen_capability_json_schemas.py          # after changing a contract in the ontology
python scripts/gen_capability_json_schemas.py --check  # CI: fail on drift
```

### Check the TypeScript package (in `packages/acs-core/`)
```bash
cd packages/acs-core
npm ci             # install the exact versions in package-lock.json
npm run build:wasm # build core/ for WebAssembly into dist/acs_core.wasm
npm run build      # compile to dist/ and bundle dist/documents.json
npm run check      # type-check
npm test           # vitest; reads tests/conformance/ in place, and replays the fixtures through the WebAssembly core
```
`build:wasm` needs the `wasm32-unknown-unknown` target of the toolchain
`RUSTUP_TOOLCHAIN` names (`rustup target add wasm32-unknown-unknown
--toolchain <toolchain>`). The package is published to npm from a tag
`acs-core-vX.Y.Z` on `main` by `.github/workflows/publish-npm.yml`, when the
repository variable `NPM_PUBLISH_ENABLED` is `true` and the secret
`NPM_TOKEN` is set (a dry run otherwise).
A host-neutral TypeScript module (one that imports nothing from
`@standardagents/spec`) goes in `packages/acs-core/src/` and its tests in
`packages/acs-core/test/`; code that reads or describes Standard Agents state
stays in `examples/standard_agents/src/acs/`. No conformance file is copied
under `examples/standard_agents/test/fixtures/`.

### Check the Standard Agents binding (TypeScript, in `examples/standard_agents/`)
```bash
(cd packages/acs-core && npm ci --ignore-scripts && npm run build:ts)
cd examples/standard_agents
npm ci          # install the exact versions in package-lock.json
npm run check   # type-check against the published @standardagents/spec types
npm test        # vitest
```
The binding depends on the package with `file:../../packages/acs-core` and
imports its built `dist/` (the plain-TypeScript entry, so `build:ts` is
enough): the first line builds it.

### Run conformance tests (optional, local only)
```bash
python scripts/run_conformance.py
```

### Setup Python environment (one-time)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" -c constraints.txt
```

The package is built with maturin: the validator and the executor live in
the Rust crate under `core/` and
compiles into `grounded_agency._core`, so a Rust toolchain (rustc >= 1.88) is
required. After changing Rust code, re-run the `pip install -e` line to rebuild
the extension.

### Rust core checks
```bash
cd core
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo clippy --all-targets --features python -- -D warnings
cargo clippy --all-targets --features wasm -- -D warnings
cargo test
cargo test --features wasm --test wasm
```

CI pins the toolchain that runs these (`RUST_TOOLCHAIN` in
`.github/workflows/ci.yml`), as `constraints.txt` pins ruff.

Install the `dev` extra rather than individual packages, and pass
`-c constraints.txt` — that file pins the exact tool versions CI runs, so the
local formatter matches CI's exactly. Without it, `ruff>=0.17,<0.18` resolves
to whatever 0.17.x is newest and a reformat can appear in CI that never
appeared locally.

The bounds in `pyproject.toml` are the *supported range*; `constraints.txt` is
the *one version CI runs*. The range caps each dependency at the major this
repo has been verified against, so a new major is a deliberate bump — run the
suite on it, then raise the cap. Note the range still admits patch and minor
drift: two installs a week apart are not identical unless both use the
constraints file.

## Documentation site

The site in `site/` is an Astro project built from the repository's own files.
Node is pinned in `site/.nvmrc`. `.github/workflows/site.yml` runs the same
commands on pushes and pull requests to main and on manual runs, and deploys
pushes to main to Cloudflare Pages once the `SITE_DEPLOY_ENABLED` repository
variable is `true`.

```bash
cd site
npm ci          # install the exact versions in package-lock.json
npm run check   # type-check, colour contrast, design data, no hand-typed counts
npm test        # vitest; also builds the site into a temporary directory
npm run build   # build, Pagefind index, then scripts/check-dist.mjs
npm run check:axe  # after a build: axe over every built page (CI runs it; slow)
npm run dev     # local server; search works only on a built site (npm run preview)
```

`check:axe` needs a Chromium: Playwright's own, or the binary `ACS_CHROMIUM`
names. For a quick run on the pages a change touches:
`node scripts/check-axe.mjs --paths /guides/standard-agents/`. It fails on any
axe violation, for example a Markdown table whose header cell is empty.

`check:axe` then runs `scripts/check-runs.mjs`, the figure-gap sweep: a page
in the enforced scope (`site/src/lib/runs.ts`: every generated template, the
current Standard and a few guides) fails with a run of text longer than
1800px at 1440px wide that holds no figure and is not an exempt run there.
Line breaks differ between Chromium builds, so a run within a few lines of the
limit can pass with one and fail with another. CI measures with the headless
shell of the revision the pinned `playwright` names: install it with
`npx playwright install chromium` and leave `ACS_CHROMIUM` unset to measure as
CI does, for example `node scripts/check-runs.mjs --paths /spec/1.2.0/ --all`.

`npm run build` fails when a Markdown link or `#anchor` does not resolve, when
rendered heading ids differ from GitHub's ids for the source, and, in
`scripts/check-dist.mjs`, when a link in the built HTML, the Markdown copies or
`llms-full.txt` does not resolve, a raw `.md` link remains, a page has no
Markdown copy, a copy is listed in no section's `<section>/llms.txt` (the root
`llms.txt` links each section's file), the sitemap differs from the built
pages, or the files under `/api/v1/` differ from the paths `/openapi.json`
describes.

The sitemap's `lastmod` dates come from `git log`, so the build needs the full
history: it fails in a shallow clone (CI checks out with `fetch-depth: 0`).

The build also writes a Cloudflare Pages worker into the output: _worker.js
(advanced mode, bundled from `site/src/worker/` by
`site/src/lib/worker-build.ts`) and _routes.json beside it. The worker serves
a page's Markdown copy to clients that prefer `text/markdown` and to AI
agents, answers `<page>.md`, returns Markdown and problem+json 404s to
non-browsers, adds Link headers, and runs the read-only docs MCP server at
`/mcp`. `site/src/worker/entry.ts` says why advanced mode and which paths skip
the worker. To try it after `npm run build`:
```bash
npx wrangler@4.160.0 pages dev dist --ip 127.0.0.1   # the version the deploy job pins
```

Rules:
- **No YAML file under `site/`.** `tests/test_core_yaml.py` checks every
  tracked YAML file outside `.github/` as an Agent Capability Standard
  document. Use JSON or TypeScript instead.
- **Every new public `.md` file needs a route.** These get one automatically,
  so do not add a row for them: a capability's `skills/<id>/SKILL.md`,
  `spec/RFC-NNNN-*.md`, `spec/STANDARD-v*.md`, and a domain profile's
  `docs/domains/<domain>/README.md`. A composed skill's `SKILL.md` needs an
  entry in `COMPOSED_SKILLS` in `site/src/data/skills.ts`. Any other public
  `.md` file needs a row in `site/src/lib/routes.ts`, or an entry in its
  `EXCLUSIONS` list. Once the file is tracked by git, the build and the tests
  fail with `<path>: public Markdown with no route`; a second row for an
  automatic route fails with `routed twice`.
- **A workflow id a domain profile lists that no catalog defines** must be in
  `PROPOSED_WORKFLOWS` in `site/src/data/proposed-workflows.ts`, or the build
  fails. Remove it from there once a catalog defines it.

The site tests read the live repository (the ontology, workflow catalogs,
profiles, `CLAUDE.md`, `skills/README.md`, the Standard), so a change there can
fail `npm test` in `site/`. When adding a capability (see below), the site
needs:
- the layer table in this file and the **Total** line in `skills/README.md`
  updated (the tests compare the ontology with both);
- the capability's two-letter symbol added, in layer order, to the list in
  `site/test/views.test.ts` ("periodic table symbols"); the failing test prints
  the symbol the site computed.

Nothing else in the site needs editing: pages, counts and the sidebar come from
the ontology. A release (new version in `.claude-plugin/plugin.json` and a
`CHANGELOG.md` section) needs no site change; the site reads the version from
`plugin.json`.

## Architecture

This is a **Claude Code plugin** that defines a formal capability ontology for AI agents with **36 atomic capabilities** across **9 cognitive layers**, plus 12 composed workflow patterns.

### Core Philosophy: Grounded Agency

Every agent action must be:
1. **Grounded** — backed by evidence anchors, not hallucination
2. **Auditable** — with provenance and lineage
3. **Safe** — mutations require checkpoints
4. **Composable** — typed contracts between capabilities

### Key Files

| File | Purpose |
|------|---------|
| `schemas/capability_ontology.yaml` | Master ontology defining all 36 capabilities with I/O contracts, risk levels, and edges |
| `schemas/workflow_catalog.yaml` | Reference workflows that compose capabilities |
| `schemas/profiles/*.yaml` | Domain-specific profiles (trust weights, risk thresholds, checkpoint/evidence policies) |
| `schemas/profiles/profile_schema.yaml` | Schema defining structure for domain profiles |
| `skills/<name>/SKILL.md` | Individual skill implementations (flat structure, no nesting) |
| `hooks/hooks.json` | Claude Code hooks for safety enforcement |
| `templates/SKILL_TEMPLATE_ENHANCED.md` | Template for creating new skills |
| `_archive/` | Archived files from v1 (99-capability model) |
| `schemas/interop/oasf_mapping.yaml` | OASF skill-code-to-capability mapping |
| `schemas/interop/standard_agents_mapping.yaml` | Standard Agents binding conventions (capability rulings, anchor forms, identity map) |
| `grounded_agency/remote_writes.py` | The plugin's MCP server for remote writes (push, tags, pull requests, releases, issues) to the origin recorded for the project; standard library only, Python 3.9 syntax |
| `schemas/generated/capability_contracts.schema.json` | The capability contracts as strict JSON Schema 2020-12 (generated) |
| `docs/guides/MODALITY_HANDLING.md` | Modality handling guide (vision, audio, multimodal) |
| `docs/proposals/OASF_SAFETY_EXTENSIONS.md` | OASF safety extension proposal |

### Layer Architecture

Capabilities are organized into 9 cognitive layers (defined in ontology):

| Layer | Purpose | Count | Capabilities |
|-------|---------|-------|--------------|
| PERCEIVE | Information acquisition | 4 | retrieve, search, observe, receive |
| UNDERSTAND | Making sense of information | 6 | detect, classify, measure, predict, compare, discover |
| REASON | Planning and analysis | 4 | plan, decompose, critique, explain |
| MODEL | World representation | 5 | state, transition, attribute, ground, simulate |
| SYNTHESIZE | Content creation | 3 | generate, transform, integrate |
| EXECUTE | Changing the world | 3 | execute, mutate, send |
| VERIFY | Correctness assurance | 5 | verify, checkpoint, rollback, constrain, audit |
| REMEMBER | State persistence | 2 | persist, recall |
| COORDINATE | Multi-agent and user interaction | 4 | delegate, synchronize, invoke, inquire |

### Skill Structure

Skills are at `skills/<skill-name>/SKILL.md` (flat structure, not nested by category). Each skill has:

- YAML frontmatter with `name` (the directory name), `description`, `allowed-tools` and `agent` type; each key's owner (Agent Skills, Claude Code or ACS) is in `skills/README.md`, and no skill declares a `layer` (the ontology gives every capability's layer)
- Intent and success criteria
- Input/output contracts with `domain` parameter for specialization
- Procedure steps with evidence grounding
- Safety constraints from ontology

### Domain Parameterization

The 36-capability model uses **domain parameters** instead of domain-specific variants:

| Old (99 model) | New (36 model) |
|----------------|----------------|
| `detect-anomaly`, `detect-entity` | `detect` with `domain: anomaly`, `domain: entity` |
| `estimate-risk`, `estimate-impact` | `measure` with `domain: risk`, `domain: impact` |
| `forecast-risk`, `forecast-time` | `predict` with `domain: risk`, `domain: time` |

### Hooks

The plugin enforces safety through Claude Code hooks:
- **PreToolUse (every tool, `onFailure: "block"`, timeout 30 s)**: reads Claude Code's JSON payload; classifies the call (a tool the SDK mapper maps to a capability needing neither a checkpoint nor approval, such as Read, Grep, Skill or Agent, needs nothing; Bash: every call is a gated mutate unless the hook verifies Claude Code's strict sandbox for it from the managed, user, project and local settings files (from user or managed scope: `sandbox.enabled`, `failIfUnavailable`, `network.strictAllowlist` true, `allowUnsandboxedCommands` false, no excluded command, `allowRead`, IP or loopback allowlist entry or other route out, denials of writes to the records, settings files, user configuration directory, hook scripts and audit key and of reads of the audit key and the user's credentials; project and local files may only narrow the sandbox and name no command run outside it; no `dangerouslyDisableSandbox`; it cannot see `--settings`, and no environment variable says the sandbox is on), and under it by command, a command over 4096 bytes is gated before it is read, its words dequoted as bash does: read-only commands and `git stash list|show` need nothing, `git stash create` takes a checkpoint, `git stash pop|apply <commit>` restores a checkpoint recorded (an entry in `<git dir>/acs/checkpoints/commits/`, outside the work tree, for a call run in the project's repository) and needs nothing; any other restore is a gated call; the plugin's remote-write MCP tools (`mcp__plugin_agent-capability-standard_remote__*`) are bound as a gated mutate; any other tool, other MCP tools, Monitor and PowerShell included, is unbound: a gated mutate); every call is refused F504 while a file under `<git dir>/acs/` has a hard link outside the records, and every call it does not let pass outright (a gated call, a `git stash create` put to a person, a restore of a recorded checkpoint) while a file of the project's records has one (counted with perl, or find, awk and GNU/BSD stat; without them every call is R407 while `<git dir>/acs/` exists, and every gated call otherwise); the boundary is the permission deny rules `python3 -I grounded_agency/layer_records.py [PROJECT_DIR]` prints, and the hook's reading of a call's text is an advisory early refusal; a gated call that names the layer's records (`checkpoint.ok`, `.claude/checkpoints`, `acs/checkpoints`, in any letter case, with `//`, `./` and `x/../` read as a path reads them) is refused F504; every other gated call uses up the checkpoint marker (one marker per call, untracked by git and within `ACS_CHECKPOINT_MAX_AGE`, filed under `.claude/checkpoints/used/`, F501) and is asked for approval (`ask`, F502) in permission modes default, acceptEdits and plan, and blocked F502 in the others unless `ACS_HOOK_APPROVAL=off`; a failure of the hook blocks with R407
- **PostToolUse (Bash)**: a successful `git stash create` enters its commit in `<git dir>/acs/checkpoints/commits/` and writes the checkpoint marker (expiry `ACS_CHECKPOINT_MAX_AGE`, at most 30 minutes); a marker it replaces is filed under `.claude/checkpoints/ended/`
- **Stop, StopFailure, UserPromptSubmit, SessionStart, SessionEnd**: files the marker under `.claude/checkpoints/ended/` (a turn or a session ended or started: an execution boundary of the hooks' scope, the project directory); a rollback can still restore its commit
- **PostToolUse and PostToolUseFailure (every tool)**: Log every tool call to `.claude/audit.log` as an action record (Standard 1.2.0 §6.4): time, status (`executed` or `failed`), tool, call id, and under `details` the event, the skill name on a `Skill` call and a SHA-256 digest of the input in place of the input; each line is HMAC-chained under the key in `~/.config/acs/audit.key`, else `AUDIT_HMAC_KEY` (without a key the line is written unsigned and the hook exits 1; `tools/verify_audit_log.py` checks the chain), and each line names the layer and its configuration (`recorded_by`: version, sha256 of `hooks/hooks.json`, effective settings)

### Ontology Edge Types

Relationships between capabilities (in `capability_ontology.yaml`):
- `requires`: Hard dependency — a `from` step must run before the target (e.g. `checkpoint` → `mutate`/`send`/`rollback`), else V102
- `soft_requires`: Recommended — any one incoming source must run before the target, else warning W601
- `enables`: Unlocks other capabilities
- `precedes`: Ordering only — when both capabilities are present, the source must come first (V102)
- `conflicts_with`: May not share a `parallel_group` (F504); running them in sequence is allowed
- `alternative_to`: Substitutable capabilities
- `specializes`: Parent-child inheritance

See [spec/EDGE_TYPES.md](spec/EDGE_TYPES.md) for full edge type documentation.

## Creating New Capabilities

When adding a new atomic capability, you MUST complete ALL of these steps:

### 1. Update the Ontology
- Add capability node to `schemas/capability_ontology.yaml` with full input/output schemas
- Add edges connecting to related capabilities (`requires`, `soft_requires`, `enables`)
- Update the layer's `capabilities` array in the `layers` section
- Update the `meta.description` count (e.g., "36 atomic capabilities" → "37 atomic capabilities")

### 2. Create the Skill
- Use `templates/SKILL_TEMPLATE_ENHANCED.md` as the starting template
- Place skill at `skills/<name>/SKILL.md` (kebab-case name)

### 3. Update ALL Capability Count References
Search and update capability counts in these files:
- `CLAUDE.md` — Architecture section and layer table
- `README.md` — Multiple references throughout
- `spec/WHITEPAPER.md` — Summary and derivation sections
- `docs/GROUNDED_AGENCY.md` — Capability ontology section
- `docs/FAQ.md` — Capability count references
- `docs/GLOSSARY.md` — Layer descriptions
- `docs/WORKFLOW_PATTERNS.md` — Pattern references
- `docs/TUTORIAL.md` — Tutorial references
- `docs/methodology/EXTENSION_GOVERNANCE.md` — Governance references
- `skills/README.md` — Layer counts and totals
- `.claude-plugin/plugin.json` — Description field

**Tip:** Use `grep -r "N atomic capabilit" .` and `grep -r "N capabilities" .` to find all references (where N is the old count).

### 3a. Update the Documentation Site
- Add the capability's two-letter symbol, in layer order, to the "periodic table symbols" list in `site/test/views.test.ts` (the failing test prints the symbol the site computed)
- The site tests compare the ontology with the layer table in this file and the **Total** line in `skills/README.md`, so step 3 must be complete
- Run `npm test` in `site/` (see "Documentation site" above)

### 4. Validate
```bash
python tools/validate_workflows.py
python tools/validate_profiles.py
python -c "import yaml; yaml.safe_load(open('schemas/capability_ontology.yaml'))"
```

### 5. Update Workflow Catalog (if adding workflow patterns)
- Add workflow to `schemas/workflow_catalog.yaml`
- Update workflow count in `skills/README.md`

### 6. Generate Local Schema
```bash
python tools/sync_skill_schemas.py
```
This regenerates `skills/<name>/schemas/output_schema.yaml` from the ontology
(removing orphaned generated ones), regenerates the skill-bundled
`skills/*/reference/workflow_catalog.yaml` copies from
`schemas/workflow_catalog.yaml` with their schema paths rewritten, and keeps the
vendored schema copies in sync. `--check` fails on drift (CI); `--dry-run` lists
what would change.

Then regenerate the Standard Agents binding's ontology table and annotation
schema, and the strict JSON Schema rendering, which list every capability:
```bash
python scripts/gen_standard_agents_binding.py
python scripts/gen_capability_json_schemas.py
```

## Releasing

When creating a new release, update the version in `.claude-plugin/plugin.json` to match the new tag before committing. This file does not auto-sync with git tags.

A version change also updates the Versions table in `spec/ROADMAP.md` (and its sentence "Plugin X implements Standard Y"); a Standard or ontology version change also updates `meta.agent_capability_standard` in `schemas/interop/oasf_mapping.yaml` and the header of `docs/integrations/oasf_coverage.md`; a Python package version change updates both `pyproject.toml` and `__version__` in `grounded_agency/__init__.py`. `tests/test_version_lines.py` fails otherwise.

Give the release its `## [vX.Y.Z] — date` section in `CHANGELOG.md`, then push an annotated tag `vX.Y.Z` on `main`. `.github/workflows/release.yml` publishes the GitHub Release with that section as its notes (a `-suffix` tag is a pre-release). Where the tag cannot be pushed, run the workflow by hand on `main` with the tag as its input: it creates the annotated tag on `main`'s head, then publishes the Release. It refuses a tag that does not match `plugin.json` or has no section, or (run by hand) one that already exists; check first with:
```bash
python scripts/release_notes.py vX.Y.Z
```

The plugin release that carries the renamed skills (`/capability-gap-analysis`,
`/digital-twin-sync-loop`, ACS-59) changes two slash commands, so under
SemVer it is a plugin MAJOR version (3.0.0). The TypeScript package has its
own tag, `acs-core-vX.Y.Z` on `main` (its version in
`packages/acs-core/package.json`), which `.github/workflows/publish-npm.yml`
publishes.

## Claude Agent SDK Integration

The `grounded_agency/` Python package provides SDK integration:

### Install
```bash
pip install -e ".[sdk]"  # From repo root
```

### Run SDK integration tests
```bash
pytest tests/test_sdk_integration.py -v
```

### Run examples
```bash
python examples/grounded_agent_demo.py
python examples/checkpoint_enforcement_demo.py
python examples/capability_skills_demo.py
```

### Key Components

| Component | Purpose |
|-----------|---------|
| `GroundedAgentAdapter` | Main entry point - wraps SDK options with safety layer |
| `CapabilityRegistry` | Loads and queries `capability_ontology.yaml` |
| `ToolCapabilityMapper` | Maps SDK tools to capability metadata |
| `CheckpointTracker` | Manages checkpoint lifecycle for mutation safety |
| `EvidenceStore` | Collects evidence anchors from tool executions |
| `WorkflowRunner` | Runs a workflow on the core's executor, dispatching actions to a `Host` ([guide](docs/guides/RUNNING_WORKFLOWS.md)) |

### Example Usage

```python
from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

adapter = GroundedAgentAdapter(GroundedAgentConfig(strict_mode=True))
adapter.create_checkpoint(["*.py"], "Before changes")
options = adapter.wrap_options(base_options)
```

See [docs/integrations/claude_agent_sdk.md](docs/integrations/claude_agent_sdk.md) for full documentation.

## Safety Model

High-risk capabilities (`mutate`, `send`) have:
- `mutation: true`
- `requires_checkpoint: true`
- `requires_approval: true`
- `risk: "high"`

Medium-risk capabilities (`execute`, `rollback`, `delegate`, `synchronize`, `invoke`) have:
- `risk: "medium"`
- `execute` also has `requires_approval: true`

Other mutation capabilities (`checkpoint`, `audit`, `persist`) have:
- `mutation: true`, but need no checkpoint
- Lower risk levels (low or medium)
- `audit` also has `mutation_overridable: true`, so a step may declare `mutation: false`

A checkpoint must run before `mutate`, `send` and `rollback` (`requires_checkpoint`
or a `checkpoint` `requires` edge); on a tool-calling host each gated call uses
up one checkpoint (STANDARD 1.2.0 §5.18). Safety flags on workflow steps are optional and
inherit from the ontology; a step value weaker than the ontology's is ignored with
warning W602, and a stricter one takes effect (a step that raises
`requires_checkpoint` with no checkpoint before it is F501).

These are enforced structurally—not by convention.

## Workflow Orchestration

### 1. Plan Mode Default

- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately - don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy

- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop

- After ANY correction from the user: update 'tasks/lessons.md" with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done

- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)

- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing

- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests - then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **PLan First**: Write plan to 'tasks/todo.md" with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to tasks/todo.md*
6. **Capture Lessons**: Update "tasks/lessons.md" after corrections

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.