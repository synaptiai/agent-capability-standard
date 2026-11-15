# FOUNDATION — what lands before the workstreams implement in parallel (ACS 1.2.0)

Phase 2 of round 3 (`tasks/todo.md`). Merged from the seven reconciled
designs in this directory (S1, S2a, S2b, S3, S4, S5, S6); every conflict
between them is resolved in `RECONCILIATION.md` (cited here as C1–C38).
Where a delta has one source, this file names the design part that holds its
exact text; where several designs touch one thing, the merged text is here.

The foundation is one change on the round-3 branch. It changes no run of a
1.1 workflow and no validation result: every behaviour it adds is a shape (a
schema member, a struct field, a code, a helper) that a workstream fills in
later, or a pure function with its vectors. After it, the six tracks (S1, S3,
S5, S6 in parallel worktrees; S2a → S2b → S4 as one chain) start from the
same base.

Contents:

- **Part A** — ontology 2.2.0: every delta, as exact YAML by node
- **Part B** — canonical and supporting schemas: every delta and new file
- **Part C** — diagnostic codes: final table, `diag.rs`/`errors.py`, merged §9 text
- **Part D** — `spec/STANDARD-v1.2.0.md` skeleton
- **Part E** — version lines
- **Part F** — shared code that lands here, file ownership, shared files,
  merge order and checks

---

## Part A. Ontology `schemas/capability_ontology.yaml` 2.1.0 → 2.2.0

