# About this site

This site is the documentation of the Agent Capability Standard: an open
specification of the capabilities an AI agent uses, the typed contracts
between them, a workflow language that composes them into steps, and the
rules a validator checks before a workflow runs. The philosophy behind it is
called Grounded Agency: every claim an agent makes is backed by evidence,
every action leaves an audit trail, and every change to the world can be
undone from a checkpoint.

## Who publishes it

The standard and this site are published by [Synapti](https://synapti.ai)
and developed in the open in the
[agent-capability-standard repository](https://github.com/synaptiai/agent-capability-standard)
on GitHub. Anyone can propose a change: the [contributing guide](../../CONTRIBUTING.md)
explains how, and [governance](../../spec/GOVERNANCE.md) explains how
proposals become part of the standard through the RFC process.

## License

The specification, the schemas, the skills and the tools are released under
the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0). Using
the standard, this site, its data API and its MCP server costs nothing and
needs no account or key.

## How the site is built

Every page is built from the files in the repository: the Markdown documents,
the capability ontology, the workflow catalogs and the domain profiles. The
footer of each page names the commit it was built from, and a page built from
one Markdown file links that file. Each page also has a Markdown copy for
agents, listed in [llms.txt](https://acs.synapti.ai/llms.txt).

To ask a question or report a mistake, see [Contact](CONTACT.md). What the
site does with your visit is described under [Privacy](PRIVACY.md).
