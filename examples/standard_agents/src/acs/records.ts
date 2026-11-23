/**
 * The records a grounded thread keeps, and where it keeps them.
 *
 * Everything is stored in the thread's durable key-value store
 * (`ThreadState.getValue` / `setValue`). The Standard Agent Specification
 * requires every runtime to back that store durably, to isolate it per
 * thread, and to make a write visible to every later read on the same thread
 * "across any execution context (tools, hooks, endpoints)" (Runtime, Durable
 * Key-Value Store). That is what lets a tool prove a checkpoint was taken by
 * an earlier tool call, and read an approval that an authenticated endpoint
 * recorded.
 *
 * The store has no key listing, so lists are kept as a counter plus one key
 * per entry.
 */
import type { ThreadState } from '@standardagents/spec';
import { redactAnchor, redactText, type EvidenceAnchor, type Json, type TRUST_CLASSES } from '@synaptiai/acs-core';
import { layerSecrets } from './layer.js';
import type { CapabilityId } from './ontology.js';

/** The part of `ThreadState` the binding uses. */
export type Store = Pick<ThreadState, 'getValue' | 'setValue'>;

export const KEYS = {
  traceCount: 'acs:trace:count',
  trace: (seq: number) => `acs:trace:${seq}`,
  /** How many times each capability has executed: what `requires` edges read. */
  executed: 'acs:executed',
  /** Trace entries the audit hook has not yet matched to a tool call id. */
  unlinked: 'acs:trace:unlinked',
  /** The trace entry a tool call id was given to, so a hook delivered twice adds nothing. */
  call: (id: string) => `acs:trace:call:${encodeURIComponent(id)}`,
  checkpoints: 'acs:checkpoints',
  approval: (digest: string) => `acs:approval:${digest}`,
  /** One approver's approval. Only that approver's request writes it. */
  approvedBy: (digest: string, round: number, approver: string) =>
    `acs:approval:${digest}:${round}:by:${encodeURIComponent(approver)}`,
  /** Who has approved in this round: the list `approvedBy` keys are found by. */
  approvers: (digest: string, round: number) => `acs:approval:${digest}:${round}:approvers`,
  /** Set by any rejection in this round. A fixed key, so it cannot be lost. */
  rejected: (digest: string, round: number) => `acs:approval:${digest}:${round}:rejected`,
  pendingApprovals: 'acs:approvals:pending',
} as const;

/**
 * The codes a grounded tool refuses or fails a call with (STANDARD 1.2.0
 * §5.18.8, §9): a missing checkpoint (F501), approval (F502), rollback
 * history (F503) or other prerequisite (V102); a binding it does not list
 * (F504) or `persist` data or an `audit` record that holds a secret
 * (F504, §6.7); an output that breaks its contract (R402) or a grounding
 * policy (F505, §5.20); a failure of the layer itself (R407).
 */
export type RefusalCode = 'F501' | 'F502' | 'F503' | 'F504' | 'F505' | 'R402' | 'R407' | 'V102';

export const CODE_NAMES: Record<RefusalCode, string> = {
  F501: 'CHECKPOINT_REQUIRED',
  F502: 'APPROVAL_REQUIRED',
  F503: 'ROLLBACK_FAILED',
  F504: 'CONSTRAINT_VIOLATED',
  F505: 'PROVENANCE_MISSING',
  R402: 'EXECUTION_FAILED',
  R407: 'SAFETY_CHECK_FAILED',
  V102: 'MISSING_PREREQUISITE',
};

/**
 * A diagnostic in the format of STANDARD 1.2.0 §9.8: a refusal of a call
 * names the tool, its capability (absent for an unbound or control-only
 * tool) and, where the runtime gives calls an id, the call; never a
 * workflow or a step.
 */
export interface Diagnostic {
  code: RefusalCode;
  name: string;
  severity: 'error';
  message: string;
  location: { tool: string; capability?: CapabilityId; call?: string };
  suggestion?: string;
}

