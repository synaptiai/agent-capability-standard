# Record the authenticated caller on a message sent through the Thread Client API

## Problem

A message record does not say who sent it. `role` is a perspective, not a
sender: "`role: 'user'` is the **side B** perspective" and
"`role: 'assistant'` is the **side A** perspective", whatever backs each side
([Messages §4](https://standardagentspec.org/0.2.0/specification/threads/messages#4-queueing-messages)).
A `role: 'user'` message can have been created by any of these:

- a person or a service, through the Thread Client API's send route;
- a parent thread: "Parent traffic enters the child in the **side B
  perspective** (`role: 'user'`)"
  ([Subagents §6.1](https://standardagentspec.org/0.2.0/specification/subagents#61-parent--child)),
  including a `subagent_message` call a model chose to make;
- package code, through `queueMessage()` or `injectMessage()` in a tool, a
  hook, a handler, an effect or a thread endpoint;
- the runtime, as a child's completion message.

The record ([Messages §1](https://standardagentspec.org/0.2.0/specification/threads/messages#1-message-structure))
already answers part of this. `prompt` is the "Name of the prompt that
produced the message", and `subagent_id` with the projected `subagent_*`
fields relate a message to a child. It does not cover the first case, a
message a client sent, and that is the one case only the runtime can attest.
The send route requires "an authenticated
caller"
([Thread Client API §3.1](https://standardagentspec.org/0.2.0/specification/threads/client-api#31-authentication-and-access)),
so the runtime has resolved who that caller is, and the stored message does
not keep it. The route also accepts `role: 'user' | 'assistant' | 'system'`
([Thread Client API §12](https://standardagentspec.org/0.2.0/specification/threads/client-api#12-sending-a-message)),
so the role does not even say which side the caller wrote as.

The provenance keys in `metadata` do not fill the gap. They are "conventions,
not requirements", consumers "**MUST** tolerate their absence"
([Messages §1.1](https://standardagentspec.org/0.2.0/specification/threads/messages#11-provenance-metadata-conventions)),
and any code that creates or rewrites a message can set `metadata`.

Code that reads messages needs the caller in several ordinary situations:

- **A person's step in an automated composition.** The specification gives
  the approval gate as the canonical use of a human-backed side
  ([Agents §7](https://standardagentspec.org/0.2.0/specification/agents#7-human-in-the-loop-composition)).
  The child's parked turn "is fulfilled by an inbound message on that side's
  perspective"
  ([Agents §1.1](https://standardagentspec.org/0.2.0/specification/agents#11-the-three-backings)).
  The parent's traffic arrives on the same perspective. Read literally, the
  model that asked for approval can queue the message that ends the wait, and
  the child's code cannot tell that message from a client's.
- **Shared threads.** "`caller` identifies who is making the request, while
  `state.userId` identifies who owns the thread; the two frequently differ"
  ([Thread Endpoints §4](https://standardagentspec.org/0.2.0/specification/threads/endpoints#4-access-and-authentication)).
  A thread endpoint can see its caller. A handler or tool reading the
  conversation cannot see who wrote each message, and two clients cannot
  show who said what.
- **Audit.** "Who sent this?" has no answer in the record.

## Proposed rule

Add one read-only member to the message record:

```typescript
interface Message {
  // ...
  /**
   * The id of the authenticated caller, for a message accepted through the
   * Thread Client API send route. `null` on every other message.
   */
  user_id: string | null;
}
```

- For a message accepted through the send route (Thread Client API §12), the
  runtime **MUST** set `user_id` to the id of the authenticated caller, the
  id a thread endpoint sees as `auth.caller.id`. On every other message it
  **MUST** be `null`.
- `user_id` **MUST NOT** be settable by a writer: it is not a member of
  `SendMessageRequest`, `InjectMessageInput`, `QueueMessageInput` or
  `MessageUpdates`, and a value returned for it by `before_create_message` or
  `before_update_message` **MUST** be ignored.

The name and the rule both have precedent in the Thread Client API. A thread
record already has `user_id` for its owner, and of creating a thread it says:
"The runtime **MUST** set the owner of the new thread from the authenticated
caller. The request **MUST NOT** be able to name a different owner."
([§6](https://standardagentspec.org/0.2.0/specification/threads/client-api#6-creating-a-thread))

### What this does not ask for

The Agents page says: "The specification deliberately does **not** define who
the person is or how their input arrives — identity, notification, and reply
surfaces are runtime and interface concerns." This proposal stays inside that
boundary. It does not define who a caller is, whether the caller is a person,
or how they authenticate; that remains "implementation-defined", as Thread
Endpoints §4 says. It asks only that the id the runtime has already resolved
for the request is kept with the message the request created.

### A related clarification

Agents §1.1 could then say which messages fulfil a human-backed side's turn:
any message on that side's perspective, and code that needs a client's answer
checks `user_id`. Agents §1.1 reads that way today. Agents §4 and §7 and
Runtime §3 speak of "the human's inbound message", so the sentence would also
settle which of the two readings a runtime follows.

### One thing to decide

A `message_data` frame carries the complete message record
([Thread Client API §16.1](https://standardagentspec.org/0.2.0/specification/threads/client-api#161-server-frames),
item 3), so `user_id` would reach every client connected to the thread. For a
thread several people can access, that tells each of them who wrote what.
That is usually the point, but it is a disclosure the specification should
choose deliberately: either state that it is intended, or let a runtime omit
`user_id` from frames sent to other callers.

## Alternatives considered

- **Keep the `metadata` conventions, or add a key to them.** They are
  optional and writable by any code, so they cannot carry a guarantee unless
  the runtime also overwrites a value that a client or package code supplied.
  A reserved key with that rule would serve as well as a member of the
  record.
- **Use a thread endpoint instead of a message for anything that needs the
  caller.** This works today and is the right tool for a structured decision.
  It does not help code that reads the conversation, and a person's reply in
  a chat surface is a message.
- **Infer the sender from `role`.** The send route lets a caller choose the
  role, and several kinds of sender share each role.
- **A `sender` object that classifies every message** (client, model, tool,
  package code, another thread). The record already says which prompt
  produced a message and which child it relates to, so most of such a
  classification would repeat it. The client case is the one that only the
  runtime can fill in; with it, code can tell a client's message from every
  other.

## Conformance impact

Additive: one new member that existing code ignores, required of runtimes
that expose the Thread Client API in the version that adds it. Checks: a
message accepted through the send route has the caller's id; messages created
by `queueMessage()` and `injectMessage()`, by `subagent_message`, and by a
child's completion have `null`; no input type and no message hook can set or
change it.
