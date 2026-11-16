---
name: send
description: Emit a message or event to an external system with policy enforcement and approval gates. Use when publishing messages, calling APIs, sending notifications, or triggering external workflows. REQUIRES EXPLICIT APPROVAL.
argument-hint: "[destination] [payload] [protocol]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Bash
context: fork
agent: general-purpose
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: prompt
          prompt: |
            Model-judged additions (STANDARD 1.2.0 §5.18.10): these may refuse
            the call; the checks the Standard requires (approval, the checkpoint,
            rollback history, the destination policy, secrets) are made by code,
            not here.

            OUTBOUND COMMUNICATION SAFETY CHECK

            The tool call follows this prompt as JSON; the command is tool_input.command.

            This skill sends data to external systems. Verify:
            1. The destination is one the destination policy allows (checked by
               code where a policy is in force, STANDARD 1.2.0 §4.4.2); judge it
               here only when none is.
            2. No sensitive data (API keys, passwords, PII) in payload

            CRITICAL: External sends are IRREVERSIBLE.

            Return ok: true only if ALL conditions are verified.
            Return ok: false, with the specific violation as the reason, if any check fails.
          once: false
        - type: command
          command: |
            # Block a request to localhost or a private IPv4 address (a host-specific
            # destination rule, STANDARD 1.2.0 §5.18.10, F504). Claude Code passes
            # the tool call as JSON on stdin; exit 2 blocks the call and the reason
            # on stderr is shown to Claude. A call that cannot be read is blocked
            # (R407).
            CMD="$(jq -r '.tool_input.command // empty' 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            ADDR='(localhost|127\.0\.0\.1|10\.[0-9]+\.[0-9]+\.[0-9]+|192\.168\.[0-9]+\.[0-9]+|172\.(1[6-9]|2[0-9]|3[01])\.[0-9]+\.[0-9]+)'
            # The address must stand where a host does: after a URL scheme, a user@,
            # a space or a quote, and before a port, a path, a query or the end.
            # Host names are case-insensitive, so the match is too.
            if printf '%s\n' "$CMD" | grep -qiE "(curl|wget|http)" && printf '%s\n' "$CMD" | grep -qiE "(^|[[:space:]\"']|://|@)${ADDR}([:/?#[:space:]\"']|\$)"; then
              echo "F504 CONSTRAINT_VIOLATED: the send skill does not send to localhost or a private IPv4 address (internal network access)" >&2
              exit 2
            fi
            exit 0
  PostToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: |
            # Log the call without its input. Claude Code passes the tool call as
            # JSON on stdin; a SHA-256 digest of tool_input stands in for it.
            DIGEST=""
            INPUT="$(jq -cS '.tool_input' 2>/dev/null)" &&
              DIGEST="$(printf '%s' "$INPUT" | { sha256sum 2>/dev/null || shasum -a 256 2>/dev/null || openssl dgst -sha256 -r 2>/dev/null; } | cut -c1-64)"
            mkdir -p .audit 2>/dev/null || true
            echo "[SEND] $(date -u +%Y-%m-%dT%H:%M:%SZ) | Bash | input_sha256: ${DIGEST:-unavailable}" >> .audit/send-operations.log 2>/dev/null || true
---

## Intent

Send a message, event, or payload to an external destination with full policy enforcement, approval gates, and audit trail. This capability handles external side effects that cannot be undone.

**CRITICAL: This capability requires explicit user approval before execution.**

**Success criteria:**
- Message delivered to destination successfully
- All policy constraints verified before sending
- Approval gate passed (explicit user confirmation)
- Complete audit trail of what was sent
- Delivery confirmation obtained where possible

