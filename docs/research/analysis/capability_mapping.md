# Detailed Capability Mapping Analysis

> This document provides detailed mappings between observed agent failures and Grounded Agency capabilities, including mitigation strategies.

## Methodology

For each failure, we document:
1. **Issue Reference**: Repository and issue number
2. **Category**: One of the six taxonomy categories
3. **Root Cause**: The underlying system deficiency
4. **Mapped GA Capabilities**: Which capabilities address this failure
5. **Mitigation Pattern**: How to compose capabilities to prevent/mitigate

---

## Category 1: State Management Failures

State management is the largest failure category (~35%), reflecting the fundamental challenge of maintaining consistent state in distributed, asynchronous agent systems.

### Key Patterns

| Pattern | Description | Prevention Capabilities |
|---------|-------------|------------------------|
| Race Condition | Concurrent access corrupts state | `synchronize`, `checkpoint` |
| Unbounded Growth | State accumulates without cleanup | `constrain`, `measure` |
| Lost State | State not persisted across boundaries | `persist`, `recall` |
| Ordering Violation | Events processed out of order | `synchronize`, `state` |

### Detailed Mappings

#### LangChain #34887: Dict mutation during iteration
- **Symptoms**: RuntimeError during concurrent access
- **Root Cause**: Shared mutable state without synchronization
- **Capabilities**:
  - `checkpoint` → Snapshot state before iteration
  - `state` → Create immutable representation
  - `constrain` → Enforce no concurrent mutation
- **Mitigation**:
  ```
  checkpoint(state) → state(immutable_copy) → iterate → mutate(from_checkpoint)
  ```

#### Clawdbot #2397: Memory flush fires after compaction
- **Symptoms**: Data loss from event ordering violation
- **Root Cause**: Async events not properly sequenced
- **Capabilities**:
  - `synchronize` → Ensure proper event ordering
  - `state` → Track operation dependencies
  - `checkpoint` → Save state before dangerous operations
- **Mitigation**:
  ```
  synchronize([flush, compaction]) → checkpoint → compaction → verify → flush
  ```

#### Clawdbot #2384: Unbounded memory growth in groupHistories
- **Symptoms**: OOM errors over time
- **Root Cause**: No cleanup policy for accumulated history
- **Capabilities**:
  - `constrain` → Enforce maximum size
  - `state` → Track current usage
  - `persist` → Move old data to durable storage
- **Mitigation**:
  ```
  state(current_size) → constrain(max_size) → if exceeded: persist(oldest) → delete
  ```

#### AutoGen #2659: Parallel agent execution race condition
- **Symptoms**: Inconsistent state, data corruption
- **Root Cause**: Concurrent state access without locks
- **Capabilities**:
  - `synchronize` → Coordinate agent state access
  - `checkpoint` → Save before parallel operations
  - `state` → Create isolated state per agent
- **Mitigation**:
  ```
  checkpoint(shared_state) → delegate(agents, isolated_state_copy) →
    synchronize(results) → integrate → verify
  ```

---

## Category 2: Workflow/Type Failures

Workflow failures (~25%) occur at component boundaries where data contracts are not enforced.

### Key Patterns

| Pattern | Description | Prevention Capabilities |
|---------|-------------|------------------------|
| Type Mismatch | Output doesn't match expected type | `verify`, `constrain` |
| Format Error | Data in wrong format for consumer | `transform`, `verify` |
| Null/Empty | Missing data not handled | `constrain`, `detect` |
| Schema Drift | Schema changes break consumers | `verify`, `constrain` |

### Detailed Mappings

#### LangChain #34874: Inconsistent astream return types
- **Symptoms**: Different types from same method signature
- **Root Cause**: No return type contract enforcement
- **Capabilities**:
  - `verify` → Check return type matches signature
  - `constrain` → Enforce type at boundary
- **Mitigation**:
  ```
  astream() → verify(output, expected_type) → if mismatch: transform(to_expected)
  ```

