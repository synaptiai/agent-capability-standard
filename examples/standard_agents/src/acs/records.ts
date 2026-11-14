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
import type { Json } from './canonical.js';
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

/** The ACS safety codes a grounded tool reports (STANDARD v1.1.0 §9.6). */
export type RefusalCode = 'F501' | 'F502' | 'F503';

export const CODE_NAMES: Record<RefusalCode, string> = {
  F501: 'CHECKPOINT_REQUIRED',
  F502: 'APPROVAL_REQUIRED',
  F503: 'ROLLBACK_FAILED',
};

/** A diagnostic in the format of STANDARD v1.1.0 §9.8. */
export interface Diagnostic {
  code: RefusalCode;
  name: string;
  severity: 'error';
  message: string;
  location: { tool: string; capability: CapabilityId };
  suggestion?: string;
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
   * execution: see `flowOf`.
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

/** One person's answer to an approval request. */
export interface ApprovalDecision {
  decision_id: string;
  decision: 'approved' | 'rejected';
  /** `ThreadUser.id` of the authenticated caller who decided. */
  approver: string;
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
  /** How long the approval stays valid after the last decision, in milliseconds. */
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
  /** The tool's name. */
  action: string;
  /** `null` for a tool call the audit hook saw that no grounded tool recorded. */
  capability: CapabilityId | null;
  domain?: string;
  /**
   * `started` is written before the tool's own code runs and replaced when
   * it returns, so an entry that stays `started` is a call that was cut off
   * (an aborted execution, a lost process) after it may have acted.
   */
  status: 'started' | 'executed' | 'failed' | 'refused';
  /** SHA-256 of the canonical JSON of the arguments; absent for an unclassified call. */
  args_digest?: string;
  /** Why the call was refused. */
  code?: RefusalCode;
  /** The checkpoint this call used (`requires_checkpoint`) or took (`checkpoint`). */
  checkpoint_id?: string;
  approval?: { digest: string; approvers: string[]; decision_ids: string[] };
  evidence_anchors?: Json[];
  /** Filled in by the `tool_call_done` hook: a tool cannot see its own call id. */
  tool_call_id?: string;
  error?: string;
}

/** A trace entry waiting for the audit hook to supply its tool call id. */
export interface Unlinked {
  seq: number;
  action: string;
}

/** Append an entry to the thread's trace and return it with its sequence number. */
export async function appendTrace(store: Store, entry: Omit<TraceEntry, 'seq'>): Promise<TraceEntry> {
  const seq = ((await store.getValue<number>(KEYS.traceCount)) ?? 0) + 1;
  const stored: TraceEntry = { seq, ...entry };
  await store.setValue(KEYS.trace(seq), stored);
  await store.setValue(KEYS.traceCount, seq);
  if (stored.capability !== null && stored.tool_call_id === undefined) {
    const unlinked = (await store.getValue<Unlinked[]>(KEYS.unlinked)) ?? [];
    await store.setValue(KEYS.unlinked, [...unlinked, { seq, action: stored.action }]);
  }
  await countExecuted(store, stored);
  return stored;
}

/** Replace a `started` entry with what became of the call. */
export async function completeTrace(
  store: Store,
  started: TraceEntry,
  outcome: Pick<TraceEntry, 'at' | 'status'> & Partial<Pick<TraceEntry, 'error' | 'evidence_anchors'>>,
): Promise<TraceEntry> {
  const stored: TraceEntry = { ...started, ...outcome };
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
