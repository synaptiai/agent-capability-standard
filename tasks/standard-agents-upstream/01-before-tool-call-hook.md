# Define a hook that runs before a tool executes and can decline the call

## Problem

In 0.2.0 no hook, and no other specified decision point, can decline a tool
call between the model asking for it and the tool executing.

- `tool_call_started` fires when the call appears in the model's stream, or
  once the tool's `progressArgument` has streamed. Its arguments "**MAY** be
  an incomplete JSON fragment (or empty)", and "The return value **MUST** be
  ignored; the hook cannot modify the tool call."
  ([Hooks §5.1](https://standardagentspec.org/0.2.0/specification/hooks#51-tool_call_started))
- `before_store_tool_result`, `after_tool_call_success`,
  `after_tool_call_failure` and `tool_call_done` all run after the tool has
  executed ([Hooks §5.2–§5.5](https://standardagentspec.org/0.2.0/specification/hooks#5-tool-execution-hooks)).
- The step cycle goes from "Persist assistant response" straight to "Execute
  tool calls sequentially"
  ([Runtime §3](https://standardagentspec.org/0.2.0/infrastructure/runtime#3-step-cycle)).
- `before_create_message` does run before the assistant message that carries
  the calls is stored, and "Failures **SHOULD** prevent message creation"
  ([Hooks §4.1](https://standardagentspec.org/0.2.0/specification/hooks#41-before_create_message)).
  The text does not say what happens to that message's tool calls when it
  does, and it would stop every call in the message, not one. The published
  types (0.45.10) add that a runtime "can still perform an insertion that an
  execution cannot go on without, such as the message of a model step", so a
  failure there does not stop the calls.

So a rule that should hold before a side effect can only be written inside
each tool, or by reshaping the agent around it (see Alternatives). Rules of
that kind are common and are not specific to any one product:

- a rate limit or a spending cap across all of an agent's tools;
- an allow list or deny list that depends on the arguments (which paths,
  which recipients, which hosts);
- a dry-run mode that answers every side-effecting call without performing it;
- confirmation by a person before a destructive call;
- a policy an agent's author applies to every tool its prompts offer,
  including tools that come from other packages.

Writing the rule inside each tool has three costs.

1. **It does not compose.** A packaged agent's tools are opaque to whoever
   composes it. `parentHooks` lets a child require a hook on its parent, and
   a missing one "**MUST** fail composition closed"
   ([Agents §6](https://standardagentspec.org/0.2.0/specification/agents#6-required-parent-hooks)),
   but no hook that exists today can stop a call, so a child cannot use the
   mechanism to hold its parent to a rule.
2. **It is not portable if a runtime adds its own gate.** Packaging says a
   packed agent must not depend on "private runtime RPCs", and: "When an
   agent category needs a new runtime primitive, that primitive belongs in
   the specification and its conformance surface rather than in a
   product-private package/runtime agreement."
   ([Packaging, Portability requirements](https://standardagentspec.org/0.2.0/distribution/packaging#portability-requirements))
3. **The specification already half-names the concept.** A note in
   [Hooks §3.3](https://standardagentspec.org/0.2.0/specification/hooks#33-prefilter_llm_history)
   says "Runtimes may support request-context hooks acting as **policy
   gates** — refusing to let a request proceed", and
   [Execution State §4.2](https://standardagentspec.org/0.2.0/specification/threads/execution-state#42-reasons)
   lists a `hook_blocked` reason code. Neither says which hook may block,
   how, or what the runtime then does. A gate exists informally for model
   requests, where nothing has happened yet, and not for tool calls, where
   the side effects are.

## Proposed rule

Add one thread hook to Hooks §1.1 and §5.

### `before_tool_call`

Called once per tool call, after the call is complete and its arguments have
been validated against the tool's schema, and before the tool executes.

```typescript
(state: ThreadState, toolCall: HookToolCall, context: HookExecutionContext)
  => Promise<HookToolResult | null | undefined>
```

- Implementations **MUST** call this hook exactly once for each tool call
  they are about to execute, with `toolCall.function.arguments` complete.
- If every `before_tool_call` hook returns `null` or `undefined`, the runtime
  **MUST** execute the tool as it does today.
- If a hook returns a `HookToolResult`, the runtime **MUST NOT** execute the
  tool and **MUST NOT** call the remaining `before_tool_call` hooks for that
  call. The returned value is the result of the call: it passes through
  `after_tool_call_success` or `after_tool_call_failure`,
  `before_store_tool_result` and `tool_call_done`, and is persisted as a tool
  result message, as an executed tool's result is.
- If a hook throws or exceeds the runtime's hook timeout, the runtime **MUST
  NOT** execute the tool and **MUST** persist an error result for the call.
  The turn continues, as it does after any tool error
  ([Runtime §5.2](https://standardagentspec.org/0.2.0/infrastructure/runtime#52-error-handling)).
- Hooks run in the order of
  [Hooks §1.3](https://standardagentspec.org/0.2.0/specification/hooks#13-hook-scoping).
  That section orders the sources of hooks and does not order two hooks of
  one type listed in one `hooks` array. The first-result rule above needs
  that order as well: within one array, hooks run in array order.
  A child may require one on its parent through `parentHooks`.
- Hooks §1.2 already requires that `hook` "**MUST** reference one of the hook
  types in §1.1", and the published `defineHook()` throws for a type it does
  not know. A runtime that predates this hook is not bound by it, so a
  package that needs the gate on such a runtime keeps its check inside the
  tool.

Scope, to keep the rule small:

- It covers tool calls the runtime executes. Provider tools "execute
  server-side"
  ([Providers §10](https://standardagentspec.org/0.2.0/specification/providers#10-provider-tools))
  and have already run when the response reaches the runtime, so no runtime
  hook can decline them.
- It covers the thread whose prompt or agent lists the hook. A hook a child
  requires of its parent runs with the parent's `ThreadState`
  ([Agents §6](https://standardagentspec.org/0.2.0/specification/agents#6-required-parent-hooks)),
  so it sees the parent's calls, not calls made inside the child's thread.
  Whoever composes a packaged agent still cannot gate the calls that agent
  makes in its own thread.
- A hook listed on an agent applies to prompts that list no hooks of their
  own: "When `hooks` is non-empty, only those hooks form the prompt base set"
  ([Prompts §8](https://standardagentspec.org/0.2.0/specification/prompts#8-hook-scoping)).
  A hook required through `parentHooks` applies "during every prompt on
  either side".
- It decides at once. "Runtimes **SHOULD** enforce a timeout on hook
  execution", and hooks "**SHOULD NOT** perform blocking operations"
  ([Hooks §1.2](https://standardagentspec.org/0.2.0/specification/hooks#12-hook-definition)),
  so a gate that needs a person declines the call now and lets the decision
  arrive some other way; it does not hold the call open.

Two properties are deliberate.

- **The hook returns a result, not a verdict.** No new type is needed, a
  declined call looks to the model like any other tool error, and the same
  hook serves a cache or a dry-run mode by returning a success.
- **A failing hook declines the call.** Hook failures stay "non-fatal to the
  decorated turn", as the Hooks page requires. But a gate that lets the call
  through when it fails is not a gate, so the call it was guarding does not
  run.

### The same questions for the existing tool hooks

A gate is only as complete as the set of calls it sees, and the same holds
for a hook that redacts, audits or meters tool results. Four points that the
new hook needs settled are open in 0.2.0 for the existing tool hooks too.
They could be settled with this change or separately.

1. **Which calls fire the tool hooks.** Hooks §5 has a requirement to call
   the hook only for `tool_call_started` and `tool_call_done` ("Implementations
   **MUST** call this hook once per tool call, whether it succeeded or
   failed."); §5.2 to §5.4 state none, and the step cycle
   ([Runtime §3](https://standardagentspec.org/0.2.0/infrastructure/runtime#3-step-cycle),
   [§5](https://standardagentspec.org/0.2.0/infrastructure/runtime#5-tool-execution))
   names no hook. The text does not say whether the tool hooks fire for
   prompt tools, handoffs, the injected lifecycle tools, provider-executed
   tools, or calls made through `state.invokeTool()` and `state.queueTool()`,
   or whether a caller of `invokeTool` receives the tool's own result or the
   result as the hooks rewrote it. **Suggested:** a table in Hooks §5 of call
   origin (model-issued, `invokeTool`, `queueTool`, sub-prompt, handoff,
   lifecycle tool, provider-executed) by tool hook, with a column for
   `before_tool_call`.
2. **Provider-executed tools.** Provider tools "execute server-side"
   ([Providers §10](https://standardagentspec.org/0.2.0/specification/providers#10-provider-tools)).
   The published types (0.45.10) carry `executionMode: 'local' | 'provider'`,
   `ProviderResponse.providerTools`, whose entries "must not be re-executed
   locally", and the stream chunks `web-search-done` and
   `provider-tool-done`; none of these is in the 0.2.0 text.
   [Tools §9](https://standardagentspec.org/0.2.0/specification/tools#9-conformance-notes)
   requires implementations to "execute local tools sequentially in the
   order they were returned" and does not define a local tool. Whether a
   provider-executed call and its result are persisted, and whether any tool
   hook fires for one, is not stated, so that activity has no defined record.
   **Suggested:** define a provider-executed tool on the Tools page and state
   that its `execute` is not invoked; document the members the types already
   have in
   [Providers §5](https://standardagentspec.org/0.2.0/specification/providers#5-response-format),
   [§6](https://standardagentspec.org/0.2.0/specification/providers#6-streaming)
   and §10; and give such calls their row in the table of point 1.
3. **In what order the hooks after execution run, and what each receives.**
   The text orders none of `after_tool_call_success` or
   `after_tool_call_failure`, `before_store_tool_result`, persisting the
   result and `tool_call_done`. It does not say whether `tool_call_done`
   receives the result as the tool returned it or as it was stored, or
   whether a result is persisted before the next call of the same response
   executes; Tools §9 requires implementations to "persist tool results as
   messages before advancing". **Suggested:** one paragraph in Hooks §5
   giving the order, the result each hook receives, and that
   `toolCall.function.arguments` is complete in every tool hook except
   `tool_call_started`. The rule above that a returned result "passes
   through" the hooks after execution then follows that order.
4. **What a throw or a timeout does.** Each message hook states an outcome:
   "Failures **SHOULD** prevent message creation", "Failures **SHOULD NOT**
   affect the created message", and so on
   ([Hooks §4.1](https://standardagentspec.org/0.2.0/specification/hooks#41-before_create_message)
   to §4.4). The five tool hooks and the three request-context hooks state
   none; Hooks §1.2 says only that "Runtimes **SHOULD** enforce a timeout on
   hook execution". So whether a result is stored unredacted when the
   `before_store_tool_result` hook that redacts it throws is undefined. The
   published types say more than the text: after a throwing
   `before_create_message`, a runtime "can still perform an insertion that an
   execution cannot go on without". **Suggested:** a table in Hooks §1
   giving, for each hook, what the runtime uses and whether the operation
   goes on when the hook throws or times out; the failure sentences that
   exist only in the type comments moved into §4.1 and §4.3; and a reported
   hook failure attributed as `hook:<id>`, the form
   [Providers §7](https://standardagentspec.org/0.2.0/specification/providers#7-error-handling)
   already defines in `ErrorOrigin`.

## Alternatives considered

- **Leave it to each tool.** This is what authors do today. It cannot be
  applied to a tool one did not write, and every tool author has to remember
  it.
- **A provider extension that filters tool calls.** An override of `generate`
  or `stream` returns the response that carries the calls
  ([Providers §1.3](https://standardagentspec.org/0.2.0/specification/providers#13-provider-extension-factories)).
  The request-scoped overrides "additionally receive the executing thread's
  `state` on their context when the runtime has one"
  ([Infrastructure: Providers, Method Overrides](https://standardagentspec.org/0.2.0/infrastructure/providers#method-overrides));
  the context that Providers §1.3 lists has no `state`, and the published
  type makes it optional, so an override cannot count on thread state.
  It belongs to a model definition, not to an agent; it has to rewrite a
  stream; the stored assistant message no longer shows what the model asked
  for; it does not see calls made through `invokeTool` or `queueTool`, or by
  a child's models; and the text does not say that a runtime executes only
  the calls an override returns.
- **A handler-backed side that alone calls the tools that act.** The model
  proposes and deterministic code acts. This works, and it changes the shape
  of the agent to get one check.
- **A guard tool that fronts another through `state.invokeTool()`.** One
  wrapper per guarded tool, and the model must be unable to call the guarded
  tool directly; the 0.2.0 text does not say what a runtime does with a call
  to a tool the prompt did not offer.
- **Give `tool_call_started` a return value.** It fires before the arguments
  are complete, by design, so that a UI can show progress early. A gate needs
  the complete, validated arguments.
- **Stop the run from `tool_call_started`.** The hook receives `state`, so it
  can call `state.execution.stop()` or `state.terminate()`. That ends the
  run, or terminates the thread, where a gate should decline one call. The
  hook may fire before the arguments are complete, and the text does not say
  that the runtime waits for the hook before it executes the tool, or that a
  stop prevents the calls already returned in the same response.
- **Declarative fields on the tool** (for example a "needs confirmation"
  flag). This would put one policy into the specification. A hook leaves
  policy in userland, in the same way the Handlers page leaves outbound
  messaging there.
- **A runtime-specific gate.** Agents that depend on it are not portable.

## Open questions

1. Should the hook also fire for the runtime-injected lifecycle tools
   (`subagents`, `subagent_create`, `subagent_message`)? Declining a
   `subagent_create` before a child thread exists seems useful, and Hooks §5
   does not currently say whether the existing tool hooks fire for those
   tools (point 1 above).
2. Should it fire for calls made from code through `state.invokeTool()` and
   `state.queueTool()`? The same question is open for the existing tool hooks
   (point 1 above).
3. Is `hook_blocked` meant for this, or for a hook that ends the run? If the
   latter, that behaviour needs its own rule; this proposal does not end the
   run.
4. When a hook returns a result for a call to a tool that a side names in
   `stopTool`, `sessionStop`, `sessionFail` or `sessionStatus`, does the
   binding still take effect? Agents §3 and §4 do not say whether a binding
   applies when its tool returns `status: 'error'`. If it does, a declined
   `sessionStop` call still ends the session and forwards the model-supplied
   `messageProperty` argument to the parent. A gate that declines such a call
   needs the answer to be no.

## Conformance impact

Additive for existing packages: an agent that defines no `before_tool_call`
hook behaves as it does today, and no existing interface changes. It is a new
requirement on runtimes of the version that adds it (the community page says
accepted changes are published "in a new version of the specification"). A
runtime's conformance checks would cover:

- the hook is called exactly once per call, before execution, with complete
  arguments;
- `null` and `undefined` let the tool execute;
- a returned result prevents execution, is persisted, and reaches the
  post-execution hooks;
- a throwing hook and a timed-out hook both prevent execution and produce an
  error result, and the turn continues;
- with several hooks, the first returned result wins and later hooks are not
  called;
- a hook required through `parentHooks` runs for the parent's tool calls.

If the four points on the existing tool hooks are settled too, the checks
extend to the table of call origins, the order of the hooks after execution
and the result each receives, and each hook's outcome when it throws or
times out. Those are clarifications: a runtime whose behaviour matches the
settled text needs no change.

## Evidence that this is needed more widely

Other agent frameworks have each added this point, under different names:

- The Claude Agent SDK has a `PreToolUse` hook that runs before a tool call
  executes and can deny it
  ([hooks](https://code.claude.com/docs/en/agent-sdk/hooks)).
- The OpenAI Agents SDK has tool input guardrails, which can skip the call or
  replace its output
  ([guardrails](https://openai.github.io/openai-agents-python/guardrails/)).
- Google's Agent Development Kit has `before_tool_callback`: when it returns
  a result, the tool is skipped and that result is used
  ([callbacks](https://adk.dev/callbacks/types-of-callbacks/)). This is the
  shape proposed here.
- LangChain has `wrap_tool_call` middleware, and a human-in-the-loop
  middleware that lets a person approve, edit or reject a call before it runs
  ([human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)).
- The Model Context Protocol asks hosts for the same thing in prose: "there
  **SHOULD** always be a human in the loop with the ability to deny tool
  invocations"
  ([tools](https://modelcontextprotocol.io/specification/latest/server/tools)).

The [Agent Capability Standard](https://github.com/synaptiai/agent-capability-standard)
is one consumer. Its
[reference binding for Standard Agents](https://github.com/synaptiai/agent-capability-standard/tree/8ec818c217d55c8138986786c700da38a7ee25a6/examples/standard_agents)
requires a restore point and a recorded approval before a change, and enforces
that by wrapping each tool's `execute`, because no hook can do it. That works, and it shows
the limit described above: the rule holds only for tools written with the
wrapper. The
[integration notes](https://github.com/synaptiai/agent-capability-standard/blob/8ec818c217d55c8138986786c700da38a7ee25a6/docs/integrations/standard_agents.md)
have the detail.
