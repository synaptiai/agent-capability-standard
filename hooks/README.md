# Safety Hooks

This directory contains hooks that implement the VERIFY layer capabilities from the Agent Capability Standard.

## Spec-Aligned Hooks

These hooks directly implement capabilities defined in the standard's VERIFY layer:

| Hook | Event | Purpose |
|------|-------|---------|
| `pretooluse_require_checkpoint.sh` | PreToolUse (every tool), PreSkillShellCommand (`Bash`, `PowerShell`); both `onFailure: "block"` | Classify the call; one checkpoint marker per gated call; ask for approval; let a restore of a recorded checkpoint run as a rollback; refuse a gated command that a skill injects as it loads |
| `posttooluse_take_checkpoint.sh` | PostToolUse (`Bash`) | Write the checkpoint marker after a successful `git stash create`, with its commit entered in the git directory (`<git dir>/acs/checkpoints/commits/`), filing a marker it replaces under `.claude/checkpoints/ended/` |
| `stop_end_checkpoints.sh` | Stop, StopFailure, UserPromptSubmit, SessionStart, SessionEnd | End the marker's validity, filing it under `.claude/checkpoints/ended/`: the end and the start of a turn or a session are execution boundaries |
| `posttooluse_log_tool.sh` | PostToolUse, PostToolUseFailure (every tool) | Log every tool call as an action record (§6.4), with the configuration that decided it, for the audit trail and provenance; it is not an `audit` step |

The hooks apply the rules of
[STANDARD 1.2.0 §5.18](../spec/STANDARD-v1.2.0.md#518-tool-calling-hosts)
where Claude Code lets them, and do not claim the safety-layer class SL
([SECURITY.md §5.5](../spec/SECURITY.md#55-hooks-and-the-safety-layer-class)
says why). The Python SDK adapter and the Standard Agents binding claim it
(their conformance statements are in `tests/conformance/calls/statements/`).

## Platforms

The hooks need `bash`, `jq` and `openssl`, and perl or `find`, `awk` and a
GNU or BSD `stat` (the pre-tool-use hook counts the links of the layer's
records with them; without them every call is blocked with `R407` while
the git directory's `acs/` exists, and every call the hook gates
otherwise). CI runs them, and every test, on Linux (GNU tools,
bash 5) and on macOS. On macOS:

- **Bash.** The hooks start under `/bin/sh` and run the first `bash` on
  `PATH`: the `/bin/bash` 3.2 that macOS ships, or a newer one such as
  Homebrew's. Both work.
- **BSD tools.** `grep` and `sed` read the same patterns as on Linux, but
  about ten times more slowly. A Write of about 3.5 MB, or a command of a
  few hundred kilobytes of line breaks, runs past the hooks' 30-second
  limit there, and the call is blocked.
- **The agent's shell.** Claude Code runs the agent's commands in your login
  shell, zsh by default on macOS. The hooks read a command as bash 5 reads
  it. A form zsh reads differently, and that the hooks cannot read, is gated
  like any other command they cannot read (SECURITY.md §5.5).

## How Hooks Work

```mermaid
---
title: One tool call through the two hooks
---
flowchart TB
  accDescr: Claude Code passes each tool call as JSON on stdin to the pre-tool-use hook; exit 0 lets the tool run, exit 2 blocks it with the reason shown to Claude, and any other non-zero exit, or no verdict in time, is a failure, which blocks the call because hooks.json sets onFailure to block (a Claude Code without that setting runs the tool); after the tool runs, whether it succeeded or failed, the post-tool-use hook logs it.
  call[Tool call from Claude Code] -->|JSON on stdin| pre[Pre-tool-use hook]
  pre -->|exit 0| run[The tool runs]
  pre -->|exit 2| block["Blocked: the reason on stderr is shown to Claude"]
  pre -->|"other exit, or no verdict in time: onFailure block"| block
  run -->|JSON on stdin| post["Post-tool-use hook: logging and audit"]
```


### Pre-Tool-Use Hooks

Run **before** a tool executes and can block operations. Claude Code passes
the tool call as a JSON object on stdin; exit 0 allows the call (with an
`ask` decision on stdout for a call that needs approval), and exit 2 blocks
it, with the reason on stderr shown to Claude. Any other non-zero exit, a
run that cannot start and one that gives no verdict within the hook's
`timeout` (30 seconds) are failures: `hooks.json` sets `onFailure: "block"`
on this hook, so Claude Code blocks the call. Claude Code honours
`onFailure` from version 2.1.295; an earlier version treats a failure as a
non-blocking error and runs the tool, so the plugin needs 2.1.295 or later.
Every tool call is routed here (matcher `*`). The reason opens with the
Standard's code and name for the refusal, such as `F501
CHECKPOINT_REQUIRED:`. Only Claude Code's JSON object is read: a payload that
is not one, or a system without `jq`, is blocked with `R407
SAFETY_CHECK_FAILED:`.

The same hook runs on `PreSkillShellCommand` (matcher `Bash|PowerShell`,
`onFailure: "block"`, 30 seconds): before each shell command that a skill,
or a command such as `/security-review`, injects as it loads
(``!`cmd` `` and ```` ```! ```` blocks), which no PreToolUse hook sees.
Claude Code runs such a command through the Bash or PowerShell tool, and
the hook classifies it as it classifies that tool's call. On this event a
hook can block a command but cannot ask a person (Claude Code treats `ask`
as a block), so a command that needs nothing (an `observe` read, or
`git stash create`, under the strict sandbox) runs, and every other one,
a restore included, is refused with `F502 APPROVAL_REQUIRED:`, whatever
`ACS_HOOK_APPROVAL` and the permission mode say. The refusal is decided
before the checkpoint marker is read, so it uses no marker. The skill still
loads, with `[not run: blocked by hook: <reason>]` in place of the
command's output; Claude can run the command afterwards as a tool call,
which can be approved. Without the strict sandbox every Bash command is
gated, so every injected command is refused. The event needs Claude Code
2.1.332 or later: an earlier version runs injected commands without calling
it, and shows `Unknown hook event "PreSkillShellCommand" was ignored` when a
session starts. There, `disableSkillShellExecution` in the user or managed
settings keeps skills from running injected commands at all.

The hooks' settings (`ACS_HOOK_APPROVAL`, `ACS_CHECKPOINT_MAX_AGE`,
`AUDIT_HMAC_KEY`, `AUDIT_LOCK_WAIT`), and any variable that is not one of
Claude Code's own settings, belong in `~/.claude/settings.json` (`env`),
managed settings or the environment Claude Code starts in, never in the
project's `.claude/settings.json` or `.claude/settings.local.json`. Claude
Code applies a project's `env`, which is repository content, to every hook
and every command it runs, over the user's settings: a hook cannot tell the
person's value of a setting from the repository's (a cloned repository could
set `ACS_HOOK_APPROVAL=off`), and any other variable can change what a hook
or a command it lets pass runs (`BASH_ENV` runs a repository script first,
`SHELLOPTS=noexec` runs nothing, `PATH` or `HOME` a repository's `jq`, `git`
or `openssl` or a `jq` library, `LD_PRELOAD` a library, `GIT_CONFIG_*` a
program `git status` runs). While either project file sets in `env` a name
other than Claude Code's own (`ANTHROPIC_*`, `OTEL_*`,
`CLAUDE_CODE_ENABLE_TELEMETRY`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS`,
`CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`,
`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `DISABLE_TELEMETRY`,
`DISABLE_ERROR_REPORTING`, `DISABLE_AUTOUPDATER`, `MAX_THINKING_TOKENS`,
`MAX_MCP_OUTPUT_TOKENS`, `MCP_TIMEOUT`, `MCP_TOOL_TIMEOUT`,
`BASH_DEFAULT_TIMEOUT_MS`, `BASH_MAX_TIMEOUT_MS`, `BASH_MAX_OUTPUT_LENGTH`,
as written), or cannot be read, the pre-tool-use hook blocks every call with
`R407 SAFETY_CHECK_FAILED:`, the log hook writes no line and the checkpoint
hook writes no marker and runs no git command. Claude Code started in the
home directory reads `~/.claude/settings.json` as the project's too: there,
set them in the environment instead.

Each hook starts under `bash -p`, which reads no `BASH_ENV` or `ENV` file,
imports no shell function and ignores `SHELLOPTS`, `BASHOPTS`, `CDPATH` and
`GLOBIGNORE` (the scripts open with `#!/bin/sh` and start themselves so,
whoever starts them); the three that read a setting keep on `PATH` only the
absolute directories outside the project directory (all of them where the
project is the user's home directory, as the password database gives it,
or holds it), run `jq` with no `HOME`
(jq loads `$HOME/.jq` as a library), and read the settings files before
they run any other program. Each git command they run, and each read of a
settings file, is stopped after 5 seconds: git reads the files a
repository's configuration includes, and a FIFO or a terminal there
(`include.path = /dev/ptmx`) holds the read until someone writes, past the
30-second limit after which a Claude Code without `onFailure` runs the
call. A git that did not answer counts as one that cannot say: the
pre-tool-use hook blocks the call (`R407`, or `F501` for the marker's git
directory) or gates it (a git read, `git stash create` or a restore is
`mutate`), the checkpoint hook writes no marker, and the log hook writes
its line without the anchor and says why; a settings file that is not a
regular file is unreadable (`R407`). What they cannot reach: Claude Code starts each
hook through `/bin/sh -c` with that env applied, so where `/bin/sh` is bash
(macOS, Fedora, Arch, Git Bash) `SHELLOPTS=noexec` or an exported function
stops that shell first, and anywhere a `PATH` naming a repository directory
ahead of bash's, or `LD_PRELOAD`, runs the repository's code in the hook's
place: repository settings the person accepts reach as far as project hooks,
which run the repository's code. Review them before accepting them.

