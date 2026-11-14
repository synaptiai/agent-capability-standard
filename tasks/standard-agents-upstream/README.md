# Proposals for the Standard Agent Specification

Issue texts for [`standardagents/spec`](https://github.com/standardagents/spec),
ready to file. Each file is one issue: the first line is the title, the rest
is the body. They come out of the mapping in
[Standard Agents interoperability](../../docs/integrations/standard_agents.md).

**Status: not filed.** They are written against 0.2.0 at commit `faccc8b`
(12 November 2026). Before filing, check that the passages they quote are
unchanged; the specification's maintainers edit 0.2.0 in place. Their
community page says accepted changes are published "in a new version of the
specification", so each addition proposed here would apply from that version.

| # | Title | Why it matters for a grounded agent | Size |
|---|-------|-------------------------------------|------|
| [01](01-before-tool-call-hook.md) | Define a hook that runs before a tool executes and can decline the call | Lets a safety rule be imposed on tools one did not write. Today a rule holds only inside tools written with the binding | One new hook |
| [02](02-message-sender.md) | Record the authenticated caller on a message sent through the Thread Client API | Lets code tell a client's answer from a message a model or a parent queued. An approval gate built on messages cannot be trusted without it | One read-only field |
| [03](03-tool-call-identity.md) | Let a tool know which call it is serving | Lets a tool's own records (evidence, audit, idempotency keys) be tied to the stored tool result | One optional property |
| [04](04-tool-result-contract.md) | Specify what a tool's `execute` returns, and give results a field for metadata | Gives refusal codes and evidence a defined place that is not model-facing text | Text, plus one optional field |
| [05](05-annotations.md) | Annotations: allow them on agents and prompts, pass a tool's to its hooks, and say whom the rule binds | Lets a composed agent carry a classification, and lets a hook read a tool's | Three optional fields, one reworded sentence |
| [06](06-editorial-inconsistencies.md) | Nine inconsistencies in the 0.2.0 text | None directly; found while checking references | Editorial |

## Order

File 06 first: it is small, checkable and asks for nothing. Then 01, which
the others do not depend on but which matters most. 02 to 05 are independent
of one another.

## How the maintainers take proposals

From their community page, and from their issue tracker as it read on 14
November 2026 (paraphrased; check the issues themselves before relying on
the wording):

- "A conversation or a pull request is enough to propose a change." There is
  no template and no formal process.
- Two earlier proposals
  ([#1](https://github.com/standardagents/spec/issues/1),
  [#3](https://github.com/standardagents/spec/issues/3)) were closed as not
  planned because each was framed around one product's needs. The closing
  comments ask for a product-neutral proposal that rests on interoperability
  and conformance, with evidence from more than one consumer.
- A recent pull request
  ([#47](https://github.com/standardagents/spec/pull/47)) uses the headings
  **Problem**, **Proposed rule**, **Alternatives considered** and
  **Conformance impact**.

These drafts follow that: each opens with the problem as the specification's
own text shows it, proposes the smallest additive change, and names ACS only
as one consumer, at the end.

## After filing

Add the issue links to the table above and to the
[proposals section](../../docs/integrations/standard_agents.md#changes-proposed-to-the-standard-agent-specification)
of the integration document.
