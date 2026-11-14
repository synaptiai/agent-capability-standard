# Nine inconsistencies in the 0.2.0 text (numbering, cross-references, requirement levels)

Small corrections found while reading 0.2.0 closely. Each is a place where
two passages disagree, so an implementer cannot tell which to follow. Items 1
to 3 are mechanical; 4 to 9 need a decision.

## 1. The Runtime page has two sections numbered 14

`infrastructure/runtime.md` has "## 14. Code Execution Runtime" and then
"## 14. Durable Key-Value Store", followed by "## 15. Thread Client API" and
"## 16. Conformance Summary". The key-value section's subsections are
numbered 14.1 and 14.2, which repeats the code execution section's 14.1 and
14.2.

**Suggested fix:** renumber from the second section 14 onward (Durable
Key-Value Store becomes 15, Thread Client API 16, Conformance Summary 17), or
whichever numbering you prefer, and update the references in items 2 and 3.

## 2. The Conformance Summary links to an anchor that does not exist

The Conformance Summary's Code Execution item links to
`#13-code-execution-runtime`. Section 13 is "Runtime Streams"; the code
execution section's anchor is `#14-code-execution-runtime`.

## 3. Threads §7 points at "Runtime §15" for the key-value store

`specification/threads.md` §7 ends by sending the reader to "Runtime §15"
for the key-value store's runtime semantics, with the link target
`/0.2.0/infrastructure/runtime#15-durable-key-value-store`. On the Runtime
page that section is numbered 14 and §15 is the Thread Client API, so the
anchor does not resolve.

## 4. `maxInstances`: SHOULD in one place, MUST in another

- [Subagents §1](https://standardagentspec.org/0.2.0/specification/subagents#1-subagentrelationship):
  "When reached, creation attempts **SHOULD** return a tool error explaining
  the cap".
- [Runtime §7.2](https://standardagentspec.org/0.2.0/infrastructure/runtime#72-lifecycle-tooling):
  "Creation attempts beyond `maxInstances` **MUST** return tool errors with
  actionable guidance."

**Suggested fix:** use MUST in both. A cap that a runtime may ignore is not a
cap an agent author can rely on.

## 5. The order of child-required hooks is described two ways

- [Hooks §1.3](https://standardagentspec.org/0.2.0/specification/hooks#13-hook-scoping):
  child `before_parent` requirements run "in side A then side B relationship
  order and child declaration order".
- [Runtime §7.3.1](https://standardagentspec.org/0.2.0/infrastructure/runtime#731-required-parent-hook-composition):
  runtimes "**MUST** run child `before_parent` hooks in prompt tool order and
  declaration order".

Relationships are declared on sides, not in a prompt's `tools`
([Tools §5](https://standardagentspec.org/0.2.0/specification/tools#5-subagent-composition)),
so "prompt tool order" looks like wording from before that change.

**Suggested fix:** use the Hooks §1.3 wording in Runtime §7.3.1.

## 6. Key-value isolation, and a `ThreadState` for another thread

- [Runtime, Durable Key-Value Store](https://standardagentspec.org/0.2.0/infrastructure/runtime#14-durable-key-value-store),
  item 3: "Values **MUST NOT** be readable by any other thread, including
  parent, child, or sibling threads."
- [Subagents §6.4](https://standardagentspec.org/0.2.0/specification/subagents#64-child--parent-explicit-escalation):
  explicit-mode children "deliver results through another channel — the
  parent's key-value store, for example".
- `getParentThread()` and `getChildThread()` return a `ThreadState`
  ([Threads §9](https://standardagentspec.org/0.2.0/specification/threads#9-subagent-hierarchy-communication-and-termination)),
  which has `getValue` and `setValue`.

A reader cannot tell whether
`(await state.getParentThread())?.setValue(key, value)` is the sanctioned
channel that Subagents §6.4 has in mind, or a violation of item 3.

**Suggested fix:** reword item 3 to say what is isolated (a thread's own
`getValue` and `setValue` never resolve another thread's keys, and nothing is
inherited or copied), and state whether a `ThreadState` obtained through
`getParentThread()` or `getChildThread()` may read and write that thread's
store. The same question applies to its file system.

## 7. Where thread endpoints are mounted

- [Thread Endpoints §2](https://standardagentspec.org/0.2.0/specification/threads/endpoints#2-file-based-routing):
  `{runtime_prefix}/{threadId}/{endpoint_path}`. Packaging and Examples §9
  use the same form.
- [Thread Client API §2](https://standardagentspec.org/0.2.0/specification/threads/client-api#2-routes),
  item 2: thread endpoints "are mounted beneath the same
  `{runtime_prefix}/threads/{threadId}/` prefix".

If `{runtime_prefix}` means the same thing on both pages, one of the two
paths has a `threads/` segment the other lacks.

**Suggested fix:** use one form everywhere. The Thread Client API form keeps
package endpoints beside the routes it reserves (`messages`, `fs`, `stop`,
`stream`), which is what its reservation rule assumes.

## 8. "The specification defines no route to create a thread"

[Examples §9](https://standardagentspec.org/0.2.0/getting-started/examples)
says: "Thread creation is runtime-defined. The specification defines no route
to create a thread."
[Thread Client API §6](https://standardagentspec.org/0.2.0/specification/threads/client-api#6-creating-a-thread)
defines `POST {runtime_prefix}/threads`.

**Suggested fix:** in the example, say that a runtime that exposes the Thread
Client API creates a thread with that route, and that the API itself is a
SHOULD ([Runtime, Thread Client API](https://standardagentspec.org/0.2.0/infrastructure/runtime#15-thread-client-api)).

## 9. `parallelToolCalls` is described as parallel execution

[Prompts §1.2](https://standardagentspec.org/0.2.0/specification/prompts#12-optional-properties)
describes `parallelToolCalls` as "Allow parallel tool execution".
[Runtime §5.1](https://standardagentspec.org/0.2.0/infrastructure/runtime#51-ordering)
says "Tool calls **MUST** execute sequentially in the returned order", and
Tools §9 says the same.

The sentence after the Prompts table suggests the intent: "An explicit
`parallelToolCalls` value controls the provider option." That option lets a
model return several calls in one response; it does not make the runtime run
them at once.

**Suggested fix:** describe the property as "Allow the model to return
several tool calls in one response; the runtime still executes them in
order."
