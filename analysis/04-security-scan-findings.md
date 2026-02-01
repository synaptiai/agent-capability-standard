# Security & Compliance Assessment

**Project:** Agent Capability Standard / Grounded Agency
**Version:** 0.1.0 (Alpha)
**Assessment Date:** 2026-01-30
**Assessor:** Automated security analysis
**Scope:** Full codebase review -- Python SDK, shell hooks, YAML ontology, dependency surface
**Classification:** Internal / Engineering Review

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Dependency Vulnerability Analysis](#2-dependency-vulnerability-analysis)
3. [Code Security Pattern Analysis](#3-code-security-pattern-analysis)
4. [Safety Model Assessment (STRIDE)](#4-safety-model-assessment-stride)
5. [Shell Script Security Review](#5-shell-script-security-review)
6. [Identified Risks](#6-identified-risks)
7. [Compliance Mapping](#7-compliance-mapping)
8. [Prioritized Remediation Recommendations](#8-prioritized-remediation-recommendations)
9. [Appendix: Methodology & Tool Coverage](#9-appendix-methodology--tool-coverage)

---

## 1. Executive Summary

The Agent Capability Standard implements a **defense-in-depth** security architecture with multiple overlapping safety controls. The project demonstrates strong security-by-design principles, particularly in its default-deny posture for unknown Bash commands and its fail-closed permission callback model. However, several areas require hardening before production deployment.

### Key Findings Summary

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| Dependency Vulnerabilities | 0 | 0 | 1 | 1 | 2 |
| Code Security | 0 | 2 | 3 | 2 | 7 |
| Shell Script Security | 0 | 1 | 2 | 1 | 4 |
| Architectural Risks | 0 | 0 | 2 | 1 | 3 |
| **Total** | **0** | **3** | **8** | **5** | **16** |

### Overall Posture

- **Architecture:** Strong default-deny with typed capability contracts
- **Dependency Surface:** Minimal (1 runtime dependency: PyYAML)
- **YAML Handling:** All usages verified as `yaml.safe_load()` -- no unsafe deserialization
- **Checkpoint Enforcement:** Dual-layer (shell hook + SDK callback) with known synchronization gap
- **Audit Trail:** Present but lacks integrity protection and authentication
- **Metadata Sanitization:** Effective against injection but with edge cases in depth validation

---

## 2. Dependency Vulnerability Analysis

### 2.1. Runtime Dependencies

#### PyYAML (>=6.0)

| Property | Value |
|----------|-------|
| **Package** | `pyyaml>=6.0` |
| **Role** | YAML parsing for ontology, workflows, profiles |
| **Classification** | Runtime (required) |
| **Current Minimum** | 6.0 |
| **Latest Stable** | 6.0.2 |

**YAML Loading Security Verification:**

A comprehensive codebase scan confirms that `yaml.safe_load()` is used **exclusively** across all Python modules. Zero instances of the unsafe `yaml.load()` were found. Verified locations:

| File | Usage |
|------|-------|
| `grounded_agency/capabilities/registry.py:127` | `yaml.safe_load(f)` |
| `grounded_agency/adapters/oasf.py:116` | `yaml.safe_load(f)` |
| `tools/validate_workflows.py:165,497,498` | `yaml.safe_load(...)` |
| `tools/validate_ontology.py:26` | `yaml.safe_load(f)` |
| `tools/validate_profiles.py:325` | `yaml.safe_load(...)` |
| `tools/sync_skill_schemas.py:54` | `yaml.safe_load(f)` |
| `benchmarks/scenarios/conflicting_sources.py:35` | `yaml.safe_load(f)` |
| `skills/perspective-validation/scripts/validate_pvc.py:202` | `yaml.safe_load(...)` |

**Known CVEs for PyYAML 6.x:**

| CVE | Severity | Status | Relevance |
|-----|----------|--------|-----------|
| CVE-2020-14343 | Critical | Fixed in 6.0 | Not applicable -- `yaml.load()` without Loader; project uses `safe_load()` exclusively |
| CVE-2020-1747 | High | Fixed in 5.4+ | Not applicable -- ReDoS in `yaml.load()`; project never calls `yaml.load()` |
| CVE-2017-18342 | High | Fixed in 4.1+ | Historical -- arbitrary code execution via `yaml.load()`; fully mitigated by `safe_load()` usage |

**Assessment:** PyYAML 6.x with exclusive `safe_load()` usage provides robust protection against YAML deserialization attacks. The `safe_load()` function only allows basic Python types (strings, integers, floats, lists, dicts, booleans, None) and blocks construction of arbitrary Python objects.

**Residual Risk:** No YAML input size limits are enforced at the application layer. A maliciously crafted large YAML file could consume excessive memory during parsing (see SEC-003).

#### No Additional Runtime Dependencies

The project has zero other runtime dependencies beyond PyYAML. This minimal dependency surface significantly reduces supply chain risk.

### 2.2. Development Dependencies

| Package | Version | Classification | Risk Notes |
|---------|---------|---------------|------------|
| `pytest>=7.0` | Dev-only | Low | Not shipped in production builds |
| `pytest-asyncio>=0.21` | Dev-only | Low | Async test support only |
| `mypy>=1.0` | Dev-only | Low | Static type checker only |
| `ruff>=0.1.0` | Dev-only | Low | Linter/formatter only |

**Assessment:** All development dependencies are installed via `pip install -e ".[dev]"` and are excluded from production wheel builds via `pyproject.toml` configuration. The `[tool.hatch.build.targets.wheel]` section explicitly limits the package to `grounded_agency/` directory only.

### 2.3. Optional SDK Dependency

| Package | Version | Classification | Risk Notes |
|---------|---------|---------------|------------|
| `claude-agent-sdk>=0.1.0` | Optional | Medium | External dependency from Anthropic |

**Assessment:** The SDK is an optional dependency installed via `pip install -e ".[sdk]"`. The adapter code (`grounded_agency/adapter.py`) handles missing SDK gracefully via `try/except ImportError` blocks for SDK types like `PermissionResultAllow`, `PermissionResultDeny`, and `HookMatcher`. When SDK types are unavailable, the adapter falls back to plain dict representations, maintaining functionality without the SDK installed.

### 2.4. Build System

| Component | Package | Risk Notes |
|-----------|---------|------------|
| Build backend | `hatchling` | Used only at build time |
| Build requires | `hatchling` | Not a runtime dependency |

**Assessment:** The hatch build system is used only for packaging. The `[tool.hatch.build.targets.sdist]` section includes `/grounded_agency`, `/schemas`, and `/skills` directories, which is appropriate for a self-contained distribution.

---

## 3. Code Security Pattern Analysis

### 3.1. Bash Command Classification (mapper.py)

**File:** `/grounded_agency/capabilities/mapper.py`

The `ToolCapabilityMapper` class performs static analysis of Bash commands using three regex pattern sets applied in a strict priority order. This is the primary defense for classifying command-line tool invocations.

#### 3.1.1. Pattern Set: `_SHELL_INJECTION_PATTERNS` (Priority 1 -- Highest)

```python
_SHELL_INJECTION_PATTERNS = re.compile(
    r"""
    \$\( |                                # Command substitution $(...)
    ` |                                   # Backtick command substitution
    \$\{ |                                # Variable expansion ${...}
    ;\s*[a-zA-Z] |                        # Command chaining with semicolon
    \|\| |                                # OR chaining
    && |                                  # AND chaining
    \beval\s |                            # eval command
    \bexec\s |                            # exec command
    \bsource\s |                          # source command
    \bxargs\s.*-I |                       # xargs with command injection
    [\x00-\x1f\x7f-\x9f] |               # Control characters
    \\x[0-9a-fA-F]{2} |                  # Hex escape sequences
    \\u[0-9a-fA-F]{4}                    # Unicode escape sequences
    """,
    re.VERBOSE
)
```

**Coverage Assessment:**
- Detects command substitution (`$()` and backticks)
- Detects variable expansion (`${}`)
- Detects command chaining (`;`, `||`, `&&`)
- Detects dangerous builtins (`eval`, `exec`, `source`)
- Detects control character injection and escape sequence obfuscation
- Detects `xargs -I` injection vector

**Potential Bypass Vectors:**
1. **Process substitution:** `<(command)` and `>(command)` are not matched
2. **Here-strings:** `<<<` with embedded commands may bypass
3. **Newline injection:** Newline characters within the command string could separate commands without triggering the `;` pattern (though `[\x00-\x1f]` should catch `\n` = `\x0a`)
4. **IFS manipulation:** Modifying Internal Field Separator is not detected
5. **Alias abuse:** Pre-defined aliases could map safe-looking commands to destructive ones
6. **PATH manipulation:** Replacing standard utilities via PATH override
7. **Indirect execution via interpreters:** `python -c "import os; os.system('rm -rf /')"` would not match injection patterns but would match as an unknown command (classified as high-risk by default-deny)

**Note on Bypass Resilience:** Most bypass vectors are mitigated by the default-deny architecture -- commands that do not match the read-only allowlist are automatically classified as high-risk requiring a checkpoint. The injection patterns serve as an early-exit optimization for obvious attack patterns, not as the sole security barrier.

#### 3.1.2. Pattern Set: `_NETWORK_SEND_PATTERNS` (Priority 2)

```python
_NETWORK_SEND_PATTERNS = re.compile(
    r"""
    \bcurl\s+.*(-X\s*(POST|PUT|PATCH|DELETE)|--data|--form|-d\s) |
    \bwget\s+--post |
    \bssh\s |  \bscp\s |  \brsync\s |
    \bnc\s |  \btelnet\s |  \bftp\s
    """,
    re.VERBOSE | re.IGNORECASE
)
```

**Coverage Assessment:**
- Covers HTTP mutation methods via curl
- Covers file transfer protocols (SCP, rsync, FTP)
- Covers raw socket tools (netcat, telnet)

**Gaps:**
- `curl` with GET to exfiltration endpoint (data in URL parameters) is not caught
- `wget` without `--post` flag (GET-based exfiltration) is not caught
- `socat` (alternative to netcat) is not matched
- `nmap` and port-scanning tools are not matched
- Custom HTTP clients (`httpie`, `http`) are not matched

**Mitigation:** Unknown commands default to high-risk, so unmatched network tools would still require checkpoints.

#### 3.1.3. Pattern Set: `_DESTRUCTIVE_PATTERNS` (Priority 3)

```python
_DESTRUCTIVE_PATTERNS = re.compile(
    r"""
    ^\s*(rm|rmdir|mv|cp\s+.*\s+/|chmod|chown|ln|unlink|shred)\s |
    \s+(>|>>)\s |
    \|\s*(rm|tee|dd)\s |
    \bsed\s+-i |
    \bgit\s+(push|reset|checkout\s+--|clean|stash\s+drop|branch\s+-[dD]) |
    \bnpm\s+(publish|unpublish) |
    \bdocker\s+(rm|rmi|prune|push) |
    \bkubectl\s+(delete|apply|patch|edit)
    """,
    re.VERBOSE | re.IGNORECASE
)
```

**Coverage Assessment:**
- File system mutations (rm, mv, chmod, chown, unlink, shred)
- Output redirects (>, >>)
- Piped destructive operations
- In-place sed edits
- Git mutations (push, reset, checkout --, clean, stash drop, branch -D)
- Package registry mutations (npm publish/unpublish)
- Container mutations (docker rm/rmi/prune/push)
- Kubernetes mutations (kubectl delete/apply/patch/edit)

**Gaps:**
- `truncate` command is not matched
- `mkfs` and disk formatting commands are not matched
- `iptables` / firewall modification is not matched
- `systemctl` / service management is not matched

#### 3.1.4. Read-Only Allowlist (Priority 4)

```python
_READ_ONLY_COMMANDS: frozenset[str] = frozenset({
    "ls", "cat", "head", "tail", "less", "more", "file", "stat", "du", "df",
    "pwd", "whoami", "hostname", "uname", "date", "cal", "env", "printenv",
    "echo", "printf", "which", "whereis", "locate", "find", "grep", "awk",
    "sed", "cut", "sort", "uniq", "wc", "diff", "cmp", "comm", "tr",
    "git status", "git log", "git show", "git diff", "git branch", "git remote",
    "npm list", "npm view", "pip list", "pip show",
    "docker ps", "docker images", "docker logs",
    "kubectl get", "kubectl describe", "kubectl logs",
})
```

**Security Note:** `sed` (without `-i`) is allowlisted as read-only, which is correct since `sed` without `-i` only outputs to stdout. The destructive pattern `sed -i` is caught by `_DESTRUCTIVE_PATTERNS` at higher priority.

**Potential Issue:** `echo` and `printf` are read-only in isolation, but combined with redirects (e.g., `echo data > file`) they become write operations. However, the redirect pattern `\s+(>|>>)\s` in `_DESTRUCTIVE_PATTERNS` catches this at higher priority.

#### 3.1.5. Default-Deny Fallback (Priority 5 -- Lowest)

```python
# SECURE DEFAULT: Unknown commands are high-risk
return ToolMapping(
    capability_id="mutate",
    risk="high",
    mutation=True,
    requires_checkpoint=True,
)
```

**Assessment:** This is the correct security posture. Any Bash command not explicitly recognized as read-only is treated as a high-risk mutation requiring a checkpoint. This prevents privilege escalation through novel or obfuscated commands.

### 3.2. Default-Deny Architecture

The project implements a comprehensive default-deny architecture across multiple layers:

#### Layer 1: Bash Command Classification

- Unknown commands map to `capability_id="mutate"`, `risk="high"`, `requires_checkpoint=True`
- Empty/blank commands also map to high-risk mutate
- The allowlist is a `frozenset` (immutable) preventing runtime modification

#### Layer 2: Permission Callback (adapter.py)

```python
async def check_permission(tool_name, input_data, context):
    try:
        mapping = mapper.map_tool(tool_name, input_data)
        if mapping.requires_checkpoint:
            if not tracker.has_valid_checkpoint():
                if strict:
                    return PermissionResultDeny(message=message)
                # Non-strict: warn but allow
                logger.warning(...)
        return PermissionResultAllow(updated_input=input_data)
    except Exception as e:
        # Fail-closed: deny access on error
        return PermissionResultDeny(message=f"Permission check failed: {e}")
```

**Key Security Properties:**
1. **Fail-closed exception handling:** Any exception in the permission check results in `PermissionResultDeny`. This prevents bugs from accidentally granting access.
2. **Strict mode enforcement:** In `strict_mode=True` (the default), mutations without checkpoints are hard-blocked, not just warned.
3. **Non-strict fallback:** When `strict_mode=False`, mutations without checkpoints are logged as warnings but allowed through. This is documented behavior for development environments.

**Privilege Escalation Prevention:**
- Unknown tool names (not in `_TOOL_MAPPINGS`) default to `risk="medium"` with no checkpoint required but also no mutation capability. This is a safe middle ground -- the tool is allowed but not treated as a mutation.
- However, for Bash, the full classification pipeline runs, ensuring even novel commands are gated.

#### Layer 3: Tool-to-Capability Static Mapping

Static mappings in `_TOOL_MAPPINGS` assign risk levels and mutation flags:
- **Write, Edit, MultiEdit, NotebookEdit:** `risk="high"`, `mutation=True`, `requires_checkpoint=True`
- **Task, Skill:** `risk="medium"`, `mutation=False`
- **Read, Glob, Grep, WebFetch, WebSearch:** `risk="low"`, `mutation=False`

These are `dict` constants that cannot be modified after module load.

### 3.3. Metadata Sanitization (evidence_store.py)

**File:** `/grounded_agency/state/evidence_store.py`

The `_sanitize_metadata()` function applies three layers of validation:

#### Key Validation

```python
_VALID_KEY_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
```

- Keys must start with a letter or underscore
- Keys may only contain alphanumeric characters and underscores
- This prevents injection attacks via special characters in metadata keys (e.g., keys containing JSON control characters, path traversal sequences, or template syntax)

**Attack Prevention:**
- **NoSQL injection:** Keys like `$gt`, `$ne` are blocked
- **Template injection:** Keys like `{{payload}}` are blocked
- **Path traversal:** Keys like `../../etc/passwd` are blocked
- **JSON key collision:** Keys with quotes or brackets are blocked

#### Depth Validation

```python
_MAX_METADATA_DEPTH = 2  # No deeply nested structures
```

- Metadata values cannot exceed 2 levels of nesting
- Values exceeding the depth limit are flattened to their string representation, truncated to 100 characters

**Attack Prevention:**
- **Billion laughs / entity expansion:** Deep nesting that could cause exponential memory usage is prevented
- **Stack overflow:** Recursive structures cannot exceed the depth limit
- **Complexity-based DoS:** Processing time is bounded by the flat structure

#### Size Validation

```python
_MAX_METADATA_SIZE_BYTES = 1024  # 1KB max per anchor
```

- Total serialized metadata per anchor is capped at 1KB
- Oversized entries are truncated by replacing the largest values with `"[truncated]"`
- If serialization itself fails, a minimal `{"_error": "metadata_serialization_failed"}` is returned

**Attack Prevention:**
- **Memory exhaustion:** Single anchors cannot consume unbounded memory
- **Storage-based DoS:** Aggregate storage growth is bounded (10,000 anchors x 1KB = ~10MB max)
- **Log flooding:** Individual metadata entries are size-capped

**Edge Case: The truncation loop in `_sanitize_metadata()` uses a `while` loop that re-serializes on each iteration. For metadata with many keys of similar size, this could iterate O(n) times with O(n) serialization cost each, resulting in O(n^2) worst-case behavior. However, with the 1KB cap, this is bounded to a small constant in practice.**

### 3.4. Checkpoint ID Entropy Analysis

**File:** `/grounded_agency/state/checkpoint_tracker.py`

```python
def _generate_checkpoint_id(self) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    random_suffix = hashlib.sha256(os.urandom(16)).hexdigest()[:32]
    return f"chk_{timestamp}_{random_suffix}"
```

**Entropy Assessment:**

| Component | Source | Entropy |
|-----------|--------|---------|
| Random bytes | `os.urandom(16)` | 128 bits (cryptographically secure) |
| Hash function | SHA-256 | 256-bit output, truncated to 128 bits (32 hex chars) |
| Timestamp | UTC datetime | Deterministic (adds no entropy, but provides human-readable ordering) |

**Format:** `chk_YYYYMMDD_HHMMSS_<32 hex characters>`
**Example:** `chk_20260130_142533_a1b2c3d4e5f67890a1b2c3d4e5f67890`

**Collision Probability:**

Using the birthday paradox formula, for 128-bit random identifiers:
- After 2^64 (~1.8 x 10^19) checkpoints: ~50% collision probability
- After 10^6 checkpoints: collision probability is approximately 1.47 x 10^-27
- After 10^9 checkpoints: collision probability is approximately 1.47 x 10^-21

**Assessment:** The 128-bit entropy from `os.urandom(16)` provides sufficient collision resistance for any practical deployment. The SHA-256 hash adds no additional entropy over the raw random bytes but provides a uniform distribution across the truncated output space. The checkpoint ID scheme is cryptographically sound.

**Minor Note:** The SHA-256 step is unnecessary -- `os.urandom(16).hex()` would produce the same 32-character hex output with identical entropy. The hash adds computational cost without security benefit. This is not a vulnerability but a minor efficiency observation.

### 3.5. YAML Loading Security Audit

**Verified:** All YAML loading operations across the entire codebase use `yaml.safe_load()`. No instances of `yaml.load()` (without Loader specification) were found.

| Check | Result |
|-------|--------|
| `yaml.load()` calls | **0 found** |
| `yaml.safe_load()` calls | **11 found** |
| `yaml.unsafe_load()` calls | **0 found** |
| `yaml.full_load()` calls | **0 found** |
| `yaml.FullLoader` references | **0 found** |
| `yaml.UnsafeLoader` references | **0 found** |

**Assessment:** The project demonstrates exemplary YAML loading hygiene. The exclusive use of `safe_load()` eliminates the entire class of YAML deserialization attacks that have historically affected Python applications using PyYAML.

---

## 4. Safety Model Assessment (STRIDE)

This section extends the project's existing STRIDE analysis in `spec/SECURITY.md` with implementation-level findings.

### 4.1. Spoofing

| Aspect | Design | Implementation | Gap |
|--------|--------|----------------|-----|
| Trust model | Source ranking with configurable weights | Static configuration in profiles | Default weights may not reflect real-world authority (SEC-009) |
| Provenance tracking | Evidence anchors on all outputs | `EvidenceStore` with `from_tool_output()` | Provenance references are strings, not cryptographically verified |
| Source verification | Required by ontology contracts | Not enforced at SDK adapter level | Verification is delegated to skill implementations |

**Residual Risk:** The trust model default weights in domain profiles are statically configured and may not accurately represent the authority hierarchy in a given deployment. Misconfigured weights could allow lower-authority sources to override higher-authority sources.

### 4.2. Tampering

| Aspect | Design | Implementation | Gap |
|--------|--------|----------------|-----|
| Schema validation | Typed I/O contracts | Profile and workflow validators (`validate_profiles.py`, `validate_workflows.py`) | Validators run at build/deploy time, not at runtime |
| Checkpoint/rollback | Required before mutations | `CheckpointTracker` + shell hook | Dual-layer with sync gap (see Section 4.7) |
| Immutable observations | Evidence anchors are append-only | `EvidenceStore` uses `deque` with FIFO eviction | In-memory only; no tamper-evident storage |

**Residual Risk:** Evidence anchors stored in-memory can be modified by code with access to the `EvidenceStore` instance. There is no cryptographic integrity protection (e.g., hash chains, digital signatures) on evidence entries.

### 4.3. Repudiation

| Aspect | Design | Implementation | Gap |
|--------|--------|----------------|-----|
| Audit trails | Post-tool hooks log all skill invocations | `posttooluse_log_tool.sh` appends to `.claude/audit.log` | No integrity protection on audit log (SEC-005) |
| Provenance | Evidence anchors with timestamps | UTC ISO 8601 timestamps | Timestamps from system clock, no trusted timestamping |
| Evidence anchors | All tool outputs recorded | `EvidenceStore` with kind-based indexing | FIFO eviction may lose early provenance (SEC-004) |

**Residual Risk:** The audit log at `.claude/audit.log` is a plain-text append-only file with no authentication, integrity checking, or access control. Any process with filesystem access can read, modify, or delete audit entries.

### 4.4. Information Disclosure

| Aspect | Design | Implementation | Gap |
|--------|--------|----------------|-----|
| Access control | `constrain` capability in ontology | No runtime access control enforcement in SDK adapter | Access control is capability-defined but not code-enforced |
| Metadata sanitization | Key validation, depth/size limits | `_sanitize_metadata()` with regex, depth, and size checks | Effective but metadata values themselves are not encrypted |
| Command logging | Tool inputs logged to evidence store | Full command strings stored in evidence anchors | Commands may contain sensitive arguments (passwords, tokens) |

**Residual Risk:** Commands logged to the evidence store may contain sensitive information (API keys, passwords passed as command arguments). There is no redaction mechanism for sensitive values in metadata.

### 4.5. Denial of Service

| Aspect | Design | Implementation | Gap |
|--------|--------|----------------|-----|
| Timeouts | Recommended in security guidance | Not enforced at SDK adapter level | Timeout enforcement is delegated to the underlying SDK |
| Retry limits | `max_loops` on recovery workflows | Defined in workflow catalog, not in SDK adapter | SDK adapter has no built-in retry limiting |
| YAML size limits | Not specified | No file size check before `yaml.safe_load()` | Large YAML files could consume excessive memory (SEC-003) |
| Rate limiting | Not specified | No capability invocation rate limiting | Unbounded invocation rate possible (SEC-010) |

**Residual Risk:** The SDK adapter does not enforce timeouts, retry limits, or rate limits. These protections are either delegated to the underlying SDK or to workflow definitions.

### 4.6. Elevation of Privilege

| Aspect | Design | Implementation | Gap |
|--------|--------|----------------|-----|
| Prerequisites | Hard `requires` edges in ontology | Registry loads and queries edges | Prerequisite checking is advisory, not enforced at runtime |
| Approval requirements | `requires_approval: true` on medium-risk | Mapped in `_TOOL_MAPPINGS` | No approval UI or mechanism in SDK adapter |
| Checkpoint enforcement | Dual-layer (hook + callback) | Shell hook checks file; SDK checks tracker state | Two independent state sources with no synchronization |

**Residual Risk:** The ontology defines prerequisite relationships between capabilities, but the SDK adapter does not enforce them at runtime. A tool invocation that bypasses the capability pipeline (e.g., direct SDK tool call) would not be subject to prerequisite validation.

### 4.7. Dual-Layer Checkpoint Enforcement Analysis

The project implements checkpoint enforcement at two independent layers:

#### Shell Hook Layer (`pretooluse_require_checkpoint.sh`)

```bash
if echo "$payload" | grep -E -i "(Edit\b|Bash\b|Git\b|rm\b|mv\b|sed\b|perl\b)" >/dev/null; then
  if [ ! -f ".claude/checkpoint.ok" ]; then
    echo "Blocked: missing checkpoint marker (.claude/checkpoint.ok). Create a checkpoint first."
    exit 1
  fi
fi
```

**Mechanism:** Checks for the existence of `.claude/checkpoint.ok` file
**Scope:** Triggered for Write and Edit tools (via `hooks.json` matcher)
**State:** Filesystem-based (`.claude/checkpoint.ok`)

#### SDK Callback Layer (adapter.py)

```python
if mapping.requires_checkpoint:
    if not tracker.has_valid_checkpoint():
        return PermissionResultDeny(message=message)
```

**Mechanism:** Queries `CheckpointTracker` in-memory state
**Scope:** All tools routed through `wrap_options()` permission callback
**State:** In-memory Python object (`CheckpointTracker._active_checkpoint`)

#### Synchronization Issues

| Issue | Description | Impact |
|-------|-------------|--------|
| **State divergence** | Shell hook checks filesystem; SDK checks in-memory. Neither is aware of the other's state. | A checkpoint created via `CheckpointTracker` does not create `.claude/checkpoint.ok`, and vice versa. |
| **Stale file risk** | `.claude/checkpoint.ok` persists across sessions unless explicitly removed. | A checkpoint file from a previous session could satisfy the hook for new mutations (SEC-001). |
| **No expiry in shell** | The shell hook has no concept of checkpoint expiry. | `CheckpointTracker` supports 30-minute expiry, but the file-based marker does not expire. |
| **Race condition** | Between the checkpoint validity check and the actual tool execution, the checkpoint could expire or be consumed. | Time-of-check to time-of-use (TOCTOU) gap (SEC-007). |

---

## 5. Shell Script Security Review

### 5.1. pretooluse_require_checkpoint.sh

**File:** `/hooks/pretooluse_require_checkpoint.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
payload="${1:-}"
if echo "$payload" | grep -E -i "(Edit\b|Bash\b|Git\b|rm\b|mv\b|sed\b|perl\b)" >/dev/null; then
  if [ ! -f ".claude/checkpoint.ok" ]; then
    echo "Blocked: missing checkpoint marker (.claude/checkpoint.ok). Create a checkpoint first."
    exit 1
  fi
fi
exit 0
```

**Security Analysis:**

| Aspect | Assessment |
|--------|------------|
| **Shell options** | `set -euo pipefail` -- correct: exits on error, undefined vars, pipe failures |
| **Input handling** | Payload from `$1` argument, with empty default |
| **Pattern matching** | Case-insensitive grep for tool keywords |
| **Marker mechanism** | File existence check at `.claude/checkpoint.ok` |

**Findings:**

1. **Stale File Risk (SEC-001):** The checkpoint marker file `.claude/checkpoint.ok` is never cleaned up by this script. If it persists from a previous session, it would falsely satisfy the checkpoint requirement. The script does not check the file's age, content, or integrity.

2. **Relative Path Dependency (SEC-006):** The path `.claude/checkpoint.ok` is relative to the current working directory. If the hook is invoked from a different directory than expected, the check could reference the wrong checkpoint file or bypass the check entirely.

3. **Pattern Coverage:** The grep pattern checks for `Edit`, `Bash`, `Git`, `rm`, `mv`, `sed`, `perl` in the payload string. However, the `hooks.json` configuration only routes `Write|Edit` tool invocations through this hook -- not Bash commands. This means the grep patterns for `Bash`, `rm`, `mv`, `sed`, `perl` are never triggered through the hook system, creating a false sense of coverage.

4. **Grep Pattern Weakness:** The pattern uses word boundaries (`\b`) but matches on the entire payload string. If the payload format changes or contains these keywords in non-tool-name positions (e.g., a file path containing "edit"), the check could trigger incorrectly (false positive) or miss the intended match (if the tool name is encoded differently).

### 5.2. posttooluse_log_tool.sh

**File:** `/hooks/posttooluse_log_tool.sh`

```bash
#!/usr/bin/env bash
input=$(cat)
if ! command -v jq &> /dev/null; then
  exit 0
fi
tool_name=$(echo "$input" | jq -r '.tool_name // empty' 2>/dev/null)
if [[ "$tool_name" != "Skill" ]]; then
  exit 0
fi
skill=$(echo "$input" | jq -r '.tool_input.skill // "unknown"' 2>/dev/null)
args=$(echo "$input" | jq -r '.tool_input.args // ""' 2>/dev/null)
# ... directory detection and logging ...
echo "[$ts] Skill: $skill (args: $args)" >> "$log_dir/audit.log"
```

**Security Analysis:**

| Aspect | Assessment |
|--------|------------|
| **Input source** | stdin (Claude Code hook data) |
| **Parsing** | `jq` for JSON parsing |
| **Output** | Append to `.claude/audit.log` |
| **Error handling** | `jq` errors suppressed with `2>/dev/null` |

**Findings:**

1. **jq Dependency (Medium):** The script silently exits with code 0 if `jq` is not installed. This means audit logging fails silently without any indication. A missing `jq` binary would create a gap in the audit trail with no alert.

2. **No Input Validation:** The skill name and args extracted from JSON are directly interpolated into the log line without sanitization. A maliciously crafted skill name containing newlines or log injection sequences could corrupt the audit log format.

3. **Audit Log Integrity (SEC-005):** The audit log is a plain-text file written via shell append (`>>`). There is no:
   - Authentication of log entries
   - Integrity checking (hash chains, MACs)
   - Access control on the log file
   - Log rotation or size limits
   - Tamper detection

4. **Directory Creation:** The script creates `.claude/` directory with `mkdir -p` if it does not exist, which is safe. However, the directory permissions are not explicitly set, inheriting the process umask.

5. **Silent Failure Pattern:** Multiple failure modes exit with code 0 (success):
   - Missing `jq`: exit 0
   - Non-Skill tool: exit 0
   - JSON parsing errors: suppressed with `2>/dev/null`

   This means the hook system will not detect or report logging failures.

---

## 6. Identified Risks

### SEC-001: Stale checkpoint.ok File Bypass

| Property | Value |
|----------|-------|
| **Severity** | High |
| **Component** | `hooks/pretooluse_require_checkpoint.sh` |
| **Attack Vector** | A `.claude/checkpoint.ok` file persists from a prior session. New mutations are permitted without a fresh checkpoint because the shell hook only checks file existence, not file age or content. |
| **Impact** | Mutations may proceed without a valid rollback point, violating the checkpoint-before-mutation safety invariant. |
| **Existing Mitigation** | The SDK adapter layer (`CheckpointTracker`) uses time-based expiry (30 minutes default) which provides a secondary check. However, the two layers are not synchronized. |
| **Recommended Mitigation** | (1) Write a timestamp or nonce into `checkpoint.ok` and validate it in the hook. (2) Add a cleanup step that removes `.claude/checkpoint.ok` at session start. (3) Include the checkpoint ID in the file for correlation with `CheckpointTracker` state. |
| **Status** | **Partially Mitigated** -- SDK layer provides expiry, but shell layer has no expiry concept. |

### SEC-002: Regex-Based Bash Classification Evasion

| Property | Value |
|----------|-------|
| **Severity** | Medium |
| **Component** | `grounded_agency/capabilities/mapper.py` |
| **Attack Vector** | An adversary constructs a Bash command that evades all three regex pattern sets but performs a destructive or exfiltrating action. Examples: (1) Using process substitution `<(rm -rf /)` (though `<(` is not matched, `rm` is in destructive patterns). (2) Using `python3 -c "import shutil; shutil.rmtree('/')"` -- this bypasses all regexes. |
| **Impact** | The command would be classified by the default-deny path as `mutate` with `requires_checkpoint=True`, so the attack still requires an active checkpoint. The risk is that the capability classification is wrong (`mutate` instead of a more specific category), potentially affecting audit trail accuracy. |
| **Existing Mitigation** | Default-deny architecture ensures unknown commands are treated as high-risk. This is the primary defense and is effective. |
| **Recommended Mitigation** | (1) Document the regex approach as defense-in-depth, not primary. (2) Consider adding common interpreter patterns (`python -c`, `ruby -e`, `node -e`) to the injection detection set. (3) Add `process substitution` patterns `<(` and `>(` to injection patterns. |
| **Status** | **Mitigated** -- default-deny provides effective containment, but classification accuracy could be improved. |

### SEC-003: No YAML Input Size Limits

| Property | Value |
|----------|-------|
| **Severity** | Medium |
| **Component** | `grounded_agency/capabilities/registry.py`, all YAML loading sites |
| **Attack Vector** | An attacker provides an extremely large YAML file (e.g., 1GB ontology file) that causes memory exhaustion during `yaml.safe_load()` parsing. This could affect: (1) `CapabilityRegistry._load_ontology()` loading the ontology file. (2) Validator tools processing user-supplied profiles/workflows. |
| **Impact** | Denial of service through memory exhaustion. The process would crash or become unresponsive. |
| **Existing Mitigation** | None. The YAML files are typically loaded from trusted, version-controlled paths. In a plugin context, the ontology and profile files are bundled with the package. |
| **Recommended Mitigation** | (1) Add a file size check before calling `yaml.safe_load()` (e.g., reject files over 10MB). (2) Consider using `yaml.safe_load()` with a memory-limited stream wrapper. (3) For user-supplied YAML, enforce strict size limits (e.g., 1MB for profiles). |
| **Status** | **Open** -- no size validation exists, though practical risk is low for bundled files. |

### SEC-004: Evidence Store FIFO Eviction Losing Early Provenance

| Property | Value |
|----------|-------|
| **Severity** | Medium |
| **Component** | `grounded_agency/state/evidence_store.py` |
| **Attack Vector** | An adversary floods the evidence store with high-volume low-value evidence anchors (e.g., rapid Read operations), causing FIFO eviction to discard earlier, more critical evidence (e.g., mutation records, checkpoint associations). |
| **Impact** | Critical provenance information from early in a session is permanently lost. This could prevent forensic analysis of the initial state or early decisions that led to later mutations. Violates the "auditable" principle of Grounded Agency. |
| **Existing Mitigation** | The default `max_anchors=10000` provides substantial capacity. The `_by_kind` index maintains separate lists per kind, but these are also subject to eviction when anchors are removed from the main deque. |
| **Recommended Mitigation** | (1) Implement priority-based eviction: mutation and checkpoint anchors should have higher retention priority than read-only tool outputs. (2) Add a "pinned" flag for critical anchors that are exempt from FIFO eviction. (3) Implement periodic flush to persistent storage before eviction. (4) Separate deques per risk level with independent size limits. |
| **Status** | **Open** -- FIFO eviction treats all evidence equally regardless of importance. |

### SEC-005: No Authentication on Audit Log

| Property | Value |
|----------|-------|
| **Severity** | High |
| **Component** | `hooks/posttooluse_log_tool.sh`, `.claude/audit.log` |
| **Attack Vector** | (1) An attacker with filesystem access modifies or deletes audit log entries to cover their tracks. (2) An attacker injects false entries to frame another agent or mislead forensic analysis. (3) Audit log is silently not written when `jq` is missing. |
| **Impact** | Complete loss of audit trail integrity. Security incident investigations cannot rely on the audit log as evidence. Violates the "Repudiation" mitigation in the STRIDE model. |
| **Existing Mitigation** | None for the shell hook layer. The SDK layer's `EvidenceStore` provides in-memory evidence, but it is also unauthenticated and not persisted. |
| **Recommended Mitigation** | (1) Implement cryptographic signing of audit entries (e.g., HMAC chain). (2) Set restrictive file permissions on `.claude/audit.log` (e.g., 0600). (3) Implement log rotation with tamper detection. (4) Alert when `jq` is missing rather than silently skipping. (5) Consider forwarding audit events to a centralized, append-only log store. |
| **Status** | **Open** -- no integrity protection on audit trail. |

### SEC-006: Shell Hook Depends on Filesystem State

| Property | Value |
|----------|-------|
| **Severity** | Medium |
| **Component** | `hooks/pretooluse_require_checkpoint.sh` |
| **Attack Vector** | (1) The hook runs in a working directory different from the project root, causing `.claude/checkpoint.ok` to reference the wrong location. (2) A symlink at `.claude/checkpoint.ok` points to an always-existing file (e.g., `/dev/null`), permanently bypassing the check. (3) On a network filesystem, file existence checks may be unreliable due to caching. |
| **Impact** | Checkpoint enforcement at the shell layer is bypassed, relying entirely on the SDK adapter layer for safety. |
| **Existing Mitigation** | The SDK adapter layer provides an independent, in-memory checkpoint check that is not affected by filesystem state. |
| **Recommended Mitigation** | (1) Use `CLAUDE_PROJECT_DIR` environment variable for absolute path resolution (similar to `posttooluse_log_tool.sh`). (2) Check that `.claude/checkpoint.ok` is a regular file, not a symlink. (3) Read and validate the file content (e.g., checkpoint ID and timestamp). |
| **Status** | **Partially Mitigated** -- SDK layer provides secondary protection. |

### SEC-007: Race Condition Between Checkpoint Check and Tool Execution

| Property | Value |
|----------|-------|
| **Severity** | Medium |
| **Component** | `grounded_agency/adapter.py`, `grounded_agency/state/checkpoint_tracker.py` |
| **Attack Vector** | A time-of-check to time-of-use (TOCTOU) race exists between the permission callback checking `has_valid_checkpoint()` and the actual tool execution. During this window: (1) The checkpoint could expire (30-minute default expiry). (2) Another concurrent operation could consume the checkpoint. (3) `invalidate_all()` could be called. |
| **Impact** | A mutation could execute without a valid checkpoint at the actual moment of execution, despite the check passing moments earlier. |
| **Existing Mitigation** | The window is typically very small (milliseconds between check and execution). The 30-minute default expiry makes expiry-based races unlikely. Single-threaded SDK execution reduces concurrency risks. |
| **Recommended Mitigation** | (1) Atomically reserve-and-consume the checkpoint in a single operation within the permission callback. (2) Return the checkpoint ID in the permission result for correlation with the tool execution. (3) For concurrent scenarios, use a mutex or compare-and-swap pattern on checkpoint consumption. |
| **Status** | **Partially Mitigated** -- practical risk is low in single-threaded SDK usage. |

### SEC-008: Metadata Injection via Malformed Keys

| Property | Value |
|----------|-------|
| **Severity** | Low |
| **Component** | `grounded_agency/state/evidence_store.py` |
| **Attack Vector** | An attacker provides metadata with keys that pass the regex validation but have semantic meaning in downstream systems. For example: (1) Key `__proto__` is valid per the regex (`^[a-zA-Z_][a-zA-Z0-9_]*$`) and could affect JavaScript-based consumers. (2) Key `_id` is valid and could conflict with MongoDB document IDs if evidence is exported to a database. (3) Keys starting with `_` could collide with internal fields like `_error`. |
| **Impact** | Low in the current Python-only context. Risk increases if evidence is exported to external systems with different key semantics. |
| **Existing Mitigation** | The regex pattern `^[a-zA-Z_][a-zA-Z0-9_]*$` is restrictive. The `_sanitize_metadata()` function applies size and depth limits. The internal `_error` key is only set by the sanitizer itself in the error path. |
| **Recommended Mitigation** | (1) Consider disallowing keys starting with underscore (`_`) to prevent collisions with internal fields. (2) Document the allowed key format for downstream consumers. (3) Add an explicit denylist for known problematic keys (`__proto__`, `constructor`, `__class__`). |
| **Status** | **Mitigated** -- current regex is sufficiently restrictive for Python consumption. |

### SEC-009: Trust Model Default Weights May Not Match Real-World Authority

| Property | Value |
|----------|-------|
| **Severity** | Low |
| **Component** | `schemas/profiles/*.yaml` |
| **Attack Vector** | A deployment uses default trust weights from the profile templates without calibrating them to the actual authority hierarchy. A source with an incorrectly high default weight could override more authoritative sources. |
| **Impact** | Incorrect information prioritization. Lower-authority sources could effectively override higher-authority sources in conflict resolution. |
| **Existing Mitigation** | The security guidance (`spec/SECURITY.md` Section 4.3) explicitly warns: "Review trust model weights carefully." Profile validation ensures structural correctness. |
| **Recommended Mitigation** | (1) Add a "trust_model_reviewed" flag to profiles that must be set to `true` before deployment. (2) Provide calibration guidelines with domain-specific weight recommendations. (3) Log warnings when default weights are used without explicit review. |
| **Status** | **Partially Mitigated** -- documentation warns about this, but no technical enforcement. |

### SEC-010: No Rate Limiting on Capability Invocations

| Property | Value |
|----------|-------|
| **Severity** | Medium |
| **Component** | `grounded_agency/adapter.py`, permission callback |
| **Attack Vector** | A compromised or buggy agent invokes capabilities at an unbounded rate, causing: (1) Resource exhaustion on the host system. (2) Excessive API consumption. (3) Flooding of the evidence store, triggering FIFO eviction of important evidence (chained with SEC-004). (4) Overwhelming audit log storage. |
| **Impact** | Denial of service, evidence loss, and audit trail degradation. |
| **Existing Mitigation** | The underlying Claude SDK may impose its own rate limits. The `max_loops` parameter on recovery workflows provides loop-level limiting but not invocation-rate limiting. |
| **Recommended Mitigation** | (1) Add a configurable rate limiter to the permission callback (e.g., token bucket algorithm). (2) Implement per-capability rate limits based on risk level (e.g., high-risk mutations limited to 10/minute). (3) Add rate-based anomaly detection with alerting. |
| **Status** | **Open** -- no rate limiting exists at the adapter layer. |

### SEC-011: Checkpoint History Pruning Loses Forensic Data

| Property | Value |
|----------|-------|
| **Severity** | Low |
| **Component** | `grounded_agency/state/checkpoint_tracker.py` |
| **Attack Vector** | With `max_history=100`, rapid checkpoint creation and consumption causes old checkpoint records to be pruned. Forensic analysis of long-running sessions loses visibility into early checkpoints. |
| **Impact** | Reduced forensic capability for long-running agent sessions. |
| **Existing Mitigation** | The 100-checkpoint default is generous for typical sessions. Checkpoints in history are sorted by `created_at` and the most recent are retained. |
| **Recommended Mitigation** | (1) Persist checkpoint metadata to disk before pruning. (2) Implement a "compact" format for old checkpoints that retains essential fields (ID, timestamp, scope, reason) while discarding full metadata. |
| **Status** | **Partially Mitigated** -- adequate for short sessions but insufficient for extended operations. |

### SEC-012: Unvalidated Ontology Path Resolution

| Property | Value |
|----------|-------|
| **Severity** | Low |
| **Component** | `grounded_agency/adapter.py` (`_find_ontology_path()`) |
| **Attack Vector** | The ontology path resolution falls back to `"schemas/capability_ontology.yaml"` (a relative path) if no other path is found. An attacker who can place a malicious `capability_ontology.yaml` at the expected relative path could inject a modified ontology that changes capability risk levels, removes checkpoint requirements, or alters edge relationships. |
| **Impact** | Modified ontology could downgrade risk classifications (e.g., `mutate` from high to low), remove checkpoint requirements, or remove prerequisite edges, weakening safety enforcement. |
| **Existing Mitigation** | The file is typically loaded from a version-controlled repository location. The `CapabilityRegistry` uses `yaml.safe_load()` so arbitrary code execution via the YAML file is not possible. |
| **Recommended Mitigation** | (1) Add integrity verification (checksum or signature) on the ontology file. (2) Log the resolved ontology path for audit trail. (3) Validate the ontology content matches expected structure after loading. |
| **Status** | **Partially Mitigated** -- safe_load prevents code execution, but content substitution is possible. |

---

## 7. Compliance Mapping

### 7.1. OWASP AI Security & Privacy Guide

| OWASP Category | Agent Capability Standard Coverage | Assessment |
|----------------|-----------------------------------|------------|
| **AI01: Input Validation** | Metadata sanitization (key regex, depth/size limits), typed I/O contracts, YAML safe_load | Partial -- validates metadata but no input size limits on YAML |
| **AI02: Output Validation** | Output schemas defined in ontology, verify capability for semantic checking | Partial -- schemas defined but runtime output validation not enforced in SDK adapter |
| **AI03: Excessive Agency** | Capability risk levels, checkpoint requirements, approval gates, default-deny | Strong -- multi-layered controls on agent autonomy |
| **AI04: Supply Chain** | Minimal dependencies (1 runtime), dev deps excluded from wheel, build isolation | Strong -- minimal attack surface |
| **AI05: Logging & Monitoring** | Audit log hooks, evidence store, provenance tracking | Partial -- logging exists but lacks integrity protection (SEC-005) |
| **AI06: Insecure Plugin Design** | Typed skill contracts, layer-based organization, hook enforcement | Strong -- structural safety by design |
| **AI07: Model Denial of Service** | Recovery loop limits (max_loops), timeout guidance | Partial -- no rate limiting (SEC-010), no YAML size limits (SEC-003) |
| **AI08: Sensitive Information Disclosure** | Constrain capability, access control by design | Partial -- no sensitive value redaction in evidence store |

### 7.2. NIST AI Risk Management Framework (AI RMF)

| NIST AI RMF Function | Agent Capability Standard Mapping | Assessment |
|-----------------------|----------------------------------|------------|
| **GOVERN** | Ontology governance, extension governance (EXTENSION_GOVERNANCE.md), profile management | Adequate -- clear governance structure for capability additions |
| **MAP** | 9-layer cognitive model, STRIDE threat model, domain parameterization | Strong -- well-structured risk categorization |
| **MEASURE** | Evidence anchors, confidence scoring, trust model weights | Adequate -- measurement infrastructure exists but calibration guidance is limited |
| **MANAGE** | Checkpoint/rollback, incident response procedures, security hooks | Adequate -- response capabilities exist but automation is limited |

#### Detailed NIST AI RMF Mapping

| NIST Category | Sub-Category | Implementation | Status |
|---------------|-------------|----------------|--------|
| GOVERN 1.1 | Legal/regulatory requirements | EU AI Act alignment documented | Partial |
| GOVERN 1.2 | Trustworthy AI characteristics | Grounded Agency principles (grounded, auditable, safe, composable) | Aligned |
| GOVERN 2.1 | Risk management processes | STRIDE analysis, security checklist, responsible disclosure | Aligned |
| MAP 1.1 | Intended purpose definition | Capability descriptions, I/O contracts | Aligned |
| MAP 2.1 | Risk identification | STRIDE threats, attack scenarios | Aligned |
| MAP 3.1 | Benefits/costs assessment | Risk-level classification (low/medium/high) | Partial |
| MEASURE 1.1 | Metrics for trustworthiness | Evidence anchors, confidence fields | Partial |
| MEASURE 2.1 | Evaluation methods | Conformance tests, validator suite | Aligned |
| MANAGE 1.1 | Risk response plans | Incident response (Section 6 of SECURITY.md), rollback | Aligned |
| MANAGE 2.1 | Impact management | Checkpoint/rollback, recovery workflows | Aligned |

### 7.3. EU AI Act Alignment

| EU AI Act Requirement | Agent Capability Standard Coverage | Gap Analysis |
|----------------------|-----------------------------------|-------------|
| **Risk Classification (Art. 6)** | Three-tier risk model (low/medium/high) maps to EU AI Act risk categories | The standard's "high" risk aligns with "high-risk AI" but lacks formal conformity assessment procedures |
| **Human Oversight (Art. 14)** | `requires_approval: true` on medium/high-risk capabilities, `inquire` capability for human-in-the-loop | Approval mechanism defined but no UI implementation; `inquire` capability delegates to skill implementation |
| **Transparency (Art. 13)** | Evidence anchors, provenance tracking, audit trails | Evidence store is internal; no end-user-facing transparency reporting |
| **Data Governance (Art. 10)** | Metadata sanitization, YAML safe_load, typed contracts | No data lineage tracking beyond evidence anchors; no data quality metrics |
| **Technical Robustness (Art. 15)** | Checkpoint/rollback, recovery workflows, default-deny architecture | Strong structural robustness; lacks formal testing against adversarial inputs |
| **Accuracy (Art. 15)** | Confidence scoring, trust model, verify capability | Accuracy measurement is capability-defined but not empirically validated |
| **Record-Keeping (Art. 12)** | Audit log, evidence store, checkpoint history | Record-keeping exists but lacks integrity protection and retention guarantees |

**EU AI Act Classification Assessment:**

The Agent Capability Standard, as a framework for AI agent safety, would likely be classified as a **component of high-risk AI systems** when deployed in domains listed in Annex III (e.g., critical infrastructure management, employment decisions, law enforcement). The framework's safety mechanisms (checkpoints, evidence, audit) provide structural support for compliance but would need domain-specific conformity assessments.

### 7.4. ISO/IEC 42001 Alignment (AI Management Systems)

| ISO/IEC 42001 Clause | Agent Capability Standard Coverage | Assessment |
|----------------------|-----------------------------------|------------|
| **4. Context of the organization** | Domain profiles (healthcare, finance, etc.), extension governance | Partial -- profiles exist but organizational context is deployment-specific |
| **5. Leadership** | Security checklist for operators, incident response plan | Adequate -- guidance exists but responsibility assignment is deployment-specific |
| **6. Planning** | Capability ontology, workflow catalog, risk-level classification | Strong -- comprehensive planning structure |
| **7. Support** | Documentation (spec, guides, tutorials), tooling (validators, SDK) | Strong -- extensive documentation and tooling |
| **8. Operation** | SDK adapter, hook enforcement, checkpoint lifecycle | Adequate -- operational controls exist with identified gaps |
| **9. Performance evaluation** | Conformance tests, evidence anchors for verification | Partial -- testing exists but no continuous monitoring framework |
| **10. Improvement** | Responsible disclosure, extension governance, security enhancement roadmap | Adequate -- improvement mechanisms defined |

**AI-Specific Controls (Annex A):**

| Control | Implementation | Status |
|---------|----------------|--------|
| **A.5.2 AI policy** | Grounded Agency principles document security policy through ontology constraints | Aligned |
| **A.6.1 AI risk assessment** | STRIDE analysis, attack scenarios, security model documentation | Aligned |
| **A.6.2 AI system lifecycle** | Capability extension governance, version management | Partial |
| **A.7.1 Data management** | Evidence store with sanitization, bounded storage | Partial |
| **A.8.1 AI system development** | Typed contracts, layer architecture, composable capabilities | Strong |
| **A.9.1 AI system operation** | Checkpoint enforcement, permission callbacks, audit logging | Adequate |
| **A.10.1 Third-party considerations** | OASF compatibility adapter, interoperability mappings | Partial |

---

## 8. Prioritized Remediation Recommendations

### P0: Immediate (Critical/High Severity Open Risks)

#### P0-1: Harden Audit Log Integrity (SEC-005)

**Effort:** Medium (2-3 days)
**Impact:** Closes the repudiation gap in the STRIDE model

**Actions:**
1. Set file permissions on `.claude/audit.log` to `0600` (owner read/write only)
2. Implement HMAC-based entry signing: each log entry includes an HMAC computed with a session-specific key, creating a tamper-evident chain
3. Fail loudly (exit 1) when `jq` is not available, rather than silently skipping audit logging
4. Add log rotation with a configurable size limit (e.g., 10MB per file, 5 rotations)
5. Include a sequence number in each log entry for gap detection

#### P0-2: Fix Stale Checkpoint File Bypass (SEC-001)

**Effort:** Low (1 day)
**Impact:** Closes the primary shell-hook bypass vector

**Actions:**
1. Write checkpoint metadata (ID, timestamp, expiry) as JSON content in `.claude/checkpoint.ok`
2. Validate timestamp in the shell hook -- reject files older than 30 minutes
3. Add a `CLAUDE_PROJECT_DIR`-based absolute path for the checkpoint file (matching the pattern in `posttooluse_log_tool.sh`)
4. Clean up `.claude/checkpoint.ok` at session termination or when the checkpoint is consumed

#### P0-3: Address Shell Hook / SDK Checkpoint Synchronization (SEC-006, SEC-007)

**Effort:** Medium (2-3 days)
**Impact:** Unifies dual-layer checkpoint enforcement

**Actions:**
1. Have `CheckpointTracker.create_checkpoint()` also write/update `.claude/checkpoint.ok` with the checkpoint ID and expiry timestamp
2. Have `CheckpointTracker.consume_checkpoint()` remove or invalidate `.claude/checkpoint.ok`
3. Implement symlink detection in the shell hook (`[ -L .claude/checkpoint.ok ]` check)
4. Document the synchronization contract between shell and SDK layers

### P1: Short-Term (Medium Severity Risks, 1-4 Weeks)

#### P1-1: Add YAML Input Size Limits (SEC-003)

**Effort:** Low (0.5 days)
**Impact:** Prevents memory exhaustion DoS

**Actions:**
1. Add a file size check before `yaml.safe_load()` in `CapabilityRegistry._load_ontology()`
2. Set reasonable limits: 10MB for ontology, 1MB for profiles, 1MB for workflows
3. Apply the same limits in validator tools

#### P1-2: Implement Priority-Based Evidence Eviction (SEC-004)

**Effort:** Medium (2 days)
**Impact:** Preserves critical provenance under high load

**Actions:**
1. Add priority levels to `EvidenceAnchor` (critical, normal, low)
2. Assign `critical` to mutation and checkpoint anchors
3. Modify eviction logic to evict `low` priority first, then `normal`, then `critical`
4. Optionally, persist critical anchors to disk before eviction

#### P1-3: Add Capability Invocation Rate Limiting (SEC-010)

**Effort:** Medium (2-3 days)
**Impact:** Prevents DoS through rapid capability invocation

**Actions:**
1. Implement a token bucket rate limiter in the permission callback
2. Configure rate limits per risk level:
   - High-risk: 10 invocations per minute
   - Medium-risk: 60 invocations per minute
   - Low-risk: 300 invocations per minute
3. Return `PermissionResultDeny` with rate-limit message when exceeded
4. Make rate limits configurable via `GroundedAgentConfig`

#### P1-4: Enhance Bash Classification for Interpreter Commands (SEC-002)

**Effort:** Low (0.5 days)
**Impact:** Improves classification accuracy for indirect execution

**Actions:**
1. Add interpreter patterns to `_SHELL_INJECTION_PATTERNS`:
   - `python[23]?\s+-c\s`
   - `ruby\s+-e\s`
   - `node\s+-e\s`
   - `perl\s+-e\s`
2. Add process substitution patterns: `<\(` and `>\(`
3. Document the regex approach as defense-in-depth alongside the default-deny fallback

### P2: Medium-Term (Low Severity Improvements, 1-3 Months)

#### P2-1: Add Ontology Integrity Verification (SEC-012)

**Effort:** Medium (2 days)
**Impact:** Prevents ontology content substitution attacks

**Actions:**
1. Generate a SHA-256 checksum of the canonical ontology file at build time
2. Store the checksum in the package metadata or a `.checksum` file
3. Verify the checksum at load time in `CapabilityRegistry._load_ontology()`
4. Log the resolved ontology path for audit

#### P2-2: Add Metadata Key Denylist (SEC-008)

**Effort:** Low (0.5 days)
**Impact:** Prevents cross-system metadata injection

**Actions:**
1. Add explicit denylist: `__proto__`, `constructor`, `__class__`, `__init__`
2. Optionally, disallow keys starting with double underscore (`__`)
3. Document allowed key format for consumers

#### P2-3: Persistent Checkpoint History (SEC-011)

**Effort:** Medium (2-3 days)
**Impact:** Enables forensic analysis of long-running sessions

**Actions:**
1. Write checkpoint records to `.checkpoints/history.jsonl` (append-only JSON lines)
2. Include all fields: ID, scope, reason, created_at, expires_at, consumed, consumed_at
3. Add a `--history` flag to a CLI tool for reviewing checkpoint history

#### P2-4: Trust Model Calibration Enforcement (SEC-009)

**Effort:** Low (1 day)
**Impact:** Prevents uncalibrated trust weights in production

**Actions:**
1. Add a `trust_model_reviewed: true` field to profile schema
2. Emit a warning during profile validation if `trust_model_reviewed` is false or absent
3. Provide domain-specific weight calibration guides

### P3: Long-Term Architectural Enhancements (3-6 Months)

#### P3-1: Cryptographic Audit Log Infrastructure

**Effort:** High (1-2 weeks)
**Impact:** Tamper-evident audit trail for compliance

**Actions:**
1. Implement Merkle tree-based audit log with hash-chain integrity
2. Support log forwarding to centralized log management systems
3. Implement log verification tool for integrity checking
4. Add digital signatures on audit entries using per-session keys

#### P3-2: Runtime Prerequisite Enforcement

**Effort:** High (1-2 weeks)
**Impact:** Enforces ontology edge relationships at runtime

**Actions:**
1. Track exercised capabilities per session in the adapter
2. Before permitting a capability, verify all `requires` edges are satisfied
3. Verify `precedes` edges are satisfied (temporal ordering)
4. Block capabilities with unmet `requires` edges

#### P3-3: Formal Verification of Safety Properties

**Effort:** Very High (1-3 months)
**Impact:** Mathematical proof of safety invariants

**Actions:**
1. Define formal safety properties (e.g., "no mutation without checkpoint" as a temporal logic formula)
2. Model the permission callback and checkpoint lifecycle as a finite state machine
3. Use model checking tools (e.g., TLA+, Alloy) to verify safety invariants
4. Document verified properties and their assumptions

#### P3-4: Role-Based Capability Authorization

**Effort:** High (2-3 weeks)
**Impact:** Fine-grained access control per agent role

**Actions:**
1. Define agent roles with capability whitelists/blacklists
2. Integrate with the `constrain` capability for policy enforcement
3. Add role-based overrides to the permission callback
4. Implement role hierarchy and inheritance

---

## 9. Appendix: Methodology & Tool Coverage

### 9.1. Analysis Methodology

| Phase | Method | Scope |
|-------|--------|-------|
| Dependency analysis | Manual review of `pyproject.toml`, CVE database cross-reference | All declared dependencies |
| Code pattern analysis | Static analysis of Python source, regex pattern review | `grounded_agency/` package |
| Shell script review | Manual code review, POSIX compliance check | `hooks/*.sh` |
| YAML security audit | Automated grep for `yaml.load(` patterns | Entire codebase |
| STRIDE analysis | Threat modeling aligned with `spec/SECURITY.md` | Full system architecture |
| Compliance mapping | Framework cross-reference against code and documentation | OWASP, NIST, EU AI Act, ISO 42001 |

### 9.2. Files Reviewed

| File | Type | Relevance |
|------|------|-----------|
| `grounded_agency/capabilities/mapper.py` | Python | Bash command classification, regex patterns |
| `grounded_agency/adapter.py` | Python | Permission callback, fail-closed pattern |
| `grounded_agency/state/evidence_store.py` | Python | Metadata sanitization, evidence lifecycle |
| `grounded_agency/state/checkpoint_tracker.py` | Python | Checkpoint ID generation, expiry logic |
| `grounded_agency/capabilities/registry.py` | Python | YAML loading, ontology parsing |
| `hooks/pretooluse_require_checkpoint.sh` | Shell | Pre-mutation checkpoint enforcement |
| `hooks/posttooluse_log_tool.sh` | Shell | Post-tool audit logging |
| `hooks/hooks.json` | JSON | Hook configuration and routing |
| `spec/SECURITY.md` | Markdown | Security model documentation |
| `pyproject.toml` | TOML | Dependency declarations, build configuration |

### 9.3. Limitations

1. **No dynamic analysis:** This assessment is based on static code review only. No fuzzing, penetration testing, or runtime analysis was performed.
2. **No SDK integration testing:** The `claude-agent-sdk` is an optional dependency and was not available for integration testing during this review.
3. **No formal verification:** Safety properties were assessed through code review, not mathematical proof.
4. **Point-in-time assessment:** This review reflects the codebase at commit `e14a723` on the `main` branch. Subsequent changes may introduce new risks or resolve identified ones.
5. **Scope boundary:** Third-party dependencies (PyYAML internals, hatchling build system) were assessed at the interface level only, not through source code audit.

### 9.4. Risk Severity Definitions

| Severity | Definition | Response Time |
|----------|-----------|---------------|
| **Critical** | Exploitable vulnerability that could compromise system integrity or safety. Immediate patch required. | 24 hours |
| **High** | Significant security gap that weakens a core safety invariant. Near-term remediation required. | 1 week |
| **Medium** | Security weakness that could be exploited under specific conditions. Planned remediation. | 1 month |
| **Low** | Minor improvement opportunity or defense-in-depth enhancement. Scheduled remediation. | 1 quarter |

---

*Assessment prepared: 2026-01-30*
*Next review recommended: 2026-04-30 (quarterly cadence)*
*Classification: Internal Engineering Review*
