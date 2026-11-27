# Safety-Layer Failure Classes

The security review loop on the Standard 1.2 safety layers confirmed 130
defects over five rounds: 9 high, 101 medium and 20 low. The layers it
reviewed must fail closed: the plugin's hooks and the skills' command hooks,
the Python SDK adapter and its Bash classifier, the TypeScript package, the
Standard Agents binding and the redactors. Every defect was reproduced by an
independent verifier and then fixed, with a test that fails on the code
before the fix.

This page sorts the defects into failure classes. For each class it gives
the count per round and per severity, the Standard section whose rule the
defects broke, and the test suites that now hold the fixes. The classes are
ranked by their residual trend: by the count in round 5, the last round,
then by the count in round 4.

## Classes ranked by residual trend

A round's count is the number of confirmed defects of the class found in
that round. A count that stays level from round to round means the review
keeps finding new defects of the class; a count that falls to 0 or 1 means
the fixes have closed most of it.

| Rank | Class | Round 1 | Round 2 | Round 3 | Round 4 | Round 5 | High | Medium | Low | Total | Trend |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Shell-text reading and classification | 5 | 8 | 10 | 10 | 10 | 6 | 33 | 4 | 43 | Level at 10 a round |
| 2 | Redaction coverage | 8 | 2 | 6 | 7 | 7 | 0 | 28 | 2 | 30 | Level at about 7 a round |
| 3 | Composite and nesting checks | 7 | 4 | 1 | 2 | 4 | 0 | 18 | 0 | 18 | Falling, then up to 4 |
| 4 | Trust in layer records | 3 | 6 | 3 | 3 | 1 | 1 | 7 | 8 | 16 | Falling |
| 5 | Time bounds | 5 | 0 | 0 | 2 | 1 | 0 | 4 | 4 | 8 | Low |
| 6 | Decision and checkpoint state | 9 | 5 | 0 | 0 | 1 | 2 | 11 | 2 | 15 | Closed but for 1 |
| | **All classes** | **37** | **25** | **20** | **24** | **24** | **9** | **101** | **20** | **130** | |

## What each class covers

### 1. Shell-text reading and classification

The layer reads a shell command differently from the way bash or zsh runs
it, so it classifies a command that changes or sends something as one that
only reads. Examples: quoting and ANSI-C quoting, brace and extglob
expansion, double-byte locales, `printf -v` and `{varname}` redirections
that set variables, aliases, program lookup through `PATH`, and the
configuration files that git, curl, wget, pip and npm read at run time.

- Rule broken: Standard 1.2.0 §5.18.3 (classification): a classifier's
  result applies only to what it recognises, and any argument it does not
  recognise takes the tool's worst case.
- Tests: `tests/test_bash_classification.py`,
  `tests/test_bash_program_words.py`,
  `tests/test_bash_redirections_and_braces.py`,
  `tests/test_pretooluse_hooks.py`, `tests/test_skill_hooks.py`,
  `tests/test_records_guard.py`.
- Residual: this class still yields about 10 confirmed defects a round,
  because each fix models one more feature of the shell. (The loop's own
  summary of about 20 medium defects a round counts every medium defect of
  the round; most of them are in the layers that read text, and this page
  puts the redaction and records-guard ones in their own classes.) The open
  structural answer is to classify fewer forms: take the tool's worst case
  for any command outside a small grammar. A proposed amendment of
  Standard 1.2.0 (RFC-0011, under review and not yet accepted) would make
  that the rule for shell-like tools: a call would get the tool's worst
  case unless the layer has verified that an operating-system
  boundary holds for it, with no route outside the boundary and limits on
  writes, credentials and network.

### 2. Redaction coverage