#### LangChain #34876: Crash on empty messages
- **Symptoms**: NoneType error, uncaught exception
- **Root Cause**: No null/empty validation
- **Capabilities**:
  - `constrain` → Require non-empty input
  - `verify` → Check before processing
- **Mitigation**:
  ```
  input → constrain(non_empty) → if empty: return early or transform(default)
  ```

#### CrewAI #1823: Agent output not matching expected schema
- **Symptoms**: Downstream parsing failures
- **Root Cause**: No output validation against schema
- **Capabilities**:
  - `verify` → Validate against schema
  - `constrain` → Enforce schema compliance
  - `transform` → Coerce to expected format
- **Mitigation**:
  ```
  agent_output → verify(schema) → if invalid: transform(to_schema) or rollback
  ```

---

## Category 3: Coordination/Execution Failures

Coordination failures (~20%) involve multiple agents or async operations not properly synchronized.

### Key Patterns

| Pattern | Description | Prevention Capabilities |
|---------|-------------|------------------------|
| Fire-and-Forget | No acknowledgment of receipt | `synchronize`, `verify` |
| Timeout Mishandling | Improper timeout handling | `constrain`, `execute` |
| Dependency Conflict | Version incompatibilities | `constrain`, `verify` |
| Infinite Loop | No termination condition | `constrain`, `detect` |

### Detailed Mappings

#### Clawdbot #2402: Exec approval fire-and-forget
- **Symptoms**: Proceeds without confirmed approval
- **Root Cause**: No acknowledgment protocol
- **Capabilities**:
  - `synchronize` → Wait for acknowledgment
  - `receive` → Listen for approval response
  - `verify` → Confirm approval received
- **Mitigation**:
  ```
  send(approval_request) → receive(response, timeout) →
    verify(response.approved) → if timeout: rollback
  ```

#### LangChain #34357: Graph cycles cause infinite recursion
- **Symptoms**: Stack overflow, infinite loop
- **Root Cause**: No cycle detection
- **Capabilities**:
  - `detect` → Find cycles before execution
  - `constrain` → Limit recursion depth
  - `verify` → Check termination conditions
- **Mitigation**:
  ```
  graph → detect(cycles) → if cycles: reject →
    execute(with constrain(max_depth)) → verify(terminated)
  ```

#### AutoGen #2724: Nested agent calls exceed recursion limit
- **Symptoms**: RecursionError
- **Root Cause**: No depth limit on delegation
- **Capabilities**:
  - `constrain` → Limit delegation depth
  - `delegate` → Track depth in delegation
- **Mitigation**:
  ```
  delegate(task, depth+1) → constrain(depth < max_depth) →
    if exceeded: return partial or error
  ```

---

## Category 4: Data/Grounding Failures

Grounding failures (~10%) occur when agents make claims without evidence.

### Key Patterns

| Pattern | Description | Prevention Capabilities |
|---------|-------------|------------------------|
| Hallucination | Claims without evidence | `ground`, `verify` |
| Stale Data | Using outdated information | `verify`, `observe` |
| Missing Source | Cannot trace claim origin | `ground`, `audit` |
| False Success | Claiming success despite failure | `verify`, `detect` |

### Detailed Mappings

#### AutoGen #2945: Agent cites non-existent sources
- **Symptoms**: URLs don't exist, hallucinated citations
- **Root Cause**: No evidence verification
- **Capabilities**:
  - `ground` → Require evidence for citations
  - `verify` → Check sources exist
  - `detect` → Find unsupported claims
- **Mitigation**:
  ```
  citation → ground(source) → verify(source_exists) →
    if not grounded: remove citation or flag uncertainty
  ```

#### LangChain #34604: Agent claims tool succeeded when it failed
- **Symptoms**: Proceeds as if successful despite failure
- **Root Cause**: Error not checked after tool call
- **Capabilities**:
  - `verify` → Check tool result status
  - `ground` → Anchor success claim to evidence
  - `detect` → Identify error conditions
- **Mitigation**:
  ```
  tool_call → execute → verify(result.success) →
    ground(success_claim, result) → if failed: handle_error
  ```

---

