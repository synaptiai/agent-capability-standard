# State the persistence and delivery guarantees of thread files, scheduled effects and eligible history

## Problem

The durable key-value store has nine numbered runtime rules
([Runtime, Durable Key-Value Store](https://standardagentspec.org/0.2.0/infrastructure/runtime#14-durable-key-value-store),
§14.1). Three other things that packages rely on across executions are
described and not required, so two conforming runtimes can differ on each.

**1. The thread file system.** The File System page says each thread's file
system "survives execution cycles — two separate invocations of the same
thread see the same file tree"
([File System](https://standardagentspec.org/0.2.0/specification/threads/filesystem)),
and Threads §7.3 lists it as "Durable"
([Threads §7.3](https://standardagentspec.org/0.2.0/specification/threads#73-comparison-with-other-storage)).
The page has one requirement keyword, on the order of streamed chunks
([§9.4](https://standardagentspec.org/0.2.0/specification/threads/filesystem#94-behavior)),
and the Runtime conformance summary mentions files only for attachment
copying. No passage requires that a file written in one execution is there
in the next, or after a restart or a redeploy; that a completed write is
visible to the next file call; or that one thread's tree is isolated from
another's. Smaller points are open too: whether `writeFile` replaces an
existing path and creates missing parent directories (`moveFile`, by
contrast, "does not overwrite",
[§5](https://standardagentspec.org/0.2.0/specification/threads/filesystem#5-moving-and-renaming)),
the glob grammar of `findFiles`, and what `readFile` returns for a file
whose `storage` is external. `moveFile` and `renameFile` are not in the
Threads method table.

**2. Scheduled effects.** Runtimes "**MUST** enqueue effects asynchronously
for execution" and "**MUST** preserve scheduled `args` until execution time"
([Effects §3](https://standardagentspec.org/0.2.0/specification/effects#3-execution-semantics)).
No passage says that a scheduled effect survives a restart or a redeploy,
that it never runs before its scheduled time, how many times its handler may
run, or what follows a throw. "**SHOULD** keep effect handlers idempotent" is
addressed to runtimes, which do not write the handlers. When
`removeScheduledEffect` returns `false` is stated only in a comment in the
published types. A scheduled effect is the only time-based trigger the text
defines
([Runtime §2](https://standardagentspec.org/0.2.0/infrastructure/runtime#2-invocation-triggers)),
and the Examples page asks for a reminder posted "24 hours later, even if
the conversation has ended"
([Examples §4](https://standardagentspec.org/0.2.0/getting-started/examples#4-effects)),
so a reminder, a timeout or a watchdog built on one is not portable.

**3. Eligible persisted history.** Runtime §4 and Hooks §3 require a
"stable snapshot of eligible persisted history"
([Runtime §4](https://standardagentspec.org/0.2.0/infrastructure/runtime#4-context-assembly),
[Hooks §3.4](https://standardagentspec.org/0.2.0/specification/hooks#34-stored-history-and-the-request-context)).
The text fixes eligibility by the time a message was persisted, and says
silent messages remain eligible. It does not define eligibility in terms of
`includeChat`, `includePastTools`, depth, the rendering side or message
status. What the two flags exclude is stated in one table row each ("Include
full chat history", "Include past tool results",
[Prompts §1.2](https://standardagentspec.org/0.2.0/specification/prompts#12-optional-properties))
and on the non-normative Examples page, which says "The default excludes past
tool results". The text does not say whether a tool result of an earlier
step of the current execution is a past tool result. Whether a model sees a
tool's result on its next step by default therefore depends on the runtime.

## Proposed rule

**Thread files.** Add a "Thread File System" section to the Runtime page,
worded like the key-value rules, and one line in the conformance summary:

1. Files **MUST** persist for the thread's lifetime across executions,
   process restarts and runtime redeploys.
2. A completed write, delete, move or rename **MUST** be visible to every
   later file call on the same thread, in any execution context.
3. Each thread's tree **MUST** be isolated: no file call on one thread
   resolves a path of another, and nothing is copied or inherited except as
   the attachment-copying rules say.

Separately, say whether `writeFile` replaces an existing path and creates
missing parent directories, give the glob grammar of `findFiles`, say what
`readFile` returns for an externally stored file, and add `moveFile` and
`renameFile` to the Threads method table.

**Scheduled effects.** Add to Effects §3:

1. A scheduled effect **MUST** be persisted with the durability the
   key-value store requires, and **MUST NOT** run before its scheduled time.
2. The delivery guarantee: at-least-once (the handler can run more than once
   after a failure, so it has to be idempotent) or at-most-once. Either is
   workable if it is stated.
3. What follows a throw: retried, and how, or dropped.
4. Whether an effect handler may schedule effects.

Address the idempotency advice to effect authors, and move the return values
of `removeScheduledEffect` from the type comment into Threads §4.3.

**Eligible history.** Define eligibility in Runtime §4: which persisted
messages a snapshot contains as a function of `includeChat`,
`includePastTools`, `depth` and `parent_id`, the rendering side and message
`status`, and in particular whether the tool results of the current
execution are included when `includePastTools` is `false`. The published
types add `PromptDefinition.historyLimit`, which narrows
`execution.messageHistory` and is not in the text; if it belongs to 0.2.x,
document it here with its effect.

## Alternatives considered

- **Keep durable state in the key-value store only.** It is the one store
  with stated rules, but values are small and JSON, and its capacity caps are
  implementation-defined. Files are the store the text names for "Large or
  binary payloads".
- **Use an external scheduler.** A package that needs a reminder or a
  timeout to fire can call a scheduler outside the runtime through an
  endpoint. That works on every runtime, and is a dependency the text's own
  effect example does not need.
- **Set `includePastTools: true` on every prompt whose tools return
  results the model must read.** This is the safe choice today. It sends
  every earlier tool result to the model, which a prompt may not want, and
  it is not what the property's description suggests a default prompt
  receives.

## Conformance impact

The file rules and the first effect rule codify what the pages already
describe, so a runtime that meets the description needs no change. The
delivery guarantee, the throw rule and the eligibility definition are new
statements; each is a requirement on runtimes of the version that adds it.
Checks: a file written in one execution is read in the next and after a
restart; a write is visible to the next call; one thread cannot read
another's file; a scheduled effect survives a restart and does not run early;
a throwing handler is treated as stated; and the messages a snapshot holds
under each combination of the two flags.

The [Agent Capability Standard](https://github.com/synaptiai/agent-capability-standard)
is one consumer. Its
[reference binding for Standard Agents](https://github.com/synaptiai/agent-capability-standard/tree/8ec818c217d55c8138986786c700da38a7ee25a6/examples/standard_agents)
keeps a restore point in a thread file, so a rollback rests on persistence
the text describes and does not require; a workflow run hosted in a thread
has to end a wait at its timeout, and a scheduled effect is the only timer;
and a tool that declines a call explains why in its result, so whether the
model sees that result on its next step decides whether the agent can
proceed. The
[integration notes](https://github.com/synaptiai/agent-capability-standard/blob/8ec818c217d55c8138986786c700da38a7ee25a6/docs/integrations/standard_agents.md)
have the detail.
