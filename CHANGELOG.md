# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

Standard 1.2.0 (Candidate Standard) and capability ontology 2.2.0, accepted
by RFC-0005 to RFC-0011, with their implementation: the reference validator
and executor, the Python SDK, the plugin's hooks and skills, the new
TypeScript package `@synaptiai/acs-core` and the Standard Agents binding.
They resolve the findings of the Standard Agents mapping, which this release
also adds: all 64 findings about this standard are fixed
([`findings_agent_capability_standard.yaml`](docs/research/analysis/standard_agents_mapping/findings_agent_capability_standard.yaml)).
Every change to the Standard is backward compatible: a workflow valid under
1.1.0 validates and runs as before, and a change that would invalidate one
is phased in as a warning (Standard 1.2.0, Appendix D). The implementations
change in the ways listed under Upgrading. The plugin release that carries
this is a MAJOR version (3.0.0), for the renamed skills and the hooks'
behaviour; the version files change only at that release.

**Upgrading from v2.0.0.** Every breaking or behaviour change for a user of
the Python SDK, the plugin, the Standard Agents binding or the TypeScript
package, by component. A change described under Changed or Fixed is named
here and marked so.

**Before you upgrade.** The changes most likely to stop or change a setup
that works with v2.0.0, each linked to its entry under Upgrading.