```bash
echo '{"tool_name": "Write", "tool_input": {"file_path": "a.py"}}' \
  | ./pretooluse_require_checkpoint.sh   # exit 2 without a valid marker
./pretooluse_require_checkpoint.sh '{"tool_name": "Bash", "tool_input": {"command": "ls"}}'   # $1 also works
```

### Post-Tool-Use Hooks

Run **after** a tool executes for logging and audit. Claude Code fires
`PostToolUse` after a call that succeeded and `PostToolUseFailure` after one
that failed; the audit hook is registered for both, for every tool. The tool
call arrives as JSON on stdin.

```bash
echo '{"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}}' \
  | ./posttooluse_log_tool.sh
```

## Configuration

Hooks are configured in `hooks.json` (loaded automatically by the Claude Code plugin):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/pretooluse_require_checkpoint.sh",
            "timeout": 30,
            "onFailure": "block"
          }
        ]
      }
    ],
    "PreSkillShellCommand": [
      {
        "matcher": "Bash|PowerShell",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/pretooluse_require_checkpoint.sh",
            "timeout": 30,
            "onFailure": "block"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/posttooluse_log_tool.sh",
            "timeout": 90
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/posttooluse_take_checkpoint.sh",
            "timeout": 90
          }
        ]
      }
    ],
    "PostToolUseFailure": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/posttooluse_log_tool.sh",
            "timeout": 90
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/stop_end_checkpoints.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/stop_end_checkpoints.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "StopFailure": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/stop_end_checkpoints.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/stop_end_checkpoints.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/stop_end_checkpoints.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

Each hook entry specifies:
- **matcher**: Regex pattern matching tool names that trigger the hook (`*` matches every tool; an event with no tool, such as Stop, has none)
- **hooks**: Array of hook commands to execute
- **type**: Hook type (`command` for shell scripts)
- **command**: Path to the hook script (`${CLAUDE_PLUGIN_ROOT}` resolves to the plugin directory)
- **timeout**: Seconds the hook may run. Every entry sets one: 30 for the pre-tool-use hook; 90 for the log and checkpoint hooks, above the longest their bounded reads and the log's lock wait (`AUDIT_LOCK_WAIT`, at most 55) can take together; 10 for the boundary hook, which on SessionEnd also raises Claude Code's 1.5-second budget for that event
- **onFailure**: `block` makes a run that fails, cannot start or times out block the call

## Checkpoint System

`pretooluse_require_checkpoint.sh` classifies every tool call by its
effect (STANDARD 1.2.0 §5.18.3), with lists derived from the SDK mapper's
(`grounded_agency/capabilities/mapper.py`; `tests/test_hook_lists_match_mapper.py`
keeps the hook's tool list and read-only list subsets of the mapper's and its
`git stash` table equal to it):

- A tool the mapper maps to a capability that needs neither a checkpoint nor
  approval (`Read`, `Glob`, `Grep`, `LS`, `WebFetch`, `WebSearch`,
  `AskUserQuestion`, `TodoWrite`, `TaskList`, `TaskGet`, `TaskCreate`,
  `TaskUpdate`, `ToolSearch`, `BashOutput`, `TaskOutput`,
  `ListMcpResourcesTool`, `ReadMcpResourceTool`, `ExitPlanMode`, and the
  older names `AskUser` and `TodoRead`): needs neither. Those of them the
  mapper maps to `persist` (`TodoWrite`, `TaskCreate`, `TaskUpdate`) store
  what they are given, so a call whose input holds a secret the layer
  recognises is refused with `F504 CONSTRAINT_VIOLATED:` in every
  permission mode (STANDARD 1.2.0 §5.18.10, §6.7), as the SDK adapter
  refuses it: the shared scan (`secret_scan.sh`, copied into the hook) over
  every string of the input and its JSON text, and the SDK redactor's rule
  for data (`secret_member.jq`, copied too), a value of 4 or more
  characters (or a number) that is not a placeholder under a member named
  for a credential, the value of a `{"name": "Authorization", "value": ...}`
  pair, or the second of a `["Cookie", ...]` tuple. A test keeps the
  hook's verdict the adapter's on the credential vectors and on data forms.
  The credentials the plugin holds itself are refused too: `AUDIT_HMAC_KEY`'s
  value, and the project's checkpoint key, read from
  `<git dir>/acs/checkpoints/key` where git names the project's git
  directory (a git that cannot say reads none). The audit key file
  (`~/.config/acs/audit.key`, below) is not read for this: it is kept out of
  the agent's reach instead. The log hook, which reads that file to sign,
  does count the key it read as a credential it holds: a tool name or skill
  name that holds it is logged as `[REDACTED]`.
- `Write`, `Edit`, `MultiEdit`, `NotebookEdit`: `mutate`.
- `Skill`, `Agent`, `Task`: `mutate`. Claude Code runs the shell commands a
  skill's file embeds (``!`cmd` `` and ```` ```! ```` blocks, the call's
  arguments substituted into them) as the skill loads, under its
  `allowed-tools`, and the hooks and MCP servers a subagent's definition
  names as the subagent runs; before Claude Code 2.1.332 none of them
  reaches a hook, and from 2.1.332 the embedded commands reach this hook
  on `PreSkillShellCommand` (above) but the subagent's hooks and MCP
  servers still do not. A project's
  skill or agent can take any name (a project's agent replaces a built-in
  one of the same name). The call is asked for approval with the reason
  `<tool> (capability 'mutate': the shell commands a skill's file embeds,
  and the hooks and MCP servers a subagent's definition names, run with no
  hook seeing them)`. Loading the checkpoint skill takes no checkpoint: run
  `git stash create` first.
