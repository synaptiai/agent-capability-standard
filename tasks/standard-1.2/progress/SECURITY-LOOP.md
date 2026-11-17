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
  project-level configuration.

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
