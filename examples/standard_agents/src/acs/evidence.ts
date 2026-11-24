/**
 * Evidence of a Standard Agents thread (STANDARD v1.2.0 §6.5, §6.6).
 *
 * The binding keeps its evidence in the thread's trace (records.ts): each
 * executed call's `evidence_anchors`, redacted (§6.7). As an evidence store
 * (§6.6) the trace appends and never changes an entry; {@link getEvidence}
 * returns a record by its id, {@link findEvidence} the records whose
 * capability, anchor kind or run match, and {@link exportEvidenceJsonl} the
 * records as JSON Lines, each in append order. The thread store is
 * deleted with the thread, so its durability is `session`
 * ({@link EVIDENCE_STORE_INFO}): evidence that must outlive the thread is
 * exported, when it is written, to a durable store ({@link exportEvidence}
 * gives the thread's records in the common shape). When a call completes
 * with evidence anchors, the binding emits {@link EVIDENCE_EVENT} through
 * `state.emit`, delivered at most once and only to connected clients: a
 * notification, not the record.
 */
import type { ThreadState } from '@standardagents/spec';
import { isEvidenceAnchor, type EvidenceRecord, type EvidenceRecorded, type StoreInfo } from '@synaptiai/acs-core';
import { readTrace, type Store, type TraceEntry } from './records.js';

/** The notification's event name and `type` (§6.6). */
export const EVIDENCE_EVENT = 'acs.evidence_recorded';

/** What the thread store is, as an evidence store (§6.6): deleted with its thread, not bounded. */
export const EVIDENCE_STORE_INFO: StoreInfo = Object.freeze({ durability: 'session', bounded: false });

/** The `record_id` of the `index`th anchor of a trace entry: `<threadId>/<seq>/<index>`. */
export function recordId(threadId: string, seq: number, index: number): string {
  return `${threadId}/${seq}/${index}`;
}

function correlation(threadId: string, entry: TraceEntry): Omit<EvidenceRecord, 'record_id' | 'anchor' | 'recorded_at'> {
  return {
    run_id: entry.flow_id ?? threadId,
    ...(entry.step !== undefined ? { step: entry.step } : {}),
    ...(entry.capability !== null ? { capability: entry.capability } : {}),
    tool: entry.action,
    ...(entry.tool_call_id !== undefined ? { call_id: entry.tool_call_id } : {}),
  };
}

/**
 * The thread's evidence as `EvidenceRecord`s (`schemas/interop/evidence.schema.json`),
 * in trace order: every evidence anchor of every executed call; items that
 * are not evidence anchors (the deprecated legacy forms, §6.5) are skipped.
 */
export async function exportEvidence(state: Pick<ThreadState, 'threadId'> & Store): Promise<EvidenceRecord[]> {
  const records: EvidenceRecord[] = [];
  for (const entry of await readTrace(state)) {
    if (entry.status !== 'executed' || !Array.isArray(entry.evidence_anchors)) continue;
    entry.evidence_anchors.forEach((anchor, i) => {
      if (!isEvidenceAnchor(anchor)) return;
      records.push({
        record_id: recordId(state.threadId, entry.seq, i),
        anchor,
        recorded_at: new Date(entry.at).toISOString(),
        ...correlation(state.threadId, entry),
      });
    });
  }
  return records;
}

/** The record with `record_id` `id` (§6.6), or null when the thread holds none. */
export async function getEvidence(
  state: Pick<ThreadState, 'threadId'> & Store,
  id: string,
): Promise<EvidenceRecord | null> {
  return (await exportEvidence(state)).find((r) => r.record_id === id) ?? null;
}

/** A filter of {@link findEvidence}: each member given must match. */
export interface EvidenceFilter {
  capability?: string;
  /** The anchor's `kind` (§6.5). */
  kind?: string;
  run_id?: string;
}

/**
 * The records whose `capability`, `anchor.kind` and `run_id` match each
 * member of `filter` that is given (§6.6), in the order they were appended.
 */
export async function findEvidence(
  state: Pick<ThreadState, 'threadId'> & Store,
  filter: EvidenceFilter,
): Promise<EvidenceRecord[]> {
  return (await exportEvidence(state)).filter(
    (r) =>
      (filter.capability === undefined || r.capability === filter.capability) &&
      (filter.kind === undefined || r.anchor.kind === filter.kind) &&
      (filter.run_id === undefined || r.run_id === filter.run_id),
  );
}

/** The thread's records as JSON Lines, one `EvidenceRecord` per line, in append order (§6.6). */
export async function exportEvidenceJsonl(state: Pick<ThreadState, 'threadId'> & Store): Promise<string> {
  return (await exportEvidence(state)).map((r) => `${JSON.stringify(r)}\n`).join('');
}

/**
 * The notification for a completed trace entry, or null when it holds no
 * evidence anchor: the anchors' `ref`, `kind` and `digest` (no excerpt).
 * The entry is the one the binding stored, already redacted.
 */
export function evidenceNotification(threadId: string, entry: TraceEntry): EvidenceRecorded | null {
  const anchors = (entry.evidence_anchors ?? []).flatMap((a, i) =>
    isEvidenceAnchor(a) ? [{ i, ref: a.ref, kind: a.kind, digest: a.digest }] : [],
  );
  if (anchors.length === 0) return null;
  return {
    type: EVIDENCE_EVENT,
    record_ids: anchors.map((a) => recordId(threadId, entry.seq, a.i)),
    anchors: anchors.map(({ ref, kind, digest }) => ({ ref, kind, ...(digest !== undefined ? { digest } : {}) })),
    recorded_at: new Date(entry.at).toISOString(),
    ...correlation(threadId, entry),
  };
}

/**
 * Emit the notification for a completed entry through `state.emit`, when
 * the runtime has it. At most once, and never a failure of the call: an
 * `emit` that is missing or throws is ignored.
 */
export function notifyEvidence(state: ThreadState, entry: TraceEntry): void {
  try {
    const payload = evidenceNotification(state.threadId, entry);
    if (payload === null) return;
    const emit = (state as { emit?: unknown }).emit;
    if (typeof emit === 'function') (emit as (event: string, data?: unknown) => void).call(state, EVIDENCE_EVENT, payload);
  } catch {
    // A notification is not the record (§6.6): the call stands.
  }
}