/**
 * The layer and the configuration that decided a call (STANDARD 1.2.0
 * §5.18.8): the binding, its version, and the SHA-256 of the canonical JSON
 * of what decides the tool's calls: `{annotation, settings:
 * {checkpoint_max_age_ms}}` for a grounded tool, the annotation for a
 * control tool.
 */
export interface RecordedBy {
  name: string;
  version: string;
  config_sha256: string;
}

/** One checkpoint. `valid` turns false when a step that requires one uses it. */
export interface CheckpointRecord {
  id: string;
  valid: boolean;
  /** The trace entry of the `checkpoint` call that took it. */
  seq: number;
  at: number;
  /**
   * The execution (`state.execution.flowId`) it was taken in, or `null` when
   * taken outside one. A checkpoint authorises a call only within that
   * execution, so one taken outside an execution authorises nothing: see
   * `flowOf`.
   */
  flow_id: string | null;
}

/**
 * The execution a call belongs to. A thread that goes idle and runs again,
 * for instance after waiting for a person, starts a new execution with a new
 * `flowId` ("Unique execution ID"), and a checkpoint taken before that wait
 * describes a world that may have changed. The Standard says so of workflow
 * waits (STANDARD v1.1.0 §5.13, W608: "a checkpoint taken before it no
 * longer authorises the step"); an idle thread is the same situation.
 */
export function flowOf(state: { execution: { flowId: string } | null }): string | null {
  return state.execution?.flowId ?? null;
}

/** The model step of the execution a call belongs to (`stepCount`), or `null` outside an execution. */
export function stepOf(state: { execution: { stepCount: number } | null }): number | null {
  return state.execution?.stepCount ?? null;
}

/**
 * Who a party is, as the host authenticated it: an `agent_identity`
 * (STANDARD v1.2.0 §5.17, `schemas/agent_identity_schema.yaml`).
 */
export interface AgentIdentity {
  principal: string;
  kind: 'agent' | 'human' | 'service';
  role?: string;
  /** The family of the model it ran on, compared exactly (§5.15); a host derives it with `modelFamily`. */
  model_family?: string;
  /** The identifier of the model it ran on (§5.17). */
  model_id?: string;
  owner?: string;
  authenticated_by?: string;
  trust_class?: (typeof TRUST_CLASSES)[number];
}

/** One person's answer to an approval request. */
export interface ApprovalDecision {
  decision_id: string;
  decision: 'approved' | 'rejected';
  /** `ThreadUser.id` of the authenticated caller who decided. */
  approver: string;
  /**
   * The caller as an approver identity (§5.17), per the interop identity
   * map's `endpoint_caller`: see `approverIdentity`. Absent on a decision
   * an earlier version of the binding stored.
   */
  approver_identity?: AgentIdentity;
  at: number;
}

/**
 * An approval request and the decisions on it (STANDARD v1.1.0 §5.14). The
 * request is keyed by the digest of the shown values, so a decision can only
 * ever apply to exactly what the approver was shown.
 *
 * The request is written only by the tool that needs the approval.
 * `decisions` is not stored with it: each decision is under a key of its
 * own, and `readApproval` puts them together. See `decideApproval` for why.
 */
export interface ApprovalRecord {
  digest: string;
  /** What approvers see: the action, its capability and its arguments. */
  shown: Json[];
  min_approvers: number;
  /** When set, only a caller holding this application role may decide. */
  role?: string;
  requested_at: number;
  /**
   * How long a decision stays valid, in milliseconds: no approval is
   * accepted later than this after `requested_at`, and an approval counts
   * for this long after it was given. See `approvalState`.
   */
  expires_ms?: number;
  decisions: ApprovalDecision[];
  /** Set when a tool call ran under this approval: an approval is single-use. */
  used_at?: number;
  /** Earlier rounds for the same shown values: used, rejected or expired. */
  history?: ApprovalRound[];
}

/** A closed round of an approval request, kept so no decision is lost. */
export type ApprovalRound = Pick<ApprovalRecord, 'requested_at' | 'decisions' | 'used_at'>;

