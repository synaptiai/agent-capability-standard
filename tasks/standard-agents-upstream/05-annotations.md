# Annotations: allow them on agents and prompts, pass a tool's to its hooks, and say whom the rule binds

## Problem

[Tools §8](https://standardagentspec.org/0.2.0/specification/tools#8-annotations)
lets a function tool carry `annotations`: "implementation-specific hints,
keyed by the runtime or tool that reads them". It is a good extension point:
it is preserved ("`defineTool()` **MUST** return `annotations` unchanged"),
namespaced by owner, and inert. Three gaps limit what it can be used for.

**1. Two of the three tool categories cannot carry them.**
[Tools §1](https://standardagentspec.org/0.2.0/specification/tools#1-tool-categories)
defines function tools, prompt tools and agent tools. Only `defineTool`
accepts `annotations`; in the published types (0.45.10) neither
`AgentDefinition` nor `PromptDefinition` has the field. Anything that reads
annotations (a user interface choosing how to show a call, a packager, an
audit hook, a registry describing a package) gets hints for one category in
three, and nothing at all for a composed agent, which is the unit people
install.

**2. A hook is not given the annotations of the tool it is told about.** A
tool hook receives a call as a name and a JSON string
([Hooks §6.2](https://standardagentspec.org/0.2.0/specification/hooks#62-hooktoolcall)).
`ThreadState` has `loadModel`, `loadPrompt` and `loadAgent`
([Threads §2](https://standardagentspec.org/0.2.0/specification/threads#2-resource-loading));
it has no lookup for tools. Code can import a tool's module, or load a packed
tool through its package's `tools` export
([Packaging, Lazy Loading](https://standardagentspec.org/0.2.0/distribution/packaging#lazy-loading)),
but it has to know which module or package a call's name resolves to, which
the runtime has just worked out and the hook has not.

**3. The rule does not say whom it binds.** "Annotations **MUST NOT** change
argument validation, execution, the tool's results, or what is sent to the
model" is passive. [Tools §9](https://standardagentspec.org/0.2.0/specification/tools#9-conformance-notes)
addresses implementations ("preserve tool `annotations` and never let them
affect execution"). It is unclear whether a hook that reads a tool's
annotation and, say, redacts the stored result for tools marked sensitive,
is using the feature as intended or breaking the rule.

## Proposed rule

**1. Annotations on agents, then on prompts.** Add
`annotations?: Record<string, unknown>` to `AgentDefinition`, with the
semantics of Tools §8 unchanged: non-normative; returned unchanged by
`defineAgent()`; a runtime **MAY** read keys it understands and **MUST**
ignore the others.

For a packed agent, the packer **SHOULD** copy the annotations of each entry
agent into the package metadata (`PackedMeta` and the `standardagent` field
of `package.json`), as it already does for `parentHooks`, so that they can be
read without importing the package's code. Two rules make that copy safe:

- Annotations on an agent **MUST** be JSON-serializable, so that a packer can
  copy them. Tools §8 does not say this of a tool's annotations.
- Packaging does not say whether a reader of `__meta` or of the
  `standardagent` field ignores members it does not recognise. State that
  rule with this change (readers **MUST** ignore members they do not
  recognise), as Thread Client API §1 does for clients; the copy is additive
  only with it.

`PromptDefinition` is the natural second step, for prompts used as tools. The
existing per-reference slot does not serve: `options` on a prompt's tool
reference is "Static tool options" for that one use of a tool
([Prompts §3.2](https://standardagentspec.org/0.2.0/specification/prompts#32-tool-configuration-with-environment-values)),
not a description of the prompt itself.

**2. A tool's annotations on the call its hooks receive.** Add an optional,
read-only member to `HookToolCall`:

```typescript
interface HookToolCall {
  // ...
  /** The annotations of the tool this call resolved to, if any. */
  readonly annotations?: Readonly<Record<string, unknown>>;
}
```

The runtime sets it when the call resolves to a definition that declares
annotations: a function tool today, and a prompt tool or an agent handoff
once part 1 gives those definitions the field. A hook can then observe, label or display a call by what its
tool declares, without importing anything.

A `loadTool(name)` beside the existing loaders would be the more general
answer. It is left out here because it raises questions this proposal does
not need answered: it would hand a hook another package's `execute`, and it
needs the namespace rules of the other loaders spelled out for tools.

**3. An explicit subject for the rule.** Reword the fourth bullet of Tools §8
along these lines:

> A runtime **MUST NOT** change argument validation, execution, a tool's
> results, or what is sent to the model on the basis of annotations. A tool
> behaves identically in a runtime that ignores them.

and answer the question the passive form leaves open: may package code
(tools, hooks, handlers) read annotations and act on them, as part of the
package's own behaviour? Either answer is workable. Without one, cautious
authors avoid a use the specification probably intends, and others assume a
permission it may not give.

## Alternatives considered

- **Describe prompts and agents in `toolDescription`.** That text is for the
  model. It is not structured, and using it for machine-readable hints would
  change what is sent to the model.
- **Keep a side table from tool names to metadata in each package.** Works
  within one package. It cannot describe tools from other packages and
  duplicates what the definition already holds.
- **Leave the rule's subject implicit.** See the question above.

## Conformance impact

Additive. No existing definition changes meaning, and a runtime that ignores
every annotation remains conformant. Checks: `defineAgent()` (and
`definePrompt()`, if adopted) returns `annotations` unchanged; a packed entry
agent's annotations appear in the package metadata; a runtime that implements
the hook member passes the resolved tool's annotations, unchanged, to that
tool's hooks.