- Python 3.14 or newer is required, and Rust 1.88 or newer to build from
  source ([requirements](#upgrade-requirements)).
- The slash commands `/gap-analysis-workflow` and
  `/digital-twin-sync-workflow` are now `/capability-gap-analysis` and
  `/digital-twin-sync-loop` ([renamed skills](#upgrade-renamed-skills)).
- The plugin's PreToolUse hook runs for every tool. `Skill`, `Agent`, `Task`
  and every tool the SDK mapper does not map (MCP tools, `Monitor`,
  `PowerShell`, `ExitWorktree`, ...) are a gated `mutate`: each call uses up
  its own checkpoint marker (F501 without one) and is asked for approval
  (F502) in the permission modes default, acceptEdits and plan, and blocked
  with F502 in the others unless `ACS_HOOK_APPROVAL=off`
  ([every tool](#upgrade-every-tool), [one marker per call](#upgrade-jq-marker)).
- Without Claude Code's strict sandbox, every Bash call is a gated `mutate`,
  read-only commands and `git stash create` included, so no checkpoint
  marker can be taken and every gated call is refused with F501. Add the
  settings `hooks/README.md` lists under "The strict sandbox" to
  `~/.claude/settings.json` outside Claude Code, then start it again
  ([strict sandbox](#upgrade-strict-sandbox)).
- While the project's `.claude/settings.json` or
  `.claude/settings.local.json` sets in `env` a hook setting or any variable
  other than Claude Code's own (for example `NODE_ENV` or `PATH`), or cannot
  be read, every call is blocked with R407. Move such an entry to
  `~/.claude/settings.json`, managed settings or the environment
  ([project settings](#upgrade-project-env)).
- While a file under the git directory's `acs/` has a hard link outside the
  records, the hook blocks every call with F504; while another of the
  project's records has one, it blocks every call it does not let pass
  outright. Remove the link outside the session. Counting links needs perl,
  or `find`, `awk` and a GNU or BSD `stat` (R407 without them)
  ([hard links](#upgrade-record-links)).
- The hooks need `jq` (R407 without it). Without `openssl` the take hook
  writes no checkpoint marker, so every gated call is refused with F501, and
  the log hook writes its lines unsigned ([jq](#upgrade-jq-marker),
  [checkpoint entries](#upgrade-earlier-checkpoints),
  [audit key](#upgrade-audit-key)).
- Checkpoints taken before the upgrade restore only as a gated `mutate`
  ([earlier checkpoints](#upgrade-earlier-checkpoints)).
- The log hook signs with the key in `~/.config/acs/audit.key`, else
  `AUDIT_HMAC_KEY`, and derives no key from the host name: with neither, it
  writes its lines unsigned. A log v2.0.0 wrote has no head and is signed
  with `AUDIT_HMAC_KEY` or the host-name key: outside Claude Code, move
  `.claude/audit.log` aside and verify it with `tools/verify_audit_log.py
  --no-head --hmac-key` and that key. The audit skill's
  `.claude/audit/records.jsonl` verifies with `--no-head --hmac-key
  "$AUDIT_HMAC_KEY"`; lines v2.0.0 wrote there carry no chain
  ([audit key](#upgrade-audit-key), [audit head](#upgrade-audit-head),
  [audit skill](#upgrade-audit-records)).
- Python SDK: a tool the mapper does not know is the strictest case (a
  checkpoint and approval), and `GroundedAgentConfig.approval` defaults to
  `"ask"`. Register an MCP tool with its real capability, and set
  `approval="off"` for the earlier approval behaviour
  ([Python SDK tools](#upgrade-sdk-tools)).
- Runs of 1.1 workflows can end differently. An approved step that fails has
  a `failed` record, with its code, from the moment it fails, also when its
  failure mode's rollback or checkpoint then fails (F503, F501) or finds no
  checkpoint to roll back to, where v2.0.0 left the record `approved`. The
  1.1 runtime fixtures `records_failure_rollback_fails` and
  `records_failure_nothing_to_roll_back` show it: on the v2.0.0 executor
  both end with F503 and the step's record `approved`; now that record is
  `failed` with code R402. A version-1 snapshot of a run in progress
  restores with the record members 1.2 adds
  ([failed record](#upgrade-failed-record), [snapshots](#upgrade-snapshots)).

**Requirements.**

- <a id="upgrade-requirements"></a>Python 3.14 or 3.15 is required (`requires-python = ">=3.14"`); 3.10–3.13
  are no longer supported. The extension's stable-ABI floor is 3.14.
- Building from source needs Rust 1.88 or newer (was 1.86), because `sha2`
  0.11 requires it.

**Python SDK: tool calls and the adapter (Standard 1.2.0 §5.18).**

- <a id="upgrade-sdk-tools"></a>Python SDK: a tool the mapper does not know is now the strictest case (a
  high-risk mutation that needs a checkpoint and approval), not `observe`;
  register an MCP tool with its real capability. `GroundedAgentConfig.approval`
  defaults to `"ask"`, so a call whose capability requires approval (Write,
  Edit, a mutating Bash command, `execute`/`mutate`/`send` tools) is put to
  the host's permission flow; set `approval="off"` for the earlier behaviour.
  `ToolMapping` is frozen and has a required `requires_approval` field.
  `ToolCapabilityMapper(ontology_dict)` now takes every flag from the dict it
  is given: pass the full ontology, a `CapabilityRegistry`, or nothing for the
  packaged ontology; with an empty or partial dict `map_tool` raises V101. An
  MCP tool registered without a `risk` takes its capability's risk (was
  `"medium"`), so a `retrieve` or `search` tool counts against the low-risk
  rate limit.
- Python SDK, the Bash classifier (security round 5): a command the
  read-only list would let pass, `git stash create` and a recorded restore
  take the worst case where the program the shell finds for the first word
  may be the repository's own: on `ToolCapabilityMapper.command_path` (the
  PATH the commands run with; `None`, this process's) it is found under an
  empty or relative entry, in a file in `ToolCapabilityMapper.project_dir`
  (`None`, this process's working directory; links followed, not where the
  project is the home directory, or holds it), or nowhere
  (`command_may_be_content`). `wrap_options()` sets both from the options
  (`env["PATH"]`, `cwd`). A project settings file that is not a regular
  file (a FIFO, a link to `/dev/ptmx`) is unreadable, so every call is
  refused with R407, as the plugin's hooks refuse it.
- Python SDK, the Bash classifier (security round 5, batch 2): `pip list`
  and `pip show` are off the read-only list and get Bash's worst case
  (`mutate` and `send`: a checkpoint, approval, and F504 under a
  destination policy), since pip runs the program its site configuration's
  `python =` names (`.venv/pip.conf`, which `python -m venv` keeps from the
  repository, read even with `--isolated`) and its interpreter runs the
  `.pth` files of its site-packages. So does a line with a simple command
  that holds a redirection and no words (`ls; <f`: zsh runs
  `$READNULLCMD <f`, a pager, for it). A local git change that writes the
  work tree (`git reset`, `git checkout --`, `git stash ...`; it was
  `mutate`) and the restore of a recorded checkpoint (it was `rollback`,
  needing nothing) get the worst case wherever any scope, the user's
  included, configures a filter's `smudge` or `process` command
  (`ToolCapabilityMapper.git_filter_may_run`): git-lfs's, which `git lfs
  install` writes, asks the LFS server the repository's `.lfsconfig` names
  for each object its store lacks. With git-lfs installed, take a
  checkpoint and approve a restore, or install it with `git lfs install
  --skip-smudge`, whose two commands count as none.
- Python SDK, tool calls (security round 5, batch 3): the checkpoint
  recorder classifies a call in the directory it ran in (its hook input's
  `cwd`, else the one the PreToolUse hook kept; `create_checkpoint_recorder`
  takes `call_dir`, which `wrap_options()` sets), so a `git stash create`
  the PreToolUse hook classified the worst case there (a git directory the
  repository ships, such as `vendor/evil.git` with a `core.worktree`, or a
  repository's `git` on `PATH`) takes no checkpoint, and one whose input
  names another directory than the hook's takes none. The permission
  callback counts a decision against the binding as it is when the decision
  arrives: a call whose binding changed since PreToolUse checked it, or
  while your `can_use_tool` decided (the tool registered again, or a
  composite loaded again because a tool it invokes was), is checked again
  under the new binding and, where it requires approval, refused with F502;
  the new policy's `min_approvers` above 1 or `role` is F502 too, and its
  `approval.expires` counts from PreToolUse's ask. Register a tool before
  its calls, not while one waits for a decision.
- Python SDK, tool calls (security round 5, batch 5): the reason of every
  PreToolUse decision, an ask's F502 included, is redacted as the call
  record is (§6.7): an ask named the tool the model called verbatim, a name
  that may hold a secret, in the text a host's `can_use_tool` callback and
  permission prompt show. `check_offered` is unchanged; give it the
  mappings `adapter.mapper.map_tool` gives under domain profiles (below).
- Python SDK, `wrap_options()` (Changed): tools pre-approved in
  `allowed_tools` now count against the rate limit (raise
  `GroundedAgentConfig(rate_limit=...)` if an agent needs more); an error in
  the PreToolUse safety check denies the call in strict mode (in non-strict
  mode it is logged, and a call that requires approval is still asked),
  and an error in the rate check denies it in either mode (R407); `Skill`
  is no longer added to `allowed_tools`; Stop, UserPromptSubmit and
  SubagentStop hooks are added.
- Python SDK, `wrap_options()` (Fixed): a `can_use_tool` callback in the
  options it is given is now chained to, not replaced: once the layer's
  checks pass, the adapter's callback hands the call to the host's, whose
  answer decides it, so a callback that v2.0.0 dropped now takes effect.
- Python SDK, `wrap_options()` (Fixed): `setting_sources` is passed through
  unchanged. It added `"project"`: `[]`, the SDK's isolation mode for a
  `cwd` that may be untrusted, loaded that directory's project settings
  (whose hooks run commands and whose `env` applies), `None` (every source)
  became the project's settings alone, so the user's and local deny rules
  and hooks were dropped, and `["user"]` became `["user", "project"]`. A
  host that wants a project's skills or CLAUDE.md loaded includes
  `"project"` itself (or leaves `None`, every source, on an SDK where that
  is the default).
- Python SDK, `wrap_options()`: where the CLI loads the project's settings
  (`setting_sources` `None`, or naming `"project"` or `"local"`), the
  PreToolUse hook refuses every call with R407 while the
  `.claude/settings.json` or `.claude/settings.local.json` it loads from
  the options' `cwd` sets a variable in `env` that is not one of Claude
  Code's own settings (`grounded_agency.utils.project_settings`,
  `ALLOWED_PROJECT_ENV`), or cannot be read: the CLI applies that env to
  every command it runs, so `BASH_ENV` made `ls` run a repository script
  and `GIT_CONFIG_*` made `git status` run a repository program, each
  classified `observe`. Move such an entry into `options.env` or the
  host's environment, or pass `setting_sources` without `"project"` and
  `"local"`. The plugin's hooks refuse the same calls.
- Python SDK, `wrap_options()`: Bash runs under Claude Code's sandbox by
  default, and the Bash classifier relaxes a call (a read-only command,
  `git stash create`, a recorded restore, a local change without `send`)
  only while that sandbox is verified for it (STANDARD 1.2.0 §5.18.3,
  RFC-0011), and only for the CLI the Agent SDK bundles in a version under
  which the boundary tests ran (Claude Code 2.1.332, bundled with
  `claude-agent-sdk` 0.2.189, which `constraints.txt` pins): with
  `cli_path`, an SDK that bundles no CLI, or one that bundles another
  Claude Code version, every Bash call is its worst case. It relaxes a
  call only in `bypassPermissions` mode (`CHECKED_PERMISSION_MODES`), the
  one mode in which the precedence of settings files was tested: a call in
  any other mode, or with no mode stated (it runs in `default`), is its
  worst case, and so is every call under options, or a settings file's
  `permissions.defaultMode`, in another mode. In `bypassPermissions` a call
  that requires approval is refused with F502 unless `approval="off"`. The
  pre-tool-use check decides once for each call whether the sandbox is
  verified, and a Bash call it gave the worst case takes no checkpoint
  when it reports back, even where the sandbox is verified by then; its
  evidence is filed under the worst case's capability
  (`create_evidence_collector` takes the decision as `boundary_held`). An
  allowlist entry the setup command would not list (a
  trailing-dot or hex form of a local address, a wildcard such as `*.*`),
  a `metadata.` name, a port or an IPv6 literal leaves the sandbox
  unverified. Where the options carry no sandbox of their own,
  `wrap_options()` sets a strict one: on, refusing to start when it cannot
  sandbox (`failIfUnavailable`), no unsandboxed commands, no excluded
  commands, a network allowlist of
  `GroundedAgentConfig.sandbox_allowed_domains` (empty by default: no
  host) with `strictAllowlist`, and the keychains, `~/.ssh`, `~/.gnupg`,
  `~/.netrc`, the cloud tools' and package registries' credential files,
  gh's and git's credential files, the audit key file, Claude Code's
  credentials, the paths in `GroundedAgentConfig.sandbox_deny_paths`, the
  token and agent variables and every variable whose name looks like a
  credential's (with `sandbox_deny_env` for more) out of reach, and
  `filesystem.denyWrite` paths for the plugin hooks' records. It also
  adds `permissions.deny` rules to the options' `settings` (a settings
  file is read and passed inline): `Edit` and `Read` of the adapter's
  records; the rules `grounded_agency/layer_records.py` gives for the
  hooks' records, `Edit` and `Read` of `acs/` in each git directory of
  the repository (the project's, the main checkout's, each linked
  worktree's and each submodule's, and, from a submodule checkout, its
  superprojects', as they exist at the wrap) among them;
  `Edit` of the project's `.claude/` and `.mcp.json`, the
  repository's git configuration and hooks, the user's Claude Code
  settings, and the code that runs outside the sandbox (the
  `grounded_agency` and `claude_agent_sdk` packages, the interpreter and
  its site-packages, `cli_path`, local plugins and the files stdio MCP
  servers run), and `Read` of the credential files. The `Edit` rules
  apply to the file tools too, so a wrapped session cannot edit an
  editable install of `grounded_agency` in its project. A sandboxed command cannot reach the network,
  so `gh`, `git push`, `curl` or a package install from Bash fails unless
  its host is on `sandbox_allowed_domains`, and with the keychain denied
  `gh` and `git push` cannot authenticate. Options with a sandbox of their
  own (`sandbox`, or a `sandbox` member of `settings`) keep it; the
  classifier relaxes their Bash calls only if it holds every value of the
  strict one. Claude Code refuses to start where it cannot start the
  sandbox (Linux without bubblewrap and socat, native Windows, a container
  that cannot run bubblewrap); there, pass
  `GroundedAgentConfig(sandbox=False)`. Without a verified sandbox
  (`sandbox=False`, a weaker sandbox, a `WebFetch` allow rule or an `Edit`,
  `Write` or `Read` allow rule with a path in `settings` or
  `allowed_tools`, `add_dirs` or `permissions.additionalDirectories`, any
  `extra_args` flag but `debug-to-stderr`, `mcp_servers` given as a file
  or text, a settings source the CLI reads that may weaken it or that
  changed since the wrap, a policy source the adapter does not read, a
  non-empty allowlist while a destination policy is in force, a deny rule
  or `denyWrite` path for the hooks' records missing, hooks' records that
  cannot be named (no git, or a path a rule reads as a pattern), options
  changed after the wrap, or options not yet wrapped), every Bash call is a gated `mutate` and `send`: `ls`
  needs a checkpoint and approval, and `git stash create` takes no
  checkpoint (use `create_checkpoint`). The deny rules are added either
  way. A call that sets `dangerouslyDisableSandbox` is always the worst
  case.
  `ToolCapabilityMapper.os_boundary` is the check; with `None`, the
  default, every Bash call is the worst case, so a bare
  `ToolCapabilityMapper()`, and `create_checkpoint_recorder` or
  `create_evidence_collector` without the adapter's mapper, classify
  `ls` as `mutate` and `send` and record no checkpoint for
  `git stash create`.
- Python SDK, `register_mcp_tool` (Fixed): a capability the ontology does
  not define raises `ValueError` (V101) at registration, where v2.0.0
  registered the tool; a declared `risk` below the capability's is ignored
  and reported (W602), so a `mutate` tool registered with `risk="low"`
  needs a checkpoint again.
- Python SDK, Bash: `sed`, `awk` and `env` are no longer read-only, since they
  can write a file or run another command; a call to one needs a checkpoint
  and approval like any other mutation. The classifier reads the whole line
  with the shell's quoting rules (Fixed): a line is read-only only when
  every command in it is.
- Python SDK, tool calls (Standard 1.2.0 §5.18):
  - A checkpoint is used up when its call is allowed (at the permission
    callback's allow, or at PostToolUse for a call that did not pass the
    callback), and a call that fails uses it too. The newest valid checkpoint
    no other call holds is used, the earlier ones included. A hold that
    lapses or is unresolved when the turn ends counts as used. The Stop of
    any session the adapter serves ends every checkpoint's validity, and so
    does its next prompt (UserPromptSubmit), since a turn can end without
    Stop (StopFailure after an API error, an interrupt): take a checkpoint
    in the turn that needs it, and serve sessions that must not share this
    with separate adapters. A tracker does not load a state file
    (`tracker_state.json`) that git tracks: a repository can ship one, and
    its checkpoints were taken by no call here; the tracker starts fresh and
    logs a warning. Security round 4: nor does it merge one into the file
    it writes (unless it is the file it wrote last), and a state file nested
    too deeply to parse (`[[[...`, RecursionError) is one that does not
    parse, so the tracker starts fresh and replaces it; a write of the state
    file no longer raises (it is logged, and the change stands in memory),
    so a boundary always ends every checkpoint's validity and a PreToolUse
    check that fails releases the hold it made.
  - One adapter, and one `CheckpointTracker`, is one scope: a checkpoint it
    reads back from its `checkpoint_dir`, taken by an earlier process or by
    another adapter on the same directory (the default `.checkpoints` is
    shared by every adapter in a working directory), no longer authorises
    its calls. It is still found and restored (`find_checkpoint`,
    `restore_checkpoint`), but `has_valid_checkpoint`, `validate_and_reserve`,
    `has_taken_since` and `has_commit` count only the tracker's own, and a
    hold the state file names is left to its holder (it is no longer marked
    used on load). After a restart, take a new checkpoint before a gated
    call. Trackers that share a directory merge their records into its
    state file under a lock (`tracker_state.lock`, where the platform has
    `fcntl`), so one no longer drops or rewinds another's.
  - `CheckpointTracker` (Fixed) opens `checkpoint_dir`, its `archive/` and
    their files without following a symbolic link (at those directories, at
    each directory on the way to a relative `checkpoint_dir`, and at the
    files), appends only to a regular archive file (created with mode
    0600), and neither reads nor appends to an archive git tracks. A
    repository could ship a link there (the default `.checkpoints` is in the
    working directory), and the 101st checkpoint's prune appended the
    pruned checkpoints, with a `reason` and `scope` a bound checkpoint
    tool's caller writes, wherever it led. With such a link the tracker
    writes nothing, keeps its records in memory and logs a warning; a prune
    is logged with the ids it drops, and the pruned checkpoints' content is
    discarded whether or not the archive was written.
    `FileSnapshotStore(root, store_dir)` raises `ValueError` when
    `store_dir`, its `objects/` or its `manifests/` is a symbolic link (or,
    for a relative `store_dir`, a directory on the way to it): name the
    directory it leads to.
  - `wrap_options()` registers the safety PreToolUse hook with
    `on_failure="block"`: a callback that fails or gives no verdict in time,
    as the CLI sees it, blocks the call, where it was no decision and the
    call ran. With it, the SDK refuses to connect to a Claude Code that does
    not honour `on_failure` (`CLIConnectionError`): update Claude Code. A
    `claude-agent-sdk` whose `HookMatcher` has no `on_failure` cannot ask
    for it; the adapter logs a warning and registers the hook as before.
    Its matcher also states the CLI's time limit, `timeout=60` seconds
    (`SAFETY_HOOK_TIMEOUT_S`, the SDK's default), where the SDK's
    `HookMatcher` has the field.
  - `expiry_minutes` (the adapter's and `CheckpointTracker.create_checkpoint`'s)
    must be more than 0 and at most 30; `checkpoint_reservation_seconds`, if
    set, more than 0 and at most the expiry, and
    `CheckpointTracker(reservation_seconds=...)`, if set, more than 0: a 0,
    which made a hold lapse at once, now raises `ValueError`.
    `GroundedAgentConfig` gains `call_record_limit`.
  - `CheckpointTracker(max_age_minutes=...)` (default 30; the adapter passes
    its `expiry_minutes`) bounds every checkpoint: one taken through
    `adapter.checkpoint_tracker.create_checkpoint()` with a longer
    `expiry_minutes` is stored with the maximum age as its expiry, and one
    taken through the tracker stops authorising a call at its `created_at`
    plus the maximum age. A checkpoint dated after the clock
    (a crafted state file, a clock that stepped back) authorises nothing,
    counts as no checkpoint taken and names no restore point; one found
    dated after the load is dropped from the state.
  - `CheckpointTracker`: `can_reserve()` and `release_reservation_in_scope()`
    are removed. `resolve_holds_in_scope(scope)` replaces the latter, and
    counts the holds it ends as used instead of releasing them.
    `DEFAULT_RESERVATION_SECONDS` is `None` (was 600.0): a hold lasts until
    its checkpoint expires unless `reservation_seconds` is set.
    `has_valid_checkpoint()` now counts every valid checkpoint, those in the
    history included, whether or not a call holds it: use
    `valid_checkpoint_id()` for the one a call would hold, or
    `get_active_checkpoint_id()` for the active one.
  - `WorkflowEngine.ensure_checkpoint_before_step()` returns the valid
    checkpoint a step can use, one in the history included, and takes a new
    one only when every valid checkpoint is held; before, it took a new one
    whenever the active checkpoint had been used.
  - A call that needs a checkpoint and carries no `tool_use_id` (a `None`
    or id-less `can_use_tool` context, a PreToolUse hook called without
    one) is refused: F501 when no valid checkpoint exists, else R407, since
    the layer cannot hold a checkpoint for a call it cannot name. Before,
    such a call was allowed when a valid checkpoint existed. Claude Code
    always names its calls; code that calls the callback or the hook itself
    passes a context with a `tool_use_id`, one per call.
  - Approval is asked only in the permission modes `default`, `acceptEdits`
    and `plan`. In `bypassPermissions`, `auto`, `dontAsk` or any other mode,
    a call that requires approval is refused (F502), since nothing puts it to
    a person. A binding whose `approval` asks for more than one approver or a
    `role` is refused F502. Arguments the permission callback changes are
    classified again. A binding's `approval.expires` is applied: the
    permission callback refuses (F502) an allow that arrives later than
    that after the PreToolUse hook asked.
  - With a `permission_prompt_tool_name` (no `can_use_tool`), the adapter
    never sees a call allowed, so it cannot check the call's checkpoint
    again then, nor when the decision came: a call that requires a
    checkpoint (Write, Edit, a mutating Bash command, a `mutate` or `send`
    tool) is refused with R407, and one whose binding sets
    `approval.expires` with F502. Before, such a call was asked about and
    ran on its checkpoint even when the prompt was answered after the
    maximum age or a boundary. Pass a `can_use_tool` callback to run them.
    On that route a call that requires approval of a tool
    `create_grounded_mcp_server` serves (with `require_layer`) is refused
    with R407 too: such a tool runs only a call the adapter saw allowed.
  - `wrap_options()` on options it already wrapped (Fixed): the safety hook
    is replaced by one built for the options now wrapped, so a
    `permission_prompt_tool_name` or a `permission_mode` set between the
    two wraps applies as if the options were wrapped once (R407 for a call
    that requires a checkpoint and F502 for `approval.expires` on the
    prompt-tool route). Before, the first wrap's hook stayed: with a prompt
    tool added, a Write was asked about, held a checkpoint no callback
    checked again, and ran after a boundary.
  - The permission callback decides only on what the PreToolUse hook
    checked of the call (Fixed). The hook keeps, by `tool_use_id`, the
    digest of the input it checked, the call's directory and the time of
    its ask, until the call reports back or the callback refuses it; an
    execution boundary no longer clears them. The callback refuses with
    R407 a call the hook has no record of: code that calls
    `_make_permission_callback()` itself runs the hook on the call first,
    as Claude Code does. An input other than the one the hook checked
    (another PreToolUse hook's `updatedInput`) is changed arguments
    (Standard 1.2.0 §5.18.7): F504 when a secret or destination check fails
    with it, F501 when it needs a checkpoint the call does not hold, F502
    when it needs approval. Before, another session's Stop or prompt
    between the hook and the callback made the callback classify the call
    in the host process's directory (a git read in a partial clone then
    ran as `observe`, with no approval and on an ended checkpoint) and count
    `approval.expires` from its own start, and an input another hook
    rewrote was allowed without the secret and destination checks. A call
    the hook passed that Claude Code's own rules allow without the callback
    (`allowed_tools`, an allow rule, `bypassPermissions`) still runs with
    another hook's `updatedInput` unchecked: keep the tools such a hook
    rewrites out of those rules (the statement names this host gap).
  - A tool `create_grounded_mcp_server` serves (with `require_layer`) runs
    a call only once it is allowed: the PreToolUse hook's pass, or the
    permission callback's allow of a call the hook asked about. Before, the
    hook's ask granted it, so a caller outside the wrapped session that
    shared the server object ran the call while no one had decided, and the
    decision stayed after a refusal the adapter never heard of. Every
    refusal the callback makes (an error of the host's callback included)
    and a call that reports back withdraw it.
  - Every refusal reason is the text form `CODE NAME: message` (F501, F502,
    F503, F504, R407, V102), and the diagnostics are kept in
    `adapter.call_records`. A rate limit is F504; a failure of the safety
    check itself is R407.
  - A `rollback` call is refused (F503) unless a checkpoint was taken since
    the adapter started; it uses no checkpoint, and no longer invalidates
    the others.
  - `Skill`, `Agent` and `Task` are their own capability (`invoke`,
    `delegate`) and Bash's worst case, `mutate` and `send`, whatever the
    skill or agent (was `invoke` and `delegate` alone, needing nothing):
    Claude Code runs the shell commands a skill's file embeds (``!`cmd` ``
    and ```` ```! ```` blocks) as the skill loads, and the hooks and MCP
    servers a subagent's definition names, with no hook event the adapter
    sees. Each such call needs a checkpoint and approval, and a destination
    policy refuses it. `Skill(checkpoint)` still takes no checkpoint: the
    call that saves the state does, so take one (`git stash create`)
    before the Skill call. `create_checkpoint_recorder`
    (`create_skill_tracker` stays as an alias) records one when a call
    classified `checkpoint`, such as `git stash create`, succeeds. It takes
    none for a `git stash create` run in the background, one whose output
    is neither a commit id nor empty, or one that printed nothing while the
    tracked files or the index of the repository it ran in (the call's
    `cwd`) differ from `HEAD`: `HEAD` would not restore that change.
  - Bash: `git stash create` is `checkpoint`, `git stash list|show` only
    read, and a line of several commands takes the strictest flags and every
    prerequisite of all of them. `git stash pop|apply <commit>` is `rollback`
    only when `<commit>` is the full id of a commit a checkpoint of the
    adapter's scope recorded (`metadata["commit"]`); git applies any merge
    commit as if it were a stash, so any other `pop` or `apply`, a bare one
    included, is a gated mutation that needs a checkpoint and approval.
    `git rev-parse` and `git ls-files` are read-only (they were gated
    mutations). A command whose effect the classifier does not know (any
    command off its lists, `curl URL`, `gh`, a `git push`, `npm publish`,
    `docker push` or `kubectl` change) now has `send` beside `mutate`, and
    an interpreter `send` beside `execute`, in its capabilities and records,
    so a profile's rule for `send` applies to it and a destination policy
    refuses it (F504). These lines are no longer read-only: one with a `$`
    outside single quotes (`echo $HOME` included) or a brace expansion; an
    unquoted `*`, `?` or `[` in a `find`, `sort`, `uniq`, `date`,
    `hostname`, `file` or `git` command (quote a pattern you pass on); and
    `sort`, `uniq`, `date`, `hostname` or `file` with an option outside the
    listed read-only set or an abbreviation of one that writes (`sort
    --o=x`, `git diff --outp=x`), or `date` with an operand other than
    `+FORMAT`.
  - Bash: commands that ask another host are no longer read-only: `npm
    view`, `kubectl get`, `describe` and `logs` (a registry or a cluster
    that the configuration or an option names; a kubeconfig's `exec` runs a
    command), `git remote show`, and `pip list` or `pip show` with an option
    outside a listed set (an index, a proxy, `--outdated`); nor is a line
    with an input redirection from `/dev/tcp/` or `/dev/udp/`. Each gets
    Bash's worst case, `mutate` and `send`: it
    needs a checkpoint and approval, and a destination policy refuses it
    (F504). `git remote`, `git remote -v` and `git remote get-url` stay
    read-only.
  - Bash, fail-closed fixes: these are no longer read-only and get the
    worst case, `mutate` and `send`. `less` and `more`, with any options (a
    lesskey file, which `less -k`, `--lesskey-src` or an abbreviation names,
    `/dev/stdin` fed by a pipe included, sets `LESSOPEN`, which less runs;
    use `cat` or `head`). `npm list` (npm's update check sends the token a
    project's `.npmrc` gives for the registry it names) and `docker ps`,
    `docker images` and `docker logs` (the daemon `DOCKER_HOST` or the
    docker context names). A git command that would only read (`git
    status`, `git log`, `git show`, `git diff`, `git stash list|show`, ...)
    where the repository it runs in is a partial clone, or where git cannot
    say: there git fetches each object it lacks from the promisor remote.
    The adapter reads the call's directory from the hook input's `cwd`, and
    `ToolCapabilityMapper.map_tool` takes it as an optional `cwd` (None:
    the process's working directory); `git stash create` and the restore of
    a recorded checkpoint keep their classes there. A command over 4096
    UTF-8 bytes is not read (the plugin hook's bound): the worst case, where
    a quoted run of 40,000 blanks took 8 seconds to classify; a quoted `>`
    (`grep " > " f`) is now an argument, not a redirection. Any quoted or
    escaped operator (`'<'`, `";"`, `\;`, `'&&'`) is now the word the shell
    passes: it no longer hides the word after it (`find f '<' -execdir sh
    -c ... {} +` and `find . ! -name '<' -delete` were `observe`) nor splits
    the line (`grep ';' f` is one read-only command); a redirection that
    names no file (`cat <`, `ls > ;`) is the worst case. A command whose
    first word holds a blank or a slash (a quoted `"git status"`, which
    bash runs as the program of that name) is on no list: the worst case. A git read
    also gets the worst case in a repository with submodules (`modules/` in
    its git directory, or a gitlink in its index: a read that looks into a
    submodule fetches into its object store), and every git command the
    classifier would let pass (a read, `git stash create`, a restore) where
    the git directory git finds is not one git made for a work tree (a
    directory a repository ships holding `HEAD`, `objects/` and `refs/`,
    whose `config` names programs git runs):
    `ToolCapabilityMapper.git_dir_may_be_content` is the new lookup beside
    `git_may_fetch`. The adapter's own git commands run with
    `core.fsmonitor` and hooks turned off and fetch nothing, and the
    tracker reads no state file in such a git directory. Security round 3:
    a git read, and a restore, also get the worst case where the
    repository's own configuration (local and worktree scopes, with what
    they include) names a program git runs (a `core.fsmonitor` other than
    a boolean, a diff driver, a filter, a merge driver, a signature
    program, a pager) or its hooks hold `post-index-change`, as a project
    delivered with its `.git` can; `git stash create` there is `checkpoint`
    with the worst case beside it (take the first checkpoint with
    `create_checkpoint`). `ToolCapabilityMapper.git_config_may_run` is the
    new lookup. The recorder's clean-tree check turns those filters off.
    `printf` with an option (`printf -v NAME`, which sets a shell variable
    the later commands of the line run with), or with a word bash expands,
    is the worst case, where a line of read-only commands could run code
    as `observe`. Security round 3, batch 2: a class narrower than the
    worst case now comes only from the command's program (its first word as
    the shell passes it), never from text in an argument: `curl URL -A 'git
    reset'`, `bash -c '...' x 'git clean'` and `node x.js 'docker rm'` were
    `mutate` alone, so a destination policy let them through; a read-only
    command whose argument holds such text (`grep 'git reset' f`) now
    observes. `sed -i` (GNU sed's `e` command runs one) and `docker
    rm|rmi|prune` (the daemon `DOCKER_HOST` names receives the request) get
    the worst case. A local git change (`git reset`, `git checkout --`,
    `git clean`, `git branch -d`, `git stash ...`) gets it in a partial clone
    or a repository with submodules (`git reset` fetched the objects it
    lacked), and where the repository's configuration names a program or
    its hooks hold `post-index-change`, `reference-transaction` or
    `post-checkout` (`ToolCapabilityMapper.git_change_may_run` is the new
    lookup); a recorded restore where the configuration names a program
    gets it too (it was `mutate`). Every worst case now holds `mutate`: an
    interpreter is `execute`, `mutate` and `send` (it was `execute` and
    `send`, found anywhere in the command), and `curl -X POST`, `ssh`,
    `scp` and `rsync` are `send` and `mutate` (they were `send`), so a
    profile's rule for `mutate` applies to them. A line with a character
    outside ASCII right before a backslash or another character bash treats
    specially (`|`, `{`, `}`, `[`, `]`, `;`, `<`, `>`, `?`, `@`, `^`, `~`),
    quoted or not, gets the worst case (in a GBK, GB18030, BIG5, Shift JIS
    or JOHAB locale bash reads that character as the other's second byte,
    so `ls ぁ\;touch f` is two commands and `find t1 -name ぁ|ls -o -delete`
    one find, which deletes; security round 4 added every character but
    the backslash, so `grep -E '日本|中国' f` now asks too), and so does
    `pip` with a word the shell expands (`pip show *` became `pip show
    --log=FILE`). Security round 4: so does a word with an unquoted `{`,
    then a `,` or `..`, then a `}`, in any order of braces between (bash
    closes a group only at a `}` after its first comma, so `sort {a},-o}x`
    is `sort a}x -ox`; a space Unicode has and bash does not split at, such
    as U+3000, no longer ends the word), a `{name}` word right before a
    redirection (`echo x {PATH}>/dev/null; ls` set `PATH` and ran the
    repository's `./10/ls`; `{name} >file`, with a blank, asks too), and
    `>&` before anything but ASCII digits (`>&١` writes a file named `١`).
  - MCP: a tool registered or served with no capability is no longer
    `execute`: it is unbound, the strictest case, and reported as W617 in
    `mapper.warnings`. Tool `metadata` may be a tool binding record
    (`capability`, `flags`, `additional_capabilities`, `invokes`,
    `approval`, `control`); the flat keys still work, and `capability` and
    `capability_id` that disagree are S303. An `invokes` name resolves only
    to a bound tool: one registered with no capability, or whose record did
    not load, is V107 (it resolved before), and so is a cycle through tools
    registered earlier (V105). Registering or loading a tool again loads
    again every composite that invokes it, transitively: the composite
    takes the tool's flags as they are now (it kept those it was loaded
    with), and one whose tool is now unbound is itself unbound (V107 in
    `mapper.diagnostics`). `register_binding` raises only for its own
    record's errors. Security round 3: the metadata is read as the record
    in full, so a member no record has (a misspelt `aproval`, `flag` or
    `capabilty`) is S303 and `create_grounded_mcp_server()` raises, where
    it was dropped and the tool loaded with what remained; a metadata
    `ontology` is now the record's (V109 if the adapter does not support
    it). Put vendor data under a key that starts with `x-`.
    `create_grounded_mcp_server()` now defaults to `require_layer=True`:
    each tool it serves refuses (R407) a call the adapter's layer did not
    allow, so a session whose options were not wrapped with
    `adapter.wrap_options()` cannot run them. Pass `require_layer=False`
    for the earlier behaviour (outside class SL). A control-only tool
    (`control: true`) is served as it is: it is never refused.
- Python SDK, tool calls: a `persist` call (`TodoWrite`, a tool bound to
  `persist`) or an `audit` call whose data holds a credential-shaped value
  (a key or token format, a credential assignment, a URL's userinfo
  password, an `Authorization` header's value), or, in JSON data, a value
  in a member named for a credential (`password`, `accessToken`,
  `Authorization`, ...) that redaction replaces and that is not a
  placeholder (`{"password": "correct horse battery staple"}`), is refused
  with F504 (Standard 1.2.0 §5.18.10, §6.7), also when the host's
  permission flow changes the call's arguments. The TypeScript package's
  `holdsCredential` and the memory stores apply the same rule. Redaction
  replaces, in such a member, a number and every string and number of a
  list or an object (a header's list of values), and an assignment to a
  longer name ending in a credential name with no separator
  (`PGPASSWORD=...`).
- Python SDK, tool calls: a composite's call asks for the strictest approval
  of its own and each binding it invokes, transitively (the most
  `min_approvers`, the shortest `expires`, a `role` one of them sets), since
  its approval covers their nested calls (Standard 1.2.0 §5.18.4): its
  `ToolMapping.approval` is that join. A composite that reaches a binding
  needing two approvers or a role is now refused with F502, as that binding
  is; one that reaches an `approval.expires` takes it.
- Python SDK and TypeScript package, redaction: the password of a URL's
  userinfo is now redacted whatever precedes the scheme's run of
  characters (`x_https://user:pw@host`), and every pattern reads a text in
  time in proportion to its length; the rest is redacted as before.
- Python SDK, TypeScript package and plugin, secrets given as pairs: a
  header or credential given as a name/value pair (an object whose `name`,
  `key` or `header` member, in any case, names a credential or a header that
  carries one: a HAR's `{"name": "Authorization", "value": ...}`, Postman,
  Kubernetes `env`) or as a two-element `[name, value]` array is redacted
  as a secret member is (its `value` member, its second element), and a
  `persist` or `audit` call whose data holds one is refused (F504,
  `secret_in_data`), as `{"Authorization": ...}` already was; a member
  named `cookies` (a HAR's) is a secret member. In text, the value after
  such a pair or tuple (`"Authorization", "value": "Basic ...`,
  `('Cookie', 'sid=...')`) is redacted, and refused when it is 8 or more
  characters mixing letters and digits (the plugin's `persist` and `audit`
  hooks too; a list of names is not a tuple).
- Python SDK, TypeScript package and plugin, credential forms (Standard
  1.2.0 §6.7): the redactors, the refusal rule (`holds_credential`,
  `holdsCredential`, the `persist` and `audit` hooks' scan) and so the
  runner, the stores and the binding also read a URL's userinfo with an
  empty user's name (`redis://:<password>@`), quotes escaped as JSON text
  inside a JSON string or a shell's double quotes escapes them
  (`{\"password\": \"...\"}`, also around a header pair or tuple), a
  command's user option (`curl -u user:<password>`, `-uuser:...`,
  `--user`, `-U`, `--proxy-user`, also as a list's items, as an
  exception's text quotes a command), an option named for a credential with
  its value after blanks (`--password <value>`, `--api-key <value>`, not
  another option), and `secret_key` (`SECRET_KEY`, `DJANGO_SECRET_KEY`) and
  `passphrase` as credential names. Redaction replaces them, and reads a
  quoted value in text (an assignment's, an option's, a quoted user
  option's password, a header pair's or tuple's) to its closing quote on
  its line, whitespace and all, so `"passphrase": "correct horse battery
  staple"` and a `Cookie` pair's later cookies are replaced whole, not to
  the first blank, `,` or `;`; a `persist` or
  `audit` call is refused (F504) for a user option's password of 8 or more
  characters mixing letters and digits (`docker run -u 1000:1000` passes)
  and for a credential option's value as for an assignment's. A registered
  secret is also replaced and refused JSON-escaped (once or twice, `/` as
  `\/` or not, non-ASCII as `\uXXXX` or not) and percent-encoded (each
  common encoding, upper- or lower-case hex): `encoded_forms` and
  `encodedForms` list the forms. `Redactor.add_secret` registers them all.
  A user option's name is read for at most 256 characters (a run such as
  `.-u.-u.-u...` was read again from each of its positions: 48 s for 200
  KB in Python), so a password after a longer name is not recognised.
  Security round 4 (batch 5): an `Authorization` or `Proxy-Authorization`
  header's credential is read after any scheme (`ApiKey`, `SSWS`, `Bot`,
  `Splunk`, `GenieKey`, `Key`, `AWS4-HMAC-SHA256`), where only the scheme
  word was replaced and the credential kept: redaction replaces the scheme
  and the next word on its line when the first word is not `Bearer`,
  `Basic`, `Token`, `Digest` or `Negotiate` (so a credential with no scheme
  takes the next word of its line with it, `Authorization: [REDACTED] the
  admin API`), and reads a quoted value or a header line quoted whole (`-H
  "Authorization: ..."`) to its closing quote; the refusal rule and the
  plugin's scan refuse a value of 8 or more characters mixing letters and
  digits after any scheme and spaces, also as a pair or tuple in text.
  OpenPGP private key blocks (`-----BEGIN PGP PRIVATE KEY BLOCK-----`) are
  redacted and refused as PEM keys are, and after a private key header
  with no end line the rest of the text is redacted (nothing was), so a
  log line or an excerpt that quotes a key loses the text after the
  header. In JSON data a number whose JSON text holds a registered secret
  (a PIN, a card number given as a number) is redacted whole and refused,
  as its string form is. The Python `MemoryStore` refuses data the refusal
  rule recognises whether or not redaction would change it (a private
  key's opening line alone was stored). The plugin's scan runs its `grep`
  and `sed` with `LC_ALL=C`, reading bytes as the pre-tool-use hook does,
  in the persist and audit skills' hooks too.
- Python SDK, TypeScript package and plugin, session cookies, other
  encoders' escapes, service tokens and the plugin's own keys (§6.7;
  security round 5, batch 6). A `Cookie` or `Set-Cookie` header in text is
  redacted whole (a header line to the end of its line, with a Set-Cookie
  line's attributes; a header line quoted whole or a quoted member to its
  closing quote), and so is curl's `-b`/`--cookie` value when it holds a
  cookie (a name and `=` in its first 64 characters); the refusal rule and
  the plugin's scan refuse such a cookie whose value is 8 or more token
  characters mixing letters and digits, where all three let it through as
  text. Redaction reads a quote written as its JSON escape (`\u0022`,
  `\u0027`, .NET), `=` as `\u003d` (Gson) and a URL's slashes as `\/`
  (PHP) in place, and starts a token right after an escaped quote; the
  refusal rule and the scan read a text with those escapes, and `&`'s,
  `<`'s, `>`'s and `+`'s, decoded. `encoded_forms` and `encodedForms` add
  the HTML-safe JSON forms of a registered value (Go's `encoding/json`,
  Gson, .NET; both hex cases, also escaped again), so their lists of a
  value holding `&<>'+="` or a backtick are longer. Stripe, Google, GitLab,
  npm, Vault and SendGrid tokens, a Slack webhook's path and a `.netrc`
  entry's password are redacted and refused, and an account, signing,
  encryption, HMAC or master key and `credential` join the credential names
  (in text and as JSON member names: `{"accountKey": ...}`,
  `{"credential": ...}` are now secret members, redacted and refused). The
  plugin's scan refuses `AUDIT_HMAC_KEY`'s value wherever it runs (a
  persist tool's data, the persist and audit skills, a logged tool's name),
  and the pre-tool-use hook the project's checkpoint key in a persist
  tool's data; a `TodoWrite` holding either was stored. The blanks after a
  quoted `Authorization:` header line's colon are read whole (40 KB of them
  with no closing quote took 67 s in Python). Redaction is broader: a word
  after `Cookie:` in prose is replaced to the end of its line.
- Python SDK and TypeScript package, where a token starts and signed URLs
  (§6.7). Redaction is broader: a prefix-shaped token (AWS key id, GitHub,
  Slack, `sk-`, Stripe, Google, GitLab, npm, Vault and SendGrid tokens,
  JWTs) is replaced wherever the character before it is not an ASCII letter
  or digit, after `_` too, so an MCP tool named `mcp__srv__ghp_...` is
  recorded as `mcp__srv__[REDACTED]` in the adapter's call records, audit
  records and diagnostics and in the binding's trace (it was kept); and a
  signed URL's signature (`X-Amz-Signature`, `X-Goog-Signature`, `sig`,
  `Signature` as a query parameter, percent-encoded or JSON-escaped) is
  replaced, so an `IdempotencyLog` file, an evidence store and a trace
  written now keep none. The refusal rule (`holds_credential`,
  `holdsCredential`) refuses `persist` and `audit` data holding a signed
  URL's signature (F504), and reads `sk-` only where a token starts, so
  text such as `feature/task-12345-update-readme-file` is no longer
  refused; the longer prefixes are refused as before, glued after a letter
  or digit too. The plugin's shell scan is unchanged.
- Python SDK and Standard Agents binding, evidence anchors that held a
  secret (Standard 1.2.0 §6.7): an anchor whose `ref`, `excerpt` or
  metadata redaction changed is kept with no `digest` and no
  `metadata.hash`, and its metadata says `digest_omitted: "secret"` (the
  Python evidence stores, `Redactor.redact_anchor`; the binding's trace,
  its notifications and `exportEvidence`), since the content it cites
  holds the secret and the redacted excerpt would show the text to check a
  guess against. An anchor with no secret keeps its digest. The TypeScript
  package exports `redactAnchor` and the Python `Redactor` gains
  `redact_anchor_data`, the same rule on an anchor's JSON form.
- Python SDK, coordination records (§6.7): `CoordinationAuditLog.record`
  redacts every value an event keeps, not only `details`: `intent` (an
  `audit` step's event intent or type), `evidence_refs` (a shared or
  delegated anchor's ref), the event type, the agent ids and the
  capability, so `CoordinationEvent`, `to_dict()` and the action record hold
  the redacted text; a query by an agent id or event type that held a
  secret matches the redacted one. `manual_override` (and
  `TrustModel.manual_override`) redacts its action record, its anchors kept
  as an evidence store keeps them, and takes an optional `redactor`.
- Python SDK, `WorkflowRunner` (§6.7): the runner redacts the `reason` of
  every `Error` it submits as well as its `message` (a string as text, any
  other value as JSON; a token is unchanged), so a `HostCannotServe` given
  free text, or a `reason` object, no longer reaches the trace and the
  snapshot as `reason_ignored` with a secret in it; and the `Error` it
  builds when the run refuses a host's response (whose account repeats the
  value refused) is redacted too. Security round 3: it also redacts the
  evidence anchors of an `Event` (the core copies them into a `receive` or
  `wait` step's output), anchors given as a tuple (they reach the core and
  the evidence store as a list), the `not_covered` items of a `RolledBack`
  and the reason given to `cancel` (the R408 message, the trace and the
  records hold the redacted reason). When the runner has a `redactor` of
  its own, it gives what it recognises to the host's `IdempotencyLog`,
  `CheckpointTracker` and `MemoryStore` and to its `memory` (a store on the
  shared default redactor gets one of its own), so the host's memory
  refuses a `persist` of a registered value. `IdempotencyLog`,
  `CheckpointTracker` and `MemoryStore` gain a `redactor` property, and
  `Redactor` gains `include(other)`. Security round 4: it also redacts a
  `Decision`'s `decision_id`, `decision`, `approvers` and
  `approver_identities` (the trace's `approval_decided`, the record's
  `approval` and an F502's reason held them as the host sent them) and an
  `Event`'s `principal` and `identity` (the received item's `sender` and
  `sender_identity`). Redaction can make two values one: approvers that
  differ only in a secret count once, and a `decision_id` that differs from
  one used before only in a secret is refused as used (F502). A checkpoint
  the host names by an id that holds a secret is refused, not redacted
  (the run gives the id back to roll back to): a `CreateCheckpoint`
  answered with one fails F501, a `checkpoint` step whose output names one
  fails R402. The executor's approval refusals no longer repeat the
  decision: `'<decision>' is not a decision` is now `the decision is none
  of approved, rejected or unavailable`, and `decision '<id>' was already
  used` is `the decision was already used` (the trace's `approval_decided`
  names both).
- Python SDK, `CheckpointTracker` (§5.18.8, §6.7): the tracker redacts
  every string it records, with its new `redactor` (the default patterns
  unless given; the adapter's tracker has the layer's redactor, so the
  host's `secret_values` too): a checkpoint's `reason`, its `scope` items
  and its `metadata`, the reason an execution boundary gives
  (`invalidated_by`) and the words that use one (`consumed_by`), in memory,
  in `tracker_state.json` and in the archive. A bound checkpoint tool's
  `reason` and `scope` are the model's words, which reached the state file
  as written. A snapshot store still captures the files the scope names as
  given; the checkpoint's recorded `scope` (and so `matches_scope` and
  `has_checkpoint_for_scope`) is the redacted one. Checkpoints a tracker
  wrote before keep what they hold: delete `tracker_state.json` and the
  archive once they are no longer needed.
- Python SDK, `IdempotencyLog` (§6.4, §6.7): the log keeps a `send`'s
  output as the runner submits it (its anchors redacted without their
  digest, `evidence_seen` rewritten to match) with every other secret its
  redactor recognises replaced (a receipt's `Authorization`, a URL's
  password), in its file and in memory; a replay answers with that output,
  not the one the effect returned. Entries a log wrote before keep what
  they hold: delete the file once its runs' keys are no longer needed.
- Python SDK, evidence: anchor metadata nested deeper than two levels is
  kept as its JSON text, redacted while its structure can still be read and
  whole (the 1 KB metadata limit replaces a value too large), not as the
  first 100 characters of its repr; a value with no JSON text (a reference
  cycle) becomes `"[unserializable]"`. A delegation anchor's `description`
  and the orchestration anchor's `task_goal` are kept whole, not cut at 100
  characters: a cut could keep part of a secret no redactor then
  recognises. Security round 4: so is an `inquire` step's
  `ambiguous_input`, in its anchor's metadata and its audit event (it was
  cut at 200 characters before the store and the log redacted it, keeping
  the start of a token cut there).
- Python SDK, evidence and logs (security round 4): `EvidenceStore.get`
  finds a record only by its id as written (`ev-1`), as
  `JsonlEvidenceStore.get` does; `ev-01` and `ev-١` (which `int()` read as
  1) find none. A line nested too deeply to parse (`[[[...`, which raised
  RecursionError) is an unreadable line: `JsonlEvidenceStore` skips and
  counts it, `IdempotencyLog` cuts it off as a torn last line and raises
  `ValueError` for one anywhere else, and the snapshot store keeps every
  object while a manifest is one. After the loop: whether the parser raises
  RecursionError there depends on the stack size (on a larger one it returns
  the nested lists), so a line or file that parses to anything but what its
  reader writes (a list, a number, a string, null, an object short of a
  member the reader needs) is read as one that does not parse: the
  checkpoint archive skips such a line (it raised AttributeError, and the
  archive could not be read), `IdempotencyLog` reads it as above, a
  `MemoryStore` file or a snapshot manifest that is not what the store
  writes is a `ValueError` (a manifest before a restore puts anything back;
  an entry's SHA-256 must be one, so it names no file outside the store).
  That includes a memory row whose time no date-time states (a recall
  raised OverflowError) or whose data persist would refuse (not I-JSON, or
  nested deeper than 100 levels: a recall raised RecursionError), and a
  manifest path capture never records (a NUL or a lone surrogate, which
  stopped a restore part way; an empty, `.` or `..` part) or an
  `expires_at` with no UTC offset (TypeError).
- Python SDK, the output contract of a tool's result (Standard 1.2.0
  §5.18.9, §5.18.10): an MCP tool bound to a capability, one that
  `create_grounded_mcp_server` serves or one of another server bound with
  `register_mcp_tool` or `load_bindings`, must return that capability's
  output as the I-JSON text of the output object, its one text content
  item, with every field the capability's output contract requires. The
  SDK's server delivers a result's content and `is_error` to the session,
  not its `structuredContent`, so the text is what is checked: a result
  that carries its output only as `structuredContent` is refused, and a
  `structuredContent` beside the text is not read. A result that does not
  carry the output (prose, a partial object, an integer beyond ±2^53, a
  confidence outside 0 to 1) fails the call that ran with R402, and the
  call's record is `failed` with R402: a served tool returns an error
  result whose text opens with `R402 EXECUTION_FAILED:`, and for another
  server's tool the PostToolUse hook replaces the result the session reads
  with that text (`updatedMCPToolOutput`). Such a call has failed: a
  `checkpoint` tool's call takes no checkpoint, and no call counts as a
  prerequisite that ran. A result is an error, passed on as before, only
  when its `is_error` is `True`; any other value is checked. Return the
  output's JSON text, or set `GroundedAgentConfig(check_outputs=False)`
  (outside class SL; the configuration's `config_sha256` then records it),
  which skips only this check: the grounding policies and a minimum
  confidence read the output the one text item carries. The check runs
  before the grounding policies and the profiles' minimum confidence, as
  the executor's does, and those apply to the output it read.
  `create_grounded_mcp_server` guards every tool with a callable `handler`,
  whatever its class, and refuses one without (`ValueError`, R407) unless
  `require_layer=False`.

**Python SDK: evidence, workflows and coordination.**

- Python SDK, evidence (Standard 1.2.0 §6.5, §6.6):
  - Anchor kinds are §6.5's: `tool_output` and `command` anchors are now
    `tool`, `mutation` and coordination anchors `record`. The old names are
    accepted with a `DeprecationWarning` (`kind` reads back the new one; a
    former `mutation` keeps its high priority), any other free kind becomes
    a vendor kind `x-...`, and a query by an old name (`get_by_kind("command")`)
    returns what it returned before, by ref prefix, with the warning; a query
    by a free kind (`get_by_kind("observation")`) is answered by its vendor
    kind (`x-observation`), with the warning.
    `get_for_capability_output()` warns: use `evidence_anchors_for()`, which
    returns §6.5 objects. An empty `ref` or a malformed `digest` is a
    `ValueError`, and `EvidenceAnchor.from_dict` refuses a `digest` of
    `null` too.
  - A store keeps a frozen copy of each anchor: assigning to an anchor read
    back from a store, or calling `mark_critical()` on it, raises
    `FrozenInstanceError`, and its metadata is read-only. Your own anchor is
    not frozen. `add_anchor` returns the record kept.
  - Record ids are never reused: `clear()` no longer resets the sequence,
    and the records it drops count in `info().removed`.
  - Evidence anchors no longer keep a tool's input (Fixed): v2.0.0 stored
    it in each anchor's `metadata["tool_input"]`; set
    `GroundedAgentConfig(evidence_include_tool_input=True)` to keep it.
  - Every store redacts what it keeps (§6.7). With
    `evidence_include_tool_input=True` a call's input is kept redacted, not
    as given; the collector keeps no `digest` of a response that holds a
    recognised secret.
  - `CoordinationAuditLog.record` redacts `details`; the runner redacts the
    message of every `Error` it submits; the adapter redacts its call
    records and refusal messages.
  - `GroundedAgentAdapter.create_checkpoint` records the checkpoint's anchor
    (`checkpoint:<id>`, kind `record`, capability `checkpoint`) in the
    adapter's evidence store: `len(evidence_store)` and `get_evidence()`
    count it, and subscribers are notified.
  - `OrchestrationRuntime.execute_workflow_step` returns the contracts'
    outputs, grounded in the record of the action (§6.5): `invoke` and
    `inquire` give `evidence_anchors` as §6.5 objects (were ref strings: read
    `anchor["ref"]`); `audit` gives `{ref: "audit:<audit_id>", kind:
    "record"}` and its `store`; `delegate` gains `evidence_anchors`; and
    `synchronize` gives `{synchronized, agreed_state, participants,
    evidence_anchors}` instead of the agreed state itself (read
    `output["agreed_state"]`).
- `WorkflowRunner`: `run` and `start` take `attendance=None` (the trigger's
  attendance, else attended, as before) and refuse a caller-given `run_id`
  the runner has already started (`RunStartError`): a `run_id` must be
  unique among the runs whose records or keys the host keeps (§5.19.2).
  `drive` is now a loop of `advance` turns: it sleeps until the run's
  wake-up time (`run.wake_at()`) instead of a deadline it computed, and
  calls `Host.withdraw` for an action the run timed out. `RunResult` gains
  `run_id`, `reason`, `checkpoint_id` and `run_record`.
- Coordination: the orchestrator's `audit` step returns the `audit`
  contract's output (`recorded`, `audit_id`, `record`, `timestamp`,
  `evidence_anchors`) instead of `{"audited": true}`, and records only the
  step's `event`, `context` and `retention`, the event under
  `details.event` of a record of the log's own (Standard 1.2.0 §6.4).
- Python SDK: `AgentDescriptor.identity()` refuses a `model_family` not
  written `[a-z][a-z0-9_-]*` (`ValueError`) and derives one from a
  `model_id` in its metadata; `DelegationProtocol.delegate()` refuses a task
  that does not fit the agent's declared `task_inputs`;
  `WorkflowEngine.effective_flags(step, workflow)` raises
  `UnboundedDelegation` for a delegate step of a 1.2 workflow that declares
  `agents` whose target manifests were not added. The orchestrator's
  `inquire` output gives questions as objects with `id`, `parameter` and
  `answer_type`, `inquiry_id`, and `ambiguity_analysis` as an object (it
  gave strings, against the contract). `_core.Run.start` and `restore` take
  `catalogs` and `agents`.
- Python SDK: `OASFAdapter.translate` raises `UnknownCapabilityError` (V101,
  with the closest id) for an entry that names a capability the ontology
  does not define; it logged a warning and translated the entry without it,
  so its `max_risk` and `requires_checkpoint` could be too low. Catch it
  where a mapping written against a later ontology may be loaded.
- Python SDK: `grounded_agency.trust.decay_factor` counts an age below zero
  as zero (it raised `ValueError`), and `TrustModel` reads its field
  authorities from `field_authority.fields`, refusing a malformed entry or
  an unknown tie-breaker. `_core.Run.start` and
  `Validator.validate` take `profiles`, which they apply;
  `GroundedAgentConfig(profiles=...)` needs `approval="ask"`.
- Python SDK: `SyncStrategy`, `Severity` and `StepStatus` are `StrEnum`s
  (Changed), so `str()` of a member is its value.
- Python SDK (Fixed): an evidence metadata key with a final newline is
  refused like any other key outside `[a-zA-Z_][a-zA-Z0-9_]*`, and a trust
  model's `half_life` written with digits other than ASCII ones is refused.
- Python SDK, workflow runner (Fixed; Standard 1.2.0 §6.5, §6.7): the runner
  redacts the evidence anchors of every `Output` it submits with its
  `redactor` (registered secrets included), as the evidence stores do, so
  an anchor whose `ref`, `excerpt` or metadata held a secret is kept in the
  run's state, outputs and snapshots with it replaced and without its
  `digest` (`metadata.digest_omitted: secret`). `evidence_seen` is
  rewritten to match: it lists an anchor's redacted `ref` when it listed the
  anchor's own, and when two anchors are one after redaction it lists
  neither unless it listed both (fail closed). A signed URL's signature
  (the `X-Amz-Signature`, `X-Goog-Signature`, `sig` or `Signature` query
  parameter) is a default pattern; a host that cites URLs signed another
  way adds a pattern (`Redactor(patterns=[*DEFAULT_PATTERNS, ...])`).

**Across components (validator, executor, Python SDK, binding).**

- An ontology whose capability contract keeps a `$ref` that names nothing,
  is cyclic or nests deeper than 12 is refused when it is loaded (it was
  kept silently): by the validator CLI, the executor and WebAssembly, and in
  Python by `_core.Validator`, `WorkflowEngine` and `GroundedAgentAdapter`,
  which now loads its ontology through the core as well. An adapter whose
  ontology is not at `<root>/schemas/` names the directory its `$ref`s are
  relative to with `GroundedAgentConfig(schema_root=...)`. A same-file
  `$ref` (`#<pointer>`) names a node of the ontology itself (§4.1.2).
- Domain profiles (Standard 1.2.0 §5.21) are now applied where they are
  given, and refused when malformed: a `checkpoint_policy` key must be a
  capability id or `"*"` (a label such as `before_send` is V101), the
  members of `risk_thresholds` and `evidence_policy` are closed (another is
  S303), and `required_anchor_types` lists anchor kinds. A third-party
  profile written for 1.1, which nothing applied, is refused where it is
  applied now: migrate it as the shipped profiles were (each to 2.0.0).
  `tools/validate_profiles.py` checks profiles with the core and fails on
  any diagnostic; its old helper functions are gone. A profile that sets a
  rule an implementation does not put in force is refused too, rather than
  applied without it (§5.21.4): the adapter, with `strict_mode=False`
  (which only logs a missing checkpoint), a `checkpoint_policy` that raises
  `requires_checkpoint`. A profile's grounding policy (`require_grounding`,
  every shipped profile's) and its `minimum_confidence` are applied: an
  output they cover that is not grounded fails with F505, one not confident
  enough with F504, in runs, in the adapter (on the outputs of every MCP
  tool bound to a capability, served or not) and in the binding. A member without
  an exact JSON form (an integer beyond 2^53) is S303. An unknown top-level
  profile member stays a warning (W604) and is now reported with the member
  meant: logged at WARNING by the Python layers, and passed by the
  binding's `bindingProfiles` to its `onWarning` (`console.warn` by
  default).
- Checkpoints, rollbacks, sends and memory (Standard 1.2.0 §4.4.1, §4.4.2,
  §4.5; RFC-0009):
  - Every `InvokeCapability` action carries `idempotency_key`
    (`<run_id>:<n>`, the same for every attempt of one pass), and the
    pass's action record carries it too. A host that keeps no keys can
    ignore it; a pending action restored from a state saved before it gets
    `<run_id>:<id>`.
  - A host or an applied profile that gives destination policies puts them
    in force: a `send` step whose destination one does not allow fails F504
    (`destination_not_allowed`) before approval or a checkpoint. A domain
    profile with `allowed_destinations` is no longer refused by the
    executor, `WorkflowRunner`, `GroundedAgentAdapter` or the Standard
    Agents binding: it is applied. `_core.Run.start(destinations=...)`,
    `WorkflowRunner.start/run(destinations=...)`,
    `GroundedAgentConfig(allowed_destinations=...)` and the binding's
    `configureLayer({destinations})` give the host's own; an invalid
    pattern is refused, and a `WorkflowRunner` policy given as a string
    rather than a list of patterns raises `TypeError`. While a policy is in
    force, `GroundedAgentAdapter` also refuses (F504) a call of an unbound
    tool, which it cannot tell sends or not, and of a composite whose
    `invokes` reach a binding that performs `send`, or an unbound tool: it
    does not see nested calls, so it cannot tell where they go. In the
    Standard Agents binding,
    the `allowed_destinations` of profiles given to a composite reach the
    sends its code invokes, at any depth. Security round 4: the adapter
    reads a binding's `destination` pointer as RFC 6901 and the binding
    reads it: an array index is ASCII digits with no leading zero, so
    `/to/01` and `/to/١` locate nothing and, under a policy, the call is
    refused (F504; the adapter took the element `int()` read).
  - A `persist` or `recall` step of a workflow that targets 1.2 and binds
    `scope` fails R402 (`unsupported_scope`) unless the output echoes the
    scope. Steps that do not bind it, and those of a 1.0 or 1.1 workflow
    (where `scope` is W616 and passed on), are unchanged.
  - `RolledBack` may carry `not_covered`, which the executor validates (a
    malformed one, `null` included, is refused), traces and records. An
    item's members other than `item`, `reason` and a string `detail` are
    ignored, not refused.
  - Validator: W624 (a 1.2 `rollback` step whose `restored` nothing
    checks), W625 (a 1.2 `send` approval whose `shows` hides its
    destination), W626 (an unknown literal memory scope), W614 for a
    literal `persist` `ttl` outside the duration grammar or zero, W603 for
    a reference to `persist`'s deprecated `timestamp` (read `stored_at`),
    and W616 for a 1.0 or 1.1 workflow that binds the memory `scope`.
  - Python SDK: `WorkflowRunner.run/advance/drive(save=...)` refuses a host
    whose `IdempotencyLog` is in memory (give it a path); a rollback by
    `Host` lists a send whose outcome is unknown as transmitted
    (`detail: "outcome unknown"`), and each entry the run's `persist` steps
    wrote since the checkpoint as `outside_scope` (`memory <scope>:<key>`),
    since no checkpoint captures the memory store; with a
    `MemoryStore`, a run's `run` scope ends with the run, in the host's
    store and in `WorkflowRunner(memory=...)`'s (so `cancel` without a host
    ends it too). `MemoryStore` stores and returns copies of values, and
    refuses (`unsupported_ttl`, nothing stored) a `ttl` that would end an
    entry after 9999-12-31T23:59:59.999Z, as the binding's `memoryTools`
    do; `Host` gives a `persist` with no `key` one derived from the pass's
    `idempotency_key`. `FileSnapshotStore` reads a scope item that names a
    directory (`src`, `src/`, `./src`, an absolute path under the root) as
    everything under it, lists an item outside the root in `excluded`,
    never captures or restores `.audit/`, reports a rollback pattern that
    names nothing captured as `not_captured` unless the checkpoint's scope
    covers it, and computes `verification` over everything the checkpoint
    captured; `GroundedAgentAdapter` and `WorkflowRunner` keep a file
    evidence store out of every checkpoint. `Host.__init__`
    takes keyword-only `memory`, `idempotency`, `session_id`, `user`,
    `project` and `protected_paths`; a subclass that calls
    `super().__init__(tracker)` is unaffected.
  - Plugin: the `checkpoint` skill takes a git checkpoint with a plain
    `git stash create` (and `HEAD` on a clean tree) instead of `git stash
    push`, which the safety layers count as a gated `mutate`; the
    `rollback` skill restores with `git restore`.

**Reference validator and executor.**

- Reference executor: the saved state of a run that deferred steps holds two
  more members (`ahead`, and `parked` for a nested run that ended deferred);
  a state with deferrals that an earlier version saved still restores, but
  cannot be resumed (`Run.resume` refuses it): cancel such a run and start a
  new one. The state of a run that never deferred holds neither.
- <a id="upgrade-snapshots"></a>Reference executor, host protocol (Standard 1.2.0 §5.19): snapshots are
  version 2. The terminal action is derived from the state rather than
  stored with copies of the records and outputs, every action carries
  `run_id`, and the state may hold the record mode and the chain heads of
  what a host took; version-1 snapshots still restore (a finished run's
  stored terminal action must equal the one derived; in a run still in
  progress, the records of its current steps and of its deferrals gain
  `run_id`, `frame`, `step`, `capability` and the checkpoint their pass
  used, and the records 1.1 settled keep their members). Actions and
  records gain members (`run_id`; on records `run_id`, `frame`, `step`,
  `capability`, `checkpoint_id`, `code`, `approval.decision_id`); code that
  compares whole actions or records must allow them. `_core.Run.next()`
  returns a fresh dict each time, `Run.tick` returns whether it changed the
  run, and `Run::next` in Rust returns an owned `Action`.
- Reference executor, starting a run (Standard 1.2.0 §11.5): the catalog's
  version header is a start member every caller states. `_core.Run.start`
  takes a required keyword-only `header`, the version the catalog's
  `# Standard version:` header declares or `None` for a catalog without
  one; a call without it raises `TypeError`. In Rust, `StartOptions` gains
  `header`, `records`, `profiles`, `grounding` and `destinations`, which
  every construction names. `WorkflowRunner` states the header itself.
- <a id="upgrade-failed-record"></a>Reference executor: an approved step that fails now has a `failed` record,
  with the step's code, from the moment it fails, before its failure modes
  run, and also when its failure mode's rollback or checkpoint then fails
  (F503, F501) or finds no checkpoint to roll back to; 1.1 left that record
  `approved` until its failure modes ended, or for good in those cases,
  which a cancellation would then turn into `cancelled` and which held back
  `take_records` for the rest of the run. A host that reads the records
  while a failure mode's checkpoint or rollback is pending sees `failed`
  where it saw `approved`. A record a resumed run reuses no longer keeps the
  `checkpoint_id` of an earlier pass. The 1.1 runtime fixtures
  `records_failure_rollback_fails` and `records_failure_nothing_to_roll_back`
  end this way: on the v2.0.0 executor both end with F503 and the step's
  record `approved`, without a code; now that record is `failed` with code
  R402.
- Validator: an `audit` step's literal `retention` outside the duration
  grammar is W614 (`P1Y` is not a duration: write `P365D` or `365d`); a
  1.1 workflow that uses `grounding@1` or F505 in `on_error` gets W616.
- Validator (every Standard version): W620 for a workflow name that is not
  an identifier or is `catalog`, a step `domain` that is not a domain id
  (`schemas/workflow_catalog.yaml`'s `plan-invalidation` is now
  `plan_invalidation`; rename yours the same way) and a literal model family
  outside `[a-z][a-z0-9_-]*`; W623 for a schedule trigger with `overlap:
  allow_all` on a workflow that exercises both capabilities of a
  `conflicts_with` pair. A top-level `catalog` mapping without `steps` is
  now the catalog's manifest, no longer a malformed workflow (S304).
  Diagnostics gain `location.path` (RFC 6901) and, in a catalog set,
  `location.catalog`; `column` counts code points (it counted bytes).
- Validator and executor, workflows that target 1.2: a `delegate` step
  that may act on the world unchecked is W621 and one with a computed agent
  and no `agents` is W622; an accepted `read_only` delegation whose host
  does not attest `effective.read_only` fails the step (R402), not retried.
  A delegation that binds `continues` and attests a fresh context, or
  returns the `task_id` it continues, fails (R402). An attested identity's
  `model_id` must equal `effective.model_id` (R402). An identity's
  `model_id` is a string, as `agent_identity_schema.yaml` 1.1.0 says: an
  identity whose `model_id` is not is malformed, so it refuses the run's
  start as the actor identity and fails what reports it, like an identity
  with a non-string `role`. Below 1.2 the executor reads no identity's
  `model_id`, as 1.1 did not (schema 1.0.0 does not define it).
- Validator, workflows that target 1.0 or 1.1: the workflow field `agents`
  and the `delegate` input `continues` are W616 where 1.1 reported W604
  (with no version, W605 alone); the executor still ignores `agents` and
  passes `continues` on unread there. A qualified `invoke` target
  (`<catalog id>/<name>` naming no workflow of the caller's catalog) is W616
  too, whatever catalogs are given. Every W616 about a step member (1.1
  features such as gate `phase` included) now carries the step's `step` and
  `capability` with `field` relative to the step (`gates[0].phase`, not
  `steps[0].gates[0].phase`), and is sorted with that step's findings; its
  code and `location.path` are unchanged.
- Executor, Python SDK, TypeScript package and binding (Fixed; Standard
  1.2.0 §6.7): a diagnostic repeats no text of a host's output. A grounding
  refusal (F505) names an anchor by its index and kind (`evidence_anchors[0]
  (kind 'url') cites a ref the host's evidence_seen does not list`), never
  by the `ref` it cites, which a presigned or signed URL makes a
  credential, and reached the trace, the run record and the snapshot; an
  `acs:` anchor's reference is not repeated either, nor a vendor kind. A
  confidence that is not a number from 0 to 1 (R402, F504
  `invalid_confidence`, F505) is named by its type (`the output's
  confidence (a string) ...`) unless it is a number, a boolean or null, and
  an `inference_method` outside the vocabulary is not repeated. Match on codes and
  reason tokens, not on these messages. `@synaptiai/acs-core` exports
  `shownValue`, how a diagnostic names such a value.

**Plugin: hooks and skills (released with plugin 3.0.0).**

- <a id="upgrade-renamed-skills"></a>**Breaking (plugin):** two composed skills take their directory names
  (Agent Skills requires `name` to equal the directory): the slash commands
  `/gap-analysis-workflow` and `/digital-twin-sync-workflow` become
  `/capability-gap-analysis` and `/digital-twin-sync-loop`. The plugin
  release that carries this is a MAJOR version (3.0.0). No workflow,
  ontology or schema changes. The `layer` frontmatter key is removed from
  the 13 skills that had it (the ontology gives a capability's layer).
- <a id="upgrade-strict-sandbox"></a>Plugin hooks (released with plugin 3.0.0, Changed): without Claude
  Code's strict sandbox, every Bash call needs a checkpoint and approval,
  read-only commands included, and `git stash create` and a restore are
  gated calls too, so no checkpoint can be taken through Bash and every
  gated call is refused with F501 until the sandbox is set up. The hook
  also refuses the agent's own edits to the settings files, so add the
  strict sandbox, the deny rules and the credential denials listed in
  `hooks/README.md` (The strict sandbox) to `~/.claude/settings.json`
  yourself, outside Claude Code, and start it again. The hook verifies them
  from the managed, user, project and local settings files; a project or
  local file that turns the sandbox off, excludes a command, widens what it
  can write or read, or names a command that runs outside it turns the
  relaxation off.
- <a id="upgrade-record-links"></a>Plugin hooks (released with plugin 3.0.0, Added): while a file under the
  git directory's `acs/` has a hard link outside the records, the
  PreToolUse hook blocks every call with F504, reads included; while a file
  of the project's records has one, it blocks every call it does not let
  pass outright. Remove the other link outside the session. The hook needs
  perl, or `find`, `awk` and a GNU or BSD `stat`, to count the links (R407
  without them, or when a directory of the records cannot be read).
- <a id="upgrade-jq-marker"></a>Plugin hooks (released with plugin 3.0.0): the PreToolUse hook reads only
  Claude Code's JSON payload and needs `jq`; anything else is blocked with
  R407, as is a failure of the hook. The checkpoint marker is used up by the
  gated call it authorises, so each such call needs its own; a successful
  `git stash create` writes the marker and the new Stop hook ends its
  validity when the turn ends. A marker whose validity ended unused (it
  expired, its turn ended, a newer one replaced it) is filed under
  `.claude/checkpoints/ended/`, as a used one is under `used/`. A read-only
  Bash command and `git stash list|show` need no marker, and `git stash
  pop|apply <commit>` needs none when a checkpoint recorded `<commit>` (the
  entry `<git dir>/acs/checkpoints/commits/<commit>` a successful `git stash
  create` writes in the project's git directory, one lookup however many
  checkpoints were taken) and the call runs in the project's repository;
  any other restore needs a marker like any write. The rollback
  skill's command hook refuses (F503) a `git stash pop|apply` that does not
  name such a commit, whatever `git stash list` holds; before, it refused a
  restore only when `git stash list` was empty. The rollback and send skills'
  command hooks open a refusal with its code and name (`F503
  ROLLBACK_FAILED:`, `F504 CONSTRAINT_VIOLATED:`, `R407
  SAFETY_CHECK_FAILED:`) in place of `BLOCK:`. The
  marker's `created_at` and `expires_at` must be whole seconds of at most 12
  digits, the first not in the future and the second at most 1800 seconds
  after it; otherwise the call is blocked with F501 and the marker removed. A
  gated call is answered `ask` with an F502 reason in the permission modes
  default, acceptEdits and plan, and blocked with F502 in the others;
  `ACS_HOOK_APPROVAL=off` leaves approval to Claude Code's permission rules.
  `ACS_CHECKPOINT_MAX_AGE` (seconds, at most 1800) sets the marker's expiry.
  Each audit line gains `recorded_by`. The composed skills take a checkpoint
  with `/checkpoint` instead of writing `.claude/checkpoint.ok`. The hook
  reads a Bash command's words as bash does (quotes removed), so a quoted or
  abbreviated option that writes (`"--output=x"`, `--outp`, `file --compi`)
  and a `git` or `file` command with an unquoted `*`, `?` or `[` need a
  marker. A Bash line over 4096 bytes is not read (a gated `mutate`), so
  the reading never runs past Claude Code's hook time limit, and the hooks
  read a command as bytes whatever the locale. `posttooluse_take_checkpoint.sh`
  writes no marker for a call run in the background or in another
  repository than the project's (the payload's `cwd`), for output that is
  neither a commit id nor empty, or for empty output while the project's
  tracked files or index differ from `HEAD`. The audit, checkpoint, persist, rollback, send and transform
  skills no longer append their own lines to `.audit/*-operations.log`: the
  plugin's log hook records every call in `.claude/audit.log`, as action
  records, and reports a line it cannot write. The send skill's command hook also refuses the
  rest of 127/8, 0/8, 169.254/16, IPv6 loopback, mapped, link-local and
  unique-local literals, and an IPv4 host in another form (`127.1`,
  `2130706433`, `0x7f000001`).
- Plugin hooks, fail-closed fixes (released with plugin 3.0.0):
  - <a id="upgrade-every-tool"></a>The PreToolUse hook is registered for every tool (matcher `*`), with
    `onFailure: "block"` and a 30-second `timeout`, so a run that fails,
    cannot start or times out blocks the call where Claude Code supports
    that setting. A tool the SDK mapper maps to a capability that needs
    neither a checkpoint nor approval (Read, Grep, Glob, WebFetch,
    TodoWrite, ...) still needs nothing; `Skill`, `Agent` and `Task` are
    `mutate` (a skill's embedded shell commands and a subagent's hooks and
    MCP servers run with no hook event; take a checkpoint before each, and
    each is asked for approval); every other tool, MCP tools,
    `Monitor`, `PowerShell` and `ExitWorktree` included, is now an unbound
    `mutate` (Standard 1.2.0 §5.18.2): take a checkpoint (`git stash
    create`) before each such call, which is asked for approval. Before,
    only Write, Edit, MultiEdit, NotebookEdit and Bash were checked.
  - A Bash command over 4096 bytes is gated before it is trimmed or read: a
    command padded with blanks (50,000 trailing ones took 44 seconds to
    trim) can no longer hold the hook past its time limit.
  - <a id="upgrade-earlier-checkpoints"></a>The commits a rollback may restore are entered in the project's git
    directory (`<git dir>/acs/checkpoints/commits/`), outside the work tree,
    and a restore must run in the project's repository: an entry or a
    marker a cloned repository ships no longer lets `git stash apply` run
    without a checkpoint or approval. Entries under
    `.claude/checkpoints/commits/` and the marker's `commit` no longer
    authorise a restore (checkpoints taken before the upgrade are restored
    as a gated `mutate`), and `git stash create` outside a git repository
    writes no marker for a commit. The rollback skill's hook reads the same
    entries. An entry holds the HMAC-SHA-256 of its commit under the
    project's checkpoint key (`<git dir>/acs/checkpoints/key`, drawn at
    random by the take hook, which needs `openssl` to enter a commit), so a
    file a command creates there is no entry; an empty entry written before
    the upgrade restores nothing (it is a gated `mutate`), and nothing is
    entered in a git directory git did not make for a work tree.
  - A marker git tracks authorises nothing (F501; it is left in place:
    remove it from the repository), nor does one in a directory whose git
    directory git did not make for a work tree (a repository can ship
    `.claude` as a git directory), nor one git cannot answer for. A gated
    call whose path, Bash, Monitor or PowerShell command, or Skill
    arguments, names the layer's records (`checkpoint.ok`,
    `.claude/checkpoints`, `acs/checkpoints`) is refused with F504, in any
    spelling a path accepts: any letter case, a run of slashes, `./`
    segments and (in a text of at most 4096 bytes) `x/../`, and through a
    symbolic link on a path one of its words names. Security round 3: the
    hook also reads every string and member name of any other tool's input
    but Agent's and Task's (an MCP filesystem server's path, an MCP shell
    server's command), a `~` the shell expands (`~+`, `~user`; `~-` and
    `~N` are refused outright), a path attached to a short option
    (`-tdir`), and the command a quoted word holds (`sh -c '...'`); a call
    that names the directory holding the records (the project's `.claude`,
    the git directory's `acs/`: `rm -rf .claude`, `mv .claude x`) is
    refused too, as is a call with more than 65536 bytes of strings of at
    most 4096 bytes. A commit message or an MCP text that names
    `.claude` as a word, or a record's name, is refused: write it otherwise.
    Security round 4: the hook expands brace groups and decodes `$'...'` as
    bash does (`{fixtures/,.git/acs/check}points`,
    `$'.claude/checkpoint\x2eok'` are refused), and refuses (F504) a call
    with more than 4096 strings and member names (empty ones included),
    brace expansions that make more than 8192 words, or more than 262144
    bytes of paths to resolve; of a long cluster of short options it reads
    only the texts whose first component exists, or that are absolute.
    Security round 4, batch 2: it finds a brace group as bash does (the
    first `{` a `}` closes, at the first `}` after a comma at its own level:
    `{a},.claude/check}point.ok` names the marker and is refused; it paired
    each `}` with the nearest `{`), and refuses (F504) a call whose brace
    expansions read more than 65536 braces, commas and characters. The
    audit and send skills' hooks read brace groups the same way
    (`env {-u},cu{r,r}l} ...` runs curl; `tee -a .cl{x},a}ude/...` appends
    to the audit records). After the loop: bash 5.3 expands a group with no
    comma at its own level that is no sequence otherwise than bash 5.2
    (`{a..b{c,d}}` is `a..bc a..bd` to 5.2, `{a..bc} {a..bd}` to 5.3), and
    the hooks run under whichever bash the user has, so the guard and the
    audit and send skills' hooks read each word as both versions expand it
    (`touch {x..y{a..b}}/key`, through a shipped link `{x..ya}` to the git
    directory's `acs/checkpoints/`, writes the key on bash 5.3 and is
    refused). That one word is all of bash 5.3's seen (on a runner, without
    its source), and two readings give it: the `{` kept and all after it
    expanded, or the group's braces kept around the words of its text; the
    readers give the words of both (`touch {{..c}..{}{{b..b}}},}/key`
    through a link `{{..c}..{}{b}},}` is refused), and
    `tests/brace_readings.py` holds words that tell them apart, which a
    runner with bash 5.3 checks. The readers merge the readings' words in
    bash, with no process started (the guard ran `sort` for each word, a
    process no budget counted). A sequence takes a sign and an increment
    of any length, as bash does (`.cl{a..a..+1}ude` and
    `.cl{a..a..1000000000}ude` are `.claude`; both were kept as written);
    one with a number of more than 9 digits (an increment of more than 18),
    leading zeros aside, is not read and the call is refused (bash 5.2
    prints a zero-padded one as a 32-bit number).
  - The audit, persist, rollback and send skills' command hooks set
    `onFailure: block` and a 30-second `timeout`, as the PreToolUse hook
    does: a check that fails or gives no verdict in time blocks the call
    where it let the call run. The audit hook reads its append form in time
    that grows with the line alone (a 100 KB record with no closing quote
    took 15 seconds, and about 700 KB outlived Claude Code's default
    timeout).
  - A marker older than `ACS_CHECKPOINT_MAX_AGE` (the setting in force when
    it is used, which every audit line records) authorises nothing, whoever
    wrote it with whatever expiry.
  - The send skill's command hook reads a command that names `curl`, `wget`
    or `http` (or `.curlrc`, `.wgetrc`, `/etc/hosts`, `/dev/tcp`) in any
    quoting, as the shell passes its words, and each request as the tool
    reads it. It now also refuses an internal host with no scheme
    (`curl 127.1:18777`), after one slash (`http:/127.0.0.1`), under
    `.localhost`, in `100.64/10` or `localhost.localdomain`; a host it
    cannot read (percent-encoded, non-ASCII, curl's `[1-2]` or `{a,b}`
    globbing); a quoted, abbreviated or variant option that redirects the
    connection (`-''x`, `--resol`, `--proxy1.0`, wget's `--exe=`), curl's
    `--variable`/`--expand-*`, git's `-c http.*`/`-c url.*`; a variable set
    on the line or `CURL_HOME`, `HOME`, `XDG_CONFIG_HOME`, `WGETRC` or a
    proxy exported; a request inside `sh -c` or an interpreter's code; an
    unquoted brace, a glob before a URL's path, an unclosed quote or a
    here-document; and such a command over 16384 bytes (send a payload
    from a file, `-d @file`). An IPv6 host's brackets must be quoted
    (`curl 'http://[2001:db8::1]/'`).
  - The audit skill's hooks: a record whose JSON gives a member name twice
    is refused (I-JSON); a command that may name the records file (it names
    `records`, `jsonl`, `audit` or `.claude` in any quoting, runs under
    `.claude`, or holds a glob that may match the file) and is not the one
    append form may not redirect output to a file, run a program but a few
    that only read (`cat`, `jq`, `tail`, `wc`, ...; `mkdir`; `openssl dgst`;
    `mv` only to move the file aside), substitute a command or a process,
    or set `PATH`, `LD_*` or `OPENSSL_*`; and a new hook on Edit, Write,
    MultiEdit and NotebookEdit refuses an edit of the records file or of
    another file under `.claude/audit/`, links followed. Compute the HMAC
    in a command of its own.
  - Skill hooks, security round 2 (they stay registered for the rest of
    the session once the skill ran): the send skill's hook now refuses, in
    every command, a word a glob or a brace may expand to `curl`, `wget`
    or `http` (`/usr/bin/c?rl`, `cu{r,r}l`; `ls /usr/bin/c*` too), and
    reads a command holding `$'...'`, `$"..."` or a `/dev/` path the shell
    expands; in a command that names a request tool it refuses code piped
    or redirected to a shell or an interpreter (`curl .../install.sh | sh`,
    `| python3`; `| python3 -m json.tool` and `| python3 -c '...'` still
    run), a request inside a word of any program that runs one (`trap`,
    `awk`, `sed`, `find -exec`, `git rebase -x`, `env -S`, ...), `xargs` or
    `parallel` feeding the tool, a copy or a link of it, a git setting
    outside `user.*`, `color.*`, `advice.*`, `init.defaultbranch`,
    `core.quotepath`, `i18n.*`, `column.*` and `log.*` (`-c` or `git
    config`), and a word naming a proxy, CA-bundle, resolver, git
    (`GIT_*`) or loader (`LD_*`) variable, or `HOME`, `PATH`, `ENV`, `IFS`,
    with or without a value (`for http_proxy in`, `read`, `printf -v`).
    The audit skill's hook now refuses, in every command, a program that
    writes files its input names (`patch`, `git apply`/`am`, `tar` but to
    create or list with short options, `unzip` but to list, `cpio`,
    `rsync`, `7z`, git's index and tree plumbing, a git alias, `find
    -exec` or `xargs` running a program other than its readers), and reads
    a brace expansion, a glob that may name `.claude` or `.claude/audit`,
    and a redirection to a name the shell builds (`>> $A$B`) as it reads a
    command naming the records file. The rollback skill's hook reads the
    command's words as the shell passes them and allows a restore only as
    `git stash apply|pop <recorded id>`, those four words alone: `git -C .
    stash apply`, `env git stash ...`, `git stash branch` and a restore in
    `sh -c` are refused with F503 (the plugin's hook gated them as
    `mutate` already).
  - Skill hooks, security round 3. The shared word reader pairs quotes as
    bash does (a backslash escapes the next character, in double quotes
    and `$'...'` too; a line continuation is removed, also inside an
    operator and before a comment), so an escaped quote no longer hides
    the commands after it, and each hook's first reading removes line
    breaks (`cu\<newline>rl`, `sta\<newline>sh`). The audit skill's hook
    reads in full a command holding `$'...'` or `$"..."` and refuses it
    there; `mv` moves only the project's records file aside in
    `<project>/.claude/audit` (any other directory, `..`, `~` or an
    expansion is refused); and it now refuses, in every command, `gunzip`
    and its kin with `-N`, `curl` unless run as `curl -q` without `-J`,
    `-K` or `--variable`, `wget` unless run with `--no-config` and without
    `-r`, `-m`, `-p`, `-x`, `-i` or `--content-disposition`, HTTPie,
    `aria2c`, `dpkg -x|-i`, `rpm -i`, `python -m zipfile|tarfile`, and any
    git command that is not one of git's own (an alias from a
    configuration file): run `curl -q ...` and `wget --no-config ...` once
    the audit skill ran. The send skill's hook now runs `curl` only with
    `-q` first and `wget` only with `--no-config` (their configuration
    files may set a proxy), HTTPie only where its configuration file sets
    no default options, and no `ipfs://` URL; refuses, in every command, a
    glob or a brace that may name `.curlrc`, `.wgetrc`, `/etc/hosts`,
    `resolv.conf`, `~/.ipfs/gateway` or HTTPie's `config.json`, and a word
    naming `IPFS_GATEWAY`, `IPFS_PATH`, `SYSTEM_WGETRC` or
    `HTTPIE_CONFIG_DIR`; and a new hook on Edit, Write, MultiEdit and
    NotebookEdit refuses an edit of those files.
  - Skill hooks, security round 4. The shared word reader reads an
    unquoted extglob opener (`@(`, `!(`, `+(`, `*(`, `?(`), which bash
    expands as a pattern once a command has run `shopt -s extglob`, as text
    it cannot read: the audit, rollback and send skills' hooks refuse such
    a command (in the send skill's case, any command that holds one). The
    send skill's hook applies the `curl -q`/`wget --no-config` rule and the
    copy rule wherever the tool runs: after `!`, `if`, `while`, `until` or
    `coproc`, and after any program; it runs a tool only as the command's
    program or after a program that runs the one a later word names (`env`,
    `sudo`, `timeout 5`, `nice -n 10`, ...) with only options and numbers
    between, and refuses one given to another program (`prlimit curl`,
    `setpriv`, a loader, `head -c ... /usr/bin/curl`, `git grep curl`;
    `which curl`, `echo curl` and `apt-get install curl` still run); it
    counts wget's `--no-config` only where wget reads it as an option (not
    as `-O --no-config`, not after `--`) and reads every word after `--` as
    a URL; it refuses `alias`, `hash`, `enable` and a word naming
    `BASH_ALIASES` or `BASH_CMDS` in a command that names a tool, a command
    line in a word that runs the tool by its path or names it as a value
    (`sh -c '/usr/bin/curl ...'`, `eval 'alias g=curl'`), and a glob that
    may expand to a tool's name in any letter case (`shopt -s nocaseglob`)
    or, where the command may turn on dotglob (`shopt`, `GLOBIGNORE`, a
    sourced file), to a setting file by a leading dot. The audit skill's
    hook now refuses, in every command, a recursive copy (`cp -r`, `-R` or
    `-a`, `scp`, `rclone`, `sftp`, `lftp`), every git command but git's
    reads and those that write no file from a commit (`checkout` and
    `restore` only of literal paths after `--` that do not hold the
    records, `reset` only `--soft` or `--mixed`, `stash` only `list`,
    `show`, `create`, `store`, `drop` or `clear`; `switch`, `merge`,
    `pull`, `rebase`, `cherry-pick`, `revert`, `clone`, `worktree`,
    `submodule` and the like are refused once the audit skill ran), `wget`
    unless `--no-config` is its first word, and a writer after `!`, `if`
    or `while` or after any program it does not read with a rule of its
    own (`setpriv patch`, `runcon tar`); a here-document's body is read as
    commands, with the old rule where a reader takes it as data (`cat
    <<'EOF' > notes.md`, a commit message), and a command whose data body
    holds a line continuation or ends at a delimiter other than a plain
    word is refused. The rollback skill's hook reads a command holding a
    glob or a brace too, and refuses one that may spell `git stash
    apply|pop` (`git st?sh apply <id>` once a file named `stash` exists;
    `git add *` is refused, `git add *.py` still runs).
  - Skill hooks, security round 4 (batch 4). The audit skill's hook
    refuses a record holding a value under a member named for a credential
    (`{"password":"hunter2"}`, `{"token":4111111111111111}`, a value in an
    array, one with blanks, the value of a `{"name": "Authorization",
    "value": ...}` pair, the second of a `["Cookie", ...]` tuple), as the
    plugin's pre-tool-use hook refuses the same data from a persist tool
    and the SDK redactor reads it (`hooks/secret_member.jq`, copied into
    both): write such a record by reference (`<ref>`) or digest. The send
    skill's hook reads every word naming a tool after a wrapper as a
    request's program (a wrapper's option may take a tool's name as its
    value: in `env -u http curl ...` and `sudo -u http curl ...` curl runs,
    and its words were read with HTTPie's grammar), so each reading must
    pass; such a value may stand between the wrapper and the tool, and a
    command with more than 8 such words after a wrapper is refused.
  - The boundary hook (`stop_end_checkpoints.sh`) also runs on StopFailure,
    UserPromptSubmit, SessionStart and SessionEnd: a marker a turn left
    when an API error or an interrupt ended it, or a killed session, no
    longer carries into the next turn. The hooks' scope, the project
    directory with every session in it, is stated in SECURITY.md §5.5.
  - The log hook reports (exit 1) input `jq` cannot parse, which may be a
    tool call (nested past jq's depth limit, a lone surrogate escape), where
    it exited 0 with nothing logged; input that is not JSON at all is
    reported the same way. The limit is the installed jq's (1.7: 256
    levels; 1.8: 10 000): a call the jq on `PATH` parses is logged. Its
    input digest is taken only over text that is JSON: jq prints a value
    nested past 256 levels as `<skipped: too deep>`, so a tool input that a
    jq parses but cannot print (the CI runner's jq parses 300 levels) is
    logged with the digest `unavailable` (reported, as any digest the hook
    cannot compute), never with a digest of the cut text.
  - A git command on the read-only list (`git status`, `git log`, `git
    show`, `git diff`, `git rev-parse`, `git ls-files`, `git stash
    list|show`) is a gated `mutate` when the call's directory (the payload's
    `cwd`) is in a partial clone, or git cannot say: there git fetches what
    a read lacks from the promisor remote, sending the object id the command
    names. `git stash create` still takes a checkpoint there. The same in a
    repository with submodules (`modules/` in its git directory, or a
    gitlink in its index). Every git command the hook would let pass (a
    read, `git stash create`, a restore) is `mutate` where the git
    directory git finds is not one git made for a work tree (a directory a
    repository ships holding `HEAD`, `objects/` and `refs/`, whose `config`
    names programs git runs). The hooks' own git commands run with
    `core.fsmonitor` and hooks turned off and fetch nothing. Security round
    3: the same where the repository's own configuration (the local and
    worktree scopes, with what they include) names a program git runs (a
    `core.fsmonitor` other than `true` or `false`, a diff driver's
    `textconv` or `command`, `diff.external`, a filter, a merge driver, a
    signature program, a pager) or its hooks directory holds
    `post-index-change`: a git read and a recorded restore are a gated
    `mutate`, and `git stash create` is put to a person with no marker
    asked for (F502 in `bypassPermissions` or `dontAsk` unless
    `ACS_HOOK_APPROVAL=off`). A project that sets such a program itself
    (git-lfs or git-crypt installed with `--local`, a watchman fsmonitor)
    gets these prompts; set it in the global configuration instead. The
    take hook's clean-tree check turns the repository's own filters off. A
    Bash `printf` with an option (`printf -v NAME`) is a gated `mutate`.
  - <a id="upgrade-project-env"></a>The hooks' settings (`ACS_HOOK_APPROVAL`, `ACS_CHECKPOINT_MAX_AGE`,
    `AUDIT_HMAC_KEY`, `AUDIT_LOCK_WAIT`) belong in `~/.claude/settings.json`,
    managed settings or the environment Claude Code starts in. While the
    project's `.claude/settings.json` or `.claude/settings.local.json` names
    one of them in `env` (any letter case), or cannot be read, the
    PreToolUse hook blocks every call with R407, the log hook writes no line
    and the checkpoint hook writes no marker: Claude Code applies a
    project's `env`, which is repository content, to every hook over the
    user's settings, so a cloned repository could set
    `ACS_HOOK_APPROVAL=off` or an audit key it knows. Move such an entry out
    of the project's files (Claude Code started in the home directory reads
    `~/.claude/settings.json` as the project's too: there, set them in the
    environment).
  - The same holds for every variable those files set in `env` but Claude
    Code's own settings (`ANTHROPIC_*`, `OTEL_*`, `MAX_THINKING_TOKENS`,
    `MCP_TIMEOUT`, `BASH_DEFAULT_TIMEOUT_MS` and the few more
    `hooks/README.md` lists, as written): Claude Code applies that env to
    every hook and every command it runs, and `BASH_ENV`, `SHELLOPTS`,
    `PATH`, `HOME`, `LD_PRELOAD`, `GIT_CONFIG_*`, a proxy or an exported
    function changes what a hook, or a command it lets pass, runs. A
    project whose settings set, say, `NODE_ENV` or `PATH` now has every
    call blocked with R407 until the entry moves to
    `~/.claude/settings.json`, managed settings or the environment. The
    hook scripts open with `#!/bin/sh` and start themselves under
    `bash -p` (so `bash` must be on `PATH`, as before); the three that
    read a setting drop relative and project directories from their own
    `PATH`, and run `jq` with no `HOME`.
  - A Bash command whose first word holds a blank or a slash (a quoted
    `"git status"`, which bash runs as the program of that name) is a gated
    `mutate`, not a read-only list entry.
  - Security round 5. A command on the read-only list, `git stash create`
    and a recorded restore are a gated `mutate` where the program bash finds
    for the first word on the `PATH` Claude Code gives the hook may be the
    repository's own: found under an empty or relative entry
    (`PATH=node_modules/.bin:$PATH`, a leading colon), in a file in the
    project (links followed: an activated virtual environment, direnv's
    `PATH_add`; not where the project is the home directory, or holds it),
    or nowhere. A project whose `PATH` holds such an entry gets a checkpoint
    and an approval for `ls` or `git status` only where that entry has a
    file of that name. Each git command the hooks run, and each read of a
    project settings file, stops after 5 seconds (a repository's
    configuration can include a FIFO or `/dev/ptmx`, which held the hook
    past its 30-second limit): a call whose project or marker git directory
    git cannot name in time is blocked (R407, F501), a git read or
    checkpoint there is a gated `mutate`, the take hook writes no marker
    and the log hook writes its line without the anchor and says why; a
    settings file that is not a regular file is unreadable (R407). The
    records guard compares every path it resolves however many there are
    (past about 64 KB of them, a match was read as none), follows a link
    to a name that ends in a line break to that name, and reads the call's
    `cwd` and git's answers exactly; the persist, audit, send and rollback
    skills' hooks read a `file_path`, a `cwd` and a link target exactly
    too.
  - Security round 5, batch 2. A restore of a recorded checkpoint (`git
    stash pop|apply <commit>`) is a gated `mutate` (a marker and approval),
    not a rollback, wherever any scope, the user's included, configures a
    filter's `smudge` or `process` command: git-lfs's, which `git lfs
    install` writes to the user's configuration, asks the LFS server the
    repository's `.lfsconfig` names for each object its store lacks,
    sending the object's id. The two commands `git lfs install
    --skip-smudge` writes count as none. The log hook writes a tool's name
    (`tool`, `intent`) and a `Skill` call's skill name (`details.skill`)
    only when it is plain (1 to 128 ASCII letters, digits, `.`, `_`, `:`
    or `-`) and the plugin's secret scan finds no credential in it, else
    `[REDACTED]`: the model chooses a skill's name, and the line is signed,
    so a secret in it could not be taken out. The pre-tool-use hook's
    refusals and approval requests name the tool the same way.
  - Security round 5, batch 3. The take hook writes no checkpoint marker
    for a `git stash create` the pre-tool-use hook classified the worst
    case where it ran (a `git` on `PATH` that may be the repository's, or a
    git directory git did not make for a work tree: a shipped
    `vendor/evil.git` whose `core.worktree` is the project stashed into its
    own object store), nor for one run with another git directory than the
    project's. The send, audit and rollback skills' hooks read a glob's
    bracket expressions as bash does (`cur[[:alpha:]]`, `cur[]l]`,
    `.cl[a-z]ude`, `git st[[:alpha:]]sh` are now refused; a set bash cannot
    be read exactly makes the run any run). The audit skill's hook refuses
    `printf` with an option (`printf -v NAME` sets a variable for the rest
    of the line) and a word that names `PATH`, `IFS`, `ENV`, `BASH_ENV`,
    `CDPATH`, `BASH_CMDS`, `BASH_ALIASES`, `LD_*`, `DYLD_*` or `OPENSSL_*`
    in a command it reads; the rollback skill's hook refuses a recorded
    restore beside a command that does more than read (`printf -v PATH ...;
    git stash apply <sha>`, `cd`, `alias`, a function, a file written):
    restore on a line of its own, or after `git status` and other reads.
  - Security round 5, batch 4. The shared secret scan reads a text line by
    line and again with its line breaks read as blanks, as the SDK's and the
    TypeScript rules do, so a value on the line after its name
    (`password:` then the value, a YAML value indented under its key,
    `Authorization:` or `Bearer` then the token) is now refused: in what
    `TodoWrite`, `TaskCreate` and `TaskUpdate` store (each string read on
    its own), in an audit record and in what the persist skill writes. The
    persist skill's hook also refuses an edit that builds a credential with
    the lines around it (a value put under a name the file holds, a name put
    over a value, a line taken out from between them: the changed lines and
    six lines that are not blank on each side are compared before and after
    the call), and any change to a line of a private key block (from its
    BEGIN line to its END line, or the end of the file), such as a key's
    body put into a template. The send skill's hook reads curl's `--url`
    value as a URL (`--url=VALUE` too) and refuses an operand or a `--url`
    value that starts with `@` (curl 8.13 and later reads URLs from that
    file; pass the URLs on the command line), and refuses `/etc/hosts` and
    the other files that set where a request goes in any spelling
    (`/etc//hosts`, `/etc/./hosts`, a `..` segment) and by their last
    component where the command may change the directory (`cd /etc && ...
    >> hosts`, `curl --output-dir /etc -o hosts`, `wget -P /etc
    .../hosts`); its Edit/Write hook refuses a path with a `..` segment
    whose last component is such a file's. The audit skill's hook refuses
    curl's URLs read from a file (`--url @file`, an `@file` operand), whose
    file names curl takes from them.
- Plugin audit log: `.claude/audit.log` now holds one JSON line per tool
  call, an action record (Standard 1.2.0 §6.4): `action_id`, `timestamp`,
  `actor`, `intent`, `status`, `tool`, `call_id`, `details` (`event`,
  `skill`, `input_sha256`: a digest of the input in place of the input),
  `recorded_by`, `prev_hmac`, `hmac`. `tools/verify_audit_log.py` verifies
  old and new lines in one chain, so logs that mix them still verify. The hook now reports, as a non-blocking error
  (exit 1, the reason on standard error), every call it does not log or
  cannot sign: no `jq`, a symlinked log, no `openssl` (it no longer writes a
  line with `hmac: "no-hmac-available"`, which broke the chain), a line that
  could not be built, an unreadable last line, an unavailable digest.
- <a id="upgrade-audit-head"></a>Plugin audit log, its end: the chain shows a changed or removed entry by
  the link of the entry after it, but not the removal of the last entries
  or of the whole log, which the hook's comment claimed it did. The hook now
  keeps the chain's end in `.claude/audit.head` (the number of entries and
  the last one's `hmac`, signed with the same key), and
  `tools/verify_audit_log.py` fails a log that no longer holds that entry at
  its place. The verifier reads the head beside the log (`--head-file`
  names another) and fails when there is none: verify a log begun before
  the hook kept a head, or the audit skill's `records.jsonl`, with
  `--no-head` (the chain alone). The hook reports, as a non-blocking error,
  a log that no longer holds its head's entry (it writes the line and keeps
  the head as the evidence: move `audit.log` and `audit.head` aside together
  to start a new log), a head another key signed, a log that had no head
  (anchored from then on, once) and a head that cannot be written. The
  pre-tool-use hook refuses a call that names `audit.head` (F504). The hook
  now also runs `mv`. Security round 3: in a git repository the hook keeps
  the same head, its anchor, in `<git dir>/acs/audit.head`, which `git
  clean -fdx` or `rm -rf .claude` leaves, so a log removed with its head
  is reported and fails verification; the verifier reads the anchor where
  it exists (`--anchor-file` names another). To start a new log, move
  `audit.log`, `audit.head` and the anchor aside together. Security round
  4: the head and the anchor do not show a cut made through the agent the
  log records (its commands read both without a checkpoint or approval, and
  the key from their environment, so an approved command that names
  neither can write back an earlier head, or sign a new one); the verifier
  gains `--witness PATH` (repeatable), a copy of the head kept where the
  agent cannot write it, which shows such a cut.
- <a id="upgrade-audit-records"></a>Audit skill: each line it appends to `.claude/audit/records.jsonl` is now
  an action record of its own (Standard 1.2.0 §6.4), with the event under
  `details.event`, the collected `audit_record`, `changes` and `provenance`
  under `details`, and `prev_hmac` and `hmac` under `AUDIT_HMAC_KEY` (the
  record is unsigned without it), so `tools/verify_audit_log.py --log-file
  .claude/audit/records.jsonl --no-head --hmac-key "$AUDIT_HMAC_KEY"`, run
  outside Claude Code, checks the file (no head anchors its end; without
  `--hmac-key` the verifier uses the key file when it exists, which did not
  sign these records). Lines an earlier version
  wrote (`audit_id`, `timestamp`, `event`, `context`, `retention`,
  `audit_record`, `changes`, `provenance`) carry no chain and do not verify:
  move an existing file aside and let the skill start a new one (it does so
  itself when the last line has no `hmac`), and read the old members under
  `details` in new lines.
- <a id="upgrade-audit-key"></a>Plugin audit log, its key: the log hook and `tools/verify_audit_log.py`
  read the HMAC key from `~/.config/acs/audit.key` when that file exists,
  else from `AUDIT_HMAC_KEY`, so the file wins when both are set. No key is
  derived from the host name. The file is used only when it is a regular
  file owned by the user, with mode 600 or 400, one link (a second hard
  link, made where the agent's commands can read, would expose the key),
  in a directory that is not a symbolic link and that group and others
  cannot write, and its first line is 32 to 4096 visible ASCII characters;
  the hook also refuses a key file inside the project directory, which the
  agent's commands may write. A file that fails one of these is refused,
  and `AUDIT_HMAC_KEY` is not used in its place. The hook computes the HMAC
  from SHA-256 with the key passed through pipes, so the key is on no
  command line. Without a key, or without `openssl`, the hook writes the
  line unsigned (`hmac` empty), leaves the head and the anchor as they are,
  and reports it (exit 1, a non-blocking error); the verifier reports each
  unsigned line, and with no key runs no check (exit 2). The key file is
  meant to be out of reach of the agent's commands, so the audit skill,
  which signs through them, signs its records under `AUDIT_HMAC_KEY` and
  writes them unsigned without it. Create the key file (`set -C` keeps an
  existing key):
  ```bash
  mkdir -p ~/.config/acs && chmod 700 ~/.config/acs
  (umask 077; set -C; head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > ~/.config/acs/audit.key)
  ```
  Then deny the agent both reading and writing it, in user settings, with
  literal absolute paths: `permissions.deny` `Read(//<key file>)`,
  `Edit(//<key file>)` and `Edit(//<key directory>/**)`, a
  `sandbox.credentials.files` deny entry for the key file, and
  `sandbox.filesystem.denyWrite` for the directory (`hooks/README.md`,
  "The audit key"). A key file the agent can replace gives no evidence
  against the agent.
  A log signed with the key derived from the host name verifies only with
  that key. Outside Claude Code (the pre-tool-use hook refuses a command
  that names these files), move `.claude/audit.log`, `.claude/audit.head`
  and the anchor, `<git dir>/acs/audit.head`, aside together; otherwise the
  hook reports the old head, which another key signed, on every call.
  Verify the moved files with the earlier key (each path is where that
  file was moved):
  ```bash
  python tools/verify_audit_log.py --hmac-key "grounded-agency-audit-$(hostname -s)" \
    --log-file moved/audit.log --head-file moved/audit.head --anchor-file moved/anchor.head
  ```
  The earlier hook took the short host name each time it signed, and used
  `grounded-agency-audit-default` where `hostname -s` failed: if an intact
  log fails with this command, give that key, or the key with the short
  host name the machine had when the log was written. A log signed with
  `AUDIT_HMAC_KEY` before a key file existed is moved aside and verified
  the same way, with `--hmac-key` given that key.
- Checkpoint key: the take hook, the pre-tool-use hook and the rollback
  skill's hook compute the HMAC of a checkpoint's commit entry under the
  project's checkpoint key (`<git dir>/acs/checkpoints/key`) from openssl's
  SHA-256, with the key passed through pipes. Before, they passed the key
  to `openssl dgst -hmac` on its command line, where any process of the
  user could read it. The value is the same, so entries written before
  still verify.
- Plugin: the `persist` skill refuses content that holds a credential-shaped
  value (a URL's userinfo password and an `Authorization` header's value
  included), and the `audit` skill an append to
  `.claude/audit/records.jsonl` that holds one (F504); both hooks' refusals
  now open with the Standard's
  code and name (`F504 CONSTRAINT_VIOLATED:`, `R407 SAFETY_CHECK_FAILED:`).
  The `persist` skill's hooks now see `Write` and `MultiEdit` as well as
  `Edit` (each `edits[].new_string` is scanned), and check the file a
  path reaches with symbolic links followed (a link they cannot follow is
  refused), under `/private/etc` and `~/.claude` too. The `audit` skill
  appends a record only as `printf '%s\n' '<json>' >> <the records file>`,
  one JSON object on one line, scanned with its JSON escapes resolved; it
  refuses any other command naming the file with `$` (but in
  `${CLAUDE_PROJECT_DIR:-.}`), a backtick, `\`, `<` or `>`, which could
  build a record when the command runs. The `send` skill's hook refuses,
  in a `curl`, `wget` or `http` command, text the shell expands or escapes
  (`$`, a backtick, `\`, `<(`, `>(`) and an option or setting that
  redirects the connection (`--resolve`, `--connect-to`, a Unix socket, a
  proxy or `*_proxy=` variable, `--doh-url`, curl's `-K`, wget's `-e` and
  `-i`), and reads `localhost.` and `127.0.0.1.nip.io` as internal; put a
  credential header in a file (`curl -H @file`).
- Plugin: the `persist` skill's hooks see `NotebookEdit` too (its
  `notebook_path` and `new_source`), and the command hook reads what the
  call stores, not only the text it carries: the lines the file holds after
  the call that it does not hold now (the edits applied to the file the path
  reaches), each with its `\uXXXX`, `\UXXXXXXXX`, `\xXX`, `\/` and `\"`
  escapes decoded. So a value whose key or other half is already in the
  file (`password: "CHANGEME"` edited to a password, a token built by two
  edits or calls) or a JSON-escaped token is refused (F504). An existing
  target that is not a regular file, or is over 8 MB, is refused. Security
  round 3: the hook reads the file and applies the edits as Claude Code's
  Edit does: a file opening with FF FE as UTF-16LE (with `iconv`; without
  it, refused, R407), CRLF line ends as LF, and an empty `new_string`
  removing `old_string` with the line break after it. An Edit or MultiEdit
  whose `old_string` an existing file does not hold as written, nor with
  curly quotes read as straight ones, is refused (R407): Claude Code may
  still find it (as a `\uXXXX` escape in the file, or the character of
  one in `old_string`), and the hook cannot tell what the file will hold;
  give `old_string` as the file spells it.
- Skills: the `send`, `rollback`, `checkpoint`, `persist` and `transform`
  skills' prompt hooks no longer judge approval, checkpoints, rate limits or
  expiry (Changed), and the persist, rollback and send skills' command hooks
  now block (exit 2) a call they refuse, which they let through before
  (Fixed).
- Plugin, pre-tool-use hook (Fixed; Standard 1.2.0 §5.18.10, §6.7): a
  `TodoWrite`, `TaskCreate` or `TaskUpdate` call (`persist`) whose input
  holds a secret the layer recognises is blocked with `F504
  CONSTRAINT_VIOLATED:` in every permission mode, as the SDK adapter
  refuses it: the shared scan over every string of the input and its JSON
  text, and a value under a member named for a credential (`{"password":
  "..."}`, an `Authorization` name/value pair, a `["Cookie", ...]` tuple).
  Keep credentials out of todos and tasks; cite them by reference.
- Plugin, `tools/verify_audit_log.py` (Fixed): each line is verified as the
  bytes the hook signed, the compact JSON `jq -c` writes ending in its
  `hmac` member, with each member named once. A line edited without the key
  so that it parses to the signed entry (a member named twice, a blank or a
  `\u` escape inserted, the `hmac` moved) now fails, as does a blank line;
  a line the hook wrote verifies as before. `verify_entry` checks a parsed
  entry; `verify_line` checks a line.

**Standard Agents binding and TypeScript package.**

- TypeScript package and Standard Agents binding: `annotationRecord` reads
  an `ai.synapti/acs` annotation as the record in full (security round 3): every
  member but the copies (`tool`, `layer`, `risk`, `mutation`,
  `requires_checkpoint`, `requires_approval`) reaches the record, so a
  misspelt one (`aproval`, `flag`, `aditional_capabilities`) is S303 and
  the annotation does not load, where it was dropped and the tool loaded
  as what remained: `groundedTool` refuses a composite listing such a tool
  (V107), `lintPromptTools` reports it unbound (W617) and
  `deriveAgentManifest` names it malformed. Put vendor data under `x-`.
- TypeScript package: `npm test` replays the fixtures through the
  WebAssembly core, so run `npm run build:wasm` (which needs the
  `wasm32-unknown-unknown` target) and `npm run build` first; the binding
  needs only `npm run build:ts`.
- Standard Agents binding: `src/acs/canonical.ts` and
  `src/acs/ontology.gen.ts` are removed. The binding depends on the
  TypeScript package `@synaptiai/acs-core` (`file:../../packages/acs-core`)
  and imports its built `dist/`, so run `npm ci` and `npm run build:ts` in
  `packages/acs-core` before the binding's check and tests. Import
  `canonicalize`, `digest`, `sha256Hex`, `NotCanonicalizableError` and
  `Json` from `@synaptiai/acs-core`, and `CAPABILITIES`, `REQUIRES` and
  `ONTOLOGY_VERSION` from it or from `src/acs/ontology.ts`. The binding's
  copy of the approval digest vectors, `test/fixtures/approval-digests.json`,
  is removed: read `tests/conformance/approval/digests.json`. The package
  is not on npm until `.github/workflows/publish-npm.yml` publishes it (it
  does only when `NPM_PUBLISH_ENABLED` and `NPM_TOKEN` are set), so a copy
  of the binding outside this repository builds the package from
  `packages/acs-core` or bundles it.
- Standard Agents binding: `STANDARD_VERSION` is 1.2.0 and the `ai.synapti/acs`
  annotation carries the tool binding record (`tool`, declared `flags`,
  `additional_capabilities`, `invokes`, `approval`); the copies of the layer
  and flags are informative. `lintPromptTools` and `lintAgentBindings` report
  `W617`, `V111`, `V102` and `F506` in place of `unclassified`,
  `misnamed_tool` and `bound_gated_tool`. A prerequisite other than a
  checkpoint that has not run is refused with V102, and a check or record
  the binding cannot complete with R407. A tool's success result is the
  output's I-JSON text, and an output with an integer beyond 2^53, a
  non-finite number or a lone surrogate is refused with R402. A composite
  lists the tools it invokes in `invokes`, which also becomes its `uses`; an
  invocation outside the list is refused (F504). A call that needs approval
  whose arguments are not I-JSON is refused with F502 before anything is
  asked or used. An approval policy's `min_approvers` is at most
  `MAX_APPROVERS` (1000). A grounded tool's `recorded_by.config_sha256`
  digests `{annotation, settings: {checkpoint_max_age_ms}}`, not the
  annotation alone. The annotation schema now refuses a copy of the layer
  or flags that names another layer or a weaker flag than the capability's
  (Changed).
- Standard Agents binding: a trace entry's `approval.approvers` (and
  `GroundedCall.approvers`) are now the approvers' principals,
  `sa-user:<id>`, not bare `ThreadUser` ids, and the entry carries
  `approval.approver_identities`; compare approvers by principal. They list
  only the approvers whose approvals counted when the call ran
  (`countedDecisions`): one that had lapsed under `expires_ms` is left out.
  `POST acs/approvals` takes the digest in either case.
  `decideApproval` takes an optional last argument, `ApproverOptions`
  (`kind`, `ownerId`). Decisions stored by an earlier version have no
  identity, and a call that uses one records no `approver_identities`.
- Standard Agents binding: `fileAnchor` returns `{ref, kind: 'file', digest:
  'sha256:...'}` instead of `metadata.sha256`; every trace entry's
  `evidence_anchors` and `error` are stored redacted (default patterns,
  plus the tool's `secrets`), as are the notifications; a `persist` or
  `audit` tool refuses data that holds a credential (F504), a URL's
  userinfo password and an `Authorization` header's value included.
- Standard Agents binding: `LintDiagnostic.code` gains `V107` and
  `location` a variant `{workflow, field, path}` (`lintDelegationTargets`).
- TypeScript package and Standard Agents binding, the lint (security round
  5, batch 5): `checkBindings` takes `raised`, the flags a layer applies to
  a loaded tool beyond its record (those its domain profiles raise,
  §5.21.3), joined into the tool's effective flags and the checks of the
  offered tools. `lintAgentBindings` and `lintPromptTools` pass the flags
  each tool defined with `groundedTool` computed (`computedFlags`), so a
  stop or session action tied to a tool whose profiles, or the layer's,
  make it need approval or a checkpoint is now F506, and a checkpoint they
  require that no offered tool takes is V102, where both passed before.
  The Python SDK's `check_offered` checks the mappings it is given: pass
  those `adapter.mapper.map_tool` gives, which carry the profiles' flags.
- TypeScript package: `checkBindings(records, {known})` reports V105 for a
  cycle that runs through the `known` bindings too (a record that invokes a
  known composite that invokes it), and does not load the record, as the
  Python loader does; before, a set loaded in two steps closed the cycle.
  A loaded composite's `approval` is the join of its own and its invoked
  bindings' (`joinApproval`), as in the Python loader.
- Standard Agents binding, composites (Standard 1.2.0 §5.18.4):
  `groundedTool` throws (V107) for a composite that lists a tool with no
  binding the layer loads (plain `defineTool` with no `ai.synapti/acs` annotation, or
  one that does not load on its own); before, it counted as the strictest
  case and its calls went unchecked and unrecorded. A listed tool defined
  with plain `defineTool` and a binding record is now checked by the
  composite's nesting state (a `send`'s destination at its record's
  `destination` against every policy in force, F504; the composite's
  decisions against its approval, F502; its prerequisites) and recorded
  with `covered_by`. A composite asks for the strictest approval of its own
  and its invoked tools' (the most approvers, the shortest expiry, a role
  one of them sets), and a nested call is covered only when the decisions
  that approved the composite are valid for its own approval (else it is
  checked on its own). `requestApproval` starts a new round when the live
  request was asked under a weaker policy than the call's.
- Standard Agents binding, domain profiles (Standard 1.2.0 §5.21.1):
  `configureLayer({ profiles })` applies `bindingProfiles` to every grounded
  tool defined after it, beside the tool's own, and a tool defined before
  the layer's profiles changed refuses its calls (R407): call it before
  defining the tools. `configureLayer({ profilePolicy })` throws for a
  policy that sets a minimum confidence or grounding policies, which it
  does not put in force. `memoryTools` takes `profiles` and `grounding`
  (before, its tools applied no profile), and its `recall` tool registers
  `secrets` too.
- Standard Agents binding, sends (Standard 1.2.0 §4.4.2, §5.18.10): a `send`
  tool's destination is no longer read from `args.destination` by default.
  Its `destination` option says where: an RFC 6901 pointer into the
  arguments (`destination: '/destination'`, new, which the annotation
  states as the binding record's `destination`) or a function of them, as
  before. While a destination policy is in force, every call of a `send`
  tool defined without the option is refused with F504 (the layer cannot
  tell where it sends); give each `send` tool the option. With no policy in
  force nothing changes.
- Standard Agents binding, composites (Standard 1.2.0 §5.18.4): a nested
  call is covered by the composite's approval and checkpoint only as far as
  the composite's call held them (a nested call that needs a checkpoint is
  covered only when the composite's call used one), since the runtime runs
  whatever tool it knows under a listed name; otherwise it is checked as a
  call of its own. An invocation through a composite's state once its call
  has ended (code that kept the state, or an invocation the composite did
  not wait for) is refused with F504, or, for a grounded tool whose
  invocation had started, checked as a call of its own. Security round 5,
  batch 4: a nested call is covered only by the decisions the composite's
  call counted (under a person requirement, a person's), so an approval the
  deployment attests as an agent's, given to the composite's request, no
  longer covers a nested call that needs a person once the person's
  approval has expired: the nested call is checked as a call of its own
  (F502 for a plain tool, or its own request for a grounded one). Security
  round 5, batch 5: the destination policies and output rules (grounding,
  minimum confidence) of the profiles given to a composite, and to those
  enclosing it, now apply to every call of a tool the composite has a
  pending invocation of, whether or not the call takes the invocation's
  token: a runtime that gives the tool its validated arguments (a zod
  `.default()` or `.transform()`, a stripped key) changed their digest, a
  listed tool that states another name than the one it is invoked under
  never matched, and a composite running outside an execution (an
  endpoint, an effect) issued no token, so the nested call ran with none
  of them. Such a call still asks its own approval and checkpoint; a send
  those policies forbid is now refused (F504) and an output they refuse
  fails (F505, F504). Another call of the tool made while the invocation is
  pending (a parallel call, an endpoint's), which the binding cannot tell
  from it, is held to them too. Security round 6: the profiles given to a
  composite and to the composites enclosing it (and the layer's) also raise
  the flags and person requirement of every nested call, plain or grounded,
  at any depth, for what it performs and for what its own nested calls
  perform, whether or not it takes the invocation's token. A raised
  approval is covered only by the composite's decisions that still meet it
  when the nested call runs, so a nested call made after the composite's
  approval lapsed is refused (F502), and a raised checkpoint only when the
  composite's call used one (F501 otherwise). A nested composite that takes
  no token asks its own approval (a person's where the profiles require
  one) and uses its own checkpoint, and those then cover its nested calls.
  The trace entries of a call that only the enclosing profiles require a
  person for carry `person_required`, its R407 entries included.
- Standard Agents binding, composites and plain tools (Standard 1.2.0
  §5.18.4, §5.18.10): a nested call of a listed tool defined with plain
  `defineTool` runs only under a name the new `registerTools` (in
  `src/acs/layer.ts`) registers as that very tool, since the runtime runs
  whatever tool it registers under the name; call `registerTools` with the
  agent's tools, by the names the runtime runs them under, once they are
  defined. Without it such a call is refused (F504), as is an invocation of
  any listed name registered as another tool than the one listed, or as two,
  and, while a destination policy is in force (the layer's, a composite's
  profiles', or, security round 4, the profiles' given to the listed tool
  or to a tool it invokes, transitively), an invocation of any listed name
  not registered, a grounded tool's included.
  Such a nested call is now checked as a grounded tool's call is: a
  `persist` or `audit` call whose data holds a secret is refused (F504),
  and what it returns is checked against its capability's output contract
  (R402), the composite's grounding policies (F505) and its profiles'
  minimum confidence (F504), so a plain tool must return its output's JSON
  text (a plain `checkpoint` that returns other text takes none, and no
  rollback runs on it). Security round 4: the output rules of the profiles
  given to a composite (their grounding policies and minimum confidence),
  with its own `grounding`, now reach the output of every nested call it
  covers, at any depth, a grounded tool's (after the tool's own rules) as
  well as a plain tool's, where before they reached only a plain tool's
  call the composite itself made: a nested grounded call whose output they
  refuse fails (F505, F504) and is not counted as executed. A composite's
  state refuses `queueTool` (it throws the F504 refusal, which is
  recorded) for a tool the composite does not list, a listed plain tool,
  and any tool once its call has ended; a listed grounded or control tool
  is queued as before. A grounded tool with no
  `invokes` now declares `uses: []`, so a runtime that enforces `uses`
  refuses its `invokeTool` and `queueTool` calls.
- Standard Agents binding, secrets (Standard 1.2.0 §6.7):
  `configureLayer({ secrets })` registers the host's own secrets layer-wide:
  every trace entry the binding writes, the audit hook's for plain tools
  included, is redacted with them, and `persist` data or an `audit` record
  holding one is refused. `recordToolCall` takes an optional last argument,
  `{ secrets }`. `configureLayer` replaces the whole configuration, so pass
  `secrets` with the policies and profiles. A grounded tool's own `secrets`
  join the layer's (`registerSecrets`; an array when the tool is defined, a
  function's values at each call) and `configureLayer` keeps them, so the
  audit hook's entry for a plain tool, and `persist` data, are redacted and
  refused with every secret any tool registered; `resetLayer` forgets them. An evidence anchor that held a
  secret loses its `digest` in the trace (above). A call refused because a
  tool's `secrets` function threw (R407) is now recorded, as a `refused`
  entry with the layer's `recorded_by`, redacted with the secrets the layer
  holds, so the audit hook links it rather than writing an entry of its
  own. Security round 3: a nested call whose checks the layer cannot
  complete, a read of its records that fails or arguments with no
  canonical JSON (a cycle, nesting too deep to walk, a value that is not
  JSON), is refused with R407 and recorded with the call that covered it,
  where the exception reached the composite's code and nothing was
  recorded; a nested plain call with such arguments, which ran, is refused
  too, as a grounded tool's own call is. The id of a checkpoint the layer
  records (`acs:checkpoints`, and a trace entry's `checkpoint_id`), the
  value the `checkpoint` call returned, is stored redacted too
  (`addCheckpoint`); two ids that are one once redacted name one
  checkpoint, so a call that uses one uses both. Security round 4 (batch
  5): a trace entry's `action`, the tool's name, is redacted too (the name
  the model called, or the one a composite's code invoked, may be a secret
  under a prompt injection), and so are the exported audit record's `tool`
  and `intent` and the waiting list `acs:trace:unlinked`; the audit hook
  matches a call to its entry by the redacted name. A refusal a
  composite's state returns for a nested call (or throws, for
  `queueTool`) is redacted, the tool it names included. The Python
  adapter's call records, the audit records exported from them and its
  diagnostics redact the tool's name likewise. Security round 5 (batch 5):
  every result a grounded call returns that is not a success is redacted
  before the runtime stores it and the model reads it, as its trace entry
  is: the R407 of a `secrets` function that throws or of a check the
  layer cannot complete (which quoted the store's error), an R402 that
  names an output member, the tool's own error (which a thrown `Error`'s
  message becomes), and an F502's `error_data.shown`, whose arguments now
  have their secrets replaced (its `digest` stays that of the values the
  approver decides on, which the approvals endpoint still shows); and so is
  every result a composite's state returns that is not a success, a nested
  plain tool's own error included, and a control tool's own error result.
  Security round 6: an error a control tool's code throws is now returned
  as an error result, redacted the same way, instead of reaching the
  runtime as thrown; the control tool's entry is still `executed`.
- TypeScript package and Standard Agents binding: `checkBindings` and the
  lint read tool names as own members only (security round 6), so a tool
  offered or tied to a host action under a name a plain object holds on
  its prototype (`constructor`, `toString`, `hasOwnProperty`, `__proto__`)
  whose record did not load is reported W617 or F506, and `groundedTool`
  refuses a composite listing it with V107, where the check threw; a
  binding record whose `tool` is `__proto__` is returned among the
  bindings.
- Standard Agents binding, audit hook (Standard 1.2.0 §6.4): an entry
  written by a nested call, or by a call made while a composite's
  invocation of the tool is pending, waits for a tool call id only while
  the composite's own entry waits (security round 6). In a runtime that
  fires no `tool_call_done` for `state.invokeTool`, the hook of the model's
  own later call of the same tool now links its own entry, not the nested
  one. This relies on the calls of a step running one after another, with
  each hook before the next call.

**Interoperability data.**

- `schemas/interop/oasf_mapping.yaml`: `meta.grounded_agency_version` is
  replaced by `meta.agent_capability_standard.standard` and `.ontology`.

### Added
- Standard 1.2.0 (Candidate Standard), `spec/STANDARD-v1.2.0.md`, with
  capability ontology 2.2.0, accepted by RFC-0005 to RFC-0011 (RFC-0002
  stays a Draft). Appendix D lists every change from 1.1.0 and
  `spec/CHANGELOG.md` summarises them; the entries below follow the RFCs.
  Ontology 2.2.0 is additive (§11.6, which now says how the ontology is
  versioned): every output contract declares `confidence`,
  `inference_method` and `uncertainty`, its `evidence_anchors` items are
  §6.5 anchors (a bare string or another object is accepted as a deprecated
  legacy form), and the inputs and outputs each RFC adds are listed with it.
  New codes: V110, V111, R407, R408, F506 and W617–W626.
- Standard 1.2.0, tool-calling hosts
  ([RFC-0005](spec/RFC-0005-tool-calling-hosts.md); findings ACS-01,
  ACS-02, ACS-03, ACS-07, ACS-08, ACS-36, ACS-38, ACS-39, ACS-41, ACS-55,
  ACS-57): how the Standard applies to a host where a model chooses tool
  calls. §5.18 Tool-Calling Hosts: the tool binding record
  (`schemas/interop/tool_binding.schema.json`), unbound tools, classification
  by effect, composite and control-only tools, the scope, order and
  concurrency of calls, one checkpoint and one decision per call, refusals as
  §9.8 diagnostics, records that name the layer, and capability outputs on a
  text-only channel; §5.2.2 states the executor's checkpoint use for steps.
  §10.4 adds the safety-layer conformance class SL.
- Offered-tool checks, `check_offered` (Python) and `checkBindings`
  (TypeScript): a `shell_tools` (`shellTools`) argument names the layer's
  shell-like tools as its statement does, and one with no declared
  boundary performs only its worst case, so its `classifier` does not count
  it as able to perform any capability (STANDARD 1.2.0 §5.18.2); binding
  fixtures may carry `shell_tools`. The Standard Agents binding's
  `lintPromptTools` counts a classified tool only as its own capability, since the binding applies no classifier: a prompt
  whose only checkpoint route was a classified tool now gets V102.
- Safety-layer conformance fixtures: 37 binding fixtures in
  `tests/conformance/bindings/` and 33 call-sequence fixtures in
  `tests/conformance/calls/`, with their schemas and the statements of the
  two reference layers, generated by `scripts/gen_call_fixtures.py`
  (`--check` in CI). The Python SDK adapter and the Standard Agents binding
  run them.
- Conformance statement schema
  (`tests/conformance/calls/schema/statement.schema.json`, §10.4):
  `approval.expires` is a duration or null; `not_applied` lists the
  §5.18.10 checks a layer does not apply, and a layer that lists any does
  not conform to class SL until it applies them; `calls_without_output`
  names the covered calls whose results carry no capability output, to
  which no output check applies. Both reference layers list nothing in
  `not_applied` and claim class SL: the Python SDK adapter checks the
  output contract of the results it receives as capability outputs, those
  of every MCP tool bound to a capability, in the form the session reads
  them (R402), and its statement names the calls whose results come in
  other forms (Claude Code's own tools) in `calls_without_output`; the
  Standard Agents binding checks every grounded tool's output.
- Python SDK: `load_bindings`, `check_offered` and `ToolBinding` (binding
  records, W617, V111, V102, F506); `encode_capability_output`,
  `decode_capability_output` and `CapabilityOutputError` (§5.18.9);
  `grounded_agency.errors.text_form`.
- Python SDK tool binding records (`grounded_agency.capabilities.bindings`,
  Standard 1.2.0 §5.18.1): a record with a member that has no I-JSON form
  (an `x-` member holding an integer beyond 2^53, a lone surrogate or an
  object that is not JSON) is S303 and not loaded, and its tool stays
  unbound. A float that canonical JSON writes as an integer beyond ±2^53
  (1.8e16) has no I-JSON form either: in a record it is S303, and in the
  arguments of a call that requires approval F502, as in the TypeScript
  package (`i_json_problem`). `approval.min_approvers` written as `1.0`
  loads; `approval.role: null` is S303, and `approval.expires` longer than
  2^53 - 1 ms is S303, as is a `domain` that is not a domain id (§5.2.4;
  in the TypeScript loader too, and in both binding schemas). A diagnostic's `location.field` is the member's path
  with keys joined by a dot (`approval.min_approvers`, `flags.risk`); W602
  names `flags.<flag>`. `adapter.recorded_by["config_sha256"]` digests the
  rate limits (`config.rate_limit`), which decide F504 refusals, with the
  bindings and settings.
- Python SDK: `GroundedAgentAdapter.check_call_result` checks the result of
  a call of an MCP tool bound to a capability (the output contract, R402;
  then grounding, F505, and a minimum confidence, F504): a tool
  `create_grounded_mcp_server` serves calls it with its result, and the
  PostToolUse hook with another server's; `GroundedAgentConfig.check_outputs`;
  `tool_result_output` in `grounded_agency.capabilities`, the output an MCP
  result carries (§5.18.10); `create_checkpoint_recorder(refuses_output=...)`.
- Approval digest vectors of kind `tool_call` for a call's shown values.
- Capability output vectors (informative), `tests/conformance/output/vectors.json`,
  which the Python and TypeScript codecs of §5.18.9 both pass. TypeScript
  package: `iJsonProblem`. Python SDK: `CheckpointTracker.valid_checkpoint_id()`,
  `has_commit()` and `max_age_minutes`.
- TypeScript package: `checkBindings`, `annotationRecord`,
  `encodeCapabilityOutput`, `decodeCapabilityOutput`, `effectiveFlagsOf`,
  `prerequisitesOf`. The Standard Agents binding adds `controlTool`,
  `additional_capabilities` and `invokes` with one-shot nesting tokens.
- TypeScript package (`packages/acs-core`), security round 3:
  `decodeCapabilityOutput`'s refusal of a text that is not JSON no longer
  repeats the JSON parser's message, which quoted part of the text (a
  window that cut a secret left a piece no redaction matched in the trace);
  it says where the text stops being JSON, when the parser tells
  (`(at character N)`). Code that matched the parser's wording (`Unexpected
  token`) reads the R402 code instead.
- TypeScript package (`packages/acs-core`): `decodeCapabilityOutput` accepts
  a number written in exponent form (1.8e16, 1e300) and checks integer
  literals in the text itself; `encodeCapabilityOutput` accepts a value it
  writes in exponent form (1e21 and above) and refuses one it would write as
  an integer literal beyond ±2^53 (1.8e16). A tool binding record's
  `location.field` follows the Python loader's dotted paths. `iJsonProblem`
  refuses a `bigint`, and `parseJsonExact` reads JSON text with an integer
  literal beyond ±2^53 as a `bigint` instead of rounding it (JSON.parse
  reads 9007199254740993 as 2^53): read text that is then checked as I-JSON
  with it.
- Standard 1.2.0, approval, deferral and run identity
  ([RFC-0006](spec/RFC-0006-host-protocol-approval-and-runs.md), Part A;
  findings ACS-10, ACS-11, ACS-12, ACS-13, ACS-35, ACS-44):
  - §5.14 states the request for a step with no or a partial `approval`
    field, what the approval digest is computed over (the shown array,
    RFC 8785, lowercase hexadecimal, compared regardless of case), the
    integer bound as the executor applies it, that whatever reads values
    from JSON text refuses a member name twice in one object (the core's
    `exec::read_json` does), and the meaning of `in_session` and
    `out_of_band`. `tests/conformance/approval/digests.json`
    is normative under §10.3, with a vector for a `shows` reference that
    resolves to nothing.
  - Resuming a deferred run (§5.14.1): `_core.Run.resume`,
    `WorkflowRunner.resume` and `RunResult.resumable`. The deferred steps
    run again as the same run, with the steps that ran ahead of them that
    they read and a checkpoint step a queued mutation binds; a nested run
    that ended deferred continues; a queued step is asked afresh (of a
    person when attended), every request of the step names
    `queued_action_id` (a re-ask after a recheck and a recovery loop before
    the step performs its capability included) until its action is carried
    out, that is until the step calls its capability, waits for its event,
    starts its nested run or has its quorum evaluated, whatever the result,
    and its `planned` record is updated in place with each decision and
    refusal until then; a loop after a failed call asks for a new action,
    with a record of its own. A queued record the resumption decides or
    supersedes takes the time and actor of then. A recovery loop during
    a resumption runs again only the steps from its target to the step that
    looped, a deferred handler among them keeping its nested run, and the
    resumption then goes on, so nothing that ran ahead runs twice. Trace
    kinds `run_resumed` and `invoke_resumed`.
  - With `identity@1`, an approval decision may attest its approvers
    (`approver_identities`); approvers are then counted by principal and
    checked against the requested kind and role, and the record lists the
    approvers that counted (`ActionRecord.approval.approver_identities`). In
    a workflow that targets 1.2, the approver may require `sender_check`
    and `accept_trust_classes` (V106 without `identity@1`, S303 when
    malformed); in an earlier target they stay unknown fields (W604) and
    get W616.
  - A run keeps its actor (§5.17): `Run.restore` and
    `WorkflowRunner.restore` take `actor_identity` and refuse another
    principal; a resumption may name a new actor, which the trace and later
    records show.
  - 46 runtime fixtures (`approval_*`, `approver_*`, `resume_*`; a script's
    `resume` entry and the `{{digest_upper}}` placeholder) and four
    validator fixtures (`*approver_identity*`). Each `step` digest vector
    gives what its step shows from (`bindings`, `recheck_read`), so an
    executor can be checked against the file alone.
- Standard 1.2.0, host protocol, runs and audit records
  ([RFC-0006](spec/RFC-0006-host-protocol-approval-and-runs.md), Part B;
  findings ACS-14, ACS-15, ACS-20, ACS-30, ACS-31, ACS-32, ACS-33, ACS-34,
  ACS-37, ACS-45, ACS-62):
  - §5.19 Host Protocol: every action and response, the members the
    executor computes and the outputs it composes, the run operations, the
    tick boundaries and wake-up time, the host's obligations (one writer,
    save before acting, at-least-once delivery keyed by `run_id` and `id`,
    a unique `run_id`, integrity and a key where others can change stored
    states), cancellation (R408), protocol traffic, error reasons and the
    run record every host keeps; `schemas/host_protocol.schema.json`
    requires `run_id` on every action. Class EX (§10.5): the runtime
    fixtures are normative for executors, after an audit of every member
    they pin (the generator refuses a fixture that pins an unlisted one).
  - Reference executor: `Run::cancel`, `wake_at`, `take_trace`,
    `take_records`, `taken_heads` (SHA-256 chain heads over what was taken)
    and `run_record`; record mode `actions` (`StartOptions.records`,
    `records="actions"`), with a record for every step that runs, every
    failure-mode checkpoint and every rollback; an `audit` step of a
    workflow that targets 1.2 or later that binds `require_record: true`
    fails R402, reason `not_recorded`, when it did not record (a 1.1
    workflow passes the input on, as before). In a workflow that targets
    1.2 or later, an `Output` is checked as §5.18.9's consumer checks an
    output, as a safety layer checks a call's: an `evidence_anchors` that is
    not an array, or a required `confidence` that is not a number from 0 to
    1, is R402 (retried as any R402), before grounding (F505) and a minimum
    confidence (F504); a 1.1 workflow's outputs are checked for their
    required fields only, as before (eight `output_contract_*` runtime
    fixtures). Python: `_core.Run` gains the same operations, `_core.next_fire`;
    `WorkflowRunner.advance`, `cancel`, `archive=`, `save=`/`key=` (on
    `run`, `drive`, `advance`, `resume` and `cancel`), `run_ids=` and
    `event_seen=` (host stores for used `run_id`s and seen `event_id`s),
    `start(records=, trigger=, event=)`; `Host.withdraw`, `HostCannotServe`,
    `RunArchiveError`, `Turn`; `grounded_agency.workflows.protocol` (typed
    actions and responses) and `grounded_agency.workflows.triggers`
    (`OverlapGate`, `EventGate`, `trigger_attendance`, `next_fire`).
    `CoordinationEvent` keeps its record's `intent`, so the orchestrator's
    `audit` step returns the record its log exports.
  - §5.10.2 Evaluating Triggers: the host's duties, event acceptance with
    one run per `event_id`, fire times in the schedule's time zone (RFC 5545
    for clock changes), `every` anchored at the Unix epoch, `overlap` and
    missed fire times; a run an `invoke` step starts always has its
    invoker's attendance, whatever its `invoke` trigger declares; normative
    trigger vectors (`tests/conformance/triggers/`, from
    `scripts/gen_trigger_vectors.py`).
  - §5.2.3 Parallel Groups: members are unordered and the reference executor
    runs them in list order; W618 (`UNKNOWN_JOIN`) and W619
    (`GROUP_MATE_READ`).
  - §6.4 Audit Records and §8.4 Manual Overrides: the action record and the
    canonical event are the audit records; `CoordinationEvent.to_action_record`,
    `CoordinationAuditLog.export_action_records`,
    `grounded_agency.trust.manual_override` and
    `TrustModel.manual_override`; the evidence collector's `required=True`
    reports a capture that failed; the audit skill writes a record of its own
    with the event under `details.event`; the safety layers export their
    records of calls as action records, each with the `recorded_by` of the
    layer that decided the call: the Python SDK adapter's
    `export_action_records(scope)` (each call record gains `seq`, its number
    in the scope) and the Standard Agents binding's `actionRecord(entry,
    scope)`.
  - 45 runtime fixtures (`cancel_*`, `wake_at_*`, `records_*`,
    `run_record_*`, `parallel_group_*`, `audit_*`, `error_reason_*`,
    `invoke_trigger_attendance_*`,
    `response_extra_members_ignored`, `action_has_run_id`,
    `approval_record_decision_id`), whose script may hold `tick` with
    `changed`, `wake_at` and `cancel` entries and whose fixture may state
    `records` and `run_record`; four validator fixtures (W618, W619,
    `require_record`).
- Standard 1.2.0, delegation, catalogs and validator diagnostics
  ([RFC-0007](spec/RFC-0007-delegation-catalogs-and-diagnostics.md);
  findings ACS-04, ACS-09, ACS-16, ACS-17, ACS-24, ACS-29, ACS-46, ACS-47,
  ACS-49, ACS-50, ACS-54):
  - §5.1.1 catalog manifests (`id`, `version`, `ontology`, `exports`),
    catalog sets and qualified workflow ids `<catalog id>/<name>` for
    `invoke`, resolved by one resolver in the validator and the executor
    (`core/src/catalogs.rs`); V107 for a hidden or missing workflow of a
    loaded catalog, W607 otherwise, V105 across catalogs.
  - §5.15.1 agent manifests (`schemas/agent_manifest_schema.yaml` 1.0.0) with
    derived maxima; §5.15.2 the workflow field `agents` (1.2 only): a
    literal unlisted agent is V107, a delegate step takes its target maxima
    (F501, approval, W602), the executor refuses an unlisted, unmanifested
    or task-refused delegation before approval or a checkpoint (R402, not
    retried), a literal task is checked (S303/S304); §5.15.3 `continues`.
  - §5.15 model families compared exactly and derived from a model
    identifier by one rule; `model_id` on identities and `effective`.
  - §5.2.4 domain ids and the host's selection rule; §5.13.1 typed,
    correlatable answers to `inquire`; §4.3 the scope of `conflicts_with`;
    §9.8 every location key, `path` and `catalog`.
  - §11.5: `agents`, `continues`, a catalog manifest and an `invoke` target
    that is a qualified id are 1.2 features (W616 in a workflow or catalog
    that targets 1.0 or 1.1, located at the step for a step member).
  - Rust: `names`, `agents` and `catalogs` modules; `validate::validate_set`,
    `validate_with` takes `catalogs` and `agents` beside the profiles;
    `Run::start_set`, `Run::restore_set` and `SetOptions`;
    `_core.model_family`; the WebAssembly interface's `validate`,
    `run.start` (in `options`) and `run.restore` take `catalogs` (each
    `{catalog, header}`) and `agents`. CLI:
    `tools/validate_workflows.py --with-catalog PATH --agents PATH`.
  - Python SDK: `WorkflowEngine.load_library`, `libraries`,
    `add_agent_manifest`, `load_agents`, `agent_manifests`; the runner
    passes them to the executor; `coordination.manifest`
    (`check_agent_manifest`, `manifest_maxima`, `join_maxima`,
    `target_maxima`, `check_task`), `coordination.families`
    (`model_family`), `coordination.inquiry` (`match_answers`),
    `workflows.domains` (`select_implementation`, `UnsupportedDomain`);
    `AgentDescriptor.from_manifest`, `.manifest()`, `.maxima()`,
    `AgentRegistry.register_manifest`.
  - TypeScript package: `manifestMaxima`, `joinMaxima`, `checkTask`,
    `workflowTarget`, `agentsApply`,
    `modelFamily`, `isModelFamily`, `selectImplementation`,
    `UnsupportedDomainError`, `isDomainId`, `issuePath`; `CoreContext`'s
    `validate`, `start` and `restore` take `catalogs` and `agents`
    (`SetArgs`). Binding:
    `deriveAgentManifest` (loads each `ai.synapti/acs` annotation as a binding record,
    as the layer does, and follows `invokes`, with `invoked` for helper
    tools the prompts do not offer; refuses unannotated tools, annotations
    that do not load, invoked tools not given, declared flags stricter than
    a tool's capabilities and missing subagent manifests), `taskRefusal`,
    `declaredAgents` and `lintDelegationTargets` (both take the catalog's
    version header; `agents` has effect only in a workflow that targets
    1.2); `AgentIdentity.model_id`.
  - Conformance: 38 workflow fixtures with `catalogs`, `agents` and
    `expected_locations` (a `code` and its `path`, or for a finding with no
    `path` its `catalog`, `workflow` and `field`); 20 runtime fixtures (two
    of them, `agents_maxima_with_profile_person` and
    `agents_read_only_maxima_with_profile_checkpoint`, with a profile
    applied; `delegate_continues_v11_unchecked` and
    `delegate_identity_model_id_v11_unchecked` pin 1.1); normative vectors
    `tests/conformance/domains/match.json`, `agents/maxima.json`,
    `families/derive.json` and `inquiry/answers.json`.
- Standard 1.2.0, evidence, grounding and secrets
  ([RFC-0008](spec/RFC-0008-evidence-grounding-and-secrets.md); findings
  ACS-06, ACS-21, ACS-22, ACS-23, ACS-40, ACS-51, ACS-53, ACS-58):
  - §3.1 defines grounded and inferred outputs; §4.1.1 defines
    `confidence`, `inference_method` and `uncertainty`; §6.5 one evidence
    anchor (`ref`, `kind`, `timestamp`, `excerpt`, `digest`; kinds with
    `record` and `x-...`; the `acs:` ref scheme; bare strings and other
    objects deprecated), the evidence available to a producer, and how an
    output reporting an action is grounded (a `record` anchor); §6.6 evidence
    records, stores and the `acs.evidence_recorded` notification; §6.7
    secrets in records; §6.3 retention follows the store, and `audit`
    reports its `store`.
  - §5.20 Grounding: the extension `grounding@1` and host policies (a list,
    covering nested runs) make the reference executor check host outputs:
    `acs:` citations covered by a bound reference, the `Output` response's
    `evidence_seen`, `attested`; F505 is raised and can fire a failure
    mode; with `grounding@1` an `invoke` step carries its nested run's
    anchors. In a 1.2 target `grounding` without the extension is V106.
    Python: `_core.check_grounding`, `Run.trace(since=...)`,
    `Run.trace_seq`, `grounded_agency.grounding` (`GroundingPolicy`,
    `check_grounding_output`), `WorkflowRunner.run(grounding=...)`,
    `GroundedAgentConfig.grounding` (applied to the outputs of the MCP
    tools bound to a capability; a refused output's call record is
    `failed` with F505 and the call id, and a policy that requires the
    capability of a call whose output the adapter cannot see, Claude
    Code's own tools, is warned about once per tool). TypeScript
    package: `evidence.ts` (`checkGrounding`, `groundingPolicies`, `covers`,
    `refsIn`) and `holdsCredential`; the binding's `grounding`, `seen` and
    `secrets` options. A host policy with a member other than `require`,
    `kinds`, `attested` and `x-...` is refused in all three languages; an
    `acs:` reference holds no index above 2^53 - 1.
  - Vectors: `tests/conformance/grounding/check.json` (normative, run in
    Rust, Python and TypeScript); `tests/conformance/secrets/credentials.json`
    (informative: the credential shapes the refusals of `persist` and
    `audit` data recognise, run in Python, TypeScript and the plugin's shell
    scan); 23 `grounding_*` runtime fixtures and
    `error_reason_secret_in_data`; seven workflow fixtures.
  - Evidence stores: `EvidenceStoreProtocol`, `EvidenceRecord`, `StoreInfo`,
    a durable `JsonlEvidenceStore` (repairs a torn last line),
    `subscribe()`, `record_capture_failure()`; the runner's
    `evidence_store` records the evidence of outputs the core kept, and its
    `redactor` registers the host's secrets; `GroundedAgentConfig` gains
    `evidence_store` and `secret_values`; `EvidenceAnchor.from_checkpoint`,
    and `create_checkpoint` records it. Binding: `exportEvidence`,
    `getEvidence`, `findEvidence`, `exportEvidenceJsonl`,
    `EVIDENCE_STORE_INFO`, `checkpointAnchor`.
  - `schemas/interop/evidence.schema.json` is listed in §6.1; the catalog
    schema accepts `grounding@1`.
  - Plugin: `hooks/secret_scan.sh`, the one scan the `persist` and `audit`
    skills' hooks copy; every skill's `evidence_anchors` examples are §6.5
    anchors, and the capability skills gloss `confidence` as §4.1.1 defines
    it.
- Standard 1.2.0, checkpoints, rollbacks, sends and memory
  ([RFC-0009](spec/RFC-0009-checkpoint-rollback-send-memory.md); findings
  ACS-18, ACS-19, ACS-26, ACS-27, ACS-48, ACS-52): §4.4.1 (what a
  checkpoint holds, what `restored` asserts, what a rollback never
  reaches), §4.4.2 (transmissions, idempotency keys, compensation,
  destination policies), §4.5 (memory scopes, `ttl`, what `stored: true`
  guarantees), §5.15.4 (checkpoints across a delegation), the §12.5
  patterns Guarded Send and Checked Rollback, Appendix D.6. Ontology
  outputs `checkpoint.mechanism/captured/excluded/digest/expires_at`,
  `rollback.unrestored/not_covered/changes_reverted/verification`,
  `send.compensation`, `persist`/`recall` `scope`, `stored_at`,
  `expires_at`, `delegate.effective.checkpointed`.
- Normative vectors `tests/conformance/destinations/match.json` (run by the
  core, Python and TypeScript) and `tests/conformance/memory/store.json`;
  22 runtime fixtures (idempotency keys, destination refusals, rollback
  reports, memory scope echo) and 8 validator fixtures.
- Python SDK: `FileSnapshotStore` (checkpoint content that never captures
  the host's own records; `CheckpointTracker(snapshots=...)`,
  `restore_checkpoint`, `checkpoint_output`), `MemoryStore`
  (`MemoryContext`, `MemoryStoreError`), `IdempotencyLog`,
  `Host.send_once`, and `Host` defaults that perform `checkpoint`,
  `rollback`, `persist` and `recall` and answer `Rollback` with these
  stores; `GroundedAgentConfig(allowed_destinations=..., snapshots=...)`.
- TypeScript package: `destinations.ts` (`checkPattern`, `allowed`, ...)
  and `duration.ts` (`parseDurationMs`). Standard Agents binding:
  `configureLayer`, a `send` tool's `destination` option, `memoryTools`.
- Standard 1.2.0, profiles, trust, versioning and schema dialect
  ([RFC-0010](spec/RFC-0010-profiles-trust-versioning-and-dialect.md);
  findings ACS-05, ACS-25, ACS-28, ACS-42, ACS-56, ACS-59, ACS-64): the
  text of §4.1.2 (schema dialect), §5.21 (domain profiles), §7.1 (entity
  ids), §8.1–§8.3 (trust), §11.5–§11.7 (versions and artifacts) and
  Appendix D.7. The entries on domain profiles, trust, entity ids, cited
  versions and WebAssembly below implement it.
- Standard 1.2.0, shell-like tools and the operating-system boundary
  ([RFC-0011](spec/RFC-0011-shell-like-tools-and-os-boundary.md)): the
  text of §2, §5.18.2, §5.18.3, §5.18.8, §10.4 and D.8. A safety
  layer gives every call of a shell-like tool (a shell, an interpreter, a
  REPL, or a tool that runs code its arguments supply) the tool's worst
  case unless its conformance statement declares an operating-system
  boundary for the tool and the layer has verified by code, for that call,
  that the boundary holds in the effective host configuration: the values
  the host applies, from every source it reads, each counting only where
  the host honours it. The boundary is defined by four properties: no
  route outside it, writes kept from the layer's records, its code and any
  file that code outside the boundary runs, credentials (the user's, the
  host's and the layer's) out of reach, and a network allowlist that
  refuses other hosts. The conformance statement schema has a required
  member `shell_tools`; the Python adapter's statement declares Claude
  Code's sandbox as Bash's boundary and `"none"` for Monitor, PowerShell,
  Skill, Agent and Task, and the Standard Agents binding's declares no
  shell-like tool. The plugin's text readers (the
  records guard, the Bash classification, the send and audit skills'
  command hooks) are documented as advisory, not as the boundary.
- Domain profiles (Standard 1.2.0 §5.21, RFC-0010): the core loads and
  checks them (`profile::Policy`), the validator and the executor apply
  them (raised flags, a person for `require_human` and `block_autonomous`
  with `person_required` on records and in the trace, F504
  `below_minimum_confidence` and `invalid_confidence`, W606 for a
  mandate-only step), and they are saved with a run. Python:
  `AppliedProfiles`, `ProfileError`, `load_profile`,
  `GroundedAgentConfig(profiles=...)`, `WorkflowRunner(profiles=...)`,
  `_core.Validator.check_profiles`, `profile_flags`, `profile_policy`;
  `tools/validate_workflows.py --profile`. Normative profile vectors
  (`tests/conformance/profiles/`), 17 runtime fixtures and validator
  fixtures with profiles (`EXPECTATIONS.json` gains `profiles`). A runtime
  fixture's script entry may list `absent` members, which the pending
  action must not hold. The adapter's records digest (`config_sha256`)
  covers the applied profiles; `GroundedAgentConfig(schema_root=...)`. When
  a profile requires a person for a call, the adapter's ask reason says
  `requires approval by a person`, and an unbound tool's record carries
  `person_required` when a profile requires one for `mutate`
  (`ToolCapabilityMapper.person_required`).
- Domain profiles in every reference layer (§5.21.3): a profile's grounding
  policy is checked by the executor's grounding check (§5.20) and by
  `GroundedAgentAdapter.check_call_output`, which also applies the
  profiles' minimum confidence (`_core.check_confidence`) to the output of
  every MCP tool bound to a capability, served or not, with or without
  `config.grounding`; an exported call record carries `reason_code` and
  `person_required` (a failed call's record too). A composite tool takes
  the flags a profile raises for each binding it `invokes`, and its person
  requirement, transitively (§5.18.4), in the adapter
  (`ToolCapabilityMapper.map_tool`) as in the binding, so no profile rule
  is bypassed through a composite. The Standard Agents binding applies
  profiles through `groundedTool({profiles})` and `bindingProfiles` (raised
  flags at the call's effective risk with its `invokes`, and for what the
  tools it invokes perform; a person's approval, also for a composite whose
  approval covers a call needing one; grounding; minimum confidence;
  loading warnings such as W604 reported to `onWarning`), and a TypeScript
  host's `CoreContext.start` reports those warnings likewise (the
  WebAssembly interface's `run.start` answers them as `warnings`).
  Runtime fixtures `profile_grounding_*` and the header fixtures
  `header_1_2_sender_check_needs_identities` and
  `header_null_sender_check_not_read`; validator fixtures
  `warn_version_feature_1_2`, `warn_version_feature_1_2_grounding`
  (`grounding@1` and F505 in `on_error`) and
  `warn_version_feature_1_2_trust_classes` (`accept_trust_classes`), with
  the other streams' `pass_approver_identity_1_1_warn` and `*_v11_warn`
  fixtures one for every 1.2 feature of §11.5's table.
- Trust (§8): `grounded_agency.trust.resolve` with the six strategies of
  §8.2 and tie-breaking (a single candidate is chosen whatever the
  strategy), `Candidate`, `Resolution`, `merge_trust_weights`;
  the trust vectors are normative, with `resolve.json`. The
  conflicting-sources benchmark resolves with `resolve` (same results).
- Entity ids (§7.1): `grounded_agency.entities.parse_entity_id`,
  `tests/conformance/entities/ids.json`; `entity_taxonomy.yaml`'s pattern
  is checked against its examples, and names every white space and control
  character a segment cannot hold (U+00A0, U+2028 and U+0085 among them),
  so it means the same in every regular expression dialect.
- Entity merge and split checks (§7.3 for Standard 1.3.0, as the Draft
  RFC-0012 proposes it): `grounded_agency.entities.check_merge`,
  `check_split` and `class_index`, held to the proposed vectors
  `tests/conformance/entities/merge.json`. No reference layer merges or
  splits entities, so nothing calls them yet.
- Cited versions (§11.6): `grounded_agency.versions.check_cited` and
  `CitedVersionError`; the OASF adapter refuses a mapping that cites
  another ontology major or an unsupported Standard.
- WebAssembly (ACS-42): the core's `wasm` feature (`core/src/wasm.rs`, a
  JSON interface over three C-ABI exports) and the TypeScript package's
  `./wasm` entry (`AcsCore`, `CoreContext`, `CoreRun`, `loadDocuments`),
  which runs the validator and executor, profiles included, in process,
  with the host protocol's run operations (`run.resume`, `run.cancel`,
  `run.wake_at`, `run.take_trace`, `run.take_records`, `run.run_record`,
  `run.trace` since a `seq`; `CoreRun.resume`, `cancel`, `wakeAt`, ...);
  `Context::from_values` with an in-memory schema store.
  `.github/workflows/publish-npm.yml` publishes `@synaptiai/acs-core` from
  a tag `acs-core-vX.Y.Z` on `main` when `NPM_PUBLISH_ENABLED` and
  `NPM_TOKEN` are both set (a dry run otherwise).
- TypeScript package `@synaptiai/acs-core` 0.1.0, in `packages/acs-core/`
  ([its README](packages/acs-core/README.md)): the host-neutral core the
  Standard Agents binding is built on, with the ontology table, effective
  flags, canonical JSON and the approval digest, I-JSON checks
  (`iJsonProblem`, `parseJsonExact`), redaction, evidence and grounding,
  destination policies, durations, tool binding records, capability
  outputs, agent manifests, model families, step domains and diagnostic
  paths; the reference core through WebAssembly is its `./wasm` entry. Its
  tests read the conformance vectors in place; CI type-checks, builds and
  tests it.
- `skills/README.md` lists each frontmatter key's owner (Agent Skills,
  Claude Code, ACS), checked by `tests/test_skill_frontmatter.py`.
- [Standard Agents interoperability](docs/integrations/standard_agents.md):
  a mapping of this standard against the Standard Agent Specification 0.2.0,
  how to build a grounded agent on it, and the changes proposed to each
  standard.
- `docs/research/analysis/standard_agents_mapping/`: the row-level mapping
  behind that document (319 rows in ten concerns, each with references and
  verbatim quotes from both sides), the findings it produced about each
  standard (83 and 64) and the questions the texts leave open. `tests/test_standard_agents_mapping.py` keeps the index, the
  files and their references to this repository in agreement.
- `examples/standard_agents/`: a reference binding in TypeScript and a worked
  example. `groundedTool` classifies a Standard Agents tool by an ontology
  capability and enforces the capability's checkpoint, approval and output
  rules inside the tool; approvals are recorded through an authenticated
  thread endpoint and bound to the §5.14 digest, which is tested against the
  reference executor's. A rejection cannot be lost to an approval made at the
  same moment and stops a call that is starting on that approval, a decision
  applies only to the round of the request it was made on (`POST
  acs/approvals` takes `{ digest, round, decision }`), a call is recorded
  before its tool runs, a checkpoint or an approval authorises a call only
  inside an execution and a checkpoint for ten minutes at most, and canonical
  JSON refuses unpaired surrogates. `lintPromptTools` and `lintAgentBindings` check a prompt's
  tools and an agent's stop and session bindings before anything runs. CI
  type-checks it against the published `@standardagents/spec` types and runs
  its tests.
- `schemas/interop/standard_agents_annotation.schema.json`: the schema of
  the `ai.synapti/acs` annotation the binding puts on a tool.
- Standard Agents binding: a tool's binding record is the value of the
  annotation key `ai.synapti/acs` (`ANNOTATION_KEY`): a reverse-DNS prefix
  of a domain the project controls, then a slash, as the Model Context
  Protocol names `_meta` keys, so it cannot collide with the key of a
  package that follows the same rule. JavaScript reads it with bracket
  access, `tool.annotations?.['ai.synapti/acs']`. A reader reads this key
  only: a tool whose annotations hold a bare `acs` key and no
  `ai.synapti/acs` key is unbound. The layer name every record the binding
  writes carries (`LAYER_NAME`, `recorded_by.name`) is
  `@synaptiai/standard-agents-binding`.
- `scripts/gen_standard_agents_binding.py` generates the TypeScript
  package's ontology table (`packages/acs-core/src/ontology.gen.ts`), the
  annotation schema and the approval digest vectors
  (`tests/conformance/approval/digests.json`) from the ontology and the
  reference executor; `--check` fails on drift (CI).
- `tasks/standard-agents-upstream/`: nine issue texts for the Standard Agent
  Specification, and `file-issues.sh`, which files them in order with the
  GitHub CLI.
- `schemas/interop/standard_agents_mapping.yaml`: the Standard Agents
  binding's conventions as data (capability rulings, anchor forms, identity
  map), checked against the ontology and the mapping rows.
- `schemas/generated/capability_contracts.schema.json`: the 72 capability
  contracts as strict JSON Schema 2020-12, generated by
  `scripts/gen_capability_json_schemas.py` (`--check` in CI).
- Conformance vectors: approval digests in `tests/conformance/approval/`
  and trust scores in `tests/conformance/trust/`, both normative in
  Standard 1.2.0 (§10.3), and `grounded_agency.trust`, a reference of the
  section 8 arithmetic.
- `spec/ROADMAP.md` lists the five version lines and where each is declared;
  `tests/test_version_lines.py` keeps them in agreement.
- `spec/GOVERNANCE.md` defines the statuses of a Standard document
  (Candidate Standard, Standard, Supported, Unsupported), the criteria for
  releasing a Candidate Standard, what the `**Date:**` line gives for each
  status, and the support window. Standard 1.1.0 is the released Standard,
  1.0.0 is Supported and 1.2.0 is a Candidate Standard. The site states each
  version's status from its own header. `tests/test_standard_statuses.py`
  checks each header against GOVERNANCE, the Standard table and the
  "Plugin X implements Standard Y" sentence of the roadmap, and the
  specification changelog.
- `docs/guides/RUNNING_WORKFLOWS.md` lists the executor's trace event fields
  and kinds, tested against the core.
- `grounded_agency/layer_records.py` gives the Claude Code settings that keep
  the agent from the layer's records (#181): `permissions.deny` `Edit(...)`
  rules for every record and `Read(...)` rules for `acs/` (the checkpoint
  key), and a `sandbox.filesystem.denyWrite` list, every path literal and
  absolute. `acs/` is named in the git directory git names for the project
  (a linked worktree's own) and in each other git directory of the
  repository: the main checkout's, linked worktrees' and submodules', and,
  for a submodule checkout, the same for each superproject above it. It
  uses the standard library alone and the syntax of Python 3.9;
  `python3 -I grounded_agency/layer_records.py [PROJECT_DIR]` prints the
  settings as JSON.
- Plugin hooks: the pre-tool-use hook refuses every call (`F504`) while a
  file under `acs/` has a name outside the records, and every call it does
  not let pass outright while one of the project's records has (a hard link
  made outside the sandbox, through which a command could read or write the
  record past the deny rules). It counts links with perl, or, where perl
  is not installed, with `find`, `awk` and GNU or BSD `stat`; without them
  every call is blocked with `R407` while the git directory's `acs/`
  exists, and every call the hook gates otherwise. The deny rules are the boundary;
  the hook's reading of a call's paths is an early refusal
  (`hooks/README.md`, `spec/SECURITY.md` §5.5).
- Plugin hooks: the log hook reads an empty `audit.head` (a mount point the
  Linux sandbox runtime leaves) as none and writes the head anew; the
  anchor still shows a cut log. The take hook writes a new marker, and the
  log hook a new head, in `.claude/checkpoints/` before renaming it onto
  the record.
- Plugin: an MCP server for remote writes (#185),
  `grounded_agency/remote_writes.py`, declared in
  `.claude-plugin/plugin.json` and started as `/usr/bin/env -u
  DEVELOPER_DIR -u TOOLCHAINS -u SDKROOT /usr/bin/python3 -I` (on macOS
  `/usr/bin/python3` is a shim that runs the interpreter those variables
  choose; standard library only, Python 3.9 or later). Its tools are `push`
  (`branch`, optional `force_with_lease`: the object id the remote branch
  must still point at), `tag_push` (`tag`; an existing tag is never
  replaced), `pr_create`, `pr_merge` (`number`, `method`: `merge`,
  `squash` or `rebase`, optional `match_head_commit`), `release_create`
  (for a tag that already exists on the remote), `issue_create` and
  `issue_assign`, one action per call; Claude Code names them
  `mcp__plugin_agent-capability-standard_remote__<tool>`. The server runs
  outside the sandbox with the user's own git and gh credentials, which
  the strict sandbox denies to Bash. It takes no repository argument: the
  target is the origin a person records with `remote_writes.py record`, in
  a terminal outside Claude Code, in `~/.config/acs/remotes.json`. The
  strict sandbox the hook verifies requires writes to the whole of
  `~/.config/acs/` denied, not only to the audit key file, and the hook
  refuses (F504) a gated call that names the record or
  `~/.config/acs/work/`. The record
  also names the git and gh found on the person's
  PATH, which are the programs the server runs (it does not search its own
  PATH). With no record every tool refuses. A local origin must lie
  outside the project, the temporary directories and Claude Code's plugins
  directories, since git's local transport runs that repository's own
  hooks; a recorded program there is refused too, and so is a project
  directory that holds the home directory. It runs git and gh by argument
  list, with each option's value in the same argument; it pushes from an
  empty bare repository that reads the project's objects through
  `objects/info/alternates`, so the project's git configuration and hooks
  take no part, with `core.hooksPath=/dev/null`, `core.fsmonitor=false`,
  `--no-verify` and only the https, ssh and file protocols; it runs gh in
  an empty directory with `--repo` from the record. Each call works in a
  new directory under `~/.config/acs/work/`, not in the environment's
  `TMPDIR`. It checks branch and tag names as `git check-ref-format` does
  (and runs it), kept to ASCII letters, digits and `. _ / @ + -`, numbers
  as integers and methods from a fixed set, and refuses a member a tool
  does not declare. The home directory comes from the password database,
  the children's PATH is the recorded programs' directories and
  `/usr/bin:/bin:/usr/sbin:/sbin`, and the children get no `GIT_*`,
  `GH_REPO`, `GH_HOST`, `GH_CONFIG_DIR`, `XDG_CONFIG_HOME`,
  `DEVELOPER_DIR` or `SDKROOT` (a project's settings `env` reaches the
  server). Each tool is bound as a gated `mutate` (Standard 1.2.0
  §5.18.1): the pre-tool-use hook asks for a checkpoint and a person's
  approval for every call and names the call's target in the request
  (`push branch 'main' to the recorded origin, fast-forward only`); a
  call whose target looks like a credential, which the request could not
  show, is refused (F504). The SDK mapper classifies the tools the same way
  (`remote_writes.binding_records(prefix)` gives the records for a host
  that names the server otherwise) (`hooks/README.md`, "Remote writes").
- Plugin: the `/grounded-setup` command (#179, #182) turns on Claude Code's
  strict sandbox in the user's settings (`~/.claude/settings.json`, or
  `$CLAUDE_CONFIG_DIR/settings.json`) for the project it runs in. It shows
  the change to the `permissions` and `sandbox` members as a diff, asks,
  then merges it in and leaves every other setting as it is; run again, it
  changes nothing. It writes: the sandbox on with `failIfUnavailable` and
  no unsandboxed route (`allowUnsandboxedCommands: false`,
  `excludedCommands` removed); a network allowlist with
  `strictAllowlist: true`, from the hosts a domain profile's
  `allowed_destinations` name (`--profile`) and the package registries of
  the ecosystems whose manifests the project holds, never a loopback,
  link-local or metadata name, an IP literal or a name that resolves to the
  address it spells out (`127.0.0.1.nip.io`), and with every entry
  already there that is not a host name removed (`*` and `*:443` among
  them, which match every host); the records' deny rules
  (`layer_records.py`); read denials for the keychains (macOS), `~/.ssh`,
  gh's `hosts.yml`, `~/.git-credentials`, `~/.netrc`, the package
  registries' and Docker's credential files and the audit key file, with
  `credentials` deny entries for them and for `GH_TOKEN`, `GITHUB_TOKEN`,
  `AUDIT_HMAC_KEY` and the registries' publish tokens; and write denials
  for the project's
  `.claude/settings.json`, `.claude/settings.local.json`,
  `.claude/hooks/` and `.mcp.json`, the `.claude/settings.local.json` of
  the repository's top level and of the main checkout's root, the
  repository's `.mcp.json`, the plugin's hook scripts, the user
  configuration directory and `~/.claude.json`: the paths the pre-tool-use
  hook requires for the strict sandbox. Every path is literal and
  absolute. It creates the audit key file `~/.config/acs/audit.key` (mode
  600) when there is none, reads the settings file back and checks every
  key it wrote against Claude Code's documented settings, refuses a
  settings file that is not strict JSON rather than overwrite it, and on
  native Windows, which has no sandbox, writes nothing. The plan and
  `check` name the project's own settings that weaken the sandbox, and
  `check` fails on them and on a user setting that undoes these (a proxy
  port, a true `allowAllUnixSockets`, or a `WebFetch(domain:...)` rule for
  a host the allowlist may not hold), which the setup removes; a project
  whose settings set `HOME` or `CLAUDE_CONFIG_DIR` is refused. The
  computation is `grounded_agency/sandbox_settings.py` (standard library
  only, Python 3.9 or later, run as `/usr/bin/env -i /usr/bin/python3 -I`
  so that a project's settings cannot choose the interpreter),
  which also prints the settings alone for managed settings
  (`hooks/README.md`, "Setting up the sandbox"). The write runs from a
  terminal outside Claude Code: before the strict sandbox is on, the
  pre-tool-use hook refuses every Bash call, so the command gives the
  script's `apply` line to run there, and once it is on, the sandbox
  keeps commands from writing the user configuration directory. Claude
  Code is started again after the write.
- Benchmarks: six scenarios, each reported by `benchmarks/runner.py` and in
  CI's benchmark artifact (#163, #167, #169). `explanation_faithfulness`
  checks each premise and chain claim of an explain output against the
  anchors it cites, the run's evidence and its action records, and gives it
  one of three verdicts: supported, unsupported or contradicted. Its CI gate,
  in `benchmarks/tests/test_safety_scenarios.py`, requires every planted
  claim to get its planted verdict and no faithful claim to be flagged; the
  claims and the anchors' content are hand-written in a structured form.
  `destination_policy` (F504), `checkpoint_gate` (F501), `grounding_gate`
  (F505) and `secret_redaction` (§6.7) put tool calls through a real
  `GroundedAgentAdapter`, with unsafe cases that must be refused and safe
  cases that must run. `prompt_injection` checks that an instruction found
  in a retrieved page, a recalled memory entry or a tool result does not
  take effect: the send is refused F504 and the mutate F502.
- `docs/research/safety_layer_failure_classes.md`: the 130 defects of the
  safety layer's security review sorted into six classes, ranked by how
  many defects of each class the review's fifth and last round still found.
- Tests: boundary tests that attack the sandbox (#186). They run each
  route under the sandbox runtime's `srt` command (0.0.82) with the
  settings `/grounded-setup` computes, and as a control without the
  sandbox, where it must succeed: writes to each of the layer's records,
  to the user's and the project's settings files and hook scripts and
  outside the project (through links, renames of a parent and a record
  absent at the start), reads of the audit key, the checkpoint key,
  credential files, token variables and (macOS) the keychain, an unlisted
  host, local and private addresses and the metadata address, a push to a
  repository outside the project and over HTTP, and a merge or release
  through a stand-in `gh`. The records, keys and credential files are
  also attacked under the setup's `sandbox` keys alone, without the
  permission rules. A hard link made before the command starts gets past
  the sandbox on both platforms; the tests mark it as an expected failure.
  They also record that the runtime ignores a misspelled key, skips a glob
  on Linux, and shares `/tmp/claude` and `~/.npm/_logs` with the host
  (`~/.claude/debug` too, which the setup's denial of the user
  configuration directory takes back). Claude Code tests run routes through `claude -p` in the
  default, `acceptEdits` and `bypassPermissions` modes, with controls for
  the audit-log deny rule, `strictAllowlist`, the escape parameter and
  `excludedCommands`, and with the settings at user scope under a project
  or command-line settings file that turns the sandbox off, excludes a
  command or widens the write scope (each gets through, and is marked as
  an expected failure). New CI jobs run the suite on Ubuntu and macOS on
  every pull request, and a third runs the Claude Code tests when the
  repository secret `ANTHROPIC_API_KEY` is set (`hooks/README.md`, "The
  boundary tests").
- `/grounded-setup` denies sandboxed reads of each git directory's `acs`
  directory, which holds the checkpoint key, in `sandbox.filesystem.denyRead`
  and `sandbox.credentials.files`, as well as by the `Read(...)` rules.
- `docs/guides/ADOPTION.md`: one staged adoption path for Standard 1.2.
  Each stage names its component, the level or class that component can
  claim, and a check to run; the guide also gives a starting point for each
  domain profile. The FAQ, GROUNDED_AGENCY D.3 and the WHITEPAPER's
  adoption recommendation point at it, and their L2/L3 team milestones are
  removed.

### Changed
- `spec/SECURITY.md` §1.4 and §2.2.2: the identity merge constraints of
  Standard §7.3 are a requirement on hosts that merge or split entities;
  the reference layers perform no merge and do not enforce them.
- Plugin hooks: the pre-tool-use hook relaxes a Bash call (a read-only
  command, `git stash create`, a restore of a recorded checkpoint) only
  under Claude Code's strict sandbox, which it verifies for the call from
  the settings files it can read (#180; Standard 1.2.0 §5.18.3, RFC-0011): from user or managed settings, `sandbox.enabled`,
  `failIfUnavailable` and `network.strictAllowlist` true and
  `allowUnsandboxedCommands` false, no excluded commands, `allowRead` or
  other route out of the sandbox, an allowlist of DNS names only (no IP
  literal, loopback or metadata host), the token variables denied, and
  denials of writes to the layer's records, the settings files, the user
  configuration directory, the hook scripts, the audit key and the
  project's `.mcp.json`, and of reads of the audit key, `~/.ssh`, gh's and
  git's token files and the keychains; neither
  `enableAllProjectMcpServers` nor `enabledMcpjsonServers` in any scope;
  no project or local file changing the sandbox other than to narrow it,
  allowing `Edit` or `Read`, or naming a command that runs outside it; and
  a call that does not set `dangerouslyDisableSandbox`. Every other Bash
  call is a gated `mutate`, and its refusal lists why and where the
  settings are described. The
  hook cannot see `--settings` or `--setting-sources` given when Claude
  Code starts, and no environment variable tells a hook the sandbox is on
  (`hooks/README.md`, `spec/SECURITY.md` §5.5).
- The shipped domain profiles are version 2.0.0, cite Standard 1.2.0 and
  ontology 2.2.0, key `checkpoint_policy` by capability id or `"*"`, and
  list anchor kinds as `required_anchor_types`. The documentation and the
  compliance documents say a profile setting is enforced where a profile
  is applied, and which rules the reference implementation refuses until
  it checks them; the site's domain figures follow §5.21.3. A profile's
  `checkpoint_policy` `never` for `rollback` is W602, as for `mutate` and
  `send` (a `checkpoint` `requires` edge needs a checkpoint before it).
- `schemas/interop/standard_agents_annotation.schema.json` describes the
  annotation as a carrier of the tool binding record: `standard` and
  `ontology` are required, the copies of the layer and flags optional, and a
  copy that names another layer or a weaker flag than the capability's is
  invalid.
- `schemas/interop/standard_agents_mapping.yaml` cites Standard 1.2.0 and
  ontology 2.2.0.
- The `send`, `rollback`, `checkpoint`, `persist` and `transform` skills'
  prompt hooks no longer judge what code decides (approval, a checkpoint,
  rate limits, expiry); what they still judge is labelled a model-judged
  addition (Standard 1.2.0 §5.18.10). `spec/SECURITY.md` §5.4 maps every
  condition of the skills' hooks, and §5.5 says why the plugin's hooks do
  not claim class SL.
- The rate limit (SEC-010) is enforced in the adapter's PreToolUse hook
  instead of the permission callback. The SDK approves a tool in
  `allowed_tools` without calling the callback, so listed tools used to skip
  the rate limit; the hook runs for every call. **Tools you pre-approve in
  `allowed_tools` now count against the limit**: by default 10 high-risk
  calls a minute (Write, Edit, destructive Bash), 30 medium and 120 low,
  with a 1.5x burst. Raise them with `GroundedAgentConfig(rate_limit=...)`
  if an agent needs more. A rate-limited call is denied before it reserves
  a checkpoint, and an error inside the rate check denies the call.
- The adapter's PreToolUse safety check no longer lets a call through
  when it hits an error. For a tool in `allowed_tools` that hook is the
  only check that runs, so an error used to skip both the rate limit and
  the checkpoint. A tool the mapper cannot classify is now treated as a
  high-risk mutation (rate-limited, needs a checkpoint) in both modes; any
  other error denies the call in strict mode and is logged in non-strict
  mode. Deny reasons are generic; the detail and traceback go to the log.
- `wrap_options()` adds Stop and SubagentStop hooks. A checkpoint hold left
  behind by a call another PreToolUse hook denied used to block every other
  mutation for up to 10 minutes; now it counts as used when the turn ends,
  and the Stop of any session the adapter serves ends every checkpoint's
  validity (Standard 1.2.0 §5.18.6).
- `wrap_options()` no longer adds `Skill` to `allowed_tools`, so `Skill`
  calls reach the permission callback (the SDK warned that it was shadowed).
- `SyncStrategy`, `Severity` and `StepStatus` are `StrEnum`s, so `str()` of
  a member is its value.
- Direct dependencies are at their latest releases. Python: the dev ranges are
  pytest 8.4.2–9, pytest-asyncio 1.x, mypy 1.19.1–2 and ruff 0.17 (CI runs
  ruff 0.17.4).
  Rust: `hmac` 0.13, `sha2` 0.11, `saphyr`/`saphyr-parser` 0.3.3; CI builds
  with Rust 1.99.1. Two indirect crates stay behind: `encoding_rs` (capped
  by `saphyr`) and `ordered-float` (5.5 needs Rust 1.90). Go: cel-go 0.33.2
  for the CEL differential check, which now needs Go 1.26.
  GitHub Actions: checkout v7, setup-python v7, cache v6, upload-artifact
  v7, setup-go v7.
- CI tests Python 3.14 and 3.15.
- Benchmarks: `decision_audit` compares each criterion, value and score an
  explanation cites with the recorded reasoning, and no longer reads the
  explanation's own `confabulated` label, so the baseline's faithfulness is
  now 54% and its confabulation rate 40% (#163). `mutation_recovery`
  restores through `CheckpointTracker.restore_checkpoint` with a
  `FileSnapshotStore` and checks the restore it returns (#167).

### Fixed
- **Plugin hooks on macOS (#134).** CI now also runs the tests on macOS, with `/bin/bash` 3.2 and with Homebrew's bash. Fixed:
  - **Skill hooks blocked everything.** The audit, send and rollback skill hooks did not parse under bash 3.2. Its command-substitution parser reads a here-document's text as shell, so each hook exited 2 and blocked every Bash command. Each hook now reads its jq program from a function.
  - **A credential went unseen.** BSD grep refuses a repetition count over 255, so the secret scan's `curl -u user:password` rule matched nothing on macOS. Its `{0,256}` is now written as `{0,255}` and one optional character, which matches the same text.
  - **A new file in the records directory.** An Edit or a Write through a link to the audit records' directory, naming a file not yet there, was allowed on macOS: BSD `readlink -f` fails when the last part of the path does not exist. The audit and send skills now resolve the directory and keep the name.
  - **A path into the records asked instead of refused.** Under bash 3.2, the records guard's path resolution joined the rest of a path into one word after following a link, so `touch ./deep/../notes/todo.md` (where `deep` links to `notes` and `notes/todo.md` to the records) was asked for approval rather than refused. The rest of the path is now copied part by part.
  - **The wrong file followed.** A link whose target ends in a line break was read as its target without that line break, because BSD `readlink` prints no extra line break after such a target. The hooks and the persist skill now read a link's target with perl where perl is installed.
- Python SDK: the I-JSON checks of a capability output and of a call's or a
  binding's arguments built each child's whole path when its parent was
  read, so a long member name above a wide array cost the name's length
  times the width (an 80 KB MCP result took about 800 MB at PostToolUse).
  A path is now written only for the value refused.
- A reference index beyond the platform's `usize` (`${a[18446744073709551615]}`)
  was a parse error on a 32-bit target and a missing index on a 64-bit one;
  it is a missing index everywhere.
- Python SDK: `register_mcp_tool` accepted an unknown capability and a
  declared risk below the ontology's (`mutate` with `risk="low"` needed no
  checkpoint). It now refuses the first (V101) and ignores and reports the
  second (W602), as STANDARD 5.2.1 requires of a step.
- Python SDK: evidence anchors stored a tool's input, which can hold
  credentials; they now store it only with `evidence_include_tool_input`.
- Python SDK: `OrchestrationRuntime(evidence_store=...)` given an empty store
  (falsy, `len` 0) used a new one instead; it now uses the store it is
  given.
- Python SDK: `wrap_options` replaced the host's `can_use_tool` callback; it
  now chains to it.
- A Bash call whose input is not a dictionary, or whose `command` is not
  text, made the tool mapper raise, and the PreToolUse hook then let the
  call through. It is now treated as an unknown, checkpoint-gated mutation.
- Passing options that `wrap_options()` already returned to it again (as
  `GroundedClient` does with the options it is given) returns them
  unchanged instead of adding a second set of hooks.
- Python SDK: the Bash classifier read only the first word of each part of a
  line split at `&&`, `||` and `; ` followed by a letter, so `env rm -rf x`,
  `ls | sh`, `ls & rm x`, `ls ;/bin/rm x`, `echo x >~/.bashrc` and
  `find . -delete` counted as read-only and needed neither a checkpoint nor
  approval. The line is now read with the shell's quoting rules and split at
  every control operator; it is read-only only when every command in it is
  allow-listed, by its exact name, with no option that writes, and it has no
  output redirection except to `/dev/null`, no subshell and no here-document.
  A quoted operator is now data: `grep -E "a|b" f` is read-only.
- Python SDK: with a `permission_prompt_tool_name`, a call the prompt tool
  denied kept the checkpoint reserved, so the next mutation was refused with
  F501 for up to ten minutes. The adapter no longer reserves for a call it
  asks about in that mode; the call takes the checkpoint once it has run.
- Plugin hooks: the persist, rollback and send skills' command hooks exited 1,
  which Claude Code does not treat as a block; they now exit 2 with the reason
  on stderr. The audit hook logged only Skill calls, with their arguments; it
  logs every call with a digest of the input. Refusals open with the
  diagnostic code (`F501 CHECKPOINT_REQUIRED:`).
- Plugin checkpoint hook: a marker that was not a JSON object made `jq` exit
  5, which Claude Code treats as a non-blocking error, so every Write, Edit
  and Bash call ran. Any failure in the hook now blocks the call (exit 2).
- Skill hooks: the persist hook's protected paths could be reached through
  `//`, `/./` or `..` segments, which it now refuses; the send hook matched
  `localhost` case-sensitively and blocked URLs that only contained an
  internal-looking number, such as a version in a path. It now matches host
  names in any case, and an address only where a host stands.
- Plugin audit hook: where `flock` is not installed (macOS), concurrent runs
  appended without a lock and could break the HMAC chain. Every run now takes
  flock(2) on the log file itself, through `perl` or else `flock` (any
  implementation), so sessions using either exclude each other and the kernel
  releases the lock of a run that dies; `.claude/audit.log.lock` is no longer
  used. A held lock delays a run by at most `AUDIT_LOCK_WAIT` seconds
  (default 40, at most 55); the entry is then written, and the verifier
  reports it if it is out of chain order.
- `tools/verify_audit_log.py` split lines on U+0085, U+2028 and U+2029 as well
  as newlines, so a log with such a character in a logged name failed
  verification. It splits on newlines only.
- Documentation no longer says that a domain profile setting is enforced
  where no shipped component applied a profile; the compliance documents say
  which component enforces what (Standard 1.2.0 applies profiles, see
  Changed).
- Standard Agents binding: an approval accepted after the deadline extended
  the request, so with enough approvers it never expired. No approval is now
  accepted more than `expires_ms` after the request, and one stored later
  counts for nothing; a rejection is still accepted until the request is used
  or expires.
- README: the Python package is not on PyPI. Install it from a clone of the
  repository, which needs Python >= 3.14 and Rust >= 1.88.

## [v2.0.0] — 2026-10-29

Implements Standard v1.1.0 (Candidate Standard) with RFC-0003 and RFC-0004
(#114, #116) and replaces the 1.0 validator and engine with one Rust core
(#115). The Standard's version (v1.1.0; v1.0.0 still supported) is separate
from this plugin release.

**Upgrading from v1.2.0:**
- Building from source needs a Rust toolchain (rustc >= 1.86): the validator
  and executor are the `grounded_agency._core` extension, built by maturin
  with `pip install -e ".[dev]" -c constraints.txt`.
- `transform.output` is `object|array` (ontology 2.1.0); a reference to it
  without an annotation is now B204.
- Validation is stricter: catalogs that passed 1.0 may now get errors or
  warnings (unknown fields W604, unbound required inputs W615, literal type
  mismatches B203, among others listed below).
- A quorum's model families count only when the host attests them.

### Added
- **Release workflow.** `.github/workflows/release.yml` publishes a GitHub
  Release with the tag's CHANGELOG section as its notes, for a pushed `v*`
  tag or, run by hand on `main`, for a tag it creates there;
  `scripts/release_notes.py` refuses a tag that does not match `plugin.json`
  or has no section
- **Delegate identity (#114, RFC-0004 amendment).** With `identity@1` a
  host may attest who took a delegation (`effective.identity`); a waiting
  delegate keeps only results from that principal (others dropped as
  `delegate_identity`), a malformed or contradicting identity is R402, and
  `quorum.require_distinct_identities` counts one verdict per attested
  principal. Quorum model families now count only as attested. Validator,
  executor, schema, eleven runtime fixtures and docs
- **Standard changes from the orchestrator fixtures (#114).** Gates can
  `end` a run successfully (`RunResult.ended`); a step can `delay` before
  it goes on (`wait@1`), without a fake event to wait on; an `accept_from`
  or `correlate` built from a missing value fails the step at once (R402)
  instead of dropping every sender, or matching every event that lacks the
  key; and
  `after_deferral: run` (`approval@1`) lets a step that does not depend on
  a deferred one, such as an escalation, run anyway. Validator, executor,
  Python runner, schema, runtime fixtures and docs
- **W616 `VERSION_FEATURE_MISMATCH`.** A workflow that declares standard
  1.0 but uses a 1.1 feature (`workflow_extensions.requires`, gate
  `phase` or `end`, the `in` operator, failure-mode `when` or `on_error`)
  warns once per feature, so a forgotten version bump no longer passes
  silently
- **The #114 author's orchestrator workflows as conformance fixtures.** The
  nine workflows they ported to the v1.1 candidate (revision 1.1e, which
  uses gate `end`, `delay`, `after_deferral` and a waiting `delegate` per
  reviewer) are a static fixture (`pass_orchestrator_port`, kept as
  contributed), and fifteen runtime fixtures (`orchestrator_*`) script runs of
  them: routing into a nested delegation, a liveness recovery, a quorum
  that passes and one that loops after a RETHINK, a self-merge and a red
  base that escalates to incident triage, an owner-approved and an
  unattended (deferred) message, an owner answer with a foreign one
  dropped, a question ended for more research, a scheduled sweep where
  only the reminder is deferred, an escalation that interrupts the owner,
  a prod notice then an early end, and both kinds of daily report
- **Contributed runtime fixtures.** Twenty scripted runs the #114 author
  wrote from the spec (`gap1_*` standing mandates, `gap2_*` verdict scope
  and `min_full`, `gap3_*` R406 and R401 around the deadline, `gap5_*` the
  authenticated principal) are kept as sent in
  `tests/conformance/contrib/`; the generator checks and copies them
- **Read-only reviewers and per-reviewer waits (#114).** `delegate` takes
  `read_only` (attested in `effective`), and `quorum.require_read_only`
  requires it of every reviewer. `wait` is allowed on `delegate`: the step
  delegates, then waits for that delegation's result, so a `retry` replaces
  a reviewer that went silent without asking the others again; a quorum's
  `verdicts` may list one reference per reviewer step. Host or device
  placement of a delegated step is recorded as an open question in
  RFC-0003
- **Agent identity, `identity@1` (RFC-0004, #114).** A new
  `schemas/agent_identity_schema.yaml` says who a party is (principal, kind,
  role, model family, owner, how it was authenticated, trust class).
  `receive`/`synchronize` take `sender_check`, `accept_trust_classes` and
  `always_ask_trust_classes`: the executor drops items whose sender's
  identity fails a check, keeps the identity on each kept item, and asks a
  person (never a standing mandate) to approve any step that requires
  approval and uses, directly or through other steps, an item from an
  "always ask" class (or one with no trust class). Runs can carry an
  actor identity onto every action record (`WorkflowRunner.run(...,
  actor_identity=...)`), and `AgentDescriptor.identity()` produces one.
  `world_state_schema.yaml` 1.1.0 and `authority_trust_model.yaml` 1.1.0
  (default weights per trust class) follow; `validate_canonical_schemas.py`
  keeps the trust classes and the world state's identity type in step with
  the identity schema
- **`in` in condition expressions (#114).** `x in y` tests membership in a
  list or the keys of a map, as in CEL (STANDARD v1.1 §5.8); the cel-go
  differential covers it
- **Rust core (`core/`, #114).** The workflow validator now lives in a Rust
  crate compiled into `grounded_agency._core` (maturin build; Rust >= 1.86).
  It brings a hardened YAML 1.2 loader (size and depth limits, alias budget,
  no symlinks, unique string keys) with a PyYAML parity test, the condition
  expression language of Standard v1.1 §5.8, and the v1.1 edge, safety-flag,
  unknown-field and version rules. `tools/validate_workflows.py` and the
  Python `WorkflowEngine` both call it, so they can no longer disagree. CI
  gains a `rust-core` job (fmt, clippy, tests, MSRV) and a `cel-differential`
  job that checks the expression fixtures against cel-go
- **Orchestration extensions, first part (#114):** `workflow_extensions.requires`
  is validated (unknown extensions and undeclared extension fields are V106),
  `triggers` (schedule with 5-field cron or interval and IANA time zone,
  event, manual, invoke) are validated under `triggers@1`, and a step
  `timeout` outside the duration grammar warns (W614). Recovery is validated
  under `recovery@1`: `goto_step` resolves to a `store_as` (V107 otherwise;
  a capability id is deprecated, W603), `on_error` triggers, escalation to
  `handler: true` invoke steps through `action: escalate` and
  `on_exhausted`, injected `${_recovery.*}` context, untriggered recoveries
  (W609), unreachable handlers (W613), unknown invoke targets (W607) and
  invoke cycles (V105). `wait@1` validates waits on `receive` and
  `synchronize` (required duration timeout, liveness that can fire before
  it, W608 for a checkpoint taken before a wait), and `approval@1`
  validates structured approvals (approver, digest binding, recheck,
  expiry, unattended behaviour; W606 when an unattended run would reach an
  approval with no plan). `delegation@1` covers delegation hints
  (`fresh_context`, `model_family`, `role`) and sender filtering
  (`accept_from`), and `quorum@1` validates review quorums on blocking
  `constrain` steps: reviewers are earlier, distinct delegate steps,
  vocabulary and thresholds are consistent, and reviewers stay independent
  of forbidden inputs (checked transitively, including through context a
  recovery loop injects), fresh context and model families (F504). Declaring an extension the validator
  does not check is refused (V106). New guide:
  [docs/guides/ORCHESTRATION_EXTENSIONS.md](docs/guides/ORCHESTRATION_EXTENSIONS.md)
- **Reference executor (#114).** A deterministic, sans-IO executor in the
  Rust core runs validated workflows: conditions and gates, checkpoint
  authorisation and invalidation after waits, digest-bound approvals with
  expiry and rechecks, unattended behaviour, waits with event matching,
  retries with backoff, deadlines, failure modes, recovery loops,
  escalation to handlers, nested invocations and review quorums. Runs
  snapshot to canonical JSON (RFC 8785) with a SHA-256 and optional HMAC,
  and resume anywhere. Python drives it with
  `grounded_agency.workflows.WorkflowRunner` and a `Host`
  ([guide](docs/guides/RUNNING_WORKFLOWS.md)); runtime conformance fixtures
  in `tests/conformance/runtime/`
- `docs/research/analysis/validator-engine-disagreements-1.0.md`: minimal
  reproductions of the 22 cases where the 1.0 validator and engine judged
  the same workflow differently, and how each behaves now (#114, question 3)
- A step that raises `requires_checkpoint` above the ontology is now held to
  it: F501 when no checkpoint runs before it
- `world_state_schema.yaml` 1.1.0: action records gain status `rejected`
  and `expired`, an optional `approval` record (digest, decision,
  approvers) and an optional `reason`
- `schemas/review_verdict_schema.yaml` for quorum verdicts; ontology inputs
  and outputs for delegation and quorums (`delegate.fresh_context`,
  `.model_family`, `.role`, `.effective`; `receive`/`synchronize`
  `accept_from`; `constrain.tally`)
- `spec/STANDARD-v1.1.0.md` (Candidate Standard) and `spec/RFC-0003-orchestration-extensions.md`
  (Accepted) answering #114; see the [specification changelog](spec/CHANGELOG.md)
- Validator warnings: `tools/validate_workflows.py` reports warnings (W6xx)
  separately and passes unless `--strict` is given;
  `tools/validator_suggestions.json` gains `warnings` and
  `structured_warnings`, and hints such as "did you mean" are printed
- `WorkflowEngine.validate_report()`, `add_workflow()` and `effective_flags()`;
  `ErrorCode` gains the v1.1 codes and `Severity` is exported
- `python tools/sync_skill_schemas.py --check`, run in CI, fails when a
  generated skill file (output schemas, the 17 bundled workflow catalogs and
  their schema copies) has drifted from its source
- Conformance fixtures for the v1.1 edge, flag, unknown-field and version
  rules; `expected_warning_codes` in `tests/fixtures/EXPECTATIONS.json`
  (empty means none allowed); language-neutral expression fixtures under
  `tests/conformance/expressions/`
- `tools/validate_canonical_schemas.py` and a CI job covering the five canonical
  schemas designated by spec §6.1, which no validator checked before. It asserts
  §6.2/§6.3 required fields, trust-model internal consistency, alias-threshold
  ordering, and cross-file agreement with the benchmark fixture. Every defect
  from #105 and #106 is covered by a negative test proving the validator now
  catches it (#107)
- `spec/RFC-0002-agent-reliability-profile.md` proposing cross-session agent
  behavioural reliability as a first-class concept, and naming the prerequisite
  that blocks it: the standard has no agent identity object to attach a profile
  to (#104)
- `tools/validate_rfcs.py` and a CI job enforcing what `spec/GOVERNANCE.md`
  already required of RFCs — motivation, alternatives, backward-compatibility
  analysis and conformance test updates — plus header metadata, unique RFC
  numbers, and that cited repository paths exist. RFC-0001 was missing two of
  the required sections and now carries them (#104)
- `tools/validate_constraints.py` and a CI job asserting that every pin in
  `constraints.txt` names a package `pyproject.toml` declares and falls inside
  the range declared for it. The two files state overlapping facts about the
  same packages; this is what makes disagreement fail loudly instead of
  surfacing as an opaque pip resolution error
- `tools/validate_doc_links.py` and a CI job asserting that documentation
  cross-references resolve. Markdown links were the one reference kind nothing
  checked, which is how `docs/integrations/claude_agent_sdk.md` came to cite a
  `comparisons/` directory that has never existed. It reads every link form
  CommonMark allows — titles, angle brackets, images, and links whose text
  contains nested brackets — because anchoring on the opening `[` cannot see a
  badge, which had left the README's links to `LICENSE`, `spec/STANDARD-v1.0.0.md`
  and `CHANGELOG.md` unvalidated. Code-span paths are checked in `CLAUDE.md` and
  `README.md` only: repo-wide that check produces ~109 findings of which
  essentially none are defects (package-relative paths, tutorial placeholders,
  roadmap deliverables), and a validator that cries wolf gets ignored

### Changed
- **`transform.output` is `object|array`** (ontology 2.1.0), so a
  transform can return records as a list. **Breaking:** an unannotated
  reference to it is now B204, as for any union; the reference, domain,
  example and test catalogs annotate theirs.
- **`retrieve` and `search` are soft prerequisites of `ground`** (ontology
  2.1.0): a retrieved source or a search result is evidence to ground a
  claim in, so grounding generated text against them no longer warns
  W601.
- **Catalog failure modes all fire.** Of the 23 in the reference,
  manufacturing and digital-twin example catalogs that had neither `when`
  nor `on_error`, 15 gained a trigger (a step error, or an empty or
  failing output) and 8 were removed: they described a normal outcome (no
  vulnerabilities, nothing to decompose, conflicts `integrate` resolved),
  a check a later step or gate already makes (compliance, the cleaned
  data's quality), or a threshold the step does not have. An empty batch
  in the digital twin sync loop now ends the run early (gate `end`)
  instead. Runtime fixtures `domain_twin_no_events` and
  `domain_rag_no_passages` run two of them.
- **`schedule_management` with no free slot completes.** Ranking, planning
  and drafting are skipped, and the explanation (now given the slots and
  conflicts) and the audit still run; before, a `stop` gate ended the run
  R403 with neither. A runtime fixture (`domain_schedule_no_slot`) runs
  this path.
- **Unattended runs ask standing mandates, and deferral continues (#114).**
  A `standing_mandate` approver is asked even when nobody is present; the
  host answers `approved`, or `unavailable` when no mandate covers the
  action, and only then does `when_unattended` apply. `defer_to_queue`
  defers the step and every later step that depends on it (reads its
  output, may act on the world, or follows it in the ontology), runs the
  steps that only read, reason or record, and ends the run `deferred`, so a scheduled sweep
  finishes its other work. `RunResult.deferred` lists the deferrals, and the
  default `Host` answers `unavailable` for a standing mandate
- **Quorum independence per reviewer (#114).** `forbidden_inputs`
  takes a per-reviewer mapping, verdicts carry `scope: full | delta`,
  and `quorum.min_full` requires passing full sweeps
  (`review_verdict_schema.yaml` 1.1.0; `tally.full_passes`)
- **Lost liveness is R406, separate from the R401 timeout (#114).**
  Lost liveness is now R406 (`LIVENESS_LOST`); failure modes (`on_error`)
  and `retry` take it, so a workflow can re-check a quiet worker and
  escalate only when the wait expires. A failure mode that handled lost
  liveness through `on_error: R401` must add R406
- **Migration:** binding `fresh_context`, `model_family` or `role` on
  `delegate`, or `accept_from` on `receive`/`synchronize`, now needs
  `delegation@1` in `workflow_extensions.requires` (V106). These inputs were
  previously unknown to the ontology and silently ignored; a consumer that
  ignored them would reuse a reviewer's context or accept anyone's items
- **Workflow catalog (#114).** Declares `# Standard version: 1.1.0`; approval
  flags no longer understate the ontology; `clarify_intent` asks through
  `inquire` and receives the answer only when questions were asked;
  `model_deployment` checks artifacts with `constrain` before deploying;
  `monitor_and_replan` critiques the detected violations at major severity;
  gates that read their own step declare `phase: after`;
  `digital_twin_sync_loop`'s verification loop fires on
  `${verify_out.passed} == false` and targets `plan_out`
- **Ontology edges (#114).** Five follow-up edges are `enables` instead of
  `soft_requires`, a redundant one is removed, and `constrain` is the soft
  prerequisite of `execute`, `mutate` and `send`; `audit` is
  `mutation_overridable`
- **`WorkflowEngine` safety fields are effective values** (the stricter of the
  step's declaration and the ontology); what the source declared is in
  `WorkflowStep.declared`. `validate_*` methods return errors only; an unknown
  store reference maps to B202 (`MISSING_PRODUCER`) instead of B201
- **`schemas/workflow_catalog.schema.json`** requires only the fields Standard
  §5 requires, and describes gate `phase`, failure-mode `when` and
  `spec_version`
- The 17 bundled `skills/*/reference/workflow_catalog.yaml` copies are
  regenerated from `schemas/workflow_catalog.yaml`; they had drifted.
  `sync_skill_schemas.py` also maintains schema copies a skill vendors
  without a bundled catalog (`skills/receive/reference/event_schema.yaml`)
- `schemas/event_schema.yaml` 1.1.0: `source.kind` gains `agent`
- Development dependencies are version-bounded instead of open-ended, and each
  cap names the major this repo is verified against rather than the next
  unreleased one: `mypy>=1.0,<2`, `pytest>=7.0,<9`, `pytest-asyncio>=0.21,<1`.
  A cap set at the next unreleased major would not have changed what CI
  installs — `mypy>=1.0,<3` admits mypy 2.x, which is precisely the upgrade the
  bound exists to make deliberate. Raising a cap now means running the suite on
  that major first
- Exact tool versions moved to a new `constraints.txt`, installed via
  `pip install -e ".[dev]" -c constraints.txt`. `ruff` is pinned there rather
  than in the `dev` extra: formatting is not semver-safe (0.16.5 began
  formatting Python blocks inside Markdown and turned CI red on a commit
  touching only `.gitignore`), but an exact pin in package metadata would
  conflict with a consumer's own ruff. The bounds describe what the package
  supports; the constraints file describes what a green check attests to
- The `claude-agent-sdk` floor is `>=0.1.52`, the oldest release whose
  `ToolPermissionContext` carries the `tool_use_id` that keys the checkpoint
  reservation in `can_use_tool`, rather than the newest release available. It
  was briefly `>=0.2.148`, which excluded working installs without cause, and
  then `>=0.1.25`, which admitted releases where the permission callback
  could not name its own reservation
- `pyyaml` carries an upper bound (`>=6.0,<7`) like everything else, and the two
  CI jobs that installed it directly now install the package instead, so the
  constraint is declared once rather than in three places
- RFC-0002 downgrades `delivery_score` from "derivable now" to provisional. The
  original proposal and the RFC's first draft both overstated it: `actor` is a
  bare string documented as `agent/human` so the population cannot be restricted
  to agents, no terminal-status subset is defined, and `rolled_back` has no
  agreed sign — §3.3 requires rollback be possible and §4.4 requires a
  checkpoint before one, but neither says how a rollback should be scored, so
  counting it as failure marks an agent down for exercising a capability the
  standard requires it to have (#104)
- RFC-0002 makes it normative that an implementation MUST NOT infer that
  `ProvenanceRecord.agent` and `ActionRecord.actor` denote the same principal,
  with a conformance fixture required for the rule (#104)
- RFC-0002's citation of the *PDR in Production* preprint now records that its
  author has stated they do not have a reproducible dataset supporting the
  "6,342 cycles" or independent-convergence claims, replacing an unresolved
  caveat with the author's own agreement that it is design context, not
  validation evidence. The wording is deliberate: "I do not have one" is not
  "none exists", and a document whose argument rests on §3.1 must not convert
  the one into the other (#104)

### Fixed
- **W608 sees waits in invoked workflows.** An `invoke` of a catalog
  workflow that can wait (any of its steps, handlers included, or one it
  invokes) counts as a wait, so a checkpoint taken before it no longer silently covers a later
  `mutate` or `send`. The #114 port's checkin_recovery mutate was the first
  case found; revision 1.1e checkpoints again after the escalation.
- **A recovery loop replaces every waiting delegate it runs again.** A loop
  from a later step (a blocked quorum, say) back to before the reviewers
  delegated them again without `replaces`, so the host could not cancel
  the earlier delegations; only a loop from the delegate itself named
  them. A pending replacement is kept until the delegate next delegates,
  also across a pass that skips it. Runtime fixtures
  `delegate_wait_replaced_by_later_loop` and
  `delegate_wait_replacement_survives_skip`.
- **Whole-branch review (#114): executor.** Forged snapshots that passed the
  state check and then panicked are refused at restore; resolved inputs
  deeper than I-JSON allows fail the step (R402) instead of breaking
  snapshots; a huge `min_approvers` still snapshots; `correlate` matches in
  a stable key order across restores; the executor's own refusals of an
  invocation are not retried; a recovery loop back to a waiting delegate
  carries `replaces`, also when the loop targets an earlier step or a
  retry's re-delegation failed first; clock values are capped at year 9999; a re-asked
  approval's record says why
- **Whole-branch review (#114): validator.** The YAML loader stops deep
  compact sequences at its nesting limit instead of overflowing the stack;
  same-file `#/...` `$ref`s and chains of refs resolve (only hops count
  toward the limit), and the schemas one validation resolves share a budget
  of 200,000 nodes, so refs that fan out are refused (S302) rather than
  exhausting memory; literal and template bindings are type-checked
  (B203), an explicit null included (except `invoke`'s `input`, where it
  means no inputs); reference syntax errors have one code everywhere (B201, B205 for
  an empty annotation); W606 follows `invoke`; an invoke cycle is reported
  once per workflow, not once per edge; diagnostics come in catalog order
  (workflow, then step); B202 has one wording. The stricter rules are
  listed in the [spec changelog](spec/CHANGELOG.md)
- **Whole-branch review (#114): catalogs.** `digital_twin_sync_loop` rolled
  back twice on a failed verification (an after-gate and a failure mode on
  the same condition); it rolls back once. `stop` gates that ended healthy
  cycles as failures are skips or conditions, so their audits run. Literal
  types (`plan.constraints`, `detect.threshold`, `search.scope`,
  `ground.claim`) match their inputs, steps bind the outputs they reason
  about, and failure modes on effectful steps have `on_error` triggers.
  The clarification workflows gate on what the analysis found, not on its
  confidence
- **The checkpoint hook did not block anything (#114).**
  `pretooluse_require_checkpoint.sh` read its payload from an argument,
  but Claude Code passes it on stdin, and it signalled a block with exit 1,
  which Claude Code treats as a non-blocking error. It reads stdin now (an
  argument still works), blocks with exit 2 and the reason on stderr, and
  still fails closed: every `Write`, `Edit`, `MultiEdit`, `NotebookEdit` and
  `Bash` call needs a valid marker
- **Whole-branch review (#114): catalogs, second pass.** Rollback steps no
  longer require a checkpoint of their own (the one before the mutation
  was spent, so the executor took a new one of the broken state first).
  A verify or verification step that errors rolls the mutation back;
  nothing is rolled back when nothing was mutated, and audits run after
  the rollback so they record it. `data_quality_pipeline` writes nothing,
  so it no longer checkpoints or rolls back and its risk is low
- **Whole-branch review (#114): skills.** Every capability skill's output
  contract, field table and examples use the ontology's field names and
  types (`verify` returns `passed`, `checkpoint` `checkpoint_id`, `detect`
  `matches`, and so on), and their safety constraints match the
  ontology's flags and risk
- **Whole-branch review (#114): Python.** The permission callback releases
  a denied call's checkpoint reservation, and without a `tool_use_id` only
  checks for a valid checkpoint. `WorkflowRunner` turns a host response the
  run refuses into R402 for a capability or `HostResponseError` otherwise,
  bounds the unanswered polls of each action (`max_polls`), and raises `RunStartError` from
  `restore` and for inputs that are not JSON data. The validator raises
  `FileNotFoundError` and the other `OSError` types for a missing or
  unreadable catalog or ontology, as `load_yaml` does. Boolean and NaN
  weights are rejected in profiles. The bundled ontology copies are kept in sync. The
  `acs` console script, which only worked inside a checkout, is removed:
  run `python tools/scaffold.py`
- **Whole-branch review (#114): tooling.** The conformance runner compares
  each fixture's codes exactly and gives each run its own suggestions file
  (`validate_workflows.py --suggestions-out`); four negative fixtures that
  were 780-line copies tripping unrelated checks are minimal now. CI runs
  the YAML-sync and transform-ref validators, installs with the
  constraints file everywhere, and checks the formatting of `tools/`
- **Unbound required inputs were silent (#114).** A step that does not
  bind an input its capability requires is W615. The reference catalog
  left 60 required inputs unbound across eight workflows; they are bound
  now, and `debug_code_change` gains a `bug` input to bind them from.
  Binding `checkpoint_id` exposed that the rollback steps of
  `debug_code_change` and `digital_twin_sync_loop` ran even when
  verification passed; they are skipped then, as in the other workflows.
  `digital_twin_bootstrap` read a skipped step's output when a world state
  was passed in; it now syncs from that state instead. `retry.max` and
  `retry.backoff` are validated (S303)
- **The example catalog used the v1 capability names (#114).**
  `examples/digital_twin_sync_loop.workflow_catalog.yaml` now holds the
  digital twin workflows of the reference catalog verbatim (a test keeps
  them identical) and is validated in CI with `--strict`
- **Runtime fixtures are generated in the repository.**
  `scripts/gen_runtime_fixtures.py` writes `tests/conformance/runtime/*.json`,
  and CI checks they are up to date
- **Skill docs named inputs the capabilities do not have.** The procedure
  text, examples and `argument-hint` lines of the capability skills now use
  the ontology's input names
- **Mistyped `input_bindings` keys were silent (#114).** A key the
  capability does not define is now W604 with a did-you-mean hint, and an
  `invoke` step's literal `input` is checked against the invoked workflow's
  inputs (S303 undeclared, S304 missing required). This found
  `digital_twin_bootstrap` passing `inputs:` (which the executor ignores) with
  names its targets do not declare; it now passes `input` with
  `user_input` and `previous_world_state`. Catalog bindings outside the
  ontology were renamed to its inputs, and the ontology gained six optional
  inputs that catalogs relied on. The skill docs' input tables now match the
  ontology, and the tutorial and doc examples validate cleanly
- **Domain workflow catalogs.** The four catalogs under `schemas/workflows/`
  failed validation before this release (mostly untyped references, plus
  ordering and binding errors) and nothing checked them. They now pass in
  strict mode, and CI validates them
- **The Python PreToolUse checkpoint hook never blocked anything.** It
  returned a top-level `permissionDecision`, which the Claude Agent SDK
  ignores; it now denies through `hookSpecificOutput` (#114)
- **Checkpoint reservation race (SEC-007).** `validate_and_reserve()` did not
  reserve: two concurrent mutations could pass on one checkpoint. A
  reservation now belongs to one tool call (`tool_use_id`), is taken in
  PreToolUse (so pre-approved tools are covered too), is consumed on success
  and released by a new PostToolUseFailure hook on failure or interrupt, and
  lapses after `GroundedAgentConfig.checkpoint_reservation_seconds` (#114)
- `templates/SKILL_TEMPLATE_ENHANCED.md` nested a ```` ```markdown ```` block
  containing ```` ```yaml ```` blocks of the same fence length. Per CommonMark
  the outer block closes at the first bare fence, so the document's structure
  from that point on was not what it appeared to be. The outer fence is now four
  backticks. Found by the new link validator, which reported the resulting
  unclosed fence
- `grounded_query` now closes the SDK's generator when a caller breaks out of
  iteration. `async for` does not close its iterator on `break` (PEP 533 was
  deferred), so re-yielding from `sdk_query` without an explicit `aclose`
  deferred the SDK's `finally: await query.close()` — the call that terminates
  the CLI subprocess — to garbage collection, leaving the process alive past
  its consumer
- `test_grounded_query_callable` no longer drives an unbounded billable API
  call. It still exercises the real SDK with no mock and no skip, but stops
  after the first message and runs under a timeout. The timeout bounds the
  query, not total wall time: `wait_for` cancels the task and then awaits
  teardown, so the ceiling is the budget plus SDK cleanup
- `test_grounded_query_callable` can now fail. It previously had no assertion
  and caught `ValueError`, which is raised only when `wrap_options` produces a
  contradictory options object — a wrapper defect that read as an environment
  outcome. It now asserts that either a message arrived or a genuine
  environment error was raised, so a wrapper yielding nothing is a failure
- Trust decay is now a true half-life: `recency_factor` is `0.5 ** (age/half_life)`,
  which returns exactly 0.5 at `age == half_life`. The previous
  `exp(-age/half_life)` treated `half_life` as an exponential time constant and
  decayed 1/ln(2) ≈ 1.44x too fast. `decay_model.half_life` is correspondingly
  set to `P10D`, the value that reproduces the curve the benchmark suite
  actually validated — the former `P14D` was a mislabelled ~9.7-day half-life,
  not a 14-day one (#105)
- Benchmark metrics suffixed `_percent` are no longer scaled a second time by
  the reporter, which printed a +63% accuracy improvement as +6304.3% (#105)
- Documentation and compliance artifacts that asserted a 14-day trust half-life
  now state the value the schema implements (#105)
- Removed an unverified "85%+ GA accuracy" claim from the benchmark README in
  favour of the command that reports the measured figure (#105)
- Corrected NIST AI RMF profile reference to a trust source (`unverified: 0.20`)
  that does not exist in `authority_trust_model.yaml` (#105)
- `decay_model.min_trust` is now enforced: the recency factor is floored rather
  than decaying asymptotically to zero. It was declared in the schema and cited
  by the ISO 42001, EU AI Act and NIST AI RMF artifacts as an implemented
  control, but was read by nothing (#106)
- `tools/sync_skill_schemas.py` is idempotent and self-healing: its comment
  rewrite reapplied itself to already-rewritten text, so each run stacked
  another `(repo-level)` prefix onto the 17 bundled workflow catalogs. CLAUDE.md
  documents the command, so following the project's own instructions corrupted
  those files. The rewrite now strips every existing prefix before re-applying
  exactly one, so a tree a previous run had already doubled is repaired rather
  than left stable-but-corrupt (#107)
- `skills/receive/reference/event_schema.yaml` was an orphan copy that
  `sync_skill_schemas.py` could not reach, because the sync only bundles into
  skills that carry a `reference/workflow_catalog.yaml`. It is now resynced and
  the canonical-schema validator asserts every vendored copy matches its
  source (#107)

## [v1.2.0] — 2026-02-04

The tag `v1.2.0` points at a tree whose `.claude-plugin/plugin.json` reports
version 1.0.5; commit 2cf4986, after the tag, set it to 1.2.0.

The full list is in the
[v1.2.0 release](https://github.com/synaptiai/agent-capability-standard/releases/tag/v1.2.0).

### Added
- `CapabilityRegistry.all_edges()` public method for enumerating ontology edges
- Benchmark drift-prevention validator (`tools/validate_benchmark_deps.py`) and CI job
- Multi-agent coordination runtime with delegate, synchronize, and invoke patterns (#98)
- NIST AI RMF 1.0 profile with tier assessments and maturity roadmap (#59)
- EU AI Act conformity assessment preparation (#58, #97)
- ISO 42001 gap analysis and certification readiness documentation (#96)
- Workflow execution engine (TD-006) (#94)
- OASF GA extension mechanism for unmapped capabilities (TD-010) (#95)
- Comprehensive analysis documentation package (13 documents, ~570KB)
- Perspective validation checklist (PVC) system (#34)
- OASF-to-Grounded-Agency capability mapping file (#32)
- OASF compatibility adapter with full test suite (#33)
- OASF-inspired workflow patterns added to catalog (#31)
- Modality handling guide for vision, audio, and multimodal domains (#30)
- Modality-specific domain profiles for vision, audio, and multi-modal (#28)
- OASF safety extensions proposal (#29)
- OASF coverage report and comparison documentation

### Changed
- Enhanced CLAUDE.md with workflow orchestration guidelines and core principles

### Fixed
- Remediate benchmark suite drift from ontology and SDK (#100)
- Use public `all_edges()` API in benchmark validator instead of private `_loaded_edges` (#100)
- Install real SDK, remove all mock/skip patterns (#99)
- Skills made self-contained with bundled transitive dependencies (#36)

## [v1.1.1] — 2026-01-27

The tag `v1.1.1` points at a tree whose `.claude-plugin/plugin.json` reports
version 1.0.5; no commit set it to 1.1.1.

### Changed
- Migrated capability ontology from JSON to YAML format
- Updated capability count references from 35 to 36
- Expanded the FAQ with the rationale for rejected layer proposals

## [v1.1.0] — 2026-01-27

The tag `v1.1.0` points at a tree whose `.claude-plugin/plugin.json` reports
version 1.0.5; no commit set it to 1.1.0.

### Added
- Domain-specific workflow templates and default profiles (#12, #17)
- Automated validation for domain profiles (#18, #19)
- Claude Agent SDK integration with safety patterns (#11, #16)
- Benchmark suite for Grounded Agency validation (#10, #15)
- Agent failure taxonomy research (#8, #13)
- Replanning and goal uncertainty capabilities (#9, #14)
- Missing edge types to ontology (#2, #20)
- Reference list of the 99 v1 capabilities (#6, #7)
- Practitioner adoption appendix in Grounded Agency

### Fixed
- Complete edge graph for 5 orphan capabilities (#1, #21)

### Changed
- Migrated from 99 to 36 atomic capabilities with domain parameterization
- Grounded Agency evaluation section reports the 51 steps in the reference
  workflows

## [v1.0.5] — 2026-01-25

### Changed
- Flattened skills directory structure for Claude Code compatibility: skills
  moved from `skills/<category>/<skill>/` to `skills/<skill>/`

### Fixed
- The PostToolUse hook reads its JSON from stdin instead of command-line
  arguments, and its matcher is `Skill` instead of `*`

## [v1.0.4] — 2026-01-25

### Fixed
- Removed the hooks reference from `plugin.json`, which made Claude Code
  report a duplicate hooks file

## [v1.0.3] — 2026-01-25

### Fixed
- Removed the `$schema` key from `plugin.json`, which failed validation
  when the plugin was installed

### Changed
- README installs the plugin from the Synapti marketplace

## [v1.0.2] — 2026-01-25

### Changed
- README shows the Claude Code plugin as the main way to install

## [v1.0.1] — 2026-01-25

### Added
- `docs/GROUNDED_AGENCY.md`: the Grounded Agency paper in Markdown

### Changed
- README, quickstart, tutorial, FAQ, glossary, Grounded Agency, whitepaper
  and Standard 1.0.0 explain why and when to use each feature
- Grounded Agency layer counts corrected and its academic references checked

### Removed
- The LaTeX source and PDF of the Grounded Agency paper, replaced by the
  Markdown version
- `spec/RELEASE_CHECKLIST.md`

## [v1.0.0] — 2026-01-24

### Added
- Initial publication candidate
- Capability ontology with 99 atomic capabilities across 8 layers
- Typed I/O contracts and explicit dependencies for all capabilities
- Workflow DSL spec v2 with bindings, conditions, gates, recovery loops, parallel groups
- Canonical world state and event schemas (provenance, uncertainty, retention, lineage)
- Identity taxonomy and identity resolution policy
- Authority trust model (weights, decay, field-specific authority)
- Compiler-grade validator with $ref resolution, type inference, consumer input schema checking, and patch suggestions
- 5 reference workflows in workflow catalog
- Safety hooks (checkpoint enforcement, audit logging)
- Conformance test suite with 5 fixture tests