/** What happened to one tool call. */
export interface TraceEntry {
  seq: number;
  at: number;
  /** The execution the call ran in (`state.execution.flowId`), when there was one. */
  flow_id?: string;
  /** The model step of that execution (`state.execution.stepCount`). */
  step?: number;
  /** The tool's name. */
  action: string;
  /**
   * `null` for a tool call the audit hook saw that no grounded tool
   * recorded, and for a control-only tool's call (`control`).
   */
  capability: CapabilityId | null;
  /** A call of a control-only tool (`controlTool`): never refused. */
  control?: true;
  domain?: string;
  /**
   * `started` is written before the tool's own code runs and replaced when
   * it returns, so an entry that stays `started` is a call that was cut off
   * (an aborted execution, a lost process) after it may have acted.
   */
  status: 'started' | 'executed' | 'failed' | 'refused';
  /**
   * SHA-256 of the canonical JSON of the arguments; absent for an
   * unclassified call, and for arguments that have no canonical JSON.
   */
  args_digest?: string;
  /** Why the call was refused. */
  code?: RefusalCode;
  /** The failure's reason token (STANDARD 1.2.0 §5.19.7), when it has one. */
  reason_code?: 'below_minimum_confidence' | 'invalid_confidence';
  /** An applied domain profile required a person for the call (§5.21.3). */
  person_required?: true;
  /**
   * The `seq` of the composite whose invocation covered this call
   * (STANDARD 1.2.0 §5.18.4): a nested call skips the approval and the
   * checkpoint, which the composite's call used.
   */
  covered_by?: number;
  /**
   * The layer and configuration that decided the call (§5.18.8): on every
   * entry a grounded or control tool writes, refusals and failures of the
   * layer's own checks included. Absent only on an entry the audit hook
   * writes for a call no grounded tool recorded, which the layer did not
   * decide.
   */
  recorded_by?: RecordedBy;
  /** The checkpoint this call used (`requires_checkpoint`) or took (`checkpoint`). */
  checkpoint_id?: string;
  /**
   * The approval the call used. `approvers` are the approvers' principals
   * (`sa-user:<id>`), and `approver_identities` their identities, as the
   * deployment attests them (STANDARD v1.2.0 §5.17); the identities are
   * absent when a decision was stored without one.
   */
  approval?: { digest: string; approvers: string[]; approver_identities?: AgentIdentity[]; decision_ids: string[] };
  /**
   * The output's evidence anchors (§6.5), redacted (§6.7); a bare string or
   * another object is a deprecated legacy form, kept as given.
   */
  evidence_anchors?: Array<EvidenceAnchor | string | Json>;
  /** Filled in by the `tool_call_done` hook: a tool cannot see its own call id. */
  tool_call_id?: string;
  error?: string;
}

/** A trace entry waiting for the audit hook to supply its tool call id. */
export interface Unlinked {
  seq: number;
  action: string;
  /** The execution and model step the call was made in: only a hook of the same step may link it. */
  flow_id: string | null;
  step: number | null;
}

/** Whether a waiting entry belongs to the given execution and model step. */
export function samePosition(waiting: Unlinked, flow: string | null, step: number | null): boolean {
  return (waiting.flow_id ?? null) === flow && (waiting.step ?? null) === step;
}

/**
 * Whether a waiting entry can no longer be linked, as seen from a call or a
 * hook at the given position. Seen from an execution, an entry of any other
 * execution or model step cannot: the runtime runs one execution of a thread
 * at a time, and no model step starts between a call and its hook. Code
 * outside an execution, such as a thread endpoint, can run while an entry of
 * the execution waits for its hook, so from there no entry is stale.
 */
export function stale(waiting: Unlinked, flow: string | null, step: number | null): boolean {
  return flow !== null && !samePosition(waiting, flow, step);
}

/**
 * An entry's `error` and `evidence_anchors` with every secret replaced
 * (STANDARD v1.2.0 §6.7): always the default patterns and the secrets
 * registered layer-wide (`configureLayer({ secrets })`), plus `secrets`.
 * An anchor that held a secret loses its `digest` (`redactAnchor`). Nothing
 * else in an entry holds a value a call received.
 */
