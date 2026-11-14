# Specify what a tool's `execute` returns, and give results a field for metadata

## Problem

The Tools page never defines the value a function tool returns. Its examples
return `{ status: 'success', result: '...' }`, and other pages add fields in
passing:

- the published `@standardagents/spec` types (0.45.10, `SPEC_VERSION` 0.2.0)
  declare `ToolResult` with `status`, `result`, `error`, `error_code`,
  `error_data`, `stack` and `attachments`;
- an example in
  [Runtime Streams](https://standardagentspec.org/0.2.0/specification/threads/runtime-streams)
  returns `{ status: 'error', error: opened.error, error_code: opened.code }`;
- [Subagents §5.1](https://standardagentspec.org/0.2.0/specification/subagents#51-persistent-invocation-arguments)
  requires "a structured `subagent_arguments_required` error", and §5.2 "a
  structured error (e.g. `subagent_env_required`)", without saying where in a
  result the code goes;
- [Hooks §6.3](https://standardagentspec.org/0.2.0/specification/hooks#63-hooktoolresult)
  defines `HookToolResult` as `status`, `result`, `error`, `stack` and
  `attachments`: no `error_code`, no `error_data`;
- the stored message has `tool_status` and `content`
  ([Messages §1](https://standardagentspec.org/0.2.0/specification/threads/messages#1-message-structure)),
  and nothing says what becomes of an error code.

Two things follow.

1. **A portable tool cannot rely on a machine-readable error.** A tool
   author who returns `error_code` cannot know whether a hook, the stored
   message or a client will ever see it. A client that wants to treat "needs
   confirmation", "rate limited" and "crashed" differently has to parse the
   error text.
2. **A result has no place for data that is about the result but not for the
   model.** Where the data came from, how long the call took, what it cost,
   whether it was served from a cache: the only field is `result`, a string,
   and all of it is sent to the model. `Message` has `metadata`, but nothing
   connects a tool's return value to it.

## Proposed rule

**1. Define `ToolResult` in Tools §2**, as the published types already have
it, and state that it is the return type of `execute`:

```typescript
interface ToolResult {
  status: 'success' | 'error';
  result?: string;
  error?: string;
  error_code?: string;                  // stable, machine-readable
  error_data?: Record<string, unknown>; // JSON-serialisable detail
  stack?: string;
  attachments?: Array<ToolAttachment | AttachmentRef>;
}
```

**2. Align `HookToolResult` with it.** Hooks that receive a result **MUST**
receive `error_code` and `error_data` when the tool returned them, and a hook
that replaces a result may set them.

**3. Say what is stored.** When a tool result is persisted, the runtime
**MUST** keep `error_code` and `error_data` with the tool result message, so
that `getMessages()` and a client reading the thread can see them. Naming the
place is a decision for the maintainers; `metadata.error_code` and
`metadata.error_data` on the message would need no new message field.

**4. Add an optional `metadata` field to `ToolResult` and `HookToolResult`:**

```typescript
metadata?: Record<string, unknown>; // JSON-serialisable
```

- The runtime **MUST** merge it into the `metadata` of the persisted tool
  result message and pass it to the result hooks.
- The runtime **MUST NOT** include it in what is sent to the model.
- Keys are owned by whoever writes them, as tool `annotations` are: the
  specification defines none.

## Alternatives considered

- **Encode everything in `result` as JSON.** Possible today. The model reads
  all of it, it costs tokens on every later request, and a hook that wants
  one field has to parse a string whose shape it cannot know.
- **Write side data to the thread's key-value store.** Also possible today,
  but then it is not attached to the message it describes, and since a tool
  does not know its own call id it cannot even key the entry by the call.
- **Leave `error_code` to the types.** Then it is implementation behaviour,
  and a second runtime has nothing to conform to.

## Conformance impact

Parts 1 to 3 document and pin down what the published types already expose;
no definition changes. Part 4 is additive and optional. A runtime's
conformance checks would cover: `error_code` and `error_data` returned by a
tool reach `after_tool_call_failure`, `before_store_tool_result` and
`tool_call_done`, and are readable from the stored message; `metadata`
returned by a tool is readable from the stored message and is absent from the
provider request.
