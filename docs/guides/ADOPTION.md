# Adopting the Standard

This guide is the adoption path for Agent Capability Standard 1.2. It has
five stages. Each stage adds one component, names the conformance level or
class that component can claim, and ends with a check you can run. You can
stop after any stage: each one is useful on its own, and a later stage does
not change what an earlier one checks.

| Stage | Component | Level or class | Exit check |
|-------|-----------|----------------|------------|
| 1. Validate in CI | The validator (`tools/validate_workflows.py`) | L1 to L4 rank validators | Every catalog passes `--strict`, with a version header |
| 2. Gate Claude Code sessions | The plugin's hooks | None: the hooks claim no class | A gated call with no checkpoint is refused, and the audit log verifies |
| 3. Gate an agent's tool calls | The Python SDK adapter or the Standard Agents binding | SL, the safety-layer class | The binding and call-sequence fixtures pass under a conformance statement |
| 4. Run workflows | The executor (`WorkflowRunner`) or your own | EX, the executor class | The runtime fixtures pass |
| 5. Apply domain rules | Domain profiles and the authority trust model | Applied by an SL layer or an EX executor | The profiles validate and the layer loads them |

The levels and classes are defined in
[STANDARD-v1.2.0 §10.1](../../spec/STANDARD-v1.2.0.md#101-conformance-levels).
Levels L1 to L4 rank validators only. SL and EX are separate classes: a
safety layer validates no catalog, and a validator checks no call and runs
no workflow. A team does not "reach L2" or "reach L3"; a validator conforms
at a level, and a layer or an executor conforms to a class.

## Install

The Python package is not on PyPI. Install it from a clone of the
repository. You need Python 3.14 or later and a Rust toolchain, version
1.88 or later, because the install compiles the validator and executor
core:

```bash
git clone https://github.com/synaptiai/agent-capability-standard.git
cd agent-capability-standard
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" -c constraints.txt
```

Stage 3 with the Standard Agents binding also needs Node; the binding's
guide says how to build it
([Standard Agents interoperability](../integrations/standard_agents.md)).

## Stage 1: validate workflows in CI

Start here. The validator reads your workflow catalogs and needs no change
to how your agents run.

1. Put a version header on the first line of each catalog:
   `# Standard version: 1.2.0`. A catalog with no version is reported as
   W605 ([§11.5](../../spec/STANDARD-v1.2.0.md#115-version-declaration)).
2. Run the validator in strict mode, which fails on warnings as well as
   errors:

   ```bash
   python tools/validate_workflows.py --catalog path/to/catalog.yaml --strict
   ```

3. Fix what it reports. Where the validator cannot infer the type of a
   binding, it reports B204 and asks for a type annotation on that binding.
   Each finding carries a hint, and `tools/validator_suggestions.json`
   holds the patches it suggests.
4. Add the same command to your CI, one run per catalog.

**Exit check:** every catalog passes with `VALIDATION PASS` under
`--strict`.

## Stage 2: gate Claude Code sessions with the plugin's hooks

If your agents run in Claude Code, install the plugin
([Installation](../../README.md#installation)). Its hooks apply the
tool-calling rules of
[§5.18](../../spec/STANDARD-v1.2.0.md#518-tool-calling-hosts) where Claude
Code lets them:

- Before each tool call, the pre-tool-use hook classifies the call. A read
  needs nothing. A call that changes something (an edit, a write, a Bash
  command it cannot show to be read-only, an MCP tool) needs a checkpoint,
  which it uses up, and asks for a person's approval.
- A `git stash create` takes the checkpoint, and a restore of a recorded
  checkpoint runs as a rollback.
- After each tool call, a hook writes an action record to
  `.claude/audit.log`, each line chained to the one before by an HMAC.
- Under the strict sandbox, the agent's commands cannot use git's or gh's
  credentials. A push, a pull request, a merge, a release or an issue goes
  through the plugin's remote-write tools instead, and each one is a gated
  change a person approves
  ([Remote writes](../../hooks/README.md#remote-writes)).

The hooks claim no conformance class. Claude Code leaves gaps they cannot
close, and [SECURITY.md §5.5](../../spec/SECURITY.md#55-hooks-and-the-safety-layer-class)
lists them. Until Claude Code's strict sandbox is set up in your user
settings, the hooks treat every Bash call as a change, so Bash calls are
refused ([The strict sandbox](../../hooks/README.md#the-strict-sandbox)).
To set it up, run `/grounded-setup` in Claude Code, in each project you
use the plugin in. The first time, it gives you a command to run in a
terminal outside Claude Code; that command shows the settings it would add
and writes them only when you agree
([Setting up the sandbox](../../hooks/README.md#setting-up-the-sandbox)).

**Exit check:** in a session with the plugin and the sandbox set up, an
edit made with no checkpoint is refused with F501, and
`python tools/verify_audit_log.py` prints `INTEGRITY CHECK PASSED`.

## Stage 3: gate an agent's tool calls with a safety layer (class SL)

A safety layer applies §5.18 to the tool calls of an agent you build. Two
reference layers claim class SL:

- the Python SDK adapter, `grounded_agency.GroundedAgentAdapter`, for the
  Claude Agent SDK ([Claude Agent SDK](../integrations/claude_agent_sdk.md));
- the Standard Agents binding, in `examples/standard_agents/`
  ([Standard Agents interoperability](../integrations/standard_agents.md)).

Each layer has a conformance statement in
`tests/conformance/calls/statements/`. It says which calls the layer covers
and which it cannot see, how it obtains approval, and its host gaps
([§10.4](../../spec/STANDARD-v1.2.0.md#104-safety-layer-conformance)). A
layer conforms only in a mode that fails closed. For the Python adapter,
keep `strict_mode=True` and `approval="ask"`, the defaults:
`approval="off"` and `strict_mode=False` are outside class SL.

Run the fixtures for the layer you use:

```bash
# Python SDK adapter
pytest tests/test_binding_fixtures.py tests/test_call_fixtures.py
```

For the Standard Agents binding, the runners are `npm test` in
`packages/acs-core/` (after `npm ci` and `npm run build:wasm`) and in
`examples/standard_agents/` (after `npm ci`, with the package built by
`npm run build:ts`); the binding's README gives the full steps.

A layer of your own runs the same fixtures with a runner of its own and
publishes a statement that follows
`tests/conformance/calls/schema/statement.schema.json`
([Safety-layer conformance](../../spec/CONFORMANCE.md#safety-layer-conformance-class-sl)).

**Exit check:** every binding fixture and call-sequence fixture that your
statement's features cover passes, and the statement names the features
the layer lacks, whose fixtures it skips.

## Stage 4: run workflows with an executor (class EX)

An executor runs a validated workflow step by step and enforces the runtime
rules: checkpoints before mutations, approvals, waits, retries and failure
modes. The reference executor is in the Rust core, and Python drives it
through `grounded_agency.workflows.WorkflowRunner`
([Running workflows](RUNNING_WORKFLOWS.md)). It starts a run only when the
catalog validates.

Run the runtime fixtures:

```bash
pytest tests/test_runner.py
(cd core && cargo test --test runtime)
```

Another executor runs the fixtures in `tests/conformance/runtime/` with a
harness built from their schema, and its conformance statement names its
version, the Standard version and the extensions it implements
([Executor conformance](../../spec/CONFORMANCE.md#executor-conformance-class-ex),
[§10.5](../../spec/STANDARD-v1.2.0.md#105-executor-conformance)).

**Exit check:** every runtime fixture whose extensions the executor
implements passes.

## Stage 5: apply domain profiles and the trust model

A domain profile raises the safety flags of capabilities for one domain,
requires a person's approval above a risk level, sets grounding rules and a
minimum confidence for outputs, and limits where `send` may deliver
([§5.21](../../spec/STANDARD-v1.2.0.md#521-domain-profiles)). The safety
layers of stage 3 and the executor of stage 4 both apply profiles.

The authority trust model weighs evidence from several sources and resolves
conflicts between them
([§8](../../spec/STANDARD-v1.2.0.md#8-authority-trust-model)). A profile's
`trust_weights` adjust its static weights; `grounded_agency.trust` computes
the scores and resolutions.

```bash
python tools/validate_profiles.py
pytest tests/test_profiles.py tests/test_trust.py
```

**Exit check:** your profiles validate, and the layer loads them with no
error. The Python adapter refuses a configuration whose profile has an
error.

## Starting points for each domain

Each domain profile in `schemas/profiles/` can start an adoption. Copy the
profile, and the domain's workflow catalog where one exists, into your
project, then run stages 1 and 3 on them.

| Domain | Profile | Workflow catalog | Domain page |
|--------|---------|------------------|-------------|
| Audio | `schemas/profiles/audio.yaml` | None yet | [Audio](../domains/audio/README.md) |
| Data analysis | `schemas/profiles/data_analysis.yaml` | `schemas/workflows/data_analysis_workflows.yaml` | [Data analysis](../domains/data-analysis/README.md) |
| Healthcare | `schemas/profiles/healthcare.yaml` | `schemas/workflows/healthcare_workflows.yaml` | [Healthcare](../domains/healthcare/README.md) |
| Manufacturing | `schemas/profiles/manufacturing.yaml` | `schemas/workflows/manufacturing_workflows.yaml` | [Manufacturing](../domains/manufacturing/README.md) |
| Multimodal | `schemas/profiles/multimodal.yaml` | None yet | [Multimodal](../domains/multimodal/README.md) |
| Personal assistant | `schemas/profiles/personal_assistant.yaml` | `schemas/workflows/personal_assistant_workflows.yaml` | [Personal assistant](../domains/personal-assistant/README.md) |
| Vision | `schemas/profiles/vision.yaml` | None yet | [Vision](../domains/vision/README.md) |

The domain catalogs in the repository declare Standard 1.1.0 in their
headers. In your copy, change the first line to
`# Standard version: 1.2.0`; each of the four catalogs passes strict
validation with that header.

Stage 1, for the healthcare starter:

```bash
python tools/validate_workflows.py --catalog healthcare_workflows.yaml --strict
```

Stage 3 with the Python adapter: apply the profile to every call the
adapter covers. Profiles need `approval="ask"`, the default.

```python
from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig

adapter = GroundedAgentAdapter(
    GroundedAgentConfig(profiles=["healthcare.yaml"])
)
```

Then run the stage 3 fixtures above. With the Standard Agents binding, pass
the profiles to `configureLayer({ profiles })` in the module that defines
the agent's tools
([Sends and memory](../integrations/standard_agents.md#sends-and-memory)).