function redacted<T extends Partial<Pick<TraceEntry, 'error' | 'evidence_anchors'>>>(
  entry: T,
  secrets: readonly string[],
): T {
  const values = [...secrets, ...layerSecrets()];
  const out = { ...entry };
  if (typeof out.error === 'string') out.error = redactText(out.error, values);
  // An anchor that held a secret keeps no digest of what it cites
  // (`redactAnchor`): a digest of content that may be no more than the
  // secret could be inverted by guessing.
  if (Array.isArray(out.evidence_anchors)) {
    out.evidence_anchors = (out.evidence_anchors as Json[]).map((a) => redactAnchor(a, values).value);
  }
  return out;
}

/**
 * Append an entry to the thread's trace and return it with its sequence
 * number. The count is advanced before the entry is written, so a write that
 * fails part-way leaves a gap in the numbering, never an entry that the next
 * one overwrites. The entry is redacted first (§6.7), always: `secrets` adds
 * the host's own values to the default patterns and the layer's.
 */
export async function appendTrace(
  store: Store,
  entry: Omit<TraceEntry, 'seq'>,
  secrets: readonly string[] = [],
): Promise<TraceEntry> {
  const seq = ((await store.getValue<number>(KEYS.traceCount)) ?? 0) + 1;
  const stored: TraceEntry = { seq, ...redacted(entry, secrets) };
  await store.setValue(KEYS.traceCount, seq);
  await store.setValue(KEYS.trace(seq), stored);
  if ((stored.capability !== null || stored.control) && stored.tool_call_id === undefined) {
    const waiting: Unlinked = { seq, action: stored.action, flow_id: stored.flow_id ?? null, step: stored.step ?? null };
    // An entry of an earlier step can no longer be linked (see audit.ts).
    const unlinked = ((await store.getValue<Unlinked[]>(KEYS.unlinked)) ?? []).filter(
      (u) => !stale(u, waiting.flow_id, waiting.step),
    );
    await store.setValue(KEYS.unlinked, [...unlinked, waiting]);
  }
  await countExecuted(store, stored);
  return stored;
}

/** Replace a `started` entry with what became of the call, redacted as {@link appendTrace} redacts. */
export async function completeTrace(
  store: Store,
  started: TraceEntry,
  outcome: Pick<TraceEntry, 'at' | 'status' | 'code'> & Partial<Pick<TraceEntry, 'error' | 'evidence_anchors' | 'reason_code'>>,
  secrets: readonly string[] = [],
): Promise<TraceEntry> {
  const stored: TraceEntry = { ...started, ...redacted(outcome, secrets) };
  await store.setValue(KEYS.trace(stored.seq), stored);
  await countExecuted(store, stored);
  return stored;
}

/** Count an executed capability: what `requires` edges read. */
async function countExecuted(store: Store, stored: TraceEntry): Promise<void> {
  if (stored.capability === null || stored.status !== 'executed') return;
  const executed = await readExecuted(store);
  executed[stored.capability] = (executed[stored.capability] ?? 0) + 1;
  await store.setValue(KEYS.executed, executed);
}

/** How many times each capability has executed in this thread. */
export async function readExecuted(store: Store): Promise<Partial<Record<CapabilityId, number>>> {
  return (await store.getValue<Partial<Record<CapabilityId, number>>>(KEYS.executed)) ?? {};
}

/** The thread's trace, oldest first. */
export async function readTrace(store: Store): Promise<TraceEntry[]> {
  const count = (await store.getValue<number>(KEYS.traceCount)) ?? 0;
  const entries: TraceEntry[] = [];
  for (let seq = 1; seq <= count; seq += 1) {
    const entry = await store.getValue<TraceEntry>(KEYS.trace(seq));
    if (entry) entries.push(entry);
  }
  return entries;
}

export async function readCheckpoints(store: Store): Promise<CheckpointRecord[]> {
  return (await store.getValue<CheckpointRecord[]>(KEYS.checkpoints)) ?? [];
}

