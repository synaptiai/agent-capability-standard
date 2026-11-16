# @synaptiai/acs-core

The Agent Capability Standard core for TypeScript, with two entries:

- `@synaptiai/acs-core`, plain TypeScript: the capability ontology as types
  and data, effective safety flags, canonical JSON and approval digests,
  secret redaction, tool binding records, and capability outputs carried as
  text. It is host-neutral: nothing in it reads a particular agent
  framework's state. The
  [Standard Agents binding](../../examples/standard_agents/README.md) is
  built on it.
- `@synaptiai/acs-core/wasm`: the reference core itself (validator,
  executor, YAML loader, condition expressions and domain profiles) in
  process, through WebAssembly. It is the package's only way to check and
  apply domain profiles (section 5.21): the core's loader serves Rust,
  Python and TypeScript alike.

Package 0.1.0 implements the Agent Capability Standard 1.2.0
([the Standard](../../spec/STANDARD-v1.2.0.md)) with capability ontology
2.2.0. The package is versioned on its own line; see the
[roadmap](../../spec/ROADMAP.md).

## What it holds

| Module | What |
|--------|------|
| `ontology` | Every capability's layer, safety flags and required output fields; the `requires` edges; the trust classes; `prerequisitesOf(capabilities)`, the capabilities a call of them requires; `STANDARD_VERSION`, `SPEC_VERSIONS` and `ONTOLOGY_VERSION`. The table is generated from the ontology by `scripts/gen_standard_agents_binding.py` |
| `flags` | `effectiveFlags(capability, declared)`: the stricter of a declaration and the ontology (section 5.2.1), with W602 for a weaker declaration; `effectiveFlagsOf(capabilities, declared)` for a call that performs several, and `joinFlags` |
| `canonical` | `canonicalize` (RFC 8785), `sha256Hex` and `digest`: the approval digest the reference executor computes (section 5.14) |
| `redact` | `redactText` and `redactJson`: secrets replaced by `[REDACTED]` (section 6.7), with the same default patterns as the Python redactor; `holdsCredential`, the credential shapes a refusal of `persist` or `audit` data recognises (section 5.18.10) |
| `evidence` | `isEvidenceAnchor`, `ANCHOR_KINDS` and `INFERENCE_METHODS`: the evidence anchor (section 6.5) and the common output fields (section 4.1.1); `groundingPolicies` and `checkGrounding`: the grounding check of one output (section 5.20), with `parseRef`, `covers` and `refsIn` for `acs:` references; the evidence record and store types (section 6.6) |
| `binding` | `checkBindings(records, options)`: loads tool binding records (section 5.18.1) and computes each tool's effective flags, the tools a composite invokes included, with the diagnostics of section 5.18 (S303, S304, V101, V105, V107, V109, V110, W602; with the offered tools, W617, V111, V102 and F506). `annotationRecord` reads the record a Standard Agents `acs` annotation carries |
| `output` | `encodeCapabilityOutput` and `decodeCapabilityOutput`: a capability output as the I-JSON text of the object, with every required field (section 5.18.9), else `CapabilityOutputError` (R402) |

```ts
import { canonicalize, digest, effectiveFlags, redactJson } from '@synaptiai/acs-core';

effectiveFlags('mutate').flags.requires_checkpoint; // true
await digest([{ action: 'write_config', args: { key: 'a' } }]);
redactJson({ api_key: 'AIzaSyD-1234567890' }); // { value: { api_key: '[REDACTED]' }, pointers: ['/api_key'] }
```

The tests read the conformance vectors in place:
`tests/conformance/approval/digests.json`,
`tests/conformance/secrets/redact.json`,
`tests/conformance/secrets/credentials.json`, the grounding vectors
`tests/conformance/grounding/check.json` and the binding fixtures of the
safety-layer class, `tests/conformance/bindings/*.json`.

## The core through WebAssembly

`AcsCore.load()` instantiates `acs_core.wasm` (beside `wasm.js`; pass the
bytes, a compiled module or a URL to load another copy). `loadDocuments()`
reads the bundled `documents.json`: the ontology and the schema documents
a contract or workflow may reference, parsed by the core at build time, so
a context needs no file system.