- `Bash`: every call is `mutate` unless the hook verifies Claude Code's
  strict sandbox for it ([The strict sandbox](#the-strict-sandbox), below);
  without it, `git stash create` and a restore are `mutate` too, so no
  checkpoint can be taken through Bash. Under it, the classes below apply.
  A command over 4096 bytes is `mutate`, decided before anything
  else is done with it, so no reading runs into the hook's time limit (a
  command padded with 50,000 blanks once took 44 seconds to trim). A command
  with any of `` ; & | < > $ ` ( ) { } \ `` or a line
  break may be more than one command or expand something, so it is `mutate`.
  Otherwise it is read as one simple command, its words split and dequoted
  as bash does (`"--output=x"` is `--output=x`; an unbalanced quote is
  `mutate`): an option that writes is `mutate` (for `git`, `--output` or an
  abbreviation of it such as `--outp`; for `file`, `-C` or `-p` in any short
  option, or `--compile` or `--preserve-date` or an abbreviation such as
  `--compi`; for `printf`, any option: `printf -v NAME` sets a shell
  variable), and so is a `git`, `file` or `printf` command with a word
  holding an unquoted `*`, `?` or `[`, which bash replaces with file names,
  options included; `git stash create` takes a
  checkpoint; `git stash list` and `git stash show` only read; `git stash pop
  <commit>` and `git stash apply <commit>` restore one (`rollback`) when
  `<commit>` is the full id of a commit a checkpoint recorded, the call
  runs in the project's repository and no smudge filter is configured
  (below); any
  other `pop` or `apply`, a bare one included, is `mutate`, since git applies
  any merge commit as if it were a stash; any other `git stash` form
  is `mutate`; a command on the read-only list (`ls`, `cat`, `head`, `tail`,
  `wc`, `pwd`, `grep`, `stat`, `file`, `du`, `df`, `which`, `whoami`,
  `uname`, `echo`, `printf`, `git status`, `git log`, `git diff`, `git show`,
  `git rev-parse`, `git ls-files`) only reads and needs nothing; anything else
  is `mutate`. The first word must be the listed program exactly, and a
  two-word entry's subcommand the second word: bash runs a first word that
  holds a blank (a quoted `"git status"`) or a slash as the program of that
  name, which is `mutate`. Each of these commands (the read-only list, `git
  stash create`, a restore) is `mutate` where the program bash finds for its
  first word, on the `PATH` Claude Code gives the hook and the agent's
  commands, may be the repository's own: the name is found under an empty
  or relative entry (bash reads it from the working directory:
  `PATH=node_modules/.bin:$PATH`, a leading colon), or in a file that lies,
  links followed, in the project (an entry in it: an activated virtual
  environment, direnv's `PATH_add`; not where the project is the home
  directory, or holds it), or nowhere. The entries the Bash tool adds from
  the user's shell startup files (its shell snapshot) reach no hook and are
  not seen, nor are the aliases, functions and shell options those files
  set (with zsh's `EXTENDED_GLOB`, `^`, `#` and `~` are pattern characters
  too, read here as text); the SDK mapper reads the CLI's `PATH` the same way. A git command that would only read (`git stash list` and
  `git stash show` included) is `mutate` where the call's directory (the
  payload's `cwd`, else the project directory) is in a partial clone (a
  promisor remote, or `extensions.partialClone`), in a repository with
  submodules (`modules/` in its common git directory, or a gitlink in its
  index), or where git cannot say: there git fetches each object it lacks
  from the promisor remote, its own or a submodule's (`--submodule=diff`,
  `diff.submodule`, `git status`), so `git show <id>` sends the id to that
  host. `git stash create` still takes a checkpoint there (it reads only
  what the local state holds). Every `git` command the hook would let pass
  (a read, `git stash create`, a restore) is `mutate` where the git
  directory git finds is not one git made for a work tree (a `.git`
  directory, or a linked worktree's or a submodule's under one): a
  repository can ship a directory holding `HEAD`, `objects/` and `refs/`
  (an embedded bare repository), and git run there reads its `config` and
  runs what it names (`core.fsmonitor` for `git status`, a textconv driver
  for `git log -p`). The same holds where the repository's own
  configuration (the local and worktree scopes, with the files they
  include) names a program git runs (a `core.fsmonitor` other than `true`
  or `false`, a diff driver's `textconv` or `command`, `diff.external`, a
  filter's `clean`, `smudge` or `process`, a merge driver, a signature
  program, a pager) or its hooks directory holds `post-index-change` (which
  `git status` runs when it writes the index): a project delivered with its
  `.git`, or one approved `git config core.fsmonitor ./x`, brings them. There
  a read and a restore are `mutate`, and `git stash create` is put to a
  person with no marker asked for (only it makes one; `F502` in a mode that
  asks no one). The user's own configuration (global, system) gates no
  read and no `git stash create`, but a restore is `mutate` wherever any
  scope, the user's included, configures a filter's `smudge` or `process`
  command (security round 5): git runs it when it writes the tree, and
  git-lfs's, which `git lfs install` writes to the user's configuration,
  asks the LFS server the repository's `.lfsconfig` or remote names for each
  object its store lacks, sending the object's id. The two commands `git
  lfs install --skip-smudge` writes (`git-lfs smudge --skip -- %f`,
  `git-lfs filter-process --skip`), which ask no server, count as none.
  The hooks' own git commands run with `core.fsmonitor` and hooks
  turned off and no object fetched (`hgit`), and the take hook's clean-tree
  check with the repository's filters turned off.
- Any other tool (`Monitor` and `PowerShell`, which run commands,
  `EnterWorktree`, `ExitWorktree`, every MCP tool, a tool the hook does not
  know) is unbound: `mutate`, since a layer cannot know that an unknown tool
  only reads (§5.18.2). Its approval request says
  `<tool> (unbound: treated as a mutation, STANDARD 1.2.0 §5.18.2)`.

Then:

- **Rollback** (`git stash pop|apply <commit>`): allowed when a checkpoint
  of the project recorded `<commit>`, an entry
  `<git dir>/acs/checkpoints/commits/<commit>` that
  `posttooluse_take_checkpoint.sh` writes for each checkpoint it takes, and
  the call runs in the project's repository (its `cwd`; a restore into
  another repository or worktree restores other state). The entries are in
  the project's git directory, outside the work tree: a clone, a checkout
  or an applied stash can put files in the work tree, `.claude/` included,
  but none there. Each holds the HMAC-SHA-256 of
  `acs-checkpoint-commit:<commit>` under the project's checkpoint key
  (`<git dir>/acs/checkpoints/key`, 64 hex digits the take hook draws from
  `/dev/urandom` the first time, mode 600), so a file a command creates
  there, through a link the repository ships for instance, is no entry; and
  the git directory must be one git made for a work tree (a shipped one
  could hold a key and entries of its own). The check is one lookup,
  however many checkpoints were taken. It uses no checkpoint: one that was used, expired, ended with its
  turn or was replaced can still be restored. Restoring anything else is a
  `mutate`.
- **The layer's records**: a `mutate` call that names them is blocked
  with `F504 CONSTRAINT_VIOLATED:`: only the hooks write them. The texts
  read are a `Write`, `Edit`, `MultiEdit` or `NotebookEdit` call's path, a
  `Bash` command, a `Skill` call's arguments, and every string and member
  name of any other tool's input but `Agent`'s and `Task`'s (`Monitor` and
  `PowerShell` commands, an MCP filesystem server's path, an MCP shell
  server's command; a subagent's own calls come here). A text that holds
  `checkpoint.ok`, `.claude/checkpoints`, `acs/checkpoints` or `audit.head`
  (the audit log's head, below) is blocked, read as a path is: in any
  letter case, with a run of slashes and `./` segments as one slash, and,
  in a text of at most 4096 bytes, each `x/../` resolved. In a text of at
  most 4096 bytes each path it names (a file tool's path whole, a
  command's words as the shell passes them; for other tools both, each
  string whole and as words) is then followed, from the call's directory,
  through the symbolic links on it, so `touch notes/todo.md`, where the
  repository ships `notes/todo.md` as a link to
  `.git/acs/checkpoints/key`, is blocked too. Each link target, the call's
  directory and git's answers are read exactly, line breaks that end a
  name included (a link to `evil<newline>` leads there, not to `evil`). So are the paths the shell
  reads differently from their text: a `~` it expands (`~`, `~+`, `~user`;
  `~-` and `~N`, which name a directory the hook cannot know, are blocked
  outright), a brace group it expands, found as bash finds it (the first
  `{` a `}` closes, at the first `}` after a comma at its own level, so
  `{a},.claude/check}point.ok` names the marker:
  `{fixtures/,.git/acs/check}points`, `audit.he{ad,x}`, `.claud{e..e}`,
  `.cl{a..a..+1}ude`) and expanded as bash 5.2 and bash 5.3 expand it.
  They differ on a group with no comma at its own level that is no
  sequence: `{a..b{c,d}}` is `a..bc a..bd` to 5.2 and `{a..bc} {a..bd}`
  to 5.3, the one word of 5.3's seen (on a runner, without its source),
  which two readings give; the hook reads both (`tests/brace_readings.py`
  holds words that tell them apart, which a runner with bash 5.3 checks).
  A sequence with a number of more than 9 digits (an increment of more
  than 18), leading zeros aside, is not read: bash 5.2 prints a padded one
  as a 32-bit number, and the call is blocked. So are a
  `$'...'` it decodes
  (`$'.git/acs/check\x70oints'`, and octal, `\u`, `\U` and `\c`
  escapes; `$"..."` as `"..."`), a path attached to a short option
  (`-tnotes/k`, `-onotes/todo.md`; of a long cluster only the texts whose
  first component exists in the call's directory, or that are absolute),
  and the command a quoted word holds for a shell that reads it again (`sh
  -c 'cp x notes/k/'`). A path that leads to the directory holding the
  records (the project's `.claude`, its git directory's `acs/`) is blocked
  too: `rm -rf .claude` removes the marker, and the audit log with its
  head. So is a link that cannot be followed (a loop, more than 40 links),
  and, rather than hold the hook past its time limit, a call with more than
  4096 strings and member names or more than 65536 bytes of strings of at
  most 4096 bytes, brace expansions that make more than 8192 words or read
  more than 65536 braces, commas and characters, or more than 262144 bytes
  of paths to resolve (the slowest reading found within
  these bounds takes about 4 seconds). Reading the records is not refused; a path a command builds when
  it runs, a pattern the shell expands and a link a command reaches without
  naming it (copying a directory that holds one) are not seen, nor is a
  text over 4096 bytes read for paths. This reading is an advisory early
  refusal, not the boundary: the deny rules below are.
- **A record with another name**: a regular file under the records with
  more links than names among them has a hard link elsewhere, through which
  a command or a file tool can read or write it past the deny rules (the
  Linux sandbox runtime denies a path, not a file). While a file under `acs/`
  in the git directory git names for the project (the checkpoint key, the
  entered commits, the head's anchor) has one, every call of any tool is
  blocked with `F504 CONSTRAINT_VIOLATED:`, reads included (`Read`, `Grep`,
  `cat`): the key could be read through the link. While a file of the
  project's records (`.claude/checkpoint.ok`, `.claude/checkpoints/`,
  `.claude/audit.log`, `.claude/audit.head`) has one, every call the hook
  does not let pass outright (`mutate`, a `git stash create` put to a
  person, a restore of a recorded checkpoint) is blocked the same way,
  whatever it names, before a marker is used. The reason names the record;
  remove the other name outside the session (`find <directory> -samefile
  <record>` lists them), since the command that removes it is refused too.
  The hook counts each regular file of the records that exist with `lstat`,
  following no link, with perl, or, where perl is not installed, with
  `find` and GNU `stat -c %h` or BSD `stat -f %l`. A file that goes while it
  is counted (a marker a parallel call takes) is no error. A count that
  finds a second name is taken once more after 0.2 seconds (the take hook
  enters the checkpoint key with `ln`, so it has two names for a moment),
  as is a `find` and `stat` count that meets an error; perl's count blocks
  the call at once when it meets an error. A directory of the records that cannot be read blocks the call
  with `R407`, with either counter, as does a git that does not say in time
  which git directory is the project's, for a call the hook gates.
- **Mutate**: the marker `.claude/checkpoint.ok` must exist, be a regular
  file (not a symlink, SEC-006) that git does not track (a repository can
  ship a tracked one; git is asked from the marker's own directory, so a
  linked or submodule `.claude` counts too, and the file is left as it is;
  the git directory git finds there must be one git made for a work tree,
  since a repository can ship `.claude` itself as a git directory whose
  index would answer and whose config names a program git runs; and an
  answer of git other than yes or no authorises nothing),
  be a JSON object with a `checkpoint_id`, a
  `created_at` and an `expires_at` in whole seconds of at most 12 digits, the
  first not in the future and the second at most 1800 seconds (30 minutes)
  after it, and be within both its `expires_at` and the layer's maximum age,
  `ACS_CHECKPOINT_MAX_AGE` seconds after its `created_at` (SEC-001), whoever
  wrote it; otherwise the call is blocked
  with `F501 CHECKPOINT_REQUIRED:`, a marker past either is filed under
  `.claude/checkpoints/ended/` and a malformed one is removed. Unless `ACS_HOOK_APPROVAL=off`,
  the permission mode must put the call to a person (`default`,
  `acceptEdits` or `plan`); in any other mode the call is blocked with `F502
  APPROVAL_REQUIRED:` and the marker is left in place. The call then **uses
  the marker up**: one rename moves it into `.claude/checkpoints/used/`, so
  two calls never pass on one marker (the one that loses is blocked with
  F501). Finally, unless `ACS_HOOK_APPROVAL=off`, the hook answers
  `permissionDecision: "ask"` with an `F502 APPROVAL_REQUIRED:` reason, so
  Claude Code asks the person; with `off`, approval is left to Claude Code's
  permission rules, and every audit line records that setting. The marker
  was used before the person answers, and Claude Code runs no hook when
  they do: a call allowed after the marker's maximum age, or after a
  boundary of another session, runs all the same (a host gap of these
  hooks, which do not claim the safety-layer class; SECURITY.md §5.5).
- A failure of the hook itself blocks the call with `R407
  SAFETY_CHECK_FAILED:` (exit 2; another exit code is blocked by
  `onFailure: "block"` only where Claude Code supports it).

The marker is written by `posttooluse_take_checkpoint.sh` after a `git stash
create` that succeeded (the call that saves the state takes the checkpoint,
§5.18.6), and by `CheckpointTracker(marker_dir=".claude")` in the Python SDK.
The hook writes none for a command over 4096 bytes, for a call run in the
background (its output is not yet the command's), for one the pre-tool-use
hook classified the worst case where it ran (its `cwd`: a `git` the shell
finds in the repository, or a git directory git did not make for a work
tree, such as a shipped `vendor/evil.git` whose `core.worktree` names the
project; the two hooks hold the same functions), for one whose `cwd` is in
another repository than the project's (another git directory or work tree),
for a commit it has no git directory to enter in, or for output that is
neither a commit id nor empty; empty
output (nothing to save) gives `HEAD` as the restore point only when the
project's tracked files and index are `HEAD`'s.
Its expiry is `ACS_CHECKPOINT_MAX_AGE` seconds when that is an integer from 1
to 1800, else 1800 (the Standard caps a checkpoint's maximum age at 30
minutes); while the project's settings files name one of the hooks' settings,
it writes no marker. Before it writes the marker, the hook enters the commit in
`<git dir>/acs/checkpoints/commits/` (an empty file named by the commit),
where a rollback looks it up. A new marker replaces the old one, which is
filed under `.claude/checkpoints/ended/`. `stop_end_checkpoints.sh` files the
marker there at an execution boundary: when a turn ends (`Stop`, or
`StopFailure` when an API error ended it), when the next turn starts
(`UserPromptSubmit`, which also ends a marker an interrupted turn left) and
when a session starts or ends (`SessionStart`, `SessionEnd`).

The hooks' scope is the project directory: every session in it, and each
session's subagents, share one marker, its history and the commit entries,
so a boundary of any session ends the marker.
Each gated call needs its own checkpoint; every marker filed under `used/`
or `ended/` stays the record of a checkpoint taken.

```mermaid
---
title: One checkpoint per gated call
---
flowchart TB
  accDescr: A successful git stash create writes the marker; a gated call that finds a valid marker in a mode that reaches a person moves it into the used directory and asks for approval; without a valid marker it is blocked with F501; the end or start of a turn or a session files the marker under the ended directory, and a rollback can still restore its commit.
  s["git stash create succeeds"] -->|writes| m[".claude/checkpoint.ok"]
  c["A gated call"] --> q{"Valid marker?"}
  m -.-> q
  q -->|no| f501["Blocked: F501"]
  q -->|yes| mode{"Mode reaches a person?"}
  mode -->|no| f502["Blocked: F502"]
  mode -->|yes| used["Marker moved to used/"]
  used --> ask["ask: the person decides"]
  stop["A turn or a session ends or starts"] -->|"files under ended/"| m
