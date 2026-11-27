# Proposals for the Standard Agent Specification

Issue texts for [`standardagents/spec`](https://github.com/standardagents/spec),
ready to file. Each file is one issue: the first line is the title, the rest
is the body. They come out of the mapping in
[Standard Agents interoperability](../../docs/integrations/standard_agents.md).

**Status: not filed.** They are written against 0.2.0 at commit `faccc8b`
(12 November 2026). On 27 November 2026 they were checked against
[`f462a67`](https://github.com/standardagents/spec/commit/f462a673297faed1f849ef1741ddda1e06b6c817),
the head of `main` that day:

- No file under `content/` changed between `faccc8b` and `f462a67`; the
  commits between them change the site, the model recommendations and
  `AGENTS.md`.
- Every passage the texts quote from `content/0.2.0` is found there, and
  every `standardagentspec.org/0.2.0` link names a page and a heading that
  exist.
- The passages quoted from the published types are unchanged in
  `@standardagents/spec` 0.45.13, the current release; the texts cite them as
  0.45.10, the version the mapping was made against.
- The open upstream proposals were read against the texts. None asks for a
  change these texts ask for. Pull request
  [#53](https://github.com/standardagents/spec/pull/53) (cancellation of
  queued messages, head `33f5262`) edits Client API §12 and §13 and Messages
  §6, pages text 02 cites; it changes no passage text 02 quotes.

The specification's maintainers edit 0.2.0 in place, so check again on the
day of filing: compare `content/` between `f462a67` and the head of `main`,
and read any proposal opened since. Their community page says accepted
changes are published "in a new version of the specification", so each
addition proposed here would apply from that version.

## Filing

Texts 01, 07, 08 and 09 link the reference binding and the integration
document at one commit of this repository, so that each issue keeps showing
what its text describes. They are pinned to `8ec818c`, the head of `main` on
27 November 2026. On the day of filing, set them to the head of `main`
first:

```bash
git fetch origin main
sha=$(git rev-parse origin/main)
sed -i.bak -E "s#(synaptiai/agent-capability-standard/(tree|blob))/[0-9a-f]{40}/#\1/$sha/#g" \
  tasks/standard-agents-upstream/[0-9][0-9]-*.md && rm tasks/standard-agents-upstream/*.bak
```

The links then show the binding and the integration document as they stand
at that commit. Commit the changed texts with the filing results.

```bash
tasks/standard-agents-upstream/file-issues.sh          # lists what would be filed
tasks/standard-agents-upstream/file-issues.sh --file   # creates the nine issues
```

The script needs the GitHub CLI, signed in as the account the issues should
come from. It files in the order under [Order](#order), skips a title that
already exists, and prints each new issue's address.

| # | Title | Why it matters for a grounded agent | Size |
|---|-------|-------------------------------------|------|
| [01](01-before-tool-call-hook.md) | Define a hook that runs before a tool executes and can decline the call | Lets a safety rule be imposed on tools one did not write. Today a rule holds only inside tools written with the binding | One new hook |
| [02](02-message-sender.md) | Record the authenticated caller on a message sent through the Thread Client API | Lets code tell a client's answer from a message a model or a parent queued. An approval gate built on messages cannot be trusted without it | One read-only field |
| [03](03-tool-call-identity.md) | Let a tool know which call it is serving | Lets a tool's own records (evidence, audit, idempotency keys) be tied to the stored tool result | One optional property |
| [04](04-tool-result-contract.md) | Specify what a tool's `execute` returns, and give results a field for metadata | Gives refusal codes and evidence a defined place that is not model-facing text | Text, plus one optional field |
| [05](05-annotations.md) | Annotations: allow them on agents and prompts, pass a tool's to its hooks, and say whom the rule binds | Lets a composed agent carry a classification, and lets a hook read a tool's | Three optional fields, one reworded sentence |
| [06](06-editorial-inconsistencies.md) | Eleven inconsistencies in the 0.2.0 text | None directly; found while checking references | Editorial |
| [07](07-unoffered-tool-call.md) | State what a runtime does with a tool call the request did not offer | Decides whether a prompt's tool list, `toolChoice: 'none'` and `hidden` are boundaries a runtime enforces. A read-only prompt, a guard tool and a gated delegation all rest on it | Two sentences, no API change |
| [08](08-child-creation-from-code.md) | Specify the lifecycle operations code calls to create and message a child | The injected `subagent_create` has no `execute` to wrap, so a delegation that must be checked first has to be created from code, and the text does not give the call | One subsection, two sentences |
| [09](09-execution-concurrency-and-flow-id.md) | Say what may run alongside an execution of a thread, and when `flowId` changes | The binding's records are read and rewritten in a store with no conditional write, and its checkpoint rule is keyed on `flowId` | Text only |

## Order

File 06 first: it is small, checkable and asks for nothing. Then 01, which
the others do not depend on but which matters most. 02 to 05 and 07 to 09 are
independent of one another. 07 and 09 ask only for sentences that settle what
the text leaves open, with no API change, so they are the easiest of the rest
to accept and the script files them next.

The proposals come out of 83 findings about the specification, listed with
their evidence in
[`findings_standard_agents.yaml`](../../docs/research/analysis/standard_agents_mapping/findings_standard_agents.yaml).
Each finding says which issue covers it, or why none does. Eleven are marked
`candidate`: they would stand as issues of their own and are not drafted. The
file also lists 30 questions the text leaves open.

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
