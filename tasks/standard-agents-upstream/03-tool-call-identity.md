# Let a tool know which call it is serving

## Problem

A function tool's `execute` receives the thread state and its arguments
([Tools §2](https://standardagentspec.org/0.2.0/specification/tools#2-function-tool-definition)).
It is not told the id of the tool call it is serving, or the name it was
called by.

Both exist. Hooks receive them as `HookToolCall` (`id`, `function.name`,
[Hooks §6.2](https://standardagentspec.org/0.2.0/specification/hooks#62-hooktoolcall)),
and the persisted result message carries `tool_call_id` and `name`
([Messages §1](https://standardagentspec.org/0.2.0/specification/threads/messages#1-message-structure)).
`state.execution` has no field for either
([Execution State §2](https://standardagentspec.org/0.2.0/specification/threads/execution-state#2-execution-properties)).
`defineTool` takes no name: a prompt refers to a tool by the name it is
registered under (in a package, its key in the `tools` registry), so the
tool's own module does not contain it.

A tool therefore cannot connect anything it does to the call that caused it:

- an idempotency key for an external API, so that a retried step does not
  repeat a payment or a message;
- a log line, a trace span, or a row in the thread's key-value store that a
  hook or a client can later match to the tool result message;
- the name of a file it writes for this call.

The workaround is to match records by order: a `tool_call_done` hook assumes
that the most recent record a tool wrote belongs to the call the hook is
being told about. That relies on sequential execution, breaks if a hook
invocation is lost (hook failures are non-fatal), and cannot be used at all
from inside the tool.

## Proposed rule

Add an optional property to `ExecutionState`:

```typescript
interface ExecutionState {
  // ...
  /** The tool call being executed, while a tool's `execute` runs. */
  readonly toolCall?: { id: string; name: string };
}
```

- While the runtime executes a tool for a model-issued tool call, it **MUST**
  set `state.execution.toolCall` to that call's id and the name it was called
  by.
- `toolCall.id` **MUST** equal the `id` hooks receive in `HookToolCall` for
  the same call, and the `tool_call_id` of the persisted result message.
- Outside a tool's execution the property is absent.

## Alternatives considered

- **A third parameter to `execute`.** Equivalent. A property on
  `state.execution` keeps the `execute(state, args)` signature and is also
  visible to helper functions that only receive `state`.
- **Match by order from a hook.** Described above; fragile, and not available
  to the tool.
- **A `name` field on `defineTool`.** Gives the name but not the call id, and
  can disagree with the name the runtime assigned.

## Open question

What should a tool invoked from code through `state.invokeTool()` or
`state.queueTool()` see? There is no model-issued call in that case. The
property could be absent, or carry a runtime-generated id; either is workable
if it is specified.

## Conformance impact

Additive and optional to read. Existing tools are unaffected. A runtime's
conformance checks would cover: the property is present during `execute` for a
model-issued call; its `id` matches `HookToolCall.id` in `tool_call_done` and
the stored message's `tool_call_id`; its `name` matches `HookToolCall.function.name`;
it is absent in hooks that run outside a tool's execution and at rest.
