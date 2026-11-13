# AGENTS.md

Instructions for coding agents working on this repository. The full guide,
with the reasons behind each rule, is [CLAUDE.md](CLAUDE.md); read it before
a change of any size. Agents that want to *use* the standard rather than
change it should start at <https://acs.synapti.ai/agents.md>.

## What this repository is

The Agent Capability Standard: a capability ontology
(`schemas/capability_ontology.yaml`), workflow catalogs
(`schemas/workflow_catalog.yaml`, `schemas/workflows/`), domain profiles
(`schemas/profiles/`), one skill per capability (`skills/<name>/SKILL.md`),
the normative specification (`spec/STANDARD-v*.md`), a validator and executor
in Rust (`core/`) with Python bindings (`grounded_agency/`), and the
documentation site (`site/`).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" -c constraints.txt   # builds the Rust core; needs rustc >= 1.88
```

## Checks CI runs

```bash
python tools/validate_workflows.py --strict
for c in schemas/workflows/*.yaml examples/*.workflow_catalog.yaml; do python tools/validate_workflows.py --catalog "$c" --strict; done
python tools/validate_profiles.py
python tools/validate_skill_refs.py
python tools/validate_ontology.py
python tools/validate_canonical_schemas.py
python tools/validate_rfcs.py
python tools/validate_constraints.py
python tools/validate_doc_links.py
python tools/validate_yaml_util_sync.py
python tools/validate_transform_refs.py
python tools/validate_benchmark_deps.py
python tools/sync_skill_schemas.py --check
python scripts/gen_runtime_fixtures.py --check
pytest tests/ -v --tb=short
```

Rust core, from `core/`:

```bash
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo clippy --all-targets --features python -- -D warnings
cargo test
```

Documentation site, from `site/` (Node version in `site/.nvmrc`):

```bash
npm ci
npm run check
npm test
npm run build
npm run check:axe
```

## Rules that break the build when missed

- Adding a capability touches the ontology, a new skill, every capability
  count in the docs and the site's symbol list. Follow "Creating New
  Capabilities" in CLAUDE.md step by step.
- After editing the ontology or the workflow catalog, run
  `python tools/sync_skill_schemas.py` to regenerate the skill-local copies.
- No YAML file under `site/`. Every new public Markdown file needs a route in
  `site/src/lib/routes.ts` or an entry in its `EXCLUSIONS` list.
- Do not type counts (capabilities, layers, workflows) into site code; the site
  reads them from the data.
- `mutate`, `send` and `rollback` need a `checkpoint`
  step before them; the validator rejects a workflow without one.

## Conventions

- Conventional commit messages (`feat:`, `fix:`, `docs:`, `chore:`).
- Releases: see "Releasing" in CLAUDE.md.
- Report problems in the GitHub issue tracker.
