---
name: critique
description: Find failure modes, edge cases, ambiguities, and exploit paths in plans, code, or designs. Use when reviewing proposals, auditing security, stress-testing logic, or validating assumptions.
argument-hint: "[target] [focus_areas] [severity_threshold]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep
context: fork
agent: explore
---

## Intent

Systematically analyze a target (plan, code, design, document) to identify failure modes, edge cases, ambiguities, and potential exploits. Produce actionable findings with severity ratings and mitigation recommendations.

**Success criteria:**
- All major failure modes identified
- Edge cases documented with reproduction scenarios
- Ambiguities flagged with clarification requests
- Security/exploit risks rated appropriately
- Each finding has actionable recommendation

**Compatible schemas:**
- `docs/schemas/critique_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `target` | Yes | string or object | Plan, code, design, or document to critique |
| `focus_areas` | No | array | Specific areas to examine (security, performance, logic, etc.) |
| `severity_threshold` | No | string | Minimum severity to report: low, medium, high, critical |
| `context` | No | object | Additional context about the target |
| `adversarial` | No | boolean | Enable adversarial/red-team thinking (default: true) |

## Procedure

1) **Understand the target**: Analyze what is being critiqued
   - Read and comprehend the target fully
   - Identify the purpose and intended behavior
   - Note stated assumptions and constraints
   - Understand success criteria

2) **Identify failure modes**: Find ways the target could fail
   - What happens under unexpected inputs?
   - What if dependencies are unavailable?
   - What if timing assumptions are wrong?
   - What if scale exceeds expectations?

3) **Enumerate edge cases**: Find boundary conditions
   - Empty inputs, null values, missing fields
   - Maximum/minimum values
   - Concurrent access scenarios
   - Unicode, special characters, injection patterns

4) **Detect ambiguities**: Find unclear specifications
   - Terms with multiple interpretations
   - Missing definitions
   - Implicit assumptions
   - Contradictory requirements

5) **Assess exploit paths**: Identify security vulnerabilities
   - Input validation gaps
   - Authentication/authorization bypasses
   - Data exposure risks
   - Privilege escalation opportunities

6) **Rate severity**: Classify each finding
   - CRITICAL: System compromise or data loss
   - HIGH: Significant functionality or security impact
   - MEDIUM: Moderate impact, workarounds exist
   - LOW: Minor issues, cosmetic or edge-case

7) **Recommend mitigations**: Provide actionable fixes
   - Specific changes to address each finding
   - Priority ordering for fixes
   - Estimated effort for each mitigation

## Output Contract

Return a structured object:

```yaml
findings:
  - id: string  # Unique finding identifier
    type: failure_mode | edge_case | ambiguity | exploit | gap
    description: string  # Clear description of the issue
    severity: low | medium | high | critical
    location: string  # Where in target (file:line, section, etc.)
    evidence: string  # Supporting evidence
    reproduction: string | null  # How to reproduce
    recommendation: string  # Suggested fix
risk_summary:
  overall_risk: low | medium | high | critical
  mitigations_possible: boolean
  urgent_issues: array[string]  # Finding IDs requiring immediate attention
  risk_distribution:
    critical: integer
    high: integer
    medium: integer
    low: integer
recommendations:
  - finding_ref: string  # Finding ID
    suggestion: string  # Detailed fix suggestion
    effort: low | medium | high
    priority: integer  # 1 = highest priority
patterns_identified:
  - pattern: string  # Recurring issue pattern
    affected_findings: array[string]
    systemic_fix: string  # How to address pattern
confidence: 0..1
evidence_anchors: ["file:line", "section:name"]
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `findings` | array | Individual issues discovered |
| `risk_summary` | object | Overall risk assessment |
| `recommendations` | array | Prioritized fix suggestions |
| `patterns_identified` | array | Recurring issues with systemic fixes |
| `confidence` | number | 0.0-1.0 based on analysis completeness |
| `evidence_anchors` | array | References to target locations |
| `assumptions` | array | Assumptions made during analysis |

## Examples

### Example 1: Plan Critique

**Input:**
```yaml
target:
  id: "deploy-plan-001"
  goal: "Deploy new authentication service"
  steps:
    - id: "step-1"
      action: "Stop old auth service"
    - id: "step-2"
      action: "Deploy new auth service"
    - id: "step-3"
      action: "Run smoke tests"
focus_areas: ["availability", "rollback", "security"]
```

