---
name: execute
description: Run code or scripts deterministically with captured output. Use when running tests, executing build commands, invoking tools, or performing read-only operations that produce results.
argument-hint: "[code] [language] [timeout]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Bash
context: fork
agent: general-purpose
layer: EXECUTE
---

## Intent

Execute code or commands in a controlled manner, capturing output for verification. Unlike `mutate`, this capability is for operations that don't permanently change state (tests, queries, builds, analysis tools).

**Success criteria:**
- Code/command executed successfully
- Output captured completely
- Exit code recorded
- Errors properly surfaced
**Compatible schemas:**
- `schemas/output_schema.yaml`


## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `code` | Yes | string | Code or command to execute |
| `language` | No | string | Programming language or shell (bash, python, ruby, etc.) |
| `timeout` | No | string | Maximum execution time (default: "60s") |
| `environment` | No | object | Environment variables to set |

## Procedure

1) **Validate execution request**: Ensure code is safe to run
   - Check for mutation operations (if found, suggest `mutate` instead)
   - Verify timeout is reasonable
   - Confirm execution environment

2) **Prepare environment**: Set up execution context
   - Set required environment variables
   - Ensure dependencies are available
   - Create isolated context if needed

3) **Execute code**: Run the code/command
   - Capture stdout and stderr
   - Record start time
   - Monitor for timeout

4) **Capture results**: Collect execution output
   - Record exit code
   - Capture complete stdout
   - Capture complete stderr
   - Note execution duration

5) **Analyze output**: Interpret results
   - Identify success/failure from exit code
   - Extract key information from output
   - Note warnings or anomalies

6) **Return results**: Structure output for consumption
   - Include all captured data
   - Provide execution summary
   - Reference evidence for assertions

## Output Contract

Return a structured object:

```yaml
result:
  success: boolean  # Exit code == 0
  exit_code: integer  # Process exit code
  stdout: string  # Standard output
  stderr: string  # Standard error
  duration: string  # Execution time
execution:
  command: string  # What was executed
  language: string  # Execution environment
  started_at: string  # ISO timestamp
  completed_at: string  # ISO timestamp
analysis:
  summary: string  # One-line result summary
  warnings: array[string]  # Notable warnings
  errors: array[string]  # Extracted error messages
evidence_anchors: ["command:output"]
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `result.success` | boolean | Whether execution succeeded |
| `result.exit_code` | integer | Process exit code |
| `result.stdout` | string | Standard output |
| `result.stderr` | string | Standard error |
| `result.duration` | string | How long execution took |
| `execution` | object | Execution metadata |
| `analysis` | object | Interpreted results |

## Examples

### Example 1: Run Tests

**Input:**
```yaml
code: "npm test -- --grep 'UserService'"
language: "bash"
timeout: "120s"
```

**Output:**
```yaml
result:
  success: true
  exit_code: 0
  stdout: |
    > project@1.0.0 test
    > jest --grep 'UserService'

    PASS src/services/__tests__/UserService.test.ts
      UserService
        ✓ creates user with valid data (45ms)
        ✓ validates email format (12ms)
        ✓ hashes password on save (23ms)

    Test Suites: 1 passed, 1 total
    Tests:       3 passed, 3 total
  stderr: ""
  duration: "2.3s"
execution:
  command: "npm test -- --grep 'UserService'"
  language: "bash"
  started_at: "2024-01-15T10:30:00Z"
  completed_at: "2024-01-15T10:30:02Z"
analysis:
  summary: "3 tests passed in UserService"
  warnings: []
  errors: []
evidence_anchors:
  - "command:npm test:output"
```

### Example 2: Execute Query

**Input:**
```yaml
code: "SELECT COUNT(*) as user_count FROM users WHERE created_at > '2024-01-01'"
language: "sql"
environment:
  DATABASE_URL: "${DATABASE_URL}"
```

**Output:**
```yaml
result:
  success: true
  exit_code: 0
  stdout: |
    user_count
    ----------
    15423
    (1 row)
  stderr: ""
  duration: "0.15s"
execution:
  command: "psql -c \"SELECT COUNT(*)...\""
  language: "sql"
  started_at: "2024-01-15T10:35:00Z"
  completed_at: "2024-01-15T10:35:00Z"
analysis:
  summary: "Query returned 15423 users created in 2024"
  warnings: []
  errors: []
evidence_anchors:
  - "command:psql:query_result"
```

### Example 3: Execution Failure

**Input:**
```yaml
code: "python -c 'import nonexistent_module'"
language: "bash"
```

**Output:**
```yaml
result:
  success: false
  exit_code: 1
  stdout: ""
  stderr: |
    Traceback (most recent call last):
      File "<string>", line 1, in <module>
    ModuleNotFoundError: No module named 'nonexistent_module'
  duration: "0.05s"
execution:
  command: "python -c 'import nonexistent_module'"
  language: "bash"
  started_at: "2024-01-15T10:40:00Z"
  completed_at: "2024-01-15T10:40:00Z"
analysis:
  summary: "Import failed: module 'nonexistent_module' not found"
  warnings: []
  errors:
    - "ModuleNotFoundError: No module named 'nonexistent_module'"
evidence_anchors:
  - "command:python:error"
```

## Verification

- [ ] Exit code is captured
- [ ] Stdout and stderr are both recorded
- [ ] Duration is reasonable
- [ ] Analysis summary matches output
- [ ] No mutations occurred

**Verification tools:** Bash (to verify command execution environment)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: true
- `risk`: medium

**Capability-specific rules:**
- Verify code does not mutate persistent state
- Enforce timeout limits
- Capture all output for audit trail
- Do not execute code that requires elevated privileges without approval
- Prefer `mutate` for state-changing operations

## Composition Patterns

**Commonly follows:**
- `plan` - Execute planned actions
- `generate` - Execute generated code
- `transform` - Execute transformation scripts

**Commonly precedes:**
- `verify` - Verify execution results
- `detect` - Detect patterns in output
- `audit` - Record execution for audit

**Anti-patterns:**
- Never use execute for persistent state changes (use `mutate`)
- Avoid execute without timeout limits
- Never execute untrusted code without sandboxing

**Workflow references:**
- See `reference/workflow_catalog.yaml#debug_code_change` for execute in testing
- See `reference/workflow_catalog.yaml#digital_twin_sync_loop` for execute in sync loops
