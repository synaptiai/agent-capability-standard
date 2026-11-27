# Say which source governs where the 0.2.0 text and the published types differ

## Problem

A package compiles against `@standardagents/spec`; a runtime is built from
the text. The two are versioned apart: the text is 0.2.0, "The current
specification version is 0.2.0" (repository README), and the package is at
0.45.13 and exports a constant that the text does not mention:

```typescript
/**
 * The Standard Agent Specification version these types implement.
 * Implementations report conformance against exactly one version.
 */
declare const SPEC_VERSION = "0.2.0";
```

The package also exports members that the 0.2.0 text does not contain,
among them:

- `PromptDefinition.historyLimit`, and `ThreadState.runAgent`;
- the user-value methods `getUserValue`, `setUserValue` and
  `listUserValues`;
- `executionMode` and `executionProvider` on tool definitions;
- the callable prefixes `provider:` and `mcp:`, whose comments describe them
  as references "stored by Standard Agents Builder prompts";
- `validateAgentDefinition` and `defineController`;
- the `ToolResult` interface with `error_data`, and `FileRecord.updatedAt`.

No passage says whether such a member is part of 0.2.0, a preview of a
later version, or one runtime's feature. Some of them change behaviour the
text states. The text requires that "`execution.messageHistory` **MUST**
represent live chronological persisted execution history"
([Execution State §2.2](https://standardagentspec.org/0.2.0/specification/threads/execution-state#22-live-execution-history)),
and the comment on `historyLimit` says that with it set, "The window is the
execution's history itself, not only the request: `execution.messageHistory`,
tools, hooks and `filter_messages` all see just these rows".

So a package author cannot tell whether a member the types offer is
portable, and a runtime author cannot tell whether it must provide one. A
field that a runtime built from the text drops cannot be detected from
package code either.

The version numbers raise the same question from the other side. No passage
relates the package's version to the text's, or says which governs where
they differ. The Packaging example's peer range is
`"@standardagents/spec": ">=0.2.0"`
([Packaging, package.json Requirements](https://standardagentspec.org/0.2.0/distribution/packaging#packagejson-requirements)),
a range that every package version meets, and `PackedMeta` and
`package.json.standardagent` have no member for the specification version a
package targets.

## Proposed rule

Add to the Packaging page, or to the introduction of the specification:

- `@standardagents/spec` is versioned independently of the text.
  `SPEC_VERSION` names the version of the text the package implements.
- Where the text of a version and the published types differ, **the text
  governs**. A member that the text of the version does not define is not
  part of that version: a portable package **MUST NOT** rely on it, and a
  runtime need not provide it.

Then, for each member that exists only in the types, either define it in the
text or mark it in the package as outside the specification, for example
with a documentation tag such as `@nonstandard` or
`@experimental` and the name of the runtime that provides it. The list
above is a starting point; it was made by searching `content/0.2.0` for
each exported name.

The opposite rule, that the types govern, would also settle the question.
It would make each types-only member a requirement on every runtime, and the
text would need to describe them before the next version is published.

In a later version, an optional member of `PackedMeta` and
`package.json.standardagent` naming the specification version a package
targets would let a runtime refuse a package written for another version.

## Alternatives considered

- **Leave it to each runtime's documentation.** A package that uses a
  types-only member then depends on one runtime, which is what the Packaging
  portability requirements set out to prevent.
- **Remove every types-only member from the package.** This settles
  portability, but breaks packages that use them on the runtime that
  provides them.
- **Pin the package version in each package.** A bounded
  `peerDependencies` range fixes which types a package compiled against. It
  does not say which of those types a runtime must honour.

## Conformance impact

The statement adds no requirement on a runtime that provides what the text
defines; it settles what conformance means for the members it does not
define. The documentation tags change no type. A check by search is enough to
keep it true: every exported member of the package either has a section in
the text of its `SPEC_VERSION`, or carries the tag.

The [Agent Capability Standard](https://github.com/synaptiai/agent-capability-standard)
is one consumer. Its
[reference binding for Standard Agents](https://github.com/synaptiai/agent-capability-standard/tree/8ec818c217d55c8138986786c700da38a7ee25a6/examples/standard_agents)
treats every types-only member as not portable: it pins the text version,
the upstream commit and the types version together, and repeats a refusal
code in a tool result's `error` text because it cannot rely on a field the
text does not define. The
[integration notes](https://github.com/synaptiai/agent-capability-standard/blob/8ec818c217d55c8138986786c700da38a7ee25a6/docs/integrations/standard_agents.md)
have the detail.