**Compatible schemas:**
- `schemas/output_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `destination` | Yes | string | Target endpoint, queue, API, or address |
| `payload` | Yes | any | Data to send |
| `protocol` | No | string | Communication protocol (http, grpc, smtp, amqp, etc.) |

Inputs not listed here are outside the capability's contract: a workflow step that binds them gets W604 (STANDARD v1.1 §5.5).

## Procedure

1) **Verify approval**: Confirm explicit user approval exists
   - Check the approval is valid and recent
   - BLOCK send if approval is missing or expired
   - Log approval verification for audit

2) **Verify checkpoint**: Confirm recovery point exists
   - Validate that a checkpoint was created before this send
   - BLOCK send if checkpoint is missing
   - External sends are irreversible - checkpoint is for state recovery

3) **Validate destination**: Ensure target is permitted
   - Check destination against allowlist if defined
   - Verify destination format matches protocol
   - Block sends to disallowed destinations

4) **Apply constraints**: Enforce policy limits
   - Check rate limits have not been exceeded
   - Verify message size within bounds
   - Validate message format against schema
   - Apply `constrain` capability rules

5) **Prepare payload**: Format message for transmission
   - Serialize according to protocol requirements
   - Add required headers/metadata
   - Generate message ID for tracking
   - Record payload summary (not full content if sensitive)

6) **Execute send**: Transmit to destination
   - Use appropriate protocol handler
   - Capture response or confirmation
   - Handle timeouts gracefully
   - Retry according to policy if configured

7) **Verify delivery**: Confirm successful transmission
   - Check response status/acknowledgment
   - Log delivery confirmation
   - Capture any error responses

8) **Audit trail**: Record complete send operation
   - What was sent (summary, not sensitive content)
   - Where it was sent
   - When it was sent
   - Delivery status
   - Approval reference

## Output Contract

Return a structured object:

```yaml
sent: boolean  # true when the transport accepted the message (delivery.status sent or queued)
response: any  # Recipient's response or delivery receipt, if any
timestamp: string  # ISO 8601 date-time of send
message:
  destination: string  # Where message was sent
  payload_type: string  # Type of content sent
  payload_summary: string  # Non-sensitive summary of payload
  message_id: string | null  # Tracking ID if available
delivery:
  status: sent | queued | failed  # Delivery outcome
  retry_count: integer  # Number of retry attempts
  response_code: integer | null  # HTTP status or protocol response
  error: string | null  # Error message if failed
constraints_applied:
  - constraint: string  # What constraint was checked
    enforced: boolean  # Whether it passed
    details: string | null  # Additional context
approval:
  token: string  # Approval token used
  timestamp: string  # When approval was given
  scope: string  # What was approved
confidence: number  # probability that the message was delivered as reported (§4.1.1)
evidence_anchors: [{ref: "sent:<idempotency_key>", kind: record}, {ref: "log:timestamp", kind: log}, {ref: "api:response", kind: api}]  # a message sent is grounded by its record, under the pass's idempotency key (STANDARD v1.2 §3.1)
assumptions: []  # Explicit assumptions
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `sent` | boolean | Whether the message was sent (accepted by the transport) |
| `response` | any | Recipient's response or delivery receipt, or null |
| `timestamp` | string | ISO 8601 date-time of send |
| `message` | object | Details of what was sent (destination, payload type, non-sensitive summary, message ID) |
| `delivery` | object | Outcome of send operation |
| `constraints_applied` | array | Policy checks performed |
| `approval` | object | Approval gate information |
| `confidence` | number | Probability, 0.0-1.0, that the message was delivered as reported (§4.1.1) |
| `evidence_anchors` | array of evidence anchors (§6.5) | Logs, responses, confirmations |
| `assumptions` | array | Explicit assumptions (e.g., "network stable") |

## Examples

### Example 1: API Webhook Notification

**Input:**
```yaml
destination: "https://api.partner.com/webhooks/order-updates"
payload:
  event: "order.completed"
  order_id: "ORD-12345"
  timestamp: "2024-01-15T10:30:00Z"
  customer_notified: true
protocol: "http"
```

Approval and the checkpoint come from the workflow (an approved step after a `checkpoint` step), not from inputs. A preceding `constrain` step enforces the policy: at most 100 sends per hour, to `api.partner.com` only.

