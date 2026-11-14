# State what a runtime does with a tool call the request did not offer

## Problem

"Tool calls **MUST** execute sequentially in the returned order"
([Runtime §5.1](https://standardagentspec.org/0.2.0/infrastructure/runtime#51-ordering))
does not say which calls. A model can return three kinds of call that the
request which produced it did not offer, and for none of them does a passage
of 0.2.0 say what the runtime does:

- a defined tool the active prompt does not list, or a name that no
  definition has. A prompt's `tools` are "Available tools, sub-prompts, and
  handoff agent tools"
  ([Prompts §1.2](https://standardagentspec.org/0.2.0/specification/prompts#12-optional-properties));
  nothing says a tool left out cannot be called;
- any call under `toolChoice: 'none'`. "The LLM **MUST NOT** call a tool in
  its response"
  ([Prompts §4.2](https://standardagentspec.org/0.2.0/specification/prompts#42-tool-choice-behavior))
  binds the model, while "Tool definitions **MAY** still be sent". For
  `'required'` the section says what the runtime does with the response
  ("Implementations **SHOULD** retry if the LLM fails to call a tool"); for
  `'none'` what it asks of the runtime concerns the request
  ("Implementations **MUST** pass `toolChoice: 'none'` to the provider with
  any tool definitions they send");
- a lifecycle call that targets a hidden relationship, which "stays
  declared" and is meant for children "the model must never invoke"
  ([Subagents §1](https://standardagentspec.org/0.2.0/specification/subagents#1-subagentrelationship)).
  The rejection rule names other cases: "Runtimes **MUST** reject lifecycle
  invocations that target undeclared or disabled relationships without
  creating a child"
  ([Subagents §5](https://standardagentspec.org/0.2.0/specification/subagents#5-lifecycle-tools)).

The neighbouring rule covers code, not models: "When a `uses` list is
supplied, the runtime **MUST** reject an invocation of a target outside the
list"
([Tools §2.1](https://standardagentspec.org/0.2.0/specification/tools#21-tool-dependencies)).

Authors meet these cases in ordinary use.

- A model misspells or invents a name. One runtime may persist an error
  result, another may fail the step, a third may drop the call. "Tool errors
  **MUST** be persisted as tool results"
  ([Runtime §5.2](https://standardagentspec.org/0.2.0/infrastructure/runtime#52-error-handling)),
  and the text does not say that a call with no tool to run is a tool error.
  The assistant message is persisted before its calls execute
  ([Runtime §3](https://standardagentspec.org/0.2.0/infrastructure/runtime#3-step-cycle)),
  so a dropped call stays in the history with no result.
- After a handoff the new agent works "within the same thread with full
  context preserved"
  ([Threads §1.1](https://standardagentspec.org/0.2.0/specification/threads#11-agent-assignment))
  and with its own prompt's tool list. A model can repeat a call it sees in
  the history, and whether it runs depends on whether the runtime resolves
  names against the request or against every definition it can see. The
  [Visibility Rules](https://standardagentspec.org/0.2.0/distribution/packaging#visibility-rules)
  limit which names resolve across packages ("**Packed code** sees only its
  own package contents plus other entry points"); within a package, or among
  unpacked definitions, they limit nothing.
- Prompts in one agent get different tools: a reviewer without the worker's
  tools, a read-only prompt beside one that writes. In
  [Examples §7](https://standardagentspec.org/0.2.0/getting-started/examples#7-dual-ai-agents)
  the artist's prompt lists `generate_image`, and the reviewer's lists
  `view_banner` and `approve_banner`.

For relationships the text speaks of a grant: "the *side's declaration* is
the grant"
([Prompts §3.4](https://standardagentspec.org/0.2.0/specification/prompts#34-subagent-lifecycle-tools)).
For a prompt's `tools` it leaves open whether the list limits what a model
can cause to run, or only describes what the model is told.

## Proposed rule

Add a subsection to
[Runtime §5](https://standardagentspec.org/0.2.0/infrastructure/runtime#5-tool-execution):

> A runtime **MUST NOT** execute a tool call returned by a model when the
> call's name was not in the tool list sent with the request that produced
> it, or when that request was made under `toolChoice: 'none'`. The runtime
> **MUST** persist an error tool result for the call, and the execution
> continues as after any other tool error (§5.2).

The tool list is the `tools` of the provider request
([Providers §2](https://standardagentspec.org/0.2.0/specification/providers#2-request-format)),
injected lifecycle tools included. The rule covers calls the runtime
executes: provider tools "execute server-side"
([Providers §10](https://standardagentspec.org/0.2.0/specification/providers#10-provider-tools))
and are outside it. Calls from code through `state.invokeTool()` and
`state.queueTool()` are unaffected; the `uses` list of a calling tool, where
it supplies one, governs those.

In Subagents §5, after the rejection sentence:

> A lifecycle call returned by a model that targets a hidden relationship, or
> an instance of one, **MUST** be rejected in the same way.

No type, definition or hook changes.

## Alternatives considered

- **Rely on the provider.** The provider interface does not require a
  provider to hold a model to the declared tools or to `none`: a returned
  call's `name` is a `string`
  ([Providers §3.2](https://standardagentspec.org/0.2.0/specification/providers#32-tool-calls)),
  with no stated relation to the request's `tools`.
- **A provider extension that filters the response.** An override of
  `generate` or `stream` is given the request and returns the response that
  carries the calls
  ([Providers §1.3](https://standardagentspec.org/0.2.0/specification/providers#13-provider-extension-factories),
  with the override types in §11), so it can drop a call the request did not
  offer. It belongs to a model definition, not to an agent or a prompt; a
  `stream` override has to rewrite the stream; and the text does not say
  that a runtime executes only the calls an override returns.
- **Argument validation.** Validating "tool args against the declared
  schema"
  ([Tools §9](https://standardagentspec.org/0.2.0/specification/tools#9-conformance-notes))
  applies once a call has resolved to a tool. For a hidden target it depends
  on a reading. The `agent` argument is to "enumerate the side's enabled
  relationship *names*"
  ([Subagents §5](https://standardagentspec.org/0.2.0/specification/subagents#5-lifecycle-tools)),
  and a hidden relationship can be enabled, while Subagents §1 has it
  "excluded from every LLM request's tool surface". If the enumeration
  leaves hidden names out, validation would catch a `subagent_create` that
  names one. A `subagent_message` addresses an instance "by reference", and
  no schema enumerates references.
- **A check in package code.** A tool can read
  `state.execution.promptPath` and refuse under a prompt it does not expect,
  which covers neither an unknown name, nor a lifecycle tool, nor a tool the
  author did not write. The one tool hook that runs before execution cannot
  decline a call: "The return value **MUST** be ignored; the hook cannot
  modify the tool call"
  ([Hooks §5.1](https://standardagentspec.org/0.2.0/specification/hooks#51-tool_call_started)).
  A `before_create_message` hook can rewrite the assistant message, since
  "The returned object **MUST** be used for insertion"
  ([Hooks §4.1](https://standardagentspec.org/0.2.0/specification/hooks#41-before_create_message));
  the text does not say that the runtime executes the calls of the stored
  message and not the calls the model returned.

## Open questions

Does `stopTool` or a session binding act on a refused call? `stopTool` is
"Stop side turn when this tool is called"
([Agents §1.2](https://standardagentspec.org/0.2.0/specification/agents#12-sideconfig)),
and no rule requires a bound tool to be in the prompt's `tools`.

Do the hooks of
[Hooks §5](https://standardagentspec.org/0.2.0/specification/hooks#5-tool-execution-hooks)
run for a refused call? `tool_call_started` and `tool_call_done` are each
required "once per tool call"; `after_tool_call_failure` is "Called after a
tool execution fails", and a refused call has no execution.

## Conformance impact

A package whose models call only offered tools behaves as before. A runtime
that already refuses these calls needs at most to persist the error result;
one that resolves returned names against every definition it can see adds
the check. With a scripted provider, conformance checks would cover:

- a call to a defined tool the active prompt does not list, to an undefined
  name, or to a listed tool under `toolChoice: 'none'` is not executed and
  gets a persisted error result with its `tool_call_id`, and the step cycle
  continues;
- a model-issued `subagent_create` naming a hidden relationship creates no
  child, and code can still spawn one.

The [Agent Capability Standard](https://github.com/synaptiai/agent-capability-standard)
is one consumer. Its
[reference binding](https://github.com/synaptiai/agent-capability-standard/tree/main/examples/standard_agents)
enforces its rules inside each of its tools' `execute`, so they hold however
a call arrives. Two arrangements in its
[integration notes](https://github.com/synaptiai/agent-capability-standard/blob/main/docs/integrations/standard_agents.md)
rest on the missing rule: a guard tool in front of a tool written without
the binding, and a parent that gates delegation by spawning children from
code with every relationship `hidden`.
