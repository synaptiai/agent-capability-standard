# Say what may run alongside an execution of a thread, and when `flowId` changes

## Problem

The 0.2.0 rule on concurrency within a thread is: "A single thread **MUST
NOT** execute multiple concurrent flows. Cross-thread concurrency is
allowed."
([Runtime §11](https://standardagentspec.org/0.2.0/infrastructure/runtime#11-concurrency))
No passage defines a flow. The same page requires runtimes to "execute one
step at a time per thread" (§1) and to "prevent per-thread concurrent
execution"
([§16](https://standardagentspec.org/0.2.0/infrastructure/runtime#16-conformance-summary)),
and the text leaves three cases open.

- **Effects.** A scheduled effect is a trigger at which "Execution begins",
  and "If a thread is already executing, new work is queued."
  ([Runtime §2](https://standardagentspec.org/0.2.0/infrastructure/runtime#2-invocation-triggers))
  Effects also "Run **independently** of the conversation flow"
  ([Threads §4](https://standardagentspec.org/0.2.0/specification/threads#4-effect-scheduling)),
  and `context` shares values "between tools, hooks, effects, and runtime
  lifecycle code during one execution"
  ([Threads §6.2](https://standardagentspec.org/0.2.0/specification/threads#62-per-execution-context)).
  The three readings put an effect behind an execution, beside one, or
  inside one. The access-context table
  ([Threads §1.3](https://standardagentspec.org/0.2.0/specification/threads#13-access-contexts))
  omits effects and handler turns.
- **Thread endpoints.** "`state.execution` is always `null` because the
  thread is not actively executing"
  ([Thread Endpoints §5](https://standardagentspec.org/0.2.0/specification/threads/endpoints#5-endpoint-context)).
  The run status "describes the thread from outside: whether an execution is
  in flight", and is "available everywhere `ThreadState` is"
  ([Execution State §4](https://standardagentspec.org/0.2.0/specification/threads/execution-state#4-run-status)),
  which suggests that outside code can run during one. Nothing says that a
  request arriving during an execution waits, or that two are handled in
  turn.
- **Tools that code starts.** "Tool calls **MUST** execute sequentially in
  the returned order."
  ([Runtime §5.1](https://standardagentspec.org/0.2.0/infrastructure/runtime#51-ordering))
  That orders a model's calls, not two `state.invokeTool()` calls awaited
  together.

Handler delivery is serialized
([Handlers §4](https://standardagentspec.org/0.2.0/specification/handlers#4-delivery-semantics)),
and the Draft Users page serializes user endpoints because "Quotas, leases,
counters, and registries require read-modify-write atomicity"
([Users, Appendix A](https://standardagentspec.org/0.2.0/specification/users#appendix-a-notes-non-normative)).
The thread's key-value store has no such rule and no conditional write, and
its example is a counter
([Threads §7.1](https://standardagentspec.org/0.2.0/specification/threads#71-reading-and-writing-values)):

```typescript
const count = (await state.getValue<number>('invocation_count')) ?? 0;
await state.setValue('invocation_count', count + 1);
```

It is correct only if nothing writes the key between the two lines; so is a
usage total that a tool and a billing endpoint both update.

`flowId` is the other half: the "Unique execution ID"
([Execution State §2](https://standardagentspec.org/0.2.0/specification/threads/execution-state#2-execution-properties)),
in the published types (0.45.10) "unique per execution". Nothing says
whether a sub-prompt, a handoff, a tool queued mid-run, a tool call awaiting
a `blocking` child, or "a later recovery run"
([§4.3](https://standardagentspec.org/0.2.0/specification/threads/execution-state#43-requirements))
keeps it. `promptPath` has one value "Inside a sub-prompt" and another
"After handoff"
([§2.1](https://standardagentspec.org/0.2.0/specification/threads/execution-state#21-prompt-path)),
and each step begins with "Drain queued messages/tools for this step"
([Runtime §3](https://standardagentspec.org/0.2.0/infrastructure/runtime#3-step-cycle)),
which suggests that those three belong to the execution that reached them;
neither passage mentions the id. Stamping messages with the id (as
[Hooks §8.6](https://standardagentspec.org/0.2.0/specification/hooks#86-adding-metadata-to-messages)
does), a per-run budget or cache, and a confirmation that lapses with the
run all depend on the answer.

## Proposed rule

**1. Runtime §11.** Add:

- A flow is one execution of a thread: the span in which its run status is
  `running`.
- Effect handlers and executions of one thread **MUST NOT** overlap; the
  later one waits.
- `invokeTool` calls that code starts without awaiting one another **MUST**
  run one at a time, in the order started.
- A thread endpoint handler **MAY** run during an execution or beside
  another endpoint handler.

The effect clause is one reading of Runtime §2, which queues the work and
does not say when it then runs; as written, an effect cannot act as a
timeout on an execution that is still running. The tool clause follows
"preserve sequential step and tool execution within a thread"
([Runtime §16](https://standardagentspec.org/0.2.0/infrastructure/runtime#16-conformance-summary)).
The endpoint clause is the reading the run status suggests; with it,
`execution` is `null` in an endpoint while an execution is in flight, and
the reason given in Thread Endpoints §5 needs rewording.
Either answer works in each clause, once written. Where overlap is allowed,
the
[key-value section](https://standardagentspec.org/0.2.0/infrastructure/runtime#14-durable-key-value-store)
should say that `getValue` then `setValue` is not atomic.

**2. Threads §1.3.** Add rows for handler turns, where `execution` is
present
([Execution State §2.3](https://standardagentspec.org/0.2.0/specification/threads/execution-state#23-handler-turns)
says so), and for effects: present if an effect is an execution of its own,
null if not.

**3. Execution State §2.** Add:

- Each execution of a thread **MUST** have a `flowId` that no other
  execution of that thread has had, and it **MUST NOT** change while the run
  status is `running`.
- Hooks, sub-prompts and handler turns that run in an execution, and work
  queued during it, see its `flowId`. An execution that starts after the
  status has settled, a recovery run included, has a new one.

## Alternatives considered

- **Never share a key between writers.** The thread's key-value store
  cannot list keys, so an index of each writer's keys is itself a
  read-modify-write.
- **The thread's file system.** It lists a directory, so one file per
  record needs no index, and `moveFile` "does not overwrite" an existing
  destination
  ([File System §5](https://standardagentspec.org/0.2.0/specification/threads/filesystem#5-moving-and-renaming)).
  The page does not say what two callers that race get, and a counter or a
  total is still a read-modify-write.
- **The Users page's serialization.** The page is a draft, a thread may
  have no user, and it excludes thread state: "Operations on the resolved
  `ThreadState` execute in the thread scope; the §2.1 guarantee does not
  extend across them."
  ([Users §2.2](https://standardagentspec.org/0.2.0/specification/users#22-reaching-threads))
- **Route every write through a tool.** An endpoint that calls `queueTool`
  gets `void` back; `invokeTool` from an endpoint is open question 2.
- **Check the run status before writing.** `state.status()` tells an
  endpoint whether an execution is in flight (Execution State §4). The
  check and the write are two steps, and it orders neither two requests nor
  an effect.
- **`state.context` in place of `flowId`.** Its scope is "Single execution
  only"
  ([Threads §6.3](https://standardagentspec.org/0.2.0/specification/threads#63-context-limitations)):
  the same undefined boundary, and it is not durable.
- **`status().since` in place of `flowId`.** "`since` **MUST** change only
  when `state` or `reason` changes"
  ([Execution State §4.3](https://standardagentspec.org/0.2.0/specification/threads/execution-state#43-requirements)),
  and the published types call it "When the thread entered this state", so
  its value while `running` marks one execution, at the cost of a call.
  Part 3 gives `flowId` that boundary. The text does not connect the two
  today, and the Hooks §8.6 example stamps `flowId`.

## Open questions

1. Does the run status stay `running` through a handoff, and while a tool
   call awaits a `blocking` child
   ([Subagents §3.3](https://standardagentspec.org/0.2.0/specification/subagents#33-blocking-and-create-or-continue))?
   If so, both keep the `flowId`.
2. `invokeTool` from an endpoint: the published types say that on a thread
   that is not executing it "creates a minimal execution context for the
   tool"; the text does not. Does that context have a `flowId`, and what
   happens when an execution is in flight?
3. Should the tool clause except the lifecycle tools? As written, two
   `subagent_create` calls for `blocking` relationships that code starts
   together wait on each child in turn, as a model's two calls already do
   under Runtime §5.1.

## Conformance impact

No interface, type or package changes. Each **MUST** above is a new
requirement on runtimes of the version that adds it; a runtime changes only
where it differs from the adopted wording. Checks: an effect due during an
execution starts after the status settles; two `invokeTool` calls started
together do not overlap; `state.execution` in an effect and in a handler
turn matches the table; a sub-prompt and a queued tool see the caller's
`flowId`; the next execution sees another.

The [Agent Capability Standard](https://github.com/synaptiai/agent-capability-standard)
is one consumer. Its
[reference binding for Standard Agents](https://github.com/synaptiai/agent-capability-standard/tree/8ec818c217d55c8138986786c700da38a7ee25a6/examples/standard_agents)
keeps a trace counter, a list of restore points and approvals in the
thread's key-value store, written by tools, a hook and an endpoint. Nothing
orders an endpoint request against a running tool call or against a second
request, so each approval has its own key, and two arriving together
can still drop one from the approver list; a restore point counts only in
the execution that took it, by `flowId`, with a ten-minute limit that holds
whatever a runtime does with the id. The
[integration notes](https://github.com/synaptiai/agent-capability-standard/blob/8ec818c217d55c8138986786c700da38a7ee25a6/docs/integrations/standard_agents.md)
state both limits.
