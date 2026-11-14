/**
 * Approval records (STANDARD v1.1.0 §5.14) for a Standard Agents thread.
 *
 * A grounded tool that needs approval calls `requestApproval`, which stores
 * what the approver must see under the digest of those values. A person then
 * decides through an authenticated thread endpoint, which calls
 * `decideApproval` with the caller the runtime authenticated. No model sits
 * between the caller and the record: the endpoint never reads model output.
 *
 * The runtime authenticates a caller; it does not say that the caller is a
 * person. A deployment has to keep every credential the runtime accepts out
 * of reach of the agent's tools, or a tool that can make HTTP requests could
 * decide its own request.
 */
import type { ThreadUser } from '@standardagents/spec';
import { digest as digestOf, type Json } from './canonical.js';
import { KEYS, type ApprovalDecision, type ApprovalRecord, type ApprovalRound, type Store } from './records.js';

export interface ApprovalPolicy {
  /** Distinct approvers needed (default 1). */
  min_approvers?: number;
  /** Only a caller holding this application role may decide. */
  role?: string;
  /** How long a decision stays valid, in milliseconds. */
  expires_ms?: number;
}

export type ApprovalState = 'pending' | 'approved' | 'rejected' | 'expired' | 'used';

/** The identity fields of the authenticated caller that a decision records. */
export type Approver = Pick<ThreadUser, 'id' | 'roles'>;

export class ApprovalError extends Error {
  constructor(
    readonly reason: 'unknown_request' | 'not_authorized' | 'already_decided' | 'closed',
    message: string,
  ) {
    super(message);
    this.name = 'ApprovalError';
  }
}

/** Where an approval request stands at time `now`. */
export function approvalState(record: ApprovalRecord, now: number): ApprovalState {
  if (record.used_at !== undefined) return 'used';
  if (record.decisions.some((d) => d.decision === 'rejected')) return 'rejected';
  const approvers = new Set(record.decisions.map((d) => d.approver));
  if (approvers.size < record.min_approvers) return 'pending';
  if (record.expires_ms !== undefined) {
    const decidedAt = Math.max(...record.decisions.map((d) => d.at));
    if (now > decidedAt + record.expires_ms) return 'expired';
  }
  return 'approved';
}

async function pending(store: Store): Promise<string[]> {
  return (await store.getValue<string[]>(KEYS.pendingApprovals)) ?? [];
}

/** The round a request record is in: 1, then one more each time it is asked again. */
function roundOf(record: Pick<ApprovalRecord, 'history'>): number {
  return (record.history?.length ?? 0) + 1;
}

/** The decisions of the request's current round, read from their own keys. */
async function readDecisions(store: Store, record: ApprovalRecord): Promise<ApprovalDecision[]> {
  const round = roundOf(record);
  const decisions: ApprovalDecision[] = [];
  for (const approver of (await store.getValue<string[]>(KEYS.approvers(record.digest, round))) ?? []) {
    const decision = await store.getValue<ApprovalDecision>(KEYS.approvedBy(record.digest, round, approver));
    if (decision) decisions.push(decision);
  }
  const rejection = await store.getValue<ApprovalDecision>(KEYS.rejected(record.digest, round));
  if (rejection) decisions.push(rejection);
  return decisions.sort((x, y) => x.at - y.at);
}

/**
 * Record that `shown` needs approval, unless a live request for exactly these
 * values already exists. Returns the request.
 */