**Output:**
```yaml
findings:
  - id: "CRT-001"
    type: failure_mode
    description: "Zero-downtime deployment not guaranteed. Stopping old service before new is verified creates outage window."
    severity: high
    location: "step-1 to step-2 transition"
    evidence: "step-1 stops service, step-2 starts new - gap exists"
    reproduction: "Execute plan; observe 503 errors between steps"
    recommendation: "Use blue-green deployment: start new service, verify health, then route traffic"
  - id: "CRT-002"
    type: gap
    description: "No rollback step defined. If step-3 smoke tests fail, no recovery procedure."
    severity: critical
    location: "plan.steps - missing rollback"
    evidence: "No rollback_action in any step"
    reproduction: "Smoke tests fail; manual intervention required"
    recommendation: "Add rollback step: 'If step-3 fails, restart old auth service'"
  - id: "CRT-003"
    type: ambiguity
    description: "'Smoke tests' not defined. Unclear what is being tested or pass criteria."
    severity: medium
    location: "step-3"
    evidence: "No verification_criteria specified"
    reproduction: null
    recommendation: "Define specific test cases: auth flow, token validation, error handling"
  - id: "CRT-004"
    type: exploit
    description: "No security verification step. New service could have misconfigured permissions."
    severity: high
    location: "plan - missing security check"
    evidence: "No step validates auth service security posture"
    reproduction: "Deploy service with open admin endpoint; not caught by smoke tests"
    recommendation: "Add security scan step before traffic routing"
risk_summary:
  overall_risk: critical
  mitigations_possible: true
  urgent_issues: ["CRT-002", "CRT-001"]
  risk_distribution:
    critical: 1
    high: 2
    medium: 1
    low: 0
recommendations:
  - finding_ref: "CRT-002"
    suggestion: "Add rollback step with automatic trigger on smoke test failure"
    effort: low
    priority: 1
  - finding_ref: "CRT-001"
    suggestion: "Rewrite as blue-green deployment with health check before cutover"
    effort: medium
    priority: 2
  - finding_ref: "CRT-004"
    suggestion: "Add security scan after deployment, before enabling traffic"
    effort: medium
    priority: 3
  - finding_ref: "CRT-003"
    suggestion: "Define smoke test checklist with pass/fail criteria"
    effort: low
    priority: 4
patterns_identified:
  - pattern: "Missing safety gates"
    affected_findings: ["CRT-001", "CRT-002", "CRT-004"]
    systemic_fix: "Adopt CAVR pattern: checkpoint before each mutation, verify after each step"
confidence: 0.9
evidence_anchors:
  - "plan:step-1:stops-service"
  - "plan:steps:no-rollback"
assumptions:
  - "Auth service is critical for all user operations"
  - "Downtime of auth service blocks all authenticated requests"
```

**Evidence pattern:** Each finding references specific plan location; recommendations are actionable.

---

### Example 2: Code Critique (Security Focus)

**Input:**
```yaml
target:
  file: "src/api/auth.py"
  code: |
    def login(username, password):
        user = db.query(f"SELECT * FROM users WHERE username='{username}'")
        if user and user.password == password:
            return create_token(user.id)
        return None
focus_areas: ["security"]
adversarial: true
```

**Output:**
```yaml
findings:
  - id: "CRT-001"
    type: exploit
    description: "SQL injection vulnerability. Username is interpolated directly into query string."
    severity: critical
    location: "auth.py:2"
    evidence: "f-string query with unescaped username input"
    reproduction: "username=\"admin'--\", password=\"anything\" bypasses auth"
    recommendation: "Use parameterized query: db.query('SELECT * FROM users WHERE username=?', (username,))"
  - id: "CRT-002"
    type: exploit
    description: "Plain-text password comparison. Passwords stored in cleartext or compared unsafely."
    severity: critical
    location: "auth.py:3"
    evidence: "Direct comparison: user.password == password"
    reproduction: "Database compromise exposes all passwords"
    recommendation: "Use bcrypt or argon2: bcrypt.checkpw(password, user.password_hash)"
  - id: "CRT-003"
    type: failure_mode
    description: "No rate limiting. Brute force attacks possible."
    severity: high
    location: "auth.py:login function"
    evidence: "No attempt tracking or delay mechanism"
    reproduction: "Script 1000 login attempts per second"
    recommendation: "Add rate limiting: max 5 attempts per minute per IP/username"
  - id: "CRT-004"
    type: edge_case
    description: "Empty username/password not handled. Could cause unexpected behavior."
    severity: low
    location: "auth.py:1"
    evidence: "No input validation at function entry"
    reproduction: "login('', '') - behavior undefined"
    recommendation: "Add input validation: if not username or not password: return None"
risk_summary:
  overall_risk: critical
  mitigations_possible: true
  urgent_issues: ["CRT-001", "CRT-002"]
  risk_distribution:
    critical: 2
    high: 1
    medium: 0
    low: 1
recommendations:
  - finding_ref: "CRT-001"
    suggestion: "IMMEDIATE: Replace f-string query with parameterized query"
    effort: low
    priority: 1
  - finding_ref: "CRT-002"
    suggestion: "IMMEDIATE: Migrate to bcrypt password hashing"
    effort: medium
    priority: 2
  - finding_ref: "CRT-003"
    suggestion: "Add rate limiting middleware before login endpoint"
    effort: medium
    priority: 3
  - finding_ref: "CRT-004"
    suggestion: "Add input validation decorator"
    effort: low
    priority: 4
patterns_identified:
  - pattern: "OWASP Top 10 violations"
    affected_findings: ["CRT-001", "CRT-002"]
    systemic_fix: "Security code review and SAST integration in CI"
confidence: 0.95
evidence_anchors:
  - "auth.py:2:sql-injection"
  - "auth.py:3:plaintext-password"
assumptions:
  - "This code handles real user authentication"
  - "Database contains actual user credentials"
```

## Verification

- [ ] All focus areas were examined
- [ ] Severity ratings are justified
- [ ] Each finding has a recommendation
- [ ] Critical issues are highlighted
- [ ] Patterns are identified for systemic fixes

**Verification tools:** Read (for code/doc analysis), Grep (for pattern search)

## Safety Constraints

- `mutation`: false
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Never test exploits on production systems
- Report all critical findings immediately
- Do not disclose security findings to unauthorized parties
- If finding reveals active exploit, escalate immediately
- Be thorough but avoid false positives

## Composition Patterns

**Commonly follows:**
- `plan` - Critique plans before execution
- `inspect` - Understand target before critique
- `retrieve` - Gather context for critique

**Commonly precedes:**
- `plan` - Revise plan based on critique findings
- `mitigate` - Address identified risks
- `verify` - Validate fixes for findings
- `audit` - Record critique and responses

**Anti-patterns:**
- Never skip critique for high-risk plans
- Never proceed with critical findings unaddressed
- Avoid superficial critique of security-sensitive targets

**Workflow references:**
- See `composition_patterns.md#debug-code-change` for critique in debugging
- See `composition_patterns.md#capability-gap-analysis` for planning context
