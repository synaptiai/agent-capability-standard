# Record who or what sent a message

## Problem

A message record does not say where it came from. `role` is a perspective,
not a sender: "`role: 'user'` is the **side B** perspective" and
"`role: 'assistant'` is the **side A** perspective", whatever backs each side
([Messages §4](https://standardagentspec.org/0.2.0/specification/threads/messages#4-queueing-messages)).
A `role: 'user'` message can have been created by any of these:

- a person, through the Thread Client API's send route;
- a parent thread: "Parent traffic enters the child in the **side B
  perspective** (`role: 'user'`)"
  ([Subagents §6.1](https://standardagentspec.org/0.2.0/specification/subagents#61-parent--child)),
  including a `subagent_message` call a model chose to make;
- package code, through `queueMessage()` or `injectMessage()` in a tool, a
  hook, a handler, an effect or a thread endpoint;
- the runtime, as a child's completion message.

The record ([Messages §1](https://standardagentspec.org/0.2.0/specification/threads/messages#1-message-structure))
has no field for a sender. It has `subagent_id` and several projected
`subagent_*` fields "when available", but nothing says when a runtime sets
them, and a `before_create_message` hook returns the whole record, so package
code can set them too. The provenance keys in `metadata` are "conventions,
not requirements", consumers "**MUST** tolerate their absence"
([Messages §1.1](https://standardagentspec.org/0.2.0/specification/threads/messages#11-provenance-metadata-conventions)),
and any writer can set `metadata`. The send route itself accepts `role:
'user' | 'assistant' | 'system'`
([Thread Client API §12](https://standardagentspec.org/0.2.0/specification/threads/client-api#12-sending-a-message)),
so the role does not even say which side an authenticated caller wrote as.

The runtime knows the answer in every case. A runtime that exposes the Thread
Client API requires "an authenticated caller" on every route
([Thread Client API §3.1](https://standardagentspec.org/0.2.0/specification/threads/client-api#31-authentication-and-access)),
and the runtime itself performs every other kind of delivery. The
information is simply not passed on to the code that reads the message.

The specification already does this for hooks. A hook receives a `source`
that says why it is running: "This context is deterministic runtime metadata
and must not be inferred from mutable thread data"
([Hooks §2.4](https://standardagentspec.org/0.2.0/specification/hooks#24-execution-provenance)).
Messages have no equivalent.

Code that reads messages needs it in several ordinary situations:

- **A person's step in an automated composition.** The specification gives
  the approval gate as the canonical use of a human-backed side
  ([Agents §7](https://standardagentspec.org/0.2.0/specification/agents#7-human-in-the-loop-composition)).
  The child's parked turn "is fulfilled by an inbound message on that side's
  perspective"
  ([Agents §1.1](https://standardagentspec.org/0.2.0/specification/agents#11-the-three-backings)).
  The parent's traffic arrives on the same perspective. Read literally, the
  model that asked for approval can queue the message that ends the wait, and
  the child's code cannot tell that message from a person's answer.
- **Shared threads.** "`caller` identifies who is making the request, while
  `state.userId` identifies who owns the thread; the two frequently differ"
  ([Thread Endpoints §4](https://standardagentspec.org/0.2.0/specification/threads/endpoints#4-access-and-authentication)).
  A thread endpoint can see its caller. A handler or tool reading the
  conversation cannot see who wrote each message.
- **Treating forwarded text as data.** A relay, or a hook that guards against
  prompt injection, wants to treat a person's own words differently from text
  that code injected or forwarded from another thread.
- **Audit.** "Who said this?" has no answer in the record.

## Proposed rule

Add one optional, read-only member to the message record, set by the
runtime:

```typescript
interface MessageSender {
  /**
   * client:  accepted from an authenticated caller through the Thread Client API
   * model:   produced by a model step
   * tool:    a tool result
   * code:    created by package code (queueMessage / injectMessage from a tool,
   *          hook, handler, effect or endpoint)
   * thread:  delivered from a related thread (parent traffic, a child's
   *          completion, notifyParent)
   */
  kind: 'client' | 'model' | 'tool' | 'code' | 'thread';
  /** kind 'client': the authenticated caller's `ThreadUser.id`. */
  user_id?: string;
  /** kind 'thread': the thread the message came from. */
  thread_id?: string;
}

interface Message {
  // ...
  sender?: MessageSender | null;
}
```

(`origin` would be the natural name, but the Providers page already uses
`origin` for where an error arose.)

- A runtime that sets `sender` **MUST** set `kind: 'client'`, with `user_id`,
  on a message it accepted through the Thread Client API send route, and
  **MUST NOT** set `kind: 'client'` on any other message.
- `sender` **MUST NOT** be settable by a writer: it is not a member of
  `SendMessageRequest`, `InjectMessageInput`, `QueueMessageInput` or
  `MessageUpdates`, and a value returned for it by `before_create_message` or
  `before_update_message` **MUST** be ignored.
- `sender` is absent or `null` when the runtime does not record it. Consumers
  that depend on it feature-detect and fail closed.

The first rule is the one that matters: a message says `client` if and only
if an authenticated caller sent it. The other kinds could be fewer or
differently named without affecting that.

This does not ask the specification to define who a person is or how they
are authenticated. That stays "implementation-defined", as Thread Endpoints
§4 says. It asks only that what the runtime already knows about a message
reaches the code that reads it.

### A related clarification

With `sender` in place, Agents §1.1 could say precisely which messages fulfil
a human-backed side's turn. Two options:

1. Document today's behaviour: any message on that side's perspective
   fulfils it, and code that needs a person's answer checks `sender`.
2. Add an opt-in on `HumanSide`, for example `fulfilledBy: ['client']`, so
   that only such messages end the parked state.

Either removes the ambiguity. Option 1 needs no new behaviour.

### One thing to decide

A `message_data` frame carries the complete message record
([Thread Client API §16.1](https://standardagentspec.org/0.2.0/specification/threads/client-api#161-server-frames),
item 3), so `sender.user_id` would reach every client connected to the
thread. For a
thread several people can access, that tells each of them who wrote what.
That is usually the point, but it is a disclosure the specification should
choose deliberately: either state that it is intended, or let a runtime omit
`user_id` from frames sent to other callers.

## Alternatives considered

- **Keep the `metadata` conventions.** They are optional and writable by any
  code, so they cannot carry a guarantee.
- **Use a thread endpoint instead of a message for anything that needs the
  caller.** This works today and is the right tool for a structured decision.
  It does not help code that reads the conversation, and a person's reply in
  a chat surface is a message.
- **Infer the sender from `role`.** The send route lets a caller choose the
  role, and several kinds of sender share each role.

## Conformance impact

Additive: a new optional field that existing code ignores. A runtime that
implements it would be checked for: a message accepted through the send
route has `sender.kind === 'client'` and the caller's id; messages created by
`queueMessage()` and `injectMessage()`, by `subagent_message`, and by a
child's completion do not; a writer cannot set or change `sender`.
