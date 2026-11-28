# Say what a parent receives for each way a child session ends

## Problem

A child session can end in five ways: a `sessionStop` call, a `sessionFail`
call, `state.stopSession()` from code, a turn cap, and an error. Subagents
§4.1 lists the same set: "When a child session ends — stop, fail, error, or
turn-cap — the registry status transitions (`running` → `idle` / `failed`)"
([Subagents §4.1](https://standardagentspec.org/0.2.0/specification/subagents#41-persistence-is-universal)).
What reaches the parent is stated for the first two only, and three gaps
follow from that.

**1. Code cannot end a session as failed.** `sessionFail` is a binding that
only a prompt-backed side may declare: session bindings on a non-prompt side
are a definition-time error
([Agents §8](https://standardagentspec.org/0.2.0/specification/agents#8-definition-time-errors),
item 6), and "handlers end sessions through `ThreadState` APIs
(`state.stopSession()`) rather than declarative bindings"
([Agents §1.2](https://standardagentspec.org/0.2.0/specification/agents#12-sideconfig)).
`state.stopSession()` is a success: "Implementations should treat this as a
successful terminal child run for blocking and non-blocking subagent
lifecycle handling"
([Runtime §8.3](https://standardagentspec.org/0.2.0/infrastructure/runtime#83-status-updates)),
and its reason `state_stop_session` settles `idle`
([Execution State §4.2](https://standardagentspec.org/0.2.0/specification/threads/execution-state#42-reasons)).
Its published options are `result`, `notifyParent` and `status`. Yet
[Handlers §5](https://standardagentspec.org/0.2.0/specification/handlers#5-error-semantics)
says that session failure (`sessionFail` / `stopSession`) is something "a
handler must invoke explicitly if an error should end the session". A
handler-backed child, or tool code, can report failure to its parent only
inside the text of a successful result, and the run status and a blocking
caller record success.

**2. Whether `state.stopSession()` sends the completion message is not
stated.** Subagents §6.2 defines the message for a session that "ends via
`sessionStop`" under `implicit` parent communication, and says `sessionFail`
"similarly delivers a failure message"
([Subagents §6.2](https://standardagentspec.org/0.2.0/specification/subagents#62-child--parent-completion-and-failure)).
For `state.stopSession()`, Runtime §8.3 treats the end as a successful
terminal run, with a lower-case "should", while the published types (0.45.10)
say of its `result`: "This does not send a parent message by itself." For a
turn cap or an error, the text gives only the registry transition. A parent
under `implicit` communication cannot know whether such a child's end wakes
it, or delivers `result`. A child that also passes `notifyParent` to be sure
can produce two messages on a runtime that queues the implicit one too.

**3. A blocking creation whose child does not close normally has no
outcome.** "`blocking: true` makes `subagent_create` await the child
session's close and return its result payload."
([Subagents §3.3](https://standardagentspec.org/0.2.0/specification/subagents#33-blocking-and-create-or-continue))
No result is defined when the child is terminated, when its run settles
`failed`, when it stops on a turn cap, or when the caller's own execution is
lost while it waits ("A lost execution settles to `failed` with reason
`execution_lost`",
[Execution State §4.3](https://standardagentspec.org/0.2.0/specification/threads/execution-state#43-requirements)).
No bound on the wait is stated. A child that parks for a person
([Subagents §4.3](https://standardagentspec.org/0.2.0/specification/subagents#43-human-in-the-loop-children))
can keep its caller waiting without limit, and the warning about holding the
thread is addressed to handlers only. A caller that builds its own deadline
from an effect and `terminate()` depends on what the blocked call then
returns.

All three come down to one table the text does not have: for each way a
child session ends, what the parent receives and what a blocking caller's
`subagent_create` returns.

## Proposed rule

Add to Subagents §6.2, and restate in Runtime §8.3, a table of the ways a
child session ends:

| The session ends by | Registry status | Under `implicit`, the parent receives | A blocking `subagent_create` returns |
|---|---|---|---|
| `sessionStop` | `idle` | The completion message (as today) | The result payload (as today) |
| `sessionFail` | `failed` | The failure message (as today) | An error result |
| `state.stopSession({ result })` | `idle` | The completion message, with `result` as its payload | `result` |
| `state.stopSession({ fail })`, below | `failed` | The failure message | An error result |
| A turn cap (`max_session_turns`) | `idle` | to be decided | to be decided |
| An error, or `execution_lost` | `failed` | The failure message | An error result |
| `state.terminate()` of the child | none: the instance is destroyed | to be decided | An error result |

The rows marked "to be decided" are the maintainers' choice; the point is
that each row has an answer. Three rules go with the table.

- **Failure from code.** Add an option to `stopSession()`, for example
  `fail: true` or `outcome: 'failed'`, that settles the run `failed` with
  reason `session_fail` and delivers the failure message, as the
  `sessionFail` binding does. Correct the sentence in Handlers §5 either
  way: if the option is not added, it should say that code cannot end a
  session as failed.
- **No double message.** When `stopSession()` is called with `notifyParent`
  under `implicit` communication, say whether the runtime queues both
  messages or only the explicit one.
- **An error result with a stable code.** Where the table says "an error
  result", the blocking call returns a tool result with `status: 'error'` and
  a code that names the row (for example `child_failed`,
  `child_terminated`), so a caller can tell a failed child from a finished
  one without parsing text. When the caller's own execution is lost while it
  waits, say what the recovery run does with the pending call: return the
  child's result to it, or store an error result for it. Waiting while a child is
  `awaiting_human` is ordinary waiting, and the §3.3 warning should apply to
  prompt-backed callers too. Optionally, a per-relationship bound on the
  wait.

## Alternatives considered

- **Report failure in the result text.** This is what code does today. A
  parent has to parse text, and the run status, a blocking caller and every
  client show success.
- **Have a handler child call a tool bound to `sessionFail`.** Session
  bindings are a definition-time error on a non-prompt side, and a handler
  has no model to call the tool.
- **Use `explicit` parent communication and `notifyParent` only.** This
  avoids the question of the implicit message, but a child's finish then
  "does not wake the parent at all"
  ([Subagents §6.4](https://standardagentspec.org/0.2.0/specification/subagents#64-child--parent-explicit-escalation)),
  and a blocking caller still gets no defined result for a child that fails.
- **Avoid `blocking` relationships.** A caller that spawns without blocking
  and reads the child's status later can set its own deadline, at the cost of
  the one composition pattern the text names for "run the child again".

## Conformance impact

The failure option is additive: a new optional member of the
`stopSession()` options and one more path to an existing reason code. The
table is mostly clarification: a runtime whose behaviour matches the adopted
rows changes nothing. Checks: each row's registry status, the message the
parent receives under `implicit` and `explicit`, and the result a blocking
caller receives, for each way the session ends; and that no session end
destroys the child thread, as Runtime §10 already requires.

The [Agent Capability Standard](https://github.com/synaptiai/agent-capability-standard)
is one consumer. A workflow it runs inside a handler-backed child ends a
failed run with `state.stopSession({ result })`, so the parent records a
success whose text carries the failure code, and a delegation that must be
bounded in time cannot use a `blocking` relationship. The
[integration notes](https://github.com/synaptiai/agent-capability-standard/blob/8ec818c217d55c8138986786c700da38a7ee25a6/docs/integrations/standard_agents.md)
have the detail.