/**
 * An audit record (STANDARD v1.2.0 §6.4): an action record of
 * `schemas/world_state_schema.yaml`, with the members the binding fills.
 */
export interface ActionRecord {
  action_id: string;
  run_id: string;
  timestamp: string;
  actor: 'agent';
  intent: string;
  status: 'approved' | 'executed' | 'failed' | 'rejected';
  tool: string;
  capability?: string;
  call_id?: string;
  checkpoint_id?: string;
  code?: string;
  reason_code?: string;
  person_required?: true;
  approval?: {
    digest: string;
    decision: 'approved';
    approvers: string[];
    decision_id?: string;
    approver_identities?: AgentIdentity[];
  };
  details?: { args_digest?: string; flow_id?: string; step?: number; error?: string; covered_by?: string };
  recorded_by: { name: string; version?: string; config_sha256?: string };
}

/**
 * Who writes the binding's audit records (§6.4 `recorded_by`) when the entry
 * names no layer configuration: an entry the audit hook wrote for a call no
 * grounded tool recorded. Every other entry carries its own `recorded_by`
 * (§5.18.8), which the record keeps.
 */
export const RECORDED_BY = { name: '@acs/standard-agents-binding' } as const;

const STATUS: Record<TraceEntry['status'], ActionRecord['status']> = {
  executed: 'executed',
  failed: 'failed',
  // §6.4: `rejected` covers a refusal by a safety layer, with its code.
  refused: 'rejected',
  // Allowed, with no outcome yet: an entry that stays so was cut off.
  started: 'approved',
};

/**
 * A trace entry as an audit record (STANDARD v1.2.0 §6.4). The binding keeps
 * `TraceEntry` in the thread's store; this is the export the Standard allows
 * ("written in, or exported as"). `scope` names the records' scope, the
 * thread, as `run_id`, and prefixes `action_id`. `recorded_by` is the
 * entry's own (the layer, its version and `config_sha256`, §5.18.8), else
 * `RECORDED_BY`; a nested call's `details.covered_by` is the `action_id` of
 * the composite call that covered it (§5.18.4).
 */
export function actionRecord(entry: TraceEntry, scope: string): ActionRecord {
  const recordedBy: ActionRecord['recorded_by'] = entry.recorded_by ?? RECORDED_BY;
  const record: ActionRecord = {
    action_id: `${scope}/${entry.seq}`,
    run_id: scope,
    timestamp: new Date(entry.at).toISOString(),
    actor: 'agent',
    intent: `${entry.action} call`,
    status: STATUS[entry.status],
    tool: entry.action,
    recorded_by: { ...recordedBy },
  };
  if (entry.capability !== null) record.capability = entry.capability;
  if (entry.tool_call_id !== undefined) record.call_id = entry.tool_call_id;
  if (entry.checkpoint_id !== undefined) record.checkpoint_id = entry.checkpoint_id;
  if (entry.code !== undefined) record.code = entry.code;
  if (entry.reason_code !== undefined) record.reason_code = entry.reason_code;
  if (entry.person_required) record.person_required = true;
  if (entry.approval !== undefined) {
    const { digest, approvers, approver_identities, decision_ids } = entry.approval;
    record.approval = { digest, decision: 'approved', approvers: [...approvers] };
    if (decision_ids[0] !== undefined) record.approval.decision_id = decision_ids[0];
    if (approver_identities !== undefined) record.approval.approver_identities = approver_identities;
  }
  const details: NonNullable<ActionRecord['details']> = {};
  if (entry.args_digest !== undefined) details.args_digest = entry.args_digest;
  if (entry.flow_id !== undefined) details.flow_id = entry.flow_id;
  if (entry.step !== undefined) details.step = entry.step;
  if (entry.error !== undefined) details.error = entry.error;
  if (entry.covered_by !== undefined) details.covered_by = `${scope}/${entry.covered_by}`;
  if (Object.keys(details).length > 0) record.details = details;
  return record;
}
