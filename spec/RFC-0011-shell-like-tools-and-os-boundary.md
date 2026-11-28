# RFC-0011: Shell-like tools and the operating-system boundary

**Status:** Accepted
**Target:** Standard v1.2.0
**Date:** 2026-11-27
**Tracking issue:** [#178](https://github.com/synaptiai/agent-capability-standard/issues/178)

## Summary

This RFC amends Standard 1.2.0, a Candidate Standard, for tools whose
call runs a program that its arguments supply: a shell, an interpreter, a
REPL. Under
the text of §5.18.3 before this RFC, a safety layer could classify such a
call from its text and give it less than the tool's worst case, for example let a command
it reads as read-only skip the checkpoint. This RFC allows that only when the
layer's conformance statement declares an operating-system boundary for the
tool and the layer has verified, for the call, that the boundary holds in the
effective host configuration. Otherwise every call of the tool gets the
worst case. A layer that declares no boundary still conforms.

The RFC defines the boundary by four properties rather than by one
platform's settings, adds the terms *shell-like tool* and *operating-system
boundary* (§2), counts an offered shell-like tool with no boundary as
performing only its worst case (§5.18.2), says that an unverified boundary
gives the worst case rather than a refusal (§5.18.8), adds a criterion and
a member to the conformance statement (§10.4,
`tests/conformance/calls/schema/statement.schema.json`), and lists the
change in Appendix D. Decision 7 quotes the text `spec/STANDARD-v1.2.0.md`
carries. The rule binds every claim of class SL; both reference layers that
claim the class meet it.

## Motivation

§5.18.3 lets a layer read a call's arguments and return a classification
weaker than the tool's worst case. For most tools the arguments are data the
tool interprets, and a classifier can know what each value does. For a
shell-like tool the argument is a program, and a different program
interprets it: the shell, with its own version, options, configuration,
environment and the files it reads. A classifier that reads the text cannot
show that its reading matches what that program does.

Both reference layers classify shell calls from their text. The Python
adapter's Bash classifier and the plugin's pre-tool-use hook let a command whose every
program is on a read-only list run with no checkpoint and no approval, take
`git stash create` as a checkpoint, take `git stash pop` or `apply` of a
recorded commit as a rollback, and give local file changes a gated `mutate`
without `send`. Each of these rests on reading shell text as the shell reads
it.

That reading has not held:

- **Security review did not converge.** Five rounds of security review ran
  on the plugin's hooks and the Python Bash classifier. Each round confirmed
  15 to 30 new medium-severity defects, most of them in reading shell text
  the way bash reads it. Among them were commands the readers took for
  read-only that run a program or write a file: a pager whose
  preprocessor runs code, `sed`'s `e` command, `printf -v`, `pip` reading a
  configuration that names an interpreter, brace expansions bash closes at
  an unexpected `}`, a multi-byte locale in which an escaped `;` separates
  commands, git configuration and hooks that name programs. Each fix added a
  case to a list that kept growing.
- **The text depends on the shell.** Claude Code runs the agent's commands
  in the user's login shell: zsh by default on macOS, or `/bin/bash` 3.2.
  The readers model bash 5. zsh has forms that run code (glob qualifiers
  such as `*(e:...:)`, parameter flags such as `${(e)x}`) that bash does not
  have, and bash 3.2 and bash 5.3 expand some text differently. The macOS
  test runs added to CI found such differences in the hooks themselves.
- **Other agents' command filters fail the same way**: through command
  substitutions, options that run programs, and allow-listed commands with
  dangerous options.

An operating-system sandbox confines what a process can do, whatever
program it runs and however the shell reads its text. Claude Code has one
(Seatbelt on macOS, bubblewrap on Linux). A test of it on macOS with Claude
Code 2.1.332 established these facts, which the boundary's definition
follows:

- **Credentials.** A sandboxed command could read the user's GitHub token
  from the macOS keychain (through `gh auth token`, `security` and git's
  credential helper) and could read the SSH private key file. Denying the
  keychain directories and `~/.ssh` stopped both. A sandboxed command also
  inherited Claude Code's environment, a token variable included, until a
  setting removed it.
- **Escape routes.** A call that asked to run outside the sandbox ran
  outside it, with no prompt, whenever the configuration allowed unsandboxed
  commands. Commands listed as excluded ran outside it, from the project's
  settings whenever no higher scope forbade unsandboxed commands, and from
  settings given at start in every case.
- **Configuration scopes.** A settings file of higher precedence than the
  project's could turn the sandbox off, allow unsandboxed commands, or add
  excluded commands. Reading one file does not tell a layer what is in force.
- **Writes and the layer's records.** With no further rules, the sandbox
  left every one of the layer's records writable. Deny rules for the records
  stopped every route tried, about 20 in all (links, hard links, renames of
  the file and of each directory above it, appends from an interpreter), for
  sandboxed commands and for the host's file tools alike.
- **Network.** In the permission mode that allows every call, a list of
  allowed domains did not refuse an unlisted host until a separate strict
  setting was on, and the network settings had no
  effect when set in the project's settings file.
- **Code outside the sandbox.** Hooks, the layer's own decision code, and a
  plugin's tool server ran outside the sandbox: they wrote to the home
  directory and read the token that sandboxed commands could not.

So a sandbox is a boundary only with every one of these properties, checked
in the configuration actually in force for the call. A layer that has no
such boundary has no sound basis for relaxing a shell call, and gives every
call the worst case.

## Goals

- Allow a classifier to relax a call of a shell-like tool only where an
  operating-system boundary holds for that call, and require the worst case
  everywhere else.
- Define the boundary by the properties it must have, so that any platform's
  mechanism (a sandbox profile, a container, a virtual machine, a separate
  account) can meet it.
- Require the layer to verify the boundary by code in the effective
  configuration, the values the host applies from every source it reads,
  and in the call's own arguments.
- Make each layer state, for each shell-like tool, its boundary or "none",
  and the code that runs outside the boundary.
- Keep a layer without a boundary conformant.

## Non-goals

- Making a classifier's reading of shell text sound. The RFC treats every
  such reading as advisory.
- Prescribing one platform's settings. The reference layers' settings for
  Claude Code are an implementation matter.
- Testing a boundary with conformance fixtures. A fixture plays calls
  against a layer; it cannot start a process under an operating system's
  confinement.
- Classifiers of tools that are not shell-like. Their rules are unchanged.
- Confining the layer's own code or a tool server that runs outside the
  boundary. The statement names them, their calls are governed by their own
  bindings, and the boundary keeps the files they run from being written
  inside it.

## Key decisions

### 1) Shell-like tool

A **shell-like tool** is a tool whose call runs a program that the call's
arguments, or a definition or file the call names, supply in whole or in
part, whoever runs it: the host, a tool server, or a program the tool
starts. That covers a command line for a shell, a script for an
interpreter and input to a REPL. It also covers a tool that passes an
argument into a command a shell or interpreter runs (`bash -c`, `git -c`,
`find -exec`, `env`, `make`), a skill whose embedded commands take the
call's arguments, a subagent whose definition names hooks or tool servers,
a tool server's exec or eval tool, and a composite that invokes a
shell-like tool. A tool that passes its arguments as values to one fixed
program is not shell-like when no argument, and no definition or file the
call names, can make that program run other code. The term is defined in
§2.

The term follows what a call can make run, not the tool's name or who runs
the program: a reading of the arguments of each of these tools has the
same problem as a reading of shell text.

### 2) Any classification other than the worst case is a relaxation

A classification is a relaxation when it is anything other than the tool's
worst case, whatever its flags. That includes one that takes a checkpoint,
one that restores one, and one that leaves out a capability of the worst
case with the same flags (a gated `mutate` without `send`, which a
destination policy no longer refuses). Each of these rests on the same
reading of the text.

Leaving out `send` is allowed under a boundary only where every host on the
boundary's allowlist is one that every destination policy in force allows
(§4.4.2). Otherwise a call misread as local could send data from the scope
to an allowlisted host, such as a package registry, that a policy forbids.

### 3) The condition for relaxing

A layer MUST give every call of a shell-like tool the tool's worst case,
unless its conformance statement declares an operating-system boundary for
the tool and, before the call runs, the layer has verified by code
(§5.18.10), from the effective host configuration and the call's
arguments, that the boundary holds for that call. A model's judgement does
not verify a boundary.

The effective host configuration is the values the host applies to the
call: from every source it reads (such as a managed policy, the user's, the
project's, local ones, and settings, flags and environment variables given
when the host starts), merged in the host's order, each value counting only
from a source the host honours it from and as the host interprets it. The
test of Claude Code's sandbox found that the network keys had no effect
from a project's settings file and that relative filesystem entries given
at start were ignored. A layer that merged the files as written would read
a boundary the host does not apply.

The boundary is unverified for the call when:

- a source is one the layer can neither read nor supply itself, or has
  changed since the host last loaded it (a relaxed call, or the user, can
  edit a settings file the host has already read);
- the layer does not know, for the host's version and permission mode,
  which sources the host reads and which values it honours from each;
- the configuration excludes any command from the boundary, or honours an
  argument that runs a call outside it. Whether a command matches an
  exclusion depends on how the host's matcher reads the shell text (every
  command of a chain must match; a command substitution changes the
  result), which is the reading this RFC stops relying on;