`meta.version: 2.2.0` (and `meta.generated_at` to the foundation's date).
Nothing else in `meta` changes except `principles` (A1). No node, layer,
edge, flag or `required` list changes; no input or output field is removed
or retyped. Every change is MINOR or PATCH under §11.6 (A5).

Checked while reconciling: `scratchpad/tools/merge_ontology.py` applies
every delta below to the 2.1.0 file
(`scratchpad/merged_capability_ontology.yaml` is its output). The merged
ontology loads in the reference core, every `required` list and every
existing property is preserved, and the 89 catalogs of the repository
(`schemas/workflows/`, `schemas/workflow_catalog.yaml`, `examples/`,
`tests/fixtures/`) give exactly the same diagnostics under it as under 2.1.0.

### A1. `meta.principles` (S4 3.1.1)

```yaml
  principles:
  - Capabilities are atomic and composable into workflows
  - Every capability output carries evidence anchors, or is marked inferred with an inference method and a confidence
  - A capability whose output contract requires a confidence returns one in every output
  - High-risk capabilities require checkpoint + verification
  - Capabilities are organized into 9 cognitive layers
```

### A2. Templates applied to every node (S4 3.1.2)

Applied to all 36 `output_schema.properties`. `evidence_anchors` is replaced
in place; `confidence`, `inference_method` and `uncertainty` are appended in
that order after the node's other properties (a `confidence` a node already
has keeps its place and gets template B's description).

- **Template A** (`evidence_anchors`), all 36. `retrieve` ("Source
  references") and `inquire` ("Evidence supporting the ambiguity
  assessment") keep their description and append " (Standard v1.2 §6.5)."
- **Template B** (description of the existing `confidence`), the 23 that
  require it: retrieve, search, observe, detect, classify, measure, predict,
  compare, discover, plan, decompose, critique, explain, state, transition,
  attribute, ground, simulate, generate, transform, integrate, verify,
  inquire. `inquire` keeps "Confidence that clarification is needed" and
  appends " (Standard v1.2 §4.1.1)".
- **Template C** (`confidence` added, not required), the other 13: receive,
  execute, mutate, send, checkpoint, rollback, constrain, audit, persist,
  recall, delegate, synchronize, invoke.
- **Template D** (`inference_method`), all 36.
- **Template E** (`uncertainty`), 35: all but `measure` (A3).

#### Template A

```yaml
      evidence_anchors:
        type: array
        description: What the output is based on, as evidence anchors (Standard v1.2
          §6.5). An empty list grounds nothing, and the output is then marked inferred
          (§3.1).
        items:
          anyOf:
          - $ref: 'schemas/event_schema.yaml#/types/Anchor'
          - type: string
            description: Deprecated legacy form (Standard v1.2 §6.5) - an anchor given
              by its ref alone, with no kind; accepted, never counted toward grounding,
              removed in 2.0
          - type: object
            description: Deprecated legacy form (Standard v1.2 §6.5) - an object that
              is not an evidence anchor (no kind, or a kind outside the vocabulary);
              accepted, never counted toward grounding, removed in 2.0
```

#### Template B

```yaml
      confidence:
        type: number
        minimum: 0
        maximum: 1
        description: The producer's probability that the output's claim is correct,
          self-reported unless the host documents a calibration (Standard v1.2 §4.1.1)
```

#### Template C

```yaml
      confidence:
        type: number
        minimum: 0
        maximum: 1
        description: The producer's probability that the output's claim is correct,
          self-reported; given when the output is inferred (Standard v1.2 §3.1, §4.1.1)
```

#### Template D

```yaml
      inference_method:
        type: string
        description: How the output was reached when it is not grounded in evidence;
          with confidence it marks the output inferred (Standard v1.2 §3.1, §4.1.1).
          A producer should use model_knowledge, deduction, induction, abduction,
          analogy, statistical, simulation, assumption or an x- vendor value; a
          grounding policy (§5.20) requires one of them.
```

#### Template E

```yaml
      uncertainty:
        $ref: 'schemas/event_schema.yaml#/types/Uncertainty'
        description: The uncertainty of the output's principal value; its confidence
          equals the output's confidence (Standard v1.2 §4.1.1)
```

### A3. Nodes with their own changes (merged)

The full `input_schema` and `output_schema` of each node that more than the
templates change, after every workstream's delta. `<Template X>` stands for
the template of A2, verbatim. Sources: `audit` S2b 3.1 + S4 3.1.4; the five
memory and safety nodes S5 3.1; `delegate` S3 3.1 + S5 3.1; `inquire` and
`receive` S3 3.1; `measure` S4 3.1.3; `edge_types.conflicts_with` S3 3.1.

```yaml
- id: audit
  input_schema:
    type: object
    required:
    - event
    properties:
      event:
        type: object
        description: What happened, as the step reports it. The implementation records it,
          whatever its shape, as details.event of an action record of its own (capability
          audit), whose recorded_by and chain fields it sets itself; no member of the event
          becomes a member of that record (Standard v1.2 §6.4).
      context:
        type: object
        description: Event context
      retention:
        type: string
        description: How long the record is to be kept in the store it is written to, a duration
          (Standard v1.2 §5.10.1, e.g. 2555d or P30D); absent, the store's own policy applies
          (§6.3). A literal outside the grammar is W614.
      require_record:
        type: boolean
        description: The record must be written. When true, the step fails (R402, reason not_recorded)
          unless the output's recorded is true (Standard v1.2 §6.4). Default false.
  output_schema:
    type: object
    required:
    - recorded
    - evidence_anchors
    properties:
      recorded:
        type: boolean
        description: Whether the record was written.
      audit_id:
        type: string
        description: Audit record ID
      record:
        type: object
        description: The action record written for the event (Standard v1.2 §6.4).
      store:
        type: object
        description: Where the record was written, so a workflow can tell whether it outlives
          the session (Standard v1.2 §6.3, §6.6)
        properties:
          name:
            type: string
            description: The store, as the host documents it
          durability:
            type: string
            enum:
            - memory
            - session
            - durable
            description: memory - lost when its process ends; session - deleted with the session
              or thread; durable - kept until its retention removes it
          retention:
            type: string
            description: The retention the store applies to the record, a duration (§5.10.1);
              absent when it keeps records until they are removed by hand
      timestamp:
        type: string
        format: date-time
      evidence_anchors: <Template A>
      confidence: <Template C>
      inference_method: <Template D>
      uncertainty: <Template E>

- id: checkpoint
  input_schema:
    type: object
    required:
    - scope
    properties:
      scope:
        type: string
        description: What to capture, in the host's naming (paths or patterns, keys, resource
          identifiers, e.g. separated by white space); '*' for everything the host can restore
          (Standard v1.2 §4.4.1)
      label:
        type: string
        description: Checkpoint name
      metadata:
        type: object
        description: Additional metadata
  output_schema:
    type: object
    required:
    - checkpoint_id
    - evidence_anchors
    properties:
      checkpoint_id:
        type: string
        description: Checkpoint identifier
      timestamp:
        type: string
        format: date-time
      size:
        type: integer
        description: Checkpoint size
      mechanism:
        type: string
        description: How the checkpoint was taken, e.g. vcs_snapshot, file_copy, store_snapshot,
          savepoint, or an x- name (Standard v1.2 §4.4.1)
      captured:
        type: array
        items:
          type: string
        description: What the checkpoint holds, in the host's naming
      excluded:
        type: array
        items:
          type: string
        description: What the scope named that the checkpoint does not hold, such as a secret
          the host will not copy or the host's own records, which no checkpoint holds (Standard
          v1.2 §4.4.1)
      digest:
        type: string
        description: Digest of the captured content as <algorithm>:<lowercase hex>, e.g. sha256
          followed by the hex digest, which a rollback's verification compares
      expires_at:
        type: string
        format: date-time
        description: When the host may discard the content, after which a rollback cannot
          restore it; not its validity for authorising a step (Standard v1.2 §5.2.2)
      evidence_anchors: <Template A>
      confidence: <Template C>
      inference_method: <Template D>
      uncertainty: <Template E>

- id: rollback
  input_schema:
    type: object
    required:
    - checkpoint_id
    properties:
      checkpoint_id:
        type: string
        description: Checkpoint to restore
      scope:
        type: string
        description: Part of what the checkpoint captured to restore, in the host's naming;
          all of it when absent. An item it names that the checkpoint did not capture is unrestored
          (not_captured) (Standard v1.2 §4.4.1)
  output_schema:
    type: object
    required:
    - restored
    - evidence_anchors
    properties:
      restored:
        type: boolean
        description: True only if everything the rollback concerns is back in its checkpointed
          state, and then unrestored is empty; the step completes either way (Standard v1.2
          §4.4.1)
      previous_state:
        type: any
        description: State before rollback
      restored_state:
        type: any
        description: State after rollback
      unrestored:
        type: array
        description: What the rollback concerns that is not back in its checkpointed state,
          including an item its scope names that the checkpoint did not capture; empty exactly
          when restored is true
        items:
          type: object
          required:
          - item
          - reason
          properties:
            item:
              type: string
            reason:
              type: string
              description: failed, conflict, discarded, not_captured (the rollback's scope
                names it and the checkpoint did not capture it), or an x- reason
            detail:
              type: string
      not_covered:
        type: array
        description: Changes since the checkpoint that it never covered, which no rollback
          to it restores; they do not make restored false
        items:
          type: object
          required:
          - item
          - reason
          properties:
            item:
              type: string
            reason:
              type: string
              description: transmitted, delegated, outside_scope, or an x- reason
            detail:
              type: string
      changes_reverted:
        type: array
        description: What the rollback undid
        items:
          type: object
          required:
          - item
          - operation
          properties:
            item:
              type: string
            operation:
              type: string
              enum:
              - create
              - modify
              - delete
              - other
            summary:
              type: string
      verification:
        type: object
        description: The digest of the restored content, computed as the checkpoint's was,
          and whether it matches the checkpoint's digest
        properties:
          digest:
            type: string
          match:
            type: boolean
      evidence_anchors: <Template A>
      confidence: <Template C>
      inference_method: <Template D>
      uncertainty: <Template E>

- id: send
  input_schema:
    type: object
    required:
    - destination
    - payload
    properties:
      destination:
        type: string
        description: Where the data goes, in the host's naming (a URL, an address, a queue
          or a channel); checked against the destination policies in force (Standard v1.2
          §4.4.2)
      payload:
        type: any
        description: Data to send
      protocol:
        type: string
        description: Communication protocol
  output_schema:
    type: object
    required:
    - sent
    - evidence_anchors
    properties:
      sent:
        type: boolean
        description: Whether the destination accepted the data; a delivered transmission cannot
          be recalled (Standard v1.2 §4.4.2)
      response:
        type: any
        description: Response if any
      timestamp:
        type: string
        format: date-time
      compensation:
        type: object
        description: How the transmission's effect can be compensated, in the form of world_state_schema.yaml
          TransitionRule.rollback; nothing performs it automatically (Standard v1.2 §4.4.2)
        properties:
          strategy:
            type: string
          inverse_effects:
            type: array
            items:
              type: string
      evidence_anchors: <Template A>
      confidence: <Template C>
      inference_method: <Template D>
      uncertainty: <Template E>

- id: persist
  input_schema:
    type: object
    required:
    - data
    properties:
      data:
        type: any
        description: Data to store; it round-trips as I-JSON, and data holding a secret the
          host recognises is refused (Standard v1.2 §4.5, §6.7)
      key:
        type: string
        description: Storage key; without one the host chooses it and returns it as key
      ttl:
        type: string
        description: Time to live, a duration (Standard v1.2 §5.10.1) longer than zero; the
          entry ends ttl after stored_at (§4.5)
      scope:
        type: string
        description: Who can read the entry and how long it lasts, one of run (the run the
          host started and every run nested in it), session, user, project, global or an x-
          name; the host's default when absent (Standard v1.2 §4.5)
  output_schema:
    type: object
    required:
    - stored
    - evidence_anchors
    properties:
      stored:
        type: boolean
        description: When true, a recall of the key in the scope returns the data until the
          entry ends; when false, nothing was written (Standard v1.2 §4.5)
      key:
        type: string
        description: Storage key
      scope:
        type: string
        description: The scope used
      stored_at:
        type: string
        format: date-time
        description: When the entry was stored
      expires_at:
        type: string
        format: date-time
        description: When the entry ends, for an entry with a ttl
      timestamp:
        type: string
        format: date-time
        description: Deprecated, the same instant as stored_at (Standard v1.2 §4.5)
      evidence_anchors: <Template A>
      confidence: <Template C>
      inference_method: <Template D>
      uncertainty: <Template E>

- id: recall
  input_schema:
    type: object
    required:
    - key
    properties:
      key:
        type: string
        description: Storage key, compared by code point
      default:
        type: any
        description: Default if not found
      scope:
        type: string
        description: The scope to read, as for persist (Standard v1.2 §4.5)
  output_schema:
    type: object
    required:
    - data
    - evidence_anchors
    properties:
      data:
        type: any
        description: The entry's data, or default when no live entry has the key
      found:
        type: boolean
        description: Whether a live entry has the key in the scope (Standard v1.2 §4.5)
      scope:
        type: string
        description: The scope used
      stored_at:
        type: string
        format: date-time
        description: When the entry was stored
      expires_at:
        type: string
        format: date-time
        description: When the entry ends, for an entry with a ttl
      evidence_anchors: <Template A>
      confidence: <Template C>
      inference_method: <Template D>
      uncertainty: <Template E>

- id: delegate
  input_schema:
    type: object
    required:
    - task
    - agent
    properties:
      task:
        type: object
        description: Task to delegate
      agent:
        type: string
        description: Target agent, by the name its agent manifest and the workflow's agents
          use; a target name, not a principal (STANDARD v1.2 §5.15, §5.15.2)
      constraints:
        type: object
        description: Delegation constraints
      fresh_context:
        type: boolean
        description: Start the delegate without this agent's context (delegation@1, STANDARD
          v1.1 §5.15)
      model_family:
        type: string
        description: Model family the delegate should run on, the lowercase name of a provider's
          model line such as claude or gpt (as derived from a model identifier), compared
          exactly (delegation@1, STANDARD v1.2 §5.15)
      role:
        type: string
        description: Role the delegate takes, e.g. reviewer (delegation@1)
      read_only:
        type: boolean
        description: The delegate may read but must not change anything (files, repositories,
          external state); the host attests it in effective. A host that cannot enforce it
          refuses the delegation; in a workflow that targets 1.2, an accepted delegation the
          host does not attest as read_only fails (delegation@1, STANDARD v1.2 §5.15, §5.15.2)
      continues:
        type: string
        description: The task_id of an earlier delegation whose delegate the host continues
          instead of starting a new one; the call still returns a task_id of its own, a continued
          delegation never has a fresh context, and null delegates anew (STANDARD v1.2 §5.15.3)
      accept_from:
        type: array
        items:
          type: string
        description: For a delegate that waits, principals to accept its result from; others
          are dropped and counted (delegation@1, STANDARD v1.1 §5.13, §5.15)
      sender_check:
        type: array
        items:
          type: string
        description: For a delegate that waits, how the result's sender must have been authenticated
          (identity@1, STANDARD v1.1 §5.17)
      accept_trust_classes:
        type: array
        items:
          type: string
        description: For a delegate that waits, trust classes to accept its result from (identity@1,
          STANDARD v1.1 §5.17)
      always_ask_trust_classes:
        type: array
        items:
          type: string
        description: For a delegate that waits, trust classes whose result (and a result with
          no trust class) makes any step that requires approval and uses it be asked of a
          person (identity@1, STANDARD v1.1 §5.17)
  output_schema:
    type: object
    required:
    - accepted
    - evidence_anchors
    properties:
      accepted:
        type: boolean
      task_id:
        type: string
        description: Delegated task ID
      agent:
        type: string
        description: Assigned agent
      effective:
        type: object
        description: The delegation settings actually used, as attested by the host
        properties:
          fresh_context:
            type: boolean
          model_family:
            type: string
            description: The family of the model the delegate ran on, as the host attests
              it, derived from the model's identifier (STANDARD v1.2 §5.15)
          model_id:
            type: string
            description: The provider's identifier of the model the delegate ran on, such
              as claude-opus-4-1, as the host attests it (STANDARD v1.2 §5.15, §5.17)
          role:
            type: string
          read_only:
            type: boolean
          checkpointed:
            type: boolean
            description: The host attests that, before each change it makes, the delegate
              has a checkpoint valid in the scope where that change is checked (Standard v1.2
              §5.15.4)
          identity:
            type: object
            description: The agent_identity of the party that took the delegation (identity@1);
              a waiting delegate keeps only its results
      result:
        type: object
        description: The delegate's result, when the step waits for it (wait@1, STANDARD v1.1
          §5.13), with its sender (and, with identity@1, its sender_identity)
      evidence_anchors: <Template A>
      confidence: <Template C>
      inference_method: <Template D>
      uncertainty: <Template E>

- id: inquire
  input_schema:
    type: object
    required:
    - ambiguous_input
    properties:
      ambiguous_input:
        type: any
        description: The underspecified request or goal
      context:
        type: object
        description: Available context for question generation
      max_questions:
        type: integer
        default: 3
        description: Maximum clarifying questions to generate
  output_schema:
    type: object
    required:
    - questions
    - ambiguity_analysis
    - evidence_anchors
    - confidence
    properties:
      inquiry_id:
        type: string
        description: Names this inquiry; the items that answer it carry the same inquiry_id,
          so a wait can correlate on it (STANDARD v1.2 §5.13.1)
      questions:
        type: array
        items:
          type: object
          properties:
            id:
              type: string
              description: Unique within the inquiry; an answer names it as its question_id
                (STANDARD v1.2 §5.13.1)
            question:
              type: string
            parameter:
              type: string
              description: What parameter this resolves; keys the answer when the question
                has no id
            answer_type:
              type: string
              enum:
              - text
              - choice
              - boolean
              - number
              description: 'The type of the answer: text is a string, choice one of options,
                boolean or number (STANDARD v1.2 §5.13.1)'
            options:
              type: array
              description: Suggested answers if bounded; for answer_type choice, the answers
                allowed
        description: Clarifying questions to resolve ambiguity
      ambiguity_analysis:
        type: object
        properties:
          missing_parameters:
            type: array
          conflicting_interpretations:
            type: array
          confidence_without_clarification:
            type: number
      evidence_anchors:
        type: array
        description: Evidence supporting the ambiguity assessment (Standard v1.2 §6.5).
        items:
          anyOf:
          - $ref: schemas/event_schema.yaml#/types/Anchor
          - type: string
            description: Deprecated legacy form (Standard v1.2 §6.5) - an anchor given by
              its ref alone, with no kind; accepted, never counted toward grounding, removed
              in 2.0
          - type: object
            description: Deprecated legacy form (Standard v1.2 §6.5) - an object that is not
              an evidence anchor (no kind, or a kind outside the vocabulary); accepted, never
              counted toward grounding, removed in 2.0
      confidence:
        type: number
        minimum: 0
        maximum: 1
        description: Confidence that clarification is needed (Standard v1.2 §4.1.1)
      inference_method: <Template D>
      uncertainty: <Template E>

- id: receive
  input_schema:
    type: object
    properties:
      channel:
        type: string
        description: Source channel
      filter:
        type: object
        description: Event filter criteria
      timeout:
        type: string
        description: Wait timeout
      accept_from:
        type: array
        items:
          type: string
        description: Principals to accept items from; items from others are dropped and counted
          (delegation@1, STANDARD v1.1 §5.15)
      sender_check:
        type: array
        items:
          type: string
        description: How a sender must have been authenticated (agent_identity authenticated_by
          values); items whose sender identity says otherwise, or that carry none, are dropped
          and counted (identity@1, STANDARD v1.1 §5.17)
      accept_trust_classes:
        type: array
        items:
          type: string
        description: Trust classes to accept items from; others, and items with no trust class,
          are dropped and counted (identity@1, STANDARD v1.1 §5.17)
      always_ask_trust_classes:
        type: array
        items:
          type: string
        description: Trust classes whose items (and items with no trust class) make any step
          that requires approval and uses them be asked of a person, whatever mandate would
          cover it (identity@1, STANDARD v1.1 §5.17)
  output_schema:
    type: object
    required:
    - data
    - evidence_anchors
    properties:
      data:
        type: array
        items:
          type: object
          properties:
            sender:
              type: string
              description: The host-authenticated principal that sent the item
            sender_identity:
              type: object
              description: The sender's identity as the host reported it (agent_identity_schema.yaml;
                identity@1, STANDARD v1.1 §5.17)
            inquiry_id:
              type: string
              description: For answers to an inquiry, the inquiry_id of the inquire output
                they answer (STANDARD v1.2 §5.13.1)
            answers:
              type: array
              items:
                type: object
                required:
                - question_id
                properties:
                  question_id:
                    type: string
                    description: The id of the question answered, or its parameter when it
                      has no id
                  value:
                    type: any
                    description: The answer, of the question's answer_type
              description: For answers to an inquiry, one entry per question answered (STANDARD
                v1.2 §5.13.1)
        description: Received data/events
      source:
        type: string
        description: Event source
      timestamp:
        type: string
        format: date-time
      evidence_anchors: <Template A>
      confidence: <Template C>
      inference_method: <Template D>
      uncertainty: <Template E>

- id: measure
  input_schema:
    type: object
    required:
    - target
    - metric
    properties:
      target:
        type: any
        description: What to measure
      metric:
        type: string
        description: Measurement type
      unit:
        type: string
        description: Unit of measurement
  output_schema:
    type: object
    required:
    - value
    - uncertainty
    - evidence_anchors
    - confidence
    properties:
      value:
        type: number
      uncertainty:
        type: object
        description: The value's uncertainty. lower and upper bound the value; the other members
          are those of an Uncertainty, whose interval.low and interval.high then equal lower
          and upper (Standard v1.2 §4.1.1)
        properties:
          lower:
            type: number
          upper:
            type: number
          type:
            type: string
            enum:
            - epistemic
            - aleatoric
            - mixed
          confidence:
            type: number
            minimum: 0
            maximum: 1
          interval:
            type: object
            properties:
              low:
                type: number
              high:
                type: number
          distribution:
            type: object
            description: e.g. {name, mean, stdev}
          notes:
            type: string
      unit:
        type: string
      evidence_anchors: <Template A>
      confidence: <Template B>
      inference_method: <Template D>

```

`edge_types.conflicts_with` (S3 3.1), `description` and `semantics` replaced:

```yaml
edge_types:
  conflicts_with:
    description: 'No concurrency within a workflow: ''from'' and ''to'' must not run in the
      same parallel_group; the rule does not reach across runs or agents (STANDARD v1.2 §4.3)'
    semantics: Validator MUST reject the pair within one parallel_group (F504); in sequence
      they are allowed; a trigger with overlap allow_all on a workflow that exercises both,
      itself or through the workflows it invokes, is W623
    transitive: false
    symmetric: true
```

`integrate` (S6 3.1), one description (PATCH):

```yaml
- id: integrate
  input_schema:
    properties:
      conflict_resolution:
        type: string
        description: 'How conflicting values are resolved: a strategy of Standard
          v1.2 §8.2 (highest_score, the default; prefer_authoritative_sources;
          prefer_recent; prefer_high_confidence; merge_with_uncertainty;
          escalate_to_human)'
```

### A4. Quoting and dialect

Quote every description that would contain `: ` (S4). The ontology uses the
dialect of §4.1.2 (S6): the new `$ref`s point at
`schemas/event_schema.yaml#/types/Anchor` and `#/types/Uncertainty` (B2),
which every loader of the ontology resolves from the repository root; the
three-branch `anyOf` and `enum` on new members are in the dialect. No
`pattern` is added to the ontology.

### A5. Change classification (§11.6; S6 3.1, with C32's two rows)

| Workstream | Change | §11.6 row | Version |
|---|---|---|---|
| S1, S2a | none | — | — |
| S2b | `audit` input `require_record`; output `record`; `event` description | optional input; optional output field; description | MINOR; MINOR; PATCH |
| S3 | `delegate` input `continues`; `agent`, `model_family`, `read_only` descriptions | optional input; description | MINOR; PATCH |
| S3 | `delegate.effective.model_id` | optional member of an output object | MINOR |
| S3 | `inquire` output `inquiry_id`; `questions` items gain `id`, `answer_type` | optional output field; members of an output field's items left open | MINOR |
| S3 | `receive.data` items gain `inquiry_id`, `answers` | members of an output field's items left open | MINOR |
| S3 | `edge_types.conflicts_with` description and semantics | description | PATCH |
| S4 | `evidence_anchors.items` on 36 outputs | items of an existing output field left open | MINOR |
| S4 | `confidence` descriptions (23); `confidence` (13), `inference_method` (36), `uncertainty` (35) added | description; optional output field | PATCH; MINOR |
| S4 | `measure.uncertainty` members; `audit.retention` description; `audit.store`; `meta.principles` | members left open; description; optional output field; description | MINOR; PATCH; MINOR; PATCH |
| S5 | `checkpoint`, `rollback`, `send`, `persist`, `recall`: optional properties and descriptions | optional input / output field; description | MINOR; PATCH |
| S5 | `delegate.effective.checkpointed` | optional member of an output object | MINOR |
| S6 | `integrate.conflict_resolution` description | description | PATCH |

The foundation re-checks the ontology diff against this table; a row that
is not MINOR or PATCH is refused.

### A6. Regenerated with the ontology

`python tools/sync_skill_schemas.py` (36 `skills/*/schemas/output_schema.yaml`,
resolved contracts, refs inlined; the vendored ontology copies with their
`$ref`s pointed at the co-located `event_schema.yaml`; the vendored canonical
schemas), `python scripts/gen_capability_json_schemas.py`,
`python scripts/gen_standard_agents_binding.py` (writes
`packages/acs-core/src/ontology.gen.ts`, F3). The code these runs need is in
F2.

---

## Part B. Schemas

Canonical schemas are the five of §6.1. Every change below is additive under
§11.4 (optional members, an enum value, descriptions, an anchor kind pattern
that widens an enum), except where stated.

### B1. `schemas/world_state_schema.yaml` 1.1.0 → 1.2.0 (canonical; S2a, S2b, S3, S4, S5, S6)

One bump. `schema.version: 1.2.0`. The vendored copies under
`skills/*/reference/` are refreshed by `tools/sync_skill_schemas.py`.

**`types.ActionRecord.properties`**, final order (unchanged members named
only):

```yaml
      action_id: …                       # unchanged
      run_id:                            # S2b
        type: string
        description: The run the record belongs to (Standard v1.2 §5.19) or, for a
          record of a tool call, the layer scope its safety layer keeps records for
          (§5.18.5).
      frame:
        type: array
        items:
          type: string
        description: For a step of a run, the workflows of its nested runs, root first.
      step:
        type: integer
        minimum: 0
        description: For a step of a run, its index in the last workflow of frame.
      capability:
        type: string
        description: The ontology capability the action performs.
      tool:
        type: string
        description: For a tool call, the name the host offers the tool under (§5.18).
      call_id:
        type: string
        description: For a tool call, the host's identifier of the call, if it has one.
      checkpoint_id:
        type: string
        description: The checkpoint the action used, took or restored.
      idempotency_key:                   # S5
        type: string
        description: For a step that called its capability, the key of the pass, under
          which the host performs the effect at most once (Standard v1.2 §4.4.2).
      code:                              # S2b
        type: string
        description: The diagnostic code (Standard v1.2 §9) of an action that failed,
          was refused or was cancelled.
      reason_code:
        type: string
        description: Why, as a token (Standard v1.2 §5.19.7), such as unsupported_domain.
      details:
        type: object
        description: Other data the record carries, such as the event an audit step
          recorded (details.event) or how a run ended (a run record, Standard v1.2
          §5.19.8, §6.4).
      recorded_by:                       # S2b; settings from S1 (C14)
        type: object
        required:
        - name
        properties:
          name:
            type: string
          version:
            type: string
          config_sha256:
            type: string
            description: SHA-256 of the configuration the implementation applied.
          settings:
            type: object
            description: The settings that decided the action, listed where they are
              few (Standard v1.2 §5.18.8), such as a safety layer's approval mode
              and checkpoint maximum age.
        description: The implementation that wrote the record, set by that
          implementation only, never taken from what it records (Standard v1.2 §6.4).
      prev_hmac:
        type: string
        description: In an append-only log of records, the hmac of the record before
          this one; empty for the first (Standard v1.2 §6.4).
      hmac:
        type: string
        description: In such a log, the HMAC-SHA-256 of this record without hmac, under
          the log's key, as lowercase hexadecimal. The log computes prev_hmac and hmac
          when it appends the record, never taking them from what it records.
      timestamp:                         # S2a
        type: string
        description: When the record was written. A record that a resumed run
          updates (Standard v1.2 §5.14.1) carries the time of its latest change.
      actor: …                           # unchanged
      actor_identity: …                  # unchanged
      always_ask:                        # S6
        type: boolean
        description: The action used an item from an always-ask trust class, so no
          standing mandate could approve it (Standard v1.1 §5.17). A step that a
          domain profile requires a person for carries person_required instead
          (Standard v1.2 §5.21.3).
      person_required:                   # S6
        type: boolean
        description: An applied domain profile required a person's approval for this
          step (require_human or block_autonomous), so no standing mandate could
          approve it (Standard v1.2 §5.21.3). Unlike always_ask it marks no data.
      intent: …                          # unchanged
      status:                            # S2a + S2b, merged (C13)
        type: string
        enum:
        - planned
        - approved
        - rejected
        - expired
        - executed
        - failed
        - rolled_back
        - cancelled
        description: rejected, an action that was refused before it ran, by its
          approvers (Standard v1.1 §5.14) or by an executor or a safety layer
          (Standard v1.2 §5.18), with code saying why; expired, an approval that
          lapsed; an action deferred to a queue stays planned (its approval, if
          any, says why it was not approved now) until its run is resumed, which
          updates this record in place and keeps its action_id (Standard v1.2
          §5.14.1), and a run record is planned while its run can be resumed
          (§5.19.8); a planned record in the terminal action of a run that did
          not end deferred is abandoned and never carried out; cancelled, an
          action that was approved or queued when its run was cancelled, or had
          started and may have been carried out (Standard v1.2 §5.19.5).
      reason:                            # S2b
        type: string
        nullable: true
        description: Why the action did not go ahead or failed, in words (rejected,
          expired, refused in an unattended run, cancelled); reason_code says it as
          a token.
      approval:
        properties:
          digest:                        # S2a
            type: string
            description: SHA-256 of the canonical JSON (RFC 8785) of the values
              shown to the approvers, as 64 lowercase hexadecimal digits
              (Standard v1.2 §5.14).
          decision: …                    # unchanged
          decision_id:                   # S2b
            type: string
            description: The identifier the host gave the decision; single-use
              within the run (Standard v1.2 §5.14, §5.19.1). Absent when no decision
              arrived (expired).
          approvers:                     # S2a
            type: array
            items:
              type: string
            description: The distinct approvers that counted toward
              min_approvers. With attested approver identities, their principals
              (Standard v1.2 §5.17).
          approver_identities:           # S2a
            type: array
            items:
              $ref: '#/types/AgentIdentity'
            description: The identities of the approvers that counted, as the host
              attested them (Standard v1.2 §5.17, identity@1), one per principal.
              Present only when the decision carried identities.
          mode:                          # S2a
            type: string
            enum:
            - in_session
            - out_of_band
            description: Where the approvers were asked (Standard v1.2 §5.14).
              in_session, the party attending the run, in its session;
              out_of_band, through a channel separate from the run's session,
              whose approvers need not attend the run.
          mandate_ref: …                 # unchanged
          decided_at: …                  # unchanged
          expires_at: …                  # unchanged
      plan_ref: …                        # unchanged (and changes, verification, anchors)
```

**Other types**:

- `types.AgentIdentity` (S3 3.2): `model_family` gets the new description and
  `model_id` follows it, identical to `agent_identity_schema.yaml` (B5);
  `tools/validate_canonical_schemas.py` `validate_identity_type` checks it.
- `types.Anchor` (S4 3.3): byte-identical to the event schema's `Anchor` (B2)
  except the first sentence of its description ("An evidence anchor
  (Standard v1.2 §6.5); the same type as event_schema.yaml's Anchor.").
  `types.Uncertainty` unchanged. `tools/validate_canonical_schemas.py` gains
  `validate_shared_types` (the two files' `Anchor` and `Uncertainty` equal
  once `description` keys are removed).
- `world_state.properties.retention_policy` and its `max_age` members (S4
  3.3, exact YAML there).
- `types.TransitionRule.properties.rollback` description (S5 3.2).
- `types.EntityRef.properties.entity_id` and the entity `id`/`type`
  descriptions (S6 3.4).

### B2. `schemas/event_schema.yaml` 1.1.0 → 1.2.0 (canonical; S4 3.2)

`types.Anchor` replaced (`ref`, `kind` required; `kind` pattern
`^(file|url|tool|log|sensor|human_note|api|record|x-[a-z0-9][a-z0-9_.-]*)$`;
`timestamp`, `excerpt` nullable; `digest` `^sha256:[0-9a-f]{64}$`);
`types.Uncertainty` gains `interval` and `distribution`; `event.properties.raw`
description; new optional `event.properties.redactions`. Exact text: S4 3.2.

### B3. `schemas/entity_taxonomy.yaml` 1.0.0 → 1.1.0 (canonical; S6 3.3)

`id_convention.pattern` and the §7.1 example. Exact text: S6 3.3.

### B4. `schemas/authority_trust_model.yaml` 1.1.0 → 1.2.0 (canonical; S6 3.5 + S2b 3.3)

S6's bump with the additive `field_authority.fields`; S2b's §8.4 comments on
`overrides` ride on it (no value changes). Exact text: S6 3.5, S2b 3.3.
`schemas/identity_resolution_policy.yaml` stays 1.0.0.

### B5. `schemas/agent_identity_schema.yaml` 1.0.0 → 1.1.0 (supporting; S3 3.3)

`model_family` description and optional `model_id`; no pattern. One bump
(S2a uses the schema unchanged).

### B6. New `schemas/agent_manifest_schema.yaml` 1.0.0 (supporting; S3 3.4)

Full content in S3 3.4: required `agent`, `standard`, `ontology`,
`capabilities`; optional `task`, `version`, `description`, `x-` keys.

### B7. `schemas/workflow_catalog.schema.json` (supporting; merged)

Each source is exact in its design; they touch different members:

| Member | Change | Source |
|---|---|---|
| top-level `catalog` | `if {type: object, required: [steps]} then #/$defs/workflow else #/$defs/catalog_manifest` | S3 3.5 |
| `$defs.catalog_manifest` | new | S3 3.5 |
| `$defs.workflow.properties.agents` | new (non-empty list of distinct non-empty strings) | S3 3.5 |
| `$defs.workflow.properties.domain`; `$defs.step` `domain`, `workflow_id` | descriptions | S3 3.5 |
| `$defs.workflow.properties.grounding`, `$defs.grounding` | new | S4 3.4 |
| `workflow_extensions.requires` enum | gains `grounding@1` | S4 3.4 |
| `$defs.fireable_code` | gains `F505` | S4 3.4 |
| `$defs.approval.properties.approver.properties` | `sender_check`, `accept_trust_classes` | S2a 3.3 |
| `$defs.approval` `mode`, `expires`; step `approval` description | default `in_session`, descriptions | S2a 3.3 |
| `parallel_group`, `join` | descriptions (join stays a string) | S2b 3.4 |
| `profile` | description (descriptive in every version) | S6 3.6a |

### B8. New `schemas/host_protocol.schema.json` (supporting; S2b 3.5, merged)

S2b 3.5 is the base (it already carries S2a's members:
`RequestApproval.queued_action_id`, `Decision.approver_identities`, the
approver fields). Merged into it:

- `$defs.reason.pattern` (C5):
  `^(x-[a-z0-9][a-z0-9_.-]{0,61}|unsupported_capability|unsupported_domain|not_recorded|outcome_unknown|key_conflict|destination_not_allowed|unsupported_scope|unsupported_ttl|over_capacity|secret_in_data|below_minimum_confidence|invalid_confidence)$`
- `$defs.Output.properties.evidence_seen` (S4 3.6):
  `{"type": "array", "items": {"type": "string"}, "description": "The refs of the evidence the host attests the output's producer had for this answer; absent, it attests nothing (section 3.1, 5.20)."}`
- `$defs.InvokeCapability.properties.idempotency_key` (S5 3.3), **not yet in
  `required`**: S5 adds it to `required` when it merges, with the executor
  that emits it (C33).
- `$defs.RolledBack.properties.not_covered` and new `$defs.not_covered_item`
  (S5 3.3, exact).
- `$defs.run_options` (informative), `required` gains `header`; properties
  gain:
  - `header` (S6 3.10): `{"oneOf": [{"type": "string", "pattern": "^\\d+\\.\\d+(\\.\\d+)?$"}, {"type": "null"}], "description": "Informative: the version the catalog's header declares, or null for a catalog without one (section 11.5). Always given."}`
  - `profiles` (S6 3.10): `{"type": "array", "items": {"type": "object"}}`
  - `grounding` (S4 3.6): `{"type": "array", "items": {"$ref": "workflow_catalog.schema.json#/$defs/grounding"}}`
  - `destinations` (S5 3.3): `{"type": "array", "items": {"type": "array", "items": {"type": "string", "minLength": 1}}}`
  - `catalogs` (S3, C4): `{"type": "array", "items": {"type": "object", "required": ["catalog", "header"], "properties": {"catalog": {"type": "object"}, "header": {"oneOf": [{"type": "string", "pattern": "^\\d+\\.\\d+(\\.\\d+)?$"}, {"type": "null"}]}}, "additionalProperties": false}}`
  - `agents` (S3): `{"type": "array", "items": {"type": "object"}, "description": "Informative: agent manifests (section 5.15.1)."}`
- Trace kinds (informative, in the schema's `trace_event` description and
  `docs/guides/RUNNING_WORKFLOWS.md`): `run_resumed`, `invoke_resumed` (S2a),
  `grounding` (S4), `person_required` (S6), S2b's own.

`run_id` in every action's head is required from S2b's merge (it emits it).
Until a member's implementer merges, the schema declares it optional (C33).

### B9. New `tests/conformance/runtime/schema/fixture.schema.json` (S2b 3.6, merged)

S2b 3.6 is the base. Top-level properties added (C4, C8), with `header` in
`required`:

```json
"header": {
  "oneOf": [
    { "type": "string", "pattern": "^\\d+\\.\\d+(\\.\\d+)?$" },
    { "type": "null" }
  ],
  "description": "The version the catalog's '# Standard version:' header declares, or null for a catalog without one; the runner passes it to start as is (STANDARD v1.2 §11.5, §5.19.2). Required."
},
"catalogs": {
  "type": "array",
  "items": {
    "type": "object",
    "required": ["catalog", "header"],
    "additionalProperties": false,
    "properties": {
      "catalog": { "type": "object" },
      "header": { "oneOf": [{ "type": "string", "pattern": "^\\d+\\.\\d+(\\.\\d+)?$" }, { "type": "null" }] }
    }
  },
  "description": "Further catalogs of the run's catalog set (§5.1.1), each with its header's version."
},
"agents": { "type": "array", "items": { "type": "object" }, "description": "Agent manifests the host gives (§5.15.1)." },
"destinations": { "type": "array", "items": { "type": "array", "items": { "type": "string" } }, "description": "The run's destination policies (§4.4.2); absent: none." },
"grounding": { "type": "array", "items": { "type": "object" }, "description": "Grounding policies the host applies (§5.20); absent: none." },
"profiles": { "type": "array", "items": { "type": "object" }, "description": "Domain profiles the host applies (§5.21); absent: none." }
```

Every existing fixture (the 175 generated and the 20 under
`tests/conformance/contrib/`) gains `"header": null` in the foundation.

### B10. New `schemas/interop/tool_binding.schema.json` (S1 3.3, as reconciled)

S1 3.3's content, which now also holds the optional `standard` (§11.6), an
`ontology` pattern of `MAJOR.MINOR[.PATCH]` and S5's `destination` (refused
together with `control`) (C25).

### B11. New `schemas/interop/evidence.schema.json` (S4 3.5)

Full content in S4 3.5: `EvidenceAnchor`, `Kind`, `Digest`, `Correlation`,
`EvidenceRecord`, `StoreInfo`, `EvidenceRecorded`.

### B12. `schemas/profiles/profile_schema.yaml` 1.0.0 (S6 3.6)

Full content in S6 3.6 (it merges S3's `workflows` description, S4's
`required_anchor_types` and `require_grounding` descriptions and S5's
`allowed_destinations`). The shipped profiles are migrated by S6 (3.7), not
here.

### B13. `schemas/capability_ontology.schema.json` (S6 3.2)

The dialect metaschema. Lands here, since the ontology of Part A must pass
it in CI.

### B14. Generated files

`schemas/generated/capability_contracts.schema.json` and
`schemas/interop/standard_agents_annotation.schema.json` are regenerated by
their generators (A6, F2); S1 later changes the annotation schema's
generator (S1 3.4).

### B15. Vector files that land here

- `tests/conformance/destinations/match.json` (S5 3.7, full content), with
  `core/src/destination.rs` (F1).
- `tests/conformance/approval/digests.json`: every vector gains
  `"kind": "step"`; the `fields` doc gains `kind` and `call` (S2a 5.10;
  C36). S1 adds the `tool_call` vectors and S2a the `unresolved_reference`
  vector and the normative header in their workstreams.

Every other vector file (bindings, calls, triggers, grounding, secrets,
memory, domains, agents, families, inquiry, profiles, trust, entities)
lands with the workstream that writes it.

---

## Part C. Diagnostic codes

### C1. Final table of new codes (15)

The provisional numbers of the designs are rewritten in every design file
(RECONCILIATION C2). Families continue the existing ranges (V101–V109,
B201–B206, S301–S304, R401–R406, F501–F505, W601–W616).

| Code | Name | Severity | Meaning (§9 text) | Owner |
|------|------|----------|-------------------|-------|
| V110 | DUPLICATE_BINDING | error | Two tool bindings in one set name the same tool (§5.18.1) | S1 |
| V111 | TOOL_NAME_MISMATCH | error | A tool binding's `tool` is not the name the host offers the tool under (§5.18.2) | S1 |
| R407 | SAFETY_CHECK_FAILED | error | A safety layer could not complete its checks of a call, or a tool was reached without a layer's decision, so the call was refused (§5.18.8) | S1 |
| R408 | CANCELLED | error | The host cancelled the run (§5.19.5); no retry, failure mode, recovery or handler ran | S2b |
| F506 | GATED_CONTROL_ACTION | error | A host action taken whenever a tool is called, whatever the result, is tied to a tool that is not control-only and is unbound, has a prerequisite, or requires a checkpoint or approval (§5.18.3) | S1 |
| W617 | UNBOUND_TOOL | warning | A tool offered to a model has no binding; its calls are treated as the strictest case (§5.18.2) | S1 |
| W618 | UNKNOWN_JOIN | warning | A `join` other than `all_complete`, or a `join` on a step with no `parallel_group`; it is ignored (§5.2.3) | S2b |
| W619 | GROUP_MATE_READ | warning | A step reads the store of a step in its own `parallel_group`, which need not have run yet (§5.2.3) | S2b |
| W620 | NONCANONICAL_NAME | warning | A workflow name that is not an identifier or is `catalog` (§5.1), a step `domain` that is not a domain id (§5.2.4), or a literal model family outside `[a-z][a-z0-9_-]*` (§5.15) | S3 |
| W621 | UNBOUNDED_DELEGATION | warning | In a workflow that targets 1.2 or later, a `delegate` step whose target maxima are unknown: in a workflow that declares `agents`, always (the executor will not delegate there); otherwise, when it binds no literal `read_only: true` and its effective `requires_approval` is false (§5.15.2) | S3 |
| W622 | UNDECLARED_DELEGATE | warning | In a workflow that targets 1.2 or later and declares no `agents`, a `delegate` step whose `agent` is not a literal (§5.15.2) | S3 |
| W623 | CONCURRENT_RUN_CONFLICT | warning | A workflow with a trigger whose `overlap` is `allow_all` exercises both capabilities of a `conflicts_with` pair: through its steps, a gate's or failure mode's `rollback` action, or the workflows it invokes (§4.3). Event triggers do not count: they declare no overlap policy, and whether their runs overlap is the host's (§4.3) | S3 |
| W624 | UNCHECKED_ROLLBACK | warning | In a workflow that targets 1.2 or later, a `rollback` step whose `restored` no condition, gate or failure-mode `when` reads (§4.4.1) | S5 |
| W625 | DESTINATION_NOT_SHOWN | warning | In a workflow that targets 1.2 or later, a `send` step whose `approval.shows` leaves out a destination given by reference (§4.4.2) | S5 |
| W626 | UNKNOWN_MEMORY_SCOPE | warning | A literal `persist` or `recall` `scope` that is neither a defined scope nor an `x-` name (§4.5) | S5 |

S2a, S4 and S6 add no code. F505 is defined (was reserved) by S4.

### C2. `core/src/diag.rs` and `grounded_agency/errors.py`

In the `codes!` table, in code order (so `Code::ALL` and `_core.CODES` list
them; `tests/test_errors.py` keeps `ErrorCode` equal to `_core.CODES`):

```rust
    DuplicateBinding = "V110", "DUPLICATE_BINDING", Error;
    ToolNameMismatch = "V111", "TOOL_NAME_MISMATCH", Error;
    // after LivenessLost = "R406"
    SafetyCheckFailed = "R407", "SAFETY_CHECK_FAILED", Error;
    Cancelled = "R408", "CANCELLED", Error;
    // after ProvenanceMissing = "F505"
    GatedControlAction = "F506", "GATED_CONTROL_ACTION", Error;
    // after VersionFeatureMismatch = "W616"
    UnboundTool = "W617", "UNBOUND_TOOL", Warning;
    UnknownJoin = "W618", "UNKNOWN_JOIN", Warning;
    GroupMateRead = "W619", "GROUP_MATE_READ", Warning;
    NoncanonicalName = "W620", "NONCANONICAL_NAME", Warning;
    UnboundedDelegation = "W621", "UNBOUNDED_DELEGATION", Warning;
    UndeclaredDelegate = "W622", "UNDECLARED_DELEGATE", Warning;
    ConcurrentRunConflict = "W623", "CONCURRENT_RUN_CONFLICT", Warning;
    UncheckedRollback = "W624", "UNCHECKED_ROLLBACK", Warning;
    DestinationNotShown = "W625", "DESTINATION_NOT_SHOWN", Warning;
    UnknownMemoryScope = "W626", "UNKNOWN_MEMORY_SCOPE", Warning;
```

`grounded_agency/errors.py` `ErrorCode` gains the same 15 members, named by
the canonical name (`DUPLICATE_BINDING = "V110"`, …,
`UNKNOWN_MEMORY_SCOPE = "W626"`), in code order; its module docstring says
"v1.2.0". The TypeScript code-name tables (`records.ts`) gain the codes the
binding raises, in the workstream that raises them. The site's diagnostics
page reads §9.

### C3. Merged §9 text (STANDARD-v1.2.0)

§9.1, after "…it MUST NOT change any code's severity otherwise.", two
paragraphs in this order: S1 2.9's ("A V1xx code is a static validation
failure of a workflow, and the same code keeps its meaning where §5.18 uses
it: …") and S3 2.19's ("The codes of this section are this standard's. A
code an implementation defines … MUST NOT have the form of a standard
code …").

Rows that change or are new, merged from every design (C11); rows not listed
keep their 1.1.0 text:

**§9.2 Validation Errors**

| Code | Name | Description |
|------|------|-------------|
| V101 | UNKNOWN_CAPABILITY | Capability ID not found in ontology: a step's; a tool binding's `capability` or `additional_capabilities` entry (§5.18.1); an id in a grounding policy's `require` (§5.20); an id in a domain profile's `block_autonomous`, `require_grounding` or `checkpoint_policy` keys (§5.21.2); a capability an agent manifest lists, at each `delegate` step whose target maxima draw on it (§5.15.1); any id that a document citing a later ontology minor names, where it is used (§11.6) |
| V102 | MISSING_PREREQUISITE | A `requires` or `precedes` edge is violated (§4.3); a call's prerequisite other than a checkpoint has not run, and the layer refuses the call (§5.18.5); an offered tool requires a capability no offered tool can perform (§5.18.2) |
| V105 | CIRCULAR_DEPENDENCY | Workflow contains circular dependencies, including `invoke` cycles across the catalogs of a set (§5.1.1), or tool bindings' `invokes` form a cycle (§5.18.4) |
| V106 | UNSUPPORTED_EXTENSION | `workflow_extensions.requires` lists an unknown or unsupported extension, or an extension field is used without its declaration; in a workflow that targets 1.2, also `grounding` without `grounding@1` (§5.20) and an approver's `sender_check` or `accept_trust_classes` without `identity@1` (§5.17) |
| V107 | UNRESOLVED_TARGET | A `goto_step`, `on_exhausted`, `reviewers`, `forbidden_inputs` or `delivers_to` name does not resolve, or names the wrong kind of step or input; an `invoke` of a workflow whose `triggers` include no `invoke`; a handler's failure mode that loops or escalates (§5.10–§5.12, §5.16); a manifest `exports` entry that names no workflow of its catalog, or an invoke target that is a qualified id of the invoking catalog or of another catalog of the set where that catalog does not have the workflow or (another catalog) does not export it (§5.1.1); a literal `delegate` `agent` that the workflow's `agents` does not list, or a listed agent that a host composing agents statically does not provide (§5.15.2); a tool binding's `invokes` name that no binding of the set has (§5.18.4). Every other invoke target that resolves to nothing, a bare name included, is W607 |
| V109 | UNSUPPORTED_SPEC_VERSION | The declared standard version is not supported; or a document's cited `standard` is not supported, or its cited `ontology` has another major than the implementation's (§11.5, §11.6): a domain profile, a tool binding record (§5.18.1), a catalog manifest (§5.1.1), an interoperability mapping. (An agent manifest that does is refused when loaded, §5.15.1.) |
| V110 | DUPLICATE_BINDING | Two tool bindings in one set name the same tool (§5.18.1) |
| V111 | TOOL_NAME_MISMATCH | A tool binding's `tool` is not the name the host offers the tool under (§5.18.2) |

**§9.4 Schema Errors**

| S303 | SCHEMA_VALIDATION_FAILED | A field has the wrong type or value; or a domain profile member of the wrong type or outside its grammar, including a member of `risk_thresholds` or `evidence_policy` this version does not define and the `checkpoint_policy` key `checkpoint` (§5.21.2) |
|---|---|---|

**§9.5 Runtime Errors**

| R402 | EXECUTION_FAILED | Step execution failed; an `Error` may say why (`reason`, §5.19.7); a capability output on a text-only channel is not I-JSON, not an object, or lacks a required field (§5.18.9) |
|---|---|---|
| R407 | SAFETY_CHECK_FAILED | A safety layer could not complete its checks of a call, or a tool was reached without a layer's decision, so the call was refused (§5.18.8) |
| R408 | CANCELLED | The host cancelled the run (§5.19.5); no retry, failure mode, recovery or handler ran |

**§9.6 Safety Errors**

| F501 | CHECKPOINT_REQUIRED | A step or call that requires a checkpoint has no valid one, or one could not be taken (§5.2.2, §5.18.6) |
|---|---|---|
| F502 | APPROVAL_REQUIRED | A step or call that requires approval has no valid decision (§5.14, §5.18.7) |
| F503 | ROLLBACK_FAILED | Could not restore a checkpoint: the host failed the executor's `Rollback`, or there was no checkpoint to restore (§4.4.1, §5.2.2, §5.18.6) |
| F504 | CONSTRAINT_VIOLATED | Policy constraint violated: conflicting capabilities in one parallel group; a `send` destination that a destination policy in force does not allow (§4.4.2); a composite's call to a binding it does not list (§5.18.4); a safety layer's own policy, such as a rate limit (§5.18.8); a `persist` or `audit` write that holds a secret the layer recognises (§5.18.10, §6.7); an output whose confidence is below an applied profile's minimum, or not a number from 0 to 1 while a minimum applies (§5.21.3) |
| F505 | PROVENANCE_MISSING | Under a grounding policy, a host's output that is neither grounded nor marked inferred, that cites evidence its producer did not have, or whose citation of a workflow value is not of kind `record` (§3.1, §5.20) |
| F506 | GATED_CONTROL_ACTION | A host action taken whenever a tool is called, whatever the result, is tied to a tool that is not control-only and is unbound, has a prerequisite, or requires a checkpoint or approval (§5.18.3) |

**§9.7 Warnings**

| W601 | SOFT_REQUIREMENT_UNMET | No `soft_requires` source runs before the step (a safety layer MAY report it for a call, §5.18.5) |
|---|---|---|
| W602 | SAFETY_FLAG_DOWNGRADE | A step, a tool binding (§5.18.1) or a `delegate` step of a workflow with `agents` (§5.15.2) declares a flag weaker than its baseline (the ontology's, or the delegation's target maxima), or a domain profile's `checkpoint_policy` says `never` for a capability whose ontology requires a checkpoint (§5.21.2); the stricter value applies |
| W603 | DEPRECATED_FORM | Accepted legacy form (self-reading gate without `phase`, goto_step by capability id, a profile threshold `critical` (§5.21.2), a reference to `persist`'s `timestamp` (§4.5)) |
| W604 | UNKNOWN_FIELD | Unrecognised field, ignored; or a binding key outside the capability's inputs (§5.5); or an unknown top-level domain profile member (§5.21.2); with a closest-match hint |
| W606 | UNATTENDED_APPROVAL | An unattended trigger reaches an approval step without `when_unattended` or a standing mandate, or whose mandate cannot cover it: an always-ask item it uses (§5.17), or a person an applied profile requires (§5.21) |
| W607 | UNRESOLVED_WORKFLOW | An invoke target that resolves to no workflow: a bare name its catalog does not have, or a qualified id whose catalog is not in the catalog set (§5.1.1, §5.12); it cannot be checked |
| W614 | INVALID_DURATION | Legacy `timeout`, a literal `audit` `retention` or a literal `persist` `ttl` outside the duration grammar, or a `ttl` of zero (§4.5, §5.10.1, §6.3) |
| W616 | VERSION_FEATURE_MISMATCH | A workflow that targets an earlier version uses a feature new in a later one (§11.5) |
| W617–W626 | | As in C1 |

**§9.8 Diagnostic Format**: S3 2.20's full replacement (the merged location
table, which carries S1's `tool`, `call`, `action`, S2b's `mate`, S6's
`profile`, and `ref`, used by W619 and W625), followed by S1 2.9's
paragraph on a safety layer's refusal of a call. S2b's and S5's one-line
location sentences are not added (C30).

---

## Part D. `spec/STANDARD-v1.2.0.md` skeleton

The foundation copies `STANDARD-v1.1.0.md` to `STANDARD-v1.2.0.md`
(1.1.0 stays, supported), sets the header, adds every new heading below in
its place with an owner comment
(`<!-- owner: S4; text: S4.md part 2.5 -->`) and nothing else in it, adds
the reference and Appendix D entries, and merges the few shared one-liners
it owns (marked **foundation**). A workstream fills only its own headings
and the edits its design lists in other sections (F5's rule decides who
applies an edit to another workstream's section).

### D1. Header

```markdown
# Standard: Agent Capability Ontology + Workflow DSL

**Version:** 1.2.0
**Status:** Candidate Standard — accepted by
[RFC-0005](RFC-0005-tool-calling-hosts.md),
[RFC-0006](RFC-0006-host-protocol-approval-and-runs.md),
[RFC-0007](RFC-0007-delegation-catalogs-and-diagnostics.md),
[RFC-0008](RFC-0008-evidence-grounding-and-secrets.md),
[RFC-0009](RFC-0009-checkpoint-rollback-send-memory.md) and
[RFC-0010](RFC-0010-profiles-trust-versioning-and-dialect.md); the reference
validator and executor implement §4, §5 and §9–§11 and claim class EX
(§10.5); they check §3.1's grounding where a grounding policy applies
(§5.20, F505) and apply domain profiles (§5.21), as the Python adapter does;
the Python SDK adapter and the Standard Agents binding implement §5.18 and
claim class SL (§10.4); `grounded_agency` implements §7.1's entity ids and
§8's arithmetic; §7.2 and §7.3 are not implemented
**Date:** <the release date>
**Supersedes:** [STANDARD-v1.1.0](STANDARD-v1.1.0.md) (still supported; see §11.5)
```

The six RFC files exist from the foundation on (F1, item 14), so the links
resolve.

### D2. New headings, in document order, with owners

| Number | Heading | Owner | Text |
|--------|---------|-------|------|
| §1 item 10 | **Tool-calling hosts** | S1 | S1 2.2 |
| §1 item 11 | A **host protocol** … | S2b | S2b 2.1 |
| §1 item 12 | **Domain profiles** … | S6 | S6 2.2 |
| §1 | "Changes from 1.1.0 are listed in Appendix D." (replaces the Appendix C sentence; Appendix C stays) | foundation | — |
| §1.1 | RFC 5545 §3.3.5 (§5.10.2); RFC 6901 (§4.1.2, §6.2, §9.8); RFC 3986 (§7.1) | foundation | S2b 2.2, S3, S6 2.21 |
| §2 | Rows, in this order after **Runs before**: S1's six (**Layer scope** for S1's "Scope", C18), S2b's five, S5's four (**Pass** … **Memory scope**), S3's four; S5 replaces **Checkpoint** and adds **Rollback** after it; S4 replaces **Grounding** and adds four after it; S6 adds its rows after **Effective flag** | each | S1 2.3, S2b 2.3, S5 2.1, S3 2.1, S4 2.2, S6 2.3 |
| §3.3 bullets | after 1.1's first bullet: S5's; after "A workflow cannot weaken …": S3's, then S6's; last: S1's | each | S5 2.2, S3 2.2, S6 2.4, S1 2.4 |
| §4.1.1 | Common Output Fields | S4 | S4 2.5 |
| §4.1.2 | Schema Dialect | S6 | S6 2.6 |
| §4.4.1 | Checkpoints and Rollback | S5 | S5 2.4 |
| §4.4.2 | Transmissions | S5 | S5 2.5 |
| §4.5 | Memory | S5 | S5 2.6 |
| §5.1.1 | Catalog Manifests and Qualified Names | S3 | S3 2.5 |
| §5.2.2 | Checkpoint Use | S1 | S1 2.6 |
| §5.2.3 | Parallel Groups | S2b | S2b 2.6 |
| §5.2.4 | Domain Parameter | S3 | S3 2.7 |
| §5.10.2 | Evaluating Triggers | S2b | S2b 2.9 |
| §5.13.1 | Answers to an Inquiry | S3 | S3 2.11 |
| §5.14.1 | Resuming a Deferred Run | S2a | S2a 2.3 |
| §5.15.1 | Agent Manifests | S3 | S3 2.13 |
| §5.15.2 | Delegation Targets | S3 | S3 2.14 |
| §5.15.3 | Continuing a Delegation | S3 | S3 2.15 |
| §5.15.4 | Checkpoints Across a Delegation | S5 | S5 2.7 |
| §5.18 | Tool-Calling Hosts | S1 | S1 2.8 |
| §5.18.1–§5.18.10 | Tool Bindings; Unbound Tools; Classification; Composite Tools; Scope, Order and Concurrency; Checkpoints for Calls; Approval for Calls; Refusals, Records and Failure; Text-Only Results; Capability Checks | S1 | S1 2.8 |
| §5.19 | Host Protocol | S2b | S2b 2.11 |
| §5.19.1–§5.19.8 | Actions and Responses; Run Operations; Time; Saving and Continuing a Run; Cancelling a Run; Protocol Traffic; Error Reasons; The Run's Record | S2b | S2b 2.11 (with S4 2.10's and S5 2.8's edits, the start item and reasons merged, C3, C5) |
| §5.20 | Grounding | S4 | S4 2.9 |
| §5.21 | Domain Profiles | S6 | S6 2.11 |
| §5.21.1–§5.21.4 | Applying Profiles; Loading a Profile; Effect on Steps and Calls; Conformance | S6 | S6 2.11 |
| §6.1 | the supporting-schemas sentence (D3) | foundation | — |
| §6.4 | Audit Records | S2b | S2b 2.14 (+ S5 2.9, S6 2.10b sentences) |
| §6.5 | Evidence Anchors | S4 | S4 2.14 |
| §6.6 | Evidence Records and Stores | S4 | S4 2.15 |
| §6.7 | Secrets in Records | S4 | S4 2.16 |
| §8.4 | Manual Overrides | S2b | S2b 2.15 |
| §9 | Part C3 text | foundation | — |
| §10.1 | rows **SL** and **EX**, and the merged sentence (C7) | foundation | S1 2.10, S2b 2.17 |
| §10.4 | Safety-Layer Conformance | S1 | S1 2.10 |
| §10.5 | Executor Conformance | S2b | S2b 2.17 |
| §11.5 | Version Declaration (replaced) | S6 | S6 2.18 (W616 row as reconciled, C12) |
| §11.6 | Ontology Versions | S6 | S6 2.19 |
| §11.7 | Artifacts of This Version | foundation (table E2), S6 text | S6 2.20 |
| §12.5 | patterns *Guarded Send* and *Checked Rollback* after *Recovery Loop* | S5 | S5 2.13 |
| §13.1 | RFC 5545, RFC 6901, RFC 3986 | foundation | — |
| §13.2 | RFC-0005 to RFC-0010; Agent Skills specification | foundation | S1 2.12, S3 2.23, S6 2.21 |
| Appendix B | S4's two sentences; S6's last line | foundation | S4 2.21, S6 2.22 |
| Appendix D | Changes from 1.1.0 (D4) | each subsection's owner | each design's Appendix D part |

§10.3 gains one paragraph per workstream, appended in this order: S2b
(runtime fixtures normative for EX, trigger vectors; it replaces 1.1's last
sentence), S1 (binding and call fixtures for SL), S2a (approval digest
vectors), S3 (fixture keys, four vector sets), S4 (grounding vectors and
fixtures), S5 (destination and memory vectors), S6 (trust, profile and
entity vectors).

### D3. Shared one-liners the foundation writes

- §6.1, after the table (C10): "Supporting schemas that specific sections
  use, not required of every implementation: `review_verdict_schema.yaml`
  (§5.16), `agent_identity_schema.yaml` 1.1.0 (§5.17),
  `agent_manifest_schema.yaml` 1.0.0 (§5.15.1), `host_protocol.schema.json`
  (§5.19, required for class EX, §10.5), `interop/tool_binding.schema.json`
  (§5.18.1, required for class SL, §10.4), `interop/evidence.schema.json`
  (§6.5, §6.6) and `profiles/profile_schema.yaml` (§5.21, the shape of a
  domain profile)."
- §10.1, after the table (C7): "Levels L1–L4 rank validators; SL (§10.4)
  and EX (§10.5) are separate classes: a layer validates no catalog, a
  validator checks no call and runs no workflow, and an implementation
  claims each level or class it meets."
- §5.9, the closing sentence (S4 2.7): "*(The reference validator implements
  all of them.)*"
- `spec/EDGE_TYPES.md` header: "accompanies STANDARD-v1.2.0 §4.3" (S3 2.25
  fills the body).

### D4. Appendix D skeleton

```markdown
## Appendix D: Changes from 1.1.0

Every change is backward compatible: a workflow valid under 1.1.0 is valid
under 1.2.0 and runs the same way unless its host opts in to a new feature;
a change that would invalidate a 1.1 workflow is phased in as a warning.
Clarifications of 1.1 semantics apply to 1.0 and 1.1 workflows too.

### D.1 Tool-calling hosts (RFC-0005)
<!-- owner: S1; entries: S1.md part 2.13 -->

### D.2 Approval, deferral and run identity (RFC-0006, Part A)
<!-- owner: S2a; entries: S2a.md part 2.8 -->

### D.3 Host protocol, runs and audit records (RFC-0006, Part B)
<!-- owner: S2b; entries: S2b.md part 2.18 -->

### D.4 Delegation, catalogs and diagnostics (RFC-0007)
<!-- owner: S3; entries: S3.md part 2.24 -->

### D.5 Evidence, grounding and secrets (RFC-0008)
<!-- owner: S4; entries: S4.md part 2.22 -->

### D.6 Checkpoint, rollback, send and memory (RFC-0009)
<!-- owner: S5; entries: S5.md part 2.15 -->

### D.7 Profiles, trust, versioning and schema dialect (RFC-0010)
<!-- owner: S6; entries: S6.md part 2.23 -->
```

Each subsection lists its clarifications first, then what is new in 1.2.0,
as Appendix C does.

---

## Part E. Version lines

### E1. Files the foundation changes

| What | From | To | Where |
|------|------|----|-------|
| Standard | 1.1.0 | 1.2.0 | new `spec/STANDARD-v1.2.0.md` (D1); 1.1.0's file stays |
| Capability ontology | 2.1.0 | 2.2.0 | `schemas/capability_ontology.yaml` `meta.version` |
| Plugin | 2.0.0 | **3.0.0** (MAJOR: S6 renames two user-invocable skills; S1's hook behaviour rides on it, C31) | `.claude-plugin/plugin.json` `version` |
| Python package `grounded-agency` | 0.1.0 | **0.2.0** (0.x minor for the SDK's breaking changes: unbound MCP tools no longer default to `execute`, `require_layer`, the start `header`, checkpoint tracker semantics) | `pyproject.toml`, `grounded_agency/__init__.py` `__version__` |
| TypeScript package `@synaptiai/acs-core` | — | 0.1.0 (new, fifth line) | `packages/acs-core/package.json` |
| `spec/ROADMAP.md` | | | Versions table: five rows (the four above at their new values, plus the TypeScript package); Standard table: 1.2.0 "Candidate Standard, current", 1.1.0 "supported"; plugin table: "3.0.0 — Implements Standard 1.2.0"; both mermaid `accDescr` lines and nodes; RFC-0002 stays Draft and moves to a later 1.x (C37) |
| `schemas/interop/oasf_mapping.yaml` | `meta.agent_capability_standard` 1.1.0 / 2.1.0 | `standard: "1.2.0"`, `ontology: "2.2.0"` | |
| `docs/integrations/oasf_coverage.md` | header | "**Agent Capability Standard:** Standard 1.2.0, ontology 2.2.0 (36 atomic capabilities)" | |
| `schemas/interop/standard_agents_mapping.yaml` | `meta.agent_capability_standard` | 1.2.0 / 2.2.0 (a citing document, §11.6) | |
| Validator | `SUPPORTED_VERSIONS = [(1,0), (1,1)]` | `[(1,0), (1,1), (1,2)]` | `core/src/validate/semantics.rs`; `parse_version` `pub(crate)` |
| TypeScript | `STANDARD_VERSION = '1.1.0'` | `'1.2.0'`; `SPEC_VERSIONS = ['1.0', '1.1', '1.2']` | `packages/acs-core/src/ontology.ts`, generated `ontology.gen.ts` |
| Canonical and supporting schema versions | | world_state 1.2.0, event 1.2.0, entity_taxonomy 1.1.0, authority_trust_model 1.2.0, agent_identity 1.1.0, agent_manifest 1.0.0, profile_schema 1.0.0 | Part B |
| Citations | `CITATION.cff`, `spec/CITATION.cff` `version: "1.1.0"` | `"1.2.0"` | |
| README | badge, "Versioning" note, the two STANDARD links, the status line | v1.2.0 Candidate (accepted by RFC-0005 to RFC-0010; 1.1.0 and 1.0.0 still supported) | `README.md` |
| Spec documents | `spec/CONFORMANCE.md` line 3, `spec/EDGE_TYPES.md` header, `spec/WHITEPAPER.md` footer and the header example | STANDARD-v1.2.0 | |
| Docstrings | `grounded_agency/errors.py`, `grounded_agency/trust.py`, `scripts/gen_standard_agents_binding.py` | "v1.2.0" | |

`tests/test_version_lines.py` checks the ROADMAP table against the
declaring files; it gains the fifth line (S6 part 6.4 test change, landed
here with the line). `CHANGELOG.md`'s `## [v3.0.0]` section and the
release are phase 5, not the foundation.

### E2. §11.7 table (final list)

S6 2.20's table with the rows S1–S5 own:

| Artifact | File | Version | Sections |
|----------|------|---------|----------|
| Capability ontology | `schemas/capability_ontology.yaml` | 2.2.0 | §4 |
| Ontology dialect metaschema | `schemas/capability_ontology.schema.json` | — | §4.1.2 |
| Contracts in Draft 2020-12 (generated) | `schemas/generated/capability_contracts.schema.json` | — | §4.1.2 |
| World state (canonical) | `schemas/world_state_schema.yaml` | 1.2.0 | §6.3, §6.4 |
| Events (canonical) | `schemas/event_schema.yaml` | 1.2.0 | §6.2, §6.5 |
| Entity taxonomy (canonical) | `schemas/entity_taxonomy.yaml` | 1.1.0 | §7.1 |
| Authority trust model (canonical) | `schemas/authority_trust_model.yaml` | 1.2.0 | §8 |
| Identity resolution policy (canonical) | `schemas/identity_resolution_policy.yaml` | 1.0.0 | §7.2, §7.3 |
| Review verdict | `schemas/review_verdict_schema.yaml` | 1.1.0 | §5.16 |
| Agent identity | `schemas/agent_identity_schema.yaml` | 1.1.0 | §5.17 |
| Agent manifest | `schemas/agent_manifest_schema.yaml` | 1.0.0 | §5.15.1 |
| Domain profile | `schemas/profiles/profile_schema.yaml` | 1.0.0 | §5.21 |
| Workflow catalog (JSON Schema) | `schemas/workflow_catalog.schema.json` | — | §5 |
| Host protocol | `schemas/host_protocol.schema.json` | — | §5.19 |
| Tool binding record | `schemas/interop/tool_binding.schema.json` | — | §5.18.1 |
| Evidence anchors and records | `schemas/interop/evidence.schema.json` | — | §6.5, §6.6 |
| Conformance vectors and fixtures | `tests/conformance/` and `tests/fixtures/` | — | §10.3 |

---

## Part F. Shared code, ownership and how to avoid conflicts

### F1. Shared code spine that lands in the foundation (C23)

Each item is used by two or more tracks that run in parallel, so it lands
first. Each is a shape with no behaviour of its own, or a pure function with
its vectors; the design that specifies it stays the specification, and its
owner fills in the behaviour later.

1. **Codes**: C2 (`diag.rs`, `errors.py`).
2. **Version helpers** (S6 5.1): `SUPPORTED_VERSIONS` with `(1, 2)`;
   `semantics::parse_version` `pub(crate)`; `semantics::target(wf, header)`;
   `semantics::check_cited` exposed as `_core.check_cited_versions` (S3's
   `names::parse_cited` is this function); `Ontology.version` (read by
   `check_cited` and S3's manifests).
3. **W616 mechanism** (S6 5.1): the table-driven `FEATURES` list and
   `version_feature_diag`, with only the 1.1 entries; S2a, S2b, S3, S4 and
   S5 append their 1.2 entries (S6 2.18's table as reconciled, C12).
4. **Effective flags** (S6 5.1 with S3's type): `semantics::Flags` (S3:
   `of(node)`, `join`, `NONE`) and `semantics::effective(node, step,
   maxima: Option<Flags>, policy: &profile::Policy) -> Effective`, called at
   every site S6 5.1 lists, with `maxima = None` and an empty
   `profile::Policy` (a stub type whose `raise` raises nothing). No result
   changes; S3 supplies maxima, S6 the profile policy.
5. **Options and start options**: `validate::Options { header, profiles,
   agents, catalogs }` (empty defaults; S3 and S6 fill them); executor
   `StartOptions { attendance, run_id, now_ms, actor_identity, header,
   records, profiles, grounding, destinations }` with **no `Default`**
   (S6) and `header` required, every construction naming it; the other new
   members are stored in the run's state and unused until their owner
   merges. Python `_core.Run.start(validator, catalog, workflow,
   inputs=None, *, header, attendance="attended", run_id, now_ms,
   actor_identity=None, records="approvals", profiles=None, grounding=None,
   destinations=None, catalogs=None, agents=None)` and `restore` alike;
   `_core.pyi` stubs.
6. **Start header end to end** (S6 3.10, 5.1, 5.3): `Run::prepare` validates
   with the header; the snapshot keeps it; `gen_runtime_fixtures.py`'s
   `add()` writes `"header": None`; the runtime harnesses
   (`core/tests/runtime.rs`, `tests/test_runner.py`) pass every start member
   of B9 through; every fixture regenerated with `"header": null`; the 20
   contributed fixtures edited likewise; `WorkflowRunner.start` passes
   `header=None` (S6's reason).
7. **Runtime fixture generator split**: `scripts/gen_runtime_fixtures.py`
   keeps the format code and imports one module per workstream from
   `scripts/runtime_fixtures/` (`s2a.py`, `s2b.py`, `s3.py`, `s4.py`,
   `s5.py`, `s6.py`, each `def register(add): ...`, empty here), so six
   workstreams add fixtures without editing one file. The fixture schema
   (B9) and `tests/runtime_replay.py` (S2b's shared replay helper, with the
   B9 members) land here.
8. **Error reasons** (S2b 5.3, ACS-62): `Response::Error.reason`
   (`Option<Value>`), the §5.19.7 grammar check (a defined token, from the
   merged list, or `x-`; anything else ignored and traced as
   `reason_ignored`), `exec_error`/`step_error` carrying a reason to
   `Failed.reason` and a record's `reason_code`. S5 and S6 raise reasons
   through it.
9. **`exec::read_json`** (S2a 5.1): JSON text with an integer literal beyond
   2^53 is refused; S6's WebAssembly entry points use it.
10. **Canonical JSON in Python** (S1 5.1): `_core.canonical_json(value) ->
    str` and `_core.approval_digest(shown) -> str`. There is no
    `_core.canonical_digest`; a digest of other values is
    `sha256(_core.canonical_json(v))` (C27).
11. **`refs::executable_roots`** (S2b 5.5): the root collection moved out of
    `exec::program` into one function, called from `program.rs`; S2b (W619)
    and S5 (W603) call it.
12. **Durations** (S5 5.1, S4): `extensions::literal_duration(step, key,
    positive, why, at, report)` replacing the body of the W614 `timeout`
    check, and `_core.duration_ms`. S4 (`audit.retention`) and S5
    (`persist.ttl`) call it.
13. **Destination policies** (S5 5.1): `core/src/destination.rs` complete
    (`Pattern`, `Policy::parse`, `Policy::allows`, `check_pattern`,
    `check_policies`, `allowed`), `_core.check_destination_pattern`,
    `_core.destination_allowed`, and `tests/conformance/destinations/match.json`
    with its Rust test. S5 (executor, adapter, binding) and S6 (profile
    loader) use it.
14. **Grounding policy shape** (S4 5.1): `core/src/grounding.rs` with
    `Policy { require, kinds, attested }`, `Policy::new` (refusing an unknown
    capability id, V101) and `is_kind` (the §6.5 kind grammar, one
    constant); S4 adds `check`, S6 builds profile policies with `new`.
15. **Redaction** (S4 5.2, 5.3): `grounded_agency/state/redaction.py`
    (`Redactor`, `DEFAULT_REDACTOR`, `MARKER`, `redact`, `redact_text`,
    `holds_secret`) and `packages/acs-core/src/redact.ts` (`MARKER`,
    `DEFAULT_PATTERNS`, `redactText`, `redactJson`), with their unit tests
    and `tests/conformance/secrets/redact.json`. S4 and S5 use them.
16. **RFC files**: `spec/RFC-0006-host-protocol-approval-and-runs.md`,
    `RFC-0007-delegation-catalogs-and-diagnostics.md`,
    `RFC-0008-evidence-grounding-and-secrets.md`,
    `RFC-0009-checkpoint-rollback-send-memory.md`,
    `RFC-0010-profiles-trust-versioning-and-dialect.md`, each with
    **Status:** Accepted, **Target:** Standard v1.2.0, and every section
    `tools/validate_rfcs.py` requires holding the design's Summary and one
    line pointing to the design; each workstream replaces its file with its
    part-9 text (S2b writes RFC-0006's header, summary and Part B, S2a Part
    A). RFC-0005 keeps its Draft text until S1 replaces it.

### F2. Code that lands with the ontology and schemas (C20)

So that CI stays green with Part A and B:

- `_core.Validator.contracts()` (S6 5.1/5.2): the resolved contracts.
- `scripts/gen_capability_json_schemas.py` (S6 5.3): renders from
  `contracts()`, `CARRIED` additions, the `nullable` rule; the `--check`
  output regenerated.
- `tools/sync_skill_schemas.py` (S6 5.3 + S4 5.4): skill-local schemas from
  `contracts()` (refs inlined, the dialect header line);
  `render_vendored_ontology` for the two vendored ontology copies; the
  tests S4 5.4 lists.
- `core/src/types.rs`: duplicate union members dropped (S4 5.1), so
  `evidence_anchors` items still read `union<object,string>`.
- `tools/validate_canonical_schemas.py`: `validate_shared_types` (S4), the
  identity check over the new `model_id` (S3).
- `site/src/lib/views.ts` `typeOf`/`constraintsOf` for `$ref`, `anyOf` and
  `pattern`, with their `views.test.ts` cases (S4 5.4), if the site tests
  need them for the new contracts.

### F3. TypeScript package skeleton and moves (C21)

The foundation creates `packages/acs-core/` (S6 5.4: `package.json` at
0.1.0, `package-lock.json`, `tsconfig.json`, `tsconfig.build.json`,
`README.md`, `LICENSE`, `NOTICE`, `.gitignore`, `.nvmrc`, `src/index.ts`,
`src/ontology.ts`, `src/ontology.gen.ts` (generated), `src/flags.ts`,
`src/canonical.ts`, `src/redact.ts`, `test/`) and moves the binding's
ontology table, flags and canonical JSON there (S6 5.5): the binding's
`src/acs/ontology.ts` re-exports from `@synaptiai/acs-core`,
`src/acs/ontology.gen.ts` and `src/acs/canonical.ts` are deleted, the
canonical tests move, `examples/standard_agents/test/fixtures/approval-digests.json`
is deleted (tests read `tests/conformance/approval/digests.json`), the
binding's `package.json` depends on `file:../../packages/acs-core`.
`scripts/gen_standard_agents_binding.py` writes the new path and checks the
old one is gone. CI gets a package job (`npm ci`, `npm run check`, `npm
test`) and CLAUDE.md the package's commands. The WebAssembly entry
(`src/wasm.ts`, `core/src/wasm.rs`, the build scripts), `src/core-types.ts`
and publishing stay with S6.

Placement rule from here on: a host-neutral TypeScript module (one that
imports nothing from `@standardagents/spec` and needs no WebAssembly) goes in
`packages/acs-core/src/` and its tests in `packages/acs-core/test/`, reading
`tests/conformance/` in place; code that reads or describes Standard Agents
state stays in `examples/standard_agents/src/acs/`. So: S1 `binding.ts`,
`output.ts`, `effectiveFlagsOf`, `prerequisitesOf`; S4 `redact.ts`
(foundation), the grounding part of `evidence.ts`, `FieldTypes`; S5
`destinations.ts`, `duration.ts` in the package; S1 `grounded.ts`, `lint.ts`,
`records.ts`, S2a `approval.ts`, S4 `exportEvidence`, S5 `layer.ts`,
`memory.ts` in the binding. No conformance file is copied under
`examples/standard_agents/test/fixtures/`.

### F4. Ownership during the parallel phase

**Exclusive files.** A file a design creates belongs to that workstream
alone (for example S1 `grounded_agency/capabilities/bindings.py`,
`hooks/stop_end_checkpoints.sh`, `scripts/gen_call_fixtures.py`; S2b
`core/src/trigger.rs`, `grounded_agency/workflows/triggers.py`; S3
`core/src/agents.rs`, `core/src/catalogs.rs`, `core/src/names.rs`; S4
`core/src/validate/grounding.rs`, `grounded_agency/grounding.py`; S5
`core/src/validate/effects.rs`, `grounded_agency/state/memory.py`,
`grounded_agency/workflows/idempotency.py`; S6 `core/src/profile.rs`,
`core/src/wasm.rs`, `grounded_agency/profiles.py`, `entities.py`,
`versions.py`), as do its RFC, its vector directories, its fixtures and its
tests named after its features. Each design's file list says which.

**Shared files, their primary owner and the others' regions.** The primary
owner may restructure the file; the others change only the region named,
and keep each change local (a new function, a new match arm, appended
lines), never reformatting what they do not own.

| File | Primary | Others and their region |
|------|---------|-------------------------|
| `core/src/exec/machine.rs` | S2b (chain) | S2a resume/reopen; S3 delegate refusals at the pre-call point and `output()` delegate checks; S4 `grounding_check` in `output()`; S5 destination check at the pre-call point, idempotency key on `InvokeCapability`, scope echo in `output()`, `RolledBack.not_covered`; S6 profile raise (via `program.rs`), minimum confidence in `output()`, `person_required` in the request path |
| `core/src/exec/mod.rs` | S2b | S2a `resume`, `restore(actor_identity)`, frame fields; S3 `start_set`/`restore_set`; S4/S5/S6 nothing beyond F1's struct (behaviour lives in `machine.rs`/`program.rs`) |
| `core/src/exec/program.rs` | S2b | S2a `Workflow.targets_1_2`; S3 target maxima on `Step`; S4 `Step.bound`; S6 profile policy on `Program` |
| `core/src/validate/mod.rs` | S3 | S2b W618/W619 block; S4 `grounding::check` call; S5 `effects` calls; S6 profiles in `validate_catalog_with` over S3's `validate_set` |
| `core/src/validate/semantics.rs` | S6 | S3 `exercised`, `concurrent_conflicts`; S4 `WORKFLOW_KEYS` += `grounding`; S3 += `agents`; each stream's `FEATURES` entries |
| `core/src/validate/approval.rs` | S2a | S3 the delegate exemption; S6 W606 with profiles |
| `core/src/validate/extensions.rs` | foundation (F1.12) | S4 `audit_retention`; S5 `memory_inputs` calls |
| `core/src/python.rs`, `grounded_agency/_core.pyi` | foundation (F1) | each stream adds its own `#[pyfunction]`s/methods and stubs, appended in its own block |
| `core/src/lib.rs`, `core/Cargo.toml` | foundation | `pub mod` lines and features appended (S2b `trigger`, S3 `agents`/`catalogs`/`names`, S6 `profile`/`wasm`) |
| `core/tests/runtime.rs`, `tests/test_runner.py` | S2b | others add test functions only; option plumbing is F1.6 |
| `grounded_agency/workflows/runner.py` | S2b | S2a `resume`; S3 `catalogs`/`agents`; S4 `evidence_store`, redaction; S5 idempotency log, `destinations`; S6 `profiles` |
| `grounded_agency/adapter.py` | S1 | S4 `GroundedAgentConfig` `evidence_store`, `secret_values`, `grounding` and their use; S5 `allowed_destinations` and the send check; S6 `profiles` |
| `grounded_agency/capabilities/mapper.py` | S1 | S6 `profiles` in `_effective_mapping`, `ToolMapping.person_required` |
| `grounded_agency/state/checkpoint_tracker.py` | S1 | S5 `snapshots`, `restore_checkpoint`, `checkpoint_output`, discard on prune |
| `grounded_agency/coordination/audit.py`, `orchestrator.py`, `delegation.py` | S2b | S3 delegation/inquiry; S4 redaction, anchors |
| `grounded_agency/hooks/evidence_collector.py` | S4 | S2b `required=` and `record_capture_failure` |
| `grounded_agency/__init__.py` | foundation | exports appended per stream |
| `grounded_agency/trust.py` | S6 | S2b §8.4 overrides |
| `examples/standard_agents/src/acs/grounded.ts` | S1 | S2a identities in records; S4 `grounding` option; S5 destination check |
| `examples/standard_agents/src/acs/records.ts` | S1 | S2a approver identities; S2b export as `ActionRecord`; S4 evidence; S5 `F504` |
| `examples/standard_agents/src/acs/lint.ts` | S1 | S3 `lintDelegationTargets` |
| `hooks/posttooluse_log_tool.sh`, `tools/verify_audit_log.py`, `hooks/README.md` | S2b (line format) | S1 `recorded_by` content and the other hooks; S4 `secret_scan.sh`; S6 one sentence |
| `skills/<capability>/SKILL.md` | the body's design: S5 `checkpoint`, `rollback`, `send`, `persist`(body), `recall`; S2b `audit` (record shape); S3 `delegate`, `inquire`, `receive` | S1 frontmatter prompt hooks (six skills) and three composed skills' step 0; S4 command hooks (`persist`, `audit`), anchor examples and `confidence` glosses (all); S6 frontmatter `name`/`layer` (ACS-59) |
| `scripts/gen_standard_agents_binding.py` | foundation (path, `kind`) | S1 annotation schema and `tool_call` vectors; S2a `unresolved_reference` and the normative header |
| `tools/sync_skill_schemas.py`, `scripts/gen_capability_json_schemas.py` | foundation (F2) | S6 refinements |
| `spec/STANDARD-v1.2.0.md` | foundation (skeleton) | each stream its headings (D2) and the edits its design lists |
| `spec/CONFORMANCE.md`, `spec/SECURITY.md`, `docs/guides/RUNNING_WORKFLOWS.md`, `docs/guides/ORCHESTRATION_EXTENSIONS.md`, `docs/integrations/standard_agents.md`, `docs/integrations/claude_agent_sdk.md`, `docs/GLOSSARY.md`, `docs/guides/MODALITY_HANDLING.md`, `docs/domains/README.md` | the first design in merge order that edits it | each stream edits only the sections its design names and appends new sections at the end of the relevant chapter; table rows (trace kinds, glossary terms, the conformance list) are appended |
| `CLAUDE.md`, `.github/workflows/ci.yml` | foundation | command blocks and CI steps appended (S1 call fixtures; S2b trigger vectors; S3 vectors; S6 WebAssembly, publish job) |
| `tests/fixtures/EXPECTATIONS.json` | — | entries keyed by fixture name; a merge takes the union |
| `schemas/workflow_catalog.yaml`, `skills/*/reference/workflow_catalog.yaml` | S2b (recovery texts) | S3 catalog changes, S6 skill names; the bundled copies are regenerated, never edited |

**Generated files are never merged by hand**: after every merge, run every
generator (`sync_skill_schemas.py`, `gen_capability_json_schemas.py`,
`gen_standard_agents_binding.py`, `gen_runtime_fixtures.py`,
`gen_call_fixtures.py`, `gen_trigger_vectors.py`) and commit their output;
`--check` must pass.

**Integration points** are wired by the workstream that merges second
(F5): S6 adds the profile grounding policies to S4's `grounding_check`, and
`person_required` to S2a's request path and S2b's records; S3 places its
delegate refusals at the pre-call point (C24); S5 adds the profiles'
destination policies (S6) to the executor's policies in force, its check at
the pre-call point beside S3's, and `details.not_covered` to S2b's rollback
records.

### F5. Merge order

1. **S1** — no dependency on another track's code; the chain's hooks,
   records and adapter edits build on it.
2. **S2a**, 3. **S2b**, 4. **S4** — the chain, merged in its own order; the
   most invasive executor change goes in before the localised ones.
5. **S6** — after S4 (grounding), S2a (request path) and S2b (records).
6. **S3** — after S6 (`semantics::effective` with policies in use) and S2b
   (fixture format, reasons).
7. **S5** — last: it builds on S1 (tracker, adapter, classifier), S2b
   (records, reasons, `run_id`), S3 (§5.15.1–§5.15.3), S4 (redaction) and S6
   (profile destinations).

A track that is ready early may merge before its slot only if every
integration point it would wire is already on main; otherwise it waits.
Each merge rebases on main, regenerates (F4), and passes F6 before the next
starts. `SNAPSHOT_VERSION` becomes 2 once, in S2b; every saved-state member
any track adds is optional with a default that gives 1.1 behaviour, so
states from either side of every merge restore (C34).

### F6. Checks after the foundation and after every merge

Every command of CLAUDE.md that CI runs: the Python validators
(`validate_workflows.py --strict` and the catalog loop, `validate_profiles`,
`validate_skill_refs`, `validate_ontology`, `validate_canonical_schemas`,
`validate_rfcs`, `validate_constraints`, `validate_doc_links`,
`validate_yaml_util_sync`, `validate_transform_refs`,
`validate_benchmark_deps`), every generator with `--check`, `pytest`, the
Rust checks (`cargo fmt --check`, both `clippy` runs, `cargo test`), the
binding's and the package's `npm run check` and `npm test`, and the site's
`npm run check`, `npm test` and `npm run build`. The foundation itself must
leave every one green with no fixture expectation changed except the added
`"header": null`.
