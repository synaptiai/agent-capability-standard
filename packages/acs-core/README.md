# @synaptiai/acs-core

The Agent Capability Standard core for TypeScript: the capability ontology
as types and data, effective safety flags, canonical JSON and approval
digests, secret redaction, tool binding records, and capability outputs
carried as text. It is host-neutral: nothing in it reads a
particular agent framework's state. The
[Standard Agents binding](../../examples/standard_agents/README.md) is built
on it.

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
| `redact` | `redactText` and `redactJson`: secrets replaced by `[REDACTED]` (section 6.7), with the same default patterns as the Python redactor |
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
`tests/conformance/secrets/redact.json` and the binding fixtures of the
safety-layer class, `tests/conformance/bindings/*.json`.

## Develop

```bash
npm ci          # install the exact versions in package-lock.json
npm run check   # type-check
npm test        # vitest
npm run build   # compile to dist/, which the package exports
```

A consumer in this repository (the Standard Agents binding) depends on the
package with `file:../../packages/acs-core` and imports the built `dist/`, so
run `npm run build` here before installing the consumer.