```

The marker file holds a JSON object. `checkpoint_id`, `created_at` and
`expires_at` are checked; `commit` names the restore point (a full commit
id, entered in the git directory, or `HEAD` for a clean tree), and `source`
is written for the reader:

```json
{"checkpoint_id": "3f2a...", "commit": "3f2a...", "created_at": 1706000000, "expires_at": 1706001800, "source": "git stash create"}
```

### Keeping the Agent from the Records

The hooks alone write the layer's records:

| Record | What it is |
|--------|------------|
| `.claude/checkpoint.ok` | The checkpoint marker |
| `.claude/checkpoints/` | Used and ended markers (`used/`, `ended/`) |
| `.claude/audit.log`, `.claude/audit.head` | The audit log and its head |
| `<git dir>/acs/` | The checkpoint key and entered commits (`checkpoints/`) and the head's anchor (`audit.head`) |

The audit log is not rotated: a person who starts a new log moves
`audit.log`, `audit.head` and the anchor aside under names of their own.

The boundary that keeps the agent's commands and file tools from the records
is Claude Code's permission deny rules, with the sandbox on. What was run
(Claude Code 2.1.332 on macOS, in `bypassPermissions` mode, on 2026-11-25):
`Edit(...)` deny rules for the marker, the checkpoint directories and the
audit log (relative, with `/**` and `audit.log*`; one absolute `//` form gave
the same result) refused the `Write` and `Edit` tools, and every route a
sandboxed command took: a symbolic or hard link made in the session, a
rename of the record or of a directory above it, `cp`, `rm`, truncation and
an interpreter's writes. A `Read(...)` rule, on a test directory, refused
the `Read` tool and `cat`. On Linux only the sandbox runtime was run
(`@anthropic-ai/sandbox-runtime` 0.0.82): literal absolute `denyWrite` paths
refused every route tried, and a glob was skipped. The exact rules below
(absolute, one per record), with the sandbox's `denyWrite` list, were run
under Claude Code 2.1.332 on macOS on 2026-11-25 for a fresh project: they
refused all 11 command routes tried (an append to the log and to the head,
`touch` of the marker, a new file under `.claude/checkpoints/` and under
`acs/`, a symbolic link to the log and to `.claude`, `python3`, `cp`, `rm`,
and a rename of `.claude`). The `Write` and `Edit` tools and the `Read`
rules on the git directories' records were not run with these rules, and
they have not been run under Claude Code on Linux. The sandbox's own `filesystem.denyWrite`
list covers sandboxed commands only, not the file tools. The hooks' reading of a call's
paths (above) refuses some calls early, and is advisory: it cannot see a
path a command builds when it runs. It still applies where the sandbox does
not: to hooks, to MCP servers and to commands the settings run outside the
sandbox.

`grounded_agency/layer_records.py` gives the rules for a project. It uses
the standard library alone and the syntax of Python 3.9, so it runs from the
plugin's directory under the system's `python3` (3.9 or newer):

```bash
python3 -I grounded_agency/layer_records.py /path/to/project
```

It prints a settings fragment, every path literal and absolute (the Linux
sandbox runtime skips a glob such as `audit.log*`):

```json
{
  "permissions": {
    "deny": [
      "Edit(//path/to/project/.claude/checkpoint.ok)",
      "Edit(//path/to/project/.claude/checkpoints/**)",
      "Edit(//path/to/project/.claude/audit.log)",
      "Edit(//path/to/project/.claude/audit.head)",
      "Edit(//path/to/project/.git/acs/**)",
      "Read(//path/to/project/.git/acs/**)"
    ]
  },
  "sandbox": {
    "filesystem": {
      "denyWrite": [
        "/path/to/project/.claude/checkpoint.ok",
        "/path/to/project/.claude/checkpoints",
        "/path/to/project/.claude/audit.log",
        "/path/to/project/.claude/audit.head",
        "/path/to/project/.git/acs"
      ]
    }
  }
}
```

- A permission rule's `//` opens an absolute path. A directory is denied as
  a whole: `dir/**` in a rule, the plain directory in `denyWrite`.
- Every record gets an `Edit(...)` rule. Only `acs/` gets a `Read(...)`
  rule: it holds the checkpoint key. The project's records hold no secret,
  and the audit skill cites the audit log as evidence.
- The git directory is the one `git rev-parse --absolute-git-dir` names for
  the project, where the hooks keep `acs/`: in a linked worktree, whose
  `.git` is a file, that is `.git/worktrees/<name>/acs` in the main
  repository. The `acs/` of the repository's other git directories gets the
  same rules: the main checkout's, each linked worktree's
  (`.git/worktrees/<name>`) and each submodule's (`.git/modules/<path>`,
  nested ones included), since a session in one checkout can otherwise
  write another's commit entries or read its key. A project in no
  repository has no `acs/` rule.
- A rule names a path that exists when the settings are made, so make them
  again after `git worktree add` or a submodule's first checkout.
- A project path reached through a symbolic link gets the rules under both
  its written and its physical path (`/var` and `/private/var` on macOS).
- A path that holds a character a rule reads as a pattern (`*`, `?`, `[`,
  `]`, `{`, `}`, `(`, `)`, `\`) or a control character cannot be written as
  a literal rule; the module refuses it (exit status 2), as it does when git
  does not say which git directory is the project's.
- `grounded_agency.layer_records.deny_settings(project_dir)` returns the
  same fragment to Python code; `layer_records(project_dir)` returns the
  records' paths. The pre-tool-use hook holds the same list of records, and
  a test keeps the two equal.

A deny rule protects a path, not a file. A record with a second hard link
made outside the boundary (by a person, a hook, an MCP server or a command
run outside the sandbox) can be written through that link on Linux, so the
pre-tool-use hook refuses every call it does not let pass outright while a
record has one (above).

While a sandboxed command runs, the Linux sandbox runtime puts empty files
and directories in the project as mount points (`.bashrc`, `.gitconfig`,
`.mcp.json`, an empty `.claude/` where there is none, and, under these
rules, an empty file at a record's path that does not exist yet), removed
when the command ends normally but left behind when it is killed. The
hooks must ignore them, and do for the files: an empty `.claude/` is used
as it is; an empty marker is removed, and the call needs a checkpoint; an
empty file has one link, so the link count passes it; the log hook reads
an empty `audit.head` as none and writes the head anew, while the anchor
in `acs/` still shows a cut log; an empty `audit.log` is a log with no
entries, a cut where its head or anchor records some. What the runtime
puts at a directory record that does not exist yet (`.claude/checkpoints`,
`acs`) has not been run; an empty file there would stop the hooks from
keeping that record (no marker is written, and the log hook says the
anchor is not kept) until it is removed.

The hooks write a new marker and a new head in `.claude/checkpoints/`, and
new entries, keys and anchors in `acs/`, then rename them onto the record,
so no file a hook writes is outside the rules before it becomes a record.

### The strict sandbox

The pre-tool-use hook lets a Bash call run with less than the worst case
(a read-only command with no checkpoint or approval, `git stash create` as
a checkpoint, a restore of a recorded checkpoint as a rollback) only when
Claude Code runs it under an operating-system boundary the hook has
verified for that call (STANDARD 1.2.0 §5.18.3, as RFC-0011 proposes it).
Otherwise the call is a gated `mutate`: it needs a checkpoint marker and
approval. Without the strict sandbox no checkpoint can be taken through
Bash, so every gated call is refused with `F501 CHECKPOINT_REQUIRED:`,
whose reason lists why the sandbox is not verified (up to six reasons).
The hook also refuses the agent's own edits to the settings files, so the
person adds the settings below to their user settings file outside the
session and starts Claude Code again.

The hook reads the settings files Claude Code reads, with `jq`:

| Scope | Files |
|-------|-------|
| Managed | `managed-settings.json`, then `managed-settings.d/*.json` (not hidden, in name order), in `/Library/Application Support/ClaudeCode/` on macOS and `/etc/claude-code/` on Linux |
| User | `settings.json` in `CLAUDE_CONFIG_DIR`, else in `~/.claude/` |
| Project | `.claude/settings.json` in the project directory |
| Local | `.claude/settings.local.json` in the project directory, at the repository's top level and at the main checkout's root (Claude Code reads it there in a git repository and a worktree) |

A file that exists must be a regular file that parses as a JSON object;
otherwise the sandbox is not verified. In a user or managed file, the
`sandbox`, `permissions`, `env` and `hooks` keys must have the types Claude
Code accepts (booleans, lists of strings, `credentials` lists of objects,
port numbers, objects), since Claude Code ignores a whole file with a value
of the wrong type. Where a managed source the hook does not read is
present, the sandbox is not verified either: the macOS managed preferences
domain `com.anthropic.claudecode` (in `/Library/Managed Preferences/`), the
server-managed settings cache (`remote-settings.json` in the user settings
directory), and, under WSL, the Windows policy chain. The system is decided
from files only the system installs (`/System/Library/CoreServices` on
macOS, `/proc/version` on Linux), and `OSTYPE` must agree with it, since
bash takes `OSTYPE` from the environment. On a system other than macOS and
Linux, Claude Code has no sandbox.

The conditions count only from user and managed settings, merged as Claude
Code merges them (managed over user, lists joined), so no repository file
can make a call more relaxed:

- `sandbox.enabled: true`, `sandbox.failIfUnavailable: true`,
  `sandbox.allowUnsandboxedCommands: false` and
  `sandbox.network.strictAllowlist: true`;
- none of `sandbox.excludedCommands`, `sandbox.filesystem.disabled`,
  `sandbox.filesystem.allowRead`, `sandbox.network.allowAllUnixSockets`,
  `allowUnixSockets`, `allowLocalBinding`, `allowMachLookup`,
  `httpProxyPort` or `socksProxyPort`, `sandbox.allowAppleEvents`,
  `allowNestedUserNamespaces`, `enableWeakerNestedSandbox` or
  `enableWeakerNetworkIsolation` (an empty list or `false` is fine): each
  runs a command outside the sandbox, lets a sandboxed command reach a
  process outside it, routes around the network allowlist, or (`allowRead`)
  reopens a path that a deny closes;
- every `sandbox.network.allowedDomains` entry a dotted DNS name in lower
  case whose last label is alphabetic, optionally with `*.` before it and
  `:port` after it, and not a loopback, link-local, metadata or local-use
  name (`localhost`, `*.local`, `*.internal`, `metadata.goog`, ...): an IP
  literal, a one-label name or `*` opens a route to a process outside the
  boundary or to every host;
- `sandbox.credentials.envVars` entries `{"name": ..., "mode": "deny"}` for
  `GH_TOKEN` and `GITHUB_TOKEN`, and for `AUDIT_HMAC_KEY` while it is set;
- a denial of each of these paths:
  - writes to the records, and reads of the git directories' records, as
    `grounded_agency/layer_records.py` gives them for the project (above);
  - writes to the project's `.claude/settings.json` and every local
    settings file in the table, the project's `.claude/hooks/`, the
    plugin's hooks directory (where the running hook is, links resolved),
    the user configuration directory (`CLAUDE_CONFIG_DIR` or `~/.claude`:
    the user settings, plugins, agents, commands, skills and, with
    `CLAUDE_CONFIG_DIR`, `.claude.json`) and, without `CLAUDE_CONFIG_DIR`,
    `~/.claude.json` (the user's tool servers): a command that writes them
    changes what the next session, hook or tool server runs;
  - reads and writes of the audit key file, `~/.config/acs/audit.key`;
  - reads of the user's credentials: `~/.ssh/`, `~/.config/gh/hosts.yml`,
    `~/.git-credentials` and, on macOS, `~/Library/Keychains/` and
    `/Library/Keychains/`;
  - writes to the project directory, where it holds a `.mcp.json` (and to
    the repository's top level, where that holds one): the tool servers it
    names run outside the sandbox from code in the repository; where there
    is none, writes to the `.mcp.json` path itself, so that no sandboxed
    command can create one for the next session to start;
- neither `enableAllProjectMcpServers: true` nor `enabledMcpjsonServers`:
  either starts the tool servers a `.mcp.json` names with no prompt.

A path is denied by a `permissions.deny` rule written `Tool(//<absolute
path>)` for a file, or `Tool(//<directory>/**)` for a directory or for any
directory that holds the path (`Edit` for writes, `Read` for reads), or by
an entry of `sandbox.filesystem.denyWrite` (writes) or `denyRead` (reads)
that is the absolute path or a directory that holds it, written literally.
Home paths count under the home directory as written and as resolved;
project paths under the project directory as written and as resolved, as
for the records. The plugin's hooks directory changes with each plugin
version, so a rule over a directory above it (the plugin cache) keeps
covering it. A rule or entry written another way (`~/`, `./`, a relative
path, another glob, a bare tool name) does not count. Under
`allowManagedPermissionRulesOnly` in managed settings, only managed rules
and entries count. A user `settings.json` that is a symbolic link means the
sandbox is not verified: a rule on its path does not protect the file it
leads to.

The project's and the local settings can only weaken the sandbox, and the
user-scope test showed that they do: a project's `sandbox.enabled: false`,
`excludedCommands` (even under the user's `allowUnsandboxedCommands:
false`) and `filesystem.allowWrite` each took effect over a strict user
sandbox, and so does an `Edit(...)` allow rule, which Claude Code merges
into `filesystem.allowWrite`. So in a project or local file:

- `sandbox` may hold only `enabled: true`, `failIfUnavailable: true`,
  `allowUnsandboxedCommands: false`, `autoAllowBashIfSandboxed`, an empty
  `excludedCommands`, `filesystem.denyWrite` and `denyRead`,
  `network.deniedDomains`, `network.strictAllowlist: true`, and
  `credentials.envVars` and `files` whose entries all have `"mode":
  "deny"`;
- `permissions` may hold no `additionalDirectories` and no `Edit` or `Read`
  allow rule;
- nothing may name a command or tool server that runs outside the sandbox:
  `hooks` (other than an empty object), `statusLine`, `fileSuggestion`,
  `apiKeyHelper`, `awsAuthRefresh`, `awsCredentialExport`,
  `otelHeadersHelper`, `enableAllProjectMcpServers: true` or
  `enabledMcpjsonServers`;
- the local files outside the project directory may set in `env` only the
  variables the check of the project's own env lets through (above): the
  hooks and commands run with their env too.

Anything else there (`enabled: false`, an excluded command, `allowWrite`,
`allowRead`, an `allowedDomains` list) means the sandbox is not verified.
Only managed settings keep a repository from changing the sandbox.

A call whose input sets `dangerouslyDisableSandbox` to anything other than
`false` is a gated `mutate` whatever the settings; under the strict sandbox
its refusal says to run it without the parameter. The hook does not decide
from a command's text whether it matches an excluded command: any
`excludedCommands` entry means no Bash call is relaxed.

The settings that meet these conditions for the project, with deny rules
for its records, come from `grounded_agency/layer_records.py` (above) and
the rules this section lists; written by hand, they look like this (paths
absolute, for each project and plugin copy):

```json
{
  "sandbox": {
    "enabled": true,
    "failIfUnavailable": true,
    "allowUnsandboxedCommands": false,
    "network": {"allowedDomains": ["example.com"], "strictAllowlist": true},
    "filesystem": {
      "denyWrite": ["/Users/me/.claude", "/Users/me/.claude.json"],
      "denyRead": ["/Users/me/.ssh", "/Users/me/.config/gh/hosts.yml",
                   "/Users/me/.git-credentials", "/Users/me/Library/Keychains",
                   "/Library/Keychains"]
    },
    "credentials": {"envVars": [{"name": "GH_TOKEN", "mode": "deny"},
                                {"name": "GITHUB_TOKEN", "mode": "deny"},
                                {"name": "AUDIT_HMAC_KEY", "mode": "deny"}]}
  },
  "permissions": {"deny": ["...the rules layer_records.py prints...",
                           "Edit(//Users/me/project/.claude/settings.json)",
                           "Edit(//Users/me/project/.claude/settings.local.json)",
                           "Edit(//Users/me/project/.claude/hooks/**)",
                           "Edit(//Users/me/project/.mcp.json)",
                           "Edit(//<plugin hooks directory>/**)",
                           "Read(//Users/me/.config/acs/audit.key)",
                           "Edit(//Users/me/.config/acs/audit.key)"]}
}
```

The check runs only for a call the classifier reads as other than
`mutate`, and for the text of a refusal. The hooks run nothing from, and
read nothing in, the directories the Linux sandbox runtime shares with the
host (`/tmp/claude`, `~/.claude/debug`): every temporary file they make is
in the records' directories.

What the hook cannot see, so cannot detect:

- settings given with `--settings` when Claude Code starts (they rank above
  user, project and local settings), and sources left out with
  `--setting-sources`. A person who starts Claude Code with weaker settings
  that way is not detected;
- that the sandbox is on: hooks run outside it, and Claude Code gives them
  no environment variable that says so (sandboxed commands see
  `SANDBOX_RUNTIME`, hooks do not);
- a value of the wrong type outside the keys it type-checks, which makes
  Claude Code skip the whole file, and a change since Claude Code loaded a
  file;
- whether the sandbox works on this system: `failIfUnavailable` makes
  Claude Code refuse to start where it does not;
- a program put on `PATH` by a local settings file at the repository's top
  level or the main checkout's root: such a file means the sandbox is not
  verified, but the hook's own programs (`jq`, `git`) are found on that
  `PATH` before the hook reads the file, as for any variable Claude Code
  sets before a hook runs;
- credential files other than those listed above (registry tokens, cloud
  credentials): deny them too, with `denyRead`.

## Audit Trail

The `posttooluse_log_tool.sh` hook keeps the plugin's log of tool calls,
one action record ([STANDARD v1.2 §6.4](../spec/STANDARD-v1.2.0.md#64-audit-records))
per call, in `.claude/audit.log`. It is not an `audit` step: the `audit`
skill writes its own records, of the events a workflow reports.

- Logs every tool call that ran, one JSON line per call (the `PostToolUse` and `PostToolUseFailure` matchers are `*`). A call that a pre-tool-use hook or a permission rule refused did not run and is not logged
- Never writes the tool input: a command, a file's content or a skill's arguments can hold a credential. A SHA-256 digest of the input is written in its place
- Uses HMAC-SHA256 chaining for tamper detection (SEC-005), under the key in `~/.config/acs/audit.key`, else `AUDIT_HMAC_KEY` (below)
- Each entry includes the HMAC of the previous entry, creating a hash chain: a changed or removed entry breaks the link of the entry after it
- Keeps the chain's end in `.claude/audit.head`: the number of entries and the last one's `hmac`, signed with the same key (`head_hmac`, the HMAC of `acs-audit-head:<entries>:<hmac>`), and the same head, its anchor, in the project's git directory (`<git dir>/acs/audit.head`; none outside a repository). Removing the last entries, or the whole log, breaks no link; the head shows it, and a command that removes `.claude` whole with the log and its head (`git clean -fdx`) leaves the anchor, which shows it. An earlier head written back with the cut, or one signed anew with the key, shows nothing: only a witness kept off the agent's reach does (below). Before it appends, the hook checks that the log still holds the entry the head and the anchor record, at its place: when it does not, or one is not a head this key signed, the hook says so, writes the line, and leaves both as they are, the evidence of the cut. The pre-tool-use hook refuses a call that names the head, `.claude` or the git directory's `acs/` (`F504`). To start a new log, move `audit.log`, `audit.head` and the anchor aside together
- Serializes concurrent runs (tool calls made in parallel) with flock(2) on the log file itself, opened for append, taken by `perl` or, without it, by `flock`, so the chain stays in order and sessions using either exclude each other. There is no separate lock file, and the kernel releases the lock when its holder exits, however it exits. A run tries for at most `AUDIT_LOCK_WAIT` seconds (default 40, at most 55) and then appends without the lock, with a warning, at once where the lock cannot be taken at all: the verifier reports an entry out of chain order, and a held lock cannot silence the log

The log is a best-effort capture (STANDARD v1.2 §6.4): it can miss a call,
but never silently. When it does not log a call, or logs it without a valid
HMAC or chain link, the hook says why on standard error and exits 1, which
Claude Code shows as a non-blocking hook error: no `jq`, a symlinked
`audit.log` (refused, SEC-006), no key or a key file it refuses, or no
`openssl` (the line is written unsigned, with `hmac` empty, and the head and
the anchor are left as they are; the verifier reports the line, and a signed
line after it starts a new chain), a line that could not
be built or written, a last line whose `hmac` cannot be read (the line is
written and starts a new chain), an input digest that could not be computed
(the line is written with `unavailable`), a log that no longer holds the
entry its head records or a head this key did not sign (the line is written
and the head kept), a log that had no head (one begun before the hook kept
one: its end is anchored from that line on), a head that cannot be written,
and input `jq` cannot parse:
Claude Code passes a call's input and result on as they are, and `jq`
refuses JSON nested past its depth limit or holding a lone surrogate escape
(a string cut in the middle of an emoji), so such input may be a tool call.
It exits 0 for a call it logged and for JSON that is not a tool call (no
input, a value that is not an object, no string `tool_name`).

As a store ([STANDARD v1.2 §6.6](../spec/STANDARD-v1.2.0.md#66-evidence-records-and-stores)),
the log is `durable`: a file in the project, which outlives the session,
with no retention of its own: lines are kept until someone removes them
(§6.3).

The layer's records grow with use, and the plugin neither rotates nor prunes
any of them:

| Record | Grows by | Size |
|--------|----------|------|
| `.claude/audit.log` | one line per tool call, succeeded or failed | about 0.7 KB a line (689 bytes on average over 30 lines for `Bash` and `Write` calls; a longer tool or skill name, or an anchor's reason, adds its length) |
| `.claude/checkpoints/used/`, `.claude/checkpoints/ended/` | one marker file per checkpoint: under `used/` when a gated call takes it, under `ended/` when its validity ends unused | about 160 bytes a file |
| `<git dir>/acs/checkpoints/commits/` | one entry per checkpoint taken, named by its commit | 64 bytes a file (the commit's signature), plus the objects `git stash create` wrote |

Each entry is an action record with these fields, in this order:

| Field | Value |
|-------|-------|
| `action_id` | The call's `tool_use_id`, or `<timestamp>-<pid>-<8 hex digits>` when the input names none |
| `timestamp` | Time of the entry, ISO 8601 in UTC |
| `actor` | `agent` |
| `intent` | `<tool> call`, the tool's name as `tool` shows it |
| `status` | `executed` (the call succeeded, `PostToolUse`) or `failed` (`PostToolUseFailure`) |
| `tool` | Tool name, as written when it is plain (1 to 128 ASCII letters, digits, `.`, `_`, `:` or `-`) and the secret scan (`hooks/secret_scan.sh`) finds no credential in it, else `[REDACTED]` (STANDARD 1.2.0 §6.7: an MCP server names its tools) |
| `call_id` | The call's `tool_use_id`, when the input names one |
| `details` | `event` (the hook event), `skill` (the skill name, on a `Skill` call only, shown as `tool` is: the model chooses it, and an MCP skill address is any text after a server's name, so one that is not plain or holds a credential is `[REDACTED]`) and `input_sha256`: SHA-256 of the tool input as compact JSON with sorted keys (`jq -cS .tool_input`), or `unavailable` when it cannot be computed (no SHA-256 tool, the one used fails, or jq's compact text is not JSON: jq prints a value nested past 256 levels as `<skipped: too deep>`, and a jq whose parser reads deeper input, as the CI runner's does, would otherwise digest that cut text) |
| `recorded_by` | The layer and the configuration that decided the call (STANDARD 1.2.0 §5.18.8): `name`, `version` (from `.claude-plugin/plugin.json`), `config_sha256` (SHA-256 of `hooks/hooks.json`) and `settings`, the effective `approval` (`ask`, or `off` with `ACS_HOOK_APPROVAL=off`) and `checkpoint_max_age_s` (`ACS_CHECKPOINT_MAX_AGE`, 1 to 1800, default 1800) |
| `prev_hmac` | HMAC of the previous entry, empty on the first |
| `hmac` | HMAC of this entry's other fields, as written |

A `Skill` call with the input `{"skill": "checkpoint"}`, logged with `AUDIT_HMAC_KEY=example-key`:

```json
{"action_id":"toolu_01AbCdEf","timestamp":"2026-11-15T12:00:00Z","actor":"agent","intent":"Skill call","status":"executed","tool":"Skill","call_id":"toolu_01AbCdEf","details":{"event":"PostToolUse","skill":"checkpoint","input_sha256":"a69e8f80ec2830e5006e68ce275a5077f299455c58def8f4d12762083815e11a"},"recorded_by":{"name":"agent-capability-standard plugin hooks","version":"2.0.0","config_sha256":"0ceea65560acc150f04a3b2a0fda541747b3dd4da7d8908d55fb5a6dbbbcc9f1","settings":{"approval":"ask","checkpoint_max_age_s":1800}},"prev_hmac":"","hmac":"c54196a4763dcfe01a567d39bfa73f5e43d16ede4f10984ea5861a6e2ad94900"}
```

A reader who holds a tool input can confirm it against `input_sha256`. The
digest is not a way to keep a short or guessable input secret: such an input
can be found by trying candidates. The digest is taken over the text jq
prints, and jq 1.6 and 1.7 print some numbers differently (jq 1.7 keeps
`1.000` as written, jq 1.6 prints `1`), so an input that holds such a number
is confirmed with the jq version that wrote the log.

A log begun before Standard 1.2 opens with entries of an earlier form: `ts`,
`event`, `tool`, `skill`, `input_sha256`, `prev_hmac`, `hmac`, and, before the
hook logged every tool call, `ts`, `skill`, `args`, `prev_hmac`, `hmac`, for
`Skill` calls only. The chain continues across each change and the verifier
accepts every form; the earliest entries still hold the skill arguments they
were written with.


```mermaid
---
title: The audit log's hash chain
---
flowchart TB
  accDescr: Each audit log entry includes the HMAC of the entry before it, so the entries form a hash chain, and audit.head keeps the chain's end, so that tools/verify_audit_log.py can check the log for changed, removed and missing last entries.
  e1[Entry 1] -->|HMAC included in| e2[Entry 2] -->|HMAC included in| e3[Entry 3]
  e3 -->|count and HMAC kept in| h[audit.head]
  e3 -.-> v[verify_audit_log.py checks the chain and its end]
  h -.-> v
```

Verify audit log integrity:
```bash
python tools/verify_audit_log.py
```

It checks the chain and that the log still holds the entry its head
records, at its place (`--head-file` names another head), and the same of
the anchor where there is one (`<git dir>/acs/audit.head` for a log in
`<project>/.claude/`; `--anchor-file` names another). Each line is
checked as the bytes the hook signed: the compact JSON `jq -c` writes,
ending in its `hmac` member, with each member named once, the HMAC taken
over the line without that member. A line that parses to the entry signed
but is not those bytes fails: one edited to name a member twice (most JSON
readers keep the last value, so `"status":"executed","status":"failed"`
parses to the signed `failed` and reads as `executed` to a reader that
keeps the first, or to grep), one with a blank or a `\u` escape inserted, one whose
`hmac` is not last, and a blank line. A log begun
before the hook kept a head, or a chain no head anchors (the `audit`
skill's `.claude/audit/records.jsonl`), is checked with `--no-head`, the
chain alone: removing its last entries is not seen.

The head and the anchor show a cut made by a writer that holds neither
the key nor an earlier head (an accident, a person's edit, `git clean
-fdx`). They do not show one made through the agent the log records: a
head stays valid for as long as its key, the agent's commands can read
the head and the anchor without a checkpoint or approval, and they can
read the key wherever it is in their environment or in a file they can
read. A command a person approved that names none of the records can then
cut the log and write back an earlier head, or a head the key signs anew,
and the log verifies. Keep a witness against that: copy `.claude/audit.head`
where the agent cannot write it (off the machine at the end of a session,
a CI artifact, a write-once store), and verify with
`--witness <copy>` (repeatable): a log cut before the witness's entry
fails, and goes on failing as the log grows again.

```bash
python tools/verify_audit_log.py --witness /mnt/audit-witness/project.head
```

### The audit key

The hook signs with the key in `~/.config/acs/audit.key` (`$HOME/.config/acs/audit.key`)
when that file exists, and with `AUDIT_HMAC_KEY` otherwise. When both are
set, the file wins. The file is the way to keep the key: hooks run outside
Claude Code's sandbox (as tested with Claude Code on macOS; Claude Code on
Linux has not been tested) and can read a file that a deny rule keeps from
the agent's commands and file tools, while every command the agent runs
inherits `AUDIT_HMAC_KEY` unless the sandbox removes it.

Create the key file once, from a terminal (`set -C` keeps a key that is
already there):

```bash
mkdir -p ~/.config/acs && chmod 700 ~/.config/acs
(umask 077; set -C; head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > ~/.config/acs/audit.key)
```

The hook uses the file only when all of these hold, and refuses it
otherwise:

- it is a regular file, not a symbolic link;
- it is owned by the user the hook runs as, and group and others have no
  permission on it (mode 600 or 400);
- it has one link: a second hard link, made where the agent's commands can
  read, gives them the key past a deny rule on this path;
- its directory is owned by the same user, is not a symbolic link, and
  group and others cannot write to it;
- its directory, as the system resolves it, is not inside the project
  directory, which the agent's commands may write (so a session started in
  the home directory signs nothing with the key file);
- its first line, without the line break, is 32 to 4096 visible ASCII
  characters. That line is the key.

A refused file is not replaced by `AUDIT_HMAC_KEY`: the hook writes the line
unsigned and says why the file was refused. With no file and no
`AUDIT_HMAC_KEY`, the hook writes each line unsigned and says so (exit 1, a
non-blocking error). No key is derived from anything else. The verifier
reads the key by the same rules, except the one about the project
directory, which it does not know (`--hmac-key` gives a key instead), reports each
unsigned line, and with no key runs no check (exit 2). The hook computes
the HMAC from SHA-256 with the key passed through pipes, so the key is on
no command line, where any process of the user could read it. The
checkpoint hooks and the rollback skill's hook compute the HMAC of a
checkpoint's commit entry under the project's checkpoint key the same way.
All four copy one implementation, `hmac_sha256.sh` in this directory, and
`tests/test_hmac_sha256.py` keeps the copies equal.

Keep the key out of the agent's reach with user settings that deny reading
it and writing it. A key file the agent can replace gives no evidence
against the agent: a key it chose signs whatever it writes. Give, with
literal absolute paths and no other globs:

- `permissions.deny`: `Read(//<absolute path of the key file>)`,
  `Edit(//<absolute path of the key file>)` and
  `Edit(//<absolute path of ~/.config/acs>/**)`. These cover the file tools
  and Bash under the sandbox, links and renames included (tested with Claude
  Code on macOS);
- `sandbox.credentials.files`: a deny entry for the key file;
- `sandbox.filesystem.denyWrite`: the directory, `<absolute path of
  ~/.config/acs>` (the Linux sandbox runtime skips a glob in `denyWrite`;
  Claude Code itself on Linux has not been tested);
- where `AUDIT_HMAC_KEY` is set, a `sandbox.credentials.envVars` deny entry
  for it, or every sandboxed command can read it.

Set `AUDIT_HMAC_KEY`, where it is used, in `~/.claude/settings.json`,
managed settings or the environment Claude Code starts in: while the
project's settings files name it (or another of the hooks' settings), the
hook writes no line (exit 1 with the reason), so no key the repository may
know signs one. A key the agent's commands can read is evidence against a
writer that is not the agent, not against the agent's own approved
commands (above).

A log signed with an earlier key (the one derived from the host name, or
an `AUDIT_HMAC_KEY` the key file now replaces) verifies only with that key,
and the hook reports its head, which that key signed, on every call. Move
`.claude/audit.log`, `.claude/audit.head` and the anchor
(`<git dir>/acs/audit.head`) aside together, outside Claude Code (the
pre-tool-use hook refuses a command that names them), and verify the moved
files with the earlier key:

```bash
python tools/verify_audit_log.py --hmac-key "grounded-agency-audit-$(hostname -s)" \
  --log-file moved/audit.log --head-file moved/audit.head --anchor-file moved/anchor.head
```

The earlier hook took the short host name each time it signed, and used
`grounded-agency-audit-default` where `hostname -s` failed. If an intact log
fails with the command above, give `--hmac-key grounded-agency-audit-default`,
or the key with the short host name the machine had when the log was
written.

The audit skill signs its records, `.claude/audit/records.jsonl`, under
`AUDIT_HMAC_KEY` only, never with the key file. Unlike the hooks, the skill
computes the HMAC with `openssl dgst -sha256 -hmac "$AUDIT_HMAC_KEY"`, so
while that command runs the key is on its command line, where any process
of the user can list it. Check the records with that key, outside Claude
Code:

```bash
python tools/verify_audit_log.py --log-file .claude/audit/records.jsonl --no-head --hmac-key "$AUDIT_HMAC_KEY"
```

Records written without `AUDIT_HMAC_KEY` are unsigned, and the verifier
reports each one.

## Hooks in Skill Frontmatter

Six skills (`audit`, `checkpoint`, `persist`, `rollback`, `send`, `transform`)
declare hooks of their own in the frontmatter of their `SKILL.md`. Claude Code
registers them when the skill is invoked. Their command hooks follow the same
contract as the hooks here: the tool call as JSON on stdin, exit 2 to block
with the reason on stderr, and a digest in place of the tool input in what
they log. Each sets `onFailure: block` and a 30-second `timeout`, as
`hooks.json` does for the pre-tool-use hook, so a run that fails, cannot
start or gives no verdict in time blocks the call; each reads a command in
time that grows with its length alone. Their prompt hooks hold only model-judged additions: a check the
Standard requires (approval, the checkpoint, rollback history, the
destination policy, secrets) is decided by code (STANDARD 1.2.0 §5.18.10).
[SECURITY.md §5.4](../spec/SECURITY.md#54-checks-enforced-by-code-and-checks-a-model-judges)
maps every condition of the skills' hooks to the Standard's checks or marks
it a model-judged addition. The rollback skill's command hook reads the
same entries as the hook here: a `git stash pop` or `git stash apply` that
does not name a commit a checkpoint entered in `<git dir>/acs/checkpoints/commits/`,
or that runs in another repository, restores no checkpoint and is blocked
with `F503 ROLLBACK_FAILED:`; it reads the command's words as the shell
passes them, and any spelling of a stash restore but `git stash apply|pop
<id>`, those four words alone, is blocked the same way.

The `persist` skill's command hook, the `audit` skill's `Bash` hook and
`pretooluse_require_checkpoint.sh` (for `TodoWrite`, `TaskCreate` and
`TaskUpdate`) share one secret scan, `secret_scan.sh` in this directory:
each copies it verbatim between its `# BEGIN secret-scan` and `# END
secret-scan` lines (a skill copied out of the plugin keeps working), and
`tests/test_skill_hooks.py` keeps every copy equal to the file. The file is not a hook: `hooks.json`
does not run it. The scan blocks content written to memory, and a record
appended to `.claude/audit/records.jsonl`, that holds a credential-shaped
value, with `F504 CONSTRAINT_VIOLATED:` (STANDARD v1.2 §6.7). `secret_in`
reads a text line by line and again with its line breaks read as blanks, as
the SDK's and the TypeScript rules read whitespace (a value on the line after
its name); `secret_lines` reads each line on its own, for a hook that joins
texts read apart (each string of a persist tool's input or of an audit
record, given once as it is and once with its own line breaks read as
blanks); `secret_values` lists what the rules whose match may hold whitespace
find, for the `persist` hook's comparison. Each reads a text with the JSON
escapes other encoders write for the characters its rules read decoded
(`secret_decoded`: `\u0022` and `\u0027` as an escaped quote, `\u0026`,
`\u002b`, `\u003c`, `\u003d` and `\u003e` as the character, PHP's `\/` as
`/`), as the SDK's and the TypeScript refusal rules do; and `secret_lines`
first looks for a value the plugin holds itself (`secret_held`):
`AUDIT_HMAC_KEY`'s value and `SECRET_HELD`, which the pre-tool-use hook sets
to the project's checkpoint key (`<git dir>/acs/checkpoints/key`) for a
persist tool's data, and the log hook to the audit key it read from
`~/.config/acs/audit.key` for the names it logs (STANDARD 1.2.0 §6.7: a
host recognises at least the credentials it holds itself). The `persist`
hook scans the text a call carries and the lines the file will hold after it
that it does not hold now, each also with its JSON-style escapes decoded, so
a credential whose key is already in the file, or that two edits build, is
read whole; it reads the lines a call changes with the six lines that are
not blank on each side, before and after the call, and refuses a value the
rules read there more often after it (a value put under a name the file
holds), and a change to a line of a private key block. Each of the scan's patterns reads the text in time linear in
its length: `grep -o`, which prints each match, looks for one from each
position of a line that matches, so its patterns start where no earlier
attempt's run can hold another (a URL's scheme from the start of its run)
or read a bounded run (a user option's name, at most 256 characters; a
cookie option's cookie name, at most 64); time
it with grep's output to a pipe, as the scan reads it, not to `/dev/null`,
where grep stops at the first match, and in a multibyte locale too: the
scan reads bytes (its functions set `LC_ALL=C` in the subshells they run in),
since in UTF-8 GNU grep reads a pattern whose class follows a repeated one
(the scheme rule, `[A-Za-z][A-Za-z0-9._-]* +`) with a matcher whose time
grows with the square of the line, and the skills' hooks run in the user's
locale.

The `audit` skill's `Bash` hook and `pretooluse_require_checkpoint.sh` also
share the SDK redactor's rule for JSON data, `secret_member.jq` in this
directory, copied the same way between `# BEGIN secret-member` and `# END
secret-member` (inside a single-quoted shell string, so the file holds no
single quote) and kept equal by the same tests: a value of 4 or more
characters, or a number, that is not a placeholder under a member named
for a credential, the value of a `{"name": "Authorization", "value": ...}`
pair, or the second of a `["Cookie", ...]` tuple. The pre-tool-use hook
applies it to what a persist tool stores, the audit hook to the record an
append writes (`{"password":"hunter2"}`, which the text scan, needing a
long or quoted value, does not see), each refusing with `F504
CONSTRAINT_VIOLATED:`. It compares names in ASCII lower case, as the SDK
does, with string functions rather than regular expressions, which jq
compiles at each test (1 MB of members took 22 s that way, 2 s now); a
name outside ASCII is also tested with Unicode case folding, so the hooks
find a name the SDK does not in rare spellings, never the reverse.

The `send`, `audit` and `rollback` skills' `Bash` hooks share one reader of
a command's words, `shell_words.jq` in this directory, copied the same way
between `# BEGIN shell-words` and `# END shell-words` and kept equal by the
same tests. It reads a command's simple commands and their words as the
shell passes them (quotes removed, unquoted glob characters marked, a
redirection's target and whether it writes), pairing quotes as bash pairs
them: a backslash escapes the next character, in double quotes and `$'...'`
too, so an escaped quote never closes one, and a line continuation is
removed, inside an operator (`<\<newline><` is `<<`) and before a comment as
well. It marks a word that holds `$'...'` or `$"..."` (kept as written: bash
decodes or translates them) and one that holds a command substitution whose
own quotes bash pairs apart from the text around it (a backtick, or `$(` or
`${` in double quotes), reads an unquoted extglob opener (`@(`, `!(`,
`+(`, `*(`, `?(`: once a command has run `shopt -s extglob`, bash expands
the group as a pattern and reads it as part of a word, blanks and `;`
included) as a token of its own, and names what it cannot follow (an
unclosed quote, an extglob pattern, a here-document, a process
substitution). jq's global
match costs the text times its matches, so each hook reads a command of at
most 16384 bytes with it; skill hooks stay registered for the rest of the
session, so each reads only a command that may concern it (one that names
`curl`, `wget` or `http`, the audit records, a program that writes the files
its input names, or `git stash`, in any quoting, line continuations joined,
or holds `$'...'`, `$"..."`, or a glob, a brace or an extglob opener that
may expand to one of those names) and leaves the others alone.

The same file holds the reader of a glob the three hooks match names with
(`glob_marks`, security round 5): each bracket expression is read as bash
reads one, a `[` with `!` or `^` and the characters up to the `]` that
closes it being one character, `[:alpha:]`, `[=c=]`, `[.c.]` and a `]`
first in the set included (`cur[[:alpha:]]`, `cur[]l]`, `.cl[a-z]ude` and
`git st[[:alpha:]]sh` once read the set's text as letters the name must
hold, or ended the set at its first `]`). Where a `[` that a `]` follows
opens a set it cannot read exactly, the run from it to the last `]` may
match any run, so it matches every name bash does, never fewer, and it
reads a word in time linear in its length. The send hook, which removes a
run's quotes before, also reads a `]` after a set as part of it.

## Relationship to Spec

These hooks implement runtime enforcement of VERIFY layer requirements:

| Spec Field | Hook Implementation |
|------------|---------------------|
| `requires_checkpoint: true` | `pretooluse_require_checkpoint.sh` blocks without a valid marker and uses one up per call (F501) |
| `requires_approval: true` | `pretooluse_require_checkpoint.sh` asks for approval in modes that reach a person, and blocks in others (F502) |
| `checkpoint` → `rollback` (`requires`) | `pretooluse_require_checkpoint.sh` counts a restore as a rollback only for a commit a checkpoint recorded, so a checkpoint was taken before it; any other restore is a `mutate` (F501) |
| Taking a checkpoint (§5.18.6) | `posttooluse_take_checkpoint.sh` writes the marker after a successful `git stash create` |
| Execution boundary (§5.18.6) | `stop_end_checkpoints.sh` files the marker under `.claude/checkpoints/ended/` when a turn or a session ends or starts; a rollback can still restore its commit |
| Unbound tools (§5.18.2) | `pretooluse_require_checkpoint.sh` treats every tool it does not list, MCP tools included, as a `mutate` |
| Audit records (§6.4), the layer's identity (§5.18.8) | `posttooluse_log_tool.sh` writes an action record of every tool call, with the configuration that decided it; the `audit` capability is the `audit` skill's |

The hooks apply no domain profile (Standard 1.2.0 §5.21): to apply one to
tool calls, use the Python adapter (`GroundedAgentConfig(profiles=...)`), or
a host that gives profiles to its runs.

See `schemas/capability_ontology.yaml` for full capability definitions.