**Output:**
```yaml
sent: true
response:
  received: true
timestamp: "2024-01-15T10:30:15Z"
message:
  destination: "https://api.partner.com/webhooks/order-updates"
  payload_type: "order.completed event"
  payload_summary: "Order completion notification for ORD-12345"
  message_id: "msg-abc123"
delivery:
  status: sent
  retry_count: 0
  response_code: 200
  error: null
constraints_applied:
  - constraint: "rate_limit: 100/hour"
    enforced: true
    details: "Current rate: 45/hour"
  - constraint: "allowed_domains"
    enforced: true
    details: "api.partner.com is in allowlist"
approval:
  token: "approve-send-2024-01-15-001"
  timestamp: "2024-01-15T10:30:00Z"
  scope: "Send order notification to partner API"
confidence: 0.95
evidence_anchors:
  - {ref: "sent:run-4f2a:7", kind: record}
  - {ref: "log:2024-01-15T10:30:15Z:send-success", kind: log}
  - {ref: "api:response:200-OK", kind: api}
assumptions:
  - "Partner API is available and processing webhooks"
```

**Evidence pattern:** HTTP response code and body confirmation, timestamped log entry.

---

### Example 2: Email Notification (with failure)

**Input:**
```yaml
destination: "smtp://mail.company.com:587"
payload:
  to: "user@example.com"
  subject: "Action Required: Review pending"
  body: "You have 3 items awaiting review..."
protocol: "smtp"
```

**Output:**
```yaml
sent: false
response: null
timestamp: "2024-01-15T11:00:05Z"
message:
  destination: "smtp://mail.company.com:587"
  payload_type: "email"
  payload_summary: "Email to user@example.com regarding pending review"
  message_id: null
delivery:
  status: failed
  retry_count: 3
  response_code: null
  error: "Connection timeout after 30s - SMTP server unreachable"
constraints_applied:
  - constraint: "recipient_validation"
    enforced: true
    details: "Email format valid"
approval:
  token: "approve-email-2024-01-15-002"
  timestamp: "2024-01-15T11:00:00Z"
  scope: "Send review notification email"
confidence: 0.0
evidence_anchors:
  - {ref: "log:2024-01-15T11:00:05Z:smtp-timeout", kind: log}
  - {ref: "error:connection-refused", kind: tool}
assumptions:
  - "SMTP server should be available on port 587"
next_actions:
  - "Verify SMTP server status"
  - "Check network connectivity"
  - "Retry with backup mail server if available"
```

## Verification

- [ ] Approval token is valid and not expired
- [ ] Checkpoint reference exists
- [ ] Destination passes policy validation
- [ ] All constraints were checked before send
- [ ] Delivery status is accurately reported
- [ ] Audit trail is complete

**Verification tools:** Read (for logs), Bash (for health checks)

## Safety Constraints

- `mutation`: true
- `requires_checkpoint`: true
- `requires_approval`: true
- `risk`: high

**Capability-specific rules:**
- NEVER send without explicit user approval (CRITICAL)
- NEVER send without a valid checkpoint reference
- ALWAYS validate destination against policy before sending
- ALWAYS log what was sent for audit (sanitize sensitive data)
- DO NOT retry indefinitely - respect retry limits
- BLOCK sends to destinations not in allowlist when list is defined
- If approval token is missing, REQUEST approval before proceeding
- Never send credentials, API keys, or secrets in payloads

**APPROVAL GATE REQUIREMENT:**
Before any send operation, the user must explicitly approve:
1. What will be sent (summary)
2. Where it will be sent (destination)
3. Why it is being sent (context)

The approval must be captured with a token that is recorded in this operation's audit trail.

## Composition Patterns

**Commonly follows:**
- `constrain` - Apply policy limits before sending (recommended; warning W601 if no constrain step runs first)
- `checkpoint` - Create recovery point before external send (REQUIRED)
- `plan` - Sends are typically part of a larger plan
- `transform` - Format data before sending

**Commonly precedes:**
- `audit` - Record what was sent for compliance
- `verify` - Confirm delivery where possible
- `receive` - May expect response from destination

**Anti-patterns:**
- NEVER send without `constrain` check (policy bypass)
- NEVER send without `checkpoint` (no state recovery)
- NEVER send without explicit approval (unauthorized action)
- NEVER retry failed sends indefinitely (resource exhaustion)

**Workflow references:**
- See `reference/composition_patterns.md#anti-patterns` for send safety rules
- See `reference/composition_patterns.md#digital-twin-sync-loop` for send in sync context
