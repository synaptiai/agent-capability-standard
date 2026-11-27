# Specify the lifecycle operations code calls to create and message a child

## Problem

The 0.2.0 text says that code can create a child, and no page gives the
call.

- Instances are created by "runtime code (`invokeTool` / `queueTool` on the
  lifecycle surface, or dedicated runtime APIs) from tools, hooks, and
  handlers"
  ([Subagents §3.1](https://standardagentspec.org/0.2.0/specification/subagents#31-creation-paths)).
- A handler creates child instances "via lifecycle APIs"; where prompts have
  the injected tools, "a handler calls the same operations as code"
  ([Handlers §6](https://standardagentspec.org/0.2.0/specification/handlers#6-capabilities)).
- A `hidden` relationship stays "spawnable by runtime code
  (`invokeTool`/`queueTool` from hooks, tools, and handlers)"
  ([Runtime §7.3](https://standardagentspec.org/0.2.0/infrastructure/runtime#73-optional--immediate--hidden-branches)).

`ThreadState` has `getChildThread` and no method that creates a child
([Threads §1.2.2](https://standardagentspec.org/0.2.0/specification/threads#122-methods)),
in the text or in the published types (0.45.10). Five points are open.

1. **The name.** The target may be `subagent_create` with its `agent`
   argument, or the relationship name: "Relationship names are tool names."
   ([Subagents §1](https://standardagentspec.org/0.2.0/specification/subagents#1-subagentrelationship))
   A comment in the published types mentions "the exposed relationship name
   that may be passed to `state.invokeTool()` or `state.queueTool()`"; the
   text does not.
2. **The result.** For a successful call, only the blocking case is
   described: `subagent_create` will "await the child session's close and
   return its result payload"
   ([Subagents §3.3](https://standardagentspec.org/0.2.0/specification/subagents#33-blocking-and-create-or-continue)).
   Nothing says that the result of any other call carries the new
   `reference` (`queueTool` returns `void`), or when `state.children` first
   lists the instance.
3. **Messaging.** `subagent_message` "queues a message to an existing
   instance by reference"
   ([Subagents §5](https://standardagentspec.org/0.2.0/specification/subagents#5-lifecycle-tools));
   beyond `agent`, its arguments are not named. Code holding a reference
   can call the child's `queueMessage` instead (Subagents §6.1).
4. **Arguments.** "The invocation arguments a subagent accepts are dictated
   solely by the *receiving* agent, through the `requiredSchema` of its side
   A prompt."
   ([Subagents §5.1](https://standardagentspec.org/0.2.0/specification/subagents#51-persistent-invocation-arguments))
   A side A backed by a handler or a human has no prompt. For subagent
   threads, "runtimes **MUST** restore the creation-time
   `subagent_create.arguments` object into `ThreadState.arguments` on every
   run"
   ([Threads §6.1](https://standardagentspec.org/0.2.0/specification/threads#61-thread-arguments)).
   What such a child accepts, and what the runtime validates `arguments`
   against, is unstated. The arguments also carry the property that
   `initUserMessageProperty` names.
5. **The user.** For a thread a client creates, "The runtime **MUST** set
   the owner of the new thread from the authenticated caller."
   ([Thread Client API §6](https://standardagentspec.org/0.2.0/specification/threads/client-api#6-creating-a-thread))
   No page says which user a child thread has.

Authors meet these in ordinary work.

- A router or relay handler starts a child per customer, document or task
  and messages each one later, so it needs every reference.
- A `hidden` infrastructure child
  ([Runtime §7.3](https://standardagentspec.org/0.2.0/infrastructure/runtime#73-optional--immediate--hidden-branches)
  gives "background context compaction") that is not `immediate` can be
  created only by code.
- "A packed tool **MUST** declare the targets it invokes by name."
  ([Tools §2.1](https://standardagentspec.org/0.2.0/specification/tools#21-tool-dependencies))
  Its author has to know the name.
- `env()` falls back to "User-account environment variables"
  ([Threads §2.3](https://standardagentspec.org/0.2.0/specification/threads#23-environment-variable-resolution)),
  and a non-administrative caller lists "only threads that the caller owns"
  ([Thread Client API §7](https://standardagentspec.org/0.2.0/specification/threads/client-api#7-listing-threads)).
  Both depend on the child's user.

## Proposed rule

Add "5.3 Lifecycle operations from code" to Subagents §5. A wording close to
the existing text follows; where the intent differs, the text should say so.

- Runtimes **MUST** accept `state.invokeTool('subagent_create', args)`, and
  the same call to `state.queueTool`, from tools, hooks and handlers, for
  any declared and enabled relationship, `hidden` or not. `args` has the
  `agent`, `name` and `arguments` members of §5. The checks a model's call
  meets still apply (`maxInstances`, §5, §5.1, §5.2), and so does the `uses`
  list of a calling tool (Tools §2.1).
- For a relationship that is not `blocking`, a successful `invokeTool`
  result **MUST** carry the new instance's `reference`. The form needs
  stating: `ToolResult.result` is a string in the published types.
- When the call resolves, `children` on the calling `ThreadState` **MUST**
  include the new entry.
- `subagent_message` takes the relationship (`agent`, per §2.3), the
  instance reference, the message text and, if it carries them, attachment
  paths; the subsection names them.

And one sentence in each of two places:

- §5.1: "When the child's side A has no `requiredSchema`, runtimes **MUST**
  accept `arguments` without validation, and persist and hydrate them as
  above."
  [Runtime §7.4](https://standardagentspec.org/0.2.0/infrastructure/runtime#74-initial-payload-mapping)
  restates the validation rule ("should be validated", where §5.1 says
  **MUST**) and needs the same sentence.
- §4: "A child thread's user is its parent's user, and `userId` on the
  child reports it." Who the person on a human-backed side is stays a
  runtime concern
  ([Agents §1.1](https://standardagentspec.org/0.2.0/specification/agents#11-the-three-backings)).

## Alternatives considered

- **Declare the child `immediate` and read `state.children`**, as the relay
  in
  [Handlers §9](https://standardagentspec.org/0.2.0/specification/handlers#9-worked-example-the-relay)
  does. This is specified, but it cannot create an instance on demand or
  pass arguments that code computed.
- **Look for the new entry in `state.children` after the call.** The text
  does not say when that array changes. An entry has no member for the call
  that created it; `threadName` and `initialArguments` could identify it,
  and both are optional
  ([Subagents §4.2](https://standardagentspec.org/0.2.0/specification/subagents#42-registry)).
- **Take the child from `after_subagent_created`.** The hook runs "On parent
  after child thread creation"
  ([Hooks §1.1](https://standardagentspec.org/0.2.0/specification/hooks#11-available-hooks))
  and receives the child's `ThreadState`. It has a table row and a
  signature and no section, so the text does not say that it has run when
  the creating call returns. It returns nothing: it would have to leave the
  child in `state.context` for the creating code.
- **Use the "dedicated runtime APIs".** They are undefined, and "Packed
  definitions MUST NOT require private runtime RPCs"
  ([Packaging](https://standardagentspec.org/0.2.0/distribution/packaging#portability-requirements)).
- **Add a creation method to `ThreadState`.** It could return the registry
  entry as a typed value. It is a new method for every runtime, where the
  text already names `invokeTool` and `queueTool` as the route.
- **Let a handler declare an argument schema**, used where the side A
  prompt's `requiredSchema` is used. This is a larger change: `defineHandler`
  takes `description` and `execute`
  ([Handlers §1](https://standardagentspec.org/0.2.0/specification/handlers#1-handler-definition)),
  and a human-backed side A would still have no schema.

## Open questions

If a relationship name is also a target, which form is normative? A
defaulted name can equal an exposed agent's name, and
[Threads §1.1](https://standardagentspec.org/0.2.0/specification/threads#11-agent-assignment)
has "Queue a tool call to an agent to trigger handoff programmatically", so
one name could mean a handoff or a new child.

Is a lifecycle tool's name a legal `uses` entry? Tools §2.1 describes `uses`
as "names of tools, prompts, or agents" and says "A package **MUST** include
its required tool dependencies"; a runtime-injected tool is not a definition
that a package includes.

## Conformance impact

Additive for existing packages: no definition changes meaning. Each rule is
a new requirement on runtimes of the version that adds it. Checks: a handler
and a tool each create an instance of a `hidden` relationship that is not
`immediate`; the result's `reference` resolves through `getChildThread`;
`state.children` lists the instance when the call resolves; a handler-backed
child reads its creation `arguments` from `state.arguments`; the child's
`userId` equals its parent's.

The [Agent Capability Standard](https://github.com/synaptiai/agent-capability-standard)
is one consumer. Its
[reference binding for Standard Agents](https://github.com/synaptiai/agent-capability-standard/tree/8ec818c217d55c8138986786c700da38a7ee25a6/examples/standard_agents)
enforces its rules by wrapping each tool's `execute`, and `subagent_create`
is injected by the runtime and has no `execute` to wrap. A delegation that
is to be checked first has to be created from a wrapped tool or a handler,
and the binding composes no child today. The
[integration notes](https://github.com/synaptiai/agent-capability-standard/blob/8ec818c217d55c8138986786c700da38a7ee25a6/docs/integrations/standard_agents.md)
have the detail.
