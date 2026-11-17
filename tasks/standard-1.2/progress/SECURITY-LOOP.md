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
