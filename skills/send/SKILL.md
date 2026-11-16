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
            # Block a request to localhost or a loopback, private, link-local or
            # unspecified address written as its host (a host-specific destination
            # rule, STANDARD 1.2.0 §5.18.10, F504), and a request whose destination
            # this check cannot read: one whose text the shell expands or escapes,
            # or whose connection an option or a proxy setting redirects. A name
            # that resolves to an internal address, and a redirect a server answers
            # with, are not checked here. Claude Code passes the tool call as JSON
            # on stdin; exit 2 blocks the call and the reason on stderr is shown to
            # Claude. A call that cannot be read is blocked (R407).
            CMD="$(jq -r '.tool_input.command // empty' 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            printf '%s\n' "$CMD" | grep -qiE "(curl|wget|http)" || exit 0
            # IPv4 in dotted-decimal form: 0/8, 127/8 (loopback), 10/8, 172.16/12,
            # 192.168/16 and 169.254/16 (link-local, cloud metadata); also as the
            # first labels of a name (127.0.0.1.nip.io resolves to 127.0.0.1).
            ADDR4='(0(\.[0-9]+){3}|127(\.[0-9]+){3}|10(\.[0-9]+){3}|192\.168(\.[0-9]+){2}|172\.(1[6-9]|2[0-9]|3[01])(\.[0-9]+){2}|169\.254(\.[0-9]+){2})(\.[a-z0-9-]+)*'
            # IPv6 literals: ::1, ::, ::ffff:<IPv4> (mapped), fc00::/7 (unique
            # local), fe80::/10 (link-local).
            ADDR6='\[(::|0*:|f[cd][0-9a-f]*:|fe[89ab][0-9a-f]*:)[^]]*\]'
            # IPv4 in another form a resolver accepts, as a URL's host: one to three
            # parts (127.1, 2130706433), or a part in hex (0x7f) or octal (0177).
            NUMERIC='((0x[0-9a-f]*|[0-9]+)\.){0,2}(0x[0-9a-f]*|[0-9]+)|([0-9a-fx.]*\.)?(0x[0-9a-f]*|0[0-9]+)(\.[0-9a-fx]*)*'
            # The address must stand where a host does: after a URL scheme, a user@,
            # a space or a quote, and before a port, a path, a query or the end; a
            # host may end in the root's dot (localhost., 127.0.0.1.). Host names
            # are case-insensitive, so the match is too.
            AFTER="\.?([:/?#[:space:]\"']|\$)"
            if printf '%s\n' "$CMD" | grep -qiE "(^|[[:space:]\"']|://|@)(localhost|${ADDR4}|${ADDR6})${AFTER}" \
              || printf '%s\n' "$CMD" | grep -qiE "(://|@)(${NUMERIC})${AFTER}"; then
              echo "F504 CONSTRAINT_VIOLATED: the send skill does not send to localhost or a loopback, private, link-local or unspecified address written as the host (internal network access)" >&2
              exit 2
            fi
            # Options and settings that send the request elsewhere than its URL's
            # host: curl's --resolve, --connect-to, a Unix socket, a proxy (-x in any
            # short option cluster), a DNS server, options read from a file (-K);
            # wget's -e/--execute (wgetrc commands, a proxy among them) and URLs read
            # from a file (-i); a *_proxy variable set on the line.
            if printf '%s\n' "$CMD" | grep -qiE -- "(^|[[:space:]\"'])(--resolve|--connect-to|--unix-socket|--abstract-unix-socket|--proxy[a-z0-9-]*|--preproxy|--socks[a-z0-9-]*|--doh-url|--dns-servers|--config|--execute|--input-file)([=[:space:]\"']|\$)" \
              || { printf '%s\n' "$CMD" | grep -qi curl && printf '%s\n' "$CMD" | grep -qE -- "(^|[[:space:]\"'])-[A-Za-z0-9]*[xK]"; } \
              || { printf '%s\n' "$CMD" | grep -qi wget && printf '%s\n' "$CMD" | grep -qE -- "(^|[[:space:]\"'])-[A-Za-z0-9]*[ei]"; } \
              || printf '%s\n' "$CMD" | grep -qiE -- "(^|[[:space:]\"';&|])[a-z_]*proxy="; then
              echo "F504 CONSTRAINT_VIOLATED: the send skill does not run a request whose connection an option or a proxy setting redirects (--resolve, --connect-to, a socket, a proxy, a DNS server, options or URLs read from a file): the address it reaches is not the one this check reads" >&2
              exit 2
            fi
            # Text the shell expands or escapes can be any host or option
            case "$CMD" in
              *'$'* | *'`'* | *'\'* | *'<('* | *'>('*)
                echo "F504 CONSTRAINT_VIOLATED: the send skill does not run a request whose text the shell expands or escapes (\$, a backtick, \\, <( or >()): the host it reaches is not the one this check reads. Write the command on one line with literal values; curl reads a credential header from a file with -H @file" >&2
                exit 2
                ;;
            esac
            exit 0
---

## Intent

Send a message, event, or payload to an external destination with full policy enforcement, approval gates, and audit trail. This capability handles external side effects that cannot be undone: the checkpoint before it restores the agent's own state, not the transmission, so a send is made safe before it happens (STANDARD v1.2 §4.4.2).

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
| `destination` | Yes | string | Where the data goes, in the host's naming (a URL, an address, a queue or a channel); checked against the destination policies in force (STANDARD v1.2 §4.4.2) |
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
   - The checkpoint restores the agent's own state, not the transmission (§4.4.2): once delivered, the data cannot be recalled, and a later rollback reports the send as `not_covered` (`transmitted`)

3) **Validate destination**: Ensure the destination is permitted
   - Where a destination policy is in force (the host's, or an applied profile's `allowed_destinations`), code checks it before approval and refuses a destination it does not allow (F504, STANDARD v1.2 §4.4.2); never try another destination to get around a refusal
   - In a workflow, a `constrain` step with the destination as `target` records the check, and the approval `shows` the destination (§12.5, Guarded Send)
   - Verify destination format matches protocol

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
   - Pass the pass's idempotency key to a destination that accepts one (an `Idempotency-Key` header, a message de-duplication id)
   - Capture response or confirmation
   - Handle timeouts gracefully
   - Retry: a retry carries the same idempotency key; never transmit twice under one key; when unsure whether an earlier attempt delivered, do not send again (report `outcome_unknown`, §4.4.2)

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
compensation:  # How the effect can be compensated, if known; nothing performs it automatically (§4.4.2)
  strategy: string
  inverse_effects: array[string]
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
| `compensation` | object | How the transmission's effect can be compensated (`strategy`, `inverse_effects`), in the form of `TransitionRule.rollback`; a workflow that compensates does so in a send of its own (§4.4.2) |
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
  - constraint: "destination policy (STANDARD v1.2 §4.4.2)"
    enforced: true
    details: "https://api.partner.com/webhooks/* allows it"
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
- BLOCK sends to destinations the destination policy does not allow, where one is in force (code refuses them with F504, §4.4.2)
- NEVER transmit twice under one idempotency key; when unsure whether an earlier attempt delivered, do not send again
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