export async function requestApproval(
  store: Store,
  shown: Json[],
  policy: ApprovalPolicy,
  now: number,
): Promise<ApprovalRecord> {
  const digest = await digestOf(shown);
  const existing = await readApproval(store, digest);
  if (existing) {
    const state = approvalState(existing, now);
    if (state === 'pending' || state === 'approved') return existing;
    // The round is closed and is kept in `history` below; its keys can go.
    const round = roundOf(existing);
    for (const decision of existing.decisions) {
      await store.setValue(KEYS.approvedBy(digest, round, decision.approver), null);
    }
    await store.setValue(KEYS.approvers(digest, round), null);
    await store.setValue(KEYS.rejected(digest, round), null);
  }
  const history: ApprovalRound[] = existing
    ? [
        ...(existing.history ?? []),
        {
          requested_at: existing.requested_at,
          decisions: existing.decisions,
          ...(existing.used_at !== undefined ? { used_at: existing.used_at } : {}),
        },
      ]
    : [];
  const record: ApprovalRecord = {
    digest,
    shown,
    min_approvers: policy.min_approvers ?? 1,
    requested_at: now,
    decisions: [],
    ...(policy.role !== undefined ? { role: policy.role } : {}),
    ...(policy.expires_ms !== undefined ? { expires_ms: policy.expires_ms } : {}),
    ...(history.length > 0 ? { history } : {}),
  };
  await store.setValue(KEYS.approval(digest), record);
  // The tool is the only writer of the list of open requests, so it also
  // drops the ones that are no longer pending.
  const open: string[] = [];
  for (const other of await pending(store)) {
    const request = other === digest ? null : await readApproval(store, other);
    if (request && approvalState(request, now) === 'pending') open.push(other);
  }
  await store.setValue(KEYS.pendingApprovals, [...open, digest]);
  return record;
}

/** The approval request for `digest` with the decisions made on it, if there is one. */
export async function readApproval(store: Store, digest: string): Promise<ApprovalRecord | null> {
  const record = await store.getValue<ApprovalRecord>(KEYS.approval(digest));
  return record ? { ...record, decisions: await readDecisions(store, record) } : null;
}

/** The requests still waiting for a decision, oldest first. */
export async function listPendingApprovals(store: Store, now: number): Promise<ApprovalRecord[]> {
  const records: ApprovalRecord[] = [];
  for (const digest of await pending(store)) {
    const record = await readApproval(store, digest);
    if (record && approvalState(record, now) === 'pending') records.push(record);
  }
  return records;
}

/**
 * Record `approver`'s decision on the request with this digest.
 *
 * Call it only with an identity the runtime authenticated, such as
 * `auth.caller` in a thread endpoint. An approver counts once, and a request
 * that is rejected, expired or used accepts no further decision.
 *
 * Two decisions can arrive together: nothing serialises endpoint requests,
 * and the store has no conditional write. So a decision never rewrites the
 * request. A rejection sets one fixed key, which no other write can undo.
 * An approval is written under the approver's own key and then added to a
 * shared list; if two approvals collide the list can lose one, which leaves
 * the request pending until that approver decides again. The request can
 * lose an approval this way and never a rejection.
 */
export async function decideApproval(
  store: Store,
  approver: Approver,
  digest: string,
  decision: 'approved' | 'rejected',
  now: number,
): Promise<ApprovalRecord> {
  const record = await readApproval(store, digest);
  if (!record) throw new ApprovalError('unknown_request', `no approval request has digest ${digest}`);
  if (record.role !== undefined && !(approver.roles ?? []).includes(record.role)) {
    throw new ApprovalError('not_authorized', `deciding this request needs the role '${record.role}'`);
  }
  const state = approvalState(record, now);
  if (state === 'rejected' || state === 'expired' || state === 'used') {
    throw new ApprovalError('closed', `the request is ${state} and accepts no decision`);
  }
  if (record.decisions.some((d) => d.approver === approver.id)) {
    throw new ApprovalError('already_decided', `${approver.id} has already decided this request`);
  }
  const round = roundOf(record);
  const entry: ApprovalDecision = {
    decision_id: `${digest.slice(0, 12)}-${round}.${approver.id}`,
    decision,
    approver: approver.id,
    at: now,
  };
  if (decision === 'rejected') {
    await store.setValue(KEYS.rejected(digest, round), entry);
  } else {
    await store.setValue(KEYS.approvedBy(digest, round, approver.id), entry);
    const listed = (await store.getValue<string[]>(KEYS.approvers(digest, round))) ?? [];
    if (!listed.includes(approver.id)) {
      await store.setValue(KEYS.approvers(digest, round), [...listed, approver.id]);
    }
  }
  return { ...record, decisions: await readDecisions(store, record) };
}

/** Mark an approved request as used, so it authorises nothing further. */
export async function consumeApproval(store: Store, record: ApprovalRecord, now: number): Promise<ApprovalRecord> {
  await store.setValue(KEYS.approval(record.digest), { ...record, decisions: [], used_at: now });
  return { ...record, used_at: now };
}
