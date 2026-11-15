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
  /** Distinct approvers needed: an integer of at least 1 (default 1). */
  min_approvers?: number;
  /** Only a caller holding this application role may decide. */
  role?: string;
  /**
   * How long a decision stays valid, in milliseconds (more than zero). No
   * decision is accepted later than this after the request, as in the
   * reference executor, and an approval counts for this long after it was
   * given.
   */
  expires_ms?: number;
}

/**
 * What is wrong with `policy`, if anything. §5.14 makes `min_approvers` an
 * "integer ≥ 1" and `expires` "a duration longer than zero"; anything else
 * could let a call run on no decision, or never expire.
 */
export function policyProblems(policy: ApprovalPolicy): string[] {
  const problems: string[] = [];
  const { min_approvers, expires_ms } = policy;
  if (min_approvers !== undefined && !(Number.isInteger(min_approvers) && min_approvers >= 1)) {
    problems.push(`approval.min_approvers must be an integer of at least 1, not ${min_approvers}`);
  }
  if (expires_ms !== undefined && !(Number.isFinite(expires_ms) && expires_ms > 0)) {
    problems.push(`approval.expires_ms must be a finite number of milliseconds greater than zero, not ${expires_ms}`);
  }
  return problems;
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

/**
 * Where an approval request stands at time `now`.
 *
 * With `expires_ms`, an approval counts only while `now` is within
 * `expires_ms` of when it was given, and once `expires_ms` has passed since
 * the request, a request without enough such approvals is expired and
 * accepts no further decision. The reference executor likewise fixes the
 * deadline when the request is made (`core/src/exec/machine.rs`).
 */
export function approvalState(record: ApprovalRecord, now: number): ApprovalState {
  if (record.used_at !== undefined) return 'used';
  if (record.decisions.some((d) => d.decision === 'rejected')) return 'rejected';
  // A count §5.14 does not allow is never met.
  if (!Number.isInteger(record.min_approvers) || record.min_approvers < 1) return 'pending';
  const expires = record.expires_ms;
  if (expires !== undefined && !(expires > 0)) return 'expired';
  const counted = record.decisions.filter((d) => expires === undefined || now <= d.at + expires);
  if (new Set(counted.map((d) => d.approver)).size >= record.min_approvers) return 'approved';
  return expires !== undefined && now > record.requested_at + expires ? 'expired' : 'pending';
}

async function pending(store: Store): Promise<string[]> {
  return (await store.getValue<string[]>(KEYS.pendingApprovals)) ?? [];
}

/**
 * The round a request record is in: 1, then one more each time the same
 * values are asked for again after a round closed. A decision is made on
 * one round, so it cannot carry over to the next.
 */
export function approvalRound(record: Pick<ApprovalRecord, 'history'>): number {
  return (record.history?.length ?? 0) + 1;
}

/** The decisions of the request's current round, read from their own keys. */
async function readDecisions(store: Store, record: ApprovalRecord): Promise<ApprovalDecision[]> {
  const round = approvalRound(record);
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
  if (existing) {
    // The closed round is now in `history`, so its keys can go. They are
    // removed only after the new round is stored: a write that fails leaves
    // the closed round as it was, rejection included.
    const round = approvalRound(existing);
    for (const decision of existing.decisions) {
      await store.setValue(KEYS.approvedBy(digest, round, decision.approver), null);
    }
    await store.setValue(KEYS.approvers(digest, round), null);
    await store.setValue(KEYS.rejected(digest, round), null);
  }
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
 * `auth.caller` in a thread endpoint, and with the `round` the approver was
 * shown: a decision made on a list loaded before the round closed (rejected,
 * expired or used, then asked again) is refused instead of applying to the
 * next round. An approver counts once, and a request that is rejected,
 * expired or used accepts no further decision.
 *
 * Two decisions can arrive together: nothing serialises endpoint requests,
 * and the store has no conditional write. So a decision never rewrites the
 * request. A rejection sets one fixed key, which no other write can undo.
 * An approval is written under the approver's own key and then added to a
 * shared list; if two approvals collide the list can lose one, which leaves
 * the request pending until that approver decides again. The request can
 * lose an approval this way and never a rejection.
 *
 * A tool call can also use the request while a decision is being recorded.
 * So the request is read again after the decision is written, and the
 * decision is refused (`closed`) if a call has used the request, or asked
 * again, in between; `consumeApproval` does the same from the other side.
 */
export async function decideApproval(
  store: Store,
  approver: Approver,
  digest: string,
  decision: 'approved' | 'rejected',
  now: number,
  round?: number,
): Promise<ApprovalRecord> {
  const record = await readApproval(store, digest);
  if (!record) throw new ApprovalError('unknown_request', `no approval request has digest ${digest}`);
  if (record.role !== undefined && !(approver.roles ?? []).includes(record.role)) {
    throw new ApprovalError('not_authorized', `deciding this request needs the role '${record.role}'`);
  }
  const current = approvalRound(record);
  if (round !== undefined && round !== current) {
    throw new ApprovalError('closed', `round ${round} of this request is closed; the request is in round ${current}`);
  }
  const state = approvalState(record, now);
  if (state === 'rejected' || state === 'expired' || state === 'used') {
    throw new ApprovalError('closed', `the request is ${state} and accepts no decision`);
  }
  if (record.decisions.some((d) => d.approver === approver.id)) {
    throw new ApprovalError('already_decided', `${approver.id} has already decided this request`);
  }
  const entry: ApprovalDecision = {
    decision_id: `${digest.slice(0, 12)}-${current}.${approver.id}`,
    decision,
    approver: approver.id,
    at: now,
  };
  if (decision === 'rejected') {
    await store.setValue(KEYS.rejected(digest, current), entry);
  } else {
    await store.setValue(KEYS.approvedBy(digest, current, approver.id), entry);
    const listed = (await store.getValue<string[]>(KEYS.approvers(digest, current))) ?? [];
    if (!listed.includes(approver.id)) {
      await store.setValue(KEYS.approvers(digest, current), [...listed, approver.id]);
    }
  }
  const after = await readApproval(store, digest);
  if (!after || after.used_at !== undefined || approvalRound(after) !== current) {
    throw new ApprovalError(
      'closed',
      "a tool call took up this request while the decision was being recorded; the thread's trace shows whether that call ran",
    );
  }
  return after;
}

/**
 * Mark an approved request as used, so it authorises nothing further, and
 * return the rejection recorded in its round meanwhile, if there is one: the
 * call must then not run.
 *
 * A rejection can arrive after the caller read the request as approved. This
 * writes `used_at` and then looks for a rejection; `decideApproval` writes a
 * rejection and then looks for `used_at`. A value written "MUST be visible to
 * every subsequent `getValue(key)` on the same thread, across any execution
 * context" (Runtime, Durable Key-Value Store), so at least one of the two
 * sees the other: a rejection the endpoint reports as recorded always stops
 * the call. When this side sees one, the request is stored again without
 * `used_at`, so it reads as rejected.
 */
export async function consumeApproval(
  store: Store,
  record: ApprovalRecord,
  now: number,
): Promise<ApprovalDecision | null> {
  const stored: ApprovalRecord = { ...record, decisions: [] };
  await store.setValue(KEYS.approval(record.digest), { ...stored, used_at: now });
  const rejection = await store.getValue<ApprovalDecision>(KEYS.rejected(record.digest, approvalRound(record)));
  if (rejection) await store.setValue(KEYS.approval(record.digest), stored);
  return rejection;
}