A secret reaches a record, a trace, a diagnostic or a file the layer writes:
a credential form the patterns do not recognise (cookies, Authorization
schemes, PGP and PEM keys, other JSON encoders' escapes), a record field
that is not redacted (an error message, a decision, a cancel reason, a tool
name the model chose), or a registered secret in a form it was not
registered in.

- Rule broken: Standard 1.2.0 §6.7 (secrets in records).
- Tests: `tests/test_redaction.py`, `tests/test_checkpoint_secrets.py`, the
  shared vectors in `tests/conformance/secrets/`, and the redaction tests of
  the TypeScript package and the Standard Agents binding.
- Residual: level at about 7 a round. Each new credential format or record
  field is a new defect, so the patterns and the list of redacted fields are
  kept in shared vectors that every implementation reads.
- Benchmark: the `secret_redaction` scenario writes secrets in seven forms
  to evidence, checkpoint records and call records through the shipped
  adapter, and checks that none reaches a record or file.

### 3. Composite and nesting checks

A tool that calls other tools escapes a check its nested calls need: a
nested call of a tool the binding does not define, a nested send outside
the composite's destination policy, a composite's approval covering a
nested call that needs more, or a profile rule applied to plain nested
calls but not to grounded ones.

- Rule broken: Standard 1.2.0 §5.18.4 (composite tools), with §4.4.2 for
  destination policies and §5.18.7 for approval.
- Tests: the call-sequence fixtures in `tests/conformance/calls/` (run by
  `tests/test_call_fixtures.py` and by the Standard Agents binding), and the
  binding's `nesting.test.ts`.
- Residual: falling, with 4 in round 5, all in the Standard Agents binding.

### 4. Trust in layer records

The layer trusts a record that someone other than the layer can write or
remove: checkpoint state in the work tree, a link the repository ships, a
project's settings `env`, an audit log whose last lines were cut, or a call
refused without a record.

- Rule broken: Standard 1.2.0 §5.18.8 (refusals, records and failure) and
  §6.4 (audit records).
- Tests: `tests/test_records_guard.py`, `tests/test_layer_records.py`,
  `tests/test_verify_audit_log.py`, `tests/test_checkpoint_persistence.py`,
  `tests/test_checkpoint_state_depth.py`.
- Residual: falling, with 1 in round 5.

### 5. Time bounds

A check takes time quadratic in its input, or calls a program with no time
limit, so the hook gives no verdict in time, and a host runs the call
unchecked unless the hook is set to block when it fails. A layer that
cannot finish a check must refuse the call (§5.18.8).

- Rule broken: Standard 1.2.0 §5.18.8.
- Tests: the time-bound tests in `tests/test_pretooluse_hooks.py` and the
  bounded-time tests of the redactors in `tests/test_redaction.py`.
- Residual: low, with 1 in round 5.

### 6. Decision and checkpoint state

A checkpoint or an approval covers a call it should not: a checkpoint of
another scope, one checkpoint for two calls, a turn boundary the layer did
not see, an approval decided under an earlier policy, or a hook that let a
call run when it failed.

- Rule broken: Standard 1.2.0 §5.18.5 (scope), §5.18.6 (checkpoints for
  calls) and §5.18.7 (approval for calls).
- Tests: `tests/test_checkpoint_holds.py`,
  `tests/test_hook_checkpoint_lifecycle.py`,
  `tests/test_permission_callback.py`, `tests/test_permission_modes.py`, and
  the call-sequence fixtures.
- Residual: closed but for 1 defect in round 5.
- Benchmark: the `checkpoint_gate` scenario puts gated calls without a valid
  checkpoint through the shipped adapter and checks each is refused with
  F501.

## What the counts include

The counts are the 130 confirmed defects of the five rounds. The loop's
record also numbers seven siblings that round 1 found while fixing its
reported defects and fixed in the same batches: one high, five medium and
one low. They are not in the counts above. By class they are three in
shell-text reading, two in decision and checkpoint state, one in redaction
coverage and one in time bounds.

Each defect is in exactly one class, assigned by hand from its title in
the loop's record. A defect that touched two classes, for example a
quadratic redaction pattern, is counted in the class of the check that
failed, here time bounds.