- the configuration lets the host run the call without the boundary when
  its mechanism cannot start, unless the layer observes, for that call, that
  the boundary is applied. Claude Code, for example, has a setting
  (`failIfUnavailable`) that makes it refuse to run a command when its
  sandbox cannot start, and the strict settings of the sandbox test set it;
- a verification fails or cannot be completed.

An unverified boundary gives the call the worst case, which can still run
with a checkpoint and approval. It is not the failure of a check under
§5.18.8, and the call is not refused with R407. A layer that declares no
boundary, or cannot verify it for a call, gives that call the worst case
and conforms. It can take checkpoints by a route that is not a classified
shell call, such as a checkpoint tool or the host's own checkpoints
(§5.18.6). For the same reason, §5.18.2 counts an offered shell-like tool
with a classifier and no declared boundary as performing only its worst
case: it never takes the checkpoint that the host's other tools need.

### 4) The boundary, by its properties

An **operating-system boundary** holds for a call when every process that
runs the call's program, whether the call starts it or it was already
running (an interpreter, a REPL, a kernel), runs as the operating system
enforces it with the four properties of the table in §5.18.3 (quoted in
decision 7). Each property covers these routes:

- **No route outside the boundary.** The escape argument and excluded
  commands, and also a confined process that asks a process outside to act
  for it: a container daemon's socket (`docker run -v /:/host`), a
  scheduler (`at`, cron, launchd), messages to an application (Apple
  Events), a running language server or tool server. A REPL tool starts no
  process, so the boundary covers the process that is already running.