## Category 5: Explainability Failures

Explainability failures (~5%) prevent understanding of agent decisions.

### Key Patterns

| Pattern | Description | Prevention Capabilities |
|---------|-------------|------------------------|
| Missing Audit | No record of decisions | `audit` |
| Error Leakage | Internal details exposed | `constrain`, `explain` |
| No Provenance | Cannot trace decision chain | `audit`, `explain` |
| Black Box | No visibility into process | `audit`, `explain` |

### Detailed Mappings

#### Clawdbot #2415: Internal errors leak to users
- **Symptoms**: Stack traces visible to end users
- **Root Cause**: No error sanitization
- **Capabilities**:
  - `constrain` → Filter what can be exposed
  - `explain` → Provide user-appropriate explanation
  - `audit` → Log full error internally
- **Mitigation**:
  ```
  error → audit(full_details) → explain(user_friendly) →
    constrain(no_internal_details) → send(sanitized_error)
  ```

#### AutoGen #2867: Cannot trace multi-agent decision
- **Symptoms**: No way to understand how decision was made
- **Root Cause**: No provenance chain recorded
- **Capabilities**:
  - `audit` → Record each decision step
  - `explain` → Provide reasoning for each step
- **Mitigation**:
  ```
  for each agent_turn:
    decision → explain(reasoning) → audit(step, reasoning, evidence)
  final_decision → audit(full_chain)
  ```

---

## Category 6: Trust/Conflict Failures

Trust failures (~5%) involve contradictory information without resolution.

### Key Patterns

| Pattern | Description | Prevention Capabilities |
|---------|-------------|------------------------|
| Contradiction | Conflicting sources accepted | `integrate`, `compare` |
| Misrouting | Output sent to wrong target | `verify`, `constrain` |
| Trust Bypass | Low-trust overrides high-trust | `constrain`, `ground` |
| No Resolution | Conflicts not resolved | `integrate`, `compare` |

### Detailed Mappings

#### Clawdbot #2412: Responses routed to wrong channel
- **Symptoms**: Privacy breach, wrong recipient
- **Root Cause**: Missing routing validation
- **Capabilities**:
  - `verify` → Validate target before send
  - `constrain` → Enforce routing rules
  - `ground` → Anchor to authorized targets
- **Mitigation**:
  ```
  response → verify(target_authorized) → constrain(valid_channels) →
    ground(target, permission_evidence) → send
  ```

#### AutoGen #2934: Conflicting agent opinions not resolved
- **Symptoms**: Deadlock, no consensus
- **Root Cause**: No conflict resolution strategy
- **Capabilities**:
  - `integrate` → Merge with conflict resolution
  - `compare` → Evaluate options against criteria
  - `synchronize` → Achieve consensus
- **Mitigation**:
  ```
  opinions → compare(against_criteria) →
    integrate(strategy=weighted_voting) → synchronize(final_decision)
  ```

---

## Summary: Capability Utilization

### Most Critical Capabilities (by coverage)

| Capability | Categories | Key Role |
|------------|-----------|----------|
| `verify` | 6/6 | Universal validation |
| `constrain` | 6/6 | Policy enforcement |
| `state` | 3/6 | State representation |
| `checkpoint` | 2/6 | Recovery point |
| `synchronize` | 3/6 | Coordination |
| `ground` | 3/6 | Evidence anchoring |
| `audit` | 3/6 | Decision recording |

### Composition Patterns

Most failures require **capability composition** rather than single capabilities:

1. **Safe Mutation**: `checkpoint → mutate → verify → (rollback if failed)`
2. **Validated Transform**: `input → constrain(schema) → transform → verify`
3. **Grounded Claim**: `claim → ground(sources) → verify → output`
4. **Coordinated Execution**: `delegate → synchronize → execute → verify`
5. **Audited Decision**: `decide → explain → audit → constrain(output)`

---

## References

- [Main Failure Taxonomy](../failure_taxonomy.md)
- [Capability Ontology](../../../schemas/capability_ontology.json)
- [Raw Issue Data](../raw_data/)