```ts
import { AcsCore, loadDocuments } from '@synaptiai/acs-core/wasm';

const core = await AcsCore.load();
const ctx = core.context(await loadDocuments());

// A domain profile: a person approves every step.
const clinic = { domain: 'clinic', version: '1.0.0', risk_thresholds: { require_human: 'low' } };

// Validate a catalog file's text with the version its header declares.
const { catalog, header } = core.parseCatalog(text);
const report = ctx.validate(catalog, { header, profiles: [clinic] });

// Run a workflow: answer each action until the run ends.
const run = ctx.start({ catalog, header, workflow: 'change_config', runId: 'r1', nowMs: Date.now(), profiles: [clinic] });
for (let action = run.next(); !run.finished(); action = run.next()) {
  run.submit(action.id, await host.answer(action), Date.now());
}
const saved = run.snapshot(); // restore with ctx.restore({ catalog, snapshot: saved })
```

`header` is required on `validate` and `start`: the version the catalog's
`# Standard version:` header declares, or `null` for a catalog without one
(section 11.5). `validate`, `start` and `restore` also take the other
catalogs of the catalog's set (`catalogs`, each `{ catalog, header }`) and
agent manifests (`agents`) (sections 5.1.1 and 5.15.1); a run is restored
with the ones it started with. `ctx.checkProfiles`, `profileFlags` and `profilePolicy`
answer what domain profiles change (section 5.21.3). `start` reports each
warning of loading its profiles (a misspelled member is W604, and ignored)
to `onWarning`, `console.warn` by default. The executor checks a profile's
grounding policy (`require_grounding`) with its grounding check (section
5.20) and its minimum confidence; it does not check a destination policy
(`allowed_destinations`) yet, so `start` refuses a profile that sets one
(`CoreError` kind `start`) rather than run without the rule (section
5.21.4); no shipped profile does. A refused request
throws `CoreError` with its `kind` and, where the core gives them, its
diagnostics. A WebAssembly trap marks the instance broken; load a new one.
Release contexts and runs with `dispose()` (a `FinalizationRegistry` is the
backstop).

The interface is three C-ABI exports over JSON (`core/src/wasm.rs`):
`acs_alloc(len)`, `acs_call(ptr, len)`, whose result buffer starts with its
length as a 4-byte little-endian integer, and `acs_free(ptr, len)`.

**Standard Agents.** A packed Standard Agents agent can bundle the package;
the Standard Agents packaging page does not say how npm dependencies of a
packed agent are resolved, so bundle it rather than rely on an install.

## Develop

```bash
npm ci             # install the exact versions in package-lock.json
npm run build:wasm # build core/ for wasm32-unknown-unknown into dist/acs_core.wasm
npm run build      # compile to dist/ and bundle dist/documents.json
npm run check      # type-check
npm test           # vitest: the vectors in place, and the fixtures through the core
```

`build:wasm` runs `cargo` with the toolchain `RUSTUP_TOOLCHAIN` names, which
needs the `wasm32-unknown-unknown` target
(`rustup target add wasm32-unknown-unknown --toolchain <toolchain>`). The
tests replay the validator fixtures, every runtime fixture (straight and
saved and restored before every entry), the expression fixtures and the
profile vectors through the module.

A consumer in this repository (the Standard Agents binding) depends on the
package with `file:../../packages/acs-core` and imports the built `dist/`;
it uses the plain-TypeScript entry, so `npm run build:ts` here is enough
before installing the consumer.

## Publishing

`.github/workflows/publish-npm.yml` publishes the package from a tag
`acs-core-vX.Y.Z` on `main` (pushed, or given to a hand run from `main`):
it refuses a tag whose commit is not on `main` or whose version differs
from `package.json`'s, builds and tests that commit, then publishes with
provenance when the repository variable `NPM_PUBLISH_ENABLED` is `true` and
the secret `NPM_TOKEN` is set; otherwise it ends with a dry run.