- **Writes.** Hooks, tool servers and the layer's own git commands run
  outside the boundary. A file they run or read as configuration (a host
  settings file, `.mcp.json`, a hook's script, a repository's
  `.git/config` or `.git/hooks`), written from inside, runs code outside it
  at the next hook event or the next session. The test of the sandbox found
  that the sandbox alone, with no deny rules, left every one of the layer's
  records writable.
- **Credentials.** The user's credentials, the host's own (an API key or
  login token) and the layer's secrets (an audit key, with which a command
  could forge the audit chain), neither readable nor usable through a
  service outside the boundary: the test of the sandbox read the user's
  token through `gh auth token`, `security` and git's credential helper.
- **Network.** Name lookups count as connections, since a resolver carries
  data in the names it is asked for.

The layer's own decision code (a hook, a callback) and a tool server the
host starts outside the boundary are not confined by it. The statement
names them, and the Writes property keeps every file they run or read as
configuration out of reach from inside the boundary.

Where a boundary holds, a command misread as read-only can still change
what the boundary lets it write and reach the hosts on the allowlist, but
not the layer's records, the credentials or a process outside the
boundary. A change it makes within the write scope has no checkpoint. This
RFC accepts that risk in exchange for not gating every read-only command;
§5.18.3 states it.

### 5) The conformance statement

