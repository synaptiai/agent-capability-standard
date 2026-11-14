# Annotations: allow them on prompts and agents, let code read them, and say whom the rule binds

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
`PromptDefinition` nor `AgentDefinition` has the field. Anything that reads
annotations (a user interface choosing how to show a call, a packager, an
audit hook, a registry describing a package) gets hints for one category in
three, and nothing at all for a composed agent, which is the unit people
install.

**2. Package code has no specified way to read them.** The text says
annotations are keyed by "the runtime or tool that reads them", but only a
runtime can get at a tool's definition. `ThreadState` has `loadModel`,
`loadPrompt` and `loadAgent`, with `getModelNames`, `getPromptNames` and
`getAgentNames`
([Threads §2](https://standardagentspec.org/0.2.0/specification/threads#2-resource-loading));
there is no counterpart for tools. A hook receives a tool call as a name and
a JSON string
([Hooks §6.2](https://standardagentspec.org/0.2.0/specification/hooks#62-hooktoolcall)).
A hook that wants to know what kind of tool was just called has to import
the tool's module itself, which does not work across project layouts or for
a tool that came from a package.

**3. The rule does not say whom it binds.** "Annotations **MUST NOT** change
argument validation, execution, the tool's results, or what is sent to the
model" is passive. [Tools §9](https://standardagentspec.org/0.2.0/specification/tools#9-conformance-notes)
addresses implementations ("preserve tool `annotations` and never let them
affect execution"). It is unclear whether a hook that reads a tool's
annotation and, say, redacts the stored result for tools marked sensitive,
is using the feature as intended or breaking the rule.

## Proposed rule

**1. Annotations on prompts and agents.** Add
`annotations?: Record<string, unknown>` to `PromptDefinition` and
`AgentDefinition`, with the semantics of Tools §8 unchanged: non-normative;
returned unchanged by `definePrompt()` and `defineAgent()`; a runtime **MAY**
read keys it understands and **MUST** ignore the others.

For a packed agent, the packer **SHOULD** copy the annotations of each entry
agent into the package metadata (`PackedMeta` and the `standardagent` field
of `package.json`), as it already does for `parentHooks`, so that they can be
read without importing the package's code.

**2. Reading a tool's definition.** Add to `ThreadState`, beside the existing
loaders and under the same namespace visibility rules:

```typescript
loadTool<T = unknown>(name: string): Promise<T>;
getToolNames(): string[];
```

They may be optional and feature-detected, as `instanceEnv?` is, so that
existing runtimes stay conformant.

**3. An explicit subject for the rule.** Reword the fourth bullet of Tools §8
along these lines:

> A runtime **MUST NOT** change argument validation, execution, a tool's
> results, or what is sent to the model on the basis of annotations. A tool
> behaves identically in a runtime that ignores them. Package code (tools,
> hooks, handlers) **MAY** read annotations and act on them; what such code
> does is part of the package's own behaviour.

and add a recommendation on keys: an annotation key **SHOULD** be the npm
package name or a domain name of whoever defines its meaning, so that two
owners do not pick the same key.

## Alternatives considered

- **Describe prompts and agents in `toolDescription`.** That text is for the
  model. It is not structured, and using it for machine-readable hints would
  change what is sent to the model.
- **Keep a side table from tool names to metadata in each package.** Works
  within one package. It cannot describe tools from other packages and
  duplicates what the definition already holds.
- **Leave the rule's subject implicit.** Then cautious authors avoid a use
  the specification probably intends, and others assume a permission it may
  not give.

## Conformance impact

Additive. No existing definition changes meaning, and a runtime that ignores
every annotation remains conformant. Checks: `definePrompt()` and
`defineAgent()` return `annotations` unchanged; a runtime that implements
`loadTool` returns the definition, annotations included, and applies the
namespace rules of the other loaders; a packed entry agent's annotations
appear in the package metadata.
