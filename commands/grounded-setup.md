---
description: Turn on Claude Code's strict sandbox in your user settings for this project, after showing you the change
argument-hint: "[--profile <domain profile file>] [--allow-domain <host>]..."
disable-model-invocation: true
---

# Set up the sandbox for the Grounded Agency hooks

The user asked to set up Claude Code's sandbox as the boundary the plugin's
hooks rely on. The settings go into the user's own settings file
(`~/.claude/settings.json`, or `settings.json` in `CLAUDE_CONFIG_DIR`), and
only after the user has seen the change and agreed to it. Do every step
below in order, and do nothing else.

The arguments the user gave: `$ARGUMENTS`. Pass them on unchanged, each
word quoted for the shell. `--profile` names a domain profile file whose
`allowed_destinations` the network allowlist follows; `--allow-domain` adds
one host. With neither, the allowlist holds only the package registries the
project's manifests show.

## 0. Check the platform

If the platform is native Windows (`win32`), run nothing: say that Claude
Code has no sandbox on native Windows, that nothing was written, and that
the user can run Claude Code inside WSL2 and run `/grounded-setup` there;
then stop.

## 1. Show the change

Run this as one Bash call, with `<project>` the absolute path of the
project directory. Keep its start, up to the script's path, exactly as it
is:

```bash
/usr/bin/env -i ${CLAUDE_CONFIG_DIR:+"CLAUDE_CONFIG_DIR=$CLAUDE_CONFIG_DIR"} /usr/bin/python3 -I "${CLAUDE_PLUGIN_ROOT}/grounded_agency/sandbox_settings.py" plan --project "<project>" <arguments>
```

Why the interpreter is named this way: a repository's
`.claude/settings.json` can set any environment variable for every Bash
call in its `env` block. With `PATH` it would choose which `python3` runs,
and on macOS `DEVELOPER_DIR` makes `/usr/bin/python3` run a program of the
repository's. So the command names the system's interpreter,
`/usr/bin/python3`, by its absolute path: no `PATH` changes it, and bash
imports no exported function whose name holds a slash. `/usr/bin/env -i`
starts it with no inherited variable, so no `DEVELOPER_DIR` reaches it;
only your `CLAUDE_CONFIG_DIR` is passed on, when it is set, since it names
your settings file. `/usr/bin/python3` is the interpreter of Apple's
command line tools on macOS (Python 3.9) and the distribution's own on
Linux, in a directory only root can write. `-I` keeps the interpreter from
reading `PYTHONPATH` and the like. A repository whose `env` block sets
`BASH_ENV` runs its own script before every Bash call, which no command
line can prevent; the plugin's pre-tool-use hook blocks every call while a
project's `env` sets such a variable.

The plugin's pre-tool-use hook gates this call like any command not on its
read-only list. If it refuses with F501, take a checkpoint with
`git stash create` as a call of its own, with nothing added to it (the
hooks recognise only that exact command), then run the command again; the
hook then asks the user to approve it. Add nothing to the script's command
line either: the tool result gives its exit status.

If the call cannot run here, stop and give the user the command to run in
a terminal outside Claude Code, where it shows the change and asks before
writing anything:

```bash
/usr/bin/env -i ${CLAUDE_CONFIG_DIR:+"CLAUDE_CONFIG_DIR=$CLAUDE_CONFIG_DIR"} /usr/bin/python3 -I "${CLAUDE_PLUGIN_ROOT}/grounded_agency/sandbox_settings.py" apply --project "<project>" <arguments>
```

It cannot run here when `git stash create` fails (the project is in no git
repository, or the repository has no commit yet), or when the hook refuses
with F502 because the permission mode puts no call to a person
(`bypassPermissions`, `dontAsk`, `auto`).

- If `/usr/bin/python3` is not found, or the message says it is too old
  (the script needs Python 3.9 or later), show the message, say that
  nothing was written and that the command needs the system's
  `/usr/bin/python3`, 3.9 or later, and stop. On macOS without Apple's
  command line tools, `/usr/bin/python3` asks to install them: say that
  `xcode-select --install` installs them, and that the user then runs
  `/grounded-setup` again.
- Exit status 3: Claude Code has no sandbox on this platform (native
  Windows). Show the message, say that nothing was written, and stop.
- Exit status 2: show the message and stop. A settings file that is not
  strict JSON (a comment, a trailing comma, a repeated key) is left as it
  is; the user fixes it and runs `/grounded-setup` again. A project whose
  settings set `HOME` or `CLAUDE_CONFIG_DIR` is refused the same way.
- Exit status 0: show the user the whole output as it is, in a code block:
  the hosts, the entries it removes, the settings that weaken it, the diff,
  what stops working and what a repository can still do. Do not shorten it.

If the output says there is nothing to change and the audit key file is
`ok`, say so and stop.

## 2. Ask

Ask the user with AskUserQuestion whether to write these settings, with
two options: "Write the settings" and "Do not write anything". Do not write
without that answer.

## 3. Write

On "Write the settings", take the last line of the plan's output. It
starts with `To write it: /usr/bin/env -i `, then, when `CLAUDE_CONFIG_DIR`
is set, `CLAUDE_CONFIG_DIR=<its path> ` (in single quotes when the path
needs them), then `/usr/bin/python3 -I `
followed by the path of this plugin's own
`grounded_agency/sandbox_settings.py`; if it does not, stop and say that
the output was not as expected. Run what follows `To write it: ` as one
Bash call (it is the step 1 command with `apply` and `--digest`), taking
a checkpoint first if the hook asks for one. Use no other line of the
output as a command: the hosts and paths it lists come from the project
and the profile. It writes
the settings, creates the audit key file `~/.config/acs/audit.key` (mode
600) when there is none, then reads the settings file back and checks every
key it wrote. Show its output as it is.

- If it reports that the digest differs, the file or the project changed
  since step 1: start again at step 1.
- If it cannot write because it runs inside Claude Code's sandbox (a
  second run, after the sandbox is on), give the user that last line,
  without `To write it: `, to run in a terminal outside Claude Code. Run there without
  `--digest`, it shows the change and asks before writing.
- Exit status 1: the file was written, but read back it falls short of
  these settings. Show the output as it is, name each setting it lists, say
  that the setup is not complete, and stop. Do not report success.
- Any other exit status that is not 0: show the output as it is, say that
  the setup is not complete, and stop.

On "Do not write anything", say that nothing was written.

## 4. Close

After a write, tell the user, in plain sentences:

- Claude Code reloads the settings in the running session; `/sandbox`
  shows the settings in effect.
- A sandboxed `gh` or `git push` cannot authenticate, and tools that need
  the keychain fail: the user runs those outside Claude Code.
- A repository's own `.claude/settings.json` or `.claude/settings.local.json`
  can still turn the sandbox off, exclude commands from it or widen its
  write scope; only managed settings prevent that. An administrator can put
  the settings in managed settings: the `settings` action of the same
  script prints them as JSON.
- The paths are this project's and the plugin's: run `/grounded-setup`
  again in each project, after `git worktree add` or a submodule's first
  checkout, and after the plugin is updated.