The statement names, for each shell-like tool whose calls the layer covers,
the operating-system boundary its calls run under, or "none". For a
boundary it names the mechanism, how each property holds, how the layer
verifies it in the effective configuration and in each call, and the code
that runs outside it. The statement schema's new required member
`shell_tools` maps each tool name to `"none"` or such an object, whose
`outside` names at least the layer's own decision code; `{}` states that
the layer covers no shell-like tool. That the boundary holds is stated, not
tested by fixture (§10.4). §10.4 also gains a criterion: the layer
classifies each call as §5.18.2 and §5.18.3 state, so that the rule is part
of what a claim of class SL covers.

### 6) No new diagnostic code

The rule constrains what a layer does with a call: it either relaxes the
call or gives it the worst case, and the existing refusals (F501, F502,
F504) follow from the worst case. No validator reads a statement, so no new
code is needed.

### 7) Normative text

Each passage below is quoted word for word from `spec/STANDARD-v1.2.0.md`.

**§2**, two rows in the table of terms of tool-calling hosts, after
*Execution boundary*:

> | Term | Definition |
> |------|------------|
> | **Shell-like tool** | A tool whose call runs a program that the call's arguments, or a definition or file the call names, supply in whole or in part, whoever runs it (the host, a tool server, a program the tool starts): a command line for a shell, a script for an interpreter, input to a REPL, a skill whose embedded commands take the call's arguments, a composite that invokes a shell-like tool. A tool that passes its arguments as values to one fixed program is not shell-like when no argument, and no definition or file the call names, can make that program run other code (§5.18.3) |
> | **Operating-system boundary** | Confinement the operating system applies to every process that runs a call of a shell-like tool, with the properties §5.18.3 lists |

**§5.18.2**, the sentence after the table of offered tools and host
actions:

> An offered tool with a `classifier` counts as able to perform any
> capability, except a shell-like tool for which the layer's statement
> declares no operating-system boundary (§5.18.3), which performs only its
> worst case; and a host that takes checkpoints itself (§5.18.6) counts as
> performing `checkpoint`.

**§5.18.3**, the paragraph *Classifiers*, followed by the new paragraphs
*Shell-like tools*, and the boundary and its table:

> **Classifiers.** A layer MAY classify each call of a tool from its
> arguments (`classifier` names how), as a call whose `method` argument is
> `GET` may only read. The record's `capability`, `additional_capabilities`
> and `flags` are then the tool's worst case, which applies to any argument
> the classifier does not recognise and whenever it fails. A classification
> it returns is a capability and declared flags, subject to §5.18.1: never
> weaker than that capability's ontology flags, though it may be weaker than
> the worst case. For a shell-like tool this holds only as the next paragraph
> states.
>
> **Shell-like tools.** A call of a shell-like tool (§2) runs a program that
> its arguments, or a definition or file it names, supply, and a reading of
> that text cannot be shown to match what the shell or interpreter that runs
> it does. A layer MUST give every call of a shell-like tool the tool's
> worst case unless its conformance statement declares an operating-system
> boundary for the tool (§10.4) and, before the call runs, the layer has
> verified, by code (§5.18.10) from the effective host configuration and the
> call's arguments, that the boundary holds for that call. The effective host
> configuration is the values the host applies
> to the call, from every source it reads (such as a managed policy, the
> user's, the project's, local ones, and settings, flags and environment
> variables given when the host starts), merged in the host's order, a value
> counting only from a source the host honours it from and as the host
> interprets it (a relative path where the host ignores one counts as
> absent). The boundary is unverified for the call when:
>
> - a source is one the layer can neither read nor supply itself, or has
>   changed since the host last loaded it;
> - the layer does not know, for the host's version and permission mode,
>   which sources the host reads and which values it honours from each;
> - the configuration excludes any command from the boundary, or honours an
>   argument that runs a call outside it; a layer does not decide from a
>   call's text whether it matches an exclusion;
> - the configuration lets the host run the call without the boundary when
>   its mechanism is unavailable, unless the layer observes, for that call,
>   that the boundary is applied;
> - a verification fails or cannot be completed. This is not the failure of
>   a check under §5.18.8: the call gets the worst case, not R407.
>
> Any classification other than the worst case relaxes the call, whatever
> its flags: one that takes or restores a checkpoint, or leaves out a
> capability of the worst case, included. A layer leaves out `send` only
> where every host on the boundary's allowlist is one that every destination
> policy in force allows (§4.4.2). A layer that
> declares no boundary, or cannot verify it for a call, gives the call the
> worst case and conforms; it can take checkpoints by another route, such as
> a checkpoint tool or the host's own (§5.18.6).
>
> An **operating-system boundary** holds for a call when every process that
> runs the call's program, whether the call starts it or it was already
> running (an interpreter, a REPL, a kernel), runs, as the operating system
> enforces it, with each of these properties:
>
> | Property | What holds |
> |----------|------------|
> | No route outside the boundary | No part of the call runs outside the boundary: the call carries no argument the host honours to run it outside, the configuration excludes no command from the boundary, and no process inside the boundary can ask a process outside it to run a program or act for it (through a local socket, a loopback port, a scheduler, or messages to an application), except the boundary's own network proxy, which carries only the connections the Network property allows |
> | Writes | Writes reach only the places the statement names, and never, by any route (a symbolic or hard link, or a rename of the file or of a directory above it): the layer's own records; the layer's own code and configuration; any configuration source of the host; or any file that code outside the boundary runs or reads as configuration, such as a hook's script, a tool server's code or definition, and the configuration and hooks of a repository whose git commands run outside the boundary |
> | Credentials | Credentials are out of reach, neither readable nor usable through a service outside the boundary (an operating-system keychain, an SSH or GPG agent, a credential helper, a cloud metadata endpoint): the user's, in the files that hold them, SSH private keys and the environment variables that carry them; the host's own; and the layer's own secrets, such as an audit key |
> | Network | Connections, name lookups included, reach only hosts on an allowlist, and one to a host not on it is refused |
>
> The layer's own decision code (a hook, a callback) and a tool server the
> host starts outside the boundary are not confined by it; the statement
> names them, and no file such code runs or reads as configuration is
> writable from inside the boundary (Writes). Where a boundary holds, a call
> misread as read-only can still change what the boundary lets it write and
> reach the hosts on the allowlist, but not the layer's records, the
> credentials or a process outside the boundary; a change it makes within
> the write scope has no checkpoint.

**§5.18.8**, the start of the item *Fail closed*:

> A layer that cannot classify a call, or cannot verify an operating-system
> boundary for it, applies §5.18.2 or §5.18.3.

**§10.4**, a criterion after the first:

> - classifies each call as §5.18.2 and §5.18.3 state, giving every call of
>   a shell-like tool the tool's worst case unless it has verified, for that
>   call, an operating-system boundary its statement declares;

the statement paragraph, after the execution boundaries:

> for each shell-like tool whose calls it covers, the operating-system
> boundary its calls run under (its mechanism, how each property holds, how
> the layer verifies it in the effective configuration and in each call, and
> the code that runs outside it), or none (§5.18.3)

its last clause:

> and any check of §5.18.10, or the rule for
> shell-like tools of §5.18.3, it does not apply, which a conforming layer
> has none of.

and the sentence on what is stated rather than tested ends:

> and that an operating-system boundary it declares holds (§5.18.3).

**Appendix D** gains D.8, *Shell-like tools and the operating-system
boundary (RFC-0011)*:

> **New in 1.2.0** (binds safety layers, not workflows):
>
> - A call of a shell-like tool gets the tool's worst case unless the layer's
>   conformance statement declares an operating-system boundary for the tool
>   and the layer has verified by code, for the call, that it holds in the
>   effective host configuration; any other classification relaxes the call,
>   a checkpoint or a restore read from the command included; a verification
>   that fails gives the worst case, not R407 (§5.18.3, §5.18.8)
> - The boundary defined by four properties: no route outside the boundary,
>   writes limited and kept from the layer's records, its code and anything
>   that code outside the boundary runs, credentials (the user's, the
>   host's and the layer's) out of reach, and a network allowlist that
>   refuses other hosts (§5.18.3)
> - An offered shell-like tool with a classifier and no declared boundary
>   counts as performing only its worst case (§5.18.2)
> - The conformance statement names each shell-like tool's boundary or none,
>   and the code that runs outside it; its schema's required member
>   `shell_tools`; a class SL criterion for classifying calls (§10.4)
> - The terms shell-like tool and operating-system boundary (§2)

### 8) How a layer records a gap

The rule binds every claim of class SL. §10.4's list of what a layer does
not apply (`not_applied` in the statement schema) covers the rule for
shell-like tools as well as the checks of §5.18.10, and a layer that lists
anything there does not conform. Neither reference layer lists anything
there: the Python adapter meets the rule and the Standard Agents binding
covers no shell-like tool (below), and `spec/CONFORMANCE.md` states that
neither lists anything.

## Backward compatibility

The change constrains safety layers; no workflow, catalog, binding record,
ontology or executor changes meaning. The change amends the 1.2.0
Candidate in place; no version number changes.

It does withdraw a permission. A layer that relaxed shell calls under the
1.2.0 Candidate text without an operating-system boundary does not conform
under this text. This is acceptable because 1.2.0 is a Candidate: no
released Standard carries §5.18 or class SL, and the change narrows what a
layer may do rather than what a workflow may say. The statement schema's new
member is required, which §11.4 counts as breaking for a schema; the schema
is a conformance artifact of the same Candidate, and both reference
statements carry the member.

What each reference layer does:

- **The Python SDK adapter** offers Claude Code's Bash. `wrap_options()`
  turns on Claude Code's sandbox with the four properties in the options
  it builds, unless they carry a sandbox of their own, and adds deny rules
  for the layer's records (#184). Its classifier relaxes a Bash call (a
  read-only command, `git stash create`, a restore of a recorded
  checkpoint, a local file change) only while it has verified, in the
  options it built and in the other settings files the CLI loads, that the
  sandbox has each property, only for the CLI its Agent SDK bundles in
  a version whose settings it checks (Claude Code 2.1.321), and only in a
  permission mode it has checked (`default`, `acceptEdits`,
  `bypassPermissions`, the modes of open question 5's tests); every other
  Bash call gets the worst case. It checks the keys against the settings
  schema of 2.1.321. The sources the CLI reads and the values it honours
  from each were observed under 2.1.332 (open questions 1 and 5), and no
  run of the tests of source precedence under 2.1.321 is recorded. One run
  of the adapter's live test (the bundled CLI, default mode, no settings
  sources), reported on 2026-11-26 without the CLI's version, saw the
  sandbox refuse a host not on the allowlist. A Bash call the pre-tool-use check gave
  the worst case is the worst case when it reports back too: it takes no
  checkpoint. Its statement declares that sandbox for Bash, and `"none"`
  for Monitor, PowerShell, Skill, Agent and Task, which it gives one worst
  case whatever their arguments.
- **The Standard Agents binding** covers no shell-like tool and applies no
  classifier: a binding with a `classifier` gets its worst case. Its
  statement declares `{}`. It conforms unchanged.
- **The plugin's Claude Code hooks** do not claim class SL and have no
  statement. Their pre-tool-use hook relaxes a Bash call only under
  Claude Code's strict sandbox, which it verifies from the managed, user,
  project and local settings files (#180), and `/grounded-setup` writes
  those settings to the user's settings file (#179). The hook cannot read
  settings given when Claude Code starts, so it does not verify the
  effective configuration as §5.18.3 requires (open question 3).

A layer that adopts the rule either declares a boundary, verifies it as
decision 3 states and keeps relaxing where it holds, or gives every call of
its shell-like tools the worst case and takes checkpoints by another route.

## Conformance test updates

- `tests/conformance/calls/schema/statement.schema.json` gains the required
  member `shell_tools`: an object mapping each shell-like tool's name to
  `"none"` or a closed object with `mechanism`, `routes_outside`,
  `writes`, `credentials`, `network`, `verification` and `outside` (at
  least one entry). Its `not_applied` covers the rule for shell-like tools
  as well as the checks of §5.18.10.
- `tests/conformance/calls/statements/grounded_agency_adapter.json` declares
  Claude Code's sandbox for Bash and `"none"` for Monitor, PowerShell,
  Skill, Agent and Task;
  `tests/conformance/calls/statements/standard_agents_binding.json` declares
  `{}`. The existing tests validate every statement against the schema; a
  new test checks that the schema refuses an empty `outside`, a member it
  does not define and a statement without `shell_tools`. The adapter's test
  checks the statement against the mapper: Monitor and PowerShell get an
  unbound tool's worst case, Skill, Agent and Task one gated mapping
  whatever their arguments, and Bash is relaxed only in options the
  adapter wrapped with its sandbox. Its tests also check that a CLI that
  `cli_path` names, or a bundled CLI of a version it has not checked,
  leaves the boundary unverified, and that a `git stash create` its
  pre-tool-use check gave the worst case takes no checkpoint.
- The binding fixture `offered_classified_tool_counts` names its classified
  tool `batch` instead of `shell`: a fixture cannot say whether a tool is
  shell-like, and under §5.18.2 a shell-like tool with no boundary would not
  count as taking a checkpoint.
- No binding or call-sequence fixture is added. A fixture cannot run a
  process under operating-system confinement. §10.4 lists the boundary
  among what is stated rather than tested.
- The boundary itself is tested by the layers that declare one:
  `tests/test_sandbox_boundary.py` tries, each through several spellings,
  to write the records, read credentials, reach an unlisted host and leave
  the boundary through an escape argument or an excluded command, under
  the sandbox runtime on macOS (Seatbelt) and Linux (bubblewrap), in CI,
  with a control in which each route succeeds without the sandbox (#186).

## Alternatives considered

- **A smaller accepted shell grammar.** Accept only commands in a narrow
  grammar (no expansions, no redirections, a fixed list of programs and
  options) and give everything else the worst case. Rejected: it still reads
  text that another program interprets. The shell, its version, its
  configuration and the environment still decide what a command in the
  grammar does (a pager's preprocessor, a program's configuration file, a
  `PATH` entry), and each newly found case would again widen the list of
  exceptions.
- **No classifiers for shell-like tools.** Every call of a shell-like tool
  gets the worst case, always. Rejected as the only rule: it is sound, and it
  is what a layer without a boundary does under this RFC. But where an
  operating-system boundary holds, a command misread as read-only can reach
  only the places and hosts the boundary allows, never the layer's records,
  the credentials or a process outside it. A change it makes within the
  write scope has no checkpoint, which is the risk this RFC accepts in
  exchange: gating every `ls` behind a checkpoint and an approval leads
  people to turn the layer off.
- **Leaving §5.18.3 as it is.** Rejected: it lets a conforming layer relax
  calls on a reading that review showed it cannot make sound, and the
  release of 1.2.0 would carry that.
- **A boundary named by a platform's settings** (a list of Claude Code
  sandbox keys). Rejected: the Standard is host-neutral, setting names
  change between versions, and the same properties can be met by a
  container or a virtual machine.
- **Verifying one configuration file.** Rejected: a higher-precedence
  source can turn the sandbox off or add exclusions, and some settings take
  effect only from some sources.
- **Matching a call against the configuration's exclusions.** Relax a call
  that matches no excluded command, as the host's matcher reads it.
  Rejected: the match depends on reading the shell text (chains, command
  substitutions) the way the host does, the reading this RFC stops relying
  on. Any exclusion leaves the boundary unverified for every call.
- **Refusing a call whose boundary cannot be verified (R407).** Rejected: a
  layer with no boundary conforms by giving the worst case, and a layer
  that cannot verify one is in the same position. The worst case still
  runs only with a checkpoint and approval.
- **Naming an unreadable configuration source as a host gap.** Rejected: a
  host gap is a case where a call runs without the layer's decision; here
  the layer decides, and an unverified boundary would let it relax on a
  guess.

## Open questions

1. **User scope.** Do sandbox settings in a user's own settings file take
   effect, the network settings in particular, and can a project's settings
   file override them? **Answered** by a test with Claude Code 2.1.332 on
   macOS on 2026-11-25, with a second, isolated login whose own
   `settings.json` held the strict sandbox (reported on #141). Every
   sandbox key took effect from the user's file, the network allowlist
   included. From the project's settings file (`settings.json` in its `.claude`
   directory), `enabled: false`,
   `excludedCommands` (even under the user's `allowUnsandboxedCommands:
   false`) and `filesystem.allowWrite` each took effect over the user's
   strict sandbox; `allowUnsandboxedCommands: true`, `strictAllowlist:
   false`, an `allowedDomains` entry and an `Edit` allow rule over a deny
   rule had no effect. Only managed settings can stop the three overrides.
   So a layer's setup writes the settings to the user's file
   (`/grounded-setup`, #179), and a layer reads the project's and the local
   files as well, to detect the three overrides (#180, and the adapter's
   check of the files its options load).
2. **Platforms without a sandbox.** On a host with no operating-system
   sandbox (native Windows, a host that cannot start one), every shell call
   gets the worst case. Should the Standard name containers or virtual
   machines as the expected boundary there, or leave the mechanism to the
   statement? Open: #216.
3. **Configuration a layer cannot see.** The plugin's hooks cannot read
   settings given when Claude Code starts, and hooks get no environment
   variable that says the sandbox is on. Under decision 3 the hooks then
   never verify the boundary. The boundary tests confirmed the gap: a
   command-line `--settings` file's `excludedCommands` let a command run
   outside the sandbox under the setup's user settings. Is a host mechanism
   that reports the effective sandbox to the layer needed, or should such a
   source be ruled out by the layer's setup? Open: #217. The Python adapter
   does not have this gap: it supplies the `--settings` value itself and
   reads the other sources the CLI loads.
4. **The plugin's checkpoint route.** The plugin takes checkpoints only
   through Bash's `git stash create`, which is a classified shell call. It
   relaxes that call only under the strict sandbox it verifies (#180);
   without it, no checkpoint can be taken and every gated call is refused
   with F501. Should the plugin serve a checkpoint tool, or count the host's
   own checkpoints, so that a session without the sandbox can still take
   one? Open: #218.
5. **Linux and other permission modes.** **Partly answered.** The sandbox
   runtime that Claude Code uses on Linux (srt 0.0.82, bubblewrap) refused
   every write, credential and network route of the boundary tests, in
   containers and in CI on `ubuntu-latest` on 2026-11-27 (601 passed, 2
   expected failures), except a hard link made before a command starts,
   which both Seatbelt and bubblewrap let through and the layers refuse
   instead. Under Claude Code 2.1.332 on macOS, the routes Claude Code
   decides itself were tested with the setup's settings given at start in
   the default, `acceptEdits` and `bypassPermissions` modes (the escape
   argument, excluded commands, the network allowlist), and with them in
   the user's settings in `bypassPermissions` mode only (the precedence of
   settings files). Claude Code itself has not been run on Linux, and
   `plan` mode has not been tested. The Python adapter relaxes Bash only in
   the three tested modes. Open: #186.
